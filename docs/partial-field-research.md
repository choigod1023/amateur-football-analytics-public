# 경기장 부분 표식 학습 실험

이 코드는 연구용이며 서버의 자동 보정 경로에 연결하지 않는다. 예측 결과를 승인된 호모그래피나 실제 미니맵 좌표로 사용하지 않는다.

## 방법과 결과

AI Hub 축구 데이터 71482의 q6c 단일 경기에서 페널티 구역 교차점 2개 이상이 보이는 951개 프레임을 학습하고, 다른 Vss 경기에서 네 점이 모두 있는 200개 프레임을 개발 평가했다. 각 이미지의 네 교차점 중 없는 점은 손실에서 제외한다. ImageNet 사전학습 ResNet-18을 사용해 40 epoch 학습했으며 ImageNet 평균과 표준편차로 정규화했다. 독립 평가 데이터가 아닌 개발 자료를 반복 사용했으며 한 경기의 인접 프레임은 서로 상관되어 있다.

2026-11-11 별도 실험의 각 프레임에서 네 점 평균 픽셀 오차 중앙값은 **77.83 px**, 90백분위는 **159.61 px**였다. GPU 연산 등의 비결정성으로 실행 결과가 달라진다. 원본 해상도 1920×1080 기준이고, 교차점 정답과 비교한 픽셀 거리이지 미니맵의 미터 단위 위치 오차가 아니다. 이전의 완전한 네 점만 사용한 단일 경기 모델은 다른 개발 프레임 표본에서 중앙값 143.7 px이었다. 프레임 표본이 달라 두 수치의 차이를 모델의 개선량으로 해석할 수 없다. 운동장 전체 범위, 야간, 카메라 이동, 영상 간 정확도, 선수 발 위치 오차와 실제 코칭의 유효성은 검증되지 않았다.

후속 단계는 촬영 조건과 경기 장소가 다른 영상을 경기 단위로 나누고 별도 정답으로 보정 실패율, 미터 오차, 신뢰도와 오류 검출률을 측정하는 것이다. 충분한 근거가 없으므로 자동 승인은 금지한다.

## 실행

이 프로젝트의 기존 환경과 로컬 AI Hub 데이터, 사전학습 가중치가 필요하다. `scripts/experimental_partial_field.py`에 표시된 경로를 확인한 뒤 프로젝트 루트에서 실행한다.

```powershell
& '..\football-coach-server\.venv\Scripts\python.exe' scripts\experimental_partial_field.py
& '..\football-coach-server\.venv\Scripts\python.exe' -m pytest tests\test_partial_field_loss.py -q
```

실행마다 상위 작업 공간의 `work/partial-field-runs/<고유 ID>/`에 결과와 가중치를 따로 쓴다. 기존 결과를 덮어쓰지 않으며 데이터와 가중치는 저장소에 포함하지 않는다. 기존 결과는 `work/field-auto-normalized-20261111/results.json`에 있다.

데이터는 승인받은 [AI Hub 축구 데이터 71482](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71482)이며 이용 조건에 따른 사용이 필요하다. 사전학습 모델 전처리와 출처는 [Torchvision ResNet-18 문서](https://pytorch.org/vision/stable/models/generated/torchvision.models.resnet18.html)를 참조한다. 데이터와 모델 가중치의 배포 및 상업 이용 권한은 각각 별도 확인해야 한다.
