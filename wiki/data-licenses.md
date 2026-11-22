# 자료와 도구의 이용 조건 (2026-11-16 조사)

이 문서는 법률 자문이 아닙니다. **확인된 문구**와 **해석**을 나누어 적었고, 불확실한 부분은 "확인 못 함, 담당 기관에 문의 필요"로 표시했습니다. 서비스화(코치에게 제공, 판매) 전에 담당 기관 문의나 전문가 확인이 필요합니다.
조사 방법: 로컬에 이용 약관 문서가 있는지 찾았고(`work/aihub-official/`에는 내려받기 도구와 인증 파일뿐이며 이용 약관 문서는 없음, 인증 파일은 열지 않음), 공식 페이지와 데이터 카드를 읽었습니다. 웹 페이지는 요약기를 거쳐 읽었으므로 조항 번호나 표현이 원문과 다를 수 있어, 서비스화 전에 원문을 직접 확인합니다.

## 1. 자료별 이용 조건

| 자료 | 확인된 문구 | 해석과 우리 사용 | 출처 |
|---|---|---|---|
| AI Hub 71482 (데이터셋 페이지 제목: 전술 판정 영상 데이터(축구), 구축 기관 컨소시엄) | 데이터셋 페이지에 라이선스와 상업 이용 가능 여부는 **명시되어 있지 않음**. 신청 자격은 내국인만, 다운로드 전 승인이 필요. | 개별 조건은 AI Hub 공통 이용정책을 따른다고 보는 것이 자연스럽지만 **확인 못 함**. 우리는 승인을 받아 로컬에서만 연구 학습에 사용. | [데이터셋 페이지](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71482) |
| AI Hub 공통 이용정책 | 영리, 비영리 연구와 개발 목적으로 활용할 수 있다는 취지의 소개 문단. 인공지능 학습모델의 학습용으로만 사용(제4항). 판매 등 상업적 이용은 수행기관과 별도 협의(제7항). 제3자에게 열람, 제공, 양도, 대여, 판매 금지(제5항). 국외 반출과 국외 소재 주체의 이용은 별도 합의(제2, 3항). 이 데이터로 만든 2차적 저작물에도 NIA 사업 결과임을 표시(제1항). 사용자가 만든 AI 모델의 소유와 이용에 관한 조항은 **없음**. 소개 문단은 사업 결과물(AI 응용모델 포함)의 권리가 수행기관과 NIA에 있다고 함. | 조항 번호는 요약 과정에서 매긴 번호일 수 있음. **모델 가중치를 서비스로 제공하는 것이 상업적 이용에 해당하는지는 문구만으로는 판단할 수 없음.** 무료로 코치에게 제공해도 제3자 제공과 상업적 이용 경계가 불분명. | [AI Hub 이용정책](https://aihub.or.kr/intrcn/guid/usagepolicy.do) |
| SoccerTrack v1 (영상과 위치 주석) | GitHub 페이지에 코드와 데이터의 라이선스 문구가 **없음**(LICENSE 파일 링크만 있고 본문 미확인). 참가자의 서명된 사전 동의가 있었다는 언급만 있음. 프로젝트 문서는 Kaggle 쪽이 LGPL 3.0으로 표기한다고 기록. | 상업 이용, 재배포 가능 여부 **확인 못 함**. 우리는 연구와 시험 평가에만 사용하고 가중치는 배포하지 않음. | [GitHub](https://github.com/keisuke198619/SoccerTrack), 프로젝트 문서 `docs/soccertrack-landmark-evaluation.md` |
| SoccerNet (SN-GSR 포함) | 데이터에 NDA가 필요하고 재배포 방지가 목적. 데이터는 상업 목적이 아님. 영상의 저작권은 유럽 리그에 있음. 학습에 쓰는 것은 허용. SN-GSR 개별 조건과 학습된 모델의 재배포 가능 여부는 이 페이지에 **없음**. | 비상업 연구용. 이 자료로 학습한 가중치는 운영에 쓰지 않는 것이 이미 프로젝트 원칙(`docs/team-pair-research.md`). | [SoccerNet FAQ](https://www.soccer-net.org/faq) |
| martinjolif/football-player-detection (선수와 공 상자) | 데이터 카드에 cc-by-4.0. 인용 요청. 원본 경기, 방송사, 촬영 허락, 촬영된 사람의 동의 여부는 **명시되지 않음**. | CC BY 4.0은 출처 표시를 조건으로 상업 이용을 허용하는 라이선스지만, 원본 영상 권리가 별개라서 위험이 남음. 현재 학습에는 쓰지 않음(공 연구 참고). | [데이터 카드](https://huggingface.co/datasets/martinjolif/football-player-detection) |
| Francesco/soccer-players-5fuqs (Roboflow 100) | 데이터 카드에 "cc"만 있고 버전 없음. 상세는 Roboflow Universe 원본 페이지를 보라고 함. 이미지 출처와 동의 여부 **명시되지 않음**. | 조건 **확인 못 함**. 탐색 학습 한 번만 했고 채택하지 않음(`docs/training-evaluation.md`). | [데이터 카드](https://huggingface.co/datasets/Francesco/soccer-players-5fuqs) |
| 사용자님이 직접 만든 라벨(그린 상자, 판정, person-check) | 우리가 만든 자료. 영상 자체(휴대폰 영상)에는 촬영된 선수와 관중이 있음. | 선수 동의와 개인정보(얼굴, 이름) 문제는 별도. 영상을 외부 서비스로 보내지 않는 현재 원칙이 맞음. | 프로젝트 원칙 |
| Ultralytics YOLO (코드와 가중치 학습 도구, 설치 버전 8.4.208) | 설치된 패키지 메타데이터에 AGPL-3.0. 공식 안내는 학습한 모델도 기본적으로 AGPL-3.0이고, 상업 이용은 별도 Enterprise 라이선스를 받는 구조라고 함. 사용자가 어느 라이선스가 적용되는지 스스로 판단할 책임이 있다고 함. | **네트워크로 서비스를 제공하거나 코치에게 배포하면 AGPL 의무(소스 공개 등)가 문제될 수 있음.** 폐쇄형 상업 제공은 Enterprise 라이선스가 필요하다는 것이 공식 설명. 경계 사례(네트워크 제공)는 제3자 의견이 갈리므로 **확인 못 함, 담당 기관에 문의 필요**. | [Ultralytics 라이선스](https://www.ultralytics.com/license), 설치 파일 `outputs/football-coach-server/.venv/Lib/site-packages/ultralytics-8.4.208.dist-info/METADATA`, 제3자 의견: [Roboflow 블로그](https://blog.roboflow.com/why-agpl-3-0-is-a-risk-for-computer-vision-teams/) |

## 2. 현재 사용 방식이 위반 소지가 있는가

판단 기준: 지금은 **로컬 연구, 개발, 평가**이고 서비스나 판매가 아닙니다.
- AI Hub: 승인된 계정으로 내려받아 로컬에서만 학습에 사용하고, 영상과 가중치를 외부로 보내지 않습니다. 이는 이용정책의 "학습용" 범위와 맞아 보입니다. 위험이 되는 경우: (a) 영상이나 가중치를 클라우드(특히 국외)에 올리는 경우, (b) 학습한 모델을 다른 사람에게 제공하는 경우. 두 경우 모두 지금은 하지 않았습니다.
- 학습한 가중치를 다른 기기나 사람에게 전달하는 것은 제3자 제공으로 해석될 여지가 있어서 승인 전에는 하지 않습니다.
- SoccerNet, SoccerTrack: 평가와 시험만 했고 가중치를 운영에 연결하지 않았습니다(문서 기록 근거).
- Ultralytics AGPL: 검토 서버와 라이브 분석이 네트워크로 접근 가능한 형태(HTTP, 무인증 시제품 상태)라서, **서비스를 다른 사람에게 제공하는 순간** 의무가 생길 수 있습니다. 지금은 사용자님 본인의 연구 용도입니다.
- 결론: 현재 방식에서 명백한 위반은 발견하지 못했습니다. 단, 이것은 문구와 기록에 근거한 것이며 법적 확인이 아닙니다.

## 3. 서비스화(코치에게 제공) 때 필요한 조치

1. **AI Hub 수행기관 문의**: 학습한 가중치를 유료나 무료 서비스에 쓰는 것이 허용되는지, 제7항의 상업적 이용 협의 절차가 무엇인지 문의합니다. 문의처는 데이터셋 페이지에 있습니다(이 문서에는 개인 연락처를 적지 않음).
2. **자체 자료 확대**: AI Hub 의존도를 줄이기 위해 사용자님 영상으로 직접 만든 라벨(그린 상자, person-check 판정)을 계속 늘립니다. 이 자료는 권리가 사용자님께 있습니다(선수 동의는 별도).
3. **대체 자료**: 라이선스가 명확한 자료(예: 상업 이용이 명시된 공개 데이터)를 찾아 비교합니다. martinjolif 자료는 CC BY 4.0이지만 원본 영상 권리가 불확실하므로 사용 전 추가 확인이 필요합니다.
4. **Ultralytics**: 제공 방식이 정해지면 AGPL 준수(소스 공개)와 Enterprise 라이선스 중 선택하거나, 상업 이용이 가능한 다른 검출 구현(예: 허용적 라이선스의 모델)으로 바꾸는 것을 비교합니다.
5. **출처 표시**: AI Hub 데이터로 만든 결과물에는 NIA 사업 결과임을 표시하는 의무가 있을 수 있습니다(제1항 취지).
6. **개인정보**: 영상 속 선수와 관중의 동의와 보관 방식을 정하고, 외부 서비스로 영상과 이름을 보내지 않는 원칙을 유지합니다.

## 4. 권고

- 지금 하는 연구 학습은 계속해도 됩니다. 다만 가중치를 외부에 전달하거나 클라우드에 올리지 않습니다.
- 서비스화를 계획하기 전에 먼저 (1) AI Hub 수행기관 문의와 (2) Ultralytics 라이선스 방침 결정을 합니다. 이 둘의 답에 따라 AI Hub 학습을 계속할 가치가 달라집니다.
- 문의 결과가 부정적일 경우를 대비해, 자체 라벨 확대를 병행합니다.
- 이 문서의 요약은 웹 페이지 요약기를 거친 것이므로, 문의 전에 원문(이용정책, 데이터셋 페이지)을 직접 읽어 확인합니다.

## 출처
- [AI Hub 71482 데이터셋 페이지](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71482)
- [AI Hub 이용정책](https://aihub.or.kr/intrcn/guid/usagepolicy.do)
- [SoccerTrack GitHub](https://github.com/keisuke198619/SoccerTrack)
- [SoccerNet FAQ](https://www.soccer-net.org/faq)
- [martinjolif/football-player-detection](https://huggingface.co/datasets/martinjolif/football-player-detection)
- [Francesco/soccer-players-5fuqs](https://huggingface.co/datasets/Francesco/soccer-players-5fuqs)
- [Ultralytics 라이선스](https://www.ultralytics.com/license)
- [Roboflow: AGPL-3.0 위험(제3자 의견)](https://blog.roboflow.com/why-agpl-3-0-is-a-risk-for-computer-vision-teams/)

## 5. 알림 규칙 타당성 시험용 공개 추적 자료와 검증 모델 (2026-11-17 조사)
요약기를 거친 읽기이므로 원문과 다를 수 있습니다. 법률 자문이 아닙니다. 모두 연구 확인용으로만 쓰고 재배포하지 않습니다.
| 자료 | 확인된 문구와 내용 | 해석 |
|---|---|---|
| Metrica Sports 샘플 ([GitHub](https://github.com/metrica-sports/sample-data)) | 라이선스 이름은 없고 "자료를 책임 있게 사용하라, 공개적으로 쓰면 출처를 밝혀라"라는 문구만 있음. 3경기, 추적과 이벤트(동기화됨). | 연구 확인용 사용은 문제없어 보이나 상업 이용은 **확인 못 함**. 출처 표시를 지킴. |
| SkillCorner 공개 자료 ([GitHub](https://github.com/SkillCorner/opendata)) | MIT 라이선스 파일이 연결되어 있으나 본문은 확인 못 함. 출처 표시는 "요청". 상업 이용 여부는 명시하지 않고 상업 문의는 회사로 안내. 호주 A리그 2024/25 10경기, 중계 영상 기반 추적(초당 10프레임)과 동적 이벤트, 경기 단계 구분. | 연구 확인용으로 사용. 상업 이용 전에 확인 필요. |
| 검증 모델 3종 (모델 카드에서 확인) | Grounding DINO tiny(IDEA-Research), OWLv2 base(Google), SigLIP base(Google) 모두 `apache-2.0`. OWLv2 카드는 "연구자를 위한 연구 산출물"이라고 서술하나 별도 사용 제한은 적지 않음. | AI Hub나 Ultralytics(AGPL)와 달리 서비스에 쓰는 것을 막는 조항은 보이지 않음(모델 카드 기준, 원문 라이선스 전문은 확인 못 함). |
