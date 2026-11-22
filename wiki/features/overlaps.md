# 겹치는 기능 분석 (2026-11-21)

근거: 이 폴더의 [routes.csv](routes.csv)와 아래에 적은 file:line. 코드는 이 저장소의 2026-11-21 작업 사본을 읽었습니다(커밋하지 않은 변경 포함). 운영 서버의 상태는 읽기만 했습니다.

권고는 세 가지입니다. **합치기**(경로나 화면을 하나로), **공통 부분만 빼기**(주소와 동작은 그대로 두고 같은 코드를 한 곳에 둠), **그대로 두기**. "공통 부분만 빼기"는 [refactor-plan.md](refactor-plan.md)의 A부(동작 변화 없음)에 들어가고, "합치기"와 동작이 바뀌는 것은 B부(사용자님 결정)에 들어갑니다.

## 요약표
| 번호 | 겹치는 것 | 중복 양 | 알아챌 사람 | 권고 |
|---|---|---|---|---|
| O1 | 사람 판정 화면이 9개 주소, 8개 저장 방식으로 나뉨 | 저장 모듈 8개, 판정 단어 묶음 8가지 | 분석가 | 공통 부분만 빼기 + B부 질문 |
| O2 | 파일·영상 제공 경로 11개가 거의 같은 코드 | 약 77줄 | 아무도(헤더를 지키면) | 공통 부분만 빼기 |
| O3 | 화면 파일을 내보내는 방식이 6가지 | 약 82줄 | 아무도 | 공통 부분만 빼기 |
| O4 | 벤치 화면 한 장에 입력 상태 표시가 3개, 기준이 서로 다름 | 판정 규칙 2벌, 요청 중복 | 코치 | B부 질문(합치기) |
| O5 | "가장 최근 라이브 세션" 규칙이 두 곳에 복사, `label-` 세션도 라이브로 봄 | 약 20줄 | 코치 | 공통 부분만 빼기 + B부 질문 |
| O6 | 알림 파일(jsonl) 읽기와 세션 찾기가 두 모듈에 똑같이 있음 | 약 25줄 | 아무도 | 공통 부분만 빼기 |
| O7 | JSON을 임시 파일로 쓰고 바꾸는 코드가 12곳, 3가지 방식 | 약 130줄 | 아무도 | 공통 부분만 빼기(늦게) |
| O8 | 라벨 폴더(`*.json`)를 읽고 이름을 확인하는 코드가 4곳 | 약 40줄 | 아무도 | 공통 부분만 빼기 |
| O9 | `ValueError`를 409로 바꾸는 같은 4줄이 22번 | 약 90줄 | 아무도 | 공통 부분만 빼기 |
| O10 | 입력 검사 방식이 두 가지(pydantic과 손 검사) | 슛·태그 경로 7개 | 분석가(500 오류) | 공통 부분만 빼기 + B부 |
| O11 | 화면 스크립트의 작은 도우미가 파일마다 복사 | `el` 18곳, POST 도우미 13곳, 시계 글자 6곳 | 아무도 | 공통 부분만 빼기(경기 화면은 늦게) |
| O12 | 경기장 그림을 그리는 코드가 5가지 | 화면마다 20~200줄 | 아무도 | 그대로 두기 |
| O13 | 첫 주소 `/`의 예전 대시보드와 `/bench`·`/live` | 별칭 11개, 없는 API 호출 6개 | 분석가, 코치 | B부 질문 |
| O14 | 송출 상태 화면(별도 서버)과 `/watch` | 서버 2개 | 분석가 | 그대로 두기 + B부 질문 |
| O15 | `/alerts` 정리(보관)가 벤치 정확도 문구를 바꿈 | 결합 1곳 | 코치 | B부 질문 |

## O1. 사람 판정 화면이 여러 갈래
**확인함.** 같은 사람(분석가)이 "모델 후보를 보고 맞다, 아니다를 말하는" 같은 일을 하는데, 화면마다 저장 모듈, 저장 폴더, 판정 단어가 다릅니다.

