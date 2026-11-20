"""'Save/Export file' control used after encryption and decryption."""

from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from core.file_handler import export_copy

from .. import dialogs
from ..context import AppContext
from ..workers import TaskWorker
from .basics import button, label


class SaveControl(QWidget):
    """Primary button + slim progress bar + 'saved to…' status, backed by a background copy."""

    saved = Signal(str)

    def __init__(self, ctx: AppContext, text: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.saved_path: str | None = None
        self._source = ""
        self._suggested = ""
        self._filter = ""
        self._title = ""
        self._worker: TaskWorker | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.button = button(text, "primary", icon, size="lg")
        self.button.clicked.connect(self._choose_and_save)
        lay.addWidget(self.button)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.status = label("", "muted", wrap=True)
        self.reveal = button("Show in folder", "ghost", "fa5s.external-link-alt")
        self.reveal.hide()
        self.reveal.clicked.connect(lambda: self.saved_path and dialogs.reveal_in_folder(self.saved_path))
        row.addWidget(self.status, 1)
        row.addWidget(self.reveal)
        lay.addLayout(row)
        self._button_text = text

    def configure(self, source: str, suggested_name: str, file_filter: str, dialog_title: str) -> None:
        self._source, self._suggested, self._filter, self._title = source, suggested_name, file_filter, dialog_title
        self.saved_path = None
        self.status.setText("")
        self.reveal.hide()
        self.bar.hide()
        self.button.setEnabled(True)
        self.button.setText(self._button_text)

    def is_saving(self) -> bool:
        return self._worker is not None

    def _choose_and_save(self) -> None:
        if self._worker is not None or not self._source:
            return
        start = os.path.join(self.ctx.settings.export_dir, self._suggested)
        path = dialogs.save_file(self, self._title, start, self._filter)
        if not path:
            return
        wanted_ext = os.path.splitext(self._suggested)[1]
        if wanted_ext and not os.path.splitext(path)[1]:
            path += wanted_ext
        self._save_to(path)

    def _save_to(self, path: str) -> None:
        self.button.setEnabled(False)
        self.button.setText("Saving…")
        self.bar.setValue(0)
        self.bar.show()
        worker = TaskWorker(export_copy, self._source, path, parent=self)
        self._worker = worker
        worker.progress.connect(lambda _s, f: self.bar.setValue(int(f * 100)))
        worker.succeeded.connect(lambda p, w=worker: self._done(p))
        worker.failed.connect(self._failed)
        worker.cancelled.connect(lambda: self._failed("Saving was cancelled.", "OperationCancelled"))
        worker.finished.connect(self._cleanup_worker)
        worker.start()

    def _cleanup_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()

    def _done(self, path: str) -> None:
        self.saved_path = path
        self.bar.hide()
        self.button.setEnabled(True)
        self.button.setText("Save a copy…")
        self.status.setText(f"Saved to {path}")
        self.reveal.show()
        self.ctx.toast("success", "File saved", os.path.basename(path))
        self.saved.emit(path)

    def _failed(self, message: str, _kind: str) -> None:
        self.bar.hide()
        self.button.setEnabled(True)
        self.button.setText(self._button_text if self.saved_path is None else "Save a copy…")
        self.ctx.toast("error", "Could not save file", message)

    def wait(self) -> None:
        if self._worker is not None:
            self._worker.wait(5000)
