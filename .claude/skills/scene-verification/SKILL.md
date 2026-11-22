---
name: scene-verification
description: Use whenever a sub-agent in the football match video project must check a match moment against the real video before anything is written or drawn about it - a transition, a regain, a goal, "nobody marked him", "the flank was empty", "our defender with the ball", player counts in a zone, or a pattern counted over many scenes. Gives the frame-grid commands, the time base, the ball and stoppage rules and the fixed result table. Use it even when the moment was already picked from position logs or tracking, because those picks have been wrong (foul stoppages, missing far-side players, hidden markers).
---

# 장면을 영상으로 확인하기 (하위 작업용)

자세한 절차: `wiki/agents/task-cards/scene-check.md`(한 순간), 여러 장면 횟수는 `wiki/agents/task-cards/scene-count.md`. 이 스킬은 반드시 할 확인만 다시 적습니다.

## 시간 기준
- h1 = `<WORK_DIR>/work/match-1120/halves/first_half.mp4`, h2 = `second_half.mp4`. 위치 기록의 `time`과 같은 초입니다.
- 11-20 경기 시계 = 파일 초 - 25(전반), - 57(후반). 전반 파일과 후반 및 그 뒤 구간이 들어 있는 파일은 시간 기준이 달라 쓰지 않습니다.

## 명령 (파이썬은 `outputs/football-coach-server/.venv/Scripts/python.exe -X utf8`)
- 격자: `work/match-1120/coach/hl/grid.py <1|2> <키 초>` → `hl/grids/h<반>_<초>.jpg`, 키 초 -4~+4초 9장.
- 확대: 뒤에 `1 x0 y0 x1 y1`(16:9 픽셀 영역) → `_c.jpg`. 0.5초 간격은 세 번째 인자 `0.5`.
- 다른 영상: `scripts/scene_check_frames.py --video <파일> --times <초> --before 4 --after 4 --out-dir <폴더>`.
- 구역 선(11-20 전용, 작업 폴더 `<WORK_DIR>`에서 실행): `work/match-1120/tactics-deep/zones.py front|attack|ring <출력.jpg> h2:382 ...`.

## 반드시 할 확인
1. 정지(L01): 9장 중 쓰러진 선수, 심판 접근, 땅에 놓인 공, 절반 이상 걷기가 하나라도 있으면 "정지 포함". 전환·압박 장면으로 쓰지 않습니다.
2. 공(L05, L08): 장마다 공 픽셀 위치 또는 "안 보임". 2초 넘게 10픽셀 안에 머문 흰 점은 공이 아닙니다. "공 가진, 공 쪽" 문장은 공을 찾았을 때만.
3. 비어 있음(L02, L03): 그 구역을 확대해 사람 0명일 때만. 주장 선수 5m 안에 다른 색 옷이 겹치면 "1대1".
4. 인원(L04): 구역을 미터로 정하고 선을 그려 셉니다. 눈대중 인원은 적지 않습니다.
5. 추적 번호로 한 선수의 달리기를 이야기하지 않습니다(L22).

## 결과 표 (`result.md`, 빈 칸 없음)
| 초 | 공 위치(x,y 또는 안 보임) | 정지 신호 | 주장 관련 인원 | 메모 |
- 주장마다 판정: 맞음 / 틀림 / 확인 못 함. 사진에서 센 값은 "모델 판정(사람 아님)"(L23).

## 보고
| 한 일 | 근거 파일 | 수치와 표본 크기 | 확인한 것 | 확인 못 한 것 | 불확실한 사실 |
- "공 위치를 적은 장 9장 중 n장"을 수치 칸에 넣습니다.
