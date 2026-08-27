from __future__ import annotations

from datetime import datetime, timezone

from snooker_vision.domain.models import MatchEvent, MatchEventType, Player
from snooker_vision.rules import EventLog


def make_event(event_id: str, event_type: MatchEventType = MatchEventType.SCORE) -> MatchEvent:
    return MatchEvent(
        event_id,
        event_type,
        "match",
        1,
        datetime.now(timezone.utc),
        Player.PLAYER_A,
        f"shot-{event_id}",
        1,
        {"source": "test"},
    )


def test_event_log_is_idempotent_queryable_and_persistent(tmp_path) -> None:
    path = tmp_path / "match-events.jsonl"
    log = EventLog(path)
    event = make_event("one")
    assert log.append(event) is event
    assert log.append(event) is event
    assert len(log.events) == 1
    assert log.for_frame(1) == (event,)
    assert log.for_shot("shot-one") == (event,)

    loaded = EventLog(path)
    assert len(loaded.events) == 1
    assert loaded.events[0].event_id == "one"
    assert loaded.events[0].timestamp.tzinfo is not None


def test_undo_audit_record_marks_prior_events_after_reload(tmp_path) -> None:
    path = tmp_path / "match-events.jsonl"
    log = EventLog(path)
    log.append(make_event("score"))
    log.append(
        MatchEvent(
            "undo",
            MatchEventType.UNDO,
            "match",
            1,
            datetime.now(timezone.utc),
            details={"undone_event_ids": ["score"]},
        )
    )
    loaded = EventLog(path)
    assert loaded.events[0].undone
    assert loaded.events[1].event_type is MatchEventType.UNDO


def test_event_log_handles_more_than_one_thousand_events_in_memory() -> None:
    log = EventLog()
    for index in range(1100):
        log.append(make_event(f"event-{index}"))
    assert len(log.events) == 1100
    assert log.events[-1].event_id == "event-1099"
