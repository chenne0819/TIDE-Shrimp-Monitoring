import argparse
import csv
import random
import re
import shutil
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".wmv"}
HBB_CLASS_NAMES = ["male_line"]
SHRIMP_CLASS_NAME = "shrimp"
HEAD_CLASS_NAME = "shrimp_head"
TAIL_CLASS_NAME = "shrimp_tail"


def parse_args(
    default_model="runs/obb/traindata_obb_dataset3_yolo11m/weights/best.pt",
    default_output_dir="../HBB/shrimp_temporal_crops_from_obb_3",
    default_direction_mode="head-tail",
):
    parser = argparse.ArgumentParser(
        description="Use a trained OBB model to crop single shrimp images for later HBB annotation/training."
    )
    parser.add_argument(
        "--model",
        default=default_model,
        help=f"Trained OBB model path. Default: {default_model}",
    )
    parser.add_argument(
        "--video-dir",
        default="../video",
        help="Folder that contains source videos. Default: ../video",
    )
    parser.add_argument(
        "--output-dir",
        default=default_output_dir,
        help=f"Output crop dataset folder. Default: {default_output_dir}",
    )
    parser.add_argument(
        "--layout",
        choices=["temporal", "hbb"],
        default="temporal",
        help="Output layout. temporal writes ordered images/ for multi-channel stacking; hbb writes train/val images. Default: temporal",
    )
    parser.add_argument(
        "--existing",
        choices=["fail", "skip", "append", "overwrite"],
        default="fail",
        help="What to do if output already has files. Default: fail",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=180,
        help="Run OBB inference once every N frames. Default: 180",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.2,
        help="Ratio of cropped shrimp images assigned to val when --layout hbb. Default: 0.2",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="OBB inference image size. Use the same or larger size as OBB training. Default: 640",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.35,
        help="Minimum OBB detection confidence. Default: 0.35",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=40,
        help="Skip crops whose width or height is smaller than this many pixels. Default: 40",
    )
    parser.add_argument(
        "--crop-width",
        type=int,
        default=416,
        help="Resize width used when --resize-mode is letterbox or stretch. Default: 416",
    )
    parser.add_argument(
        "--crop-height",
        type=int,
        default=416,
        help="Resize height used when --resize-mode is letterbox or stretch. Default: 416",
    )
    parser.add_argument(
        "--resize-mode",
        choices=["original", "letterbox", "stretch"],
        default="original",
        help="original keeps exact OBB crop size; letterbox pads; stretch forces exact size and may distort. Default: original",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic train/val split. Default: 42",
    )
    parser.add_argument(
        "--image-ext",
        choices=["jpg", "png"],
        default="jpg",
        help="Saved image format. Default: jpg",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=95,
        help="JPEG quality from 1 to 100. Used only when --image-ext jpg. Default: 95",
    )
    parser.add_argument(
        "--enhance",
        action="store_true",
        help="Apply CLAHE + sharpening to cropped images.",
    )
    parser.add_argument(
        "--orientation",
        choices=["horizontal", "keep"],
        default="horizontal",
        help="Crop orientation. horizontal rotates tall crops to landscape. keep preserves OBB output. Default: horizontal",
    )
    parser.add_argument(
        "--direction-mode",
        choices=["head-tail", "stable"],
        default=default_direction_mode,
        help=f"head-tail uses shrimp_head/shrimp_tail; stable supports shrimp-only models. Default: {default_direction_mode}",
    )
    parser.add_argument(
        "--no-stable-direction",
        action="store_true",
        help="Disable left/right direction stabilization within each video and detection index.",
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=0,
        help="Process at most this many videos. 0 means no limit.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Read at most this many frames from each video. 0 means no limit.",
    )
    parser.add_argument(
        "--empty-labels",
        action="store_true",
        help="Create an empty YOLO HBB .txt label file for each cropped image.",
    )
    parser.add_argument(
        "--write-yaml",
        action="store_true",
        help="Also write HBB/data.yaml pointing to this cropped dataset.",
    )
    return parser.parse_args()


