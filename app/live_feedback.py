"""Tactical feedback while the match is running: positions in, short coaching alerts out.

The offline report looks at a whole half and picks the best moments. A live feed cannot wait, so this module keeps only the last seconds of play and, once
per second, asks the same questions the report asks: are three or more of our players in the penalty area, did an opponent run past our back line, is our
front player alone, is our back line sinking, are our lines too far apart. An alert is sent when the answer is yes and the same kind has been quiet for
`cooldown` seconds, so a coach is not flooded: every kind has its own wait (COOLDOWN), no two alerts come closer than MIN_SPACING seconds and, when several kinds fire
in the same second, only the most important one (PRIORITY) is sent.

Input is metres on the pitch (x along the length, y across it) of the players of both teams, as the calibration turns tracked boxes into positions.
`direction` is +1 when the focus team attacks toward +x. There is no ball in this data, so no alert says who has the ball.
"""
import math
from collections import deque
from math import ceil
from statistics import median

from app.attack_options import analyse, describe
from app.event_miner import POLARITY, TITLES, smooth
from app.lane_forecast import forecast
from app.review_text import attack_instructions, coaching
from app.report_scenes import second_metrics
from app.tactical_concepts import BOX_DEPTH, BOX_HALF_WIDTH, runs_in_behind
from app.coaching_fields import fields as coaching_fields

TITLES = {**TITLES, 'gap_wide': '라인 간격 벌어짐', 'box_attack': '박스 안 선수 배치'}
POLARITY = {**POLARITY, 'gap_wide': 'poor', 'box_attack': 'info'}
MESSAGES = {
    'box_attack': '박스 안에 우리 선수가 {n}명 있습니다. 가까운 포스트, 먼 포스트, 뒤쪽 자리를 나눠 서세요',
    'run': '수비 라인 뒤로 침투가 나왔습니다. 공격 줄의 다른 선수도 같은 타이밍으로 출발하세요',
    'conceded_run': '상대가 우리 수비 라인 뒤로 뛰어 들어갔습니다. 수비 줄에서 가장 가까운 선수가 먼저 따라붙고 나머지 수비는 라인을 내리세요',
    'isolated': '앞선 선수가 6초 넘게 동료와 12미터 넘게 떨어져 있습니다. 중원 줄에서 가장 가까운 선수는 앞선 선수와 15미터 안으로 올라가 주세요',
    'line_drop': '우리 수비 라인이 10초 안에 {drop}미터 내려갔습니다(골키퍼 제외). 의도한 하프 라인 수비가 아니면 신호를 주고 함께 올리세요',
    'gap_wide': '공격 줄과 수비 줄이 {gap}미터 벌어져 있습니다(골키퍼 제외, 기준 {limit}미터). 중원 줄이 간격을 좁히세요',
}
# box_attack when the players in the box already stand spread over the box: the same alert, a text that keeps the places instead of asking to spread
SPREAD_MESSAGE = '박스 안에 우리 선수가 {n}명, 가로 약 {width}미터 깊이 약 {depth}미터로 이미 나눠 서 있습니다. 자리를 지키고 먼 포스트 쪽이 비지 않게 하세요'
SPREAD_WIDTH, SPREAD_DEPTH = 12.0, 8.0
# how far an alert can be trusted, from the marks of the coach on 108 alerts of this match (sessions gk2-h1, gk2-h2, 2026-11-16, right / marked): the counts are small
# and in-sample, they are shown so that the reader can see that. 'high' is a kind with 8 of 9 or better, 'reference' is a kind that was wrong in a third or more of its marks.
CONFIDENCE = {'box_attack': 'high', 'conceded_run': 'high', 'run': 'high', 'isolated': 'reference', 'gap_wide': 'reference', 'line_drop': 'reference'}
# Two sources, kept apart: the marks of the coach on this match (small, in-sample) and the replay of 20 professional matches (SkillCorner open data, 526 shots, 30 s window,
# scripts/research_rule_validity_skillcorner.py, 2026-11-17): how many times more often than usual a shot followed within 30 s. There is no amateur evidence of the second kind.
EVIDENCE = {'box_attack': '내 경기 판정 9개 중 8개 맞음, 프로 20경기에서 알림 뒤 30초 안에 슛이 평소의 3.2배',
            'conceded_run': '내 경기 판정 2개 중 2개 맞음, 프로 20경기에서 상대 슛이 평소의 2.2배',
            'run': '내 경기 판정 2개 중 2개 맞음, 프로 20경기에서 알림 뒤 슛이 평소의 2.1배',
            'isolated': '내 경기 판정 3개 중 2개 맞음, 프로 20경기에서 알림 뒤 슛이 평소의 1.4배(약한 관계)',
            'gap_wide': '꺼 둔 알림: 프로 20경기에서 알림 뒤 상대 슛이 평소의 0.4배(위험 신호가 아님)',
            'line_drop': '내 경기 판정 9개 중 4개 맞음, 프로 20경기에서 상대 슛이 평소의 1.4배(약한 관계)'}


