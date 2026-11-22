# 파이프라인과 파일 위치

근거: `인수인계 문서(공개본에서 제외)` (2026-11-13), 이후 변경은 이 위키의 다른 페이지. 경로는 저장소 루트 기준입니다.

## 한 줄 요약
휴대폰 한 대로 찍은 축구 경기 영상(1080p)에서 선수 위치를 읽어 코치가 쓸 전술 분석(보고서 PDF, 영상, 웹 화면, 실시간 알림)을 만드는 시스템. B팀만 분석합니다.

## 분석 순서
1. 검출: 타일 YOLO (`scripts/track_review_clip.py`의 `detect`, 384px 조각을 768로 확대, 기본 모델 yolo11n). 저장된 검출로 추적하는 `scripts/track_from_cache.py`가 ByteTrack, 팀 분류, 이음, 빈틈 채우기를 합니다.
2. 경기장 좌표: `app/pitch_map.py`(동형 변환)과 `scripts/build_match_report.py`의 `load_half`. `half['by_frame'][프레임][팀] = [(추적번호, x, y)]`, 5fps.
3. 분석: `app/attack_options.py`(패스길), `app/tactical_concepts.py`, `app/event_miner.py`(박스 공격, 침투, 허용된 침투, 고립), `app/team_tactics.py`(팀 모양, 구역, 빈 쪽, 활동량), `app/goalkeeper.py`.
4. 산출물: `scripts/build_match_report.py`, `scripts/images_to_pdf.py`, `scripts/build_goal_check_video.py`, `scripts/build_surge_clips.py`, `scripts/build_player_cards.py`.

## 위치
| 무엇 | 위치 |
|---|---|
| 파이썬(cv2, torch, ultralytics, fastapi) | `..\football-coach-server\.venv\Scripts\python.exe` (시스템 `python`에는 cv2가 없음) |
| ffmpeg | `..\..\work\ffmpeg-local\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe` |
| 경기 영상 | `..\..\work\own-match-merged-20261111\match_from_17min.mp4` (1920x1080 HEVC, 프레임 간격 불규칙) |
| 경기장 보정 | `..\..\work\human-labels\public-own-match-review-20261111\calibration\calibrations.json` |
| 서버 저장소 | `..\..\work\human-labels\public-own-match-review-20261111` |
| 서버 설정 | `..\..\work\report-config\server.json` |
| 추적 결과 | `..\..\work\tracks-ov3-20261113\` (`h1_v3.json`, `h2_v3.json`, 후반 개선판 `h2_ov3.json`) |
| 저장된 검출 | `..\..\work\detection-cache-20261112\half{1,2}_cam{1,3}_xn` |
| 팀 분류 모델 | `..\..\work\team-role-model-20261112b\model.pt` |
| 보고서 | `..\..\work\match-report-20261113e\` (35쪽, `match_report.pdf`) |
| 큰 검출 모델 | `..\..\work\models-20261112\yolo11x.pt` |
| 우리 영상으로 학습한 검출기 | `..\..\work\detector-ft-20261112\ft_n2\best.pt` |

## 구간 지정(`--half`) 형식
`이름|추적.json|카메라|공격방향|영상 시작 초|배경 보정 a,b,tx,ty|이동 일정|골 시각들`
- 전반: `전반|h1_v3.json|cam1|-1|64|1.000657,0.000035,-0.67,-0.47|0:0.0,-0.2|300,450,500`
- 후반: `후반|h2_v3.json|cam3|1|1740|1.003087,-0.001614,-7.41,5.61|0:-1.8,6.8;1950:0.3,0.3|1800,2000,2300`

## 선수 확인 모델 (`app/player_identity.py`)
- 저장: `<저장소>/players/` 아래 `roster.json`, 구간별 `index.json`, `assign/`, `links/`, `rejects/`. 같은 사람 연결은 묶음으로 처리하고, 한 묶음에 서로 다른 선수가 달리면 충돌로 표시합니다.
- 추적을 다시 만들면 조각 번호가 바뀌므로 `scripts/migrate_player_answers.py`로 답을 옮깁니다.
- 사람 답(`assign`, `links`, `rejects`)과 컴퓨터가 읽은 값(`auto_notes.json`, `suggestions/`)은 분리 보관합니다.

## 측정된 사실 (2026-11-13)
- 한 순간에 추적되는 선수는 팀당 약 10~11명입니다. 문제는 검출 부족보다 추적 조각이 잘게 끊기는 것입니다(팀 B만 전반 204개, 후반 약 176개 조각). (기준이 다름: 204/176은 `인수인계 문서(공개본에서 제외)` 기준 값이고, 같은 조각을 '과반이 B인 조각'으로 다시 센 `wiki/gap-link-experiment.md`는 전반 209, 후반 183입니다. 어느 값이든 결론(약 10~20번 끊김)은 같습니다.)
- 선수 상자 키 중간값은 약 30픽셀(가까운 쪽 47~48, 가운데 29~31, 먼 쪽 21~22). 등번호 읽기에는 약 150픽셀이 필요해서 대부분 사진만으로 구분할 수 없습니다.
- 공 추적: 정밀도 약 96%, 재현율 약 43% (슛 같은 빠른 구간을 놓침).
- 팀 모양의 절대 길이와 폭은 보정 오차를 포함합니다. 같은 칸끼리의 비교만 믿을 수 있습니다. "머문 구역"은 점유율이 아니라 팀이 선 위치의 비율입니다.
