"""Check before kickoff whether a source (video file or stream) is ready for the live coaching run. Every answer is a suggestion for a person to confirm.

python scripts/startup_check.py <source> <calibrations.json> <cam1|cam2|cam3> [--start 64 --seconds 20] [--kickoff] [--focus-colour dark|bright]
                                [--reference-bg a b tx ty] [--tile-camera cam1|cam3] [--detector yolo11n.pt] [--out startup_out] [--device 0|cpu]

It reads the first N seconds of the source and writes <out>/startup_report.json and <out>/startup_teams.jpg, and prints a checklist:
  1. input: size, frame rate, how irregular the frame times are, failed reads
  2. people: how many people the tile detector sees on the pitch per sampled second
  3. teams: bright (neon) and dark shirts by the same colour rule as the live run; a picture of both groups so that the coach says once which one is the own team
  4. attack direction: proposed from the mean positions of the two groups when the window starts at kickoff (--kickoff); needs the calibration
  5. calibration: file, fit error, reference picture and how far this picture lies from it
The limits of pass, attention and fail are proposed values, not validated ones. Nothing here is confirmed for the person: the team colour and the attack direction
are always marked "needs a person" and the address of a stream is never printed or written.
"""
import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# proposed limits (not validated)
NEON_MIN, DARK_MIN = 0.10, 0.30        # the colour rule of the live run (TeamVotes without a classifier)
MIN_SIDE_PLAYERS = 4                    # people of a group a frame needs to count for the position mean
DIRECTION_MIN_GAP = 5.0                 # metres between the two position means for a proposal (wiki/live-startup-and-halftime.md)
PEOPLE_OK, PEOPLE_WARN = 14, 8          # people on the pitch per sampled second: pass / attention
IRREGULAR_WARN, IRREGULAR_FAIL = 0.5, 1.5   # largest gap between two frames in seconds
SHIFT_OK, SHIFT_WARN = 0.005, 0.015    # picture shift against the reference as a share of the width
MIN_CROP_HEIGHT = 40                    # pixels: a crop needs this height to be shown on the team sheet
ORDER = {'통과': 0, '주의': 1, '실패': 2}


def interval_stats(times):
    """Frame times in seconds -> {'frames', 'span', 'fps', 'mean_gap', 'cv', 'max_gap'}; None values when fewer than two frames."""
    if len(times) < 2:
        return {'frames': len(times), 'span': 0.0, 'fps': None, 'mean_gap': None, 'cv': None, 'max_gap': None}
    gaps = [b - a for a, b in zip(times, times[1:])]
    span = times[-1] - times[0]
    mean = statistics.fmean(gaps)
    cv = statistics.pstdev(gaps) / mean if mean > 0 else None
    return {'frames': len(times), 'span': round(span, 3), 'fps': round((len(times) - 1) / span, 2) if span > 0 else None,
            'mean_gap': round(mean, 4), 'cv': round(cv, 3) if cv is not None else None, 'max_gap': round(max(gaps), 3)}


def grade_input(stats, failed_reads, reported_fps):
    """-> (status, reason) for the input check."""
    if stats['frames'] < 2:
        return '실패', '읽은 프레임이 2개 미만입니다.'
    reasons, status = [], '통과'
    if stats['max_gap'] is not None and stats['max_gap'] > IRREGULAR_FAIL:
        return '실패', f'프레임 사이 최대 간격이 {stats["max_gap"]:.1f}초입니다.'
    if stats['max_gap'] is not None and stats['max_gap'] > IRREGULAR_WARN:
        status = '주의'
        reasons.append(f'프레임 사이 최대 간격 {stats["max_gap"]:.1f}초')
    if failed_reads:
        status = '주의'
        reasons.append(f'읽기 실패 {failed_reads}번')
    if reported_fps and stats['fps'] and stats['fps'] < 0.8 * reported_fps:
        status = '주의'
        reasons.append(f'실제 프레임 속도 {stats["fps"]}가 보고된 {reported_fps:.1f}보다 낮음')
    return status, ', '.join(reasons) or '이상 없음'


