# 실시간 벤치 화면과 라이브 영상

근거 코드: `app/bench_view.py`, `app/review_public.py:389-391`, `app/service_routes.py:128-155`, `app/coach_feedback.py`, `app/live_video_routes.py`, `web/bench.html`, `web/bench.js`, `web/bench-extra.js`, `web/live.html`, `web/live-video-view.js`. 관련 위키: `wiki/bench-screen.md`, `wiki/outage-halftime-service.md`. 작성 2026-11-21.

## 1. 목적
- 누가: 코치(벤치에서 태블릿이나 휴대폰으로).
- 언제: 경기 중.
- 무엇을: 가장 최근 코칭 알림 하나를 크게 보고, 이전 알림 5개, 영상 입력이 살아 있는지, 지금 두 팀 위치(작은 지도), 라이브 영상을 한 화면에서 봅니다. 알림마다 "도움됨/아님"을 누를 수 있습니다.
- `/live`는 영상만 크게 보는 화면입니다(보기만 하는 사람용).

## 2. 화면과 경로
[routes.csv](routes.csv)의 24, 40, 57~59, 77~80, 113~115번입니다.
| 경로 | 방식 | 정의 | 종류 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|
| `/bench` | GET | `app/review_public.py:216`(별칭) | 화면 | 벤치 화면 | `web/live.html:11`, `web/watch.html:30` | `test_bench_view.py::test_routes_serve_the_page_and_the_snapshot` |
| `/bench.js`, `/bench.css` | GET | `app/review_public.py:216` | 파일 | 큰 알림, 이전 알림, 위쪽 띠 | `web/bench.html:42`, `:8` | 같은 시험 |
| `/bench-extra.js` | GET | `app/service_routes.py:19` | 파일 | 작은 지도와 의견 버튼 | `web/bench.html:43` | `test_coach_feedback.py` |
| `/api/v1/bench` | GET | `app/review_public.py:389` | API | 화면 전체 자료 한 번에 | `web/bench.js:66`, `web/bench-extra.js:114` | `test_bench_view.py` 8개 |
| `/api/v1/bench/minimap` | GET | `app/service_routes.py:130` | API | 지금 두 팀 위치 | `web/bench-extra.js:118` | `test_coach_feedback.py::test_the_map_route_and_a_missing_file` |
| `/api/v1/bench/feedback` | GET | `app/service_routes.py:142` | API | 코치 의견과 검토자 판정 | `web/bench-extra.js:108` | `test_coach_feedback.py::test_routes_check_the_origin_and_the_values_and_report_both_ratings` |
| `/api/v1/bench/feedback` | POST | `app/service_routes.py:149` | API | 코치 의견 저장 | `web/bench-extra.js:68` | 같은 시험 |
| `/live` | GET | `app/live_video_routes.py:129` | 화면 | 영상만 | `web/bench.html:22` | 시험 없음 |
| `/live-video.css`, `/live-video-view.js` | GET | `app/live_video_routes.py:144-145` | 파일 | 영상 칸 | `web/bench.html:19`, `:44`, `web/live.html:8`, `:13` | 시험 없음 |
| `/live-video.mjpg` | GET | `app/live_video_routes.py:147` | 영상 | 수신 영상을 JPEG 연속으로 | `web/live-video-view.js:13` | 시험 없음 |
벤치 화면은 이 밖에 `/watch-banner.js`와 `/api/v1/service`, `/api/v1/halftime`도 부릅니다([service-watch-and-stream.md](service-watch-and-stream.md), [halftime.md](halftime.md)).

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 알림 기록 | `<저장소>/alerts/<세션>/alerts.jsonl`: 한 줄에 `time`, `kind`, `title`, `text`, `polarity`(`status`면 상태 줄), `detail`; 하트비트 줄은 `kind` 또는 `type`이 `heartbeat` | `scripts/run_live_feedback.py` | 벤치, 감시, 하프타임, `/alerts` |
| 검토자 판정 | `alerts/labels/<세션>-<번호>.json`: `id`, `label`(ok, wrong, useless), `note`, `updated` | `/alerts` | 벤치의 종류별 정확도 |
| 코치 의견 | `alerts/labels-coach/<세션>-<번호>.json`: `id`, `session`, `number`, `label`(ok, wrong), `origin: coach_button`, `kind`, `at` | `POST /api/v1/bench/feedback` | `GET /api/v1/bench/feedback` |
| 위치 기록 | `alerts/<세션>/positions.jsonl`(머리 줄과 초마다 한 줄) | 라이브 실행(`--positions`) | 작은 지도, 하프타임 |
| 라이브 영상 | RTSP `LIVE_VIDEO_URL`(기본 같은 컴퓨터의 수신 서버 18554 포트 `match`) | 송출 수신(MediaMTX) | `/live-video.mjpg` |

