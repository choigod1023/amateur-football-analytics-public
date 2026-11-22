# 위키 목차

규칙은 [WIKI.md](WIKI.md)에 있습니다. 마지막 갱신: 2026-11-22. 작업 전에 이 목차를 읽고 관련 페이지를 읽습니다.

## 현재 상태와 규칙
| 페이지 | 내용 |
|---|---|
| [match-1120-live-and-report.md](match-1120-live-and-report.md) | 경기 C(2026-11-20, 야간)의 기술 교훈: 라이브 문제와 원인(보정, 팀 색, 옷 색 30픽셀 제한, 시작 스크립트), 20픽셀 재분석, 알림 판정 집계, 코치 자료와 영상 제작 교훈, 정정에서 얻은 규칙 (2026-11-20 ~ 21). 경기 진행, 결과, 전술 평가는 공개본에서 제외 |
| [calibration-check-and-track-stitch.md](calibration-check-and-track-stitch.md) | 보정 자동 점검(선 일치 점수, 4픽셀 이상 이동 감지, 11월 20일 49장과 라이브 131장, 시작 구간 구도 변화 감지, 점과 발 어긋남 36곳)과 추적 번호 이어 붙이기(공백 1초 미만은 거의 맞고 3초까지는 개인 분석에 부적합) (2026-11-21) |
| [team-role-1120.md](team-role-1120.md) | 11월 20일 위치 기록의 우리 팀 점 458개 중 우리 필드 선수는 64%(상대 골키퍼 6%, 심판 8%, 상대 필드 9% 등 섞임, 임시 판정), 걸러내면 88%(잘못 뺀 우리 선수 17/291), 옷 색 최소 키는 현재 색 읽기로는 키가 커도 안 나아지고 조끼 색 픽셀 비율은 16픽셀부터 96% 이상, 정확히 10명인 초는 20%→23%뿐(못 잡은 선수가 원인), 전반 겹쳐 그리기 방향 부호 오류라는 주장은 2026-11-22에 정정(오류 아님), 전반 임시 정답은 시각 어긋남 가능성 주의 (2026-11-21, 주의 2026-11-22) |
| [team-role-exclusion-1122.md](team-role-exclusion-1122.md) | 11월 20일 우리 팀 점에서 상대 골키퍼 제외 규칙 A10(모델 판정 29점 중 27 제거, 우리 필드 0/291 제거, 독립 검증 제거 40점 중 골키퍼 39)과 지표별 판단(팀 길이만 조건부), 전반 기록이 영상보다 최대 1.7초 늦는 시각 어긋남 발견(후반은 0)과 보정, 심판 제외 조건(제외한 40점 중 심판 35, 우리 필드 4), 전반 394점 재판정(70점 바뀜)과 세 규칙 합산 효과(우리 팀 점 순도 약 69% → 89% 전반, 68% → 87% 후반), 실시간 기록은 영상과 시각이 맞으나 필드 선수 62%에만 점, 판정 세션 `label-1121-role` 전반 사진 44장 교체 (2026-11-22, 모델 판정) |
| [track-breaks-and-linking-1122.md](track-breaks-and-linking-1122.md) | 11월 20일 추적 번호 끊김의 원인(끝남 전반 1,065·후반 954, 10초 유지 시간은 원인 아님, 새 번호 311건은 예측 상자가 너비의 2.8배 벗어남)과 저장한 탐지로 한 연결 방식 시험(거리 연결 사전값은 사진 50개 중 20개가 다른 사람, 사후 값은 3개이나 후반 우리 팀 12명 이상 0.22 → 0.54, 팀 색 조건만 사용 가능), 옵션 이름 (2026-11-22, 사진 판정은 모델 판정) |
| [prematch-check-1122.md](prematch-check-1122.md) | 경기 전 자동 점검 시제품: 보정 점검 독립 표본 49장(오경보 0, 5픽셀 이동·1도 회전 49/49, 확대 1~2% 0/49 구멍, 4~25픽셀 이동 자동 보정 24/24), 11-20 라이브 첫 24초는 자동 보정 불가, 킥오프 대형 옷 색 학습(고정 색과 96~100% 일치, 정확도 83~84% 대 약 90%), 심판·골키퍼는 색으로 구분 불가, 고정값 59개 분류 (2026-11-22) |
| [stoppage-and-zone-count.md](stoppage-and-zone-count.md) | 경기 멈춤 구분(표본 174구간, 멈춤 25)과 박스 앞 구역 인원·거리 자동 계산: 멈춤 분류는 멈춤을 맞힌 비율 72%이지만 "멈춤" 판정의 정답률 49%이고 후반 520초 파울을 못 잡아 참고용, 박스 앞 구역만 후보 찾기용(판정 일치 8/14), 공 반대쪽 거리는 쓸 수 없음, 확인할 장면 후보 20개 (2026-11-21). 2026-11-22 재시험: 문턱을 고르지 않으면 균형 정확도 0.76, "멈춤" 판정 정답률 38%(앞의 49%는 낙관적), 새 신호 보강 실패(위치만으로는 구분 불가), 휘슬 소리 검출(멈춤 신호로는 약함, 킥오프와 종료 시각에는 쓸 만함) |
| [ball-1120-eval.md](ball-1120-eval.md) | 11월 20일 경기 공 위치 시험: 방법 4개와 시간 보정을 임시 판정 105장으로 평가(맞음 55%대, 공 없는데 답함 74%라 전술 분석에 쓸 수 없음), 정적 제거 버그와 경기장 안 거름 효과, 정지한 공 문제, 사용자님 확인 화면 (2026-11-21) |
| [research-position-metrics.md](research-position-metrics.md) | 포지션(줄)별로 볼 지표 조사: 수비 줄, 미드필더, 공격의 "꼭 볼 것" 표와 계산 방법, 문헌 기준(수비수 간격 6~8m, 줄 간 10~15m, 미드블록 27.2 x 40.1m), 공 기록이 없어 못 재는 것, 히트맵 읽는 법 (2026-11-21 웹 조사, 우리 영상으로 검증 전) |
| [hardcoded-values-audit.md](hardcoded-values-audit.md) | 고정값 전수 조사(59개 값, 위치와 줄, 왜 고정했나, 바꾸는 방법): 경기장·카메라 고정값은 경기장 설정 파일 한 곳으로, 경기별 값은 경기 설정 파일과 시작 거절 점검으로, 11월 20일 기준 우선 변경 10개와 설계안 (2026-11-21) |
| [pipeline-and-paths.md](pipeline-and-paths.md) | 분석 순서, 파일 위치, 구간 지정 형식, 측정된 사실 |
| [user-rules-and-pitfalls.md](user-rules-and-pitfalls.md) | 사용자 지시, 서버 운영 요령, 환경의 함정 |

