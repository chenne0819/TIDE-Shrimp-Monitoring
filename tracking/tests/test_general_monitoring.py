"""Exercise the original tracking/crop/sex paths with deterministic model outputs."""

import csv
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch

from general_track.modules import head_tail_pipeline
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


@pytest.fixture
def pipeline(monkeypatch):
    module = head_tail_pipeline
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
    monkeypatch.setattr(module.visualization, "show_preview_or_raise", lambda *args: 0)
    monkeypatch.setattr(module.visualization, "fit_preview_to_screen", lambda image: image)

    def create(monitoring):
        return module.HeadTailShrimpAnalyzer(FakeYOLO("new_obb.pt"), classifier, monitoring=monitoring)

    return SimpleNamespace(kind="head_tail", module=module, create=create, models=models, captures=captures, writers=writers)


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def test_clear_water_preserves_tracking_and_attaches_measurements(pipeline, tmp_path):
    monitoring = FakeMonitoring()
    analyzer = pipeline.create(monitoring)
    kwargs = {"conf": 0.37, "iou": 0.24}
    paths = analyzer.run("sample.mp4", output_root=str(tmp_path), tracker="custom_tracker.yaml", **kwargs)

    assert monitoring.reset_calls == 1
    assert monitoring.checks == [(0, 25.0, (100, 160, 3))]
    assert len(pipeline.models[0].track_calls) == 2
    assert pipeline.models[0].path == "new_obb.pt"
    for call in pipeline.models[0].track_calls:
        assert call == {"conf": 0.37, "iou": 0.24, "imgsz": 640, "verbose": False, "persist": True, "tracker": "custom_tracker.yaml"}
    assert pipeline.captures[0].released and pipeline.writers[0].released
    assert len(pipeline.writers[0].frames) == 2
    assert len(monitoring.measurements) == len(monitoring.annotations) == 2
    for polygon, shape in monitoring.measurements:
        np.testing.assert_array_equal(polygon, POLYGON)
        assert shape == (100, 160, 3)

    detections = read_rows(paths["detections"])
    assert [row["raw_tracker_id"] for row in detections] == ["42", "42"]
    assert [row["track_id"] for row in detections] == ["1", "1"]
    assert [row["label"] for row in detections] == ["female", "female"]
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



def test_run_track_loads_obb_and_classifier_only(pipeline, tmp_path):
    analyzer = pipeline.create(FakeMonitoring())
    assert [model.path for model in pipeline.models] == ["new_obb.pt"]
    paths = analyzer.run("sample.mp4", output_root=str(tmp_path), debug=True, save_crops=True)
    assert read_rows(paths["per_shrimp"])[0]["final_label"] == "female"
    assert len(list(tmp_path.rglob("classifier_crops/*.jpg"))) == 2


def test_general_cli_accepts_config_only():
    from general_track.run_track import build_parser, DEFAULT_CONFIG
    args = build_parser().parse_args([])
    assert args.config == DEFAULT_CONFIG
    assert build_parser().parse_args(["--config", "job.toml"]).config == Path("job.toml")
    assert set(vars(args)) == {"config"}


def test_run_track_dispatches_to_head_tail_pipeline(monkeypatch):
    from general_track import run_track
    calls = {}
    settings = {"video": "input.mp4", "output_root": "out", "tracker": "bytetrack.yaml", "conf": .4, "iou": .2,
                "preview": False, "preview_only": False, "debug": False, "save_crops": False,
                "max_frames": 2, "cnn_threshold": .7, "smooth_video": True}

    class Analyzer:
        def run(self, **kwargs):
            calls.update(kwargs)
            return {"output_dir": "", "skipped": False}

    def load(path):
        calls["config"] = path
        return settings

    def create(values):
        assert values is settings
        return Analyzer()

    monkeypatch.setattr(run_track, "load_settings", load)
    monkeypatch.setattr(run_track, "create_analyzer", create)
    monkeypatch.setattr("sys.argv", ["run_track", "--config", "job.toml"])
    run_track.main()
    assert calls["config"] == Path("job.toml")
    assert calls["conf"] == .4 and calls["iou"] == .2 and calls["max_frames"] == 2
    assert calls["video"] == "input.mp4"
    assert calls["smooth_video"] is True


