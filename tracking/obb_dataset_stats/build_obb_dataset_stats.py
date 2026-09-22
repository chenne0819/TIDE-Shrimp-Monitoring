from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm
from ultralytics import YOLO


DEFAULT_VIDEOS = [
    "video/公蝦仰拍-1.mp4",
    "video/公蝦仰拍-2.mp4",
    "video/公蝦仰拍-3.mp4",
    "video/母蝦仰拍-1.mp4",
    "video/母蝦仰拍-2.mp4",
    "video/母蝦仰拍-3.mp4",
]
DEFAULT_OBB_MODEL = "model/yolo/best-obb-yolo11m-head_tail.pt"
DEFAULT_OUTPUT_ROOT = "obb_dataset_stats/outputs"
DEFAULT_TRACKER = "bytetrack.yaml"
IMGSZ_OBB = 640
REQUIRED_OBB_CLASSES = {"shrimp", "shrimp_head", "shrimp_tail"}


def extract_obb_track_id(obb) -> int | None:
    track_id = getattr(obb, "id", None)
    if track_id is None:
        return None
    try:
        value = track_id.cpu().numpy() if hasattr(track_id, "cpu") else track_id
        array = np.asarray(value).reshape(-1)
        if array.size == 0:
            return None
        return int(array[0])
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


def order_points(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(differences)]
    ordered[3] = points[np.argmax(differences)]
    return ordered


