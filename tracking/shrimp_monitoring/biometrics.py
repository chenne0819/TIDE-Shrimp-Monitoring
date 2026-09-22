"""Size calibration and weight regressions retained from ShrimpVisionRT.

Inputs are ordered OBB corners in the source frame, before drawing or cropping.
Pixel measurements use an aspect-preserving fit into the configured reference
canvas (800 x 450 by default), where the old code used 2.5 pixels/mm. One uniform
scale preserves lengths for every OBB rotation. For a different aspect ratio,
this is a reference-canvas adaptation, not exact legacy geometric parity or a
camera calibration. Rescaling cannot calibrate a different camera, field of
view or shrimp depth.

The new detector's short OBB edge is a width *proxy*: the original width model
was trained for measurements from a separate segmentation detector. Accordingly,
the default weight calculation preserves the old length-only fallback. Every
successful measurement is explicitly marked as an estimate with a width proxy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

import joblib
import numpy as np


MODEL_FILES = {
    "length": ("final_linear_model_length.pkl", 1),
    "width": ("final_linear_model_width.pkl", 1),
    "weight_length": ("polynomial_regression_model_degree3.pkl", 1),
    "weight_length_width": ("multi_feature_model.pkl", 2),
}


class BiometricsEstimator:
    """Load the four original regressions once and measure new OBB detections."""

    def __init__(
        self,
        model_dir: str | Path,
        pixels_per_mm: float = 2.5,
        weight_mode: str = "length",
        reference_size: tuple[int, int] = (800, 450),
    ) -> None:
        self.model_dir = Path(model_dir)
        self.pixels_per_mm = float(pixels_per_mm)
        if not np.isfinite(self.pixels_per_mm) or self.pixels_per_mm <= 0:
            raise ValueError("pixels_per_mm must be a finite positive number")
        if weight_mode not in {"length", "length-width"}:
            raise ValueError("weight_mode must be 'length' or 'length-width'")
        self.weight_mode = weight_mode
        try:
            reference = np.asarray(reference_size, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("reference_size must contain positive (width, height)") from exc
        if reference.shape != (2,) or not np.all(np.isfinite(reference)) or np.any(reference <= 0):
            raise ValueError("reference_size must contain positive (width, height)")
        self.reference_size = tuple(float(value) for value in reference)
        self.models = {}
        for name, (filename, features) in MODEL_FILES.items():
            path = self.model_dir / filename
            if not path.is_file():
                raise FileNotFoundError(f"Required ShrimpVisionRT biometrics model is missing: {path}")
            try:
                model = joblib.load(path)
                if not callable(getattr(model, "predict", None)):
                    raise ValueError("model has no predict method")
                if getattr(model, "n_features_in_", None) != features:
                    raise ValueError(f"model must accept {features} input feature(s)")
                # Check compatibility immediately, rather than failing inside a video loop.
                sample = [[120.0, 20.0]] if features == 2 else [[120.0]]
                self._predict_scalar(model, sample)
            except Exception as exc:
                raise ValueError(f"Cannot load compatible biometrics model {path}: {exc}") from exc
            self.models[name] = model

    @staticmethod
    def _predict_scalar(model, features) -> float:
        prediction = np.asarray(model.predict(np.asarray(features, dtype=float)), dtype=float)
        if prediction.size != 1 or not np.isfinite(prediction).all():
            raise ValueError("regression must return one finite prediction")
        return float(prediction.reshape(-1)[0])

    def _empty(self, status: str) -> dict:
        return {
            "length_px": None,
            "width_px": None,
            "length_mm": None,
            "width_mm": None,
            "weight_g": None,
            "width_source": "obb_proxy",
            "weight_method": self.weight_mode,
            "measurement_status": status,
        }

    def measure(self, polygon, frame_shape) -> dict:
        """Return reference-frame pixels, calibrated mm, g, and provenance.

        ``polygon`` accepts four cyclic corners as (4, 2), or eight flattened
        coordinates. ``frame_shape`` is NumPy's (height, width[, channels]).
        Reference mapping uses min(reference_width/frame_width,
        reference_height/frame_height), as an aspect-preserving letterbox fit.
        Padding translation is omitted because it does not affect edge lengths.
        Invalid geometry or length returns null measurements. A bad width proxy
        is independent of length-only weight; a bad weight retains valid sizes.
        """
        result = self._empty("invalid_geometry")
        try:
            points = np.asarray(polygon, dtype=float)
            if points.shape == (8,):
                points = points.reshape(4, 2)
            dimensions = np.asarray(frame_shape, dtype=float)
            if (
                points.shape != (4, 2)
                or dimensions.ndim != 1
                or dimensions.size < 2
                or not np.all(np.isfinite(points))
                or not np.all(np.isfinite(dimensions[:2]))
                or np.any(dimensions[:2] <= 0)
            ):
                return result
            frame_h, frame_w = dimensions[:2]
            reference_w, reference_h = self.reference_size
            # Preserve geometry: independent x/y scaling would make a shrimp's
            # inferred size vary solely when it rotates in a portrait video.
            geometry_scale = min(reference_w / frame_w, reference_h / frame_h)
            scaled = points * geometry_scale
            # The original poly_label uses edges corner 0 -> 1 and 0 -> 3.
            # Retain this definition rather than replacing it with an AABB.
            edges = np.linalg.norm(scaled[[1, 3]] - scaled[0], axis=1)
            area = 0.5 * abs(
                np.dot(scaled[:, 0], np.roll(scaled[:, 1], -1))
                - np.dot(scaled[:, 1], np.roll(scaled[:, 0], -1))
            )
            if not np.all(np.isfinite(edges)) or np.any(edges <= 0) or not np.isfinite(area) or area <= 0:
                return result
            length_px, width_px = float(max(edges)), float(min(edges))
        except (TypeError, ValueError, IndexError, OverflowError):
            return result

        try:
            # The old code rounds calibrated dimensions BEFORE predicting weight.
            length_mm = round(self._predict_scalar(self.models["length"], [[length_px / self.pixels_per_mm]]), 1)
            if length_mm <= 0:
                return self._empty("invalid_prediction")
        except (TypeError, ValueError, IndexError, OverflowError, ArithmeticError):
            return self._empty("invalid_prediction")

        result.update(length_px=length_px, width_px=width_px, length_mm=length_mm)
        width_mm = None
        try:
            predicted_width = round(self._predict_scalar(self.models["width"], [[width_px / self.pixels_per_mm]]), 1)
            if predicted_width > 0:
                width_mm = predicted_width
        except (TypeError, ValueError, IndexError, OverflowError, ArithmeticError):
            pass
        result.update(
            width_mm=width_mm,
            measurement_status="estimated_obb_width_proxy" if width_mm is not None else "estimated_width_unavailable",
        )
        # Explicit dual-feature mode cannot use an unavailable width. Do not
        # silently switch the requested method or send negative width to it.
        if self.weight_mode == "length-width" and width_mm is None:
            return result
        try:
            if self.weight_mode == "length-width":
                weight_g = self._predict_scalar(self.models["weight_length_width"], [[length_mm, width_mm]])
            else:
                weight_g = self._predict_scalar(self.models["weight_length"], [[length_mm]])
            weight_g = round(weight_g, 1)
            if weight_g <= 0:
                result["measurement_status"] = "invalid_weight"
                return result
        except (TypeError, ValueError, IndexError, OverflowError, ArithmeticError):
            result["measurement_status"] = "invalid_weight"
            return result

        result["weight_g"] = weight_g
        return result


def summarize_measurements(records: Iterable[Mapping]) -> dict:
    """Independent valid-value means; sample count is valid length observations.

    Records from disabled monitoring have no measurement_status; return no new
    columns in that case to preserve the project's existing CSV schema.
    """
    fields = ("length_mm", "width_mm", "weight_g")
    samples = {field: [] for field in fields}
    monitoring_present = False
    for record in records:
        if "measurement_status" not in record:
            continue
        monitoring_present = True
        for field in fields:
            try:
                value = float(record.get(field))
            except (TypeError, ValueError, OverflowError):
                continue
            if np.isfinite(value) and value > 0:
                samples[field].append(value)
    if not monitoring_present:
        return {}
    return {
        "measurement_samples": len(samples["length_mm"]),
        **{
            f"mean_{field}": round(float(np.mean(values)), 1) if values else None
            for field, values in samples.items()
        },
    }
