"""Encryption-side tests (spec items 1, 7, 8, 9, 10, 11)."""

from __future__ import annotations

import os
import threading

import pytest

from core.cpx_format import HEADER_LEN, MAGIC, chunk_nonce, parse_header
from core.encryption import encrypt_file, suggested_output_name
from core.errors import (
    CipherPixelError,
    EmptyFileError,
    OperationCancelled,
    UnsupportedImageError,
)


def _leftovers(directory) -> list[str]:
    return [n for n in os.listdir(directory) if n.endswith(".part") or n.startswith(".cipherpixel-")]


# 1 -- successful encryption ----------------------------------------------------
def test_encrypt_succeeds_for_every_supported_format_and_kdf(sample_image, tmp_path, password, kdf):
    dst = str(tmp_path / "out.cpx")
    result = encrypt_file(sample_image, dst, password, kdf=kdf)
    assert os.path.exists(dst)
    assert result.output_size == os.path.getsize(dst) > result.input_size
    assert result.image_format in {"PNG", "JPEG", "BMP", "TIFF"}
    with open(dst, "rb") as fh:
        header = parse_header(fh.read(HEADER_LEN))
    assert header.kdf == kdf and header.version == 1
    assert _leftovers(tmp_path) == []


def test_ciphertext_does_not_contain_plaintext_or_filename(png_path, tmp_path, password, fast_kdf):
    dst = str(tmp_path / "out.cpx")
    encrypt_file(png_path, dst, password, kdf=fast_kdf)
    blob = open(dst, "rb").read()
    plain = open(png_path, "rb").read()
    assert blob.startswith(MAGIC)
    assert plain[:64] not in blob and b"IHDR" not in blob
    assert os.path.basename(png_path).encode() not in blob  # original name is encrypted


