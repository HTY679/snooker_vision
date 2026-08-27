from __future__ import annotations

import pytest

from snooker_vision.application import P0Application
from snooker_vision.demo import run_recorded_event_demo
from snooker_vision.domain.models import BallColor, ShotStatus


@pytest.mark.integration
def test_required_red_black_undo_demo(config: dict[str, object]) -> None:
    app = P0Application(config)
    assert run_recorded_event_demo(app) == {
        "initial": 0,
        "after_red": 1,
        "after_black": 8,
        "after_undo": 1,
    }
    assert app.score_engine.state.current_break == 1
    assert app.last_shot is not None and app.last_shot.shot_id == "demo-red-shot"
    assert app.last_shot.status is ShotStatus.COMPLETED
    assert app.last_pot is not None and app.last_pot.ball_color is BallColor.RED
    black_score = next(event for event in app.score_engine.events if event.ball_color is BallColor.BLACK)
    assert black_score.undone
