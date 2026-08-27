from __future__ import annotations

from datetime import datetime, timezone

import pytest

from snooker_vision.config import ConfigError, load_config
from snooker_vision.domain.models import Ball, BallColor, MotionState, Player, TableState


def test_ball_and_table_state_are_typed() -> None:
    ball = Ball("red-1", BallColor.RED, 10.0, 20.0, 5.0, 0.9)
    state = TableState(datetime.now(timezone.utc), (ball,), MotionState.STATIC, 0.9)
    assert state.color_counts.red == 1
    assert state.color_counts.black == 0
    assert Player.PLAYER_A.other() is Player.PLAYER_B


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_invalid_ball_confidence_rejected(confidence: float) -> None:
    with pytest.raises(ValueError):
        Ball("bad", BallColor.UNKNOWN, 0.0, 0.0, 1.0, confidence)


def test_default_config_loads_and_contains_threshold_sections(config: dict[str, object]) -> None:
    for section in ("calibration", "detection", "classification", "motion", "state", "pot", "scoring"):
        assert section in config


def test_missing_config_fails_loudly(tmp_path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.yaml")

