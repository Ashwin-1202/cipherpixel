"""Theme system: palettes + a QSS generator (a small, dependency-free replacement for qdarktheme).

Widgets are styled through *dynamic properties* (``variant``, ``card``, ``badge`` …) so
the same code supports both dark and light themes without per-widget colour logic.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

from utils.paths import assets_dir

FONT_STACK = '"Inter", "Manrope", "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial, sans-serif'

PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0B1020", "bg2": "#111827", "card": "#151E30", "card_hover": "#1B2740",
        "border": "#26344F", "border_soft": "#1D2940", "input": "#0F1729",
        "primary": "#3B82F6", "primary_hover": "#5B9BFF", "secondary": "#06B6D4",
        "success": "#22C55E", "warning": "#F59E0B", "error": "#EF4444",
        "text": "#F8FAFC", "text2": "#94A3B8", "muted": "#64748B", "on_primary": "#FFFFFF",
        "scroll": "#2A3A57", "scroll_hover": "#3B4F73",
        "hero_a": "#16316B", "hero_b": "#0B4B66", "hero_text": "#F8FAFC", "hero_text2": "#B6C7E3",
    },
    "light": {
        "bg": "#F1F4FA", "bg2": "#FFFFFF", "card": "#FFFFFF", "card_hover": "#F1F5F9",
        "border": "#D5DDEA", "border_soft": "#E4E9F2", "input": "#F8FAFC",
        "primary": "#2563EB", "primary_hover": "#3B82F6", "secondary": "#0891B2",
        "success": "#16A34A", "warning": "#D97706", "error": "#DC2626",
        "text": "#0F172A", "text2": "#475569", "muted": "#94A3B8", "on_primary": "#FFFFFF",
        "scroll": "#CBD5E1", "scroll_hover": "#94A3B8",
        "hero_a": "#DCE8FF", "hero_b": "#D2F1F7", "hero_text": "#0F172A", "hero_text2": "#475569",
    },
}


def rgba(color: str, alpha: int) -> str:
    h = color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


def build_qss(name: str, p: dict[str, str]) -> str:
    icons = assets_dir() / "icons"
    chevron = (icons / f"chevron-down-{name}.svg").as_posix()
    check = (icons / "check.svg").as_posix()
    grad = f"qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['primary']},stop:1 {p['secondary']})"
    grad_hover = f"qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['primary_hover']},stop:1 #22D3EE)"

    def badge(kind: str, color: str) -> str:
        return (f'QLabel[badge="{kind}"] {{ background: {rgba(color, 34)}; color: {color}; }}')

    def accent(kind: str, color: str) -> str:
        return (f'QLabel[iconBadge="true"][accent="{kind}"] {{ background: {rgba(color, 32)}; }}'
                f'QProgressBar[tone="{kind}"]::chunk {{ background: {color}; }}')

    return f"""
QWidget {{ color: {p['text']}; font-family: {FONT_STACK}; font-size: 13px; }}
QWidget#AppRoot {{ background: {p['bg']}; }}
QLabel {{ background: transparent; }}
QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QWidget#PageBody {{ background: transparent; }}

/* ---------- typography roles ---------- */
QLabel[role="h1"] {{ font-size: 30px; font-weight: 700; }}
QLabel[role="h2"] {{ font-size: 17px; font-weight: 650; }}
QLabel[role="h3"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {p['text2']}; }}
QLabel[role="caption"] {{ color: {p['muted']}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel[role="value"] {{ font-size: 26px; font-weight: 700; }}
QLabel[role="mono"] {{ font-family: "JetBrains Mono","Cascadia Mono","Consolas","DejaVu Sans Mono",monospace; font-size: 12px; color: {p['text2']}; }}
QLabel#PageTitle {{ font-size: 21px; font-weight: 700; }}
QLabel#Breadcrumb {{ color: {p['muted']}; font-size: 12px; }}
QLabel#HeroTitle {{ font-size: 32px; font-weight: 750; color: {p['hero_text']}; }}
QLabel#HeroEyebrow {{ color: {p['secondary']}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#HeroText {{ font-size: 14px; color: {p['hero_text2']}; }}
QLabel#ErrorText {{ color: {p['error']}; }}

/* ---------- shell ---------- */
QFrame#Sidebar {{ background: {p['bg2']}; border: none; border-right: 1px solid {p['border_soft']}; }}
QFrame#TopBar {{ background: transparent; border: none; border-bottom: 1px solid {p['border_soft']}; }}
QFrame#Logo {{ background: {grad}; border-radius: 11px; border: none; }}
QFrame#SidebarFoot {{ background: {p['card']}; border: 1px solid {p['border_soft']}; border-radius: 12px; }}
QPushButton#NavButton {{ text-align: left; padding: 11px 14px; border-radius: 10px; border: none;
    background: transparent; color: {p['text2']}; font-weight: 500; }}
