"""Exercise predict and temporal tracking with controlled detector outputs.

Water checkpoints generated here are synthetic test fixtures. The shared water
preprocessing/classifier, measurement regressions, assignment, temporal input,
recording, and CSV writers run normally.
"""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pandas as pd
import pytest
import torch

from shrimp_monitoring import MonitoringSession
from shrimp_monitoring.biometrics import BiometricsEstimator
from shrimp_monitoring.water import WaterClassifier


ROOT = Path(__file__).resolve().parents[1]
MODES = ("predict", "multi_channel_track")


class Capture:
    def __init__(self, frames, live=False):
        self.frames = frames
        self.live = live
        self.position = 0
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        return 30.0 if prop == cv2.CAP_PROP_FPS else (0 if self.live else len(self.frames))

    def set(self, prop, value):
        assert prop == cv2.CAP_PROP_POS_FRAMES
        self.position = int(value)
        return True

    def read(self):
        if self.position >= len(self.frames):
            return False, None
        frame = self.frames[self.position].copy()
        self.position += 1
        return True, frame

    def release(self):
        self.released = True


class Detector:
    def __init__(self, kind):
        self.kind = kind
        self.calls = []

    def __call__(self, inputs, **kwargs):
        return self._infer("predict", inputs, kwargs)

    def track(self, inputs, **kwargs):
        return self._infer("track", inputs, kwargs)

    def _infer(self, method, inputs, kwargs):
        self.calls.append((method, inputs, kwargs))
        if self.kind == "obb":
            # Source-frame geometry is deliberately rotated and fractional.
            obb = SimpleNamespace(
                cls=torch.tensor([0]), conf=torch.tensor([0.95]),
                xywhr=torch.tensor([[400.25, 225.75, 250.5, 65.25, 0.31]]),
                id=torch.tensor([77]),
            )
            return [SimpleNamespace(obb=[obb], names={0: "shrimp"})]
        return [SimpleNamespace(boxes=[], names={0: "male_line"}) for _ in inputs]


@pytest.fixture
def estimator():
    return BiometricsEstimator(ROOT / "model/biometrics")


def water_checkpoint(tmp_path, label):
    # Zero logits plus a chosen bias make deterministic clear/turbid fixtures.
    path = tmp_path / f"synthetic_test_{label}.pth"
    torch.save({
        "linear.weight": torch.zeros((2, 784)),
        "linear.bias": torch.tensor([5.0, -5.0] if label == "turbid" else [-5.0, 5.0]),
    }, path)
    return WaterClassifier(path)


