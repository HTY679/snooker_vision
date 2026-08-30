from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
from statistics import mean, median

import cv2
from ultralytics import YOLO


VIDEO_EXTENSIONS = {".avi", ".mkv", ".mov", ".mp4"}
BALL_LIMITS = {
    "black-ball": 1,
    "blue-ball": 1,
    "brown-ball": 1,
    "green-ball": 1,
    "pink-ball": 1,
    "red-ball": 15,
    "white-ball": 1,
    "yellow-ball": 1,
}


def sample_indices(frame_count: int, samples: int) -> tuple[int, ...]:
    """Return approximately uniform, unique frame indices including both ends."""
    if frame_count <= 0 or samples <= 0:
        return ()
    if samples == 1:
        return (frame_count // 2,)
    if samples >= frame_count:
        return tuple(range(frame_count))
    return tuple(
        sorted(
            {
                round(index * (frame_count - 1) / (samples - 1))
                for index in range(samples)
            }
        )
    )


def rule_diagnostics(
    class_ids: list[int],
    confidences: list[float],
    names: dict[int, str],
    threshold: float,
) -> tuple[Counter[str], int]:
    counts = Counter(
        names[class_id]
        for class_id, confidence in zip(class_ids, confidences, strict=True)
        if confidence >= threshold
    )
    impossible_extras = sum(
        max(0, counts[name] - limit) for name, limit in BALL_LIMITS.items()
    )
    return counts, impossible_extras


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    groups: dict[tuple[str, float], list[dict[str, object]]] = defaultdict(list)
    overall: dict[float, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        video = str(row["video"])
        threshold = float(row["threshold"])
        groups[(video, threshold)].append(row)
        overall[threshold].append(row)

    def metrics(items: list[dict[str, object]]) -> dict[str, object]:
        detections = [int(item["detections"]) for item in items]
        extras = [int(item["impossible_extras"]) for item in items]
        violations = sum(value > 0 for value in extras)
        return {
            "frames": len(items),
            "violation_frames": violations,
            "violation_rate": round(violations / max(1, len(items)), 4),
            "mean_detections": round(mean(detections), 3),
            "median_detections": round(median(detections), 3),
            "mean_impossible_extras": round(mean(extras), 3),
            "max_impossible_extras": max(extras, default=0),
        }

    return {
        "rule_limits": BALL_LIMITS,
        "limitation": (
            "Rule violations measure impossible false positives only. "
            "They do not measure missed balls or color accuracy."
        ),
        "overall": {
            f"{threshold:.2f}": metrics(items)
            for threshold, items in sorted(overall.items())
        },
        "videos": {
            video: {
                f"{threshold:.2f}": metrics(items)
                for (group_video, threshold), items in sorted(groups.items())
                if group_video == video
            }
            for video in sorted({video for video, _ in groups})
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample videos and measure impossible snooker-ball detections"
    )
    parser.add_argument("--model", required=True, help="YOLO model path")
    parser.add_argument("--input-dir", default="data/raw", help="Directory of videos")
    parser.add_argument(
        "--output-dir",
        default="data/processed/yolo_eval/video_domain_eval",
        help="CSV and JSON output directory",
    )
    parser.add_argument("--samples-per-video", type=int, default=60)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--iou", type=float, default=0.7)
    parser.add_argument(
        "--agnostic-nms",
        action="store_true",
        help="Suppress overlapping boxes even when their predicted classes differ",
    )
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=(0.25, 0.35, 0.45, 0.55),
    )
    args = parser.parse_args()

    thresholds = tuple(sorted(set(args.thresholds)))
    if not thresholds or thresholds[0] <= 0 or thresholds[-1] >= 1:
        raise ValueError("Thresholds must be between 0 and 1")

    input_dir = Path(args.input_dir)
    videos = sorted(
        path for path in input_dir.iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS
    )
    if not videos:
        raise FileNotFoundError(f"No videos found in {input_dir.resolve()}")

    model = YOLO(args.model)
    model_names = {int(key): str(value) for key, value in model.names.items()}
    if set(model_names.values()) != set(BALL_LIMITS):
        raise ValueError(f"Unexpected model classes: {model_names}")

    rows: list[dict[str, object]] = []
    for video in videos:
        capture = cv2.VideoCapture(str(video))
        frame_count = round(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        indices = sample_indices(frame_count, args.samples_per_video)
        pending_frames: list[object] = []
        pending_indices: list[int] = []

        def process_pending() -> None:
            if not pending_frames:
                return
            results = model.predict(
                pending_frames,
                imgsz=args.imgsz,
                conf=thresholds[0],
                iou=args.iou,
                device=args.device,
                agnostic_nms=args.agnostic_nms,
                verbose=False,
            )
            for frame_index, result in zip(pending_indices, results, strict=True):
                class_ids = [int(value) for value in result.boxes.cls.cpu().tolist()]
                confidences = [float(value) for value in result.boxes.conf.cpu().tolist()]
                for threshold in thresholds:
                    counts, impossible_extras = rule_diagnostics(
                        class_ids, confidences, model_names, threshold
                    )
                    rows.append(
                        {
                            "video": video.name,
                            "frame": frame_index,
                            "threshold": threshold,
                            "detections": sum(counts.values()),
                            "impossible_extras": impossible_extras,
                            "counts": json.dumps(
                                dict(sorted(counts.items())), ensure_ascii=False
                            ),
                        }
                    )
            pending_frames.clear()
            pending_indices.clear()

        try:
            for frame_index in indices:
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok:
                    continue
                pending_frames.append(frame)
                pending_indices.append(frame_index)
                if len(pending_frames) >= args.batch:
                    process_pending()
            process_pending()
        finally:
            capture.release()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "frame_diagnostics.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "video",
                "frame",
                "threshold",
                "detections",
                "impossible_extras",
                "counts",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)

    summary_path = output_dir / "summary.json"
    summary = summarize(rows)
    summary["model"] = str(Path(args.model).resolve())
    summary["videos_evaluated"] = len(videos)
    summary["samples_per_video_requested"] = args.samples_per_video
    summary["agnostic_nms"] = args.agnostic_nms
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"CSV: {csv_path.resolve()}")
    print(f"Summary: {summary_path.resolve()}")


if __name__ == "__main__":
    main()
