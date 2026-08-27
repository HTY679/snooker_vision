from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from snooker_vision.calibration import (
    CalibrationData,
    CalibrationError,
    CalibrationStore,
    PerspectiveTransformer,
)
from snooker_vision.classification import BallColorClassifier
from snooker_vision.detection import BallDetector
from snooker_vision.domain.models import (
    Ball,
    MotionObservation,
    Player,
    PotEvent,
    PotStatus,
    ScoreEvent,
    ScoreboardState,
    ShotEvent,
    ShotStatus,
    SystemStatus,
    TableState,
)
from snooker_vision.game_state import PocketActivityTracker, PotDetector, ShotFSM, StableStateEstimator
from snooker_vision.input import FrameQualityGate
from snooker_vision.motion import MotionDetector
from snooker_vision.scoring import PlayerSwitchLocked, ScoreEngine


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class P0ViewState:
    scoreboard: ScoreboardState
    system_status: SystemStatus
    motion: str
    last_shot: ShotEvent | None
    last_pot: PotEvent | None
    last_score_event: ScoreEvent | None
    stable_state: TableState | None
    review_events: tuple[PotEvent, ...]
    message: str


@dataclass(slots=True)
class ApplicationUndoRecord:
    score_event_id: str
    prior_last_shot: ShotEvent | None
    prior_last_pot: PotEvent | None
    prior_stable_state: TableState | None
    shot: ShotEvent
    pot_event: PotEvent