## 하위 작업 지시 (브리프 아키텍처, 2026-11-21)
| 페이지 | 내용 |
|---|---|
| [agents/index.md](agents/index.md) | 세 층(위키, 작업 카드와 스킬, 브리프)과 작업 종류 → 카드 → 스킬 → 모델 → 검수 방법 표 |
| [agents/brief-template.md](agents/brief-template.md) | 모든 브리프의 11개 절 틀, 채운 예(후반 449초 장면 확인), 보내기 전 구체성 점검표 |
| [agents/lessons.md](agents/lessons.md) | 교훈 장부 L01~L33: 이미 틀린 일(파울을 전환으로, 먼 쪽 누락, 겹친 수비수, 눈대중 횟수, 공 없는 선수 표시, 자막 시점, 상대 골키퍼 섞임 등)과 확인 가능한 규칙, 인용 카드 |
| [agents/maintenance.md](agents/maintenance.md) | 사용자님 정정 뒤 장부와 카드를 고치는 순서, 브리프가 맞는 카드를 인용했는지 점검 |
| [agents/task-cards/scene-check.md](agents/task-cards/scene-check.md) | 한 순간을 영상으로 확인: 시간 기준 파일, `hl/grid.py` 격자(±4초), 공·정지·비어 있음 기준, 결과 표 |
| [agents/task-cards/scene-count.md](agents/task-cards/scene-count.md) | 여러 장면 횟수 세기: 글로 된 숫자 기준, `zones.py` 구역 선, 장면별 표, 문제 예와 잘한 예 비교 |
| [agents/task-cards/coach-video.md](agents/task-cards/coach-video.md) | Remotion 전술 영상: 클립 시간, 픽셀 좌표, 렌더·정지 사진·접촉 시트 명령, 자막 규칙 |
| [agents/task-cards/coach-report-page.md](agents/task-cards/coach-report-page.md) | 휴대폰 리뷰 페이지 고정 형식(`build_page.py`, `boards.py`), 휴대폰 폭 캡처, Artifact 게시 |
| [agents/task-cards/position-metrics.md](agents/task-cards/position-metrics.md) | 줄별 경기 전체 지표 계산(`features.py`, `analyze.py`)과 신뢰 표시, 영상 겹침(`overlay.py`) |
| [agents/task-cards/detector-experiment.md](agents/task-cards/detector-experiment.md) | 검출기 실험 브리프에 채울 값(기준 모델, 채택 기준 1~5, 작은 시험 먼저) |
| [agents/task-cards/server-labelling.md](agents/task-cards/server-labelling.md) | `/alerts` 손 판정 세션 형식, 300개 합계 계산 명령, 보관 이동 규칙, 서버 확인 도구 |
| [agents/task-cards/independent-review.md](agents/task-cards/independent-review.md) | 검수 점검 8개(공, 정지, 판정 자체, 자막 시점 등)와 심각도가 있는 지적 표 |
| [agents/task-cards/gpu-job.md](agents/task-cards/gpu-job.md) | `gpu_guard.py` 사용, 한 번에 하나, Git bash 경로, 메모리 예산과 종료 코드 |
| [review-store-and-open-tasks.md](review-store-and-open-tasks.md) | 검토 서버와 라벨 저장소, 원칙, 남은 일 |

