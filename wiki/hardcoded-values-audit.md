# 고정값 전수 조사: 왜 하드코딩했고, 어디까지 바꿀 수 있는가

작성: 2026-11-21. 코드는 읽기만 했고 바꾸지 않았습니다(GPU, 다운로드, 재시작 없음). 근거는 `app/`, `scripts/`, `web/`, 경기 11-20 분석 스크립트 5개(`work/match-1120/reanalysis/run_min20.py`, `coach/coach_4231.py`, `coach/coach_numbers.py`, `coach/deep.py`, `position-metrics/features.py`)와 시작 스크립트의 실제 줄입니다. 줄 번호는 2026-11-21 작업 폴더 기준이고(커밋 전 수정이 섞여 있음), 줄이 밀리면 값으로 다시 찾습니다. 이 페이지는 `wiki/match-1120-live-and-report.md`의 "고정값이 들어간 이유 (2026-11-20 밤 조사)"(7개 값)를 넓힌 것이며, 그 표와 다른 결론은 없습니다.

전제(사용자님 말씀, 2026-11-21): 카메라는 앞으로도 지금 자리(관중석 위, cam4 구도)에 두고 1080p로 송출합니다. 4K 촬영도, 두 번째 카메라도 없습니다. 그래서 경기장과 카메라에만 달린 값은 경기마다 다시 정하지 않고 한 곳에 모아 적어 둡니다. 멀리 있는 작은 선수와 겹친 선수는 카메라를 바꿔서가 아니라 검출 설정, 학습, 추적으로 다룹니다.

## 1. 한눈에 보는 답: 왜 하드코딩했고, 동적 할당이 왜 안 되는가

### 왜 하드코딩했는가
- 값 대부분은 하나의 경기에서 급히 정한 숫자입니다. 표의 59개 항목 가운데 "왜 고정했나"에 근거(주석, 커밋, 위키)가 있는 것은 37개, "근거 없음"으로 적은 것은 22개입니다(5절 목록. 한 행에 값이 여럿이면 일부만 근거가 없어도 포함). 근거가 있는 것도 "같은 표본에서 고른 값"이 많습니다(예: 옷 색 최소 키 30픽셀은 11월 11일 라벨 35장면, 라인 간격 41m는 판정 15개).
- 커밋 메시지가 이유를 담은 경우는 없었습니다. 이 조사에서 `git log -S`로 찾은 값 20여 개의 메시지는 모두 기능 이름(예: "Add live tactical feedback engine ...")이고 값의 이유는 코드 옆 주석과 위키에만 있었습니다. 옷 색 값들은 11-20의 합친 커밋 하나로 들어왔습니다.
- 라이브 코드에는 "한 경기, 한 카메라 자리, 한 조명"에서 확인한 값을 기본값으로 둔 것이 많고, 다른 경기에서 확인하는 단계가 없었습니다. 11월 20일에 틀린 것은 모두 이 유형입니다.

### 왜 동적 할당이 안 되는가 (이유 네 가지)
1. 정답이 없어서입니다. 알림 기준(12m, 14m, 41m, 쿨다운)은 사람 판정(경기당 수십 개)으로만 맞출 수 있고, 공 위치가 없어 "이 알림이 좋았는가"를 자동으로 잴 수 없습니다.
2. 사람이 정하는 값이기 때문입니다. 우리 팀 옷, 공격 방향, 계획한 포메이션 좌표, 상대 이름은 경기 전에 코치가 정하고 코드가 추측할 수 없습니다.
3. 틀리면 라이브가 멈추거나 말없이 틀린 숫자가 나가기 때문입니다. 수신 주소, 보정, 팀 색은 자동으로 정하더라도 사람이 한 번 보고 눌러야 안전합니다.
4. 이미 있는 자동 추정이 라이브에 연결되지 않았습니다. 팀 색 프로필(`/team-select`), 시작 점검(`scripts/startup_check.py`), 카메라 이동 감지(`app/camera_drift.py`)는 있지만 시작 스크립트가 쓰도록 강제하지 않아서, 11-20에는 손으로 넘겼습니다.

### 묶음별 항목 수 (표의 "그룹" 칸 기준, 합계 59)
| 그룹 | 뜻 | 항목 수 |
|---|---|---|
| 1 | 지금도 고정이 맞는 것(물리 상수, 안전 한계, 보안 제한) | 8 |
| 2 | 경기장과 카메라 고정값: 경기장 설정 파일 한 곳에 모으면 되는 것 | 19 |
| 3 | 경기별 설정으로 빼면 되는 단순 작업 | 17 |
| 4 | 자동으로 정할 수 있지만 안전장치(사람 한 번 확인)가 필요한 것 | 7 |
| 5 | 지금 기술로는 자동이 어려운 것 | 8 |

### 그룹 1: 지금도 고정이 맞는 것
페널티 지역 16.5m와 폭 40.32m(`app/tactical_concepts.py:11-12`), 규격 경기장 표(`app/pitch_map.py:13`), 서버의 Host와 Origin 검사(`app/review_public.py:229-231`)와 로컬 전용 검사(`app/main.py:110`), 디스크 30GB 경고, 입력 끊김 판정 시간, GPU 감시 한계(8GB, 12GB, 90%, 95%)가 여기 듭니다. 이유는 규칙이나 안전 한계이지 경기에 따라 변하는 값이 아니기 때문입니다. 다만 "조용히 잘라 버리는" 한계(`MAX_ALERTS = 300`)는 잘렸다는 표시를 화면에 넣어야 합니다.

### 그룹 2: 경기장과 카메라 고정값 (경기장 설정 파일 한 곳)
경기장 크기 89 x 62m, 보정 파일과 카메라 이름 cam4, 위쪽 자르는 비율(`TOP`, `PITCH_TOP`), 타일 384, 확대 768, 신뢰도 0.10, 옷 색 최소 키, 경기장 경계 여유(`PITCH_MARGIN`), 영상 크기와 프레임 속도, 비트레이트 한계가 여기 듭니다. 지금은 같은 값이 코드 여러 곳에 따로 적혀 있습니다(경기장 크기는 `app/` 17곳, `web/` 5곳, `scripts/` 27개 파일). 카메라가 안 움직이는 한 경기마다 다시 구할 필요가 없고, 한 파일에 모아 모든 코드가 읽게 하면 됩니다. 이미 `work/venue-1120/calibrations.json`의 `cam4.pitch`에 경기장 크기가 들어 있는데 코드 대부분이 읽지 않고 89와 62를 다시 적습니다. 삼각대가 움직이지 않았는지는 매번 새로 추정하지 않고 선 일치 점수로 점검합니다(7절).

### 그룹 3: 경기별 설정으로 빼면 되는 것 (단순 작업)
수신 주소와 환경값(`DEMO_*`), 서버 주소, 경기 이름과 보고서 문구, 저장 폴더, 전반 공격 방향, 킥오프와 하프타임 시각, 포메이션 계획 좌표와 선수 명단, 꺼 둘 알림 종류, 야간용 명령줄 값(`--detector-imgsz 1280`, `--dark-min 0.15`)이 여기 듭니다. 모두 사람이 아는 값이므로 파일 한 장(`match.json`)에 적고 코드가 읽게 하면 됩니다. 핵심은 빠뜨리면 시작하지 않는 점검입니다(7절).

### 그룹 4: 자동으로 정할 수 있지만 안전장치가 필요한 것
- 우리 팀 옷 색(상자 색 묶음, `/team-select`에 이미 있음). 안전장치: 묶음 대표 사진을 벤치 화면에 그리고 코치가 "우리 팀"을 한 번 누르면 적용합니다. 심판이나 관중이 섞였으면 거절합니다(`MIN_SEPARATION` 1.5 미만이면 경고).
- 공격 방향(킥오프 때 두 팀 평균 위치, `startup_check.py`의 5m 기준). 안전장치: 제안 방향을 화살표로 그린 그림을 벤치 화면에 띄우고 코치가 누르기 전에는 적용하지 않습니다. 후반 전환 버튼도 같은 그림으로 확인합니다.
- 킥오프와 하프타임 시각(`/tag` 버튼 기록 + 두 팀이 각자 진영에 80% 넘게 나뉜 순간). 안전장치: 버튼 시각 앞뒤 2분의 영상 사진을 보여 주고 사람이 고릅니다(11-20 후반 전환 버튼이 킥오프보다 약 1분 빨랐음).
- 위쪽 자르는 비율(보정 점의 가장 먼 선 위치에서 계산). 안전장치: 기준 사진에 자르는 선을 그려 보여 주고 한 번 확인합니다. 카메라가 고정이라 설치 때 한 번이면 됩니다.
- 경기 영상의 카메라 구간 경계(선 일치 점수). 새 경기에는 필요 없고 11월 11일 학습 자료에만 쓰입니다.
- 수신 주소(기본 경로의 LAN 주소). 안전장치: 찾은 주소를 화면에 보여 주고 `server.json`의 값과 다르면 시작을 거절합니다.

