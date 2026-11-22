# 촬영과 SRT 송출 안내, 영상의 한계, 사용자님 아이디어 검토 (2026-11-16)

이 문서는 세 가지를 한곳에 정리합니다. (A) 지금 우리 영상이 가진 한계, (B) 휴대폰으로 어떻게 찍고 SRT로 보내야 하는지, (C) 사용자님이 이전에 제시하신 아이디어에 대한 검토입니다.
표기: **측정**은 이 프로젝트의 파일이나 영상에서 직접 잰 값, **추정**은 계산이나 판단, **제안값**은 외부 자료와 이 프로젝트 조건을 합쳐 제가 정한 시작 값(현장에서 시험해 조정해야 함), **확인 못 함**은 자료를 찾지 못했거나 재지 않은 것입니다. 외부 주장에는 출처를 달았습니다.
근거 위키: [pipeline-and-paths.md](pipeline-and-paths.md), [research-detection-tracking.md](research-detection-tracking.md), [research-calibration.md](research-calibration.md), [research-team-and-roles.md](research-team-and-roles.md), [research-player-identity-and-labelling.md](research-player-identity-and-labelling.md), [research-operations.md](research-operations.md), [detector-experiments.md](detector-experiments.md), [coach-operating-guide.md](coach-operating-guide.md), [live-service-audit.md](live-service-audit.md). 원본 문서는 `docs/srt-local.md`, `docs/live-recording.md`입니다.

---

## A. 우리 영상의 한계

### A-1. 영상 파일 자체 (측정)
대상: `work/own-match-merged-20261111/match_from_17min.mp4` (ffprobe와 ffmpeg로 직접 확인).

| 항목 | 값 | 비고 |
|---|---|---|
| 해상도, 코덱 | 1920x1080, HEVC(Main), yuvj420p | 측정 |
| 길이, 프레임 수 | 2,916.5초(48분 36초), 130,376프레임 | 측정 |
| 평균 비트레이트 | 약 6.9 Mbps (파일 전체), 영상 스트림 약 6.8 Mbps | 측정 |
| 프레임레이트 | **약 1,400~1,500초 사이를 경계로 앞은 30fps, 뒤는 60fps** | 측정: 4초 창 14곳(60, 300, 600, 900, 1100, 1200, 1300, 1400초는 30fps, 1500초 이후 1800, 2100, 2400, 2700, 2900초는 60fps). 60초 창 4곳에서 프레임 간격은 각각 33.3ms 또는 16.7ms로 거의 일정(편차 0.1ms 이하) |
| 평균 fps가 44.7로 나오는 이유 | 30fps 구간과 60fps 구간을 이어 붙였기 때문 | 측정(130,376프레임 / 2,916.5초) |
| 밝기 (0~255) | 경기장 쪽(화면 아래 38%) 평균: 전반 94~101, 후반 115~125. 하위 5%는 30~37 | 측정: 9개 프레임 |

해석: 이어 붙인 영상이라 "프레임 간격이 불규칙하다"는 표현은 정확히는 **구간마다 30fps와 60fps가 다르다**는 뜻입니다(구간 안에서는 규칙적). 전환 시점은 카메라가 바뀐 24분 44초(1,484초) 무렵과 같습니다(추정: 같은 시점이라고 확정하지는 않았습니다). 후반이 전반보다 약 20% 밝아서 같은 색 기준이 구간마다 다르게 작동할 수 있습니다(추정, 팀 분류 오차에 미치는 영향은 재지 않았습니다).

### A-2. 촬영 조건 (측정 또는 추정)

