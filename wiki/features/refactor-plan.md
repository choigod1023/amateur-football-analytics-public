# 검토 서버 정리 계획 (2026-11-21 작성, 아직 실행 안 함)

근거: [routes.csv](routes.csv), [overlaps.md](overlaps.md), 기능 페이지들. 이 문서는 계획뿐입니다. 코드는 바꾸지 않았습니다.

## 전제와 지킬 것
- **작업 폴더**: 구현은 별도 작업 폴더에서 합니다. 운영 중인 폴더에서 고치면 안 됩니다. 운영 서버가 그 폴더의 `web/` 파일을 요청마다 읽으므로 여기서 화면 파일을 고치는 순간 코치와 분석가 화면이 바뀝니다([common.md](common.md) 4절).
- **운영 서버**: 운영 서버(예약 작업 `<SCHEDULED_TASK>`, 운영 폴더에서 실행 중)는 사용자님이 재시작을 승인할 때까지 지금 체크아웃을 계속 씁니다. 정리 작업은 서버를 재시작하지 않습니다. 재시작과 병합은 사용자님 승인 뒤에, 경기가 없는 날에만 합니다(`CLAUDE.md` 10줄, 19줄).
- **출발점**: 지금 이 폴더에는 커밋하지 않은 서버 코드가 있고 이미 운영 중입니다(`app/alert_review.py`, `app/review_public.py`, `app/live_feedback.py`, `web/alerts.js`, `web/alerts.css` 등, 2026-11-21 `git status`). 정리 브랜치를 그 변경이 없는 커밋에서 시작하면 정리 결과를 배포할 때 그 변경이 사라집니다. 먼저 사용자님 승인을 받아 이 변경을 커밋하고, 그 커밋에서 정리 브랜치를 만듭니다.
- **저장소**: 시험은 모두 `tmp_path`의 임시 저장소로 합니다. 운영 저장소(`work/human-labels/public-own-match-review-20261111`)는 읽지도 쓰지도 않습니다. 실제 자료 모양이 필요하면 그 저장소에서 몇 개 파일을 임시 폴더로 **복사**해서 씁니다.
- **GPU**: 이 작업은 GPU를 쓰지 않습니다.

## A부. 구조만 바꾸기 (동작 변화 없음, 사용자님께 묻지 않고 할 수 있음)
목표 모양:
```
app/routes/__init__.py        create_app가 부르는 install 순서표
app/routes/common.py          화면 파일 등록, 파일 응답(file_or_404), ValueError→HTTP 도우미
app/routes/security.py        Host·Origin 미들웨어, 보고서 토큰 검사
app/routes/static_pages.py    화면 등록표(별칭 38개), /, catch-all(항상 마지막)
app/routes/<기능>.py          기능별 경로(아래 단계)
app/alert_store.py            알림 파일 읽기, 세션 찾기, "가장 최근 라이브 세션" 규칙
app/store_io.py               JSON 저장(임시 파일 후 바꾸기), 라벨 폴더 읽기
web/common.js                 el, postJson, getJson, 분:초 글자, 글자 노드
```
`app/review_public.py`에는 설정 읽기와 `create_app`(저장소 객체 만들기, install 순서대로 부르기), `main`만 남깁니다. 기존 모듈(`app/service_routes.py`, `app/team_select_routes.py`, `app/shot_routes.py`, `app/analyst_tags.py`, `app/live_video_routes.py`)은 파일 이름을 그대로 두고 안쪽 도우미만 공통 모듈로 바꿉니다(시험과 다른 스크립트가 이 이름으로 가져다 쓰기 때문).

### 단계표
각 단계는 커밋 하나입니다. 모든 단계의 공통 확인: 0단계의 특성 시험 + 전체 `pytest`가 그대로 통과. 되돌리기: 그 커밋을 `git revert`. 서버를 재시작하지 않으므로 운영에는 영향이 없습니다.

