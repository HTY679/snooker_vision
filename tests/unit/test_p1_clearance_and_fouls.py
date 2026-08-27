from __future__ import annotations

from dataclasses import replace

import pytest

from snooker_vision.domain.models import (
    BallColor,
    FoulStatus,
    FrameStatus,
    MatchEventType,
    MatchStatus,
    Player,
    RuleDecisionStatus,
    RulePhase,
    ShotOutcome,
)
from snooker_vision.rules import PendingDecision, SnookerRulesEngine, UnknownFoul


def engine_with_frame(best_of: int = 3) -> SnookerRulesEngine:
    engine = SnookerRulesEngine()
    engine.new_match(best_of=best_of, match_id="match")
    engine.start_frame()
    return engine


def outcome(engine: SnookerRulesEngine, shot_id: str, *colors: BallColor) -> ShotOutcome:
    return ShotOutcome(shot_id, engine.state.current_frame.current_player, tuple(colors))


def set_last_red(engine: SnookerRulesEngine) -> None:
    frame = replace(engine.state.current_frame, remaining_reds=1)
    engine._state = replace(engine.state, current_frame=frame)  # controlled state fixture


def enter_clearance(engine: SnookerRulesEngine) -> None:
    set_last_red(engine)
    engine.process_shot(outcome(engine, "last-red", BallColor.RED))
    engine.process_shot(outcome(engine, "last-color", BallColor.BLACK))
    engine.complete_respot(BallColor.BLACK)
    assert engine.state.current_frame.phase is RulePhase.CLEARANCE


def test_last_red_still_requires_one_color_before_clearance() -> None:
    engine = engine_with_frame()
    set_last_red(engine)
    engine.process_shot(outcome(engine, "last-red", BallColor.RED))
    frame = engine.state.current_frame
    assert frame.remaining_reds == 0 and frame.phase is RulePhase.EXPECT_COLOR
    engine.process_shot(outcome(engine, "last-black", BallColor.BLACK))
    frame = engine.state.current_frame
    assert frame.phase is RulePhase.CLEARANCE
    assert frame.expected_ball is BallColor.YELLOW
    assert frame.pending_respots == (BallColor.BLACK,)


@pytest.mark.parametrize(
    "color,next_color,points",
    [
        (BallColor.YELLOW, BallColor.GREEN, 2),
        (BallColor.GREEN, BallColor.BROWN, 3),
        (BallColor.BROWN, BallColor.BLUE, 4),
        (BallColor.BLUE, BallColor.PINK, 5),
        (BallColor.PINK, BallColor.BLACK, 6),
    ],
)
def test_clearance_advances_in_order(color: BallColor, next_color: BallColor, points: int) -> None:
    engine = engine_with_frame()
    enter_clearance(engine)
    index = list((BallColor.YELLOW, BallColor.GREEN, BallColor.BROWN, BallColor.BLUE, BallColor.PINK)).index(color)
    frame = engine.state.current_frame
    consumed = tuple((BallColor.YELLOW, BallColor.GREEN, BallColor.BROWN, BallColor.BLUE, BallColor.PINK)[:index])
    score = sum({BallColor.YELLOW: 2, BallColor.GREEN: 3, BallColor.BROWN: 4, BallColor.BLUE: 5, BallColor.PINK: 6}[item] for item in consumed)
    frame = replace(
        frame,
        expected_ball=color,
        colors_on_table=tuple(item for item in frame.colors_on_table if item not in consumed),
        player_a_score=frame.player_a_score + score,
        current_break=frame.current_break + score,
    )
    engine._state = replace(engine.state, current_frame=frame)  # controlled state fixture
    result = engine.process_shot(outcome(engine, f"clear-{color.value}", color))
    assert result.points == points
    assert engine.state.current_frame.expected_ball is next_color
    assert color not in engine.state.current_frame.colors_on_table
    assert engine.state.current_frame.pending_respots == ()


