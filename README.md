# Amateur football analytics (public copy)

휴대폰 한 대로 찍은 아마추어 축구 경기 영상에서 선수 위치를 읽어 코치용 전술 분석을 만드는 연구용 시제품입니다.
선수 검출(YOLO), 추적(ByteTrack), 경기장 보정, 옷 색 기반 팀 구분을 거쳐 수비 줄, 간격, 박스 공격 같은 전술 지표를 계산합니다.
경기 중에는 SRT로 받은 영상을 실시간으로 분석해 알림을 만들고, 경기 후에는 장면 설명이 붙은 보고서와 영상을 만듭니다.
검토 서버(FastAPI)에서 사람이 장면을 확인하고 라벨을 달 수 있으며, 사람의 판정과 모델의 값은 따로 저장합니다.

> **공개용 사본 안내.** 이 저장소는 분석 코드와 방법, 실험 기록을 담고 있습니다. 실제 경기의 영상, 위치 기록, 사람의 라벨, 선수 정보, 경기별 보고서는 포함하지 않습니다. 문서에 남은 수치는 방법의 평가를 위한 익명 수치이며, 경기는 "경기 A/B/C"나 날짜로만 가리킵니다. 개인 정보(선수와 코치 이름, 팀과 경기장 이름)와 서버 주소, 내부 운영 문서는 제거했고 현재 상태만 내보냈습니다(과거 기록 없음). 문서 속 `<SERVER_HOST>`, `<LAN_HOST>`, `<WORK_DIR>` 같은 표기는 자리 표시입니다. 모델 가중치와 경기장 보정 파일도 포함하지 않으므로 실행하려면 자신의 영상과 설정이 필요합니다. 라인업과 보고서 문장은 예시(일반 4-4-2, "예시 문장")로 바꿔 두었습니다. 검토 서버는 인증이 없는 시제품이라 공개 배포 전에는 인증을 추가해야 합니다.

> **서버 주의.** 이 코드의 검토 서버는 시제품이며 인증이 없습니다. 인터넷에 직접 노출하지 말고, 사설 망이나 인증이 있는 프록시 뒤에서만 실행하십시오.

*English summary: a research prototype that turns single-phone amateur football match video into player positions and coaching analysis (detection, tracking, pitch calibration, team split, tactical metrics, live alerts, post-match reports). This is a sanitized public copy: it contains code, methods and experiment notes only, and no real match video, position logs, human labels, player information or per-match reports; numbers left in the docs are anonymous method-evaluation figures; names, server addresses and internal ops notes are removed; you need your own video, model weights and configuration to run it. The review server has no authentication and must not be exposed to the internet as is.*

아마추어 축구 경기를 휴대폰 한 대로 촬영해 분석하고, 코치에게 경기 중 조언과 경기 후 보고서를 제공하는 시스템입니다. 선수 검출(YOLO), 추적(ByteTrack), 경기장 보정(호모그래피), 팀 구분(옷 색), 전술 지표(수비 줄, 간격, 공간 점유, 전환)를 하나의 흐름으로 묶었습니다.

이 저장소는 연구용 시제품입니다. 모든 수치에는 근거 파일과 표본 크기가 있고, 사람이 확인하지 않은 결과는 사실로 단정하지 않습니다. 자세한 실험 기록은 [`wiki/index.md`](wiki/index.md)에 있습니다.

## 1. 전체 구조

```
휴대폰(Moblin) ──SRT──▶ MediaMTX ──RTSP──┬─▶ 녹화 루프(10분 조각, 재인코딩 없음)
                                          └─▶ 실시간 분석(검출 → 추적 → 보정 → 팀 구분 → 지표 → 알림)
                                                         │
               검토 서버(app/review_public.py) ◀─────────┘
               /bench 코치 화면 · /live 영상 · /tag 분석가 표시 · /halftime · /shots · /team-select

경기 후: 녹화 → 위치 기록(positions.jsonl) → 지표 계산 → 보고서(HTML/PDF/HWPX) → 영상으로 장면 확인
```

