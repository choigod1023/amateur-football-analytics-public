# 학습 장면 라벨 (놓친 선수, /train)

근거 코드: `app/training_labels.py`, `app/review_public.py:522-529`, `:545-623`, `web/train.html`, `web/training-label.js`, `web/review-annotation.js`, `web/minimap.js`. 관련 위키: `wiki/review-store-and-open-tasks.md` 10줄, `wiki/detector-experiments.md`, 메모리 노트(사용자님이 장면 100~123에서 놓친 선수를 그림). 작성 2026-11-21.

## 1. 목적
- 누가: 분석가.
- 언제: 선수 검출기를 개선할 때(지금 가장 높은 우선순위).
- 무엇을: 저장된 경기 장면에서 검출 상자마다 역할(선수, 골키퍼, 심판, 관중, 그림자, 중복, 모름), 팀, 옷 색을 저장하고, 검출기가 놓친 사람은 상자를 직접 그립니다. 같은 화면에서 카메라별 경기장 영역(다각형)과 경기장 보정 점도 찍습니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 39, 89~104번입니다.
| 경로 | 방식 | 정의 | 종류 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|
| `/train` | GET | `app/review_public.py:211`(별칭) | 화면 | 학습 자료 확인 | `web/ball.html:4`, `web/events.html:4` | `test_review_public.py` |
| `/training-label.js`, `/review-annotation.js`, `/minimap.js` | GET | `:211-212` | 파일 | 라벨, 상자 그리기·영역, 보정·미니맵 | `web/train.html:3` | 앞의 둘만 |
| `/thumbs/{name}` | GET | `:522` | 파일 | 장면 작은 사진(처음 요청 때 만들어 저장) | `web/training-label.js:311` | `test_scene_thumbnails_and_label_counts` |
| `/api/v1/training-labels/scenes` | POST | `:552` | API | 장면 목록 | `web/training-label.js:333`, `:488`, `web/review-annotation.js:175`, `web/minimap.js:328` | `test_scene_queue_is_ordered_and_skips_broken_scenes` |
| `/api/v1/training-labels/restore` | POST | `:593` | API | 장면 열기 | `web/training-label.js:343`, `:489`, `:495` | `test_review_public.py` |
| `/api/v1/training-labels/latest` | POST | `:545` | API | 목록이 비었을 때 최근 장면 | `web/training-label.js:491` | `test_review_public.py` |
| `/api/v1/training-labels` | POST | `:614` | API | 상자 하나의 답 저장 | `web/training-label.js:133`, `:405` | `test_public_review_manual_box_and_distinct_false_positive_labels` |
| `/api/v1/training-labels/suggestions` | POST | `:600` | API | 팀 추천(모델 값)과 답한 상자 | `web/training-label.js:411` | 경로 시험 없음 |
| `/api/v1/training-labels/manual-box` | POST | `:607` | API | 놓친 사람 상자 추가 | `web/review-annotation.js:83` | `test_public_review_manual_box_and_distinct_false_positive_labels` |
| `/api/v1/training-labels/delete-box` | POST | `:586` | API | 그린 상자 지우기 | `web/training-label.js:449` | `test_hand_drawn_box_can_be_deleted_only_while_unanswered` |
| `/api/v1/training-labels/pitch-regions`, `/pitch-region` | POST | `:556`, `:560` | API | 경기장 영역 읽기·저장 | `web/review-annotation.js:175`, `:205` | `test_pitch_region_is_validated_stored_and_clearable` |
| `/api/v1/training-labels/calibrations`, `/calibration` | POST | `:567`, `:571` | API | 보정 점 읽기·저장 | `web/minimap.js:328`, `:311`, `:321` | `test_calibration_scene_labels_and_camera_fields` |
| `/api/v1/training-labels/scene-labels` | POST | `:579` | API | 장면 하나의 저장된 답 | `web/minimap.js:328`, `:346` | 같은 시험 |

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 장면 | `<저장소>/pending/<32자리 토큰>.json`과 `.jpg`. JSON: `people`(상자 `id`, `bbox`, `annotation_origin`, 힌트), `timestamp`, `source`, `order`, `source_provenance`(`split`, `camera_setting`, `clip_time_sec`, `bg_to_ref`) | 장면 준비 스크립트, 손 상자 추가·삭제 | 이 화면 |
| 사람 답 | `<저장소>/<해시 32자리>.json`(장면 토큰과 상자 id의 해시) + 장면 사진 `<토큰>.jpg`: `image`, `track_id`, `bbox_image_norm`, `role`, `team_group`, `shirt_color`, `shirt_detail`, `provenance`(`human_confirmed_detection` 또는 `human_drawn_and_confirmed`), `annotation_origin`, `training_disposition`, `source_provenance`, 모델 힌트는 `*_unverified` 칸에 따로 | 이 화면 | 학습·평가 스크립트 |
| 경기장 영역 | `regions/pitch_regions.json` | 이 화면 | 이 화면 |
| 경기장 보정 | `calibration/calibrations.json`(카메라별 점 4~40개, 경기장 치수), 바뀌기 전 값은 `calibration/calibration_history.jsonl` | 이 화면 | 보고서 작업(`FOOTBALL_REPORT_CALIBRATIONS`, `scripts/run_review_server.ps1:77`), 라이브와 분석 스크립트 |
| 작은 사진 | `thumbs/<토큰>.jpg`(폭 192) | `/thumbs` | 이 화면 |

