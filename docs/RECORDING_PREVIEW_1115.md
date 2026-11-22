# 개선 버전 녹화 프리뷰

이 PC에서 http://127.0.0.1:8766/ 를 연다. 운영과 분리된 읽기 전용 프리뷰다. 기존 대시보드 UI를 사용한다. 영상은 직접 촬영한 경기 녹화의 1950~2010초 구간이고, 미니맵과 코칭은 해당 영상의 clean_candidate 관측값에 최신 위치 필터와 코칭 규칙을 적용한다. 새 GPU 추론이나 실시간 SRT 시험은 아니다.

15초·23초·35초 버튼으로 대상·행동·근거를 확인한다. 원본 비디오 태그에서 재생/정지/시간 이동을 지원한다. 영상 시간보다 뒤의 관측을 먼저 사용하지 않는다. 영상을 바꿀 때는 해당 영상에서 생성한 trace를 반드시 함께 지정해야 한다.

실행:
```powershell
../football-coach-server/.venv/Scripts/python.exe scripts/preview_recording.py --video ../../work/live-dashboard-validation-20261113/replay-1950-2010.mp4 --trace ../../work/minimap-tracking-validation-20261115/role/clean_candidate/observations.jsonl --port 8766
```

API 응답·비디오 Range 206·3개 코칭 장면을 확인했다. 현재 채팅 브라우저 연결을 사용할 수 없어 실제 화면 캡처 및 브라우저 육안 검증은 하지 못했다. localhost 전용이므로 다른 기기의 같은 주소에서는 접근할 수 없다. 방화벽이나 운영 서버를 변경하지 않았다. 원본 데이터나 사용자 분류 답을 쓰는 API는 제공하지 않는다.

이 프리뷰는 아직 승격되지 않은 후보 모델의 관측값을 포함한다. ID 단절·과다 탐지·좌표 오차가 남아 있으며 이 화면을 정확도 개선의 증거로 사용하면 안 된다. 전술적 정답도 미확정이다.