| 단계 | 하는 일 | 주요 파일 |
|---|---|---|
| 입력 | 휴대폰 SRT 송출 수신, 녹화 | `app/plaintext_demo.py`, `configs/mediamtx-srt-local.yml`, `scripts/record_stream_loop.ps1` |
| 검출 | 사람 상자 찾기(타일 384px, 입력 768px) | `scripts/run_live_feedback.py`, `scripts/finetune_person_detector.py` |
| 추적 | 프레임 사이 같은 사람 잇기 | `app/track_vote.py`(ByteTrack 설정) |
| 보정 | 화면 좌표를 경기장 미터로 변환 | `app/pitch_map.py`, `app/camera_guard.py` |
| 팀 구분 | 우리 팀, 상대, 심판, 관중 | `app/team_role_infer.py`, `app/team_color_profile.py` |
| 지표와 알림 | 수비 줄, 간격, 박스 공격 등 | `app/live_feedback.py`, `app/tactical_feedback.py` |
| 보고서 | 경기 후 분석 문서 | `scripts/build_detailed_report.py`, `scripts/build_player_cards.py`, `scripts/build_kordoc_report.py` |
| 분석가 도구 | 경기 중 버튼 표시, 클립 자르기 | `app/analyst_tags.py`, `app/tag_clips.py`, `scripts/cut_halves_from_tags.py` |

## 2. 경기 날 사용법

```powershell
# 1) 컴퓨터를 켜면 검토 서버는 예약 작업(<SCHEDULED_TASK>)으로 자동 시작됩니다.
# 2) 송출 수신과 녹화를 켭니다(이미 켜져 있으면 건너뜀).
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_match_day.ps1
# 3) 경기 후 분석가 표시로 전반과 후반 영상을 킥오프부터 자릅니다.
python scripts\cut_halves_from_tags.py --store <검토 저장소> --day 2026-11-20 --out-dir halves --small
```

- 휴대폰: `/tag`(분석가 표시), `/bench`(코치 화면), `/live`(영상)
- 보고서에 장면 설명을 쓰기 전에 `scripts/scene_check_frames.py`로 영상 사진을 만들어 확인합니다. 추적 결과만으로 쓴 장면 설명이 영상과 맞지 않은 사례가 있었습니다([`wiki/analyst-tags.md`](wiki/analyst-tags.md)).
- 서버 API와 설정 항목은 [`docs/server-api.md`](docs/server-api.md)에 있습니다.

## 3. 사용한 모델

판정 기준은 사람이 그린 상자 34개(그중 시험 구간 7개), 사람이 "사람"으로 판정한 상자 116개, "사람 아님"으로 판정한 상자 38개입니다. 상자는 IoU 0.3 이상이면 찾은 것으로 셉니다. 자세한 내용은 [`wiki/detector-experiments.md`](wiki/detector-experiments.md)와 [`wiki/module-scorecard.md`](wiki/module-scorecard.md)에 있습니다.

| 모델 | 용도와 학습 방법 | 평가 결과 (표본) | 상태 |
|---|---|---|---|
| YOLO11n | 기본 사람 검출기(conf 0.35, 입력 640) | 116개 중 46, 시험 7개 중 2 | 운영 서버 |
| ft_n2 | YOLO11n을 우리 경기 타일(학습 171, 검증 186, 384px)로 미세조정 | 116개 중 56, 시험 7개 중 4, 사람 아님 38개 중 22를 다시 검출 | 분석 기준 모델 |
| auto_only | ft_n2를 자동 라벨 타일 3,570개로 20 에폭 추가 학습 | 116개 중 76, 시험 7개 중 5 | 보류(라이브 재생 결과가 섞임) |
| AI Hub 혼합 | AI Hub 타일 13,440개로 추가 학습 | AI Hub 검증 mAP50 0.983, 우리 영상 116개 중 38 | 탈락(작은 선수를 놓침, 이용 조건상 연구용) |
| 팀·역할 분류기 | MLP(은닉 24, dropout 0.2, 500 에폭, 시드 3개 평균). 입력은 색상 구간 12개, 형광·어두움·옅음 비율, 채도·명도, 상자 모양 | 장면 하나씩 빼는 검증 정확도 0.919(상자 732개), 따로 둔 136개도 0.919. 심판 재현율 0.76 | 운영(한 경기 안에서만 잰 값) |
| 팀 색 프로필 | 학습 없음. Lab 색 공간에서 2개 묶음으로 나누고 코치가 우리 팀을 고름(`/team-select`) | 이 경기 상자 531개 중 82.5% 맞음 | 새 유니폼용 대체 경로 |
| 공 후보 재순위 | 32px 패치 CNN과 표 특징 14개를 합친 MLP. 사람이 찍은 공에서 6px 안 후보를 정답으로 학습, 경기 조각 단위 5겹 교차검증 | 야간 경기 정밀도 약 93%, 재현율 약 40%. 새 경기장(cam4) 정밀도 71%, 재현율 35% | 야간 모델 사용, cam4는 실험 |
| 자동 라벨러 | 판정 상자 105개로 학습한 로지스틱 회귀(검출 점수, 모양, 색, 선명도, resnet18 특징 PCA 6개) | 시간 구간별 교차검증 AUC 0.93 | 연구용. 자동 라벨은 `origin: auto_labeller`로 따로 두고 사람 검수 30개 이상, 정밀도 95% 이상일 때만 사용 |
| Grounding DINO, OWLv2 | 학습 없는 외부 검증 모델(사람 판정 자동화 시험) | 같은 120개 상자에서 OWLv2 AUC 0.97, GDINO 0.93 | 실험 |