## 검토 서버 기능 명세 (2026-11-21)
| 페이지 | 내용 |
|---|---|
| [features/index.md](features/index.md) | 검토 서버 경로 전수 조사(등록 100개, 열 수 있는 주소 137개, 송출 상태 서버 3개)와 기능별 명세 13쪽의 목차. `label-` 판정 묶음이 벤치의 "라이브 실행"으로 잡히는 문제 발견 |
| [features/routes.csv](features/routes.csv) | 경로 141줄 표: 정의 위치, 읽고 쓰는 자료, 보호, 부르는 화면, 시험, 쓰임 여부 |
| [features/overlaps.md](features/overlaps.md) | 겹치는 기능 15가지(판정 화면 갈래, 파일 경로 11개, 상태 표시 기준, 세션 고르기 규칙, 300개 제한과 보관이 벤치 정확도를 바꾸는 문제 등)와 권고 |
| [features/refactor-plan.md](features/refactor-plan.md) | 정리 계획: A부 동작 변화 없는 19단계(별도 작업 폴더, 0단계 특성 시험), B부 사용자님 결정 질문 9개, 위험 |

## 현재 경기에서 한 일 (2026-11-16 기준)
| 페이지 | 내용 |
|---|---|
| [goalkeeper-rule.md](goalkeeper-rule.md) | 골키퍼를 라인 계산에서 빼는 규칙과 효과 |
| [detector-experiments.md](detector-experiments.md) | 선수 검출기 비교(사용자님이 그린 상자 기준), 모델 예측 라벨 방식, person-check1 판정, 먼 쪽 작은 선수 설정 비교(현재 63개, 입력 1280 73, 먼 쪽 띠 1024 추가 73·잃은 것 0, 1280 + 띠 78, 라이브 재생 검증 결과: 절반 정밀도 + 띠 0.13~0.15초로 예산 안, 현재 설정은 0.17~0.20초로 5~42% 초과), 띠 상자 오탐 거르기(점수 0.25), 저장한 원본 탐지, 사람 확인 자료만의 재학습(어려운 상자 41 → 59, 채택 보류), 11-20 그리기 장면 20개 등록) (2026-11-22) |
| [live-feedback.md](live-feedback.md) | 실시간 코칭 분석 구조, 한계, 알림 판정 집계 |