def safe_stem(name):
    stem = Path(name).stem.strip()
    stem = re.sub(r'[<>:"/\\|?*]+', "_", stem)
    stem = re.sub(r"\s+", "_", stem)
    return stem or "video"


def resolve_path(path, base_dir):
    path = Path(path)
    return path if path.is_absolute() else base_dir / path


def collect_videos(video_dir):
    video_dir = Path(video_dir)
    return sorted(
        path
        for path in video_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def prepare_output_dir(output_dir, layout, existing):
    output_dir = Path(output_dir)
    has_files = output_dir.exists() and any(path.is_file() for path in output_dir.rglob("*"))
    if has_files:
        if existing == "fail":
            raise FileExistsError(f"Output already contains files: {output_dir}. Use --existing append/skip/overwrite.")
        if existing == "skip":
            print(f"[SKIP] Output already contains files: {output_dir}")
            return output_dir, True
        if existing == "overwrite":
            shutil.rmtree(output_dir)

    if layout == "temporal":
        (output_dir / "images").mkdir(parents=True, exist_ok=True)
    else:
        for split in ("train", "val"):
            (output_dir / split / "images").mkdir(parents=True, exist_ok=True)
            (output_dir / split / "labels").mkdir(parents=True, exist_ok=True)
    return output_dir, False


def choose_split(rng, val_ratio):
    return "val" if rng.random() < val_ratio else "train"


def write_image(path, frame, image_ext, jpeg_quality):
    encode_ext = ".jpg" if image_ext == "jpg" else ".png"
    params = []
    if image_ext == "jpg":
        params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]

    ok, encoded = cv2.imencode(encode_ext, frame, params)
    if not ok:
        return False

    encoded.tofile(str(path))
    return path.exists() and path.stat().st_size > 0


def order_quad_points(points):
    points = np.asarray(points, dtype="float32").reshape(4, 2)
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    ordered = points[np.argsort(angles)]
    start_index = np.argmin(ordered.sum(axis=1))
    ordered = np.roll(ordered, -start_index, axis=0)
    return ordered


