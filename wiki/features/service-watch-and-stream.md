# 송출 상태와 감시

근거 코드: `app/service_watch.py`, `app/service_routes.py:47-72`, `web/watch.html`, `web/watch.js`, `web/watch-banner.js`, `app/stream_health.py`, `scripts/run_stream_health.py`, `web/stream_health.html`. 관련 위키: `wiki/outage-halftime-service.md`, `wiki/stream-diagnosis.md`. 작성 2026-11-21.

## 1. 목적
- 누가: 분석가(감시), 코치(벤치 화면 위의 빨간 띠).
- 언제: 경기 중.
- 무엇을: 라이브 분석이 멈췄는지(영상 끊김, 분석 프로그램 종료, 응답 없음)를 빨간 띠와 소리로 알리고, 멈춤 기록을 남깁니다. 따로 실행하는 송출 상태 화면은 녹화 파일로 비트레이트와 끊김을 재서 초록·노랑·빨강으로 알려 줍니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 41~44, 47~49, 139~141번입니다.
| 경로 | 서버 | 방식 | 정의 | 종류 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|---|
| `/watch` | 검토 | GET | `app/service_routes.py:19` | 화면 | 상태, 멈춤 기록 표, 하프타임 칸 | `web/halftime.html:27` | `test_halftime_report.py::test_routes_pages_and_the_origin_rule` |
| `/watch.js`, `/watch.css` | 검토 | GET | 같은 곳 | 파일 | 감시 화면 그리기와 스타일 | `web/watch.html:33`, `:8`, `web/halftime.html:8` | 같은 시험(JS만) |
| `/watch-banner.js` | 검토 | GET | 같은 곳 | 파일 | 빨간 띠, 소리, 알림, 전반 끝·후반 시작 버튼 | `web/bench.html:41`, `web/watch.html:32` | 같은 시험 |
| `/api/v1/service` | 검토 | GET | `:62` | API | 상태와 멈춤 기록 8개 | `web/watch-banner.js:142` | 같은 시험 |
| `/api/v1/service/ack` | 검토 | POST | `:66` | API | 소리 끄기 | `web/watch-banner.js:73` | 같은 시험 |
| `/api/v1/service/finish` | 검토 | POST | `:70` | API | 멈춤을 사람이 끝냄 | `web/watch-banner.js:74` | 경로 시험 없음 |
| `/stream` | 송출 상태(8791) | GET | `app/stream_health.py:305` | 화면 | 송출 상태 진단 | 직접 엶 | `test_stream_health.py::test_web_app_serves_page_and_cached_json` |
| `/api/stream-health` | 송출 상태(8791) | GET | `app/stream_health.py:301` | API | 마지막 측정 판정 | `web/stream_health.html:48` | 같은 시험 |
| `/` | 송출 상태(8791) | GET | `scripts/run_stream_health.py:33` | 화면 | `/stream`으로 이동 | 직접 엶 | 시험 없음 |

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 알림 기록과 하트비트 | `alerts/<세션>/alerts.jsonl`. 하트비트 줄에 `pid`, `wall` | 라이브 실행 | 감시 스레드(2초마다) |
| 멈춤 기록 | `<저장소>/service/outages.jsonl`(추가만): `down`, `cause`, `up`, `finished` 줄 | 감시 스레드, `/finish` | 서버 시작 때 다시 읽음 |
| 녹화 파일 | 녹화 폴더의 가장 최근 파일(`FOOTBALL_RECORD_DIR` 또는 `--directory`, `--file`) | 녹화 스크립트 | 송출 상태 서버(ffprobe 3초마다) |

## 4. 동작 규칙 (지금 코드)
- 감시 대상: 벤치와 같은 "가장 최근 라이브 세션"(`app/service_watch.py:136-145`).
- 판정(`:147-169`): 하트비트의 프로세스가 없으면 `process_dead`, 마지막 줄이 `no_input`이면 `video_lost`, 하트비트가 있는데 파일이 25초 넘게 안 바뀌면 프로세스가 살아 있으면 `video_lost`, 확인할 수 없으면 `silent`. 하트비트와 상태 줄이 모두 없으면 `unknown`(멈춤으로 기록하지 않음). 3시간 넘게 안 바뀐 실행은 `idle`(`IDLE_AFTER`).
- 사람이 `finish`로 끝낸 실행은 파일이 다시 바뀔 때까지 조용합니다.
- 화면 쪽: 서버 응답이 6초 넘게 없으면 "서버 응답 없음" 띠를 띄웁니다(`web/watch-banner.js:6`). 소리는 멈춤 하나에 한 번만, 사용자가 켜 둔 경우에만 냅니다(브라우저에 기억, `:8`, `:44-59`).
- 송출 상태 판정 기준표는 `wiki/stream-diagnosis.md`에 있습니다(1080p 3800kbps 이상 초록 등).
- 송출 상태 서버는 8443 포트를 거부합니다(`scripts/run_stream_health.py:47-48`).

## 5. 받아들임 기준
1. 하트비트가 새로우면 `ok`이고 기록이 없습니다. (`test_service_watch.py::test_a_run_with_fresh_heartbeats_is_ok_and_nothing_is_logged`)
2. 하트비트 없는 조용한 파일은 `unknown`이고 멈춤이 아닙니다. (`test_a_quiet_file_without_heartbeats_is_unknown_and_never_an_outage`)
3. 프로세스가 죽으면 파일이 새로워도 `process_dead`입니다. (`test_a_dead_process_is_found_even_while_the_file_is_still_fresh`)
4. 서버를 다시 켜도 열린 멈춤의 시작 시각이 유지됩니다. (`test_an_open_outage_keeps_its_start_after_the_server_restarts`)
5. `person_check` 세션은 감시하지 않습니다. (`test_the_rating_sessions_are_not_watched`) `label-` 세션은 감시 대상이 됩니다(지금 동작). 시험 없음, 의도 확인 필요.
6. `POST /api/v1/service/finish`는 열린 멈춤을 닫고 `finished`를 씁니다. 경로 시험 없음(`test_finishing_closes_the_outage_and_stays_quiet_until_the_run_writes_again`은 함수 시험).
7. 녹화 파일이 없으면 송출 상태는 회색 "기다림"입니다. (`test_stream_health.py::test_no_file_is_gray_waiting`)
8. 송출 상태 서버는 POST를 받지 않습니다(405). (`test_web_app_serves_page_and_cached_json`)

## 6. 겹치는 기능과 정리 방향
- 벤치 위쪽 띠(10초)와 이 빨간 띠(25초)가 같은 일을 다른 기준으로 합니다: [overlaps.md](overlaps.md) O4, B부 질문 4.
- 세션 고르기 규칙 중복과 `label-` 세션 문제: O5, B부 질문 2.
- 송출 상태 화면은 검토 서버에 없고 시작 스크립트도 없습니다. 붙이려면 페이지 안 스크립트를 파일로 빼야 합니다(CSP): O14, B부 질문 6.

## 7. 알려진 문제와 고정값
- `STALE = 25`, `IDLE_AFTER = 3시간`(`app/service_watch.py:29-30`), 화면 `LOST_AFTER = 6000ms`(`web/watch-banner.js:6`), 폴링 2초(`:156`).
- 읽기 호출이 멈춘 채 돌아오지 않는 경우는 라이브 실행 쪽에서 감지하지 못합니다(`wiki/live-service-audit.md` 12절 남은 위험). 감시 화면은 하트비트가 끊긴 것으로만 알 수 있습니다.
- 송출 상태 서버는 로그인이 없어 127.0.0.1에만 열도록 안내되어 있습니다(`wiki/stream-diagnosis.md`).