QPushButton#NavButton:hover {{ background: {p['card_hover']}; color: {p['text']}; }}
QPushButton#NavButton:checked {{ background: {rgba(p['primary'], 40)}; color: {p['text']}; font-weight: 650; }}
QFrame#StatusPill {{ border-radius: 15px; border: 1px solid {p['border']}; background: {p['card']}; }}
QFrame#StatusPill[state="ok"] {{ border-color: {rgba(p['success'], 90)}; background: {rgba(p['success'], 26)}; }}
QFrame#StatusPill[state="fail"] {{ border-color: {rgba(p['error'], 100)}; background: {rgba(p['error'], 28)}; }}
QLabel#StatusDot {{ border-radius: 4px; background: {p['muted']}; }}
QFrame#StatusPill[state="ok"] QLabel#StatusDot {{ background: {p['success']}; }}
QFrame#StatusPill[state="fail"] QLabel#StatusDot {{ background: {p['error']}; }}

/* ---------- cards ---------- */
QFrame[card="true"] {{ background: {p['card']}; border: 1px solid {p['border_soft']}; border-radius: 16px; }}
QFrame[card="true"][tone="success"] {{ border: 1px solid {rgba(p['success'], 90)}; }}
QFrame[card="true"][tone="error"] {{ border: 1px solid {rgba(p['error'], 100)}; background: {rgba(p['error'], 22)}; }}
QFrame#Hero {{ border: 1px solid {rgba(p['primary'], 70)}; border-radius: 22px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p['hero_a']},stop:1 {p['hero_b']}); }}
QFrame#HeroOrb {{ border-radius: 70px; background: {rgba('#FFFFFF', 18)}; border: 1px solid {rgba('#FFFFFF', 40)}; }}
QFrame#Divider {{ background: {p['border_soft']}; border: none; max-height: 1px; min-height: 1px; }}
QLabel[iconBadge="true"] {{ border-radius: 12px; }}
{accent('primary', p['primary'])}
{accent('secondary', p['secondary'])}
{accent('success', p['success'])}
{accent('warning', p['warning'])}
{accent('error', p['error'])}

/* ---------- badges ---------- */
QLabel[badge] {{ border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 650; }}
{badge('success', p['success'])}
{badge('error', p['error'])}
{badge('warning', p['warning'])}
{badge('info', p['primary'])}
QLabel[badge="neutral"] {{ background: {p['card_hover']}; color: {p['text2']}; }}

/* ---------- buttons ---------- */
QPushButton {{ background: {p['card_hover']}; border: 1px solid {p['border']}; border-radius: 10px;
    padding: 9px 16px; font-weight: 600; }}
