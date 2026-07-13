"""Version / build identification for the startup banner."""
from __future__ import annotations

import os
import subprocess
import sys

__version__ = "0.1.0"


def git_revision() -> str:
    """Short git commit hash of this checkout, or "unknown" if unavailable."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip() or "unknown"
    except Exception:
        return "unknown"


def startup_line() -> str:
    return (
        f"cam-reverse (Python) v{__version__} "
        f"[git {git_revision()}] on Python {sys.version.split()[0]}"
    )
