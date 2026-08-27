from __future__ import annotations

import pytest

from snooker_vision.domain.models import (
    BallColor,
    FrameStatus,
    MatchStatus,
    Player,
    RuleDecisionStatus,
    RulePhase,
    ShotOutcome,
)
from snooker_vision.rules import (
    InvalidRespot,
    MatchInProgress,
    MatchNotReady,
    PendingDecision,
    RuleStateConflict,
    SnookerRulesEngine,
)


def started_engine(best_of: int = 3) -> SnookerRulesEngine:
    engine = SnookerRulesEngine()
    engine.new_match("Alice", "Bob", best_of=best_of, match_id="match")
    engine.start_frame()
    return engine


def shot(
    engine: SnookerRulesEngine,
    shot_id: str,
    *colors: BallColor,
    player: Player | None = None,
    nominated: BallColor | None = None,
) -> ShotOutcome:
    return ShotOutcome(
        shot_id,
        player or engine.state.current_frame.current_player,
        tuple(colors),
        nominated_color=nominated,
    )


def test_match_initialization_start_and_idempotency() -> None:
    engine = SnookerRulesEngine()
    state = engine.new_match("", "", best_of=3, match_id="stable-id")
    assert state.current_frame.remaining_reds == 15
    assert state.current_frame.status is FrameStatus.NOT_STARTED
    assert state.player_a.display_name == "Player A"
    assert engine.new_match(match_id="stable-id") is state
    with pytest.raises(MatchInProgress):
        engine.new_match(match_id="different")
    started = engine.start_frame()
    assert started.status is MatchStatus.PLAYING
    assert started.current_frame.status is FrameStatus.PLAYING
    assert engine.start_frame() is started


def test_scoring_requires_started_frame_and_correct_player() -> None:
    engine = SnookerRulesEngine()
    engine.new_match(match_id="match")
    with pytest.raises(MatchNotReady):
        engine.process_shot(ShotOutcome("red", Player.PLAYER_A, (BallColor.RED,)))
    engine.start_frame()
    with pytest.raises(RuleStateConflict):
        engine.process_shot(ShotOutcome("wrong-player", Player.PLAYER_B, (BallColor.RED,)))


def test_red_then_black_scores_and_keeps_player() -> None:
    engine = started_engine()
    red = engine.process_shot(shot(engine, "red", BallColor.RED))
    frame = engine.state.current_frame
    assert red.status is RuleDecisionStatus.LEGAL and red.points == 1
    assert frame.player_a_score == 1 and frame.remaining_reds == 14
    assert frame.phase is RulePhase.EXPECT_COLOR
    assert frame.current_player is Player.PLAYER_A

    black = engine.process_shot(shot(engine, "black", BallColor.BLACK))
    frame = engine.state.current_frame
    assert black.points == 7 and frame.player_a_score == 8
    assert frame.phase is RulePhase.EXPECT_RED
    assert frame.pending_respots == (BallColor.BLACK,)
    assert frame.current_player is Player.PLAYER_A


def test_multiple_reds_are_scored_and_decremented_together() -> None:
    engine = started_engine()
    result = engine.process_shot(shot(engine, "two-reds", BallColor.RED, BallColor.RED))
    assert result.points == 2
    assert engine.state.current_frame.remaining_reds == 13


def test_color_respot_must_complete_before_next_shot() -> None:
    engine = started_engine()
    engine.process_shot(shot(engine, "red", BallColor.RED))
    engine.process_shot(shot(engine, "blue", BallColor.BLUE))
    with pytest.raises(PendingDecision):
        engine.process_shot(shot(engine, "early", BallColor.RED))
    with pytest.raises(InvalidRespot):
        engine.complete_respot(BallColor.BLUE, observed_color=BallColor.PINK)
    engine.complete_respot(BallColor.BLUE, observed_color=BallColor.BLUE)
    assert engine.state.current_frame.pending_respots == ()


def test_miss_switches_player_at_correct_phase() -> None:
    engine = started_engine()
    miss = engine.process_shot(shot(engine, "red-miss"))
    assert miss.status is RuleDecisionStatus.MISS
    frame = engine.state.current_frame
    assert frame.current_player is Player.PLAYER_B and frame.phase is RulePhase.EXPECT_RED

    engine.process_shot(shot(engine, "b-red", BallColor.RED))
    color_miss = engine.process_shot(shot(engine, "b-color-miss"))
    frame = engine.state.current_frame
    assert color_miss.status is RuleDecisionStatus.MISS
    assert frame.current_player is Player.PLAYER_A and frame.phase is RulePhase.EXPECT_RED


def test_duplicate_shot_is_idempotent() -> None:
    engine = started_engine()
    outcome = shot(engine, "red", BallColor.RED)
    first = engine.process_shot(outcome)
    second = engine.process_shot(outcome)
    assert first is second
    assert engine.state.current_frame.player_a_score == 1


def test_unconfirmed_shot_waits_without_switching_player() -> None:
    engine = started_engine()
    result = engine.process_shot(
        ShotOutcome("review", Player.PLAYER_A, (BallColor.RED,), confirmed=False, confidence=0.5)
    )
    assert result.status is RuleDecisionStatus.REVIEW_REQUIRED
    assert engine.state.current_frame.current_player is Player.PLAYER_A
    resolved = engine.resolve_review(ShotOutcome("review", Player.PLAYER_A, (BallColor.RED,)))
    assert resolved.status is RuleDecisionStatus.LEGAL


def test_red_count_cannot_underflow() -> None:
    engine = started_engine()
    too_many = (BallColor.RED,) * 16
    with pytest.raises(RuleStateConflict):
        engine.process_shot(shot(engine, "too-many", *too_many))
