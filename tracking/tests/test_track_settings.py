import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tomllib

import pytest

from general_track import run_track


def change(path, **values):
    text = path.read_text(encoding="utf-8")
    for name, value in values.items():
        if isinstance(value, float) and not math.isfinite(value):
            encoded = "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
        else:
            encoded = json.dumps(value, ensure_ascii=False)
        replacement = f"{name} = {encoded}"
        pattern = rf"^{re.escape(name)}\s*=.*$"
        if re.search(pattern, text, re.MULTILINE):
            text = re.sub(pattern, lambda match: replacement, text, flags=re.MULTILINE)
        else:
            text += "\n" + replacement + "\n"
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "settings.toml"
    # Exercise a stable configuration independently of the editable sample.
    path.write_text('''video = "input.mp4"
obb_model = "obb.pt"
classifier_model = "cnn.pt"
tracker = "bytetrack.yaml"
imgsz = 640
conf = 0.3
iou = 0.3
water_quality = false
biometrics = false
water_model = "water.pth"
biometrics_model_dir = "biometrics"
water_policy = "stop"
pixels_per_mm = 2.5
measurement_reference_size = [800, 450]
weight_mode = "length"
output_root = "exports"
preview = false
preview_only = false
debug = false
save_crops = false
''', encoding="utf-8")
    for name in ("input.mp4", "obb.pt", "cnn.pt"):
        (tmp_path / name).touch()
    change(path, video="input.mp4", obb_model="obb.pt", classifier_model="cnn.pt", output_root="exports")
    return path


def test_config_paths_are_relative_to_file_not_caller(config, tmp_path, monkeypatch):
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    settings = run_track.load_settings(config)
    assert settings["video"] == str(tmp_path / "input.mp4")
    assert settings["obb_model"] == str(tmp_path / "obb.pt")
    assert settings["output_root"] == str(tmp_path / "exports")
    assert settings["tracker"] == "bytetrack.yaml"
    assert settings.get("cnn_threshold") is settings.get("max_frames") is None
    assert settings["smooth_video"] is False
    assert not (tmp_path / "exports").exists()


@pytest.mark.parametrize("name,value", [
    ("cnn_threshold", -.1), ("cnn_threshold", 1.1), ("cnn_threshold", float("nan")),
    ("conf", float("inf")), ("iou", -.1), ("conf", True), ("imgsz", 0), ("imgsz", 640.5),
    ("max_frames", 0), ("max_frames", -1), ("max_frames", True), ("preview", "false"),
    ("smooth_video", "true"), ("smooth_video", 1),
    ("pixels_per_mm", 0), ("pixels_per_mm", float("inf")), ("measurement_reference_size", [0, 450]),
    ("measurement_reference_size", [800, True]), ("measurement_reference_size", [800]),
    ("water_policy", "skip"), ("weight_mode", "both"), ("video", -1), ("video", True),
    ("tracker", ""), ("output_root", ""), ("output_root", "input.mp4"), ("cnn_treshold", .7),
])
def test_bad_settings_fail_before_models(config, name, value):
    change(config, **{name: value})
    with pytest.raises(ValueError):
        run_track.load_settings(config)


@pytest.mark.parametrize("threshold", [0, .7, 1])
def test_optional_threshold_and_limit(config, threshold):
    change(config, cnn_threshold=threshold, max_frames=3)
    settings = run_track.load_settings(config)
    assert settings["cnn_threshold"] == threshold and settings["max_frames"] == 3


def test_camera_index_is_preserved(config):
    change(config, video=0)
    assert run_track.load_settings(config)["video"] == 0


@pytest.mark.parametrize("enabled", [True, False])
def test_optional_video_smoothing(config, enabled):
    change(config, smooth_video=enabled)
    assert run_track.load_settings(config)["smooth_video"] is enabled


def test_unknown_nested_section_is_rejected(config):
    with config.open("a", encoding="utf-8") as file:
        file.write("\n[tracking]\nconf = 0.4\n")
    with pytest.raises(ValueError, match="Unknown settings: tracking"):
        run_track.load_settings(config)


