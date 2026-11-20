"""Base class shared by all pages: scrolling, centred max-width content, worker bookkeeping."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .context import AppContext
from .workers import TaskWorker


class BasePage(QWidget):
    key = ""
    title = ""
    crumbs: list[str] = []

    def __init__(self, ctx: AppContext, max_width: int = 1240) -> None:
        super().__init__()
        self.ctx = ctx
        self._workers: list[TaskWorker] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        holder = QWidget()
        holder.setObjectName("PageBody")
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(32, 26, 32, 32)
        hl.addStretch(1)
        self.content = QWidget()
        self.content.setMaximumWidth(max_width)
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        hl.addWidget(self.content, 100, Qt.AlignTop)
        hl.addStretch(1)
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(22)
        self.scroll.setWidget(holder)

    # ---- lifecycle hooks used by MainWindow ---------------------------------------
    def on_show(self) -> None:
        """Called each time the page becomes visible (and after theme changes)."""

    def has_unsaved_work(self) -> bool:
        return False

    def is_busy(self) -> bool:
        return any(w.isRunning() for w in self._workers)

    def request_cancel(self) -> None:
        for w in self._workers:
            w.cancel()

    def shutdown(self) -> None:
        """Cancel and join background threads (called on application exit)."""
        self.request_cancel()
        for w in list(self._workers):
            w.wait(8000)

    # ---- worker helper ---------------------------------------------------------------
    def run_worker(self, worker: TaskWorker) -> TaskWorker:
        self._workers.append(worker)

        def _forget() -> None:
            if worker in self._workers:
                self._workers.remove(worker)
            worker.deleteLater()

        worker.finished.connect(_forget)
        worker.start()
        return worker
