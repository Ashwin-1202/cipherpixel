"""Shared fixtures.  Tests use the *minimum* allowed KDF cost so the suite is fast;
production presets are exercised separately in test_security.py."""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.key_manager import KdfParams  # noqa: E402

PASSWORD = "Correct-Horse-Battery-Staple-9!"
FAST_ARGON2 = KdfParams.argon2id(1, 8 * 1024, 1)
FAST_PBKDF2 = KdfParams.pbkdf2(100_000)


@pytest.fixture
def password() -> str:
    return PASSWORD


@pytest.fixture(params=[FAST_ARGON2, FAST_PBKDF2], ids=["argon2id", "pbkdf2"])
def kdf(request) -> KdfParams:
    return request.param


@pytest.fixture
def fast_kdf() -> KdfParams:
    return FAST_ARGON2


def _noise_image(w: int, h: int, mode: str = "RGB") -> Image.Image:
    rng = np.random.default_rng(1234)
    channels = {"RGB": 3, "L": 1, "RGBA": 4}[mode]
    shape = (h, w) if channels == 1 else (h, w, channels)
    return Image.fromarray(rng.integers(0, 256, size=shape, dtype=np.uint8), mode)


@pytest.fixture(params=["png", "jpg", "jpeg", "bmp", "tiff"])
def sample_image(request, tmp_path) -> str:
    fmt = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "bmp": "BMP", "tiff": "TIFF"}[request.param]
    path = tmp_path / f"sample.{request.param}"
    _noise_image(120, 80).save(path, fmt)
    return str(path)


@pytest.fixture
def png_path(tmp_path) -> str:
    path = tmp_path / "photo.png"
    _noise_image(200, 150).save(path, "PNG")
    return str(path)


@pytest.fixture
def make_image(tmp_path):
    def _make(name: str, w: int, h: int, mode: str = "RGB") -> str:
        p = tmp_path / name
        _noise_image(w, h, mode).save(p)
        return str(p)

    return _make


@pytest.fixture
def encrypted(png_path, tmp_path, password, fast_kdf):
    """A small multi-chunk container plus its source path."""
    from core.encryption import encrypt_file

    dst = str(tmp_path / "photo.cpx")
    result = encrypt_file(png_path, dst, password, kdf=fast_kdf, chunk_size=4096)
    assert result.chunk_count > 3, "fixture must produce several chunks"
    return dst, png_path
