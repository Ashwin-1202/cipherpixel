"""Encrypt Image workspace."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from core.encryption import EncryptionResult, encrypt_file, suggested_output_name
from core.errors import CipherPixelError, WeakPasswordError
from core.file_handler import CPX_FILTER, IMAGE_FILTER, ImageInfo, inspect_image
from core.history import ENCRYPT, FAILED, SUCCESS
from core.security_utils import generate_password, human_size
from utils.validators import password_ready, validate_new_password

from . import dialogs
from .base_page import BasePage
from .components.basics import Card, IconBadge, InfoTile, KeyValueRow, ResponsiveRow, SectionHeader, button, label
from .components.inputs import DropZone, PasswordField, StrengthMeter
from .components.kdf import KdfSelector
from .components.media import ImagePreview, ProgressPanel
from .components.save import SaveControl
from .context import AppContext
from .theme import set_prop
from .workers import TaskWorker

CLIPBOARD_CLEAR_MS = 30_000


class EncryptPage(BasePage):
    key = "encrypt"
    title = "Encrypt Image"
    crumbs = ["Encrypt Image"]

    IDLE, READY, RUNNING, DONE = range(4)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.state = self.IDLE
        self.image: ImageInfo | None = None
        self.result: EncryptionResult | None = None
        self._out_path: str | None = None
        self._worker: TaskWorker | None = None

        self.body.addWidget(label(
            "Protect an image with AES-256-GCM authenticated encryption. Your password never leaves this "
            "computer and is never stored.", "muted", wrap=True))
        row = ResponsiveRow(980, 22)
        row.add(self._build_left(), 5)
        row.add(self._build_right(), 4)
        self.body.addWidget(row)
        self.body.addStretch(1)

        self._apply_defaults()
        self._refresh()
        ctx.bus.settings_changed.connect(self._on_setting_changed)

    # ------------------------------------------------------------------ UI building
    def _build_left(self) -> QWidget:
        card = Card()
        card.body.addWidget(SectionHeader("Image", "Select the image you want to protect"))
        self.left_stack = QStackedWidget()

        self.drop = DropZone(
            "Drag & drop an image here",
            "PNG, JPG, JPEG, BMP or TIFF. The original file is encrypted byte-for-byte, so quality "
            "and metadata are preserved exactly.",
            "fa5s.cloud-upload-alt", "Select image to encrypt", IMAGE_FILTER, "Browse Files",
            start_dir=lambda: self.ctx.settings.export_dir)
        self.drop.fileSelected.connect(self.load_file)
        self.left_stack.addWidget(self.drop)

        ready = QWidget()
        rl = QVBoxLayout(ready)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(14)
        self.preview = ImagePreview("Preview")
        self.preview.setMinimumHeight(300)
        rl.addWidget(self.preview, 1)
        tiles = QGridLayout()
        tiles.setSpacing(10)
        self.t_name, self.t_dims = InfoTile("File name"), InfoTile("Dimensions")
        self.t_size, self.t_format = InfoTile("File size"), InfoTile("Format")
        for i, t in enumerate((self.t_name, self.t_dims, self.t_size, self.t_format)):
            tiles.addWidget(t, i // 2, i % 2)
        tiles.setColumnStretch(0, 1)
        tiles.setColumnStretch(1, 1)
        rl.addLayout(tiles)
        actions = QHBoxLayout()
        self.replace_btn = button("Replace image", "secondary", "fa5s.sync")
        self.replace_btn.clicked.connect(self.drop.browse)
        self.remove_btn = button("Remove", "ghost", "fa5s.trash-alt")
        self.remove_btn.clicked.connect(self._remove_image)
        actions.addWidget(self.replace_btn)
        actions.addWidget(self.remove_btn)
        actions.addStretch(1)
        rl.addLayout(actions)
        self.left_stack.addWidget(ready)

        card.body.addWidget(self.left_stack)
        self.left_card = card
        return card

    def _build_right(self) -> QWidget:
        holder = QWidget()
        v = QVBoxLayout(holder)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(18)

        self.form = QWidget()
        fv = QVBoxLayout(self.form)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.setSpacing(18)
        fv.addWidget(self._build_password_card())
        fv.addWidget(self._build_settings_card())
        self.encrypt_btn = button("ENCRYPT IMAGE", "primary", "fa5s.lock", size="lg",
                                  tooltip="Encrypt the selected image with your password")
        self.encrypt_btn.clicked.connect(self._start)
        self.hint = label("", "muted", align=Qt.AlignCenter, wrap=True)
        fv.addWidget(self.encrypt_btn)
        fv.addWidget(self.hint)
        v.addWidget(self.form)

        self.progress = ProgressPanel()
        self.progress.cancelRequested.connect(self._cancel)
        self.progress.hide()
        v.addWidget(self.progress)

        v.addWidget(self._build_result_card())
        v.addStretch(1)
        return holder

    def _build_password_card(self) -> Card:
        card = Card()
        card.body.addWidget(SectionHeader("Password protection",
                                          "Used to derive your encryption key. It cannot be recovered if lost."))
        card.body.addWidget(label("Password", "muted"))
        self.pw = PasswordField("Enter a strong password")
        self.pw.setToolTip("Minimum 8 characters. Longer passphrases are stronger.")
        card.body.addWidget(self.pw)
        card.body.addWidget(label("Confirm password", "muted"))
        self.pw2 = PasswordField("Re-enter the password")
        card.body.addWidget(self.pw2)
        self.pw.revealedChanged.connect(self.pw2.set_revealed)
        self.pw2.revealedChanged.connect(self.pw.set_revealed)
        self.mismatch = label("The passwords do not match.", wrap=True)
        self.mismatch.setObjectName("ErrorText")
        self.mismatch.hide()
        card.body.addWidget(self.mismatch)
        self.meter = StrengthMeter()
        card.body.addWidget(self.meter)

        row = QHBoxLayout()
        self.gen_btn = button("Generate secure password", "secondary", "fa5s.random",
                              tooltip="Create a random 20-character password with the system's secure generator")
        self.gen_btn.clicked.connect(self._generate)
        self.copy_btn = button("Copy", "ghost", "fa5s.copy", tooltip="Copy the password to the clipboard")
        self.copy_btn.clicked.connect(self._copy)
        row.addWidget(self.gen_btn)
        row.addWidget(self.copy_btn)
        row.addStretch(1)
        card.body.addLayout(row)

        self.pw.textChanged.connect(self._on_password_changed)
        self.pw2.textChanged.connect(self._on_password_changed)
        return card

    def _build_settings_card(self) -> Card:
        card = Card()
        card.body.addWidget(SectionHeader("Encryption settings", "Safe defaults – change only if you know why"))
        algo = QHBoxLayout()
        algo.addWidget(label("Algorithm", "muted"))
        algo.addStretch(1)
        from .components.basics import Badge

        algo.addWidget(Badge("AES-256-GCM", "info"))
        card.body.addLayout(algo)
        self.kdf_sel = KdfSelector()
        card.body.addWidget(self.kdf_sel)
        return card

    def _build_result_card(self) -> Card:
        card = Card(padding=24, spacing=14)
        card.set_tone("success")
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(IconBadge("fa5s.check-circle", "success", size=54, icon_size=28))
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label("Image encrypted successfully", "h2"))
        text.addWidget(label("Authenticated with AES-256-GCM. Only your password can unlock it.", "muted", wrap=True))
        head.addLayout(text, 1)
        card.body.addLayout(head)

        self.r_name = KeyValueRow("Encrypted file name")
        self.r_orig = KeyValueRow("Original size")
        self.r_enc = KeyValueRow("Encrypted size")
        self.r_kdf = KeyValueRow("Key derivation")
        self.r_time = KeyValueRow("Time taken")
        self.r_hash = KeyValueRow("Original SHA-256")
        for r in (self.r_name, self.r_orig, self.r_enc, self.r_kdf, self.r_time, self.r_hash):
            card.body.addWidget(r)
        card.body.addWidget(label(
            "Keep your password safe. Without it, this file cannot be decrypted by anyone – including us.",
            "muted", wrap=True))
        self.save = SaveControl(self.ctx, "Save Encrypted File", "fa5s.save")
        card.body.addWidget(self.save)
        self.again_btn = button("Encrypt Another Image", "secondary", "fa5s.redo")
        self.again_btn.clicked.connect(self._encrypt_another)
        card.body.addWidget(self.again_btn)
        card.hide()
        self.result_card = card
        return card

    # ------------------------------------------------------------------ state / helpers
    def _apply_defaults(self) -> None:
        s = self.ctx.settings
        self.kdf_sel.set_values(s.get("kdf"), s.get("kdf_level"))
        if not self.pw.text():
            self.pw.set_revealed(bool(s.get("show_password_default")))

    def _on_setting_changed(self, key: str) -> None:
        if self.state != self.RUNNING and key in ("kdf", "kdf_level", "show_password_default"):
            self._apply_defaults()

    def _show(self, which: str) -> None:
        self.form.setVisible(which == "form")
        self.progress.setVisible(which == "progress")
        self.result_card.setVisible(which == "result")

    def _on_password_changed(self) -> None:
        text, confirm = self.pw.text(), self.pw2.text()
        self.meter.update_for(text)
        bad = bool(confirm) and confirm != text
        self.mismatch.setVisible(bad)
        self.pw2.set_invalid(bad)
        self._refresh()

    def _refresh(self) -> None:
        text, confirm = self.pw.text(), self.pw2.text()
        interactive = self.state in (self.IDLE, self.READY)
        if self.image is None:
            hint = "Select an image to continue."
        elif not text:
            hint = "Enter a password to protect the image."
        elif len(text) < 8:
            hint = "Use at least 8 characters."
        elif text != confirm:
            hint = "Confirm the password to continue." if not confirm else "The passwords do not match."
        elif not password_ready(text, confirm):
            hint = "This password is too easy to guess."
        else:
            hint = "Ready – your image will be encrypted locally."
        ready = self.image is not None and password_ready(text, confirm)
        self.encrypt_btn.setEnabled(ready and interactive)
        self.hint.setText(hint)
        self.copy_btn.setEnabled(bool(text))

    def _set_interactive(self, on: bool) -> None:
        # Lock controls only; disabling the whole panel would grey out the image preview.
        self.form.setEnabled(on)
        self.drop.setEnabled(on)
        self.replace_btn.setEnabled(on)
        self.remove_btn.setEnabled(on)

    # ------------------------------------------------------------------ image selection
    def load_file(self, path: str) -> None:
        if self.state == self.RUNNING:
            self.ctx.toast("warning", "Please wait", "An encryption is already in progress.")
            return
        if self.has_unsaved_work() and not self._confirm_discard():
            return
        try:
            info = inspect_image(path)
        except CipherPixelError as exc:
            self.ctx.toast("error", "Can't use this file", exc.user_message)
            return
        self._discard_output()
        self.image = info
        self.state = self.READY
        self._show("form")
        self.preview.load(path)
        self.t_name.set_value(info.name)
        self.t_dims.set_value(f"{info.width} × {info.height} px")
        self.t_size.set_value(human_size(info.size))
        self.t_format.set_value({"JPEG": "JPEG", "TIFF": "TIFF"}.get(info.format, info.format))
        self.left_stack.setCurrentIndex(1)
        self._refresh()
        self.pw.setFocus()

    def _remove_image(self) -> None:
        if self.state == self.RUNNING:
            return
        self.image = None
        self.preview.clear()
        self.left_stack.setCurrentIndex(0)
        self.state = self.IDLE
        self._refresh()

    # ------------------------------------------------------------------ password helpers
    def _generate(self) -> None:
        password = generate_password(20)
        self.pw.setText(password)
        self.pw2.setText(password)
        self.pw.set_revealed(True)
        self.ctx.toast("info", "Secure password generated",
                       "Copy it into a password manager before encrypting – it can't be recovered.")

    def _copy(self) -> None:
        text = self.pw.text()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        clear = bool(self.ctx.settings.get("clear_clipboard"))
        self.ctx.toast("info", "Password copied", "The clipboard will be cleared in 30 seconds." if clear else "")
        if clear:
            QTimer.singleShot(CLIPBOARD_CLEAR_MS, lambda t=text: self._clear_clipboard(t))

    @staticmethod
    def _clear_clipboard(copied: str) -> None:
        cb = QGuiApplication.clipboard()
        if cb.text() == copied:
            cb.clear()

    # ------------------------------------------------------------------ encryption flow
    def _start(self) -> None:
        if self.image is None or self.state == self.RUNNING:
            return
        try:
            validate_new_password(self.pw.text(), self.pw2.text())
        except WeakPasswordError as exc:
            self.ctx.toast("warning", "Check your password", exc.user_message)
            return
        self._discard_output()
        self._out_path = self.ctx.temp.new_path(".cpx")
        kdf = self.kdf_sel.params()
        self.state = self.RUNNING
        self._set_interactive(False)
        self.progress.start("Encrypting image", kdf.name)
        self._show("progress")

        worker = TaskWorker(encrypt_file, self.image.path, self._out_path, self.pw.text(), kdf=kdf, parent=self)
        self._worker = worker
        worker.progress.connect(self.progress.set_progress)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        self.run_worker(worker)

    def _cancel(self) -> None:
        if self._worker is not None:
            self.progress.cancel_button.setEnabled(False)
            self.progress.stage.setText("Cancelling…")
            self._worker.cancel()

    def _on_success(self, res: EncryptionResult) -> None:
        self._worker = None
        self.state = self.DONE
        self.result = res
        self.progress.finish()
        self.ctx.record(ENCRYPT, res.original_name, res.image_format, res.input_size, SUCCESS)
        self.pw.clear()
        self.pw2.clear()
        self.r_name.set_value(suggested_output_name(res.original_name))
        self.r_orig.set_value(human_size(res.input_size))
        self.r_enc.set_value(f"{human_size(res.output_size)}  ({res.chunk_count} authenticated chunk{'' if res.chunk_count == 1 else 's'})")
        self.r_kdf.set_value(res.kdf.describe())
        self.r_time.set_value(f"{res.duration_s:.2f} s")
        self.r_hash.set_value(res.sha256[:16] + "…")
        self.save.configure(res.output_path, suggested_output_name(res.original_name), CPX_FILTER,
                            "Save encrypted file")
        self._set_interactive(True)
        self.replace_btn.setEnabled(False)  # image already processed; use "Encrypt Another"
        self.remove_btn.setEnabled(False)
        self._show("result")
        self._refresh()
        self.ctx.toast("success", "Encryption complete", f"{res.original_name} is now protected.")

    def _on_failed(self, message: str, kind: str) -> None:
        self._worker = None
        if self.image is not None:
            self.ctx.record(ENCRYPT, self.image.name, self.image.format, self.image.size, FAILED)
        self._discard_output()
        self.state = self.READY if self.image else self.IDLE
        self._set_interactive(True)
        self._show("form")
        self._refresh()
        self.ctx.toast("error", "Encryption failed", message)

    def _on_cancelled(self) -> None:
        self._worker = None
        self._discard_output()
        self.state = self.READY if self.image else self.IDLE
        self._set_interactive(True)
        self._show("form")
        self._refresh()
        self.ctx.toast("info", "Encryption cancelled", "No file was created.")

    # ------------------------------------------------------------------ cleanup / reset
    def _discard_output(self) -> None:
        self.ctx.temp.remove(self._out_path)
        self._out_path = None
        self.result = None

    def has_unsaved_work(self) -> bool:
        return self.state == self.DONE and self.save.saved_path is None

    def _confirm_discard(self) -> bool:
        return dialogs.confirm(
            self, "Discard encrypted file?",
            "You haven't saved the encrypted file yet. If you continue it will be deleted and you will "
            "need to encrypt the image again.", "Discard", danger=True)

    def _encrypt_another(self) -> None:
        if self.save.is_saving():
            return
        if self.has_unsaved_work() and not self._confirm_discard():
            return
        self.reset()

    def reset(self) -> None:
        self._discard_output()
        self.image = None
        self.preview.clear()
        self.left_stack.setCurrentIndex(0)
        self.pw.clear()
        self.pw2.clear()
        self.state = self.IDLE
        self._show("form")
        self._set_interactive(True)
        self._refresh()

    def shutdown(self) -> None:
        super().shutdown()
        self.save.wait()
