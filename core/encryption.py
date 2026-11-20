"""Streaming image encryption (AES-256-GCM, chunked, header-bound)."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .cpx_format import (
    CHUNK_DATA,
    CHUNK_FINAL,
    CHUNK_META,
    DEFAULT_CHUNK_SIZE,
    EXTENSION,
    FORMAT_VERSION,
    HEADER_LEN,
    LEN_PREFIX,
    MAX_COUNTER,
    MAX_META_LEN,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    NONCE_PREFIX_LEN,
    SALT_LEN,
    TAG_LEN,
    pack_header,
    parse_header,
    seal_chunk,
)
from .errors import CipherPixelError, EmptyFileError, OperationCancelled
from .file_handler import atomic_write, ensure_free_space, inspect_image, same_file, translate_oserror
from .key_manager import KdfParams, default_kdf, derive_key
from .security_utils import sha256_file

ProgressFn = Callable[[str, float], None]

# Overall progress is split into phases so the UI bar moves smoothly.
_P_VALIDATE_END = 0.08
_P_KEY_END = 0.20
_P_ENCRYPT_END = 0.98


@dataclass(frozen=True)
class EncryptionResult:
    output_path: str
    input_size: int
    output_size: int
    kdf: KdfParams
    original_name: str
    image_format: str
    width: int
    height: int
    sha256: str
    chunk_count: int
    duration_s: float
    salt: bytes
    nonce_prefix: bytes


class _Ctl:
    """Small helper combining progress reporting and cooperative cancellation."""

    def __init__(self, progress: ProgressFn | None, cancel: threading.Event | None) -> None:
        self._progress = progress
        self._cancel = cancel

    def check(self) -> None:
        if self._cancel is not None and self._cancel.is_set():
            raise OperationCancelled()

    def report(self, stage: str, fraction: float) -> None:
        if self._progress:
            self._progress(stage, max(0.0, min(1.0, fraction)))


def suggested_output_name(image_name: str) -> str:
    return os.path.splitext(os.path.basename(image_name))[0] + EXTENSION


def encrypt_file(
    src: str,
    dst: str,
    password: str,
    *,
    kdf: KdfParams | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress: ProgressFn | None = None,
    cancel: threading.Event | None = None,
) -> EncryptionResult:
    """Encrypt the image at ``src`` into a ``.cpx`` container at ``dst``.

    The *original file bytes* are encrypted (not re-encoded pixels), so decryption
    restores the file bit-for-bit, including EXIF/ICC metadata and compression.
    Memory use is bounded by ~2 chunks regardless of image size.

    Raises :class:`CipherPixelError` subclasses for all expected failures; ``dst`` is
    only created if the whole operation succeeds.
    """
    ctl = _Ctl(progress, cancel)
    started = time.perf_counter()

    kdf = kdf or default_kdf()
    try:
        kdf.validate()
    except ValueError as exc:
        raise CipherPixelError("Invalid key-derivation settings.", detail=str(exc)) from exc
    if not MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError("chunk_size out of range")
    if not password:
        raise CipherPixelError("A password is required.")

    ctl.report("validating", 0.0)
    info = inspect_image(src)
    if same_file(src, dst):
        raise CipherPixelError("The output file must be different from the source image.")
    ensure_free_space(os.path.dirname(os.path.abspath(dst)), info.size + 4096)

    ctl.check()
    digest = sha256_file(src, check=ctl.check)
    ctl.report("validating", _P_VALIDATE_END)

    # Fresh randomness for every encryption (OS CSPRNG).
    salt = secrets.token_bytes(SALT_LEN)
    nonce_prefix = secrets.token_bytes(NONCE_PREFIX_LEN)
    header_raw = pack_header(kdf, chunk_size, salt, nonce_prefix)
    header = parse_header(header_raw)

    ctl.report("deriving_key", _P_VALIDATE_END)
    key = derive_key(password, salt, kdf)
    aead = AESGCM(key)
    ctl.check()
    ctl.report("encrypting", _P_KEY_END)

    meta = json.dumps(
        {
            "v": FORMAT_VERSION,
            "name": info.name,
            "format": info.format,
            "width": info.width,
            "height": info.height,
            "mode": info.mode,
            "size": info.size,
            "sha256": digest,
            "created": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(meta) > MAX_META_LEN - TAG_LEN:
        raise CipherPixelError("Image metadata is too large.")

    chunks = 0
    try:
        with open(src, "rb") as fin, atomic_write(dst) as fout:
            fout.write(header_raw)
            sealed_meta = seal_chunk(aead, header, CHUNK_META, 0, meta)
            fout.write(LEN_PREFIX.pack(len(sealed_meta)))
            fout.write(sealed_meta)

            counter = 1
            done = 0
            check = hashlib.sha256()
            current = fin.read(chunk_size)
            if not current:
                raise EmptyFileError()
            while True:
                ctl.check()
                nxt = fin.read(chunk_size)  # read-ahead tells us which chunk is last
                final = not nxt
                if counter > MAX_COUNTER:
                    raise CipherPixelError("The file is too large to encrypt with this chunk size.")
                check.update(current)
                sealed = seal_chunk(aead, header, CHUNK_FINAL if final else CHUNK_DATA, counter, current)
                fout.write(LEN_PREFIX.pack(len(sealed)))
                fout.write(sealed)
                done += len(current)
                chunks += 1
                counter += 1
                ctl.report("encrypting", _P_KEY_END + (_P_ENCRYPT_END - _P_KEY_END) * (done / info.size))
                if final:
                    break
                current = nxt

            if done != info.size or check.hexdigest() != digest:
                raise CipherPixelError("The source image changed while it was being encrypted. Please try again.")
            ctl.report("finalizing", _P_ENCRYPT_END)
    except OSError as exc:
        raise translate_oserror(exc) from exc

    out_size = os.path.getsize(dst)
    ctl.report("finalizing", 1.0)
    return EncryptionResult(
        output_path=dst,
        input_size=info.size,
        output_size=out_size,
        kdf=kdf,
        original_name=info.name,
        image_format=info.format,
        width=info.width,
        height=info.height,
        sha256=digest,
        chunk_count=chunks,
        duration_s=time.perf_counter() - started,
        salt=salt,
        nonce_prefix=nonce_prefix,
    )


__all__ = ["encrypt_file", "EncryptionResult", "suggested_output_name", "HEADER_LEN"]
