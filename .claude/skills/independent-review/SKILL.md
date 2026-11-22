---
name: independent-review
description: Use when a sub-agent must review another sub-agent's output in the football match video project before it reaches the user - a coach video, the phone review page, a scene count, position metrics, a labelling session or a code or command report. Gives the eight mandatory checks (ball, stoppage, the judgement itself, caption timing, mark position, line assignment, numbers, commands) and the fixed finding table with severities. Use it whenever you are asked to "check", "verify" or "review" project output, because reviews that only checked mark positions missed wrong claims.
---

# 독립 검수 (하위 작업용, 권장 모델 Opus)

자세한 절차: `wiki/agents/task-cards/independent-review.md`. 만든 쪽 보고를 믿지 않고 원본(영상, 위치 기록, 파일)을 다시 봅니다. 대상 파일은 고치지 않습니다.

## 반드시 할 점검 (주장 하나마다, 통과/실패/확인 못 함)
1. 공: 앞뒤 1초 확대 사진에서 공 픽셀 위치. "공 가진, 공 쪽" 문구와 맞는가(L05, L08).
2. 정지: `work/match-1120/coach/hl/grid.py <1|2> <초>` 격자에서 쓰러짐, 심판 접근, 놓인 공(L01).
3. 판정 자체: 주장한 모양이 글로 된 숫자 기준에서 성립하는가. 기준이 없으면 그 자체가 지적(L04). "비어 있음"은 0명, 겹친 수비수 없음(L02, L03).
4. 자막 시점: 말하는 사건이 그 화면 구간 안에 있는가. 느린 화면은 원본 3초(L06).
5. 표시 위치: 정지 사진에서 원·화살표가 대상 위에 있는가(L12).
6. 분류와 문구: 장면의 주인공 줄 = 편 이름(L15), 코치 글에 개발 정보 없음(L24).
7. 숫자: 표본 크기와 출처 파일, 상대 골키퍼 섞임(L07), 사람 판정과 모델 값 분리(L23).
8. 명령: "확인했다"마다 실제 명령과 출력, 모의 실행은 따로(L19), 경로 존재(L18).

추가 점검: 문구는 소스가 아니라 렌더된 영상의 프레임에서 읽고 영상 수정 시각이 소스보다 뒤인지 본다(L27). 자막의 인원수는 멈춤 프레임에서 다시 센다(L26). 좋은 예는 결과가 이유를 보여 주는지 본다(L30). 마무리 할 일마다 근거 장면이 있는가(L29). 실제 속도 자막과 멈춤 자막이 같은 문장이면 지적(L28). 금지 문구는 지시문에 적힌 적용 범위 안에서만 판정한다(L31). 보고서 파일을 쓸 수 없을 수 있으니 사소 지적까지 답변 본문에 표로 적는다(L32). 수정과 검수가 3회 넘게 반복되면 장면 확인표 유무를 확인한다(L33).

장면이 10개를 넘으면 공·비어 있음·횟수 주장은 전부, 나머지는 무작위 5개. 본 수/전체 수를 적습니다.

## 지적 표 (고정)
| 번호 | 심각도 | 위치(파일, 초 또는 줄) | 무엇이 틀렸나 | 근거(사진 경로, 명령 출력) | 고칠 안 |
- 치명: 사실이 영상과 다름, 숫자 기준에서 판정이 뒤집힘, 틀린 수치가 코치에게 보임.
- 중요: 근거 없음, 자막과 화면 시점 불일치, 기준이 글로 없음, 편 분류 틀림.
- 사소: 말투, 글자 수, 색, 오타.
- 지적이 없으면 "본 항목 n개, 치명 0, 중요 0".

## 보고
점검 항목별 통과/실패 표 + 지적 표 + 사진 폴더 경로(예: `work/match-1120/coach/check/review-<YYYYMMDD>/`).
