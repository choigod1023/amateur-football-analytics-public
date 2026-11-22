# Unlabelled team-colour temporal smoothing: exploratory oracle audit

The current model clusters unlabelled shirt histograms once; its distance and
margin gates can reject unstable or small crops. Prior cross-match supervised
metric and frozen ResNet experiments failed to improve the held-out footage;
see `team-continuity-research.md`. The hypothesis here was that averaging
features from the same track could stabilize the colour evidence before the
existing gate. This experiment is inference only, not new model training.

Reproduce, using the separately obtained local SoccerTrack files:

```powershell
..\football-coach-server\.venv\Scripts\python.exe scripts/research_team_feature_smoothing.py ../../work/field-like/soccertrack-v1/match-20200220 --frames 80
```

The first ten frames initialise colour clusters without labels. Ground truth
from those frames only maps the arbitrary cluster numbers to the team labels
for scoring; it does not fit the colour features or cluster centres. Later,
80 contiguous frames (101–180, one-indexed) in each segment are scored. GT
bounding boxes and persistent GT IDs are supplied for all frames. Models have
no access to team labels in those frames. EMA uses up to eight previous valid
histograms; no prediction is made for a missing crop and history resets after
a gap greater than three frames. Counts are observations, not independent
players or matches.

| Segment | Method | Correct | Wrong | Unknown |
|---|---|---:|---:|---:|
| 60–90 s | Baseline | 779 | 75 | 906 |
| 60–90 s | EMA alpha 0.3 | 785 | 82 | 893 |
| 60–90 s | EMA alpha 0.7 | 791 | 76 | 893 |
| 60–90 s | Mean of last 3 | 778 | 77 | 905 |
| 120–150 s | Baseline | 706 | 117 | 937 |
| 120–150 s | EMA alpha 0.3 | 733 | 116 | 911 |
| 120–150 s | EMA alpha 0.7 | 719 | 120 | 921 |
| 120–150 s | Mean of last 3 | 726 | 116 | 918 |

The apparent coverage gain is small and not robust: the first segment has more
wrong assignments. This is an optimistic oracle experiment using one game and
stable ground-truth identities; real tracker ID switches can contaminate
history. This new feature-smoothing experiment has **not** been evaluated on
actual detections. It cannot measure unmatched detections or separate referee
and goalkeeper errors. Previous actual-detection continuity experiments are
reported separately in `team-continuity-research.md`; those results do not
validate this different method. No change was made to the live server.

Next evaluation must use independently trained detection, tracker-produced IDs,
matched and unmatched detections reported separately, and independently
labelled role/team examples across multiple games, lighting and cameras. Treat
team IDs as provisional, do not infer that unmatched detections are referees,
and do not promote smoothing to tactical calculations without those checks.
