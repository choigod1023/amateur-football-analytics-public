# 작업 카드: 휴대폰 리뷰 페이지 (coach-report-page)

경로 (Git bash에 먼저 붙여 넣음):
```
W=<WORK_DIR>/work
PY=<WORK_DIR>/outputs/football-coach-server/.venv/Scripts/python.exe
EDGE="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
```

## 언제 쓰는가
경기 리뷰를 코치와 사용자님께 보낼 때. 사용자님이 2026-11-21에 이 형식을 고정했습니다("항상 이 형식으로"). 기준 페이지: 코치용 휴대폰 페이지(비공개). PDF나 여러 쪽 보고서는 사용자님이 요청할 때만 만듭니다.

## 고정 형식 (위에서 아래 순서)
1. 점수 머리(두 팀 이름, 점수, 결과 한 줄).
2. 경기 수치표 1개(골, 슛, 유효슈팅, 상대 박스까지 간 공격, 상대 진영 시간 등 7줄 안팎, 우리:상대).
3. 요약 칩 3개.
4. 생각 하나당 카드 1장, 4~6장. 카드 = 태그 칩(`수비 · 문제` 등, 좋음은 초록 `good`, 문제는 빨강 `bad`) + 질문 한 줄 + 답(120자 이하) + 전술판 2장 나란히("오늘" / "이렇게") + "다음엔" 한 문장(60자 이하) + 접힌 실제 영상 사진 1장(경기 평균 그림이면 없음).
5. "다음 경기에서 할 일" 3개 안팎, 각 한 줄.
6. 각주 한 문단(노란 점선 = 제안, 이름은 프리뷰 자리 기준).

## 필요한 입력
- 경기 계획과 라인업: `$W/report-*/preview/`와 경기 계획 문서에서 먼저 찾음(L09).
- 카드마다 scene-check 카드로 확인된 장면(반, 초, `result.md`)과 숫자 1개(있으면).
- 위치 기록 `$W/match-<MMDD>/reanalysis/h1_match.jsonl`, `h2_match.jsonl`.

## 단계
1. 새 경기 폴더 `$W/match-<MMDD>/coach/`에 `$W/match-1120/coach/build_page.py`와 `boards.py`를 복사합니다. 두 파일은 11-20 경로·초·이름이 박혀 있습니다(`O`, `W`, `d1`, `d2`, 장면 초). 경기 이름 옵션이 있는 일반 빌더는 없음, 새로 만들어야 함.
2. `boards.py`에서 카드마다 "오늘" 판(그 초의 실제 위치, 필요한 선수만 이름표, 나머지 흐린 점)과 "이렇게" 판(노란 점선 = 프리뷰 계획에 맞춘 제안)을 만듭니다. 실행: `$PY -X utf8 $W/match-<MMDD>/coach/boards.py` → `coach/boards/*.png`.
3. `build_page.py`의 `CARDS`(tag, state, q, a, boards, nxt, video, vcap)와 수치표, 할 일, 각주를 고칩니다. 실행하면 `coach/page_<MMDD>.html`이 생깁니다(그림은 base64로 들어감, 16 MB 이하).
4. 휴대폰 폭 캡처: `"$EDGE" --headless=new --disable-gpu --hide-scrollbars --window-size=390,7000 --screenshot=$W/match-<MMDD>/coach/check/shot_page.png file:///<WORK_DIR>/work/match-<MMDD>/coach/page_<MMDD>.html`. 가로 스크롤이 없고 두 판이 위아래로 쌓이는지 봅니다.
5. 게시: Artifact 도구로 `page_<MMDD>.html`을 게시하고 URL을 보고합니다. 이미 게시한 페이지를 고칠 때는 그 URL을 먼저 `read`한 뒤 같은 URL로 게시합니다.

## 숫자 기준과 문구 규칙
- 카드 한 장에 숫자 1개까지. 미터, 검출 수, 신뢰도, "추정" 표시 없음(L24). 확인한 사실은 단정해서 씀(L25).
- 카드의 장면 문장은 모두 scene-check 판정 "맞음"인 것만. "비어 있음"은 L02·L03, "공 가진"은 L05 확인 뒤.
- 공격수 자리, 박스 안 인원 숫자는 L07 확인(골키퍼 섞임) 전에는 쓰지 않음.
- 카드 주제와 태그 줄이 같아야 함(공격수 문제는 `공격` 태그, L15).
- 좋은 답 예: "상대 1번이 측면에서 공을 잡았고, 우리 수비수가 바로 앞에서 1대1로 막고 있었습니다." 나쁜 예: "수비 집중력이 부족했습니다."(볼 것이 없음)

## 필수 근거 (보고에 붙일 것)
- 게시 URL, html 경로와 크기(MB), 휴대폰 캡처 경로.
- 표: | 카드 | 장면(반, 초) | scene-check result.md 경로 | 쓴 숫자와 출처 |

## 끝난 상태
게시 URL이 열리고, 카드마다 확인 근거 경로가 보고에 있으며, 휴대폰 캡처에서 가로 스크롤이 없습니다.

## 자주 틀리는 것
L01, L02, L03, L05, L07, L09, L15, L24, L25.

## 권장 모델
Sonnet 제작. 게시 전 independent-review(Opus) 한 번.
