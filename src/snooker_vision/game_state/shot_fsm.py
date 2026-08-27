from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Mapping
from uuid import uuid4

from snooker_vision.domain.models import (
    MotionObservation,
    MotionState,
    Player,
    ShotEvent,
    ShotStatus,
    TableState,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ShotTransition:
    started: bool = False
    completed: bool = False
    review_required: bool = False
    shot: ShotEvent | None = None


class ShotFSM:
    def __init__(self, shot_config: Mapping[str, object], min_state_confidence: float) -> None:
        self.minimum_duration = float(shot_config["minimum_duration_seconds"])
        self.min_state_confidence = min_state_confidence
        self.last_stable_state: TableState | None = None
        self.active_shot: ShotEvent | None = None

    @property
    def locked(self) -> bool:
        return self.active_shot is not None

    def reset(self) -> None:
        self.last_stable_state = None
        self.active_shot = None

    def update(
        self,
        observation: MotionObservation,
        timestamp: datetime,
        stable_state: TableState | None,
        player: Player,
    ) -> ShotTransition:
        if not observation.valid:
            return ShotTransition(shot=self.active_shot)
        if stable_state is not None and self.active_shot is None:
            self.last_stable_state = stable_state
        if observation.state is MotionState.MOVING and self.active_shot is None:
            if self.last_stable_state is None:
                return ShotTransition(review_required=True)
            self.active_shot = ShotEvent(
                shot_id=f"shot-{uuid4().hex}",
                player=player,
                before_state=self.last_stable_state,
                started_at=timestamp,
            )
            LOGGER.info(
                "shot_started",
                extra={"event": {"shot_id": self.active_shot.shot_id, "player": player.value}},
            )
            return ShotTransition(started=True, shot=self.active_shot)
        if self.active_shot is None:
            return ShotTransition()
        if observation.state is MotionState.MOVING:
            self.active_shot.status = ShotStatus.IN_PROGRESS
            return ShotTransition(shot=self.active_shot)
        self.active_shot.status = ShotStatus.SETTLING
        if stable_state is None or stable_state.timestamp <= self.active_shot.started_at:
            return ShotTransition(shot=self.active_shot)
        duration = (timestamp - self.active_shot.started_at).total_seconds()
        self.active_shot.after_state = stable_state
        self.active_shot.ended_at = timestamp
        if duration < self.minimum_duration or stable_state.confidence < self.min_state_confidence:
            self.active_shot.status = ShotStatus.REVIEW_REQUIRED
            LOGGER.warning(
                "shot_review_required",
                extra={"event": {"shot_id": self.active_shot.shot_id, "confidence": stable_state.confidence}},
            )
            return ShotTransition(review_required=True, shot=self.active_shot)
        self.active_shot.status = ShotStatus.COMPLETED
        completed = self.active_shot
        self.last_stable_state = stable_state
        self.active_shot = None
        LOGGER.info("shot_completed", extra={"event": {"shot_id": completed.shot_id}})
        return ShotTransition(completed=True, shot=completed)

    def resolve_review(self, accept: bool) -> ShotEvent | None:
        if self.active_shot is None or self.active_shot.status is not ShotStatus.REVIEW_REQUIRED:
            return None
        shot = self.active_shot
        if accept and shot.after_state is not None:
            shot.status = ShotStatus.COMPLETED
            self.last_stable_state = shot.after_state
        else:
            shot.status = ShotStatus.REVERTED
        self.active_shot = None
        return shot

