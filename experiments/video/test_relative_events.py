from relative_events import analyze


def frame(t, yaw=20, gaze=25):
    return {'timestamp_s':t,'face_count':1,'status':'ok',
        'pose_x_deg':15,'pose_y_deg':yaw,'pose_z_deg':-5,
        'mobilegaze_yaw_deg':gaze,'mobilegaze_pitch_deg':-10,
        'head_deviation':True,'eye_deviation':None}


def test_fixed_oblique_pose_is_not_a_relative_change_and_calibration_is_excluded():
    rows=[frame(i/2) for i in range(80)]
    r,_=analyze(rows,2,40)
    assert r['evaluation_frames']==20 and r['head_baseline_available'] and r['gaze_baseline_available']
    assert r['signal_coverage']['head_deviation']['positive_frames']==0
    assert r['events']==[]


def test_turn_forms_event_eye_abstains_and_event_is_clipped_to_video_duration():
    rows=[frame(i/2) for i in range(67)]
    for row in rows[60:]:row['pose_y_deg']=55
    r,m=analyze(rows,2,33.2)
    assert all(row['eye_deviation'] is None for row in m)
    assert r['events']==[{'type':'relative_head_change','start_s':30.0,'end_s':33.2,'duration_s':3.2}]


def test_missing_calibration_abstains_and_future_frames_do_not_fill_baseline():
    rows=[frame(i/2) for i in range(80)]
    for row in rows[:60]:row.update(face_count=0,status='no_face_detected',pose_x_deg=None)
    r,_=analyze(rows,2,40)
    assert not r['head_baseline_available'] and not r['gaze_baseline_available']
    assert r['signal_coverage']['head_deviation']['measured_frames']==0


def test_wraparound_rotation_does_not_create_a_358_degree_jump():
    rows=[frame(i/2,yaw=0) for i in range(80)]
    for i,row in enumerate(rows):row['pose_z_deg']=179 if i<60 else -179
    r,_=analyze(rows,2,40)
    assert r['signal_coverage']['head_deviation']['positive_frames']==0
