# 분석가 태그 (/tag)

근거 코드: `app/analyst_tags.py`, `app/tag_clips.py`, `web/tag.html`, `web/tag.js`, `web/tag.css`, `scripts/cut_halves_from_tags.py`. 관련 위키: `wiki/analyst-tags.md`. 작성 2026-11-21.

## 1. 목적
- 누가: 분석가(휴대폰).
- 언제: 경기 중(버튼), 하프타임과 경기 후(클립 보기).
- 무엇을: 경기 중 일이 생기면 버튼(우리 슛, 상대 골, 측면 빔 등)을 누릅니다. 서버 시각으로 저장하고, 전후반 시작·끝 표시로 경기 시계("전반 12:34")를 붙입니다. 나중에 표시마다 녹화본에서 클립을 잘라 봅니다. 전후반 자르기 스크립트도 이 표시를 씁니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 68~76번입니다.
| 경로 | 방식 | 정의 | 종류 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|
| `/tag` | GET | `app/analyst_tags.py:91` | 화면 | 버튼 화면 | 링크 없음, `scripts/start_match_day.ps1:40`이 주소 안내 | `test_analyst_tags.py::test_add_list_note_delete_and_page` |
| `/tag.js`, `/tag.css` | GET | `:92-93` | 파일 | 스크립트, 스타일 | `web/tag.html:56`, `:7` | JS만 같은 시험 |
| `/api/v1/analyst-tags` | GET | `:144` | API | 하루치 목록 | `web/tag.js:101` | 같은 시험 |
| `/api/v1/analyst-tags` | POST | `:149` | API | 표시 추가 | `web/tag.js:34`, `:49` | 같은 시험, `test_late_press_keeps_the_estimated_time_only_within_ten_minutes` |
| `/api/v1/analyst-tags/delete` | POST | `:171` | API | 지우기 | `web/tag.js:89`, `:113` | 같은 시험 |
| `/api/v1/analyst-tags/note` | POST | `:182` | API | 메모 고치기 | `web/tag.js:94` | 같은 시험 |
| `/api/v1/analyst-tags/clips` | POST | `:194` | API | 클립 자르기 줄 세우기 | `web/tag.js:119` | 경로 시험 없음 |
| `/analyst-clip/{tag_id}.mp4` | GET | `:206` | 영상 | 클립 | `web/tag.js:97` | 잘못된 이름 404만 |

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 표시 기록 | `<저장소>/analyst-tags/tags.jsonl`(추가만). 줄: `op`(add, delete, note), `id`(12자리 16진), `kind`, `note`, `epoch`, 늦게 보낸 경우 `sent_late` | 이 화면 | 이 화면, `scripts/cut_halves_from_tags.py` |
| 클립 | `analyst-tags/clips/<id>.mp4`(다시 인코딩 없이 복사) | 서버 작업 스레드 | `/analyst-clip` |
| 녹화본 | `FOOTBALL_RECORDINGS` 또는 `app/tag_clips.default_recordings()` | 녹화 스크립트 | 클립 자르기 |
| 화면의 미전송 표시 | 브라우저 저장소 `tagPending`(최대 200개, `web/tag.js:11-12`) | 화면 | 화면 |

## 4. 동작 규칙 (지금 코드)
- 종류: 표시 4개(전반 시작·종료, 후반 시작·종료)와 사건 14개(`app/analyst_tags.py:23-29`).
- 시각은 서버 시각입니다. 바로 못 보낸 표시는 화면이 추정한 시각을 `at`으로 보내고, 서버는 지금부터 10분 전 ~ 5초 후 안이면 받아들입니다(`:159-161`).
- 경기 시계: 시작 표시부터 그 반의 시간을 세고, 종료 표시 0.5초 뒤부터의 표시는 시계가 없습니다(`:55-69`).
- 하루 최대 3000개, 메모 200자(`:33-34`). 목록은 하루 단위(`?day=YYYY-MM-DD`, 기본 오늘).
- 지우기와 메모 고치기는 줄을 덧붙이고, 읽을 때 접습니다(`:41-52`). 잘린 줄은 건너뜁니다.
- 클립 상태: none, queued, running, done, no-recording, failed. 상태는 서버 메모리에만 있어 서버를 다시 켜면 파일이 있는 done 말고는 none이 됩니다(`:80`, `:114-117`).
- 화면은 5초마다 목록, 1초마다 시계를 새로 그립니다(`web/tag.js:125`).

## 5. 받아들임 기준
1. 알려진 종류만 받고 모르는 종류는 400입니다. (`test_analyst_tags.py::test_add_list_note_delete_and_page`)
2. 메모는 200자로 잘립니다. (같은 시험)
3. 지운 표시는 목록에서 빠지고, 메모 고침은 반영됩니다. (같은 시험)
4. 10분 안의 늦은 표시는 추정 시각을, 그보다 오래된 것은 서버 시각을 씁니다. (`test_late_press_keeps_the_estimated_time_only_within_ten_minutes`)
5. 경기 시계는 킥오프부터 세고 종료 휘슬에서 멈춥니다. (`test_clock_counts_from_the_kickoff_and_stops_at_the_whistle`)
6. 클립은 녹화 조각 두 개에 걸쳐도 잘립니다. (`test_clip_is_cut_across_two_recording_pieces`)
7. `/analyst-clip/../x.mp4`는 404입니다. (`test_add_list_note_delete_and_page`)
8. JSON 객체가 아닌 본문은 지금 500입니다(시험용 앱에서 확인). 400이 되어야 하는지는 의도 확인 필요.

## 6. 겹치는 기능과 정리 방향
- 골과 슛 기록이 `/events`, `/shots`와 겹칩니다: O1.
- 화면 파일 도우미가 슛 모듈과 거의 같습니다: O3. 파일 제공: O2.
- 입력 검사 방식: O10.
- 경기 중에 쓰는 화면이므로 A부에서 서버 쪽만 옮기고 `web/tag.js`는 마지막에, 경기 없는 날에만 바꿉니다.

## 7. 알려진 문제와 고정값
- 11월 20일 경기에는 `/tag` 기록이 없었습니다(`wiki/match-1120-live-and-report.md` 8줄).
- 서버를 켤 때마다 클립 작업 스레드 하나를 시작합니다(`app/analyst_tags.py:142`). 라우터를 나눌 때 두 번 시작하지 않게 해야 합니다.
- 고정값: `PER_DAY_MAX = 3000`, `NOTE_MAX = 200`, 늦은 표시 600초, 미전송 보관 200개.
