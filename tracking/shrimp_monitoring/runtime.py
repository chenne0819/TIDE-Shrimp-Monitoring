"""Small adapter shared by the new project's four inference entry points."""

import csv
import json
from pathlib import Path

import cv2
import numpy as np

from .biometrics import summarize_measurements


class MonitoringSession:
    def __init__(self, *, water_classifier=None, estimator=None, water_policy="stop"):
        if water_policy not in {"stop", "report"}:
            raise ValueError("water_policy must be stop or report")
        self.water_classifier = water_classifier
        self.estimator = estimator
        self.water_policy = water_policy
        self.reset()

    @property
    def enabled(self) -> bool:
        return self.water_classifier is not None or self.estimator is not None

    def reset(self) -> None:
        self.water_result = None
        self.stopped = False
        self.frames_seen = 0

    def check_frame(self, frame, frame_index: int, fps: float) -> bool:
        self.frames_seen += 1
        if self.water_classifier is not None and self.water_result is None:
            result = self.water_classifier.predict(frame)
            self.water_result = {
                "frame": frame_index,
                "time_sec": round(frame_index / fps, 3) if np.isfinite(fps) and fps > 0 else 0.0,
                **result,
                "water_policy": self.water_policy,
                "preprocessing": "legacy_bgr_as_rgb_gray28",
            }
            self.stopped = result["water_label"] == "turbid" and self.water_policy == "stop"
            self.water_result["action"] = "stop" if self.stopped else "continue"
            print(f"Water: {result['water_label']} ({result['water_confidence']:.1%}); {self.water_result['action']}")
        return not self.stopped

    def measure(self, polygon, frame_shape) -> dict:
        result = self.estimator.measure(polygon, frame_shape) if self.estimator is not None else {}
        if self.water_result is not None:
            result.update({key: self.water_result[key] for key in ("water_label", "water_confidence")})
        return result

    @staticmethod
    def summarize(records) -> dict:
        return summarize_measurements(records)

    @staticmethod
    def annotate_measurement(image, record: dict, anchor) -> None:
        if "measurement_status" not in record:
            return
        length, width, weight = (record.get(key) for key in ("length_mm", "width_mm", "weight_g"))
        if length is None:
            text = "Size unavailable"
        else:
            text = f"L {length:.1f} mm"
            if width is not None:
                text += f"  W~ {width:.1f} mm"
            if weight is not None:
                text += f"  {weight:.1f} g"
        text_size, baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        x = max(4, min(int(anchor[0]), image.shape[1] - text_size[0] - 8))
        y = max(40, min(int(anchor[1]) + 22, image.shape[0] - baseline - 8))
        cv2.rectangle(image, (x - 3, y - text_size[1] - 4),
                      (x + text_size[0] + 3, y + baseline + 3), (30, 30, 30), -1)
        cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    def annotate_water(self, image) -> None:
        if self.water_result is None:
            return
        label = self.water_result["water_label"]
        confidence = self.water_result["water_confidence"]
        color = (0, 210, 0) if label == "clear" else (0, 100, 255)
        text = f"Water (first frame): {label} {confidence:.0%}"
        anchor = (10, max(20, image.shape[0] - 15))
        text_size, baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(image, (anchor[0] - 4, anchor[1] - text_size[1] - 4),
                      (anchor[0] + text_size[0] + 4, anchor[1] + baseline + 3), (30, 30, 30), -1)
        cv2.putText(image, text, anchor, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)

    def export(self, output_dir) -> dict:
        if not self.enabled:
            return {}
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        status = "skipped_turbid" if self.stopped else ("completed" if self.frames_seen else "no_frames")
        paths = {"status": status, "skipped": self.stopped, "monitoring_status": status}
        if self.water_classifier is not None:
            path = output_dir / "water_quality.csv"
            fields = ["frame", "time_sec", "water_label", "water_confidence", "water_policy", "preprocessing", "action"]
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                if self.water_result is not None:
                    writer.writerow(self.water_result)
            paths["water_quality"] = str(path)
        metadata = {
            "status": status,
            "water_policy": self.water_policy,
            "water_check": "first_frame_only" if self.water_classifier is not None else "disabled",
            "water_model": str(getattr(self.water_classifier, "model_path", "")),
            "biometrics_enabled": self.estimator is not None,
            "biometrics_model_dir": str(getattr(self.estimator, "model_dir", "")),
            "pixels_per_mm": getattr(self.estimator, "pixels_per_mm", None),
            "reference_size": getattr(self.estimator, "reference_size", None),
            "reference_mapping": "uniform_aspect_preserving_fit",
            "weight_mode": getattr(self.estimator, "weight_mode", None),
            "width_source": "obb_proxy" if self.estimator is not None else None,
            "calibration_note": "Original camera calibration; OBB width proxy and new camera geometry need validation.",
        }
        metadata_path = output_dir / "monitoring.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["monitoring_metadata"] = str(metadata_path)
        return paths
