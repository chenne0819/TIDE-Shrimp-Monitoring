import argparse
import sys

from shrimp_monitoring.cli import add_monitoring_arguments, monitoring_from_args

from .modules.config import HBB_CONF, MODEL_HBB_PATH, MODEL_HEAD_TAIL_OBB_PATH
from .modules.track_pipeline import HbbVotingShrimpAnalyzer, WINDOW_FRAMES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track shrimp with head/tail OBB crops, run HBB male_line detection on rectified crops, and vote with a sliding window."
    )
    parser.add_argument("--video", required=True, help="Input video path or camera index.")
    parser.add_argument("--output-root", default="general_track/exports/run_track", help="Output root directory.")
    parser.add_argument("--obb-model", default=MODEL_HEAD_TAIL_OBB_PATH, help="Head/tail OBB model path.")
    parser.add_argument("--hbb-model", default=MODEL_HBB_PATH, help="HBB male_line model path. Default from config.py.")
    parser.add_argument("--tracker", default="bytetrack.yaml", help="Ultralytics tracker YAML. Default: bytetrack.yaml")
    parser.add_argument("--obb-conf", type=float, default=0.2, help="OBB track confidence threshold.")
    parser.add_argument("--obb-iou", type=float, default=0.3, help="OBB track IoU threshold.")
    parser.add_argument("--hbb-conf", type=float, default=HBB_CONF, help=f"HBB male_line threshold. Default: {HBB_CONF}")
    parser.add_argument("--window-frames", type=int, default=WINDOW_FRAMES, help=f"Sliding vote window length. Default: {WINDOW_FRAMES}")
    parser.add_argument("--max-frames", type=int, help="Optional frame limit for testing.")
    parser.add_argument("--preview", action="store_true", help="Show live preview.")
    parser.add_argument("--preview-only", action="store_true", help="Show preview without saving video or CSV files.")
    parser.add_argument("--debug", action="store_true", help="Attach/export rectified shrimp crops with male_line boxes.")
    parser.add_argument("--gt", choices=["Male", "Female", "male", "female", "M", "F"], help="Ground-truth sex label for this run.")
    parser.add_argument("--number-of-shrimps", type=int, help="Ground-truth shrimp count for exported video_info.csv.")
    add_monitoring_arguments(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        paths = HbbVotingShrimpAnalyzer(
            obb_model_path=args.obb_model,
            hbb_model_path=args.hbb_model,
            window_frames=args.window_frames,
            monitoring=monitoring_from_args(args),
        ).run(
            video=args.video,
            output_root=args.output_root,
            tracker=args.tracker,
            obb_conf=args.obb_conf,
            obb_iou=args.obb_iou,
            hbb_conf=args.hbb_conf,
            max_frames=args.max_frames,
            preview=args.preview,
            preview_only=args.preview_only,
            debug=args.debug,
            gt=args.gt,
            number_of_shrimps=args.number_of_shrimps,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    if paths.get("skipped"):
        print("Skipped: the first frame was classified as turbid water.")
    if paths["output_dir"]:
        print(f"Output: {paths['output_dir']}")
    elif not paths.get("skipped"):
        print("Preview complete. No outputs were saved.")


if __name__ == "__main__":
    main()
