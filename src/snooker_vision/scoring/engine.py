from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
from threading import RLock
from typing import Mapping

from snooker_vision.domain.models import (
    BallColor,
    Player,
    PotEvent,
    PotStatus,
    ScoreEvent,
    ScoreboardState,
)


LOGGER = logging.getLogger(__name__)


class ReviewRequired(RuntimeError):
    pass


class PlayerSwitchLocked(RuntimeError):
    pass


@dataclass(slots=True)
class LedgerEntry:
    event: ScoreEvent
    before: ScoreboardState
    after: ScoreboardState


class ScoreEngine:
    """Thread-safe, idempotent P0 score ledger with snapshot-based Undo."""

    def __init__(self, scoring_config: Mapping[str, object]) -> None:
        values = scoring_config["values"]
        if not isinstance(values, Mapping):
            raise ValueError("scoring.values must be a mapping")
        self.values = {BallColor(str(name)): int(value) for name, value in values.items()}
        self.state = ScoreboardState()
        self._ledger: list[LedgerEntry] = []
        self._source_events: dict[str, list[ScoreEvent]] = {}
        self._lock = RLock()

    @property
    def events(self) -> tuple[ScoreEvent, ...]:
        return tuple(entry.event for entry in self._ledger)

    def apply_pot(
        self,
        pot_event: PotEvent,
        player: Player | None = None,
        allow_reconfirm: bool = False,
    ) -> ScoreEvent | None:
        with self._lock:
            if pot_event.status is not PotStatus.CONFIRMED:
                raise ReviewRequired(f"Pot event {pot_event.event_id} is not confirmed")
            value = self.values.get(pot_event.ball_color)
            if value is None:
                return None
            prior = self._source_events.get(pot_event.event_id, [])
            active = next((event for event in reversed(prior) if not event.undone), None)
            if active is not None:
                return active
            if prior and not allow_reconfirm:
                return prior[-1]
            scoring_player = player or self.state.current_player
            delta = value * pot_event.count
            before = self.state
            if scoring_player is Player.PLAYER_A:
                after = replace(
                    before,
                    player_a_score=before.player_a_score + delta,
                    current_break=before.current_break + delta,
                )
            else:
                after = replace(
                    before,
                    player_b_score=before.player_b_score + delta,
                    current_break=before.current_break + delta,
                )
            generation = len(prior) + 1
            suffix = "" if generation == 1 else f"-r{generation}"
            event = ScoreEvent(
                event_id=f"score-{pot_event.event_id}{suffix}",
                player=scoring_player,
                ball_color=pot_event.ball_color,
                score_delta=delta,
                timestamp=datetime.now(timezone.utc),
                source_pot_event_id=pot_event.event_id,
                shot_id=pot_event.shot_id,
            )
            self.state = after
            self._ledger.append(LedgerEntry(event, before, after))
            self._source_events.setdefault(pot_event.event_id, []).append(event)
            LOGGER.info(
                "score_applied",
                extra={"event": {"event_id": event.event_id, "player": scoring_player.value, "delta": delta}},
            )
            return event

    def switch_player(self, locked: bool = False) -> ScoreboardState:
        with self._lock:
            if locked:
                raise PlayerSwitchLocked("Player switch is locked while a shot or review is active")
            self.state = replace(self.state, current_player=self.state.current_player.other(), current_break=0)
            LOGGER.info("player_switched", extra={"event": {"player": self.state.current_player.value}})
            return self.state

    def undo(self) -> ScoreEvent | None:
        with self._lock:
            entry = next((entry for entry in reversed(self._ledger) if not entry.event.undone), None)
            if entry is None:
                LOGGER.warning("undo_ignored_no_history")
                return None
            entry.event.undone = True
            self.state = entry.before
            LOGGER.info("score_undone", extra={"event": {"event_id": entry.event.event_id}})
            return entry.event

