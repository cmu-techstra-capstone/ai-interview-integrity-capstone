from pathlib import Path

from features import annotation, events_from_rows


def test_event_requires_sustained_duration_and_resets_after_missing_eye_measurement():
    rows = [{'timestamp_s': i / 5, 'status': 'ok', 'eye_deviation': True} for i in range(9)]
    assert events_from_rows(rows, 5) == []
    rows.append({'timestamp_s': 1.8, 'status': 'ok', 'eye_deviation': True})
    assert events_from_rows(rows, 5)[0]['duration_s'] == 2
    rows[5] = {'timestamp_s': 1, 'status': 'eye_quality_low', 'eye_deviation': None}
    assert events_from_rows(rows, 5) == []


def test_absence_is_detection_status_and_sampling_gaps_do_not_bridge_events():
    rows = [{'timestamp_s': i / 5, 'status': 'no_face_detected'} for i in range(10)]
    event = events_from_rows(rows, 5)[0]
    assert event == {'type': 'no_face_detected', 'start_s': 0, 'end_s': 2, 'duration_s': 2}
    rows[5]['timestamp_s'] = 10
    assert not any(e['duration_s'] > 2 for e in events_from_rows(rows[:6], 5))


def test_annotation_requires_two_agreeing_eyes_and_supports_missing_head(tmp_path: Path):
    path = tmp_path / 'example.txt'
    path.write_text('3 .5 .5 .4 .5\n8 .4 .4 .1 .05\n9 .6 .4 .1 .05\n')
    assert annotation(path) == {'head_label': 3, 'eye_label': None}
    path.write_text('8 .4 .4 .1 .05\n8 .6 .4 .1 .05\n')
    assert annotation(path) == {'head_label': None, 'eye_label': 8}
