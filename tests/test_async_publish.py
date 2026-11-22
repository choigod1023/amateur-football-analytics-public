from threading import Event
import json
import cv2
import numpy as np
import pytest
from app.async_publish import AsyncPublisher, PublishWorkerError


class ControlledPublisher:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.records = []

    def publish(self, frame, metadata, *, extra):
        if not self.records:
            self.started.set()
            if not self.release.wait(5):
                raise TimeoutError('Test did not release publisher')
        self.records.append((int(frame[0, 0, 0]), metadata['frame_id'],
                             metadata['players'][0]['id'], extra['tags'][:]))


def test_latest_pending_frame_and_metadata_are_coherent_and_copied():
    target = ControlledPublisher(); publisher = AsyncPublisher(target)
    try:
        first = np.full((4, 4, 3), 1, np.uint8)
        meta = {'frame_id': 1, 'players': [{'id': 'one'}]}; extra = {'tags': ['one']}
        publisher.publish(first, meta, extra=extra)
        assert target.started.wait(2)
        first[:] = 91; meta['players'][0]['id'] = 'mutated'; extra['tags'].append('mutated')
        publisher.publish(np.full((4, 4, 3), 2, np.uint8),
                          {'frame_id': 2, 'players': [{'id': 'two'}]}, extra={'tags': ['two']})
        third = np.full((4, 4, 3), 3, np.uint8)
        meta3 = {'frame_id': 3, 'players': [{'id': 'three'}]}; extra3 = {'tags': ['three']}
        publisher.publish(third, meta3, extra=extra3)
        third[:] = 93; meta3['frame_id'] = 93; extra3['tags'][0] = 'mutated'
        assert publisher.stats['pending'] == 1
        assert publisher.stats['replaced'] == 1
    finally:
        target.release.set()
        publisher.close(timeout=5)
    assert target.records == [(1, 1, 'one', ['one']), (3, 3, 'three', ['three'])]
    assert publisher.stats == {'submitted': 3, 'completed': 2, 'replaced': 1,
                               'abandoned': 0, 'pending': 0, 'active': False,
                               'closed': True, 'failed': False}
    publisher.close(timeout=1)
    with pytest.raises(RuntimeError, match='closed'):
        publisher.publish(np.zeros((1, 1, 3)), {}, extra={})


def test_worker_error_propagates_through_close_and_next_publish():
    class Broken:
        def publish(self, *args, **kwargs):
            raise OSError('Disk write failed')
    publisher = AsyncPublisher(Broken())
    publisher.publish(np.zeros((1, 1, 3)))
    with pytest.raises(PublishWorkerError) as error:
        publisher.close(timeout=5)
    assert isinstance(error.value.__cause__, OSError)
    assert 'Disk write failed' in str(error.value.__cause__)
    with pytest.raises(PublishWorkerError):
        publisher.publish(np.zeros((1, 1, 3)))
    assert publisher.stats['failed']


def test_timeout_is_reported_and_later_close_can_finish():
    target = ControlledPublisher(); publisher = AsyncPublisher(target)
    publisher.publish(np.ones((1, 1, 3)), {'frame_id': 1, 'players': [{'id': 'one'}]}, extra={'tags': []})
    assert target.started.wait(2)
    try:
        with pytest.raises(TimeoutError, match='close timeout'):
            publisher.close(timeout=.001)
    finally:
        target.release.set()
        publisher.close(timeout=5)
    assert publisher.stats['completed'] == 1


def test_empty_close_does_not_invoke_publisher():
    class Unused:
        def publish(self, *args, **kwargs):
            pytest.fail('No snapshot submitted')
    publisher = AsyncPublisher(Unused())
    publisher.close(timeout=2)
    assert publisher.stats['submitted'] == publisher.stats['completed'] == 0


def test_real_live_publisher_retains_snapshot_contract(tmp_path):
    from app.live_publish import LivePublisher
    publisher = AsyncPublisher(LivePublisher(tmp_path))
    publisher.publish(np.full((32, 48, 3), 21, np.uint8),
                      [{'id': 'player-1', 'team': 'home', 'x': .1, 'y': .2}], [],
                      12.4, {'length': 89, 'width': 62}, True, 5., 20.)
    publisher.close(timeout=5)
    snapshot = json.loads((tmp_path/'snapshot.json').read_text(encoding='utf-8'))
    assert snapshot['analysis']['source_time_s'] == 12.4
    assert snapshot['analysis']['players'][0]['id'] == 'player-1'
    assert snapshot['status']['fps'] == 5.
    picture = cv2.imread(str(tmp_path/snapshot['frame_file']))
    assert picture.shape == (32, 48, 3)
    assert np.max(np.abs(picture.astype(float)-21)) <= 1
