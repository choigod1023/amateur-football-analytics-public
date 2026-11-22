# 선수 데이터 탐색 학습 기록

데이터: [soccer-players-5fuqs](https://huggingface.co/datasets/Francesco/soccer-players-5fuqs). 메타데이터는 CC BY 4.0을 명시하지만 카드 태그는 일반 `cc`이며, 원본 방송 영상의 개별 권리는 확인하지 못했다. 학습 산출물이나 영상을 배포하지 않았다. 실제 COCO 분할은 train 114, valid 33, test 16장으로 메타데이터의 validation/test 숫자와 반대다.

분할 사이 정확히 같은 이미지 해시는 없었지만 valid 33장 중 25장, test 16장 중 10장은 train과 같은 파일명 접두어에서 번호 차이가 1 이하인 파일이 존재했다. 파일명 번호의 시간 의미는 검증되지 않았으므로 인접 장면 누출 가능성이지 확정은 아니다. 원본 경기 독립성은 증명되지 않았다.

YOLO11n의 원본 가중치(COCO person)를 640 입력으로 평가한 제공 valid 33장의 사람(선수+심판) 주석 379개 기준 P/R/mAP50/mAP50-95는 0.528/0.319/0.410/0.147이었다. Ultralytics 평가 기준이며 운영 conf 0.35의 수치가 아니다. 이 분할은 독립 성능으로 사용하지 않는다.

탐색 학습은 이름에 경기가 나타난 프레임만 사용해 Liverpool–Man City 17장 학습, Liverpool–Burnley 15장 검증, Tottenham–West Brom 14장 보류로 나눴다. 경기 미상 그룹은 제외했다. 두 그룹 사이 정확 이미지 해시 및 pHash 거리 5 이하 짝은 없었지만 원본 경기 독립성이나 기존 COCO 학습 데이터와의 중복을 입증하지 못했다. player와 referee를 person 하나로 합쳤고 football은 제외했다. 결과는 보류 14장, 사람 주석 197개에 대한 것이다.

| 모델 | Precision | Recall | mAP50 | mAP50–95 |
|---|---:|---:|---:|---:|
| 기존 YOLO11n | 0.817 | 0.884 | 0.863 | 0.331 |
| 탐색 학습 | 0.889 | 0.816 | 0.855 | 0.361 |

입력 640, batch 4, 최대 30 epoch 설정에서 16 epoch 조기 종료, 검증 기준 최적 4 epoch. 로그에 나온 학습 루프 시간은 약 22초(반올림), 표시된 `GPU_mem` 최대는 0.811G였다. GPU 프로세스 전체 peak VRAM은 별도로 계측하지 않았다. Recall과 mAP50이 하락해 일관된 개선이 아니며 작은 상관 표본이므로 **새 모델을 운영 후보로 선정하거나 기본 모델을 바꾸지 않았다.** 학습 실험 가중치와 재현 로그는 로컬 작업 폴더에만 보관한다.

[football-pitch-detection](https://huggingface.co/datasets/martinjolif/football-pitch-detection)은 카드에 CC BY 4.0, 317장, 32 keypoints로 표기한다. 라벨 317개 형식은 확인했지만 원본 경기 영상 권리와 독립 경기 분리는 미확인이다. 카드가 한 경기장/경기를 설명하므로 다른 경기 일반화 평가 자료로 쓰지 않았다. 경기장 보정 또는 팀 분류 모델을 추가 학습하거나 교체하지 않았다.
