import argparse

from shrimp_monitoring.cli import add_monitoring_arguments, monitoring_from_args

from .modules.analyzer import ShrimpSexRatioAnalyzer
from .modules.config import (
    DEFAULT_KEYFRAMES,
    DEFAULT_SKIP_FRAMES,
    DEFAULT_TIME_WINDOW_SEC,
    DEFAULT_TOTAL_SHRIMP,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run shrimp sex-ratio analysis with YOLO OBB predict().")
    parser.add_argument("--video", required=True, help="Input video path or camera index.")
    parser.add_argument("--output-root", default="predict/exports", help="Output root directory.")
    parser.add_argument("--total-shrimp", type=int, default=DEFAULT_TOTAL_SHRIMP, help="Expected shrimp count when --known-total is used.")
    parser.add_argument("--unknown-total", dest="unknown_total", action="store_true", default=True, help="Create IDs dynamically. Default: enabled.")
    parser.add_argument("--known-total", dest="unknown_total", action="store_false", help="Use --total-shrimp as a fixed count.")
    parser.add_argument("--auto-total", action="store_true", help="Estimate total shrimp count with an OBB-only prescan.")
    parser.add_argument("--auto-total-percentile", type=float, default=90.0, help="Percentile of per-frame OBB counts used for --auto-total.")
    parser.add_argument("--auto-total-skip-frames", type=int, help="Frame interval for the OBB-only auto-total prescan.")
    parser.add_argument("--auto-total-max-frames", type=int, help="Maximum sampled frames used by the auto-total prescan.")
    parser.add_argument("--skip-frames", type=int, default=DEFAULT_SKIP_FRAMES, help="Analyze every N frames.")
    parser.add_argument("--max-frames", type=int, help="Maximum source frames to read.")
    parser.add_argument("--keyframes", type=int, default=DEFAULT_KEYFRAMES, help="Number of evidence keyframes to export.")
    parser.add_argument("--window-sec", type=int, default=DEFAULT_TIME_WINDOW_SEC, help="Seconds per temporal summary window.")
    parser.add_argument("--truth-csv", help="Optional CSV with columns Shrimp_ID,True_Label.")
    parser.add_argument("--gt-male", type=int, help="Optional ground-truth male count.")
    parser.add_argument("--gt-female", type=int, help="Optional ground-truth female count.")
    parser.add_argument("--preview", action="store_true", help="Show a live annotated preview.")
    parser.add_argument("--preview-only", action="store_true", help="Only show preview; do not write outputs.")
    parser.add_argument("--preview-scale", type=float, default=0.75, help="Scale factor for the live preview window.")
    parser.add_argument("--preview-wait-ms", type=int, default=1, help="Delay in milliseconds for each preview frame.")
    parser.add_argument("--obb-model", help="Override the new project's OBB detector weights.")
    parser.add_argument("--hbb-model", help="Override the new project's male-line HBB weights.")
    add_monitoring_arguments(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    ShrimpSexRatioAnalyzer(
        monitoring=monitoring_from_args(args),
        obb_model_path=args.obb_model,
        hbb_model_path=args.hbb_model,
    ).run(
        video_path=args.video,
        output_root=args.output_root,
        total_shrimp=args.total_shrimp,
        unknown_total=args.unknown_total,
        auto_total=args.auto_total,
        auto_total_percentile=args.auto_total_percentile,
        auto_total_skip_frames=args.auto_total_skip_frames,
        auto_total_max_frames=args.auto_total_max_frames,
        skip_frames=args.skip_frames,
        max_frames=args.max_frames,
        keyframes=args.keyframes,
        window_sec=args.window_sec,
        truth_csv=args.truth_csv,
        gt_male=args.gt_male,
        gt_female=args.gt_female,
        preview=args.preview,
        preview_only=args.preview_only,
        preview_scale=args.preview_scale,
        preview_wait_ms=args.preview_wait_ms,
        mode="predict",
    )


if __name__ == "__main__":
    main()
