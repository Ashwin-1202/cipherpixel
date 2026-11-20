"""Main application window: sidebar + top bar + page stack."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from core.selftest import run_self_test

from . import APP_NAME, APP_VERSION, dialogs
from .about_page import AboutPage
from .base_page import BasePage
from .components.media import FadeStack, ToastHost
from .components.shell import Sidebar, TopBar
from .context import AppContext
from .dashboard import DashboardPage
from .decrypt_page import DecryptPage
from .encrypt_page import EncryptPage
from .history_page import HistoryPage
from .security_page import SecurityPage
from .settings_page import SettingsPage
from .theme import theme
from .workers import TaskWorker

COMPACT_BELOW = 1000


def _selftest_task(progress=None, cancel=None):
    return run_self_test()


class MainWindow(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.setObjectName("AppRoot")
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} – Advanced Image Security System")
        self.resize(1360, 860)
        self.setMinimumSize(900, 640)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = Sidebar(APP_VERSION)
        root.addWidget(self.sidebar)

        right = QVBoxLayout()
        right.setSpacing(0)
        self.topbar = TopBar()
        right.addWidget(self.topbar)
        self.stack = FadeStack()
        right.addWidget(self.stack, 1)
        root.addLayout(right, 1)

        self.toasts = ToastHost(self)
        ctx._toast = lambda kind, title, message="": self.toasts.show(kind, title, message)
        ctx.navigate = self.navigate
        ctx.run_selftest = self.run_selftest

        self.pages: dict[str, BasePage] = {}
        for page in (DashboardPage(ctx), EncryptPage(ctx), DecryptPage(ctx), HistoryPage(ctx), SecurityPage(ctx),
                     SettingsPage(ctx, self.set_theme), AboutPage(ctx)):
            self.pages[page.key] = page
            self.stack.addWidget(page)
        self._keys = list(self.pages)
        self.current_key = "overview"

        self.sidebar.navigate.connect(self.navigate)
        self.topbar.navigate.connect(self.navigate)
        self.topbar.themeToggleRequested.connect(lambda: self.set_theme("light" if theme.name == "dark" else "dark"))
        self.topbar.quitRequested.connect(self.close)
        self.topbar.openExportFolder.connect(lambda: dialogs.reveal_in_folder(ctx.settings.export_dir))

        for i, key in enumerate(self.pages, start=1):
            if i <= 9:
                QShortcut(QKeySequence(f"Ctrl+{i}"), self, activated=lambda k=key: self.navigate(k))

        self._selftest_worker: TaskWorker | None = None
        self._closing = False
        self.navigate("overview", animate=False)
        self._startup_timer = QTimer(self)  # let the window paint first
        self._startup_timer.setSingleShot(True)
        self._startup_timer.timeout.connect(self.run_selftest)
        self._startup_timer.start(150)

    # ---- navigation ---------------------------------------------------------------------
    def navigate(self, key: str, animate: bool = True) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.current_key = key
        idx = self.stack.indexOf(page)
        if animate:
            self.stack.fade_to(idx)
        else:
            self.stack.setCurrentIndex(idx)
        self.sidebar.set_active(key)
        self.topbar.set_page(page.title, page.crumbs)
        page.on_show()

    def set_theme(self, name: str) -> None:
        theme.apply(name)
        self.ctx.settings.set("theme", name)
        self.ctx.bus.settings_changed.emit("theme")
        combo = self.pages["settings"].theme_combo
        if combo.currentData() != name:
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(name))
            combo.blockSignals(False)

    # ---- self-test ----------------------------------------------------------------------
    def run_selftest(self) -> None:
        if self._selftest_worker is not None or self._closing:
            return
        self.topbar.set_status("checking", "Verifying engine…")
        worker = TaskWorker(_selftest_task, parent=self)
        self._selftest_worker = worker
        worker.succeeded.connect(self._selftest_ok)
        worker.failed.connect(lambda msg, kind: self._selftest_ok([]))
        worker.finished.connect(self._selftest_cleanup)
        worker.start()

    def _selftest_cleanup(self) -> None:
        worker, self._selftest_worker = self._selftest_worker, None
        if worker is not None:
            worker.deleteLater()

    def _selftest_ok(self, results) -> None:
        self.ctx.selftest_results = results
        ok = bool(results) and all(r.passed for r in results)
        self.topbar.set_status("ok" if ok else "fail",
                               "AES-256-GCM · Engine verified" if ok else "Engine check failed")
        if not ok:
            self.ctx.toast("error", "Cryptographic self-test failed",
                           "Do not rely on this installation. Reinstall dependencies and run the test-suite.")
        self.ctx.bus.selftest_done.emit(results)

    # ---- resize / close -----------------------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802
        compact = event.size().width() < COMPACT_BELOW
        if compact != self.sidebar.compact:
            self.sidebar.set_compact(compact)
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        busy = [p for p in self.pages.values() if p.is_busy()]
        if busy and not dialogs.confirm(
                self, "Operation in progress",
                "An encryption or decryption is still running. Quitting now will cancel it and no file will be created.",
                "Quit anyway", danger=True):
            event.ignore()
            return
        unsaved = [p for p in self.pages.values() if p.has_unsaved_work()]
        if unsaved and not dialogs.confirm(
                self, "Unsaved result",
                "You have an encrypted or decrypted image that hasn't been saved. It will be deleted if you quit.",
                "Quit and discard", danger=True):
            event.ignore()
            return
        self.shutdown()
        event.accept()

    def shutdown(self) -> None:
        """Stop every background thread and delete temporary files (idempotent)."""
        self._closing = True  # no new background work may start from here on
        self._startup_timer.stop()
        for p in self.pages.values():
            p.shutdown()
        worker = self._selftest_worker
        if worker is not None:
            worker.wait(15000)
        self.ctx.temp.cleanup()
