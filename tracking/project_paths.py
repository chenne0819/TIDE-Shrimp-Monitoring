"""Resolve bundled assets relative to this checkout, never a user's home/CWD.

Callers supply a portable name such as ``model/yolo/model.pt``. The resulting
absolute path is computed at runtime and follows the checkout when it moves.
Explicit CLI overrides, input videos and output folders keep their existing
working-directory-relative semantics.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def project_path(relative_path: str | Path) -> str:
    """Return a string accepted by YOLO, OpenCV and checkpoint loaders."""
    return str(PROJECT_ROOT / relative_path)