| 화면 | 저장 모듈 | 저장 위치 | 판정 단어 |
|---|---|---|---|
| `/train` | `app/training_labels.py:403` `save` | `<저장소>/<해시>.json`, 손 상자는 `pending/<토큰>.json` | 역할 7가지, 팀 8가지, 옷 색 6가지 (`app/review_public.py:135-141`) |
| `/alerts` | `app/alert_review.py:108` `set_label` | `alerts/labels/<세션>-<번호>.json` | ok, wrong, useless |
| `/alerts`의 `label-` 세션 | 같은 모듈 | 같은 폴더 | 같은 세 단어를 세션마다 다른 뜻으로 씀(예: `label-1121-missed`의 "쓸모없음 = 판단하기 어렵습니다", 저장소 `alerts/label-1121-missed/alerts.jsonl` 2번째 줄) |
| `/ball` | `app/ball_review.py:78`, `:113` | `ball/labels/<클립>.json` | ball, none, unsure, 검증 ok, rejected, moved |
| `/events` | `app/event_review.py:81` | `events/labels/<id>.json` | kickoff, goal, set_piece, shot, other, none, unsure |
| `/shots` | `app/shot_routes.py:109` | `shots/tags/<id>.json` | none, off, saved, blocked, post, goal |
| `/players` | `app/player_identity.py` | `players/assign`, `links`, `rejects` | 배정, 같음·다름, 아님 |
| `/review-differences`, `/train/reappearance` | `app/difference_review.py:77` | `differences/answers/<id>.json`(한 번만 씀) | same, different, unclear 또는 before, after, both_wrong, unclear |
| `/bench`(코치) | `app/coach_feedback.py:56` | `alerts/labels-coach/` | ok, wrong |

겹침의 실제 예:
- **놓친 선수**: `/train`에서 상자를 직접 그리는 방식(`/api/v1/training-labels/manual-box`, `app/review_public.py:607`)과 `/alerts`의 `label-1121-missed` 세션 15개("노란 원 안에 상자 없는 선수가 있습니까?")가 같은 질문을 다른 형식으로 받습니다. 두 답은 서로 다른 폴더에 남고 서로를 모릅니다.
- **팀 판정**: `/train`의 `team_group`과 `label-1121-team` 60개("옷 색 팀이 맞는지")가 같은 사실을 묻습니다.
- **골과 슛**: `/events`(골·슛 라벨), `/tag`(경기 중 "우리 골" 버튼, `app/analyst_tags.py:25`), `/shots`(슛 결과와 위치)가 같은 사건을 세 곳에 기록합니다. 다만 시점이 다릅니다(경기 중과 경기 후).
- **같은 파일 두 주소**: `/review-differences`와 `/train/reappearance`는 둘 다 `differences.html`입니다(`app/review_public.py:217`). 차이는 `web/differences.js:5`가 주소를 보고 범위 `occlusion-reappearance`를 붙이는 것뿐입니다. `/review-differences`는 어느 화면도 부르지 않습니다.
- **판정 집계가 섞임**: `/alerts` 위쪽의 "도움이 된 비율"(`web/alerts.js:28-31`)은 코칭 알림과 `label-` 세션의 판정을 모두 더합니다. 질문이 다른 판정이 한 비율에 들어갑니다.

중복 양: 저장 모듈 8개, 판정 단어 묶음 8가지. 합치면 알아챌 사람은 분석가입니다(화면 모양과 버튼이 바뀜).
권고: **공통 부분만 빼기**(저장 형식과 "예·아니오·모름" 같은 판정 틀). 화면을 합칠지는 B부 질문 1, 3입니다. 이유: 각 판정이 학습과 평가에서 이미 다른 형식으로 읽히고 있어서(예: `scripts/evaluate_own_role_split.py`, `scripts/evaluate_labeled_srt.py`가 학습 라벨의 `bbox_image_norm` 칸을 읽음) 저장 형식을 바꾸면 그 스크립트도 바뀝니다.

## O2. 파일·영상 제공 경로 11개
**확인함.** 모두 "이름을 정규식으로 검사, 경로 만들기, 파일 있으면 FileResponse, 없으면 404"입니다.

| 경로 | 정의 | 줄 수 | 다른 점 |
|---|---|---|---|
| `/card-files/{name}` | `app/review_public.py:339-344` | 6 | png |
| `/player-files/{half}/{name}` | `:346-351` | 6 | jpg/mp4 |
| `/difference-files/{name}` | `:371-376` | 6 | mp4/jpg/png, 목록에 있는 이름만 |
| `/alert-files/{session}/{name}` | `:393-398` | 6 | jpg/mp4 |
| `/report-files/{job}/{name}` | `:471-480` | 10 | mp4/md/json, 정해진 이름만 |
| `/ball-media/{clip}/{name}` | `:507-512` | 6 | jpg, `Cache-Control: private, max-age=3600` |
| `/event-media/{name}` | `:514-520` | 7 | mp4/jpg, 1시간 캐시 |
| `/thumbs/{name}` | `:522-529` | 8 | jpg, 1시간 캐시, 없으면 만들어 저장 |
| `/shots-clip/{name}` | `app/shot_routes.py:88-95` | 8 | mp4 |
| `/analyst-clip/{tag_id}.mp4` | `app/analyst_tags.py:206-213` | 8 | mp4 |
| `/team-select-files/{name}` | `app/team_select_routes.py:77-82` | 6 | jpg |