| 단계 | 하는 일 | 건드리는 파일 | 무엇이 어디로 | 그대로임을 보이는 시험 | 되돌리기 |
|---|---|---|---|---|---|
| 0 | **임시 저장소 사본으로 모든 경로의 특성 시험을 먼저 씀** | 새 `tests/test_route_characterisation.py`, 새 `tests/fixtures/route_store.py`(작은 가짜 저장소 만들기), 새 `tests/fixtures/route_snapshot.json` | 없음(시험만) | 아래 "0단계 내용" | 파일 삭제 |
| 1 | 공통 도우미 추가(아직 아무도 안 씀) | 새 `app/routes/__init__.py`, `app/routes/common.py`, `tests/test_routes_common.py` | 없음 | 새 단위 시험 + 0단계 | revert |
| 2 | 접속 확인 옮기기 | `app/review_public.py:192-194`, `:227-237`, `:404-406` → `app/routes/security.py` | 미들웨어 `restrict`, `require_token` | 0단계(헤더 포함), `test_review_public.py::test_service_rejects_wrong_host_and_only_serves_expected_files`, `test_report_jobs.py::test_service_routes_need_the_token_for_every_change` | revert |
| 3 | 정적 화면 옮기기 | `app/review_public.py:211-225`, `:239-241`, `:537-543` → `app/routes/static_pages.py` | 별칭 표, `/`, catch-all. catch-all은 `install_catch_all`로 따로 두고 `create_app`의 맨 마지막에 부름 | 0단계(경로 순서 검사 포함), `test_review_dashboard.py` | revert |
| 4 | 이벤트 경로 | `:265-281`, `:514-520` → `app/routes/events.py` | 3개 API와 `/event-media` | `test_review_public.py::test_event_review_lists_labels_and_serves_media` + 0단계 | revert |
| 5 | 공 경로 | `:482-512` → `app/routes/ball.py` | 4개 API와 `/ball-media` | `test_ball_verify.py`, `test_review_public.py::test_ball_review_lists_clips_and_saves_only_valid_positions` | revert |
| 6 | 선수·카드·비교 장면 | `:283-376` → `app/routes/players.py`, `cards.py`, `differences.py` | 선수 7개, 카드 2개, 선수 파일, 비교 4개 | `test_player_identity.py`, `test_player_chain.py`, `test_player_cards_page.py`, `test_difference_review.py` | revert |
| 7 | 보고서 작업 | `:400-480` → `app/routes/report_jobs_routes.py`(토큰 검사는 2단계 모듈 사용) | 6개 API와 `/report-files` | `test_report_jobs.py`, `test_report_upload.py` | revert |
| 8 | 학습 장면 라벨과 보정 | `:522-529`, `:545-623`, 모델 클래스 `:36-141` → `app/routes/training.py`(학습 라벨 10개 + `/thumbs`)와 같은 파일 안 `install_calibration`(보정 2개) | 13개 경로와 입력 모델 | `test_review_public.py` 전체, `test_training_labels.py` | revert |
| 9 | 알림 판정 | `:378-398` → `app/routes/alerts.py` | 2개 API와 `/alert-files` | `test_alert_review.py` | revert |
| 10 | 벤치 경로 모으기 | `app/review_public.py:389-391`과 `app/service_routes.py:128-155` → `app/routes/bench.py`. `HalftimeService` 객체는 인자로 받음. 감시·하프타임 스레드 시작은 `service_routes.install`에 그대로 둠 | `/api/v1/bench`, `/bench/minimap`, `/bench/feedback` 2개 | `test_bench_view.py`, `test_coach_feedback.py`, `test_halftime_report.py`, 스레드가 한 번만 시작되는지 새 시험 | revert |
| 11 | 라이브 스냅샷 | `:243-263` → `app/routes/live_snapshot.py` | 3개 | `test_live_snapshot.py`, `test_review_dashboard.py` | revert |
| 12 | 화면 파일 도우미 하나로 | `app/service_routes.py:52-60`, `app/team_select_routes.py:57-65`, `app/shot_routes.py:41-51`, `app/analyst_tags.py:83-93`, `app/live_video_routes.py:129-145` → `common.serve_page` | 18개 등록. media type은 지금 값 그대로(슛·태그·라이브 자원은 `application/javascript`, `text/css`) | 0단계의 content type 비교 | revert |
| 13 | 파일 응답 도우미 | 파일 경로 11개의 몸통 → `common.file_or_404(path, media_type, cache)` | media type과 캐시 헤더를 [media-files.md](media-files.md) 표대로 | 0단계 헤더 비교, `test_difference_review.py::test_page_api_same_origin_and_range_media`(Range) | revert |
| 14 | 오류 변환 도우미 | `ValueError → 409` 22곳 | 404·422로 바꾸는 곳은 그대로 | 0단계의 오류 사례 비교 | revert |
| 15 | 알림 파일 읽기 하나로 | `app/alert_review.py:15-48`, `app/bench_view.py:21`, `:77-99`, `:115`, `app/service_watch.py:136-145` → `app/alert_store.py`. "가장 최근 라이브 세션" 함수 하나(규칙은 지금과 같게: `label-`도 포함) | 읽기, 세션 찾기, 정규식 | `test_alert_review.py`, `test_bench_view.py`, `test_service_watch.py`, `test_halftime_report.py`, `test_coach_feedback.py` | revert |
| 16 | JSON 저장·라벨 폴더 읽기 하나로(우선순위 낮음) | [overlaps.md](overlaps.md) O7, O8의 곳들. 한 번만 쓰기(`difference_review`, `training_labels`의 `only_if_new`)는 건드리지 않음 | `app/store_io.py` | 각 모듈 시험 + 저장 뒤 `.tmp` 파일이 남지 않는다는 새 시험 | revert |
| 17 | 분석가 화면 스크립트 도우미 | 새 `web/common.js`, 별칭 표에 `/common.js` 1개 추가. `alerts.js`, `events.js`, `ball.js`, `ball-verify.js`, `cards.js`, `players.js`, `differences.js`, `report.js`, `shots.js`가 사용 | 도우미만 | 새 node 시험(`tests/test_web_common.cjs`), 임시 서버(다른 포트, 임시 저장소)로 화면마다 열어 콘솔 오류 없음 확인, 0단계(새 별칭 1개만 늘어난 것을 확인하고 스냅샷 갱신) | revert |
| 18 | 경기 화면 스크립트 도우미(마지막, 경기 없는 날만) | `bench.js`, `bench-extra.js`, `watch-banner.js`, `live-video-view.js`, `team_select.js`, `tag.js`, `training-label.js`(예전 대시보드와 공유) | 도우미만. `bench.js`와 `bench-extra.js`의 `/api/v1/bench` 요청을 하나로 나누어 쓰기 | 17단계와 같음 + 벤치 화면 리허설(합성 알림 파일로 큰 알림, 이전 알림, 띠, 지도, 의견 단추 확인) | revert |

