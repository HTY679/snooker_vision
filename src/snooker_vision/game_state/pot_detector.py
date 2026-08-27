from __future__ import annotations

from collections import defaultdict
import logging
from typing import Mapping, Sequence

import cv2
import numpy as np

from snooker_vision.calibration import PocketROI
from snooker_vision.domain.models import Ball, BallColor, Point, PotEvent, PotEvidence, PotStatus, ShotEvent
from snooker_vision.game_state.state_estimator import compare_states


LOGGER = logging.getLogger(__name__)


class PocketActivityTracker:
    def __init__(self, pockets: Sequence[PocketROI]) -> None:
        self.pockets = tuple(pockets)
        self.previous_gray: np.ndarray | None = None
        self.max_activity: dict[str, float] = {pocket.pocket_id: 0.0 for pocket in pockets}

    def reset(self) -> None:
        self.previous_gray = None
        self.max_activity = {pocket.pocket_id: 0.0 for pocket in self.pockets}

    def observe(self, rectified_frame: np.ndarray) -> None:
        gray = cv2.cvtColor(rectified_frame, cv2.COLOR_BGR2GRAY) if rectified_frame.ndim == 3 else rectified_frame
        if self.previous_gray is None:
            self.previous_gray = gray
            return
        difference = cv2.absdiff(self.previous_gray, gray)
        self.previous_gray = gray
        for pocket in self.pockets:
            mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.circle(mask, (round(pocket.x), round(pocket.y)), round(pocket.radius * 1.8), 255, -1)
            pixels = difference[mask > 0]
            activity = float(np.mean(pixels > 15)) if pixels.size else 0.0
            self.max_activity[pocket.pocket_id] = max(self.max_activity[pocket.pocket_id], activity)

    def snapshot(self) -> Mapping[str, float]:
        return dict(self.max_activity)


class PotDetector:
    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config

    @staticmethod
    def _nearest_pocket(point: Point, pockets: Sequence[PocketROI]) -> tuple[PocketROI, float]:
        if not pockets:
            raise ValueError("Pot detection requires six pocket ROIs")
        return min(((pocket, pocket.center.distance_to(point)) for pocket in pockets), key=lambda item: item[1])

    def _evidence_for_ball(
        self,
        ball: Ball,
        pockets: Sequence[PocketROI],
        paths: Mapping[str, Sequence[Point]],
        activity: Mapping[str, float],
        missing_frames: int,
    ) -> tuple[PotEvidence, bool, float]:
        path = tuple(paths.get(ball.id, ()))
        endpoint = path[-1] if path else ball.center
        pocket, endpoint_distance = self._nearest_pocket(endpoint, pockets)
        direction = False
        if len(path) >= 2:
            start_distance = pocket.center.distance_to(path[0])
            direction = start_distance - endpoint_distance >= float(self.config["min_direction_improvement_px"])
        proximity = endpoint_distance <= pocket.radius * float(self.config["pocket_proximity_factor"])
        pocket_activity = float(activity.get(pocket.pocket_id, 0.0))
        strong = (proximity and direction) or pocket_activity >= float(self.config["strong_pocket_activity"])
        confidence = 0.25
        if proximity:
            confidence += 0.25
        if direction:
            confidence += 0.20
        confidence += min(0.25, pocket_activity * 2.0)
        if missing_frames >= int(self.config["missing_confirmation_frames"]):
            confidence += 0.10
        evidence = PotEvidence(
            pocket_id=pocket.pocket_id,
            endpoint_distance=endpoint_distance,
            direction_toward_pocket=direction,
            pocket_activity=pocket_activity,
            missing_frames=missing_frames,
            reason="STRONG_POCKET_EVIDENCE" if strong else "DISAPPEARANCE_WITHOUT_STRONG_POCKET_EVIDENCE",
        )
        return evidence, strong, min(1.0, confidence)

    def detect(
        self,
        shot: ShotEvent,
        pockets: Sequence[PocketROI],
        ball_paths: Mapping[str, Sequence[Point]] | None = None,
        pocket_activity: Mapping[str, float] | None = None,
    ) -> tuple[PotEvent, ...]:
        if shot.after_state is None:
            raise ValueError("Shot must have an After State before pot detection")
        difference = compare_states(shot.before_state, shot.after_state)
        if not difference.missing_balls:
            return ()
        paths = ball_paths or {}
        activities = pocket_activity or {}
        raw: list[tuple[Ball, PotStatus, float, PotEvidence]] = []
        states_confident = min(shot.before_state.confidence, shot.after_state.confidence)
        for ball in difference.missing_balls:
            evidence, strong, evidence_confidence = self._evidence_for_ball(
                ball, pockets, paths, activities, shot.after_state.stable_frames
            )
            confidence = min(states_confident, evidence_confidence)
            if shot.after_state.stable_frames < int(self.config["missing_confirmation_frames"]):
                status = PotStatus.UNKNOWN
            elif strong and confidence >= float(self.config["confirmed_confidence"]):
                status = PotStatus.CONFIRMED
            elif confidence >= float(self.config["candidate_confidence"]):
                status = PotStatus.CANDIDATE
            else:
                status = PotStatus.UNKNOWN
            raw.append((ball, status, confidence, evidence))
        grouped: dict[tuple[BallColor, PotStatus], list[tuple[Ball, float, PotEvidence]]] = defaultdict(list)
        for ball, status, confidence, evidence in raw:
            grouped[(ball.color, status)].append((ball, confidence, evidence))
        events: list[PotEvent] = []
        for index, ((color, status), items) in enumerate(sorted(grouped.items(), key=lambda item: item[0][0].value), start=1):
            event = PotEvent(
                event_id=f"pot-{shot.shot_id}-{color.value.lower()}-{index:02d}",
                shot_id=shot.shot_id,
                ball_color=color,
                count=len(items),
                status=status,
                confidence=min(item[1] for item in items),
                evidence=items[0][2],
            )
            events.append(event)
        shot.potted_balls = tuple(events)
        if any(event.status is not PotStatus.CONFIRMED for event in events):
            LOGGER.warning(
                "pot_review_required",
                extra={"event": {"shot_id": shot.shot_id, "events": [event.event_id for event in events]}},
            )
        else:
            LOGGER.info(
                "pots_confirmed",
                extra={"event": {"shot_id": shot.shot_id, "colors": [event.ball_color.value for event in events]}},
            )
        return tuple(events)

    @staticmethod
    def confirm_candidate(event: PotEvent) -> PotEvent:
        if event.status not in (PotStatus.CANDIDATE, PotStatus.UNKNOWN):
            return event
        event.status = PotStatus.CONFIRMED
        return event

    @staticmethod
    def reject_candidate(event: PotEvent) -> PotEvent:
        if event.status in (PotStatus.CANDIDATE, PotStatus.UNKNOWN):
            event.status = PotStatus.REJECTED
        return event

