from app.live_input import ReconnectingReader, status_record


class FakeCapture:
    def __init__(self, frames):
        self.frames, self.released = list(frames), False

    def read(self):
        if self.frames:
            value = self.frames.pop(0)
            if isinstance(value, Exception):
                raise value
            return True, value
        return False, None

    def release(self):
        self.released = True


def make_reader(captures, is_file=False, max_retries=4, events=None):
    queue = list(captures)
    waits = []

    def open_source():
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    reader = ReconnectingReader(open_source, is_file=is_file, max_retries=max_retries, notify=lambda kind, text: events.append(kind) if events is not None else None,
                                sleep=waits.append, clock=lambda: 0.0, log=lambda text: None)
    return reader, waits


def test_frames_pass_through_and_a_file_that_ends_is_not_reconnected():
    reader, waits = make_reader([FakeCapture(['a', 'b'])], is_file=True)
    assert reader.read() == (True, 'a') and reader.read() == (True, 'b') and reader.read() == (False, None)
    assert waits == [] and not reader.gave_up


def test_a_stream_that_drops_is_opened_again_with_growing_waits_and_the_loss_is_reported():
    events = []
    reader, waits = make_reader([FakeCapture(['a']), FakeCapture([]), RuntimeError('down'), FakeCapture(['b', 'c'])], events=events)
    assert reader.read() == (True, 'a')
    assert reader.read() == (True, 'b')                                          # the first reopen gives an empty capture, the second fails, the third works
    assert waits == [1.0, 2.0, 4.0] and reader.reconnects == 1
    assert events == ['no_input', 'input_back'] and reader.read() == (True, 'c')


def test_the_reader_gives_up_after_the_maximum_number_of_tries():
    events = []
    reader, waits = make_reader([FakeCapture([])] * 5, max_retries=3, events=events)
    assert reader.read() == (False, None)
    assert reader.gave_up and len(waits) == 3 and events == ['no_input', 'no_input']


def test_an_exception_while_reading_is_a_failed_read_not_a_crash():
    reader, waits = make_reader([FakeCapture([OSError('broken')]), FakeCapture(['x'])])
    assert reader.read() == (True, 'x') and waits == [1.0]


def test_a_status_record_is_not_a_coaching_alert():
    record = status_record('no_input', 12.34)
    assert record['polarity'] == 'status' and record['time'] == 12.3 and record['detail'] is None and record['title'] == '입력 없음'


def _waits(attempts, max_wait=None):
    waits = []
    extra = {} if max_wait is None else {'max_wait': max_wait}
    reader = ReconnectingReader(lambda: FakeCapture([]), max_retries=attempts, sleep=waits.append, clock=lambda: 0.0, log=lambda t: None, **extra)
    reader.read()
    return waits


def test_default_wait_sequence_is_unchanged():
    assert _waits(8) == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


def test_a_cap_of_two_seconds_gives_1_2_2_2():
    assert _waits(4, max_wait=2.0)[:4] == [1.0, 2.0, 2.0, 2.0]


def test_a_cap_that_is_zero_or_negative_is_an_error():
    import pytest
    for bad in (0, -1.0):
        with pytest.raises(ValueError):
            ReconnectingReader(lambda: FakeCapture([]), max_wait=bad)


def test_a_cap_of_two_seconds_keeps_trying_until_the_default_total_wait_is_spent():
    waits = _waits(8, max_wait=2.0)
    assert waits[:4] == [1.0, 2.0, 2.0, 2.0] and sum(waits) >= 121.0 and sum(waits[:-1]) < 121.0 and len(waits) == 61


def test_default_cap_gives_up_after_eight_tries_as_before():
    waits = _waits(8)
    assert len(waits) == 8 and sum(waits) == 121.0


def test_a_user_given_max_retries_sets_the_budget_for_a_cap():
    assert _waits(3) == [1.0, 2.0, 4.0]                                  # budget 7 s
    assert _waits(3, max_wait=2.0) == [1.0, 2.0, 2.0, 2.0]               # 7 s as well


def test_give_up_seconds_keeps_trying_until_that_much_time_has_passed_and_no_longer():
    waits = []
    now = [0.0]

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds
    reader = ReconnectingReader(lambda: FakeCapture([]), max_wait=2.0, give_up_seconds=1200.0, sleep=sleep, clock=lambda: now[0], log=lambda t: None)
    assert reader.read() == (False, None) and reader.gave_up
    assert 1198 <= sum(waits) <= 1202 and len(waits) > 500 and max(waits) == 2.0           # about 20 minutes of tries every 2 seconds, not the old 61 tries


def test_give_up_seconds_stops_the_wait_as_soon_as_the_stream_is_back():
    events = []
    captures = [FakeCapture(['a']), FakeCapture([])] + [FakeCapture([]) for _ in range(200)] + [FakeCapture(['b'])]
    reader = ReconnectingReader(lambda: captures.pop(0), max_wait=2.0, give_up_seconds=1200.0, sleep=lambda s: None, clock=lambda: 0.0, log=lambda t: None, notify=lambda kind, text: events.append(kind))
    assert reader.read() == (True, 'a') and reader.read() == (True, 'b')
    assert events == ['no_input', 'input_back'] and not reader.gave_up


def test_give_up_seconds_must_be_above_zero():
    import pytest
    for bad in (0, -5):
        with pytest.raises(ValueError):
            ReconnectingReader(lambda: FakeCapture([]), give_up_seconds=bad)
