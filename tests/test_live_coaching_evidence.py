import numpy as np
from app.live_feedback import LiveAnalyzer
from app.coaching_fields import fields
from app.live_publish import LivePublisher


def gap_alerts(wide_at):
    wide = [(i, x, 0) for i, x in enumerate([-25,-24,-23,23,24,25])]
    narrow = [(i, x, 0) for i, x in enumerate([-5,-4,-3,3,4,5])]
    other = [(i+100, x, y) for i, x, y in narrow]
    analyzer = LiveAnalyzer(1, disabled=())          # gap_wide is off by default (DISABLED_KINDS); the rule itself is tested here
    return [a for i in range(31)
            for a in analyzer.update(i/5, wide if wide_at(i) else narrow, other)
            if a['kind'] == 'gap_wide']


def test_last_frame_spikes_do_not_imply_five_second_wide_gap():
    assert gap_alerts(lambda i: i % 5 == 4) == []


def test_input_pause_does_not_publish_old_gap_as_current_advice():
    wide = [(i, x, 0) for i, x in enumerate([-25,-24,-23,23,24,25])]
    other = [(i+100, x, y) for i, x, y in wide]
    a = LiveAnalyzer(1)
    for i in range(25):
        a.update(i/5, wide, other)
    assert a.update(8, wide, other) == []


def test_supported_gap_keeps_measured_evidence_and_conditional_advice():
    alerts = gap_alerts(lambda i: True)
    assert len(alerts) == 1
    a = alerts[0]
    assert a['time'] == 5
    assert a['evidence']['support_samples_per_second'] == [5]*5
    assert a['evidence']['tactical_correctness_verified'] is False
    assert a['observation'] != a['interpretation'] != a['suggestion']


def test_retreat_does_not_order_both_up_and_down_without_ball_context():
    for supported in (True, False):
        result = fields('line_drop', {'retreat_supported': supported}, '')
        assert '함께 올리세요' not in result['suggestion']
        assert '같이 내려' not in result['suggestion']
        assert '검증하지 못했습니다' in result['limitations']


def test_publisher_preserves_four_distinct_feedback_fields(tmp_path):
    a = gap_alerts(lambda i: True)[0]
    data = LivePublisher(tmp_path).publish(np.zeros((20,20,3), dtype=np.uint8), [], [a],
                                            5, {'length':89, 'width':60}, True, 5, 20)
    assert data['feedback'] == [{key:a[key] for key in ('observation','interpretation','suggestion','limitations','directive')}]


def test_legacy_alert_still_publishes_without_new_fields(tmp_path):
    data = LivePublisher(tmp_path).publish(np.zeros((20,20,3), dtype=np.uint8), [],
        [{'title':'old title','text':'old text'}], 5, {'length':89,'width':60}, True, 5, 20)
    assert data['feedback'][0]['observation'] == 'old title'
    assert data['feedback'][0]['suggestion'] == 'old text'