### 그룹 5: 지금 기술로는 자동이 어려운 것과 이유
- 골과 슛의 시각: 공 위치를 믿을 수 없어서입니다(공 기록 없음, 사용자님 확인이 필요).
- 상대 골키퍼가 "우리 팀"으로 섞이는 것: 골키퍼는 다른 색을 입고 경기 중 거의 서 있어서 색 묶음으로 가를 수 없습니다. 11-20 우리 팀 점 458개 중 상대 골키퍼가 6%였습니다(`wiki/team-role-1120.md`).
- 알림 기준값(12m, 14m, 41m, 쿨다운, 우선순위): 정답이 사람 판정뿐이고 판정이 종류당 20개 미만이어서입니다.
- 계획 포메이션의 좌표: 코치의 의도라서 측정으로 알 수 없습니다.
- 먼 쪽 선수의 검출(키 15~25픽셀): 설정이 아니라 학습과 추적의 문제이며 이 페이지의 범위 밖입니다(`wiki/match-1120-live-and-report.md`의 문제 목록 3번).

### 2026-11-20에 가장 많은 문제를 막았을 변경 10개 (순서대로)
| 순위 | 변경 | 막았을 일(2026-11-20) | 수고 |
|---|---|---|---|
| 1 | 시작 스크립트가 `match.json`의 경기별 칸(공격 방향, 팀 프로필, 킥오프, 수신 주소, 경기 이름)이 비어 있으면 시작을 거절 | 환경값이 빠진 채 시작해서 수신 서버가 켜지자마자 꺼짐, 문서 예시 `--direction 1`(실제 전반은 -1) | 중간 |
| 2 | 경기장 설정 파일 `venue.json`에 보정 경로와 카메라 이름을 두고 시작 때 선 일치 점수와 이동량 4픽셀 점검 | 11-18 보정을 그대로 써서 선수가 경기장 밖으로 계산됨(하프라인 약 110픽셀), 전반 중 재시작 | 중간 |
| 3 | 옷 색 최소 키를 `venue.json`(20픽셀)에서 읽고 `run_min20.py`의 덮어쓰기를 없앰 | 우리 선수가 초당 2~6명만 잡히고 코칭 알림 0개 | 작음 |
| 4 | 라이브는 `team_profile.json`이 오늘 날짜이고 보정과 같은 구도에서 만든 것이 아니면 시작 거절 | 어긋난 보정으로 만든 팀 색(연두 13 / 회색 17)이 하프타임까지 감, 하프타임에 재시작 | 중간 |
| 5 | 킥오프와 후반 시작을 `match.json`에 적고 후반 전환 버튼은 그 시각 앞뒤에서만 받음 | 후반 전환 버튼이 킥오프보다 약 1분 빨리 눌려 그 동안 공격 방향이 거꾸로 | 작음 |
| 6 | 시작 스크립트가 수신 서버가 켜진 것을 확인하기 전에는 녹화를 켜지 않고, 녹화 기본 폴더(지금 `match-1118`)를 없애 `-OutDir` 필수로 | 녹화 시작 직전까지 안 됨, 기본 폴더가 다른 경기여서 섞일 위험 | 작음 |
| 7 | `--positions` 경로를 `<저장소>/alerts/<세션>/positions.jsonl`로 자동 정함 | 벤치 미니맵이 안 나와 하드 링크로 연결 | 작음 |
| 8 | 야간용 값(확대 1280, `--dark-min 0.15`, `--vote-min 2`, `--pitch-margin -1.5`)을 `venue.json`의 조명 칸으로 이동 | 명령줄을 손으로 길게 적다가 빠뜨릴 위험, 관중 점 4.40개/초(기본 2.0m 여유) | 작음 |
| 9 | 보고서 스크립트의 경기 이름과 결과 문구를 `match.json`에서 읽기 | 보고서 html의 문구를 손으로 고침(`_final.html`) | 작음 |
| 10 | 포메이션 계획 좌표와 선수 명단을 `match.json`의 `lineup`에서 읽기(분석 스크립트 5곳이 복사본 사용) | 처음 판 코칭 리뷰가 11-18 평균 자리와 비교되어 사용자님이 고쳐 주심 | 중간 |

## 2. 조사 범위와 방법
- 대상: `app/`(약 160개 파일), `scripts/`(약 306개 파일), `web/`, 위 5개 분석 스크립트, 시작 스크립트 3개(`scripts/start_match_day.ps1`, `scripts/record_stream_loop.ps1`, `scripts/run_review_server.ps1`)와 `plaintext_demo`의 srt 실행(`app/plaintext_demo.py`), `scripts/run_live_feedback.py`. 검색 도구는 ripgrep이 설치되어 있지 않아 `grep -rE`로 했습니다(`.py .ps1 .js .cjs .html .css`, `__pycache__` 제외).
- 아래 표의 모든 줄은 제가 열어서 보았습니다. 검색 결과 전체 줄(아래 3절 합계)을 하나하나 열어 보지는 않았습니다. 따라서 이 표는 "알려진 값과 검색에서 걸린 대표 값"이며, 나머지는 같은 유형으로 봅니다.
- "왜 고정했나"는 (1) 값 옆 주석, (2) `git log -S`로 찾은 도입 커밋, (3) 위키 순서로 찾았습니다. 근거를 찾지 못하면 "근거 없음(추정: ...)"으로 적었고 추정은 이유가 아닙니다.
- 사람 판정과 모델 값은 섞지 않았습니다. 판정 수는 표본이 작아(종류당 20개 미만) 확정 못 하는 값입니다.

## 3. 검색 패턴과 결과 수
대상은 `app/ scripts/ web/`와 5개 분석 스크립트입니다(`.py .ps1 .js .cjs .html .css`).
| 패턴 | 줄 수 | 파일 수 |
|---|---|---|
| 모듈 최상위 대문자 상수(숫자, 문자열, 튜플, 딕셔너리 대입) | 417 | 143 |
| `cam[0-9]` | 90 | 47 |
| IPv4 모양 주소(루프백 포함) | 83 | 27 |
| IPv4 모양 주소(루프백 제외, 시작 스크립트와 방화벽 스크립트만 남음) | 8 | 4 |
| 절대 경로 `X:\Users` 또는 `X:/Users` | 21 | 12 |
| 드라이브 글자가 있는 경로 전체 | 51 | 24 |
| 경기장 크기 `89 62 105 68 52.5` | 92 | 61 |
| 그 가운데 `105 68 52.5`만 | 21 | 16 |
| 영상과 타일 크기 `1920 1080 1280 768 384` | 119 | 61 |
| `1920` 또는 `1080` | 62 | 32 |
| 프레임 속도 `60 30` fps | 6 | 6 |
| `MAX_` 또는 `MIN_` 또는 `THRESH` 또는 `RATIO` 또는 `TOP` | 201 | 52 |
| 따로 센 값: `MAX_` 94줄, `MIN_` 88줄, `THRESH` 2줄, `RATIO` 20줄, `TOP` 9줄(한 줄에 둘이 있어 합이 201과 다름) | | |
| `DEMO_BIND_IP`, `DEMO_SOURCE_IP`, `DEMO_SRT_ALLOW_ANY` | 13 | 3 |
| `Host` 대문자(`scripts/run_review_server.ps1:42` 등) | 3 | 3 |
| 포트 8000 8443 8890 18554 18890 18555 8888 | 53 | 20 |
| 팀 글자 `'A'` `'B'` 또는 `own_letter` | 154 | 64 |
| 날짜나 경기 이름(11-20, 1118, 경기 이름 등) | 82 | 52 |
| `kickoff` 또는 `half_time` 또는 `HALF` | 80 | 21 |
| 포메이션 좌표 `PLAN_A/D`, 예시 4-4-2, `LB..LCB..RCB` | 20 | 7 |
| 카메라 전환 초 `1484 1495 1735 1490 1500 1730 1740` | 14(`1484`만은 0) | 8 |
| 경기 함수 안 숫자 비교: `live_feedback.py` 13줄, `team_color_profile.py` 16줄, `pitch_map.py` 9줄, `alert_review.py` 0줄, 타일 검출(`track_review_clip.py`) 7줄 | 45 | 5 |
| 선수 이름(`app/ scripts/ web/`) | `scripts/build_preview_report.py` 한 파일에만 있음 | 1 |
- `cam[0-9]` 90줄 가운데 `app/` 10, `scripts/` 77(나머지 3줄은 5개 분석 스크립트 밖의 파일 하나와 중복 없음 확인 못 함, 미확인).
- 경기장 크기는 `app/`에서 정의 17곳(`attack_options.py:115`, `event_miner.py:82`, `goalkeeper.py:10`, `halftime_accumulator.py:166`, `live_feedback.py:76`, `shot_routes.py:57,118,147`, `report_scenes.py:13`, `tactical_concepts.py:64,70,77,83`, `team_formation.py:20`, `team_tactics.py:16`, `xg.py:22`), `web/` 5개 파일입니다.
- `1484`는 코드와 5개 분석 스크립트에서 0줄입니다. `CAM3_FROM = 1484`는 2026-11-17에 고쳐졌습니다(7절 마지막과 표의 R33).

