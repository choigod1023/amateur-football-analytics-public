# 일회성 공개 영상 평문 시험

## 아이폰 셀룰러 송출 옵션

평문 무인증 시험 사용을 위한 `scripts/start_cellular_demo.ps1`은 `-BindIP`로 서버 LAN 주소를 받습니다. SRT 게시와 읽기 전용 HTTP의 모든 출발지를 허용합니다. RTSP는 로컬 전용입니다. SRT와 HTTP는 인증과 암호화가 없어 다른 사람도 게시를 시도하고 영상을 볼 수 있습니다. 이 옵션으로 실제 개인 영상은 보호되지 않습니다. 서버 LAN 주소가 변하면 다시 설정해야 합니다. 이 스크립트는 자동 시작을 등록하지 않으며 서버는 수동 실행해야 합니다.

Windows의 `scripts/demo_firewall.ps1 -Action AllowCellular -PeerFile <맥북 IP 파일>`은 MediaMTX UDP 8890 규칙의 출발지를 전체로, `-Action AllowViewers`는 TCP HTTP 8443 규칙의 출발지를 전체로 변경합니다. 각 동작은 관리자 권한이 필요합니다. `-Action CheckCellular`와 `-Action CheckViewers`는 변경 없이 사전 확인합니다. 별도의 iPhone 셀룰러 실측 송출은 아직 검증되지 않았습니다.

`app.plaintext_demo`는 사용자가 명시적으로 선택한 공개 데모 영상만을 위한 시험 경로입니다. SRT 영상과 HTTP는 평문이며 제3자가 읽거나 변조할 수 있습니다. 비밀번호와 인증 토큰이 없고 단일 송출지 IP 제한은 신원 확인이나 도청 방지가 아닙니다. 같은 공인 IP를 공유하는 다른 기기에서도 접근할 수 있고 네트워크 환경에 따라 출발지가 바뀔 수 있습니다. 사용자 경기 영상이나 개인정보에 사용하지 마세요. 일반 운영용이 아니며 시험 후 즉시 수신기와 규칙을 제거해야 합니다.

별도 프로세스 환경변수 `DEMO_BIND_IP`와 `DEMO_SOURCE_IP`에 각 단일 IPv4를 지정한 뒤 `python -m app.plaintext_demo srt` 또는 `gateway`를 실행합니다. SRT는 UDP 8890, 경로 `publish:match`를 사용하며 암호구가 없습니다. RTSP는 loopback 18554, FastAPI는 loopback 8000에 있어야 합니다. HTTP gateway는 TCP 8443에서 허용된 출발지에만 GET status·analysis·frame.jpg를 내보냅니다. 프로세스는 공개 준비가 완료될 때까지 loopback에서만 시험해야 합니다. 프로그램은 방화벽이나 공유기를 변경하지 않습니다.

HTTP 포트는 8443이어도 TLS가 아닙니다. 직접 브라우저에서 HTTPS 페이지가 이 HTTP 엔드포인트를 호출하면 혼합 콘텐츠 차단 등이 발생할 수 있습니다. 맥북 측 로컬 Python 프록시가 원격 HTTP를 읽고 사용자 브라우저에 localhost로 전달하는 구성을 따로 시험해야 합니다. `/frame.jpg`는 최대 2,000,000바이트이고 `Cache-Control: no-store`, `X-Frame-Timestamp`를 전달합니다. 유효한 프레임이 없거나 오래되면 204입니다. 분석과 영상은 시간 동기화되지 않습니다. 헤더의 timestamp는 카메라 촬영 시각이 아닙니다.

테스트 `python -m pytest -q tests/test_plaintext_demo.py`는 허용 IP·위조 헤더·읽기 전용 경로와 프레임을 검증하고, `python -m tests.plaintext_srt_smoke`는 같은 컴퓨터에서 합성 SRT→RTSP 10프레임을 디코딩합니다. FFmpeg 시험 경로는 현재 작업 폴더 설치에 한정됩니다. 두 테스트는 외부 네트워크를 열지 않습니다. 실제 맥북·방화벽·공인망, 전체 실시간 속도와 JPEG/분석 동시성은 별도 검증이 필요합니다.

`python -m app.demo_supervisor`는 세 프로세스를 실행하고 로컬 분석 API에 입력 연결을 반복 요청합니다. 두 환경변수를 생략하면 loopback만 사용합니다. Windows에서는 자식 프로세스를 전용 Job Object로 묶어 supervisor 종료 시 하위 프로세스를 정리합니다. `tests.plaintext_stack_smoke`는 합성 SRT에서 실제 HTTP JPEG까지, `tests.plaintext_kill_smoke`는 supervisor 강제 종료 후 포트 반환을 확인합니다. 이 시험은 고정 포트를 쓰므로 다른 실행과 동시에 돌리지 마세요.
