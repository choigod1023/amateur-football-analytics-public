# 알림 판정과 손 라벨 묶음 (/alerts)

근거 코드: `app/alert_review.py`, `app/review_public.py:378-398`, `web/alerts.html`, `web/alerts.js`, `web/alerts.css`. 관련 위키: `wiki/review-store-and-open-tasks.md` 5~8줄, `wiki/live-feedback.md`, `CLAUDE.md` 49줄(손 라벨은 `/alerts`에 `label-<날짜>-<주제>` 세션으로 올림). 작성 2026-11-21.

## 1. 목적
- 누가: 분석가(사용자님).
- 언제: 경기 후, 그리고 하위 작업이 손 라벨 묶음을 올렸을 때.
- 무엇을: (1) 라이브 코칭 알림 하나하나를 "맞음, 틀림, 맞지만 쓸모없음"으로 판정합니다. 이 판정은 알림 기준을 조정하는 유일한 정답입니다(`app/alert_review.py:1-6`). (2) 2026-11-21부터 같은 화면이 모델 개선용 사람 판정 묶음(`label-` 세션)을 받습니다. 이 세션들은 맨 위에 "먼저" 표시로 보입니다.

## 2. 화면과 경로
[routes.csv](routes.csv)의 22, 23, 25, 110~112번입니다.
| 경로 | 방식 | 정의 | 종류 | 하는 일 | 부르는 곳 | 시험 |
|---|---|---|---|---|---|---|
| `/alerts` | GET | `app/review_public.py:215`(별칭) | 화면 | 판정 화면 | `web/report.html:17`, `:57`, `web/players.html:59` | `test_alert_review.py::test_the_pages_and_the_api_work_through_the_server` |
| `/alerts.js`, `/alerts.css` | GET | 같은 곳 | 파일 | 판정 화면 스크립트와 스타일 | `web/alerts.html:38`, `:9` | 같은 시험 |
| `/api/v1/alerts/list` | POST | `:378` | API | 전체 목록과 집계 | `web/alerts.js:123` | 같은 시험 |
| `/api/v1/alerts/label` | POST | `:382` | API | 판정 저장·지우기 | `web/alerts.js:49` | 같은 시험 |
| `/alert-files/{session}/{name}` | GET | `:393` | 파일 | 장면 사진·영상 | `web/alerts.js:66-71` | `test_unknown_alerts_and_labels_are_refused_and_images_stay_inside_the_session` |

## 3. 자료
| 자료 | 위치와 형식 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| 세션 | `<저장소>/alerts/<세션>/alerts.jsonl`(한 줄 한 알림), 사진 `alerts_NNNN.jpg`, 영상 `alerts_NNNN.mp4`. 세션 이름은 영문, 숫자, `_`, `-` 40자 이하 | 라이브 실행, `scripts/import_alerts_for_review.py`, 하위 작업의 세션 만들기 스크립트 | 이 화면, 벤치, 감시, 하프타임 |
| 판정 | `alerts/labels/<세션>-<번호>.json`: `id`, `label`(ok, wrong, useless), `note`(200자), `updated` | 이 화면 | 이 화면, 벤치 정확도 |
| 보관 | `alerts/_archive-YYYYMMDD/`(이름에 `_`가 앞에 있어도 정규식에는 맞지만 그 안에 `alerts.jsonl`이 없으므로 세션이 아님) | 손으로 옮김 | 없음 |
- 번호는 `alerts.jsonl`의 줄 번호(0부터)입니다. 깨진 줄도 자리를 지켜 번호가 밀리지 않습니다(`app/alert_review.py:45`). `label-` 세션은 1번부터 세려고 0번 줄에 안내용 상태 줄을 넣습니다.

## 4. 동작 규칙 (지금 코드)
- 서버(`app/alert_review.py:62-95`): 세션을 `alerts.jsonl` 수정 시각이 최근인 순으로, 세션 안은 알림 시각이 늦은 순으로 늘어놓고 **최대 300개에서 자릅니다**(`MAX_ALERTS`, `:18`, `:84`). `polarity: status` 줄은 빼지만 번호는 유지합니다. 종류별 집계는 자른 뒤의 300개로 합니다.
- 화면(`web/alerts.js`):
  - 정렬(`:114-115`): `label-` 세션의 미판정 항목이 맨 위, 세션 순서는 `label-1121-missed`, `label-1121-newbox`, `label-1121-team`, 그 밖은 이름순(`LABEL_ORDER`, `:9`), 세션 안은 번호순. 나머지는 영상이 있는 것, 사진이 있는 것, 없는 것 순, 그다음 급한 종류 순.
  - 세션 선택 목록도 `label-` 세션을 먼저 둡니다(`:42`).
  - 카드: 영상이 있으면 소리 없이 반복 재생, 사진은 누르면 새 창(`:63-72`). 급함·주의·참고 표시는 코칭 알림 종류에만, `label-` 세션에는 "먼저"(`:75-76`).
  - 판정 단추를 다시 누르면 판정이 지워집니다. 메모만 저장하려면 판정이 먼저 있어야 합니다(`:95`, `:100`).
  - 10초마다 목록을 다시 읽습니다. 입력 칸에 글을 쓰는 중이면 카드는 다시 그리지 않습니다(`:127`).
  - 위쪽 "도움이 된 비율"은 모든 종류(코칭 알림과 `label-` 세션)의 판정을 합친 비율입니다(`:28-31`).