def test_multi_chunk_and_exact_chunk_boundary(make_image, tmp_path, password, fast_kdf):
    path = make_image("b.bmp", 64, 64)
    size = os.path.getsize(path)
    for chunk in (4096, 5000, size, size + 1):
        if chunk < 4096:
            continue
        r = encrypt_file(path, str(tmp_path / f"o{chunk}.cpx"), password, kdf=fast_kdf, chunk_size=chunk)
        assert r.chunk_count == -(-size // chunk)


def test_suggested_output_name():
    assert suggested_output_name("/x/y/holiday.JPG") == "holiday.cpx"


def test_empty_password_rejected(png_path, tmp_path, fast_kdf):
    with pytest.raises(CipherPixelError):
        encrypt_file(png_path, str(tmp_path / "o.cpx"), "", kdf=fast_kdf)


# 7 -- unsupported formats ------------------------------------------------------
@pytest.mark.parametrize("name", ["note.txt", "doc.pdf", "anim.gif", "icon.webp", "noext"])
def test_unsupported_extensions_rejected(tmp_path, name, password, fast_kdf):
    p = tmp_path / name
    p.write_bytes(b"not an image at all" * 20)
    with pytest.raises(UnsupportedImageError):
        encrypt_file(str(p), str(tmp_path / "o.cpx"), password, kdf=fast_kdf)
    assert not (tmp_path / "o.cpx").exists()


def test_text_disguised_as_png_rejected(tmp_path, password, fast_kdf):
    p = tmp_path / "fake.png"
    p.write_text("this is plain text pretending to be a PNG")
    with pytest.raises(UnsupportedImageError):
        encrypt_file(str(p), str(tmp_path / "o.cpx"), password, kdf=fast_kdf)


def test_gif_disguised_as_png_rejected(tmp_path, password, fast_kdf):
    from PIL import Image

    p = tmp_path / "sneaky.png"
    Image.new("P", (8, 8)).save(p, "GIF")  # real GIF content, .png name
    with pytest.raises(UnsupportedImageError):
        encrypt_file(str(p), str(tmp_path / "o.cpx"), password, kdf=fast_kdf)


def test_truncated_image_rejected(png_path, tmp_path, password, fast_kdf):
    data = open(png_path, "rb").read()
    p = tmp_path / "cut.png"
    p.write_bytes(data[:20])
    with pytest.raises(UnsupportedImageError):
        encrypt_file(str(p), str(tmp_path / "o.cpx"), password, kdf=fast_kdf)


def test_missing_source_rejected(tmp_path, password, fast_kdf):
    with pytest.raises(CipherPixelError):
        encrypt_file(str(tmp_path / "nope.png"), str(tmp_path / "o.cpx"), password, kdf=fast_kdf)


# 8 -- empty files --------------------------------------------------------------
def test_empty_file_rejected(tmp_path, password, fast_kdf):
    p = tmp_path / "empty.png"
    p.write_bytes(b"")
    with pytest.raises(EmptyFileError):
        encrypt_file(str(p), str(tmp_path / "o.cpx"), password, kdf=fast_kdf)


# 9 -- large files --------------------------------------------------------------
def test_large_image_streams_in_many_chunks(make_image, tmp_path, password, fast_kdf):
    path = make_image("large.bmp", 2400, 1800)  # ~13 MB uncompressed
    assert os.path.getsize(path) > 12_000_000
    seen: list[float] = []
    r = encrypt_file(path, str(tmp_path / "large.cpx"), password, kdf=fast_kdf,
                     progress=lambda s, f: seen.append(f))
    assert r.chunk_count >= 12  # default 1 MiB chunks
    assert seen == sorted(seen) and seen[-1] == 1.0  # monotonic progress


# 10/11 -- unique nonces and salts ---------------------------------------------
def test_unique_salt_and_nonce_for_each_encryption(png_path, tmp_path, password, fast_kdf):
    salts, prefixes, blobs = set(), set(), set()
    for i in range(25):
        r = encrypt_file(png_path, str(tmp_path / f"{i}.cpx"), password, kdf=fast_kdf)
        salts.add(r.salt)
        prefixes.add(r.nonce_prefix)
        blobs.add(open(r.output_path, "rb").read())
    assert len(salts) == len(prefixes) == len(blobs) == 25


def test_chunk_nonces_are_unique_within_a_file():
    prefix = b"\x01" * 8
    nonces = {chunk_nonce(prefix, i) for i in range(5000)}
    assert len(nonces) == 5000 and all(len(n) == 12 for n in nonces)  # 96-bit nonces


def test_nonce_counter_exhaustion_is_refused():
    with pytest.raises(ValueError):
        chunk_nonce(b"\x00" * 8, 2**32)


# Safety ------------------------------------------------------------------------
def test_refuses_to_overwrite_source(png_path, password, fast_kdf):
    before = open(png_path, "rb").read()
    with pytest.raises(CipherPixelError):
        encrypt_file(png_path, png_path, password, kdf=fast_kdf)
    assert open(png_path, "rb").read() == before


def test_cancel_leaves_no_output(make_image, tmp_path, password, fast_kdf):
    path = make_image("c.bmp", 1200, 900)
    ev = threading.Event()

    def progress(stage, frac):
        if stage == "encrypting" and frac > 0.4:
            ev.set()

    dst = tmp_path / "c.cpx"
    with pytest.raises(OperationCancelled):
        encrypt_file(path, str(dst), password, kdf=fast_kdf, chunk_size=4096, progress=progress, cancel=ev)
    assert not dst.exists() and _leftovers(tmp_path) == []


def test_failure_does_not_clobber_existing_output(png_path, tmp_path, password, fast_kdf):
    dst = tmp_path / "keep.cpx"
    dst.write_bytes(b"previous good file")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"junk")
    with pytest.raises(UnsupportedImageError):
        encrypt_file(str(bad), str(dst), password, kdf=fast_kdf)
    assert dst.read_bytes() == b"previous good file"


def test_unwritable_destination_directory(png_path, tmp_path, password, fast_kdf):
    with pytest.raises(CipherPixelError):
        encrypt_file(png_path, str(tmp_path / "missing_dir" / "o.cpx"), password, kdf=fast_kdf)


def test_invalid_kdf_parameters_rejected(png_path, tmp_path, password):
    from core.key_manager import KdfParams

    with pytest.raises(CipherPixelError):
        encrypt_file(png_path, str(tmp_path / "o.cpx"), password, kdf=KdfParams.pbkdf2(10))
