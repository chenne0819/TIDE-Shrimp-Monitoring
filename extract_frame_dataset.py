"""Extract and verify 120 non-overlapping 30-frame segments per shrimp video."""

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "dataset"
SEGMENTS = 120
FRAMES_PER_SEGMENT = 30
JPEG_QUALITY = 95


def write_metadata(metadata):
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def inspect_sources():
    sources = []
    for sex in ("公蝦", "母蝦"):
        for number in (1, 2, 3):
            path = ROOT / "tracking" / "video" / f"{sex}仰拍-{number}.mp4"
            capture = cv2.VideoCapture(str(path))
            try:
                if not capture.isOpened():
                    raise RuntimeError(f"Cannot open {path}")
                count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = capture.get(cv2.CAP_PROP_FPS)
                width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            finally:
                capture.release()
            if count < SEGMENTS * FRAMES_PER_SEGMENT or fps <= 0:
                raise RuntimeError(f"Insufficient frames or invalid FPS: {path}")
            starts = [round(i * (count - FRAMES_PER_SEGMENT) / (SEGMENTS - 1))
                      for i in range(SEGMENTS)]
            if any(b - a < FRAMES_PER_SEGMENT for a, b in zip(starts, starts[1:])):
                raise RuntimeError(f"Overlapping segments: {path}")
            sources.append({
                "source": path.relative_to(ROOT).as_posix(),
                "split": "val" if number == 3 else "train",
                "frame_count": count, "fps": fps, "width": width, "height": height,
                "segment_start_frames": starts,
            })
    return sources


def frame_name(source, segment, frame_index):
    stem = Path(source["source"]).stem
    return f"{stem}_segment{segment:03d}_frame{frame_index:06d}.jpg"


def verify(metadata):
    expected = {}
    source_map = {source["source"]: source for source in metadata["sources"]}
    for source in metadata["sources"]:
        starts = source["segment_start_frames"]
        if len(starts) != SEGMENTS:
            raise RuntimeError("Incorrect segment count")
        if any(b - a < FRAMES_PER_SEGMENT for a, b in zip(starts, starts[1:])):
            raise RuntimeError("Overlapping segments")
        for segment, start in enumerate(starts, 1):
            for frame_index in range(start, start + FRAMES_PER_SEGMENT):
                if not 0 <= frame_index < source["frame_count"]:
                    raise RuntimeError("Frame index out of bounds")
                relative = f"{source['split']}/{frame_name(source, segment, frame_index)}"
                expected[relative] = (source["source"], segment, frame_index)
    with (OUTPUT / "manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != len(expected):
        raise RuntimeError("Manifest row count mismatch")
    seen = set()
    for row in rows:
        relative = row["image"]
        actual = (row["source"], int(row["segment"]), int(row["source_frame"]))
        if relative in seen or expected.get(relative) != actual:
            raise RuntimeError(f"Duplicate or incorrect manifest entry: {relative}")
        seen.add(relative)
    counts = {}
    total_bytes = 0
    for split in ("train", "val"):
        files = sorted((OUTPUT / split).iterdir())
        expected_names = {name for name in expected if name.startswith(split + "/")}
        if {f"{split}/{path.name}" for path in files} != expected_names:
            raise RuntimeError(f"Unexpected or missing files in {split}")
        for path in files:
            source = source_map[expected[f"{split}/{path.name}"][0]]
            image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None or image.shape != (source["height"], source["width"], 3):
                raise RuntimeError(f"Unreadable image or incorrect dimensions: {path}")
            total_bytes += path.stat().st_size
        counts[split] = len(files)
        print(f"Verified {split}: {len(files)} readable full-size images", flush=True)
    return {"image_counts": counts, "total_image_bytes": total_bytes,
            "manifest_rows": len(rows), "all_images_decoded": True,
            "consecutive_frames_and_nonoverlap_checked": True}


def extract():
    sources = inspect_sources()
    # Refuse existing output, including incomplete runs, to avoid overwriting data.
    OUTPUT.mkdir(exist_ok=False)
    for split in ("train", "val"):
        (OUTPUT / split).mkdir()
    metadata = {
        "status": "in_progress", "opencv_version": cv2.__version__,
        "segments_per_video": SEGMENTS, "frames_per_segment": FRAMES_PER_SEGMENT,
        "jpeg_quality": JPEG_QUALITY, "frame_index_base": 0,
        "selection": "round(i * (frame_count - 30) / 119), i=0..119",
        "sources": sources,
    }
    write_metadata(metadata)
    with (OUTPUT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "image", "source", "segment", "source_frame", "nominal_time_seconds"
        ])
        writer.writeheader()
        for source in sources:
            capture = cv2.VideoCapture(str(ROOT / source["source"]))
            saved = 0
            current = 0
            try:
                if not capture.isOpened():
                    raise RuntimeError(f"Cannot open {source['source']}")
                for segment, start in enumerate(source["segment_start_frames"], 1):
                    while current < start:
                        if not capture.grab():
                            raise RuntimeError(f"Cannot advance to frame {start}")
                        current += 1
                    for frame_index in range(start, start + FRAMES_PER_SEGMENT):
                        if round(capture.get(cv2.CAP_PROP_POS_FRAMES)) != frame_index:
                            raise RuntimeError(f"Unexpected decoder frame position: {frame_index}")
                        ok, image = capture.read()
                        if not ok or image is None:
                            raise RuntimeError(f"Cannot decode frame {frame_index}")
                        if image.shape != (source["height"], source["width"], 3):
                            raise RuntimeError("Unexpected source frame dimensions")
                        relative = f"{source['split']}/{frame_name(source, segment, frame_index)}"
                        ok, encoded = cv2.imencode(
                            ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                        )
                        if not ok:
                            raise RuntimeError(f"Cannot encode {relative}")
                        encoded.tofile(OUTPUT / relative)
                        writer.writerow({
                            "image": relative, "source": source["source"],
                            "segment": segment, "source_frame": frame_index,
                            "nominal_time_seconds": f"{frame_index / source['fps']:.6f}",
                        })
                        current += 1
                        saved += 1
                    if segment % 30 == 0:
                        print(f"{Path(source['source']).name}: {segment}/120 segments, {saved} images", flush=True)
            finally:
                capture.release()
            handle.flush()
    (OUTPUT / "README.md").write_text(
        "# Shrimp frame dataset\n\n"
        "Train: male/female videos 1 and 2; validation: male/female video 3.\n"
        "Each video contributes 120 evenly distributed, non-overlapping segments; "
        "each segment contains 30 consecutive source frames (approximately one second).\n"
        "Images retain the complete original frame and resolution; JPEG quality is 95.\n"
        "No cropping, resizing, or FPS conversion is performed.\n\n"
        "Filenames use one-based segment numbers and zero-based source frame numbers.\n"
        "manifest.csv records every image and nominal frame/FPS timestamp; "
        "timestamps are approximate, not container presentation timestamps.\n"
        "metadata.json records source properties, selected intervals, and verification.\n\n"
        "Recheck all images: `python extract_frame_dataset.py --verify-only` "
        "from the repository root. Extraction refuses to overwrite an existing dataset.\n",
        encoding="utf-8",
    )
    metadata["verification"] = verify(metadata)
    metadata["status"] = "complete"
    write_metadata(metadata)
    return metadata["verification"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    if args.verify_only:
        result = verify(json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8")))
    else:
        result = extract()
    print(json.dumps(result, ensure_ascii=False), flush=True)
    print(f"Elapsed: {time.monotonic() - started:.1f} seconds", flush=True)
