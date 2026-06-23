import argparse
import csv
import shutil
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
ASSIGNMENTS = (
    ("train", "male", "公蝦仰拍-1"),
    ("train", "female", "母蝦仰拍-3"),
    ("val", "male", "公蝦仰拍-2"),
    ("val", "female", "母蝦仰拍-2"),
    ("test", "male", "公蝦仰拍-3"),
    ("test", "female", "母蝦仰拍-1"),
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rotate OBB shrimp crops horizontally and export the middle third as abdomen crops."
    )
    parser.add_argument(
        "--input",
        default="../HBB/shrimp_temporal_crops_from_obb_3/images",
        help="Source OBB crop folder. Default: ../HBB/shrimp_temporal_crops_from_obb_3/images",
    )
    parser.add_argument(
        "--output",
        default="CNN_dataset4",
        help="Output dataset folder. Default: CNN_dataset2",
    )
    parser.add_argument("--jpeg-quality", type=int, default=95, help="Output JPEG quality. Default: 95")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete and rebuild the output folder if it already exists.",
    )
    return parser.parse_args()


def resolve_path(path, base_dir):
    path = Path(path)
    return path if path.is_absolute() else (base_dir / path).resolve()


def read_image(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def write_jpeg(path, image, quality):
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return False
    encoded.tofile(str(path))
    return path.exists() and path.stat().st_size > 0


def collect_source_images(input_dir):
    grouped = defaultdict(list)
    video_names = {video_name for _, _, video_name in ASSIGNMENTS}
    for path in sorted(input_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        for video_name in video_names:
            if path.stem.startswith(f"{video_name}__"):
                grouped[video_name].append(path)
                break
    return grouped


def build_assignments(grouped):
    assignments = []
    for split, class_name, video_name in ASSIGNMENTS:
        image_paths = grouped.get(video_name, [])
        if not image_paths:
            raise ValueError(f"No source images found for {video_name}")
        assignments.append((split, class_name, video_name, image_paths))
    return assignments


def crop_abdomen(image):
    source_height, source_width = image.shape[:2]
    rotated = source_height > source_width
    horizontal = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE) if rotated else image

    horizontal_height, total_length = horizontal.shape[:2]
    left = total_length // 4
    right = total_length - total_length // 2
    top = horizontal_height // 5
    bottom = horizontal_height - horizontal_height // 5
    if right <= left:
        raise ValueError(f"Image is too short to crop into thirds: {total_length}px")
    if bottom <= top:
        raise ValueError(f"Image is too low to crop into thirds: {horizontal_height}px")

    abdomen = horizontal[top:bottom, left:right].copy()
    return abdomen, {
        "source_width": source_width,
        "source_height": source_height,
        "rotated_clockwise": rotated,
        "horizontal_width": total_length,
        "horizontal_height": horizontal_height,
        "crop_left": left,
        "crop_right": right,
        "crop_top": top,
        "crop_bottom": bottom,
        "crop_width": abdomen.shape[1],
        "crop_height": abdomen.shape[0],
    }


def prepare_output(output_dir, overwrite):
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {output_dir}. Use --overwrite to rebuild it.")
        shutil.rmtree(output_dir)

    for split, class_name, _ in ASSIGNMENTS:
        (output_dir / split / class_name).mkdir(parents=True, exist_ok=True)


def main():
    args = parse_args()
    if not 1 <= args.jpeg_quality <= 100:
        raise ValueError("--jpeg-quality must be between 1 and 100")

    script_dir = Path(__file__).resolve().parent
    input_dir = resolve_path(args.input, script_dir)
    output_dir = resolve_path(args.output, script_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")

    grouped = collect_source_images(input_dir)
    selections = build_assignments(grouped)
    prepare_output(output_dir, args.overwrite)

    manifest_path = output_dir / "manifest.csv"
    fieldnames = [
        "output_image",
        "source_image",
        "source_video",
        "split",
        "class_name",
        "source_width",
        "source_height",
        "rotated_clockwise",
        "horizontal_width",
        "horizontal_height",
        "crop_left",
        "crop_right",
        "crop_top",
        "crop_bottom",
        "crop_width",
        "crop_height",
    ]

    total_saved = 0
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=fieldnames)
        writer.writeheader()

        for split, class_name, video_name, image_paths in selections:
            target_dir = output_dir / split / class_name
            saved = 0
            for output_index, source_path in enumerate(image_paths):
                image = read_image(source_path)
                if image is None:
                    raise ValueError(f"Cannot read image: {source_path}")

                abdomen, crop_info = crop_abdomen(image)
                output_name = f"{video_name}_abdomen_{output_index:04d}.jpg"
                output_path = target_dir / output_name
                if not write_jpeg(output_path, abdomen, args.jpeg_quality):
                    raise OSError(f"Cannot write image: {output_path}")

                writer.writerow(
                    {
                        "output_image": str(output_path),
                        "source_image": str(source_path),
                        "source_video": video_name,
                        "split": split,
                        "class_name": class_name,
                        **crop_info,
                    }
                )
                saved += 1
                total_saved += 1

            print(f"{split}/{class_name}: {saved} image(s) from {video_name}")

    print(f"Output: {output_dir}")
    print(f"Total saved: {total_saved}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
