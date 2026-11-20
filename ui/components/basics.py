"""Small building blocks: labels, buttons, cards, badges, stat cards, empty states."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..icons import bind_icon
from ..theme import set_prop


def label(text: str = "", role: str | None = None, *, wrap: bool = False, selectable: bool = False,
          align: Qt.AlignmentFlag | None = None) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if align is not None:
        lb.setAlignment(align)
    return lb


def button(text: str = "", variant: str = "secondary", icon: str | None = None, *, tooltip: str | None = None,
           size: str | None = None, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(("  " + text) if (icon and text) else text, parent)  # gap between icon and label
    b.setProperty("variant", variant)
    if size:
        b.setProperty("size", size)
    b.setCursor(Qt.PointingHandCursor)
    if icon:
        bind_icon(b, icon, "on_primary" if variant in ("primary",) else ("error" if variant == "danger" else "text"),
                  size=16 if size != "lg" else 18)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line


class Card(QFrame):
    """Rounded surface.  Add content through :attr:`body`."""

    def __init__(self, parent: QWidget | None = None, *, padding: int = 22, spacing: int = 14) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)

    def set_tone(self, tone: str | None) -> None:
        set_prop(self, "tone", tone or "")


class Badge(QLabel):
    def __init__(self, text: str = "", kind: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        set_prop(self, "badge", kind)


class IconBadge(QLabel):
    """Rounded square with a tinted background and a coloured icon."""

    def __init__(self, icon_name: str, accent: str = "primary", size: int = 44, icon_size: int = 20,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("iconBadge", True)
        self.setProperty("accent", accent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        bind_icon(self, icon_name, accent, size=icon_size)

    def set_icon(self, icon_name: str, accent: str) -> None:
        set_prop(self, "accent", accent)
        bind_icon(self, icon_name, accent, size=20)


class StatCard(Card):
    def __init__(self, icon_name: str, title: str, value: str, caption: str = "", accent: str = "primary",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=20, spacing=10)
        top = QHBoxLayout()
        top.addWidget(IconBadge(icon_name, accent))
        top.addStretch(1)
        self.body.addLayout(top)
        self.title = label(title, "muted")
        self.value = label(value, "value")
        self.caption = label(caption, "caption")
        self.body.addWidget(self.title)
        self.body.addWidget(self.value)
        if caption:
            self.body.addWidget(self.caption)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class SectionHeader(QWidget):
    """Title + optional subtitle on the left, optional widget(s) on the right."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = label(title, "h2")
        text.addWidget(self.title)
        if subtitle:
            self.subtitle = label(subtitle, "muted", wrap=True)
            text.addWidget(self.subtitle)
        lay.addLayout(text, 1)
        self.right = QHBoxLayout()
        self.right.setSpacing(8)
        lay.addLayout(self.right)


class InfoTile(QFrame):
    """Compact 'caption + value' tile used for file facts."""

    def __init__(self, caption: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InfoTile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(3)
        self._caption = label(caption.upper(), "caption")
        self._value = label(value, "h3")
        self._value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self._caption)
        lay.addWidget(self._value)

    def set_value(self, value: str, tooltip: str | None = None) -> None:
        self._value.setText(value)
        self.setToolTip(tooltip if tooltip is not None else value)


class KeyValueRow(QWidget):
    def __init__(self, key: str, value: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self.key = label(key, "muted")
        self.value = label(value)
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value.setWordWrap(True)
        lay.addWidget(self.key)
        lay.addWidget(self.value, 1)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class EmptyState(QWidget):
    actionClicked = Signal()

    def __init__(self, icon_name: str, title: str, text: str, action: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)
        lay.setContentsMargins(20, 36, 20, 36)
        self.icon = IconBadge(icon_name, "primary", size=64, icon_size=28)
        lay.addWidget(self.icon, 0, Qt.AlignHCenter)
        lay.addSpacing(6)
        self.title = label(title, "h2", align=Qt.AlignCenter)
        self.text = label(text, "muted", wrap=True, align=Qt.AlignCenter)
        self.text.setMaximumWidth(420)
        lay.addWidget(self.title)
        lay.addWidget(self.text, 0, Qt.AlignHCenter)
        if action:
            self.button = button(action, "primary")
            self.button.clicked.connect(self.actionClicked)
            lay.addSpacing(8)
            lay.addWidget(self.button, 0, Qt.AlignHCenter)


class ResponsiveRow(QWidget):
    """Lays children out side by side, stacking them vertically below ``breakpoint`` px."""

    def __init__(self, breakpoint: int = 900, spacing: int = 20, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bp = breakpoint
        self._lay = QBoxLayout(QBoxLayout.LeftToRight, self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(spacing)

    def add(self, widget: QWidget, stretch: int = 1) -> None:
        self._lay.addWidget(widget, stretch)

    def resizeEvent(self, event) -> None:  # noqa: N802
        direction = QBoxLayout.LeftToRight if event.size().width() >= self._bp else QBoxLayout.TopToBottom
        if self._lay.direction() != direction:
            self._lay.setDirection(direction)
        super().resizeEvent(event)


class ReflowGrid(QWidget):
    """Grid whose column count adapts to width: ``columns = [(min_width, n), ...]``."""

    def __init__(self, columns: list[tuple[int, int]], spacing: int = 16, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rules = sorted(columns, reverse=True)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)
        self._items: list[QWidget] = []
        self._cols = 0

    def add(self, widget: QWidget) -> None:
        self._items.append(widget)
        self._reflow(self._cols or self._rules[0][1], force=True)

    def _columns_for(self, width: int) -> int:
        for min_w, n in self._rules:
            if width >= min_w:
                return n
        return self._rules[-1][1]

    def _reflow(self, cols: int, force: bool = False) -> None:
        if cols == self._cols and not force:
            return
        self._cols = cols
        while self._grid.count():
            self._grid.takeAt(0)
        for i, w in enumerate(self._items):
            self._grid.addWidget(w, i // cols, i % cols)
        for c in range(max(cols, 6)):
            self._grid.setColumnStretch(c, 1 if c < cols else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._reflow(self._columns_for(event.size().width()))
        super().resizeEvent(event)
