from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from math import acos, pi, sqrt
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Mapping, Sequence

import cv2
import numpy as np

from snooker_vision.domain.models import Point


LOGGER = logging.getLogger(__name__)
POCKET_IDS = ("TOP_LEFT", "TOP_MIDDLE", "TOP_RIGHT", "BOTTOM_RIGHT", "BOTTOM_MIDDLE", "BOTTOM_LEFT")


class CalibrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PocketROI:
    pocket_id: str
    x: float
    y: float
    radius: float

    def __post_init__(self) -> None:
        if self.pocket_id not in POCKET_IDS:
            raise ValueError(f"Unknown pocket id: {self.pocket_id}")
        if self.radius <= 0:
            raise ValueError("Pocket radius must be positive")

    @property
    def center(self) -> Point:
        return Point(self.x, self.y)

    def contains(self, point: Point, factor: float = 1.0) -> bool:
        return self.center.distance_to(point) <= self.radius * factor


def _polygon_area(points: Sequence[Point]) -> float:
    return abs(sum(p.x * points[(i + 1) % len(points)].y - points[(i + 1) % len(points)].x * p.y for i, p in enumerate(points))) / 2.0


def _validate_corner_order(corners: Sequence[Point]) -> None:
    crosses: list[float] = []
    for index in range(4):
        a, b, c = corners[index], corners[(index + 1) % 4], corners[(index + 2) % 4]
        crosses.append((b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x))
    if any(abs(value) < 1e-6 for value in crosses) or not (all(value > 0 for value in crosses) or all(value < 0 for value in crosses)):
        raise CalibrationError("Corners must form a non-self-intersecting convex quadrilateral in TL,TR,BR,BL order")
    tl, tr, br, bl = corners
    if not (tl.x < tr.x and bl.x < br.x and tl.y < bl.y and tr.y < br.y):
        raise CalibrationError("Corner order must be TL, TR, BR, BL")


def validate_corners(
    corners: Sequence[Point],
    frame_width: int,
    frame_height: int,
    min_distance: float,
    min_area_ratio: float,
) -> tuple[Point, Point, Point, Point]:
    if len(corners) != 4:
        raise CalibrationError("Exactly four table corners are required")
    normalized = tuple(corners)
    for point in normalized:
        if not (0 <= point.x < frame_width and 0 <= point.y < frame_height):
            raise CalibrationError("Calibration corner lies outside the frame")
    for index, point in enumerate(normalized):
        for other in normalized[index + 1 :]:
            if point.distance_to(other) < min_distance:
                raise CalibrationError("Calibration corners are too close or duplicated")
    _validate_corner_order(normalized)
    if _polygon_area(normalized) / float(frame_width * frame_height) < min_area_ratio:
        raise CalibrationError("Calibrated table area is too small")
    return normalized  # type: ignore[return-value]


def _circle_overlap_ratio(first: PocketROI, second: PocketROI) -> float:
    r1, r2 = first.radius, second.radius
    d = first.center.distance_to(second.center)
    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        return min(r1, r2) ** 2 / max(r1, r2) ** 2
    a1 = r1 * r1 * acos((d * d + r1 * r1 - r2 * r2) / (2 * d * r1))
    a2 = r2 * r2 * acos((d * d + r2 * r2 - r1 * r1) / (2 * d * r2))
    triangle = 0.5 * sqrt(max(0.0, (-d + r1 + r2) * (d + r1 - r2) * (d - r1 + r2) * (d + r1 + r2)))
    intersection = a1 + a2 - triangle
    return intersection / (pi * min(r1, r2) ** 2)


