# 작업 카드: 검출기·라벨 실험 (detector-experiment)

경로 (Git bash에 먼저 붙여 넣음):
```
R=<REPO_DIR>
W=<WORK_DIR>/work
PY=<WORK_DIR>/outputs/football-coach-server/.venv/Scripts/python.exe
```

## 언제 쓰는가
선수 검출기 학습·벤치마크, 모델 예측 라벨이나 자동 라벨 세트, 외부 검증 모델을 시험할 때. 절차 본문은 프로젝트 스킬 `detector-experiment`(`$R/.claude/skills/detector-experiment/SKILL.md`)에 있고, 이 카드는 브리프에 채울 값만 정리합니다.

## 브리프에 반드시 적을 값
| 값 | 예 |
|---|---|
| 기준 모델 | `$W/detector-ft-20261112/ft_n2/best.pt` |
| 후보 모델 경로와 학습 자료 | yaml 경로, 기반 모델, 학습 장면의 시간 구간 |
| 채택 기준 | `wiki/detector-experiments.md` "채택 기준 (2026-11-17 확정)" 절 1)~5)를 그대로 옮김. 결과를 본 뒤 바꾸지 않음 |
| 시험 순서 | 아래 단계 번호 |
| GPU 예산 | gpu-job 카드: 그래픽 8 GB, 일반 12 GB, 한 번에 하나 |
| 작은 시험 먼저 | 1 epoch 또는 클립 2개로 `runs.jsonl` 최대값 확인 뒤 전체 |
| 산출 폴더 | `$W/<실험이름>-<YYYYMMDD>/` (새 폴더만) |

## 단계
1. `wiki/detector-experiments.md`, `wiki/auto-labeller.md`, `wiki/data-licenses.md`, `wiki/gpu-memory-rules.md`를 읽고, 같은 방법이 이미 실패했는지 한 줄로 보고합니다(예: "AI Hub 섞은 학습은 2026-11-16 실패").
2. 작은 시험: `$PY $R/scripts/gpu_guard.py --name <실험>-smoke -- $PY -X utf8 $R/scripts/finetune_person_detector.py <yaml> <기반 모델> <출력> --epochs 1`.
3. `$W/gpu-guard/runs.jsonl` 마지막 줄의 `peak_gpu_used_gb`, `peak_ram_percent`, `exit`를 읽고 batch를 정합니다.
4. 전체 학습을 같은 방식으로 실행합니다(gpu-job 카드).
5. 벤치마크(각각 gpu_guard로): `bench_human_boxes.py`(116개, 신뢰도 0.25와 0.1), `bench_false_boxes.py`(사람 아님 38개), `bench_drawn_boxes.py`(사용자님이 그린 34개, 시험 구간 7개가 편향 없는 유일한 기준). 모두 `$R/scripts/`.
6. 채택 기준표에 기준 모델과 후보의 값을 나란히 적고 기준마다 통과/실패/측정 못 함을 씁니다.

## 숫자 기준
- 채택 기준 1) 116개 중 66개 이상, 2) 사람 아님 재검출 22개 이하, 3) 시험 구간 7개 중 4개 아래로 안 떨어짐, 4) 학습에 안 쓴 새 판정 장면에서도 나쁘지 않음, 5) 라이브 재생에서 초당 B팀 인식 수가 줄지 않음.
- 한 라운드 개선이 상자 3개 미만이면 같은 방식을 반복하지 않습니다.
- 자동 라벨은 사람 검수 30개 이상에서 정밀도 95% 미만이면 학습에 쓰지 않습니다.

## 필수 근거 (보고에 붙일 것)
- 채택 기준표(기준마다 값, 표본 크기, 통과 여부), 각 벤치마크 결과 json 경로, `runs.jsonl`의 해당 줄(이름, 초, exit, 최대 메모리).

## 끝난 상태
결과가 `wiki/detector-experiments.md`에 날짜, 근거 파일, 표본 크기와 함께 추가되어 있고, 채택 판단은 "후보" 또는 "채택하지 않음"으로 적혀 있습니다(최종 채택은 주 세션과 사용자님).

## 자주 틀리는 것
L17(한 경기 값을 다른 카메라에 그대로 씀), L20(GPU 동시 실행), L23(자동 라벨을 사람 라벨과 섞음).

## 권장 모델
실행 Sonnet. 채택 여부 판단과 편향 해석은 Opus.