| 한계 | 내용 | 근거 |
|---|---|---|
| 선수 크기(키 픽셀) | 가까운 쪽(경기장 y>12m) 중간값 47~48px, 가운데 29~31px, 먼 쪽(y<-12m) 21~22px. 먼 쪽은 가까운 쪽의 약 절반 | 측정: 팀 추적 상자 전반 약 13만 줄, 후반 약 11만 줄 ([pipeline-and-paths.md](pipeline-and-paths.md)) |
| 등번호 읽기 | 번호를 읽으려면 약 150px이 필요한데, 우리 영상의 가장 큰 선수도 약 48px (3분의 1) | 측정(키)과 문서에 인용된 연구(SoccerNet 등번호 과제, `인수인계 문서(공개본에서 제외)`) |
| 밤 조명 | 어두운 옷(B팀)이 어두운 배경과 섞임. 하위 5% 밝기가 30 안팎 | 측정(밝기). 검출과 팀 분류에 미치는 영향의 크기는 확인 못 함 |
| 카메라 높이, 거리, 각도 | 촬영 당시 값은 기록이 없음. 먼 쪽 선수가 가까운 쪽의 약 절반이라는 사실로 보아 비스듬히 낮게 본 구도로 추정 | 추정 (정확한 높이와 거리는 확인 못 함) |
| 카메라 구도 변경 | 전반 cam1, 카메라가 바뀐 구간 cam2(보정 없음), 후반 cam3. 24분 44초 무렵 카메라가 바뀜 | [live-service-audit.md](live-service-audit.md) |
| 흔들림과 줌 | 정량 측정은 하지 않았음. 후반 카메라 이동 보정 일정이 1,950초에서 한 번 바뀐 기록이 있음(이동량 단위는 확인 못 함). 라이브 스크립트는 카메라 이동 감시를 연결하지 않아 움직임이 생기면 조용히 틀어짐 | [pipeline-and-paths.md](pipeline-and-paths.md), [live-service-audit.md](live-service-audit.md) 3절 |
| 먼 쪽 선수와 박스 안 | 먼 쪽(21~22px)은 놓치기 쉽고, 붐비는 페널티 박스 안 선수는 검출이 빠짐. 실제 라이브 4분 시험에서 한 골 직전 박스 안 선수가 잡히지 않아 박스 침투 알림이 나오지 않음. 한 순간 팀 B가 최근 1초를 합쳐 평균 10.0명(마지막 프레임만이면 7.4명) | 측정: [live-feedback.md](live-feedback.md) |
| 프레임레이트 혼합 | 구간마다 30/60fps. 라이브 분석은 "N번째 프레임마다 분석"하는 구조라서(코드 확인), 60fps 구간에서는 같은 N이면 초당 분석 횟수가 2배가 될 수 있음 | 추정: 코드를 실제로 60fps 영상으로 돌려 확인하지 않았음 |

### A-3. 한계가 기능에 주는 영향

| 기능 | 영향 | 심각도 | 근거 |
|---|---|---|---|
| 검출(선수 찾기) | 먼 쪽과 박스 안 선수를 놓침. 사용자님이 그리신 상자 34개를 찾는 비율은 모델에 따라 17~28개 | 큼 | 측정: [detector-experiments.md](detector-experiments.md) |
| 번호 읽기 | 대부분의 추적 조각에서 불가능. 선수 이름 연구는 중단 | 큼 | 측정(키 픽셀) |
| 팀 분류 | 이 경기는 A 형광, B 어두운 옷이라 색 차이가 커서 비교적 안전하지만, 심판과 벤치 인원이 섞이고 전후반 밝기가 다름 | 중간 | 문서 기록(팀 구분 약 85%, 근거 표본은 확인 못 함), 밝기는 측정 |
| 경기장 보정 | 카메라가 바뀌면 보정을 바꿔야 함. cam2 구간은 보정이 없어 그 구간의 골이 분석에서 빠짐. 보정 오차는 팀 모양의 절대 길이에 들어감 | 큼 | [research-calibration.md](research-calibration.md) |
| 공 | 슛처럼 빠른 구간을 놓침(정밀도 약 96%, 재현율 약 43%). 공을 쓰는 알림은 없음 | 큼 | [research-tactics-and-ball.md](research-tactics-and-ball.md) |
| 알림 | 선수 수 부족과 보정 한계가 알림 품질을 제한. 후반 판정 25개 중 맞음 18개. 알림이 상황보다 3~11초 늦음 | 큼 | [coach-operating-guide.md](coach-operating-guide.md) |

핵심: 한계의 큰 부분은 **카메라가 멀고 낮아서 선수가 작게 찍히는 것**과 **카메라 구도와 프레임레이트가 중간에 바뀐 것**입니다. 앞으로의 촬영에서 이 두 가지를 먼저 바로잡는 것이 효과가 큽니다(추정).

---

## B. 스마트폰 촬영과 SRT 송출 안내

