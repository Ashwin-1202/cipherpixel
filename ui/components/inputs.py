"""Password field, strength meter and drag-and-drop zone."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from core.security_utils import estimate_strength

from ..icons import bind_icon
from ..theme import set_prop
from .basics import IconBadge, button, label


class PasswordField(QLineEdit):
    """Password input with an inline show/hide toggle."""

    revealedChanged = Signal(bool)

    def __init__(self, placeholder: str = "Password", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(False)
        self.setAttribute(Qt.WA_MacShowFocusRect, False)
        self._toggle = QAction(self)
        self._toggle.setToolTip("Show password")
        self._toggle.triggered.connect(lambda: self.set_revealed(not self.is_revealed()))
        bind_icon(self._toggle, "fa5s.eye", "text2")
        self.addAction(self._toggle, QLineEdit.TrailingPosition)

    def is_revealed(self) -> bool:
        return self.echoMode() == QLineEdit.Normal

    def set_revealed(self, revealed: bool) -> None:
        if revealed == self.is_revealed():
            return  # also stops signal ping-pong between linked fields
        self.setEchoMode(QLineEdit.Normal if revealed else QLineEdit.Password)
        bind_icon(self._toggle, "fa5s.eye-slash" if revealed else "fa5s.eye", "text2")
        self._toggle.setToolTip("Hide password" if revealed else "Show password")
        self.revealedChanged.emit(revealed)

    def set_invalid(self, invalid: bool) -> None:
        set_prop(self, "invalid", invalid)


class StrengthMeter(QWidget):
    """Four-segment strength bar with a label and short feedback text."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(5)
        self._segs: list[QFrame] = []
        for _ in range(4):
            seg = QFrame()
            seg.setObjectName("Seg")
            seg.setProperty("fill", "off")
            self._segs.append(seg)
            row.addWidget(seg, 1)
        self._label = label("", "muted")
        self._label.setMinimumWidth(120)
        self._label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addSpacing(8)
        row.addWidget(self._label)
        outer.addLayout(row)
        self._feedback = label("", "muted", wrap=True)
        outer.addWidget(self._feedback)
        self.update_for("")

    def update_for(self, password: str) -> None:
        s = estimate_strength(password)
        lit = 0 if not password else max(1, s.score)
        tone = {0: "bad", 1: "bad", 2: "fair", 3: "good", 4: "great"}[s.score]
        for i, seg in enumerate(self._segs):
            set_prop(seg, "fill", tone if i < lit else "off")
        self._label.setText(f"{s.label} · {s.entropy_bits:.0f} bits" if password else "")
        self._feedback.setText(s.feedback if password else "Use 12+ characters with letters, numbers and symbols.")


class DropZone(QFrame):
    """Large drag-and-drop target that also opens a file dialog.

    Accepts *any* dropped local file and lets the page validate it, so the user always
    gets a clear error message instead of a silently ignored drop.
    """

    fileSelected = Signal(str)

    def __init__(self, title: str, subtitle: str, icon_name: str, dialog_title: str, dialog_filter: str,
                 button_text: str = "Browse Files", start_dir=lambda: os.path.expanduser("~"),
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(300)
        self.setCursor(Qt.PointingHandCursor)
        self._dialog_title = dialog_title
        self._dialog_filter = dialog_filter
        self._start_dir = start_dir

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)
        lay.addWidget(IconBadge(icon_name, "primary", size=72, icon_size=32), 0, Qt.AlignHCenter)
        lay.addSpacing(6)
        lay.addWidget(label(title, "h2", align=Qt.AlignCenter))
        sub = label(subtitle, "muted", wrap=True, align=Qt.AlignCenter)
        sub.setMaximumWidth(380)
        lay.addWidget(sub, 0, Qt.AlignHCenter)
        lay.addSpacing(8)
        self.browse_button = button(button_text, "primary", "fa5s.folder-open")
        self.browse_button.clicked.connect(self.browse)
        lay.addWidget(self.browse_button, 0, Qt.AlignHCenter)

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self._dialog_title, self._start_dir(), self._dialog_filter)
        if path:
            self.fileSelected.emit(path)

    # ---- drag & drop ---------------------------------------------------------
    def _local_files(self, event) -> list[str]:
        md = event.mimeData()
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile()] if md.hasUrls() else []

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._local_files(event):
            set_prop(self, "dragActive", True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        set_prop(self, "dragActive", False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        set_prop(self, "dragActive", False)
        files = self._local_files(event)
        if files:
            event.acceptProposedAction()
            self.fileSelected.emit(files[0])

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.browse()
        super().mouseReleaseEvent(event)