def test_general_exports_are_readable_by_web_worker(pipeline, tmp_path):
    import importlib.util
    results_path = Path(__file__).resolve().parents[2] / "web/backend/app/results.py"
    spec = importlib.util.spec_from_file_location("worker_results", results_path)
    results = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(results)
    session = MonitoringSession(estimator=SimpleNamespace(measure=lambda polygon, shape: MEASUREMENTS.copy()))
    paths = pipeline.create(session).run("sample.mp4", output_root=str(tmp_path))
    Path(paths["video"]).touch()
    parsed = results.read_results(Path(paths["output_dir"]))
    assert parsed["status"] == "completed"
    assert parsed["tracks"] == [{"track_id": "1", "label": "Female", "observations": 2,
                                  "length_mm": 102.0, "width_mm": 12.0, "weight_g": 8.5}]
    assert parsed["avg_length_mm"] == 102.0
    assert parsed["video"].name == "result.mp4"


def test_legacy_worker_mode_uses_renamed_entry():
    import ast
    path = Path(__file__).resolve().parents[2] / "web/backend/app/worker.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MODULES" for t in node.targets))
    assert modules["general"] == modules["head_tail"] == "general_track.run_track"


@pytest.mark.parametrize("source", ["head", "tail"])
def test_retained_head_tail_crop_is_oriented_head_left(source):
    from general_track.modules.head_tail_common import orient_head_left
    crop = np.broadcast_to(np.arange(100, dtype=np.uint8)[None, :, None], (30, 100, 3)).copy()
    head = [(90., 15.)] if source == "head" else []
    tail = [(10., 15.)] if source == "tail" else []
    oriented, actual_source = orient_head_left(crop, np.eye(3), head, tail)
    assert actual_source == source
    np.testing.assert_array_equal(oriented, cv2.flip(crop, 1))


@pytest.mark.parametrize("threshold,label,confidence", [(None, "female", 0.8), (0.1, "male", 0.2),
                                                         (0.2, "male", 0.2), (0.7, "female", 0.8)])
def test_cnn_threshold_changes_frame_labels_and_votes(pipeline, tmp_path, threshold, label, confidence):
    analyzer = pipeline.create(FakeMonitoring())
    analyzer.cnn_threshold = threshold
    paths = analyzer.run("sample.mp4", output_root=str(tmp_path), debug=True)
    detections = read_rows(paths["detections"])
    assert all(row["label"] == label for row in detections)
    assert all(float(row["confidence"]) == pytest.approx(confidence) for row in detections)
    assert all(float(row["male_probability"]) == 0.2 for row in detections)
    summary = read_rows(paths["per_shrimp"])[0]
    assert summary["final_label"] == label
    assert summary[f"{label}_votes"] == "2"
    if threshold is not None:
        assert all(float(row["cnn_threshold"]) == threshold for row in detections)


@pytest.mark.parametrize("value", ["-0.1", "1.1", "nan", "inf"])
def test_cnn_threshold_rejects_invalid_cli_values(value):
    from general_track.run_track import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--video", "sample.mp4", "--cnn-threshold", value])


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf")])
def test_cnn_threshold_validated_before_model_loading(threshold):
    with pytest.raises(ValueError, match="CNN threshold"):
        head_tail_pipeline.HeadTailShrimpAnalyzer(None, None, cnn_threshold=threshold)


@pytest.mark.parametrize("option,value", [("--conf", "nan"), ("--conf", "1.1"), ("--iou", "inf"), ("--iou", "-0.1"), ("--max-frames", "0"), ("--max-frames", "-1")])
def test_general_cli_rejects_invalid_detection_limits(option, value):
    from general_track.run_track import build_parser
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["--video", "sample.mp4", option, value])
    assert error.value.code == 2


def test_preview_smoothing_does_not_change_raw_exports_and_resets_each_run(pipeline, tmp_path, monkeypatch):
    analyzer = pipeline.create(FakeMonitoring())
    rendered = []

    def render(frame, records, items, monitoring):
        rendered.append([(value["label"], "preview_male_probability" in value) for value in items])
        return frame.copy()

    monkeypatch.setattr(head_tail_pipeline.visualization, "render_frame", render)
    clock = iter([0.0, 0.5, 0.6, 0.7])
    monkeypatch.setattr(head_tail_pipeline.time, "monotonic", lambda: next(clock))
    for labels in (("male", "female"), ("female", "male")):
        predictions = iter(labels)
        def predict(crop):
            label = next(predictions)
            return label, 0.8, 0.8 if label == "male" else 0.2
        analyzer.classifier.predict = predict
        paths = analyzer.run("sample.mp4", output_root=str(tmp_path), preview=True)
        assert [row["label"] for row in read_rows(paths["detections"])] == list(labels)
        assert "preview_male_probability" not in read_rows(paths["detections"])[0]
    assert rendered == [[("male", False)], [("male", True)],
                        [("female", False)], [("male", True)],
                        [("female", False)], [("female", True)],
                        [("male", False)], [("female", True)]]