QPushButton:hover {{ border-color: {p['primary']}; background: {rgba(p['primary'], 22)}; }}
QPushButton:pressed {{ background: {rgba(p['primary'], 40)}; }}
QPushButton:disabled {{ color: {p['muted']}; border-color: {p['border_soft']}; background: transparent; }}
QPushButton:focus {{ border-color: {p['primary']}; }}
QPushButton[variant="primary"] {{ background: {grad}; border: none; color: {p['on_primary']}; }}
QPushButton[variant="primary"]:hover {{ background: {grad_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {p['primary']}; }}
QPushButton[variant="primary"]:disabled {{ background: {p['card_hover']}; color: {p['muted']}; border: 1px solid {p['border_soft']}; }}
QPushButton[variant="danger"] {{ background: {rgba(p['error'], 30)}; border: 1px solid {rgba(p['error'], 110)}; color: {p['error']}; }}
QPushButton[variant="danger"]:hover {{ background: {p['error']}; color: #FFFFFF; border-color: {p['error']}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; color: {p['text2']}; }}
QPushButton[variant="ghost"]:hover {{ background: {p['card_hover']}; color: {p['text']}; border-color: transparent; }}
QPushButton[size="lg"] {{ padding: 15px 30px; font-size: 14px; letter-spacing: 1px; border-radius: 12px; font-weight: 700; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 10px; padding: 7px; color: {p['text2']}; }}
QToolButton:hover {{ background: {p['card_hover']}; border-color: {p['border']}; }}
QToolButton::menu-indicator {{ image: none; }}

/* ---------- inputs ---------- */
QLineEdit {{ background: {p['input']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 10px 12px;
    selection-background-color: {p['primary']}; selection-color: #FFFFFF; }}
QLineEdit:hover {{ border-color: {p['muted']}; }}
QLineEdit:focus {{ border: 1px solid {p['primary']}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {p['error']}; }}
QLineEdit:disabled {{ color: {p['muted']}; }}
QLineEdit:read-only {{ color: {p['text2']}; }}
QComboBox {{ background: {p['input']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 9px 12px; min-height: 18px; }}
QComboBox:hover {{ border-color: {p['muted']}; }}
QComboBox:focus, QComboBox:on {{ border-color: {p['primary']}; }}
QComboBox:disabled {{ color: {p['muted']}; }}
QComboBox::drop-down {{ border: none; width: 30px; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 4px;
    selection-background-color: {rgba(p['primary'], 60)}; selection-color: {p['text']}; outline: none; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {p['border']}; background: {p['input']}; }}
QCheckBox::indicator:hover {{ border-color: {p['primary']}; }}
QCheckBox::indicator:checked {{ background: {p['primary']}; border-color: {p['primary']}; image: url("{check}"); }}
QCheckBox:disabled {{ color: {p['muted']}; }}

/* ---------- drop zone ---------- */
QFrame#DropZone {{ background: {rgba(p['primary'], 12)}; border: 2px dashed {p['border']}; border-radius: 18px; }}
QFrame#DropZone:hover {{ border-color: {p['primary']}; background: {rgba(p['primary'], 20)}; }}
QFrame#DropZone[dragActive="true"] {{ border: 2px dashed {p['secondary']}; background: {rgba(p['secondary'], 30)}; }}
QFrame#PreviewBox {{ background: {p['input']}; border: 1px solid {p['border_soft']}; border-radius: 14px; }}
QFrame#InfoTile {{ background: {p['input']}; border: 1px solid {p['border_soft']}; border-radius: 12px; }}

/* ---------- progress ---------- */
QProgressBar {{ border: none; border-radius: 5px; background: {p['input']}; min-height: 10px; max-height: 10px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ border-radius: 5px; background: {grad}; }}

/* ---------- strength meter ---------- */
QFrame#Seg {{ background: {p['border']}; border-radius: 3px; border: none; min-height: 6px; max-height: 6px; }}
QFrame#Seg[fill="bad"] {{ background: {p['error']}; }}
QFrame#Seg[fill="fair"] {{ background: {p['warning']}; }}
QFrame#Seg[fill="good"] {{ background: {p['secondary']}; }}
QFrame#Seg[fill="great"] {{ background: {p['success']}; }}

/* ---------- tables ---------- */
QTableWidget {{ background: transparent; border: none; gridline-color: transparent; outline: none;
    selection-background-color: {rgba(p['primary'], 36)}; selection-color: {p['text']}; }}
QTableWidget::item {{ padding: 6px 12px; border-bottom: 1px solid {p['border_soft']}; }}
QTableWidget::item:hover {{ background: {rgba(p['primary'], 14)}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {p['muted']}; border: none; border-bottom: 1px solid {p['border']};
    padding: 10px 12px; font-size: 11px; font-weight: 700; letter-spacing: 1px; text-align: left; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

/* ---------- scrollbars ---------- */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['scroll']}; border-radius: 4px; min-height: 36px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {p['scroll_hover']}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['scroll']}; border-radius: 4px; min-width: 36px; margin: 2px 0; }}
QScrollBar::handle:horizontal:hover {{ background: {p['scroll_hover']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- toast, tooltip, menu, dialogs ---------- */
QFrame#Toast {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 12px; }}
QFrame#ToastAccent {{ border: none; border-radius: 2px; background: {p['primary']}; min-width: 4px; max-width: 4px; }}
QFrame#ToastAccent[kind="success"] {{ background: {p['success']}; }}
QFrame#ToastAccent[kind="error"] {{ background: {p['error']}; }}
QFrame#ToastAccent[kind="warning"] {{ background: {p['warning']}; }}
QToolTip {{ background: {p['card']}; color: {p['text']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 6px 10px; }}
QMenu {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 9px 22px 9px 14px; border-radius: 7px; }}
QMenu::item:selected {{ background: {rgba(p['primary'], 45)}; }}
QMenu::separator {{ height: 1px; background: {p['border_soft']}; margin: 5px 8px; }}
QDialog, QMessageBox {{ background: {p['bg2']}; }}
QMessageBox QLabel {{ color: {p['text']}; }}
QInputDialog QLineEdit {{ min-width: 240px; }}
"""


class ThemeManager(QObject):
    changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.name = "dark"

    @property
    def palette(self) -> dict[str, str]:
        return PALETTES[self.name]

    def color(self, role: str) -> str:
        return self.palette[role]

    def apply(self, name: str | None = None) -> None:
        if name is not None:
            if name not in PALETTES:
                raise ValueError(name)
            self.name = name
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss(self.name, self.palette))
        self.changed.emit(self.name)


theme = ThemeManager()


def set_prop(widget: QWidget, name: str, value) -> None:
    """Set a dynamic property and re-evaluate the stylesheet for that widget."""
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
