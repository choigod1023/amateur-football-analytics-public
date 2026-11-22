"""Who is who: the roster of the two teams and the answer to 'which player is this track?' for the tracks of a recorded half.

The tracker follows a person for some seconds or minutes and then loses him or swaps him with a neighbour, so a half is made of several hundred short tracks. A person (or an app in
the same room) looks at three small pictures of each track, picks the player from the roster, and answers 'same person?' for the pairs of tracks that follow each other close in time and place.
Both answers are kept as plain files next to the review labels and nothing is guessed from them:

  <store>/players/roster.json            the players: id, team, name, number, position (a code of app.position_slots.POSITIONS)
  <store>/players/<half>/index.json      the tracks of a half and the candidate pairs, written by scripts/prepare_player_review.py, with the pictures next to it
  <store>/players/assign/<half>.json     track id -> player id
  <store>/players/links/<half>.json      {'same': [[a, b], ...], 'different': [[a, b], ...]}

A track gets the player of its own answer, or else the answer of any track that is linked to it with 'same' (links join tracks into groups). If two answers in one group disagree, the group is
marked as in conflict and nothing is guessed.
"""
import json
import hashlib
from datetime import datetime, timezone
import re
import threading
from pathlib import Path

from app.position_slots import POSITIONS

LINE_OF = {'GK': 'GK', 'DF': 'DF', 'LB': 'DF', 'LCB': 'DF', 'CB': 'DF', 'RCB': 'DF', 'RB': 'DF', 'LWB': 'DF', 'RWB': 'DF', 'defence': 'DF',
           'MF': 'MF', 'LM': 'MF', 'LCM': 'MF', 'CM': 'MF', 'RCM': 'MF', 'RM': 'MF', 'midfield': 'MF',
           'FW': 'FW', 'LW': 'FW', 'RW': 'FW', 'LS': 'FW', 'ST': 'FW', 'RS': 'FW', 'attack': 'FW'}
REACH_BASE, REACH_SPEED, MAX_GAP = 4.0, 5.0, 90.0          # metres allowed at no gap, metres per second a player may run between two tracks, the longest gap offered
HALF = re.compile(r'^[a-z0-9]{1,12}$')
TRACK = re.compile(r'^[A-Za-z0-9_-]{1,20}$')
PLAYER = re.compile(r'^[a-z0-9_]{1,20}$')
IMAGE = re.compile(r'^[A-Za-z0-9_-]{1,40}\.(jpg|mp4)$')


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def _read(path, default):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


