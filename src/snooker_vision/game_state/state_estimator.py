from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
import logging
from statistics import median
from typing import Mapping, Sequence

from snooker_vision.domain.models import Ball, BallColor, MotionState, TableState


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StateDiff:
    missing_balls: tuple[Ball, ...]
    added_balls: tuple[Ball, ...]
    count_delta: Mapping[BallColor, int]


def compare_states(before: TableState, after: TableState) -> StateDiff:
    deltas: dict[BallColor, int] = {}
    missing: list[Ball] = []
    added: list[Ball] = []
    for color in BallColor:
        before_balls = [ball for ball in before.balls if ball.color is color]
        after_balls = [ball for ball in after.balls if ball.color is color]
        delta = len(after_balls) - len(before_balls)
        deltas[color] = delta
        if delta < 0:
            missing.extend(sorted(before_balls, key=lambda ball: (ball.y, ball.x))[: -delta])
        elif delta > 0:
            added.extend(sorted(after_balls, key=lambda ball: (ball.y, ball.x))[:delta])
    return StateDiff(tuple(missing), tuple(added), deltas)


class StableStateEstimator:
    def __init__(self, config: Mapping[str, object]) -> None:
        self.confirmation_frames = int(config["confirmation_frames"])
        self.position_tolerance = float(config["position_tolerance_px"])
        self.min_confidence = float(config["min_state_confidence"])
        self._observations: deque[tuple[datetime, tuple[Ball, ...], int | None]] = deque(
            maxlen=self.confirmation_frames
        )

    def reset(self) -> None:
        self._observations.clear()

    def add(
        self,
        timestamp: datetime,
        balls: Sequence[Ball],
        motion_state: MotionState,
        frame_index: int | None = None,
    ) -> TableState | None:
        if motion_state is not MotionState.STATIC:
            self.reset()
            return None
        self._observations.append((timestamp, tuple(balls), frame_index))
        if len(self._observations) < self.confirmation_frames:
            return None
        latest = self._observations[-1][1]
        stable_balls: list[Ball] = []
        supports: list[float] = []
        used_by_frame: list[set[int]] = [set() for _ in self._observations]
        for latest_index, anchor in enumerate(latest):
            matches: list[Ball] = []
            for frame_index_in_window, (_, candidates, _) in enumerate(self._observations):
                ranked = sorted(
                    (
                        (anchor.center.distance_to(candidate.center), candidate_index, candidate)
                        for candidate_index, candidate in enumerate(candidates)
                        if candidate.color is anchor.color and candidate_index not in used_by_frame[frame_index_in_window]
                    ),
                    key=lambda item: item[0],
                )
                if ranked and ranked[0][0] <= self.position_tolerance:
                    _, candidate_index, candidate = ranked[0]
                    used_by_frame[frame_index_in_window].add(candidate_index)
                    matches.append(candidate)
            support = len(matches) / self.confirmation_frames
            if support < 0.67:
                continue
            confidence = float(median(ball.confidence for ball in matches)) * support
            stable_balls.append(
                Ball(
                    id=f"stable-{anchor.color.value.lower()}-{latest_index:02d}",
                    color=anchor.color,
                    x=float(median(ball.x for ball in matches)),
                    y=float(median(ball.y for ball in matches)),
                    radius=float(median(ball.radius for ball in matches)),
                    confidence=max(0.0, min(1.0, confidence)),
                )
            )
            supports.append(support)
        count_consistency = 1.0 - (
            max(len(item[1]) for item in self._observations) - min(len(item[1]) for item in self._observations)
        ) / max(1.0, max(len(item[1]) for item in self._observations))
        if stable_balls:
            confidence = float(median(ball.confidence for ball in stable_balls)) * max(0.0, count_consistency)
        else:
            # An empty detection window is not evidence of an empty snooker table.
            # It most commonly means occlusion or detector failure and must never
            # become a high-confidence After State that pots every missing ball.
            confidence = 0.0
        state = TableState(
            timestamp=self._observations[-1][0],
            balls=tuple(stable_balls),
            motion_state=MotionState.STATIC,
            confidence=max(0.0, min(1.0, confidence)),
            stable_frames=len(self._observations),
            source_frame=self._observations[-1][2],
        )
        LOGGER.info(
            "stable_table_state",
            extra={"event": {"balls": len(state.balls), "confidence": state.confidence}},
        )
        return state


def states_continuous(previous_after: TableState, next_before: TableState, tolerance: int = 0) -> bool:
    return all(
        abs(previous_after.color_counts.for_color(color) - next_before.color_counts.for_color(color)) <= tolerance
        for color in BallColor
    )
