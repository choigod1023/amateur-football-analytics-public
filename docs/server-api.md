# 서버 API와 설정 (이전 README)

고정 카메라 MP4 또는 MediaMTX RTSP 입력을 YOLO11n 사람 탐지와 ByteTrack 임시 ID로 처리합니다. 탐지는 축구 선수 전용이 아니며 심판·골키퍼를 구별하지 못합니다. 색상 분류에도 오인 가능성이 있으므로 측정값을 전술적 사실로 단정하지 마세요. 선수 이름·등번호·점유율·공 위치는 제공하지 않습니다. 이 소프트웨어는 검증 전 시제품입니다.

## 환경과 설치

확인 환경: Windows 빌드 26200, Ryzen 7 7800X3D, RTX 5070 12GB, 드라이버 610.88, Python 3.14.3, uv. 독립 `.venv`에서 PyTorch 2.14.1+cu130의 CUDA 장치 인식을 확인했습니다. 시스템 FFmpeg 명령은 없지만 OpenCV에 포함된 FFmpeg로 MP4를 읽었습니다.

PowerShell에서 프로젝트 폴더로 이동 후:

```powershell
uv venv --python 3.14
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
uv pip install --python .venv\Scripts\python.exe --index https://download.pytorch.org/whl/cu130 --force-reinstall torch torchvision
.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

CUDA 패키지 인덱스의 가용 버전은 달라질 수 있습니다. 최초 실행 시 `yolo11n.pt`를 프로젝트 폴더에 내려받습니다. 무게 파일 출처를 신뢰할 수 없으면 사용하지 마세요. 의존성은 고정 잠금 파일이 없어 새 설치 결과는 달라질 수 있습니다.

### 별도 출처 대시보드 연결

기본적으로 브라우저의 다른 출처에서 호출할 수 있도록 CORS를 허용하지 않습니다. 별도로 운영하는 맥북 대시보드가 교차 출처로 API에 접근해야 하는 경우에만 서버를 시작하기 전에 `FOOTBALL_CORS_ORIGINS`를 실제 대시보드의 출처로 설정합니다. 예를 들어 맥북 브라우저에서 `http://localhost:3000`으로 열린 개발 대시보드라면 해당 **브라우저의 주소**가 출처입니다.

```powershell
$env:FOOTBALL_CORS_ORIGINS = 'http://localhost:3000'
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

여러 출처는 쉼표로 구분하고 URL 경로와 끝의 `/`는 빼세요. 와일드카드, 자격 증명, `null` 출처는 허용하지 않으며 잘못된 설정은 시작 시 거부합니다. 실행 중인 프로세스에는 설정이 자동으로 반영되지 않습니다. 별도 게이트웨이를 사용하는 경우 **게이트웨이 프로세스에도** 같은 환경변수를 설정해야 합니다. CORS는 브라우저의 출처 검사일 뿐 인증이나 암호화가 아니며, 실제 네트워크 접근에는 별도의 접근 제어와 보안 연결이 필요합니다. HTTPS 대시보드는 평문 HTTP API를 브라우저에서 호출할 때 혼합 콘텐츠 차단이 발생할 수 있습니다. 이 옵션은 서버 바인딩이나 방화벽을 변경하지 않습니다.

다른 PowerShell에서:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/status
Invoke-RestMethod http://127.0.0.1:8000/api/v1/analysis
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/start -ContentType 'application/json' -Body '{"source":"C:/absolute/path/match.mp4","config":"config.json"}'
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/stop
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m tests.smoke_video
```

서버는 프로세스 하나만 사용하세요. start는 서버에서 접근 가능한 파일 경로 또는 RTSP URL만 받습니다. EOF면 idle, 연결 실패·끊김은 error입니다. 재연결은 수동으로 다시 start합니다. 마지막 분석은 EOF 후 남지만 error 시 비웁니다. 분석 시각과 status를 확인하세요. 종료 명령은 비동기이며 디코더 타임아웃까지 기다릴 수 있습니다.

실시간 RTSP의 `/api/v1/status`에는 호환 가능한 추가 필드 `input_stalled`와 `decoded_frame_age_ms`가 있습니다. 디코딩된 프레임을 한 번 이상 받은 뒤 3초 넘게 새 프레임이 없으면 상태는 기존 `running`을 유지하며 `input_stalled: true`와 입력 지연 안내를 표시합니다. 입력 오류가 확정되면 기존대로 `error`입니다. 첫 프레임을 기다리는 동안과 파일 입력에는 경과 시간이 null입니다. 이 시간은 로컬 디코딩 이후 경과로, 아이폰 촬영 시각 또는 종단 간 지연이 아닙니다. 네트워크·디코더에 오래된 프레임이 남아 나중에 디코딩되면 이 경고가 잠시 해제될 수 있어 정상 송출이나 최신성을 보증하지 않습니다.

## 좌표·분류 계약

`home`은 사용자가 지정한 홈팀, `away`는 어웨이팀, `unknown`은 미분류입니다. `config.json`의 `team_hsv`에 두 팀의 상의 대표 색을 OpenCV HSV `[H 0..179, S 0..255, V 0..255]`로 수동 입력합니다. 밝은 무채색 유니폼도 비교하되 어두운 영역과 비슷한 색은 분류를 보류합니다. `team_colors`는 지정된 HSV를 변환한 RGB 색상 `#rrggbb`이며 미지정은 null입니다. 표시 색상은 유니폼 식별이 검증되었다는 뜻이 아닙니다. 둘 중 하나라도 없거나 유사도가 낮거나 두 색 차이가 작으면 unknown입니다. 잔디·심판·골키퍼 색 혼입을 막는 완전한 장치는 없고, ID는 가림과 화면 이탈 때 바뀔 수 있습니다. 양 팀 모두 실제 장면에서 검증하지 않았다면 지표를 신뢰하지 마세요. [야간 영상 조사와 평가 계획](docs/night-evaluation.md)을 참고하세요.

