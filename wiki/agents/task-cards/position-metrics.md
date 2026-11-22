# 작업 카드: 줄별 경기 전체 지표 (position-metrics)

경로 (Git bash에 먼저 붙여 넣음):
```
W=<WORK_DIR>/work
PM=$W/match-1120/position-metrics
PY=<WORK_DIR>/outputs/football-coach-server/.venv/Scripts/python.exe
```

## 언제 쓰는가
수비 줄, 미드필더, 공격의 경기 전체 수치(높이, 줄 간 간격, 구역 인원, 팀 길이)를 위치 기록으로 계산할 때. 포지션별 영상과 리뷰 페이지의 첫 그림이 여기서 나옵니다(L14). 어떤 지표를 볼지는 `wiki/research-position-metrics.md`, 11-20 결과는 이 공개본에 포함되지 않았습니다.

## 필요한 입력
- 위치 기록 `$W/match-<MMDD>/reanalysis/h1_match.jsonl`, `h2_match.jsonl`. 첫 줄 header(우리 팀 `team`, `direction`, `pitch_length` 89, `pitch_width` 62), 그다음 초마다 `team`/`other` = `[번호, x, y]`(미터). 원 기록의 x 부호는 반마다 다르므로 `features.py`의 `load()`를 거쳐 "우리 골라인 = -44.5"로 바꿔 씁니다.
- 킥오프 초(`features.py`의 `START`, 경기 C는 반별 영상 시작 초)와 골 초(`GOALS`).
- 경기 계획(라인업, 계획 자리 `PLAN_D`, `PLAN_A`): `$W/report-*/preview/`에서 찾음(L09).

## 단계
1. 새 경기면 `$PM`의 `features.py`, `analyze.py`, `figs.py`, `overlay.py`를 `$W/match-<MMDD>/position-metrics/`로 복사하고 `ROOT`, `START`, `GOALS`, `PLAN_D`, `PLAN_A`, 보정 경로(`overlay.py`의 `venue-1120`)를 그 경기 값으로 바꿉니다. 경기 이름을 인자로 받는 판은 없음, 새로 만들어야 함.
2. 계산: `cd <그 폴더> && $PY -X utf8 analyze.py` → `metrics.json`(지표마다 `trust`, `trust_reason`), `series.json`. 그림: `$PY -X utf8 figs.py` → `figs/*.png`.
3. 영상 겹침: `$PY -X utf8 overlay.py 전반 165` → `frames/ov_전반_165.jpg`(우리 연두 네모, 상대 빨강 네모, 뒤에 `X Y W H 배율`로 자르기). 지표마다 3개 초 이상 겹쳐 보고, 네모가 선수 발 위에 있는지, 가장 앞선 우리 점이 상대 골키퍼가 아닌지 봅니다(L07).
4. 지표마다 아래 신뢰 표시를 정하고 `findings.md`에 "쉬운 말 / 수치 / 신뢰 / 근거 그림 / 영상 확인 / 코치용 제안" 순서로 씁니다.

## 숫자 기준 (신뢰 표시)
| 검사 | 기준 |
|---|---|
| 10명 초 비교 | 우리 필드 점이 정확히 10개인 초만의 값과 전체 값 차이. 경기 C는 10명 초가 전체의 약 20% |
| 먼 쪽 보임 비교 | 먼 쪽 터치라인 쪽 점이 보인 초와 안 보인 초의 값 차이 |
| 표본 | 계산된 초가 100초 미만이면 쓰지 않음 |
| 폭 지표 | 먼 쪽이 4~5배 적게 잡혀(1,323 대 285) 폭은 "믿을 수 없음"(L02) |
| 가장 앞선 점 | 3단계에서 골키퍼가 1번이라도 나오면 공격수·박스 인원·팀 길이는 "믿을 수 없음"(L07) |
- 판정: 모든 검사 차이가 작으면 "믿을 만함", 일부 구간 차이면 "조건부", 대부분 차이면 "믿을 수 없음"(`analyze.py` 106~113줄 규칙). 코치 자료에는 "믿을 만함"만, "조건부"는 영상 확인이 붙은 것만 씁니다.
- 국면: 우리 필드 중심이 중앙선 앞이면 공격, 뒤면 수비(7초 중앙값). 공 위치가 없어 추정입니다. 공격 시간이 300초 미만이면 공격 지표에 "작아서 확정 못 함".

## 필수 근거 (보고에 붙일 것)
- 표: | 지표 | 전반 | 후반 | 표본(초) | 신뢰 | 겹침 사진 경로 |
- 빼낸 지표 목록과 이유 한 줄씩.

## 끝난 상태
`metrics.json`, `findings.md`, `figs/`, `frames/ov_*.jpg`가 그 경기 폴더에 있고, 코치 자료로 넘기는 지표는 모두 "믿을 만함" 또는 영상 확인된 "조건부"입니다.

## 자주 틀리는 것
L01(정지 구간 섞임), L02, L07, L09, L14, L17(다른 경기 보정을 그대로 씀).

## 권장 모델
계산 Sonnet. 수치를 코치 문장으로 바꾸는 해석 검토는 Opus.