def validate_pockets(
    pockets: Sequence[PocketROI], output_width: int, output_height: int, max_overlap_ratio: float
) -> tuple[PocketROI, ...]:
    if len(pockets) != 6:
        raise CalibrationError("Exactly six pocket ROIs are required")
    if {pocket.pocket_id for pocket in pockets} != set(POCKET_IDS):
        raise CalibrationError("Pocket IDs must contain each of the six standard positions exactly once")
    for pocket in pockets:
        if not (0 <= pocket.x < output_width and 0 <= pocket.y < output_height):
            raise CalibrationError(f"Pocket {pocket.pocket_id} lies outside the rectified table")
    for index, pocket in enumerate(pockets):
        for other in pockets[index + 1 :]:
            if _circle_overlap_ratio(pocket, other) > max_overlap_ratio:
                raise CalibrationError(f"Pocket ROIs overlap excessively: {pocket.pocket_id}, {other.pocket_id}")
    return tuple(pockets)


@dataclass(frozen=True, slots=True)
class CalibrationData:
    frame_width: int
    frame_height: int
    corners: tuple[Point, Point, Point, Point]
    output_width: int
    output_height: int
    pockets: tuple[PocketROI, ...]

    @classmethod
    def create(
        cls,
        frame_width: int,
        frame_height: int,
        corners: Sequence[Point],
        output_width: int,
        output_height: int,
        pockets: Sequence[PocketROI],
        config: Mapping[str, object],
    ) -> "CalibrationData":
        valid_corners = validate_corners(
            corners,
            frame_width,
            frame_height,
            float(config["min_corner_distance_px"]),
            float(config["min_polygon_area_ratio"]),
        )
        valid_pockets = validate_pockets(
            pockets, output_width, output_height, float(config["max_pocket_overlap_ratio"])
        )
        return cls(frame_width, frame_height, valid_corners, output_width, output_height, valid_pockets)

    def compatible_with(self, frame: np.ndarray) -> bool:
        height, width = frame.shape[:2]
        return width == self.frame_width and height == self.frame_height


def standard_pocket_rois(width: int, height: int, radius: float = 28.0) -> tuple[PocketROI, ...]:
    return tuple(
        PocketROI(pocket_id, x, y, radius)
        for pocket_id, x, y in (
            ("TOP_LEFT", 0.0, 0.0),
            ("TOP_MIDDLE", width / 2.0, 0.0),
            ("TOP_RIGHT", width - 1.0, 0.0),
            ("BOTTOM_RIGHT", width - 1.0, height - 1.0),
            ("BOTTOM_MIDDLE", width / 2.0, height - 1.0),
            ("BOTTOM_LEFT", 0.0, height - 1.0),
        )
    )


class CalibrationStore:
    @staticmethod
    def save(calibration: CalibrationData, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "frame_width": calibration.frame_width,
            "frame_height": calibration.frame_height,
            "output_width": calibration.output_width,
            "output_height": calibration.output_height,
            "corners": [{"x": point.x, "y": point.y} for point in calibration.corners],
            "pockets": [
                {"pocket_id": pocket.pocket_id, "x": pocket.x, "y": pocket.y, "radius": pocket.radius}
                for pocket in calibration.pockets
            ],
        }
        try:
            with NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent, delete=False, suffix=".tmp") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                temporary = Path(handle.name)
            temporary.replace(destination)
        except OSError as exc:
            raise CalibrationError(f"Cannot save calibration to {destination}: {exc}") from exc
        LOGGER.info("calibration_saved", extra={"event": {"path": str(destination)}})

    @staticmethod
    def load(path: str | Path, config: Mapping[str, object]) -> CalibrationData:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
            if payload.get("schema_version") != 1:
                raise CalibrationError("Unsupported calibration schema version")
            corners = tuple(Point(float(item["x"]), float(item["y"])) for item in payload["corners"])
            pockets = tuple(
                PocketROI(str(item["pocket_id"]), float(item["x"]), float(item["y"]), float(item["radius"]))
                for item in payload["pockets"]
            )
            return CalibrationData.create(
                int(payload["frame_width"]),
                int(payload["frame_height"]),
                corners,
                int(payload["output_width"]),
                int(payload["output_height"]),
                pockets,
                config,
            )
        except FileNotFoundError as exc:
            raise CalibrationError(f"Calibration file not found: {source}") from exc
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CalibrationError(f"Cannot load calibration {source}: {exc}") from exc


