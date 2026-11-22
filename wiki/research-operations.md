# 연구 요약: 송출, 녹화, 리포트 운영

근거: `docs/` 아래 report-service, live-recording, live-bookmarks, srt-local, local-srt-decoder-audit-20261111, srt-holdout-preroll-20261111, labeled-srt-audit, local-webrtc-player, plaintext-demo, one-shot-transfer, preview-refresh, tracking-team-research-plan. 서버 접속 주소와 계정 정보는 의도적으로 적지 않았습니다.

## 리포트 서비스 (`/report`)
- 녹화 영상을 올리면 선수 탐지, 추적과 팀 분류, 리뷰 영상 제작(침투, 허용된 침투, 고립, 수비 라인 하락, 입력한 득점)을 거쳐 `review.mp4`, `review.md`, `events.json`을 만듭니다.
- 한계: 공 흐름 판정 없음, 득점 장면은 사용자가 득점 시각을 입력해야 만들어짐, 팀당 평균 9~10명만 보임. 상단에 작업기 상태와 남은 저장공간(20GB 미만이면 빨강)이 표시됩니다.
- 최신 보고서: `work/match-report-20261113e/` (35쪽 PDF, 팀 전술 6쪽 포함).

## 송출과 녹화
- 구성: iPhone(Moblin) SRT 송출, MediaMTX 수신(SRT는 UDP, RTSP는 로컬 전용), 분석 서버, 검수 서버. 기본값으로 암호화와 인증이 꺼져 있는 시제품 설정이므로 공개 배포 전에는 인증을 추가해야 합니다.
- 녹화: fMP4, 약 10분 세그먼트, 자동 삭제 없음(`recordDeleteAfter: 0s`), 기본 위치 `work/recordings/match/`. 읽기 전용 점검 `python -m app.recording_health --directory <폴더> --sample-seconds 5`. 파일 증가가 없다고 송출 종료를 뜻하지 않습니다. 전원이 갑자기 꺼지면 최근 데이터가 손실될 수 있습니다.
- 시험 결과: 로컬 SRT 경유 시 MediaMTX 읽기 큐가 작아서 프레임 40개를 버리는 문제가 확인됐고(`writeQueueSize` 8192로 경고는 사라졌으나 디코더 오류가 완전히 없어지지는 않음), SRT 경로 평가 12프레임에서 정답 매칭이 31~35%였습니다.
- 라이브 북마크: "현재 장면 표시"로 최근 프레임과 지표를 최대 20개까지 메모리에 저장합니다. 재시작하면 사라집니다.
- 대시보드 미리보기는 정지 이미지 최대 초당 약 8장(JPEG 960x540 이하, 장당 약 63KB)이고 연속 동영상이 아닙니다. WebRTC 연속 재생은 로컬 127.0.0.1 시험까지만 했습니다.
- 평문 공개 데모와 한시적 파일 수신기(8GiB 상한, 1회 수신 후 종료)는 사용자님이 명시적으로 선택한 시험용이며 개인 영상에는 쓰지 않습니다.

## 추적 유지 연구 계획에서 나온 점검 목록
- 원본 25fps SRT에서 처리가 느리면 최신 프레임만 남기고 중간 프레임을 버립니다(지연 누적을 막지만 움직임 예측에는 불리).
- 타일 검출 기본 confidence 0.35가 ByteTrack의 low 0.10과 high 0.25보다 높아 저신뢰 복구 단계의 입력이 미리 걸러집니다 ([research-detection-tracking.md](research-detection-tracking.md)).
- 영상이 불연속이면(건너뛰기, 반복) 추적기와 색 후보도 초기화해야 합니다.

## 지킬 점
- 서버 재시작 전에 송출과 녹화 상태를 확인하고 녹화 파일을 지우거나 덮어쓰지 않습니다.
- 평가 화면에 인증이 없는 시제품이라는 사실을 숨기지 않습니다. 공개 배포 전에는 인증을 추가해야 합니다.
- 코드 병합과 실제 배포는 별개로 확인합니다.