## 4. 동작 규칙 (지금 코드)
- 세션 고르기: `alerts.jsonl`이 가장 최근에 바뀐 세션 중 `kind`가 `person_check`가 아닌 줄이 하나라도 있는 세션입니다(`app/bench_view.py:137-145`). `?session=이름`(40자 이하)으로 고정할 수 있지만 화면은 쓰지 않습니다. `label-` 세션도 라이브로 고릅니다(아래 7절).
- 현재 알림과 이전 알림: 하트비트 줄과 `person_check` 줄을 뺀 줄을 거꾸로 세어 맨 앞 1개가 현재, 다음 5개가 이전입니다(`RECENT = 5`, `:28`, `:159-171`). 상태 줄(`no_input`, `input_back`)도 "급함"으로 목록에 들어갑니다.
- 우선순위 색: box_attack, conceded_run은 급함, isolated, run은 주의, line_drop, gap_wide와 모르는 종류는 참고(`:22`).
- 알림 나이: 서버가 그 줄을 처음 본 시각부터 셉니다. 서버가 켜질 때 이미 있던 줄은 파일 수정 시각을 쓰고 "(이전에 나온 알림, 시간 추정)"을 붙입니다(`:150-157`, `web/bench.js:40`). 15초가 지나면 큰 알림을 흐리게 합니다(`web/bench.js:4`).
- 입력 상태: 마지막 상태 줄이 `no_input`이면 입력 없음, 하트비트가 10초 넘게 없으면 입력 없음, 하트비트가 있으면 정상, 둘 다 없으면 모름(`app/bench_view.py:49-67`). 서버 응답이 5초 넘게 없으면 띠가 "화면 연결 끊김"이 됩니다(`web/bench.js:5`, `:16-22`).
- 종류별 정확도: `alerts/labels`의 판정 중 지금 `alerts/` 안에 있는 세션의 판정만 셉니다. 5개 미만이면 "표본 적음"(`MIN_SAMPLE`, `:26`, `:38-42`).
- 새로 고침: `bench.js`가 1초, `bench-extra.js`도 1초마다 `/api/v1/bench`를 따로 부릅니다. 지도는 1초, 의견은 2.5초마다입니다(`web/bench-extra.js:121-124`).
- 코치 의견: 상태 줄, 하트비트, `half_switch`, `camera_moved`, `camera_back`, `person_check` 줄에는 저장할 수 없습니다(`app/coach_feedback.py:27-28`). 검토자 판정 파일은 건드리지 않습니다.
- 작은 지도: 기본은 카메라에서 본 방향이고, 화면에서 팀 방향으로 바꾸면 브라우저에 기억합니다(`web/bench-extra.js:10-11`). 5초 넘은 위치는 흐리게 합니다.
- 라이브 영상: 첫 시청자가 ffmpeg 하나를 켜고 모든 시청자가 나눠 봅니다. 최대 20명, 960 폭, 초당 8장, 마지막 시청자가 떠나고 15초 뒤 끔, 새 그림이 5초 없으면 요청을 끝내고 화면이 3초 뒤 다시 엽니다. 연결이 이어져도 10분마다 다시 엽니다(`app/live_video_routes.py:19-24`, `web/live-video-view.js:15-18`).

