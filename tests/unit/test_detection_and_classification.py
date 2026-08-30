from __future__ import annotations

import cv2
import numpy as np
import pytest

from snooker_vision.classification import BallColorClassifier
from snooker_vision.detection import BallDetector
from snooker_vision.domain.models import Ball, BallColor, MotionState


PROTOTYPES = {
    BallColor.RED: (12, 0, 131),
    BallColor.YELLOW: (25, 220, 225),
    BallColor.GREEN: (35, 145, 35),
    BallColor.BROWN: (35, 75, 130),
    BallColor.BLUE: (205, 90, 35),
    BallColor.PINK: (96, 55, 206),
    BallColor.BLACK: (22, 22, 22),
    BallColor.WHITE: (238, 238, 238),
}


def table_image() -> np.ndarray:
    return np.full((300, 600, 3), (40, 115, 40), dtype=np.uint8)


def test_static_ball_detection_returns_center_and_radius(config: dict[str, object]) -> None:
    frame = table_image()
    cv2.circle(frame, (200, 150), 12, PROTOTYPES[BallColor.WHITE], -1)
    balls = BallDetector(config["detection"]).detect(frame, MotionState.STATIC)
    assert any(abs(ball.x - 200) < 5 and abs(ball.y - 150) < 5 for ball in balls)
    assert all(ball.radius > 0 for ball in balls)


def test_detection_is_skipped_while_moving(config: dict[str, object]) -> None:
    assert BallDetector(config["detection"]).detect(table_image(), MotionState.MOVING) == ()


def test_cue_like_line_is_not_a_ball(config: dict[str, object]) -> None:
    frame = table_image()
    cv2.line(frame, (50, 150), (550, 150), (220, 220, 220), 5)
    assert BallDetector(config["detection"]).detect(frame, MotionState.STATIC) == ()


def test_felt_like_green_ball_is_recovered_by_surrounding_felt(
    config: dict[str, object],
) -> None:
    frame = table_image()
    cv2.circle(frame, (200, 150), 14, (18, 78, 12), -1)
    cv2.circle(frame, (200, 150), 12, (44, 137, 19), -1)
    cv2.circle(frame, (196, 146), 3, (185, 235, 185), -1)
    balls = BallDetector(config["detection"]).detect(frame, MotionState.STATIC)
    assert any(abs(ball.x - 200) < 5 and abs(ball.y - 150) < 5 for ball in balls)


def test_heavily_overlapping_candidates_are_merged(config: dict[str, object]) -> None:
    detector = BallDetector(config["detection"])
    merged = detector._merge(
        (
            (100.0, 100.0, 14.0, 0.90),
            (109.0, 104.0, 16.0, 0.92),
            (126.0, 100.0, 14.0, 0.88),
        )
    )
    assert len(merged) == 2


@pytest.mark.parametrize("expected,bgr", list(PROTOTYPES.items()))
def test_all_eight_known_colors_classify(
    config: dict[str, object], expected: BallColor, bgr: tuple[int, int, int]
) -> None:
    frame = table_image()
    cv2.circle(frame, (100, 100), 14, bgr, -1)
    ball = Ball("candidate", BallColor.UNKNOWN, 100, 100, 14, 0.99)
    result = BallColorClassifier(config["classification"]).classify(frame, ball)
    assert result.color is expected


def test_ambiguous_color_remains_unknown(config: dict[str, object]) -> None:
    frame = table_image()
    cv2.circle(frame, (100, 100), 14, (115, 115, 115), -1)
    ball = Ball("candidate", BallColor.UNKNOWN, 100, 100, 14, 0.99)
    result = BallColorClassifier(config["classification"]).classify(frame, ball)
    assert result.color is BallColor.UNKNOWN


def test_impossible_duplicate_colored_balls_are_invalidated(
    config: dict[str, object],
) -> None:
    frame = table_image()
    cv2.circle(frame, (100, 100), 14, PROTOTYPES[BallColor.PINK], -1)
    cv2.circle(frame, (200, 100), 14, PROTOTYPES[BallColor.PINK], -1)
    balls = (
        Ball("pink-a", BallColor.UNKNOWN, 100, 100, 14, 0.99),
        Ball("pink-b", BallColor.UNKNOWN, 200, 100, 14, 0.80),
    )
    classified = BallColorClassifier(config["classification"]).classify_balls(frame, balls)
    assert [ball.color for ball in classified].count(BallColor.PINK) == 2
    assert classified[0].confidence == 0.0
    assert classified[1].confidence == 0.0