## 라이브 운영과 학습 계획 (2026-11-16 작업)
| 페이지 | 내용 |
|---|---|
| [live-service-audit.md](live-service-audit.md) | 라이브 서비스 심층 점검, 위험표, 먼저 고칠 것 |
| [coach-operating-guide.md](coach-operating-guide.md) | 코치용 운영 안내서, 모델별 신뢰도, 알림 문구 점검 |
| [aihub-training-plan.md](aihub-training-plan.md) | AI Hub 자료로 검출기를 학습하는 계획과 측정값 |
| [calibration-automation.md](calibration-automation.md) | 카메라 구도 자동 구분과 이동 측정 결과, 보정 자동화 설계 |
| [live-startup-and-halftime.md](live-startup-and-halftime.md) | 공격 방향과 팀 색 자동 확인, 하프타임 요약, 상대 팀 패턴 설계 |
| [startup-check.md](startup-check.md) | 경기 전 시작 점검 도구(입력, 사람 수, 팀 색 사진, 공격 방향 제안, 보정 이동)와 시험 결과 |
| [tracking-reid-and-metrics.md](tracking-reid-and-metrics.md) | 추적 끊김 측정, re-ID 검토, IDF1과 HOTA 도입 계획 |
| [gap-link-experiment.md](gap-link-experiment.md) | 긴 공백 조각 연결 실험 (연결의 약 40%가 틀려 자동 채택 안 함) |
| [auto-labeller.md](auto-labeller.md) | 자동 라벨러: 두 검출기 의견이 갈린 상자를 자동 판정, 교차검증 결과와 한계 |
| [data-licenses.md](data-licenses.md) | 자료와 모델 이용 조건(AI Hub, YOLO, SoccerNet 등), 서비스화 전 조치 |
| [shooting-and-streaming-guide.md](shooting-and-streaming-guide.md) | 우리 영상의 한계(측정), 휴대폰 촬영과 SRT 송출 안내, 사용자님 아이디어 검토 |
| [bench-screen.md](bench-screen.md) | 코치용 벤치 화면 최소판 사용법, 우선순위 색, 한계 |
| [outage-halftime-service.md](outage-halftime-service.md) | 라이브 중단 감시(빨간 띠, 소리, 중단 기록)와 하프타임 보고서 자동 생성, 합성 장애 시험, 외부 알림 선택지 (2026-11-18) |
| [live-operations-research.md](live-operations-research.md) | 현장 실시간 운영 요구사항, 격차 분석, 로드맵, 현장 시험 계획 |
| [verifier-models.md](verifier-models.md) | 외부 검증 모델(Grounding DINO, OWLv2)로 사람 판정을 자동화하는 시험 (2026-11-17) |
| [validation-data-plan.md](validation-data-plan.md) | 알림과 전술 조언의 타당성 검증: 모을 자료, 학습, 검증 단계 (2026-11-17 제안) |
| [level-tactics-research.md](level-tactics-research.md) | 수준별(프로~아마추어) 전술 연구와 공개 자료 조사, 아마추어 근거는 약함 (2026-11-17) |
| [set-pieces.md](set-pieces.md) | 세트피스 박스 안 인원과 슛의 관계(프로 20경기), 우리 경기에서 찾을 수 있는지 (2026-11-17) |
| [formation-matchups.md](formation-matchups.md) | 포메이션 짝과 슛의 관계(프로 20경기): 유의한 짝 없음, 수비 라인 높이는 관련 (2026-11-17) |
| [moblin-field-test-plan.md](moblin-field-test-plan.md) | Moblin(아이폰)으로 송출할 때 실제 화질을 재고 설정을 정하는 시험 계획과 비교 도구 |
| [srt-degradation-test-1118.md](srt-degradation-test-1118.md) | 공개 아마추어 영상 2개로 한 SRT 송출 열화 시험(비트레이트, 해상도, 손실, 지연)과 결과 |
| [e2e-latency-1118.md](e2e-latency-1118.md) | 종단 지연(R5) 첫 측정: 사건 시각부터 벤치 화면 API까지 단계별 지연(처리 경로 1.0~2.5초, 알림 조건 시간 제외)과 합격 기준 비교 (2026-11-18) |
| [hard-frames.md](hard-frames.md) | 놓친 장면 자동 수집(`--collect-hard-frames`): 의심 규칙별 재현율(표본 70프레임), 저장 형식과 상한, 사용자님 판정 표본 40장 (2026-11-18) |
| [stream-diagnosis.md](stream-diagnosis.md) | 송출 상태 진단 화면(실제 비트레이트, 화면 수, 끊김을 읽어 초록·노랑·빨강으로 안내)과 합성 송출 시험 (2026-11-18) |
| [recorded-stream-analysis-1118.md](recorded-stream-analysis-1118.md) | 경기 한 건의 실제 송출 녹화 9개의 비트레이트와 끊김 분석: 30fps 5Mbps는 안정, 60fps 12Mbps는 끊김, 12에서 6Mbps로 하락, 3분 41초 공백 (2026-11-18) |
| [gpu-memory-rules.md](gpu-memory-rules.md) | GPU 작업 세 개 동시 실행으로 그래픽·일반 메모리가 바닥나 멈춘 일(2026-11-20, 전력·열은 정상)과 학습·평가 메모리 규칙, 감시 도구 `scripts/gpu_guard.py` |
| [module-scorecard.md](module-scorecard.md) | 모듈별 정확도 점수표(검출, 추적, 보정, 알림 등)와 보정 미터 오차 측정, 못 잰 것 목록 (2026-11-18) |
| [public-amateur-videos.md](public-amateur-videos.md) | 공개된 아마추어 경기 영상 검색과 시험용 3개(드론 2, 방송 1), 우리 카메라와 다른 점 |
| [team-select.md](team-select.md) | 경기마다 우리 팀 색 고르기(`/team-select`), 색 가정이 박힌 곳 목록, 프로필 정확도와 합성 조끼 시험, 후반 재확인 연결, 경기 후 분석과 보고서 연결(6절)과 프로필 대 모델 비교 (2026-11-18) |