## 4. 수식과 알고리즘

### 경기장 보정 (`app/pitch_map.py`)
화면의 점 $(u, v)$를 경기장의 점 $(X, Y)$로 보내는 호모그래피 $H$를 기준점(4개 이상)으로 맞춥니다. $h_{33}=1$로 두고 점마다 두 줄의 식을 세워 최소제곱으로 풉니다(DLT 방식).

$$
\begin{bmatrix} u & v & 1 & 0 & 0 & 0 & -uX & -vX \\ 0 & 0 & 0 & u & v & 1 & -uY & -vY \end{bmatrix}\mathbf{h} = \begin{bmatrix} X \\ Y \end{bmatrix}
$$

선수 위치는 상자 아래쪽 가운데(발 위치)를 변환합니다. 맞춘 점 안의 오차(RMS)가 5m를 넘으면 보정을 거부하고, 경기장 밖 2m를 넘는 점은 버립니다. 실측 오차는 cam1 0.67m, cam3 0.96m입니다.

### 팀 구분 규칙
- 형광 비율: 색상 22~44, 채도 90 초과, 명도 110 초과인 화소의 비율
- 어두움 비율: 명도 70 미만인 화소의 비율
- 경기장마다 조끼 색이 다르면 색상 구간을 바꿉니다(2026-11-18 경기장은 30~70, 비율 0.22 이상이면 형광 팀).
- 한 추적 번호에 표가 3개 이상 모이면 다수결로 팀을 정합니다.

### 추적 (ByteTrack, `app/track_vote.py`)
칼만 필터로 다음 위치를 예측하고, 헝가리안 알고리즘으로 예측 상자와 검출 상자를 IoU 기준으로 짝짓습니다. 점수가 높은 상자와 낮은 상자를 두 단계로 연결합니다. 설정은 high 0.3(라이브 0.12), low 0.05(라이브 0.06), match 0.98, buffer 50입니다.

### 팀 모양 지표 (`scripts/build_detailed_report.py`)
- 골키퍼 규칙: 가장 깊은 선수가 자기 골라인 14m 안이고, 골라인 6m 안이거나 다음 선수보다 3m 이상 뒤면 골키퍼로 봅니다.
- 수비 줄 = 가장 깊은 3명의 평균, 공격 줄 = 가장 앞선 2명의 평균, 중원 = 나머지의 평균
- 팀 길이 = 공격 줄 − 수비 줄, 팀 폭 = 옆 위치의 90백분위 − 10백분위
- 길(레인): 폭 62m를 ±6.2m, ±18.6m 경계로 다섯 칸(양쪽 측면, 양쪽 하프스페이스, 가운데)으로 나눕니다.

### 박스와 마지막 3분의 1 진입
2초 전에 경계 밖 3m 이상에 있던 선수가 지금 안에 있으면 진입으로 셉니다. 박스 깊이는 다음과 같습니다.

$$
d_{\text{box}} = \min\left(u - \left(\tfrac{L}{2} - 16.5\right),\; 20.15 - |v|\right)
$$