class PlayerIdentity:
    def __init__(self, directory):
        self.root = Path(directory) / 'players'
        self.lock = threading.Lock()

    # -- roster ----------------------------------------------------------------------------------------------------------------------
    def roster(self):
        return _read(self.root / 'roster.json', [])

    def set_player(self, ident, team, name, number, position):
        """Add a player or change one. ident '' makes a new id. Returns the saved player. Raises ValueError for a wrong team, number or position."""
        with self.lock:
            if team not in ('A', 'B'):
                raise ValueError('Team must be A or B')
            name = (name or '').strip()[:30]
            if not name and number in (None, ''):
                raise ValueError('A name or a number is needed')
            if number in (None, ''):
                number = None
            else:
                try:
                    number = int(number)
                except (TypeError, ValueError) as exc:
                    raise ValueError('The number must be a whole number') from exc
                if not 0 <= number <= 99:
                    raise ValueError('The number must be between 0 and 99')
            if position not in ('', None) and position not in POSITIONS:
                raise ValueError('Unknown position')
            players = self.roster()
            if ident:
                if not PLAYER.match(ident) or not any(p['id'] == ident for p in players):
                    raise ValueError('Unknown player')
            else:
                taken = {p['id'] for p in players}
                counter = 1
                while f'p{counter}' in taken:
                    counter += 1
                ident = f'p{counter}'
            if number is not None and any(p['team'] == team and p['number'] == number and p['id'] != ident for p in players):
                raise ValueError('This number is already used in this team')
            saved = {'id': ident, 'team': team, 'name': name, 'number': number, 'position': position or ''}
            players = [p for p in players if p['id'] != ident] + [saved]
            _write(self.root / 'roster.json', sorted(players, key=lambda p: (p['team'], p['number'] if p['number'] is not None else 100, p['name'])))
            return saved

    def delete_player(self, ident):
        """Remove a player from the roster and every answer that named him. Returns True when he was in the roster."""
        with self.lock:
            players = self.roster()
            if not any(p['id'] == ident for p in players):
                return False
            _write(self.root / 'roster.json', [p for p in players if p['id'] != ident])
            for path in (self.root / 'assign').glob('*.json') if (self.root / 'assign').is_dir() else []:
                answers = _read(path, {})
                kept = {t: p for t, p in answers.items() if p != ident}
                if kept != answers:
                    _write(path, kept)
            return True

    # -- tracks ----------------------------------------------------------------------------------------------------------------------
    def halves(self):
        if not self.root.is_dir():
            return []
        return [p.name for p in sorted(self.root.iterdir()) if p.is_dir() and HALF.match(p.name) and (p / 'index.json').is_file()]

    def _groups(self, half, tracks):
        """{track id: group id} from the 'same' links (union-find); tracks without a link are alone."""
        parent = {t: t for t in tracks}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for a, b in _read(self.root / 'links' / f'{half}.json', {}).get('same', []):
            if a in parent and b in parent:
                parent[find(a)] = find(b)
        return {t: find(t) for t in tracks}

    @staticmethod
    def _fingerprint(track):
        # A reused track id after retracking must not inherit a previous confirmation.
        identity = {k: track.get(k) for k in ('id', 'team', 'first', 'last', 'rows', 'first_pos', 'last_pos')}
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def _evidence(self, half, index, answers, links):
        records = _read(self.root / 'provenance' / f'{half}.json', {})
        auto = _read(self.root / 'auto_notes.json', {}).get('notes', {}).get(half, {})
        tracks = {t['id']: t for t in index.get('tracks', [])}
        sources, confirmed = {}, {}
        for tid, player in answers.items():
            record = records.get('assign', {}).get(tid, {})
            valid = (tid in tracks and record.get('player') == player and record.get('source') == 'human'
                     and record.get('fingerprint') == self._fingerprint(tracks[tid]))
            sources[tid] = 'human_confirmed' if valid else ('auto_unconfirmed' if tid in auto else 'legacy_unknown')
            if valid:
                confirmed[tid] = {player}
        # Only explicitly confirmed links propagate a verified assignment. Historical
        # links remain available in the UI, but their source cannot be reconstructed.
        edges = []
        for a, b in links.get('same', []):
            key = '|'.join(sorted((a, b)))
            r = records.get('links', {}).get(key, {})
            if (a in tracks and b in tracks and r.get('relation') == 'same' and r.get('source') == 'human'
                    and r.get('fingerprints') == {t: self._fingerprint(tracks[t]) for t in (a, b)}):
                edges.append((a, b))
        changed = True
        while changed:
            changed = False
            for a, b in edges:
                values = confirmed.get(a, set()) | confirmed.get(b, set())
                if values != confirmed.get(a, set()) or values != confirmed.get(b, set()):
                    confirmed[a] = set(values)
                    confirmed[b] = set(values)
                    changed = True
        return sources, confirmed

    def state(self, half):
        """The tracks of a half with the answers and the candidate pairs that still wait for an answer, or None for an unknown half."""
        if not HALF.match(half or ''):
            return None
        index = _read(self.root / half / 'index.json', {})
        if not index:
            return None
        with self.lock:
            answers = _read(self.root / 'assign' / f'{half}.json', {})
            links = _read(self.root / 'links' / f'{half}.json', {})
            roster = {p['id']: p for p in self.roster()}
            suggestions = _read(self.root / 'suggestions' / f'{half}.json', {})
            ids = [t['id'] for t in index.get('tracks', [])]
            groups = self._groups(half, ids)
            sources, confirmed = self._evidence(half, index, answers, links)
            contradicted_groups = {groups[a] for a, b in links.get('different', [])
                                   if a in groups and b in groups and groups[a] == groups[b]}
            by_group = {}
            for t in ids:
                if t in answers and answers[t] in roster:
                    by_group.setdefault(groups[t], set()).add(answers[t])
            tracks = []
            for t in index.get('tracks', []):
                own = answers.get(t['id']) if answers.get(t['id']) in roster else None
                members = by_group.get(groups[t['id']], set())
                verified = confirmed.get(t['id'], set())
                evidence = sources.get(t['id'], 'unassigned')
                group_conflict = len(members) > 1 or groups[t['id']] in contradicted_groups
                confirmed_player = next(iter(verified)) if len(verified) == 1 and not group_conflict else None
                if own is None and members:
                    evidence = 'human_confirmed_link' if confirmed_player else 'unverified_link'
                tracks.append({**t, 'suggestion': suggestions.get(t['id']), 'player': own, 'player_by_link': (next(iter(members)) if len(members) == 1 and own is None else None), 'conflict': group_conflict,
                               'assignment_evidence': evidence, 'confirmed_player': confirmed_player, 'group': groups[t['id']], 'group_size': sum(1 for g in groups.values() if g == groups[t['id']])})
            answered = {(min(a, b), max(a, b)) for key in ('same', 'different') for a, b in links.get(key, [])}
            candidates = [c for c in index.get('candidates', []) if (min(c['a'], c['b']), max(c['a'], c['b'])) not in answered]
            done = sum(1 for t in tracks if t['player'] or t['player_by_link'])
            return {'half': half, 'name': index.get('name', half), 'tracks': tracks, 'candidates': candidates[:200], 'candidates_left': len(candidates), 'done': done, 'total': len(tracks),
                    'roster': list(roster.values()), 'formation': index.get('formation')}

    def _track_ids(self, half):
        return {t['id'] for t in _read(self.root / half / 'index.json', {}).get('tracks', [])}

    def assign(self, half, track, player):
        """Answer 'which player is this track' (player '' clears the answer). Raises ValueError for an unknown half, track or player."""
        with self.lock:
            if not HALF.match(half or '') or track not in self._track_ids(half):
                raise ValueError('Unknown track')
            roster = {p['id'] for p in self.roster()}
            if player and player not in roster:
                raise ValueError('Unknown player')
            path = self.root / 'assign' / f'{half}.json'
            answers = _read(path, {})
            if player:
                team = next(t['team'] for t in _read(self.root / half / 'index.json', {})['tracks'] if t['id'] == track)
                wanted = next(p['team'] for p in self.roster() if p['id'] == player)
                if team != wanted:
                    raise ValueError('The track is of the other team')
                answers[track] = player
            else:
                answers.pop(track, None)
            provenance_path = self.root / 'provenance' / f'{half}.json'
            provenance = _read(provenance_path, {})
            entry = provenance.setdefault('assign', {})
            if player:
                track_data = next(t for t in _read(self.root / half / 'index.json', {})['tracks'] if t['id'] == track)
                entry[track] = {'player': player, 'source': 'human', 'fingerprint': self._fingerprint(track_data),
                                'confirmed_at': datetime.now(timezone.utc).isoformat()}
            else:
                entry.pop(track, None)
            # A failure between files is conservative: a mismatched sidecar never confirms an answer.
            _write(path, answers)
            _write(provenance_path, provenance)
            return player or None

    def link(self, half, a, b, relation):
        """Answer 'is it the same person?' for two tracks: relation 'same', 'different' or '' (clear). Raises ValueError for unknown tracks or relation."""
        with self.lock:
            ids = self._track_ids(half) if HALF.match(half or '') else set()
            if a not in ids or b not in ids or a == b:
                raise ValueError('Unknown tracks')
            if relation not in ('same', 'different', ''):
                raise ValueError('Unknown relation')
            path = self.root / 'links' / f'{half}.json'
            links = _read(path, {})
            pair = sorted([a, b])
            for key in ('same', 'different'):
                links[key] = [p for p in links.get(key, []) if sorted(p) != pair]
            if relation:
                links[relation].append(pair)
            provenance_path = self.root / 'provenance' / f'{half}.json'
            provenance = _read(provenance_path, {})
            entry = provenance.setdefault('links', {})
            key = '|'.join(pair)
            if relation:
                tracks = {t['id']: t for t in _read(self.root / half / 'index.json', {})['tracks']}
                entry[key] = {'relation': relation, 'source': 'human',
                              'fingerprints': {t: self._fingerprint(tracks[t]) for t in pair},
                              'confirmed_at': datetime.now(timezone.utc).isoformat()}
            else:
                entry.pop(key, None)
            _write(path, links)
            _write(provenance_path, provenance)
            return relation or None

    def image(self, half, name):
        if not HALF.match(half or '') or not IMAGE.match(name or ''):
            return None
        path = self.root / half / name
        return path if path.is_file() else None

    # -- chains: one player at a time ------------------------------------------------------------------------------------------------
    def set_reject(self, half, player, track, rejected=True):
        """Remember that `track` is not `player` (so that it is not offered again); rejected False takes the note back."""
        with self.lock:
            if not HALF.match(half or '') or track not in self._track_ids(half) or not any(p['id'] == player for p in self.roster()):
                raise ValueError('Unknown track or player')
            path = self.root / 'rejects' / f'{half}.json'
            notes = _read(path, {})
            current = [t for t in notes.get(player, []) if t != track]
            if rejected:
                current.append(track)
            notes[player] = current
            _write(path, notes)
            return rejected

    def chain(self, half, player, limit=10):
        """What to look at next for one player: his tracks so far and the tracks that may be his, best first. None for an unknown half. Raises ValueError for an unknown player.

        With no track yet the player is started from the tracks of his team whose position line (defence, midfield, attack) fits his roster position, the longest first. With tracks, a
        track is offered when it follows or precedes one of them within MAX_GAP seconds without overlapping any, and the place where one ends is within REACH_BASE + REACH_SPEED * gap metres
        of the place where the other begins; the nearer in place and time the better. A fitting position line counts in its favour, a different one against. Tracks already given to another
        player (also through links), tracks in conflict and tracks rejected for this player are left out."""
        state = self.state(half)
        if state is None:
            return None
        roster = {p['id']: p for p in state['roster']}
        if player not in roster:
            raise ValueError('Unknown player')
        want = LINE_OF.get(roster[player]['position'])
        team = roster[player]['team']
        rejected = set(_read(self.root / 'rejects' / f'{half}.json', {}).get(player, []))
        owner = {t['id']: t['player'] or t['player_by_link'] for t in state['tracks']}
        mine = sorted([t for t in state['tracks'] if owner[t['id']] == player], key=lambda t: t['first'])

        number = roster[player]['number']

        def hint(track):
            """-0.5 for a clearly read number that is the player's, +0.8 for another clearly read number, +2 for a track marked to skip (referee, spectator)."""
            sug = track.get('suggestion') or {}
            if sug.get('level') == 'skip':
                return 2.0
            if sug.get('number') is None or number is None:
                return 0.0
            weight = 1.0 if sug.get('level') == 'clear' else 0.5
            return -0.5 * weight if sug['number'] == number else 0.8 * weight

        def fits(track):
            line = LINE_OF.get(track.get('slot'))
            return None if want is None or line is None else line == want

        def free(track):
            return track['team'] == team and not owner[track['id']] and not track['conflict'] and track['id'] not in rejected
        offers = []
        if not mine:
            for t in state['tracks']:
                if free(t):
                    offers.append({**t, 'direction': None, 'gap': None, 'distance': None, 'line_match': fits(t), 'anchor': None})
            offers.sort(key=lambda t: (hint(t), t['line_match'] is not True, -t['rows']))
        else:
            for t in state['tracks']:
                if not free(t) or any(min(t['last'], m['last']) - max(t['first'], m['first']) > 1.0 for m in mine):
                    continue
                best = None
                for m in mine:
                    if 'first_pos' not in t or 'first_pos' not in m:
                        continue
                    if t['first'] >= m['last']:
                        gap, a, b, direction = t['first'] - m['last'], m['last_pos'], t['first_pos'], 'after'
                    elif t['last'] <= m['first']:
                        gap, a, b, direction = m['first'] - t['last'], t['last_pos'], m['first_pos'], 'before'
                    else:
                        continue
                    distance = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                    reach = REACH_BASE + REACH_SPEED * gap
                    if gap > MAX_GAP or distance > reach:
                        continue
                    cost = distance / min(reach, 40.0) + gap / MAX_GAP                # a long gap makes any distance possible, so it is the nearness in time and place that ranks
                    if best is None or cost < best[0]:
                        best = (cost, gap, distance, direction, m['id'])
                if best is None:
                    continue
                match = fits(t)
                offers.append({**t, 'direction': best[3], 'gap': round(best[1], 1), 'distance': round(best[2], 1), 'line_match': match, 'anchor': best[4],
                               '_rank': best[0] - (0.4 if match is True else 0.0) + (0.6 if match is False else 0.0) + hint(t)})
            offers.sort(key=lambda t: t['_rank'])
            for o in offers:
                o.pop('_rank', None)
        seconds = sum(t['last'] - t['first'] for t in mine)
        return {'half': half, 'player': roster[player], 'mine': mine, 'seconds': round(seconds, 1), 'offers': offers[:limit], 'offers_total': len(offers), 'line': want}
