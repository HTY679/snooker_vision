from __future__ import annotations

import argparse

import cv2

from snooker_vision.application import P0Application
from snooker_vision.config import load_config
from snooker_vision.input import FrameSource
from snooker_vision.logging_config import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Snooker Vision P0 pipeline")
    parser.add_argument("--source", default="0", help="Video path or camera index")
    parser.add_argument("--calibration", default="config/calibration.json")
    parser.add_argument("--config", default=None)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-frames", type=int, default=0)
    args = parser.parse_args()

    config = load_config(args.config)
    configure_logging(str(config["app"]["log_level"]), str(config["app"]["log_file"]))
    app = P0Application(config)
    app.load_calibration(args.calibration)
    processed = 0
    with FrameSource(args.source) as source:
        while True:
            packet = source.read()
            if packet is None:
                break
            view = app.process_frame(packet.frame, packet.timestamp, packet.frame_index)
            processed += 1
            if not args.headless:
                display = packet.frame.copy()
                cv2.putText(display, f"{view.system_status.value} / {view.motion}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.putText(display, f"A {view.scoreboard.player_a_score} - {view.scoreboard.player_b_score} B", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                cv2.imshow("Snooker Vision P0", display)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
            if args.max_frames and processed >= args.max_frames:
                break
    cv2.destroyAllWindows()
    print(f"Processed {processed} frames; A={app.score_engine.state.player_a_score}, B={app.score_engine.state.player_b_score}")


if __name__ == "__main__":
    main()

