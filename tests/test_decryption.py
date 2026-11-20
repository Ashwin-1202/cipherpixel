"""Decryption-side tests (spec items 2, 3, 4, 5, 6, 12 + structural attacks)."""

from __future__ import annotations

import os
import struct

import pytest

from core.cpx_format import HEADER_LEN, LEN_PREFIX, LEN_PREFIX_SIZE
from core.decryption import decrypt_file, read_container_info
from core.encryption import encrypt_file
from core.errors import (
    AuthenticationError,
    CipherPixelError,
    EmptyFileError,
    IntegrityError,
    InvalidFormatError,
    OperationCancelled,
)


def _no_output(tmp_path, *names) -> None:
    for n in names:
        assert not (tmp_path / n).exists(), f"{n} must not exist after a failed decryption"
    assert [x for x in os.listdir(tmp_path) if x.endswith(".part")] == []


def _chunk_spans(blob: bytes) -> list[tuple[int, int]]:
    """(start, end) byte offsets of each length-prefixed chunk (meta first)."""
    spans, pos = [], HEADER_LEN
    while pos < len(blob):
        (n,) = LEN_PREFIX.unpack_from(blob, pos)
        spans.append((pos, pos + LEN_PREFIX_SIZE + n))
        pos += LEN_PREFIX_SIZE + n
    return spans


# 2 + 3 -- roundtrip, byte-for-byte --------------------------------------------
def test_roundtrip_is_byte_for_byte_identical(sample_image, tmp_path, password, kdf):
    enc, out = str(tmp_path / "e.cpx"), str(tmp_path / "restored")
    encrypt_file(sample_image, enc, password, kdf=kdf)
    result = decrypt_file(enc, out, password)
    assert open(out, "rb").read() == open(sample_image, "rb").read()
    assert result.integrity_verified and result.output_size == os.path.getsize(sample_image)
    assert result.original_name == os.path.basename(sample_image)
    assert result.image_format in {"PNG", "JPEG", "BMP", "TIFF"}
    assert (result.width, result.height) == (120, 80)


def test_roundtrip_large_multi_chunk(make_image, tmp_path, password, fast_kdf):
    src = make_image("big.bmp", 2400, 1800)
    enc, out = str(tmp_path / "big.cpx"), str(tmp_path / "big_restored.bmp")
    encrypt_file(src, enc, password, kdf=fast_kdf)
    decrypt_file(enc, out, password)
    assert open(out, "rb").read() == open(src, "rb").read()


@pytest.mark.parametrize("chunk", [4096, 4097, 10_000])
def test_roundtrip_odd_chunk_sizes(png_path, tmp_path, password, fast_kdf, chunk):
    enc, out = str(tmp_path / "e.cpx"), str(tmp_path / "o.png")
    encrypt_file(png_path, enc, password, kdf=fast_kdf, chunk_size=chunk)
    decrypt_file(enc, out, password)
    assert open(out, "rb").read() == open(png_path, "rb").read()


def test_unicode_password_and_normalisation(png_path, tmp_path, fast_kdf):
    enc, out = str(tmp_path / "e.cpx"), str(tmp_path / "o.png")
    composed, decomposed = "pässwörd-é-日本語-🔐", "pässwörd-é-日本語-🔐"
    encrypt_file(png_path, enc, composed, kdf=fast_kdf)
    decrypt_file(enc, out, decomposed)  # same visible text, different code points
    assert open(out, "rb").read() == open(png_path, "rb").read()


def test_filename_with_path_traversal_in_metadata_is_sanitised(tmp_path, password, fast_kdf, make_image):
    src = make_image("..evil name.png", 20, 20)
    enc, out = str(tmp_path / "e.cpx"), str(tmp_path / "o.png")
    encrypt_file(src, enc, password, kdf=fast_kdf)
    result = decrypt_file(enc, out, password)
    assert "/" not in result.suggested_filename and "\\" not in result.suggested_filename


def test_container_info_needs_no_password(encrypted):
    enc, _ = encrypted
    info = read_container_info(enc)
    assert info.version == 1 and info.kdf.name == "Argon2id" and info.chunk_size == 4096


