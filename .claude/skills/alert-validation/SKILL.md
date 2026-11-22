---
name: alert-validation
description: Use when judging how accurate the live coaching alerts are, tuning an alert threshold, or planning how to validate tactical advice for the football match video project (alert judgement counts, per-kind error rates, replay of stored tracks, public tracking data).
---

# 알림과 전술 조언 검증 절차 (이 프로젝트 전용)

1. `wiki/index.md`에서 `live-feedback.md`, `live-service-audit.md`, `validation-data-plan.md`를 읽습니다.
2. 사람 판정 집계: `outputs/football-coach-server/.venv/Scripts/python.exe -X utf8 scripts/tabulate_alert_labels.py`. 세션별과 종류별 틀림 비율을 95% 구간과 함께 냅니다. 종류별 판정이 20개 미만이면 참고용으로만 말합니다. 틀림과 쓸모없음을 모두 틀림으로 셉니다.
3. 임계값 시험: 저장된 추적(`work/tracks-ov3-20261113/h1_v3.json`, `h2_v3.json`)을 `app/live_feedback.py`의 `LiveAnalyzer`로 재생(`scripts/replay_live_feedback.py` 참고)하고, 판정된 알림 시각의 지표값(간격, 하락량)을 뽑아 맞음과 틀림의 값을 비교합니다. 같은 표본에서 고른 값은 낙관적이므로 새 판정으로 다시 확인해야 한다고 적습니다.
4. 알려진 결과: `gap_wide`는 기준 41m(전에는 32m), `line_drop`은 값이 겹쳐 임계값으로 못 나눔, 골키퍼 제외 규칙을 바꾸면 맞는 알림까지 사라짐(`wiki/live-feedback.md`).
5. 타당성(결과와의 관계)은 공개 추적 자료(Metrica 샘플, SkillCorner 공개 자료)로 알림 뒤 30초 안의 슛 비율을 평소와 비교합니다(`wiki/validation-data-plan.md`). 이용 조건은 `wiki/data-licenses.md` 5절. 연구 확인용으로만 쓰고 재배포하지 않습니다.
6. 코치에게 확신도를 보일 때는 "판정 n개 중 m개 맞음"처럼 사람 판정 집계만 씁니다. 임의의 퍼센트 확신도는 쓰지 않습니다.
7. 사람 판정은 정답이며 파일을 수정하지 않습니다. 사용자님의 판정 부담을 줄이는 방향으로 진행하고, 사람 확인은 오탐이 많아 보일 때와 표본 검수에만 요청합니다.
8. 끝나면 위키에 날짜와 표본 크기와 함께 기록합니다.
