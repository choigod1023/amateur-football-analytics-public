"""A rough expected-goals value of a shot from where it was taken (distance and angle to the goal), nothing else.

p = 1 / (1 + exp(-(A + B * distance + C * angle)))   distance in metres to the goal centre, angle = angle in radians under which the two posts are seen.

The three numbers were fitted to six round reference values that are commonly quoted for open-play shots (about 35 % from the middle of the small box, 12 % from the penalty spot,
5 % from 20 m, 2 % from 30 m, 6 % from 12 m and 10 m wide, 10 % from 8 m and 8 m wide). They are NOT taken from a published model and were NOT checked against amateur football:
use the values to compare chances inside one report (which shot was better), not as true probabilities. The body part, the type of pass, the defenders and the goalkeeper are not in the model.
Coordinates are our team's view: our goal at u = -L/2, we attack toward +u; `attacks_right` says which goal the shooter attacks.
"""
import math

A, B, C = -2.319, -0.066, 1.743
GOAL_WIDTH = 7.32


def angle_of(depth, lateral):
    """Angle (rad) under which the posts are seen from a point `depth` metres in front of the goal line and `lateral` metres off the goal centre."""
    value = math.atan2(GOAL_WIDTH * depth, depth * depth + lateral * lateral - (GOAL_WIDTH / 2) ** 2)
    return value if value >= 0 else value + math.pi


def xg(u, v, attacks_right=True, pitch_length=89.0):
    """xG of a shot taken at (u, v) metres (our view) at the goal the shooter attacks."""
    goal_u = pitch_length / 2 if attacks_right else -pitch_length / 2
    depth = max(0.5, abs(goal_u - u))
    lateral = abs(v)
    distance = math.hypot(depth, lateral)
    z = A + B * distance + C * angle_of(depth, lateral)
    return 1.0 / (1.0 + math.exp(-z))
