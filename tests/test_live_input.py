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
