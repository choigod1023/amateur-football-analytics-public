"""Local SRT evaluation with per-frame image markers and matching annotations.

No source pixels, labels or models are sent outside loopback. The output is an
aggregate: do not interpret it as an actual phone, radio-network, or clean-image
test. A small diagnostic marker is burned into the sky, and the video is encoded
twice. The weights must not have been trained on the evaluation match.
"""
import argparse, collections, json, socket, subprocess, sys, tempfile, threading, time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.srt_path_ingest import config_for
from scripts.evaluate_wide_tracking import load_labels, match, MissedReappearanceAudit

INDEX_BITS, BITS, STEP, TOP, HEIGHT = 10, 18, 60, 4, 55


def marker_code(index):
    if not 0 <= index < (1 << INDEX_BITS):
        raise ValueError('Frame index is outside marker range')
    return index | (((index*73 + 41) & 255) << INDEX_BITS)


def mark(frame, index):
    result = frame.copy()
    code = marker_code(index)
    for bit in range(BITS):
        color = 255 if code & (1 << bit) else 0
        result[TOP:TOP+HEIGHT, bit*STEP:(bit+1)*STEP] = color
    return result


def decode(frame):
    if frame.shape[1] < BITS*STEP or frame.shape[0] < TOP+HEIGHT:
        return None
    values = [float(np.mean(frame[TOP+12:TOP+HEIGHT-12, bit*STEP+12:(bit+1)*STEP-12])) for bit in range(BITS)]
    if min(abs(v-127.5) for v in values) < 35:
        return None
    code = sum((1 << bit) for bit, value in enumerate(values) if value > 127.5)
    index = code & ((1 << INDEX_BITS)-1)
    return index if code == marker_code(index) else None


