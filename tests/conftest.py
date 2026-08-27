from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from snooker_vision.calibration import CalibrationData, PocketROI, standard_pocket_rois
from snooker_vision.config import load_config
from snooker_vision.domain.models import Ball, BallColor, MotionState, Point, TableState


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def config() -> dict[str, object]:
    return load_config(ROOT / "config" / "default.yaml")


def make_ball(color: BallColor, index: int = 0, x: float | None = None, y: float = 200.0) -> Ball:
    return Ball(
        id=f"{color.value.lower()}-{index}",
        color=color,
        x=x if x is not None else 100.0 + 60.0 * index,
        y=y,
        radius=10.0,
        confidence=0.95,
    )


def make_state(colors: list[BallColor], confidence: float = 0.95, stable_frames: int = 5) -> TableState:
    return TableState(
        datetime.now(timezone.utc),
        tuple(make_ball(color, index) for index, color in enumerate(colors)),
        MotionState.STATIC,
        confidence,
        stable_frames,
    )


@pytest.fixture
def calibration(config: dict[str, object]) -> CalibrationData:
    section = config["calibration"]
    assert isinstance(section, dict)
    return CalibrationData.create(
        640,
        360,
        (Point(20, 20), Point(620, 20), Point(620, 340), Point(20, 340)),
        1200,
        600,
        standard_pocket_rois(1200, 600, 28),
        section,
    )