class PerspectiveTransformer:
    def __init__(self, calibration: CalibrationData) -> None:
        self.calibration = calibration
        source = np.float32([[point.x, point.y] for point in calibration.corners])
        destination = np.float32(
            [
                [0, 0],
                [calibration.output_width - 1, 0],
                [calibration.output_width - 1, calibration.output_height - 1],
                [0, calibration.output_height - 1],
            ]
        )
        self.matrix = cv2.getPerspectiveTransform(source, destination)
        if not np.isfinite(self.matrix).all() or abs(float(np.linalg.det(self.matrix))) < 1e-12:
            raise CalibrationError("Perspective transform matrix is invalid")

    def warp(self, frame: np.ndarray) -> np.ndarray:
        if not self.calibration.compatible_with(frame):
            raise CalibrationError("Frame resolution does not match calibration")
        return cv2.warpPerspective(
            frame, self.matrix, (self.calibration.output_width, self.calibration.output_height)
        )

    def transform_points(self, points: Iterable[Point]) -> tuple[Point, ...]:
        array = np.float32([[[point.x, point.y] for point in points]])
        transformed = cv2.perspectiveTransform(array, self.matrix)[0]
        return tuple(Point(float(x), float(y)) for x, y in transformed)


class TableRoiDetector:
    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config

    def detect(self, frame: np.ndarray) -> tuple[tuple[Point, Point, Point, Point] | None, float]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.asarray(self.config["hsv_lower"], dtype=np.uint8)
        upper = np.asarray(self.config["hsv_upper"], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        kernel_size = int(self.config["morphology_kernel"])
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, 0.0
        contour = max(contours, key=cv2.contourArea)
        area_ratio = cv2.contourArea(contour) / float(frame.shape[0] * frame.shape[1])
        epsilon = float(self.config["approx_epsilon_ratio"]) * cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, epsilon, True)
        if len(polygon) != 4:
            box = cv2.boxPoints(cv2.minAreaRect(contour))
            polygon = box.reshape(4, 1, 2).astype(np.float32)
        points = polygon.reshape(4, 2).astype(np.float32)
        sums = points.sum(axis=1)
        differences = np.diff(points, axis=1).reshape(-1)
        ordered = (
            Point(*map(float, points[np.argmin(sums)])),
            Point(*map(float, points[np.argmin(differences)])),
            Point(*map(float, points[np.argmax(sums)])),
            Point(*map(float, points[np.argmax(differences)])),
        )
        confidence = max(0.0, min(1.0, area_ratio))
        return ordered, confidence


class CalibrationMonitor:
    def __init__(self, reference_rectified_frame: np.ndarray, config: Mapping[str, object]) -> None:
        self.reference = self._prepare(reference_rectified_frame)
        self.max_shift = float(config["max_shift_px"])
        self.min_response = float(config["min_phase_response"])
        self.max_mean_abs_diff = float(config["max_mean_abs_diff"])

    @staticmethod
    def _prepare(frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        return cv2.resize(gray, (320, 160)).astype(np.float32)

    def validate(self, rectified_frame: np.ndarray) -> tuple[bool, str]:
        current = self._prepare(rectified_frame)
        shift, response = cv2.phaseCorrelate(self.reference, current)
        scale_x = rectified_frame.shape[1] / 320.0
        scale_y = rectified_frame.shape[0] / 160.0
        shift_magnitude = sqrt((shift[0] * scale_x) ** 2 + (shift[1] * scale_y) ** 2)
        mean_abs_diff = float(np.mean(cv2.absdiff(self.reference, current)))
        if shift_magnitude > self.max_shift:
            return False, "CAMERA_MOVED"
        if response < self.min_response and mean_abs_diff > self.max_mean_abs_diff:
            return False, "CALIBRATION_REFERENCE_MISMATCH"
        return True, "OK"

