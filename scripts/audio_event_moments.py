"""List loud moments and whistle-like tones of a 16-bit mono WAV file (extract it first with ffmpeg).

Usage: python scripts/audio_event_moments.py <audio.wav> <output.json>

The output is a list of proposals for a person to check; it does not say what happened on the pitch.
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.audio_events import audio_moments, per_second_features  # noqa: E402


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    with wave.open(sys.argv[1]) as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise SystemExit('Expected a 16-bit mono WAV file')
        rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), np.int16).astype(np.float32) / 32768
    loudness, tonal = per_second_features(samples, rate)
    moments = audio_moments(loudness, tonal)
    Path(sys.argv[2]).write_text(json.dumps({'seconds': len(loudness), 'moments': moments,
                                             'note': 'heuristic audio signals, unverified'}, ensure_ascii=False), encoding='utf-8')
    print(len(loudness), 'seconds,', sum(m['kind'] == 'whistle_like' for m in moments), 'whistle-like,', sum(m['kind'] == 'surge' for m in moments), 'surges')


if __name__ == '__main__':
    main()
