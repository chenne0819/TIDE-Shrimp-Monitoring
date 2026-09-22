from pathlib import Path
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Importing the production ASGI app must not require or select a real database.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", storage_root=tmp_path / "storage",
                    analyzer_root=tmp_path, analyzer_python=Path(sys.executable), cors_origins=("http://localhost:3000",),
                    trusted_hosts=("localhost", "127.0.0.1", "testserver"), max_upload_bytes=128)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        client.headers["X-Tide-CSRF"] = client.get("/api/session").json()["csrf_token"]
        yield client