### B-1. 분석 파이프라인이 요구하는 조건 (이 프로젝트 자료)
1. **카메라를 경기 내내 한 자리에 고정**하고 줌과 각도를 바꾸지 않습니다. 이동 감시가 라이브에 연결돼 있지 않아서, 움직이면 위치가 조용히 틀어집니다 ([live-service-audit.md](live-service-audit.md)).
2. **경기장 기준점이 화면에 보여야** 합니다. 경기장 보정은 사람이 같은 프레임에서 알려진 점(골라인, 페널티 구역 모서리 등)을 4개 이상 찍어 만듭니다. 모서리가 잘리면 보정이 불안정해집니다 ([research-calibration.md](research-calibration.md)).
3. 카메라는 경기장의 한쪽 터치라인 쪽(분석 좌표에서 +y 쪽)에 두는 것으로 가정되어 있습니다 ([pipeline-and-paths.md](pipeline-and-paths.md)의 팀 모양 규칙).
4. 전후반에 카메라 위치가 바뀌면 보정이 새로 필요합니다. 같은 자리에 같은 설정으로 다시 두면 보정을 재사용할 수 있습니다(추정: 같은 구도가 정확히 복원되는지는 확인 못 함).
5. 송출에서 키프레임 간격이 길면 수신기가 첫 프레임을 못 읽을 수 있습니다. 1~2초 간격을 쓰라는 시험 기록이 있습니다 (`docs/srt-local.md`, 로컬 시험에서 10fps, GOP 10으로 재시험).
6. 프레임레이트는 **한 가지로 고정**하는 편이 안전합니다(제안값 30fps). 분석이 초당 5장이라 60fps의 이점이 작고, 비트레이트와 발열과 연산량이 늘어납니다(추정: 정확도 차이는 재지 않았습니다).

### B-2. 촬영 위치와 장비 (제안값)
외부 자료의 공통점은 **경기장 중앙선 부근, 삼각대를 가장 높게, 터치라인에서 조금 뒤**입니다.

