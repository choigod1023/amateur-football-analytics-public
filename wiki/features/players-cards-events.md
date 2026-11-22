# 선수·카드·이벤트·비교 장면 화면

근거 코드: `app/review_public.py:265-376`, `app/player_identity.py`, `app/event_review.py`, `app/difference_review.py`, `app/reappearance_review.py`, `web/players.*`, `web/cards.*`, `web/events.*`, `web/differences.*`. 관련 위키: `wiki/pipeline-and-paths.md` "선수 확인 모델" 절, `wiki/research-player-identity-and-labelling.md`. 작성 2026-11-21.

## 1. 목적
| 화면 | 누가, 언제 | 무엇을 |
|---|---|---|
| `/players` | 분석가, 경기 후 | 명단(팀, 이름, 번호, 포지션)을 적고, 추적 조각을 선수에게 배정하거나 두 조각이 같은 사람인지 답합니다. **선수 이름(정체성) 연구는 중단 상태입니다**(`CLAUDE.md` 13줄). |
| `/cards` | 분석가·코치, 경기 후 | `scripts/build_player_cards.py`가 만든 선수 카드 그림을 봅니다(보기만). |
| `/events` | 분석가, 경기 후 | 킥오프, 골, 세트피스, 슛 후보 영상을 보고 맞는 종류를 고르거나 손으로 이벤트를 더합니다. 11월 11일 경기용으로 만들어졌습니다. |
| `/train/reappearance`, `/review-differences` | 분석가 | 추적이나 코칭 설명이 바뀐 장면을 두 가지로 보여 주고 어느 쪽이 맞는지 답합니다(한 번 저장하면 덮어쓰지 않음). |

## 2. 화면과 경로
[routes.csv](routes.csv)의 5~21, 105, 106, 116~123번입니다.
| 경로 | 방식 | 정의 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|
| `/players`, `/players.js` | GET | `app/review_public.py:218` | 선수 확인 화면 | `web/report.html:18`, `web/cards.html:28`, `web/differences.html:4` | `test_player_identity.py` |
| `/api/v1/players/state` | POST | `:283` | 구간·명단·조각 | `web/players.js:237`, `:247` | `test_player_identity.py` |
| `/api/v1/players/chain` | POST | `:289` | 한 선수의 다음 조각 후보 | `web/players.js:202` | `test_player_chain.py::test_the_chain_is_served_through_the_api` |
| `/api/v1/players/reject` | POST | `:299` | 아님 기록 | `web/players.js:192` | `test_player_chain.py` |
| `/api/v1/players/roster/set` | POST | `:306` | 명단 저장 | `web/players.js:253` | `test_player_identity.py::test_roster_rules_numbers_are_unique_per_team_and_positions_must_be_known` |
| `/api/v1/players/roster/delete` | POST | `:313` | 명단 지우기 | `web/players.js:38` | 시험 없음 |
| `/api/v1/players/assign` | POST | `:317` | 배정 | `web/players.js:113`, `:190`, `:212` | `test_player_identity.py::test_answers_links_and_groups` |
| `/api/v1/players/link` | POST | `:324` | 같은 사람 연결 | `web/players.js:81` | 경로 시험 없음 |
| `/player-files/{half}/{name}` | GET | `:346` | 조각 사진·짝 영상 | `web/players.js:50`, `:69`, `:175` | `test_player_identity.py` |
| `/cards`, `/cards.js` | GET | `:219` | 카드 화면 | `web/report.html:19`, `web/players.html:60` | `test_player_cards_page.py` |
| `/api/v1/cards/list` | POST | `:331` | 카드 요약 | `web/cards.js:27` | `test_player_cards_page.py` |
| `/card-files/{name}` | GET | `:339` | 카드 PNG | `web/cards.js:20` | `test_player_cards_page.py` |
| `/events`, `/events.js` | GET | `:213` | 이벤트 화면 | `web/train.html:3`, `web/ball.html:4` | 시험 없음 |
| `/api/v1/events/list`, `/label`, `/manual` | POST | `:265`, `:269`, `:276` | 목록, 판정, 손 추가 | `web/events.js:16`, `:60`, `:94`, `:124` | `test_review_public.py::test_event_review_lists_labels_and_serves_media` |
| `/event-media/{name}` | GET | `:514` | 후보 사진·영상 | `web/events.js:45`, `:81` | 같은 시험 |
| `/train/reappearance` | GET | `:217` | 비교 화면(재등장 범위) | `web/train.html:3` | `test_difference_review.py::test_training_reappearance_route_and_filtered_api` |
| `/review-differences` | GET | `:217` | 같은 화면(범위 없음) | 없음 | 시험 없음 |
| `/differences.js`, `/differences.css` | GET | `:217` | 비교 화면 자원 | `web/differences.html:2` | JS만 시험 |
| `/api/v1/differences` | GET | `:353` | 비교 장면 목록 | `web/differences.js:27` | `test_difference_review.py` |
| `/api/v1/differences` | POST | `:364` | 답 저장 | `web/differences.js:25` | `test_page_api_same_origin_and_range_media` |
| `/difference-files/{name}` | GET | `:371` | 비교 영상·사진 | `web/differences.js:16`, `:18` | `test_verdict_and_media_validation` |
| `/api/v1/reappearance/decisions` | GET | `:357` | 지문별 확인된 재등장 연결 | 없음 | 잘못된 값만 시험 |

