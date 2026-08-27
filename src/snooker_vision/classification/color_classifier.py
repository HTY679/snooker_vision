from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Mapping, Sequence

import cv2
import numpy as np

from snooker_vision.domain.models import Ball, BallColor


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ColorClassification:
    color: BallColor
    confidence: float
    distance: float
    margin: float


class BallColorClassifier:
    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config
        prototypes = config["prototypes_bgr"]
        if not isinstance(prototypes, Mapping):
            raise ValueError("classification.prototypes_bgr must be a mapping")
        self.prototype_lab: dict[BallColor, np.ndarray] = {}
        for name, bgr in prototypes.items():
            color = BallColor(str(name))
            pixel = np.asarray([[list(bgr)]], dtype=np.uint8)
            self.prototype_lab[color] = cv2.cvtColor(pixel, cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)

    def _sample_lab(self, frame: np.ndarray, ball: Ball) -> np.ndarray | None:
        height, width = frame.shape[:2]
        radius = max(1, round(ball.radius * float(self.config["inner_radius_ratio"])))
        cx, cy = round(ball.x), round(ball.y)
        x1, x2 = max(0, cx - radius), min(width, cx + radius + 1)
        y1, y2 = max(0, cy - radius), min(height, cy + radius + 1)
        if x1 >= x2 or y1 >= y2:
            return None
        crop = frame[y1:y2, x1:x2]
        yy, xx = np.ogrid[y1 - cy : y2 - cy, x1 - cx : x2 - cx]
        circle = xx * xx + yy * yy <= radius * radius
        pixels = crop[circle]
        if pixels.size == 0:
            return None
        lab_pixels = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
        trim = float(self.config["trim_fraction"])
        if 0 < trim < 0.5 and len(lab_pixels) >= 10:
            order = np.argsort(lab_pixels[:, 0])
            start = int(len(order) * trim)
            end = max(start + 1, int(len(order) * (1.0 - trim)))
            lab_pixels = lab_pixels[order[start:end]]
        return np.median(lab_pixels, axis=0)

    def classify(self, frame: np.ndarray, ball: Ball) -> ColorClassification:
        sample = self._sample_lab(frame, ball)
        if sample is None:
            return ColorClassification(BallColor.UNKNOWN, 0.0, float("inf"), 0.0)
        sample_u8 = np.clip(sample, 0, 255).astype(np.uint8).reshape(1, 1, 3)
        sample_bgr = cv2.cvtColor(sample_u8, cv2.COLOR_LAB2BGR)
        sample_hsv = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2HSV)[0, 0]
        saturation, value = int(sample_hsv[1]), int(sample_hsv[2])
        if saturation <= int(self.config["achromatic_saturation_max"]):
            if value <= int(self.config["black_value_max"]):
                return ColorClassification(BallColor.BLACK, min(1.0, (int(self.config["black_value_max"]) - value + 20) / 40.0), 0.0, 255.0)
            if value >= int(self.config["white_value_min"]):
                return ColorClassification(BallColor.WHITE, min(1.0, (value - int(self.config["white_value_min"]) + 20) / 40.0), 0.0, 255.0)
            return ColorClassification(BallColor.UNKNOWN, 0.0, float("inf"), 0.0)
        ranked = sorted(
            ((float(np.linalg.norm(sample - prototype)), color) for color, prototype in self.prototype_lab.items()),
            key=lambda item: item[0],
        )
        distance, color = ranked[0]
        second_distance = ranked[1][0] if len(ranked) > 1 else distance
        margin = second_distance - distance
        max_distance = float(self.config["max_lab_distance"])
        distance_confidence = max(0.0, 1.0 - distance / max_distance)
        margin_confidence = max(0.0, min(1.0, margin / max(1.0, float(self.config["min_distance_margin"]) * 2.0)))
        confidence = min(1.0, 0.75 * distance_confidence + 0.25 * margin_confidence)
        if (
            distance > max_distance
            or margin < float(self.config["min_distance_margin"])
            or confidence < float(self.config["min_confidence"])
        ):
            color = BallColor.UNKNOWN
        return ColorClassification(color, confidence, distance, margin)

    def classify_balls(self, frame: np.ndarray, balls: Sequence[Ball]) -> tuple[Ball, ...]:
        classified: list[Ball] = []
        for ball in balls:
            result = self.classify(frame, ball)
            classified.append(ball.with_color(result.color, result.confidence))
        LOGGER.info(
            "balls_classified",
            extra={"event": {"colors": [ball.color.value for ball in classified]}},
        )
        return tuple(classified)