## 4. 표
그룹: 1 고정이 맞음, 2 경기장과 카메라 고정값, 3 경기별 설정, 4 자동 추정과 안전장치, 5 자동이 어려움. 주소는 "(주소)"로 적었습니다. 수고: 작음(한 파일, 시험 있음), 중간(여러 파일), 큼(라이브 코드와 화면을 함께 바꿈).

| 항목 | 값 | 위치(file:line) | 무엇에 달린 값인가 | 왜 고정했나 | 근거 | 바꾸는 방법 | 자동으로 정할 수 있나 | 틀리면 생기는 일 | 수고 |
|---|---|---|---|---|---|---|---|---|---|
| R01 (그룹 2) 경기장 크기 | 길이 89, 폭 62m | `app/live_feedback.py:76`, `scripts/run_live_feedback.py:219-220`, `app/goalkeeper.py:10`, `app/team_formation.py:20`, `app/team_tactics.py:16`, `app/report_scenes.py:13` 외 `app/` 17곳, `scripts/` 27개 파일 | 경기장 | 근거 없음(추정: 처음 경기장 한 곳의 추정 크기를 기본값으로 둠) | `app/pitch_map.py` 머리말 "The pitch size is an estimate"; `wiki/set-pieces.md` "89 x 62m는 추정 크기"; 11-20 `calibrations.json` 메모 "read by Claude from one live frame; not clicked by a person" | (a) `work/venue-1120/calibrations.json`의 `cam4.pitch`를 모든 코드가 읽기(지금도 보정 계산만 읽고 알림, 팀 모양, 구역 코드는 89를 다시 적음) | 아니오: 사진만으로는 크기를 알 수 없고(모든 거리에 같은 배율 오차), 한 번 줄자나 알려진 길이(골대 7.32m, 원 반지름 9.15m)로 재야 함. 카메라와 경기장이 고정이라 한 번이면 됨 | 모든 미터 값에 같은 배율 오차. 실제 예: 폭을 60으로 적은 화면 코드가 있음(`web/minimap-motion.js:4`, `web/app.js:37`) | 큼(라이브 코드 포함, 약 20곳) |
| R02 (그룹 2) 화면 쪽 경기장 크기 | 89, 62, 44.5, 31, 60 | `web/players.js:142`, `web/halftime.js:13`, `web/shots.js:4`, `web/minimap-motion.js:4`, `web/app.js:37` | 경기장 | 근거 없음(추정: 미니맵 그림을 그릴 때 파이썬 값을 복사) | `wiki/research-position-metrics.md` "경기장 89 x 62m"; 폭 60은 설명 없음 | (a) 서버가 `venue.json`을 화면에 내려 주기 | 아니오(R01과 같은 이유) | 미니맵 그림이 2m 틀림(60 대 62) | 중간 |
| R03 (그룹 2) 보정 파일과 카메라 이름 | `cam4`, `work/venue-1118/calibrations.json`(문서 기준) | `scripts/run_live_feedback.py:231`(선택지 `cam1`, `cam3`, `cam4`), `work/tonight-commands-20261120.md`(보정 경로), `cam[0-9]` 90줄 | 경기장, 카메라 | 11-18 구도에서 새로 만들어 이후 그대로 씀 | `wiki/match-1118-venue-and-report.md` "기존 cam1, cam3 보정을 쓸 수 없어 새로 cam4 보정"; 명령 문서 "11월 18일과 같은 자리에 카메라를 둘 때만" | (a) `venue.json`에 `camera.id`와 `calibration.file`을 한 번 적기(11-20에는 `work/venue-1120/calibrations.json`의 `cam4`가 맞음). 카메라 이름 선택지는 보정 파일의 키에서 읽기 | 조건부: 카메라가 안 움직였는지는 선 일치 점수로 자동 점검 가능. 새 보정을 처음부터 만드는 것은 사람이 점을 찍어야 함(자동 선 찾기는 오차 15~18m로 실패, `wiki/research-calibration.md`) | 11-20: 11-18 보정을 쓰면 선수가 경기장 밖으로 계산됨(하프라인 약 110픽셀 아래), 라이브 12점으로 새 보정(오차 0.54m) 후 전반 중 재시작 | 중간 |
| R04 (그룹 2) 경기장 위쪽 자르기 비율(타일 검출) | cam1 0.62, cam3 0.50, cam4 0.38 | `scripts/track_review_clip.py:22` | 카메라 | cam1, cam3 값 주석 "above this fraction is stands and sky". cam4 값은 근거 없음(추정: 11-18 사진에서 눈으로 정함) | 같은 줄 주석, 이전 변경(11-12)와 이전 변경(11-20, cam4 추가) | (a) `venue.json`의 `camera.pitch_top`. 코드 두 곳이 서로 다른 값을 가짐(R05) | 조건부: 보정 점 중 가장 먼 선의 화면 위치에서 계산 가능. 안전장치: 기준 사진에 선을 그려 한 번 확인 | 너무 낮으면 관중을 검출, 너무 높으면 먼 선수를 자름(경기장 위 상자 중 78%가 30픽셀 미만이라 이미 먼 선수가 문제) | 작음 |
| R05 (그룹 2) 공 클립용 위쪽 자르기 비율 | cam1 0.70, cam3 0.58, cam4 0.38 | `scripts/prepare_ball_clips.py:16` | 카메라 | 주석 "rows above this are sky, buildings and trees". cam1, cam3 값이 R04와 다른 이유는 근거 없음(추정: 공 클립은 더 좁게 잘라 쓰려고) | 같은 줄 주석, 이전 변경 | (a) R04와 같은 `camera.pitch_top` 한 곳(공 클립이 다르게 필요하면 `ball_top` 칸을 따로) | 조건부(R04와 같음) | 공 탐색 영역이 달라져 공 라벨 비교가 어긋남 | 작음 |
| R06 (그룹 2) 타일 크기 | 384픽셀 | `scripts/track_review_clip.py:23`, `scripts/run_live_feedback.py:245`(도움말 "the 384 px tiles") | 카메라(선수 크기), 컴퓨터(속도) | 근거 없음(추정: 선수 크기에 맞춰 이 크기로 시작) | 이전 변경(11-12) 메시지는 "Add a clip tracking script ..."뿐 | (a) `venue.json`의 `detector.tile` | 아니오: 사람이 확인한 상자로 비교 시험(`wiki/detector-experiments.md`)해야 정해짐 | 크기가 바뀌면 모든 검출 벤치 비교가 깨짐 | 작음 |
| R07 (그룹 2) 검출 확대 크기 | 768(기본), 1280(야간 계획) | `scripts/run_live_feedback.py:245`, `scripts/track_review_clip.py` 함수 `detect`의 `tile_size=768` | 카메라, 컴퓨터, 조명 | "768 = the live setting; larger values were measured only for ft_n2 on boxes a human confirmed" | 같은 줄 도움말; 명령 문서: 야간 사람 확인 상자 116개 중 1280이 74, 768이 64 | (a) `venue.json`의 `detector.imgsz`(야간 값은 R41). 11-20 라이브가 어느 값으로 돌았는지는 `work/live-run-1120/run*.log`가 비어 있어 확인하지 못함 | 아니오: 시험 비교로만 정함 | 확대가 낮으면 먼 선수를 놓침(키 15~25픽셀 선수 누락, 11-20 문제 3번) | 작음 |
| R08 (그룹 2) 검출 신뢰도 | 0.10 | `scripts/run_live_feedback.py:230`, `scripts/startup_check.py:249`, `scripts/team_select_prepare.py:55` | 카메라, 조명 | 근거: 명령 문서 "같은 시험"(위 R07 표본 116개). 값 자체가 0.10인 이유는 근거 없음(추정: 낮은 신뢰도 상자까지 모아 추적이 거르게 함) | 이전 변경(11-13) | (a) `venue.json`의 `detector.conf` | 아니오(시험 비교) | 높이면 먼 선수를 놓치고 낮추면 관중을 사람으로 셈 | 작음 |
| R09 (그룹 2) 추적기 임계값 | 높음 0.12, 낮음 0.06, 버퍼 50, 매칭 0.98 | `scripts/run_live_feedback.py:267-268`, `app/track_vote.py:11` | 카메라(먼 선수 신뢰도), 조정값 | 근거 없음(추정: 라이브에서 신뢰도가 낮은 상자를 살리려고 기본값 0.5/0.1보다 낮춤) | 이전 변경, 이전 변경; 위키에 설명 없음 | (a) `venue.json`의 `tracker` 칸 | 아니오(추적 지표 시험 필요) | 번호가 자주 바뀌거나 가짜 번호가 생김 | 작음 |
| R10 (그룹 2) 옷 색을 읽는 최소 키 | 30픽셀 | `app/team_color_profile.py:23`, 사용처 `:32`, `scripts/eval_team_profile.py:87`, `scripts/eval_team_fusion.py:24` | 카메라(선수가 화면에서 보이는 크기) | 주석 "40 px left only 3 readable people per scene of this match (35 scenes), 30 px gave 11, 24 px gave 17" | `wiki/team-select.md` 28, 49, 117줄(같은 라벨로 정한 값, 독립 시험 아님); 이전 변경 | (a) `venue.json`의 `shirt.min_height_px`를 20으로. `wiki/match-1120-live-and-report.md`: 20픽셀이면 후반 6장면에서 팀이 정해진 상자 84/125(67%), 30픽셀은 23/125(18%) | 조건부: 같은 카메라 자리이므로 경기마다 추정하지 않고 한 번 정하면 됨(경기장 위 상자 125개 중 98개가 30픽셀 미만, 중앙값 25). `wiki/team-role-1120.md`: 현재 색 읽기는 키가 커도 나아지지 않으므로 값을 바꿀 때 팀 일치 표본으로 다시 확인 | 11-20 라이브: 우리 선수 초당 2~6명, 코칭 알림 0개 | 작음 |
| R11 (그룹 2) 11-20 재분석의 최소 키 덮어쓰기 | 20픽셀 | `work/match-1120/reanalysis/run_min20.py:8`(`functools.partial(tcp.shirt_colour, min_height=20)`) | 카메라 | docstring "at this camera 78% of on-pitch boxes were below 30 px, so most players got no team" | 같은 파일 1~3줄, `wiki/match-1120-live-and-report.md` | R10을 `venue.json`에서 읽게 하면 이 스크립트가 필요 없음 | R10과 같음 | 덮어쓰기를 잊고 라이브를 돌리면 R10의 일이 반복됨 | 작음 |
| R12 (그룹 2) 경기장 경계 여유 | 2.0m(기본), -1.5(11-20 라이브 명령) | `app/pitch_map.py:16`, `scripts/run_live_feedback.py:211`(옵션), 명령 문서 | 경기장(트랙과 관중석 위치), 조명 | 주석 "people on the running track just beyond the far line sit 2 m or more outside"; 11-20은 관중 점 4.40개/초(2.0)에서 0.09(-1.5)로 줄어 -1.5 선택 | 명령 문서(야간 리허설, 안 우리 선수 수는 세 값 모두 같음); 이전 변경(11-12) | (a) `venue.json`의 `pitch.margin_m` | 조건부: 같은 경기장에서는 한 번 정하면 됨 | 너무 크면 관중과 심판이 선수로 셈, 너무 작으면 라인 근처 선수를 놓침 | 작음 |
| R13 (그룹 2) 보정 허용 오차 | 5.0m | `app/pitch_map.py:15` | 경기장, 조정값 | 주석 "metres of calibration error above which nothing is drawn". 5.0인 이유는 근거 없음(추정: 사람이 찍은 보정 오차 0.5~1m보다 넉넉한 거절선) | 이전 변경(11-12) 메시지 "refuses without a calibration" | (a) `venue.json`의 `calibration.max_rms_m`(예: 1.5) | 조건부: 11-20 보정 오차 0.54m로 보아 더 엄격하게 할 수 있음. 안전장치 없이 낮추면 정상 보정을 거절할 수 있어 사람이 확인 | 5m는 너무 느슨해 틀린 보정을 통과시킴(11-20 위치 문제의 원인이 오차 값에는 안 잡힘) | 작음 |
| R14 (그룹 2) 확대 구역 타일 | 256, 머리 위 110픽셀 | `scripts/run_live_feedback.py:91-92` | 카메라 | 주석 "read at 4 times its size (imgsz 1024)", "pixels above the feet line that still hold the bodies" | 같은 줄 주석(`--box-zoom`은 기본 꺼짐, 도움말 "no longer real time on this machine") | (a) `venue.json`의 `detector.box_zoom` | 아니오 | 켜면 라이브 지연 | 작음 |
| R15 (그룹 2) 카메라 이동 허용 | 24픽셀, 작업 폭 960 | `scripts/run_live_feedback.py:242`, `app/camera_drift.py:15, 19` | 카메라(삼각대) | 근거: `wiki/calibration-automation.md` 65줄 설계안 "한계(예: 20픽셀)". 24는 근거 없음(추정: 20에 여유) | 같은 위키 | (a) `venue.json`의 `camera.max_shift_px`. 삼각대 점검 기준(이동량 4픽셀이면 빨강)은 `wiki/calibration-check-and-track-stitch.md` 9줄 | 예: 선 일치 점수는 49장(11-20 전후반)에서 평소 19.1(표준편차 0.9, 최소 17.0)이고 5~40픽셀 이동은 17/17 잡힘. 저장소에는 아직 코드가 없음(`grep` 결과 없음) | 움직인 카메라로 위치를 계속 계산 | 중간 |
| R16 (그룹 2) 영상 크기 | 1920 x 1080 | 62줄 32개 파일. 코드가 읽는 곳도 있음(`scripts/run_live_feedback.py:292`는 `CAP_PROP_FRAME_WIDTH`) | 카메라(1080p 고정) | 근거 없음(추정: 송출 해상도) | `web/review-annotation.js:161` 주석 "in a 1080-px frame" | (d) 고정이 맞음. `venue.json`에 `frame: 1920x1080`을 적어 두고 시작 점검이 입력 크기를 비교 | 예(입력에서 읽음) | 다른 해상도가 들어오면 타일과 자르기 비율이 어긋남 | 작음 |
| R17 (그룹 2) 분석 프레임 속도와 입력 속도 | 분석 5.0fps, 입력 60/30fps | `scripts/run_live_feedback.py:221, 224`, `app/live_feedback.py:76` | 컴퓨터(속도), 카메라 | 명령 문서 "11월 18일 실전과 같은 설정. 10장은 실시간은 되지만 알림 동작을 확인하지 못함" | 명령 문서; `wiki/shooting-and-streaming-guide.md` 19줄(11-11 영상은 약 1400~1500초 앞은 30fps, 뒤는 60fps) | (a) `venue.json`의 `analysis_fps` | 아니오(컴퓨터 속도 시험) | 느리면 지연, 빠르면 알림 시험 안 됨(분석 지연 평균 0.24초) | 작음 |
| R18 (그룹 2) 비트레이트 한계 | 1080p 빨강 2100 미만, 노랑 3800 미만 kbps | `app/stream_health.py:25-27` | 네트워크(5G), 카메라 | 주석 "from the computer test ... a sender set to 4000 reaches about 3970" | `wiki/stream-diagnosis.md` 17줄(1080p 2000이면 재현율 0.53) | (a) `venue.json`의 `stream` | 아니오(시험으로 정함) | 낮은 비트레이트를 정상으로 판정 | 작음 |
| R20 (그룹 1) 규격 경기장 표 | 105 x 68, 원 9.15, 골대 7.32, 박스 16.5 x 40.3, 골 지역 5.5 x 18.3 | `app/pitch_map.py:13` | 경기 규칙(물리 상수) | 규격 값. 실제 크기는 보정 파일의 `pitch`가 덮어씀(`app/pitch_map.py:21`의 `{**DEFAULTS, **(d or {})}`) | `app/pitch_map.py` 머리말 | (d) 고정이 맞음. 길이와 폭만 R01에서 읽음 | 해당 없음 | 작은 경기장에서 박스가 표준과 다르면 보정 파일에서 따로 적음 | 해당 없음 |
| R21 (그룹 1) 박스 깊이와 반폭 | 16.5m, 20.16m | `app/tactical_concepts.py:11-12` | 경기 규칙 | 규격 값 | 같은 파일 | (d) 고정이 맞음(경기장에 따라 다르면 `venue.json`의 `pitch.pa_depth`) | 해당 없음 | 박스 안 선수 수 알림이 틀림 | 해당 없음 |
| R22 (그룹 5) 침투 속도와 줄 이동 | 3.0m/s, 6.0m, 8초 | `app/tactical_concepts.py:13-15` | 조정값 | 주석 "a jog is about 2-3, a sprint above 6; measured paths are noisy, so the bar is not set higher" | 같은 줄 주석(`LINE_MOVE`, `LINE_SECONDS`는 주석 없음, 근거 없음) | (d) 조정값이므로 판정이 쌓이면 바꿈 | 아니오: 정답(좋은 알림인가)이 사람 판정뿐 | 침투 알림이 많거나 적음(11-20 판정 상대 침투 11개 중 6개 틀림) | 작음 |
| R23 (그룹 5) 알림 규칙 숫자 | 박스 안 3명, 고립 12.0m, 라인 하락 14.0m, 보조 7.0m, 걸음 6개, 구간 4.0초, 1.5/fps | `app/live_feedback.py:215, 227, 232, 246, 255, 342, 207, 222` | 조정값 | 3명은 머리말 docstring "three or more of our players in the penalty area". 12.0과 14.0은 근거 없음(추정: 처음 경기에서 정한 값). 주석은 "sinking by 10 metres"인데 값은 14.0으로 서로 다름. 7.0은 docstring "half the 14 m trigger" | `app/live_feedback.py` 머리말 1~11줄, 이전 변경(11-13) | (a) `alerts` 설정 칸으로 이동하고 위치마다 근거를 적기 | 아니오(위와 같음) | 11-20 판정 37개 중 맞음 17: 고립 7개 중 6개 틀림, 라인 하락 9개 중 7개 맞음 | 작음 |
| R24 (그룹 5) 라인 간격 기준 | 41.0m | `app/live_feedback.py:59`, 쓰임 `:186, 240, 319` | 경기장 길이(89m 기준), 조정값 | 주석 "judged alerts at 32 were wrong 6 of 15, at 41 wrong 2 of 10 (same sample the value was chosen on, so it needs new judgements)" | `wiki/live-feedback.md` 18~23줄, 이전 변경(11-17) | (a) 경기장 길이에 비례하게 하되 현재는 꺼져 있음(R25) | 아니오(판정이 같은 표본에서 고른 값) | 틀린 간격 알림. 공개 추적 데이터(Metrica 2경기)에서 알림 뒤 상대 슛이 평소의 0.37배라 꺼 둠 | 작음 |
| R25 (그룹 3) 꺼 둘 알림 종류 | `('gap_wide', 'isolated')` | `app/live_feedback.py:60`(`isolated`는 2026-11-20 밤 수정이며 아직 커밋되지 않음, `git diff`에 있음) | 경기(상대, 전술), 팀 | 주석 "gap_wide: ... coach marked it wrong in 6 of 15", "isolated: wrong in 6 of 7 at the 2026-11-20 night match (a low block keeps the striker up on purpose); switched off by the user" | `wiki/match-1120-live-and-report.md`(사용자님 결정); 이전 변경(gap_wide) | (a) `match.json`의 `alerts.disabled`. 기본은 지금 목록 | 아니오: 낮은 블록 전술인지는 사람이 앎 | 11-20 고립 알림 7개 중 6개 틀림 | 작음 |
| R26 (그룹 5) 쿨다운과 간격 | 박스 20초, 상대 침투 25, 침투 25, 고립 45, 라인 하락 90, 간격 90초; 최소 간격 8초, 해제 30초 | `app/live_feedback.py:55-58, 61` | 조정값 | 근거 없음(추정: 알림이 한꺼번에 몰리지 않게 처음 정한 값). docstring은 쿨다운이 있는 이유만 설명 | 이전 변경(11-13) | (a) `alerts.cooldown` | 아니오 | 알림이 너무 많거나 적어 코치가 무시 | 작음 |
| R27 (그룹 1) 알림 우선순위 | box_attack, conceded_run, run, isolated, line_drop, gap_wide | `app/live_feedback.py:52`, 다른 뜻의 표 `app/bench_view.py:22` | 조정값 | 주석 "when several things happen in one second only the first is sent" | 이전 변경(11-13) | (d) 두 곳이 서로 다른 뜻(코치 화면 급함 표시)이라 이름만 구분 | 아니오 | 급한 알림이 가려짐 | 작음 |
| R28 (그룹 1) 알림 화면의 최대 개수 | 300 | `app/alert_review.py:18, 84` | 컴퓨터(화면 크기) | 근거 없음(추정: 한 화면의 크기 제한). 도입 이전 변경(11-13) "Alert rating page ..." | 커밋 메시지에 이유 없음 | (d) 안전 한계이므로 고정이 맞음. 단 최신 세션부터 300개만 남기고 나머지를 말없이 자르므로 "n개 더 있음"을 화면에 표시해야 함(`items[:MAX_ALERTS]` 뒤에 종류별 판정 집계도 잘린 목록으로 셈) | 해당 없음 | 판정이 쌓이면 오래된 세션 판정이 집계에서 빠져 정확도 숫자가 바뀜(`wiki/match-1120-live-and-report.md` 마지막 주의와 같은 종류) | 작음 |
| R29 (그룹 5) 골키퍼 규칙 | 골라인에서 14m 이내, 6m 이내면 항상, 아니면 다음 선수와 3m 이상, 8명 미만이면 안 뺌 | `app/goalkeeper.py:11-14` | 조정값(경기장 길이 R01 포함) | docstring "uses the place first and the gap second", 14m, 6m, 3m 값 자체는 근거 없음(추정: 판정에서 틀린 알림이 13~29m 뒤에 선 선수였던 것을 기준으로 맞춤) | `wiki/goalkeeper-rule.md`; 이전 변경(11-16) | (a) `venue.json`의 `pitch.length`를 읽고 숫자는 `alerts` 설정으로 | 아니오: 정답이 사람 판정 | 라인 알림이 골키퍼를 마지막 수비수로 봄. 규칙을 넣으면 맞는 알림도 일부 사라짐(맞음 line_drop 1개, run 3개 중 2개) | 작음 |
| R30 (그룹 3) 옛 골키퍼 규칙 상수 | 8.0m | `app/position_slots.py:18` | 조정값 | 주석 "metres the deepest player must stand behind the next one to be called the goalkeeper". 이 이름은 `grep`에서 정의 한 줄뿐이라 쓰이지 않는 상수로 보임 | `app/goalkeeper.py` docstring "only when the gap was 8 m or more"(옛 규칙) | 지우거나 `goalkeeper.py` 하나로 합치기 | 해당 없음 | 다른 규칙이 두 개 남음 | 작음 |
| R31 (그룹 4) 공격 방향 | 첫째 줄 `--direction` 필수(기본값 없음), 11-20 전반 -1 | `scripts/run_live_feedback.py:212, 432-433`, `app/live_control.py:3`, `work/live-run-1120/positions.jsonl:1`(헤더 `direction: -1`) | 경기, 반(전반과 후반), 팀 | 도움말 "+1 when the focus team attacks toward +x (image right)"; 후반은 버튼이 방향을 뒤집음 | `wiki/live-startup-and-halftime.md`; 11-20 명령 문서의 예시는 `--direction 1`이었고 전반 실제는 -1(화면 왼쪽) | (b) `/tag` 후반 전환 버튼(이미 있음) + (a) `match.json`의 `attack_direction_first_half` | 조건부: `startup_check.py:29`의 `DIRECTION_MIN_GAP = 5.0`m(두 팀 평균 위치 차이)으로 킥오프 때 제안 가능, 대신 사람이 확인(그림에 화살표로 보여 주고 누름) | 방향이 거꾸로면 침투, 라인 알림이 모두 반대. 11-20에는 후반 전환 버튼이 킥오프 약 1분 전에 눌림 | 중간 |
| R32 (그룹 4) 킥오프, 하프타임, 골 시각 | 경기 C: 반별 영상 시작 초, 골 시각(영상 초) | `work/match-1120/position-metrics/features.py:11-12`, `scripts/build_preview_report.py`(`GOALS`, 공개본에서는 비어 있음) | 경기 | 주석 "first recorded second of each half video (kick-off)" | 같은 파일 | (a) `match.json`의 `halves`, `events` | 킥오프는 조건부(`/tag` 버튼 + 두 팀이 각자 진영에 80% 넘게 나뉜 순간 + 장면 사진, 사람 확인). 골은 아니오(공이 없어서, 사용자님 확인) | 구간이 틀려 전반, 후반 집계가 섞임 | 작음 |
| R33 (그룹 4) 카메라 전환 초 | 1495, 1735 | `app/camera_segments.py:7-8` | 경기 영상(11-11 한 경기) | docstring "Measured with scripts/research_camera_segments.py (... this match only)" | `wiki/calibration-automation.md`; `wiki/detector-experiments.md` 121줄. 이전 `CAM3_FROM = 1484`는 2026-11-17에 이 파일로 대체되어 코드에 없음(`1484` 0줄). `wiki/review-store-and-open-tasks.md` 39줄은 아직 "고치지 않음"이라 적고 있어 낡음 | (c) 선 일치 점수로 자동 구분(11-11 영상 학습 자료에만 해당, 새 경기는 카메라가 하나라 필요 없음) | 예(구도마다 기준 사진 한 장으로 약 121개 중 모두 맞힘). 안전장치: 경계 앞뒤 사진을 사람이 한 번 봄 | 옛 값은 영상 전체의 약 8% 구간의 자르기 영역이 달랐을 뿐 라벨 좌표는 맞음(`wiki/detector-experiments.md` 64줄) | 작음(시험 있음) |
| R34 (그룹 4) 팀 글자 A, B와 기본 팀 | 형광 = A, 어두운 = B, 기본 `--team B` | `scripts/run_live_feedback.py:46, 213`, 같은 모양 154줄 64개 파일 | 팀, 경기(옷 색) | docstring "neon shirts are team A, dark shirts team B" | 메모리 노트: A/B는 11-11 경기만, 이후 경기는 코치가 우리 팀을 고름; `wiki/team-select.md` 1절 | (b) `/team-select`에서 우리 팀 고르기(프로필이 이미 `--team-profile`로 연결됨) | 조건부: 옷 색 묶음으로 두 무리를 만드는 것은 자동, 어느 쪽이 우리인지는 사람이 누름 | 팀이 뒤바뀌면 모든 알림이 상대에게 | 큼(64개 파일, 단계적으로 내부 이름만 own, opp로) |
| R35 (그룹 4) 옷 색 규칙 | 형광 색상 범위, 형광 비율 0.22, 어두운 비율 0.30(11-20 야간 0.15), 투표 3(11-20 2) | `scripts/run_live_feedback.py:46, 79, 207-210`, `app/team_role_features.py:1-5`, `scripts/track_review_clip.py:91` | 팀, 조명 | docstring "The neon range is the one used for the yellow vests of this particular match; another match needs its own labels"; 0.14는 "the colour rule of the first match" | `wiki/team-select.md` 10~16, 101줄; 명령 문서: 밤에 어두운 옷 비율이 0~0.2라 `--dark-min 0.15`로 우리 팀 4.6명이 8.3명 | (b) `/team-select` 프로필이 이 규칙과 학습 모델을 덮음(재학습 안 함). 프로필을 필수로 하면 규칙은 쓰이지 않음 | 조건부: 색 묶음은 자동. 안전장치: 대표 사진을 보여 주고 코치가 우리 팀을 누름. 분리도 1.5 미만이면 거절 | 팀 구분이 틀림(11-20: 어긋난 보정으로 만든 묶음이 연두 13 / 회색 17, 하프타임에 30초로 다시 만들어 연두 78 / 빨강 72) | 중간 |
| R36 (그룹 3) 시작 점검의 우리 팀 색 기본값 | `--focus-colour dark` | `scripts/startup_check.py:245` | 팀 | 도움말 "the dark team B in this match" | `wiki/startup-check.md` 사용법 | (b) 프로필에서 읽기 | 조건부(R35) | 11-20 우리 팀은 초록 조끼인데 어두운 옷을 기본으로 점검 | 작음 |
| R37 (그룹 2) 옷 색 프로필 조정값 | 밝기 가중치 0.6, 분산 하한 4.0, 이상값 3.5, 분리도 1.5, 팀당 4명, 분류 비율 0.7 | `app/team_color_profile.py:24-29`, 쓰임 `:96, 113, 181, 183, 204` | 조명, 조정값 | 앞 5개는 줄마다 주석(예: 분리도 1.5는 "proposed value: in this match the real colours give 1.8 to 2.1, repainted ones 2.4 to 9.9"). 분류 비율 0.7(`CLASSIFY_RATIO`)은 근거 없음(추정: 두 색이 비슷한 상자를 "불명"으로 거르는 값) | 이전 변경(11-20), `wiki/team-select.md` 표 | (a) `venue.json`의 `shirt` 칸 | 아니오(같은 표본의 시험으로 정함, 다른 조명 시험 없음, `wiki/team-select.md` 77줄) | 비율을 높이면 팀이 안 정해지는 상자가 늘고, 낮추면 비슷한 색을 섞음 | 작음(시험 있음) |
| R38 (그룹 3) 수신 서버 주소 환경값 | `DEMO_BIND_IP`, `DEMO_SOURCE_IP`, `DEMO_SRT_ALLOW_ANY` | `app/plaintext_demo.py:200-207`, `app/demo_supervisor.py:18-25`, `scripts/start_cellular_demo.ps1:6-10`, 시작 스크립트 `scripts/start_match_day.ps1:23`에는 없음 | 네트워크(오늘 컴퓨터 주소), 경기장 | 안전한 기본: 주소가 없으면 시작 거절(`plaintext_demo.py:200` 메시지 "set DEMO_BIND_IP and DEMO_SOURCE_IP in process environment") | 같은 줄 메시지; `wiki/match-1120-live-and-report.md` 문제 1번 | (a) `server.json`(이미 `bind`를 가짐)에서 읽어 시작 스크립트가 환경값을 넣기. 값은 (주소), 127.0.0.1, 1 | 조건부: 기본 경로의 LAN 주소를 찾을 수 있지만 공유기 포트 설정이 그 주소에 묶여 있어, 찾은 값이 `server.json`과 다르면 시작 거절 | 11-20: 수신 서버가 켜지자마자 꺼짐, 그 프로세스에만 환경값을 손으로 넣어 해결 | 작음 |
| R39 (그룹 3) 서버 주소와 안내 문구 | 공개 주소 (주소):8443, 묶는 주소 (주소), 송출 포트 8890 | `scripts/start_match_day.ps1:39-40`, `scripts/run_review_server.ps1:12-13` | 네트워크 | 주석 "Moblin: send to srt://<public address>:8890 as on 2026-11-18"; 설정 파일은 Git 밖에 둠(머리말 "kept outside Git") | `scripts/run_review_server.ps1:9` 머리말 | (a) `server.json`의 `origin`, `bind`를 읽어 안내 문구 만들기 | 조건부: 공개 주소는 공유기와 통신사가 정함(자동 불가), 알려 주면 코드가 읽음 | 코치가 틀린 주소를 열어 화면이 안 열림 | 작음 |
| R40 (그룹 1) Host와 Origin 검사 | Host가 `origin`과 정확히 같아야 함, POST는 Origin도 같아야 함 | `app/review_public.py:229-231`, `app/main.py:110`(로컬만) | 네트워크(보안) | 근거: 이전 변경(11-11) "Serve an isolated public review session". 주석 없음(추정: 공개 서버 보호) | 코드 | (d) 고정이 맞음(보안). 이름 두 개가 필요하면 `server.json`에 `allowed_hosts`를 추가. 상태 점검은 이미 이 검사 때문에 Host를 맞춰 보냄(`scripts/run_review_server.ps1:42`) | 해당 없음 | 다른 주소로 열면 403 | 해당 없음 |
| R41 (그룹 3) 야간용 명령줄 값 | `--detector-imgsz 1280`, `--pitch-margin -1.5`, `--dark-min 0.15`, `--vote-min 2`, `--neon-band 30 70` | `work/tonight-commands-20261120.md`(옵션은 `scripts/run_live_feedback.py:207-211, 245`) | 조명, 경기장 | 명령 문서 "정한 설정과 근거" 표(1280: 사람 확인 상자 116개 중 74 대 64, 경계: 관중 점 4.40에서 0.09, 어두운 옷: 우리 팀 4.6명에서 8.3명) | 명령 문서; 11-18 경기장 조끼 `30 70`은 이 경기장에 맞춘 값 | (a) `venue.json`에 `lighting: night` 묶음 | 조건부: 낮, 밤은 시작 때 코치가 고름. 안전장치: 몸풀기 1분 확인(우리 점이 터치라인 밖에 몰리지 않는지) | 명령줄을 손으로 길게 적다가 빠뜨리면 팀이 안 정해짐 | 작음 |
| R42 (그룹 3) 시작 스크립트의 절대 경로 | `<USER_HOME>\outputs`, 녹화 기본 폴더 `match-1118`, ffmpeg 경로 | `scripts/start_match_day.ps1:11`, `scripts/record_stream_loop.ps1:8-9`, 21줄 12개 파일 | 컴퓨터, 경기(기본 폴더 이름) | 근거 없음(추정: 한 대의 컴퓨터에서만 씀) | `start_match_day.ps1:8`은 날짜로 경기 이름을 만듦(좋음). 녹화 스크립트 기본 폴더는 다른 경기 | (a) `$PSScriptRoot` 기준 상대 경로와 `-OutDir` 필수 | 예 | 기본 폴더를 쓰면 이번 경기가 11-18 폴더에 섞임, 다른 컴퓨터에서 시작 안 됨 | 작음 |
| R43 (그룹 3) 시작 순서와 대기 | 포트 18554를 2초 x 30번 기다린 뒤 녹화 시작 | `scripts/start_match_day.ps1:24-25, 33` | 컴퓨터, 네트워크 | 근거 없음(추정: 수신 서버가 60초 안에 켜진다고 가정) | `wiki/match-1120-live-and-report.md`: "실패해도 녹화를 그대로 켬" | (a) 대기가 실패하면 녹화를 켜지 않고 거절 | 예 | 11-20: 녹화가 수신 서버보다 먼저 켜져 녹화 시작 직전까지 녹화가 안 됨 | 작음 |
| R44 (그룹 3) 녹화 설정 | 조각 600초, RTSP `rtsp://127.0.0.1:18554/match` | `scripts/record_stream_loop.ps1:10, 16-17` | 컴퓨터, 네트워크 | 머리말 "in 10-minute pieces, without re-encoding" | 같은 머리말 | (d) 고정이 맞음. 포트와 경로는 `server.json` | 해당 없음 | | 해당 없음 |
| R45 (그룹 3) 포트 번호 | 8000, 8443, 8890, 18554, 18890 외 | 53줄 20개 파일(예: `scripts/start_match_day.ps1:24, 38`, `app/live_video_routes.py:19`, `app/plaintext_demo.py`) | 컴퓨터, 네트워크 | 근거 없음(추정: 프로그램마다 정한 번호) | `app/live_video_routes.py:19`만 환경 변수로 바꿀 수 있음 | (a) `server.json`의 `ports` | 해당 없음 | 포트가 겹치면 서버가 안 켜짐 | 중간 |
| R46 (그룹 3) `--positions` 경로 | `work/live-run-1120/positions.jsonl`(명령 문서) | `scripts/run_live_feedback.py:237, 316`(옵션), 서버는 `<저장소>/alerts/<세션>/positions.jsonl`을 읽음 | 컴퓨터(폴더 이름), 경기 | 옵션은 경로를 받기만 함. 명령 문서가 위키와 대조 없이 만들어짐 | `wiki/outage-halftime-service.md` 89줄; `wiki/match-1120-live-and-report.md` | (a) 세션 이름을 `match.json`에서 받아 경로를 자동 계산 | 예 | 11-20: 벤치 미니맵이 안 나옴, 하드 링크로 연결 | 작음 |
| R47 (그룹 3) 보고서 경기 이름과 결과 문구 | 지난 경기(11월 11일), 오늘 경기(11월 18일), 결과 문구 | `scripts/build_detailed_report.py:645, 657` | 경기, 팀 | 11-18 밤 그 경기용 시제품 | `wiki/match-1120-live-and-report.md` | (a) `match.json`의 `name`, `previous`, `result` | 예 | 11-20: 결과 html의 문구를 손으로 고침(`_final.html`) | 작음 |
| R48 (그룹 3) 선수 명단과 자리 좌표(미리보기 보고서) | 프리뷰 보고서의 명단과 좌표(공개본에서는 예시 4-4-2) | `scripts/build_preview_report.py` | 팀, 경기 | 프리뷰용 | `wiki/match-1120-live-and-report.md` | (a) `match.json`의 `lineup` | 아니오(코치가 정함) | 다른 경기에 쓰면 이름이 틀림 | 중간 |
| R49 (그룹 3) 포메이션 계획 좌표 | 수비할 때와 공격할 때 열 자리 각각의 (깊이, 옆) 좌표 | `work/match-1120/coach/coach_4231.py:9-10`, 복사본 `work/match-1120/position-metrics/features.py:9-10` | 팀, 경기(상대 대응 계획) | docstring에 경기 C와 프리뷰 계획이 적혀 있음. 좌표 숫자 자체의 출처는 파일로 확인하지 못함(프리뷰 그림 스크립트의 자리 값과 다름) | `wiki/match-1120-live-and-report.md` 코치 자료 제작 교훈 절 | (a) `match.json`의 `lineup.plan` | 아니오: 코치의 의도 | 처음 판이 계획이 아닌 이전 경기 평균 자리와 비교되어 사용자님이 고쳐 주심 | 중간 |
| R50 (그룹 3) 자리 나누기 규칙 | 가장 뒤 4명 = 수비, 가장 앞 = 공격수, 남은 5명 중 가장 앞 = 공미, 나머지 4명 옆 순서, 10명 아니면 건너뜀 | `work/match-1120/coach/coach_4231.py:13-17`, `features.py:50-54` | 팀(포메이션), 경기 | docstring "4 deepest = back four (by side), most advanced = ST ..." | `wiki/match-1120-live-and-report.md`("풀백이 올라간 순간은 이 방법으로 잴 수 없습니다") | (a) `match.json`의 `lineup.formation` | 아니오 | 다른 포메이션이면 계획 점검이 틀림 | 중간 |
| R51 (그룹 5) 상대 골키퍼 제거 규칙 | u가 22m 이상, 옆 10m 이내, 17초 중 12초 안 움직임, 번호 30초 이상 u 중앙값 24m 이상 | `work/match-1120/position-metrics/features.py:18-36` | 팀(색), 경기 | docstring "The opposing keeper is often coloured as 'ours' (checked on video 11-20: 전반 165 s, 536 s, 후반 350 s)" | `wiki/team-role-1120.md`(상대 골키퍼 6%) | (d) 사후 보정. 근본 해결은 팀 판정에서 골키퍼 구분 | 아니오: 골키퍼는 다른 색이고 움직임이 적어 색 묶음으로 못 가름 | 우리 팀 점에 상대 골키퍼가 섞여 공격수, 박스, 팀 길이가 틀림 | 큼(팀 판정 쪽) |
| R52 (그룹 4) 카메라에 가까운 쪽 부호 | 20m 밖 선수가 더 많은 쪽 | `work/match-1120/position-metrics/features.py:62-68` | 카메라, 반 | docstring "Camera-near touchline sign of v per half = the side with MORE players beyond 20 m (far-side players are lost more often)" | 같은 파일 | (c) 보정에서 가까운 쪽이 +y(`app/pitch_map.py` 머리말 "near touchline positive")이므로 방향과 보정으로 계산 가능 | 예 | 반 부호를 틀리면 전반 겹쳐 그리기가 거꾸로(`wiki/team-role-1120.md`에 방향 부호 오류 발견) | 작음 |
| R53 (그룹 5) 분석 스크립트의 숫자 | 팀 길이 35m, 앞뒤 간격 28(주석은 30), 측면 줄 10m, 박스 16.5 x 20.15, 4초, 20초 | `work/match-1120/coach/coach_numbers.py:22, 33, 48`, `work/match-1120/coach/deep.py:46, 53, 66, 82` | 조정값 | 근거 없음(추정: 이 경기 분석용 기준으로 정함). 주석 "back-front < 30"과 코드 `< 28`이 어긋남 | 파일 | (a) 분석 스크립트용 설정 | 아니오 | 지표가 기준에 따라 바뀌어 11-18과 비교가 틀림 | 작음 |
| R54 (그룹 3) 분석 스크립트의 자료 경로 | `<WORK_DIR>/work/` | `coach_numbers.py:3, 5`, `coach_4231.py:4, 6`, `deep.py:4, 6-7`, `features.py:4, 6`, `run_min20.py:5` | 컴퓨터, 경기 | 근거 없음(추정: 한 번 쓰고 버릴 스크립트) | 파일 | (a) `match.json`의 `paths` | 예 | 다음 경기에 복사해 쓸 때 이전 경기 자료를 읽음 | 작음 |
| R55 (그룹 3) 경기 인원 | 11, 18 | `app/tactical_feedback.py:14`(`TEAM_SIZE`), `app/halftime_accumulator.py:28`(`SLOTS`), `app/lineup.py:13`(`MAX_PLAYERS`) | 경기(11대 11) | 근거 없음(추정: 11대 11 경기를 가정) | 메모리 노트: 11대 11 경기 | (a) `match.json`의 `players_per_side` | 해당 없음 | 다른 인원 경기에서 구역 인원 계산이 틀림 | 작음 |
| R56 (그룹 1) 컴퓨터 안전 한계 | 디스크 30GB, 확인 60초, 입력 끊김 10초와 25초, 재연결 30초 | `app/recording_space.py:11-12`, `app/bench_view.py:27`, `app/service_watch.py:29`, `app/live_input.py:10` | 컴퓨터 | 디스크 30GB는 근거 없음(추정: 녹화 1~2시간 여유), 나머지는 주석이 있음(예: STALE 25초는 "heartbeats come every 10 s") | 이전 변경(11-11) "Warn of low recording disk space" | (d) 고정이 맞음(안전 한계) | 해당 없음 | 너무 낮으면 경고가 늦음 | 해당 없음 |
| R57 (그룹 1) GPU 안전 한계 | 그래픽 메모리 8GB, 일반 메모리 12GB, 90%와 95%에서 중단 | `scripts/gpu_guard.py:128-129`, `CLAUDE.md` | 컴퓨터 | `CLAUDE.md` "2026-11-20 사용자님 결정": 세 작업 동시 실행으로 그래픽 99%, 일반 99.7%, 컴퓨터가 5분 멈춤 | `wiki/gpu-memory-rules.md` | (d) 고정이 맞음(사용자님 결정) | 해당 없음 | 올리면 컴퓨터가 다시 멈춤 | 해당 없음 |
| R58 (그룹 1) 분석 쪽 팀 중심 거리 | 30m | `app/pitch_map.py:139` | 조정값 | 주석 "a goalkeeper or a distant person is left out" | 같은 파일 | (d) 조정값 | 아니오 | 팀 길이와 폭이 골키퍼 때문에 늘어남 | 작음 |
| R59 (그룹 5) 시작 점검 값 | 두 팀 평균 위치 5m, 무리당 4명, 대표 사진 키 40픽셀 | `scripts/startup_check.py:28-29, 33` | 조정값, 팀 | 주석 "(wiki/live-startup-and-halftime.md)", 값은 위키의 제안값 | `wiki/startup-check.md` "점검 기준은 모두 제안값" | (a) `match.json` 또는 `venue.json` | 아니오 | 방향 제안을 못 하거나 틀림 | 작음 |
| R62 (그룹 4) 카메라 이동 점검 기준 | 이동량 4픽셀, 점수 기준값의 80%(약 12) | `wiki/calibration-check-and-track-stitch.md` 9줄(코드 아직 없음) | 카메라(삼각대) | 이 경기장 한 곳에서 잰 값(11-20 49장, 라이브 131장) | 같은 위키 | (c) 시작 점검에 넣고 기준 사진에서 매 경기 다시 정함 | 예 | 11-20: 보정이 틀려도 시작 점검이 없었음 | 중간 |