# 4 -- incorrect password -------------------------------------------------------
@pytest.mark.parametrize("wrong", ["wrong-password", "Correct-Horse-Battery-Staple-9", " Correct-Horse-Battery-Staple-9!", "x"])
def test_wrong_password_rejected_without_output(encrypted, tmp_path, wrong):
    enc, _ = encrypted
    with pytest.raises(AuthenticationError) as exc:
        decrypt_file(enc, str(tmp_path / "out.png"), wrong)
    msg = exc.value.user_message.lower()
    assert "password" in msg and "key" not in msg and "tag" not in msg  # no crypto internals leaked
    _no_output(tmp_path, "out.png")


def test_existing_output_untouched_when_password_wrong(encrypted, tmp_path):
    enc, _ = encrypted
    out = tmp_path / "keep.png"
    out.write_bytes(b"precious")
    with pytest.raises(AuthenticationError):
        decrypt_file(enc, str(out), "nope")
    assert out.read_bytes() == b"precious"


# 5/6 -- corruption & modified ciphertext --------------------------------------
@pytest.mark.parametrize("where", ["header_salt", "header_kdf", "meta", "first_data", "middle", "last_chunk", "last_tag"])
def test_any_single_bit_flip_is_detected(encrypted, tmp_path, password, where):
    enc, _ = encrypted
    blob = bytearray(open(enc, "rb").read())
    spans = _chunk_spans(bytes(blob))
    pos = {
        "header_salt": 20,                    # inside the salt
        "header_kdf": 9,                      # KDF time-cost field
        "meta": spans[0][0] + LEN_PREFIX_SIZE + 3,
        "first_data": spans[1][0] + LEN_PREFIX_SIZE + 10,
        "middle": spans[len(spans) // 2][0] + LEN_PREFIX_SIZE + 5,
        "last_chunk": spans[-1][0] + LEN_PREFIX_SIZE + 1,
        "last_tag": len(blob) - 1,
    }[where]
    blob[pos] ^= 0x01
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(bytes(blob))
    with pytest.raises(CipherPixelError):
        decrypt_file(str(bad), str(tmp_path / "out.png"), password)
    _no_output(tmp_path, "out.png")


def test_bit_flip_in_every_chunk_detected(encrypted, tmp_path, password):
    enc, _ = encrypted
    original = open(enc, "rb").read()
    for start, end in _chunk_spans(original):
        blob = bytearray(original)
        blob[(start + end) // 2] ^= 0x80
        bad = tmp_path / "bad.cpx"
        bad.write_bytes(bytes(blob))
        with pytest.raises(CipherPixelError):
            decrypt_file(str(bad), str(tmp_path / "out.png"), password)
    _no_output(tmp_path, "out.png")


def test_corruption_after_valid_meta_reports_integrity_not_password(encrypted, tmp_path, password):
    enc, _ = encrypted
    blob = bytearray(open(enc, "rb").read())
    spans = _chunk_spans(bytes(blob))
    blob[spans[2][0] + LEN_PREFIX_SIZE + 2] ^= 0xFF
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(bytes(blob))
    with pytest.raises(IntegrityError):
        decrypt_file(str(bad), str(tmp_path / "out.png"), password)


def test_truncation_at_every_chunk_boundary_detected(encrypted, tmp_path, password):
    enc, _ = encrypted
    blob = open(enc, "rb").read()
    for _, end in _chunk_spans(blob)[:-1]:  # drop >= 1 trailing chunk, cut exactly on a boundary
        bad = tmp_path / "bad.cpx"
        bad.write_bytes(blob[:end])
        with pytest.raises(CipherPixelError):
            decrypt_file(str(bad), str(tmp_path / "out.png"), password)
    _no_output(tmp_path, "out.png")


@pytest.mark.parametrize("cut", [1, 5, 16, 17, 100])
def test_truncation_mid_chunk_detected(encrypted, tmp_path, password, cut):
    enc, _ = encrypted
    blob = open(enc, "rb").read()
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(blob[:-cut])
    with pytest.raises(CipherPixelError):
        decrypt_file(str(bad), str(tmp_path / "out.png"), password)
    _no_output(tmp_path, "out.png")


def test_appended_garbage_detected(encrypted, tmp_path, password):
    enc, _ = encrypted
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(open(enc, "rb").read() + b"\x00" * 64)
    with pytest.raises(CipherPixelError):
        decrypt_file(str(bad), str(tmp_path / "out.png"), password)
    _no_output(tmp_path, "out.png")


def test_appended_valid_looking_chunk_detected(encrypted, tmp_path, password):
    enc, _ = encrypted
    blob = open(enc, "rb").read()
    spans = _chunk_spans(blob)
    s, e = spans[2]
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(blob + blob[s:e])  # replay an authentic earlier chunk at the end
    with pytest.raises(CipherPixelError):
        decrypt_file(str(bad), str(tmp_path / "out.png"), password)


def test_reordered_chunks_detected(encrypted, tmp_path, password):
    enc, _ = encrypted
    blob = open(enc, "rb").read()
    spans = _chunk_spans(blob)
    (s1, e1), (s2, e2) = spans[1], spans[2]
    assert e1 - s1 == e2 - s2  # equal-size full chunks, so swap is structurally valid
    swapped = blob[:s1] + blob[s2:e2] + blob[s1:e1] + blob[e2:]
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(swapped)
    with pytest.raises(IntegrityError):
        decrypt_file(str(bad), str(tmp_path / "out.png"), password)
    _no_output(tmp_path, "out.png")


def test_duplicated_chunk_detected(encrypted, tmp_path, password):
    enc, _ = encrypted
    blob = open(enc, "rb").read()
    s, e = _chunk_spans(blob)[1]
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(blob[:e] + blob[s:])  # chunk 1 appears twice
    with pytest.raises(IntegrityError):
        decrypt_file(str(bad), str(tmp_path / "out.png"), password)


def test_removed_middle_chunk_detected(encrypted, tmp_path, password):
    enc, _ = encrypted
    blob = open(enc, "rb").read()
    s, e = _chunk_spans(blob)[2]
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(blob[:s] + blob[e:])
    with pytest.raises(IntegrityError):
        decrypt_file(str(bad), str(tmp_path / "out.png"), password)


def test_chunk_from_another_file_with_same_password_rejected(png_path, tmp_path, password, fast_kdf):
    """Splicing: different salt/nonce prefix => different key & AAD => tag failure."""
    a, b = str(tmp_path / "a.cpx"), str(tmp_path / "b.cpx")
    encrypt_file(png_path, a, password, kdf=fast_kdf, chunk_size=4096)
    encrypt_file(png_path, b, password, kdf=fast_kdf, chunk_size=4096)
    ba, bb = open(a, "rb").read(), open(b, "rb").read()
    sa, ea = _chunk_spans(ba)[2]
    sb, eb = _chunk_spans(bb)[2]
    spliced = ba[:sa] + bb[sb:eb] + ba[ea:]
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(spliced)
    with pytest.raises(IntegrityError):
        decrypt_file(str(bad), str(tmp_path / "o.png"), password)


def test_header_swap_between_files_rejected(png_path, tmp_path, password, fast_kdf):
    a, b = str(tmp_path / "a.cpx"), str(tmp_path / "b.cpx")
    encrypt_file(png_path, a, password, kdf=fast_kdf, chunk_size=4096)
    encrypt_file(png_path, b, password, kdf=fast_kdf, chunk_size=4096)
    ba, bb = open(a, "rb").read(), open(b, "rb").read()
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(bb[:HEADER_LEN] + ba[HEADER_LEN:])
    with pytest.raises(CipherPixelError):
        decrypt_file(str(bad), str(tmp_path / "o.png"), password)


# 8 -- empty .cpx ---------------------------------------------------------------
def test_empty_cpx_rejected(tmp_path, password):
    p = tmp_path / "empty.cpx"
    p.write_bytes(b"")
    with pytest.raises(EmptyFileError):
        decrypt_file(str(p), str(tmp_path / "o.png"), password)


# 12 -- invalid headers ---------------------------------------------------------
def _write_with_header_edit(encrypted, tmp_path, edit):
    enc, _ = encrypted
    blob = bytearray(open(enc, "rb").read())
    edit(blob)
    bad = tmp_path / "hdr.cpx"
    bad.write_bytes(bytes(blob))
    return str(bad)


@pytest.mark.parametrize(
    "label, edit",
    [
        ("bad magic", lambda b: b.__setitem__(slice(0, 4), b"NOPE")),
        ("future version", lambda b: b.__setitem__(4, 99)),
        ("version zero", lambda b: b.__setitem__(4, 0)),
        ("unknown kdf id", lambda b: b.__setitem__(5, 77)),
        ("nonzero flags", lambda b: b.__setitem__(slice(6, 8), b"\x00\x01")),
        ("argon2 memory too big", lambda b: b.__setitem__(slice(12, 16), struct.pack(">I", 2**31))),
        ("argon2 memory too small", lambda b: b.__setitem__(slice(12, 16), struct.pack(">I", 1))),
        ("argon2 time zero", lambda b: b.__setitem__(slice(8, 12), struct.pack(">I", 0))),
        ("argon2 time huge", lambda b: b.__setitem__(slice(8, 12), struct.pack(">I", 10**9))),
        ("argon2 parallelism zero", lambda b: b.__setitem__(slice(16, 20), struct.pack(">I", 0))),
        ("chunk size zero", lambda b: b.__setitem__(slice(20, 24), struct.pack(">I", 0))),
        ("chunk size huge", lambda b: b.__setitem__(slice(20, 24), struct.pack(">I", 2**31))),
    ],
)
def test_invalid_headers_rejected_before_any_expensive_work(encrypted, tmp_path, password, label, edit):
    path = _write_with_header_edit(encrypted, tmp_path, edit)
    with pytest.raises(InvalidFormatError):
        decrypt_file(path, str(tmp_path / "o.png"), password)
    _no_output(tmp_path, "o.png")


@pytest.mark.parametrize("size", [1, 10, 47, 48, 49, 60])
def test_too_short_files_rejected(tmp_path, password, size):
    p = tmp_path / "short.cpx"
    p.write_bytes(b"CPXF" + b"\x01" * 100)  # valid-looking magic prefix
    p.write_bytes(p.read_bytes()[:size])
    with pytest.raises(InvalidFormatError):
        decrypt_file(str(p), str(tmp_path / "o.png"), password)


def test_random_and_non_cpx_files_rejected(tmp_path, password, png_path):
    junk = tmp_path / "junk.cpx"
    junk.write_bytes(os.urandom(5000))
    with pytest.raises(InvalidFormatError):
        decrypt_file(str(junk), str(tmp_path / "o.png"), password)
    with pytest.raises(InvalidFormatError):  # a plain image given as .cpx
        decrypt_file(png_path, str(tmp_path / "o2.png"), password)


def test_missing_file_rejected(tmp_path, password):
    with pytest.raises(CipherPixelError):
        decrypt_file(str(tmp_path / "ghost.cpx"), str(tmp_path / "o.png"), password)


def test_huge_chunk_length_field_rejected_without_allocating(encrypted, tmp_path, password):
    enc, _ = encrypted
    blob = bytearray(open(enc, "rb").read())
    blob[HEADER_LEN : HEADER_LEN + 4] = struct.pack(">I", 0xFFFFFFF0)  # meta length lies
    bad = tmp_path / "bad.cpx"
    bad.write_bytes(bytes(blob))
    with pytest.raises(CipherPixelError):
        decrypt_file(str(bad), str(tmp_path / "o.png"), password)


def test_refuses_to_overwrite_encrypted_source(encrypted, password):
    enc, _ = encrypted
    before = open(enc, "rb").read()
    with pytest.raises(CipherPixelError):
        decrypt_file(enc, enc, password)
    assert open(enc, "rb").read() == before


def test_cancel_during_decrypt_leaves_nothing(encrypted, tmp_path, password):
    import threading

    enc, _ = encrypted
    ev = threading.Event()

    def progress(stage, frac):
        if stage == "decrypting" and frac > 0.5:
            ev.set()

    with pytest.raises(OperationCancelled):
        decrypt_file(enc, str(tmp_path / "o.png"), password, progress=progress, cancel=ev)
    _no_output(tmp_path, "o.png")


def test_error_messages_never_contain_secrets(encrypted, tmp_path, password):
    enc, _ = encrypted
    with pytest.raises(AuthenticationError) as exc:
        decrypt_file(enc, str(tmp_path / "o.png"), "super-secret-attempt")
    text = f"{exc.value} {exc.value.user_message} {exc.value.detail}"
    assert "super-secret-attempt" not in text
