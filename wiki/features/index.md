# 검토 서버 기능 명세 목차

작성 2026-11-21. 대상: 검토 서버(`app/review_public.py`의 `create_app`, 운영 포트 8443)와 따로 실행하는 송출 상태 서버. 근거는 이 저장소의 코드를 읽은 것과, 임시 빈 저장소로 앱을 만들어 경로를 세고 응답을 확인한 것입니다. 운영 저장소는 읽기만 했고 코드와 서버는 바꾸지 않았습니다.

## 한눈에
- 검토 서버의 등록 경로 **100개**(데코레이터 82 + 반복문·도우미 18). catch-all 하나가 화면 별칭 38개를 내므로 열 수 있는 주소는 **137개**입니다. 송출 상태 서버 3개를 더해 [routes.csv](routes.csv)는 **141줄**입니다.
- 화면(HTML) 파일 17개, 검토 서버의 화면 주소 17개. 어느 화면도 부르지 않는 경로는 `/api/v1/shots/clear`, `/api/v1/reappearance/decisions`, `/review-differences`이고, 손으로만 켜는 송출 상태 서버의 경로 3개도 쓰임이 확인되지 않았습니다(모두 "쓰임 불명").
- 가장 급한 발견: 벤치·감시·하프타임이 `label-` 판정 묶음을 "라이브 실행"으로 고릅니다. 2026-11-21 저장소 기준 `/api/v1/bench`가 `label-1121-team`의 질문을 현재 알림으로 냅니다([overlaps.md](overlaps.md) O5).

## 기능 페이지
각 페이지는 1 목적, 2 화면과 경로, 3 자료, 4 동작 규칙, 5 받아들임 기준, 6 겹치는 기능과 정리 방향, 7 알려진 문제와 고정값의 순서입니다.
| 페이지 | 누가 | 주소 |
|---|---|---|
| [bench-and-live-video.md](bench-and-live-video.md) | 코치(경기 중) | `/bench`, `/live`, `/api/v1/bench*`, `/live-video.mjpg` |
| [team-select.md](team-select.md) | 코치(킥오프 직후) | `/team-select`, `/api/v1/team-select*` |
| [halftime.md](halftime.md) | 코치(하프타임) | `/halftime`, `/api/v1/halftime*` |
| [service-watch-and-stream.md](service-watch-and-stream.md) | 분석가·코치(경기 중) | `/watch`, `/api/v1/service*`, 송출 상태 서버 `/stream` |
| [alerts-and-label-sessions.md](alerts-and-label-sessions.md) | 분석가 | `/alerts`, `/api/v1/alerts/*`, `label-` 세션 |
| [shots.md](shots.md) | 분석가(경기 후) | `/shots`, `/api/v1/shots*` |
| [analyst-tags.md](analyst-tags.md) | 분석가(경기 중) | `/tag`, `/api/v1/analyst-tags*` |
| [ball.md](ball.md) | 분석가 | `/ball`, `/api/v1/ball/*` |
| [train-missed-players.md](train-missed-players.md) | 분석가 | `/train`, `/api/v1/training-labels*`(보정 찍기 포함) |
| [players-cards-events.md](players-cards-events.md) | 분석가 | `/players`, `/cards`, `/events`, `/train/reappearance`, `/review-differences` |
| [video-jobs.md](video-jobs.md) | 분석가 | `/report`, `/api/v1/report/*` (보고서 작업. 파일 이름에 "report"를 쓰면 작업 도구가 저장을 막아 이 이름) |
| [media-files.md](media-files.md) | 화면 스크립트 | 사진·영상 파일 경로 11개 |
| [common.md](common.md) | 모두 | 접속 확인, 정적 화면, 설정, `/`, 다른 서버 6개, 화면별 자원표 |

## 분석과 계획
| 페이지 | 내용 |
|---|---|
| [routes.csv](routes.csv) | 경로 전체 표(번호, 서버, 경로, 방식, 정의 위치, 종류, 하는 일, 읽는 자료, 쓰는 자료, 인증·보호, 부르는 화면, 시험, 상태, 기능 페이지) |
| [overlaps.md](overlaps.md) | 겹치는 기능 15가지와 권고(합치기, 공통 부분만 빼기, 그대로 두기) |
| [refactor-plan.md](refactor-plan.md) | A부: 동작 변화 없는 정리 19단계(0~18), B부: 사용자님이 정할 질문 9개, 위험 |

## 확인하지 못한 것
- 화면을 실제 브라우저로 열어 본 확인은 하지 않았습니다(코드와 시험용 앱의 응답만).
- `web/alerts.js`의 `label-` 정렬은 하위 작업의 기록(`work/model-improve-1121/server-labels/sim_order.cjs`)만 보았고 다시 돌리지 않았습니다.
- 송출 상태 서버를 실제로 누가 언제 켜는지는 기록이 없습니다.
- 다른 작업이 쓰는 `wiki/hardcoded-values-audit.md`, `wiki/agents/`와는 겹치지 않게 고정값은 짧게만 적었습니다.
