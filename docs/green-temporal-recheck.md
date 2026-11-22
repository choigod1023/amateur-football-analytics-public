# Green pitch candidates across time

Research only; this does not validate or activate a calibration. Existing green/line candidates were calculated at 2, 5, 8, 11, 14, 17 and 20 seconds in each of two 30-second fixed-camera clips from the same SoccerTrack match. Each segment yielded five candidates. Independently annotated pitch landmark coordinates were used only to evaluate the candidates; field corners were not included in the reported 61 checkpoint errors. The reference uses the provided 105 × 68 m pitch and source annotations, not independently measured GNSS field points. This match has been used repeatedly in development.

Combining the candidate corners by coordinate-wise median produced a median checkpoint error of 17.55 m for 60–90 seconds and 15.20 m for 120–150 seconds. Single-frame median checkpoint errors ranged from 18.23–21.25 m and 14.21–31.92 m respectively among returned candidates. Errors are spatial medians within each candidate; these are not independent samples or a field-wide guarantee. Even the combined result is far too inaccurate for tactical metric positions, and data from other games, camera motion, night footage and real players have not been tested. Temporal smoothing cannot fix systematic wrong line selection; the approach was not promoted to the server.

Run from the repository root using the locally obtained SoccerTrack files:

```powershell
..\football-coach-server\.venv\Scripts\python.exe scripts\evaluate_green_temporal.py ..\..\work\field-like\gnss\fisheye_keypoints.json ..\..\work\field-like\soccertrack-v1\match-20200220\0060_0090.mp4 ..\..\work\field-like\soccertrack-v1\match-20200220\0120_0150.mp4
```

Further work should identify individual lines and intersections, estimate camera/lens distortion, and assess independently measured landmarks across several unseen fields and cameras. Avoid using the same landmarks both for selecting a candidate and reporting its error.
