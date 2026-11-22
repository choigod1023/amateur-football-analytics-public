# 끊긴 선수 재연결 질문 준비

기존 `/train`의 '가림 뒤 선수 재연결' 링크가 `/train/reappearance`로 연결된다. 이 페이지는 현재 `occlusion-reappearance` 범위의 질문을 읽으며 같은 선수·다른 선수·판단 어려움만 묻는다. 새 질문을 위해 팀/역할 답을 다시 받을 필요가 없다. 사진은 시간에 따라 사라지지 않는다.

## 기존 인터페이스

- `GET /api/v1/differences?scope=occlusion-reappearance`: 미답변 질문 목록. `include_answered=true`로 기존 답도 확인한다.
- `POST /api/v1/differences`: `{id, verdict: "same" | "different" | "unclear", note}`. 기존 답은 덮어쓰지 않으며 충돌 시 409다.
- `GET /difference-files/{name}`: 현재 queue에 등록된 영상·사진만 제공한다.
- `GET /api/v1/reappearance/decisions?source_sha256=...`: 해당 원본의 유효한 사람 답. `same`이어도 시간상 겹치는 경계는 연결하지 않는다.

장면 등록 HTTP API는 없다. `store/differences/queue.json`에 새 항목을 추가하고 같은 디렉터리에 미디어를 배치하면 서버는 다음 요청부터 읽는다. 서버 재시작이나 UI 변경은 필요하지 않다. 기존 항목의 내용은 fingerprint에 포함되므로 수정하지 않아야 한다.

## 이번 준비 도구

`scripts/prepare_dropout_review.py`는 선택된 실제 관측 경계에서 원본 앞뒤 2초를 잘라 전체 영상과 확대 영역을 함께 보여주는 MP4를 만든다. 두 끝점은 노란 상자와 6배 확대 JPG로 제공한다. 확대는 원본 픽셀의 표시 크기만 바꾸며 없던 인물 세부를 생성하지 않는다.

기존 질문과 같은 원본·유사 시각·같은 ID 또는 겹치는 상자라면 새 질문을 만들지 않는다. 답이 `unclear`인 경우도 자동으로 반복 요청하지 않는다. 한 번에 최대 3개가 기본이고 상한은 4개다. 입력 오류나 서로 너무 먼 끝점은 거절한다.

도구는 **게시하지 않고** `staged-publication.json`과 미디어만 새 출력 폴더에 쓴다. 원본 store의 모든 JSON 해시와 queue 해시가 그대로인지 검사한다. 게시자는 manifest의 `queue_sha256`가 현재 queue와 같은지 확인하고, 기존 항목을 유지한 채 `items`를 추가해야 한다. 파일 충돌 또는 queue 변경이 있으면 새 현재 상태에서 다시 준비한다. 사람 답을 자동으로 생성하지 않는다.

별도 `scripts/publish_dropout_review.py`는 기본적으로 읽기 전용 사전 검증만 한다. `--publish`를 명시하면 모든 기존 JSON·queue·미디어 해시를 검사하고, 고유 queue 백업과 배타적 미디어 파일을 생성한 뒤 queue를 원자적으로 교체한다. 기존 질문과 답은 수정하지 않는다. 협력적 게시 lock과 교체 직전 해시 검사를 사용한다. 다른 게시 프로그램이 같은 lock을 무시하면 완전한 동시 편집 배제를 보장하지 못하므로 여러 게시 작업을 동시에 실행하지 않는다.

```powershell
& ../football-coach-server/.venv/Scripts/python.exe scripts/publish_dropout_review.py `
  ../../work/dropout-review-20261114/staged `
  ../../work/human-labels/public-own-match-review-20261111
# 위 명령은 dry-run. 게시할 때만 --publish --report NEW_REPORT_PATH 를 추가한다.
```

```powershell
& ../football-coach-server/.venv/Scripts/python.exe scripts/prepare_dropout_review.py `
  ../../work/dropout-review-20261114/audit/candidates.json `
  ../../work/live-dashboard-validation-20261113/replay-1950-2010.mp4 `
  ../../work/human-labels/public-own-match-review-20261111 `
  ../../work/dropout-review-20261114/staged `
  ../../work/ffmpeg-local/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe
```

## 실행·검증

2026-11-14 실제 준비 결과: d0113(581→748), d0114(29→431), d0115(15→417), 기존 질문 중복 0개. 기존 답을 수정하지 않았다. 이 ID들은 준비 당시 queue 기준으로 할당되므로 게시 전 경합 검사가 필요하다.

각 MP4는 30fps, 4.6초/5.4초/5.2초이며 138/162/156프레임을 끝까지 디코딩했다. 끝점 확대 사진 6장을 직접 확인했다. 실제 사람이 상자에 있고 맥락이 보이지만 동일인 정답을 자동으로 확정하지 않았다. 단위 테스트 6개 통과: 시간 역전·상자 오류, 같은 경계 재질문 방지, 원본 분리, 답/미답변 상태 보존, 확대 영역과 먼 끝점 방어.

게시 도구 테스트 6개도 통과했다. dry-run 무변경, 기존 답·질문 보존, 백업 일치, queue/답/미디어 변경과 기존 목적 파일 거절, 동시 게시 lock을 검증했다. 실제 store 대상 dry-run은 1,199개 JSON 보존과 새 질문 3개 게시 가능 상태를 확인했다.

기존 다중 프레임 점수 모델에서 세 후보는 각각 0.853/0.867/0.674로 자동 승인 하한 0.9에 못 미쳤다. 마지막 후보는 전방 운동 잔차도 1.590으로 기존 제한 1.5를 넘었다. 점수는 동일인 확률이 아니며, 이 때문에 사람 확인 질문으로 남겼다. 같은 팀 답을 다시 요청하지 않는다.

실측 산출물은 프로젝트 `work/dropout-review-20261114/staged/`에 있다. 이 문서는 준비 상태를 설명하며 공개 게시 성공 여부는 부모 작업의 게시 검증 결과를 따른다. 운영 모델·서버·사용자 답은 이 준비 도구가 변경하지 않는다.
