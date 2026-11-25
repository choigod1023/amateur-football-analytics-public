"""P3 of the second rehearsal (2026-11-25): the first half ends at the "전반 끝" mark, also after the second half was started and when the analysis was started several times.

Rehearsal store (work/overnight-1124/rehearsal2/store, session rehearsal3-20261125, 7 runs in positions.jsonl): the report said "전반 12분 02초" after the end of the
first half and "전반 19분 44초" once the second half was started, because the switch line (after the break) was taken as the end before the mark."""
import json

from fastapi.testclient import TestClient

from app import halftime_rich as hr
from app.review_public import create_app
from tests.test_halftime_rich import WALL
from tests.test_integrate_halftime import ORIGIN, write_runs

W2 = WALL + 700


def match_with_two_runs(store, switched):
    tags = [('start_h1', WALL + 100), ('end_h1', W2 + 200)]
    if switched:
        tags.append(('start_h2', W2 + 800))
    folder = write_runs(store, [(WALL, range(0, 601), 1, [], True), (W2, range(0, 1201), 1, [], True)], tags=tags)
    if switched:                                         # the live run's line for the switch (scripts/run_live_feedback.py), 600 s after the end of the first half
        lines = (folder / 'positions.jsonl').read_text(encoding='utf-8').splitlines()
        at = next(i for i, line in enumerate(lines) if json.loads(line).get('time') == 800.0 and json.loads(line).get('type') == 'second' and i > 700)
        lines.insert(at, json.dumps({'type': 'half', 'half': 2, 'direction': -1, 'time': 800.0}))
        (folder / 'positions.jsonl').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        (folder / 'control.jsonl').write_text(json.dumps({'seq': 1, 'cmd': 'second_half', 'direction': -1, 'at': W2 + 799}) + '\n', encoding='utf-8')
    return folder


def test_the_first_half_keeps_its_length_after_the_switch(tmp_path):
    before, after = tmp_path / 'before', tmp_path / 'after'
    match_with_two_runs(before, switched=False)
    match_with_two_runs(after, switched=True)
    first_before, first_after = hr.build(before, 'm1', 1), hr.build(after, 'm1', 1)
    assert (first_before['start_s'], first_before['end_s'], first_before['how_end']) == (100.0, 900.0, 'tag')
    assert (first_after['start_s'], first_after['end_s'], first_after['how_end']) == (100.0, 900.0, 'tag')
    assert first_after['direction'] == 1
    second = hr.build(after, 'm1', 2)
    assert second['start_s'] == 1500.0 and second['direction'] == -1 and second['how_end'] == 'running'


def test_without_a_mark_the_switch_is_still_the_end(tmp_path):
    folder = match_with_two_runs(tmp_path, switched=True)
    tags = tmp_path / 'analyst-tags' / 'tags.jsonl'
    tags.write_text(''.join(line + '\n' for line in tags.read_text(encoding='utf-8').splitlines() if '"end_h1"' not in line), encoding='utf-8')
    r = hr.build(tmp_path, 'm1', 1)
    assert r['how_end'] == 'switch' and r['end_s'] == 1500.0
    assert folder.is_dir()


def test_a_mark_after_the_switch_is_not_the_end_of_the_first_half(tmp_path):
    match_with_two_runs(tmp_path, switched=True)
    with open(tmp_path / 'analyst-tags' / 'tags.jsonl', 'w', encoding='utf-8') as handle:      # "전반 끝" pressed only late, in the second half
        for i, (kind, epoch) in enumerate([('start_h1', WALL + 100), ('start_h2', W2 + 800), ('end_h1', W2 + 1000)]):
            handle.write(json.dumps({'op': 'add', 'id': f'x{i}', 'kind': kind, 'epoch': epoch}) + '\n')
    r = hr.build(tmp_path, 'm1', 1)
    assert r['how_end'] == 'switch' and r['end_s'] == 1500.0


def test_the_page_api_gives_the_same_first_half_after_the_switch(tmp_path):
    match_with_two_runs(tmp_path, switched=True)
    client = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    first = client.get('/api/v1/halftime/rich', params={'session': 'm1', 'half': 1}).json()
    second = client.get('/api/v1/halftime/rich', params={'session': 'm1', 'half': 2}).json()
    assert (first['start_s'], first['end_s']) == (100.0, 900.0)
    assert second['start_s'] == 1500.0 and second['direction'] == -1
