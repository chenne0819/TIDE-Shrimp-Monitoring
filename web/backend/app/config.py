"""Portable configuration; relative paths are always relative to the app root."""
from dataclasses import dataclass
from pathlib import Path
import os
import sys

from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(APP_ROOT / ".env")


def app_path(value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else APP_ROOT / path).resolve()


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_root: Path
    analyzer_root: Path
    analyzer_python: Path
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...] = ("localhost", "127.0.0.1")
    max_upload_bytes: int = 2 * 1024**3
    lease_seconds: int = 180
    analyzer_timeout_seconds: int = 24 * 60 * 60
    poll_seconds: float = 3

    def __post_init__(self):
        if not self.database_url.strip():
            raise ValueError("DATABASE_URL 必須明確設定；不提供預設資料庫帳密。")
        if not self.trusted_hosts or any(not host or "*" in host or "/" in host or ":" in host for host in self.trusted_hosts):
            raise ValueError("TRUSTED_HOSTS 必須是明確主機名稱，不能含萬用字元、通訊協定或連接埠。")
        if "*" in self.cors_origins or "null" in self.cors_origins:
            raise ValueError("CORS_ORIGINS 必須列出可信任的網頁來源，不能使用 * 或 null。")
        if self.max_upload_bytes < 1:
            raise ValueError("MAX_UPLOAD_BYTES 必須大於零。")

    @classmethod
    def from_env(cls):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("DATABASE_URL 必須明確設定；請先建立專案 .env。")
        analyzer_root = app_path(os.getenv("ANALYZER_ROOT", "../tracking"))
        candidates = [analyzer_root / ".venv/Scripts/python.exe", analyzer_root / ".venv/bin/python"]
        default_python = next((path for path in candidates if path.is_file()), Path(sys.executable))
        return cls(
            database_url=database_url,
            storage_root=app_path(os.getenv("STORAGE_ROOT", "storage")),
            analyzer_root=analyzer_root,
            analyzer_python=app_path(os.getenv("ANALYZER_PYTHON") or str(default_python)),
            cors_origins=tuple(value.strip() for value in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if value.strip()),
            trusted_hosts=tuple(value.strip().lower() for value in os.getenv("TRUSTED_HOSTS", "localhost,127.0.0.1").split(",") if value.strip()),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024**3))),
            lease_seconds=max(30, int(os.getenv("WORKER_LEASE_SECONDS", "180"))),
            analyzer_timeout_seconds=int(os.getenv("ANALYZER_TIMEOUT_SECONDS", str(24 * 60 * 60))),
            poll_seconds=float(os.getenv("WORKER_POLL_SECONDS", "3")),
        )
