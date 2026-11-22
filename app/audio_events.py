"""Loud moments and whistle-like tones in the audio of a match recording.

Both signals are heuristics: a surge is a second that is much louder than the surrounding minute, a whistle-like
second has one narrow, strong peak between 2.5 and 4.5 kHz. They are proposals for a person to check. Nothing here
says that a whistle or a goal happened, and on one recording the signals overlapped the centre-circle candidates
only slightly more often than chance (74% against 61% for whistle-like tones, no difference for surges).
"""
import numpy as np

WHISTLE_BAND = (2500.0, 4500.0)
WHISTLE_PEAK_RATIO = 3000.0     # strongest band peak divided by the median of the whole spectrum
SURGE_RATIO = 3.0               # one-second loudness divided by the median of the surrounding minute
CLUSTER_GAP = 6                 # seconds; marked seconds closer than this form one moment
FRAME = 1024


def per_second_features(samples, rate):
    """samples: mono float array. Returns (loudness per second, whistle peak ratio per second)."""
    hop = FRAME // 2
    frames = (len(samples) - FRAME) // hop
    if frames <= 0:
        return np.zeros(0), np.zeros(0)
    window = np.hanning(FRAME)
    frequencies = np.fft.rfftfreq(FRAME, 1 / rate)
    band = (frequencies >= WHISTLE_BAND[0]) & (frequencies <= WHISTLE_BAND[1])
    loud = np.zeros(frames)
    peak = np.zeros(frames)
    for i in range(frames):
        chunk = samples[i * hop:i * hop + FRAME]
        loud[i] = np.sqrt((chunk ** 2).mean())
        spectrum = np.abs(np.fft.rfft(chunk * window)) ** 2
        peak[i] = spectrum[band].max() / (np.median(spectrum) + 1e-9) if spectrum.sum() > 0 else 0.0
    seconds = int(frames * hop / rate)
    second_of = (np.arange(frames) * hop / rate).astype(int)
    loudness = np.array([loud[second_of == s].mean() if (second_of == s).any() else 0.0 for s in range(seconds)])
    tonal = np.array([np.percentile(peak[second_of == s], 90) if (second_of == s).any() else 0.0 for s in range(seconds)])
    return loudness, tonal


def surge_ratio(loudness, half_window=30):
    """Loudness of each second relative to the median of the seconds around it."""
    out = np.zeros(len(loudness))
    for s in range(len(loudness)):
        around = loudness[max(0, s - half_window):s + half_window + 1]
        out[s] = loudness[s] / (np.median(around) + 1e-6)
    return out


def clusters(marked, gap=CLUSTER_GAP):
    """Group marked second indices that lie within `gap` seconds of each other."""
    groups = []
    for second in sorted(int(s) for s in marked):
        if groups and second - groups[-1][-1] <= gap:
            groups[-1].append(second)
        else:
            groups.append([second])
    return groups


def audio_moments(loudness, tonal):
    """List of {'t', 'kind', 'seconds', 'strength'} for whistle-like tones and surges, sorted by time."""
    moments = []
    for group in clusters(np.where(tonal > WHISTLE_PEAK_RATIO)[0]):
        moments.append({'t': group[0], 'kind': 'whistle_like', 'seconds': len(group), 'strength': round(float(max(tonal[g] for g in group)), 0)})
    ratio = surge_ratio(loudness)
    for group in clusters(np.where(ratio > SURGE_RATIO)[0]):
        moments.append({'t': group[0], 'kind': 'surge', 'seconds': len(group), 'strength': round(float(max(ratio[g] for g in group)), 2)})
    return sorted(moments, key=lambda m: m['t'])
