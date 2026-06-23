from pathlib import Path

from crop_shrimp import main


SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_PATH = SCRIPT_DIR / "runs" / "obb" / "traindata_obb_dataset2_yolo11m" / "weights" / "best.pt"
OUTPUT_DIR = SCRIPT_DIR.parent / "HBB" / "shrimp_temporal_crops_from_obb_4"


if __name__ == "__main__":
    main(
        default_model=str(MODEL_PATH),
        default_output_dir=str(OUTPUT_DIR),
        default_direction_mode="stable",
    )
