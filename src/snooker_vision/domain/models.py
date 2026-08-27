from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from math import hypot, isfinite
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BallColor(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"
    BROWN = "BROWN"
    BLUE = "BLUE"
    PINK = "PINK"
    BLACK = "BLACK"
    WHITE = "WHITE"
    UNKNOWN = "UNKNOWN"


class MotionState(str, Enum):
    STATIC = "STATIC"
    MOVING = "MOVING"


class Player(str, Enum):
    PLAYER_A = "PLAYER_A"
    PLAYER_B = "PLAYER_B"

    def other(self) -> "Player":
        return Player.PLAYER_B if self is Player.PLAYER_A else Player.PLAYER_A


class ShotStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SETTLING = "SETTLING"
    COMPLETED = "COMPLETED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVERTED = "REVERTED"


class PotStatus(str, Enum):
    CANDIDATE = "POT_CANDIDATE"
    CONFIRMED = "CONFIRMED_POT"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    REVERTED = "REVERTED"


class SystemStatus(str, Enum):
    UNCALIBRATED = "UNCALIBRATED"
    READY = "READY"
    MOVING = "MOVING"
    SETTLING = "SETTLING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CAMERA_ERROR = "CAMERA_ERROR"
    CALIBRATION_INVALID = "CALIBRATION_INVALID"


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not (isfinite(self.x) and isfinite(self.y)):
            raise ValueError("Point coordinates must be finite")

    def distance_to(self, other: "Point") -> float:
        return hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True, slots=True)
class Ball:
    id: str
    color: BallColor
    x: float
    y: float
    radius: float
    confidence: float

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Ball id must not be empty")
        if not all(isfinite(value) for value in (self.x, self.y, self.radius, self.confidence)):
            raise ValueError("Ball numeric fields must be finite")
        if self.radius <= 0:
            raise ValueError("Ball radius must be positive")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Ball confidence must be in [0, 1]")

    @property
    def center(self) -> Point:
        return Point(self.x, self.y)

    def with_color(self, color: BallColor, confidence: float) -> "Ball":
        return replace(self, color=color, confidence=min(self.confidence, confidence))


@dataclass(frozen=True, slots=True)
class ColorCounts:
    red: int = 0
    yellow: int = 0
    green: int = 0
    brown: int = 0
    blue: int = 0
    pink: int = 0
    black: int = 0
    white: int = 0
    unknown: int = 0

    @classmethod
    def from_balls(cls, balls: tuple[Ball, ...]) -> "ColorCounts":
        counts = {color: 0 for color in BallColor}
        for ball in balls:
            counts[ball.color] += 1
        return cls(**{color.value.lower(): counts[color] for color in BallColor})

    def for_color(self, color: BallColor) -> int:
        return int(getattr(self, color.value.lower()))

    def as_dict(self) -> dict[str, int]:
        return {color.value: self.for_color(color) for color in BallColor}


@dataclass(frozen=True, slots=True)
class TableState:
    timestamp: datetime
    balls: tuple[Ball, ...]
    motion_state: MotionState
    confidence: float
    stable_frames: int = 1
    source_frame: int | None = None
    color_counts: ColorCounts = field(init=False)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("TableState timestamp must be timezone-aware")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("TableState confidence must be in [0, 1]")
        if self.stable_frames < 1:
            raise ValueError("stable_frames must be positive")
        object.__setattr__(self, "color_counts", ColorCounts.from_balls(self.balls))


@dataclass(frozen=True, slots=True)
class PotEvidence:
    pocket_id: str | None = None
    endpoint_distance: float | None = None
    direction_toward_pocket: bool = False
    pocket_activity: float = 0.0
    missing_frames: int = 0
    reason: str = ""


@dataclass(slots=True)
class PotEvent:
    event_id: str
    shot_id: str
    ball_color: BallColor
    count: int
    status: PotStatus
    confidence: float
    timestamp: datetime = field(default_factory=utc_now)
    evidence: PotEvidence = field(default_factory=PotEvidence)

    def __post_init__(self) -> None:
        if not self.event_id or not self.shot_id:
            raise ValueError("PotEvent ids must not be empty")
        if self.count < 1:
            raise ValueError("PotEvent count must be positive")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("PotEvent confidence must be in [0, 1]")


@dataclass(slots=True)
class ShotEvent:
    shot_id: str
    player: Player
    before_state: TableState
    started_at: datetime
    status: ShotStatus = ShotStatus.IN_PROGRESS
    after_state: TableState | None = None
    potted_balls: tuple[PotEvent, ...] = ()
    ended_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ScoreboardState:
    player_a_score: int = 0
    player_b_score: int = 0
    current_player: Player = Player.PLAYER_A
    current_break: int = 0

    def score_for(self, player: Player) -> int:
        return self.player_a_score if player is Player.PLAYER_A else self.player_b_score


@dataclass(slots=True)
class ScoreEvent:
    event_id: str
    player: Player
    ball_color: BallColor
    score_delta: int
    timestamp: datetime
    source_pot_event_id: str
    shot_id: str
    undone: bool = False


@dataclass(frozen=True, slots=True)
class FrameQuality:
    valid: bool
    reason: str = ""
    mean_brightness: float = 0.0


@dataclass(frozen=True, slots=True)
class MotionObservation:
    state: MotionState
    raw_moving: bool
    motion_ratio: float
    global_shift: float
    valid: bool = True
    reason: str = ""


def event_to_dict(event: Any) -> Mapping[str, Any]:
    """Small explicit serializer used by logs and the UI."""
    if isinstance(event, Enum):
        return {"value": event.value}
    if hasattr(event, "__dataclass_fields__"):
        result: dict[str, Any] = {}
        for name in event.__dataclass_fields__:
            value = getattr(event, name)
            if isinstance(value, Enum):
                result[name] = value.value
            elif isinstance(value, datetime):
                result[name] = value.isoformat()
            elif isinstance(value, tuple):
                result[name] = [event_to_dict(item) if hasattr(item, "__dataclass_fields__") else item for item in value]
            elif hasattr(value, "__dataclass_fields__"):
                result[name] = event_to_dict(value)
            else:
                result[name] = value
        return result
    raise TypeError(f"Unsupported event type: {type(event)!r}")

