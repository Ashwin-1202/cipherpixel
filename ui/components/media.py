"""Image preview, animated progress panel, toast notifications and fade-in page stack."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..icons import bind_icon
from ..theme import set_prop
from .basics import Card, button, label

MAX_PREVIEW_EDGE = 1600


class ImagePreview(QFrame):
    """Aspect-ratio-preserving preview.  Decodes a *downscaled* copy so large images stay cheap."""

    def __init__(self, placeholder: str = "No image selected", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PreviewBox")
        self.setMinimumHeight(280)
        self._pix: QPixmap | None = None
        self._placeholder = placeholder
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        self._label = QLabel(placeholder)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setProperty("role", "muted")
        self._label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._label.setMinimumSize(10, 10)
        lay.addWidget(self._label)

    def load(self, path: str) -> bool:
        reader = QImageReader(path)
        reader.setDecideFormatFromContent(True)  # temp files have no meaningful extension
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and max(size.width(), size.height()) > MAX_PREVIEW_EDGE:
            size.scale(MAX_PREVIEW_EDGE, MAX_PREVIEW_EDGE, Qt.KeepAspectRatio)
            reader.setScaledSize(size)
        image = reader.read()
        if image.isNull():
            self.clear("Preview unavailable for this image")
            return False
        self._pix = QPixmap.fromImage(image)
        self._label.setText("")
        self._refresh()
        return True

    def clear(self, text: str | None = None) -> None:
        self._pix = None
        self._label.setPixmap(QPixmap())
        self._label.setText(text or self._placeholder)

    def has_image(self) -> bool:
        return self._pix is not None

    def _refresh(self) -> None:
        if self._pix is None:
            return
        target = self._label.size()
        self._label.setPixmap(self._pix.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()


STAGE_TEXT = {
    "validating": "Validating image…",
    "deriving_key": "Deriving encryption key…",
    "encrypting": "Encrypting with AES-256-GCM…",
    "decrypting": "Decrypting and authenticating…",
    "verifying": "Verifying integrity…",
    "finalizing": "Finalizing…",
    "saving": "Saving file…",
}


class ProgressPanel(Card):
    """Animated progress with stage text and a cancel button."""

    cancelRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=24, spacing=14)
        top = QHBoxLayout()
        self.title = label("Working…", "h2")
        self.percent = label("0%", "h3")
        top.addWidget(self.title, 1)
        top.addWidget(self.percent)
        self.body.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.body.addWidget(self.bar)
        self.stage = label("", "muted")
        self.body.addWidget(self.stage)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = button("Cancel", "ghost", "fa5s.times")
        self.cancel_button.clicked.connect(self.cancelRequested)
        row.addWidget(self.cancel_button)
        self.body.addLayout(row)
        self._anim = QPropertyAnimation(self.bar, b"value", self)
        self._kdf_text = ""

    def start(self, title: str, kdf_text: str = "") -> None:
        self._anim.stop()
        self.bar.setValue(0)
        self.percent.setText("0%")
        self.title.setText(title)
        self._kdf_text = kdf_text
        self.stage.setText(STAGE_TEXT["validating"])
        self.cancel_button.setEnabled(True)

    def set_progress(self, stage: str, fraction: float) -> None:
        text = STAGE_TEXT.get(stage, stage)
        if stage == "deriving_key" and self._kdf_text:
            text = f"Deriving encryption key ({self._kdf_text})…"
        self.stage.setText(text)
        self._anim.stop()
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        if stage == "deriving_key":
            # Key derivation is one long blocking call: creep forward so the bar never looks frozen.
            target, duration = int((fraction + 0.10) * 1000), 2800
        else:
            target, duration = int(fraction * 1000), 160
        self._anim.setDuration(duration)
        self._anim.setStartValue(self.bar.value())
        self._anim.setEndValue(max(target, self.bar.value()))
        self._anim.start()
        self.percent.setText(f"{int(fraction * 100)}%")

    def finish(self) -> None:
        self._anim.stop()
        self.bar.setValue(1000)
        self.percent.setText("100%")


class _Toast(QFrame):
    closed = Signal(object)

    def __init__(self, kind: str, title: str, message: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setFixedWidth(360)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 10, 12)
        lay.setSpacing(12)
        accent = QFrame()
        accent.setObjectName("ToastAccent")
        accent.setProperty("kind", kind)
        lay.addWidget(accent)
        icon_name, role = {
            "success": ("fa5s.check-circle", "success"),
            "error": ("fa5s.times-circle", "error"),
            "warning": ("fa5s.exclamation-triangle", "warning"),
        }.get(kind, ("fa5s.info-circle", "primary"))
        icon = QLabel()
        bind_icon(icon, icon_name, role, size=20)
        lay.addWidget(icon, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title, "h3", wrap=True))
        if message:
            text.addWidget(label(message, "muted", wrap=True))
        lay.addLayout(text, 1)
        close = QToolButton()
        close.setCursor(Qt.PointingHandCursor)
        bind_icon(close, "fa5s.times", "muted", size=12)
        close.clicked.connect(self.dismiss)
        lay.addWidget(close, 0, Qt.AlignTop)

        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(0.0)
        self._fade = QPropertyAnimation(self._fx, b"opacity", self)
        self._fade.setDuration(180)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._dismissing = False
        self.adjustSize()

    def pop(self, timeout_ms: int) -> None:
        self.show()
        self.raise_()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(timeout_ms)

    def dismiss(self) -> None:
        if self._dismissing:
            return
        self._dismissing = True
        self._timer.stop()
        self._fade.stop()
        self._fade.setStartValue(self._fx.opacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(lambda: self.closed.emit(self))
        self._fade.start()


class ToastHost(QObject):
    """Stacks toast notifications in the bottom-right corner of ``window``."""

    MARGIN = 22
    GAP = 10

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._toasts: list[_Toast] = []
        window.installEventFilter(self)

    def show(self, kind: str, title: str, message: str = "", timeout_ms: int | None = None) -> None:
        toast = _Toast(kind, title, message, self._window)
        toast.closed.connect(self._remove)
        self._toasts.append(toast)
        if len(self._toasts) > 4:
            self._toasts[0].dismiss()
        toast.adjustSize()
        self._layout()
        toast.pop(timeout_ms or (7000 if kind == "error" else 4200))

    def _remove(self, toast: _Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        toast.hide()
        toast.deleteLater()
        self._layout()

    def _layout(self) -> None:
        y = self._window.height() - self.MARGIN
        for toast in reversed(self._toasts):
            toast.adjustSize()
            y -= toast.height()
            toast.move(QPoint(self._window.width() - toast.width() - self.MARGIN, y))
            toast.raise_()
            y -= self.GAP

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._window and event.type() == QEvent.Resize:
            self._layout()
        return False

    def clear(self) -> None:
        for t in list(self._toasts):
            self._remove(t)


class FadeStack(QStackedWidget):
    """Stacked widget with a short fade-in when the page changes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._anim: QPropertyAnimation | None = None

    def fade_to(self, index: int) -> None:
        if index == self.currentIndex():
            return
        self.setCurrentIndex(index)
        page = self.currentWidget()
        if page is None:
            return
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(170)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda p=page: p.setGraphicsEffect(None))
        self._anim = anim
        anim.start()