ATTACK_KINDS = ('box_attack', 'isolated', 'run')                                                 # alerts about our own attack carry the passing lanes and the space of that moment
PRIORITY = ('box_attack', 'conceded_run', 'run', 'isolated', 'line_drop', 'gap_wide')       # when several things happen in one second only the first is sent
HOLD_SECONDS = 1.0           # a player missed by the detector stays where he was seen last for this long (the analysis looks at one moment per second)
SAME_PERSON = 1.0            # metres: two tracks closer than this are one person
COOLDOWN = {'box_attack': 20.0, 'conceded_run': 25.0, 'run': 25.0, 'isolated': 45.0, 'line_drop': 90.0, 'gap_wide': 90.0}
URGENT = ('box_attack', 'conceded_run')                                                          # these ignore MIN_SPACING: they are about the next few seconds
STATE_KINDS = ('line_drop', 'gap_wide')                                                          # these describe a state that can last minutes: one alert per episode, not one per cooldown
RELEASE = 30.0                                                                                  # seconds without the state before an episode is over and the same alert may come again
GAP_WIDE_MIN = 41.0         # metres between the front and back line: judged alerts at 32 were wrong 6 of 15, at 41 wrong 2 of 10 (same sample the value was chosen on, so it needs new judgements)
DISABLED_KINDS = ('gap_wide', 'isolated')   # off by default. gap_wide: replayed on public tracking (Metrica, 2 games) an alert was followed by an opponent shot 0.37x as often as usual, the coach marked it wrong in 6 of 15 (wiki/validation-data-plan.md). isolated: wrong in 6 of 7 at the 2026-11-20 night match (a low block keeps the striker up on purpose); switched off by the user (wiki/match-1120-live-and-report.md)
MIN_SPACING = 8.0                                                                            # seconds between any two alerts


PRESENT = (('가능했습니다', '가능합니다'), ('좁았습니다', '좁습니다'), ('몰려 있었습니다', '몰려 있습니다'), ('비어 있는 공간이었습니다', '비어 있는 공간입니다'),
           ('없었습니다', '없습니다'), ('서 있었고', '서 있고'), ('있었습니다', '있습니다'))


def present_tense(text):
    """The scene words of the report are written in the past tense (they describe a moment that is over); a live alert describes the moment now, so the endings are turned."""
    for past, now in PRESENT:
        text = text.replace(past, now)
    return text


