# 로컬 연속 동영상 시험

로컬 전용 WHEP 실험은 기존 RTSP `127.0.0.1:18555/match`를 FFmpeg로 1920px H.264 baseline으로 별도 인코딩하고, MediaMTX WebRTC를 거쳐 `<video>`로 재생한다. 이 인코딩은 원본 해상도와 탐지 박스를 보존하지 않으며 영상과 분석이 프레임 단위로 동기화되지 않는다. 대시보드의 `탐지 상자 미리보기`를 선택하면 같은 분석 프레임의 박스가 표시되는 기존 JPEG로 전환하고 `연속 동영상 보기`로 돌아간다. 두 화면을 동시에 겹치지 않는다.

이 옵션은 `http://127.0.0.1` 대시보드에서만 시도하며, 실패·끊김에는 기존 JPEG로 돌아가 재시도한다. MediaMTX HTTP 18889, WebRTC UDP 18189와 RTSP 18557은 모두 `127.0.0.1`에만 바인딩하고 CORS는 `http://127.0.0.1:18081`만 허용한다. STUN/TURN과 방화벽 변경은 없다. 기존 SRT나 외부 평문 데모 설정을 수정하지 않는다. 다른 PC, 맥북의 HTTPS, 인증 프록시, iPhone, 실전 네트워크, 여러 뷰어와 전체 지연은 별도 설계 및 검증이 필요하다.

로컬 기존 시뮬레이션이 18555에서 송출 중인 경우, 실제 설치 경로로 `--mediamtx`와 `--ffmpeg`를 지정해 `python scripts/local_player_sidecar.py --mediamtx <경로> --ffmpeg <경로>`를 실행한다. 별도 인코딩은 CPU와 대역폭을 추가로 사용한다. 중지하면 브라우저는 프레임 미리보기로 복귀한다.

MediaMTX WHEP 실험에서 별도 로컬 경기 영상의 브라우저 `videoWidth=1920`, `videoHeight=296`, `readyState=4`와 재생 시간 증가를 확인했다. 실험용 정적 대시보드는 API가 없었으며, 전체 사용자 대시보드·맥북에서의 통합 검증과 정확한 프레임레이트 측정은 하지 않았다. [MediaMTX WHEP 문서](https://mediamtx.org/docs/read/webrtc)
