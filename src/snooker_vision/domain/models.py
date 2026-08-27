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


class RulePhase(str, Enum):
    EXPECT_RED = "EXPECT_RED"
    EXPECT_COLOR = "EXPECT_COLOR"
    CLEARANCE = "CLEARANCE"
    RESPOTTED_BLACK = "RESPOTTED_BLACK"
    FRAME_COMPLETE = "FRAME_COMPLETE"


class FrameStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"


class MatchStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"


class FoulStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    REVERTED = "REVERTED"


class RuleDecisionStatus(str, Enum):
    LEGAL = "LEGAL"
    MISS = "MISS"
    FOUL_CANDIDATE = "FOUL_CANDIDATE"
    FOUL_CONFIRMED = "FOUL_CONFIRMED"
    FOUL_CANCELLED = "FOUL_CANCELLED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class MatchEventType(str, Enum):
    MATCH_CREATED = "MATCH_CREATED"
    MATCH_STARTED = "MATCH_STARTED"
    FRAME_STARTED = "FRAME_STARTED"
    SCORE = "SCORE"
    MISS = "MISS"
    FOUL_CANDIDATE = "FOUL_CANDIDATE"
    FOUL_CONFIRMED = "FOUL_CONFIRMED"
    FOUL_CANCELLED = "FOUL_CANCELLED"
    PLAYER_SWITCHED = "PLAYER_SWITCHED"
    RESPOT_PENDING = "RESPOT_PENDING"
    RESPOT_COMPLETED = "RESPOT_COMPLETED"
    FRAME_FINISHED = "FRAME_FINISHED"
    MATCH_FINISHED = "MATCH_FINISHED"
    UNDO = "UNDO"


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


SNOOKER_COLOR_ORDER = (
    BallColor.YELLOW,
    BallColor.GREEN,
    BallColor.BROWN,
    BallColor.BLUE,
    BallColor.PINK,
    BallColor.BLACK,
)

SNOOKER_BALL_VALUES: Mapping[BallColor, int] = {
    BallColor.RED: 1,
    BallColor.YELLOW: 2,
    BallColor.GREEN: 3,
    BallColor.BROWN: 4,
    BallColor.BLUE: 5,
    BallColor.PINK: 6,
    BallColor.BLACK: 7,
}


@dataclass(frozen=True, slots=True)
class PlayerIdentity:
    player_id: str
    seat: Player
    display_name: str

    def __post_init__(self) -> None:
        if not self.player_id:
            raise ValueError("Player id must not be empty")
        if not self.display_name.strip():
            raise ValueError("Player display name must not be empty")


@dataclass(frozen=True, slots=True)
class FrameState:
    frame_number: int
    status: FrameStatus = FrameStatus.NOT_STARTED
    player_a_score: int = 0
    player_b_score: int = 0
    current_player: Player = Player.PLAYER_A
    current_break: int = 0
    remaining_reds: int = 15
    phase: RulePhase = RulePhase.EXPECT_RED
    expected_ball: BallColor | None = BallColor.RED
    colors_on_table: tuple[BallColor, ...] = SNOOKER_COLOR_ORDER
    pending_respots: tuple[BallColor, ...] = ()
    winner: Player | None = None

    def __post_init__(self) -> None:
        if self.frame_number < 1:
            raise ValueError("Frame number must be positive")
        if not 0 <= self.remaining_reds <= 15:
            raise ValueError("remaining_reds must be in [0, 15]")
        if min(self.player_a_score, self.player_b_score, self.current_break) < 0:
            raise ValueError("Frame scores and break must not be negative")
        if len(set(self.colors_on_table)) != len(self.colors_on_table):
            raise ValueError("colors_on_table must not contain duplicates")
        if any(color not in SNOOKER_COLOR_ORDER for color in self.colors_on_table):
            raise ValueError("colors_on_table may contain colors only")
        if any(color not in SNOOKER_COLOR_ORDER for color in self.pending_respots):
            raise ValueError("pending_respots may contain colors only")
        if self.phase is RulePhase.EXPECT_RED and self.remaining_reds == 0:
            raise ValueError("EXPECT_RED is invalid when no reds remain")
        if self.phase is RulePhase.CLEARANCE and self.expected_ball not in SNOOKER_COLOR_ORDER:
            raise ValueError("Clearance requires an expected color")
        if self.phase is RulePhase.RESPOTTED_BLACK and self.expected_ball is not BallColor.BLACK:
            raise ValueError("Respotted-black phase must expect black")
        if self.status is FrameStatus.FINISHED and self.phase is not RulePhase.FRAME_COMPLETE:
            raise ValueError("Finished frame must be in FRAME_COMPLETE phase")

    def score_for(self, player: Player) -> int:
        return self.player_a_score if player is Player.PLAYER_A else self.player_b_score