def prepare(monkeypatch, mode, session, frames, live=False):
    module = importlib.import_module(f"{mode}.modules.analyzer")
    cap = Capture(frames, live)
    obb, hbb = Detector("obb"), Detector("hbb")
    requested_paths = []

    def load(path):
        requested_paths.append(path)
        return obb if path == "test-obb.pt" else hbb

    monkeypatch.setattr(module, "YOLO", load)
    monkeypatch.setattr(module.cv2, "VideoCapture", lambda _: cap)
    # Charts and physical video encoding are independent of this integration;
    # retain ReportWriter's actual CSV serialization for assertions below.
    for name in dir(module.ReportWriter):
        if name.startswith("_plot_"):
            monkeypatch.setattr(module.ReportWriter, name, lambda *a, **kw: "")
    monkeypatch.setattr(module.ShrimpSexRatioAnalyzer, "_write_result_video_frame", staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(module.ShrimpSexRatioAnalyzer, "_show_preview", staticmethod(lambda *a, **kw: False))
    monkeypatch.setattr(module.cv2, "destroyAllWindows", lambda: None)
    analyzer = module.ShrimpSexRatioAnalyzer(session, "test-obb.pt", "test-hbb.pt")
    return analyzer, cap, obb, hbb, requested_paths


def run_kwargs(mode, tmp_path):
    return dict(video_path="fixture.mp4", output_root=str(tmp_path / "out"),
                unknown_total=True, skip_frames=2, keyframes=0,
                mode="predict" if mode == "predict" else "track",
                tracker_config="bytetrack.yaml")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("preview_only", (False, True))
def test_turbid_stops_before_prescan_and_detection(monkeypatch, tmp_path, mode, preview_only):
    session = MonitoringSession(water_classifier=water_checkpoint(tmp_path, "turbid"))
    frames = [np.full((450, 800, 3), 100, np.uint8)] * 3
    analyzer, cap, obb, hbb, _ = prepare(monkeypatch, mode, session, frames)
    kwargs = run_kwargs(mode, tmp_path)
    kwargs.update(unknown_total=False, auto_total=True, preview_only=preview_only)
    result = analyzer.run(**kwargs)
    assert result["monitoring_status"] == "skipped_turbid"
    assert not obb.calls and not hbb.calls
    assert cap.released
    assert session.water_result["frame"] == 0
    if preview_only:
        assert not (tmp_path / "out").exists()
    else:
        water = pd.read_csv(result["water_quality"])
        assert water.iloc[0]["water_label"] == "turbid"
        assert json.loads(Path(result["monitoring_metadata"]).read_text())["status"] == "skipped_turbid"


@pytest.mark.parametrize("mode", MODES)
def test_measurements_csv_and_model_inputs_are_preserved(monkeypatch, tmp_path, estimator, mode):
    session = MonitoringSession(water_classifier=water_checkpoint(tmp_path, "clear"), estimator=estimator)
    frames = [np.full((450, 800, 3), value, np.uint8) for value in (30, 60, 90)]
    analyzer, cap, obb, hbb, paths = prepare(monkeypatch, mode, session, frames)
    result = analyzer.run(**run_kwargs(mode, tmp_path))
    det = pd.read_csv(result["paths"]["detections"])
    per_id = pd.read_csv(result["paths"]["per_shrimp"])
    expected_frames = [0, 2] if mode == "predict" else [0, 1, 2]
    assert det["Frame"].tolist() == expected_frames
    expected = estimator.measure(cv2.boxPoints(((400.25, 225.75), (250.5, 65.25), float(np.degrees(np.float32(0.31))))), frames[0].shape)
    for key in ("length_px", "width_px", "length_mm", "width_mm", "weight_g"):
        assert det[key].tolist() == pytest.approx([expected[key]] * len(expected_frames))
    assert det["width_source"].eq("obb_proxy").all()
    assert det["water_label"].eq("clear").all()
    assert per_id.iloc[0]["measurement_samples"] == len(expected_frames)
    assert per_id.iloc[0]["mean_weight_g"] == expected["weight_g"]
    assert result["monitoring_status"] == "completed"
    assert cap.released and paths == ["test-obb.pt", "test-hbb.pt", "test-hbb.pt"]
    for index, (method, frame, args) in enumerate(obb.calls):
        assert np.array_equal(frame, frames[expected_frames[index]])
        assert args == dict(conf=0.6, iou=0.4, imgsz=960, verbose=False, **({"persist": True, "tracker": "bytetrack.yaml"} if mode != "predict" else {}))
        assert method == ("predict" if mode == "predict" else "track")
    for _, inputs, args in hbb.calls:
        assert args == dict(imgsz=416, verbose=False)
        assert inputs[0].shape[2] == (3 if mode == "predict" else 9)
    if mode == "multi_channel_track":
        assert set(analyzer._hbb_temporal_pipeline.buffers) == {77}
        assert analyzer._hbb_temporal_pipeline.buffers[77][0][0] == 0


@pytest.mark.parametrize("mode", MODES)
def test_live_first_frame_and_preview_do_not_write(monkeypatch, tmp_path, estimator, mode):
    session = MonitoringSession(water_classifier=water_checkpoint(tmp_path, "clear"), estimator=estimator)
    frames = [np.full((450, 800, 3), value, np.uint8) for value in (30, 60, 90)]
    analyzer, cap, obb, _, _ = prepare(monkeypatch, mode, session, frames, live=True)
    kwargs = run_kwargs(mode, tmp_path)
    kwargs.update(preview_only=True, max_frames=3)
    result = analyzer.run(**kwargs)
    expected_values = [30, 90] if mode == "predict" else [30, 60, 90]
    assert [int(call[1][0, 0, 0]) for call in obb.calls] == expected_values
    assert session.water_result["frame"] == 0 and cap.released
    assert result["paths"] == {} and not (tmp_path / "out").exists()


@pytest.mark.parametrize("mode", MODES)
def test_disabled_monitoring_keeps_existing_csv_schema(monkeypatch, tmp_path, mode):
    analyzer, cap, _, _, _ = prepare(monkeypatch, mode, MonitoringSession(), [np.zeros((450, 800, 3), np.uint8)])
    result = analyzer.run(**run_kwargs(mode, tmp_path))
    for key in ("detections", "per_shrimp"):
        columns = pd.read_csv(result["paths"][key]).columns
        assert not any("length" in column or "weight" in column or "water" in column or "measurement" in column for column in columns)
    assert "monitoring_status" not in result
    assert not list(Path(result["output_dir"]).glob("water*"))
    assert cap.released


@pytest.mark.parametrize("mode", MODES)
def test_auto_total_scan_rewinds_before_analysis(monkeypatch, tmp_path, mode):
    session = MonitoringSession(water_classifier=water_checkpoint(tmp_path, "clear"))
    frames = [np.full((450, 800, 3), value, np.uint8) for value in (30, 60, 90)]
    analyzer, cap, obb, _, _ = prepare(monkeypatch, mode, session, frames)
    kwargs = run_kwargs(mode, tmp_path)
    kwargs.update(unknown_total=False, auto_total=True, auto_total_skip_frames=2)
    result = analyzer.run(**kwargs)
    expected = [0, 2] if mode == "predict" else [0, 1, 2]
    assert pd.read_csv(result["paths"]["detections"])["Frame"].tolist() == expected
    assert [int(call[1][0, 0, 0]) for call in obb.calls] == [30, 90] + [int(frames[i][0, 0, 0]) for i in expected]
    assert cap.released


@pytest.mark.parametrize("mode", MODES)
def test_cli_exposes_shared_monitoring_and_weight_overrides(mode):
    cli = importlib.import_module(f"{mode}.run_{mode}")
    args = cli.build_parser().parse_args(["--video", "sample.mp4", "--monitoring", "--water-policy", "report", "--obb-model", "body.pt", "--hbb-model", "male.pt"])
    assert args.monitoring and args.water_policy == "report"
    assert (args.obb_model, args.hbb_model) == ("body.pt", "male.pt")


@pytest.mark.parametrize("mode", MODES)
def test_report_policy_allows_turbid_detection_and_resets_session(monkeypatch, tmp_path, mode):
    session = MonitoringSession(water_classifier=water_checkpoint(tmp_path, "turbid"), water_policy="report")
    # Reusing an analyzer/session must discard the previous source's gate state.
    session.water_result = {"water_label": "clear", "water_confidence": 1.0}
    session.stopped = True
    analyzer, cap, obb, _, _ = prepare(monkeypatch, mode, session, [np.zeros((450, 800, 3), np.uint8)])
    result = analyzer.run(**run_kwargs(mode, tmp_path))
    assert len(obb.calls) == 1 and cap.released
    assert session.water_result["water_label"] == "turbid"
    assert result["monitoring_status"] == "completed"
    assert pd.read_csv(result["paths"]["detections"])["water_label"].eq("turbid").all()


@pytest.mark.parametrize("mode", MODES)
def test_detection_failure_releases_capture(monkeypatch, tmp_path, mode):
    session = MonitoringSession(water_classifier=water_checkpoint(tmp_path, "clear"))
    analyzer, cap, _, _, _ = prepare(monkeypatch, mode, session, [np.zeros((450, 800, 3), np.uint8)])

    def fail(*args, **kwargs):
        raise RuntimeError("inference failed")

    monkeypatch.setattr(analyzer, "_detect_frame", fail)
    with pytest.raises(RuntimeError, match="inference failed"):
        analyzer.run(**run_kwargs(mode, tmp_path))
    assert cap.released