def evaluate(video, labels, weights, mediamtx, ffmpeg, start, frames, destination, confidence=.35, preroll_s=0., tail_s=0.):
    if start < 0 or frames < 1 or start+frames > 1 << INDEX_BITS:
        raise ValueError('Frame marker supports indices 0 through 1023')
    if not (0 <= preroll_s <= 30 and 0 <= tail_s <= 30):
        raise ValueError('Preroll and tail must be in 0..30 seconds')
    truth = load_labels(labels)
    if any(i not in truth for i in range(start, start+frames)):
        raise ValueError('Some requested source-frame annotations are unavailable')
    for port, kind in ((23574, socket.SOCK_STREAM), (23974, socket.SOCK_DGRAM)):
        with socket.socket(socket.AF_INET, kind) as sock:
            sock.bind(('127.0.0.1', port))
    counts = collections.Counter()
    gap_audit = MissedReappearanceAudit()
    groups = collections.Counter()
    observed_indices = []
    frame_rows = []
    capture_original, state_original = main.publish_preview, main.set_state
    pending = {'frame':None}
    processes = []
    owned_tmp = None
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        with tempfile.TemporaryDirectory(prefix='labeled-srt-', dir=destination, ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            owned_tmp = tmp
            cap = cv2.VideoCapture(str(video))
            cap.set(cv2.CAP_PROP_POS_FRAMES, start)
            width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if not (width >= BITS*STEP and height >= 200 and 1 <= fps <= 60):
                raise ValueError('Unsupported video geometry or fps')
            sample = tmp/'marked.avi'
            writer = cv2.VideoWriter(str(sample), cv2.VideoWriter_fourcc(*'MJPG'), fps, (width, height))
            if not writer.isOpened(): raise RuntimeError('Cannot create temporary marked video')
            try:
                last_frame = None
                for index in range(start, start+frames):
                    ok, frame = cap.read()
                    if not ok: raise RuntimeError('Cannot decode requested input frames')
                    stamped = mark(frame,index)
                    if index == start:
                        for _ in range(round(preroll_s*fps)): writer.write(stamped)
                    writer.write(stamped)
                    last_frame = stamped
                for _ in range(round(tail_s*fps)): writer.write(last_frame)
            finally:
                writer.release(); cap.release()
            cfg = config_for('127.0.0.1','127.0.0.1',23974,23574).replace('    srtPublishPassphrase: invalid_config_not_for_direct_use\n','')
            (tmp/'mtx.yml').write_text(cfg, encoding='utf8')
            def launch(args):
                proc = subprocess.Popen([str(x) for x in args],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
                processes.append(proc); return proc
            def frame_probe(frame, grabbed, captured_at, tracks=None, groups=None):
                index=decode(frame)
                result=capture_original(frame,grabbed,captured_at,tracks,groups)
                if result is not None:
                    pending['frame']=index
                return result
            def state_probe(target, **values):
                state_original(target, **values)
                if target is not main.status or 'fps' not in values:
                    return
                index=pending.pop('frame',None); pending['frame']=None
                if index is None or index not in truth:
                    counts['unreadable_or_outside'] += 1; return
                if observed_indices and index <= observed_indices[-1]:
                    counts['nonmonotonic_or_duplicate'] += 1; return
                with main.lock:
                    players=list(main.analysis.get('players',[]))
                predictions=[]
                for player in players:
                    box=player.get('bbox_image_norm')
                    if isinstance(box,list) and len(box)==4:
                        predictions.append(([box[0]*width,box[1]*height,box[2]*width,box[3]*height],player['id']))
                found=match(truth[index],predictions)
                gap_audit.update(truth[index],found)
                counts.update(samples=1,gt=len(truth[index]),predicted=len(predictions),matched=len(found))
                byid={str(p['id']):p for p in players}
                for gt_id,tid in found:
                    group=byid.get(str(tid),{}).get('suggested_color_group')
                    if group in (0,1): groups[(int(group),gt_id.split(':',1)[0])]+=1
                frame_rows.append({'source_frame':index,'gt':len(truth[index]),'predicted':len(predictions),
                                   'matched':len(found),'gt_track_pairs':found})
                observed_indices.append(index)
            main.publish_preview, main.set_state = frame_probe, state_probe
            main.stop_event.clear()
            state_original(main.status,status='running',source='rtsp://127.0.0.1:23574/match')
            launch([mediamtx,tmp/'mtx.yml']); time.sleep(.6)
            sender=launch([ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-re','-i',sample,'-an','-c:v','libx264','-preset','ultrafast','-threads','4','-tune','zerolatency','-g','25','-bf','0','-pix_fmt','yuv420p','-f','mpegts','srt://127.0.0.1:23974?streamid=publish:match&pkt_size=1316'])
            time.sleep(.7)
            config={'model':str(weights.resolve()),'confidence':confidence,'image_size':640,'tiled_detection':'auto','manual_player_assignments':True,'suggest_team_clusters':True}
            worker=threading.Thread(target=main.run,args=('rtsp://127.0.0.1:23574/match',config),daemon=True); worker.start()
            worker.join(timeout=frames/fps+preroll_s+tail_s+25)
            if worker.is_alive():
                main.stop_event.set();worker.join(timeout=8)
            if worker.is_alive(): raise RuntimeError('Analysis did not stop')
            result={'counts':dict(counts), 'sampled_source_first':observed_indices[0] if observed_indices else None,
                    'sampled_source_last':observed_indices[-1] if observed_indices else None,
                    'source_frames_between_samples':sum(max(0,b-a-1) for a,b in zip(observed_indices,observed_indices[1:])),
                    'gap_reappearance':gap_audit.summary(),
                    'matched_group_counts':{f'{group}:{team}':n for (group,team),n in groups.items()},
                    'frame_results':frame_rows,
                    'confidence':confidence,'preroll_s':preroll_s,'tail_s':tail_s,'sender_exit':sender.poll(),'status':main.status.get('status'),'message':main.status.get('message'),
                    'limitations':'One match, loopback SRT, 18-bit sky watermark and two encodes; ROI matching IoU≥0.5; correlated detections; no physical team/role accuracy or iPhone/network claim. No training on evaluation annotations.'}
            if counts['samples']==0: raise RuntimeError('No valid synchronized analysis frames were evaluated')
            return result
    finally:
        main.publish_preview, main.set_state = capture_original, state_original
        for proc in reversed(processes):
            if proc.poll() is None: proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill();proc.wait(timeout=5)
        # Windows may keep the marked AVI open until the sender has exited.
        # Remove only files created by this invocation, inside its own temp dir.
        if owned_tmp is not None and owned_tmp.parent == destination.resolve() and owned_tmp.name.startswith('labeled-srt-') and owned_tmp.exists():
            for name in ('marked.avi', 'mtx.yml'):
                (owned_tmp / name).unlink(missing_ok=True)
            try: owned_tmp.rmdir()
            except OSError: pass


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('video','labels','weights','mediamtx','ffmpeg','work-dir'): p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--start',type=int,default=350);p.add_argument('--frames',type=int,default=250)
    p.add_argument('--confidence',type=float,default=.35)
    p.add_argument('--preroll-seconds',type=float,default=0.,help='Repeat the first marked frame to allow receiver/model startup')
    p.add_argument('--tail-seconds',type=float,default=0.,help='Repeat the final marked frame before ending the stream')
    p.add_argument('--output',type=Path,help='Optional local aggregate and frame-index results JSON')
    a=p.parse_args()
    if not a.work_dir.is_dir(): p.error('work-dir must be an existing local directory')
    if not 0 < a.confidence <= 1: p.error('confidence must be in (0,1]')
    result=evaluate(a.video,a.labels,a.weights,a.mediamtx,a.ffmpeg,a.start,a.frames,a.work_dir,a.confidence,a.preroll_seconds,a.tail_seconds)
    if a.output:
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    concise={key:value for key,value in result.items() if key != 'frame_results'}
    print(json.dumps(concise,ensure_ascii=False,indent=2))
