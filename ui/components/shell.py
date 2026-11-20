"""Application shell widgets: sidebar and top navigation bar."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..icons import bind_icon, make_icon
from ..theme import set_prop, theme
from .basics import label

NAV_ITEMS: list[tuple[str, str, str]] = [
    ("overview", "Overview", "fa5s.home"),
    ("encrypt", "Encrypt Image", "fa5s.lock"),
    ("decrypt", "Decrypt Image", "fa5s.lock-open"),
    ("history", "File History", "fa5s.history"),
    ("security", "Security Center", "fa5s.shield-alt"),
    ("settings", "Settings", "fa5s.cog"),
    ("about", "About", "fa5s.info-circle"),
]

EXPANDED_WIDTH = 252
COMPACT_WIDTH = 78


class Sidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, version: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._compact = False
        self._buttons: dict[str, QPushButton] = {}
        self._labels: dict[str, str] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(4)

        # brand
        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = QFrame()
        logo.setObjectName("Logo")
        logo.setFixedSize(40, 40)
        ll = QVBoxLayout(logo)
        ll.setContentsMargins(0, 0, 0, 0)
        glyph = QLabel()
        glyph.setAlignment(Qt.AlignCenter)
        bind_icon(glyph, "fa5s.lock", "on_primary", size=18)
        ll.addWidget(glyph)
        self._brand_text = QWidget()
        bt = QVBoxLayout(self._brand_text)
        bt.setContentsMargins(0, 0, 0, 0)
        bt.setSpacing(0)
        name = label("CipherPixel", "h2")
        tag = label("Advanced Image Security", "muted")
        tag.setStyleSheet("font-size: 11px;")
        bt.addWidget(name)
        bt.addWidget(tag)
        brand.addWidget(logo)
        brand.addWidget(self._brand_text, 1)
        lay.addLayout(brand)
        lay.addSpacing(22)

        self._section = label("MENU", "caption")
        lay.addWidget(self._section)
        lay.addSpacing(4)

        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, text, icon in NAV_ITEMS:
            if key == "settings":
                lay.addSpacing(10)
            btn = QPushButton(text)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(text)
            bind_icon(btn, icon, "text2", on_role="primary", size=18)
            btn.clicked.connect(lambda _c=False, k=key: self.navigate.emit(k))
            group.addButton(btn)
            self._buttons[key] = btn
            self._labels[key] = text
            lay.addWidget(btn)
        lay.addStretch(1)

        self._foot = QFrame()
        self._foot.setObjectName("SidebarFoot")
        fl = QVBoxLayout(self._foot)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.setSpacing(2)
        fl.addWidget(label("AES-256-GCM", "h3"))
        fl.addWidget(label("Authenticated encryption", "muted"))
        fl.addWidget(label(f"Version {version}", "caption"))
        lay.addWidget(self._foot)
        self.set_compact(False)

    def set_active(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setFixedWidth(COMPACT_WIDTH if compact else EXPANDED_WIDTH)
        self._brand_text.setVisible(not compact)
        self._section.setVisible(not compact)
        self._foot.setVisible(not compact)
        for key, btn in self._buttons.items():
            btn.setText("" if compact else self._labels[key])
            btn.setIconSize(QSize(20, 20) if compact else QSize(18, 18))
            btn.setStyleSheet("padding: 12px 0; text-align: center;" if compact else "")

    @property
    def compact(self) -> bool:
        return self._compact


class TopBar(QFrame):
    themeToggleRequested = Signal()
    navigate = Signal(str)
    quitRequested = Signal()
    openExportFolder = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(76)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(32, 0, 24, 0)
        lay.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.setContentsMargins(0, 12, 0, 12)
        self.breadcrumb = QLabel("CipherPixel")
        self.breadcrumb.setObjectName("Breadcrumb")
        self.title = QLabel("Overview")
        self.title.setObjectName("PageTitle")
        titles.addStretch(1)
        titles.addWidget(self.breadcrumb)
        titles.addWidget(self.title)
        titles.addStretch(1)
        lay.addLayout(titles, 1)

        # security status pill
        self.pill = QFrame()
        self.pill.setObjectName("StatusPill")
        self.pill.setProperty("state", "checking")
        pl = QHBoxLayout(self.pill)
        pl.setContentsMargins(12, 6, 14, 6)
        pl.setSpacing(8)
        dot = QLabel()
        dot.setObjectName("StatusDot")
        dot.setFixedSize(8, 8)
        self.pill_text = QLabel("Verifying engine…")
        self.pill_text.setStyleSheet("font-weight: 600; font-size: 12px;")
        pl.addWidget(dot)
        pl.addWidget(self.pill_text)
        self.pill.setToolTip("Result of the automatic cryptographic self-test run at start-up")
        self.pill.setFixedHeight(32)
        lay.addWidget(self.pill, 0, Qt.AlignVCenter)

        self.theme_button = QToolButton()
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.setToolTip("Toggle light / dark theme")
        self.theme_button.setIconSize(QSize(18, 18))
        self.theme_button.clicked.connect(self.themeToggleRequested)
        lay.addWidget(self.theme_button)
        theme.changed.connect(self._on_theme_changed)  # bound QObject slot: auto-disconnects on delete
        self._refresh_theme_icon()

        self.profile_button = QToolButton()
        self.profile_button.setCursor(Qt.PointingHandCursor)
        self.profile_button.setToolTip("Preferences and application menu")
        self.profile_button.setPopupMode(QToolButton.InstantPopup)
        self.profile_button.setIconSize(QSize(24, 24))
        bind_icon(self.profile_button, "fa5s.user-circle", "text2", size=24)
        menu = QMenu(self.profile_button)
        for text, icon, key in [("Preferences", "fa5s.cog", "settings"), ("Security Center", "fa5s.shield-alt", "security"),
                                ("About CipherPixel", "fa5s.info-circle", "about")]:
            act = menu.addAction(make_icon(icon, "text"), text)
            act.triggered.connect(lambda _c=False, k=key: self.navigate.emit(k))
        menu.addSeparator()
        menu.addAction(make_icon("fa5s.folder-open", "text"), "Open default export folder").triggered.connect(
            self.openExportFolder)
        menu.addSeparator()
        menu.addAction(make_icon("fa5s.times-circle", "text"), "Quit").triggered.connect(self.quitRequested)
        self.profile_button.setMenu(menu)
        self._menu = menu
        lay.addWidget(self.profile_button)

    def _on_theme_changed(self, _name: str) -> None:
        self._refresh_theme_icon()

    def _refresh_theme_icon(self) -> None:
        # In dark mode show the sun (switch to light) and vice versa.
        self.theme_button.setIcon(make_icon("fa5s.sun" if theme.name == "dark" else "fa5s.moon", "text2"))

    def set_page(self, title: str, crumbs: list[str]) -> None:
        self.title.setText(title)
        self.breadcrumb.setText("  ›  ".join(["CipherPixel", *crumbs]))

    def set_status(self, state: str, text: str) -> None:
        """state: 'checking' | 'ok' | 'fail'."""
        set_prop(self.pill, "state", state)
        self.pill_text.setText(text)