class LiveAnalyzer:
    def __init__(self, direction, pitch_length=89.0, pitch_width=62.0, fps=5.0, cooldown=25.0, history=24.0, minimum_players=6, disabled=DISABLED_KINDS, tolerant_box=False):
        self.tolerant_box = tolerant_box        # True: a second in which the count in the box dipped (a player missed by the detector for more than HOLD_SECONDS) does not stop a box_attack; off by default, not yet judged on live alerts (wiki/srt-degradation-test-1118.md)
        self.disabled = tuple(disabled)          # kinds that are not sent (pass () to measure every kind, as the research script does)
        self.direction, self.length, self.width, self.fps = direction, pitch_length, pitch_width, fps
        self.cooldown, self.history, self.minimum = cooldown, history, minimum_players       # cooldown: the least wait for kinds without their own value in COOLDOWN
        self.last_any = -10 ** 9
        self.paths = {'team': {}, 'other': {}}
        self.series = {'team': {}, 'other': {}}
        self.isolation_series = {}
        self.gap_series = {}
        self.last_sample, self.last_second = -1, -1
        self.second_players = ([], [])
        self.last_alert = {}
        self.state_seen = {}                  # state kind -> last time the state was true
        self.state_sent = {}                  # state kind -> True while the alert of the running episode was sent
        self.box_seconds = {}                 # second -> most of our players in the box inside that second
        self.box_history = {}                 # second -> most of our players in the box (kept for the report of a run)
        self.placed = []                      # per closed second: players of our team and of the other team with and without holding (for the report of a run)
        self.frames = {}                      # sample -> {'team': [(track, x, y)], 'other': [...]}: the last seconds in metres, in the form app.attack_options reads

    def interrupt_observations(self, t):
        """Break unreliable trajectories without forgetting emitted-alert cooldowns.

        No trajectory or multi-second rule may bridge an invalid observation.
        A fresh analyser is reserved for a genuinely new source/time domain.
        """
        self.paths = {'team': {}, 'other': {}}
        self.series = {'team': {}, 'other': {}}
        self.isolation_series.clear()
        self.gap_series.clear()
        self.frames.clear()
        self.box_seconds.clear()
        self.second_players = ([], [])
        self.last_second = -1
        self.last_sample = max(self.last_sample, int(round(t * self.fps)))

    # -- input ---------------------------------------------------------------------------------------------------------------------
    def update(self, t, team, other):
        """One observation at stream time `t` seconds. team / other: [(track id, x, y)] in metres. Returns the alerts raised by it (a list of dicts)."""
        sample = int(round(t * self.fps))
        if sample <= self.last_sample:
            return []
        self.last_sample = sample
        sign = {'team': self.direction, 'other': -self.direction}
        for name, players in (('team', team), ('other', other)):
            for tid, x, y in players:
                self.paths[name].setdefault(tid, deque()).append((sample, x * sign[name], y))
        self.frames[sample] = {'team': list(team), 'other': list(other), 'time': t}
        horizon = sample - int(self.history * self.fps)
        for old in [k for k in self.frames if k < horizon]:
            del self.frames[old]
        for name in self.paths:
            for tid in list(self.paths[name]):
                path = self.paths[name][tid]
                while path and path[0][0] < horizon:
                    path.popleft()
                if not path:
                    del self.paths[name][tid]
        second = int(sample / self.fps)
        in_box = sum(1 for tid, x, y in self.held('team', sample) if x * self.direction >= self.length / 2 - BOX_DEPTH and abs(y) <= BOX_HALF_WIDTH)
        self.box_seconds[second] = max(self.box_seconds.get(second, 0), in_box)
        self.box_history[second] = self.box_seconds[second]
        if second == self.last_second:
            self.second_players = (list(team), list(other))
            return []
        previous, self.last_second = self.last_second, second
        previous_players = self.second_players
        self.second_players = (list(team), list(other))
        if previous < 0:
            return []
        # The first frame of this second must not be backdated into the previous second (false line jumps at occlusions and reappearances):
        # the closed second is described by the players held as its LAST frame shows them (a player missed in one frame is still counted).
        last = max((k for k in self.frames if int(k / self.fps) == previous), default=sample - 1)
        held_team, held_other = self.held('team', last), self.held('other', last)
        self.placed.append((len(held_team), len(held_other), len(previous_players[0]), len(previous_players[1])))
        self._close_second(previous, held_team, held_other)
        return self._check(t, previous)

    def held(self, name, sample, seconds=HOLD_SECONDS, apart=SAME_PERSON):
        """The players of one side as the last `seconds` show them: every track at the place where it was seen last (a player the detector missed in this one frame is still there),
        and two tracks closer than `apart` metres are one person (the newer track is kept; a track that was lost and found again under a new number is not counted twice)."""
        latest = {}
        for k in range(sample - int(round(seconds * self.fps)), sample + 1):
            for tid, x, y in (self.frames.get(k) or {}).get(name, []):
                latest[tid] = (k, x, y)
        kept = []
        for tid, (k, x, y) in sorted(latest.items(), key=lambda item: -item[1][0]):
            if all(math.hypot(x - ox, y - oy) >= apart for _, ox, oy in kept):
                kept.append((tid, x, y))
        return kept

    def _close_second(self, second, team, other):
        # A final-frame dropout must not erase a whole second of observations.
        # Aggregate scalar measurements only; never invent or carry positions.
        measured = []
        for frame, people in self.frames.items():
            if int(frame / self.fps) != second:
                continue
            metric = second_metrics(people['team'], people['other'], self.direction, self.minimum)
            if metric:
                measured.append(metric)
        if len(measured) >= max(1, int(self.fps * .6 + .999999)):
            self.isolation_series[second] = {
                'centre': median(m['centre'] for m in measured),
                'leader_isolation': median(m['leader_isolation'] for m in measured),
                'observed_samples': len(measured),
                'leader_ids': sorted({str(m['leader']) for m in measured}),
            }
            gaps = [m['attack_line']-m['defence_line'] for m in measured]
            self.gap_series[second] = {'observed_samples': len(gaps),
                'support_samples': sum(g > GAP_WIDE_MIN for g in gaps), 'median_gap_m': float(median(gaps))}
        for old in [s for s in self.gap_series if s < second - int(self.history)]:
            del self.gap_series[old]
        for old in [s for s in self.isolation_series if s < second - int(self.history)]:
            del self.isolation_series[old]
        mine = second_metrics(team, other, self.direction, self.minimum)
        theirs = second_metrics(other, team, -self.direction, self.minimum)
        if mine:
            self.series['team'][second] = mine
        if theirs:
            self.series['other'][second] = theirs
        for name in self.series:
            for old in [s for s in self.series[name] if s < second - int(self.history)]:
                del self.series[name][old]
        for old in [s for s in self.box_seconds if s < second - int(self.history)]:
            del self.box_seconds[old]

    # -- the questions -------------------------------------------------------------------------------------------------------------------
    def _check(self, t, second):
        # A delayed/reconnected input must not publish a stale completed window
        # as if it described the current scene.
        if t - (second + 1) > 1.5 / self.fps:
            return []
        found = []
        team, other = self.series['team'], self.series['other']
        # three or more of ours in the penalty area for two seconds
        if self.tolerant_box:
            # per-second maxima: a second in which the count dipped (a player missed for longer than HOLD_SECONDS) does not stop the alert (option, off by default)
            in_box = lambda s: max(self.box_seconds.get(s, 0), self.box_seconds.get(s - 1, 0))
            if all(in_box(s) >= 3 for s in (second - 1, second)):
                found.append(('box_attack', {'n': min(in_box(second), in_box(second - 1)), **self.box_shape()}))
        else:
            # Require every expected sample in two completed seconds. Per-second
            # maxima mistake two brief sightings for sustained box occupation.
            box_frames = [self.frames.get(s) for s in range(ceil((second - 1) * self.fps), ceil((second + 1) * self.fps))]
            if (box_frames and all(box_frames)
                    and t - box_frames[-1]['time'] <= 1.5 / self.fps
                    and all(b['time'] - a['time'] <= 1.5 / self.fps for a, b in zip(box_frames, box_frames[1:]))):
                counts = [sum(1 for _, x, y in f['team']
                              if self.length / 2 - BOX_DEPTH <= x * self.direction <= self.length / 2
                              and abs(y) <= BOX_HALF_WIDTH) for f in box_frames]
                if min(counts) >= 3:
                    found.append(('box_attack', {'n': min(counts), 'observation_window_s': 2,
                                                 'observed_samples': len(counts), 'counts': counts, **self.box_shape()}))
        # our front player alone in the opponent half for six seconds
        recent = [self.isolation_series.get(s) for s in range(second - 5, second + 1)]
        if all(m and m['centre'] > 0 and m['leader_isolation'] > 12.0 for m in recent):
            found.append(('isolated', {'measurement': 'median_observed_samples_per_second',
                                      'observed_samples_per_second': [m['observed_samples'] for m in recent],
                                      'leader_ids': sorted({tid for m in recent for tid in m['leader_ids']}),
                                      'same_player_continuity_verified': False}))
        # lines too far apart for five seconds
        recent = [self.gap_series.get(s) for s in range(second - 4, second + 1)]
        if all(m and m['support_samples'] >= ceil(self.fps * .6) for m in recent):
            found.append(('gap_wide', {'gap': int(round(min(m['median_gap_m'] for m in recent))), 'observation_window_s': 5, 'threshold_m': GAP_WIDE_MIN,
                'observed_samples_per_second': [m['observed_samples'] for m in recent],
                'support_samples_per_second': [m['support_samples'] for m in recent],
                'median_gap_m_per_second': [m['median_gap_m'] for m in recent]}))
        # our back line sinking by 10 metres within 10 seconds (the opponent sees it as a line moving toward our goal)
        line_other = smooth({s: m['opponent_back_line'] for s, m in other.items()})
        if second in line_other and any(second - d in line_other and line_other[second] - line_other[second - d] >= 14.0 for d in range(1, 11)):
            drop = int(round(max(line_other[second] - line_other[second - d] for d in range(1, 11) if second - d in line_other)))
            found.append(('line_drop', {'drop': drop, **self.retreat_evidence(second)}))
        # runs past a back line, finished in the last two seconds
        for kind, runner, line_of in (('run', 'team', team), ('conceded_run', 'other', other)):
            back = smooth({s: m['opponent_back_line'] for s, m in line_of.items()}) if line_of else {}
            if not back:
                continue
            tail = {tid: [(f, u, y) for f, u, y in path if f >= (second - 6) * self.fps] for tid, path in self.paths[runner].items()}
            runs = runs_in_behind({tid: p for tid, p in tail.items() if len(p) >= 6}, back, self.fps, window=4.0)
            if any(r['end'] >= second - 2 for r in runs):
                found.append((kind, {}))
        found = [f for f in found if f[0] not in self.disabled]
        present = {kind for kind, _facts in found}
        for kind in STATE_KINDS:
            if kind in present:
                ongoing = t - self.state_seen.get(kind, -10 ** 9) <= RELEASE
                self.state_seen[kind] = t
                if not ongoing:
                    self.state_sent[kind] = False
            elif t - self.state_seen.get(kind, -10 ** 9) > RELEASE:
                self.state_sent[kind] = False
        alerts = []
        for kind, facts in sorted(found, key=lambda f: PRIORITY.index(f[0]) if f[0] in PRIORITY else 99):
            unconfirmed_retreat = kind == 'line_drop' and not facts.get('retreat_supported')
            if t - self.last_alert.get(kind, -10 ** 9) < COOLDOWN.get(kind, self.cooldown) or (t - self.last_any < MIN_SPACING and kind not in URGENT):
                continue
            if kind in STATE_KINDS and self.state_sent.get(kind):
                continue                                                                          # the same state goes on: it was said once
            if kind in STATE_KINDS:
                self.state_sent[kind] = True
            self.last_alert[kind] = t
            # A diagnostic observation is not an actionable coaching instruction
            # and must not hide a subsequently supported attack alert for 8 s.
            if not unconfirmed_retreat:
                self.last_any = t
            try:
                tips = coaching({'kind': kind}, {})
            except Exception:
                tips = {'rules': [], 'drill': None}
            text = self.message(kind, facts)
            if unconfirmed_retreat:
                text = '관측 수비선 위치가 바뀌었지만 같은 선수들의 후퇴는 확인되지 않았습니다. 선수 누락과 라인 구성을 먼저 확인하세요'
                tips = {'rules': [], 'drill': None}
            separated = coaching_fields(kind, facts, text)
            text = separated['observation'] + ' ' + separated['suggestion']
            # Keep legacy rules consistent with the same evidence-limited directive.
            tips = {'rules': [separated['suggestion']] if separated['directive']['status'] == 'conditional' else [],
                    'drill': None}
            alerts.append({'time': round(t, 1), 'kind': kind, 'polarity': 'info' if unconfirmed_retreat else POLARITY.get(kind, 'info'), 'title': '수비선 관측 변동' if unconfirmed_retreat else TITLES.get(kind, kind),
                           'text': text, 'rules': tips.get('rules', []), 'drill': tips.get('drill'),
                           'detail': self.attack_detail() if kind in ATTACK_KINDS else None,
                           'confidence': CONFIDENCE.get(kind, 'reference'), 'evidence_note': EVIDENCE.get(kind, ''),
                           'evidence': {'basis': 'player_positions', 'ball_observed': False,
                                        'identity_accuracy_verified': False, 'position_accuracy_verified': False,
                                        'tactical_correctness_verified': False, **facts},
                           **separated})
        return alerts

    def box_shape(self):
        """How the players of our team in the penalty area stand now: {'width': metres across, 'depth': metres along the pitch}; empty when fewer than two are there."""
        inside = [(x * self.direction, y) for _, x, y in self.held('team', self.last_sample) if x * self.direction >= self.length / 2 - BOX_DEPTH and abs(y) <= BOX_HALF_WIDTH]
        if len(inside) < 2:
            return {}
        return {'width': int(round(max(y for _, y in inside) - min(y for _, y in inside))), 'depth': int(round(max(u for u, _ in inside) - min(u for u, _ in inside)))}

    @staticmethod
    def message(kind, facts):
        """The one line of an alert. Numbers of the moment are put in; a kind without its numbers falls back to the plain words."""
        template = MESSAGES.get(kind, TITLES.get(kind, kind))
        if kind == 'box_attack' and facts.get('width', 0) >= SPREAD_WIDTH and facts.get('depth', 0) >= SPREAD_DEPTH:
            template = SPREAD_MESSAGE
        try:
            return template.format(n=facts.get('n', 0), width=facts.get('width', 0), depth=facts.get('depth', 0), gap=facts.get('gap', 0), drop=facts.get('drop', 0), limit=int(GAP_WIDE_MIN))
        except (KeyError, IndexError):
            return TITLES.get(kind, kind)

    def retreat_evidence(self, second):
        """Check whether shared tracked people actually moved towards their own goal.

        A changed clustering boundary is not itself retreat. This corroboration
        is heuristic (three shared IDs, median retreat >= half the 14 m trigger),
        not proof that those IDs stayed on the same people.
        """
        def people(s):
            samples = [f for f in self.frames if int(f / self.fps) == s]
            return {tid: x * self.direction for tid, x, _ in self.frames[max(samples)]['team']} if samples else {}
        current = people(second)
        evidence = {'retreat_supported': False, 'shared_tracks': 0, 'median_retreat_m': None}
        for seconds_back in range(1, 11):
            previous = people(second - seconds_back)
            common = current.keys() & previous.keys()
            if len(common) < 3:
                continue
            movement = float(median(previous[t] - current[t] for t in common))
            if evidence['median_retreat_m'] is None or movement > evidence['median_retreat_m']:
                evidence = {'retreat_supported': movement >= 7.0, 'shared_tracks': len(common),
                            'median_retreat_m': round(movement, 2), 'comparison_seconds': seconds_back}
        return evidence

    def attack_detail(self, horizon=1.5):
        """The passing lanes and the space at the latest sample, in the words of the report: {'line', 'scene', 'space', 'carrier', 'lanes', 'closing', 'advice'} or None.

        The player with the ball is not known, so the lanes start from the most advanced player. `closing` are the lanes that are open now and that a straight-line forecast
        of every player (app.lane_forecast) puts behind a defender within `horizon` seconds: on recorded matches such a call was right in about 6 of 10 cases and found about half
        of the lanes that closed, so it is shown as a hint ('may close')."""
        t = self.last_sample / self.fps
        facts = analyse(self.frames, 'team', 'other', self.direction, self.fps, 0.0, t)
        if not facts:
            return None
        words = describe(self.frames, 'team', 'other', self.direction, self.fps, 0.0, t, facts, self.length, self.width) or {'scene': [], 'space': []}
        lanes = facts['lanes']
        closing = [l['track'] for l in forecast(self.frames, 'team', 'other', self.direction, self.fps, facts['frame'], facts['carrier'], horizon) if l['open_now'] and not l['open_later']]
        total, opened = len(lanes), sum(1 for l in lanes if l['open'])
        if total:
            share = opened / total
            state = '모두 막혀 있습니다' if opened == 0 else '대부분 막혀 있습니다' if share <= 0.3 else '많이 열려 있습니다' if share >= 0.6 else '절반쯤 열려 있습니다'
            line = f'앞선 선수가 줄 수 있는 패스길이 {state}({total}곳 중 {opened}곳 열림)' + (f', 열린 길 중 {len(closing)}곳은 곧 닫힐 수 있습니다' if closing else '')
        else:
            line = '앞선 선수가 줄 수 있는 패스길을 아직 알 수 없습니다'
        if words['space']:
            line += ' · ' + present_tense(words['space'][0])
        return {'line': line, 'scene': words['scene'], 'space': words['space'], 'carrier': facts['carrier'], 'closing': closing, 'advice': attack_instructions(facts, False)[:2],
                'carrier_source': 'most_advanced_player_proxy', 'ball_observed': False,
                'lanes': [{'track': l['track'], 'open': l['open'], 'blocker': l['blocker'], 'across': l['across'], 'forward': l['forward']} for l in lanes]}
