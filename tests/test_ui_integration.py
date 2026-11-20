"""End-to-end GUI tests (headless/offscreen): real widgets, real worker threads, real crypto.

Native file dialogs are replaced via the ``ui.dialogs`` wrapper module; everything else is
exercised exactly as a user would (button clicks, typing, drag & drop events).
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.file_handler import SessionTempDir  # noqa: E402
from core.history import HistoryStore  # noqa: E402
from ui import dialogs  # noqa: E402
from ui.context import AppContext  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.theme import theme  # noqa: E402
from utils.settings import Settings  # noqa: E402

PASSWORD = "Tr1cky-Unlock-Phrase-2026!"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    settings = Settings(tmp_path / "settings.json")
    settings.set("kdf_level", "balanced")
    theme.apply("dark")
    ctx = AppContext(settings, HistoryStore(tmp_path / "h.db"), SessionTempDir())
    toasts: list[tuple[str, str, str]] = []
    window = MainWindow(ctx)
    ctx._toast = lambda kind, title, message="": toasts.append((kind, title, message))
    window.toasts_log = toasts
    # Default: any unexpected confirmation dialog is accepted so tests never block.
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: True)
    window.show()
    yield window
    window.pages["encrypt"].reset()
    window.pages["decrypt"].reset()
    window.shutdown()  # joins the start-up self-test thread before the window is destroyed
    QApplication.processEvents()
    window.deleteLater()


def wait_for(qapp, predicate, timeout_ms=60_000):
    waited = 0
    while not predicate() and waited < timeout_ms:
        QTest.qWait(25)
        waited += 25
    assert predicate(), "timed out waiting for condition"


def _kinds(win):
    return [k for k, _t, _m in win.toasts_log]


def _encrypt_via_ui(qapp, win, tmp_path, image, monkeypatch, out_name="out.cpx"):
    page = win.pages["encrypt"]
    win.navigate("encrypt", animate=False)
    page.load_file(image)
    page.pw.setText(PASSWORD)
    page.pw2.setText(PASSWORD)
    assert page.encrypt_btn.isEnabled()
    page.encrypt_btn.click()
    wait_for(qapp, lambda: page.state == page.DONE or page.state == page.READY)
    assert page.state == page.DONE, win.toasts_log
    dest = str(tmp_path / out_name)
    monkeypatch.setattr(dialogs, "save_file", lambda *a, **k: dest)
    page.save.button.click()
    wait_for(qapp, lambda: page.save.saved_path == dest)
    return dest


def test_navigation_reaches_every_page_and_updates_header(win):
    for key, page in win.pages.items():
        win.navigate(key, animate=False)
        assert win.stack.currentWidget() is page
        assert win.topbar.title.text() == page.title
    assert set(win.pages) == {"overview", "encrypt", "decrypt", "history", "security", "settings", "about"}


def test_sidebar_buttons_navigate(win):
    for key, btn in win.sidebar._buttons.items():
        btn.click()
        assert win.stack.currentWidget() is win.pages[key] and btn.isChecked()


def test_dashboard_quick_actions_navigate(win):
    dash = win.pages["overview"]
    dash.enc_btn.click()
    assert win.current_key == "encrypt"
    win.navigate("overview", animate=False)
    dash.dec_btn.click()
    assert win.current_key == "decrypt"


def test_engine_status_pill_reports_verified(qapp, win):
    wait_for(qapp, lambda: win.ctx.selftest_results is not None)
    assert win.topbar.pill.property("state") == "ok"
    assert all(r.passed for r in win.ctx.selftest_results)


def test_full_encrypt_save_decrypt_export_roundtrip(qapp, win, png_path, tmp_path, monkeypatch):
    enc_page, dec_page = win.pages["encrypt"], win.pages["decrypt"]
    enc_page.kdf_sel.set_values("argon2id", "balanced")
    cpx = _encrypt_via_ui(qapp, win, tmp_path, png_path, monkeypatch)
    assert os.path.getsize(cpx) > os.path.getsize(png_path)
    assert enc_page.pw.text() == "" and enc_page.pw2.text() == ""  # password wiped after use

    win.navigate("decrypt", animate=False)
    dec_page.load_file(cpx)
    assert dec_page.info is not None and dec_page.state == dec_page.READY
    dec_page.pw.setText(PASSWORD)
    dec_page.decrypt_btn.click()
    wait_for(qapp, lambda: dec_page.state in (dec_page.DONE, dec_page.READY))
    assert dec_page.state == dec_page.DONE
    assert dec_page.preview.has_image()
    assert dec_page.result.width == 200 and dec_page.result.height == 150

    restored = str(tmp_path / "restored.png")
    monkeypatch.setattr(dialogs, "save_file", lambda *a, **k: restored)
    dec_page.save.button.click()
    wait_for(qapp, lambda: dec_page.save.saved_path == restored)
    assert open(restored, "rb").read() == open(png_path, "rb").read()  # byte-for-byte via the GUI

    counts = win.ctx.history.counts()
    assert counts["encrypted"] == 1 and counts["decrypted"] == 1
    names = {e.file_name for e in win.ctx.history.list()}
    assert "photo.png" in names and "out.cpx" in names


def test_wrong_password_shows_error_and_creates_nothing(qapp, win, png_path, tmp_path, monkeypatch):
    cpx = _encrypt_via_ui(qapp, win, tmp_path, png_path, monkeypatch)
    page = win.pages["decrypt"]
    win.navigate("decrypt", animate=False)
    page.load_file(cpx)
    page.pw.setText("definitely-not-it")
    page.decrypt_btn.click()
    wait_for(qapp, lambda: page.state == page.READY and not page.progress.isVisible())
    assert page.error_box.isVisible() and "password" in page.error_box.text().lower()
    assert not page.result_card.isVisible() and not page.preview.has_image()
    assert "error" in _kinds(win)
    assert win.ctx.history.list(operation="decrypt")[0].status == "failed"
    assert win.ctx.history.counts()["decrypted"] == 0
    # retry with correct password works afterwards
    page.pw.setText(PASSWORD)
    page.decrypt_btn.click()
    wait_for(qapp, lambda: page.state == page.DONE)


def test_corrupted_file_reports_clean_error(qapp, win, png_path, tmp_path, monkeypatch):
    cpx = _encrypt_via_ui(qapp, win, tmp_path, png_path, monkeypatch)
    blob = bytearray(open(cpx, "rb").read())
    blob[len(blob) // 2] ^= 0xFF
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(bytes(blob))
    page = win.pages["decrypt"]
    win.navigate("decrypt", animate=False)
    page.load_file(str(bad))
    page.pw.setText(PASSWORD)
    page.decrypt_btn.click()
    wait_for(qapp, lambda: page.state == page.READY and not page.progress.isVisible())
    assert page.error_box.isVisible()
    text = page.error_box.text().lower()
    assert "corrupt" in text or "password" in text or "modified" in text
    assert "invalidtag" not in text and "traceback" not in text


def test_decrypt_page_rejects_non_cpx_and_garbage(qapp, win, png_path, tmp_path):
    page = win.pages["decrypt"]
    page.load_file(png_path)
    assert page.info is None and any("image" in t.lower() for _k, t, _m in win.toasts_log)
    junk = tmp_path / "junk.cpx"
    junk.write_bytes(os.urandom(500))
    page.load_file(str(junk))
    assert page.info is None and page.state == page.IDLE
    empty = tmp_path / "empty.cpx"
    empty.write_bytes(b"")
    page.load_file(str(empty))
    assert page.info is None


def test_encrypt_page_rejects_invalid_files(qapp, win, tmp_path):
    page = win.pages["encrypt"]
    txt = tmp_path / "a.txt"
    txt.write_text("hello")
    fake = tmp_path / "fake.png"
    fake.write_text("not really a png")
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    for p in (txt, fake, empty):
        page.load_file(str(p))
        assert page.image is None and page.state == page.IDLE
    assert _kinds(win).count("error") == 3


def test_encrypt_button_gating_and_validation(win, png_path):
    page = win.pages["encrypt"]
    win.navigate("encrypt", animate=False)
    assert not page.encrypt_btn.isEnabled()  # no image
    page.load_file(png_path)
    assert not page.encrypt_btn.isEnabled()  # no password
    page.pw.setText("Str0ng&Unique-Pass")
    page.pw2.setText("different")
    assert not page.encrypt_btn.isEnabled() and page.mismatch.isVisible()
    page.pw2.setText("Str0ng&Unique-Pass")
    assert page.encrypt_btn.isEnabled() and not page.mismatch.isVisible()
    page.pw.setText("password")
    page.pw2.setText("password")
    assert not page.encrypt_btn.isEnabled()  # common/weak password refused


def test_password_toggle_generator_and_strength(win, png_path):
    page = win.pages["encrypt"]
    page.load_file(png_path)
    assert not page.pw.is_revealed()
    page.pw.set_revealed(True)
    assert page.pw2.is_revealed()  # linked
    page.pw.set_revealed(False)
    page.gen_btn.click()
    assert len(page.pw.text()) == 20 and page.pw.text() == page.pw2.text() and page.pw.is_revealed()
    assert page.encrypt_btn.isEnabled()
    assert page.meter._label.text().startswith(("Strong", "Excellent"))
    first = page.pw.text()
    page.gen_btn.click()
    assert page.pw.text() != first


def test_copy_password_to_clipboard(qapp, win, png_path):
    page = win.pages["encrypt"]
    page.pw.setText("Copy-Me-Please-123!")
    page.copy_btn.click()
    assert QApplication.clipboard().text() == "Copy-Me-Please-123!"
    QApplication.clipboard().clear()


def test_drag_and_drop_loads_image(qapp, win, png_path):
    page = win.pages["encrypt"]
    win.navigate("encrypt", animate=False)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(png_path)])
    zone = page.drop
    enter = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    zone.dragEnterEvent(enter)
    assert enter.isAccepted() and zone.property("dragActive") is True
    drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    zone.dropEvent(drop)
    assert page.image is not None and page.image.name == "photo.png"
    assert zone.property("dragActive") is False
    assert page.t_dims._value.text() == "200 × 150 px" and page.preview.has_image()


def test_drop_of_non_file_content_is_ignored(win):
    mime = QMimeData()
    mime.setText("just text")
    ev = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    win.pages["encrypt"].drop.dragEnterEvent(ev)
    assert not ev.isAccepted()


def test_cancel_during_encryption_leaves_no_file(qapp, win, make_image, tmp_path):
    big = make_image("big.bmp", 3000, 2400)
    page = win.pages["encrypt"]
    page.kdf_sel.set_values("pbkdf2", "paranoid")  # long KDF phase gives time to cancel
    page.load_file(big)
    page.pw.setText(PASSWORD)
    page.pw2.setText(PASSWORD)
    page.encrypt_btn.click()
    wait_for(qapp, lambda: page.state == page.RUNNING)
    QTest.qWait(100)
    page.progress.cancel_button.click()
    wait_for(qapp, lambda: page.state == page.READY)
    assert page.result is None and not page.result_card.isVisible()
    assert os.listdir(win.ctx.temp.path) == []
    assert "info" in _kinds(win)


def test_encrypt_another_resets_and_confirms_when_unsaved(qapp, win, png_path, monkeypatch):
    page = win.pages["encrypt"]
    page.load_file(png_path)
    page.pw.setText(PASSWORD)
    page.pw2.setText(PASSWORD)
    page.encrypt_btn.click()
    wait_for(qapp, lambda: page.state == page.DONE)
    assert page.has_unsaved_work()
    asked = []
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: asked.append(a[1]) or False)
    page.again_btn.click()
    assert asked and page.state == page.DONE  # user declined: nothing lost
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: True)
    page.again_btn.click()
    assert page.state == page.IDLE and page.image is None and os.listdir(win.ctx.temp.path) == []


def test_history_page_search_filter_sort_export_delete_clear(qapp, win, png_path, tmp_path, monkeypatch):
    h = win.ctx.history
    h.record("encrypt", "alpha.png", "PNG", 100, "success")
    h.record("decrypt", "beta.cpx", "CPX", 200, "failed")
    h.record("encrypt", "gamma.jpg", "JPEG", 300, "success")
    page = win.pages["history"]
    win.navigate("history", animate=False)
    assert page.table.rowCount() == 3
    page.filter.setCurrentIndex(2)
    assert page.table.rowCount() == 1 and page.table.item(0, 0).text() == "beta.cpx"
    page.filter.setCurrentIndex(0)
    page.search.setText("gam")
    wait_for(qapp, lambda: page.table.rowCount() == 1)
    page.search.setText("zzz")
    wait_for(qapp, lambda: page.table.rowCount() == 0)
    assert page.empty.isVisible() and page.empty.title.text() == "No matching entries"
    page.search.clear()
    wait_for(qapp, lambda: page.table.rowCount() == 3)
    page.sort.setCurrentIndex(1)
    assert page.table.item(0, 0).text() == "alpha.png"

    csv_path = str(tmp_path / "hist.csv")
    monkeypatch.setattr(dialogs, "save_file", lambda *a, **k: csv_path)
    page.export_btn.click()
    assert os.path.exists(csv_path) and "alpha.png" in open(csv_path, encoding="utf-8-sig").read()

    page.table.selectRow(0)
    assert page.delete_btn.isEnabled()
    page.delete_btn.click()
    assert page.table.rowCount() == 2
    page.clear_btn.click()
    assert page.table.rowCount() == 0 and page.empty.isVisible()
    assert win.ctx.history.counts()["encrypted"] == 2  # totals survive clearing


def test_dashboard_updates_after_activity(win):
    dash = win.pages["overview"]
    assert dash.empty.isVisible() and dash.s_enc.value.text() == "0"
    win.ctx.record("encrypt", "x.png", "PNG", 10, "success")
    assert dash.s_enc.value.text() == "1" and dash.s_proc.value.text() == "1"
    assert dash.table.isVisible() and dash.table.rowCount() == 1 and not dash.empty.isVisible()


def test_history_recording_can_be_disabled(win):
    win.pages["settings"].record.setChecked(False)
    win.ctx.record("encrypt", "private.png", "PNG", 10, "success")
    assert win.ctx.history.list() == [] and win.ctx.history.counts()["encrypted"] == 1


def test_settings_page_controls_persist(win, tmp_path, monkeypatch):
    st = win.pages["settings"]
    s = win.ctx.settings
    st.show_pw.setChecked(True)
    assert s.get("show_password_default") is True
    win.pages["encrypt"].pw.clear()
    win.pages["encrypt"]._apply_defaults()
    assert win.pages["encrypt"].pw.is_revealed()
    st.kdf_sel.kdf_combo.setCurrentIndex(st.kdf_sel.kdf_combo.findData("pbkdf2"))
    st.kdf_sel.level_combo.setCurrentIndex(st.kdf_sel.level_combo.findData("strong"))
    assert (s.get("kdf"), s.get("kdf_level")) == ("pbkdf2", "strong")
    assert win.pages["encrypt"].kdf_sel.params().kdf_id == 2  # propagated to Encrypt page
    monkeypatch.setattr(dialogs, "choose_folder", lambda *a, **k: str(tmp_path))
    st.dir_btn.click()
    assert s.export_dir == str(tmp_path) and st.dir_edit.text() == str(tmp_path)
    st.reset_btn.click()
    assert s.get("kdf") == "argon2id" and s.get("show_password_default") is False


def test_theme_toggle_switches_and_persists(win):
    assert theme.name == "dark"
    win.topbar.theme_button.click()
    assert theme.name == "light" and win.ctx.settings.get("theme") == "light"
    assert "#F1F4FA" in QApplication.instance().styleSheet()
    win.topbar.theme_button.click()
    assert theme.name == "dark" and "#0B1020" in QApplication.instance().styleSheet()


def test_security_page_self_test_button(qapp, win):
    page = win.pages["security"]
    win.navigate("security", animate=False)
    wait_for(qapp, lambda: win.ctx.selftest_results is not None)
    win.ctx.selftest_results = None
    page.run_btn.click()
    wait_for(qapp, lambda: win.ctx.selftest_results is not None)
    assert page.summary.text().startswith("All ") and page.list_layout.count() >= 8
    assert page.run_btn.isEnabled()


def test_close_blocked_with_unsaved_result_and_cleans_temp(qapp, win, png_path, monkeypatch):
    page = win.pages["encrypt"]
    page.load_file(png_path)
    page.pw.setText(PASSWORD)
    page.pw2.setText(PASSWORD)
    page.encrypt_btn.click()
    wait_for(qapp, lambda: page.state == page.DONE)
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: False)
    assert not win.close()  # user chose to keep working
    assert os.listdir(win.ctx.temp.path)
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: True)
    assert win.close()
    assert not os.path.exists(win.ctx.temp.path)


def test_no_secret_leakage_in_logs_or_history(qapp, win, png_path, tmp_path, monkeypatch):
    _encrypt_via_ui(qapp, win, tmp_path, png_path, monkeypatch)
    log_dir = os.path.join(os.path.dirname(win.ctx.history.path), "logs")
    blobs = []
    for root, _d, files in os.walk(os.path.dirname(win.ctx.history.path)):
        for f in files:
            blobs.append(open(os.path.join(root, f), "rb").read())
    assert blobs and all(PASSWORD.encode() not in b for b in blobs)
    del log_dir