## 5. 받아들임 기준
1. `GET /bench`, `/bench.js`, `/bench.css`는 200입니다. (`test_bench_view.py::test_routes_serve_the_page_and_the_snapshot`)
2. 저장소에 알림 파일이 없으면 `/api/v1/bench`는 `session: null`, 입력 상태 `unknown`입니다. (`test_bench_view.py::test_snapshot_without_a_store_says_nothing_to_show`)
3. 알림 7개가 있으면 현재 1개와 이전 5개가 최신 순으로 나오고 종류별 정확도가 붙습니다. (`test_bench_view.py::test_snapshot_shows_newest_alert_five_before_and_accuracy`)
4. `person_check` 세션과 상태 줄은 라이브 알림으로 세지 않습니다. (`test_bench_view.py::test_review_sessions_and_status_rows_do_not_count_as_live_alerts`)
5. `label-` 세션만 가장 최근이면 `/api/v1/bench`는 그 세션을 고릅니다(지금 동작). 시험 없음, 의도 확인 필요.
6. 하트비트가 10초 넘게 없으면 상태는 `no_input`입니다. (`test_bench_view.py::test_input_state_from_status_rows_and_heartbeats`)
7. 다른 Origin의 `POST /api/v1/bench/feedback`은 403이고, 올바른 요청은 `labels-coach`에만 씁니다. (`test_coach_feedback.py::test_routes_check_the_origin_and_the_values_and_report_both_ratings`, `test_the_reviewer_wins_and_his_files_are_never_touched`)
8. 위치 파일이 없으면 `/api/v1/bench/minimap`은 `positions: null`입니다. (`test_coach_feedback.py::test_the_map_route_and_a_missing_file`)
9. ffmpeg가 없으면 `/live-video.mjpg`는 503, 21번째 시청자도 503입니다. 시험 없음.
10. `/live`는 200이고 영상 칸 하나만 있습니다. 시험 없음.

## 6. 겹치는 기능과 정리 방향
- 상태 표시 3개(위쪽 띠 10초 기준, 빨간 띠 25초 기준, 영상 칸)가 서로 다른 순간에 바뀝니다: [overlaps.md](overlaps.md) O4. B부 질문 4.
- 같은 화면이 `/api/v1/bench`를 초당 2번 부릅니다(O4). 경기 화면이므로 A부 마지막 단계, 경기 없는 날에만.
- 세션 고르기 규칙이 감시 화면과 복사되어 있고 `label-` 세션을 거르지 않습니다: O5, B부 질문 2.
- `/alerts` 세션 보관이 이 화면의 정확도 문구를 바꿉니다: O15.
- 벤치 경로가 두 파일(`app/review_public.py`, `app/service_routes.py`)에 나뉘어 있습니다. A부에서 한 라우터로 모읍니다.

## 7. 알려진 문제와 고정값
- 2026-11-21 저장소 기준으로 `/api/v1/bench`가 `label-1121-team`을 라이브 세션으로 내고 `team_ours` 항목을 현재 알림으로 보여 줍니다(읽기만 해서 확인). 라이브 실행이 알림을 쓰기 시작하면 바뀝니다.
- 2026-11-20 경기에서 작은 지도가 나오지 않았습니다. 라이브 명령의 `--positions`가 다른 폴더에 썼기 때문입니다(`wiki/match-1120-live-and-report.md` 16줄).
- 고정값: `HEARTBEAT_STALE = 10`, `RECENT = 5`, `MIN_SAMPLE = 5`(`app/bench_view.py:26-28`), `STALE_AFTER = 15`, `LOST_AFTER = 5`(`web/bench.js:4-5`), 지도 흐림 5초(`web/bench-extra.js:8`), 영상 `MAX_VIEWERS = 20`, `WIDTH = 960`, `FPS = 8`, `IDLE_STOP = 15`, `STALL_END = 5`(`app/live_video_routes.py:20-24`), 의견 번호 최대 12개(`app/service_routes.py:146`). 고정값 전체 목록은 다른 작업의 `wiki/hardcoded-values-audit.md`를 봅니다.
- 모든 화면처럼 로그인이 없습니다(Host와 Origin 확인만). 시제품이므로 공개 배포 전에는 인증을 추가해야 합니다(`wiki/live-service-audit.md` 6절).
