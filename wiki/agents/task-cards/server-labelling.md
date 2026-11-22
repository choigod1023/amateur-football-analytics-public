# 작업 카드: 사용자님 손 판정 준비 (server-labelling, `/alerts`)

경로 (Git bash에 먼저 붙여 넣음):
```
R=<REPO_DIR>
W=<WORK_DIR>/work
PY=<WORK_DIR>/outputs/football-coach-server/.venv/Scripts/python.exe
STORE=$W/human-labels/public-own-match-review-20261111
SL=$W/model-improve-1121/server-labels
```

## 언제 쓰는가
사용자님께 맞음/틀림을 눌러 달라고 할 항목(놓친 선수, 새 상자, 팀 색, 장면 판정)을 검토 서버 `/alerts`에 올릴 때(`CLAUDE.md` 모델 역할 분담 절). 서버 구조는 `wiki/review-store-and-open-tasks.md`.

## 필요한 입력
- 세션 이름 `label-<MMDD>-<주제>`(영문 소문자와 숫자와 `-`, 40자 이하, `R/app/alert_review.py`의 `SESSION` 규칙).
- 항목마다 질문 한 줄, 맞음/틀림/쓸모없음의 뜻, 사진(`alerts_NNNN.jpg`) 또는 짧은 영상(`alerts_NNNN.mp4`), 원천(origin).
- 브리프의 저장소 쓰기 허락 한 줄. 없으면 4단계 전에 멈춥니다.

## 단계
1. 스테이징 폴더 `<작업폴더>/staging/<세션>/`에 만듭니다. 본보기: `$SL/build_sessions.py`. `alerts.jsonl` 0번 줄은 `{"time":0,"kind":"note","polarity":"status",...}`(번호를 1부터 세기 위한 줄), n번 줄 항목 = `alerts_000n.jpg`. 항목 필드: `time`(초), `kind`, `polarity`("neutral"), `title`(질문), `text`(맞음/틀림/쓸모없음의 뜻), `detail.line`("모델 쪽 후보, 사람 판정 아님"), `detail.origin`(L23).
2. `manifest.json`: 항목마다 `number`, `id`(`<세션>-<n>`), 반, 초, 좌표, `origin`, `image`. 본보기 `$SL/staging/manifest.json`.
3. 300개 확인(L11): 아래 명령으로 지금 합계를 내고, 새 항목 수를 더해 300 이하인지 적습니다. 넘으면 4단계로 가지 않고, 판정 끝난 오래된 세션(파일 시각이 오래된 순)을 `alerts/_archive-<YYYYMMDD>/`로 옮기는 목록을 보고합니다. 옮기기는 사용자님 승인 뒤에만, `alerts/labels/`는 건드리지 않고, `ARCHIVE_NOTE.md`(왜, 무엇을, 되돌리는 법)를 남깁니다(본보기 `$SL/ARCHIVE_NOTE.md`).
```
$PY -X utf8 - <<'EOF'
import json, pathlib
A = pathlib.Path('<WORK_DIR>/work/human-labels/public-own-match-review-20261111/alerts')
tot = 0
for d in sorted(A.iterdir()):
    f = d / 'alerts.jsonl'
    if not f.is_file(): continue
    n = sum(1 for l in f.open(encoding='utf-8') if l.strip() and json.loads(l).get('polarity') != 'status')
    tot += n; print(d.name, n)
print('total', tot, '/ 300')
EOF
```
4. 저장소 전후 목록: `$PY -X utf8 $SL/snapshot_store.py $STORE <작업폴더>/store_before.json`, 세션 폴더를 `$STORE/alerts/`로 복사, 다시 `store_after.json`. 바뀐 기존 파일 0개여야 합니다. 서버 재시작은 필요 없습니다(폴더만 추가하면 나타남).
5. 서버 확인: `$PY -X utf8 $SL/check_server.py <작업폴더>/list.json` → 세션별 개수와 합계. 화면 순서: `node $SL/sim_order.cjs <작업폴더>/list.json $R/web/alerts.js` → "index of first non-label"이 새 세션 항목 수 이상이어야 합니다.
6. 화면 순서(L10): `R/web/alerts.js`의 `LABEL_ORDER`는 label-1121 세 세션만 적혀 있어, 새 `label-` 세션은 그 셋의 미판정 항목 뒤, 코칭 알림 앞에 옵니다. 새 세션을 맨 위에 두려면 이 목록을 고치는 코드 작업이 따로 필요합니다(경기 없는 날, 별도 브리프).

## 숫자 기준
- 합계(상태 줄 제외) ≤ 300. 2026-11-21 현재 282개.
- 같은 편 후보가 20초 안에 겹치면 하나로 합침(L21).
- 한 세션은 사용자님이 한 번에 끝낼 수 있게 60개 이하(11-21 세 세션 15, 57, 60개).

## 필수 근거 (보고에 붙일 것)
- 3단계 출력 전체, `store_before/after` 비교 결과(바뀐 파일 0), `check_server.py` 출력, `sim_order.cjs`의 첫 5줄.
- 사진 1장 경로(질문과 표시가 한 장에 보이는지).

## 끝난 상태
`/alerts` 합계 ≤ 300, 새 세션이 코칭 알림보다 위에 보이고, 매니페스트와 아카이브 메모가 남아 있습니다. 사용자님께 알릴 문장(세션 이름, 개수, 질문 한 줄)을 보고에 넣습니다.

## 자주 틀리는 것
L10, L11, L21, L23.

## 권장 모델
Sonnet.