def crop_oriented_box(image, obb_points):
    rect = cv2.minAreaRect(np.asarray(obb_points, dtype="float32").reshape(-1, 2))
    src = order_quad_points(cv2.boxPoints(rect)).astype("float32")
    top_width = np.linalg.norm(src[1] - src[0])
    bottom_width = np.linalg.norm(src[2] - src[3])
    left_height = np.linalg.norm(src[3] - src[0])
    right_height = np.linalg.norm(src[2] - src[1])
    crop_w = max(1, int(round(max(top_width, bottom_width))))
    crop_h = max(1, int(round(max(left_height, right_height))))

    dst = np.array(
        [
            [0, 0],
            [crop_w - 1, 0],
            [crop_w - 1, crop_h - 1],
            [0, crop_h - 1],
        ],
        dtype="float32",
    )

    matrix = cv2.getPerspectiveTransform(src, dst)
    crop = cv2.warpPerspective(
        image,
        matrix,
        (crop_w, crop_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return crop, matrix


def normalize_crop_orientation(image, matrix, orientation):
    if orientation == "keep":
        return image, matrix

    height, width = image.shape[:2]
    if height > width:
        rotation_matrix = np.array(
            [
                [0.0, -1.0, height - 1.0],
                [1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype="float32",
        )
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), rotation_matrix @ matrix
    return image, matrix


def find_part_detections_inside(shrimp_points, part_detections):
    body_points = order_quad_points(shrimp_points).astype("float32")
    inside = []
    for detection in part_detections:
        center = np.asarray(detection[0][:2], dtype="float32")
        if cv2.pointPolygonTest(body_points, tuple(center), False) >= 0:
            inside.append(detection)
    return sorted(inside, key=lambda detection: detection[2], reverse=True)


def select_orientation_detections(heads_inside, tails_inside):
    head_count = len(heads_inside)
    tail_count = len(tails_inside)

    if head_count > 1:
        return (None, tails_inside[0], True) if tail_count == 1 else (None, None, False)
    if tail_count > 1:
        return (heads_inside[0], None, True) if head_count == 1 else (None, None, False)
    if head_count == 0 and tail_count == 0:
        return None, None, False
    return (
        heads_inside[0] if head_count == 1 else None,
        tails_inside[0] if tail_count == 1 else None,
        True,
    )


def transform_detection_center(detection, matrix):
    if detection is None:
        return None
    center = np.asarray(detection[0][:2], dtype="float32").reshape(1, 1, 2)
    return cv2.perspectiveTransform(center, matrix)[0, 0]


def orient_head_left(image, matrix, head_detection, tail_detection):
    head_point = transform_detection_center(head_detection, matrix)
    tail_point = transform_detection_center(tail_detection, matrix)
    width = image.shape[1]

    if head_point is not None and tail_point is not None:
        if abs(float(head_point[0] - tail_point[0])) < max(2.0, width * 0.05):
            return image, False
        flip = head_point[0] > tail_point[0]
    elif head_point is not None:
        flip = head_point[0] > (width - 1) / 2
    elif tail_point is not None:
        flip = tail_point[0] < (width - 1) / 2
    else:
        return image, False

    return (cv2.flip(image, 1) if flip else image), True


def resize_crop(image, width, height, mode="letterbox"):
    if mode == "original":
        return image
    if image.shape[1] == width and image.shape[0] == height:
        return image
    if mode == "stretch":
        return cv2.resize(image, (width, height), interpolation=cv2.INTER_LINEAR)

    src_h, src_w = image.shape[:2]
    scale = min(width / src_w, height / src_h)
    resized_w = max(1, int(round(src_w * scale)))
    resized_h = max(1, int(round(src_h * scale)))
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)

    canvas = np.full((height, width, 3), 114, dtype=image.dtype)
    left = (width - resized_w) // 2
    top = (height - resized_h) // 2
    canvas[top : top + resized_h, left : left + resized_w] = resized
    return canvas


def crop_signature(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    small -= float(small.mean())
    std = float(small.std())
    if std > 1e-6:
        small /= std
    return small


def stabilize_left_right_direction(image, key, references):
    current = crop_signature(image)
    reference = references.get(key)
    if reference is None:
        references[key] = current
        return image

    flipped = cv2.flip(image, 1)
    flipped_sig = crop_signature(flipped)
    if np.mean((flipped_sig - reference) ** 2) < np.mean((current - reference) ** 2):
        references[key] = flipped_sig
        return flipped

    references[key] = current
    return image


def sharpen_and_contrast(image):
    if image.size == 0:
        return image

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(l_channel)
    enhanced = cv2.merge((enhanced_l, a_channel, b_channel))
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    blur = cv2.GaussianBlur(enhanced, (5, 5), 1.2)
    return cv2.addWeighted(enhanced, 1.45, blur, -0.45, 0)


def iter_obb_detections(result, conf_threshold):
    if result.obb is None:
        return

    xywhr = result.obb.xywhr.cpu().numpy()
    xyxyxyxy = result.obb.xyxyxyxy.cpu().numpy()
    confs = result.obb.conf.cpu().numpy() if result.obb.conf is not None else np.ones(len(xywhr))
    classes = result.obb.cls.cpu().numpy() if result.obb.cls is not None else np.zeros(len(xywhr))

    class_names = result.names
    for box, points, conf, cls_id in zip(xywhr, xyxyxyxy, confs, classes):
        if float(conf) >= conf_threshold:
            class_id = int(cls_id)
            class_name = class_names[class_id] if isinstance(class_names, dict) else class_names[class_id]
            yield box, points, float(conf), class_id, class_name


def extract_crops(
    model,
    video_path,
    output_dir,
    interval,
    val_ratio,
    rng,
    imgsz,
    conf,
    min_size,
    crop_width,
    crop_height,
    resize_mode,
    image_ext,
    jpeg_quality,
    enhance,
    orientation,
    direction_mode,
    stable_direction,
    layout,
    max_frames,
    empty_labels,
    metadata_writer,
):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[WARN] Cannot open video: {video_path}")
        return {"frames": 0, "saved": 0, "failed": 0, "detections": 0, "skipped_direction": 0}

    video_name = safe_stem(video_path.name)
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 0.0
    frame_index = 0
    crop_index = 0
    saved = 0
    failed = 0
    detections = 0
    skipped_direction = 0
    direction_refs = {} if direction_mode == "stable" else None

    while True:
        if max_frames and frame_index >= max_frames:
            break
        ok, frame = cap.read()
        if not ok:
            break

        if frame_index % interval == 0:
            results = model(frame, imgsz=imgsz, conf=conf, verbose=False)
            all_detections = list(iter_obb_detections(results[0], conf))
            shrimp_detections = sorted(
                (detection for detection in all_detections if detection[4] == SHRIMP_CLASS_NAME),
                key=lambda item: (float(item[0][0]), float(item[0][1])),
            )
            if direction_mode == "head-tail":
                head_detections = [detection for detection in all_detections if detection[4] == HEAD_CLASS_NAME]
                tail_detections = [detection for detection in all_detections if detection[4] == TAIL_CLASS_NAME]
            else:
                head_detections = []
                tail_detections = []

            for det_index, (obb_box, obb_points, det_conf, cls_id, _) in enumerate(shrimp_detections):
                detections += 1

                if direction_mode == "head-tail":
                    heads_inside = find_part_detections_inside(obb_points, head_detections)
                    tails_inside = find_part_detections_inside(obb_points, tail_detections)
                    head_detection, tail_detection, direction_is_valid = select_orientation_detections(
                        heads_inside,
                        tails_inside,
                    )
                    if not direction_is_valid:
                        skipped_direction += 1
                        continue
                else:
                    head_detection = None
                    tail_detection = None

                try:
                    crop, crop_matrix = crop_oriented_box(frame, obb_points)
                except cv2.error:
                    failed += 1
                    continue

                crop, crop_matrix = normalize_crop_orientation(crop, crop_matrix, orientation)
                height, width = crop.shape[:2]
                if width < min_size or height < min_size:
                    continue

                if direction_mode == "head-tail":
                    crop, direction_is_valid = orient_head_left(
                        crop,
                        crop_matrix,
                        head_detection,
                        tail_detection,
                    )
                    if not direction_is_valid:
                        skipped_direction += 1
                        continue
                elif stable_direction and orientation == "horizontal":
                    crop = stabilize_left_right_direction(
                        crop,
                        (video_name, det_index),
                        direction_refs,
                    )

                if enhance:
                    crop = sharpen_and_contrast(crop)

                crop = resize_crop(crop, crop_width, crop_height, resize_mode)
                output_height, output_width = crop.shape[:2]

                time_sec = frame_index / fps if fps > 0 else 0.0
                time_ms = int(round(time_sec * 1000))
                sort_key = f"{video_name}__di_{det_index:02d}__frame_{frame_index:08d}__t_{time_ms:010d}ms"
                image_stem = sort_key if layout == "temporal" else f"{video_name}_crop_{crop_index:05d}"
                if layout == "temporal":
                    split = ""
                    image_path = output_dir / "images" / f"{image_stem}.{image_ext}"
                else:
                    split = choose_split(rng, val_ratio)
                    image_path = output_dir / split / "images" / f"{image_stem}.{image_ext}"

                if image_path.exists():
                    failed += 1
                    print(f"[WARN] Skip existing image: {image_path}")
                    continue

                if write_image(image_path, crop, image_ext, jpeg_quality):
                    if empty_labels and layout == "hbb":
                        label_path = output_dir / split / "labels" / f"{image_stem}.txt"
                        label_path.write_text("", encoding="utf-8")

                    cx, cy, obb_w, obb_h, rotation = obb_box
                    metadata_writer.writerow(
                        {
                            "image": str(image_path),
                            "split": split,
                            "video_name": video_name,
                            "source_video": str(video_path),
                            "source_frame": frame_index,
                            "source_time_sec": f"{time_sec:.6f}",
                            "source_time_ms": time_ms,
                            "fps": f"{fps:.6f}",
                            "detection_index": det_index,
                            "sort_key": sort_key,
                            "obb_class": cls_id,
                            "obb_conf": f"{det_conf:.6f}",
                            "obb_cx": f"{cx:.3f}",
                            "obb_cy": f"{cy:.3f}",
                            "obb_w": f"{obb_w:.3f}",
                            "obb_h": f"{obb_h:.3f}",
                            "obb_rotation": f"{rotation:.6f}",
                            "crop_width": width,
                            "crop_height": height,
                            "output_width": output_width,
                            "output_height": output_height,
                            "resize_mode": resize_mode,
                        }
                    )
                    saved += 1
                    crop_index += 1
                else:
                    failed += 1
                    print(f"[WARN] Failed to write image: {image_path}")

        frame_index += 1

    cap.release()
    return {
        "frames": frame_index,
        "saved": saved,
        "failed": failed,
        "detections": detections,
        "skipped_direction": skipped_direction,
    }


def write_hbb_yaml(hbb_dir, output_dir):
    yaml_path = hbb_dir / "data.yaml"
    try:
        dataset_path = output_dir.relative_to(hbb_dir).as_posix()
    except ValueError:
        dataset_path = output_dir.as_posix()

    names = ", ".join(f"'{name}'" for name in HBB_CLASS_NAMES)
    yaml_text = (
        f"train: ./{dataset_path}/train/images\n"
        f"val: ./{dataset_path}/val/images\n\n"
        f"nc: {len(HBB_CLASS_NAMES)}\n"
        f"names: [{names}]\n"
    )
    yaml_path.write_text(yaml_text, encoding="utf-8")
    return yaml_path


def main(
    default_model="runs/obb/traindata_obb_dataset3_yolo11m/weights/best.pt",
    default_output_dir="../HBB/shrimp_temporal_crops_from_obb_3",
    default_direction_mode="head-tail",
):
    args = parse_args(default_model, default_output_dir, default_direction_mode)
    script_dir = Path(__file__).resolve().parent
    hbb_dir = script_dir.parent / "HBB"

    if args.interval <= 0:
        raise ValueError("--interval must be greater than 0")
    if not 0 <= args.val_ratio <= 1:
        raise ValueError("--val-ratio must be between 0 and 1")
    if not 0 <= args.conf <= 1:
        raise ValueError("--conf must be between 0 and 1")
    if args.min_size <= 0:
        raise ValueError("--min-size must be greater than 0")
    if args.crop_width <= 0 or args.crop_height <= 0:
        raise ValueError("--crop-width and --crop-height must be greater than 0")
    if not 1 <= args.jpeg_quality <= 100:
        raise ValueError("--jpeg-quality must be between 1 and 100")

    model_path = resolve_path(args.model, script_dir)
    video_dir = resolve_path(args.video_dir, script_dir)
    output_dir, skip_output = prepare_output_dir(resolve_path(args.output_dir, script_dir), args.layout, args.existing)
    if skip_output:
        return

    if not model_path.exists():
        raise FileNotFoundError(f"OBB model not found: {model_path}")
    if not video_dir.exists():
        raise FileNotFoundError(f"Video folder not found: {video_dir}")

    videos = collect_videos(video_dir)
    if args.max_videos and args.max_videos > 0:
        videos = videos[: args.max_videos]
    if not videos:
        raise FileNotFoundError(f"No video files found in: {video_dir}")

    print(f"Loading OBB model: {model_path}")
    model = YOLO(str(model_path))
    model_class_names = set(model.names.values() if isinstance(model.names, dict) else model.names)
    required_class_names = {SHRIMP_CLASS_NAME}
    if args.direction_mode == "head-tail":
        required_class_names.update({HEAD_CLASS_NAME, TAIL_CLASS_NAME})
    missing_class_names = required_class_names - model_class_names
    if missing_class_names:
        raise ValueError(
            f"OBB model is missing required classes: {sorted(missing_class_names)}. "
            f"Available classes: {sorted(model_class_names)}"
        )
    print(f"OBB classes: {sorted(model_class_names)}")
    rng = random.Random(args.seed)

    metadata_path = output_dir / "crop_metadata.csv"
    fieldnames = [
        "image",
        "split",
        "video_name",
        "source_video",
        "source_frame",
        "source_time_sec",
        "source_time_ms",
        "fps",
        "detection_index",
        "sort_key",
        "obb_class",
        "obb_conf",
        "obb_cx",
        "obb_cy",
        "obb_w",
        "obb_h",
        "obb_rotation",
        "crop_width",
        "crop_height",
        "output_width",
        "output_height",
        "resize_mode",
    ]

    total_saved = 0
    total_failed = 0
    total_detections = 0
    total_skipped_direction = 0

    print(f"Found {len(videos)} video(s) in {video_dir}")
    print(f"Output crop dataset: {output_dir}")
    print(f"Layout: {args.layout} | inference every {args.interval} frame(s), conf: {args.conf}")
    print(f"Direction mode: {args.direction_mode}")
    if args.resize_mode == "original":
        print("Saved crop size: original OBB crop size")
    else:
        print(f"Saved crop size: {args.crop_width}x{args.crop_height} ({args.resize_mode})")
    if args.direction_mode == "stable":
        print(f"Stable direction: {not args.no_stable_direction}")
    if args.max_frames:
        print(f"Max frames per video: {args.max_frames}")
    if args.layout == "hbb":
        print(f"Val ratio: {args.val_ratio}")
        print("For HBB training, label each cropped image with YOLO HBB boxes:")
        print("class x_center y_center width height")
        print("Coordinates must be normalized to 0-1.\n")

    append_metadata = args.existing == "append" and metadata_path.exists()
    with metadata_path.open("a" if append_metadata else "w", newline="", encoding="utf-8-sig") as metadata_file:
        writer = csv.DictWriter(metadata_file, fieldnames=fieldnames)
        if not append_metadata:
            writer.writeheader()

        for video_path in videos:
            result = extract_crops(
                model=model,
                video_path=video_path,
                output_dir=output_dir,
                interval=args.interval,
                val_ratio=args.val_ratio,
                rng=rng,
                imgsz=args.imgsz,
                conf=args.conf,
                min_size=args.min_size,
                crop_width=args.crop_width,
                crop_height=args.crop_height,
                resize_mode=args.resize_mode,
                image_ext=args.image_ext,
                jpeg_quality=args.jpeg_quality,
                enhance=args.enhance,
                orientation=args.orientation,
                direction_mode=args.direction_mode,
                stable_direction=not args.no_stable_direction,
                layout=args.layout,
                max_frames=args.max_frames,
                empty_labels=args.empty_labels,
                metadata_writer=writer,
            )
            total_saved += result["saved"]
            total_failed += result["failed"]
            total_detections += result["detections"]
            total_skipped_direction += result["skipped_direction"]
            print(
                f"{video_path.name}: read {result['frames']} frame(s), "
                f"detections {result['detections']}, saved {result['saved']} crop(s), "
                f"ambiguous direction {result['skipped_direction']}, failed {result['failed']}"
            )

    if args.write_yaml and args.layout == "hbb":
        yaml_path = write_hbb_yaml(hbb_dir, output_dir)
        print(f"\nWrote HBB data config: {yaml_path}")

    if args.layout == "temporal":
        image_count = len(list((output_dir / "images").glob(f"*.{args.image_ext}")))
    else:
        train_count = len(list((output_dir / "train" / "images").glob(f"*.{args.image_ext}")))
        val_count = len(list((output_dir / "val" / "images").glob(f"*.{args.image_ext}")))

    print("\nDone.")
    print(f"Total detections: {total_detections}")
    print(f"Total saved crops: {total_saved}, failed: {total_failed}")
    print(f"Skipped for missing/ambiguous head-tail direction: {total_skipped_direction}")
    if args.layout == "temporal":
        print(f"images: {image_count}")
    else:
        print(f"train/images: {train_count}")
        print(f"val/images: {val_count}")
    print(f"Metadata: {metadata_path}")
    print("\nNext step: use metadata sort_key or filename order to build multi-channel temporal stacks.")


if __name__ == "__main__":
    main()
