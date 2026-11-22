# 작업 카드: GPU를 쓰는 명령 (gpu-job)

경로 (Git bash에 먼저 붙여 넣음):
```
R=<REPO_DIR>
W=<WORK_DIR>/work
PY=<WORK_DIR>/outputs/football-coach-server/.venv/Scripts/python.exe
GITBASH="C:/Program Files/Git/bin/bash.exe"
```

## 언제 쓰는가
학습, 평가, 추론, NVENC 인코딩처럼 GPU를 쓰는 모든 명령. 2026-11-20에 GPU 작업 세 개를 동시에 돌려 그래픽 메모리 99%, 일반 메모리 99.7%가 차서 컴퓨터가 5분 멈췄습니다(`wiki/gpu-memory-rules.md`). Remotion 렌더와 ffmpeg CPU 인코딩, 사진 추출은 해당하지 않습니다.

## 필요한 입력
- 작업 이름(`--name`, 예 `ball1120-methods`)과 실행할 명령.
- 오늘이 경기 날인지. 경기 2시간 전부터 끝날 때까지는 GPU 작업을 하지 않습니다.

## 단계
1. 사전 점검만: `$PY $R/scripts/gpu_guard.py --check`. 거부 이유(다른 작업이 돎 = `$W/gpu-guard/running.lock`의 pid가 살아 있음, 라이브 분석 `run_live_feedback`이 돎, 빈 그래픽 메모리 8 GB 미만, 빈 일반 메모리 12 GB 미만)가 나오면 실행하지 않고 보고합니다.
2. 작은 시험: 클립 2개 또는 1 epoch로 `$PY $R/scripts/gpu_guard.py --name <이름>-smoke -- $PY -X utf8 <스크립트> <인자>`.
3. `tail -1 $W/gpu-guard/runs.jsonl`에서 `exit`, `stopped`, `peak_gpu_used_gb`, `peak_ram_percent`, `peak_job_rss_gb`를 읽습니다.
4. 전체 실행: 같은 형식, `--name <이름>`. 오래 걸리면 백그라운드로 돌리고 끝날 때까지 다른 GPU 작업을 시작하지 않습니다.
5. 셸 스크립트를 감쌀 때는 `$PY $R/scripts/gpu_guard.py --name <이름> -- "$GITBASH" <스크립트.sh>`. `bash`만 쓰면 WSL bash가 잡혀 실패합니다(L13: `share-encode-1120` 첫 실행 4초, exit 1).

## 숫자 기준
| 항목 | 값 |
|---|---|
| 동시 실행 | 1개(잠금 파일로 거부, 종료 코드 98) |
| 시작 조건 | 빈 그래픽 메모리 8 GB, 빈 일반 메모리 12 GB(`--vram-need`, `--ram-need` 기본값) |
| 작업 상한 | 파이썬 작업은 그래픽 메모리 8 GB(`--vram-cap`, `run_capped.py`가 적용). 명령 첫 단어가 `python...`일 때만 적용 |
| 강제 중지 | 일반 메모리 90% 또는 그래픽 메모리 95%를 2번 연속(2초 간격) 넘음 → 종료 코드 99 |
| 배치 | 추론 4~8, YOLO 추론은 `half=True`(fp16). YOLO 학습은 `cache=False`, `workers=2`로 시작 |
- 중지되면 기준(`--ram-kill`, `--vram-kill`)을 올리지 않고 배치 크기나 한 번에 읽는 자료를 줄여 2단계부터 다시 합니다.
- `--allow-live`는 쓰지 않습니다.

## 필수 근거 (보고에 붙일 것)
- `runs.jsonl`에서 이 작업의 줄 전체(작은 시험과 전체 실행 각각).
- 종료 코드와 그 뜻(0 정상, 98 시작 거부, 99 감시 중지, 그 밖은 작업 자체 오류).

## 끝난 상태
작업이 종료 코드 0으로 끝났고, 위키에 결과를 적을 때 최대 메모리(그래픽 GB, 일반 %)가 함께 적혀 있습니다(`CLAUDE.md` GPU 절).

## 자주 틀리는 것
L13(WSL bash), L19(모의 점검만 하고 돌렸다고 보고), L20(동시 실행).

## 권장 모델
Sonnet.
