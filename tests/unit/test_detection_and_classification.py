from __future__ import annotations

import cv2
import numpy as np
import pytest

from snooker_vision.classification import BallColorClassifier
from snooker_vision.detection import BallDetector
from snooker_vision.domain.models import Ball, BallColor, MotionState


PROTOTYPES = {
    BallColor.RED: (35, 35, 210),
    BallColor.YELLOW: (25, 220, 225),
    BallColor.GREEN: (35, 145, 35),
    BallColor.BROWN: (35, 75, 130),
    BallColor.BLUE: (205, 90, 35),
    BallColor.PINK: (175, 175, 235),
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

