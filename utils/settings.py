"""JSON-backed application settings (never stores passwords or keys)."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from core.key_manager import KdfParams, available_kdfs, get_preset

from .paths import data_dir, default_export_dir

DEFAULTS: dict[str, Any] = {
    "export_dir": "",
    "theme": "dark",
    "show_password_default": False,
    "kdf": "argon2id",
    "kdf_level": "balanced",
    "record_history": True,
    "clear_clipboard": True,
}
_ALLOWED = {
    "theme": {"dark", "light"},
    "kdf": {"argon2id", "pbkdf2"},
    "kdf_level": {"balanced", "strong", "paranoid"},
}


class Settings:
    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = str(path or (data_dir() / "settings.json"))
        self._values: dict[str, Any] = dict(DEFAULTS)
        self.load()

    # ---- persistence --------------------------------------------------------
    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(stored, dict):
            return
        for key, default in DEFAULTS.items():
            value = stored.get(key, default)
            if isinstance(value, type(default)) and (key not in _ALLOWED or value in _ALLOWED[key]):
                self._values[key] = value

    def save(self) -> None:
        directory = os.path.dirname(self.path) or "."
        try:
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._values, fh, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass  # settings are a convenience; failing to persist must never crash the app

    # ---- access -------------------------------------------------------------
    def get(self, key: str) -> Any:
        return self._values[key]

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        if key in _ALLOWED and value not in _ALLOWED[key]:
            raise ValueError(f"Invalid value for {key}: {value!r}")
        if not isinstance(value, type(DEFAULTS[key])):
            raise TypeError(f"Invalid type for {key}")
        self._values[key] = value
        self.save()

    @property
    def export_dir(self) -> str:
        value = self._values["export_dir"]
        return value if value and os.path.isdir(value) else default_export_dir()

    def kdf_params(self) -> KdfParams:
        kdf = self._values["kdf"]
        if kdf not in available_kdfs():
            kdf = "pbkdf2"
        return get_preset(kdf, self._values["kdf_level"])