- `label-` 세션의 세 단추 뜻은 세션마다 문장으로 다시 정의됩니다. 예: `label-1121-missed`는 "맞음 = 선수가 있고 상자가 없음, 틀림 = 선수가 없거나 이미 상자가 있음, 쓸모없음 = 판단하기 어려움"(저장소의 `alerts.jsonl` 2번째 줄).

## 5. 받아들임 기준
1. 판정을 저장하면 목록과 종류별 집계에 반영되고, 세션 안에서는 늦은 알림이 먼저입니다. (`test_alert_review.py::test_listing_marks_counts_and_the_newest_alert_of_a_session_first`)
2. 없는 알림이나 단어는 409로 거절하고, 파일 경로는 세션 폴더 밖으로 나가지 않습니다. (`test_unknown_alerts_and_labels_are_refused_and_images_stay_inside_the_session`)
3. 깨진 줄이 있어도 다른 알림의 번호는 바뀌지 않습니다. (`test_a_damaged_line_keeps_the_numbers_of_the_other_alerts`)
4. `/alerts`, `/alerts.js`, `/alerts.css`는 200입니다. (`test_the_pages_and_the_api_work_through_the_server`)
5. 상태 줄(`polarity: status`)은 목록에 나오지 않습니다. (`test_live_feedback.py` 계열, `wiki/live-service-audit.md` 10절. 이 경로 전용 시험은 확인하지 못함)
6. 항목이 300개를 넘으면 오래된 세션의 항목부터 응답에서 빠집니다. 시험 없음.
7. `label-` 세션의 미판정 항목은 화면 맨 위에 missed, newbox, team 순서로 보입니다. 파이썬 시험 없음(하위 작업의 `work/model-improve-1121/server-labels/sim_order.cjs`로 확인했다고 기록됨, 이 작업에서 다시 돌리지 않음).
8. `alerts_NNNN.mp4`가 있으면 카드에 영상이 나오고 `/alert-files`가 `video/mp4`로 줍니다. 시험 없음(커밋하지 않은 변경).

## 6. 겹치는 기능과 정리 방향
- 사람 판정 화면이 여러 갈래이고, `label-` 세션이 `/train`의 놓친 선수·팀 판정과 같은 질문을 다른 형식으로 받습니다: [overlaps.md](overlaps.md) O1, B부 질문 1, 3.
- 300개 제한을 서버가 먼저 적용하고 `label-` 우선 정렬은 화면이 나중에 합니다. 새 라이브 실행이 알림 169개 이상을 쓰면 `label-1121-missed`가 잘립니다(계산): O15, B부 질문 B1.
- 세션을 보관하면 벤치 정확도 문구에서 그 판정이 빠집니다: O15.
- 알림 파일 읽기와 세션 찾기 코드가 벤치와 복사되어 있습니다: O6, O8. A부에서 공통으로 뺍니다.

## 7. 알려진 문제와 고정값
- `MAX_ALERTS = 300`(`app/alert_review.py:18`), `LABEL_ORDER`의 세 세션 이름이 화면 코드에 박혀 있습니다(`web/alerts.js:9`). 다음 날짜의 `label-` 세션은 이름순으로만 정렬됩니다.
- 메모 200자, 판정 id 60자(`app/review_public.py:185-188`).
- 판정 파일의 임시 이름이 고정(`<id>.tmp`)입니다. 같은 프로세스 안의 잠금으로만 보호됩니다(`app/alert_review.py:120-124`).
- 커밋하지 않은 변경: `app/alert_review.py`(영상 칸), `app/review_public.py:398`(mp4 media type), `web/alerts.js`, `web/alerts.css`. 화면 파일은 운영 서버가 이 작업 폴더에서 바로 읽으므로 저장하는 즉시 운영에 보입니다. 파이썬 파일은 2026-11-20 밤에 고쳐졌고 운영 서버는 그 직후에 시작했으므로(파일 시각과 프로세스 시작 시각으로 확인) 이 변경도 이미 운영 중입니다. 커밋되지 않은 코드가 운영 중이라는 뜻입니다.
