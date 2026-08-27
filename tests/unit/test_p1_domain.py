from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from snooker_vision.domain.models import (
    BallColor,
    FrameState,
    FrameStatus,
    MatchState,
    MatchStatus,
    Player,
    PlayerIdentity,
    RulePhase,
    ShotOutcome,
)


def identities() -> tuple[PlayerIdentity, PlayerIdentity]:
    return (
        PlayerIdentity("player-a", Player.PLAYER_A, "Player A"),
        PlayerIdentity("player-b", Player.PLAYER_B, "Player B"),
    )


def test_default_frame_represents_standard_opening_state() -> None:
    frame = FrameState(frame_number=1)
    assert frame.status is FrameStatus.NOT_STARTED
    assert frame.remaining_reds == 15
    assert frame.phase is RulePhase.EXPECT_RED
    assert frame.expected_ball is BallColor.RED
    assert frame.score_for(Player.PLAYER_A) == 0


@pytest.mark.parametrize("best_of", [0, 2, 36])
def test_match_rejects_invalid_best_of(best_of: int) -> None:
    player_a, player_b = identities()
    with pytest.raises(ValueError):
        MatchState(
            "match",
            player_a,
            player_b,
            best_of,
            MatchStatus.NOT_STARTED,
            0,
            0,
            FrameState(1),
        )


def test_match_players_have_distinct_ids_even_with_same_display_name() -> None:
    state = MatchState(
        "match",
        PlayerIdentity("a", Player.PLAYER_A, "Alex"),
        PlayerIdentity("b", Player.PLAYER_B, "Alex"),
        3,
        MatchStatus.NOT_STARTED,
        0,
        0,
        FrameState(1),
    )
    assert state.player_a.display_name == state.player_b.display_name
    assert state.player_a.player_id != state.player_b.player_id
    assert state.frames_to_win == 2


def test_invalid_expect_red_with_zero_reds_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(FrameState(1), remaining_reds=0)


def test_shot_outcome_requires_confirmed_color_and_aware_time() -> None:
    with pytest.raises(ValueError):
        ShotOutcome("unknown", Player.PLAYER_A, (BallColor.UNKNOWN,))
    with pytest.raises(ValueError):
        ShotOutcome("naive", Player.PLAYER_A, timestamp=datetime.now())
    valid = ShotOutcome("red", Player.PLAYER_A, (BallColor.RED,), timestamp=datetime.now(timezone.utc))
    assert valid.potted_colors == (BallColor.RED,)
