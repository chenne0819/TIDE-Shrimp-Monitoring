"""A relocated checkout must load its own assets, not the original machine's."""

from argparse import ArgumentParser
import importlib
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from project_paths import PROJECT_ROOT
from shrimp_monitoring.cli import add_monitoring_arguments


@pytest.mark.parametrize("mode", ["general_track", "predict", "multi_channel_track"])
def test_default_models_stay_in_checkout_when_working_directory_changes(mode, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = importlib.import_module(f"{mode}.modules.config")
    defaults = {name: value for name, value in vars(config).items() if name.startswith("MODEL_")}
    assert defaults
    for value in defaults.values():
        assert Path(value).is_relative_to(PROJECT_ROOT / "model")


def test_explicit_monitoring_paths_preserve_user_choice():
    parser = ArgumentParser()
    add_monitoring_arguments(parser)
    args = parser.parse_args(["--water-model", "custom/water.pth", "--biometrics-model-dir", "custom/regressions"])
    assert args.water_model == "custom/water.pth"
    assert args.biometrics_model_dir == "custom/regressions"


def test_renamed_checkout_uses_its_copied_code_and_real_monitoring_assets(tmp_path):
    checkout = tmp_path / "shared checkout 資料"
    checkout.mkdir()
    shutil.copy2(PROJECT_ROOT / "project_paths.py", checkout)
    shutil.copytree(PROJECT_ROOT / "shrimp_monitoring", checkout / "shrimp_monitoring", ignore=shutil.ignore_patterns("__pycache__"))
    for mode in ("general_track", "predict", "multi_channel_track"):
        # The upstream package initializers import their analyzers; copy the
        # complete code tree so this also exercises real package imports.
        shutil.copytree(PROJECT_ROOT / mode, checkout / mode,
                        ignore=shutil.ignore_patterns("__pycache__", "exports", "outputs", "*.csv", "*.png", "*.mp4"))
    shutil.copytree(PROJECT_ROOT / "model/biometrics", checkout / "model/biometrics")
    shutil.copytree(PROJECT_ROOT / "model/water", checkout / "model/water")
    other_cwd = tmp_path / "caller"
    other_cwd.mkdir()
    code = r'''
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from argparse import ArgumentParser
import importlib
import numpy as np
import project_paths
from shrimp_monitoring.cli import add_monitoring_arguments, monitoring_from_args
expected = Path(sys.argv[1]).resolve()
assert project_paths.PROJECT_ROOT == expected
for name in ('general_track', 'predict', 'multi_channel_track'):
    config = importlib.import_module(name + '.modules.config')
    assert Path(config.__file__).is_relative_to(expected)
    for key, value in vars(config).items():
        if key.startswith('MODEL_'):
            assert Path(value).is_relative_to(expected / 'model')
parser = ArgumentParser()
add_monitoring_arguments(parser)
session = monitoring_from_args(parser.parse_args(['--monitoring', '--water-policy', 'report']))
assert session.water_classifier.model_path.is_relative_to(expected)
assert session.estimator.model_dir.is_relative_to(expected)
image = np.zeros((450, 800, 3), dtype=np.uint8)
assert session.check_frame(image, 0, 30)
record = session.measure([[100,100],[400,100],[400,150],[100,150]], image.shape)
assert record['length_mm'] > 0 and record['weight_g'] > 0
print('Relocated assets loaded successfully')
'''
    result = subprocess.run([sys.executable, "-c", code, str(checkout)], cwd=other_cwd,
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Relocated assets loaded successfully" in result.stdout


def test_training_yaml_follows_its_directory_after_move(tmp_path, monkeypatch):
    from ultralytics.data import utils

    training = tmp_path / "moved training"
    training.mkdir()
    data_yaml = training / "data.yaml"
    shutil.copy2(PROJECT_ROOT / "Train/male-female-shrimp/OBB/data.yaml", data_yaml)
    for split in ("train", "val", "test"):
        (training / "shrimp_OBB_dataset" / split / "images").mkdir(parents=True)
    caller = tmp_path / "different working directory"
    caller.mkdir()
    monkeypatch.chdir(caller)
    # Dataset resolution does not need to download a plotting font.
    monkeypatch.setattr(utils, "check_font", lambda *args, **kwargs: None)
    dataset = utils.check_det_dataset(str(data_yaml), autodownload=False)
    for split in ("train", "val", "test"):
        assert Path(dataset[split]) == training / "shrimp_OBB_dataset" / split / "images"