선택적으로 `"team_classifier": "guarded_palette"`를 지정하면 무채색과 유채색 유니폼의 픽셀 비율을 사용해 분류하며 주변 색과 구분이 부족하면 보류합니다. 두 팀이 모두 무채색 또는 모두 유채색이면 보류합니다. 이 실험적 설정은 기존 기본값 `"median"`보다 더 많은 결과를 `unknown`으로 남길 수 있고 현장별 정확도를 검증하지 않았습니다. 유니폼 무늬, 심판·골키퍼, 잔디 및 다른 선수의 겹침은 오분류를 일으킬 수 있습니다. [예비 비교](docs/team-colour-evaluation.md)를 참고하세요.

실험 설정 `"temporal_team_consensus": true`를 지정하면 같은 추적 ID의 연속 세 관측이 같은 팀일 때만 해당 팀을 표시합니다. 관측이 없거나 `unknown`, 팀 충돌, 같은 ID 중복, 1초 초과 간격이 생기면 누적을 버리고 다시 보류합니다. 입력 시작과 재연결에도 초기화합니다. 기본값은 false입니다. 이는 기존 팀 분류 결과의 일시적 안정화 실험이며 유니폼 기준색이나 모델 가중치를 학습·수정하지 않습니다. 일관된 오분류나 추적 ID가 다른 사람에게 바뀌는 경우를 막지 못하며, 첫 두 관측은 미분류로 남습니다. 선수 수가 일시적으로 줄어들 수 있어 지표 활용 전 실제 영상으로 별도 평가해야 합니다.

`config.json`의 `own_team`을 `home` 또는 `away`로 지정하면 폭·길이 지표와 관련 코칭의 대상 팀이 바뀝니다(미지정 기본값 `home`). 다음 입력을 시작할 때 적용됩니다. 대시보드의 표시 색상 선택은 분류 기준색이나 우리 팀을 변경하지 않습니다.

예시 형식만 보여 주며 실제 측정값은 아닙니다. `calibration`은 동일한 순서의 경기장 평면 위 네 기준점입니다. 움직이거나 줌이 변하는 카메라에는 적용하지 마세요.

```json
{
  "model": "yolo11n.pt", "confidence": 0.35, "image_size": 640, "team_classification_validated": false,
  "team_hsv": {"home": [0, 220, 200], "away": [110, 220, 200]},
  "calibration": {
    "validated": false, "image_size_px": [1920,1080], "field_size_m": [105, 68],
    "image_points": [[100,100],[900,100],[900,600],[100,600]],
    "field_points_m": [[0,0],[105,0],[105,68],[0,68]]
  }
}
```

`x,y`는 지정한 경기장 좌상단 `(0,0)`에서 우하단 `(1,1)`으로 증가하는 무차원 좌표입니다. x는 길이 방향, y는 폭 방향이며 공격 방향은 자동 변경하지 않습니다. 영상의 선수 박스 아래 중앙을 발 위치로 근사합니다. 기준점 사각형 밖이거나 보정이 없으면 좌표는 null입니다. 독립 기준점으로 검증한 뒤에만 사용자가 `calibration.validated`를 true로 설정해야 좌표가 나옵니다. 폭·길이는 좌표가 있는 지정 팀 선수 2명 이상의 y·x 범위를 경기장 실제 크기로 환산한 **화면 내 관측치**이며 팀 전체를 대표하지 않습니다. 현재는 사용자가 수동 모드에서 역할과 팀을 확인해야 지표가 나옵니다. `team_classification_validated`만으로 선수 역할까지 확인되지는 않습니다.

`/api/v1/analysis`의 선택적 추가 필드 `coaching_diagnostics`는 마지막 분석 프레임의 관측 가능 상태와 보류 사유를 보여줍니다. `not_started`는 아직 프레임이 없다는 뜻이고, `blocked`의 `reasons`는 `calibration_unavailable`, `team_references_missing`, `team_classification_unverified`, `insufficient_located_team_members` 중 해당 항목입니다. 자세한 보정 사유는 기존 `calibration_status`를 확인하세요. `observation_available`은 현재 폭·길이 계산 조건만 충족했다는 뜻이며 정확성 확인이나 전술 판정이 아닙니다. 사람 탐지기는 선수와 심판·골키퍼를 구분하지 못하므로 `player_roles_unverified` 경고가 항상 포함됩니다. 화면 밖 선수도 관측되지 않습니다. 현재 입력이 실행 중인지는 별도로 `/api/v1/status`를 확인하세요. 기존 계약 필드는 바꾸지 않았습니다.

실제 영상에서 사용자 팀 정보와 보정이 없을 때의 보류 동작은 `python scripts/evaluate_unconfigured.py --model <가중치> <영상1> [영상2 ...]`로 재현할 수 있습니다. AI Hub 검증 경기 네 편의 각 연속 25프레임을 로컬에서 실행했을 때 추적 사람 수는 프레임당 평균 8.40·3.88·9.52·5.28명이었고, 팀·보정 설정이 없어 100프레임 모두 좌표와 코칭을 보류했습니다. 추적 수는 인식 정확도나 FPS가 아니며 해당 자료는 AI Hub 이용 조건을 따릅니다.

