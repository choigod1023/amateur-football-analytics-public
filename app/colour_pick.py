"""Which pairs of colour groups of a team-colour sample the live run could tell apart, and how clearly (2026-11-25 colour pick).

The live run decides once at its start whether the bib-pixel reader is on (app/small_box_team.reader_decision): ON when the hue gap of the two team
colours is at least MIN_HUE_GAP_DEG (50 degrees) and both colours have a chroma of at least MIN_CENTRE_CHROMA (17.97). This module applies the same
rule to every pair of groups of a sample (scripts/team_select_prepare.py), without changing the rule or its values:

- pair_clarity(): min(hue gap / 50, chroma 1 / 17.97, chroma 2 / 17.97). The run's rule is ON exactly when this is at least 1; larger = clearer.
- sample_score(): the clearest pair of groups that both have MIN_PER_TEAM people or more; 'on' when that pair is ON.
  A sample is "clear" (no automatic retake) when it has such an ON pair. Of several samples the one with the largest clarity is used.
"""
from itertools import combinations

from app.small_box_team import MIN_CENTRE_CHROMA, MIN_HUE_GAP_DEG, hue_chroma, reader_decision
from app.team_color_profile import MIN_PER_TEAM, make_profile


def pair_clarity(centre_a, centre_b):
    hue_a, chroma_a = hue_chroma(centre_a)
    hue_b, chroma_b = hue_chroma(centre_b)
    gap = abs((hue_a - hue_b + 180.0) % 360.0 - 180.0)
    return {'gap': round(gap, 1), 'chromas': [round(chroma_a, 1), round(chroma_b, 1)],
            'clarity': round(min(gap / MIN_HUE_GAP_DEG, chroma_a / MIN_CENTRE_CHROMA, chroma_b / MIN_CENTRE_CHROMA), 3)}


def pairs(split, min_people=MIN_PER_TEAM):
    """Every pair (i, j) of groups with min_people or more each: [{i, j, on, line, gap, chromas, clarity}], clearest first."""
    groups = split.get('groups') or []
    out = []
    for i, j in combinations(range(len(groups)), 2):
        if min(len(groups[i]['members']), len(groups[j]['members'])) < min_people:
            continue
        on, line = reader_decision(make_profile(split, i, opponent_group=j) if len(groups) > 2 else make_profile(split, i))
        out.append({'i': i, 'j': j, 'on': bool(on), 'line': line, **pair_clarity(groups[i]['centre'], groups[j]['centre'])})
    return sorted(out, key=lambda p: -p['clarity'])


def sample_score(split):
    """{'on': any pair ON, 'clarity': of the clearest pair (None without pairs), 'best': that pair or None}."""
    found = pairs(split)
    if not found:
        return {'on': False, 'clarity': None, 'best': None}
    return {'on': any(p['on'] for p in found), 'clarity': found[0]['clarity'], 'best': found[0]}