8초, 8m 안의 중복은 하나로 합치고, 8초 안에 이어진 진입은 한 번의 공격(웨이브)으로 묶습니다.

### 공간 점유 (보로노이)
경기장을 2m 칸으로 나누고, 각 칸을 가장 가까운 선수의 팀이 차지한 것으로 봅니다. 두 팀이 모두 8~12명 보일 때만 계산합니다.

$$
\text{owner}(c) = \text{team}\left(\arg\min_{p} \lVert c - x_p \rVert\right)
$$

### 기타 지표
- 맞붙은 지점: 상대 선수와 4m 안으로 가까워진 두 선수의 중간점을 8m 칸에 모읍니다.
- 전환: 팀 중심(앞뒤 ±3초 평균)이 +5m 밖에서 −5m 안쪽으로(또는 반대로) 25초 안에 넘어가면 한 번으로 셉니다.
- 사이드 체인지: 상대 진영 선수들의 평균 옆 위치가 앞선 6초 평균보다 15m 이상 바뀌면 한 번으로 셉니다(10초 간격).
- 면적: 필드 선수 위치의 볼록 껍질(monotone chain) 넓이
- 자리(슬롯): 한 순간 필드 선수가 10명 이상이면 깊이 순서로 수비 3, 중원 4, 공격 3으로 나누고 옆 위치로 왼쪽과 오른쪽을 정합니다. 선수 개인이 아니라 자리의 평균입니다.
- 활동량: 같은 번호의 4초 동안 이동 거리 ÷ 4(초속 7m 초과는 버림). 같은 경기 안에서만 비교합니다.

### 기대 득점 xG (`app/xg.py`, 검증 안 됨)

$$
p(\text{goal}) = \frac{1}{1 + e^{-(A + B\,d + C\,\theta)}},\quad \theta = \operatorname{atan2}\!\left(7.32\,d_x,\; d_x^2 + d_y^2 - 3.66^2\right)
$$

$A=-2.319$, $B=-0.066$, $C=1.743$이며, $d$는 골대까지 거리, $\theta$는 슛 위치에서 두 골대 기둥이 이루는 각입니다. 공개 자료로 손으로 맞춘 값이라 비교용으로만 씁니다.

### 실시간 알림 규칙 (`app/live_feedback.py`)
| 알림 | 조건 | 다시 울리기까지 |
|---|---|---|
| 박스 공격 | 우리 선수 3명 이상이 박스 안에 2초 연속 | 20초 |
| 고립 | 팀 중심이 상대 진영이고 맨 앞 선수가 동료와 12m 넘게 6초 | 45초 |
| 상대 수비 줄 하락 | 상대 수비 줄이 10초 안에 14m 이상 내려감 | 90초 |
| 줄 간격 넓음 | 공격 줄 − 수비 줄 > 41m가 5초(기본은 꺼짐) | 90초 |

사람 판정 61개 기준으로 틀린 비율은 26%입니다. 박스 공격은 19개 중 1개, 줄 간격은 15개 중 6개, 수비 줄 하락은 9개 중 5개가 틀렸습니다.

## 5. 평가 원칙
- 사람이 직접 판정한 라벨이 정답입니다. 모델의 예측과 자동 라벨은 따로 보관하고 섞지 않습니다.
- 교차검증은 같은 장면이나 같은 경기 조각이 학습과 시험에 함께 들어가지 않도록 묶음 단위로 나눕니다(데이터 누수 방지).
- 모델 교체는 사람이 그린 상자 시험에서 나아질 때만 후보로 삼습니다. 고정된 채택 기준은 `.claude/skills/detector-experiment`에 있습니다.
- AI Hub 자료로 학습한 모델은 연구와 시험용으로만 씁니다([`wiki/data-licenses.md`](wiki/data-licenses.md)).
- 보고서의 장면 설명은 영상 사진으로 확인한 것만 씁니다.

## 6. 폴더 안내

