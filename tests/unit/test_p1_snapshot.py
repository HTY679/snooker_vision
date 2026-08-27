from __future__ import annotations

from snooker_vision.domain.models import BallColor, Player, RuleDecisionStatus, ShotOutcome
from snooker_vision.rules import EventLog, SnookerRulesEngine


def test_snapshot_restores_scores_turn_phase_and_event_log(tmp_path) -> None:
    log_path = tmp_path / "events.jsonl"
    snapshot_path = tmp_path / "match.json"
    engine = SnookerRulesEngine(EventLog(log_path))
    engine.new_match("Alice", "Bob", best_of=5, match_id="persisted")
    engine.start_frame()
    engine.process_shot(ShotOutcome("red", Player.PLAYER_A, (BallColor.RED,)))
    engine.process_shot(ShotOutcome("black", Player.PLAYER_A, (BallColor.BLACK,)))
    engine.save_snapshot(snapshot_path)

    restored = SnookerRulesEngine.load_snapshot(snapshot_path)
    assert restored.state == engine.state
    assert restored.state.current_frame.player_a_score == 8
    assert restored.state.current_frame.pending_respots == (BallColor.BLACK,)
    assert len(restored.events) == len(engine.events)


def test_snapshot_restores_pending_foul_and_idempotent_shot(tmp_path) -> None:
    snapshot_path = tmp_path / "pending.json"
    engine = SnookerRulesEngine()
    engine.new_match(match_id="pending")
    engine.start_frame()
    outcome = ShotOutcome("white", Player.PLAYER_A, (BallColor.WHITE,))
    candidate = engine.process_shot(outcome)
    engine.save_snapshot(snapshot_path)

    restored = SnookerRulesEngine.load_snapshot(snapshot_path)
    assert restored.pending_fouls[0].event_id == candidate.foul_event_id
    repeated = restored.process_shot(outcome)
    assert repeated.status is RuleDecisionStatus.FOUL_CANDIDATE
    assert repeated.foul_event_id == candidate.foul_event_id


def test_snapshot_rejects_unknown_version(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"version": 999}', encoding="utf-8")
    try:
        SnookerRulesEngine.load_snapshot(path)
    except ValueError as exc:
        assert "version" in str(exc)
    else:
        raise AssertionError("Unknown snapshot versions must be rejected")
