# 보고서 작업과 파일 (/report)

근거 코드: `app/report_jobs.py`, `app/review_public.py:400-480`, `scripts/run_report_job.py`, `web/report.html`, `web/report.js`, `web/report.css`, `scripts/run_review_server.ps1`. 작성 2026-11-21. (파일 이름에 "report"를 쓰면 작업 도구가 저장을 막아서 이 이름으로 둡니다.)

## 1. 목적
- 누가: 분석가(코치에게 결과를 보여 줄 때).
- 언제: 경기 후.
- 무엇을: 경기 영상을 올리고(카메라, 우리 팀, 공격 방향, 분석 구간, 골 시각) 서버가 선수 탐지, 추적, 보고서 영상 만들기를 차례로 하게 합니다. 진행 상황과 로그를 보고, 결과 영상과 문서를 엽니다. 업로드와 변경에는 접속 토큰이 필요합니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 26~32, 107~109번입니다.
| 경로 | 방식 | 정의 | 하는 일 | 부르는 곳 | 보호 | 시험 |
|---|---|---|---|---|---|---|
| `/report`, `/report.js`, `/report.css` | GET | `app/review_public.py:214` | 보고서 화면 | `web/alerts.html:18`, `web/cards.html:29`, `web/players.html:58`, `web/differences.html:4` | Host | `test_report_jobs.py`, `test_report_upload.py` |
| `/api/v1/report/list` | POST | `:400` | 작업 목록(최대 100), 업로드 가능 여부, 카메라, 작업기 상태 | `web/report.js:87`, `scripts/run_review_server.ps1:44` | Host, Origin | `test_report_jobs.py::test_health_cameras_listing_and_log_paths` |
| `/api/v1/report/upload` | POST | `:408` | 영상 업로드와 작업 등록 | `web/report.js:158` | Host, Origin, 토큰 | `test_report_upload.py` |
| `/api/v1/report/cancel`, `/retry`, `/delete` | POST | `:439`, `:447`, `:455` | 취소, 다시, 삭제 | `web/report.js:78` | Host, Origin, 토큰 | `test_report_jobs.py::test_service_routes_need_the_token_for_every_change` |
| `/api/v1/report/log` | POST | `:463` | 단계 로그 끝 4000자 | `web/report.js:136` | Host, Origin, 토큰 | `test_report_jobs.py` |
| `/report-files/{job}/{name}` | GET | `:471` | 결과 mp4, md, json | `web/report.js:123`, `:126`, `:130` | Host, 이름 목록 | `test_report_upload.py` |

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 작업 | `<저장소>/reports/r<번호>/`: `job.json`(카메라, 팀, 방향, 구간, 골, 제목, 원래 파일 이름), `status.json`(상태, 단계), 업로드 영상, 단계 로그, 결과 파일 | 업로드 경로, 작업기(`scripts/run_report_job.py`) | 이 화면 |
| 설정(환경값) | `FOOTBALL_REPORT_TOKEN`(토큰 파일에서 읽음), `FOOTBALL_REPORT_CAMERAS`, `..._DETECTOR`, `..._CLASSIFIER`, `..._FFMPEG`, `..._CALIBRATIONS`(= `<저장소>/calibration/calibrations.json`), `..._MAX_MB`(기본 4096), `..._KEEP`(기본 40) | `scripts/run_review_server.ps1:66-77` | `app/report_jobs.py` |

## 4. 동작 규칙 (지금 코드)
- 토큰이 서버에 없으면 업로드와 변경이 모두 꺼집니다(`token_ok`가 빈 값이면 거짓, `app/report_jobs.py:33-34`). 화면은 `upload_enabled`로 이를 압니다.
- 업로드는 `Content-Length`가 4096 MB를 넘거나 받는 중에 넘으면 413, 빈 파일은 422입니다. 실패하면 작업을 "업로드가 끝나지 않았습니다"로 실패 처리합니다(`app/review_public.py:412-435`).
- 서버가 켜질 때 처리 중이던 작업을 다시 줄에 세우고 깨진 업로드는 실패로 둡니다(`reports.recover()`, `:206`).
- 작업은 한 번에 하나씩 처리합니다. 끝난 오래된 작업은 40개를 넘으면 지웁니다.
- 결과 파일은 정해진 이름(`OUTPUTS`)만 줍니다.
- 삭제는 확인 창을 거칩니다(`web/report.js:70`).

## 5. 받아들임 기준
1. 토큰 없이 업로드하면 403, 토큰이 서버에 없으면 업로드가 꺼져 있습니다. (`test_report_upload.py::test_report_upload_needs_the_token_and_serves_only_listed_outputs`, `test_report_upload_is_off_without_a_token`)
2. 골 시각은 분석 구간 안이어야 합니다. (`test_report_jobs.py::test_options_are_checked_and_goals_must_lie_inside_the_range`)
3. 취소, 다시, 삭제는 작업 상태에 따라 허용됩니다. (`test_cancel_retry_and_delete_follow_the_state_of_the_job`)
4. 서버를 다시 켜면 실행 중이던 작업이 다시 줄에 섭니다. (`test_a_restart_puts_running_jobs_back_in_the_queue_and_fails_broken_uploads`)
5. 오래된 끝난 작업은 지워지고 진행 중인 작업은 남습니다. (`test_old_finished_jobs_are_pruned_but_active_ones_stay`)
6. 모든 변경 경로가 토큰을 요구합니다. (`test_service_routes_need_the_token_for_every_change`)
7. `/report-files/..%2F..%2Fx/report.md`는 404입니다. (`test_report_upload.py`)
8. 서버 상태 확인 스크립트(`run_review_server.ps1 -Status`)가 `/api/v1/report/list`로 작업기 상태를 읽습니다. 시험 없음.

## 6. 겹치는 기능과 정리 방향
- 토큰 검사는 이 기능에만 있고 다른 곳과 겹치지 않습니다([overlaps.md](overlaps.md) O10).
- 결과 파일 제공은 다른 파일 경로와 같은 모양입니다: O2.
- `/report.css`를 알림, 카드, 선수 화면이 함께 씁니다. 스타일을 나눌 때 네 화면을 같이 확인해야 합니다.
- 보고서 화면이 사실상 분석가 화면들의 메뉴(알림, 선수, 카드 링크) 역할을 합니다. 목차 화면은 B부 질문 5.

## 7. 알려진 문제와 고정값
- `MAX_BYTES` 4096 MB, `KEEP_JOBS` 40, 목록 100개, 로그 4000자, 골 12개(`app/report_jobs.py:25-30`).
- 보정 파일은 `/train` 화면이 쓰는 파일과 같습니다. `/train`에서 보정을 바꾸면 다음 보고서 작업이 바뀐 값을 씁니다.
