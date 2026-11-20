"""The ``.cpx`` container format (version 1).

Layout
------
::

    +-------------------------------------------------------------+
    | HEADER (48 bytes, plaintext but authenticated as AAD)        |
    |   magic "CPXF" | version u8 | kdf_id u8 | flags u16 (=0)       |
    |   kdf p1 u32 | p2 u32 | p3 u32 | chunk_size u32              |
    |   salt (16) | nonce_prefix (8)                               |
    +-------------------------------------------------------------+
    | META CHUNK   : u32 length | AES-GCM(ciphertext || 16-byte tag)|
    |   JSON: original name, format, size, dimensions, SHA-256      |
    +-------------------------------------------------------------+
    | DATA CHUNK 1 : u32 length | AES-GCM(ciphertext || tag)        |
    | ...                                                          |
    | FINAL CHUNK  : u32 length | AES-GCM(ciphertext || tag)        |
    +-------------------------------------------------------------+

Cryptographic design (standard primitives only – nothing custom)
----------------------------------------------------------------
* Cipher: AES-256-GCM from the ``cryptography`` library.
* One key per file: ``key = KDF(password, random 128-bit salt)``.
* Per-chunk 96-bit nonce = ``8 random bytes (per file) || 32-bit big-endian counter``.
  Because the key is unique per file *and* the counter is unique per chunk, a
  (key, nonce) pair is never repeated.
* Per-chunk associated data (AAD) = ``entire header || chunk type || counter``.
  Consequences:
    - modifying any header byte (salt, KDF params, chunk size, ...) breaks every tag;
    - reordering, duplicating or swapping chunks breaks tags (counter is bound);
    - truncating the file removes the chunk typed FINAL, so truncation is detected;
    - appending data is detected because the real final chunk was not typed as last.
* The length prefix is not itself authenticated, but any alteration makes the
  chunk boundaries (and therefore the tags) wrong, which is detected.
* Original filename and image metadata are inside the encrypted META chunk, so
  the container reveals only its size, KDF choice and chunk size.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import InvalidFormatError
from .key_manager import KdfParams

MAGIC = b"CPXF"
FORMAT_VERSION = 1
EXTENSION = ".cpx"

SALT_LEN = 16
NONCE_PREFIX_LEN = 8
TAG_LEN = 16

KIB = 1024
MIB = 1024 * 1024
DEFAULT_CHUNK_SIZE = 1 * MIB
MIN_CHUNK_SIZE = 4 * KIB
MAX_CHUNK_SIZE = 64 * MIB
MAX_META_LEN = 64 * KIB
MAX_COUNTER = 0xFFFFFFFF

CHUNK_META = 1
CHUNK_DATA = 2
CHUNK_FINAL = 3

_HEADER = struct.Struct(">4sBBHIIII16s8s")
HEADER_LEN = _HEADER.size  # 48
LEN_PREFIX = struct.Struct(">I")
LEN_PREFIX_SIZE = LEN_PREFIX.size


@dataclass(frozen=True)
class Header:
    version: int
    kdf: KdfParams
    chunk_size: int
    salt: bytes
    nonce_prefix: bytes
    raw: bytes  # exact bytes as stored; used as AAD


def pack_header(kdf: KdfParams, chunk_size: int, salt: bytes, nonce_prefix: bytes) -> bytes:
    if len(salt) != SALT_LEN or len(nonce_prefix) != NONCE_PREFIX_LEN:
        raise ValueError("Bad salt or nonce prefix length")
    if not MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError("Chunk size out of range")
    kdf.validate()
    return _HEADER.pack(
        MAGIC, FORMAT_VERSION, kdf.kdf_id, 0, kdf.p1, kdf.p2, kdf.p3, chunk_size, salt, nonce_prefix
    )


def parse_header(raw: bytes) -> Header:
    """Parse and structurally validate a header; raises :class:`InvalidFormatError`."""
    if len(raw) != HEADER_LEN:
        raise InvalidFormatError("The file is too short to be a CipherPixel file.")
    magic, version, kdf_id, flags, p1, p2, p3, chunk_size, salt, prefix = _HEADER.unpack(raw)
    if magic != MAGIC:
        raise InvalidFormatError("This file is not a CipherPixel (.cpx) file.")
    if version != FORMAT_VERSION:
        raise InvalidFormatError(
            "This file uses an unsupported format version. Update CipherPixel and try again."
            if version > FORMAT_VERSION
            else "This file uses an obsolete, unsupported format version."
        )
    if flags != 0:
        raise InvalidFormatError("This file uses unsupported features.")
    kdf = KdfParams(kdf_id, p1, p2, p3)
    try:
        kdf.validate()
    except ValueError as exc:
        raise InvalidFormatError("The file header contains invalid key-derivation settings.") from exc
    if not MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE:
        raise InvalidFormatError("The file header contains an invalid chunk size.")
    return Header(version, kdf, chunk_size, bytes(salt), bytes(prefix), bytes(raw))


# --------------------------------------------------------------------------- #
# Chunk sealing / opening
# --------------------------------------------------------------------------- #
def chunk_nonce(prefix: bytes, counter: int) -> bytes:
    """96-bit nonce: 64-bit per-file random prefix || 32-bit counter."""
    if not 0 <= counter <= MAX_COUNTER:
        raise ValueError("Chunk counter exhausted; file too large for this chunk size")
    return prefix + counter.to_bytes(4, "big")


def chunk_aad(header_raw: bytes, chunk_type: int, counter: int) -> bytes:
    return header_raw + bytes((chunk_type,)) + counter.to_bytes(4, "big")


def seal_chunk(aead: AESGCM, header: Header, chunk_type: int, counter: int, plaintext: bytes) -> bytes:
    """Encrypt one chunk; returns ``ciphertext || tag``."""
    return aead.encrypt(
        chunk_nonce(header.nonce_prefix, counter),
        plaintext,
        chunk_aad(header.raw, chunk_type, counter),
    )


def open_chunk(aead: AESGCM, header: Header, chunk_type: int, counter: int, sealed: bytes) -> bytes:
    """Authenticate and decrypt one chunk; raises ``cryptography.exceptions.InvalidTag``."""
    return aead.decrypt(
        chunk_nonce(header.nonce_prefix, counter),
        sealed,
        chunk_aad(header.raw, chunk_type, counter),
    )
