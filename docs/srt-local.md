# MediaMTX SRT 격리 시험 설정

`configs/mediamtx-srt-local.yml`과 `python -m app.secure_srt`는 서버 한 대에서만 동작하는 시험 구성입니다. 기본 MediaMTX 설정을 수정하지 않고, SRT는 `127.0.0.1:18890/UDP`, 분석 프로그램용 RTSP는 `127.0.0.1:18554/TCP`만 수신합니다. 해당 `match` 경로에 지정한 계정만 게시할 수 있으며, 읽기 권한은 loopback으로 제한합니다. 다른 경로·익명 게시를 허용하지 않습니다. RTMP, HLS, WebRTC, MoQ, 제어 API, metrics, pprof 및 playback은 꺼져 있습니다. 동일 경로의 기존 송출자를 다른 송출자가 끊고 대체하는 기능도 꺼져 있습니다.

실행 프로세스 환경에 `FOOTBALL_SRT_USER`, `FOOTBALL_SRT_PASSWORD`, `FOOTBALL_SRT_PASSPHRASE`를 공급한 뒤 `.venv\Scripts\python.exe -m app.secure_srt`로 시작합니다. 계정명은 8~64자, 비밀번호와 암호구는 각각 32~64자의 영문·숫자·`_`·`-`만 사용하며 서로 달라야 합니다. 길이는 난수성을 보장하지 않으므로 보안 난수로 생성하고 안전하게 전달해야 합니다. 비밀은 코드, 터미널 명령 이력, Git, 채팅에 기록하지 마세요. 실제 비밀을 설정하거나 아이폰에 전달한 적은 없습니다. 이 도우미는 다른 `MTX_` 환경 설정을 제거해 리스너와 권한이 덮어쓰이지 않도록 하며, MediaMTX 자식 프로세스의 환경에는 비밀이 들어갑니다. 해당 프로세스 환경을 읽을 수 있는 사용자·관리자로부터 보호되지는 않습니다. 원본 yml을 단독으로 실행하지 마세요.

임시 난수만으로 실행한 독립 로컬 시험에서 잘못된 게시 계정과 잘못된 암호구를 각각 거부했고, 올바른 SRT 송출을 RTSP로 10프레임 읽었습니다. 사용자 아이폰이나 실제 인터넷 회선은 시험하지 않았습니다. `tests/srt_security_smoke.py`도 별도 테스트 설정을 이용해 인증과 암호구를 검사합니다.

## 인터넷 공개 전 미해결 조건

- 위 수신 주소는 loopback이므로 아이폰이 다른 기기라면 연결할 수 없습니다. 공인 노출로 바꾸거나 포트포워딩을 만들지 않았습니다. 실제 인터페이스, 방화벽, 인증·접근제어와 외부 기기에서의 검증이 별도 필요합니다.
- MediaMTX는 SRT 게시 비밀번호를 stream ID에 담습니다. SRT가 영상 **payload**를 암호화한다는 사실만으로 stream ID 안의 계정정보가 네트워크에서 기밀이라고 가정할 수 없습니다. 장치·프로토콜의 전송 보호를 검증하고, 안전한 별도 보호 수단 또는 인증 방식이 마련되기 전에는 이 시험 구성을 인터넷에 공개하지 마세요. [MediaMTX 인증 문서](https://mediamtx.org/docs/features/authentication), [SRT 명세](https://github.com/Haivision/srt-rfc/blob/main/draft-sharabayko-srt.md)를 참고하세요.
- 아이폰 앱이 암호화, stream ID, 인증을 모두 지원하는지, 영상 코덱, 자동 재연결, 실제 지연 및 방화벽/NAT 경로는 미확인입니다. 보안 난수의 비밀을 두 기기에 안전하게 전달하고 교체하는 방법도 준비해야 합니다.
- WebRTC는 이 구성에서 꺼져 있으므로 별도의 안전한 구성과 검증이 필요합니다. 영상이 켜졌다는 이유로 공개 서비스에 안전하다고 판단하지 않습니다.

## 제한된 LAN 시험 준비

`python -m app.secure_srt_lan`은 위 인증 환경변수 외에 서버의 사설 IPv4 `FOOTBALL_SRT_BIND_IP`와 허용할 송출지 IPv4 하나인 `FOOTBALL_SRT_PUBLISHER_IP`가 필요합니다. 설정한 LAN 주소의 UDP 8890에서 SRT를 받고, 게시 권한을 송출지 `/32`로 제한하며 RTSP는 loopback에만 둡니다. 실행하면 LAN 리스너가 열리므로 시험이 허가된 환경에서만 사용합니다. 이 도구는 공유기나 방화벽을 수정하지 않습니다. 송출지 IP 제한은 도청 방지 수단이 아니며 연결 정보와 임시 인증정보를 안전하게 교환해야 합니다.

같은 컴퓨터에서 LAN 주소로 임시 인증·암호화 송출 후 RTSP 영상 5프레임을 읽었고, 허용되지 않은 송출지의 요청은 거부됐습니다. 처음에는 시험 영상의 키프레임 간격이 길어 첫 프레임이 시간 초과됐습니다. 10fps 및 GOP 10으로 재시험했으며 송출 프로그램에서는 1~2초 키프레임 간격부터 시험할 수 있습니다. 실제 맥북, 외부 네트워크와 공유기 경로는 미검증입니다.

### Windows 임시 방화벽 규칙

`scripts/srt_firewall.ps1`은 고유한 `<FIREWALL_RULE>` 규칙만 추가하거나 제거합니다. 인바운드 UDP 8890, 이 프로젝트의 MediaMTX 실행 파일, 복호한 송출지 IPv4 한 개로 제한합니다. 암호문과 개인키 파일 경로를 `-PrivateKeyPath`, `-CiphertextPath`로 전달합니다. `-Action Check`는 일반 권한으로 입력을 점검하며 변경하지 않습니다. `-Action Apply`와 `-Action Remove`에는 관리자 권한이 필요합니다. 추가 후 범위를 재확인하며 실패하면 새 규칙을 삭제합니다. 포트만 제한한 이 규칙 외에 기존에 더 넓게 허용하는 규칙이 있다면 이 규칙만으로 차단을 보장하지 못합니다.

```powershell
.\scripts\srt_firewall.ps1 -Action Check -PrivateKeyPath '<개인키 파일>' -CiphertextPath '<암호문 파일>'
# 관리자 권한 PowerShell에서만, 실제 시험을 승인한 직후:
.\scripts\srt_firewall.ps1 -Action Apply -PrivateKeyPath '<개인키 파일>' -CiphertextPath '<암호문 파일>'
# 시험 종료 후 관리자 권한 PowerShell에서:
.\scripts\srt_firewall.ps1 -Action Remove
```

출발지 암호문을 일반 권한으로 검증했고 규칙 이름이 비어 있음을 확인했습니다. 실제 UAC 승인, 규칙 추가와 제거, 공유기 설정 및 외부 수신은 아직 시험하지 않았습니다. 개인키와 암호문은 별도 접근 제한 폴더에 보관하고 테스트 후 제거합니다. UAC가 나타나면 사용자가 직접 확인해야 하며 비밀번호나 출발지 IP를 채팅에 입력하지 않습니다.
