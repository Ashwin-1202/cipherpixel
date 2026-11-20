"""Locations for app data (history DB, settings, logs)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "CipherPixel"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def data_dir() -> Path:
    """``<project>/data`` when writable, else the per-user data directory.

    Override with the ``CIPHERPIXEL_DATA_DIR`` environment variable.
    """
    override = os.environ.get("CIPHERPIXEL_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    project_data = PROJECT_ROOT / "data"
    if _writable(project_data):
        return project_data
    fallback = _user_data_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def assets_dir() -> Path:
    return PROJECT_ROOT / "assets"


def default_export_dir() -> str:
    pictures = Path.home() / "Pictures"
    return str(pictures if pictures.is_dir() else Path.home())
