"""A scene-scoped human answer; raw IDs must never become global person labels."""
import json
from pathlib import Path
from app.track_stitch import drop_duplicates, stitch_tracks


def test_two_human_confirmed_people_survive_duplicate_filter():
    answer=json.loads((Path(__file__).parent/'fixtures/distinct_overlap_29_31.json').read_text(encoding='utf-8'))
    assert answer['verdict']=='different_people'
    tracks=answer['tracks']
    kept,dropped=drop_duplicates(tracks)
    assert dropped==0
    assert kept==tracks
    assert len(kept['29'])==5 and len(kept['31'])==7


def test_scene_answer_cannot_be_read_as_post_crossing_identity_or_team_truth():
    answer=json.loads((Path(__file__).parent/'fixtures/distinct_overlap_29_31.json').read_text(encoding='utf-8'))
    assert answer['identity_after_crossing'] is None and answer['team'] is None
    assert len(answer['scope']['video_sha256'])==64
    assert len(answer['scope']['trace_sha256'])==64
    joined,joins=stitch_tracks(answer['tracks'],different_pairs=[answer['pair']])
    assert set(joined)=={'29','31'} and not joins