### 0단계 내용 (먼저 쓰는 특성 시험)
1. `tests/fixtures/route_store.py`가 `tmp_path`에 작은 가짜 저장소를 만듭니다: 알림 세션 2개(코칭 세션 하나, `label-` 세션 하나, 사진과 mp4 하나씩, 판정 파일), 공 클립 1개, 이벤트 후보와 미디어, 비교 장면 큐와 미디어, 선수 구간 1개와 명단, 카드 요약과 PNG, 슛 후보와 클립과 표시, 분석가 태그 2줄, 팀 후보와 사진, pending 장면 1개, 보고서 작업 1개.
2. 시험이 `create_app(tmp, 'http://review.test')`로 앱을 만들고 다음을 기록해 `route_snapshot.json`과 비교합니다(처음 실행 때 만들고 커밋).
   - 경로 표: `(path, methods)` 100개와 순서. catch-all이 모든 GET 경로보다 뒤인지.
   - 별칭 38개: 상태 코드, content type, 파일 바이트가 `web/`의 파일과 같은지.
   - 모든 GET 경로와 모든 POST 경로(정상 본문 하나, 잘못된 본문 하나): 상태 코드, content type, JSON이면 최상위 키 목록과 목록 첫 항목의 키 목록.
   - 헤더: `Cache-Control`, `Content-Security-Policy`, `X-Content-Type-Options`.
   - 접속 확인: 모든 POST 경로가 Origin 없이 403, 모든 경로가 다른 Host로 403.
   - 보고서 변경 5개 경로가 토큰 없이 403.
   - `/live-video.mjpg`는 `LIVE_VIDEO_FFMPEG`를 없는 파일로 두고 503만 기록(ffmpeg를 실제로 켜지 않음).
3. 화면 스크립트의 호출 목록 시험: `web/*.js`와 `web/*.html`에서 `/api/`로 시작하는 글자와 미디어 경로 앞부분을 모아, 경로 표에 있거나 "다른 서버용" 목록(예전 대시보드가 부르는 9개, [common.md](common.md) 2절 표)에 있는지 확인합니다.
4. 이 시험은 `create_app`이 감시·하프타임·클립 스레드를 시작하므로 데몬 스레드가 남는 것을 허용합니다(지금 다른 시험과 같음).
5. 이 시험을 쓴 뒤 지금 코드에서 통과하는지 먼저 확인하고 커밋합니다. 그다음 단계부터 스냅샷은 바꾸지 않습니다(17단계의 별칭 추가만 예외, 커밋 메시지에 적음).

