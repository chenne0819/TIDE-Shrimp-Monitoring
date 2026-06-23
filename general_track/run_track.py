import argparse
import os
import re

from .modules.analyzer import ShrimpSexRatioAnalyzer
from .modules.config import (
    CNN_MALE_LINE_THRESHOLD,
    DEFAULT_KEYFRAMES,
    DEFAULT_SKIP_FRAMES,
    DEFAULT_TIME_WINDOW_SEC,
    DEFAULT_TOTAL_SHRIMP,
    MODEL_CNN_PATH,
    MODEL_HBB_PATH,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run baseline shrimp tracking with YOLO OBB track() and single-frame HBB.")
    parser.add_argument("--video", required=True, help="Input video path or camera index.")
    parser.add_argument("--output-root", default="general_track/exports", help="Output root directory.")
    parser.add_argument("--total-shrimp", type=int, default=DEFAULT_TOTAL_SHRIMP, help="Expected shrimp count when --known-total is used.")
    parser.add_argument("--unknown-total", dest="unknown_total", action="store_true", default=True, help="Create IDs dynamically. Default: enabled.")
    parser.add_argument("--known-total", dest="unknown_total", action="store_false", help="Use --total-shrimp as a fixed count.")
    parser.add_argument("--gt-male", type=int, help="Optional ground-truth male count.")
    parser.add_argument("--gt-female", type=int, help="Optional ground-truth female count.")
    parser.add_argument("--preview", action="store_true", help="Show a live annotated preview.")
    parser.add_argument("--preview-only", action="store_true", help="Only show preview; do not write outputs.")
    parser.add_argument("--grayscale", action="store_true", help="Convert frames to grayscale BGR before OBB/HBB/CNN inference.")
    parser.add_argument("--tracker", default="bytetrack.yaml", help="Optional Ultralytics tracker YAML, such as bytetrack.yaml or botsort.yaml.")
    parser.add_argument("--hbb-model", default=None, help="Optional HBB model path for male_line detection.")
    parser.add_argument("--cnn-model", default=None, help=f"Optional CNN classifier path. Default: {MODEL_CNN_PATH}")
    parser.add_argument(
        "--cnn-threshold",
        type=float,
        default=CNN_MALE_LINE_THRESHOLD,
        help=f"CNN male_line probability threshold. Default: {CNN_MALE_LINE_THRESHOLD}",
    )
    return parser


def _model_label(path: str, role: str) -> str:
    name = os.path.splitext(os.path.basename(path))[0].lower()
    match = re.search(r"yolo\d+[a-z]?", name)
    if match:
        return f"{match.group(0)}-{role}"
    cleaned = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    return f"{cleaned}-{role}" if not cleaned.endswith(f"-{role}") else cleaned


def _grouped_output_root(base_output_root: str, hbb_model_path: str | None) -> str:
    obb_label = "yolo11m-obb"
    hbb_label = _model_label(hbb_model_path or MODEL_HBB_PATH, "hbb")
    return os.path.join(base_output_root, f"{obb_label}_and_{hbb_label}")


def main() -> None:
    args = build_parser().parse_args()
    output_root = _grouped_output_root(args.output_root, args.hbb_model)
    ShrimpSexRatioAnalyzer().run(
        video_path=args.video,
        output_root=output_root,
        total_shrimp=args.total_shrimp,
        unknown_total=args.unknown_total,
        auto_total=False,
        skip_frames=DEFAULT_SKIP_FRAMES,
        max_frames=None,
        keyframes=DEFAULT_KEYFRAMES,
        window_sec=DEFAULT_TIME_WINDOW_SEC,
        truth_csv=None,
        gt_male=args.gt_male,
        gt_female=args.gt_female,
        preview=args.preview,
        preview_only=args.preview_only,
        preview_scale=0.75,
        preview_wait_ms=1,
        mode="track",
        tracker_config=args.tracker or None,
        hbb_model_path=args.hbb_model,
        cnn_model_path=args.cnn_model,
        cnn_threshold=args.cnn_threshold,
        grayscale=args.grayscale,
    )


if __name__ == "__main__":
    main()
