"""Settings page."""

from __future__ import annotations

import os
import platform
import sys

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout

from core.key_manager import ARGON2_AVAILABLE

from . import dialogs
from .base_page import BasePage
from .components.basics import Card, KeyValueRow, SectionHeader, button, hline, label
from .components.kdf import KdfSelector
from .context import AppContext
from .theme import theme
from utils.paths import data_dir
from utils.settings import DEFAULTS


class SettingsPage(BasePage):
    key = "settings"
    title = "Settings"
    crumbs = ["Settings"]

    def __init__(self, ctx: AppContext, apply_theme) -> None:
        super().__init__(ctx, max_width=900)
        self._apply_theme = apply_theme
        s = ctx.settings

        # ---- export directory
        c = Card()
        c.body.addWidget(SectionHeader("Default export folder", "Where Save/Export dialogs open by default"))
        row = QHBoxLayout()
        self.dir_edit = QLineEdit(s.export_dir)
        self.dir_edit.setReadOnly(True)
        self.dir_btn = button("Change…", "secondary", "fa5s.folder-open")
        self.dir_btn.clicked.connect(self._choose_dir)
        self.dir_reset = button("Reset", "ghost", "fa5s.redo")
        self.dir_reset.clicked.connect(self._reset_dir)
        row.addWidget(self.dir_edit, 1)
        row.addWidget(self.dir_btn)
        row.addWidget(self.dir_reset)
        c.body.addLayout(row)
        self.body.addWidget(c)

        # ---- appearance + passwords
        c = Card()
        c.body.addWidget(SectionHeader("Appearance & privacy"))
        row = QHBoxLayout()
        row.addWidget(label("Theme"))
        row.addStretch(1)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(s.get("theme")))
        self.theme_combo.currentIndexChanged.connect(lambda _i: self._apply_theme(self.theme_combo.currentData()))
        row.addWidget(self.theme_combo)
        c.body.addLayout(row)
        c.body.addWidget(hline())
        self.show_pw = QCheckBox("Show passwords by default when typing")
        self.show_pw.setChecked(bool(s.get("show_password_default")))
        self.show_pw.toggled.connect(lambda v: self._set("show_password_default", v))
        self.clear_clip = QCheckBox("Clear the clipboard 30 seconds after copying a password")
        self.clear_clip.setChecked(bool(s.get("clear_clipboard")))
        self.clear_clip.toggled.connect(lambda v: self._set("clear_clipboard", v))
        c.body.addWidget(self.show_pw)
        c.body.addWidget(self.clear_clip)
        self.body.addWidget(c)

        # ---- default encryption config
        c = Card()
        c.body.addWidget(SectionHeader("Default encryption configuration",
                                       "Applied to new encryptions. Existing files keep the settings they were created with."))
        c.body.addWidget(label("Algorithm: AES-256-GCM (fixed)", "muted"))
        self.kdf_sel = KdfSelector()
        self.kdf_sel.set_values(s.get("kdf"), s.get("kdf_level"))
        self.kdf_sel.changed.connect(self._kdf_changed)
        c.body.addWidget(self.kdf_sel)
        if not ARGON2_AVAILABLE:
            c.body.addWidget(label("Argon2id is unavailable because 'argon2-cffi' is not installed; PBKDF2 is used.", "muted", wrap=True))
        self.body.addWidget(c)

        # ---- history
        c = Card()
        c.body.addWidget(SectionHeader("History management"))
        self.record = QCheckBox("Record operations in File History")
        self.record.setChecked(bool(s.get("record_history")))
        self.record.toggled.connect(lambda v: self._set("record_history", v))
        c.body.addWidget(self.record)
        c.body.addWidget(label("Turning this off stops new entries being stored. Dashboard totals still count operations.", "muted", wrap=True))
        row = QHBoxLayout()
        self.clear_btn = button("Clear history now", "danger", "fa5s.trash-alt")
        self.clear_btn.clicked.connect(self._clear_history)
        row.addWidget(self.clear_btn)
        row.addStretch(1)
        c.body.addLayout(row)
        self.body.addWidget(c)

        # ---- app info + reset
        c = Card()
        c.body.addWidget(SectionHeader("Application information"))
        from . import APP_VERSION

        for k, v in [("Version", APP_VERSION), ("Python", platform.python_version()),
                     ("Platform", f"{platform.system()} {platform.release()}"), ("Data folder", str(data_dir()))]:
            c.body.addWidget(KeyValueRow(k, v))
        row = QHBoxLayout()
        self.reset_btn = button("Restore default settings", "secondary", "fa5s.redo")
        self.reset_btn.clicked.connect(self._restore)
        self.open_btn = button("Open data folder", "ghost", "fa5s.external-link-alt")
        self.open_btn.clicked.connect(lambda: dialogs.reveal_in_folder(str(data_dir())))
        row.addWidget(self.reset_btn)
        row.addWidget(self.open_btn)
        row.addStretch(1)
        c.body.addLayout(row)
        self.body.addWidget(c)
        self.body.addStretch(1)

    def _set(self, key: str, value) -> None:
        self.ctx.settings.set(key, value)
        self.ctx.bus.settings_changed.emit(key)

    def _kdf_changed(self) -> None:
        self._set("kdf", self.kdf_sel.kdf_name())
        self._set("kdf_level", self.kdf_sel.level())

    def _choose_dir(self) -> None:
        path = dialogs.choose_folder(self, "Choose default export folder", self.ctx.settings.export_dir)
        if path:
            self._set("export_dir", path)
            self.dir_edit.setText(path)

    def _reset_dir(self) -> None:
        self._set("export_dir", "")
        self.dir_edit.setText(self.ctx.settings.export_dir)

    def _clear_history(self) -> None:
        if dialogs.confirm(self, "Clear all history?", "Every history entry will be permanently removed.",
                           "Clear history", danger=True):
            self.ctx.history.clear()
            self.ctx.bus.history_changed.emit()
            self.ctx.toast("success", "History cleared")

    def _restore(self) -> None:
        if not dialogs.confirm(self, "Restore default settings?", "All preferences return to their defaults.",
                               "Restore"):
            return
        for key, value in DEFAULTS.items():
            self.ctx.settings.set(key, value)
            self.ctx.bus.settings_changed.emit(key)
        self.dir_edit.setText(self.ctx.settings.export_dir)
        for box, key in ((self.show_pw, "show_password_default"), (self.clear_clip, "clear_clipboard"),
                         (self.record, "record_history")):
            box.blockSignals(True)
            box.setChecked(bool(self.ctx.settings.get(key)))
            box.blockSignals(False)
        self.kdf_sel.set_values(self.ctx.settings.get("kdf"), self.ctx.settings.get("kdf_level"))
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.ctx.settings.get("theme")))
        self.theme_combo.blockSignals(False)
        self._apply_theme(self.ctx.settings.get("theme"))
        self.ctx.toast("success", "Settings restored")