## 5. 근거를 찾지 못한 값
"왜 고정했나"에 "근거 없음(추정: ...)"이 들어간 22개 행: R01, R02, R04(cam4 값), R05, R06, R08(값 0.10), R09, R13, R15(24픽셀), R16, R23(12.0과 14.0), R26, R28, R29(14m, 6m, 3m), R37(분류 비율 0.7), R42, R43, R45, R53, R54, R55, R56(30GB). 추정은 이유가 아닙니다.
- 같은 표본에서 정한 값이라 독립 시험이 아닌 것: R10(옷 색 최소 키, 라벨 35장면), R24(라인 간격 41m, 판정 15개), R29(골키퍼 규칙, 같은 경기 재생 비교).
- 주석과 코드가 어긋난 것: R23(`live_feedback.py` 246줄 주석 "sinking by 10 metres"와 값 14.0), R53(`coach_numbers.py` 33줄 주석 30과 48줄 `< 28`).
- 쓰이지 않는 것으로 보이는 상수: R30(`GOALKEEPER_GAP`, `grep`에서 정의 한 줄뿐).

## 6. 확인하지 못한 것
- `work/live-run-1120/run.log`, `run2.log`, `run3.log`가 비어 있어서 11-20 라이브가 확대 크기를 768과 1280 중 어느 것으로 돌았는지 확인하지 못했습니다(사용자님 말씀은 768, 명령 문서의 계획은 1280).
- 검색에서 걸린 줄 전부(상수 417줄, `cam[0-9]` 90줄, 영상 크기 119줄)를 줄마다 열어 보지는 않았습니다. 표는 요청하신 알려진 값과 검색에서 걸린 대표 값입니다.
- `cam[0-9]` 90줄 중 `app/` 10줄, `scripts/` 77줄을 확인했고 나머지 3줄의 위치는 확인하지 못했습니다.
- 선 일치 점수 계산 코드는 저장소에서 찾지 못했습니다(작업 노트 스크립트로 보임). 위키의 수치(49장)만 근거입니다.
- 이 작업폴더는 시작 전부터 수정된 파일 여러 개(예: `app/live_feedback.py`의 `isolated`)와 새 파일이 커밋 전 상태입니다. 줄 번호는 그 상태 기준입니다.

