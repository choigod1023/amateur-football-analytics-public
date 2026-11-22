---
name: server-labelling
description: Use when preparing anything the user must judge by hand on the review server's /alerts page for the football match video project - missed-player checks, new detector boxes, team colour checks, scene judgements - as a label-<MMDD>-<topic> session, or when archiving old alert sessions to make room. Holds the session file format, the 300-item cap check, the ordering rule and the read-only server checks. Use it before copying any folder into the review store.
---

# `/alerts` 손 판정 세션 준비 (하위 작업용)

자세한 절차와 명령: `wiki/agents/task-cards/server-labelling.md`. 서버 구조: `wiki/review-store-and-open-tasks.md`.

## 위치
- 저장소: `<WORK_DIR>/work/human-labels/public-own-match-review-20261111/alerts/`
- 본보기와 도구: `work/model-improve-1121/server-labels/`(`build_sessions.py`, `staging/manifest.json`, `snapshot_store.py`, `check_server.py`, `sim_order.cjs`, `ARCHIVE_NOTE.md`).

## 반드시 할 확인
1. 세션 이름 `label-<MMDD>-<주제>`. `alerts.jsonl` 0번 줄은 `polarity: "status"` 안내 줄, n번 줄 = `alerts_000n.jpg`(또는 `.mp4`).
2. 항목마다 `detail.origin`과 "모델 쪽 후보, 사람 판정 아님" 문구(L23). 질문 한 줄과 맞음/틀림/쓸모없음의 뜻을 `text`에.
3. 300개 상한(L11): 카드의 계산 명령으로 지금 합계(상태 줄 제외) + 새 항목 ≤ 300인지 적습니다. 넘으면 복사하지 않고 보관 이동 목록을 보고합니다. 이동은 사용자님 승인 뒤, `alerts/labels/`는 그대로, `ARCHIVE_NOTE.md`에 되돌리는 법.
4. 같은 편 후보가 20초 안이면 합칩니다(L21). 한 세션 60개 이하.
5. 저장소 복사 전후 `snapshot_store.py`로 목록을 남겨 기존 파일 변경 0개를 보입니다. 브리프에 저장소 쓰기 허락이 없으면 복사하지 않습니다.
6. 순서(L10): `check_server.py <list.json>` 뒤 `node sim_order.cjs <list.json> <REPO_DIR>/web/alerts.js`에서 새 세션이 코칭 알림보다 앞인지 봅니다. `web/alerts.js`의 `LABEL_ORDER`에 없는 새 세션은 label-1121 세션들 뒤에 옵니다. 맨 위로 올리려면 코드 작업이 따로 필요하다고 보고합니다.
7. 운영 서버 재시작, 커밋, 푸시는 하지 않습니다(폴더 추가만으로 나타남).

## 보고
| 한 일 | 근거 파일 | 수치와 표본 크기 | 확인한 것 | 확인 못 한 것 | 불확실한 사실 |
- 합계 계산 출력, 스냅샷 비교 결과, `check_server.py`와 `sim_order.cjs` 출력 첫 5줄, 사용자님께 보낼 안내 문장(세션 이름, 개수, 질문).
