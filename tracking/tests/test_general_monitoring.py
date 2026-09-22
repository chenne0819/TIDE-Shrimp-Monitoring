"""Exercise the original tracking/crop/sex paths with deterministic model outputs."""

import csv
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch

from general_track.modules import head_tail_pipeline, track_pipeline
from shrimp_monitoring import MonitoringSession, summarize_measurements


POLYGON = np.array([[20, 30], [140, 30], [140, 70], [20, 70]], dtype=np.float32)
MEASUREMENTS = {
    "length_mm": 102.0,
    "width_mm": 12.0,
    "weight_g": 8.5,
    "measurement_status": "estimated_obb_width_proxy",
}


def obb_prediction():
    def row(polygon, class_index, track_id):
        return SimpleNamespace(
            cls=torch.tensor([class_index]),
            conf=torch.tensor([0.9]),
            xyxyxyxy=torch.tensor(polygon[None]),
            id=torch.tensor([track_id]),
        )

    head = np.array([[30, 42], [42, 42], [42, 58], [30, 58]], dtype=np.float32)
    return SimpleNamespace(
        names={0: "shrimp", 1: "shrimp_head", 2: "shrimp_tail"},
        obb=[row(POLYGON, 0, 42), row(head, 1, 77)],
    )


class FakeMonitoring:
    def __init__(self, turbid=False, enabled=True):
        self.turbid = turbid
        self.enabled = enabled
        self.reset_calls = 0
        self.checks = []
        self.measurements = []
        self.annotations = []
        self.exports = []

    def reset(self):
        self.reset_calls += 1

    def check_frame(self, frame, frame_index, fps):
        self.checks.append((frame_index, fps, frame.shape))
        return not self.turbid

    def measure(self, polygon, frame_shape):
        self.measurements.append((polygon.copy(), frame_shape))
        return MEASUREMENTS.copy() if self.enabled else {}

    def annotate_measurement(self, annotated, record, anchor):
        self.annotations.append((record.copy(), anchor))

    def annotate_water(self, annotated):
        pass

    def export(self, run_dir):
        self.exports.append(Path(run_dir))
        if not self.enabled:
            return {}
        status = "skipped_turbid" if self.turbid else "completed"
        return {"status": status, "monitoring_status": status, "skipped": self.turbid}


class FakeCapture:
    def __init__(self, count=2):
        self.frames = [np.full((100, 160, 3), 100 + i, dtype=np.uint8) for i in range(count)]
        self.count = count
        self.released = False

    def isOpened(self):
        return True

    def get(self, key):
        return 25.0 if key == cv2.CAP_PROP_FPS else self.count

    def read(self):
        return (True, self.frames.pop(0)) if self.frames else (False, None)

    def release(self):
        self.released = True


class FakeWriter:
    def __init__(self):
        self.frames = []
        self.released = False

    def isOpened(self):
        return True

    def write(self, frame):
        self.frames.append(frame.copy())

    def release(self):
        self.released = True


