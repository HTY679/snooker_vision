from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from snooker_vision.application import P1Application
from snooker_vision.domain.models import (
    Ball,
    BallColor,
    MotionState,
    Player,
    PotEvent,
    PotStatus,
    RuleDecisionStatus,
    ShotEvent,
    ShotStatus,
    TableState,
)
from snooker_vision.rules import PendingDecision


def table_state(timestamp: datetime, colors: list[BallColor]) -> TableState:
    balls = tuple(
        Ball(f"{color.value}-{index}", color, 50 + index * 20, 100, 8, 0.99)
        for index, color in enumerate(colors)
    )
    return TableState(timestamp, balls, MotionState.STATIC, 0.99, stable_frames=5)


def recorded_shot(
    app: P1Application,
    shot_id: str,
    *colors: BallColor,
    status: PotStatus = PotStatus.CONFIRMED,
) -> tuple[ShotEvent, tuple[PotEvent, ...]]:
    now = datetime.now(timezone.utc)
    before = table_state(now, [BallColor.RED, BallColor.BLACK, BallColor.WHITE])
    after = table_state(now + timedelta(seconds=1), [BallColor.BLACK, BallColor.WHITE])
    shot = ShotEvent(
        shot_id,
        app.rules.state.current_frame.current_player,
        before,
        now,
        ShotStatus.COMPLETED,
        after,
        ended_at=after.timestamp,
    )
    pots = tuple(
        PotEvent(f"pot-{shot_id}-{index}", shot_id, color, 1, status, 0.99)
        for index, color in enumerate(colors)
    )
    return shot, pots


@pytest.mark.integration
def test_p1_application_commits_whole_shot_and_syncs_view(config: dict[str, object], tmp_path) -> None:
    app = P1Application(config, tmp_path)
    app.new_match("Alice", "Bob", best_of=3, match_id="app")
    app.start_frame()
    red_shot, red_pots = recorded_shot(app, "red", BallColor.RED)
    red = app.commit_rule_shot(red_shot, red_pots)
    assert red is not None and red.points == 1
    black_shot, black_pots = recorded_shot(app, "black", BallColor.BLACK)
    black = app.commit_rule_shot(black_shot, black_pots)
    assert black is not None and black.points == 7
    view = app.view_state()
    assert view.scoreboard.player_a_score == 8
    assert view.match is not None and view.match.current_frame.player_a_score == 8
    assert view.match.current_frame.pending_respots == (BallColor.BLACK,)
    assert (tmp_path / "active-match.json").exists()
    assert (tmp_path / "match-events.jsonl").exists()


@pytest.mark.integration
def test_p1_application_candidate_pot_waits_for_review(config: dict[str, object]) -> None:
    app = P1Application(config)
    app.new_match(match_id="review")
    app.start_frame()
    shot, pots = recorded_shot(app, "candidate", BallColor.RED, status=PotStatus.CANDIDATE)
    assert app.commit_rule_shot(shot, pots) is None
    assert app.rules.state.current_frame.player_a_score == 0
    app.confirm_pot(pots[0].event_id)
    assert app.rules.state.current_frame.player_a_score == 1


@pytest.mark.integration
def test_p1_application_foul_confirmation_and_undo(config: dict[str, object]) -> None:
    app = P1Application(config)
    app.new_match(match_id="foul")
    app.start_frame()
    shot, pots = recorded_shot(app, "white", BallColor.WHITE)
    decision = app.commit_rule_shot(shot, pots)
    assert decision is not None and decision.status is RuleDecisionStatus.FOUL_CANDIDATE
    assert decision.foul_event_id is not None
    app.confirm_foul(decision.foul_event_id)
    assert app.view_state().scoreboard.player_b_score == 4
    app.undo()
    assert app.view_state().scoreboard.player_b_score == 0
    assert app.rules.state.current_frame.current_player is Player.PLAYER_A


@pytest.mark.integration
def test_p1_application_respot_gate_prevents_next_visual_shot(config: dict[str, object]) -> None:
    app = P1Application(config)
    app.new_match(match_id="respot")
    app.start_frame()
    red_shot, red_pots = recorded_shot(app, "red", BallColor.RED)
    app.commit_rule_shot(red_shot, red_pots)
    black_shot, black_pots = recorded_shot(app, "black", BallColor.BLACK)
    app.commit_rule_shot(black_shot, black_pots)
    next_shot, next_pots = recorded_shot(app, "next-red", BallColor.RED)
    with pytest.raises(PendingDecision):
        app.commit_rule_shot(next_shot, next_pots)


@pytest.mark.integration
def test_p1_application_can_restore_persisted_match(config: dict[str, object], tmp_path) -> None:
    app = P1Application(config, tmp_path)
    app.new_match(match_id="restore")
    app.start_frame()
    shot, pots = recorded_shot(app, "red", BallColor.RED)
    app.commit_rule_shot(shot, pots)
    restored = P1Application.restore(
        config,
        tmp_path / "active-match.json",
        tmp_path / "match-events.jsonl",
    )
    assert restored.view_state().scoreboard.player_a_score == 1
    assert restored.rules.state.current_frame.current_player is Player.PLAYER_A
