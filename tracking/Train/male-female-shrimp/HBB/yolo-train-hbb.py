from __future__ import annotations

import argparse
from pathlib import Path

import ultralytics
from ultralytics import YOLO


DATA_YAML = "data.yaml"
DATASET_ROOT = "shrimp_HBB_dataset_2"
MODEL_PATH = "../../yolo11m-hbb.pt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train HBB male_line model with custom Albumentations.")
    parser.add_argument("--data", default=DATA_YAML, help=f"Dataset yaml. Default: {DATA_YAML}")
    parser.add_argument("--dataset", default=DATASET_ROOT, help=f"YOLO dataset folder. Default: {DATASET_ROOT}")
    parser.add_argument("--model", default=MODEL_PATH, help=f"Base YOLO model. Default: {MODEL_PATH}")
    parser.add_argument("--name", default="traindata_hbb_dataset3_yolo11m", help="Ultralytics run name.")
    parser.add_argument("--epochs", type=int, default=200, help="Training epochs. Default: 200")
    parser.add_argument("--imgsz", type=int, default=416, help="Image size. Default: 416")
    parser.add_argument("--batch", type=int, default=16, help="Batch size. Default: 16")
    parser.add_argument("--device", default="0", help="CUDA device. Default: 0")
    parser.add_argument("--exist-ok", default=True, help="Allow reusing the same YOLO run name.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ultralytics.checks()

    dataset_root = Path(args.dataset)
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_root}")

    model = YOLO(args.model)
    print("Starting HBB male_line training with custom Albumentations transforms.")

    model.train(
        data=args.data,
        device=args.device,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        name=args.name,
        cache='disk',
        exist_ok=args.exist_ok,
        hsv_s=1.0,
        hsv_v=0.5,
        degrees=180,
        shear=5,
        perspective=0.0005,
        flipud=0.5,
        bgr=0.5,
        mixup=0.5,
        cutmix=0.5,
    )

    print("HBB training complete.")


if __name__ == "__main__":
    main()
