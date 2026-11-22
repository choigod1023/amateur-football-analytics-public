"""Find the ball in a sequence of frames: candidate circles, the re-ranker trained on the labelled clips, and the linker that answers only where the evidence is strong.

Used by scripts/build_review_video.py. On clips held out of training the path was right in about 93 % of the frames it answered (threshold 0.7) and answered in about
40 % of the frames in which a person had marked the ball, so a frame without an answer means "not found", never "no ball".
"""
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.ball_path import BALANCED, link_ball_path, link_ball_path_v2  # noqa: E402
from prepare_ball_clips import TOP, drop_static, window_starts  # noqa: E402
from train_ball_rerank import Net, patch_of, tabular  # noqa: E402
import track_review_clip as tracker  # noqa: E402


BOTTOM = {'cam4': 0.72}                  # lowest row (share of the height) that is searched; cam4 (the stand camera of 2026-11-18) sees the stands below the pitch


class BallFinder:
    def __init__(self, candidate_weights, reranker, person_weights, camera, device=0):
        from ultralytics import YOLO
        self.candidates = YOLO(candidate_weights)
        self.people = YOLO(person_weights)
        self.camera = camera if camera in TOP else 'cam1'
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.net = Net().to(self.device)
        self.net.load_state_dict(torch.load(reranker, map_location=self.device))
        self.net.eval()
        self.yolo_device = device if torch.cuda.is_available() else 'cpu'

    def circles(self, image):
        height, width = image.shape[:2]
        y0 = int(height * TOP[self.camera])
        found = []
        for y in [y0 + v for v in window_starts(int(height * BOTTOM.get(self.camera, 0.95)) - y0, 192, 0.25)]:
            for x in window_starts(width, 192, 0.25):
                result = self.candidates.predict(image[y:y + 192, x:x + 192], device=self.yolo_device, imgsz=768, conf=0.10, classes=[0], verbose=False)[0]
                if result.boxes is None:
                    continue
                for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                    found.append([float((box[0] + box[2]) / 2 + x), float((box[1] + box[3]) / 2 + y), float(score)])
        found.sort(key=lambda c: -c[2])
        kept = []
        for c in found:
            if all(abs(c[0] - k[0]) > 8 or abs(c[1] - k[1]) > 8 for k in kept):
                kept.append(c)
        return kept

    def path(self, images, threshold=None):
        """images: the frames (BGR, 5 per second) of one sequence in order. Returns {index: (x, y, probability)} for the frames where the ball was found."""
        frames = [{'file': str(i), 'cands': self.circles(image)} for i, image in enumerate(images)]
        drop_static([{'cands': f['cands']} for f in frames])
        people = [[[float(v) for v in d[:5]] for d in tracker.detect(self.people, image, self.camera, 0, 0.10)] for image in images]
        scored = []
        for number, (image, frame) in enumerate(zip(images, frames)):
            if not frame['cands']:
                scored.append([])
                continue
            patches = torch.tensor(np.stack([(patch_of(image, c[0], c[1]).astype(np.float32) / 255).transpose(2, 0, 1) for c in frame['cands']])).to(self.device)
            tabs = torch.tensor(np.stack([np.array(tabular(frames, number, c, people[number]), np.float32) for c in frame['cands']])).to(self.device)
            with torch.no_grad():
                p = torch.sigmoid(self.net(patches, tabs)).cpu().numpy()
            scored.append([(c[0], c[1], float(q)) for c, q in zip(frame['cands'], p)])
        return link_ball_path(scored, threshold=threshold) if threshold is not None else link_ball_path_v2(scored, **BALANCED)
