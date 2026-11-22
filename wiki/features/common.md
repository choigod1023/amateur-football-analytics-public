# 공통: 인증, 정적 파일, 설정, 다른 서버

근거 코드: `app/review_public.py:191-238`, `:531-543`, `:628-634`, `scripts/run_review_server.ps1`, `scripts/start_review_server_at_logon.ps1`, `scripts/start_match_day.ps1`, 그 밖의 서버 파일(아래 5절). 작성 2026-11-21.

## 1. 목적
- 검토 서버 하나(`app/review_public.py`의 `create_app`)가 분석가 화면, 코치 화면, 분석 세션용 API를 모두 냅니다. 이 페이지는 모든 기능이 함께 쓰는 부분(접속 확인, 화면 파일 제공, 시작 방법과 설정)과 첫 주소 `/`, 이 저장소에 있는 다른 서버들을 적습니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 1~4, 88, 127~138번입니다.
| 경로 | 정의 | 하는 일 | 시험 |
|---|---|---|---|
| `/` | `app/review_public.py:239` | 예전 "Touchline" 라이브 대시보드(`web/index.html`) | `test_review_dashboard.py::test_root_is_live_dashboard_with_all_assets_and_separate_train` |
| `/api/v1/status`, `/api/v1/analysis`, `/api/v1/frame.jpg` | `:243`, `:252`, `:257` | 라이브 분석 스냅샷(환경값 `FOOTBALL_LIVE_SNAPSHOT_DIR`이 있을 때만 실제 값) | `test_live_snapshot.py` 4개 |
| `/{name:path}` | `:537` | 별칭 표 `allowed_static`(`:211-225`)에 있는 38개 주소만 `web/`에서 돌려줌 | `test_review_public.py::test_service_rejects_wrong_host_and_only_serves_expected_files` |
| 별칭 11개(`/api-auth.js`, `/freshness.js`, `/teams.js`, `/pitch.js`, `/app.js`, `/sequences.js`, `/manual-confirmation.js`, `/live-bookmarks.js`, `/live-video.js`, `/minimap-motion.js`, `/match-roster.js`) | `:222-225` | 예전 대시보드 자원 | 첫 화면 시험이 모두 200인지 확인 |
| `/style.css` | `:221` | 예전 대시보드, 학습, 공, 이벤트 화면 공용 | 같은 시험 |

### 경로 수 (2026-11-21, 이 작업 폴더의 코드)
- 검토 서버에 등록된 경로는 **100개**입니다. 시험용 빈 저장소로 `create_app`을 만들어 `app.routes`를 세어 확인했습니다.
  - 데코레이터(`@app.get`, `@app.post`)로 등록: 82개(`app/review_public.py` 52, `app/service_routes.py` 13, `app/analyst_tags.py` 6, `app/shot_routes.py` 5, `app/team_select_routes.py` 4, `app/live_video_routes.py` 2).
  - 반복문이나 도우미로 등록(데코레이터 검색에 안 잡힘): 18개(`app/service_routes.py:59-60` 7, `app/team_select_routes.py:64-65` 3, `app/shot_routes.py:49-51` 3, `app/analyst_tags.py:91-93` 3, `app/live_video_routes.py:144-145` 2).
  - `APIRouter`와 `add_api_route`는 이 저장소에 없습니다.
- catch-all 하나가 별칭 38개를 냅니다. 그래서 브라우저가 열 수 있는 서로 다른 주소는 100 - 1 + 38 = **137개**입니다(경로 틀이 있는 파일 경로 11개는 한 줄로 셈).
- 별도 서버인 송출 상태 서버의 경로 3개를 더해 [routes.csv](routes.csv)는 141줄입니다.
- 화면(HTML) 파일은 `web/`에 17개입니다. 검토 서버는 그중 16개 파일을 17개 주소로 냅니다(`/`, `/train`, `/train/reappearance`와 `/review-differences`(같은 파일), `/events`, `/report`, `/alerts`, `/bench`, `/players`, `/cards`, `/ball`, `/watch`, `/halftime`, `/shots`, `/tag`, `/live`, `/team-select`). 남은 `stream_health.html` 1개는 송출 상태 서버가 냅니다.