## 4. 동작 규칙 (지금 코드)
- 장면 목록은 `order`(없으면 `created`), 그다음 토큰 순입니다. 사진이 없거나 깨진 장면은 건너뜁니다(`app/training_labels.py:141-176`).
- 첫 방문은 목록의 첫 장면을 열고, 그다음부터는 브라우저에 기억한 장면을 엽니다(`web/training-label.js:484-496`).
- 심판, 관중, 그림자, 중복, 모름은 팀이 `unknown`이어야 합니다(서버 422, `app/review_public.py:616-617`; 화면도 같은 검사).
- "빠른 예"로 저장하는 답은 처음 한 번만 씁니다(`only_if_new`). 이미 있으면 409(`app/training_labels.py:430-436`).
- 손으로 그린 상자는 답을 저장하기 전에만 지울 수 있습니다.
- 보정은 카메라 하나에 점 4~40개, 서로 다른 기준점 4개 이상, 경기장 치수가 범위 안이어야 합니다. 바꾸거나 지울 때마다 이전 값을 기록 파일에 남깁니다(`:273-325`).
- 이 화면의 "현재 화면 고정"과 "다른 학습 장면" 단추는 꺼져 있습니다(`web/train.html`). 그 단추가 부르는 `/api/v1/training-labels/snapshot`과 `/next-sample`은 이 서버에 없습니다(시험용 앱에서 405). 같은 스크립트를 쓰는 예전 대시보드와 `scripts/run_training_questions.py:63`용입니다.

## 5. 받아들임 기준
1. 장면 목록은 `order` 순이고 깨진 장면을 건너뜁니다. (`test_review_public.py::test_scene_queue_is_ordered_and_skips_broken_scenes`)
2. 손 상자를 추가하면 장면에 `human_drawn` 상자가 생기고, 그 상자의 답은 `human_drawn_and_confirmed`로 저장됩니다. (`test_public_review_manual_box_and_distinct_false_positive_labels`)
3. 답한 손 상자는 지울 수 없고, 답이 없으면 지울 수 있습니다. (`test_hand_drawn_box_can_be_deleted_only_while_unanswered`)
4. 경기장 영역은 검사 후 저장되고 지울 수 있습니다. (`test_pitch_region_is_validated_stored_and_clearable`)
5. 보정을 바꾸면 이전 값이 기록 파일에 남습니다. (`test_calibration_scene_labels_and_camera_fields`)
6. `/thumbs/not-a-token.jpg`와 `/thumbs/..%2Fpending%2F`는 404입니다. (`test_scene_thumbnails_and_label_counts`, `test_service_rejects_wrong_host_and_only_serves_expected_files`)
7. 심판 역할에 팀을 주면 422입니다. 경로 시험 확인 못함(코드 `:616-617`).
8. `/api/v1/training-labels/suggestions`의 응답에 `suggestions`와 `confirmed_ids`가 있습니다. 경로 시험 없음.

## 6. 겹치는 기능과 정리 방향
- 놓친 선수와 팀 판정을 `/alerts`의 `label-` 세션도 받습니다: [overlaps.md](overlaps.md) O1, B부 질문 1.
- 경기장 보정 찍기가 이 화면 안에 숨어 있습니다. 보고서와 라이브가 같은 파일을 읽으므로 "학습 라벨"과는 다른 기능입니다. A부에서는 같은 라우터에 두되 파일(경로 묶음)을 나눠 둡니다(`training_labels_routes`와 `calibration_routes`). 화면을 나눌지는 의도 확인 필요.
- `/train/reappearance`는 이름이 `/train` 아래지만 비교 장면 화면입니다([players-cards-events.md](players-cards-events.md)).
- 스크립트 `web/training-label.js`는 예전 대시보드와 함께 쓰므로 고칠 때 두 화면을 같이 확인해야 합니다.

## 7. 알려진 문제와 고정값
- 2026-11-17 기준 장면 133개(미배정 75, 학습 36, 시험 14, 제외 8), 후보 상자 881개, 사용자님이 그린 상자 34개(`wiki/review-store-and-open-tasks.md` 10줄). 지금 수는 다시 세지 않았습니다.
- 화면 문구가 "형광 조끼를 팀 A"로 안내하는 등 11월 11일 경기 색을 가정합니다(`wiki/team-select.md` 1절 표, `web/training-label.js:50-61`).
- 관중 판단 고정값: 1080 화면에서 98픽셀 이상이면 관중(`web/review-annotation.js:161-163`).
- 경기장 치수 범위 `PITCH_LIMITS`(`app/training_labels.py:19-20`).
