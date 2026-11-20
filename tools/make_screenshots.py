"""Render real screenshots of CipherPixel (offscreen) into docs/screenshots.

Usage:  python tools/make_screenshots.py
Drives the genuine UI (real encryption/decryption on a generated sample image).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.file_handler import SessionTempDir  # noqa: E402
from core.history import HistoryStore  # noqa: E402
from ui import dialogs  # noqa: E402
from ui.context import AppContext  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.theme import theme  # noqa: E402
from utils.settings import Settings  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
PASSWORD = "Sunrise-Harbor-Lantern-4821!"


def sample_image(path: str) -> None:
    """A colourful gradient 'landscape' so the preview looks like a real photo."""
    w, h = 1280, 800
    y, x = np.mgrid[0:h, 0:w]
    sky = np.stack([30 + 90 * (y / h), 60 + 120 * (y / h), 140 + 110 * (y / h)], axis=-1)
    hills = (np.sin(x / 140.0) * 55 + np.sin(x / 47.0) * 14 + h * 0.62) < y
    ground = np.stack([20 + 40 * (x / w) + 0 * y, 90 + 70 * (y / h), 60 + 0 * x + 0 * y], axis=-1)
    sun = ((x - 880) ** 2 + (y - 210) ** 2) < 70**2
    img = np.where(hills[..., None], ground, sky)
    img = np.where(sun[..., None], np.array([255, 224, 150]), img)
    Image.fromarray(np.clip(img, 0, 255).astype("uint8")).save(path, "PNG")


def wait(app, cond, ms=60000):
    t = 0
    while not cond() and t < ms:
        QTest.qWait(25)
        t += 25
    assert cond(), "timeout"


def shot(app, win, name):
    for _ in range(6):
        app.processEvents()
        QTest.qWait(30)
    OUT.mkdir(parents=True, exist_ok=True)
    win.grab().save(str(OUT / f"{name}.png"))
    print("saved", name)


def main() -> None:
    app = QApplication([])
    for f in (ROOT / "assets" / "fonts").glob("*.otf"):
        QFontDatabase.addApplicationFont(str(f))
    tmp = Path(tempfile.mkdtemp(prefix="cp-shots-"))
    settings = Settings(tmp / "settings.json")
    theme.apply("dark")
    ctx = AppContext(settings, HistoryStore(tmp / "h.db"), SessionTempDir())
    win = MainWindow(ctx)
    ctx._toast = lambda *a, **k: None
    win.resize(1360, 860)
    win.show()
    wait(app, lambda: ctx.selftest_results is not None)

    img = str(tmp / "sunrise-valley.png")
    sample_image(img)
    # seed a believable history
    for op, name, typ, size, st in [
        ("encrypt", "family-trip.jpg", "JPEG", 4_820_113, "success"),
        ("decrypt", "family-trip.cpx", "CPX", 4_820_705, "success"),
        ("encrypt", "passport-scan.png", "PNG", 2_104_332, "success"),
        ("decrypt", "old-backup.cpx", "CPX", 913_220, "failed"),
        ("encrypt", "receipt-0418.tiff", "TIFF", 7_301_998, "success"),
    ]:
        ctx.history.record(op, name, typ, size, st)

    shot(app, win, "01-overview")

    enc, dec = win.pages["encrypt"], win.pages["decrypt"]
    win.navigate("encrypt", animate=False)
    shot(app, win, "02-encrypt-empty")
    enc.load_file(img)
    enc.gen_btn.click()
    shot(app, win, "03-encrypt-ready")

    password_used = enc.pw.text()
    enc.encrypt_btn.click()
    wait(app, lambda: enc.state == enc.DONE)
    shot(app, win, "04-encrypt-success")

    out = str(tmp / "sunrise-valley.cpx")
    dialogs.save_file = lambda *a, **k: out
    enc.save.button.click()
    wait(app, lambda: enc.save.saved_path == out)
    win.navigate("decrypt", animate=False)
    shot(app, win, "05-decrypt-empty")
    dec.load_file(out)
    dec.pw.setText("wrong-guess-1")
    dec.decrypt_btn.click()
    wait(app, lambda: dec.state == dec.READY and not dec.progress.isVisible())
    shot(app, win, "06-decrypt-wrong-password")
    dec.pw.setText(password_used)
    dec.decrypt_btn.click()
    wait(app, lambda: dec.state == dec.DONE)
    shot(app, win, "07-decrypt-success")

    for key, name in [("history", "08-history"), ("security", "09-security"), ("settings", "10-settings")]:
        win.navigate(key, animate=False)
        shot(app, win, name)

    win.set_theme("light")
    win.navigate("overview", animate=False)
    shot(app, win, "11-overview-light")
    win.navigate("encrypt", animate=False)
    shot(app, win, "12-encrypt-light")

    win.resize(900, 700)  # minimum-ish size: compact sidebar + stacked layout
    win.set_theme("dark")
    win.navigate("overview", animate=False)
    shot(app, win, "13-compact-overview")

    dec.reset()
    enc.reset()
    win.shutdown()


if __name__ == "__main__":
    main()
