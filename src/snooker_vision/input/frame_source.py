from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Mapping

import cv2
import numpy as np

from snooker_vision.domain.models import FrameQuality


LOGGER = logging.getLogger(__name__)


class FrameSourceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FramePacket:
    frame: np.ndarray
    frame_index: int
    timestamp: datetime
    source_timestamp_ms: float


def parse_source(source: str | int) -> str | int:
    if isinstance(source, int):
        return source
    stripped = source.strip()
    if stripped.isdigit() and not Path(stripped).exists():
        return int(stripped)
    return stripped


class FrameSource:
    """Explicit OpenCV VideoCapture wrapper for files and camera indexes."""

    def __init__(self, source: str | int) -> None:
        self.source = parse_source(source)
        self._capture: cv2.VideoCapture | None = None
        self._frame_index = 0

    @property
    def is_camera(self) -> bool:
        return isinstance(self.source, int)

    @property
    def opened(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    def open(self) -> "FrameSource":
        if isinstance(self.source, str) and not Path(self.source).is_file():
            raise FrameSourceError(f"Video file does not exist: {self.source}")
        capture = cv2.VideoCapture(self.source)
        if not capture.isOpened():
            capture.release()
            raise FrameSourceError(f"Cannot open frame source: {self.source}")
        self._capture = capture
        self._frame_index = 0
        LOGGER.info("frame_source_opened", extra={"event": {"source": str(self.source)}})
        return self

    def read(self) -> FramePacket | None:
        if not self.opened or self._capture is None:
            raise FrameSourceError("Frame source is not open")
        ok, frame = self._capture.read()
        if not ok or frame is None:
            return None
        packet = FramePacket(
            frame=frame,
            frame_index=self._frame_index,
            timestamp=datetime.now(timezone.utc),
            source_timestamp_ms=float(self._capture.get(cv2.CAP_PROP_POS_MSEC)),
        )
        self._frame_index += 1
        return packet

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            LOGGER.info("frame_source_released", extra={"event": {"source": str(self.source)}})

    def __enter__(self) -> "FrameSource":
        return self.open()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


class FrameQualityGate:
    def __init__(self, config: Mapping[str, object]) -> None:
        self.black_frame_mean_max = float(config["black_frame_mean_max"])
        self.expected_resolution: tuple[int, int] | None = None

    def set_expected_resolution(self, width: int, height: int) -> None:
        self.expected_resolution = (width, height)

    def evaluate(self, frame: np.ndarray | None) -> FrameQuality:
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            return FrameQuality(False, "EMPTY_FRAME")
        if frame.ndim not in (2, 3):
            return FrameQuality(False, "INVALID_FRAME_SHAPE")
        height, width = frame.shape[:2]
        if self.expected_resolution and (width, height) != self.expected_resolution:
            return FrameQuality(False, "RESOLUTION_CHANGED", float(np.mean(frame)))
        mean = float(np.mean(frame))
        if mean <= self.black_frame_mean_max:
            return FrameQuality(False, "BLACK_FRAME", mean)
        return FrameQuality(True, mean_brightness=mean)

