from __future__ import annotations

from datetime import timedelta

from snooker_vision.calibration import standard_pocket_rois
from snooker_vision.domain.models import BallColor, Player, Point, PotStatus, ShotEvent, ShotStatus
from snooker_vision.game_state import PotDetector

from tests.conftest import make_state


def completed_shot(before, after) -> ShotEvent:
    return ShotEvent(
        "shot-1",
        Player.PLAYER_A,
        before,
        before.timestamp,
        ShotStatus.COMPLETED,
        after,
        (),
        after.timestamp + timedelta(seconds=1),
    )


def test_missing_ball_with_path_to_pocket_is_confirmed(config: dict[str, object]) -> None:
    before = make_state([BallColor.RED, BallColor.WHITE])
    after = make_state([BallColor.WHITE])
    shot = completed_shot(before, after)
    missing_id = next(ball.id for ball in before.balls if ball.color is BallColor.RED)
    events = PotDetector(config["pot"]).detect(
        shot,
        standard_pocket_rois(1200, 600),
        {missing_id: [Point(100, 100), Point(20, 20), Point(2, 2)]},
    )
    assert len(events) == 1
    assert events[0].status is PotStatus.CONFIRMED


def test_missing_ball_without_pocket_evidence_is_candidate(config: dict[str, object]) -> None:
    before = make_state([BallColor.RED, BallColor.WHITE])
    after = make_state([BallColor.WHITE])
    events = PotDetector(config["pot"]).detect(completed_shot(before, after), standard_pocket_rois(1200, 600))
    assert events[0].status is PotStatus.CANDIDATE


def test_ball_present_after_bounce_is_not_potted(config: dict[str, object]) -> None:
    before = make_state([BallColor.RED, BallColor.WHITE])
    after = make_state([BallColor.RED, BallColor.WHITE])
    events = PotDetector(config["pot"]).detect(completed_shot(before, after), standard_pocket_rois(1200, 600))
    assert events == ()


def test_single_frame_missing_is_unknown(config: dict[str, object]) -> None:
    before = make_state([BallColor.RED], stable_frames=5)
    after = make_state([], stable_frames=1)
    events = PotDetector(config["pot"]).detect(completed_shot(before, after), standard_pocket_rois(1200, 600))
    assert events[0].status is PotStatus.UNKNOWN

