from __future__ import annotations

import argparse

import ultralytics
from ultralytics import YOLO


DATA_YAML = "data-temporal.yaml"
MODEL_PATH = "../../yolo11m-hbb.pt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train 3-frame 9-channel temporal HBB model.")
    parser.add_argument("--data", default=DATA_YAML, help=f"Dataset yaml. Default: {DATA_YAML}")
    parser.add_argument("--model", default=MODEL_PATH, help=f"Base model. Default: {MODEL_PATH}")
    parser.add_argument(
        "--name",
        default="traindata_temporal_hbb_3frames_9ch-1",
        help="Run name. Default: traindata_temporal_hbb_3frames_9ch_temporal_tuned",
    )
    parser.add_argument("--epochs", type=int, default=200, help="Epochs. Default: 200")
    parser.add_argument("--imgsz", type=int, default=416, help="Image size. Default: 512")
    parser.add_argument("--batch", type=int, default=8, help="Batch size. Default: 8")
    parser.add_argument("--device", default="0", help="CUDA device. Default: 0")
    parser.add_argument("--exist-ok", action="store_true", help="Allow overwriting/reusing the run name.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    ultralytics.checks()
    model = YOLO(args.model)

    print("Starting temporal 3-frame 9-channel HBB training...")
    print(f"data={args.data}")
    print(f"model={args.model}")
    print(f"name={args.name}")
    print(f"imgsz={args.imgsz}")

    model.train(
        data=args.data,
        device=args.device,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        name=args.name,
        exist_ok=args.exist_ok,
        lr0=0.003,
        lrf=0.01,
        box=9.0,
        cls=0.3,
        dfl=2.0,
        patience=35,
        degrees=5.0,
        translate=0.03,
        scale=0.10,
    )

    print("Temporal 3-frame 9-channel HBB training complete.")


if __name__ == "__main__":
    main()