@dataclass(frozen=True, slots=True)
class FrameResult:
    frame_number: int
    player_a_score: int
    player_b_score: int
    winner: Player
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class MatchState:
    match_id: str
    player_a: PlayerIdentity
    player_b: PlayerIdentity
    best_of: int
    status: MatchStatus
    player_a_frames: int
    player_b_frames: int
    current_frame: FrameState
    completed_frames: tuple[FrameResult, ...] = ()
    winner: Player | None = None

    def __post_init__(self) -> None:
        if not self.match_id:
            raise ValueError("Match id must not be empty")
        if self.best_of < 1 or self.best_of > 35 or self.best_of % 2 == 0:
            raise ValueError("best_of must be an odd number between 1 and 35")
        if min(self.player_a_frames, self.player_b_frames) < 0:
            raise ValueError("Frame wins must not be negative")
        if self.player_a.seat is not Player.PLAYER_A or self.player_b.seat is not Player.PLAYER_B:
            raise ValueError("Player identities must match their seats")

    @property
    def frames_to_win(self) -> int:
        return self.best_of // 2 + 1

    def frames_for(self, player: Player) -> int:
        return self.player_a_frames if player is Player.PLAYER_A else self.player_b_frames


@dataclass(frozen=True, slots=True)
class ShotOutcome:
    shot_id: str
    player: Player
    potted_colors: tuple[BallColor, ...] = ()
    nominated_color: BallColor | None = None
    confirmed: bool = True
    confidence: float = 1.0
    timestamp: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.shot_id:
            raise ValueError("Shot id must not be empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("ShotOutcome timestamp must be timezone-aware")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("ShotOutcome confidence must be in [0, 1]")
        if BallColor.UNKNOWN in self.potted_colors:
            raise ValueError("Unknown potted colors require review before rule processing")
        if self.nominated_color is not None and self.nominated_color not in SNOOKER_COLOR_ORDER:
            raise ValueError("Nominated ball must be a color")


@dataclass(slots=True)
class FoulEvent:
    event_id: str
    shot: ShotOutcome
    reasons: tuple[str, ...]
    penalty_points: int
    status: FoulStatus = FoulStatus.CANDIDATE
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.event_id or not self.reasons:
            raise ValueError("Foul event id and reasons are required")
        if not 4 <= self.penalty_points <= 7:
            raise ValueError("Snooker foul penalty must be in [4, 7]")


@dataclass(frozen=True, slots=True)
class RuleDecision:
    shot_id: str
    status: RuleDecisionStatus
    player: Player
    points: int = 0
    penalty_points: int = 0
    foul_event_id: str | None = None
    message: str = ""


@dataclass(slots=True)
class MatchEvent:
    event_id: str
    event_type: MatchEventType
    match_id: str
    frame_number: int
    timestamp: datetime
    player: Player | None = None
    shot_id: str | None = None
    score_delta: int = 0
    details: dict[str, Any] = field(default_factory=dict)
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
