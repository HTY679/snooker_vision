from __future__ import annotations

import argparse

import cv2

from snooker_vision.calibration import CalibrationData, CalibrationStore, PocketROI
from snooker_vision.config import load_config
from snooker_vision.domain.models import Point
from snooker_vision.input import FrameSource


CORNER_LABELS = ("TL", "TR", "BR", "BL")
POCKET_LABELS = ("TOP_LEFT", "TOP_MIDDLE", "TOP_RIGHT", "BOTTOM_RIGHT", "BOTTOM_MIDDLE", "BOTTOM_LEFT")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual four-corner and six-pocket calibration")
    parser.add_argument("--source", default="0")
    parser.add_argument("--output", default="config/calibration.json")
    parser.add_argument("--config", default=None)
    parser.add_argument("--pocket-radius", type=float, default=28.0)
    args = parser.parse_args()
    config = load_config(args.config)
    calibration_config = config["calibration"]
    with FrameSource(args.source) as source:
        packet = source.read()
        if packet is None:
            raise RuntimeError("No frame available for calibration")
        frame = packet.frame
    clicks: list[tuple[int, int]] = []
    window = "Calibration: TL,TR,BR,BL then six pockets; R=reset, Enter=save"

    def on_mouse(event: int, x: int, y: int, flags: int, param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 10:
            clicks.append((x, y))

    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window, on_mouse)
    while True:
        display = frame.copy()
        for index, (x, y) in enumerate(clicks):
            label = CORNER_LABELS[index] if index < 4 else POCKET_LABELS[index - 4]
            cv2.circle(display, (x, y), 6, (0, 255, 255), -1)
            cv2.putText(display, label, (x + 8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        cv2.imshow(window, display)
        key = cv2.waitKey(20) & 0xFF
        if key in (ord("r"), ord("R")):
            clicks.clear()
        elif key in (13, 10) and len(clicks) == 10:
            break
        elif key in (27, ord("q")):
            raise RuntimeError("Calibration cancelled")
    cv2.destroyAllWindows()
    height, width = frame.shape[:2]
    output_width = int(calibration_config["output_width"])
    output_height = int(calibration_config["output_height"])
    corners = tuple(Point(float(x), float(y)) for x, y in clicks[:4])
    source_pockets = [Point(float(x), float(y)) for x, y in clicks[4:]]
    preliminary = CalibrationData.create(
        width,
        height,
        corners,
        output_width,
        output_height,
        tuple(PocketROI(label, 1.0 + i, 1.0, 1.0) for i, label in enumerate(POCKET_LABELS)),
        {**calibration_config, "max_pocket_overlap_ratio": 1.0},
    )
    from snooker_vision.calibration import PerspectiveTransformer

    transformed = PerspectiveTransformer(preliminary).transform_points(source_pockets)
    pockets = tuple(
        PocketROI(label, point.x, point.y, args.pocket_radius)
        for label, point in zip(POCKET_LABELS, transformed, strict=True)
    )
    calibration = CalibrationData.create(
        width, height, corners, output_width, output_height, pockets, calibration_config
    )
    CalibrationStore.save(calibration, args.output)
    print(f"Saved calibration to {args.output}")


if __name__ == "__main__":
    main()

