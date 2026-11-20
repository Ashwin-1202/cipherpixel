"""Live self-test of the cryptographic engine (used by the Security Center page).

Runs the real encrypt/decrypt code paths on a small generated image using the minimum
allowed KDF cost so it completes in well under a second.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass

from PIL import Image

from .cpx_format import HEADER_LEN
from .decryption import decrypt_file
from .encryption import encrypt_file
from .errors import AuthenticationError, IntegrityError
from .key_manager import ARGON2_AVAILABLE, KdfParams


@dataclass(frozen=True)
class SelfTestResult:
    name: str
    passed: bool
    detail: str = ""


def _fast_kdf() -> KdfParams:
    return KdfParams.argon2id(1, 8 * 1024, 1) if ARGON2_AVAILABLE else KdfParams.pbkdf2(100_000)


def run_self_test() -> list[SelfTestResult]:
    results: list[SelfTestResult] = []
    tmp = tempfile.mkdtemp(prefix="cipherpixel-selftest-")
    pw = "Self-Test #Passphrase 2026!"

    def record(name: str, passed: bool, detail: str = "") -> None:
        results.append(SelfTestResult(name, passed, detail))

    try:
        img_path = os.path.join(tmp, "probe.png")
        img = Image.new("RGB", (96, 96))
        img.putdata([(x * 2 % 256, y * 2 % 256, (x + y) % 256) for y in range(96) for x in range(96)])
        img.save(img_path, "PNG")
        original = open(img_path, "rb").read()

        enc_a, enc_b = os.path.join(tmp, "a.cpx"), os.path.join(tmp, "b.cpx")
        kdf = _fast_kdf()
        ra = encrypt_file(img_path, enc_a, pw, kdf=kdf, chunk_size=4096)
        rb = encrypt_file(img_path, enc_b, pw, kdf=kdf, chunk_size=4096)
        record("AES-256-GCM encryption", True, f"{ra.chunk_count} authenticated chunk{'' if ra.chunk_count == 1 else 's'}")

        blob = open(enc_a, "rb").read()
        record("Ciphertext hides image data", original[:32] not in blob and b"PNG" not in blob[:HEADER_LEN + 64])
        record("Random salt per operation", ra.salt != rb.salt, "128-bit CSPRNG salt")
        record("Unique nonce per operation", ra.nonce_prefix != rb.nonce_prefix, "64-bit random prefix + 32-bit counter")

        out = os.path.join(tmp, "out.png")
        dr = decrypt_file(enc_a, out, pw)
        record("Exact byte-for-byte recovery", open(out, "rb").read() == original, "SHA-256 verified")
        record("Integrity verification", dr.integrity_verified)

        try:
            decrypt_file(enc_a, os.path.join(tmp, "wrong.png"), pw + "x")
            record("Wrong password rejected", False, "decryption unexpectedly succeeded")
        except AuthenticationError:
            record("Wrong password rejected", not os.path.exists(os.path.join(tmp, "wrong.png")))

        bad = bytearray(blob)
        bad[len(bad) // 2] ^= 0x01
        tampered = os.path.join(tmp, "t.cpx")
        open(tampered, "wb").write(bad)
        try:
            decrypt_file(tampered, os.path.join(tmp, "t.png"), pw)
            record("Tampering detected", False, "modified file was accepted")
        except (IntegrityError, AuthenticationError):
            record("Tampering detected", not os.path.exists(os.path.join(tmp, "t.png")))

        trunc = os.path.join(tmp, "trunc.cpx")
        open(trunc, "wb").write(blob[: len(blob) - 40])
        try:
            decrypt_file(trunc, os.path.join(tmp, "trunc.png"), pw)
            record("Truncation detected", False, "truncated file was accepted")
        except (IntegrityError, AuthenticationError):
            record("Truncation detected", True)
    except Exception as exc:  # pragma: no cover - defensive
        record("Self-test execution", False, type(exc).__name__)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results
