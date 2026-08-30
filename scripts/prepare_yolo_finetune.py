from __future__ import annotations

import argparse
from collections import Counter
import csv
from pathlib import Path

import cv2
from ultralytics import YOLO


SPLIT_PLAN = {
    "train": {
        "ball_bounce_out_001.mp4": 25,
        "black_pot_001.mp4": 25,
        "cue_occlusion_001.mp4": 35,
        "fast_shot_001.mp4": 35,
        "hand_occlusion_001.mp4": 40,
        "static_table_001.mp4": 15,
    },
    "valid": {
        "red_pot_corner_001.mp4": 30,
    },
    "test": {
        "red_pot_middle_001.mp4": 30,
        "slow_roll_001.mp4": 40,
    },
}


def sample_indices(frame_count: int, samples: int) -> tuple[int, ...]:
    """Uniformly sample the central 90% of a video to avoid title/end cards."""
    if frame_count <= 0 or samples <= 0:
        return ()
    if samples == 1:
        return (frame_count // 2,)
    start = round((frame_count - 1) * 0.05)
    end = round((frame_count - 1) * 0.95)
    if samples >= end - start + 1:
        return tuple(range(start, end + 1))
    return tuple(
        sorted(
            {
                round(start + index * (end - start) / (samples - 1))
                for index in range(samples)
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract a video-disjoint fine-tuning set and create YOLO prelabels"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-dir", default="data/raw")
    parser.add_argument(
        "--output-dir", default="data/finetune/snooker_broadcast_v1"
    )
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="0")
    parser.add_argument(
        "--conf",
        type=float,
        default=0.15,
        help="Low prelabel threshold favors recall; all labels require review",
    )
    args = parser.parse_args()

    model = YOLO(args.model)
    names = {int(key): str(value) for key, value in model.names.items()}
    source_root = Path(args.input_dir)
    output_root = Path(args.output_dir)
    manifest_rows: list[dict[str, object]] = []

    for split, video_plan in SPLIT_PLAN.items():
        image_dir = output_root / split / "images"
        label_dir = output_root / split / "labels"
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)

        for video_name, requested_samples in video_plan.items():
            video_path = source_root / video_name
            if not video_path.exists():
                raise FileNotFoundError(video_path)
            capture = cv2.VideoCapture(str(video_path))
            frame_count = round(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            indices = sample_indices(frame_count, requested_samples)
            pending_frames: list[object] = []
            pending_indices: list[int] = []

            def process_pending() -> None:
                if not pending_frames:
                    return
                results = model.predict(
                    pending_frames,
                    imgsz=args.imgsz,
                    conf=args.conf,
                    iou=0.7,
                    device=args.device,
                    agnostic_nms=True,
                    verbose=False,
                )
                for frame_index, frame, result in zip(
                    pending_indices, pending_frames, results, strict=True
                ):
                    stem = f"{video_path.stem}_frame{frame_index:06d}"
                    image_path = image_dir / f"{stem}.jpg"
                    label_path = label_dir / f"{stem}.txt"
                    if not cv2.imwrite(
                        str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]
                    ):
                        raise RuntimeError(f"Cannot write {image_path}")

                    class_ids = [int(value) for value in result.boxes.cls.cpu().tolist()]
                    confidences = [
                        float(value) for value in result.boxes.conf.cpu().tolist()
                    ]
                    boxes = result.boxes.xywhn.cpu().tolist()
                    lines = [
                        f"{class_id} "
                        + " ".join(f"{coordinate:.8f}" for coordinate in box)
                        for class_id, box in zip(class_ids, boxes, strict=True)
                    ]
                    label_path.write_text(
                        "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
                    )

                    counts = Counter(names[class_id] for class_id in class_ids)
                    manifest_rows.append(
                        {
                            "status": "NEEDS_HUMAN_REVIEW",
                            "split": split,
                            "video": video_name,
                            "frame": frame_index,
                            "image": str(image_path),
                            "label": str(label_path),
                            "prelabel_count": len(class_ids),
                            "minimum_confidence": (
                                round(min(confidences), 4) if confidences else ""
                            ),
                            "counts": dict(sorted(counts.items())),
                        }
                    )
                pending_frames.clear()
                pending_indices.clear()

            try:
                for frame_index in indices:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                    ok, frame = capture.read()
                    if not ok:
                        raise RuntimeError(
                            f"Cannot read frame {frame_index} from {video_path}"
                        )
                    pending_frames.append(frame)
                    pending_indices.append(frame_index)
                    if len(pending_frames) >= args.batch:
                        process_pending()
                process_pending()
            finally:
                capture.release()

    manifest_path = output_root / "review_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest_rows[0].keys())
        writer.writeheader()
        writer.writerows(manifest_rows)

    yaml_lines = [
        "train: train/images",
        "val: valid/images",
        "test: test/images",
        "",
        f"nc: {len(names)}",
        f"names: {[names[index] for index in sorted(names)]}",
        "",
    ]
    (output_root / "data.yaml").write_text("\n".join(yaml_lines), encoding="utf-8")
    (output_root / "REVIEW_REQUIRED.txt").write_text(
        "Every label in this directory was generated automatically.\n"
        "Do not train on this dataset until every image has been reviewed and "
        "the manifest status has been changed to REVIEWED.\n",
        encoding="utf-8",
    )
    print(f"Prepared {len(manifest_rows)} frames in {output_root.resolve()}")
    for split in SPLIT_PLAN:
        count = sum(row["split"] == split for row in manifest_rows)
        print(f"{split}: {count}")
    print(f"Review manifest: {manifest_path.resolve()}")


if __name__ == "__main__":
    main()
