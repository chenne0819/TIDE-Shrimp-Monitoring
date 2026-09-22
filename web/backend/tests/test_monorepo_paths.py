"""The published web/tracking layout must work independently of the caller's cwd."""
import pytest

from app import config


@pytest.mark.parametrize("relative_root", [None, "../custom-analyzer"])
def test_analyzer_paths_resolve_from_web_root(tmp_path, monkeypatch, relative_root):
    web_root = tmp_path / "relocated checkout" / "web"
    web_root.mkdir(parents=True)
    analyzer = web_root.parent / ("tracking" if relative_root is None else "custom-analyzer")
    python = analyzer / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    caller = tmp_path / "unrelated caller"
    caller.mkdir()
    monkeypatch.setattr(config, "APP_ROOT", web_root)
    monkeypatch.chdir(caller)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("ANALYZER_ROOT", raising=False)
    monkeypatch.delenv("ANALYZER_PYTHON", raising=False)
    monkeypatch.delenv("STORAGE_ROOT", raising=False)
    if relative_root:
        monkeypatch.setenv("ANALYZER_ROOT", relative_root)

    settings = config.Settings.from_env()

    assert settings.analyzer_root == analyzer.resolve()
    assert settings.analyzer_python == python.resolve()
    assert settings.storage_root == (web_root / "storage").resolve()
