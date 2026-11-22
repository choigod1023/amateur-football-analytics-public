---
name: brief-writing
description: Use in the main (planning and review) session of the football match video project every time you are about to hand work to a sub-agent or parallel session (Sonnet or Opus) - scene checks, scene counts, coach videos, the phone review page, position metrics, detector runs, /alerts labelling, reviews, GPU jobs. Assembles the brief from wiki/agents (template, task cards, lesson ids) and runs the concreteness checklist before sending. Use it even for small delegated fixes, because lower models implement vague instructions abstractly.
---

# 하위 작업 브리프 쓰기 (주 세션용)

하위 모델은 지시가 추상적이면 추상적으로 구현합니다. 그래서 주 세션이 경로, 초, 숫자 기준, 통과 조건까지 정해서 보냅니다. 구조 설명은 `wiki/agents/index.md`.

## 조립 순서
1. `wiki/agents/index.md`의 작업 종류표에서 카드와 모델을 고릅니다. 카드가 없으면 브리프 끝에 "카드 없음"을 적고, 끝난 뒤 카드 만들기 작업을 따로 보냅니다.
2. `wiki/agents/brief-template.md`의 11개 절을 순서대로 채웁니다. 카드에 있는 일반 절차는 옮겨 적지 않고 "카드 3~5단계를 따름"처럼 가리킵니다.
3. 카드의 "자주 틀리는 것" 교훈 번호를 `wiki/agents/lessons.md`에서 찾아, 번호와 규칙 한 줄을 "하지 말 것"이나 "판정 기준"에 넣습니다.
4. 이 작업만의 값을 채웁니다: 절대 경로, 시간 기준 파일과 경기 시계 식, 좌표 단위, 숫자 기준, 산출 파일 이름, 멈춤 조건.
5. 사용자님께 보일 산출물이면 independent-review 브리프를 다음 단계로 계획에 넣습니다.

## 구체성 점검표 (하나라도 실패면 보내지 않음)
- [ ] 두 가지로 읽힐 명사("그 장면", "측면", "문제 구간", "공 쪽")가 경로, 숫자, 초, 예시로 바뀌었다.
- [ ] "확인한다"마다 무엇으로(명령, 사진) 보고 무엇이면 통과인지 같은 문장에 있다.
- [ ] 세는 것마다 구역(m), 순간(초), 세는 법, 경계 처리가 적혀 있다(L04).
- [ ] 자막, 라벨, 문구에는 좋은 예 1개와 나쁜 예 1개가 있다.
- [ ] 시청자나 사용자님이 실제로 볼 것(파일, 몇 초, 어떤 글자)을 한 줄로 적었다.
- [ ] 모든 경로가 절대 경로다. 처음 쓰는 경로는 하위 작업에 `ls` 확인을 1단계로 시켰다(L18).
- [ ] 보고 형식 6열(한 일, 근거 파일, 수치와 표본, 확인한 것, 확인 못 한 것, 불확실한 사실)과 멈춤 조건이 있다.
- [ ] 금지: 커밋, 푸시, 운영 서버 재시작, 내려받기, 설치. GPU를 쓰면 gpu-job 카드.

## 모델 고르기
- Sonnet: 구현, 렌더, 사진 추출, 세기, 계산, 서버 세션 만들기.
- Opus: 다른 작업 결과 검수, 기준이나 설계 선택, 두 하위 작업 판정이 엇갈릴 때.
- Fable 모델은 하위 작업에 쓰지 않습니다(`CLAUDE.md`).

## 보고를 받은 뒤
- 보고 표에 근거 경로와 표본 크기가 없으면 사용자님께 넘기지 않고 같은 작업에 보충을 요청합니다.
- 의심스러운 사실은 직접 보지 않고 scene-check 또는 independent-review 브리프를 새로 보냅니다.
- 사용자님 정정이 오면 `wiki/agents/maintenance.md`대로 유지보수 브리프를 보냅니다.
