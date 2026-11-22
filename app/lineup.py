"""The line-up that a person typed in before the match, for the half-time report (optional: no file, no line-up section).

<store>/service/lineup.json, written by hand:
  {"formation": "3-4-1-2", "players": [{"role": "GK", "name": "...", "note": "what the coach wants from this place (optional)"}, ...]}

The report shows exactly what was typed. Nothing is inferred: the tracker does not know who a player is (the study of names is stopped), so no dot of the picture is given a name and no
measured value is attached to a name. A file that is damaged or too big is ignored (the report then has no line-up section) and the reason is returned for the page.
"""
import json
import re
from pathlib import Path

MAX_PLAYERS = 18
CONTROL = re.compile(r'[\x00-\x1f\x7f]')


def _text(value, limit):
    return CONTROL.sub('', value).strip()[:limit] if isinstance(value, str) else ''


def load_lineup(directory):
    """-> {'formation': str, 'players': [{'role', 'name', 'note'}]} or None when there is no usable file."""
    path = Path(directory) / 'service' / 'lineup.json'
    try:
        if path.stat().st_size > 20000:
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get('players'), list):
        return None
    players = []
    for item in data['players'][:MAX_PLAYERS]:
        if not isinstance(item, dict):
            continue
        role, name = _text(item.get('role'), 12), _text(item.get('name'), 20)
        if role and name:
            players.append({'role': role, 'name': name, 'note': _text(item.get('note'), 80)})
    if not players:
        return None
    return {'formation': _text(data.get('formation'), 12), 'players': players}
