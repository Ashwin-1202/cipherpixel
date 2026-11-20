"""CipherPixel – Advanced Image Security System.  Run with:  python main.py"""

from __future__ import annotations

import os
import sys


def _fatal(message: str) -> int:
    print(f"CipherPixel cannot start: {message}", file=sys.stderr)
    try:  # best effort GUI message on Windows double-click launches
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "CipherPixel", 0x10)  # type: ignore[attr-defined]
    except Exception:
        pass
    return 1


def main() -> int:
    if sys.version_info < (3, 11):
        return _fatal("Python 3.11 or newer is required.")
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFontDatabase, QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return _fatal("PySide6 is not installed. Run:  pip install -r requirements.txt")

    root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, root)

    from core.file_handler import SessionTempDir
    from core.history import HistoryStore
    from ui import APP_NAME
    from ui.context import AppContext
    from ui.main_window import MainWindow
    from ui.theme import theme
    from utils.paths import assets_dir, data_dir
    from utils.settings import Settings

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    fonts = assets_dir() / "fonts"
    if fonts.is_dir():
        for font in fonts.glob("*.otf"):
            QFontDatabase.addApplicationFont(str(font))

    settings = Settings()
    theme.apply(settings.get("theme"))
    ctx = AppContext(settings, HistoryStore(data_dir() / "history.db"), SessionTempDir())

    window = MainWindow(ctx)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
