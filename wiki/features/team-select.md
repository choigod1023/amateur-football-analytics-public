# 팀 선택 (우리 팀 색 고르기)

근거 코드: `app/team_select_routes.py`, `app/team_color_profile.py`, `web/team_select.html`, `web/team_select.js`, `web/team_names.js`, `scripts/team_select_prepare.py`. 관련 위키: `wiki/team-select.md`(설계와 정확도 측정), `wiki/match-1118-venue-and-report.md` 9줄. 작성 2026-11-21.

## 1. 목적
- 누가: 코치(또는 분석가).
- 언제: 킥오프 직후, 라이브 실행을 시작하기 전. 옷을 갈아입었을 때만 다시.
- 무엇을: 처음 약 10초의 선수 옷 색을 두 무리로 나눈 사진을 보고 "우리 팀은 어느 쪽"인지 한 번 고릅니다. 결과는 라이브 실행(`--team-profile`)과 보고서 스크립트가 읽습니다. 선수·보고서 화면의 팀 이름 글자도 이 선택을 따릅니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 81~87번입니다.
| 경로 | 방식 | 정의 | 종류 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|
| `/team-select` | GET | `app/team_select_routes.py:17`, `:64-65` | 화면 | 고르기 화면 | 링크 없음(주소를 직접 엶) | `test_team_color_profile.py::test_routes_choose_with_confirmation_and_write_profile` |
| `/team-select.js` | GET | 같은 곳 | 파일 | `web/team_select.js` | `web/team_select.html:38` | 시험 없음 |
| `/team-names.js` | GET | 같은 곳 | 파일 | `web/team_names.js`: 팀 이름 글자 바꾸기 | `web/players.html:111`, `web/report.html:75` | 시험 없음 |
| `/api/v1/team-select` | GET | `:67` | API | 사진 후보와 저장된 프로필 요약 | `web/team_select.js:66`, `web/team_names.js:15` | 같은 시험 |
| `/team-select-files/{name}` | GET | `:77` | 파일 | 후보 사진 | `web/team_select.js:34` | 같은 시험 |
| `/api/v1/team-select/choose` | POST | `:84` | API | 고르기(두 번째 요청에서 저장) | `web/team_select.js:43`, `:52` | 같은 시험 |
| `/api/v1/team-select/clear` | POST | `:101` | API | 저장 지우기 | `web/team_select.js:62` | 같은 시험 |

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 사진 후보 | `<저장소>/service/team_select/candidates.json`: `created`, `source`, `start`, `seconds`, `people_read`, `ok`, `weak`, `reason`, `separation`, `groups`(무리마다 `images`, `colour_text`), `others_people`, `split`; 사진 `g0_0.jpg` 꼴 | `scripts/team_select_prepare.py` | 이 화면 |
| 팀 프로필 | `<저장소>/service/team_profile.json`: 두 무리의 대표 색과 퍼짐, `created`, `note`(확인 문장), `source` | `POST /choose`(`app/team_color_profile.py:132` 임시 파일 후 바꾸기) | `scripts/run_live_feedback.py --team-profile`, 보고서 스크립트, `/api/v1/team-select` |

## 4. 동작 규칙 (지금 코드)
- 후보가 없거나 `ok`가 아니거나 무리가 2개 미만이면 고르기를 409로 거절합니다(`app/team_select_routes.py:87-88`).
- 그룹 번호는 0(사진 왼쪽)과 1(오른쪽)뿐입니다(`:89-90`).
- 화면이 본 후보의 `created`와 지금 후보가 다르면 409 "그 사이에 새 사진이 만들어졌습니다"(`:91-92`).
- `confirmed: false`면 저장하지 않고 확인 문장만 돌려줍니다. 문장은 "우리 팀은 사진 왼쪽 … 옷 팀입니다. 맞습니까?"(`:28-30`, `:94-95`). `confirmed: true`면 저장합니다.
- 프로필 파일이 깨졌으면 요약에 `error`를 넣습니다(조용히 넘어가지 않음, `:48-51`).
- 지우기는 파일을 지우고 있었는지만 알려 줍니다.
- `web/team_names.js`: `data-team-name` 표시가 있는 글자만 "우리 팀(…색 옷)", "상대 팀"으로 바꿉니다. 프로필이 없거나 요청이 실패하면 원래 글자를 둡니다(`web/team_names.js:1-3`).
- 라이브 실행은 실행 중에 프로필을 다시 읽지 않습니다(`wiki/team-select.md` 4절).

## 5. 받아들임 기준
1. 후보가 없을 때 `/api/v1/team-select`는 `candidates: null`이고 고르기는 409입니다. (`test_team_color_profile.py::test_routes_choose_with_confirmation_and_write_profile`)
2. `confirmed: false`로 고르면 저장 없이 확인 문장을 돌려줍니다. (같은 시험)
3. `confirmed: true`로 고르면 `service/team_profile.json`이 생기고 요약에 우리 팀 색 이름이 나옵니다. (같은 시험)
4. 다른 `created` 값으로 고르면 409입니다. 시험 없음(코드 `:91-92`로만 확인).
5. `/team-select-files/../candidates.json`은 404입니다. (같은 시험)
6. 깨진 프로필 파일은 오류로 보고하고 예전 방식으로 조용히 돌아가지 않습니다. (`test_team_color_profile.py::test_damaged_profile_is_an_error_not_a_silent_fallback`)
7. 다른 Origin의 POST는 403입니다. 경로 시험 없음(미들웨어 공통 시험 `test_review_public.py::test_service_rejects_wrong_host_and_only_serves_expected_files`).
8. 프로필이 없을 때 `/players`와 `/report`의 팀 이름 글자는 그대로입니다. 시험 없음.

## 6. 겹치는 기능과 정리 방향
- 화면 파일을 내보내는 도우미가 `app/service_routes.py`와 글자까지 같습니다: [overlaps.md](overlaps.md) O3. A부에서 공통으로 뺍니다.
- 후반 "팀 색 재확인" 띠(`web/watch-banner.js`, [halftime.md](halftime.md))는 이 화면으로 링크하지 않습니다. 잇는 방법은 `wiki/team-select.md` 4절에 제안만 있습니다(의도 확인 필요).
- 어느 화면에서도 `/team-select`로 가는 링크가 없습니다(O13). B부 질문 5의 목차 화면이 생기면 들어갑니다.

## 7. 알려진 문제와 고정값
- 11월 18일 경기에서 가까운 선심의 사진이 대표로 뽑혀 쓸 수 없었습니다(`wiki/match-1118-venue-and-report.md` 9줄).
- 옷 색은 키 30픽셀 이상 상자만 읽습니다(`app/team_color_profile.py`, `wiki/match-1120-live-and-report.md` 26줄).
- 사진 이름은 `g0_0.jpg`~`g1_9.jpg`만 받습니다(`PICTURE`, `app/team_select_routes.py:18`).
- 이 화면은 스타일을 페이지 안에 씁니다(`web/team_select.html`). CSP가 `style-src 'unsafe-inline'`을 허용하므로 동작합니다.
