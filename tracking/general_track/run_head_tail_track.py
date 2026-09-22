import argparse
import sys

from shrimp_monitoring.cli import add_monitoring_arguments, monitoring_from_args

from .modules.config import (
    MODEL_HEAD_TAIL_OBB_PATH,
    MODEL_SEX_CLASSIFIER_PATH,
)
from .modules.head_tail_pipeline import HeadTailShrimpAnalyzer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track OBB shrimp, orient by head/tail, and classify female/male.")
    parser.add_argument("--video", required=True, help="Input video path or camera index.")
    parser.add_argument("--output-root", default="general_track/exports/head_tail_cls")
    parser.add_argument("--obb-model", default=MODEL_HEAD_TAIL_OBB_PATH)
    parser.add_argument(
        "--classifier-model",
        "--cnn-model",
        dest="classifier_model",
        default=MODEL_SEX_CLASSIFIER_PATH,
        help="ResNet or YOLO classification checkpoint. Default: supplied ResNet18.",
    )
    parser.add_argument("--tracker", default="bytetrack.yaml", help="Ultralytics ByteTrack config. Default: bytetrack.yaml")
    parser.add_argument("--conf", type=float, default=0.5)
    parser.add_argument("--iou", type=float, default=0.3)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--preview-only", action="store_true", help="Show preview without saving video, CSV files, or crops.")
    parser.add_argument("--debug", action="store_true", help="Start with abdomen debug tiles attached to the main preview; press D to toggle.")
    parser.add_argument("--save-crops", action="store_true", help="Save the exact abdomen crops sent to the sex classifier.")
    add_monitoring_arguments(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        analyzer = HeadTailShrimpAnalyzer(
            args.obb_model, args.classifier_model, monitoring=monitoring_from_args(args)
        )
        paths = analyzer.run(
            video=args.video,
            output_root=args.output_root,
            tracker=args.tracker,
            conf=args.conf,
            iou=args.iou,
            max_frames=args.max_frames,
            preview=args.preview,
            preview_only=args.preview_only,
            debug=args.debug,
            save_crops=args.save_crops,
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
