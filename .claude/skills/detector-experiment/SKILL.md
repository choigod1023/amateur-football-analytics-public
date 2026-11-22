---
name: detector-experiment
description: Use when training, benchmarking or adopting a person detector, a pseudo-label or auto-label set, or an outside verifier model for the football match video project. Holds the fixed adoption criteria, the benchmark commands and the mistakes already made.
---

# 검출기 실험 절차 (이 프로젝트 전용)

1. 시작 전에 `wiki/index.md`와 `wiki/detector-experiments.md`(특히 "채택 기준" 절), `wiki/auto-labeller.md`, `wiki/data-licenses.md`를 읽습니다. 이미 실패한 방법을 반복하지 않습니다.
2. 기준 모델은 `work/detector-ft-20261112/ft_n2/best.pt`. 채택 기준은 결과를 보기 전에 정한 위키의 값을 그대로 쓰고 결과를 본 뒤에 바꾸지 않습니다.
3. 점수 측정 (모두 `outputs/football-coach-server/.venv`의 파이썬, 한글 문서는 `-X utf8`):
   - `scripts/bench_human_boxes.py` 사람이 확인한 상자 116개(신뢰도 0.25, 0.1)
   - `scripts/bench_false_boxes.py` 사람 아님 38개 재검출
   - `scripts/bench_human_cv.py <영상> <겹> <겹 수> <신뢰도> <모델...>` 시간 구간 교차 검증의 시험 쪽
   - 시험 구간 7개(사용자님이 그린 상자)는 편향 없는 유일한 기준입니다.
4. 학습 자료: `scripts/build_human_tiles.py`(사람 판정 상자, 겹 나눔), `build_auto_dataset.py`, `build_pseudo_tiles.py`. 학습은 `scripts/finetune_person_detector.py <yaml> <기반 모델> <출력> --epochs N`. 학습 중에는 GPU를 다른 작업과 나눠 쓰지 않습니다.
5. 학습과 벤치마크는 모두 `scripts/gpu_guard.py --name <실험> -- <명령>`으로 실행합니다(그래픽 메모리 8 GB 상한, 일반 메모리 90% 넘으면 중지, 동시 실행 거부). 처음에는 1 epoch나 작은 표본으로 메모리 최대값을 보고 batch를 정합니다. 기준은 `wiki/gpu-memory-rules.md`.

## 이미 겪은 함정
- 큰 모델(yolo11x)이 찾은 상자가 판정 상자의 대부분이라 그 모델의 영향을 받은 모델에 유리하게 편향됩니다. 학습에 쓴 장면과 시험 장면을 시간으로 분리합니다(120초 또는 5분 구간 묶음).
- 카메라 구간: cam1 약 0~1490초, cam2 약 1500~1730초(보정 없음, 제외), cam3 1740초 이후. `app/camera_segments.py`를 쓰고 직접 경계를 적지 않습니다.
- 자동 라벨(origin auto_labeller)은 사람 라벨과 섞지 않고, 사람 검수 30개 이상에서 정밀도 95% 미만이면 학습에 쓰지 않습니다. 같은 방식의 자가 학습은 1회차 이후 개선이 없었습니다.
- AI Hub 자료는 연구와 시험용만(문의하지 않기로 함). 섞어 학습하면 작은 선수(키 20픽셀 미만)를 잃습니다.
- 외부 검증 모델은 별도 환경 `work/verifier-20261117/venv`에서만 설치하고 운영 환경(`football-coach-server/.venv`)을 건드리지 않습니다.
- 모델 점수는 표본 크기(상자 수)와 함께 적고 사람 판정과 모델 값을 섞지 않습니다.

## 끝나면
`wiki/detector-experiments.md`에 날짜, 근거 파일, 표본 크기와 함께 결과를 추가하고 `wiki/index.md`를 갱신합니다. 푸시, 운영 서버 재시작, 워크트리 삭제는 사용자님께 먼저 묻습니다.