## 7. 설계안 (구현하지 않음): 설정 파일 두 장과 시작 거절 점검

### 파일 1: 경기장 설정 `work/venue-1120/venue.json` (새 파일, `calibrations.json` 옆)
경기마다 바뀌지 않는 값을 한곳에 모읍니다. 읽는 코드를 칸마다 적습니다.
| 칸 | 11-20 값(예) | 읽을 코드 |
|---|---|---|
| `venue_id` | `venue-a-stand` | 시작 점검, 보고서 |
| `camera.id` | `cam4` | `scripts/run_live_feedback.py:231`의 선택지, `scripts/track_review_clip.py:22` |
| `camera.frame` | `[1920, 1080]` | 시작 점검(입력 크기 비교) |
| `camera.pitch_top` | `0.38` | `scripts/track_review_clip.py:22`, `scripts/prepare_ball_clips.py:16` |
| `calibration.file` | `calibrations.json` | `scripts/run_live_feedback.py`(위치 인자 대신) |
| `calibration.reference_image` | 11-20 기준 사진 경로 | `app/camera_drift.py`, 시작 점검 |
| `calibration.max_rms_m` | `1.5` | `app/pitch_map.py:15` |
| `calibration.shift_red_px` | `4` | 새 점검(선 일치 점수와 이동량) |
| `pitch.length`, `pitch.width` | `89`, `62` | `app/live_feedback.py:76`, `app/goalkeeper.py:10`, `app/team_formation.py:20`, `app/team_tactics.py:16`, `app/report_scenes.py:13`, 나머지 `app/` 정의 12곳, `web/` 5개 파일(서버가 내려 줌) |
| `pitch.margin_m` | `-1.5` | `app/pitch_map.py:16` |
| `detector.tile`, `.imgsz`, `.conf` | `384`, `768`, `0.10` | `scripts/track_review_clip.py:23`, `scripts/run_live_feedback.py:230, 245` |
| `detector.imgsz_night` | `1280` | `scripts/run_live_feedback.py:245` |
| `shirt.min_height_px` | `20` | `app/team_color_profile.py:23` |
| `analysis_fps` | `5.0` | `scripts/run_live_feedback.py:221` |
| `stream.bitrate_limits_kbps` | `{1080: [2100, 3800]}` | `app/stream_health.py:25` |