def test_missing_video_and_malformed_toml(config):
    text = config.read_text(encoding="utf-8")
    config.write_text(re.sub(r"^video\s*=.*$", "", text, flags=re.MULTILINE), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing settings: video"):
        run_track.load_settings(config)
    config.write_text("video = [", encoding="utf-8")
    with pytest.raises(tomllib.TOMLDecodeError):
        run_track.load_settings(config)


@pytest.mark.parametrize("name", ["video", "obb_model", "classifier_model", "tracker"])
def test_missing_active_asset_is_rejected(config, name):
    change(config, **{name: "missing.file"})
    with pytest.raises(FileNotFoundError):
        run_track.load_settings(config)


@pytest.mark.parametrize("enable", ["water_quality", "biometrics"])
def test_monitoring_assets_are_only_required_when_enabled(config, enable):
    assert not run_track.load_settings(config)[enable]
    change(config, **{enable: True})
    with pytest.raises(FileNotFoundError):
        run_track.load_settings(config)


def test_custom_tracker_path(config, tmp_path):
    (tmp_path / "tracker.yaml").write_text("tracker_type: bytetrack", encoding="utf-8")
    change(config, tracker="tracker.yaml")
    assert run_track.load_settings(config)["tracker"] == str(tmp_path / "tracker.yaml")


def test_model_objects_are_created_at_entry(config, monkeypatch):
    from general_track.modules import obb_track, sex_classifier
    settings = run_track.load_settings(config)
    detector, classifier = object(), object()
    monkeypatch.setattr(obb_track, "load_obb_model", lambda path: detector)
    monkeypatch.setattr(sex_classifier, "load_sex_classifier", lambda path: classifier)
    analyzer = run_track.create_analyzer(settings)
    assert analyzer.obb_model is detector and analyzer.classifier is classifier
    assert not analyzer.monitoring.enabled and analyzer.imgsz == 640


def test_invalid_config_does_not_start_analyzer(config, monkeypatch, capsys):
    change(config, cnn_threshold=2)
    monkeypatch.setattr(run_track, "create_analyzer", lambda settings: pytest.fail("Model load should not happen"))
    monkeypatch.setattr(sys, "argv", ["run_track", "--config", str(config)])
    with pytest.raises(SystemExit) as error:
        run_track.main()
    assert error.value.code == 1
    assert "cnn_threshold" in capsys.readouterr().err


@pytest.mark.parametrize("option", ["--video", "--obb-model", "--classifier-model", "--cnn-model",
                                    "--cnn-threshold", "--max-frames", "--conf", "--iou", "--monitoring",
                                    "--water-quality", "--biometrics", "--preview", "--debug", "--save-crops", "--con"])
def test_removed_cli_options_are_rejected(option):
    with pytest.raises(SystemExit) as error:
        run_track.build_parser().parse_args([option, "value"])
    assert error.value.code == 2


def test_config_and_help_do_not_load_torch(config):
    code = "from general_track.run_track import load_settings; import sys; load_settings(sys.argv[1]); assert 'torch' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code, str(config)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("limit", [None, 4])
def test_web_job_config_matches_real_tracking_contract(config, tmp_path, limit):
    import importlib.util
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("analyzer_config", root / "web/backend/app/analyzer_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template = tmp_path / "general_track/config.toml"
    template.parent.mkdir()
    template.write_text(config.read_text(encoding="utf-8"), encoding="utf-8")
    change(template, obb_model="../obb.pt", classifier_model="../cnn.pt", tracker="../tracker.yaml",
           water_model=str(root / "tracking/model/water/logistic_regression_model.pth"),
           biometrics_model_dir=str(root / "tracking/model/biometrics"),
           preview_only=True, water_quality=False, biometrics=False, max_frames=2, cnn_threshold=.03)
    (tmp_path / "tracker.yaml").write_text("tracker_type: bytetrack", encoding="utf-8")
    original = template.read_bytes()
    destination = tmp_path / "job 資料.toml"
    module.write_job_config(tmp_path, tmp_path / "input.mp4", tmp_path / "job exports", destination,
                            water_policy="report", max_frames=limit)
    args = run_track.build_parser().parse_args(["--config", str(destination)])
    settings = run_track.load_settings(args.config)
    assert settings["video"] == str(tmp_path / "input.mp4")
    assert settings["obb_model"] == str(tmp_path / "obb.pt")
    assert settings["classifier_model"] == str(tmp_path / "cnn.pt")
    assert settings["tracker"] == str(tmp_path / "tracker.yaml")
    assert settings["water_quality"] and settings["biometrics"]
    assert settings["water_policy"] == "report" and settings.get("max_frames") == limit
    assert settings["cnn_threshold"] == .03
    assert settings["smooth_video"] is True
    assert not any(settings[name] for name in ("preview", "preview_only", "debug", "save_crops"))
    assert template.read_bytes() == original