이름 검사는 저장 모듈에도 따로 있습니다: `app/alert_review.py:127-132`, `app/ball_review.py:147-151`, `app/event_review.py:120-124`, `app/difference_review.py:103-110`, `app/player_identity.py:270-274`, `app/report_jobs.py:202-207`.
알아챌 사람: 없습니다. 단, 캐시 헤더(3개 경로만 1시간, 나머지는 미들웨어의 `no-store`, `app/review_public.py:234`)와 media type을 그대로 지켜야 합니다.
권고: **공통 부분만 빼기**. 주소는 그대로 두고 `file_or_404(path, media_type, cache)` 같은 도우미 하나로 줄입니다. 경로를 하나(`/files/<종류>/...`)로 **합치는 것은 권하지 않습니다**. 화면 스크립트와 저장된 JSON 안의 주소(예: `app/alert_review.py:80-81`, `app/difference_review.py:66`)를 모두 바꿔야 해서 이득보다 위험이 큽니다.

## O3. 화면 파일(HTML, JS, CSS)을 내보내는 방식 6가지
**확인함.**
1. 별칭 표 + 마지막 catch-all: `app/review_public.py:211-225`(별칭 38개), `:537-543`.
2. `/` 전용: `:239-241`.
3. `app/service_routes.py:19`, `:52-60`(7개, 반복문으로 등록).
4. `app/team_select_routes.py:17`, `:57-65`(3개, 3과 글자까지 같은 함수).
5. `app/shot_routes.py:41-51`, `app/analyst_tags.py:83-93`(각 3개, media type을 직접 지정, analyst_tags는 `no-store` 헤더를 다시 붙임).
6. `app/live_video_routes.py:129-145`(`/live` 하나와 자원 2개).

합계 약 82줄. 겉으로 보이는 차이는 거의 없습니다(미들웨어가 `no-store`를 기본으로 붙이므로 analyst_tags의 헤더는 같은 값입니다). JS의 content type은 1번은 `text/javascript`(확인: 시험용 앱에서 `/app.js`), 5와 6은 `application/javascript`로 다릅니다.
알아챌 사람: 없습니다.
권고: **공통 부분만 빼기**(화면 등록표 하나). 주의: catch-all(`/{name:path}`)은 반드시 모든 GET 경로보다 뒤에 등록되어야 합니다. 지금은 `install_*` 다섯 개가 `:531-535`에서 먼저 등록되고 catch-all이 `:537`에 옵니다. 순서가 바뀌면 `/watch`, `/shots` 같은 주소가 404가 됩니다.

## O4. 실시간 상태 표시가 여러 기준으로 겹침
**확인함.** `/bench` 한 화면에 상태 표시가 셋 있습니다.

| 표시 | 근거 자료 | 기준 | 정의 |
|---|---|---|---|
| 위쪽 띠 "입력 정상/입력 없음/모름" | `/api/v1/bench`의 `state` | 하트비트 10초 없으면 입력 없음 | `app/bench_view.py:27`, `:49-67`; 화면 연결 끊김 5초 `web/bench.js:5` |
| 빨간 띠와 소리 | `/api/v1/service` | 파일 변화 25초 없으면 멈춤, 3시간이면 감시 안 함 | `app/service_watch.py:29-30`, `:147-169`; 서버 무응답 6초 `web/watch-banner.js:6` |
| 영상 칸 "실시간 영상/영상 없음" | `/live-video.mjpg` | 그림 요청 실패 | `web/live-video-view.js:15-16`, 서버 5초 정지 `app/live_video_routes.py:24` |