@pytest.mark.parametrize("fps", [10, 25])
@pytest.mark.parametrize("debug", [False, True])
def test_saved_video_smooths_on_video_time_without_changing_exports(pipeline, tmp_path, monkeypatch, fps, debug):
    count = 2 * fps + 1
    capture = FakeCapture(count)
    capture.get = lambda key: fps if key == cv2.CAP_PROP_FPS else count
    monkeypatch.setattr(head_tail_pipeline.cv2, "VideoCapture", lambda source: capture)
    # Headless output must not depend on processing speed or require a GUI.
    def unexpected(*args):
        pytest.fail("Saved-video smoothing must use video time without opening a preview")
    monkeypatch.setattr(head_tail_pipeline, "time", SimpleNamespace(monotonic=unexpected))
    monkeypatch.setattr(head_tail_pipeline.visualization, "show_preview_or_raise", unexpected)
    analyzer = pipeline.create(FakeMonitoring())
    probabilities = iter([0.1] + [0.9] * (count - 1))
    def predict(crop):
        p = next(probabilities)
        return ("male" if p >= .5 else "female"), .9, p
    analyzer.classifier.predict = predict
    rendered, panels = [], []
    original_render = head_tail_pipeline.visualization.render_frame
    original_debug = head_tail_pipeline.visualization.make_debug_view
    def render(frame, records, items, monitoring):
        rendered.append(items[0].copy())
        return original_render(frame, records, items, monitoring)
    def debug_view(items, index):
        panels.append(items[0].copy())
        return original_debug(items, index)
    monkeypatch.setattr(head_tail_pipeline.visualization, "render_frame", render)
    monkeypatch.setattr(head_tail_pipeline.visualization, "make_debug_view", debug_view)
    paths = analyzer.run("sample.mp4", output_root=str(tmp_path), smooth_video=True, debug=debug)

    assert len(pipeline.writers[0].frames) == count
    assert capture.released and pipeline.writers[0].released
    assert rendered[0]["label"] == rendered[fps]["label"] == "female"
    assert rendered[-1]["label"] == "male"  # sustained evidence eventually switches
    assert rendered[fps]["preview_male_probability"] == pytest.approx(.1 + (1 - np.exp(-1)) * .8)
    assert rendered[1]["raw_label"] == "male"
    if debug:
        assert [item["label"] for item in panels] == [item["label"] for item in rendered]
        assert panels[1]["raw_label"] == "male"
    detections = read_rows(paths["detections"])
    assert [row["label"] for row in detections] == ["female"] + ["male"] * (count - 1)
    assert all("preview_male_probability" not in row and "raw_label" not in row for row in detections)
    assert float(detections[1]["male_probability"]) == .9
    summary = read_rows(paths["per_shrimp"])[0]
    assert summary["final_label"] == "male" and int(summary["male_votes"]) == count - 1
    assert float(summary["mean_length_mm"]) == MEASUREMENTS["length_mm"]


def test_video_smoothing_resets_and_keeps_crop_labels_raw(pipeline, tmp_path, monkeypatch):
    analyzer = pipeline.create(FakeMonitoring())
    labels, crop_paths = [], []
    original = head_tail_pipeline.visualization.render_frame
    def render(frame, records, items, monitoring):
        labels.append(items[0]["label"])
        return original(frame, records, items, monitoring)
    monkeypatch.setattr(head_tail_pipeline.visualization, "render_frame", render)
    monkeypatch.setattr(head_tail_pipeline.cv2, "imwrite", lambda path, image: crop_paths.append(Path(path).name) or True)
    for probabilities in ((.9, .1), (.1, .9)):
        predictions = iter(probabilities)
        def predict(crop):
            p = next(predictions)
            return ("male" if p >= .5 else "female"), .9, p
        analyzer.classifier.predict = predict
        analyzer.run("sample.mp4", output_root=str(tmp_path), smooth_video=True, save_crops=True)
    assert labels == ["male", "male", "female", "female"]
    assert crop_paths == ["frame_000000_00_male.jpg", "frame_000001_00_female.jpg",
                          "frame_000000_00_female.jpg", "frame_000001_00_male.jpg"]