### 파일 2: 경기별 설정 `work/match-YYYYMMDD/match.json` (경기마다 새로 만듦)
| 칸 | 11-20 값(예) | 읽을 코드 |
|---|---|---|
| `name`, `date`, `opponent`, `previous` | `match-20261120`, 상대 팀B, 11월 18일 | `scripts/build_detailed_report.py:645`, `scripts/start_match_day.ps1:8` |
| `lighting` | `night` | `venue.json`의 야간 묶음 선택 |
| `our_team.profile` | `<저장소>/service/team_profile.json` | `scripts/run_live_feedback.py`(`--team-profile`) |
| `attack_direction_first_half` | `-1` | `scripts/run_live_feedback.py:212` |
| `halves[].kickoff_video_s`, `.end` | 경기별 값(반별 영상 시작 초) | 분석 스크립트(`features.py:11`), 후반 전환 버튼의 허용 시간 |
| `lineup.formation`, `lineup.plan`, `lineup.names` | 예시 `4-4-2`, 좌표 표 | `coach_4231.py:9-10`, `features.py:9-10`, `scripts/build_preview_report.py:28` |
| `alerts.disabled` | `["gap_wide", "isolated"]` | `app/live_feedback.py:60` |
| `players_per_side` | `11` | `app/tactical_feedback.py:14` |
| `network.bind`, `network.public_origin` | (주소), (주소):8443 | `scripts/start_match_day.ps1:39-40`, `DEMO_*` 환경값 |
| `paths.recording_dir`, `paths.positions` | `recordings/match-20261120`, `<저장소>/alerts/<세션>/positions.jsonl` | `scripts/start_match_day.ps1:11, 15`, `scripts/record_stream_loop.ps1:8` |

