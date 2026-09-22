"""Regression parity against the actual original (not synthetic deployed) models."""

from pathlib import Path
import shutil

import joblib
import numpy as np
import pytest

from shrimp_monitoring.biometrics import BiometricsEstimator, MODEL_FILES, summarize_measurements


MODEL_DIR = Path(__file__).resolve().parents[1] / "model" / "biometrics"
POLYGON = np.array([[100, 100], [400, 100], [400, 150], [100, 150]], dtype=float)


@pytest.fixture(scope="module")
def estimator():
    return BiometricsEstimator(MODEL_DIR)


@pytest.mark.parametrize("weight_mode", ["length", "length-width"])
def test_predictions_match_original_feature_order_scale_and_rounding(weight_mode):
    estimator = BiometricsEstimator(MODEL_DIR, weight_mode=weight_mode)
    result = estimator.measure(POLYGON, (450, 800, 3))
    length = round(float(joblib.load(MODEL_DIR / MODEL_FILES["length"][0]).predict([[300 / 25 * 10]])[0]), 1)
    width = round(float(joblib.load(MODEL_DIR / MODEL_FILES["width"][0]).predict([[50 / 25 * 10]])[0]), 1)
    key = "weight_length_width" if weight_mode == "length-width" else "weight_length"
    features = [[length, width]] if weight_mode == "length-width" else [[length]]
    weight = round(float(joblib.load(MODEL_DIR / MODEL_FILES[key][0]).predict(features)[0]), 1)
    assert result == {
        "length_px": 300.0, "width_px": 50.0,
        "length_mm": length, "width_mm": width, "weight_g": weight,
        "width_source": "obb_proxy", "weight_method": weight_mode,
        "measurement_status": "estimated_obb_width_proxy",
    }


def test_resizing_video_keeps_physical_prediction(estimator):
    expected = estimator.measure(POLYGON, (450, 800))
    assert estimator.measure(POLYGON * 2.4, (1080, 1920, 3)) == expected


@pytest.mark.parametrize("angle_degrees", [0, 17, 45, 90, 135])
def test_portrait_frame_uses_uniform_fit_and_is_rotation_invariant(estimator, angle_degrees):
    centered = np.array([[-300, -50], [300, -50], [300, 50], [-300, 50]], dtype=float)
    angle = np.deg2rad(angle_degrees)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    rotated = centered @ rotation.T + [495, 699]
    actual = estimator.measure(rotated, (1398, 990, 3))
    expected = estimator.measure(centered + [495, 699], (1398, 990, 3))
    scale = min(800 / 990, 450 / 1398)
    assert actual["length_px"] == pytest.approx(600 * scale)
    assert actual["width_px"] == pytest.approx(100 * scale)
    for field in ("length_mm", "width_mm", "weight_g"):
        assert actual[field] == expected[field]
        assert actual[field] is not None


def test_rotated_obb_uses_edge_length_and_not_axis_aligned_bounds(estimator):
    angle = np.deg2rad(32)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    rotated = (POLYGON - [250, 125]) @ rotation.T + [400, 225]
    actual = estimator.measure(rotated, (450, 800))
    expected = estimator.measure(POLYGON, (450, 800))
    assert actual["length_px"] == pytest.approx(300)
    assert actual["width_px"] == pytest.approx(50)
    for field in ("length_mm", "width_mm", "weight_g"):
        assert actual[field] == expected[field]


def test_custom_calibration_applied_before_regression():
    estimator = BiometricsEstimator(MODEL_DIR, pixels_per_mm=5.0)
    result = estimator.measure(POLYGON * 2, (450, 800))
    baseline = BiometricsEstimator(MODEL_DIR).measure(POLYGON, (450, 800))
    assert [result[k] for k in ("length_mm", "width_mm", "weight_g")] == [baseline[k] for k in ("length_mm", "width_mm", "weight_g")]


@pytest.mark.parametrize("polygon, shape", [
    (np.full((4, 2), np.nan), (450, 800)),
    (np.full((4, 2), np.inf), (450, 800)),
    (np.zeros((4, 2)), (450, 800)),
    ([[0, 0], [5, 0], [10, 0], [15, 0]], (450, 800)),
    ([[0, 0], [1, 1]], (450, 800)),
    (POLYGON, (0, 800)),
    (POLYGON, (450, np.nan)),
    (None, None),
])
def test_invalid_geometry_returns_json_safe_null_measurements(estimator, polygon, shape):
    result = estimator.measure(polygon, shape)
    assert result["measurement_status"] == "invalid_geometry"
    assert all(result[k] is None for k in ("length_px", "width_px", "length_mm", "width_mm", "weight_g"))


def test_nonphysical_regression_output_is_not_reported_as_real_measurement(estimator):
    tiny = np.array([[0, 0], [3, 0], [3, 1], [0, 1]])
    result = estimator.measure(tiny, (450, 800))
    assert result["measurement_status"] == "invalid_weight"
    assert result["length_mm"] > 0
    assert result["width_mm"] is None
    assert result["weight_g"] is None