## 이전 연구 요약 (`docs/`의 56개 문서, 다른 영상 위주)
| 페이지 | 내용 |
|---|---|
| [research-detection-tracking.md](research-detection-tracking.md) | 검출, 추적, 가림, 야간 |
| [research-calibration.md](research-calibration.md) | 경기장 보정과 자동 보정 실험 |
| [research-team-and-roles.md](research-team-and-roles.md) | 팀 구분, 심판과 골키퍼, 포지션 |
| [research-player-identity-and-labelling.md](research-player-identity-and-labelling.md) | 선수 확인, 사람 검토 화면 |
| [research-tactics-and-ball.md](research-tactics-and-ball.md) | 실시간 알림 규칙, 팀 모양, 공 |
| [research-operations.md](research-operations.md) | 송출, 녹화, 리포트 서비스 |
| [research-index.md](research-index.md) | 56개 문서와 위키 페이지의 대응표 |

## 2026-11-18 경기 현장 기록
| [match-1118-venue-and-report.md](match-1118-venue-and-report.md) | 경기 B(2026-11-18) 현장 적용 교훈: 새 카메라 보정(cam4), 조끼 색 규칙, 벤치 영상과 미니맵 수정, 녹화본 재분석 보고서 만들기 |
| [detailed-report-research-1118.md](detailed-report-research-1118.md) | 상세 보고서용 지표, 움직임 종류, 이동 벡터 방법 조사와 시제품 |
| [analyst-tags.md](analyst-tags.md) | 분석가 표시 도구(/tag), 표시로 클립과 전후반 자르기, 장면은 영상 사진으로 확인하는 규칙과 근거 (2026-11-19) |
