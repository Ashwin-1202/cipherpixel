"""Thin wrappers around native dialogs.

Pages call these through the module (``dialogs.save_file(...)``) so tests can replace
them without needing user interaction.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget


def confirm(parent: QWidget | None, title: str, text: str, confirm_text: str = "Confirm",
            danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    box.setWindowTitle(title)
    box.setText(f"<b>{title}</b>")
    box.setInformativeText(text)
    cancel = box.addButton("Cancel", QMessageBox.RejectRole)
    ok = box.addButton(confirm_text, QMessageBox.DestructiveRole if danger else QMessageBox.AcceptRole)
    if danger:
        ok.setProperty("variant", "danger")
    else:
        ok.setProperty("variant", "primary")
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    box.exec()
    return box.clickedButton() is ok


def save_file(parent: QWidget | None, title: str, start_path: str, file_filter: str) -> str | None:
    path, _ = QFileDialog.getSaveFileName(parent, title, start_path, file_filter)
    return path or None


def choose_folder(parent: QWidget | None, title: str, start_dir: str) -> str | None:
    path = QFileDialog.getExistingDirectory(parent, title, start_dir)
    return path or None


def reveal_in_folder(path: str) -> None:
    folder = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