### 화면별로 불러오는 자원과 부르는 경로
| 화면 파일 | 불러오는 JS·CSS | 부르는 API·파일 경로 |
|---|---|---|
| `index.html`(`/`) | `style.css`, `api-auth.js`, `freshness.js`, `teams.js`, `pitch.js`, `minimap-motion.js`, `match-roster.js`, `app.js`, `sequences.js`, `manual-confirmation.js`, `live-bookmarks.js`, `live-video.js`, `training-label.js`, `review-annotation.js` | `/api/v1/status`, `/api/v1/analysis`, `/api/v1/frame.jpg`; 이 서버에 없는 것: `/api/v1/proxy-capabilities`, `/api/v1/live-bookmarks`, `/api/v1/sequences`, `/api/v1/manual-snapshot`, `/api/v1/manual-track`, `/api/v1/upload`, `/api/v1/live`, `/api/v1/training-labels/snapshot`, `/next-sample` |
| `train.html` | `style.css`, `training-label.js`, `review-annotation.js`, `minimap.js` | `/api/v1/training-labels/*` 12개, `/thumbs/*` |
| `alerts.html` | `report.css`, `alerts.css`, `alerts.js` | `/api/v1/alerts/list`, `/label`, `/alert-files/*` |
| `bench.html` | `bench.css`, `live-video.css`, `watch-banner.js`, `bench.js`, `bench-extra.js`, `live-video-view.js` | `/api/v1/bench`, `/bench/minimap`, `/bench/feedback`, `/api/v1/service`, `/service/ack`, `/service/finish`, `/api/v1/halftime/*`, `/live-video.mjpg` |
| `watch.html` | `watch.css`, `watch-banner.js`, `watch.js` | `/api/v1/service*`, `/api/v1/halftime*` |
| `halftime.html` | `watch.css`, `halftime.js` | `/api/v1/halftime/report` |
| `live.html` | `live-video.css`, `live-video-view.js` | `/live-video.mjpg` |
| `team_select.html` | `team-select.js`(페이지 안 스타일) | `/api/v1/team-select*`, `/team-select-files/*` |
| `tag.html` | `tag.css`, `tag.js` | `/api/v1/analyst-tags*`, `/analyst-clip/*` |
| `shots.html` | `shots.css`, `shots.js` | `/api/v1/shots`, `/tag`, `/extra`, `/shots-clip/*` |
| `ball.html` | `style.css`, `ball.js`, `ball-verify.js` | `/api/v1/ball/*`, `/ball-media/*` |
| `events.html` | `style.css`, `events.js` | `/api/v1/events/*`, `/event-media/*` |
| `players.html` | `report.css`, `alerts.css`, `players.js`, `team-names.js` | `/api/v1/players/*`, `/player-files/*`, `/api/v1/team-select` |
| `cards.html` | `report.css`, `alerts.css`, `cards.js` | `/api/v1/cards/list`, `/card-files/*` |
| `report.html` | `report.css`, `report.js`, `team-names.js` | `/api/v1/report/*`, `/report-files/*`, `/api/v1/team-select` |
| `differences.html` | `differences.css`, `differences.js` | `/api/v1/differences`, `/difference-files/*` |
| `stream_health.html` | 없음(페이지 안 스크립트) | `/api/stream-health`(다른 서버) |
- 어느 화면도 불러오지 않는 JS: `web/preview-recording.js` 하나입니다. `scripts/preview_recording.py:46-53`이 `index.html`에 끼워 넣어 씁니다(검토 서버에서는 404). `team_select.js`와 `team_names.js`는 하이픈 이름(`/team-select.js`, `/team-names.js`)으로 불립니다.
- 다른 화면으로 가는 링크가 없는 화면: `/tag`, `/shots`, `/team-select`, `/review-differences`. 주소를 직접 열어야 합니다.

## 3. 자료와 설정
| 설정 | 어디서 | 뜻 |
|---|---|---|
| `FOOTBALL_REVIEW_ORIGIN` | `scripts/run_review_server.ps1:66` ← `server.json`의 `origin` | 브라우저가 쓰는 주소. Host와 Origin 확인의 기준. `http://`만 받음(`app/review_public.py:192-194`) |
| `FOOTBALL_REVIEW_DIR` | `:67` ← `store` | 저장소(절대 경로, 있어야 함) |
| `FOOTBALL_REVIEW_BIND`, `..._PORT` | `:68-69` | 기본 127.0.0.1, 8443(`app/review_public.py:633-634`). 실제 값은 (주소) |
| `FOOTBALL_LIVE_SNAPSHOT_DIR` | `:70`(선택) | `/api/v1/status` 등의 자료 |
| `FOOTBALL_REPORT_*` | `:71-77` | 보고서 작업([video-jobs.md](video-jobs.md)) |
| `LIVE_VIDEO_URL`, `LIVE_VIDEO_FFMPEG` | 환경값(설정 파일에는 없음) | 라이브 영상([bench-and-live-video.md](bench-and-live-video.md)) |
| `FOOTBALL_RECORDINGS` | 환경값 | 분석가 태그 클립용 녹화 폴더 |
`server.json`은 저장소 밖(`work/report-config/server.json`)에 있고 토큰 파일 경로만 적습니다(`scripts/run_review_server.ps1:9-23`).

