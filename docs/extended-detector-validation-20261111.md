# 추가 경기 학습 및 광각 구간 검증 — 2026-11-11

## 구성과 방법

기존 SoccerTrack 광각 경기 0120_0150.mp4의 프레임 350부터 2프레임 간격으로 100개를 읽었다. 추적 상자와 선수 정답 상자를 IoU 0.5 이상으로 탐욕적으로 매칭했다. 이 장면의 영상이나 정답은 새 학습·임계값 선택에 넣지 않았지만, 이전 실험에서도 같은 경기를 사용한 바 있어 완전히 독립적인 최종 시험으로 볼 수 없다. 네트워크 송출 시험도 아니다. 100프레임은 원본 구간 전체가 아니다.

AI Hub 다른 경기 9개에서 156프레임을 추출하여 기존 일반 YOLO11n 가중치에서 CPU 3 epoch로 학습했다. 개발용은 다른 318번 경기 6프레임이다. 7개 경기는 150프레임 간격으로 각각 20개, 나머지 2개 경기에서 기존 16개를 사용했다. 데이터는 9개 경기지만 촬영 조건과 경기 표본은 여전히 제한적이다. 선수와 심판을 모두 person으로 학습했으며 역할 및 팀 분류용 학습이 아니다. 사용 권한 제한 자료와 결과 가중치는 로컬에만 보관한다. 원본 사전학습 데이터의 전체 이력은 확인하지 못했다.

6개 개발 프레임의 타일 탐지 결과에서 IoU 0.5 기준 F1이 가장 높은 탐지 점수 0.8을 선택했다. 개발 라벨 누락이나 경기 조건 차이에 영향을 받으며 이 선택의 유효성은 미검증이다. 비교 모델의 0.95는 이전 실험에서 별도로 선택한 점수다. 따라서 결과 차이는 학습과 임계값의 결합 효과이며 어느 쪽이 원인인지는 확인하지 않았다.

## 결과

| 모델 | 매칭 / 정답 | 매칭 / 예측 | 재등장 동일 / 변경 ID | 처리 속도 |
|---|---:|---:|---:|---:|
| 일반 모델, 0.35 | 262 / 2200 (11.91%) | 262 / 1069 (24.51%) | 15 / 7 | 6.22 fps |
| 기존 9경기 51프레임 모델, 0.95 | 729 / 2200 (33.14%) | 729 / 2004 (36.38%) | 52 / 16 | 7.13 fps |
| 기존 모델, 낮은 점수 복구 사용 | 832 / 2200 (37.82%) | 832 / 2409 (34.54%) | 47 / 18 | 5.61 fps |
| 새 9경기 156프레임 모델, 0.8 | 453 / 2200 (20.59%) | 453 / 1609 (28.15%) | 31 / 11 | 6.08 fps |

매칭되지 않은 예측에는 심판, 정답 누락, 잘못된 상자가 섞일 수 있어 전부 오탐으로 단정하지 않는다. 재등장 수치는 정답이 계속 보이지만 검출 매칭이 끊긴 뒤 다시 매칭된 경우만 셌으며 표준 IDF1이나 화면 밖 위치 정확도가 아니다. 속도는 오프라인 프레임 건너뛰기 실험 값이며 동시 서버 부하와 실시간 전송 지연을 보장하지 않는다. 새 모델의 GPU 메모리 값은 측정 기록이 없어 보고하지 않는다.

추가 학습 모델은 기존 모델보다 낮은 점수를 기록해 승격하지 않았다. 낮은 점수 복구는 이 구간에서 정답 매칭을 늘리는 동시에 예측 대비 매칭 비율과 ID 유지 수치가 악화되어 기본값으로 채택할 근거가 부족하다. 팀, 골키퍼, 미니맵, 화면 밖 위치, 코칭 정확도는 이 실험에서 측정하지 않았다. 서로 다른 미사용 경기와 야간 영상을 별도로 확보하고, 완전하게 주석한 평가 구간에서 역할별 오탐 및 IDF1/HOTA를 비교해야 한다.

## 재현

Python은 기존 서버 프로젝트의 가상환경을 사용했다. `work` 경로는 상위 프로젝트 폴더에 있다. 기존 결과 폴더는 덮어쓰지 않는다.

```powershell
$py = '..\football-coach-server\.venv\Scripts\python.exe'
& $py scripts\prepare_other_match_frames.py --root ..\.. --manifest ..\..\work\aihub-role-study\manifest-seven.json --prior ..\..\work\byte-tracker-new-training\independent-dataset --output ..\..\work\detector-extended-reproduction\dataset
& $py scripts\train_extended_matches.py --dataset ..\..\work\detector-extended-reproduction\dataset --pretrained ..\football-coach-server\yolo11n.pt --project ..\..\work\detector-extended-reproduction\runs
& $py scripts\select_extended_threshold.py --dataset ..\..\work\detector-extended-reproduction\dataset --weights ..\..\work\detector-extended-reproduction\runs\nine_games_156\weights\best.pt
& $py scripts\evaluate_wide_tracking.py --video ..\..\work\field-like\soccertrack-v1\match-20200220\0120_0150.mp4 --labels ..\..\work\field-like\soccertrack-v1\match-20200220\0120_0150.csv --weights ..\..\work\detector-extended-reproduction\runs\nine_games_156\weights\best.pt --device 0 --start 350 --frames 100 --stride 2 --confidence 0.8
```

학습의 난수와 실행 환경에 따라 결과가 달라질 수 있다. 준비 스크립트는 파일명과 매니페스트를 확인하지만 원본 영상 내용의 독립성 자체를 증명하지 않는다. 권리 및 라이선스는 프로젝트의 기존 데이터 출처 문서를 따른다.
