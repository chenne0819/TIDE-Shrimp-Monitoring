import numpy as np


def track_obb_frame(obb_model, frame, tracker_config: str | None, *, conf=0.6, iou=0.3, imgsz=640):
    """Run YOLO OBB tracking for baseline track mode."""
    kwargs = {
        "conf": conf,
        "iou": iou,
        "imgsz": imgsz,
        "verbose": False,
        "persist": True,
    }
    if tracker_config:
        kwargs["tracker"] = tracker_config
    return obb_model.track(frame, **kwargs)[0]


def extract_obb_track_id(obb) -> int | None:
    track_id = getattr(obb, "id", None)
    if track_id is None:
        return None
    try:
        value = track_id.cpu().numpy() if hasattr(track_id, "cpu") else track_id
        arr = np.asarray(value).reshape(-1)
        if arr.size == 0:
            return None
        return int(arr[0])
    except (TypeError, ValueError, AttributeError, IndexError):
        return None


REQUIRED_HEAD_TAIL_OBB_CLASSES = {"shrimp", "shrimp_head", "shrimp_tail"}


def validate_head_tail_obb_model(model) -> None:
    names = set(model.names.values())
    missing = REQUIRED_HEAD_TAIL_OBB_CLASSES - names
    if missing:
        raise ValueError(f"OBB model is missing classes: {sorted(missing)}; got {sorted(names)}")


def obb_rows(result) -> list[dict]:
    rows = []
    if result.obb is None:
        return rows
    for obb in result.obb:
        class_index = int(obb.cls.cpu().numpy()[0])
        polygon = obb.xyxyxyxy.cpu().numpy()[0].astype(np.float32)
        rows.append(
            {
                "class_name": result.names[class_index],
                "polygon": polygon,
                "center": tuple(np.mean(polygon, axis=0).tolist()),
                "confidence": float(obb.conf.cpu().numpy()[0]),
                "track_id": extract_obb_track_id(obb),
            }
        )
    return rows


def load_obb_model(model_path):
    from ultralytics import YOLO
    model = YOLO(str(model_path))
    if model.task != "obb":
        raise ValueError(f"Expected an OBB model, got task: {model.task}")
    validate_head_tail_obb_model(model)
    return model


def detect_obb_rows(model, frame, tracker, *, conf, iou, imgsz):
    return obb_rows(track_obb_frame(model, frame, tracker or "bytetrack.yaml", conf=conf, iou=iou, imgsz=imgsz))


def reset_obb_tracking(model):
    predictor = getattr(model, "predictor", None)
    for tracker in getattr(predictor, "trackers", ()):
        tracker.reset()
