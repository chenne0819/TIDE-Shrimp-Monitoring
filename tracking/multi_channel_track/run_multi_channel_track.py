import argparse
import os

from .modules.analyzer import ShrimpSexRatioAnalyzer
from .modules.config import (
    DEFAULT_KEYFRAMES,
    DEFAULT_SKIP_FRAMES,
    DEFAULT_TIME_WINDOW_SEC,
    DEFAULT_TOTAL_SHRIMP,
    HBB_TEMPORAL_STEP_FRAMES,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run shrimp tracking with 3-frame 9-channel temporal HBB.")
    parser.add_argument("--video", required=True, help="Input video path or camera index.")
    parser.add_argument("--output-root", default="multi_channel_track/exports", help="Output root directory.")
    parser.add_argument("--total-shrimp", type=int, default=DEFAULT_TOTAL_SHRIMP, help="Expected shrimp count when --known-total is used.")
    parser.add_argument("--unknown-total", dest="unknown_total", action="store_true", default=True, help="Create IDs dynamically. Default: enabled.")
    parser.add_argument("--known-total", dest="unknown_total", action="store_false", help="Use --total-shrimp as a fixed count.")
    parser.add_argument("--gt-male", type=int, help="Optional ground-truth male count.")
    parser.add_argument("--gt-female", type=int, help="Optional ground-truth female count.")
    parser.add_argument("--preview", action="store_true", help="Show a live annotated preview.")
    parser.add_argument("--preview-only", action="store_true", help="Only show preview; do not write outputs.")
    parser.add_argument("--tracker", default="bytetrack.yaml", help="Optional Ultralytics tracker YAML, such as bytetrack.yaml or botsort.yaml.")
    parser.add_argument("--hbb-temporal-step-frames", type=int, default=HBB_TEMPORAL_STEP_FRAMES, help="Frame interval used by temporal HBB stacks.")
    return parser


def _grouped_output_root(base_output_root: str, step_frames: int) -> str:
    return os.path.join(base_output_root, f"{int(step_frames)}FPS")


def main() -> None:
    args = build_parser().parse_args()
    output_root = _grouped_output_root(args.output_root, args.hbb_temporal_step_frames)
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
        hbb_temporal_step_frames=args.hbb_temporal_step_frames,
    )


if __name__ == "__main__":
    main()
