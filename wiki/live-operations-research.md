# 현장 실시간 운영 연구: 코치가 경기 중에 보면서 쓰려면

작성일: 2026-11-16. 목적: 코치가 경기장에서 이 서비스를 실시간으로 보면서 운영하려면 무엇이 필요하고, 지금 무엇이 없으며, 어떻게 고쳐야 하는지를 공개 자료와 현재 프로젝트 기록으로 정리합니다.
근거 구분: 1~5절은 웹 조사(출처 URL 표기, 대부분 제조사 홍보글이나 블로그라서 자기 주장이며 독립 검증이 아닙니다). 6절 이후는 이 프로젝트의 위키와 기록입니다. 출처 없이 기억에 의존한 내용은 "확인 못 함"으로 표시했습니다. 이 문서는 코드를 바꾸지 않았고 GPU를 쓰지 않았습니다.

## 1. 요약
- 상용 제품은 코치에게 "자동 분석 숫자"보다 **지연이 짧은 영상과 빠른 표시(태깅, 즉시 재생)** 를 벤치 태블릿으로 줍니다. 공개된 지연 수치는 Spiideo의 약 4초(제조사 주장) 하나뿐이었습니다.
- 알림 연구는 **빈도가 높고 우선순위가 없을수록 무시된다**는 점을 일관되게 보여 줍니다. 우리 서비스는 분당 약 2.5회로 매우 많습니다.
- 확신도 표시는 **정확하게 보정된 값일 때만** 도움이 됩니다. 보정이 틀린 확신도는 오히려 잘못된 신뢰를 만듭니다. 그래서 확신도는 사용자님의 판정 집계로 만든 "종류별 맞은 비율과 표본 수"로만 표시해야 합니다.
- 코치가 경기 중에 쓰는 정보 경로와 시간 한계에 대한 연구는 있지만, 분석 알림의 양이 의사결정에 미치는 영향을 직접 잰 통제 연구는 찾지 못했습니다 (확인 못 함).
- 현재 서비스의 가장 큰 격차는 (a) 입력이 끊기면 멈추고 상태 표시가 없는 것, (b) 코치에게 알림이 닿는 화면이 없는 것, (c) 알림이 많고 반복되며 일부 종류의 정확도가 낮은 것입니다.

