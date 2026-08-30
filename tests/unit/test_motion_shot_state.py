from __future__ import annotations

from datetime import datetime, timedelta, timezone

from snooker_vision.domain.models import BallColor, MotionObservation, MotionState, Player, ShotStatus, TableState
from snooker_vision.game_state import ShotFSM, StableStateEstimator, compare_states
from snooker_vision.motion import MotionDetector

from tests.conftest import make_ball, make_state


def test_motion_confirmation_and_static_window(config: dict[str, object]) -> None:
    detector = MotionDetector(config["motion"])
    assert detector.update_signal(True).state is MotionState.STATIC
    assert detector.update_signal(True).state is MotionState.MOVING
    for _ in range(int(config["motion"]["static_confirmation_frames"]) - 1):
        assert detector.update_signal(False).state is MotionState.MOVING
    assert detector.update_signal(False).state is MotionState.STATIC


def test_invalid_camera_shift_does_not_create_motion(config: dict[str, object]) -> None:
    detector = MotionDetector(config["motion"])
    observation = detector.update_signal(False, global_shift=20, valid=False, reason="CAMERA_SHIFT")
    assert observation.state is MotionState.STATIC
    assert not observation.valid


def test_stable_state_requires_multiple_frames(config: dict[str, object]) -> None:
    estimator = StableStateEstimator(config["state"])
    now = datetime.now(timezone.utc)
    balls = [make_ball(BallColor.RED)]
    assert estimator.add(now, balls, MotionState.STATIC) is None
    assert estimator.add(now + timedelta(milliseconds=20), balls, MotionState.STATIC) is None
    state = estimator.add(now + timedelta(milliseconds=40), balls, MotionState.STATIC)
    assert state is not None
    assert state.color_counts.red == 1


def test_empty_detection_window_has_zero_confidence(config: dict[str, object]) -> None:
    estimator = StableStateEstimator(config["state"])
    now = datetime.now(timezone.utc)
    assert estimator.add(now, (), MotionState.STATIC) is None
    assert estimator.add(now + timedelta(milliseconds=20), (), MotionState.STATIC) is None
    state = estimator.add(now + timedelta(milliseconds=40), (), MotionState.STATIC)
    assert state is not None
    assert state.balls == ()
    assert state.confidence == 0.0


def test_shot_fsm_creates_one_shot_for_moving_interval(config: dict[str, object]) -> None:
    fsm = ShotFSM(config["shot"], float(config["state"]["min_state_confidence"]))
    before = make_state([BallColor.RED, BallColor.WHITE])
    fsm.update(MotionObservation(MotionState.STATIC, False, 0, 0), before.timestamp, before, Player.PLAYER_A)
    start_time = before.timestamp + timedelta(milliseconds=100)
    started = fsm.update(MotionObservation(MotionState.MOVING, True, 0.01, 0), start_time, None, Player.PLAYER_A)
    assert started.started
    fsm.update(MotionObservation(MotionState.MOVING, True, 0.01, 0), start_time + timedelta(seconds=1), None, Player.PLAYER_A)
    raw_after = make_state([BallColor.WHITE])
    after = TableState(
        start_time + timedelta(seconds=2),
        raw_after.balls,
        raw_after.motion_state,
        raw_after.confidence,
        raw_after.stable_frames,
    )
    completed = fsm.update(MotionObservation(MotionState.STATIC, False, 0, 0), start_time + timedelta(seconds=2), after, Player.PLAYER_A)
    assert completed.completed
    assert completed.shot is not None and completed.shot.status is ShotStatus.COMPLETED
    assert completed.shot.before_state is before
    assert completed.shot.after_state is after


def test_state_diff_reports_missing_color() -> None:
    difference = compare_states(make_state([BallColor.RED, BallColor.BLACK]), make_state([BallColor.BLACK]))
    assert len(difference.missing_balls) == 1
    assert difference.missing_balls[0].color is BallColor.RED
