"""Optional bounded image-space ball candidates, not ball tracking."""
import math

from app.tiled_tracking import merge_boxes


def ball_class_id(names):
    """Refuse models with absent or ambiguous ball classes rather than guess."""
    if not isinstance(names, dict):
        return None
    ids = [key for key, name in names.items()
           if isinstance(key, int) and not isinstance(key, bool)
           and isinstance(name, str) and name.strip().lower() in ('ball', 'sports ball')]
    return ids[0] if len(ids) == 1 else None


def tile_windows(width, height, tile_size=512, overlap=.2, max_tiles=24):
    """Cover the frame with overlapping tiles, limiting inference work."""
    if width <= 0 or height <= 0 or tile_size < 1 or not 0 <= overlap < 1 or max_tiles < 1:
        raise ValueError('Invalid tile parameters')

    def starts(length, side):
        if length <= side:
            return [0]
        stride = max(1, int(side * (1 - overlap)))
        out = list(range(0, length - side + 1, stride))
        if out[-1] != length - side:
            out.append(length - side)
        return out

    side = min(tile_size, max(width, height))
    while True:
        xs, ys = starts(width, side), starts(height, side)
        if len(xs) * len(ys) <= max_tiles:
            return [(x, y, min(x + side, width), min(y + side, height)) for y in ys for x in xs]
        side = min(max(width, height), max(side + 1, math.ceil(side * 1.15)))


def tiled_ball_candidates(model, frame, *, class_id, device, image_size, confidence):
    """Merge tile predictions in image coordinates without predicting movement."""
    height, width = frame.shape[:2]
    detections = []
    for x, y, x2, y2 in tile_windows(width, height):
        result = model.predict(frame[y:y2, x:x2], classes=[class_id], device=device,
                               imgsz=image_size, conf=confidence, max_det=100, verbose=False)[0]
        if result.boxes is None:
            continue
        for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
            a, b, c, d = map(float, box)
            detections.append([a+x, b+y, c+x, d+y, float(score)])
    merged = merge_boxes(detections, width, height, iou_threshold=.5)
    return [{'bbox_image_norm': [round(float(b[0])/width, 5), round(float(b[1])/height, 5),
                                 round(float(b[2])/width, 5), round(float(b[3])/height, 5)],
             'confidence': round(float(b[4]), 4)} for b in merged[:100]]