보정은 원본 프레임의 해상도에 종속됩니다. `image_size_px`에 기준점을 표시한 원본 영상의 `[너비, 높이]`를 넣어야 하고 현재 프레임과 다르거나 크기가 누락되면 좌표·지표는 null로 보류됩니다. 이전 설정에도 기존 필드는 유지되지만 `image_size_px`를 추가하기 전까지 좌표가 나오지 않습니다. API의 추가 필드 `calibration_status`는 `not_configured`, `not_validated`, `resolution_unverified`, `resolution_mismatch`, `active`를 제공합니다. `active`는 크기와 사용자의 검증 표시가 일치함을 뜻할 뿐 보정 정확도·고정 카메라 여부를 보장하지 않습니다. 기본 설정은 같은 해상도의 카메라 이동·줌·크롭 변화를 감지하지 못합니다. 아래 선택형 감시도 모든 변화를 보장하지 않으므로 촬영 구도가 바뀌면 보정을 다시 해야 합니다.

### 선택형 카메라 이동 감시

같은 구도와 해상도에서 기준점을 표시할 때 사용한 원본 프레임을 저장하고, `calibration` 안에 `"camera_guard_reference": "C:/경로/calibration-frame.png"`를 추가하면 ORB 특징점 이동을 검사합니다. 기본값은 꺼짐입니다. 해당 경로는 서버 로컬 파일이며 분석 시작 시 읽습니다. 기준 이미지가 없거나 특징점이 부족하면 `camera_reference_unavailable`, 현재 프레임을 비교할 특징점이 부족하면 `camera_guard_insufficient`, 이동이 감지되면 `camera_moved`가 `calibration_status`에 표시되고 위치·지표·코칭을 보류합니다. 상태가 `active`여도 정확도가 보장되지는 않습니다. 조명·가림으로 오탐하거나 움직이는 선수, 원근 변화와 렌즈 왜곡 때문에 이동을 놓칠 수 있습니다. 기준 프레임은 실제 보정한 프레임과 일치해야 하며 구도가 바뀌면 새로 보정하고 독립 지점으로 검증해야 합니다. 연구 근거와 시험의 한계는 [보정 연구](docs/calibration-research.md)에 기록했습니다.

### 고정 카메라 보정 오차 측정

실제 MP4의 원본 프레임과 빈 보정 양식을 만들려면 빈 폴더를 미리 생성하고 아래 명령을 실행합니다. 기존 결과 파일을 덮어쓰지 않으며 기준점은 자동 생성하지 않습니다. 예시의 100은 0부터 세는 프레임 번호이고, 실제 필요한 번호로 바꾸세요.

```powershell
.venv\Scripts\python.exe scripts\capture_calibration_frame.py <영상.mp4> 100 <빈_폴더>
```

`calibration-frame.png`에서 경기장 선 교차점을 읽고 `calibration-points.json`에 원본 픽셀 좌표 네 개와 대응하는 실측 미터 좌표, 경기장 가로·세로 길이, 네 점과 다른 독립 검증점을 직접 입력합니다. 디코더의 프레임 이동은 코덱에 따라 근사적일 수 있으므로 저장된 이미지를 확인하세요. 빈 양식에는 점이나 경기장 크기가 없고 `validated`는 false입니다.

기준점 네 개와는 다른 실제 경기장 선 교차점 등을 여러 지점에서 측정해 JSON으로 저장하고 아래 명령을 실행합니다. `image_point`는 원본 영상의 픽셀 좌표, `field_point_m`은 같은 지점의 경기장 기준 미터 좌표입니다. 좌표는 보정할 영상과 동일한 해상도·카메라 구도를 사용해야 합니다. 숫자는 형식 설명용이며 실제 경기장 기준점이 아닙니다.

```json
{"calibration":{"image_points":[[0,0],[100,0],[100,100],[0,100]],"field_points_m":[[0,0],[100,0],[100,50],[0,50]],"field_size_m":[100,50]},"checkpoints":[{"image_point":[50,50],"field_point_m":[50,25]}]}
```

```powershell
.venv\Scripts\python.exe scripts\evaluate_calibration.py <측정값.json>
```

측정 지점별 오차와 중앙값·최댓값을 미터로 출력하고 보정 영역 밖 지점은 제외 사유와 함께 표시합니다. fitting에 사용한 점을 검증점으로 재사용하지 마세요. 이 도구는 정확도를 자동 보증하거나 설정을 변경하지 않습니다. 기준점의 실제 위치·수동 표시 오차, 선수 발 위치, 카메라 이동도 별도로 확인해야 합니다. 오차 허용 기준을 정하고 서로 떨어진 여러 지점에서 확인한 후에만 사용자가 보정 검증 여부를 판단합니다.

`timestamp`는 분석 완료 시각 UTC(카메라 촬영 시각 아님), `fps`는 처리 완료 간격의 순간값, `latency_ms`는 OpenCV 디코딩 후 프레임을 읽은 순간부터 분석 완료까지의 경과 시간입니다. 카메라 인코딩·전송·디코딩 대기나 Mac 화면 표시 지연은 포함하지 않습니다. 실제 전체 지연을 알 수 없으므로 이 값을 종단간 지연으로 쓰지 마세요. FPS와 지연은 영상 없는 초기 상태에서 null입니다. `demo`는 합성 예시를 결과로 제공하지 않으므로 false입니다.