| 폴더 | 내용 |
|---|---|
| `app/` | 서버와 핵심 모듈(FastAPI). `main.py`는 분석 서버, `review_public.py`는 검토·코치 화면 서버 |
| `scripts/` | 명령줄 도구 다수. `train_*`, `finetune_*` 학습 / `bench_*`, `evaluate_*` 평가 / `build_*_report` 보고서 / `run_live_feedback.py` 실시간 분석 / `*.ps1` 운영 |
| `web/` | 화면(HTML, JS, CSS) |
| `tests/` | pytest 시험 |
| `wiki/` | 현재 상태와 실험 기록. 작업 전에 `wiki/index.md`를 읽고, 끝나면 갱신합니다 |
| `docs/` | 이전 연구 메모와 서버 API 설명 |
| `configs/` | MediaMTX 등 설정 |
| `.claude/skills/` | 반복 작업 절차 7개(알림 검증 `alert-validation`, 하위 작업 지시문 `brief-writing`, 코치 영상 `coach-video`, 검출기 실험 `detector-experiment`, 독립 검토 `independent-review`, 장면 확인 `scene-verification`, 서버 라벨링 `server-labelling`) |

저장소 밖에 두는 것(커밋하지 않음):
- `../../work/`: 모델 가중치, 사람 라벨 저장소, 검출 캐시, 추적 결과, 보고서
- `../football-coach-server/recordings/`: 경기 녹화
- 영상(`*.mp4`), 가중치(`*.pt`), 인증서와 키(`*.key`, `*.crt`)는 `.gitignore`로 막습니다.

## 7. 브랜치와 병합 규칙

작업은 목적별 브랜치로 나누고, 작업마다 별도 작업 폴더를 씁니다. 다음 규칙을 따릅니다.

1. `main`은 경기 날 그대로 실행할 수 있는 상태만 둡니다.
2. 작업 브랜치는 `<도구>/<주제>-<YYYYMMDD>`로 만듭니다. 예: `<도구>/analyst-tags-20261120`
3. 한 브랜치는 한 가지 목적만 다룹니다. 코드를 고치는 작업은 동시에 하나만 두고, 같은 파일을 두 작업이 함께 고치지 않습니다(위키 페이지도 같음).
4. 병합 전 조건:
   - `python -m pytest -q`가 통과해야 합니다.
   - 새 지표나 모델은 위키에 날짜, 근거 파일, 표본 크기를 적어야 합니다.
   - 송출과 녹화 코드를 바꿨다면 합성 송출 시험(`tests/*smoke*`)을 돌려야 합니다.
5. 병합은 GitHub 풀 리퀘스트로 하고, 커밋을 하나로 합치지 않고 기록을 남깁니다.
6. 푸시, 운영 서버 재시작, 워크트리 삭제는 저장소 주인의 승인을 받고 합니다.
7. 병합이 끝난 브랜치와 워크트리는 정리합니다. 실험이 실패한 브랜치도 위키에 결과를 남긴 뒤 지웁니다.
8. 경기 날에는 송출, 녹화, 운영 서버 코드를 바꾸지 않습니다.

## 8. 설치

Windows 11, Ryzen 7 7800X3D, RTX 5070 12GB, Python 3.14에서 확인했습니다. 운영 가상환경은 `../football-coach-server/.venv`(PyTorch, ultralytics 8.4, lap)에 있습니다. 설치 명령과 서버 설정은 [`docs/server-api.md`](docs/server-api.md)를 보십시오.

## 9. 한계
- 공을 안정적으로 따라가지 못합니다. 그래서 슛, 패스, 소유는 사람 표시(`/tag`, `/shots`)에 의존합니다.
- 상대 선수가 10명 중 5~7명만 잡히는 경기가 있습니다. 이런 경기에서는 공간 점유 지표를 쓰지 않습니다.
- 우리 팀으로 잡힌 점에 심판이나 교체 선수가 섞여 한 순간 평균 13개가 됩니다(필드 선수 10명).
- 추적 번호가 바뀌면 한 사람의 움직임처럼 보이는 가짜 경로가 생깁니다. 장면은 영상으로 확인합니다.
- 수치는 한 경기나 두 경기에서 잰 값이 많아서 다른 경기장과 카메라에서 다시 확인해야 합니다.

## 10. 사용권

License: AGPL-3.0-or-later. 탐지에는 Ultralytics(AGPL-3.0)를 사용합니다. 전문은 [`LICENSE`](LICENSE)에 있습니다. Copyright (C) the project authors.