### 배포 (A부가 끝난 뒤, 사용자님 승인 필요)
1. 정리 브랜치에서 전체 `pytest`와 0단계 시험 통과, 임시 서버(다른 포트, 임시 저장소 사본)로 모든 화면을 열어 확인.
2. 사용자님께 병합과 재시작 승인을 받습니다. 경기 날과 경기 전날 밤은 피합니다.
3. 운영 폴더를 정리 브랜치의 커밋으로 바꾸고 `scripts/run_review_server.ps1 -ConfigFile <server.json>`으로 다시 켭니다(저장소 백업 포함). 예약 작업의 감시 스크립트는 포트가 비면 스스로 다시 켜므로, 서버를 멈춘 채 두지 않습니다.
4. 휴대폰에서 `/bench`, `/tag`, `/team-select`, `/live`, `/alerts`를 열어 봅니다.
5. 되돌리기: 운영 폴더를 이전 커밋으로 되돌리고 같은 스크립트로 다시 켭니다(이것도 재시작이므로 승인 필요).

## B부. 사용자님이 정할 것
동작이나 화면이 바뀌는 항목입니다. 이득이 큰 순서입니다. 각 항목의 추천은 제 의견이고 정하지 않았습니다.

| 순위 | 번호 | 질문 | 선택지 | 코치·분석가가 보게 될 변화 | 추천 |
|---|---|---|---|---|---|
| 1 | B2 | `label-` 판정 묶음을 벤치·감시·하프타임의 "라이브 실행"에서 뺄까요? | ① 이름이 `label-`로 시작하는 세션 제외 ② 세션 폴더에 "판정용" 표시 파일을 두고 제외 ③ 그대로 | ①② 라이브 실행이 아직 알림을 안 쓴 동안 벤치가 "실시간 알림 파일이 없습니다"로 보임. 지금은 `label-1121-team`의 질문이 알림처럼 보임(2026-11-21 확인) | ①을 바로, ②는 나중에 |
| 2 | B1 | `label-` 묶음을 `/alerts`에서 계속 받을까요? | ① `/alerts` 유지, 서버가 `label-` 미판정 항목을 먼저 세우고 300개 제한에서 빼며, 위쪽 비율에서도 뺌 ② 새 화면 `/labels`(예·아니오·모름 단추, 저장은 같은 형식) ③ 그대로 | ① 화면은 거의 같고, 새 라이브 실행이 알림 169개를 넘겨도 묶음이 잘리지 않음 ② 판정할 곳이 둘로 나뉨 | ① |
| 3 | B2-추가 | 보관한 세션의 판정도 벤치의 "판정 n개 중 m개 맞음"에 셀까요? | ① 보관 폴더의 알림 파일도 읽어 셈 ② 그대로 | ① 벤치 정확도 문구가 보관 전 값으로 돌아감(박스 침투 등 표본이 다시 커짐) | ① (사람 판정이 정답이므로) |
| 4 | B4 | 벤치의 상태 표시 기준을 하나로 할까요? | ① 위쪽 띠도 감시 판정을 따름 ② 둘 다 같은 초(예: 10초)로 ③ 그대로 | 위쪽 띠와 빨간 띠가 같은 순간에 바뀜 | 리허설로 초를 정한 뒤 ① |
| 5 | B5 | 첫 주소 `/`를 목차 화면으로 바꿀까요? | ① 목차(각 화면 링크, 남은 판정 수) ② 예전 대시보드를 `/dashboard`로 옮기고 목차 ③ 그대로 | 휴대폰에서 주소만 열면 할 일이 보임. 예전 대시보드는 사라지거나 옮겨짐(`test_review_dashboard.py` 수정 필요) | ② |
| 6 | B3 | 같은 질문을 받는 판정 화면을 합칠까요? (놓친 선수: `/train` 손 상자와 `label-...-missed`, 팀: `/train`과 `label-...-team`, 골·슛: `/events`, `/tag`, `/shots`) | ① 판정 틀 하나(예·아니오·모름 + 메모)와 저장 형식을 맞추고 화면은 유지 ② 화면까지 합침 ③ 그대로 | ① 화면은 그대로, 학습 스크립트가 읽는 형식이 바뀔 수 있음 ② 분석가가 쓰는 화면이 바뀜 | ③ 지금은 그대로, 다음 손 라벨 묶음 때 ① 검토 |
| 7 | B6 | 송출 상태 화면을 검토 서버(`/stream`)에 붙일까요? | ① 페이지 안 스크립트를 파일로 빼서 붙임(읽기 전용, 3초마다 ffprobe) ② 별도 서버 유지 | ① 휴대폰에서 같은 주소로 송출 상태를 봄. 서버 부하가 조금 늘어남 | ① (경기 없는 날, 리허설 뒤) |
| 8 | B7 | 쓰이지 않는 경로를 지울까요? | `/review-differences`(부르는 곳 없음), `/api/v1/shots/clear`(단추 없음), `/api/v1/reappearance/decisions`(스크립트는 함수를 직접 씀), B5를 하면 예전 대시보드 별칭 11개 | 보이는 변화 없음 | `/review-differences`만 지우고 나머지는 둠 |
| 9 | B8 | 작은 것들 | ① 슛·태그 경로에 객체가 아닌 JSON을 보내면 500 대신 400 ② 연구 중단인 `/players`를 보고서 화면 메뉴에서 숨김 | ① 없음 ② 메뉴 링크 하나가 사라짐 | ① 예, ② 그대로 |