def grade_people(counts):
    """Number of people on the pitch per sampled frame -> (status, reason)."""
    if not counts:
        return '실패', '검출한 프레임이 없습니다.'
    middle = statistics.median(counts)
    if middle >= PEOPLE_OK:
        return '통과', f'프레임당 중앙값 {middle:.0f}명'
    if middle >= PEOPLE_WARN:
        return '주의', f'프레임당 중앙값 {middle:.0f}명(기준 {PEOPLE_OK}명 이상)'
    return '실패', f'프레임당 중앙값 {middle:.0f}명(너무 적음)'


def colour_group(features, neon_index, dark_index):
    """Shirt features of one box -> 'bright', 'dark' or None (unclear), by the colour rule of the live run."""
    if features[neon_index] >= NEON_MIN:
        return 'bright'
    if features[dark_index] >= DARK_MIN:
        return 'dark'
    return None


def grade_teams(counts, unclear):
    """counts: {'bright': n, 'dark': n} of the boxes seen; unclear: boxes that fit neither group."""
    if counts.get('bright', 0) < MIN_SIDE_PLAYERS or counts.get('dark', 0) < MIN_SIDE_PLAYERS:
        side = '형광' if counts.get('bright', 0) < MIN_SIDE_PLAYERS else '어두운 옷'
        return '실패', f'{side} 무리의 상자가 {MIN_SIDE_PLAYERS}개 미만이라 팀을 나눌 수 없습니다.'
    total = counts['bright'] + counts['dark'] + unclear
    if total and unclear / total > 0.5:
        return '주의', f'색으로 가려지지 않은 상자가 {100 * unclear / total:.0f}%입니다.'
    return '통과', f'형광 {counts["bright"]}개, 어두운 옷 {counts["dark"]}개'


def suggest_direction(focus_frames, other_frames, min_side=MIN_SIDE_PLAYERS, min_gap=DIRECTION_MIN_GAP):
    """Per-frame lists of x positions (metres, +x is the image right) of the own team and the other team at kickoff.

    Returns {'direction': +1|-1|None, 'focus_mean', 'other_mean', 'gap', 'frames', 'reason'}. At kickoff every team stands in its own half, so the team whose mean
    is larger in x defends +x and attacks toward -x. Frames in which a team shows fewer than `min_side` people do not count; a gap below `min_gap` metres is no proposal."""
    pairs = [(statistics.fmean(f), statistics.fmean(o)) for f, o in zip(focus_frames, other_frames) if len(f) >= min_side and len(o) >= min_side]
    if not pairs:
        return {'direction': None, 'focus_mean': None, 'other_mean': None, 'gap': None, 'frames': 0, 'reason': f'양 팀이 모두 {min_side}명 이상 보인 프레임이 없습니다.'}
    focus = statistics.fmean(p[0] for p in pairs)
    other = statistics.fmean(p[1] for p in pairs)
    gap = focus - other
    if abs(gap) < min_gap:
        return {'direction': None, 'focus_mean': round(focus, 1), 'other_mean': round(other, 1), 'gap': round(gap, 1), 'frames': len(pairs),
                'reason': f'두 팀 평균 위치 차이가 {abs(gap):.1f}m로 {min_gap:.0f}m보다 작습니다.'}
    return {'direction': -1 if gap > 0 else 1, 'focus_mean': round(focus, 1), 'other_mean': round(other, 1), 'gap': round(gap, 1), 'frames': len(pairs), 'reason': ''}


def worst(statuses):
    return max(statuses, key=lambda s: ORDER[s]) if statuses else '실패'


def public_source(source):
    """A name that is safe to print: the file name of a file, never the address of a stream or a camera."""
    return Path(source).name if isinstance(source, str) and Path(source).exists() else '(파일이 아닌 입력: 주소는 표시하지 않음)'


def read_source(cv2, source, start, seconds, is_file):
    """Read about `seconds` seconds. Returns (frames kept for analysis [(time, frame)], all frame times, failed reads, reported fps, size)."""
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        return [], [], 1, None, None
    reported = capture.get(cv2.CAP_PROP_FPS) or None
    size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    if is_file and start:
        capture.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    times, kept, failed, wall0 = [], [], 0, time.monotonic()
    last_kept = -1e9
    while True:
        ok, frame = capture.read()
        if not ok:
            failed += 1
            if is_file or failed >= 5:
                break
            continue
        now = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0 if is_file else time.monotonic() - wall0
        if not times:
            origin = now
        t = now - origin
        times.append(t)
        if t - last_kept >= 1.0 - 1e-6:
            kept.append((t, frame))
            last_kept = t
        if t >= seconds or (not is_file and time.monotonic() - wall0 > seconds + 15):
            break
    capture.release()
    # reading to the end of a short file is no failure
    if is_file and failed and times and times[-1] >= seconds - 1.0:
        failed -= 1
    return kept, times, failed, reported, size


