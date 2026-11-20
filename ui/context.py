"""Shared application context handed to every page (dependency injection, no globals)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal

from core.file_handler import SessionTempDir
from core.history import HistoryStore
from utils.logger import get_logger
from utils.settings import Settings


class Bus(QObject):
    """Application-wide signals."""

    history_changed = Signal()
    settings_changed = Signal(str)
    selftest_done = Signal(object)  # list[SelfTestResult]


class AppContext:
    def __init__(self, settings: Settings, history: HistoryStore, temp: SessionTempDir) -> None:
        self.settings = settings
        self.history = history
        self.temp = temp
        self.bus = Bus()
        self.log = get_logger()
        self.selftest_results: list | None = None
        # wired by MainWindow:
        self.navigate: Callable[[str], None] = lambda key: None
        self._toast: Callable[[str, str, str], None] = lambda kind, title, msg="": None
        self.run_selftest: Callable[[], None] = lambda: None

    def toast(self, kind: str, title: str, message: str = "") -> None:
        """kind: 'success' | 'error' | 'warning' | 'info'."""
        self._toast(kind, title, message)

    def record(self, operation: str, file_name: str, file_type: str, file_size: int, status: str) -> None:
        try:
            self.history.record(operation, file_name, file_type, file_size, status,
                                store_entry=bool(self.settings.get("record_history")))
        except Exception as exc:  # history is non-critical; never break the user's operation
            self.log.warning("history write failed: %s", type(exc).__name__)
        self.bus.history_changed.emit()