## 위험
- **경기 중에 쓰는 것**: `/bench`, `/team-select`, `/live`, `/live-video.mjpg`, `/watch`, `/halftime`, `/tag`, 그리고 이들이 부르는 `/api/v1/bench*`, `/api/v1/service*`, `/api/v1/halftime*`, `/api/v1/team-select*`, `/api/v1/analyst-tags*`. 송출 상태 서버(`/stream`)도 경기 중 도구입니다. 이들을 바꾸는 단계(10, 12, 15, 18)는 경기 없는 날에 하고, 배포 전에 합성 알림 파일로 리허설합니다.
- **경기 날 규칙**: 경기 날에는 송출, 녹화, 실시간 분석, 운영 서버 코드를 바꾸지 않습니다(`CLAUDE.md` 19줄). 배포(재시작)는 경기 날과 경기 2시간 전부터 끝까지 하지 않습니다.
- **화면 파일 즉시 반영**: 운영 서버가 운영 폴더의 `web/`을 바로 읽습니다. 정리 작업을 운영 폴더에서 하면 안 됩니다(별도 작업 폴더).
- **catch-all 순서**: catch-all이 다른 GET 경로보다 먼저 등록되면 `/watch`, `/shots`, `/tag`, `/team-select`, `/live` 등이 404가 됩니다. 0단계 경로 순서 검사로 막습니다.
- **스레드 두 번 시작**: 감시, 하프타임 합계, 분석가 클립, 보고서 작업기 스레드가 `install` 안에서 시작됩니다. 경로를 옮기다 `install`을 두 번 부르면 같은 일을 두 스레드가 하고 멈춤 기록(`service/outages.jsonl`)이 두 번 쓰일 수 있습니다.
- **Host와 Origin 확인**: 미들웨어를 옮기다 실수하면 휴대폰에서 모든 화면이 403이 되거나, 반대로 다른 사이트의 POST가 통과합니다. 0단계의 403 전수 검사로 막습니다.
- **CSP**: 페이지 안 스크립트는 막힙니다. 화면을 옮기거나 붙일 때(B6) 스크립트를 파일로 빼야 합니다.
- **커밋하지 않은 운영 코드**: 출발점 커밋에 지금 운영 중인 변경이 들어 있어야 합니다(위 "전제").
- **예약 작업의 자동 재시작**: 포트가 비면 30초 안에 지금 폴더의 코드로 다시 켭니다. 배포 중 서버를 멈춘 채 다른 일을 하면 의도하지 않은 코드로 켜질 수 있습니다.

## 가장 위험한 세 곳
1. **정적 화면과 catch-all 옮기기(3, 12단계)**: 주소 38개와 등록 순서가 한꺼번에 움직이고, 실수하면 경기 화면이 열리지 않습니다.
2. **벤치 경로와 감시·하프타임 분리(10, 15단계)**: 경기 중 화면, 서버 스레드, "가장 최근 라이브 세션" 규칙이 한데 얽혀 있습니다.
3. **접속 확인 미들웨어 옮기기(2단계)**: 로그인이 없는 서버에서 유일한 보호 장치입니다.
