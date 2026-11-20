"""Security utilities, KDF, history privacy, settings, self-test."""

from __future__ import annotations

import os
import sqlite3

import pytest

from core.history import DECRYPT, ENCRYPT, FAILED, SUCCESS, HistoryStore
from core.key_manager import (
    KdfParams,
    available_kdfs,
    derive_key,
    get_preset,
    normalize_password,
)
from core.security_utils import (
    estimate_strength,
    generate_password,
    human_size,
    sanitize_filename,
)
from core.selftest import run_self_test
from core.errors import WeakPasswordError
from utils.logger import _PATHLIKE
from utils.settings import Settings
from utils.validators import is_cpx_path, is_supported_image_path, validate_new_password

SALT = bytes(range(16))


# ---- KDF ------------------------------------------------------------------------
def test_kdf_is_deterministic_and_256_bit(kdf):
    k1, k2 = derive_key("pw-one-two", SALT, kdf), derive_key("pw-one-two", SALT, kdf)
    assert k1 == k2 and len(k1) == 32


def test_kdf_depends_on_password_salt_and_params(kdf):
    base = derive_key("pw-one-two", SALT, kdf)
    assert derive_key("pw-one-twO", SALT, kdf) != base
    assert derive_key("pw-one-two", bytes(16), kdf) != base
    other = KdfParams.pbkdf2(100_001) if kdf.kdf_id == 2 else KdfParams.argon2id(2, 8 * 1024, 1)
    assert derive_key("pw-one-two", SALT, other) != base


def test_argon2_and_pbkdf2_known_properties():
    assert derive_key("x" * 8, SALT, KdfParams.pbkdf2(100_000)) != derive_key("x" * 8, SALT, KdfParams.argon2id(1, 8192, 1))


def test_short_salt_rejected():
    with pytest.raises(ValueError):
        derive_key("password", b"short", KdfParams.pbkdf2(100_000))


@pytest.mark.parametrize(
    "params",
    [KdfParams.pbkdf2(99_999), KdfParams.pbkdf2(10**9), KdfParams(2, 100_000, 1, 0), KdfParams(9, 1, 1, 1),
     KdfParams.argon2id(0, 65536, 4), KdfParams.argon2id(3, 1024, 4), KdfParams.argon2id(3, 2**30 + 1, 4),
     KdfParams.argon2id(3, 65536, 0), KdfParams.argon2id(3, 65536, 99)],
)
def test_out_of_range_kdf_parameters_rejected(params):
    with pytest.raises(ValueError):
        params.validate()


@pytest.mark.parametrize("kdf_name", ["argon2id", "pbkdf2"])
@pytest.mark.parametrize("level", ["balanced", "strong", "paranoid"])
def test_presets_are_valid_and_increasingly_expensive(kdf_name, level):
    get_preset(kdf_name, level).validate()
    if level != "balanced":
        weaker = get_preset(kdf_name, "balanced")
        assert get_preset(kdf_name, level).p1 >= weaker.p1


def test_default_preset_meets_owasp_minimums():
    a = get_preset("argon2id", "balanced")
    assert a.p2 >= 19 * 1024 and a.p1 >= 2          # OWASP Argon2id minimum profile
    assert get_preset("pbkdf2", "balanced").p1 >= 600_000


def test_argon2_is_available_in_this_environment():
    assert "argon2id" in available_kdfs()


def test_password_normalisation_and_empty_rejected():
    assert normalize_password("e\u0301") == normalize_password("\u00e9")
    with pytest.raises(ValueError):
        normalize_password("")


# ---- password tools -------------------------------------------------------------
def test_strength_ordering_and_labels():
    scores = [estimate_strength(p).score for p in ["", "abc", "password", "Tr0ub4dor&3", "correct horse battery staple 91!", "q8#Vn!2xLm$7Zp@4Rw9&"]]
    assert scores[0] == 0 and scores[1] == 0 and scores[2] == 0
    assert scores[-1] >= 3 and scores == sorted(scores)
    assert estimate_strength("aaaaaaaaaaaa").score <= 1
    assert estimate_strength("abcdefghijkl").score <= 2


def test_generated_passwords_are_strong_unique_and_complete():
    pws = {generate_password(20) for _ in range(200)}
    assert len(pws) == 200
    for pw in list(pws)[:50]:
        assert len(pw) == 20
        assert any(c.islower() for c in pw) and any(c.isupper() for c in pw)
        assert any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)
        assert estimate_strength(pw).score >= 3
    with pytest.raises(ValueError):
        generate_password(6)


def test_validate_new_password():
    validate_new_password("Str0ng&Unique-Pass", "Str0ng&Unique-Pass")
    for pw, confirm in [("", ""), ("short1!", "short1!"), ("Str0ng&Unique-Pass", "mismatch"), ("password", "password"), ("11111111", "11111111")]:
        with pytest.raises(WeakPasswordError):
            validate_new_password(pw, confirm)


# ---- filenames / validators / sizes --------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [("../../etc/passwd", "passwd"), ("C:\\Windows\\system32\\evil.png", "evil.png"), ("a<b>c:d.png", "a_b_c_d.png"),
     ("CON.png", "_CON.png"), ("", "recovered_image"), ("...", "recovered_image"), ("photo.jpg", "photo.jpg"),
     ("trailing. ", "trailing"), ("nul", "_nul")],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_length_limit():
    assert len(sanitize_filename("a" * 500 + ".png")) <= 131


