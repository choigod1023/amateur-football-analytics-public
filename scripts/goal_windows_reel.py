"""Cut the stretches of the match video in which the goals were scored, from the match minutes of the final report.

Usage: python scripts/goal_windows_reel.py <video> <output mp4> <first half kickoff s> <second half kickoff s> <second half first minute> <half>:<minute> ... (or T:<video second> for a moment given in video time)

The match clock is assumed to run from kickoff without stoppages: a goal "at minute m" was scored m minutes after the kickoff of the match (the
second half starts at match minute <second half first minute>). The clip runs from 20 s before to 40 s after that moment, so a clock that is
off by up to about 20 s is still covered. Every frame shows the video time and the clock the assumption gives.
The reel is for a person to find the real second of each goal; nothing here detects a goal.
"""
import sys

import cv2
import numpy as np

OUT_FPS = 10
SIZE = (960, 540)


def window(half, minute, kickoffs, second_half_first_minute):
    """(start, end) in video seconds around the moment `minute` minutes after kickoff."""
    if half == 'T':
        moment = minute
        return max(0, moment - 30), moment + 40
    if half == '1H':
        moment = kickoffs[0] + 60 * minute
    else:
        moment = kickoffs[1] + 60 * (minute - second_half_first_minute)
    return max(0, moment - 20), moment + 40


def main():
    video, output = sys.argv[1], sys.argv[2]
    kickoffs = (float(sys.argv[3]), float(sys.argv[4]))
    second_first = float(sys.argv[5])
    goals = [(g.split(':')[0], int(g.split(':')[1])) for g in sys.argv[6:]]
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps / OUT_FPS))
    writer = cv2.VideoWriter(output, cv2.VideoWriter_fourcc(*'mp4v'), OUT_FPS, SIZE)
    for number, (half, minute) in enumerate(goals, 1):
        start, end = window(half, minute, kickoffs, second_first)
        card = np.zeros((SIZE[1], SIZE[0], 3), np.uint8)
        cv2.putText(card, (f'CANDIDATE {number}: video {minute // 60}:{minute % 60:02d}' if half == 'T' else f'GOAL {number}: {half} minute {minute}'), (60, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 3)
        cv2.putText(card, f'video {int(start) // 60}:{int(start) % 60:02d} - {int(end) // 60}:{int(end) % 60:02d}', (60, 320), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 2)
        for _ in range(OUT_FPS * 2):
            writer.write(card)
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        t = start
        while t < end:
            frame = None
            for _ in range(step):
                ok, grabbed = cap.read()
                if ok:
                    frame = grabbed
            if frame is None:
                break
            t += step / fps
            image = cv2.resize(frame, SIZE)
            clock = (t - kickoffs[0]) / 60 if half == '1H' else second_first + (t - kickoffs[1]) / 60
            label = f'CANDIDATE {number}  video {int(t) // 60}:{int(t) % 60:02d}  (goal moment {minute // 60}:{minute % 60:02d})' if half == 'T' else None
            cv2.rectangle(image, (0, 0), (SIZE[0], 40), (0, 0, 0), -1)
            cv2.putText(image, label or f'GOAL {number}  video {int(t) // 60}:{int(t) % 60:02d}   assumed match clock {int(clock)}:{int((clock % 1) * 60):02d} (goal at minute {minute})',
                        (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            writer.write(image)
    writer.release()


if __name__ == '__main__':
    main()
