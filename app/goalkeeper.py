"""One rule for the goalkeeper of a team that is seen only as positions.

Depths are metres toward the goal the team attacks (u), so the own goal line is at u = -pitch_length / 2.
The deepest player is the goalkeeper only when he stands where a goalkeeper stands, close to the own goal line, and clearly behind the rest of the team.
A deepest player far from the goal line is a defender (the goalkeeper was not seen, which happens often on the far side), and he stays in the lines.
The old rules cut the deepest player whenever 8 players were seen (a defender was lost when the goalkeeper was missing) or only when the gap was 8 m or more
(a goalkeeper close behind a deep defence was counted as the last defender); this rule uses the place first and the gap second.
"""

PITCH_LENGTH = 89.0
NEAR_GOAL = 14.0          # metres from the own goal line within which the deepest player can be the goalkeeper
ALWAYS_GOALKEEPER = 6.0   # within this many metres of the goal line the deepest player is taken as the goalkeeper whatever the gap
MIN_GAP = 3.0             # otherwise he must stand this far behind the next player
MIN_PLAYERS = 8          # fewer players seen than this: nothing is cut


def goalkeeper_depth_is_keeper(depths, pitch_length=PITCH_LENGTH):
    """Sorted depths (deepest first) -> True when the first one is the goalkeeper."""
    if len(depths) < MIN_PLAYERS:
        return False
    from_goal_line = depths[0] + pitch_length / 2
    if from_goal_line > NEAR_GOAL:
        return False
    return from_goal_line <= ALWAYS_GOALKEEPER or depths[1] - depths[0] >= MIN_GAP


def without_goalkeeper(items, key=lambda item: item[0], pitch_length=PITCH_LENGTH):
    """Items sorted or not -> (items sorted by depth without the goalkeeper, whether a goalkeeper was taken out)."""
    ordered = sorted(items, key=key)
    if goalkeeper_depth_is_keeper([key(i) for i in ordered], pitch_length):
        return ordered[1:], True
    return ordered, False