`"tiled_detection": true`는 광각 영상의 작은 사람을 찾기 위한 선택적 시험 기능이며 기본값은 false입니다. 영상을 가로 방향으로 겹쳐 최대 12개 구간으로 나누고 결과를 원본 영상 좌표로 되돌린 뒤 IoU 0.5 기준 중복을 제거합니다. 합친 결과를 프레임당 한 번의 ByteTrack에 넘기므로 타일별로 서로 다른 ID를 발급하지 않습니다. 한 타일당 최대 100개, 중복 제거 전 상위 300개로 제한하므로 혼잡한 장면에서 후보가 빠질 수 있고 경계·가림·유사 색상과 오탐은 해결되지 않습니다. 타일 추론은 더 많은 GPU 시간과 메모리가 필요하고 프레임 드롭이 증가할 수 있습니다. 사람 모델의 class 0과 Ultralytics 8.4.208에서 시험한 ByteTrack API를 사용하며 다른 모델·버전과 실시간 영상의 정확도·속도는 별도 검증해야 합니다. 학습이나 팀별 식별 기능은 아닙니다. Ultralytics 코드와 가중치의 AGPL-3.0 또는 별도 상용 조건을 확인하세요.

`"tiled_detection": "auto"`를 명시하면 입력의 첫 프레임 가로/세로 비율이 3 이상일 때만 타일 방식을 선택하며 입력이 끝날 때까지 이 선택을 유지합니다. 그보다 좁은 영상은 기존 전체 화면 추론을 사용하고, `false`는 모든 영상에서 이를 강제합니다. 처리 상태 메시지에서 `tiled` 또는 `whole frame`을 확인할 수 있습니다. 이 기준은 파노라마 탐지를 돕기 위한 휴리스틱이며 카메라 각도에 따른 탐지 정확도나 처리 속도를 보증하지 않습니다.

공개 SoccerTrack v1 파노라마 한 영상 앞 30프레임에서, 선수 주석 659개와 IoU 0.5 이상 일대일 비교 시 기본 방식은 일치 0개, 타일 방식은 일치 352개·미일치 후보 290개·놓친 주석 307개였습니다. 정밀도 54.8%, 재현율 53.4%로 오탐이 많고 한 영상의 짧은 연속 구간이므로 일반 성능은 아닙니다. 동일 표본에서 각 추론 및 추적 루프 시간은 2.51초, 3.80초였으며 모델 초기화가 포함되고 디코딩·네트워크·다른 분석은 제외됩니다. 이 자료를 학습에 사용하지 않았고 학습 데이터 중복과 주석 완전성은 확인되지 않았습니다.

선택적 실험 설정 `"ball_detection": true`는 `ball` 또는 `sports ball` 클래스를 가진 모델에서 별도 추론을 실행합니다. `/api/v1/analysis`의 추가 필드 `ball_detection_available`과 `ball_candidates`가 결과입니다. 각 후보의 `bbox_image_norm`은 원본 영상의 왼쪽 위 원점 기준 `[x1,y1,x2,y2]`로 0~1 사이의 영상 좌표이고 `confidence`는 모델 점수입니다. 공 위치를 경기장 좌표로 변환하거나 공 소유를 추정하지 않습니다. 후보가 비어 있다고 화면에 공이 없다는 뜻은 아니며 다른 물체가 공 후보일 수도 있습니다. 기본값은 false입니다. 이 기능은 사람 추적 모델과 별도의 예측기를 쓰므로 GPU 메모리와 처리 시간이 늘 수 있습니다. 경기별 공 탐지 정확도와 실제 속도 검증이 필요하며, 모델에 해당 클래스가 없으면 자동 비활성화합니다.

실험적으로 별도 `ball_model_path`에 클래스명이 `ball` 또는 `sports ball`인 체크포인트를 지정할 수 있으며, `ball_tiled_detection: true`를 추가하면 공 후보를 2차원 타일에서 탐지합니다. 두 설정 모두 수동으로 켜야 하고 타일 방식은 느릴 수 있습니다. 논문 근거·작은 표본 비교·안전 한계는 [공 후보 탐지 연구](docs/ball-research.md)를 확인하세요.

추가 필드 `movements`는 동일 추적 ID의 두 위치 사이 직선 변위와 구간 평균 속도의 관측값입니다. 기본값은 빈 배열입니다. 고정 카메라 보정과 팀 분류를 실제로 검증한 뒤, 로컬 MP4가 일정 프레임레이트(CFR)임을 별도로 확인한 경우에만 `verified_constant_frame_rate: true`를 설정하면 프레임 번호와 FPS로 시간 간격을 계산합니다. 프레임레이트가 가변적이거나 알 수 없다면 설정하지 마세요. SRT는 정확한 촬영 시각이 없어 현재 비활성입니다. 끊김, ID 교체, 보정 오차는 완전히 감지할 수 없고 직선 변위는 실제 이동 거리나 전술 의도가 아닙니다. 세부 조건과 테스트는 [움직임 안내](docs/movement.md)를 참고하세요.

선택적인 `formation_observation: true`는 시간·팀·보정 조건이 확인된 로컬 영상에서 동일 추적 ID의 관측 폭·길이 변화만 표시합니다. 전술적으로 좋은지나 결정적 장면인지는 판단하지 않습니다. [분포 변화 실험과 한계](docs/formation-research.md)를 참고하세요.