def test_unavailable_width_does_not_discard_length_only_prediction(estimator):
    narrow = POLYGON.copy()
    narrow[2:, 1] = 101
    result = estimator.measure(narrow, (450, 800))
    baseline = estimator.measure(POLYGON, (450, 800))
    assert result["width_mm"] is None
    assert result["measurement_status"] == "estimated_width_unavailable"
    assert result["length_mm"] == baseline["length_mm"]
    assert result["weight_g"] == baseline["weight_g"]


def test_dual_feature_mode_does_not_silently_substitute_missing_width():
    narrow = POLYGON.copy()
    narrow[2:, 1] = 101
    result = BiometricsEstimator(MODEL_DIR, weight_mode="length-width").measure(narrow, (450, 800))
    assert result["length_mm"] > 0
    assert result["width_mm"] is None
    assert result["weight_g"] is None
    assert result["weight_method"] == "length-width"
    assert result["measurement_status"] == "estimated_width_unavailable"


@pytest.mark.parametrize("bad_value", [-1.0, np.nan, np.inf])
def test_invalid_weight_preserves_valid_dimensions(estimator, monkeypatch, bad_value):
    class InvalidWeight:
        def predict(self, features):
            return [bad_value]

    monkeypatch.setitem(estimator.models, "weight_length", InvalidWeight())
    result = estimator.measure(POLYGON, (450, 800))
    assert result["length_mm"] > 0
    assert result["width_mm"] > 0
    assert result["weight_g"] is None
    assert result["measurement_status"] == "invalid_weight"


def test_invalid_length_discards_all_measurements(estimator, monkeypatch):
    class InvalidLength:
        def predict(self, features):
            return [-1]

    monkeypatch.setitem(estimator.models, "length", InvalidLength())
    result = estimator.measure(POLYGON, (450, 800))
    assert result["measurement_status"] == "invalid_prediction"
    assert all(result[key] is None for key in ("length_px", "width_px", "length_mm", "width_mm", "weight_g"))


def test_flattened_input(estimator):
    assert estimator.measure(POLYGON.ravel(), (450, 800)) == estimator.measure(POLYGON, (450, 800))


@pytest.mark.parametrize("kwargs", [
    {"pixels_per_mm": 0}, {"pixels_per_mm": -1}, {"pixels_per_mm": np.nan},
    {"reference_size": (0, 450)}, {"reference_size": (800,)},
    {"weight_mode": "unknown"},
])
def test_bad_configuration_is_a_startup_error(kwargs):
    with pytest.raises(ValueError):
        BiometricsEstimator(MODEL_DIR, **kwargs)


def test_missing_model_is_an_explicit_startup_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="final_linear_model_length.pkl"):
        BiometricsEstimator(tmp_path)


def test_wrong_feature_model_is_an_explicit_startup_error(tmp_path):
    for filename, _ in MODEL_FILES.values():
        shutil.copyfile(MODEL_DIR / filename, tmp_path / filename)
    shutil.copyfile(MODEL_DIR / MODEL_FILES["weight_length_width"][0], tmp_path / MODEL_FILES["length"][0])
    with pytest.raises(ValueError, match="must accept 1 input feature"):
        BiometricsEstimator(tmp_path)


def test_summary_uses_only_valid_observations(estimator):
    valid = estimator.measure(POLYGON, (450, 800))
    invalid = estimator.measure(np.zeros((4, 2)), (450, 800))
    summary = summarize_measurements([valid, invalid, dict(valid)])
    assert summary == {
        "measurement_samples": 2,
        "mean_length_mm": valid["length_mm"],
        "mean_width_mm": valid["width_mm"],
        "mean_weight_g": valid["weight_g"],
    }
    assert summarize_measurements([invalid]) == {
        "measurement_samples": 0,
        "mean_length_mm": None, "mean_width_mm": None, "mean_weight_g": None,
    }


def test_summary_preserves_disabled_output_schema():
    assert summarize_measurements([]) == {}
    assert summarize_measurements([{"shrimp_id": 1}, {"water_label": "clear"}]) == {}


def test_summary_averages_each_available_dimension_independently():
    rows = [
        {"measurement_status": "estimated_obb_width_proxy", "length_mm": 120, "width_mm": 20, "weight_g": 10},
        {"measurement_status": "estimated_width_unavailable", "length_mm": 140, "width_mm": None, "weight_g": 20},
        {"measurement_status": "invalid_weight", "length_mm": 160, "width_mm": 30, "weight_g": None},
        {"measurement_status": "invalid_geometry", "length_mm": None, "width_mm": None, "weight_g": None},
    ]
    assert summarize_measurements(rows) == {
        "measurement_samples": 3,
        "mean_length_mm": 140.0,
        "mean_width_mm": 25.0,
        "mean_weight_g": 15.0,
    }
