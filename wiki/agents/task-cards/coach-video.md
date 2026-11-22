# 작업 카드: 코치용 전술 영상 (coach-video, Remotion)

경로 (Git bash에 먼저 붙여 넣음):
```
W=<WORK_DIR>/work
RM=$W/match-1120/coach/remotion
FF=$W/ffmpeg-local/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe
```

## 언제 쓰는가
장면을 멈추고 원·화살표·자막을 얹은 코치용 mp4를 만들거나 고칠 때. 11-20 경기 영상(v1~v5)이 이 프로젝트로 만들어졌습니다.

## 필요한 입력
- 장면마다: 반, 멈춤 초(`first_half.mp4`/`second_half.mp4` 기준), 주인공 줄(수비 줄/미드필더/공격), 확인된 사실(scene-check 카드의 `result.md`). 확인 안 된 장면은 넣지 않습니다.
- 영상 구조: 컴포지션 목록 `$RM/src/videos.tsx`의 `VIDEOS`(id, scenes, slides, patterns), 장면 자료 `$RM/src/scenes.tsx`(형식 `SceneDef`, `Beat`, `Mark`), 포지션별 자료 `$RM/src/lines2.json`(생성 `$W/match-1120/coach/gen_lines2.py`), 화면 규칙 `$RM/src/Tactics.tsx`.

## 시간과 좌표 (Tactics.tsx 기준)
- 클립 `$RM/public/clips/<id>.mp4`: `lines2.json` 장면은 원본의 `멈춤 초 - 6`초부터 10.5초, 30fps(`gen_lines2.py`). `scenes.tsx` 장면은 그 파일 위 주석의 시작 초. 원본 초 = 클립 시작 + 클립 안 초.
- `Beat.sec`는 클립 안 초. 멈춤은 210프레임(7초), 마지막 멈춤 뒤 0.5배속 180프레임 = 원본 3초만 보입니다.
- `Mark`의 `at`, `from`, `to`는 1920x1080 클립 프레임의 픽셀입니다. 0~1 값이면 화면 밖에 그려집니다(L12).

## 단계
1. 멈춤 프레임 사진: `$FF -v error -ss <Beat.sec> -i $RM/public/clips/<id>.mp4 -frames:v 1 $RM/out/qa/<id>_<sec>.png`. 이 사진에서 원 중심을 픽셀로 읽습니다(추적 좌표 쓰지 않음).
2. 장면 자료 수정: `scenes.tsx` 또는 `lines2.json`의 `beats`, `marks`, `cap`, `playCaps`, `slowCap`, `recap`.
3. 렌더: `cd $RM && npx remotion render src/index.ts <컴포지션 id> out/<id>.mp4 --timeout=150000 --concurrency=2`. `npm run render`는 쓰지 않습니다(템플릿에 남은 `AiflPromo`를 가리킴).
4. 접촉 시트: `$FF -v error -i $RM/out/<id>.mp4 -vf "fps=1,scale=480:-1,tile=8x15" -frames:v 1 $RM/out/qa/<id>_sheet.jpg`(120칸 = 2분, 더 긴 영상은 칸 수를 영상 초보다 크게). "일시정지 n/m" 배지가 보이는 칸의 초 x 30 = 멈춤 프레임.
5. 멈춤마다 정지 사진: `npx remotion still src/index.ts <id> out/qa/<id>_<프레임>.png --frame=<프레임>`. 원과 화살표가 대상 선수 위에 있는지 봅니다.
6. 공유본 복사: `$W/match-1120/coach/video/<경기>_<이름>_v<다음 번호>.mp4`. 이전 판은 덮어쓰지 않습니다.

## 숫자 기준과 문구 규칙
- 자막 한 줄 40자 이하, 멈춤마다 2줄. 장면마다 멈춤 2개(빈 공간 → 결정적 순간).
- 멈춤 자막은 그 프레임에 보이는 것만. 느린 화면 자막은 원본 [마지막 멈춤 초, +3초] 안의 일만(L06). 클립 안에서 마지막 멈춤 초 + 3 ≤ 클립 길이(lines2 클립은 10.5초).
- 색: 우리 초록 원, 상대 빨간 원, 제안은 노란 점선 화살표와 "제안:" 표시. 원 1개는 선수 1명만 감쌈.
- "공을 가진, 공 쪽" 표시는 1단계 사진에서 공을 찾았을 때만(L05). "비어 있음"은 L02·L03 확인 뒤.
- 포지션별 편은 그 줄의 경기 전체 그림 1장 이상과 숫자 기준 횟수를 먼저 보이고, 전체 영상에 쓴 장면은 0개(L14). 장면의 주인공 줄과 편 이름이 같아야 함(L15).
- 화면 글에 검출 수, 화질, 추정 표시를 넣지 않음(L24). 좋은 예: "우리 수비 1명이 상대 2명 사이에 섰습니다". 나쁜 예: "수비 조직이 무너졌습니다"(무엇을 보는지 없음).
- 글꼴은 설치된 'Noto Sans KR'을 직접 씁니다. FontFace로 불러오면 렌더가 멈춘 일이 있습니다.

## 필수 근거 (보고에 붙일 것)
- 접촉 시트 경로, 멈춤별 정지 사진 경로, 공유본 경로와 길이(초)와 크기(MB).
- 표: | 장면 | 원본 초 | 멈춤 n | 자막 | 그 초 원본 격자 사진 | 공 위치 |

## 끝난 상태
공유본 mp4가 새 판 번호로 있고, 멈춤마다 정지 사진과 원본 격자 사진이 짝지어 보고되어 있습니다. 검수는 independent-review 카드로 별도 하위 작업이 합니다.

## 자주 틀리는 것
L01, L02, L03, L04, L05, L06, L12, L14, L15, L22, L24, L25.

## 권장 모델
제작 Sonnet. 검수 Opus(independent-review). 자막의 사실 판정이 갈리면 scene-check를 다시 보냅니다.
