# 영상·사진 파일 제공

근거 코드: 아래 표의 각 경로. 작성 2026-11-21.

## 1. 목적
- 누가: 다른 화면의 스크립트(사람이 직접 주소를 열지는 않음).
- 언제: 각 화면이 카드, 사진, 짧은 영상을 보여 줄 때.
- 무엇을: 저장소 안의 정해진 폴더에서 이름 규칙에 맞는 파일만 돌려줍니다. 저장소 밖이나 다른 폴더의 파일은 주지 않습니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 16, 17, 21, 25, 32, 37~39, 64, 76, 85번과 실시간 영상 80번입니다.
| 경로 | 정의 | 폴더 | 이름 규칙 | media type | 캐시 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|---|
| `/card-files/{name}` | `app/review_public.py:339` | `cards/` | `card_[A-Za-z0-9_-]{1,20}.png` | image/png | no-store | `web/cards.js:20` | `test_player_cards_page.py` |
| `/player-files/{half}/{name}` | `:346` | `players/<구간>/` | 구간 `[a-z0-9]{1,12}`, 이름 `[A-Za-z0-9_-]{1,40}.(jpg|mp4)`(`app/player_identity.py:28`, `:31`) | jpg 또는 mp4 | no-store | `web/players.js:50`, `:69`, `:175` | `test_player_identity.py` |
| `/difference-files/{name}` | `:371` | `differences/` | `d####(-글자).(mp4|jpg|png)`이고 `queue.json`에 있는 이름 | 확장자별 | no-store | `web/differences.js:16`, `:18` | `test_difference_review.py` |
| `/alert-files/{session}/{name}` | `:393` | `alerts/<세션>/` | 세션 40자, 이름 `[A-Za-z0-9_-]{1,60}.(jpg|mp4)` | jpg 또는 mp4 | no-store | `web/alerts.js:66-71` | `test_alert_review.py` |
| `/report-files/{job}/{name}` | `:471` | `reports/<작업>/` | `OUTPUTS` 목록의 이름만 | mp4, md(text/plain), json | no-store | `web/report.js:123`, `:126`, `:130` | `test_report_upload.py` |
| `/ball-media/{clip}/{name}` | `:507` | `ball/clips/<클립>/` | 클립 `b##`, 이름 `f_###.jpg` | image/jpeg | private, 1시간 | `web/ball.js:12`, `web/ball-verify.js:15` | `test_review_public.py` |
| `/event-media/{name}` | `:514` | `events/media/` | `c###.(mp4|jpg)` | mp4 또는 jpg | private, 1시간 | `web/events.js:45`, `:81` | `test_review_public.py` |
| `/thumbs/{name}` | `:522` | `thumbs/`(없으면 `pending/`에서 만듦) | 16진 32자리 `.jpg` | image/jpeg | private, 1시간 | `web/training-label.js:311` | `test_review_public.py` |
| `/shots-clip/{name}` | `app/shot_routes.py:88` | `shots/clips/` | `s###.mp4` | video/mp4 | no-store | `web/shots.js:87` | 시험 없음 |
| `/analyst-clip/{tag_id}.mp4` | `app/analyst_tags.py:206` | `analyst-tags/clips/` | 16진 12자리 | video/mp4 | no-store | `web/tag.js:97` | 404만 시험 |
| `/team-select-files/{name}` | `app/team_select_routes.py:77` | `service/team_select/` | `g[01]_[0-9].jpg` | image/jpeg | no-store | `web/team_select.js:34` | `test_team_color_profile.py` |
| `/live-video.mjpg` | `app/live_video_routes.py:147` | 파일 아님(RTSP) | 없음 | multipart JPEG | no-store | `web/live-video-view.js:13` | 시험 없음 |
"no-store"는 경로가 따로 정하지 않아 미들웨어가 붙인 값입니다(`app/review_public.py:234`).

## 3. 자료
각 기능 페이지의 3절을 봅니다. 이 경로들은 `/thumbs`를 빼고 아무것도 쓰지 않습니다. `/thumbs`는 처음 요청 때 작은 사진을 만들어 `thumbs/`에 저장합니다(`app/training_labels.py:118-139`).

## 4. 동작 규칙 (지금 코드)
- 이름 규칙에 맞지 않거나 파일이 없으면 404입니다. 경로 조각(`..%2F`)이 섞인 이름은 규칙에서 걸러집니다.
- `/difference-files`는 이름 규칙에 더해 `queue.json`에 적힌 이름인지와 실제 경로의 폴더가 `differences/`인지 확인합니다(`app/difference_review.py:103-110`). 가장 엄격합니다.
- `/report-files`는 작업 id가 형식에 맞지 않으면 `ValueError`를 404로 바꿉니다(`app/review_public.py:473-478`).
- 영상(mp4)은 FileResponse라 브라우저의 구간 요청(Range)을 받습니다(`test_difference_review.py::test_page_api_same_origin_and_range_media`가 확인).

## 5. 받아들임 기준
1. 규칙에 맞는 파일은 200과 표의 media type입니다. (각 기능의 시험, 위 표)
2. `..%2F`가 들어간 이름은 404입니다. (`test_alert_review.py`, `test_review_public.py`, `test_report_upload.py`, `test_team_color_profile.py`)
3. `/ball-media`, `/event-media`, `/thumbs`만 `Cache-Control: private, max-age=3600`이고 나머지는 `no-store`입니다. 시험 없음(A부 0단계에서 기록).
4. mp4는 Range 요청에 206으로 답합니다. (`test_difference_review.py::test_page_api_same_origin_and_range_media`) 다른 mp4 경로는 시험 없음.
5. `/shots-clip`은 `s###.mp4`가 아닌 이름에 404입니다. 시험 없음.

## 6. 겹치는 기능과 정리 방향
- 11개 파일 경로가 거의 같은 코드(약 77줄)입니다: [overlaps.md](overlaps.md) O2. 권고는 **공통 부분만 빼기**(주소, media type, 캐시 헤더는 그대로). 주소를 하나로 합치는 것은 권하지 않습니다(저장된 JSON과 화면이 주소를 직접 씀).

## 7. 알려진 문제와 고정값
- 캐시 정책이 경로마다 다르고 이유가 적혀 있지 않습니다. 의도 확인 필요.
- `/alert-files`의 mp4 허용은 커밋하지 않은 변경입니다(2026-11-20, 이미 운영 중).
