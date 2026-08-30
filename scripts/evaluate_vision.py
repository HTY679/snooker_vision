from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import cv2

from snooker_vision.calibration import CalibrationStore, PerspectiveTransformer
from snooker_vision.classification import BallColorClassifier
from snooker_vision.config import load_config
from snooker_vision.detection import BallDetector
from snooker_vision.domain.models import BallColor, MotionState


PALETTE = {
    BallColor.RED: (0, 0, 255),
    BallColor.YELLOW: (0, 255, 255),
    BallColor.GREEN: (0, 180, 0),
    BallColor.BROWN: (42, 42, 165),
    BallColor.BLUE: (255, 80, 0),
    BallColor.PINK: (203, 192, 255),
    BallColor.BLACK: (0, 0, 0),
    BallColor.WHITE: (255, 255, 255),
    BallColor.UNKNOWN: (0, 128, 255),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate and render ball detection/classification for one video frame"
    )
    parser.add_argument("--source", required=True, help="Input video path")
    parser.add_argument("--frame", type=int, default=0, help="Zero-based frame index")
    parser.add_argument("--output", required=True, help="Annotated PNG/JPG output path")
    parser.add_argument("--calibration", default="config/calibration.json")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    calibration = CalibrationStore.load(args.calibration, config["calibration"])
    transformer = PerspectiveTransformer(calibration)
    detector = BallDetector(config["detection"])
    classifier = BallColorClassifier(config["classification"])

    capture = cv2.VideoCapture(args.source)
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, args.frame)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise RuntimeError(f"Cannot read frame {args.frame} from {args.source}")

    rectified = transformer.warp(frame)
    balls = detector.detect(rectified, MotionState.STATIC, calibration.pockets)
    balls = classifier.classify_balls(rectified, balls)
    annotated = rectified.copy()
    for index, ball in enumerate(balls, start=1):
        color = PALETTE[ball.color]
        center = (round(ball.x), round(ball.y))
        cv2.circle(annotated, center, round(ball.radius), color, 2)
        label = f"{index}:{ball.color.value[:2]} {ball.confidence:.2f}"
        origin = (center[0] + 5, center[1] - 5)
        cv2.putText(
            annotated,
            label,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            label,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            color,
            1,
            cv2.LINE_AA,
        )

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), annotated):
        raise RuntimeError(f"Cannot write annotated frame to {destination}")

    counts = Counter(ball.color.value for ball in balls)
    unique_colors = ("YELLOW", "GREEN", "BROWN", "BLUE", "PINK", "BLACK", "WHITE")
    impossible_extras = sum(max(0, counts[color] - 1) for color in unique_colors)
    impossible_extras += max(0, counts["RED"] - 15)
    print(
        json.dumps(
            {
                "source": args.source,
                "frame": args.frame,
                "detected": len(balls),
                "colors": dict(sorted(counts.items())),
                "impossible_extras": impossible_extras,
                "output": str(destination.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
