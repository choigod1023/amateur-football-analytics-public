# 하위 작업 지시 구조 (브리프 아키텍처)

만든 날: 2026-11-21. 하위 모델은 추상적으로 구현하는 경향이 있으므로, 지시문은 주 세션이 구체적으로 써야 합니다.
주 세션(계획과 검토)은 하위 작업(Sonnet 기본, 판단은 Opus)에 지시문을 보낼 때 이 폴더의 조각을 조립합니다. 하위 작업은 지시문과 거기서 가리킨 카드만 보고 일할 수 있어야 합니다.

## 세 층
| 층 | 무엇 | 어디 | 누가 고치나 |
|---|---|---|---|
| 1. 지식 | 경기 사실, 실험 결과, 정정 기록 | `wiki/*.md` (목록은 `wiki/index.md`) | 작업을 끝낸 하위 작업 |
| 2. 되풀이 절차 | 작업 카드(단계, 명령, 숫자 기준, 끝난 상태)와 짧은 스킬, 교훈 장부 | `wiki/agents/task-cards/*.md`, `.claude/skills/*/SKILL.md`, [lessons.md](lessons.md) | 정정이 생길 때 하위 작업([maintenance.md](maintenance.md)) |
| 3. 브리프 | 한 작업만을 위한 지시문 | 주 세션이 Agent 호출의 prompt로 씀(파일로 남기지 않음) | 주 세션 |

브리프 = [brief-template.md](brief-template.md)의 틀 + 작업 카드 1~2장(경로로 가리킴) + 그 카드가 인용하는 교훈 번호 + 이 작업만의 값(초, 파일, 숫자 기준, 산출 파일 이름).
카드에 있는 일반 절차는 브리프에 다시 쓰지 않고 "카드의 3~5단계를 따름"처럼 가리킵니다. 브리프에는 카드가 비워 둔 값만 채웁니다.

## 작업 종류별 조립표
| 작업 종류 | 작업 카드 | 스킬 | 모델 | 검수 방법 |
|---|---|---|---|---|
| 한 순간을 영상으로 확인(공, 정지, 인원) | [scene-check](task-cards/scene-check.md) | `scene-verification` | Sonnet | 격자 사진 경로를 받아 두 번째 하위 작업(independent-review)이 1장 이상 다시 봄 |
| 여러 장면에서 모양 횟수 세기 | [scene-count](task-cards/scene-count.md) + scene-check | `scene-verification` | Sonnet(기준 정하기는 주 세션) | 장면별 표의 숫자를 검수 작업이 3장면 무작위로 다시 셈 |
| 코치용 전술 영상(Remotion) | [coach-video](task-cards/coach-video.md) + scene-check | `coach-video` | Sonnet 제작, Opus 검수 | `independent-review` 카드로 멈춤마다 정지 사진과 원본 격자 대조 |
| 휴대폰 리뷰 페이지(고정 형식) | [coach-report-page](task-cards/coach-report-page.md) | 없음(카드만) | Sonnet | 휴대폰 폭 캡처 1장 + independent-review |
| 줄별 경기 전체 지표 | [position-metrics](task-cards/position-metrics.md) | 없음(카드만) | Sonnet 계산, Opus 해석 검토 | 지표마다 신뢰 표시와 영상 겹침 사진 3장 확인 |
| 검출기·라벨 실험 | [detector-experiment](task-cards/detector-experiment.md) | `detector-experiment` | Sonnet, 채택 판단은 Opus | 채택 기준표 대비 수치, `runs.jsonl` 메모리 최대값 |
| 사용자님 손 판정 준비(`/alerts`) | [server-labelling](task-cards/server-labelling.md) | `server-labelling` | Sonnet | 서버 목록 확인 출력(맨 위 세션 이름, 합계 300 이하) |
| 다른 하위 작업 결과 검수 | [independent-review](task-cards/independent-review.md) | `independent-review` | Opus | 지적 표의 "치명" 0개, 엇갈리면 scene-check 하위 작업으로 재판정 |
| GPU를 쓰는 모든 명령 | [gpu-job](task-cards/gpu-job.md) | (각 작업 스킬이 가리킴) | Sonnet | `work/gpu-guard/runs.jsonl`의 그 작업 줄(exit, 최대 메모리) |

## 주 세션이 브리프를 보내기 전에
1. 위 표에서 작업 종류를 고르고 카드를 엽니다. 맞는 카드가 없으면 브리프 끝에 "카드 없음"이라고 적고, 작업이 끝난 뒤 카드를 새로 만드는 작업을 따로 보냅니다.
2. 카드의 "자주 틀리는 것"에 있는 교훈 번호를 브리프의 "하지 말 것"이나 "판정 기준"에 그대로 옮깁니다.
3. [brief-template.md](brief-template.md)의 구체성 점검표를 돌립니다. 하나라도 통과하지 못하면 보내지 않습니다.
4. 브리프를 쓰는 데는 `brief-writing` 스킬을 씁니다.

## 이 폴더의 페이지
- [brief-template.md](brief-template.md): 브리프 틀, 채운 예, 구체성 점검표
- [lessons.md](lessons.md): 교훈 장부(L01~)
- [maintenance.md](maintenance.md): 정정이 생겼을 때 장부와 카드를 고치는 순서
- `task-cards/`: 위 표의 카드 9장
