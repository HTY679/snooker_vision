from __future__ import annotations

from datetime import datetime, timedelta, timezone

from snooker_vision.application import P0Application
from snooker_vision.domain.models import (
    Ball,
    BallColor,
    MotionState,
    Player,
    PotEvent,
    PotEvidence,
    PotStatus,
    ShotEvent,
    ShotStatus,
    TableState,
)


def _state(timestamp: datetime, colors: list[BallColor]) -> TableState:
    balls = tuple(
        Ball(f"fixture-{color.value.lower()}-{index}", color, 100.0 + index * 80.0, 200.0, 10.0, 0.98)
        for index, color in enumerate(colors)
    )
    return TableState(timestamp, balls, MotionState.STATIC, 0.98, stable_frames=5)


def _recorded_shot(
    shot_id: str,
    before: TableState,
    after: TableState,
    color: BallColor,
    pot_id: str,
) -> tuple[ShotEvent, PotEvent]:
    shot = ShotEvent(
        shot_id=shot_id,
        player=Player.PLAYER_A,
        before_state=before,
        started_at=before.timestamp + timedelta(milliseconds=50),
        status=ShotStatus.COMPLETED,
        after_state=after,
        ended_at=after.timestamp,
    )
    pot = PotEvent(
        event_id=pot_id,
        shot_id=shot_id,
        ball_color=color,
        count=1,
        status=PotStatus.CONFIRMED,
        confidence=0.98,
        evidence=PotEvidence("TOP_LEFT", 2.0, True, 0.2, 5, "RECORDED_EVENT_FIXTURE"),
    )
    return shot, pot


def run_recorded_event_demo(app: P0Application) -> dict[str, int]:
    """Run the required 0 -> red +1 -> black +7 -> Undo sequence."""
    base = datetime.now(timezone.utc)
    initial = _state(base, [BallColor.RED, BallColor.BLACK, BallColor.WHITE])
    after_red = _state(base + timedelta(seconds=2), [BallColor.BLACK, BallColor.WHITE])
    after_black = _state(base + timedelta(seconds=4), [BallColor.WHITE])
    red_shot, red_pot = _recorded_shot("demo-red-shot", initial, after_red, BallColor.RED, "demo-red-pot")
    app.commit_recorded_shot(red_shot, [red_pot])
    after_red_score = app.score_engine.state.player_a_score
    black_shot, black_pot = _recorded_shot(
        "demo-black-shot", after_red, after_black, BallColor.BLACK, "demo-black-pot"
    )
    app.commit_recorded_shot(black_shot, [black_pot])
    after_black_score = app.score_engine.state.player_a_score
    app.undo()
    after_undo_score = app.score_engine.state.player_a_score
    return {
        "initial": 0,
        "after_red": after_red_score,
        "after_black": after_black_score,
        "after_undo": after_undo_score,
    }

