from __future__ import annotations

import logging
from math import pi
from typing import Mapping, Sequence

import cv2
import numpy as np

from snooker_vision.calibration import PocketROI
from snooker_vision.domain.models import Ball, BallColor, MotionState, Point


LOGGER = logging.getLogger(__name__)


class BallDetector:
    """Traditional-CV ball candidate detector for rectified, static frames."""

    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config
        self.min_radius = float(config["min_radius_px"])
        self.max_radius = float(config["max_radius_px"])

    def _object_mask(self, frame: np.ndarray, pockets: Sequence[PocketROI]) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        felt = cv2.inRange(
            hsv,
            np.asarray(self.config["felt_hsv_lower"], dtype=np.uint8),
            np.asarray(self.config["felt_hsv_upper"], dtype=np.uint8),
        )
        blur = int(self.config["mask_blur_kernel"])
        if blur % 2 == 0:
            blur += 1
        felt = cv2.medianBlur(felt, blur)
        mask = cv2.bitwise_not(felt)
        margin = int(self.config["inner_margin_px"])
        mask[:margin, :] = 0
        mask[-margin:, :] = 0
        mask[:, :margin] = 0
        mask[:, -margin:] = 0
        pocket_exclusion_factor = float(self.config.get("pocket_exclusion_factor", 1.15))
        for pocket in pockets:
            cv2.circle(
                mask,
                (round(pocket.x), round(pocket.y)),
                round(pocket.radius * pocket_exclusion_factor),
                0,
                -1,
            )
        kernel_size = int(self.config["morphology_kernel"])
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    def _contour_candidates(self, mask: np.ndarray) -> list[tuple[float, float, float, float]]:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates: list[tuple[float, float, float, float]] = []
        min_area = pi * self.min_radius**2 * 0.45
        max_area = pi * self.max_radius**2 * 1.8
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if not min_area <= area <= max_area:
                continue
            perimeter = float(cv2.arcLength(contour, True))
            if perimeter <= 0:
                continue
            circularity = 4.0 * pi * area / (perimeter * perimeter)
            x, y, width, height = cv2.boundingRect(contour)
            aspect = max(width, height) / max(1.0, min(width, height))
            (cx, cy), radius = cv2.minEnclosingCircle(contour)
            if not self.min_radius <= radius <= self.max_radius:
                continue
            if circularity < float(self.config["min_circularity"]) or aspect > float(self.config["max_aspect_ratio"]):
                continue
            fill = min(1.0, area / max(1.0, pi * radius * radius))
            confidence = max(0.0, min(1.0, 0.55 * circularity + 0.45 * fill))
            candidates.append((float(cx), float(cy), float(radius), confidence))
        return candidates

    def _hough_candidates(
        self,
        frame: np.ndarray,
        mask: np.ndarray,
        pockets: Sequence[PocketROI] = (),
    ) -> list[tuple[float, float, float, float]]:
        hough = self.config["hough"]
        if not isinstance(hough, Mapping) or not bool(hough["enabled"]):
            return []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 1.2)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=float(hough["dp"]),
            minDist=float(hough["min_distance_px"]),
            param1=float(hough["param1"]),
            param2=float(hough["param2"]),
            minRadius=round(self.min_radius),
            maxRadius=round(self.max_radius),
        )
        if circles is None:
            return []
        output: list[tuple[float, float, float, float]] = []
        min_fraction = float(self.config["min_non_felt_fraction"])
        min_surrounding_felt = float(self.config.get("min_surrounding_felt_fraction", 1.0))
        pocket_exclusion_factor = float(self.config.get("pocket_exclusion_factor", 1.15))
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        felt = cv2.inRange(
            hsv,
            np.asarray(self.config["felt_hsv_lower"], dtype=np.uint8),
            np.asarray(self.config["felt_hsv_upper"], dtype=np.uint8),
        )
        height, width = mask.shape
        yy, xx = np.ogrid[:height, :width]
        for cx, cy, radius in circles[0]:
            if any(
                Point(float(cx), float(cy)).distance_to(Point(pocket.x, pocket.y))
                <= pocket.radius * pocket_exclusion_factor
                for pocket in pockets
            ):
                continue
            disk = np.zeros(mask.shape, dtype=np.uint8)
            cv2.circle(disk, (round(cx), round(cy)), max(1, round(radius * 0.75)), 255, -1)
            pixels = mask[disk > 0]
            fraction = float(np.mean(pixels > 0)) if pixels.size else 0.0
            distance_sq = (xx - float(cx)) ** 2 + (yy - float(cy)) ** 2
            annulus = (distance_sq >= (float(radius) * 1.10) ** 2) & (
                distance_sq <= (float(radius) * 1.65) ** 2
            )
            surrounding = felt[annulus]
            surrounding_felt_fraction = (
                float(np.mean(surrounding > 0)) if surrounding.size else 0.0
            )
            # A green, blue, or white ball may fall inside the broad felt HSV range under
            # broadcast lighting.  In that case the old non-felt-only gate discarded a
            # geometrically strong Hough circle.  A felt annulus supplies independent
            # evidence that the circle is a ball sitting on the playing surface.
            if fraction >= min_fraction or surrounding_felt_fraction >= min_surrounding_felt:
                confidence = min(
                    0.95,
                    0.50 + 0.25 * fraction + 0.25 * surrounding_felt_fraction,
                )
                output.append((float(cx), float(cy), float(radius), confidence))
        return output

    def _merge(self, candidates: Sequence[tuple[float, float, float, float]]) -> list[tuple[float, float, float, float]]:
        merged: list[tuple[float, float, float, float]] = []
        factor = float(self.config["duplicate_distance_factor"])
        overlap_factor = float(self.config.get("duplicate_overlap_factor", 0.0))
        expected_radius = float(self.config.get("expected_radius_px", 0.0))
        radius_tolerance = max(1.0, float(self.config.get("radius_tolerance_px", 1.0)))

        def candidate_quality(candidate: tuple[float, float, float, float]) -> float:
            if expected_radius <= 0:
                return candidate[3]
            radius_error = abs(candidate[2] - expected_radius) / radius_tolerance
            radius_prior = max(0.25, 1.0 - 0.50 * radius_error)
            return candidate[3] * radius_prior

        for candidate in sorted(candidates, key=candidate_quality, reverse=True):
            center = Point(candidate[0], candidate[1])
            if any(
                center.distance_to(Point(existing[0], existing[1]))
                < max(
                    factor * min(candidate[2], existing[2]),
                    overlap_factor * (candidate[2] + existing[2]),
                )
                for existing in merged
            ):
                continue
            merged.append(candidate)
        return sorted(merged, key=lambda item: (item[1], item[0]))

    def detect(
        self,
        frame: np.ndarray,
        motion_state: MotionState,
        pockets: Sequence[PocketROI] = (),
    ) -> tuple[Ball, ...]:
        if motion_state is not MotionState.STATIC:
            LOGGER.debug("ball_detection_skipped_moving_frame")
            return ()
        if frame is None or frame.size == 0:
            raise ValueError("Cannot detect balls in an empty frame")
        mask = self._object_mask(frame, pockets)
        candidates = self._contour_candidates(mask)
        candidates.extend(self._hough_candidates(frame, mask, pockets))
        merged = self._merge(candidates)
        max_table_balls = max(1, int(self.config.get("max_table_balls", 22)))
        scene_confidence_scale = min(1.0, max_table_balls / max(1, len(merged)))
        if len(merged) > max_table_balls:
            LOGGER.warning(
                "implausible_ball_candidate_count",
                extra={
                    "event": {
                        "count": len(merged),
                        "max_table_balls": max_table_balls,
                        "confidence_scale": scene_confidence_scale,
                    }
                },
            )
        balls = tuple(
            Ball(
                id=f"frame-ball-{index:02d}",
                color=BallColor.UNKNOWN,
                x=cx,
                y=cy,
                radius=radius,
                confidence=confidence * scene_confidence_scale,
            )
            for index, (cx, cy, radius, confidence) in enumerate(merged, start=1)
        )
        LOGGER.info("balls_detected", extra={"event": {"count": len(balls)}})
        return balls
