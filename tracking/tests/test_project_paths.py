"""A relocated checkout must load its own assets, not the original machine's."""

from argparse import ArgumentParser
import tomllib
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from project_paths import PROJECT_ROOT
from shrimp_monitoring.cli import add_monitoring_arguments


def test_default_models_stay_in_checkout_when_working_directory_changes(tmp_path, monkeypatch):
    from general_track.run_track import DEFAULT_CONFIG
    monkeypatch.chdir(tmp_path)
    with DEFAULT_CONFIG.open("rb") as file:
        settings = tomllib.load(file)
    for name in ("obb_model", "classifier_model", "water_model", "biometrics_model_dir"):
        assert (DEFAULT_CONFIG.parent / settings[name]).resolve().is_relative_to(PROJECT_ROOT / "model")


def test_explicit_monitoring_paths_preserve_user_choice():
    parser = ArgumentParser()
    add_monitoring_arguments(parser)
    args = parser.parse_args(["--water-model", "custom/water.pth", "--biometrics-model-dir", "custom/regressions"])
    assert args.water_model == "custom/water.pth"
    assert args.biometrics_model_dir == "custom/regressions"


def test_renamed_checkout_uses_its_copied_code_and_real_monitoring_assets(tmp_path):
    required = [PROJECT_ROOT / "model/water/logistic_regression_model.pth",
                *[PROJECT_ROOT / "model/biometrics" / name for name in ("final_linear_model_length.pkl", "final_linear_model_width.pkl", "polynomial_regression_model_degree3.pkl", "multi_feature_model.pkl")]]
    if not all(path.is_file() for path in required):
        pytest.skip("Private water/regression models are not installed; relocation integration is unverified.")
    checkout = tmp_path / "shared checkout 資料"
    checkout.mkdir()
    shutil.copy2(PROJECT_ROOT / "project_paths.py", checkout)
    shutil.copytree(PROJECT_ROOT / "shrimp_monitoring", checkout / "shrimp_monitoring", ignore=shutil.ignore_patterns("__pycache__"))
    for mode in ("general_track",):
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
import tomllib
import numpy as np
import project_paths
from shrimp_monitoring.cli import add_monitoring_arguments, monitoring_from_args
expected = Path(sys.argv[1]).resolve()
assert project_paths.PROJECT_ROOT == expected
import tomllib
from general_track.run_track import DEFAULT_CONFIG
assert DEFAULT_CONFIG.is_relative_to(expected)
with DEFAULT_CONFIG.open("rb") as file:
    settings = tomllib.load(file)
for key in ('obb_model', 'classifier_model', 'water_model', 'biometrics_model_dir'):
    assert (DEFAULT_CONFIG.parent / settings[key]).resolve().is_relative_to(expected / 'model')
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