def test_validators():
    assert is_supported_image_path("X.JPeG") and not is_supported_image_path("x.gif")
    assert is_cpx_path("a.CPX") and not is_cpx_path("a.png")


def test_human_size():
    assert human_size(0) == "0 B" and human_size(1536) == "1.5 KB" and human_size(5 * 1024**2) == "5.0 MB"


# ---- logging privacy -------------------------------------------------------------
def test_log_path_redaction_pattern():
    assert _PATHLIKE.search("failed /home/alice/Pictures/secret.png now")
    assert _PATHLIKE.search(r"failed C:\Users\alice\secret.png now")


# ---- history privacy & behaviour -------------------------------------------------
@pytest.fixture
def store(tmp_path) -> HistoryStore:
    return HistoryStore(tmp_path / "history.db")


def test_history_schema_has_no_secret_columns(store):
    cols = {r[1] for r in sqlite3.connect(store.path).execute("PRAGMA table_info(history)")}
    assert cols == {"id", "ts", "operation", "file_name", "file_type", "file_size", "status"}
    forbidden = {"password", "key", "salt", "nonce", "plaintext", "data", "pixels"}
    assert not any(f in c for c in cols for f in forbidden)


def test_history_roundtrip_search_filter_sort(store):
    store.record(ENCRYPT, "holiday.png", "png", 1000, SUCCESS)
    store.record(DECRYPT, "holiday.cpx", "cpx", 1200, SUCCESS)
    store.record(DECRYPT, "bad.cpx", "cpx", 10, FAILED)
    assert len(store.list()) == 3
    assert [e.file_name for e in store.list(operation=ENCRYPT)] == ["holiday.png"]
    assert {e.file_name for e in store.list(search="HOLIDAY")} == {"holiday.png", "holiday.cpx"}
    assert store.list(newest_first=False)[0].file_name == "holiday.png"
    assert store.list(limit=1)[0].file_name == "bad.cpx"
    assert store.list(search="100%") == [] and store.list(search="_") == []  # LIKE wildcards are escaped


def test_history_search_is_injection_safe(store):
    store.record(ENCRYPT, "a.png", "png", 1, SUCCESS)
    assert store.list(search="'; DROP TABLE history;--") == []
    assert len(store.list()) == 1


def test_counters_survive_clear_and_disabled_history(store):
    store.record(ENCRYPT, "a.png", "png", 1, SUCCESS)
    store.record(ENCRYPT, "b.png", "png", 1, SUCCESS, store_entry=False)
    store.record(DECRYPT, "c.cpx", "cpx", 1, FAILED)
    assert len(store.list()) == 2
    store.clear()
    assert store.list() == []
    assert store.counts() == {"encrypted": 2, "decrypted": 0, "processed": 2}  # failures not counted


def test_history_delete_and_csv_export_neutralises_formulas(store, tmp_path):
    store.record(ENCRYPT, "=HYPERLINK(evil).png", "png", 5, SUCCESS)
    store.record(ENCRYPT, "ok.png", "png", 5, SUCCESS)
    out = tmp_path / "h.csv"
    assert store.export_csv(str(out)) == 2
    text = out.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK" in text and "Date/Time" in text
    store.delete([e.id for e in store.list() if e.file_name == "ok.png"])
    assert [e.file_name for e in store.list()] == ["=HYPERLINK(evil).png"]


# ---- settings ---------------------------------------------------------------------
def test_settings_persist_and_validate(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(path)
    s.set("theme", "light")
    s.set("kdf", "pbkdf2")
    assert Settings(path).get("theme") == "light" and Settings(path).kdf_params().kdf_id == 2
    with pytest.raises(ValueError):
        s.set("theme", "neon")
    with pytest.raises(KeyError):
        s.set("password", "hunter2")
    with pytest.raises(TypeError):
        s.set("record_history", "yes")


def test_settings_survive_corrupt_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert Settings(path).get("theme") == "dark"
    path.write_text('{"theme": "hacked", "kdf_level": 5}')
    s = Settings(path)
    assert s.get("theme") == "dark" and s.get("kdf_level") == "balanced"


def test_settings_file_contains_only_known_preferences(tmp_path):
    import json

    from utils.settings import DEFAULTS

    s = Settings(tmp_path / "s.json")
    s.set("export_dir", str(tmp_path))
    stored = json.loads((tmp_path / "s.json").read_text())
    assert set(stored) == set(DEFAULTS)  # nothing but the whitelisted preference keys
    assert all(isinstance(v, (bool, str)) for v in stored.values())
    with pytest.raises(KeyError):  # secrets cannot be injected through the settings API
        s.set("password", "hunter2")


# ---- self-test ---------------------------------------------------------------------
def test_self_test_passes():
    results = run_self_test()
    assert len(results) >= 8
    failed = [r for r in results if not r.passed]
    assert not failed, failed


def test_no_hardcoded_secrets_in_core():
    import re
    import pathlib

    core = pathlib.Path(__file__).resolve().parent.parent / "core"
    for py in core.glob("*.py"):
        src = py.read_text()
        assert not re.search(r"(?i)(password|secret|key)\s*=\s*[\"'][^\"']{6,}[\"']", src.replace("self-test", "")), py.name
