from argparse import ArgumentParser
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest
import torch
from torchvision import transforms

from shrimp_monitoring import MonitoringSession
from shrimp_monitoring.cli import add_monitoring_arguments, monitoring_from_args
from shrimp_monitoring.water import WaterClassifier, preprocess_water

ROOT = Path(__file__).resolve().parents[1]
WATER_MODEL = ROOT / "model/water/logistic_regression_model.pth"


def test_preprocessing_exactly_matches_original_torchvision():
    frame = np.random.default_rng(7).integers(0, 256, (83, 117, 3), dtype=np.uint8)
    original = transforms.Compose([
        transforms.Resize((28, 28)), transforms.ToTensor(),
        transforms.Normalize((0.5,), (0.5,)),
    ])(Image.fromarray(frame).convert("L")).view(1, 784).numpy()
    np.testing.assert_array_equal(preprocess_water(frame), original)
    # Changing the legacy BGR interpretation would change deployed predictions.
    assert not np.array_equal(preprocess_water(frame), preprocess_water(frame[:, :, ::-1]))


def test_real_checkpoint_logits_confidence_and_class_order():
    classifier = WaterClassifier(WATER_MODEL)
    state = torch.load(WATER_MODEL, map_location="cpu", weights_only=True)
    frame = np.random.default_rng(10).integers(0, 256, (450, 800, 3), dtype=np.uint8)
    logits = torch.nn.functional.linear(torch.from_numpy(preprocess_water(frame)), state["linear.weight"], state["linear.bias"])
    index = int(torch.argmax(logits, dim=1).item())
    result = classifier.predict(frame)
    assert result["water_label"] == ["turbid", "clear"][index]
    assert result["water_confidence"] == pytest.approx(float(torch.softmax(logits, dim=1)[0, index]), abs=1e-7)


def test_path_input_and_bad_checkpoint(tmp_path):
    frame = np.full((50, 60, 3), 124, dtype=np.uint8)
    path = tmp_path / "image.png"
    Image.fromarray(frame).save(path)
    np.testing.assert_array_equal(preprocess_water(path), preprocess_water(frame))
    with pytest.raises(FileNotFoundError, match="Water checkpoint"):
        WaterClassifier(tmp_path / "missing.pth")
    bad = tmp_path / "bad.pth"
    torch.save({"linear.weight": torch.zeros(2, 5), "linear.bias": torch.zeros(2)}, bad)
    with pytest.raises(ValueError, match="Linear"):
        WaterClassifier(bad)


class FixedWater:
    def __init__(self, label):
        self.label, self.calls = label, 0

    def predict(self, frame):
        self.calls += 1
        return {"water_label": self.label, "water_confidence": 0.9}


@pytest.mark.parametrize("label,policy,allowed", [("turbid", "stop", False), ("clear", "stop", True), ("turbid", "report", True)])
def test_check_once_reset_and_export(tmp_path, label, policy, allowed):
    classifier = FixedWater(label)
    session = MonitoringSession(water_classifier=classifier, water_policy=policy)
    frame = np.zeros((40, 60, 3), dtype=np.uint8)
    assert session.check_frame(frame, 0, 30) == allowed
    assert session.check_frame(frame, 1, 30) == allowed
    assert classifier.calls == 1
    paths = session.export(tmp_path)
    assert paths["skipped"] == (not allowed)
    rows = list(csv.DictReader(Path(paths["water_quality"]).open(encoding="utf-8-sig")))
    assert len(rows) == 1 and rows[0]["water_label"] == label
    assert json.loads(Path(paths["monitoring_metadata"]).read_text())["water_check"] == "first_frame_only"
    session.reset()
    assert session.water_result is None and not session.stopped
    session.check_frame(frame, 0, 30)
    assert classifier.calls == 2


def test_disabled_session_does_not_write_or_add_fields(tmp_path):
    session = MonitoringSession()
    assert session.check_frame(np.zeros((10, 10, 3), np.uint8), 0, 30)
    assert session.measure(None, None) == {}
    assert session.export(tmp_path / "unused") == {}
    assert not (tmp_path / "unused").exists()


def test_cli_default_paths_do_not_depend_on_cwd(tmp_path, monkeypatch):
    parser = ArgumentParser()
    add_monitoring_arguments(parser)
    monkeypatch.chdir(tmp_path)
    assert not monitoring_from_args(parser.parse_args([])).enabled
    session = monitoring_from_args(parser.parse_args(["--monitoring"]))
    assert session.enabled and session.estimator is not None and session.water_classifier is not None
    assert session.estimator.weight_mode == "length"
    assert session.water_policy == "stop"


def test_empty_video_has_no_fabricated_water_label(tmp_path):
    session = MonitoringSession(water_classifier=FixedWater("clear"))
    paths = session.export(tmp_path)
    assert paths["status"] == "no_frames"
    assert list(csv.DictReader(Path(paths["water_quality"]).open(encoding="utf-8-sig"))) == []