def rectify_shrimp_with_matrix(frame: np.ndarray, polygon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    polygon = np.asarray(polygon, dtype=np.float32).reshape(-1, 2)
    rect = cv2.minAreaRect(polygon)
    source = order_points(cv2.boxPoints(rect))
    width = max(1, int(round(max(np.linalg.norm(source[1] - source[0]), np.linalg.norm(source[2] - source[3])))))
    height = max(1, int(round(max(np.linalg.norm(source[3] - source[0]), np.linalg.norm(source[2] - source[1])))))
    destination = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(source, destination)
    crop = cv2.warpPerspective(frame, matrix, (width, height))
    if crop.shape[0] > crop.shape[1]:
        old_height = crop.shape[0]
        crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
        rotate_matrix = np.array([[0, -1, old_height - 1], [1, 0, 0], [0, 0, 1]], dtype=np.float32)
        matrix = rotate_matrix @ matrix
    return crop, matrix


def point_in_polygon(center: tuple[float, float], polygon: np.ndarray) -> bool:
    contour = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.pointPolygonTest(contour, (float(center[0]), float(center[1])), False) >= 0


def transform_x(center: tuple[float, float], matrix: np.ndarray) -> float:
    point = np.array([[[center[0], center[1]]]], dtype=np.float32)
    return float(cv2.perspectiveTransform(point, matrix)[0, 0, 0])


def orient_head_left(
    crop: np.ndarray,
    matrix: np.ndarray,
    head_centers: list[tuple[float, float]],
    tail_centers: list[tuple[float, float]],
) -> tuple[np.ndarray | None, str]:
    if len(head_centers) == 1:
        flip = transform_x(head_centers[0], matrix) > crop.shape[1] / 2
        source = "head"
    elif len(tail_centers) == 1:
        flip = transform_x(tail_centers[0], matrix) < crop.shape[1] / 2
        source = "tail"
    else:
        return None, "ambiguous_head_and_tail"
    return (cv2.flip(crop, 1) if flip else crop), source


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        if not fieldnames:
            return
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def validate_obb_model(model: YOLO) -> None:
    names = set(model.names.values())
    if model.task != "obb":
        raise ValueError(f"Expected YOLO OBB model, got task={model.task}, names={model.names}")
    missing = REQUIRED_OBB_CLASSES - names
    if missing:
        raise ValueError(f"OBB model must include {sorted(REQUIRED_OBB_CLASSES)}, missing {sorted(missing)}, got: {model.names}")


class ShrimpOnlyDisplayIds:
    def __init__(self) -> None:
        self.mapping: dict[int, int] = {}
        self.next_id = 1

    def get(self, raw_track_id: int | None) -> int | None:
        if raw_track_id is None:
            return None
        raw_track_id = int(raw_track_id)
        if raw_track_id not in self.mapping:
            self.mapping[raw_track_id] = self.next_id
            self.next_id += 1
        return self.mapping[raw_track_id]


def source_name(video_path: str) -> str:
    return Path(video_path).stem


def process_video(
    model: YOLO,
    video_path: str,
    output_dir: Path,
    tracker: str,
    conf: float,
    iou: float,
) -> tuple[list[dict], list[dict]]:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    name = source_name(video_path)
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 0.0
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    dataset_dir = output_dir / f"{name}_dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    display_ids = ShrimpOnlyDisplayIds()
    frame_rows: list[dict] = []
    seen_frames: dict[int, set[int]] = defaultdict(set)
    frame_index = 0
    progress_total = total_frames or None

    with tqdm(total=progress_total, desc=name, unit="frame", ncols=85) as progress:
        while True:
            ok, frame = capture.read()
            if not ok:
                break

            result = model.track(
                frame,
                conf=conf,
                iou=iou,
                imgsz=IMGSZ_OBB,
                tracker=tracker,
                persist=True,
                verbose=False,
            )[0]

            if result.obb is not None:
                rows = []
                for obb in result.obb:
                    class_index = int(obb.cls.cpu().numpy()[0])
                    class_name = result.names[class_index]
                    raw_track_id = extract_obb_track_id(obb)
                    polygon = obb.xyxyxyxy.cpu().numpy()[0].astype(np.float32)
                    confidence = float(obb.conf.cpu().numpy()[0])
                    rows.append(
                        {
                            "class_name": class_name,
                            "raw_track_id": raw_track_id,
                            "polygon": polygon,
                            "center": tuple(np.mean(polygon, axis=0).tolist()),
                            "confidence": confidence,
                        }
                    )

                shrimps = [row for row in rows if row["class_name"] == "shrimp"]
                heads = [row for row in rows if row["class_name"] == "shrimp_head"]
                tails = [row for row in rows if row["class_name"] == "shrimp_tail"]

                for shrimp in shrimps:
                    raw_track_id = shrimp["raw_track_id"]
                    shrimp_id = display_ids.get(raw_track_id)
                    if shrimp_id is None:
                        continue

                    polygon = shrimp["polygon"]
                    confidence = shrimp["confidence"]
                    head_centers = [item["center"] for item in heads if point_in_polygon(item["center"], polygon)]
                    tail_centers = [item["center"] for item in tails if point_in_polygon(item["center"], polygon)]
                    crop, matrix = rectify_shrimp_with_matrix(frame, polygon)
                    crop, direction_source = orient_head_left(crop, matrix, head_centers, tail_centers)
                    if crop is None:
                        continue
                    if crop.size == 0:
                        continue

                    id_dir = dataset_dir / f"ID_{shrimp_id:03d}"
                    id_dir.mkdir(parents=True, exist_ok=True)
                    crop_name = f"frame_{frame_index:06d}_conf_{confidence:.4f}.jpg"
                    cv2.imwrite(str(id_dir / crop_name), crop)

                    seen_frames[shrimp_id].add(frame_index)
                    frame_rows.append(
                        {
                            "video_name": name,
                            "frame_index": frame_index,
                            "shrimp_id": shrimp_id,
                            "raw_tracker_id": raw_track_id,
                            "obb_confidence": round(confidence, 6),
                            "head_count": len(head_centers),
                            "tail_count": len(tail_centers),
                            "direction_source": direction_source,
                            "crop_path": str(id_dir / crop_name),
                        }
                    )

            frame_index += 1
            progress.update(1)

    capture.release()
    summary_rows = [
        {
            "video_name": name,
            "fps": round(fps, 6),
            "shrimp_id": shrimp_id,
            "shrimp_total_frames": len(frames),
            "video_total_frames": total_frames,
        }
        for shrimp_id, frames in sorted(seen_frames.items())
    ]
    return frame_rows, summary_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build OBB track statistics and rectified shrimp crop datasets.")
    parser.add_argument("--obb-model", default=DEFAULT_OBB_MODEL, help="YOLO OBB model path.")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Output root directory.")
    parser.add_argument("--tracker", default=DEFAULT_TRACKER, help="Ultralytics tracker config. Default: bytetrack.yaml")
    parser.add_argument("--conf", type=float, default=0.5, help="YOLO OBB confidence threshold.")
    parser.add_argument("--iou", type=float, default=0.3, help="YOLO OBB IoU threshold.")
    parser.add_argument("--video", action="append", dest="videos", help="Optional video path. Can be passed multiple times.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    videos = args.videos or DEFAULT_VIDEOS
    run_dir = Path(args.output_root) / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.obb_model)
    validate_obb_model(model)

    all_frame_rows: list[dict] = []
    all_summary_rows: list[dict] = []
    for video in videos:
        frame_rows, summary_rows = process_video(
            model=model,
            video_path=video,
            output_dir=run_dir,
            tracker=args.tracker,
            conf=args.conf,
            iou=args.iou,
        )
        all_frame_rows.extend(frame_rows)
        all_summary_rows.extend(summary_rows)

    write_csv(run_dir / "frame_stats.csv", all_frame_rows)
    write_csv(run_dir / "shrimp_summary.csv", all_summary_rows)
    print(f"Output: {run_dir}")


if __name__ == "__main__":
    main()