## 실시간 연결 및 보안

업로드한 MP4에서 사용자가 시간 구간을 지정해 검토용 클립을 저장하는 기능은 [검토 장면 저장] (공개본에는 포함되지 않음)을 참고하세요. 사용자가 CFR을 확인한 파일에서 해시가 일치한 실제 분석 프레임 한 장을 함께 저장할 수 있습니다. 보정과 팀 분류가 검증되지 않으면 위치·지표·코칭은 보류합니다. 이는 전체 영상과 분석의 자동 동기화나 SRT 녹화가 아닙니다.

MediaMTX v1.21.3 Windows 바이너리를 프로젝트의 `mediamtx/`에 내려받아 SHA-256 `b2f5246b07cb72961df03b8d5e8cad43dc657bcf3f49a87bb031bdf22721af74`로 확인했습니다. 현재 실행하거나 방화벽을 변경하지 않았습니다. 기본 MediaMTX 설정은 여러 인터페이스에 열리고 인증 없이 게시/읽기가 가능한 설정을 포함합니다. 실제 연결 전 [인증](https://mediamtx.org/docs/features/authentication), [암호화](https://mediamtx.org/docs/features/encryption), 방화벽과 신뢰된 사설망을 설정하세요. 설정 예제는 공식 배포본 `mediamtx/mediamtx.yml`과 [설정 참조](https://mediamtx.org/docs/references/configuration-file)를 확인하세요.

MediaMTX를 준비한 뒤 iPhone SRT 앱에서 목적지를 `srt://<서버 사설 IP>:8890?streamid=publish:match`로 설정합니다(앱이 stream ID를 별도 입력하면 `publish:match`). 서버의 start 입력은 `rtsp://127.0.0.1:8554/match`입니다. 스트림과 코덱 호환, SRT 접속 및 재연결은 실기기에서 미검증입니다. WebRTC 기본 플레이어 경로는 `http://<서버 IP>:8889/match/`이지만 WebRTC 포트, ICE 및 코덱·브라우저 호환을 별도 설정하고 시험해야 합니다. 기본 HTTP는 TLS가 아닙니다. Mac 대시보드에 영상 플레이어를 구현한 것은 아닙니다.

API는 기본적으로 127.0.0.1만 듣고 인증·TLS가 없습니다. 현재 확인된 Ethernet IPv4는 `192.168.0.10`이나 변경될 수 있고 Mac과 같은 사설망인지 확인되지 않았습니다. 신뢰할 수 있는 사설망에서만 API를 사설 IP에 바인딩하고 해당 IP와 포트 8000에 대한 제한적 접근을 허용하거나, Windows SSH 서버가 별도 구성되어 있다면 Mac에서 `ssh -L 8000:127.0.0.1:8000 <windows-user>@<windows-private-ip>`를 이용해 Mac의 localhost로 접근할 수 있습니다. SSH 서버 설치나 방화벽 설정은 하지 않았습니다. API start는 서버 파일을 읽고 네트워크 연결을 만들 수 있으므로 인터넷에 노출하지 마세요. Mac 브라우저가 다른 origin이면 CORS 설정 또는 같은 origin의 프록시가 별도로 필요합니다. 자격 증명이 포함된 RTSP URL은 status에 그대로 나타나므로 사용하지 마세요.

라이브 캡처는 최신 프레임 한 장만 유지해 Python 큐에 과거 프레임이 쌓이지 않게 합니다. 디코더·네트워크 내부 버퍼와 전체 지연은 별도 검증이 필요합니다. 끊긴 뒤 read timeout까지 상태가 running일 수 있습니다.

### 서로 다른 네트워크에서 포트포워딩 검토

아이폰·맥북과 서버가 서로 다른 네트워크라면 위 사설 IPv4 `192.168.0.10`만으로 연결할 수 없습니다. 사용자가 직접 포트포워딩 방식을 선택했지만 아직 공유기, Windows 방화벽, 인증, TLS는 설정하지 않았습니다. 아래 포트는 **설정 후보**이지 현재 열려 있다는 뜻이 아닙니다.

1. 공유기의 WAN IPv4와 외부에서 확인한 공인 IPv4를 비교합니다. WAN이 `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10` 등에 속하거나 두 주소가 다르면 이중 NAT 또는 CGNAT 가능성이 있습니다. 통신사 NAT나 상위 공유기가 있으면 현재 공유기 한 곳의 포트포워딩만으로는 도달하지 못할 수 있습니다. 공인 IP 제공·상위 라우터 관리 가능 여부를 확인해야 하며, 확인 전에는 원인을 단정하지 않습니다. 서버 사설 IP 고정 또는 DHCP 예약, 공인 IP 변경 시 DNS 갱신도 검토합니다.
2. **아이폰 → SRT 수신:** 공유기 공인 주소의 UDP 8890 → 서버 `192.168.0.10:8890/UDP`, 해당 범위로 제한한 Windows 인바운드 규칙이 후보입니다. MediaMTX `match` 경로에 publish 권한을 가진 별도 사용자와 `srtPublishPassphrase`를 설정하고 아이폰 앱이 SRT 암호화와 stream ID 인증을 지원하는지 확인해야 합니다. SRT 미디어 암호화와 사용자 인증은 별도입니다. stream ID에 인증 정보가 들어가므로 전송 중 해당 정보의 보호 수준도 사용하는 클라이언트와 SRT 구현에서 별도 검증해야 합니다. 인증 정보는 로그·공유 문서에 쓰지 않습니다. [SRT](https://mediamtx.org/docs/publish/srt), [인증](https://mediamtx.org/docs/features/authentication), [경로별 암호구](https://mediamtx.org/docs/references/configuration-file)를 참고하세요.
3. **맥북 → 분석 API:** API는 인증과 TLS가 없어 포트 8000을 인터넷에 포워딩하면 안 됩니다. API를 loopback에 유지하고 아래 읽기 전용 HTTPS 프록시를 별도 실행하는 구성을 로컬에서 시험했습니다. 외부 연결 전 올바른 TLS 인증서, 사용자·토큰 관리, 접근 제한, 직접 8000 접근 차단, 실제 브라우저 CORS 및 방화벽을 검증해야 합니다. 인증 없이 API를 공개하지 마세요.
4. **맥북 → WebRTC 영상:** 플레이어/WHEP 신호용 HTTPS 경로와 실제 영상용 ICE 경로는 별개입니다. 인증된 HTTPS 프록시에서 MediaMTX의 로컬 TCP 8889로 연결하고, 직접 ICE를 선택하면 공인 UDP 8189 → 서버 UDP 8189 및 `webrtcAdditionalHosts`의 외부에서 도달 가능한 공인 주소 또는 DNS가 후보입니다. 기본 HTTP 8889를 그대로 공개하지 마세요. `match`에 read 권한을 별도로 제한하고 익명 publish/read 및 사용하지 않는 MediaMTX API·metrics·기타 프로토콜을 비활성화하거나 접근을 제한해야 합니다. WebRTC 미디어는 DTLS-SRTP를 사용하지만 HTTPS 신호·인증과 별도이며, 인증되지 않은 이용자의 접근을 막아주지는 않습니다. NAT/방화벽에 따라 ICE TCP 또는 인증된 TURN 릴레이가 필요할 수 있습니다. 이들은 [MediaMTX WebRTC 안내](https://mediamtx.org/docs/features/webrtc-specific-features)의 대안이며, TURN은 별도 서버·자격 증명·방화벽과 비용 가능성을 수반합니다.

설정 전에는 각 장치를 같은 임시 LAN에 두거나 서버 한 대에서 합성 입력·API를 시험할 수 있습니다. 서로 다른 네트워크에서는 공인 포트를 직접 열지 않는 대안으로, 외부 서비스에 서버와 클라이언트가 각각 **아웃바운드** 연결하는 인증된 릴레이를 검토할 수 있습니다. API용 HTTPS 터널만으로 SRT UDP나 WebRTC ICE가 자동 연결되지는 않습니다. 각각의 프로토콜 지원, 접근 제어, 운영·비용을 별도 확인해야 합니다. SSH 포워딩은 도달 가능한 SSH 서버가 이미 있어야 하며 TCP API 테스트용이지 SRT UDP를 대신하지 않습니다. 이 대안들 역시 설치하거나 계약하지 않았습니다.

설치된 MediaMTX v1.21.3 배포 설정에서 UDP 8890, UDP ICE 8189, 빈 `srtPublishPassphrase`, 비활성화된 WebRTC TLS·관리 API·metrics를 확인했습니다. 이는 배포 기본 파일의 내용이며 보안 구성이 완료되었다는 뜻이 아닙니다. 특히 기본 익명 권한과 다른 활성 리스너도 공개 전에 별도 점검해야 합니다.

### 읽기 전용 HTTPS 프록시 로컬 실행

`app.read_proxy`는 `127.0.0.1:8000`의 API 중 GET status·analysis만 전달하고 Bearer 토큰을 검증합니다. 기본 리스너는 `127.0.0.1:8443`이며 start·stop·문서 등은 노출하지 않습니다. 요청 토큰은 API로 전달하지 않습니다. 별도 TLS 인증서와 개인 키, 충분한 무작위성을 가진 32자 이상 ASCII 토큰 파일을 준비하고 접근 권한을 제한하세요. 프로젝트나 Git에 넣지 말고 별도 안전한 경로에서 관리하세요. 아래의 경로는 각자 준비한 파일 경로로 대체합니다. 비밀을 명령행이나 채팅에 직접 입력하지 마세요.

```powershell
$env:FOOTBALL_PROXY_TOKEN_FILE = '<토큰 파일 경로>'
$env:FOOTBALL_PROXY_TLS_CERT = '<인증서 PEM 경로>'
$env:FOOTBALL_PROXY_TLS_KEY = '<개인 키 PEM 경로>'
# 브라우저가 다른 origin에서 호출할 때만 정확한 origin을 지정합니다.
$env:FOOTBALL_PROXY_ALLOWED_ORIGIN = 'https://dashboard.example'
.venv\Scripts\python.exe -m app.read_proxy
```

프록시 실행과 별도로 API 서버도 loopback 8000에서 실행해야 합니다. `FOOTBALL_PROXY_HOST`, `FOOTBALL_PROXY_PORT`로 리스너를 변경할 수 있으나 현재 외부에 바인딩하거나 포워딩하지 않았습니다. loopback 외의 주소에 바인딩하려면 `FOOTBALL_PROXY_ALLOWED_CIDRS`에 허용할 출발지 IP/CIDR을 쉼표로 구분해 지정해야 하며 `/0`은 거부합니다. 실제 소켓 상대 주소를 검사하고 `X-Forwarded-For`를 신뢰하지 않습니다. NAT·중간 프록시 구성에 따라 실제 관측 주소가 달라질 수 있으며 맥북 공인 IP는 변동될 수 있으므로 연결 환경에서 검증해야 합니다. 맥북에서 접근하려면 인증서의 이름과 신뢰 체인이 실제 주소에 맞아야 합니다. 로컬 테스트의 임시 자체 서명 인증서는 실제 맥북 신뢰를 입증하지 않습니다. 토큰 회전, 인증 실패 제한, 비밀 파일 ACL, 인증서 갱신과 외부 보안 점검은 미구현입니다. 웹에 공개할 준비가 된 제품으로 간주하지 마세요.

프록시 시험 의존성은 `uv pip install --python .venv\Scripts\python.exe -r requirements-proxy-test.txt`로 설치하고 `.venv\Scripts\python.exe -m pytest -q tests/test_proxy.py`를 실행합니다. 시험은 임시 인증서와 무작위 토큰으로 실제 로컬 TLS 연결을 열고 정리합니다.

### 로컬 SRT와 공개 경기 데모 시험

MediaMTX v1.21.3에서 임시 계정·암호구와 loopback만 사용하는 합성 영상 시험으로 정상 게시·수신을 확인하고 잘못된 인증과 암호구를 거부하는지 각각 확인했습니다. 원격 인터넷 연결, 아이폰 앱은 시험하지 않았습니다. 로컬 전용 SRT 구성과 공개 전 보안 제한은 [docs/srt-local.md] (공개본에는 포함되지 않음)를 확인하세요. SRT 암호화가 인증정보를 포함하는 Stream ID까지 보호한다고 가정할 수 없어 이 조건을 해결하기 전에는 공개하지 않습니다.

WebRTC 합성 시험에서 무인증 WHEP 요청은 401, 인증 요청은 201이었고 ICE 연결 후 영상 프레임도 받았습니다. 이전 실패는 시험 클라이언트가 루프백 ICE 후보를 제외한 설정 문제였으며 시험 프로세스에서만 수정했습니다. `tests/webrtc_local_smoke.py`와 `requirements-webrtc-test.txt`로 재현할 수 있습니다. 이는 로컬 HTTP 신호 시험이며 실제 브라우저·HTTPS·맥북·인터넷 ICE 경로 검증은 아닙니다.

공개 [SoccerTrack v2 데모](https://atomscott.github.io/SoccerTrack-v2/assets/demo-gsr_and_bas.mp4)는 30초·4096×1080·25fps의 대학 아마추어 축구 파노라마이며 원저자의 미니맵·행동 오버레이가 이미 있습니다. [프로젝트](https://atomscott.github.io/SoccerTrack-v2/)와 [데이터셋 라이선스](https://github.com/AtomScott/SoccerTrack-v2/blob/main/LICENSE-DATA)는 CC BY 4.0을 안내하지만 해당 데모 파일 개별 적용 범위는 별도로 확인하지 못해 영상을 재배포하지 않았습니다. 게이트가 있는 원본 데이터셋은 사용하지 않았습니다.

5초 시점의 한 프레임에서 기본 640 입력은 선수 2명만 탐지했고 먼 선수 다수를 놓쳤습니다. 같은 프레임에서 1280은 16개, 1920은 21개의 사람 박스를 만들었으나 수동 정답 대조나 오탐률을 측정하지 않았습니다. `image_size`를 320~1920 사이 32의 배수로 조정할 수 있습니다. 큰 값은 GPU 부하와 지연을 바꾸므로 실제 송출에서 다시 측정해야 합니다. 이 파노라마의 흰색·파란색 유니폼은 작고 주변 잔디가 박스에 섞여 현재 HSV 분류가 신뢰할 수 없습니다. 홈/어웨이 색상 검증이나 보정 정확도는 확인하지 않았으며, 미확인 값을 지정하지 않고 unknown과 null을 유지합니다. 영상의 GT 오버레이는 독립 정답 평가로 사용하지 않았습니다.

통합 스모크 스크립트 `tests/secure_stream_smoke.py`는 임시 MediaMTX 설정과 무작위 게시용 비밀을 사용해 SRT→RTSP→분석 API를 시험합니다. SRT 지원 FFmpeg와 MediaMTX 바이너리 경로를 `--ffmpeg`, `--mediamtx`로 전달하고, 로컬 경기 데모 파일을 `--video`로 지정할 수 있습니다. 원 영상은 전송 시험에서 폭 1280으로 축소됩니다. 시험용 난수는 실행 중 프로세스 인자와 임시 설정에서 같은 컴퓨터의 다른 프로세스에 보일 수 있으므로 신뢰된 환경에서만 실행하세요. 실제 비밀번호를 이 스크립트에 넣지 마세요.

이 경기 데모 통합 시험의 한 시점에는 선수 2명이 `unknown`으로 반환됐고 폭·길이는 null이었습니다. 해당 시점 처리 속도는 20.74 FPS, 디코딩 후 지연은 11.5ms였으며 단일 관측값입니다. `tests/srt_security_smoke.py`는 같은 인자로 SRT 인증·암호구의 성공과 실패를 확인합니다. 두 스크립트는 고정 로컬 시험 포트를 사용하므로 동시에 실행하지 않습니다. 시험에 사용한 작업 폴더의 FFmpeg 9.0.2 빌드는 GPL 옵션으로 빌드되어 있으며 프로젝트에 포함하지 않았습니다. 배포 시 해당 빌드와 구성 라이브러리의 라이선스를 확인해야 합니다.

2026-11-10 읽기 전용 확인 결과 서버의 Ethernet 주소는 `192.168.0.10`, 기본 게이트웨이는 `192.168.0.1`, Windows 연결 프로필은 Public입니다. 외부 IP 확인 서비스와 게이트웨이 HTTP 응답은 도달했지만, 공유기 WAN 주소와 공유기 관리 권한은 확인하지 못했습니다. 따라서 CGNAT·이중 NAT 여부와 포트 개방 가능 여부는 미확인입니다. 사용자가 공유기 관리 화면에서 WAN IPv4와 외부 확인 주소를 비교하고 상위 장비 유무를 확인해야 합니다. 인터넷 회선 주소가 바뀌거나 장치 주소가 바뀔 수 있으므로 포워딩 전 다시 확인하세요. 방화벽이나 공유기 설정은 변경하지 않았습니다.

## 실전 평가와 한계

실제 경기 영상의 다양한 조명·유니폼·가림 구간에서 표본 프레임을 수동 주석하고 탐지 precision/recall, ID 전환 및 추적 누락을 측정합니다. 팀 분류는 탐지와 매칭된 선수에 대해 home/away/unknown 혼동행렬, 정확도, unknown 비율을 측정하고 심판·골키퍼를 별도 집계합니다. 보정에 쓰지 않은 측량 기준점을 영상에서 찍어 변환 후 실제 좌표와 거리 오차(m)의 중앙값·95백분위·최대값을 구하고 위치와 화면 영역별로 나눕니다. 선수 발 위치 오차도 별도 주석하여 평가합니다. 기준점 네 개로만 변환하고 자체 재투영 오차만 재는 것은 정확도 검증이 아닙니다. 이동 카메라, 화면 밖 선수, 원근·가림·보정 오류에 취약합니다.

## 라이선스와 출처

* [Ultralytics 코드 및 사전학습 YOLO 가중치](https://www.ultralytics.com/license): AGPL-3.0 또는 별도 Enterprise 라이선스. 네트워크 서비스와 배포를 포함한 사용 조건을 확인해야 합니다. ByteTrack은 Ultralytics 통합 구현을 사용합니다.
* [MediaMTX](https://github.com/bluenviron/mediamtx/blob/main/LICENSE): MIT, 배포 바이너리의 제3자 라이선스는 [별도 안내](https://github.com/bluenviron/mediamtx/blob/main/docs/6-misc/2-license.md)를 확인하세요.
* 데이터셋을 다운로드하거나 학습하지 않았습니다. 모델의 COCO 사전학습 출처는 [Ultralytics 문서](https://docs.ultralytics.com/datasets/detect/coco/) 참고. COCO 이미지 권리는 이미지별로 다를 수 있으며 데이터 사용 전 원본 라이선스와 각 이미지 조건을 확인하세요.
* 프로젝트 자체의 별도 배포 라이선스는 아직 지정하지 않았습니다. 다른 의존성의 라이선스도 배포 전에 확인하세요.

### 유니폼 색상 수동 표본

`scripts/sample_team_references.py`는 크기를 바꾸지 않은 프레임에서 사용자가 직접 고른 양 팀 상의 사각형으로 HSV 후보를 계산합니다. 각 사각형은 `x1 y1 x2 y2` 픽셀 좌표이며 오른쪽·아래쪽 경계는 포함하지 않습니다. 잔디, 피부, 그림자, 무늬와 다른 사람을 피하세요. 예: `.venv\Scripts\python.exe scripts\sample_team_references.py frame.png --home 100 100 110 110 --away 200 100 210 110` (좌표는 예시). 화면을 축소해 보았다면 원본 좌표로 변환해야 합니다. 출력의 `team_hsv`만 설정에 수동으로 옮기며, home/away는 선택한 사각형의 팀에 대응합니다. 이 도구는 선수·심판을 구별하거나 정확도를 검증하지 않으며 자동으로 설정을 변경하지 않습니다. 실제 실험에서는 미분류가 늘었습니다. [자료와 평가](docs/team-reference-study.md)를 확인하세요.

여러 실측 기준점을 순서 없이 입력해 보정 후보를 준비하고 별도 지점을 검사하려면 [기준점 보정 후보 만들기] (공개본에는 포함되지 않음)를 참고하세요. 후보는 자동 검증되지 않습니다.

기준 프레임과 실측 기준점·독립 확인점을 기존 설정에 연결하는 과정은 [고정 카메라 보정 설정 준비] (공개본에는 포함되지 않음)를 참고하세요. 기본 결과는 비활성이며 사용자가 오차 기준과 현장 확인을 명시해야 활성화됩니다. 기준 영상과 다른 카메라 사용, 잘못된 실측, 선수 역할·팀 분류는 도구가 보증할 수 없습니다.

팀 색상의 검증만으로는 탐지된 사람이 필드 선수인지 알 수 없으므로 자동 색상 분류 모드의 폭·길이 지표와 코칭은 보류합니다. 현재 지표에는 `manual_player_assignments` 모드에서 사용자가 필드 선수와 팀을 직접 확인한 ID만 사용합니다. 선수 확인 후에도 ID 전환과 보정 오류가 남습니다. 진단 경고의 `camera_motion_unchecked`는 카메라 움직임 감지 기준 화면이 없다는 뜻이며, `camera_motion_guard_limited`는 감지가 켜져 있어도 모든 움직임을 보장하지 못한다는 뜻입니다. [실제 영상에서 역할 미확인의 영향](docs/coaching-role-reliability.md)을 참고하세요.
