from __future__ import annotations

import json

from snooker_vision.application import P0Application
from snooker_vision.config import load_config
from snooker_vision.demo import run_recorded_event_demo


def main() -> None:
    app = P0Application(load_config())
    result = run_recorded_event_demo(app)
    expected = {"initial": 0, "after_red": 1, "after_black": 8, "after_undo": 1}
    if result != expected:
        raise RuntimeError(f"P0 demo failed: expected {expected}, got {result}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