그 밖의 상태 표시: `/watch`(빨간 띠와 같은 자료), `/api/v1/status`(예전 대시보드 전용, `app/review_public.py:243`), 송출 상태 서버 `/stream`(녹화 파일 기준, `app/stream_health.py`).
- 같은 순간에 위쪽 띠는 10초 뒤 "입력 없음", 빨간 띠는 25초 뒤에 뜹니다. 그 15초 동안 두 표시가 다릅니다(코드로 확인, 화면으로는 확인하지 못함).
- `web/bench.js:73`과 `web/bench-extra.js:121`이 각각 1초마다 `/api/v1/bench`를 부릅니다. 화면 하나가 같은 요청을 초당 2번 보냅니다. 거기에 `/api/v1/service`, `/api/v1/halftime`(2초마다, `web/watch-banner.js:156`), `/api/v1/bench/minimap`(1초), `/api/v1/bench/feedback`(2.5초)이 더해집니다.

알아챌 사람: 코치(벤치), 분석가(감시).
권고: 요청 하나로 줄이는 것은 **공통 부분만 빼기**지만 경기 화면 스크립트를 바꾸는 일이라 A부의 마지막 단계에 둡니다. 판정 기준을 하나로 **합치기**는 B부 질문 4입니다.

## O5. "가장 최근 라이브 세션" 규칙이 두 곳에 복사됨
**확인함.** `app/bench_view.py:137-145`(`snapshot`)와 `app/service_watch.py:136-145`(`_newest_live`)가 같은 규칙입니다: `alerts.jsonl`이 가장 최근에 바뀐 세션 중 `kind`가 `person_check`가 아닌 줄이 있는 세션. 하프타임(`app/halftime_report.py:271-273`)은 service_watch의 함수를 씁니다.
- 이 규칙은 `label-` 세션을 걸러내지 않습니다. 2026-11-21에 저장소를 읽기만 해서 확인한 결과 `/api/v1/bench`는 지금 `label-1121-team` 세션을 라이브 실행으로 고르고, 그 세션의 `team_ours` 항목을 "현재 알림"으로 냅니다. 입력 상태는 "모름"입니다. 새 라이브 실행이 알림 파일을 쓰기 시작하면 그 세션이 더 최근이 되므로 경기 중에는 바뀝니다. 경기 직전, 라이브 실행이 아직 아무것도 쓰지 않았을 때 코치가 벤치를 열면 사람 판정용 질문이 알림처럼 보입니다.
- `tests/test_service_watch.py::test_the_rating_sessions_are_not_watched`와 `tests/test_bench_view.py::test_review_sessions_and_status_rows_do_not_count_as_live_alerts`는 `person_check`만 시험합니다.

중복 양: 약 20줄. 알아챌 사람: 코치.
권고: 규칙을 한 함수로 **공통 부분만 빼기**(A부). `label-` 세션을 제외할지는 동작이 바뀌므로 B부 질문 2입니다.

## O6. 알림 파일 읽기와 세션 찾기 중복
**확인함.** `app/alert_review.py:32-48`(`_read`)과 `app/bench_view.py:77-93`(`_read`)은 줄 단위로 같습니다(16줄). `app/alert_review.py:26-30`(`_sessions`)과 `app/bench_view.py:95-99`(`_sessions`)도 같습니다. 세션 이름 정규식이 `app/alert_review.py:15`와 `app/bench_view.py:21`에, 알림 번호 정규식이 `app/alert_review.py:16`과 `app/bench_view.py:115`에 따로 있습니다. `app/service_watch.py`, `app/coach_feedback.py`는 `BenchView._read`를 가져다 씁니다(좋은 예).
권고: **공통 부분만 빼기**(`app/alert_store.py` 같은 작은 모듈).

## O7. JSON 저장(임시 파일 후 바꾸기) 12곳
**확인함.** 같은 일을 세 가지 방식으로 합니다.
- `tempfile.NamedTemporaryFile`: `app/ball_review.py:100-110`, `:135-144`(같은 파일에 두 번), `app/event_review.py:67-79`, `app/training_labels.py:221-232`, `:314-325`, `:358-367`, `:390-398`.
- `tempfile.mkstemp`: `app/shot_routes.py:71-81`, `app/team_color_profile.py:132-142`.
- 고정된 `.tmp` 이름: `app/alert_review.py:120-124`, `app/player_identity.py:34-38`, `app/report_jobs.py:59-63`, `app/coach_feedback.py:68-72`, `app/halftime_report.py:234-239`, `app/training_labels.py:133-138`, `:437-439`.
- 한 번만 쓰기(`open('x')`): `app/difference_review.py:96-100`, `app/training_labels.py:430-436`. 이것은 뜻이 다르므로 합치지 않습니다.
합계 약 130줄. 권고: **공통 부분만 빼기**, 단 우선순위는 낮습니다. 저장 방식이 다르면 동시에 두 요청이 올 때의 동작이 조금 다르므로(고정 이름은 같은 프로세스의 잠금에 기댐) 바꾼 뒤 각 모듈 시험을 모두 돌려야 합니다.