## 4. 동작 규칙 (지금 코드)
- **접속 확인(미들웨어 `restrict`, `app/review_public.py:227-237`)**: 모든 요청의 Host 헤더가 설정한 주소와 같지 않으면 403. POST는 Origin 헤더가 설정한 주소와 같지 않으면 403. 응답에 `Cache-Control: no-store`(경로가 정하지 않았을 때), `X-Content-Type-Options: nosniff`, CSP(`default-src 'self'`, 이미지 `self`와 data, 스타일 `self`와 인라인, 연결 `self`, 프레임 금지)를 붙입니다. 로그인은 없습니다(사용자님이 선택, `wiki/live-service-audit.md` 6절).
- **토큰**: 보고서 변경 5개 경로만 `X-Report-Token`을 확인합니다(`:404-406`).
- **정적 파일**: catch-all은 별칭 표에 있는 주소만, 그리고 `web/` 바로 아래 파일만 줍니다(`:539-543`). 표에 없는 `/index.html`, `/team_names.js`는 404입니다(시험용 앱에서 확인).
- **등록 순서**: `install_*` 다섯 개(`:531-535`)가 catch-all(`:537`)보다 먼저 등록됩니다. 학습 라벨 POST 12개는 catch-all 뒤에 등록되지만 catch-all이 GET만 받으므로 영향이 없습니다. 없는 주소로 POST하면 catch-all 때문에 404가 아니라 405가 나옵니다(시험용 앱에서 `/api/v1/upload` 405 확인).
- **서버가 켜질 때 시작하는 스레드**: 보고서 작업기 복구(`:206`), 감시 스레드와 하프타임 합계 스레드(`app/service_routes.py:157-159`), 분석가 클립 작업 스레드(`app/analyst_tags.py:142`). 라이브 영상 ffmpeg는 첫 시청자가 올 때 켭니다.
- **운영 서버 시작**: 예약 작업 `<SCHEDULED_TASK>`가 로그인 때 `scripts/start_review_server_at_logon.ps1`을 실행하고(이 작업 폴더의 파일), 30초마다 포트를 보고 꺼져 있으면 `scripts/run_review_server.ps1`로 다시 켭니다(한 시간에 5번까지). 시작 전 저장소를 백업합니다(6시간에 한 번). 2026-11-21에 확인한 운영 프로세스는 이 작업 폴더에서 `python -m app.review_public`으로 2026-11-20 밤에 시작했습니다.
- **중요**: 서버는 `web/` 파일을 요청마다 디스크에서 읽습니다. 그래서 이 작업 폴더의 `web/` 파일을 고치면 재시작 없이 바로 운영 화면이 바뀝니다. 파이썬 파일은 재시작해야 바뀝니다.

## 5. 이 저장소의 다른 서버
| 서버 | 파일 | 경로 수 | 무엇 | 누가 시작하는가 |
|---|---|---|---|---|
| 송출 상태 | `scripts/run_stream_health.py` + `app/stream_health.py:295-310` | 3 | `/stream`, `/api/stream-health`, `/` | 손으로만(`python scripts/run_stream_health.py`, 기본 127.0.0.1:8791, 8443 거부). 시작 스크립트 없음 |
| 예전 분석 서버 | `app/main.py:37` | 23 | 대시보드 API(`/api/v1/start`, `/upload`, `/sequences`, `/live-bookmarks`, `/training-labels/snapshot` 등) | `app/demo_supervisor.py:28`(포트 8000, `scripts/start_cellular_demo.ps1:13`이 실행), `scripts/run_label_review.py`, `scripts/run_training_questions.py`(정적 파일을 붙이고 `next-sample` 1개 추가, `:63`) |
| 공개 시연 관문 | `app/plaintext_demo.py:47` | 7 | 예전 분석 서버를 중계 | `app/demo_supervisor.py:30`. `scripts/start_match_day.ps1:23`은 `plaintext_demo srt`로 **송출 수신(MediaMTX)** 만 켜는데, 실행 위치는 이 작업 폴더가 아니라 `outputs/football-coach-server`입니다 |
| TLS 읽기 프록시 | `app/read_proxy.py:37` | 3 | 예전 분석 서버를 HTTPS로 중계, 토큰 | `python -m app.read_proxy`(시작 스크립트 없음) |
| 일회성 파일 받기 | `app/transfer_once.py:46` | 1 | `/upload` | 손으로만 |
| 녹화 미리보기 | `scripts/preview_recording.py:20` | 4 + 정적 파일 | 녹화 영상과 저장된 관측으로 대시보드 재생 | 손으로만 |
- 이 서버들은 모두 검토 서버와 다른 프로세스입니다. 이번 정리 계획의 대상은 검토 서버뿐입니다.

## 6. 겹치는 기능과 정리 방향
- 화면 파일 제공 방식 6가지: [overlaps.md](overlaps.md) O3. 오류 변환 반복: O9. 입력 검사: O10.
- 첫 주소 `/`가 이 서버에 없는 API를 부르는 예전 대시보드입니다: O13, B부 질문 5.
- 다른 서버들의 미들웨어는 각자 두는 것이 맞습니다(다른 프로세스).

## 7. 알려진 문제와 고정값
- 운영 주소, 바인드 주소, 토큰은 `server.json`과 토큰 파일에만 있습니다. 위키에는 적지 않습니다((주소)).
- `scripts/run_review_server.ps1`과 `scripts/start_match_day.ps1`의 주석과 안내 문자열에 실제 주소가 들어 있습니다(고정값 감사는 다른 작업의 `wiki/hardcoded-values-audit.md`).
- 기본 포트 8443은 HTTPS 관례 포트지만 이 서버는 평문 HTTP입니다(`origin`이 `http://`여야 함).
- 커밋하지 않은 서버 코드가 운영 중입니다(2026-11-21 `git status`: `app/alert_review.py`, `app/review_public.py`, `app/live_feedback.py`, `web/alerts.*` 등 수정).