def test_clearance_miss_switches_player_without_advancing() -> None:
    engine = engine_with_frame()
    enter_clearance(engine)
    engine.process_shot(outcome(engine, "yellow-miss"))
    frame = engine.state.current_frame
    assert frame.current_player is Player.PLAYER_B
    assert frame.expected_ball is BallColor.YELLOW


def test_wrong_clearance_ball_creates_candidate_and_does_not_advance() -> None:
    engine = engine_with_frame()
    enter_clearance(engine)
    before = engine.state
    decision = engine.process_shot(outcome(engine, "wrong-green", BallColor.GREEN))
    assert decision.status is RuleDecisionStatus.FOUL_CANDIDATE
    assert decision.penalty_points == 4
    assert engine.state == before
    assert engine.pending_fouls[0].reasons == ("CLEARANCE_ORDER",)


@pytest.mark.parametrize(
    "color,expected_penalty",
    [
        (BallColor.YELLOW, 4),
        (BallColor.BLUE, 5),
        (BallColor.PINK, 6),
        (BallColor.BLACK, 7),
    ],
)
def test_wrong_ball_foul_penalty_uses_minimum_or_involved_value(
    color: BallColor, expected_penalty: int
) -> None:
    engine = engine_with_frame()
    decision = engine.process_shot(outcome(engine, f"wrong-{color.value}", color))
    assert decision.penalty_points == expected_penalty


def test_white_and_target_ball_are_aggregated_into_one_foul() -> None:
    engine = engine_with_frame()
    decision = engine.process_shot(outcome(engine, "white-red", BallColor.WHITE, BallColor.RED))
    assert decision.status is RuleDecisionStatus.FOUL_CANDIDATE
    assert len(engine.pending_fouls) == 1
    assert engine.pending_fouls[0].reasons == ("CUE_BALL_POTTED",)


def test_multiple_foul_reasons_create_one_penalty_and_switch() -> None:
    engine = engine_with_frame()
    decision = engine.process_shot(outcome(engine, "multi", BallColor.WHITE, BallColor.BLACK))
    foul_id = decision.foul_event_id
    assert foul_id is not None
    confirmed = engine.confirm_foul(foul_id)
    frame = engine.state.current_frame
    assert confirmed.status is RuleDecisionStatus.FOUL_CONFIRMED
    assert confirmed.penalty_points == 7
    assert frame.player_a_score == 0 and frame.player_b_score == 7
    assert frame.current_player is Player.PLAYER_B
    assert engine.confirm_foul(foul_id) is confirmed
    assert frame.player_b_score == 7
    foul_events = [event for event in engine.events if event.event_type is MatchEventType.FOUL_CONFIRMED]
    assert len(foul_events) == 1


def test_foul_confirmation_blocks_next_shot_until_respot() -> None:
    engine = engine_with_frame()
    decision = engine.process_shot(outcome(engine, "wrong-black", BallColor.BLACK))
    assert decision.foul_event_id is not None
    engine.confirm_foul(decision.foul_event_id)
    assert engine.state.current_frame.pending_respots == (BallColor.BLACK,)
    with pytest.raises(PendingDecision):
        engine.process_shot(outcome(engine, "blocked", BallColor.RED))
    engine.complete_respot(BallColor.BLACK)
    assert engine.state.current_frame.pending_respots == ()


def test_cancel_foul_has_no_state_side_effect_and_allows_redetection() -> None:
    engine = engine_with_frame()
    before = engine.state
    candidate = engine.process_shot(outcome(engine, "wrong", BallColor.BLACK))
    assert candidate.foul_event_id is not None
    cancelled = engine.cancel_foul(candidate.foul_event_id)
    assert cancelled.status is RuleDecisionStatus.FOUL_CANCELLED
    assert engine.state == before
    repeated = engine.process_shot(outcome(engine, "wrong", BallColor.BLACK))
    assert repeated.status is RuleDecisionStatus.FOUL_CANDIDATE
    assert repeated.foul_event_id != candidate.foul_event_id
    with pytest.raises(UnknownFoul):
        engine.cancel_foul(candidate.foul_event_id)


