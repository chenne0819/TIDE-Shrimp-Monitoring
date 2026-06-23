import numpy as np

from .config import IMGSZ_OBB


def track_obb_frame(obb_model, frame, tracker_config: str | None):
    """Run YOLO OBB tracking for baseline track mode."""
    kwargs = {
        "conf": 0.6,
        "iou": 0.4,
        "imgsz": IMGSZ_OBB,
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
