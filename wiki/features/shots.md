# 슛 표시 (/shots)

근거 코드: `app/shot_routes.py`, `app/xg.py`, `web/shots.html`, `web/shots.js`, `web/shots.css`, `scripts/make_shot_candidates.py`. 관련 위키: `wiki/match-1120-live-and-report.md` "슛 표시 후보" 절. 작성 2026-11-21.

## 1. 목적
- 누가: 분석가.
- 언제: 경기 후.
- 무엇을: 한 팀이 상대 박스에 들어간 순간들의 짧은 영상을 보고 무슨 일이 있었는지(슛 아님, 빗나감, 막힘, 수비 맞음, 골대, 골)와 슛 위치를 누릅니다. 서버가 대략적인 xG를 붙입니다. 후보에 없던 슛(박스 밖 등)은 손으로 더합니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 60~67번입니다.
| 경로 | 방식 | 정의 | 종류 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|
| `/shots` | GET | `app/shot_routes.py:49` | 화면 | 슛 표시 화면 | 링크 없음 | 시험 없음 |
| `/shots.js`, `/shots.css` | GET | `:50-51` | 파일 | 스크립트와 스타일 | `web/shots.html:42`, `:8` | 시험 없음 |
| `/api/v1/shots` | GET | `:83` | API | 후보와 저장된 표시 | `web/shots.js:124` | 시험 없음 |
| `/shots-clip/{name}` | GET | `:88` | 영상 | 후보 영상 `s###.mp4` | `web/shots.js:87` | 시험 없음 |
| `/api/v1/shots/tag` | POST | `:109` | API | 표시 저장 | `web/shots.js:63` | 시험 없음 |
| `/api/v1/shots/clear` | POST | `:122` | API | 표시 지우기 | 없음 | 시험 없음 |
| `/api/v1/shots/extra` | POST | `:135` | API | 손으로 슛 추가 | `web/shots.js:74` | 시험 없음 |

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 후보 | `<저장소>/shots/candidates.json`: `candidates`(각 `id` `s###`, `side` ours/theirs 또는 모름, `match`), `pitch_length`(기본 89), `pitch_width`(기본 62); 영상 `shots/clips/s###.mp4` | `scripts/make_shot_candidates.py` | 이 화면 |
| 표시 | `shots/tags/<id>.json`: `result`, `side`, `saved`, 슛이면 `x`, `y`(m, 0.1 반올림), `xg`(소수 셋째), 손 추가면 `match`, `half`(전반·후반), `minute`, `manual: true`. 손 추가 id는 `x-###` | 이 화면 | 보고서 스크립트(확인 못함) |

## 4. 동작 규칙 (지금 코드)
- 결과는 `none, off, saved, blocked, post, goal` 여섯 가지(`app/shot_routes.py:20`). `none`이면 위치를 받지 않습니다.
- 팀: 후보에 `side`가 있으면 그것을 쓰고, 없으면(11월 11일 골 후보) 화면이 보낸 값을 씁니다(`:117`).
- 위치 범위: 길이 방향은 경기장 길이의 반에 5m를 더한 범위, 폭 방향은 -40~40m(`:104-105`). 벗어나면 400.
- xG는 `app/xg.py`의 대략 모델이며 우리 팀은 오른쪽으로 공격한다고 봅니다(`:106`).
- 손 추가 번호는 `x-` 파일 개수 + 1입니다(`:145`). 파일을 지우면 번호가 다시 쓰일 수 있습니다.
- 본문은 pydantic이 아니라 손으로 검사합니다. JSON 객체가 아니면 `AttributeError`(500)입니다(시험용 앱에서 확인, [overlaps.md](overlaps.md) O10).

## 5. 받아들임 기준
1. 후보 파일이 없으면 `/api/v1/shots`는 빈 후보와 89 x 62를 돌려줍니다. 시험 없음(시험용 앱에서 200과 키 `candidates, pitch_length, pitch_width, tags` 확인).
2. 없는 후보 id로 표시하면 404입니다. 시험 없음.
3. `result: goal`, 위치가 범위 안이면 `x`, `y`, `xg`가 저장됩니다. 시험 없음.
4. 범위 밖 위치는 400입니다. 시험 없음.
5. 손 추가는 알려진 `match`와 전반·후반만 받고 `x-001`부터 번호를 붙입니다. 시험 없음.
6. `/shots-clip/../x`는 404입니다. 시험 없음.
7. 다른 Origin의 POST는 403입니다. 미들웨어 공통 시험만 있음.

## 6. 겹치는 기능과 정리 방향
- 골과 슛을 `/events`, `/tag`, `/shots` 세 곳에 따로 기록합니다: O1. 시점이 달라(경기 중, 경기 후) 지금은 그대로 두기를 권하지만 B부 질문 5의 목차 화면에서 함께 보이게 할 수 있습니다.
- 화면 파일 도우미, 파일 제공, JSON 저장 코드가 다른 모듈과 복사: O2, O3, O7.
- `/api/v1/shots/clear`는 부르는 화면이 없습니다(B부 질문 7).
- 이 기능 전체에 시험이 없습니다. A부 0단계의 특성 시험이 처음 시험이 됩니다.

## 7. 알려진 문제와 고정값
- 11월 20일 경기 후보 23개를 사용자님이 표시했습니다(슛 아님 19 등, `wiki/match-1120-live-and-report.md` 48줄).
- 고정값: 경기장 89 x 62(후보 파일이 없을 때), 위치 범위 ±5m와 ±40m, 손 추가 분 0~60.