## 2. 상용 제품은 코치에게 무엇을 어떻게 주는가
| 제품 | 경기 중 기능과 전달 방식 | 지연 수치 | 출처 |
|---|---|---|---|
| Veo | 즉시 재생(instant playback), 경기 중 태깅 후 바로 팀과 검토. 실시간 방송은 5G 모델이 필요하다고 비교 글에 적혀 있음 | 공개 수치 확인 못 함 | [Veo 비교 글](https://www.veo.com/en-us/article/soccer-camera-systems-compared), [Veo 즉시 재생](https://www.veo.com/article/instant-playback-enhance-the-football-analysis) |
| Spiideo | BenchMode: 사이드라인 아이패드로 저지연 영상과 즉시 클립 공유. Perform에서 경기 중 행동 태깅과 코멘트 | 카메라에서 벤치까지 약 4초 (제조사 주장, 독립 검증 못 찾음) | [Spiideo BenchMode](https://www.spiideo.com/news/bench-mode/) |
| Pixellot | 경기 중 다각도 클립 편집, 전술 시점(Tactical View). 상세 분석(VidSwap)은 4~8시간 뒤에 도착한다고 한 페이지에 적혀 있음. 사이드라인 앱(VidSwap Replay)은 전용 하드웨어가 필요 | 경기 중 분석의 지연 수치 확인 못 함 | [Pixellot VidSwap](https://www.pixellot.tv/?p=167462) |
| Hudl Sportscode + Replay | 분석가 컴퓨터의 라이브 영상과 데이터를 사이드라인 아이패드로 전송. 코치가 아이패드에서 태깅하면 분석가에게 되돌아가며, 하프타임처럼 연결이 끊긴 사이의 태그는 다시 연결되면 자동 동기화. 실시간 갱신 보고서도 있음 | 확인 못 함 | [Coach Tagging](https://www.hudl.com/blog/new-coach-tagging-feature-enhances-hudl-replay), [라이브 보고서](https://www.hudl.com/blog/hudl-replay-live-output-reports) |
| Catapult | Vector Live 아이패드 앱(선수 교체와 구간 표시 등 라이브 조작), Pro Video가 벤치 태블릿에 경기 중 인사이트 전달 | Catapult 라이브 데이터의 지연 수치 확인 못 함 | [Catapult 라이브 분석](https://www.catapult.com/blog/pro-video-live-analysis-coaching-decisions-player-adjustments) |
| Playermaker | 축구화 센서. 훈련 중 앱으로 데이터 동기화, 훈련 후 몇 분 안에 대시보드. 경기 중 사이드라인 전용 앱 정보는 확인 못 함 | 확인 못 함 | [소개 기사](https://wearable-technologies.com/news/playermaker-a-complete-coaching-tool-for-football-teams) |
| Metrica Sports | 검색에서 근거를 찾지 못함 | 확인 못 함 | 확인 못 함 |

읽는 법과 시사점
- 모두 **사람 분석가나 코치가 직접 태깅하고 영상을 되돌려 보는 방식**이 중심입니다. 자동 전술 알림을 경기 중에 밀어 주는 상용 사례는 이번 조사에서 확인하지 못했습니다 (확인 못 함). 우리 서비스는 그 영역을 시도하는 셈이라 정확도와 전달 방식의 검증 책임이 더 큽니다.
- 업계 평균 스포츠 중계 지연이 9초, 초저지연은 약 1초라는 자료가 있습니다([Dolby 해설](https://optiview.dolby.com/resources/blog/streaming/what-is-low-latency-video-streaming-the-complete-guide/), 설문 인용). 벤치 영상 4초는 그 중간입니다.
- 아마추어와 유소년은 비용과 복잡성이 가장 큰 장벽이라는 업계 글이 있습니다([Veo 이탈리아 사례](https://www.veo.com/article/video-analysis-transforms-italian-grassroots-football), 제조사 글이라 홍보 성격). 코치가 자원봉사자인 경우 설정 절차가 짧아야 한다는 뜻입니다.

## 3. 코치의 의사결정 시간과 알림 피로
- 코치의 경기 중 의사결정 단계와 정보원(주관, 객관, 분석가 상의)을 인터뷰한 연구가 있습니다([Aarons 외, 호주식 풋볼 코치](https://lida.sport-iat.de/dsv-wasserball/Record/4085005?lng=en)). 숙련 코치는 경기 모니터링보다 성과 평가와 행동 계획에 시간을 더 쓰고, 빠른 결정과 오래 쌓인 정보의 통합이 동시에 필요하다고 합니다([Roca 외, 축구 코치](https://www.journalofexpertise.org/articles/volume5_issue4/JoE_5_4_Roca_etal.pdf)). 알림 양이 결정에 미치는 영향을 직접 잰 연구는 확인 못 함.
- 임상 의사결정 지원 분야의 알림 피로 자료: 알림 빈도가 높을수록 수용률이 떨어지고, 우선순위 없이 모두 급해 보이면 중요한 것을 놓칩니다. 중단형 알림을 수동형 안내로 바꾸고 심각도를 단계로 나누자는 제안이 있습니다([PMC 논문](https://pmc.ncbi.nlm.nih.gov/articles/PMC6962089), [정리글](https://www.mindbowser.com/reduce-cdss-alert-fatigue-clinical-decision-support/)). 무시율 수치(49~96%)는 업체 글에서 인용한 값이라 원문 확인이 필요합니다. 의료 분야 자료이므로 축구에 그대로 옮길 수 없는 유추입니다.
- 산업 경보 관리 지침(EEMUA 191, ISA-18.2)을 인용한 자료들은 운전원이 오래 감당할 수 있는 새 경보를 시간당 약 12개(10분에 약 2개) 이하, 안정 상태 목표를 10분에 1~2개, 조치 한계를 10분에 3개 초과, 10분에 10개 초과를 경보 폭주로 봅니다([Emerson 정리](https://d1-live.emerson.com/documents/automation/article-alarm-management-by-numbers-deltav-en-38292.pdf), [ABB 백서](https://library.e.abb.com/public/72f20c70c7b44d889d463db81df5c38d/SCADA%20Alarm%20Management%20White%20Paper.pdf)). 2차 자료이고 표준 원문은 보지 못했습니다. 우리 알림은 분당 2.5회, 10분에 약 25개로 이 기준의 폭주 선을 두 배 넘습니다. 산업 현장 기준이므로 축구 코치에게 맞는 적정값은 아니며 현장 시험으로 정해야 합니다.

## 4. 확신도와 설명, 신뢰
- 정확하게 보정된 확신도를 보여 주면 결정 정확도가 약 20% 올랐지만, 보정이 틀린 확신도는 효과가 없었다는 사용자 연구(184명)가 있습니다. 확신 있는 추천은 틀려도 받아들이는 경향이 있었습니다([AAAI 2026](https://ojs.aaai.org/index.php/AAAI/article/view/38798)).
- 사용자는 보정이 틀린 확신도를 스스로 알아채기 어렵고, 알려 주면 과소 신뢰로 바뀌어 결정 품질이 오르지 않을 수 있습니다([arXiv 2402.07632](https://arxiv.org/abs/2402.07632v4)).
- 불확실성 표시는 도메인 지식이 적은 사람의 과신을 줄이는 데 효과가 있었습니다([NSF 논문 요약](https://par.nsf.gov/biblio/10539627-combining-uncertainty-information-ai-recommendations-supports-calibration-domain-knowledge)). 코치는 도메인 전문가라 효과가 다를 수 있습니다 (추정).
- 스포츠 분야: 설명 가능성이 신뢰와 의사결정 지원의 핵심이라는 주장과, 분석가가 통계 결과를 코치와 선수가 이해하는 이야기로 번역해야 한다는 보고가 있습니다([스포츠 과학 범위 검토](https://link.springer.com/article/10.1007/s44163-025-00709-8), [수영 코치 8명 인터뷰](https://www.mdpi.com/1424-8220/25/22/7047), [축구 모델 설명 연구](https://arxiv.org/html/2504.00767v1)). 정확도를 보여 주는 것이 코치의 신뢰를 높인다는 직접 연구는 확인 못 함.
- 시사점: 알림에 "확신도 90%" 같은 값을 임의로 붙이면 안 됩니다. 붙이려면 **종류별로 사람이 판정한 맞은 비율과 표본 수**(예: "이 종류는 지금까지 판정 9개 중 8개 맞음")를 쓰고, 표본이 적으면 "참고용"으로 표시하는 편이 안전합니다.

## 5. 실시간 시스템의 지연과 안정성 구조
- SRT 지연값은 수신 버퍼일 뿐이고 인코딩, 디코딩 등이 그 위에 쌓여 보통 1초에서 수 초가 더해집니다. 기본 지연 120ms는 모바일 4G에서 부족해서 더 크게 잡는 것이 낫다는 보고가 있습니다([4G 시험](https://medium.com/innovation-labs-blog/examining-srt-streaming-over-4g-networks-925e71c45cdf)). 왕복 시간의 약 4배가 일반 기준이고 셀룰러와 같이 손실이 큰 경로는 5~6배가 필요하다는 자료, 셀룰러에 500~1,000ms 또는 2,000ms를 권하는 자료가 서로 다릅니다([Medialooks 해설](https://articles.medialooks.com/srt-latency-buffer-explained-how-to-tune-srt-for-cellular-satellite-and-public-internet/)). 우리 경로의 최적값은 현장에서 재야 합니다 (확인 못 함).
- 비트레이트는 측정한 업로드 속도 가까이 쓰지 말고 낮추는 것이 먼저입니다(같은 해설).
- 영상 분석 파이프라인의 일반 구조: 읽기 스레드가 항상 최신 프레임만 유지하고, 마지막 프레임 시각을 감시하는 워치독이 일정 시간 프레임이 없으면 끊김으로 보고 자동 재연결합니다([Roboflow RTSP 처리](https://blog.roboflow.com/process-rtsp-streams/)). 파이프라인 전체를 통과하는 하트비트(1초 간격, 10초 안에 응답이 없으면 경고) 사례도 있습니다([Pipecat 하트비트 문서](https://docs.pipecat.ai/server/pipeline/heartbeats), 음성 파이프라인 사례라 유추). 큐 크기를 1로 두는 것만으로 최신 프레임이 보장되지는 않는다는 경고가 있습니다([Luxonis 포럼 글](https://discuss.luxonis.com/d/5622-camera-freeze-andor-stale-frame-read)).
- MediaMTX는 RTSP 자체는 지연을 만들지 않고, 읽는 쪽이 느리면 프레임을 버린다는 경고("reader is too slow")가 이슈로 보고됩니다. 비트레이트가 네트워크에 비해 높은 것이 흔한 원인으로 안내됩니다([MediaMTX 이슈 5162](https://github.com/bluenviron/mediamtx/issues/5162)). 이 프로젝트에서도 같은 경고로 프레임 40개를 버린 시험이 있었습니다 ([research-operations.md](research-operations.md)).

## 6. 이 프로젝트의 현재 상태 (근거: 위키와 기록)
근거: [live-service-audit.md](live-service-audit.md), [live-feedback.md](live-feedback.md), [research-operations.md](research-operations.md), [review-store-and-open-tasks.md](review-store-and-open-tasks.md).
- 처리 속도는 4분 영상 250초로 거의 실시간이고 분석기는 호출당 평균 13.7ms로 가볍습니다. 알림 조건이 시간을 요구해서(박스 침투 약 3초, 그 밖은 5~11초) 상황이 시작된 뒤 알림까지 구조적으로 수 초에서 11초가 걸립니다.
- 득점 장면을 재생한 결과 15초 이상 앞선 경고는 소수이고, 나머지는 너무 늦거나 득점 뒤이거나 알림이 없었습니다. 실제 라이브 4분 시험에서는 한 골 직전의 박스 안 선수가 검출되지 않아 박스 침투 알림이 나오지 않았습니다.
- 알림 정확도(사용자님 판정, 후반 25개): 맞음 18개(72%). 박스 침투 8/9, 침투 계열 2/2와 2/2, 고립 2/3, 라인 간격 3/6, 라인 하락 1/3(쓸모없음 1). 전반 61개는 아직 판정 없음. 표본이 작아 참고값입니다.
- 빈도: 분당 약 2.5회, 라인 간격과 라인 하락은 상태가 이어지면 90초마다 같은 알림 반복.
- 입력이 끊기면 스크립트가 종료되고 재연결과 "입력 없음" 표시가 없습니다(2026-11-17 수정 완료: 재연결, 예외 건너뛰기, 입력 없음 줄, 최신 프레임 큐. `live-service-audit.md`의 '수정함' 기록 참고. 이 문장은 조사 시점의 상태입니다).
- 전달 경로는 터미널, `alerts.jsonl`, 영상 하단 띠, 평가 화면뿐이고 코치용 화면과 푸시가 없습니다.
- 시작 절차(보정, 공격 방향, 팀, 값 입력)는 모두 사람이 입력하고 방향 오입력을 막을 확인이 없습니다. 전반과 후반 전환과 카메라 전환(이 경기는 24분 44초)에 재시작이 필요합니다.
- 카메라 이동 감시, 최신 프레임 입력 큐, FP16은 별도 실험 코드에만 있고 이 코드로 옮겨 검증하지 않았습니다.

## 7. 격차 분석: 필요한 것, 지금 없는 것, 개선 방법
난이도는 구현 양과 위험, 효과는 코치에게 쓸모가 생기는 정도에 대한 제 추정입니다(정량 근거 없음).

| 번호 | 필요한 것 (요구사항) | 지금 상태 | 개선 방법 (구체적 설계) | 난이도 | 효과 |
|---|---|---|---|---|---|
| R1 | 끊겨도 스스로 복구하고, 끊긴 사실이 코치에게 보임 | 종료되고 표시 없음 | 읽기 스레드가 최신 프레임만 유지, 마지막 프레임 시각 워치독(예: 3초 무입력이면 "입력 없음"), 지수 대기 재연결, 프레임 처리 예외는 그 프레임만 건너뛰고 횟수 기록, 알림 파일에 상태 행(하트비트) 기록 | 낮음 | 매우 큼 |
| R2 | 알림이 코치 눈앞에 닿는 화면 | 없음 | **벤치 화면**: 태블릿 브라우저에서 한 장짜리 화면. 큰 글씨 알림 한 개(나이 초 표시), 아래에 최근 3개, 상단 상태 띠(입력 OK, 마지막 프레임 몇 초 전, 보정 고정 여부, 지연 초, 분석 단계). `alerts.jsonl`을 서버가 푸시(SSE)하거나 1초 폴링. 소리와 진동은 빨강 단계만 | 중간 | 매우 큼 |
| R3 | 알림이 적고 우선순위가 있음 | 분당 2.5회, 모두 같은 비중, 반복 | 3단계: 빨강(지금 행동, 예: 상대 침투 허용, 박스 침투. 10분에 1개 안팎), 노랑(곧 필요, 고립 등), 회색(참고, 라인 간격과 라인 하락은 상태 변화 때 한 번). 같은 상태 지속은 반복하지 않고 해소 때 한 번. 알림 나이가 일정 초(예: 15초)를 넘으면 자동 폐기 | 낮음~중간 | 큼 |
| R4 | 알림을 얼마나 믿을지 알 수 있음 | 표시 없음 | 종류별 "판정 n개 중 m개 맞음" 표기(사용자님 판정 집계 사용, n이 10 미만이면 "참고용"), 정확도가 낮은 종류(라인 간격, 라인 하락)는 기본 회색 또는 끔. 임의의 퍼센트 확신도는 쓰지 않음 | 낮음 | 큼 |
| R5 | 지연 예산이 보장됨 | 측정 안 됨, 조건 자체가 3~11초 요구 | 예산(제안): 송출과 수신 1~2초, 디코딩과 검출과 추적 약 0.2초(측정 104ms), 분석기 0.02초, 알림 조건 시간 3~11초(가장 큼), 전달 0.5초. 영상에 시계 마커를 넣어 종단 간 지연 측정. 지연이 예산을 넘으면 "지연 중" 표시와 알림 폐기 | 중간 | 큼 |
| R6 | 시작 절차가 짧고 틀리기 어려움 | 값 6~8개 수동 입력 | 시작 점검 화면: 보정 파일 선택, 공격 방향은 킥오프 직후 몇 초 분석으로 "B팀이 화면 오른쪽 공격으로 보입니다. 맞습니까?" 확인(자동 추정 + 사람 확인), 팀 색은 분석된 두 군집을 보여 주고 확인, 점검 통과 전에는 알림 시작 안 함 | 중간 | 큼 |
| R7 | 전반과 후반, 카메라 전환에 끊기지 않음 | 프로세스 재시작 필요 | 하프타임 전환 버튼(방향, 보정 값 교체, 분석기 상태 초기화), 카메라 이동 감시를 연결해 이동 감지 시 알림 중지와 "카메라 이동, 재보정 필요" 표시 | 중간 | 중간 |
| R8 | 하프타임에 쓸 요약 | 수동으로 보고서 생성 | 전반 종료 신호로 자동 생성: 알림 3줄 요약(종류별 횟수와 시각), 팀 모양과 빈 쪽 한 장, 상대 침투 허용 장면 클립 링크. 기존 보고서 생성 코드(팀 전술 페이지, 장면 클립) 재사용 | 중간 | 큼 |
| R9 | 놓침이 적음(특히 박스 안) | 박스 안 선수 검출 누락 | 검출기 개선(AI Hub 섞은 학습은 끝나서 채택 안 함, 우리 영상 자료 `auto_only`가 유망하나 미채택), 경기 후 분석은 두 모델 합치기(효과 작아 보류됨) | 높음 | 큼 |
| R10 | 경기 후 개선 순환 | `/alerts` 판정 화면 있음 | 코치 의견 버튼(도움됨, 아님) 추가해 같은 판정 저장소로 모음, 경기 후 종류별 정확도와 빈도 자동 집계 | 낮음 | 중간 |
| R11 | 현장 네트워크 대비 | 시험 기록만 있음 | SRT 지연 설정을 현장에서 단계 조정(2,000ms에서 시작해 25%씩 낮추며 손실 확인), 비트레이트를 업로드 속도의 절반 이하로, MediaMTX 읽기 경고 모니터링 | 낮음 | 중간 |
| R12 | 접근 제어 | 평가 화면 무인증(시제품) | 벤치 화면은 같은 무선망 안에서만 열고, 공개 배포 전에는 인증을 추가해야 함 | 낮음 | 작음 |

저하 모드(R1과 R5의 설계, 제안)
- 단계 0 정상: 모든 알림.
- 단계 1 느림: 지연이 예산을 넘으면 선택 기능(확대 검출)을 끄고 노랑과 회색 알림을 중지, 빨강만 표시.
- 단계 2 입력 없음: 3초 이상 프레임이 없으면 화면에 "입력 없음" 표시와 재연결 시도. 이 동안 새 알림은 만들지 않음(오래된 알림이 최신처럼 보이지 않게).
- 단계 3 분석 중단: 예외가 반복되면(예: 10초에 5회) 분석을 멈추고 "분석 중단, 영상만 보여 줌"을 표시. 이전 알림은 나이와 함께 회색으로 남김.

## 8. 우선순위 로드맵 (제안)
| 기간 | 할 일 | 성공 확인 |
|---|---|---|
| 1주 | R1 재연결과 예외 처리와 하트비트(2026-11-17 구현 완료), R3 반복 알림 제거, R4 종류별 맞은 비율 표시, R2 벤치 화면 최소판(알림 한 개, 나이, 상태 띠) | 합성 장애 시험 통과, 반복 알림 0, 벤치 화면에서 알림이 1초 안에 보임 |
| 1개월 | R5 지연 측정과 폐기 규칙, 최신 프레임 입력과 카메라 이동 감시를 이 코드로 옮겨 이 경기로 재검증(FP16의 정확도 포함), R6 시작 점검 화면, R7 하프타임 전환, R8 하프타임 요약 자동 생성, `gk2-h1` 전반 판정 후 종류별 기준 조정, R11 현장 SRT 설정 시험 | 아래 9절의 1~3단계 합격 |
| 그 이상 | 검출기 개선 결과 반영(R9), 공 기반 알림(패스와 점유), 사이드라인 푸시 알림, 여러 카메라나 더 가까운 촬영(4K, 반쪽 촬영), 접근 제어, 다른 경기와 팀에서 일반화 검증 | 코치 시험 합격, 다른 경기에서도 정확도 유지 |

## 9. 현장 시험 계획과 합격 기준 (제안)
아래 수치는 이번 조사의 자료(알림 수 지침, 지연 자료)와 현재 측정값에서 제가 잡은 **제안 기준**이며 검증된 값이 아닙니다. 현장 결과를 보고 사용자님과 조정합니다.

| 단계 | 시험 | 합격 기준 (제안) |
|---|---|---|
| 0 책상 재생 | 저장된 경기 90분을 실시간 속도로 재생 | 입력 지연 p95 2초 이하, 1시간당 메모리 증가 5% 이하, 비정상 종료 0회, 반복 알림 0 |
| 1 장애 주입 | 루프백 스트림을 10초와 30초 끊기, 느린 처리 모의, 카메라 이동 모의 | 3초 안에 "입력 없음" 표시, 재개 후 15초 안에 정상 복구, 끊긴 동안 새 알림 0, 이동 시 알림 중지 |
| 2 훈련 경기 (분석가가 봄) | 폰 SRT 현장 송출, 코치 없이 사용자님이 벤치 화면을 보며 판정 | 가동률 95% 이상, 사건에서 화면까지 지연 중앙값 8초 이하 p95 15초 이하(영상 시계 마커로 측정), 전체 알림 10분당 4개 이하 빨강 10분당 1개 이하, 표시된 알림 판정 맞음 80% 이상(판정 40개 이상) |
| 3 연습 경기 (코치가 봄) | 코치가 벤치 화면을 사용, 경기 후 인터뷰 | 코치가 이해했다고 답한 알림 70% 이상, 도움됐다고 한 알림이 전후반 합쳐 3개 이상, 틀린 지시로 이어진 알림 0, 코치가 시작 절차를 10분 안에 끝냄 |
| 4 반복 | 서로 다른 경기장, 낮과 밤, 다른 팀 색 | 3단계 기준을 다른 환경에서도 유지, 방향이나 보정 오입력이 점검 화면에서 걸러짐 |

## 10. 불확실한 점과 확인하지 못한 것
- 상용 제품의 최신 기능과 지연 수치는 제조사 자료뿐이고 독립 측정은 없습니다. Metrica Sports와 Playermaker의 경기 중 기능은 확인하지 못했습니다.
- 경기 중 자동 전술 알림을 코치에게 밀어 주는 상용 사례, 코치의 알림 수용 한계를 직접 잰 연구는 찾지 못했습니다.
- 알림 빈도의 적정값은 의료와 산업 분야 기준에서 유추한 것이고 2차 자료입니다. 현장 시험으로 정해야 합니다.
- 하프타임 길이와 코치가 하프타임에 실제로 쓰는 시간에 대한 자료는 확인 못 함(요약의 분량 가정은 제 추정).
- 현재 프로젝트 쪽 수치는 표본이 작습니다(후반 판정 25개, 득점 장면 소수). 전반 알림의 정확도는 모릅니다.
- 이 코드로 별도 실험 코드의 최신 입력 큐, 카메라 이동 감시, FP16을 옮겼을 때의 효과는 확인하지 못했습니다.

## 출처 목록
- Veo 비교와 즉시 재생: https://www.veo.com/en-us/article/soccer-camera-systems-compared , https://www.veo.com/article/instant-playback-enhance-the-football-analysis
- Spiideo BenchMode: https://www.spiideo.com/news/bench-mode/
- Pixellot VidSwap: https://www.pixellot.tv/?p=167462
- Hudl Replay: https://www.hudl.com/blog/new-coach-tagging-feature-enhances-hudl-replay , https://www.hudl.com/blog/hudl-replay-live-output-reports
- Catapult: https://www.catapult.com/blog/pro-video-live-analysis-coaching-decisions-player-adjustments
- Playermaker: https://wearable-technologies.com/news/playermaker-a-complete-coaching-tool-for-football-teams
- 저지연 해설(Dolby): https://optiview.dolby.com/resources/blog/streaming/what-is-low-latency-video-streaming-the-complete-guide/
- 아마추어 사례(Veo): https://www.veo.com/article/video-analysis-transforms-italian-grassroots-football
- 코치 의사결정: https://lida.sport-iat.de/dsv-wasserball/Record/4085005?lng=en , https://www.journalofexpertise.org/articles/volume5_issue4/JoE_5_4_Roca_etal.pdf
- 알림 피로: https://pmc.ncbi.nlm.nih.gov/articles/PMC6962089 , https://www.mindbowser.com/reduce-cdss-alert-fatigue-clinical-decision-support/
- 경보 관리 지침 인용 자료: https://d1-live.emerson.com/documents/automation/article-alarm-management-by-numbers-deltav-en-38292.pdf , https://library.e.abb.com/public/72f20c70c7b44d889d463db81df5c38d/SCADA%20Alarm%20Management%20White%20Paper.pdf
- 확신도와 신뢰: https://ojs.aaai.org/index.php/AAAI/article/view/38798 , https://arxiv.org/abs/2402.07632v4 , https://par.nsf.gov/biblio/10539627-combining-uncertainty-information-ai-recommendations-supports-calibration-domain-knowledge
- 스포츠 설명 가능성: https://link.springer.com/article/10.1007/s44163-025-00709-8 , https://www.mdpi.com/1424-8220/25/22/7047 , https://arxiv.org/html/2504.00767v1
- SRT 지연: https://articles.medialooks.com/srt-latency-buffer-explained-how-to-tune-srt-for-cellular-satellite-and-public-internet/ , https://medium.com/innovation-labs-blog/examining-srt-streaming-over-4g-networks-925e71c45cdf
- 파이프라인 구조: https://blog.roboflow.com/process-rtsp-streams/ , https://docs.pipecat.ai/server/pipeline/heartbeats , https://discuss.luxonis.com/d/5622-camera-freeze-andor-stale-frame-read
- MediaMTX 이슈: https://github.com/bluenviron/mediamtx/issues/5162