## O8. 라벨 폴더 읽기 4곳
**확인함.** `app/alert_review.py:50-60`, `app/event_review.py:40-50`, `app/bench_view.py:107-117`, `app/shot_routes.py:60-69`이 모두 "폴더의 `*.json`을 읽고, 깨진 파일은 건너뛰고, (대부분) 파일 이름과 `id`가 같은지 확인"합니다. `app/bench_view.py`의 것은 `/alerts`의 판정 파일을 다시 읽는 것이라 판정 파일 형식이 바뀌면 두 곳을 같이 고쳐야 합니다.
권고: **공통 부분만 빼기**.

## O9. 오류 변환 반복
**확인함.** `except ValueError as exc: raise HTTPException(409, str(exc)) from exc`가 `app/review_public.py`에 19번, `app/service_routes.py`에 3번 있습니다. 일부는 404나 422로 바꿉니다(`app/review_public.py:421-422`, `:444-445`).
권고: **공통 부분만 빼기**(작은 도우미). 상태 코드가 다른 곳은 그대로 둡니다.

## O10. 입력 검사 방식 두 가지, 인증
**확인함.**
- 검토 서버 안의 인증과 헤더 확인은 한 곳뿐입니다: 미들웨어 `restrict`(`app/review_public.py:227-237`: Host가 설정한 주소와 같아야 함, POST는 Origin도 같아야 함, CSP와 `nosniff` 헤더)와 보고서 토큰 `require_token`(`:404-406`, 보고서 변경 5개 경로). 중복은 없습니다.
- 다른 서버들은 각자 미들웨어를 가집니다: `app/plaintext_demo.py:65`, `app/read_proxy.py:48`, `app/transfer_once.py:48`. 서로 다른 프로세스이므로 **그대로 두기**.
- 입력 검사: `app/review_public.py`, `app/service_routes.py`, `app/team_select_routes.py`는 pydantic 모델을 씁니다. `app/shot_routes.py`(3개)와 `app/analyst_tags.py`(4개)는 `await request.json()`을 받아 손으로 검사합니다. 시험용 앱에서 본문을 JSON 배열(`[1]`)로 보내자 `/api/v1/shots/tag`, `/api/v1/shots/clear`, `/api/v1/analyst-tags` 모두 `AttributeError`가 났습니다(운영에서는 500 응답). 정상 화면에서는 일어나지 않습니다.
권고: 검사 도우미는 **공통 부분만 빼기**. 500을 400으로 바꾸는 것은 응답이 달라지므로 B부의 작은 항목입니다.

## O11. 화면 스크립트 도우미 복사
**확인함.**
- `const el = id => document.getElementById(id)`: 18개 파일(`alerts.js:2`, `ball.js:3`, `ball-verify.js:3`, `bench.js:3`, `cards.js:2`, `events.js:3`, `halftime.js:3`, `live-bookmarks.js:3`, `manual-confirmation.js:3`, `minimap.js:4`, `players.js:2`, `report.js:2`, `review-annotation.js:3`, `sequences.js:3`, `shots.js:3`, `training-label.js:3`, `watch.js:3`, `api-auth.js:4`).
- JSON POST 도우미: 13개(`alerts.js:20-24`, `players.js:20`, `report.js:20-28`(토큰 포함), `ball.js:4`, `ball-verify.js:5`, `events.js:6`, `minimap.js:8`, `review-annotation.js:112`, `training-label.js:483`, `shots.js:10`, `team_select.js:5`, `watch-banner.js:40`, `tag.js:14`). 실패 처리가 서로 다릅니다(오류를 던짐, 응답을 그대로 돌려줌, JSON을 바로 풂).
- 분:초 글자: `alerts.js:18`, `players.js:9`, `report.js:17`, `events.js:7`, `training-label.js:290`, `tag.js:8`. 벤치는 "n초 전" 형식으로 다릅니다(`bench.js:8-11`, `watch-banner.js:41`).
- 글자 노드 만들기: `alerts.js:17`, `report.js:8`, `watch-banner.js:38`, `bench-extra.js:4`, `differences.js:11`(인자 순서가 서로 다름).
- 토큰: 보고서 화면만 입력 칸의 토큰을 `X-Report-Token`으로 보냅니다(`report.js:22`, `:159`). `api-auth.js`의 Bearer 토큰은 보안 프록시(`app/read_proxy.py`)용이며 검토 서버에서는 쓸 곳이 없습니다.
권고: **공통 부분만 빼기**(`web/common.js`). 경기 중에 쓰는 화면(`bench*.js`, `watch-banner.js`, `live-video-view.js`, `team_select.js`, `tag.js`)은 마지막에 하고, 경기 없는 날에만 합니다.