### 시작 거절 점검 (`prematch_check`, 새 스크립트)
`start_match_day.ps1`의 맨 앞에서 실행하고 하나라도 실패하면 아무것도 켜지 않습니다.
1. `match.json`의 필수 칸(`our_team.profile`, `attack_direction_first_half`, `network.bind`, `name`)이 비었거나 예시 값(`null`)이면 거절하고 비어 있는 칸 이름을 보여 줍니다.
2. `our_team.profile`이 오늘 만든 것인지(날짜), 같은 보정으로 만든 것인지 확인합니다. 아니면 거절합니다.
3. 기준 사진과 현재 화면의 선 일치 점수와 이동량을 계산해 이동량이 4픽셀 이상이면 거절합니다(11-20 새 보정 49장 기준 평소 점수 19.1, 최소 17.0).
4. 수신 서버 포트가 열린 것을 확인한 뒤에만 녹화를 켭니다(`start_match_day.ps1:24-25, 33`을 "실패하면 중단"으로).
5. 그룹 4의 자동 제안(팀 묶음 대표 사진, 공격 방향 화살표, 킥오프 후보)은 벤치 화면에 한 장으로 띄우고, 코치가 누를 때까지 적용하지 않습니다.

## 8. 이 페이지에서 바로 보이는 위키의 어긋남
- `wiki/review-store-and-open-tasks.md` 39줄은 `CAM3_FROM = 1484`를 "아직 고치지 않음"이라고 적었지만 코드는 2026-11-17에 `app/camera_segments.py`의 1495와 1735로 바뀌었습니다(`wiki/detector-experiments.md` 121줄이 맞음). 위키 쪽을 고쳐야 하며 이 작업에서는 다른 위키 페이지를 수정하지 않았습니다.
- 이 페이지의 집계(59행, 근거 있음 37 / 없음 22)는 제 분류이며 값마다 근거 문장을 다시 대조하지는 않았습니다.

## 9. 후속: 59개 값의 자동·설정·코드 분류 (2026-11-22)
- 이 페이지의 59개 값을 "자동으로 정함/확인함 11, 경기장 설정 파일 16, 경기별 설정 파일 9, 코드에 둠 23"으로 나눈 표는 `work/model-improve-1122/prematch-check/out/hardcoded_classification.md`에 있고, 연결된 경기 전 점검 시제품의 시험 결과는 [prematch-check-1122.md](prematch-check-1122.md)입니다. 분류는 제안이며 코드와 설정은 바꾸지 않았습니다.
