---
name: coach-video
description: Use when making, editing or re-rendering a coach-facing tactical video for the football match video project - freezes with rings, arrows and Korean captions in the Remotion project at work/match-1120/coach/remotion (Tactics, LineDefence, Line2Midfield and similar compositions), per-position videos, or new scenes for them. Holds the render and still commands, the clip timing rules and the caption rules that past versions broke. Use it even for a one-caption fix, since caption timing and ball claims have been wrong before.
---

# 코치용 전술 영상 (하위 작업용)

자세한 절차와 명령: `wiki/agents/task-cards/coach-video.md`. 장면 확인은 `scene-verification` 스킬.

## 위치
- 프로젝트 `<WORK_DIR>/work/match-1120/coach/remotion`.
- 영상 목록 `src/videos.tsx`(`VIDEOS`), 장면 `src/scenes.tsx`, 포지션별 자료 `src/lines2.json`(생성 `../gen_lines2.py`), 화면 규칙 `src/Tactics.tsx`.
- 렌더: `npx remotion render src/index.ts <id> out/<id>.mp4 --timeout=150000 --concurrency=2`. `npm run render`는 쓰지 않습니다.
- 정지 사진: `npx remotion still src/index.ts <id> out/qa/<id>_<프레임>.png --frame=<프레임>`.

## 시간과 좌표
- `Beat.sec`는 클립 안 초. lines2 클립은 원본 `멈춤 초 - 6`초부터 10.5초.
- 멈춤 7초(210프레임), 마지막 멈춤 뒤 0.5배속은 원본 3초만 보여 줍니다.
- 표시 좌표는 1920x1080 픽셀. 멈춤 프레임 사진에서 읽고, 추적 좌표를 쓰지 않습니다(L12).

## 반드시 할 확인
1. 장면마다 scene-check `result.md`가 있고, 정지 없음, 공 위치가 적혀 있다(L01, L05).
2. 멈춤 자막은 그 프레임에 보이는 것만. 느린 화면 자막은 원본 [마지막 멈춤 초, +3초] 안의 일만(L06).
3. "비어 있음, 혼자"는 확대 사진에서 0명, 겹친 수비수 없음(L02, L03).
4. 횟수 화면은 숫자 기준으로 센 표에서만 가져오고, 문제 예와 잘한 예의 숫자가 기준에서 갈린다(L04).
5. 포지션별 편: 그 줄의 경기 전체 그림 먼저, 전체 영상 장면 재사용 0개, 장면의 주인공 줄 = 편 이름(L14, L15).
6. 화면 글에 검출 수, 화질, 추정 표시 없음. 자막 한 줄 40자 이하, 멈춤마다 2줄(L24).
7. 렌더 뒤 접촉 시트(`ffmpeg ... -vf "fps=1,scale=480:-1,tile=8x15"`)와 멈춤마다 정지 사진을 만들어 원·화살표가 대상 선수 위에 있는지 본다.
8. 기록된 인원수는 멈춤 프레임에 구역 선을 그려 다시 세고, 확실/불확실을 나눠 적는다. 확실한 수와 규칙대로 센 수가 다르면 자막에 쓰지 않는다(L26). 좋은 예는 결과가 이유를 보여 줄 때만, 근거 있는 것이 없으면 넣지 않는다(L30).
9. 실제 속도 자막은 곧 보일 것을 가리키고 결론은 멈춤에서 말한다(L28). 마무리 할 일마다 영상 안 근거 장면을 하나씩 대응시키고, 장면을 지우면 할 일도 확인한다(L29).
10. 자막을 쓰기 전에 장면 확인표(공 위치, 정지 여부, 인원수, 표시할 선수)를 만들고 그 표에서만 쓴다(L33). 소스를 고친 뒤에는 반드시 다시 렌더하고, 영상 수정 시각이 소스보다 뒤인지 본다(L27).
11. 공유본은 `work/match-1120/coach/video/<경기>_<이름>_v<다음 번호>.mp4`. 이전 판을 덮어쓰지 않는다.

## 보고
| 장면 | 원본 초 | 멈춤 n | 자막 | 원본 격자 사진 | 공 위치 | 정지 사진 |
- 공유본 경로, 길이(초), 크기(MB). 그다음 independent-review 검수를 받는다고 적습니다.