def test_undo_confirmed_foul_restores_scores_player_and_candidate() -> None:
    engine = engine_with_frame()
    candidate = engine.process_shot(outcome(engine, "white", BallColor.WHITE))
    assert candidate.foul_event_id is not None
    engine.confirm_foul(candidate.foul_event_id)
    engine.undo()
    frame = engine.state.current_frame
    assert frame.player_b_score == 0 and frame.current_player is Player.PLAYER_A
    assert engine.pending_fouls[0].status is FoulStatus.CANDIDATE


def test_undo_legal_color_restores_phase_score_and_respot() -> None:
    engine = engine_with_frame()
    engine.process_shot(outcome(engine, "red", BallColor.RED))
    before_color = engine.state
    engine.process_shot(outcome(engine, "black", BallColor.BLACK))
    engine.undo()
    assert engine.state == before_color
    assert engine.state.current_frame.pending_respots == ()


def test_final_black_finishes_frame_and_match_for_best_of_one() -> None:
    engine = engine_with_frame(best_of=1)
    enter_clearance(engine)
    frame = replace(
        engine.state.current_frame,
        expected_ball=BallColor.BLACK,
        colors_on_table=(BallColor.BLACK,),
    )
    engine._state = replace(engine.state, current_frame=frame)  # controlled state fixture
    engine.process_shot(outcome(engine, "final-black", BallColor.BLACK))
    assert engine.state.current_frame.status is FrameStatus.FINISHED
    assert engine.state.current_frame.winner is Player.PLAYER_A
    assert engine.state.status is MatchStatus.FINISHED
    assert engine.state.winner is Player.PLAYER_A
    with pytest.raises(Exception):
        engine.process_shot(ShotOutcome("after-end", Player.PLAYER_A, (BallColor.RED,)))


def test_tied_frame_enters_respotted_black_and_next_score_wins() -> None:
    engine = engine_with_frame(best_of=1)
    frame = replace(engine.state.current_frame, player_a_score=20, player_b_score=20)
    engine._state = replace(engine.state, current_frame=frame)  # controlled state fixture
    engine.end_frame()
    assert engine.state.current_frame.phase is RulePhase.RESPOTTED_BLACK
    engine.process_shot(outcome(engine, "tie-black", BallColor.BLACK))
    assert engine.state.status is MatchStatus.FINISHED
    assert engine.state.current_frame.winner is Player.PLAYER_A


def test_best_of_three_requires_two_frame_wins_and_starts_next_frame() -> None:
    engine = engine_with_frame(best_of=3)
    frame = replace(engine.state.current_frame, player_a_score=1)
    engine._state = replace(engine.state, current_frame=frame)  # controlled state fixture
    engine.end_frame()
    assert engine.state.player_a_frames == 1 and engine.state.status is MatchStatus.PLAYING
    engine.start_frame()
    assert engine.state.current_frame.frame_number == 2
    frame = replace(engine.state.current_frame, player_a_score=1)
    engine._state = replace(engine.state, current_frame=frame)  # controlled state fixture
    engine.end_frame()
    assert engine.state.status is MatchStatus.FINISHED
    assert engine.state.player_a_frames == 2


def test_undo_frame_finishing_shot_reopens_frame_and_match() -> None:
    engine = engine_with_frame(best_of=1)
    frame = replace(
        engine.state.current_frame,
        remaining_reds=0,
        phase=RulePhase.CLEARANCE,
        expected_ball=BallColor.BLACK,
        colors_on_table=(BallColor.BLACK,),
        player_a_score=10,
    )
    engine._state = replace(engine.state, current_frame=frame)  # controlled state fixture
    engine.process_shot(outcome(engine, "finish", BallColor.BLACK))
    engine.undo()
    assert engine.state.status is MatchStatus.PLAYING
    assert engine.state.current_frame.status is FrameStatus.PLAYING
    assert engine.state.current_frame.expected_ball is BallColor.BLACK
