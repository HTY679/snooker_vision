from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from snooker_vision.domain.models import MatchEvent, MatchEventType, Player


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


class EventLog:
    """Append-only match audit log with optional JSONL persistence."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._events: list[MatchEvent] = []
        self._ids: set[str] = set()
        self._lock = RLock()
        if self.path is not None and self.path.exists():
            self._load()

    @property
    def events(self) -> tuple[MatchEvent, ...]:
        return tuple(self._events)

    def append(self, event: MatchEvent) -> MatchEvent:
        with self._lock:
            if event.event_id in self._ids:
                return next(item for item in self._events if item.event_id == event.event_id)
            self._events.append(event)
            self._ids.add(event.event_id)
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(_jsonable(asdict(event)), ensure_ascii=False, sort_keys=True))
                    stream.write("\n")
            return event

    def mark_undone(self, event_ids: Iterable[str]) -> None:
        targets = set(event_ids)
        for event in self._events:
            if event.event_id in targets:
                event.undone = True

    def for_frame(self, frame_number: int) -> tuple[MatchEvent, ...]:
        return tuple(event for event in self._events if event.frame_number == frame_number)

    def for_shot(self, shot_id: str) -> tuple[MatchEvent, ...]:
        return tuple(event for event in self._events if event.shot_id == shot_id)

    def _load(self) -> None:
        assert self.path is not None
        undone_ids: set[str] = set()
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                payload = json.loads(line)
                event = MatchEvent(
                    event_id=str(payload["event_id"]),
                    event_type=MatchEventType(payload["event_type"]),
                    match_id=str(payload["match_id"]),
                    frame_number=int(payload["frame_number"]),
                    timestamp=datetime.fromisoformat(payload["timestamp"]),
                    player=Player(payload["player"]) if payload.get("player") else None,
                    shot_id=payload.get("shot_id"),
                    score_delta=int(payload.get("score_delta", 0)),
                    details=dict(payload.get("details", {})),
                    undone=bool(payload.get("undone", False)),
                )
                self._events.append(event)
                self._ids.add(event.event_id)
                if event.event_type is MatchEventType.UNDO:
                    undone_ids.update(str(item) for item in event.details.get("undone_event_ids", []))
        self.mark_undone(undone_ids)
