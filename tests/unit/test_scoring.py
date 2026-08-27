from __future__ import annotations

from datetime import datetime, timezone

import pytest

from snooker_vision.domain.models import BallColor, Player, PotEvent, PotStatus
from snooker_vision.scoring import PlayerSwitchLocked, ReviewRequired, ScoreEngine


def pot(event_id: str, color: BallColor, count: int = 1, status: PotStatus = PotStatus.CONFIRMED) -> PotEvent:
    return PotEvent(event_id, "shot", color, count, status, 0.95, datetime.now(timezone.utc))


@pytest.mark.parametrize(
    "color,value",
    [
        (BallColor.RED, 1),
        (BallColor.YELLOW, 2),
        (BallColor.GREEN, 3),
        (BallColor.BROWN, 4),
        (BallColor.BLUE, 5),
        (BallColor.PINK, 6),
        (BallColor.BLACK, 7),
    ],
)
def test_basic_score_map(config: dict[str, object], color: BallColor, value: int) -> None:
    engine = ScoreEngine(config["scoring"])
    event = engine.apply_pot(pot(f"pot-{color.value}", color))
    assert event is not None and event.score_delta == value


def test_white_and_unknown_do_not_add_positive_score(config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    assert engine.apply_pot(pot("white", BallColor.WHITE)) is None
    assert engine.apply_pot(pot("unknown", BallColor.UNKNOWN)) is None
    assert engine.state.player_a_score == 0


def test_duplicate_source_event_is_idempotent(config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    source = pot("same", BallColor.BLACK)
    first = engine.apply_pot(source)
    second = engine.apply_pot(source)
    assert first is second
    assert engine.state.player_a_score == 7


def test_low_confidence_candidate_is_not_scored(config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    with pytest.raises(ReviewRequired):
        engine.apply_pot(pot("candidate", BallColor.RED, status=PotStatus.CANDIDATE))
    assert engine.state.player_a_score == 0


def test_player_switch_lock_and_attribution(config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    with pytest.raises(PlayerSwitchLocked):
        engine.switch_player(locked=True)
    engine.switch_player()
    engine.apply_pot(pot("black-b", BallColor.BLACK))
    assert engine.state.player_a_score == 0
    assert engine.state.player_b_score == 7


def test_undo_restores_score_break_and_player(config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    engine.apply_pot(pot("red", BallColor.RED))
    engine.apply_pot(pot("black", BallColor.BLACK))
    undone = engine.undo()
    assert undone is not None and undone.score_delta == 7 and undone.undone
    assert engine.state.player_a_score == 1
    assert engine.state.current_break == 1
    assert engine.state.current_player is Player.PLAYER_A


def test_undo_without_history_is_safe(config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    assert engine.undo() is None
    assert engine.state.player_a_score == 0

