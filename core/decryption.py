"""Streaming, authenticated decryption of ``.cpx`` containers."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .cpx_format import (
    CHUNK_DATA,
    CHUNK_FINAL,
    CHUNK_META,
    HEADER_LEN,
    LEN_PREFIX,
    LEN_PREFIX_SIZE,
    MAX_META_LEN,
    TAG_LEN,
    Header,
    open_chunk,
    parse_header,
)
from .errors import (
    AuthenticationError,
    CipherPixelError,
    EmptyFileError,
    FileAccessError,
    IntegrityError,
    InvalidFormatError,
    OperationCancelled,
)
from .file_handler import atomic_write, ensure_free_space, same_file, translate_oserror
from .key_manager import KdfParams, derive_key
from .security_utils import sanitize_filename

ProgressFn = Callable[[str, float], None]

_P_KEY_START = 0.05
_P_KEY_END = 0.25
_P_DECRYPT_END = 0.98
_MIN_FILE = HEADER_LEN + 2 * (LEN_PREFIX_SIZE + TAG_LEN + 1)  # header + meta + >=1 data byte


@dataclass(frozen=True)
class ContainerInfo:
    """Facts readable *without* the password (nothing sensitive is exposed)."""

    path: str
    file_size: int
    version: int
    kdf: KdfParams
    chunk_size: int


@dataclass(frozen=True)
class DecryptionResult:
    output_path: str
    output_size: int
    original_name: str
    suggested_filename: str
    image_format: str
    width: int
    height: int
    mode: str
    sha256: str
    kdf: KdfParams
    container_version: int
    chunk_count: int
    duration_s: float
    integrity_verified: bool


def _read_exact(fh, n: int) -> bytes:
    data = fh.read(n)
    if len(data) != n:
        raise IntegrityError("The file is truncated or corrupted.")
    return data


def read_container_info(path: str) -> ContainerInfo:
    """Parse the plaintext header only.  Raises :class:`InvalidFormatError`/:class:`EmptyFileError`."""
    try:
        if not os.path.isfile(path):
            raise FileAccessError("The selected file does not exist or is not a regular file.")
        size = os.path.getsize(path)
        if size == 0:
            raise EmptyFileError()
        if size < _MIN_FILE:
            raise InvalidFormatError("The file is too short to be a CipherPixel file.")
        with open(path, "rb") as fh:
            header = parse_header(fh.read(HEADER_LEN))
    except OSError as exc:
        raise translate_oserror(exc) from exc
    return ContainerInfo(path, size, header.version, header.kdf, header.chunk_size)


def _read_sealed(fh, limit: int, file_size: int) -> bytes:
    (length,) = LEN_PREFIX.unpack(_read_exact(fh, LEN_PREFIX_SIZE))
    if length < TAG_LEN + 1 or length > limit:
        raise IntegrityError("The file is corrupted (invalid chunk length).")
    if length > file_size - fh.tell():
        raise IntegrityError("The file is truncated or corrupted.")
    return _read_exact(fh, length)


def _parse_meta(plain: bytes) -> dict:
    try:
        meta = json.loads(plain.decode("utf-8"))
        ok = (
            isinstance(meta, dict)
            and isinstance(meta.get("name"), str)
            and isinstance(meta.get("format"), str)
            and isinstance(meta.get("size"), int)
            and meta["size"] > 0
            and isinstance(meta.get("sha256"), str)
            and len(meta["sha256"]) == 64
        )
    except (ValueError, UnicodeDecodeError):
        ok = False
    if not ok:
        raise IntegrityError("The file's metadata is invalid.")
    return meta


def decrypt_file(
    src: str,
    dst: str,
    password: str,
    *,
    progress: ProgressFn | None = None,
    cancel: threading.Event | None = None,
) -> DecryptionResult:
    """Authenticate and decrypt ``src`` into ``dst``.

    Security properties
    -------------------
    * Every chunk's GCM tag is verified *before* its plaintext is written.
    * Output goes to a temporary file and is moved to ``dst`` only after the final
      chunk verifies, the size matches, and the SHA-256 matches – so a truncated,
      reordered or tampered container never yields a usable output file.
    * Wrong password and header tampering are reported identically (no oracle).
    """
    started = time.perf_counter()

    def check() -> None:
        if cancel is not None and cancel.is_set():
            raise OperationCancelled()

    def report(stage: str, frac: float) -> None:
        if progress:
            progress(stage, max(0.0, min(1.0, frac)))

    report("validating", 0.0)
    info = read_container_info(src)
    if same_file(src, dst):
        raise CipherPixelError("The output file must be different from the encrypted file.")
    if not password:
        raise CipherPixelError("A password is required.")
    file_size = info.file_size

    try:
        with open(src, "rb") as fin:
            header: Header = parse_header(_read_exact(fin, HEADER_LEN))
            report("deriving_key", _P_KEY_START)
            check()
            key = derive_key(password, header.salt, header.kdf)
            aead = AESGCM(key)
            check()
            report("decrypting", _P_KEY_END)

            # --- Metadata chunk: doubles as the password check -------------------
            sealed_meta = _read_sealed(fin, MAX_META_LEN, file_size)
            try:
                meta_plain = open_chunk(aead, header, CHUNK_META, 0, sealed_meta)
            except InvalidTag:
                raise AuthenticationError() from None
            meta = _parse_meta(meta_plain)
            expected_size: int = meta["size"]

            ensure_free_space(os.path.dirname(os.path.abspath(dst)), expected_size + 4096)

            digest = hashlib.sha256()
            done = 0
            counter = 1
            chunks = 0
            max_sealed = header.chunk_size + TAG_LEN
            with atomic_write(dst) as fout:
                while True:
                    check()
                    sealed = _read_sealed(fin, max_sealed, file_size)
                    final = fin.tell() == file_size  # last chunk in file must be typed FINAL
                    try:
                        plain = open_chunk(aead, header, CHUNK_FINAL if final else CHUNK_DATA, counter, sealed)
                    except InvalidTag:
                        raise IntegrityError() from None
                    fout.write(plain)
                    digest.update(plain)
                    done += len(plain)
                    chunks += 1
                    counter += 1
                    if done > expected_size:
                        raise IntegrityError()
                    report("decrypting", _P_KEY_END + (_P_DECRYPT_END - _P_KEY_END) * min(1.0, done / expected_size))
                    if final:
                        break

                # Defence in depth on top of per-chunk GCM tags.
                if done != expected_size or not hmac.compare_digest(digest.hexdigest(), meta["sha256"]):
                    raise IntegrityError()
                report("verifying", _P_DECRYPT_END)
    except OSError as exc:
        raise translate_oserror(exc) from exc

    report("verifying", 1.0)
    original = str(meta["name"])
    return DecryptionResult(
        output_path=dst,
        output_size=done,
        original_name=original,
        suggested_filename=sanitize_filename(original),
        image_format=str(meta.get("format", "")),
        width=int(meta.get("width", 0) or 0),
        height=int(meta.get("height", 0) or 0),
        mode=str(meta.get("mode", "")),
        sha256=meta["sha256"],
        kdf=header.kdf,
        container_version=header.version,
        chunk_count=chunks,
        duration_s=time.perf_counter() - started,
        integrity_verified=True,
    )