class P0Application:
    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config
        self.calibration: CalibrationData | None = None
        self.transformer: PerspectiveTransformer | None = None
        self.quality_gate = FrameQualityGate(config["input"])  # type: ignore[arg-type]
        self.detector = BallDetector(config["detection"])  # type: ignore[arg-type]
        self.classifier = BallColorClassifier(config["classification"])  # type: ignore[arg-type]
        self.motion = MotionDetector(config["motion"])  # type: ignore[arg-type]
        self.state_estimator = StableStateEstimator(config["state"])  # type: ignore[arg-type]
        self.shot_fsm = ShotFSM(
            config["shot"], float(config["state"]["min_state_confidence"])  # type: ignore[index,arg-type]
        )
        self.pot_detector = PotDetector(config["pot"])  # type: ignore[arg-type]
        self.score_engine = ScoreEngine(config["scoring"])  # type: ignore[arg-type]
        self.pocket_activity: PocketActivityTracker | None = None
        self.status = SystemStatus.UNCALIBRATED
        self.last_shot: ShotEvent | None = None
        self.last_pot: PotEvent | None = None
        self.last_score_event: ScoreEvent | None = None
        self.last_stable_state: TableState | None = None
        self.review_events: list[PotEvent] = []
        self.message = "Calibration required"
        self._undo_records: list[ApplicationUndoRecord] = []

    def load_calibration(self, path: str | Path) -> CalibrationData:
        calibration = CalibrationStore.load(path, self.config["calibration"])  # type: ignore[arg-type]
        self.set_calibration(calibration)
        return calibration

    def set_calibration(self, calibration: CalibrationData) -> None:
        self.calibration = calibration
        self.transformer = PerspectiveTransformer(calibration)
        self.pocket_activity = PocketActivityTracker(calibration.pockets)
        self.quality_gate.set_expected_resolution(calibration.frame_width, calibration.frame_height)
        self.status = SystemStatus.READY
        self.message = "Ready"
        LOGGER.info("application_calibrated")

    def _commit_pot(self, shot: ShotEvent, pot: PotEvent, allow_reconfirm: bool = False) -> ScoreEvent | None:
        prior_shot, prior_pot, prior_state = self.last_shot, self.last_pot, self.last_stable_state
        score_event = self.score_engine.apply_pot(pot, shot.player, allow_reconfirm)
        if score_event is None or score_event.undone:
            return score_event
        if not any(record.score_event_id == score_event.event_id for record in self._undo_records):
            self._undo_records.append(
                ApplicationUndoRecord(score_event.event_id, prior_shot, prior_pot, prior_state, shot, pot)
            )
        self.last_shot = shot
        self.last_pot = pot
        self.last_score_event = score_event
        self.last_stable_state = shot.after_state
        return score_event

    def process_frame(
        self, frame: np.ndarray, timestamp: datetime | None = None, frame_index: int | None = None
    ) -> P0ViewState:
        timestamp = timestamp or datetime.now(timezone.utc)
        quality = self.quality_gate.evaluate(frame)
        if not quality.valid:
            self.status = SystemStatus.CAMERA_ERROR
            self.message = quality.reason
            LOGGER.error("invalid_frame", extra={"event": {"reason": quality.reason}})
            return self.view_state()
        if self.transformer is None or self.calibration is None:
            self.status = SystemStatus.UNCALIBRATED
            self.message = "Calibration required"
            return self.view_state()
        try:
            rectified = self.transformer.warp(frame)
        except CalibrationError as exc:
            self.status = SystemStatus.CALIBRATION_INVALID
            self.message = str(exc)
            LOGGER.exception("calibration_invalid")
            return self.view_state()
        motion = self.motion.update(rectified)
        if not motion.valid and motion.reason == "CAMERA_SHIFT":
            self.status = SystemStatus.CALIBRATION_INVALID
            self.message = "Camera moved; recalibration required"
            return self.view_state()
        stable_state: TableState | None = None
        if motion.state.value == "STATIC":
            balls = self.detector.detect(rectified, motion.state, self.calibration.pockets)
            balls = self.classifier.classify_balls(rectified, balls)
            stable_state = self.state_estimator.add(timestamp, balls, motion.state, frame_index)
            if stable_state is not None and self.shot_fsm.active_shot is None:
                self.last_stable_state = stable_state
        else:
            self.state_estimator.reset()
        transition = self.shot_fsm.update(
            motion, timestamp, stable_state, self.score_engine.state.current_player
        )
        if transition.started and self.pocket_activity is not None:
            self.pocket_activity.reset()
        if self.shot_fsm.active_shot is not None and self.pocket_activity is not None:
            self.pocket_activity.observe(rectified)
        if motion.state.value == "MOVING":
            self.status = SystemStatus.MOVING
            self.message = "Shot in progress"
        elif self.shot_fsm.active_shot is not None:
            self.status = SystemStatus.SETTLING
            self.message = "Waiting for stable After State"
        else:
            self.status = SystemStatus.READY
            self.message = "Ready"
        if transition.review_required:
            self.status = SystemStatus.REVIEW_REQUIRED
            self.message = "Shot state confidence requires review"
        if transition.completed and transition.shot is not None:
            shot = transition.shot
            events = self.pot_detector.detect(
                shot,
                self.calibration.pockets,
                pocket_activity=self.pocket_activity.snapshot() if self.pocket_activity else {},
            )
            auto_threshold = float(self.config["app"]["auto_commit_confidence"])  # type: ignore[index]
            for event in events:
                if event.status is PotStatus.CONFIRMED and event.confidence >= auto_threshold:
                    self._commit_pot(shot, event)
                elif event.status in (PotStatus.CANDIDATE, PotStatus.UNKNOWN):
                    self.review_events.append(event)
            self.last_shot = shot
            self.last_stable_state = shot.after_state
            if self.review_events:
                self.status = SystemStatus.REVIEW_REQUIRED
                self.message = "Pot candidate requires confirmation"
            else:
                self.status = SystemStatus.READY
                self.message = "Shot completed"
        return self.view_state()

    def commit_recorded_shot(self, shot: ShotEvent, pot_events: Sequence[PotEvent]) -> tuple[ScoreEvent, ...]:
        """Non-visual fixture path used by the deterministic P0 demo and integration tests."""
        if shot.status is not ShotStatus.COMPLETED or shot.after_state is None:
            raise ValueError("Recorded shot must be completed and contain an After State")
        score_events: list[ScoreEvent] = []
        shot.potted_balls = tuple(pot_events)
        for pot in pot_events:
            if pot.status is PotStatus.CONFIRMED:
                result = self._commit_pot(shot, pot)
                if result is not None:
                    score_events.append(result)
            else:
                self.review_events.append(pot)
        self.last_shot = shot
        self.last_stable_state = shot.after_state
        self.status = SystemStatus.REVIEW_REQUIRED if self.review_events else SystemStatus.READY
        return tuple(score_events)

    def confirm_pot(self, event_id: str) -> ScoreEvent | None:
        event = next((item for item in self.review_events if item.event_id == event_id), None)
        if event is None or self.last_shot is None:
            raise KeyError(f"Unknown pending pot event: {event_id}")
        self.pot_detector.confirm_candidate(event)
        result = self._commit_pot(self.last_shot, event, allow_reconfirm=True)
        self.review_events.remove(event)
        self.status = SystemStatus.REVIEW_REQUIRED if self.review_events else SystemStatus.READY
        return result

    def reject_pot(self, event_id: str) -> None:
        event = next((item for item in self.review_events if item.event_id == event_id), None)
        if event is None:
            raise KeyError(f"Unknown pending pot event: {event_id}")
        self.pot_detector.reject_candidate(event)
        self.review_events.remove(event)
        self.status = SystemStatus.REVIEW_REQUIRED if self.review_events else SystemStatus.READY

    def switch_player(self) -> ScoreboardState:
        locked = self.shot_fsm.locked or bool(self.review_events)
        state = self.score_engine.switch_player(locked)
        self.message = f"Current player: {state.current_player.value}"
        return state

    def undo(self) -> ScoreEvent | None:
        undone = self.score_engine.undo()
        if undone is None:
            self.message = "Nothing to undo"
            return None
        record = next((item for item in reversed(self._undo_records) if item.score_event_id == undone.event_id), None)
        if record is not None:
            record.pot_event.status = PotStatus.REVERTED
            record.shot.status = ShotStatus.REVERTED
            self.last_shot = record.prior_last_shot
            self.last_pot = record.prior_last_pot
            self.last_stable_state = record.prior_stable_state
        self.last_score_event = next((event for event in reversed(self.score_engine.events) if not event.undone), None)
        self.status = SystemStatus.READY
        self.message = f"Undid {undone.score_delta:+d}"
        return undone

    def view_state(self) -> P0ViewState:
        return P0ViewState(
            scoreboard=self.score_engine.state,
            system_status=self.status,
            motion=self.motion.state.value,
            last_shot=self.last_shot,
            last_pot=self.last_pot,
            last_score_event=self.last_score_event,
            stable_state=self.last_stable_state,
            review_events=tuple(self.review_events),
            message=self.message,
        )