def test_saved_video_and_live_preview_have_independent_clocks(pipeline, tmp_path, monkeypatch):
    analyzer = pipeline.create(FakeMonitoring())
    probabilities = iter((.1, .9))
    def predict(crop):
        p = next(probabilities)
        return ("male" if p >= .5 else "female"), .9, p
    analyzer.classifier.predict = predict
    clock = iter((20., 20.5))
    monkeypatch.setattr(head_tail_pipeline, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    scores = []
    original = head_tail_pipeline.visualization.render_frame
    def render(frame, records, items, monitoring):
        scores.append(items[0]["preview_male_probability"])
        return original(frame, records, items, monitoring)
    monkeypatch.setattr(head_tail_pipeline.visualization, "render_frame", render)
    analyzer.run("sample.mp4", output_root=str(tmp_path), smooth_video=True, preview=True)
    assert scores == pytest.approx([.1, .1, .1 + (1 - np.exp(-1 / 25)) * .8,
                                   .1 + (1 - np.exp(-.5)) * .8])


def test_debug_preview_preserves_smoothed_overlay(pipeline, monkeypatch):
    analyzer = pipeline.create(FakeMonitoring())
    predictions = iter(("male", "female"))
    def predict(crop):
        label = next(predictions)
        return label, 0.8, 0.8 if label == "male" else 0.2
    analyzer.classifier.predict = predict
    clock = iter((0.0, 0.5))
    monkeypatch.setattr(head_tail_pipeline.time, "monotonic", lambda: next(clock))
    displayed = []
    debug_labels = []

    def render(frame, records, items, monitoring):
        # Distinguish smoothed overlays from the raw export frame at the pixel level.
        marker = 123 if "preview_male_probability" in items[0] else 45
        return np.full_like(frame, marker)

    monkeypatch.setattr(head_tail_pipeline.visualization, "render_frame", render)
    def debug_view(items, frame_index):
        debug_labels.append([(value["label"], value["raw_label"]) for value in items])
        return np.zeros((100, 160, 3), dtype=np.uint8)

    monkeypatch.setattr(head_tail_pipeline.visualization, "make_debug_view", debug_view)
    monkeypatch.setattr(head_tail_pipeline.visualization, "combine_preview", lambda main, debug: main)
    monkeypatch.setattr(head_tail_pipeline.visualization, "show_preview_or_raise",
                        lambda name, image: displayed.append(int(image[0, 0, 0])) or 0)
    analyzer.run("sample.mp4", preview_only=True, debug=True)
    assert displayed == [123, 123]
    assert debug_labels == [[("male", "male")], [("male", "female")]]


def test_debug_panel_distinguishes_smoothed_probability_from_raw_cnn(pipeline, monkeypatch):
    from general_track.modules.preview_smoothing import PreviewSmoothing
    from general_track.modules.obb_track import obb_rows

    analyzer = pipeline.create(FakeMonitoring())
    frame = np.full((100, 160, 3), 120, dtype=np.uint8)
    _, items = analyzer._process_frame(frame, obb_rows(obb_prediction()), 0, 25)
    smoothing = PreviewSmoothing()
    smoothing.update(items, 0)
    items[0].update(label="male", confidence=0.9, male_probability=0.9)
    preview_items = smoothing.update(items, 0.5)
    texts = []
    monkeypatch.setattr(head_tail_pipeline.visualization.cv2, "putText",
                        lambda image, text, *args: texts.append(text) or image)
    panel = head_tail_pipeline.visualization.make_debug_view(preview_items, 1)
    assert panel.shape == (180, 480, 3)
    assert texts == ["1 F | Pm 0.475", "CNN M 0.90"]


def test_frame_records_do_not_contain_image_data(pipeline):
    from general_track.modules.obb_track import obb_rows
    analyzer = pipeline.create(FakeMonitoring())
    frame = np.full((100, 160, 3), 120, dtype=np.uint8)
    records, items = analyzer._process_frame(frame, obb_rows(obb_prediction()), 0, 25)
    assert records and items
    assert "classifier_crop" not in records[0]
    assert not any(isinstance(value, np.ndarray) for value in records[0].values())
    assert items[0]["classifier_crop"].size > 0
    np.testing.assert_array_equal(frame, np.full_like(frame, 120))


def test_smoothed_main_label_is_kept_inside_frame(pipeline, monkeypatch):
    from general_track.modules.preview_smoothing import PreviewSmoothing
    from general_track.modules.obb_track import obb_rows

    analyzer = pipeline.create(FakeMonitoring())
    frame = np.zeros((100, 160, 3), dtype=np.uint8)
    records, items = analyzer._process_frame(frame, obb_rows(obb_prediction()), 0, 25)
    items[0]["polygon"] = np.array([[150, 0], [159, 0], [159, 20], [150, 20]], dtype=np.float32)
    preview_items = PreviewSmoothing().update(items, 0)
    texts = []
    monkeypatch.setattr(head_tail_pipeline.visualization.cv2, "putText",
                        lambda image, text, anchor, font, scale, color, thickness, line:
                        texts.append((text, anchor, font, scale, thickness)) or image)
    head_tail_pipeline.visualization.render_frame(frame, records, preview_items, FakeMonitoring())
    text, (x, y), font, scale, thickness = texts[0]
    assert text == "1 F | Pm 0.200"
    (width, height), baseline = cv2.getTextSize(text, font, scale, thickness)
    assert x >= 0 and x + width <= frame.shape[1]
    assert y - height >= 0 and y + baseline <= frame.shape[0]


def test_detector_session_and_display_ids_reset_between_runs(pipeline, tmp_path):
    analyzer = pipeline.create(FakeMonitoring())
    resets = []
    analyzer.obb_model.predictor = SimpleNamespace(trackers=[SimpleNamespace(reset=lambda: resets.append(True))])
    first = analyzer.run("same.mp4", output_root=str(tmp_path))
    second = analyzer.run("same.mp4", output_root=str(tmp_path))
    assert len(resets) == 2
    assert read_rows(first["detections"])[0]["track_id"] == read_rows(second["detections"])[0]["track_id"] == "1"
    assert first["output_dir"] != second["output_dir"]
    assert Path(first["detections"]).is_file()


def test_max_frames_limits_processing(pipeline, tmp_path):
    paths = pipeline.create(FakeMonitoring()).run("sample.mp4", output_root=str(tmp_path), max_frames=1)
    assert len(pipeline.models[0].track_calls) == len(read_rows(paths["detections"])) == 1
    assert len(pipeline.writers[0].frames) == 1


def test_failed_writer_is_released(pipeline, tmp_path, monkeypatch):
    writer = FakeWriter()
    writer.isOpened = lambda: False
    monkeypatch.setattr(pipeline.module.cv2, "VideoWriter", lambda *args: writer)
    with pytest.raises(RuntimeError, match="Unable to create result video"):
        pipeline.create(FakeMonitoring()).run("sample.mp4", output_root=str(tmp_path))
    assert writer.released and pipeline.captures[0].released


def test_failed_crop_save_releases_input(pipeline, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline.module.cv2, "imwrite", lambda *args: False)
    with pytest.raises(RuntimeError, match="Unable to save classifier crop"):
        pipeline.create(FakeMonitoring()).run("sample.mp4", output_root=str(tmp_path), save_crops=True)
    assert pipeline.captures[0].released


@pytest.mark.parametrize("key", [ord("q"), 27])
def test_preview_exit_key_releases_resources(pipeline, tmp_path, monkeypatch, key):
    monkeypatch.setattr(pipeline.module.visualization, "show_preview_or_raise", lambda *args: key)
    pipeline.create(FakeMonitoring()).run("sample.mp4", output_root=str(tmp_path), preview=True)
    assert len(pipeline.models[0].track_calls) == 1
    assert pipeline.captures[0].released and pipeline.writers[0].released


def test_preview_only_debug_toggle_never_writes(pipeline, tmp_path, monkeypatch):
    keys = iter([ord("d"), ord("q")])
    panels = []
    original = pipeline.module.visualization.make_debug_view
    monkeypatch.setattr(pipeline.module.visualization, "show_preview_or_raise", lambda *args: next(keys))
    monkeypatch.setattr(pipeline.module.visualization, "make_debug_view", lambda *args: (panels.append(True), original(*args))[1])
    pipeline.create(FakeMonitoring()).run("sample.mp4", output_root=str(tmp_path), preview_only=True, save_crops=True)
    assert len(panels) == 1
    assert not pipeline.writers and not list(tmp_path.iterdir())


def test_geometry_and_pipeline_do_not_load_torch_in_fresh_process():
    import subprocess
    import sys
    code = "from general_track.modules import head_tail_common, head_tail_pipeline; import sys; assert 'torch' not in sys.modules; assert 'ultralytics' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
