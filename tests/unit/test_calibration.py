from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from snooker_vision.calibration import (
    CalibrationData,
    CalibrationError,
    CalibrationStore,
    PerspectiveTransformer,
    PocketROI,
    TableRoiDetector,
    standard_pocket_rois,
)
from snooker_vision.domain.models import Point


def test_perspective_transform_rectifies_corners(calibration: CalibrationData) -> None:
    transformer = PerspectiveTransformer(calibration)
    transformed = transformer.transform_points(calibration.corners)
    assert transformed[0].distance_to(Point(0, 0)) < 1
    assert transformed[2].distance_to(Point(1199, 599)) < 1


def test_calibration_round_trip(calibration: CalibrationData, config: dict[str, object], tmp_path) -> None:
    path = tmp_path / "calibration.json"
    CalibrationStore.save(calibration, path)
    loaded = CalibrationStore.load(path, config["calibration"])
    assert loaded == calibration


def test_invalid_corner_order_is_rejected(config: dict[str, object]) -> None:
    with pytest.raises(CalibrationError):
        CalibrationData.create(
            640,
            360,
            (Point(20, 20), Point(620, 340), Point(620, 20), Point(20, 340)),
            1200,
            600,
            standard_pocket_rois(1200, 600),
            config["calibration"],
        )


def test_duplicate_corner_is_rejected(config: dict[str, object]) -> None:
    with pytest.raises(CalibrationError):
        CalibrationData.create(
            640,
            360,
            (Point(20, 20), Point(20, 20), Point(620, 340), Point(20, 340)),
            1200,
            600,
            standard_pocket_rois(1200, 600),
            config["calibration"],
        )


def test_exactly_six_pockets_are_required(config: dict[str, object]) -> None:
    with pytest.raises(CalibrationError):
        CalibrationData.create(
            640,
            360,
            (Point(20, 20), Point(620, 20), Point(620, 340), Point(20, 340)),
            1200,
            600,
            standard_pocket_rois(1200, 600)[:-1],
            config["calibration"],
        )


def test_corrupt_calibration_load_fails(config: dict[str, object], tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(CalibrationError):
        CalibrationStore.load(path, config["calibration"])


def test_auto_roi_detects_synthetic_green_table(config: dict[str, object]) -> None:
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    cv2.rectangle(frame, (60, 40), (580, 320), (40, 120, 40), -1)
    detector = TableRoiDetector(config["calibration"]["auto_roi"])
    corners, confidence = detector.detect(frame)
    assert corners is not None
    assert confidence > 0.25