@pytest.fixture(params=["hbb", "head_tail"])
def pipeline(request, monkeypatch):
    module = track_pipeline if request.param == "hbb" else head_tail_pipeline
    models = []

    class FakeYOLO:
        names = {0: "shrimp", 1: "shrimp_head", 2: "shrimp_tail"}

        def __init__(self, path):
            self.path = path
            self.track_calls = []
            self.predict_calls = []
            models.append(self)

        def track(self, frame, **kwargs):
            self.track_calls.append(kwargs)
            return [obb_prediction()]

        def predict(self, crop, **kwargs):
            self.predict_calls.append((crop.shape, kwargs))
            return [SimpleNamespace(boxes=None)]

    classifier = SimpleNamespace(predict=lambda crop: ("female", 0.8, 0.2))
    monkeypatch.setattr(module, "YOLO", FakeYOLO)
    if request.param == "head_tail":
        monkeypatch.setattr(module, "load_sex_classifier", lambda path: classifier)
    captures = []
    writers = []

    def capture_factory(source):
        capture = FakeCapture()
        captures.append(capture)
        return capture

    def writer_factory(*args):
        writer = FakeWriter()
        writers.append(writer)
        return writer

    monkeypatch.setattr(module.cv2, "VideoCapture", capture_factory)
    monkeypatch.setattr(module.cv2, "VideoWriter", writer_factory)
    monkeypatch.setattr(module.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(module, "show_preview_or_raise", lambda *args: 0)
    monkeypatch.setattr(module, "fit_preview_to_screen", lambda image: image)

    def create(monitoring):
        if request.param == "hbb":
            return module.HbbVotingShrimpAnalyzer("new_obb.pt", "new_hbb.pt", window_frames=1, monitoring=monitoring)
        return module.HeadTailShrimpAnalyzer("new_obb.pt", "new_classifier.pt", monitoring=monitoring)

    return SimpleNamespace(kind=request.param, module=module, create=create, models=models, captures=captures, writers=writers)


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def test_clear_water_preserves_tracking_and_attaches_measurements(pipeline, tmp_path):
    monitoring = FakeMonitoring()
    analyzer = pipeline.create(monitoring)
    kwargs = {"obb_conf": 0.37, "obb_iou": 0.24} if pipeline.kind == "hbb" else {"conf": 0.37, "iou": 0.24}
    paths = analyzer.run("sample.mp4", output_root=str(tmp_path), tracker="custom_tracker.yaml", **kwargs)

    assert monitoring.reset_calls == 1
    assert monitoring.checks == [(0, 25.0, (100, 160, 3))]
    assert len(pipeline.models[0].track_calls) == 2
    assert pipeline.models[0].path == "new_obb.pt"
    for call in pipeline.models[0].track_calls:
        assert call == {"conf": 0.37, "iou": 0.24, "imgsz": pipeline.module.IMGSZ_OBB, "verbose": False, "persist": True, "tracker": "custom_tracker.yaml"}
    assert pipeline.captures[0].released and pipeline.writers[0].released
    assert len(pipeline.writers[0].frames) == 2
    assert len(monitoring.measurements) == len(monitoring.annotations) == 2
    for polygon, shape in monitoring.measurements:
        np.testing.assert_array_equal(polygon, POLYGON)
        assert shape == (100, 160, 3)

    detections = read_rows(paths["detections"])
    assert [row["raw_tracker_id"] for row in detections] == ["42", "42"]
    assert [row["track_id"] for row in detections] == ["1", "1"]
    assert [row["label"] for row in detections] == (["F", "F"] if pipeline.kind == "hbb" else ["female", "female"])
    assert all(float(row["length_mm"]) == 102.0 and float(row["weight_g"]) == 8.5 for row in detections)
    summary = read_rows(paths["per_shrimp"])[0]
    for key, value in summarize_measurements([MEASUREMENTS, MEASUREMENTS]).items():
        assert float(summary[key]) == value
    assert paths["monitoring_status"] == "completed"


def test_turbid_water_stops_before_inference_without_false_sex_summary(pipeline, tmp_path):
    monitoring = FakeMonitoring(turbid=True)
    paths = pipeline.create(monitoring).run("sample.mp4", output_root=str(tmp_path))
    assert paths["skipped"] is True
    assert paths["status"] == "skipped_turbid"
    assert paths["video"] == ""
    assert not pipeline.models[0].track_calls
    assert not pipeline.writers
    assert not monitoring.measurements
    assert pipeline.captures[0].released
    assert read_rows(paths["detections"]) == read_rows(paths["per_shrimp"]) == []
    if pipeline.kind == "hbb":
        summary = read_rows(paths["window_vote_summary"])[0]
        assert summary["Final Prediction"] == ""
        assert summary["Status"] == "skipped_turbid"
        assert read_rows(paths["video_info"])[0]["Valid Windows"] == "0"


def test_preview_only_saves_no_monitoring_or_existing_outputs(pipeline, tmp_path):
    monitoring = FakeMonitoring()
    paths = pipeline.create(monitoring).run("sample.mp4", output_root=str(tmp_path), preview_only=True)
    assert paths["output_dir"] == ""
    assert not monitoring.exports
    assert not pipeline.writers
    assert list(tmp_path.iterdir()) == []
    assert pipeline.captures[0].released


def test_disabled_monitoring_keeps_original_detection_columns(pipeline, tmp_path):
    paths = pipeline.create(FakeMonitoring(enabled=False)).run("sample.mp4", output_root=str(tmp_path))
    assert not set(MEASUREMENTS).intersection(read_rows(paths["detections"])[0])
    assert "monitoring_status" not in paths
    assert summarize_measurements([{"label": "female"}]) == {}


def test_resources_released_on_inference_error_after_first_frame(pipeline, tmp_path):
    analyzer = pipeline.create(FakeMonitoring())
    original = pipeline.models[0].track

    def fail_second_frame(frame, **kwargs):
        if pipeline.models[0].track_calls:
            raise RuntimeError("inference failed")
        return original(frame, **kwargs)

    pipeline.models[0].track = fail_second_frame
    with pytest.raises(RuntimeError, match="inference failed"):
        analyzer.run("sample.mp4", output_root=str(tmp_path))
    assert pipeline.captures[0].released
    assert pipeline.writers[0].released


def test_session_reset_for_each_run(pipeline, tmp_path):
    monitoring = FakeMonitoring(turbid=True)
    analyzer = pipeline.create(monitoring)
    analyzer.run("first.mp4", output_root=str(tmp_path))
    analyzer.run("second.mp4", output_root=str(tmp_path))
    assert monitoring.reset_calls == 2
    assert len(monitoring.checks) == 2
    assert all(capture.released for capture in pipeline.captures)


def test_real_monitoring_session_reports_turbid_without_stopping_when_requested(pipeline, tmp_path):
    calls = []

    def predict(frame):
        calls.append(frame.shape)
        return {"water_label": "turbid", "water_confidence": 0.95}

    monitoring = MonitoringSession(
        water_classifier=SimpleNamespace(predict=predict),
        estimator=SimpleNamespace(measure=lambda polygon, shape: MEASUREMENTS.copy()),
        water_policy="report",
    )
    paths = pipeline.create(monitoring).run("sample.mp4", output_root=str(tmp_path))
    assert calls == [(100, 160, 3)]
    assert paths["skipped"] is False
    assert paths["monitoring_status"] == "completed"
    assert len(pipeline.models[0].track_calls) == 2
    assert read_rows(paths["water_quality"])[0]["action"] == "continue"
    assert all(row["water_label"] == "turbid" for row in read_rows(paths["detections"]))
    assert Path(paths["monitoring_metadata"]).is_file()


def test_real_monitoring_session_exports_turbid_skip(pipeline, tmp_path):
    monitoring = MonitoringSession(
        water_classifier=SimpleNamespace(predict=lambda frame: {"water_label": "turbid", "water_confidence": 0.98}),
    )
    paths = pipeline.create(monitoring).run("0", output_root=str(tmp_path))
    assert paths["skipped"] is True
    assert not pipeline.models[0].track_calls
    water = read_rows(paths["water_quality"])[0]
    assert water["action"] == "stop" and water["water_label"] == "turbid"
    assert Path(paths["monitoring_metadata"]).is_file()
    assert pipeline.captures[0].released
