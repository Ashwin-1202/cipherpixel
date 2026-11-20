"""Background workers so encryption/decryption never blocks the UI thread."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from core.errors import CipherPixelError, OperationCancelled
from utils.logger import get_logger

_log = get_logger()


class TaskWorker(QThread):
    """Runs ``fn(*args, progress=<cb>, cancel=<Event>, **kwargs)`` off the UI thread.

    Signals are queued across threads automatically by Qt.  Progress is throttled so a
    fast encryption loop cannot flood the event queue.
    """

    progress = Signal(str, float)
    succeeded = Signal(object)
    failed = Signal(str, str)  # user-safe message, exception class name
    cancelled = Signal()

    def __init__(self, fn: Callable[..., Any], *args: Any, parent=None, **kwargs: Any) -> None:
        super().__init__(parent)
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._cancel = threading.Event()
        self._last_emit = 0.0
        self._last_stage = ""

    def cancel(self) -> None:
        self._cancel.set()

    # progress callback executed on the worker thread
    def _on_progress(self, stage: str, fraction: float) -> None:
        now = time.monotonic()
        if stage != self._last_stage or fraction >= 1.0 or now - self._last_emit >= 0.03:
            self._last_stage, self._last_emit = stage, now
            self.progress.emit(stage, fraction)

    def run(self) -> None:  # noqa: D401 - QThread API
        try:
            result = self._fn(*self._args, progress=self._on_progress, cancel=self._cancel, **self._kwargs)
        except OperationCancelled:
            self.cancelled.emit()
        except CipherPixelError as exc:
            # Log only the exception class + sanitised detail (never passwords or image data).
            _log.info("operation failed: %s %s", type(exc).__name__, exc.detail or "")
            self.failed.emit(exc.user_message, type(exc).__name__)
        except MemoryError:
            self.failed.emit("Not enough memory to complete this operation. Try a lower KDF strength.", "MemoryError")
        except Exception as exc:  # pragma: no cover - defensive; shown generically
            _log.exception("unexpected worker error: %s", type(exc).__name__)
            self.failed.emit("An unexpected error occurred. Details were written to the log file.", type(exc).__name__)
        else:
            self.succeeded.emit(result)
        finally:
            # Drop references to arguments (which include the password string) promptly.
            self._args = ()
            self._kwargs = {}
