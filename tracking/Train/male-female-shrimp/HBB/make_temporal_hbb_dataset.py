from __future__ import annotations

import argparse
import json
import re
import shutil
from bisect import bisect_left
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


IMAGE_SUFFIXES = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
CROP_RE = re.compile(r"^(?P<prefix>.+)_crop_(?P<index>\d+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a YOLO HBB temporal multi-channel dataset from images-train JSON annotations."
    )
    parser.add_argument("--source", default="shrimp_HBB_dataset", help="Source YOLO dataset folder.")
    parser.add_argument("--output", default="shrimp_HBB_temporal30_dataset", help="Output dataset folder.")
    parser.add_argument("--frames", type=int, default=10, help="Number of consecutive RGB crops to stack. Default: 10")
    parser.add_argument(
        "--mode",
        choices=("center", "history"),
        default="center",
        help="center uses surrounding frames; history uses oldest..current frames.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the output dataset if it already exists. The source dataset is never modified.",
    )
    return parser.parse_args()


def image_path_for_stem(images_dir: Path, stem: str) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        candidate = images_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def parse_crop_key(path: Path) -> tuple[str, int] | None:
    match = CROP_RE.match(path.stem)
    if not match:
        return None
    return match.group("prefix"), int(match.group("index"))


def collect_split_items(source_root: Path, split: str) -> list[dict]:
    split_root = source_root / split
    images_train_dir = split_root / "images-train"
    if not images_train_dir.exists():
        return []

    items = []
    for json_path in sorted(images_train_dir.glob("*.json")):
        image_path = image_path_for_stem(images_train_dir, json_path.stem)
        if image_path is None:
            continue
        crop_key = parse_crop_key(image_path)
        if crop_key is None:
            continue
        prefix, index = crop_key
        items.append({"image": image_path, "json": json_path, "prefix": prefix, "index": index})
    return items


def collect_context_items(source_root: Path, split: str) -> list[dict]:
    images_train_dir = source_root / split / "images-train"
    if not images_train_dir.exists():
        return []

    items = []
    for image_path in sorted(images_train_dir.iterdir()):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        crop_key = parse_crop_key(image_path)
        if crop_key is None:
            continue
        prefix, index = crop_key
        items.append({"image": image_path, "prefix": prefix, "index": index})
    return items


def build_lookup(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(item["prefix"], []).append(item)
    for group_items in groups.values():
        group_items.sort(key=lambda x: x["index"])
    return groups


def choose_stack_items(group_items: list[dict], center_index: int, frames: int, mode: str) -> list[dict]:
    indexes = [item["index"] for item in group_items]
    center_pos = bisect_left(indexes, center_index)
    if center_pos >= len(group_items) or group_items[center_pos]["index"] != center_index:
        center_pos = max(0, min(center_pos, len(group_items) - 1))

    if mode == "history":
        offsets = range(-(frames - 1), 1)
    else:
        left = frames // 2
        offsets = range(-left, frames - left)

    stack = []
    for offset in offsets:
        pos = max(0, min(center_pos + offset, len(group_items) - 1))
        stack.append(group_items[pos])
    return stack


def read_rgb(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def resize_like(image: np.ndarray, reference_hw: tuple[int, int]) -> np.ndarray:
    ref_h, ref_w = reference_hw
    if image.shape[:2] == (ref_h, ref_w):
        return image
    return cv2.resize(image, (ref_w, ref_h), interpolation=cv2.INTER_LINEAR)


def write_multipage_tiff(path: Path, chw: np.ndarray) -> None:
    pages = [Image.fromarray(chw[channel]) for channel in range(chw.shape[0])]
    path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(path, save_all=True, append_images=pages[1:])


def make_temporal_sample(center_item: dict, group_items: list[dict], frames: int, mode: str, out_image: Path) -> None:
    stack_items = choose_stack_items(group_items, center_item["index"], frames, mode)
    center_rgb = read_rgb(center_item["image"])
    reference_hw = center_rgb.shape[:2]

    channels = []
    for item in stack_items:
        rgb = resize_like(read_rgb(item["image"]), reference_hw)
        channels.extend([rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]])
    chw = np.stack(channels, axis=0).astype(np.uint8)
    write_multipage_tiff(out_image, chw)


def json_to_yolo_lines(json_path: Path) -> list[str]:
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    image_w = float(data.get("imageWidth") or 0)
    image_h = float(data.get("imageHeight") or 0)
    if image_w <= 0 or image_h <= 0:
        raise ValueError(f"Invalid image size in JSON: {json_path}")

    lines = []
    for shape in data.get("shapes", []):
        if str(shape.get("label", "")).lower() != "male_line":
            continue
        points = shape.get("points") or []
        if len(points) < 2:
            continue
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        x1, x2 = max(0.0, min(xs)), min(image_w, max(xs))
        y1, y2 = max(0.0, min(ys)), min(image_h, max(ys))
        box_w = max(0.0, x2 - x1)
        box_h = max(0.0, y2 - y1)
        if box_w <= 0 or box_h <= 0:
            continue
        x_center = (x1 + x2) / 2.0 / image_w
        y_center = (y1 + y2) / 2.0 / image_h
        lines.append(f"0 {x_center:.6f} {y_center:.6f} {box_w / image_w:.6f} {box_h / image_h:.6f}")
    return lines


def write_yolo_label(json_path: Path, out_label: Path) -> None:
    out_label.parent.mkdir(parents=True, exist_ok=True)
    lines = json_to_yolo_lines(json_path)
    out_label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def build_dataset(source_root: Path, output_root: Path, frames: int, mode: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for split in ("train", "val"):
        items = collect_split_items(source_root, split)
        groups = build_lookup(collect_context_items(source_root, split))
        counts[split] = 0
        for item in items:
            if item["prefix"] not in groups:
                continue
            out_image = output_root / split / "images" / f"{item['image'].stem}.tif"
            out_label = output_root / split / "labels" / f"{item['json'].stem}.txt"
            make_temporal_sample(item, groups[item["prefix"]], frames, mode, out_image)
            write_yolo_label(item["json"], out_label)
            counts[split] += 1
    return counts


def main() -> None:
    args = parse_args()
    if args.frames < 1:
        raise ValueError("--frames must be >= 1")

    source_root = Path(args.source)
    output_root = Path(args.output)
    if not source_root.exists():
        raise FileNotFoundError(f"Source dataset not found: {source_root}")
    if output_root.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output already exists: {output_root}. Use --overwrite to replace it.")
        shutil.rmtree(output_root)

    counts = build_dataset(source_root, output_root, args.frames, args.mode)
    channels = args.frames * 3
    print(f"Created temporal HBB dataset: {output_root}")
    print(f"Channels: {channels}")
    print(f"Samples: train={counts.get('train', 0)}, val={counts.get('val', 0)}, test={counts.get('test', 0)}")
    print("Use data-temporal.yaml for training.")


if __name__ == "__main__":
    main()
