from __future__ import annotations

import logging
from math import hypot
from typing import Mapping

import cv2
import numpy as np

from snooker_vision.domain.models import MotionObservation, MotionState


LOGGER = logging.getLogger(__name__)


class MotionDetector:
    """Frame-difference motion detector with global-shift and transient filtering."""

    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config
        self.state = MotionState.STATIC
        self.previous: np.ndarray | None = None
        self._moving_frames = 0
        self._static_frames = 0

    def reset(self) -> None:
        self.state = MotionState.STATIC
        self.previous = None
        self._moving_frames = 0
        self._static_frames = 0

    def _prepare(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        kernel = int(self.config["blur_kernel"])
        if kernel % 2 == 0:
            kernel += 1
        return cv2.GaussianBlur(gray, (kernel, kernel), 0)

    def update_signal(
        self,
        raw_moving: bool,
        motion_ratio: float = 0.0,
        global_shift: float = 0.0,
        valid: bool = True,
        reason: str = "",
    ) -> MotionObservation:
        previous_state = self.state
        if valid:
            if raw_moving:
                self._moving_frames += 1
                self._static_frames = 0
                if self._moving_frames >= int(self.config["moving_confirmation_frames"]):
                    self.state = MotionState.MOVING
            else:
                self._static_frames += 1
                self._moving_frames = 0
                if self._static_frames >= int(self.config["static_confirmation_frames"]):
                    self.state = MotionState.STATIC
        observation = MotionObservation(self.state, raw_moving, motion_ratio, global_shift, valid, reason)
        if previous_state is not self.state:
            LOGGER.info(
                "motion_state_changed",
                extra={"event": {"from": previous_state.value, "to": self.state.value, "ratio": motion_ratio}},
            )
        return observation

    def update(self, frame: np.ndarray) -> MotionObservation:
        current = self._prepare(frame)
        if self.previous is None:
            self.previous = current
            return self.update_signal(False)
        shift, response = cv2.phaseCorrelate(self.previous.astype(np.float32), current.astype(np.float32))
        shift_magnitude = hypot(float(shift[0]), float(shift[1]))
        if shift_magnitude > float(self.config["max_global_shift_px"]):
            self.previous = current
            return self.update_signal(False, global_shift=shift_magnitude, valid=False, reason="CAMERA_SHIFT")
        transform = np.float32([[1, 0, -shift[0]], [0, 1, -shift[1]]])
        aligned = cv2.warpAffine(current, transform, (current.shape[1], current.shape[0]))
        difference = cv2.absdiff(self.previous, aligned)
        _, binary = cv2.threshold(difference, int(self.config["diff_threshold"]), 255, cv2.THRESH_BINARY)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))
        changed_ratio = float(np.count_nonzero(binary)) / float(binary.size)
        self.previous = current
        if changed_ratio > float(self.config["max_changed_ratio"]):
            return self.update_signal(False, changed_ratio, shift_magnitude, valid=False, reason="LARGE_FOREGROUND_CHANGE")
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_area = 0.0
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if not float(self.config["min_component_area_px"]) <= area <= float(self.config["max_component_area_px"]):
                continue
            _, _, width, height = cv2.boundingRect(contour)
            aspect = max(width, height) / max(1.0, min(width, height))
            if aspect > float(self.config["max_component_aspect_ratio"]):
                continue
            valid_area += area
        motion_ratio = valid_area / float(binary.size)
        raw_moving = motion_ratio >= float(self.config["min_motion_ratio"])
        return self.update_signal(raw_moving, motion_ratio, shift_magnitude, response > 0.0)