## 3. 자료
| 자료 | 위치 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 선수 | `<저장소>/players/`: `roster.json`, `<구간>/index.json`과 사진, `assign/`, `links/`, `rejects/`, `provenance/`(사람 답), `auto_notes.json`, `suggestions/`(컴퓨터 값, 따로 보관) | 이 화면, 준비 스크립트 | 이 화면, `scripts/migrate_player_answers.py` |
| 카드 | `cards/summary.json`, `card_*.png` | `scripts/build_player_cards.py` | 이 화면 |
| 이벤트 | `events/candidates.json`, `events/media/c###.mp4|jpg`, 답 `events/labels/<id>.json`(`label`, `event_time`, `note`, `manual`, `updated`) | `scripts/build_event_candidates.py`, 이 화면 | 이 화면 |
| 비교 장면 | `differences/queue.json`(`items`: `id` d####, `kind` tracking 또는 coaching, `review_scope`, 영상·사진 이름), `inactive.json`, 답 `answers/<id>.json`(`verdict`, `note`, `fingerprint`, `source: human`) | 준비 스크립트(`scripts/prepare_difference_scenes.py` 등), 이 화면 | 이 화면, `app/reappearance_review.py` |

## 4. 동작 규칙 (지금 코드)
- 선수: 번호는 팀 안에서 겹칠 수 없고 포지션은 정해진 글자만 받습니다. 명단에서 지우면 그 선수의 배정도 지웁니다(`app/player_identity.py:100-101`). 경로는 pydantic으로 길이만 검사하고 나머지는 저장 모듈이 검사합니다.
- 카드: 요약 파일이 없으면 빈 목록과 `made: null`입니다(`app/review_public.py:334-337`). 카드 이름은 `card_` + 영문·숫자 20자 + `.png`만.
- 이벤트: 후보 id는 `c###`, 손 추가는 `m` + 16진 12자리. `clear`로 답을 지우면 손 추가 이벤트는 사라집니다. 시각은 0~20000초(`app/event_review.py:21`). 화면은 판정 결과를 JSON 파일로 내려받는 단추도 있습니다(`web/events.js:117`).
- 비교 장면: 답은 장면 내용의 지문과 함께 저장되고, 장면이 바뀌면 예전 답은 "현재 아님"으로 남습니다. 같은 답을 다시 보내면 그대로 돌려주고, 다른 답은 409로 거절합니다(`app/difference_review.py:89-93`). `/train/reappearance`는 화면 스크립트가 주소를 보고 `scope=occlusion-reappearance`를 붙입니다(`web/differences.js:5`).

## 5. 받아들임 기준
1. 같은 팀에 같은 번호를 두 번 저장하면 409입니다. (`test_player_identity.py::test_roster_rules_numbers_are_unique_per_team_and_positions_must_be_known`)
2. 사람 답과 자동 메모는 다른 파일에 저장됩니다. (`test_player_identity.py::test_answers_links_and_groups`)
3. 모르는 조각이나 이상한 파일 이름(`pair_10_11.exe`)은 거절합니다. (`test_unknown_tracks_and_bad_names_are_refused_and_the_server_serves_the_page`)
4. 카드가 없으면 빈 목록이고, 카드 이름이 형식에 맞지 않으면 404입니다. (`test_player_cards_page.py` 2개)
5. 이벤트 판정과 손 추가가 목록에 나오고 미디어는 `events/media` 밖을 주지 않습니다. (`test_review_public.py::test_event_review_lists_labels_and_serves_media`)
6. 비교 장면의 답은 한 번 저장되면 다른 답으로 덮어쓸 수 없습니다. (`test_difference_review.py::test_stable_queue_preserves_answers_and_never_expires`)
7. 장면이 바뀌면 예전 답을 다시 쓰지 않습니다. (`test_new_scene_cannot_reuse_an_old_answer`)
8. `/train/reappearance`의 목록은 재등장 범위만 보입니다. (`test_training_reappearance_route_and_filtered_api`)
9. `/api/v1/players/roster/delete`와 `/link` 경로는 시험이 없습니다.

## 6. 겹치는 기능과 정리 방향
- `/review-differences`와 `/train/reappearance`가 같은 파일입니다. `/review-differences`는 부르는 곳이 없습니다: [overlaps.md](overlaps.md) O1, B부 질문 7.
- `/api/v1/reappearance/decisions`는 부르는 화면이 없고, 스크립트는 함수를 직접 가져다 씁니다(`scripts/audit_reviewed_tracking.py:9`). 쓰임 불명.
- 이벤트의 골·슛 기록이 `/tag`, `/shots`와 겹칩니다: O1.
- 선수 화면은 연구 중단 상태인데 보고서 화면 위쪽 메뉴에 남아 있습니다(`web/report.html:18`). 숨길지는 B부 질문 8.
- 파일 제공 4개(`/player-files`, `/card-files`, `/event-media`, `/difference-files`): O2.

## 7. 알려진 문제와 고정값
- 선수 화면 문구가 "B (어두운 옷)", "A (밝은 옷)"처럼 11월 11일 경기 색을 가정합니다. `web/team_names.js`가 프로필이 있으면 글자만 바꿉니다(`wiki/team-select.md` 6-1절).
- 추적을 다시 만들면 조각 번호가 바뀌어 `scripts/migrate_player_answers.py`로 답을 옮겨야 합니다(`wiki/pipeline-and-paths.md` 37줄).
- 비교 장면 메모 500자, 이벤트 메모 200자.