| 항목 | 외부 자료 | 우리에게 적용하는 제안값 |
|---|---|---|
| 위치 | 중앙선 부근. Veo는 중앙선에서 3~5m 높이를 제안하고 두 페널티 지역이 한 화면에 들어온다고 설명 ([Veo](https://www.veo.com/article/how-to-film-youth-matches)). Hudl도 경기장 중앙 근처를 권장 ([Hudl](https://www.hudl.com/support/v3/resources/soccer-recording-tips)) | 중앙선 연장선 위, 가능한 한 높은 곳 |
| 높이 | BallerCam은 약 10~15피트(약 3~4.5m) ([BallerCam](https://ballercam.com/pages/soccer-setup-instructions)). Spiideo의 고정 설치 제품은 높이 8m ([Spiideo](https://support.spiideo.com/en/articles/5079226-camera-positioning-guide)) | 3m 이상, 가능하면 스탠드나 사다리 위. 높을수록 먼 쪽 선수가 크게 보이고 가림이 줄어듭니다(추정: 높이별 효과는 재지 않았음) |
| 터치라인에서의 거리 | BallerCam 약 10피트(약 3m), Pixellot 12~15피트(약 3.7~4.6m) ([Pixellot](https://pixellotyou.wpengine.com/wp/wp-content/uploads/Pixellot-Air-Venue-Setup-Guide.pdf)). Spiideo 제품별로 6m 이상 | 3~5m 뒤. 너무 가까우면 가까운 쪽 터치라인이 잘림 |
| 방향 | Veo는 살짝 아래로 기울여 양쪽 터치라인이 모두 보이게 하라고 설명 | 양쪽 골라인과 양쪽 터치라인, 가능하면 페널티 구역 모서리 4개와 중앙 원이 모두 화면에 들어오게 |
| 삼각대 | 높이와 안정성 확보 | 바람에 흔들리지 않게 무게를 달고, 경기 내내 만지지 않기 |

※ 위 수치는 상용 제품의 지침이고 휴대폰 하나로 우리 파이프라인에 맞는지는 시험해야 합니다. 이 프로젝트에서 촬영 높이별 효과를 직접 비교한 자료는 없습니다(확인 못 함).

### B-3. 휴대폰 설정 (제안값)

| 설정 | 제안값 | 근거 |
|---|---|---|
| 해상도 | 1920x1080 | 이 프로젝트 영상이 이 해상도이고 처리 속도가 거의 실시간이어서 더 높이면 처리 부담이 커짐(측정: 4분 영상 250초). 4K는 선수가 약 2배 크게 보이지만(계산상 추정) 검출 연산도 늘어남. Moblin은 4K 60fps까지 지원한다고 개발자 페이지에 적혀 있음 ([Moblin](https://eerimoq.github.io/moblin)), 앱스토어 국가별 목록에는 1080p까지로 적힌 곳도 있음 ([App Store 독일](https://apps.apple.com/de/app/moblin/id6466745933)) |
| 프레임레이트 | 30fps 고정 | B-1의 6번. 야간에는 프레임레이트가 자동으로 떨어져 흔들림이 생길 수 있다는 지침이 있음 ([MacRumors](https://www.macrumors.com/guide/better-video-with-your-iphone/)) |
| 코덱과 비트레이트 | HEVC 약 6~8Mbps (또는 H.264 약 8Mbps) | 우리 영상이 HEVC 약 6.8Mbps(측정). 1080p30 H.264 라이브는 보통 4.5~6Mbps ([Ant Media](https://antmedia.io/video-bitrate/)), HEVC는 같은 화질에 더 낮은 비트레이트가 가능하지만 대상 서버가 지원하는지 확인 필요 ([Livepush](https://livepush.io/blog/video-bitrate/)). 이 프로젝트의 MediaMTX 수신은 HEVC로 녹화한 실적이 있음(측정: 위 영상) |
| 키프레임 간격 | 1~2초 | `docs/srt-local.md` |
| 노출과 초점 | AE/AF 잠금(화면을 길게 눌러 잠금) 후 밝기 조절. 경기 중간에 노출이 바뀌면 팀 분류가 흔들림(추정) | 방법: [Primal Video](https://primalvideo.com/video-creation/shooting/filming-videos-with-iphone-fix-lighting-and-exposure-changes-with-auto-exposure-lock). 단, 어두운 장면에서 잠금이 화면 밝기만 낮춘 것처럼 보였다는 사용자 보고도 있음(같은 검색 결과) |
| 줌 | 광각 1배에 고정, 디지털 줌 사용 금지 | 줌 변경은 보정을 깨뜨림 ([live-service-audit.md](live-service-audit.md)). 저조도에서는 기본 1배 렌즈가 낫다는 의견이 있음 ([MacRumors](https://www.macrumors.com/guide/better-video-with-your-iphone/)) |
| 흔들림 보정 | 삼각대 위에서는 끄거나 고정 | 확인 못 함: 자동 안정화가 보정에 미치는 영향은 재지 않았음 |

### B-4. SRT 송출 설정 (제안값)
- **SRT 지연(latency)**: 왕복 시간(RTT)의 3~4배가 일반 지침입니다. Haivision은 손실이 0.1~0.2% 정도인 무난한 망에서 RTT의 4배를 경험칙으로 제시하고 ([Haivision 문서](https://doc.haivision.com/SRT/1.5.3/Haivision/latency)), 다른 설정 문서는 최소 3배를 권장합니다 ([Haivision 설정 문서](https://doc.haivision.com/HMG/4.0/section-3-protocol-settings)). 4G 망 연구에서는 3~4배로는 지연 변동을 완전히 흡수하지 못할 수 있다고 합니다 ([연구 글](https://medium.com/innovation-labs-blog/examining-srt-streaming-over-4g-networks-925e71c45cdf)). 신호가 약할 때 Moblin에서 3,000~4,000ms로 올리라는 안내는 릴레이 서버 한 곳의 팁입니다 ([StreamingEst](https://streamingest.pages.dev/blog/how-to-configure-moblin-for-irl-streaming)).
  - **제안값**: 현장에서 `ping`으로 RTT를 재고(경기 전 5분), 그 값의 4배 이상으로 시작합니다. 같은 와이파이라 RTT가 20ms 이하이면 최소값(대략 120~200ms) 근처, 셀룰러이면 1,000~2,000ms부터 시험합니다. 이 숫자는 제가 정한 시작 값이며, 알림이 늦게 오지 않는 범위에서 조정합니다.
  - 알림이 경기 상황을 반영해야 하므로 SRT 지연은 코칭 지연 예산에 그대로 들어갑니다([live-operations-research.md](live-operations-research.md)에서 지연 예산을 다룸).
- **연결 방식**: 가능하면 경기장 현장에 전용 와이파이나 유선 공유기를 두고 분석 서버와 같은 망으로 보내는 편이 가장 안정적입니다(추정). 셀룰러만 쓸 때는 여러 회선을 묶는 SRTLA가 있고 Moblin은 이를 지원하며 받는 쪽에 SRTLA 수신 서버가 필요합니다 ([StreamingEst](https://streamingest.pages.dev/blog/srtla-bonding-explained)). 효과에 대한 주장은 업체와 개인 후기이며 독립된 측정은 찾지 못했습니다(확인 못 함). 현장에서 10분 이상 시험하라는 권고가 있습니다 ([VajraCast](https://vajracast.pages.dev/srtla-bonding)).
- **대역폭 여유**: 송출 비트레이트의 1.5배 이상, 또는 안정적인 업로드 속도의 50~70% 이내를 권장하는 자료가 있습니다 ([Livepush 계산기](https://livepush.io/tools/bitrate-calculator/)). 약 7Mbps 송출이면 업로드가 안정적으로 10Mbps 이상이어야 합니다(제안값).
- **보안**: 이 프로젝트의 수신은 인증과 암호구(passphrase)를 쓰는 구성을 시험했습니다(로컬 시험만, `docs/srt-local.md`). 아이폰 앱이 암호화, stream ID, 인증을 모두 지원하는지, 자동 재연결, 실제 지연은 미확인입니다(`docs/srt-local.md`). 평문 공개 송출은 시험용이며 실제 경기 영상에는 쓰지 않습니다 (`docs/plaintext-demo` 계열, [research-operations.md](research-operations.md)).

### B-5. 발열, 배터리, 전원
- 스트리밍은 CPU, 화면, 통신을 모두 쓰므로 열이 납니다. 화면 밝기를 낮추고, 케이스를 벗기고, 백그라운드 앱을 닫고, 신호가 안정적인 곳에서 쓰라는 안내가 있습니다 ([PRISM Live](https://guide.prismlive.com/mobile/guides/error-solution/performance/improving-smartphone-overheating-for-better-streaming), [삼성](https://www.samsung.com/latin_en/support/mobile-devices/prevent-overheating-galaxy-device/)).
- 충전하면서 쓰면 발열이 더 커질 수 있다는 안내가 있고, 외부 배터리(파워뱅크) 자체의 발열을 다룬 자료는 찾지 못했습니다(확인 못 함).
- **제안값**: 경기 90분 이상을 가정해 외부 전원을 연결하되(발열 상태 확인), 그늘에 두거나 햇빛을 가리고, 첫 전반 종료 때 발열 경고가 뜨는지 시험 촬영으로 미리 확인합니다. 경고가 뜨면 해상도나 프레임레이트를 낮춥니다.

### B-6. 두 대 이상, 녹화 병행
- **시간 맞추기**: 가장 간단한 방법은 시작 때 박수나 플래시를 모든 카메라가 볼 수 있게 하고 끝에서도 한 번 더 해서 어긋남(드리프트)을 확인하는 것입니다. 소리는 먼 카메라에 늦게 도착하므로 먼 쪽은 눈에 보이는 신호로 맞추라는 조언이 있습니다 ([안내 글](https://www.sheldonbrown.com/synchronize-video.html)). 긴 영상에서는 몇 분마다 프레임을 더하거나 빼야 했다는 사례도 있습니다(같은 글). 정밀한 동기는 안드로이드용 앱(RecSync)이 있고 오차 250µs 미만이라고 연구가 주장합니다 ([논문](https://arxiv.org/pdf/1812.09366), [코드](https://github.com/mobileroboticsskoltech/recsync-android)). 아이폰용은 찾지 못했습니다(확인 못 함).
- **녹화**: 이 프로젝트의 서버 녹화는 fMP4, 약 10분 세그먼트, 자동 삭제 없음입니다 (`docs/live-recording.md`). 송출 중에는 서버에서 녹화되고 있는지와 디스크 여유를 경기 전에 확인합니다. Moblin 자체의 로컬 녹화 기능은 이번 조사에서 확인하지 못했습니다(확인 못 함). 휴대폰 내장 카메라 녹화를 따로 켜는 방법은 송출과 동시에 가능한지 기기별로 시험이 필요합니다.

### B-7. 경기 전 체크리스트 (제안)

| 순서 | 할 일 | 합격 기준(제안값) |
|---|---|---|
| 1 | 삼각대를 중앙선 연장선에, 가능한 한 높게, 터치라인에서 3~5m 뒤로 설치. 케이스를 벗기고 그늘 확보 | 화면에 양쪽 골라인과 터치라인, 페널티 구역 모서리 4개와 중앙 원이 들어옴 |
| 2 | 1080p, 30fps, HEVC, 키프레임 1~2초로 설정. 줌 1배, AE/AF 잠금 | 설정 화면 캡처로 확인 |
| 3 | RTT 측정 후 SRT 지연 설정. 대역폭 시험 | 업로드가 송출 비트레이트의 1.5배 이상, 지연 설정은 RTT의 4배 이상 |
| 4 | 짧게 송출해 서버가 영상을 받는지, 녹화 파일이 커지는지 확인 | 5분 이상 끊김 없음. 입력 정지 표시가 뜨지 않음 |
| 5 | 보정용 기준 프레임을 한 장 저장하고 기준점 클릭(사람) | 기준점 4개 이상, 확인점 3개 이상에서 오차를 사용자님이 판단([research-calibration.md](research-calibration.md)) |
| 6 | 공격 방향과 팀 색을 입력하고 킥오프 전에 말로 한 번 더 확인 | 방향이 틀리면 모든 알림이 반대 ([coach-operating-guide.md](coach-operating-guide.md)) |
| 7 | 킥오프 전 시험 실행 1~5분 | 보이는 선수가 팀당 7명 이상 |
| 8 | 하프타임: 카메라 위치와 설정이 전반과 같은지 확인, 후반 방향 입력 | 삼각대를 만졌다면 보정 다시 확인 |

### B-8. 문제가 생겼을 때

| 증상 | 가능한 원인 | 대처 |
|---|---|---|
| 영상이 끊김 | 신호, 대역폭 부족, SRT 지연이 작음 | 지연을 올리고(예: 2배) 해상도나 비트레이트를 낮춤. 와이파이로 전환. 현재 라이브 스크립트는 재연결이 없어서 서버 쪽도 확인([live-service-audit.md](live-service-audit.md)) |
| 휴대폰이 뜨거워짐 | 충전과 고해상도, 직사광선 | 밝기와 해상도를 낮추고 그늘로. 경고가 뜨면 송출을 멈추고 식힘 ([PRISM Live](https://guide.prismlive.com/mobile/guides/error-solution/performance/improving-smartphone-overheating-for-better-streaming)) |
| 화면이 갑자기 밝거나 어두워짐 | 자동 노출 | AE/AF 잠금 확인 |
| 알림이 갑자기 이상해짐 | 카메라가 움직였거나 줌이 바뀜 | 화면을 눈으로 확인하고 기준 프레임과 비교. 감시는 아직 라이브에 연결돼 있지 않음 |
| 선수가 팀당 7명 미만으로 보임 | 조명, 거리, 가림 | 팀 모양 알림을 믿지 말고 사람이 눈으로 판단 ([coach-operating-guide.md](coach-operating-guide.md)) |

---

## C. 사용자님이 이전에 제시하신 아이디어 검토

출처: 프로젝트 기록에서 촬영, 카메라, 번호, 공, 궤적 표시와 관련된 의견을 모은 것입니다. 문서(`인수인계 문서(공개본에서 제외)` 9절, `docs/player-identity.md` 3절)에 있는 "반쪽씩 찍기", "4K 촬영", "경기 전 번호 보여 주는 영상"은 **사용자님의 제안이 아니라 이전 응답에서 제가 제안한 것**이며 사용자님은 이후 지금 있는 영상으로 전술 분석을 먼저 하고 촬영 방식은 나중에 정하기로 하셨습니다. 아래에 이 항목들도 함께 평가합니다.

| # | 아이디어 | 기대 효과 | 비용과 난이도 | 이 프로젝트에서의 위험 | 권고 | 근거 |
|---|---|---|---|---|---|---|
| 1 | 반대쪽에서도 카메라로 찍어 싱크를 맞추면 인식률이 더 오를까? | 먼 쪽 선수가 가까운 쪽 크기(약 2배, 키 21~22px에서 약 47px 수준)로 보여 검출과 가림이 줄 것(추정, 실측 아님). 두 카메라가 같은 사람을 이어 주면 추적 끊김도 줄 수 있음(추정) | 휴대폰 1대 추가, 시간 동기(박수와 플래시, 확인 못 함 정도의 정확도), 카메라마다 보정, **두 화면의 같은 선수를 이어 주는 합치기 코드가 없음**, 처리량이 카메라 수만큼 늘어남(지금도 거의 1배속) | 합치기가 틀리면 선수가 두 명으로 보이거나 섞임. 현재 처리량으로 실시간 불가 | **나중에(경기 후 분석부터 시험)** | 한 대로 품질을 올리는 것이 먼저(검출기 학습, 높은 위치 촬영). 두 대는 녹화해 두고 오프라인에서 효과를 재 본 뒤 실시간 여부 결정 |
| 2 | 포지션과 등번호까지 구별하면 사람을 더 정확히 인식한다는 피드백 | 포지션은 같은 팀 안에서 후보를 줄임. 번호는 직접 증거로 가장 강함 | 포지션 줄은 이미 `app/position_slots.py`에 구현. 번호는 읽을 수 없음(키 48px 대 필요 150px, 측정) | 번호를 억지로 읽으면 90과 99 같은 오배정(실제 사례: 후반 조각 7개) | **포지션은 유지, 번호는 하지 않기(현재 해상도)** | 번호는 4K나 가까운 촬영이 되어야 가능(3절 가까운 쪽 약 190px 계산은 추정). 자동 번호 읽기는 현 영상에서 효과가 없음 |
| 3 | SnapGoal처럼 휴대폰 두 대를 연결해 파노라마로 만들고 동기를 맞춰 선수와 공을 추적하기 | 화면이 넓어지고 해상도가 올라 선수가 커 보임(추정). 상용 서비스 방향 | 두 대, 동기, 영상 이어붙이기(스티칭), 파노라마 전용 보정과 검출(타일 처리가 이미 있음). SnapGoal의 주장은 검증하지 못했다고 이미 기록함(`인수인계 문서(공개본에서 제외)`) | 스티칭 경계에서 선수 중복, 시간 어긋남, 처리량 증가, 구현 기간 길다 | **나중에** | 아이디어 1과 같이 오프라인 시험이 먼저. 이 프로젝트는 SoccerTrack(6500x1000 파노라마)에서 타일 검출을 시험한 적이 있음([research-detection-tracking.md](research-detection-tracking.md)) |
| 4 | 공을 사람이 후보 중에서 클릭해 고르게 하기 | 공 정답 자료를 빨리 모아 공 모델을 학습시킴. 이미 b01~b39 라벨 확인(공 재순위 모델 v3의 기반) | 후보 클릭 화면이 이미 있는 것으로 보임(구현 상태는 확인 못 함). 사람 시간이 필요 | 라이브에서 사람이 클릭할 수는 없음. 정답 자료로만 가치 | **해보기(소량, 학습용)** | 현재 우선순위는 선수 검출이므로 규모를 작게. 공이 있으면 패스와 점유 알림이 가능해짐 ([research-tactics-and-ball.md](research-tactics-and-ball.md)) |
| 5 | 라이브에서도 경기장 보정을 자동으로 | 현장 시작 절차에서 사람 시간 10~30분(짐작)을 줄임. 카메라 변경에 대응 | 자동 보정 실험은 모두 실패(오차 77~400px). 사람이 한 번 찍고 카메라 이동은 특징점 추적으로 갱신하는 방식이 현실적 | 틀린 보정이 조용히 틀린 알림을 만듦 | **해보기(설계 먼저)** | [research-calibration.md](research-calibration.md), 별도 조사: [calibration-automation.md](calibration-automation.md) (진행 중이어서 파일이 아직 없을 수 있음) |
| 6 | 선수 이동 궤적을 3D 영상이나 미니맵에 하이라이트처럼 표시 | 이동을 한눈에 이해. 게임 하이라이트처럼 | 3D는 큼. 미니맵은 중간. 보정 정확도와 선수 누락(팀당 10명)에 의존 | 이후 사용자님의 지시로 영상에는 핵심 선수 상자, 미니맵, 이동 경로를 넣지 않기로 함(`인수인계 문서(공개본에서 제외)` 2절 3항). 미니맵이 틀리면 오히려 오해를 줌 | **하지 않기(영상)** 단, 코치 벤치 화면에서 정확도 표시와 함께 단순한 위에서 본 그림은 **나중에** | 사용자님 지시: 정확하게 만들지 않을 거면 미니맵을 쓰지 않는다. 정확도 기준을 정하고 나서 재검토 |
| 7 | 선수 사진 화질을 후처리로 개선 | 사람이 확인할 때 얼굴이나 옷을 보기 쉬움 | 이미 적용: 가장 선명한 3장 선택, 좁게 자르기, 220px 키우기, 밖을 어둡게 (`scripts/enhance_player_pictures.py`) | AI 해상도 확대는 없는 세부(숫자)를 만들어 내므로 쓰지 않음 | **현 상태 유지, AI 확대는 하지 않기** | 원본이 키 약 30px이라 한계가 큼([research-player-identity-and-labelling.md](research-player-identity-and-labelling.md)) |
| 8 | 골이 안 난 공격과 상대팀(B팀) 중심으로, 득점 직후 "올라가라" 같은 일반론 대신 시야 넓히기 같은 구체적 피드백 | 코칭 가치가 가장 높은 내용 | 공 정보 없이는 한계(패스, 점유 알림 불가). 기존 이벤트 추출을 골 미득점 공격까지 넓히는 일 | 선수 수 부족으로 박스 안 상황이 틀릴 수 있음 | **해보기** | 사용자님의 반복된 지시이며 [coach-operating-guide.md](coach-operating-guide.md)의 알림 문구 개선안과 맞닿아 있음. 구현 상태는 확인 못 함 |
| 9 | (제가 제안했던) 카메라를 경기장 반쪽씩 담고 4K로 촬영 | 같은 해상도에서 선수가 약 2배, 4K면 다시 2배(계산상 가까운 쪽 약 190px, 추정) | 카메라 2대 이상, 보정 2개, 합치기 코드 없음, GPU 처리량 증가 | 사용자님 결정으로 보류 | **나중에** | 사용자님 결정 존중. 단 4K 한 대로 중앙에서 높게 찍는 방법은 합치기 없이 시도할 수 있어 가장 먼저 시험해 볼 만함(추정) |
| 10 | (제가 제안했던) 경기 전에 선수별로 번호를 보여 주는 짧은 영상 | 번호와 선수를 연결해 이름 붙이기 부담을 줄임 | 선수들에게 1~2분 부탁하면 됨, 낮은 비용 | 번호가 안 읽히는 경기 중 영상과는 연결이 약함 | **해보기(선수 이름이 다시 필요해질 때)** | 선수 이름 연구는 현재 중단 상태 |

### 한눈에 보는 권고
- **지금 해볼 것**: 5(보정 자동화 설계), 4(소량 공 라벨), 8(골 미득점 공격 분석).
- **나중에**: 1, 3, 9(카메라 2대 이상, 파노라마, 4K 반쪽), 6의 벤치 화면 단순 그림.
- **하지 않기**: 6의 영상 표시(현재 규칙), 7의 AI 확대, 2의 번호 자동 읽기.
- **정직한 평가**: 1, 3, 9는 효과가 클 가능성이 있지만 지금은 근거가 추정뿐이고 합치기 코드가 없어서 곧바로 시작하기 어렵습니다. 먼저 **한 대를 높은 곳에 고정하고 프레임레이트를 하나로 맞춰 찍는 것**만으로도 이 영상의 가장 큰 두 가지 한계(선수 크기, 구도와 프레임레이트 변경)를 줄일 수 있습니다(추정).

---

## 확인하지 못한 것과 한계
- 촬영 당시 카메라 높이, 거리, 각도, 줌 값 (기록 없음).
- 흔들림과 줌의 정량 측정.
- 60fps 구간에서 라이브 분석 횟수가 실제로 2배가 되는지.
- Moblin의 로컬 녹화, 최신 버전의 정확한 메뉴 이름과 기본값(웹 검색 요약만 확인).
- 높이와 위치별 검출 개선 효과, SRT 지연별 알림 지연, 발열 한계 시간.
- 외부 자료는 상용 제품 안내와 블로그가 많아서, 현장 숫자는 시험으로 확인해야 합니다.

## 출처
- Moblin: [개발자 페이지](https://eerimoq.github.io/moblin), [App Store(한국)](https://apps.apple.com/kr/app/moblin/id6466745933), [App Store(독일)](https://apps.apple.com/de/app/moblin/id6466745933), [설정 가이드(StreamingEst)](https://streamingest.pages.dev/blog/how-to-configure-moblin-for-irl-streaming)
- SRT 지연: [Haivision SRT 지연](https://doc.haivision.com/SRT/1.5.3/Haivision/latency), [Haivision 설정](https://doc.haivision.com/HMG/4.0/section-3-protocol-settings), [Epiphan](https://epiphan.com/userguides/pearl-2/Content/stream/StreamSRTlatency.htm), [4G 망 SRT](https://medium.com/innovation-labs-blog/examining-srt-streaming-over-4g-networks-925e71c45cdf)
- 설치 위치: [Veo](https://www.veo.com/article/how-to-film-youth-matches), [BallerCam](https://ballercam.com/pages/soccer-setup-instructions), [Pixellot](https://pixellotyou.wpengine.com/wp/wp-content/uploads/Pixellot-Air-Venue-Setup-Guide.pdf), [Hudl](https://www.hudl.com/support/v3/resources/soccer-recording-tips), [Spiideo](https://support.spiideo.com/en/articles/5079226-camera-positioning-guide)
- 비트레이트: [Ant Media](https://antmedia.io/video-bitrate/), [Livepush](https://livepush.io/blog/video-bitrate/), [Livepush 계산기](https://livepush.io/tools/bitrate-calculator/)
- 발열: [PRISM Live](https://guide.prismlive.com/mobile/guides/error-solution/performance/improving-smartphone-overheating-for-better-streaming), [삼성](https://www.samsung.com/latin_en/support/mobile-devices/prevent-overheating-galaxy-device/)
- 노출 잠금과 저조도: [Primal Video](https://primalvideo.com/video-creation/shooting/filming-videos-with-iphone-fix-lighting-and-exposure-changes-with-auto-exposure-lock), [MacRumors](https://www.macrumors.com/guide/better-video-with-your-iphone/)
- 셀룰러 묶음(SRTLA): [StreamingEst](https://streamingest.pages.dev/blog/srtla-bonding-explained), [VajraCast](https://vajracast.pages.dev/srtla-bonding)
- 카메라 동기: [안내 글](https://www.sheldonbrown.com/synchronize-video.html), [논문](https://arxiv.org/pdf/1812.09366), [RecSync 코드](https://github.com/mobileroboticsskoltech/recsync-android)