def team_sheet(cv2, crops, path):
    """Picture with a row of crops per group, so that the coach says once which one is the own team. Returns True when written."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    rows = [('무리 1: 형광색 상의', crops.get('bright', [])), ('무리 2: 어두운 상의', crops.get('dark', []))]
    cell_h, cell_w, pad, head = 220, 110, 8, 40
    width = pad + max(1, max(len(c) for _, c in rows)) * (cell_w + pad)
    sheet = Image.new('RGB', (max(width, 760), head * 2 + 2 * cell_h + 4 * pad + 40), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 22)
    except OSError:
        font = ImageFont.load_default()
    y = pad
    for title, items in rows:
        draw.text((pad, y), f'{title}  ({len(items)}장)', fill=(255, 255, 255), font=font)
        y += head
        for k, crop in enumerate(items):
            h, w = crop.shape[:2]
            scale = min(cell_h / h, cell_w / w)
            image = cv2.resize(crop, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_CUBIC)
            sheet.paste(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)), (pad + k * (cell_w + pad), y))
        y += cell_h + pad
    draw.text((pad, y), '우리 팀은 어느 쪽입니까? 이 그림은 제안이며 사람이 확인해야 합니다.', fill=(130, 200, 255), font=font)
    sheet.save(path, quality=92)
    return True


def calibration_check(cv2, calibrations_path, camera, frame):
    """Does the calibration exist, does it fit, is there a reference picture, how far is this picture from it?"""
    out = {'file': False, 'camera_entry': False, 'fit_rms_m': None, 'reference_picture': False, 'shift_px': None, 'shift_share': None}
    shift_in_frame = (0.0, 0.0)
    path = Path(calibrations_path)
    if not path.is_file():
        return {**out, 'status': '실패', 'reason': '보정 파일이 없습니다.'}, None, shift_in_frame
    out['file'] = True
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {**out, 'status': '실패', 'reason': '보정 파일을 읽을 수 없습니다.'}, None, shift_in_frame
    record = data.get(camera) if isinstance(data, dict) else None
    if not record:
        return {**out, 'status': '실패', 'reason': f'{camera} 보정이 저장되어 있지 않습니다.'}, None, shift_in_frame
    out['camera_entry'] = True
    from app.pitch_map import fit, frame_shift_images
    fitted = fit(record)
    if 'H' not in fitted:
        return {**out, 'status': '실패', 'reason': '보정이 거부되었습니다: ' + str(fitted.get('error'))}, None, shift_in_frame
    out['fit_rms_m'] = round(fitted['rms'], 2)
    token = record.get('ref_token')
    reference = path.parent.parent / 'pending' / f'{token}.jpg' if token else None
    if not (reference and reference.is_file()):
        return {**out, 'status': '주의', 'reason': '기준 사진이 없어 화면이 기준에서 얼마나 움직였는지 알 수 없습니다.'}, fitted, shift_in_frame
    out['reference_picture'] = True
    image = cv2.imread(str(reference))
    if image is None or frame is None:
        return {**out, 'status': '주의', 'reason': '기준 사진을 읽을 수 없습니다.'}, fitted, shift_in_frame
    h, w = image.shape[:2]
    resized = cv2.resize(frame, (w, h)) if frame.shape[:2] != (h, w) else frame
    dx, dy = frame_shift_images(image, resized)
    px = math.hypot(dx, dy)
    scale = frame.shape[1] / w
    shift_in_frame = (dx * scale, dy * scale)
    share = px / w
    out['shift_px'], out['shift_share'] = round(px, 1), round(share, 4)
    if share <= SHIFT_OK:
        status, reason = '통과', f'기준 사진과 {px:.1f}픽셀 차이(너비의 {100 * share:.2f}%)'
    elif share <= SHIFT_WARN:
        status, reason = '주의', f'기준 사진에서 {px:.1f}픽셀 움직임(너비의 {100 * share:.2f}%). 카메라가 움직였는지 확인하세요.'
    else:
        status, reason = '실패', f'기준 사진에서 {px:.1f}픽셀 움직임(너비의 {100 * share:.2f}%). 다시 보정이 필요할 수 있습니다.'
    if out['fit_rms_m'] is not None and out['fit_rms_m'] > 1.5 and status == '통과':
        status, reason = '주의', reason + f'. 보정 오차 {out["fit_rms_m"]}m'
    return {**out, 'status': status, 'reason': reason}, fitted, shift_in_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', help='video file, stream URL or camera number')
    parser.add_argument('calibrations')
    parser.add_argument('camera', choices=('cam1', 'cam2', 'cam3'))
    parser.add_argument('--start', type=float, default=0.0, help='seconds to skip in a file')
    parser.add_argument('--seconds', type=float, default=20.0)
    parser.add_argument('--kickoff', action='store_true', help='the read window starts at kickoff, so the position means say which half each team defends')
    parser.add_argument('--focus-colour', choices=('dark', 'bright'), default='dark', help='shirt colour of the own team (the dark team B in this match)')
    parser.add_argument('--reference-bg', type=float, nargs=4, metavar=('A', 'B', 'TX', 'TY'))
    parser.add_argument('--tile-camera', choices=('cam1', 'cam3'), help='picture layout of the tile detector; default: cam3 for cam2 and the camera name otherwise')
    parser.add_argument('--detector', default='yolo11n.pt')
    parser.add_argument('--confidence', type=float, default=0.10)
    parser.add_argument('--pitch-length', type=float, default=89.0)
    parser.add_argument('--pitch-width', type=float, default=62.0)
    parser.add_argument('--out', default='startup_out')
    parser.add_argument('--device', default='0')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    import cv2
    import numpy as np
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source = int(args.source) if args.source.isdigit() else args.source
    is_file = isinstance(source, str) and Path(source).exists()
    kept, times, failed, reported, size = read_source(cv2, source, args.start, args.seconds, is_file)
    checks = {}
    stats = interval_stats(times)
    status, reason = grade_input(stats, failed, reported)
    checks['input'] = {'status': status, 'reason': reason, 'size': list(size) if size else None, 'reported_fps': round(reported, 2) if reported else None, **stats, 'failed_reads': failed}
    report = {'source': public_source(source), 'camera': args.camera, 'start': args.start, 'seconds': args.seconds, 'limits_are_proposed_not_validated': True, 'checks': checks}
    if not kept:
        _finish(report, out)
        return
    from ultralytics import YOLO
    import track_review_clip as tile_detector
    from app.pitch_map import feet_to_metres
    from app.team_role_features import FEATURE_NAMES, box_features
    detector = YOLO(args.detector)
    device = 'cpu' if args.device == 'cpu' else int(args.device)
    tile_camera = args.tile_camera or ('cam3' if args.camera == 'cam2' else args.camera)
    neon_index, dark_index = FEATURE_NAMES.index('neon'), FEATURE_NAMES.index('dark')
    calibration, fitted, shift = calibration_check(cv2, args.calibrations, args.camera, kept[len(kept) // 2][1])
    checks['calibration'] = calibration
    counts, group_counts, unclear, crops = [], {'bright': 0, 'dark': 0}, 0, {'bright': [], 'dark': []}
    candidates = {'bright': [], 'dark': []}
    own_x, other_x = [], []
    own_group = 'dark' if args.focus_colour == 'dark' else 'bright'
    for t, frame in kept:
        height, width = frame.shape[:2]
        found = [d for d in tile_detector.detect(detector, frame, tile_camera, device, args.confidence)
                 if not ((d[3] - d[1]) >= 90 or d[3] >= 0.84 * height)]       # the same rule as the live run: very large or very low boxes are the stands
        frame_x = {'bright': [], 'dark': []}
        on_pitch = 0
        for d in found:
            point = feet_to_metres(fitted, d, width, height, shift, tuple(args.reference_bg) if args.reference_bg else None) if fitted is not None else None
            if fitted is not None and point is None:
                continue                                              # outside the pitch and its margin: stands, bench, referee area
            on_pitch += 1
            features = box_features(frame, [d[0] / width, d[1] / height, d[2] / width, d[3] / height])
            group = colour_group(features, neon_index, dark_index)
            if group is None:
                unclear += 1
                continue
            group_counts[group] += 1
            if (d[3] - d[1]) >= MIN_CROP_HEIGHT:
                candidates[group].append((d[3] - d[1], t, frame[int(d[1]):int(d[3]), int(d[0]):int(d[2])].copy()))
            if point is not None and (not args.kickoff or t <= 10.0):
                frame_x[group].append(point[0])
        counts.append(on_pitch)
        if fitted is not None and (not args.kickoff or t <= 10.0):
            own_x.append(frame_x[own_group])
            other_x.append(frame_x['dark' if own_group == 'bright' else 'bright'])
    status, reason = grade_people(counts)
    checks['people'] = {'status': status, 'reason': reason, 'counted': 'people inside the pitch by the calibration' if fitted is not None else 'all people the detector found (no calibration)', 'sampled_frames': len(counts), 'median': statistics.median(counts) if counts else None, 'min': min(counts) if counts else None, 'max': max(counts) if counts else None}
    status, reason = grade_teams(group_counts, unclear)
    for group, items in candidates.items():
        items.sort(key=lambda item: -item[0])
        chosen, used_times = [], set()
        for h, t, crop in items:                                      # the clearest crops, from different seconds
            if round(t) not in used_times:
                chosen.append(crop)
                used_times.add(round(t))
            if len(chosen) == 4:
                break
        crops[group] = chosen
    sheet = False
    if crops['bright'] or crops['dark']:
        sheet = team_sheet(cv2, crops, out / 'startup_teams.jpg')
    checks['teams'] = {'status': status, 'reason': reason, 'bright_boxes': group_counts['bright'], 'dark_boxes': group_counts['dark'], 'unclear_boxes': unclear,
                       'picture': 'startup_teams.jpg' if sheet else None, 'needs_a_person': '우리 팀이 어느 무리인지 코치가 한 번 확인해야 합니다. 자동으로 정하지 않았습니다.'}
    if fitted is None:
        checks['direction'] = {'status': '주의', 'reason': '보정이 없어 공격 방향을 제안하지 못했습니다.', 'direction': None, 'needs_a_person': True}
    elif not args.kickoff:
        checks['direction'] = {'status': '주의', 'reason': '읽은 구간이 킥오프가 아니라서 제안하지 않았습니다(--kickoff). 킥오프 직후에만 위치 평균이 방향을 말해 줍니다.', 'direction': None, 'needs_a_person': True}
    else:
        proposal = suggest_direction(own_x, other_x)
        proposal['status'] = '통과' if proposal['direction'] is not None else '주의'
        proposal['needs_a_person'] = True
        proposal['text'] = (f'제안: 우리 팀이 화면 {"오른쪽(+1)" if proposal["direction"] == 1 else "왼쪽(-1)"}으로 공격합니다. 사람이 확인하세요.'
                            if proposal['direction'] is not None else '제안 없음: ' + proposal['reason'])
        checks['direction'] = proposal
    _finish(report, out)


def _finish(report, out):
    names = {'input': '입력', 'people': '사람 검출', 'teams': '팀 색', 'direction': '공격 방향', 'calibration': '보정'}
    for key in ('input', 'people', 'teams', 'direction', 'calibration'):
        if key not in report['checks']:
            report['checks'][key] = {'status': '실패', 'reason': '앞 단계가 실패해서 확인하지 못했습니다.'}
    report['overall'] = worst([c['status'] for c in report['checks'].values()])
    (out / 'startup_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'시작 점검 ({report["source"]}, {report["camera"]}, {report["seconds"]:.0f}초). 아래 기준은 제안값이며 모든 판정은 사람이 확인해야 합니다.')
    for key, label in names.items():
        c = report['checks'][key]
        extra = c.get('text') or c.get('reason', '')
        print(f'  [{c["status"]}] {label}: {extra}')
    if report['checks'].get('teams', {}).get('picture'):
        print(f'  팀 확인 그림: {out / "startup_teams.jpg"}')
    print(f'종합: {report["overall"]} (결과 파일 {out / "startup_report.json"})')


if __name__ == '__main__':
    main()
