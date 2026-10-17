import importlib.util
from pathlib import Path

import numpy as np
import pytest
import torch


@pytest.mark.parametrize("architecture", ["resnet18", "resnet34", "resnet50"])
@pytest.mark.parametrize("invalid_phase", ["train", "val", "test"])
def test_training_rejects_nonfinite_metrics(monkeypatch, tmp_path, architecture, invalid_phase):
    directory = Path(__file__).resolve().parents[1] / "Train/male-female-shrimp/CNN"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(f"test_{architecture}", directory / f"train_{architecture}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr("sys.argv", ["train", "--data", str(tmp_path), "--output", str(tmp_path / "output"),
                                     "--epochs", "1", "--no-pretrained"])
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(module, "build_loaders", lambda *args: ({"train": "train", "val": "val", "test": "test"},
                                                            {"female": 0, "male": 1}))
    monkeypatch.setattr(module, "build_model", lambda *args: torch.nn.Linear(1, 2))

    def phase(model, loader, criterion, optimizer, device, training):
        if training:
            optimizer.step()
        return (float("nan") if loader == invalid_phase else 0.5), 0.5

    monkeypatch.setattr(module, "run_phase", phase)
    monkeypatch.setattr(module, "evaluate", lambda *args: (
        float("nan") if invalid_phase == "test" else 0.5, 0.5, np.zeros((2, 2)),
    ))
    with pytest.raises(ValueError, match=f"Non-finite training metrics: {invalid_phase}_loss"):
        module.main()
    assert not (tmp_path / "output/metrics.json").exists()
