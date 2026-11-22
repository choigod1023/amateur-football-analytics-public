# 하프타임 요약

근거 코드: `app/service_routes.py:74-126`, `app/halftime_report.py`, `app/halftime_accumulator.py`, `web/halftime.html`, `web/halftime.js`, `web/watch-banner.js:95-138`. 관련 위키: `wiki/outage-halftime-service.md`, `wiki/live-startup-and-halftime.md`. 작성 2026-11-21.

## 1. 목적
- 누가: 코치. 버튼은 벤치 화면과 감시 화면 오른쪽 아래에 있습니다.
- 언제: 전반이 끝났을 때, 그리고 후반 시작 때.
- 무엇을: 전반의 위치 기록 합계로 코치 말로 된 보고서(어느 진영에 오래 있었나, 수비 줄 높이, 박스 침투 횟수, 팀 모양 그림)를 만들고 엽니다. "후반 시작"을 누르면 합계를 새로 시작하고 라이브 실행에 방향을 바꾸라고 알립니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 45, 46, 50~56번입니다.
| 경로 | 방식 | 정의 | 종류 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|
| `/halftime` | GET | `app/service_routes.py:19` | 화면 | 보고서 화면(`?session=이름&half=2`) | `web/watch.js:24`, `web/watch-banner.js:110`(서버가 준 `link`) | `test_halftime_report.py::test_routes_pages_and_the_origin_rule` |
| `/halftime.js` | GET | 같은 곳 | 파일 | 보고서 그리기 | `web/halftime.html:29` | 같은 시험 |
| `/api/v1/halftime` | GET | `:74` | API | 진행 상태 | `web/watch-banner.js:142` | 같은 시험 |
| `/api/v1/halftime/report` | GET | `:80` | API | 보고서 내용 | `web/halftime.js:34` | 같은 시험 |
| `/api/v1/halftime/start` | POST | `:94` | API | 전반 끝: 보고서 만들기 | `web/watch-banner.js:104`, `:136` | 같은 시험 |
| `/api/v1/halftime/confirm` | POST | `:104` | API | 자동 초안 확인 | `web/watch-banner.js:113` | 경로 시험 없음 |
| `/api/v1/halftime/second-half` | POST | `:108` | API | 후반 시작 | `web/watch-banner.js:130` | 같은 시험 |
| `/api/v1/halftime/colour-checked` | POST | `:118` | API | 팀 색 재확인 띠 닫기 | `web/watch-banner.js:121` | 같은 시험 |
| `/api/v1/halftime/dismiss` | POST | `:122` | API | 제안이나 초안 거절 | `web/watch-banner.js:105`, `:114` | 경로 시험 없음 |

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 위치 기록 | `alerts/<세션>/positions.jsonl` | 라이브 실행 `--positions` | 합계 스레드 |
| 합계와 상태 | `alerts/<세션>/` 아래 상태 파일(`state.json`, 합계 파일), 보고서 `report.json`, 후반 `report-2.json`(`app/halftime_report.py:234-247`) | 서버의 합계 스레드(2초마다), 버튼 | 이 화면 |
| 라이브 실행에 보내는 명령 | `alerts/<세션>/control.jsonl` | `/second-half` | `scripts/run_live_feedback.py` |

## 4. 동작 규칙 (지금 코드)
- 세션은 감시 화면과 같은 "가장 최근 라이브 세션" 규칙으로 고릅니다(`app/halftime_report.py:271-273`, [overlaps.md](overlaps.md) O5).
- 상태: `waiting`, `suggested`(입력이 오래 끊긴 구간이 전반 후반부에 있으면 그 시각까지를 전반으로 제안), `ready`, `failed`, `no_positions`(위치 기록이 없음), 그리고 후반 전환 뒤 `second_half`(`:308-332`).
- 사람이 확인하기 전에는 보고서를 만들지 않습니다. 예외: 전반 후반부에 입력이 끊기면 초안을 자동으로 만들고(`source: auto`) 사람에게 "맞음/아님"을 묻습니다(`:275-291`, `web/watch-banner.js:111-114`).
- "아님"으로 거절한 제안은 같은 끊김에 대해 다시 묻지 않습니다(`dismissed`).
- 후반 시작은 확인 창("…팀이 화면 …으로 공격합니다. 맞습니까?")을 거칩니다(`web/watch-banner.js:125-131`).
- 보고서 그림은 89 x 62 m, 1m에 8픽셀, 우리 팀이 오른쪽으로 공격하게 그립니다(`web/halftime.js:13-31`).

## 5. 받아들임 기준
1. `/halftime`, `/halftime.js`, `/watch`는 200이고, 다른 Origin의 POST는 403입니다. (`test_halftime_report.py::test_routes_pages_and_the_origin_rule`)
2. 위치 기록이 없는 세션의 상태는 `no_positions`이고 시작 방법을 알려 줍니다. (`test_a_session_without_positions_says_how_to_start_the_run`)
3. 버튼을 누르기 전에는 보고서가 없고, 누르면 합계로 만듭니다. (`test_the_report_waits_for_a_person_and_is_made_from_the_sums_on_the_button`)
4. 전반 후반부의 끊김은 초안을 바로 만들고 사람이 확인하거나 거절합니다. (`test_an_outage_late_in_the_first_half_makes_a_draft_at_once_and_a_person_confirms_or_refuses`)
5. 거절한 초안은 지워지고 같은 끊김으로 다시 만들지 않습니다. (`test_a_refused_draft_is_deleted_and_not_made_again_for_the_same_stop`)
6. 후반 시작은 전반 합계를 지키고 새 합계를 시작하며 라이브 실행에 알립니다. (`test_the_second_half_starts_new_sums_keeps_the_first_and_tells_the_live_run`)
7. 보고서 문장에 개발 용어와 숫자가 없습니다. (`test_the_report_is_in_coach_words_without_developer_numbers`)
8. `/api/v1/halftime/confirm`과 `/dismiss` 경로를 직접 부르는 시험은 없습니다(함수 시험만 있음).
9. `label-` 세션이 가장 최근일 때 `/api/v1/halftime`은 그 세션을 보고 `no_positions`를 냅니다(코드로 판단). 시험 없음, 의도 확인 필요.

## 6. 겹치는 기능과 정리 방향
- 버튼과 띠가 감시용 스크립트(`web/watch-banner.js`)에 함께 들어 있어, 하프타임 기능과 멈춤 감시 기능이 한 파일입니다. A부에서는 그대로 두고 서버 쪽 라우터만 나눕니다(경기 화면 스크립트이므로).
- 세션 고르기 규칙 중복: O5.

## 7. 알려진 문제와 고정값
- 11월 20일 경기에서 후반 전환 버튼은 킥오프보다 약 1분 빨리 눌렸습니다(`wiki/match-1120-live-and-report.md` 8줄).
- 고정값: `BREAK_SECONDS`, `EARLIEST`, 전반 길이(`app/halftime_report.py`), 합계 스레드 2초. 자세한 값은 `wiki/hardcoded-values-audit.md`(다른 작업)를 봅니다.
