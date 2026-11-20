"""Decrypt Image workspace."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from core.decryption import ContainerInfo, DecryptionResult, decrypt_file, read_container_info
from core.errors import AuthenticationError, CipherPixelError
from core.file_handler import CPX_FILTER, IMAGE_FILTER
from core.history import DECRYPT, FAILED, SUCCESS
from core.security_utils import human_size

from . import dialogs
from .base_page import BasePage
from .components.basics import Badge, Card, IconBadge, InfoTile, KeyValueRow, ResponsiveRow, SectionHeader, button, label
from .components.inputs import DropZone, PasswordField
from .components.media import ImagePreview, ProgressPanel
from .components.save import SaveControl
from .context import AppContext
from .theme import set_prop
from .workers import TaskWorker


class DecryptPage(BasePage):
    key = "decrypt"
    title = "Decrypt Image"
    crumbs = ["Decrypt Image"]

    IDLE, READY, RUNNING, DONE = range(4)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.state = self.IDLE
        self.info: ContainerInfo | None = None
        self.result: DecryptionResult | None = None
        self._out_path: str | None = None
        self._worker: TaskWorker | None = None

        self.body.addWidget(label(
            "Restore an image from a CipherPixel (.cpx) file. The file is fully authenticated before any "
            "image is produced.", "muted", wrap=True))
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
        card.body.addWidget(SectionHeader("Encrypted file", "Select the .cpx file you want to unlock"))
        self.left_stack = QStackedWidget()

        self.drop = DropZone(
            "Drag & drop an encrypted file here",
            "Only files created by CipherPixel (.cpx) can be opened.",
            "fa5s.file-archive", "Select encrypted file", CPX_FILTER, "Browse Encrypted File",
            start_dir=lambda: self.ctx.settings.export_dir)
        self.drop.fileSelected.connect(self.load_file)
        self.left_stack.addWidget(self.drop)

        ready = QWidget()
        rl = QVBoxLayout(ready)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(14)

        banner = QHBoxLayout()
        banner.setSpacing(14)
        banner.addWidget(IconBadge("fa5s.lock", "primary", size=56, icon_size=26))
        txt = QVBoxLayout()
        txt.setSpacing(2)
        self.f_name = label("", "h2")
        self.f_name.setWordWrap(True)
        txt.addWidget(self.f_name)
        txt.addWidget(Badge("Encrypted · password required", "info"), 0, Qt.AlignLeft)
        banner.addLayout(txt, 1)
        rl.addLayout(banner)

        tiles = QGridLayout()
        tiles.setSpacing(10)
        self.t_size, self.t_ver = InfoTile("File size"), InfoTile("Format version")
        self.t_kdf, self.t_chunk = InfoTile("Key derivation"), InfoTile("Chunk size")
        for i, t in enumerate((self.t_size, self.t_ver, self.t_kdf, self.t_chunk)):
            tiles.addWidget(t, i // 2, i % 2)
        tiles.setColumnStretch(0, 1)
        tiles.setColumnStretch(1, 1)
        rl.addLayout(tiles)

        actions = QHBoxLayout()
        self.replace_btn = button("Choose another file", "secondary", "fa5s.sync")
        self.replace_btn.clicked.connect(self.drop.browse)
        actions.addWidget(self.replace_btn)
        actions.addStretch(1)
        rl.addLayout(actions)
        rl.addStretch(1)
        self.left_stack.addWidget(ready)

        card.body.addWidget(self.left_stack)
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

        card = Card()
        card.body.addWidget(SectionHeader("Password", "Enter the password used when the image was encrypted"))
        self.pw = PasswordField("Enter password")
        self.pw.returnPressed.connect(self._start)
        card.body.addWidget(self.pw)
        self.error_box = label("", wrap=True)
        self.error_box.setObjectName("ErrorText")
        self.error_box.hide()
        card.body.addWidget(self.error_box)
        fv.addWidget(card)

        self.decrypt_btn = button("DECRYPT IMAGE", "primary", "fa5s.lock-open", size="lg",
                                  tooltip="Authenticate and decrypt the selected file")
        self.decrypt_btn.clicked.connect(self._start)
        self.hint = label("", "muted", align=Qt.AlignCenter, wrap=True)
        fv.addWidget(self.decrypt_btn)
        fv.addWidget(self.hint)
        self.pw.textChanged.connect(self._on_pw_changed)
        v.addWidget(self.form)

        self.progress = ProgressPanel()
        self.progress.cancelRequested.connect(self._cancel)
        self.progress.hide()
        v.addWidget(self.progress)

        v.addWidget(self._build_result_card())
        v.addStretch(1)
        return holder

    def _build_result_card(self) -> Card:
        card = Card(padding=24, spacing=14)
        card.set_tone("success")
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(IconBadge("fa5s.check-circle", "success", size=54, icon_size=28))
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label("Image decrypted successfully", "h2"))
        text.addWidget(label("Authentication passed – the image is identical to the original.", "muted", wrap=True))
        head.addLayout(text, 1)
        card.body.addLayout(head)

        self.preview = ImagePreview("Recovered image")
        self.preview.setMinimumHeight(260)
        card.body.addWidget(self.preview)

        self.r_name = KeyValueRow("Original file name")
        self.r_dims = KeyValueRow("Dimensions")
        self.r_format = KeyValueRow("Format")
        self.r_size = KeyValueRow("File size")
        self.r_integrity = KeyValueRow("Integrity")
        self.r_time = KeyValueRow("Time taken")
        for r in (self.r_name, self.r_dims, self.r_format, self.r_size, self.r_integrity, self.r_time):
            card.body.addWidget(r)

        self.save = SaveControl(self.ctx, "Export Image", "fa5s.file-export")
        card.body.addWidget(self.save)
        self.another_btn = button("Open Another File", "secondary", "fa5s.folder-open")
        self.another_btn.clicked.connect(self._open_another)
        card.body.addWidget(self.another_btn)
        card.hide()
        self.result_card = card
        return card

    # ------------------------------------------------------------------ state / helpers
    def _apply_defaults(self) -> None:
        if not self.pw.text():
            self.pw.set_revealed(bool(self.ctx.settings.get("show_password_default")))

    def _on_setting_changed(self, key: str) -> None:
        if key == "show_password_default" and self.state != self.RUNNING:
            self._apply_defaults()

    def _show(self, which: str) -> None:
        self.form.setVisible(which == "form")
        self.progress.setVisible(which == "progress")
        self.result_card.setVisible(which == "result")

    def _on_pw_changed(self) -> None:
        self._clear_error()
        self._refresh()

    def _clear_error(self) -> None:
        self.error_box.hide()
        self.pw.set_invalid(False)

    def _show_error(self, message: str) -> None:
        self.error_box.setText(message)
        self.error_box.show()
        self.pw.set_invalid(True)

    def _refresh(self) -> None:
        interactive = self.state in (self.IDLE, self.READY)
        if self.info is None:
            hint = "Select an encrypted file to continue."
        elif not self.pw.text():
            hint = "Enter the password to unlock this file."
        else:
            hint = "Ready – decryption happens locally on this computer."
        self.decrypt_btn.setEnabled(bool(self.info and self.pw.text()) and interactive)
        self.hint.setText(hint)

    def _set_interactive(self, on: bool) -> None:
        self.form.setEnabled(on)
        self.drop.setEnabled(on)
        self.replace_btn.setEnabled(on)

    # ------------------------------------------------------------------ file selection
    def load_file(self, path: str) -> None:
        if self.state == self.RUNNING:
            self.ctx.toast("warning", "Please wait", "A decryption is already in progress.")
            return
        if self.has_unsaved_work() and not self._confirm_discard():
            return
        if not path.lower().endswith(".cpx"):
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")):
                self.ctx.toast("error", "This is an image, not an encrypted file",
                               "Use the Encrypt Image page to protect it, or choose a .cpx file here.")
            else:
                self.ctx.toast("error", "Unsupported file", "Choose a CipherPixel encrypted file (.cpx).")
            return
        try:
            info = read_container_info(path)
        except CipherPixelError as exc:
            self.ctx.record(DECRYPT, os.path.basename(path), "cpx", self._safe_size(path), FAILED)
            self.ctx.toast("error", "Can't open this file", exc.user_message)
            return
        self._discard_output()
        self.info = info
        self.state = self.READY
        self.f_name.setText(os.path.basename(path))
        self.t_size.set_value(human_size(info.file_size))
        self.t_ver.set_value(f"v{info.version}")
        self.t_kdf.set_value(info.kdf.name, info.kdf.describe())
        self.t_chunk.set_value(human_size(info.chunk_size))
        self.left_stack.setCurrentIndex(1)
        self.pw.clear()
        self._clear_error()
        self._show("form")
        self._refresh()
        self.pw.setFocus()

    @staticmethod
    def _safe_size(path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    # ------------------------------------------------------------------ decryption flow
    def _start(self) -> None:
        if self.info is None or not self.pw.text() or self.state == self.RUNNING:
            return
        self._clear_error()
        self._discard_output()
        self._out_path = self.ctx.temp.new_path(".img")
        self.state = self.RUNNING
        self._set_interactive(False)
        self.progress.start("Decrypting image", self.info.kdf.name)
        self._show("progress")

        worker = TaskWorker(decrypt_file, self.info.path, self._out_path, self.pw.text(), parent=self)
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

    def _on_success(self, res: DecryptionResult) -> None:
        self._worker = None
        self.state = self.DONE
        self.result = res
        self.progress.finish()
        self.ctx.record(DECRYPT, os.path.basename(self.info.path), "cpx", self.info.file_size, SUCCESS)
        self.pw.clear()
        self.preview.load(res.output_path)
        self.r_name.set_value(res.original_name)
        self.r_dims.set_value(f"{res.width} × {res.height} px")
        self.r_format.set_value(res.image_format)
        self.r_size.set_value(human_size(res.output_size))
        self.r_integrity.set_value("✓ Verified (AES-GCM tags + SHA-256)")
        self.r_time.set_value(f"{res.duration_s:.2f} s")
        self.save.configure(res.output_path, res.suggested_filename, IMAGE_FILTER, "Export recovered image")
        self._set_interactive(True)
        self.replace_btn.setEnabled(False)  # use "Open Another File" instead
        self._show("result")
        self._refresh()
        self.ctx.toast("success", "Decryption complete", f"{res.original_name} was restored.")

    def _on_failed(self, message: str, kind: str) -> None:
        self._worker = None
        if self.info is not None:
            self.ctx.record(DECRYPT, os.path.basename(self.info.path), "cpx", self.info.file_size, FAILED)
        self._discard_output()
        self.state = self.READY if self.info else self.IDLE
        self._set_interactive(True)
        self._show("form")
        self._show_error(message)
        self._refresh()
        self.ctx.toast("error", "Decryption failed", message)
        self.pw.selectAll()
        self.pw.setFocus()

    def _on_cancelled(self) -> None:
        self._worker = None
        self._discard_output()
        self.state = self.READY if self.info else self.IDLE
        self._set_interactive(True)
        self._show("form")
        self._refresh()
        self.ctx.toast("info", "Decryption cancelled", "No image was created.")

    # ------------------------------------------------------------------ cleanup / reset
    def _discard_output(self) -> None:
        self.preview.clear()
        self.ctx.temp.remove(self._out_path)
        self._out_path = None
        self.result = None

    def has_unsaved_work(self) -> bool:
        return self.state == self.DONE and self.save.saved_path is None

    def _confirm_discard(self) -> bool:
        return dialogs.confirm(
            self, "Discard recovered image?",
            "You haven't exported the recovered image yet. If you continue it will be deleted and you will "
            "need to decrypt the file again.", "Discard", danger=True)

    def _open_another(self) -> None:
        if self.save.is_saving():
            return
        if self.has_unsaved_work() and not self._confirm_discard():
            return
        self.reset()
        self.drop.browse()

    def reset(self) -> None:
        self._discard_output()
        self.info = None
        self.left_stack.setCurrentIndex(0)
        self.pw.clear()
        self._clear_error()
        self.state = self.IDLE
        self._show("form")
        self._set_interactive(True)
        self._refresh()

    def shutdown(self) -> None:
        super().shutdown()
        self.save.wait()
