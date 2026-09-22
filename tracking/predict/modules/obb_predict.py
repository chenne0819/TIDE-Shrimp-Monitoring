from .config import IMGSZ_OBB


def predict_obb_frame(obb_model, frame):
    """Run single-frame YOLO OBB prediction for shrimp body detections."""
    return obb_model(
        frame,
        conf=0.6,
        iou=0.4,
        imgsz=IMGSZ_OBB,
        verbose=False,
    )[0]
