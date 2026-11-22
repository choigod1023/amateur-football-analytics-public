import numpy as np

from app.audio_events import audio_moments, clusters, per_second_features, surge_ratio

RATE = 16000


def noise(seconds, level=0.01, seed=0):
    return np.random.default_rng(seed).normal(0, level, int(seconds * RATE)).astype(np.float32)


def test_clusters_group_nearby_seconds():
    assert clusters([10, 11, 13, 40, 41]) == [[10, 11, 13], [40, 41]]
    assert clusters([]) == []


def test_a_pure_tone_is_found_as_a_whistle_like_moment_and_plain_noise_is_not():
    audio = noise(40)
    t = np.arange(int(2 * RATE)) / RATE
    audio[20 * RATE:22 * RATE] += (0.3 * np.sin(2 * np.pi * 3500 * t)).astype(np.float32)
    loudness, tonal = per_second_features(audio, RATE)
    kinds = [(m['kind'], m['t']) for m in audio_moments(loudness, tonal) if m['kind'] == 'whistle_like']
    assert kinds and all(19 <= second <= 22 for _, second in kinds)
    assert not audio_moments(*per_second_features(noise(40), RATE))


def test_a_loud_burst_is_a_surge_relative_to_its_surroundings():
    audio = noise(60)
    audio[30 * RATE:33 * RATE] *= 8
    loudness, tonal = per_second_features(audio, RATE)
    assert surge_ratio(loudness)[31] > 3
    assert any(m['kind'] == 'surge' and 29 <= m['t'] <= 33 for m in audio_moments(loudness, tonal))


def test_a_recording_shorter_than_one_frame_gives_no_moments():
    loudness, tonal = per_second_features(np.zeros(100, np.float32), RATE)
    assert len(loudness) == 0 and audio_moments(loudness, tonal) == []
