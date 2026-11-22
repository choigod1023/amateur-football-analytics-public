# 공 라벨 (/ball)

근거 코드: `app/ball_review.py`, `app/review_public.py:482-512`, `web/ball.html`, `web/ball.js`, `web/ball-verify.js`. 관련 위키: `wiki/research-tactics-and-ball.md`, `wiki/review-store-and-open-tasks.md` 49줄, 메모리 노트(공 라벨 b01~b39 확인, b40~b54 미완, b55~b63 대기). 작성 2026-11-21.

## 1. 목적
- 누가: 분석가.
- 언제: 공 추적 모델을 학습하거나 평가할 때. 지금은 선수 검출이 우선이라 공 작업은 일시 중단 상태입니다.
- 무엇을: 짧은 연속 클립의 프레임마다 공 위치를 누르거나(라벨), 이미 누른 위치가 맞는지 검증합니다(맞음, 틀림, 옮김). 후보 원은 검증되지 않은 모델 제안이고 사람이 누른 것만 라벨이 됩니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 33~37, 124~126번입니다.
| 경로 | 방식 | 정의 | 종류 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|
| `/ball` | GET | `app/review_public.py:220`(별칭) | 화면 | 라벨과 검증 두 방식이 한 화면 | `web/train.html:3` | 시험 없음 |
| `/ball.js`, `/ball-verify.js` | GET | 같은 곳 | 파일 | 라벨, 검증 | `web/ball.html:34` | 시험 없음 |
| `/api/v1/ball/list` | POST | `:482` | API | 클립 목록과 개수 | `web/ball.js:175`, `web/ball-verify.js:28` | `test_review_public.py::test_ball_review_lists_clips_and_saves_only_valid_positions` |
| `/api/v1/ball/clip` | POST | `:486` | API | 클립 하나 | `web/ball.js:140`, `:161`, `web/ball-verify.js:31` | `test_ball_verify.py::test_model_picks_prepared_offline_reach_the_page_but_are_not_labels` |
| `/api/v1/ball/label` | POST | `:493` | API | 위치 저장 | `web/ball.js:111`, `:113` | `test_ball_verify.py::test_label_source_is_recorded_and_unknown_sources_are_refused` |
| `/api/v1/ball/verify` | POST | `:500` | API | 검증 | `web/ball-verify.js:80` | `test_ball_verify.py::test_positions_can_be_verified_and_the_old_position_is_kept` |
| `/ball-media/{clip}/{name}` | GET | `:507` | 파일 | 프레임 jpg | `web/ball.js:12`, `web/ball-verify.js:15` | `test_review_public.py` |

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 클립 목록 | `<저장소>/ball/index.json`: `clips`(id), `note` | 클립 준비 스크립트(`scripts/prepare_ball_clips*.py`) | 이 화면 |
| 클립 | `ball/clips/<b##>/candidates.json`: `id`, `camera`, `start`, `fps`, `frames`(각 `file` `f_###.jpg`와 후보 원, 재순위 모델의 `pick`) | 같은 스크립트 | 이 화면 |
| 라벨 | `ball/labels/<b##>.json`: 프레임 이름마다 `state`(ball, none, unsure), `updated`, 공이면 `x`, `y`(1920 x 1080 화소), `source`(suggestion, tile, key, snap, manual), 검증되면 `verified`, `verified_at`, 옮겼으면 `history` | 이 화면 | 학습·평가 스크립트 |

## 4. 동작 규칙 (지금 코드)
- 공 위치는 0~1920, 0~1080 안이어야 합니다(`app/ball_review.py:84-86`).
- `clear`는 그 프레임의 답을 지웁니다.
- 검증은 저장된 `state: ball`에만 할 수 있습니다. `moved`면 이전 위치를 `history`에 남기고 `source: verify_click`으로 바꿉니다(`:113-145`).
- 화면(라벨): Enter나 스페이스는 제안 원을 저장, 좌우 화살표로 프레임 이동(`web/ball.js:164-171`). 원 가까이 누르면 원의 중심을 씁니다(`:150`). 재순위 모델이 고른 원을 먼저 제안합니다(`:28`).
- 화면(검증): o 또는 Enter는 맞음, x는 틀림, s나 오른쪽 화살표는 다음(`web/ball-verify.js:100-105`).
- 프레임 사진은 1시간 캐시합니다(`app/review_public.py:512`).

## 5. 받아들임 기준
1. 목록은 클립마다 라벨 수와 ball, none, unsure, 검증 개수를 셉니다. (`test_review_public.py::test_ball_review_lists_clips_and_saves_only_valid_positions`)
2. 프레임 밖 위치와 모르는 프레임은 409입니다. (같은 시험)
3. `source`가 저장되고 모르는 값은 거절합니다. (`test_ball_verify.py::test_label_source_is_recorded_and_unknown_sources_are_refused`)
4. 검증 `moved`는 이전 위치를 `history`에 남깁니다. (`test_ball_verify.py::test_positions_can_be_verified_and_the_old_position_is_kept`)
5. 모델이 고른 후보는 화면에 오지만 라벨이 아닙니다. (`test_ball_verify.py::test_model_picks_prepared_offline_reach_the_page_but_are_not_labels`)
6. `/ball-media/b01/..%2Fcandidates.json`은 404입니다. (`test_review_public.py`)
7. `/ball` 화면 자체를 여는 시험은 없습니다.

## 6. 겹치는 기능과 정리 방향
- 저장 코드가 같은 파일에 두 번 복사(`app/ball_review.py:100-110`, `:135-144`): O7.
- 파일 제공: O2. 화면 스크립트 도우미: O11.
- 사람 판정 화면 갈래: O1. 공 라벨은 좌표를 찍는 일이라 다른 판정 화면과 합치기 어렵습니다. 그대로 두기를 권합니다.

## 7. 알려진 문제와 고정값
- 화면 크기가 1920 x 1080으로 고정입니다(`app/ball_review.py:20`). 다른 해상도 클립은 맞지 않습니다.
- b55~b63(cam4)은 사용자님 라벨을 기다리고 있습니다(메모리 노트, 확인 못함).
