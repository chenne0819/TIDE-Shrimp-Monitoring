from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import cv2


DATASET_PLAN = {
    "train": [
        ("公蝦仰拍-1.mp4", 300),
        ("母蝦仰拍-1.mp4", 300),
    ],
    "val": [
        ("公蝦仰拍-2.mp4", 100),
        ("母蝦仰拍-3.mp4", 100),
    ],
    "test": [
        ("公母蝦仰拍-1.mp4", 200),
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract the fixed shrimp frame_dataset split from videos.")
    parser.add_argument("--video-dir", default="video", help="Folder that contains source videos. Default: video")
    parser.add_argument("--output-dir", default="frame_dataset", help="Output dataset folder. Default: frame_dataset")
    parser.add_argument("--interval", type=int, default=30, help="Save one frame every N frames. Default: 30")
    parser.add_argument("--image-ext", choices=["jpg", "png"], default="jpg", help="Saved image format. Default: jpg")
    parser.add_argument("--jpeg-quality", type=int, default=95, help="JPEG quality from 1 to 100. Default: 95")
    parser.add_argument("--overwrite", action="store_true", help="Delete and recreate the output folder if it exists.")
    parser.add_argument(
        "--allow-short",
        action="store_true",
        help="Save all available interval frames when a video has fewer frames than requested.",
    )
    return parser.parse_args()


def resolve_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate
    script_relative = Path(__file__).resolve().parent / path
    if script_relative.exists():
        return script_relative
    return candidate


def prepare_output(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {output_dir}. Use --overwrite to replace it.")
        shutil.rmtree(output_dir)
    for split in DATASET_PLAN:
        (output_dir / split / "images").mkdir(parents=True, exist_ok=True)


def count_available_frames(video_path: Path, interval: int) -> tuple[int, int]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    available = ((total_frames - 1) // interval + 1) if total_frames > 0 else 0
    return total_frames, available


def validate_plan(video_dir: Path, interval: int, allow_short: bool) -> None:
    problems = []
    for split, items in DATASET_PLAN.items():
        for video_name, target_count in items:
            video_path = video_dir / video_name
            if not video_path.exists():
                problems.append(f"{split}: missing video {video_path}")
                continue
            total_frames, available = count_available_frames(video_path, interval)
            if available < target_count:
                problems.append(
                    f"{split}: {video_name} needs {target_count} images, but only {available} "
                    f"are available from {total_frames} frames with interval {interval}."
                )
    if problems and not allow_short:
        joined = "\n".join(f"- {item}" for item in problems)
        raise ValueError(
            "The requested frame_dataset cannot be created exactly.\n"
            f"{joined}\n"
            "Use --allow-short to export the available frames, or reduce --interval / target counts."
        )
    for problem in problems:
        print(f"[WARN] {problem}")


def write_image(path: Path, frame, image_ext: str, jpeg_quality: int) -> bool:
    encode_ext = ".jpg" if image_ext == "jpg" else ".png"
    params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality] if image_ext == "jpg" else []
    ok, encoded = cv2.imencode(encode_ext, frame, params)
    if not ok:
        return False
    encoded.tofile(str(path))
    return path.exists() and path.stat().st_size > 0


def extract_video(
    video_path: Path,
    output_images_dir: Path,
    split: str,
    target_count: int,
    interval: int,
    image_ext: str,
    jpeg_quality: int,
    allow_short: bool,
) -> dict[str, int]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    saved = 0
    failed = 0
    frame_idx = 0
    video_stem = video_path.stem

    while saved < target_count:
        source_frame = saved * interval
        cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame)
        ok, frame = cap.read()
        if not ok:
            if allow_short:
                break
            raise RuntimeError(f"{video_path.name}: cannot read frame {source_frame}")

        image_name = f"{split}_{video_stem}_frame_{source_frame:08d}.{image_ext}"
        image_path = output_images_dir / image_name
        if write_image(image_path, frame, image_ext, jpeg_quality):
            saved += 1
        else:
            failed += 1
            print(f"[WARN] Failed to write image: {image_path}")

        frame_idx = source_frame

    cap.release()
    return {"saved": saved, "failed": failed, "last_frame": frame_idx}


def main() -> None:
    args = parse_args()
    if args.interval <= 0:
        raise ValueError("--interval must be greater than 0")
    if not 1 <= args.jpeg_quality <= 100:
        raise ValueError("--jpeg-quality must be between 1 and 100")

    video_dir = resolve_path(args.video_dir)
    if not video_dir.exists():
        raise FileNotFoundError(f"Video folder not found: {video_dir}")

    output_dir = resolve_path(args.output_dir)
    validate_plan(video_dir, args.interval, args.allow_short)
    prepare_output(output_dir, args.overwrite)

    totals = {split: 0 for split in DATASET_PLAN}
    failures = 0
    print(f"Video folder: {video_dir}")
    print(f"Output folder: {output_dir}")
    print(f"Interval: every {args.interval} frames")

    for split, items in DATASET_PLAN.items():
        output_images_dir = output_dir / split / "images"
        for video_name, target_count in items:
            result = extract_video(
                video_path=video_dir / video_name,
                output_images_dir=output_images_dir,
                split=split,
                target_count=target_count,
                interval=args.interval,
                image_ext=args.image_ext,
                jpeg_quality=args.jpeg_quality,
                allow_short=args.allow_short,
            )
            totals[split] += result["saved"]
            failures += result["failed"]
            print(
                f"{split}/{video_name}: saved {result['saved']} image(s), "
                f"failed {result['failed']}, last frame {result['last_frame']}"
            )

    print("\nDone.")
    print(f"train/images: {totals['train']}")
    print(f"val/images: {totals['val']}")
    print(f"test/images: {totals['test']}")
    print(f"failed writes: {failures}")


if __name__ == "__main__":
    main()