## O12. 경기장 그림 5가지
`web/bench-extra.js:35-62`(SVG), `web/halftime.js:13-31`(SVG), `web/shots.js:15`(SVG, 클릭으로 슛 위치), `web/minimap.js`(캔버스, 보정 계산 포함), `web/app.js:87`(예전 대시보드). 크기, 방향 규칙, 입력 방식이 모두 다릅니다. 권고: **그대로 두기**. 공통으로 뺄 것은 선 그리기 몇 줄뿐이라 이득이 작습니다.

## O13. 첫 주소 `/`의 예전 대시보드
**확인함.** `/`는 `web/index.html`("Touchline" 라이브 대시보드)을 돌려줍니다(`app/review_public.py:239-241`). 이 화면은 별칭 11개(`:222-225`)를 불러오고, 시험용 앱에서 확인한 결과 다음 호출이 이 서버에 없습니다: `/api/v1/proxy-capabilities`(404), `/api/v1/live-bookmarks`(404), `/api/v1/sequences`(404), `/api/v1/manual-snapshot`(404), `/api/v1/upload`(405), `/api/v1/live`(405). `/api/v1/status`는 스냅샷 폴더가 설정되지 않으면 항상 "라이브 분석 서버가 연결되지 않았습니다"입니다. 실제 라이브 화면 역할은 `/bench`와 `/live`가 합니다. 모든 화면을 모아 보여 주는 목차 화면은 없습니다(`/tag`, `/shots`, `/team-select`는 어느 화면에서도 링크되지 않음).
권고: B부 질문 5.

## O14. 송출 상태 화면과 감시 화면
송출 상태(`/stream`, `/api/stream-health`)는 검토 서버가 아니라 `scripts/run_stream_health.py`의 별도 서버(기본 127.0.0.1:8791)입니다. 시작 스크립트가 없어 손으로 실행할 때만 뜹니다. `/watch`는 알림 파일을 보고, `/stream`은 녹화 파일을 봅니다. 자료가 달라 같은 일이 아닙니다.
`web/stream_health.html`은 스크립트를 페이지 안에 직접 씁니다. 검토 서버의 CSP(`script-src`가 `'self'`만 허용, `app/review_public.py:236`)에서는 이 스크립트가 막히므로 그대로 붙이면 화면이 멈춘 채로 보입니다(코드로 판단, 브라우저로 확인하지 않음).
권고: **그대로 두기**. 검토 서버에 붙일지는 B부 질문 6.

## O15. `/alerts` 정리가 벤치 정확도를 바꿈
**확인함.** `/alerts`는 최대 300개만 보여 주므로(`app/alert_review.py:18`, `:84`) 2026-11-21에 세션 5개를 `alerts/_archive-20261121/`로 옮겼습니다(`wiki/review-store-and-open-tasks.md` 7줄). 그런데 벤치의 "판정 n개 중 m개 맞음"(`app/bench_view.py:105-131`)은 판정 파일마다 `alerts/<세션>/alerts.jsonl`을 다시 읽어 종류를 알아내므로, 옮긴 세션의 판정(gk2-h2 47개, re-1120-h1 16개, re-1120-h2 21개, `alerts/labels` 파일 이름으로 셈)은 더 이상 세지 않습니다. 2026-11-21 저장소를 읽어 계산한 지금 값은 박스 침투 "판정 3개 중 3개 맞음" 등 모든 종류가 "표본 적음"입니다.
또 300개 제한은 서버가 세션을 최근 순으로 늘어놓은 **뒤에** 자르고(`app/alert_review.py:84`), `label-` 세션을 맨 위로 올리는 것은 화면(`web/alerts.js:114-115`)이 **받은 뒤에** 합니다. 지금은 `label-` 세션이 가장 최근이라 모두 보이지만(282개 중 132개), 새 라이브 실행이 알림 169개 이상을 쓰면 `label-1121-missed`부터 잘려 화면에 오지 않습니다(계산, 시험하지 않음).
권고: 300개 제한은 B부 질문 B1, 보관한 세션의 판정을 벤치에서 셀지는 B2-추가.
