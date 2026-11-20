"""Theme-aware icons (Font Awesome via qtawesome) that recolour when the theme changes."""

from __future__ import annotations

import weakref

import qtawesome as qta
from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QAbstractButton, QLabel

from .theme import theme

# widget -> (icon name, colour role, "on" colour role, pixel size)
_registry: "weakref.WeakKeyDictionary[object, tuple]" = weakref.WeakKeyDictionary()


def make_icon(name: str, role: str = "text2", on_role: str | None = None) -> QIcon:
    kwargs = {"color": theme.color(role)}
    if on_role:
        kwargs["color_on"] = theme.color(on_role)
        kwargs["color_active"] = theme.color(on_role)
    return qta.icon(name, **kwargs)


def _apply(widget, name: str, role: str, on_role: str | None, size: int) -> None:
    icon = make_icon(name, role, on_role)
    if isinstance(widget, QLabel):
        widget.setPixmap(icon.pixmap(QSize(size, size)))
    else:
        widget.setIcon(icon)
        if isinstance(widget, QAbstractButton):
            widget.setIconSize(QSize(size, size))


def bind_icon(widget: QAbstractButton | QLabel | QAction, name: str, role: str = "text2",
              on_role: str | None = None, size: int = 16) -> None:
    """Attach an icon and remember it so :func:`refresh_icons` can recolour it."""
    _registry[widget] = (name, role, on_role, size)
    _apply(widget, name, role, on_role, size)


def refresh_icons() -> None:
    for widget, (name, role, on_role, size) in list(_registry.items()):
        try:
            _apply(widget, name, role, on_role, size)
        except RuntimeError:  # underlying C++ object already deleted
            pass


theme.changed.connect(lambda _name: refresh_icons())
