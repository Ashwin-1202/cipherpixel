"""Password-based key derivation.

Supported KDFs
--------------
* **Argon2id** (default) – memory-hard, recommended by OWASP for password hashing.
* **PBKDF2-HMAC-SHA256** – ubiquitous fallback for environments without Argon2.

Both derive a 256-bit key from the user's password and a random 128-bit salt.
KDF parameters are stored (authenticated) in the file header so decryption always
uses exactly the parameters used at encryption time.  Bounds are enforced when a
header is parsed so a malicious file cannot request absurd amounts of memory/CPU.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .errors import CipherPixelError

try:  # Argon2 is optional at import time so the app degrades gracefully.
    from argon2.low_level import Type as _Argon2Type
    from argon2.low_level import hash_secret_raw as _argon2_raw

    ARGON2_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when argon2-cffi is missing
    ARGON2_AVAILABLE = False

KEY_LEN = 32  # 256-bit AES key

KDF_ARGON2ID = 1
KDF_PBKDF2 = 2

# --- Accepted parameter bounds (enforced on encrypt *and* when parsing headers) ---
ARGON2_MIN_TIME, ARGON2_MAX_TIME = 1, 32
ARGON2_MIN_MEM_KIB, ARGON2_MAX_MEM_KIB = 8 * 1024, 1024 * 1024  # 8 MiB .. 1 GiB
ARGON2_MIN_PAR, ARGON2_MAX_PAR = 1, 16
PBKDF2_MIN_ITER, PBKDF2_MAX_ITER = 100_000, 20_000_000

LEVELS = ("balanced", "strong", "paranoid")
KDF_NAMES = ("argon2id", "pbkdf2")


@dataclass(frozen=True)
class KdfParams:
    """KDF identifier plus three numeric parameters (meaning depends on the KDF).

    Argon2id: ``p1`` = time cost, ``p2`` = memory in KiB, ``p3`` = parallelism.
    PBKDF2:   ``p1`` = iteration count (``p2``/``p3`` unused, zero).
    """

    kdf_id: int
    p1: int
    p2: int = 0
    p3: int = 0

    # ---- constructors -------------------------------------------------------
    @classmethod
    def argon2id(cls, time_cost: int = 3, memory_kib: int = 64 * 1024, parallelism: int = 4) -> "KdfParams":
        return cls(KDF_ARGON2ID, time_cost, memory_kib, parallelism)

    @classmethod
    def pbkdf2(cls, iterations: int = 600_000) -> "KdfParams":
        return cls(KDF_PBKDF2, iterations, 0, 0)

    # ---- presentation -------------------------------------------------------
    @property
    def name(self) -> str:
        return {KDF_ARGON2ID: "Argon2id", KDF_PBKDF2: "PBKDF2-HMAC-SHA256"}.get(self.kdf_id, "Unknown")

    def describe(self) -> str:
        if self.kdf_id == KDF_ARGON2ID:
            return f"Argon2id · {self.p2 // 1024} MiB memory · {self.p1} passes · {self.p3} lanes"
        if self.kdf_id == KDF_PBKDF2:
            return f"PBKDF2-HMAC-SHA256 · {self.p1:,} iterations"
        return "Unknown KDF"

    # ---- validation ---------------------------------------------------------
    def validate(self) -> None:
        """Raise ``ValueError`` if parameters are outside the accepted range."""
        if self.kdf_id == KDF_ARGON2ID:
            if not ARGON2_MIN_TIME <= self.p1 <= ARGON2_MAX_TIME:
                raise ValueError("Argon2 time cost out of range")
            if not ARGON2_MIN_MEM_KIB <= self.p2 <= ARGON2_MAX_MEM_KIB:
                raise ValueError("Argon2 memory cost out of range")
            if not ARGON2_MIN_PAR <= self.p3 <= ARGON2_MAX_PAR:
                raise ValueError("Argon2 parallelism out of range")
        elif self.kdf_id == KDF_PBKDF2:
            if not PBKDF2_MIN_ITER <= self.p1 <= PBKDF2_MAX_ITER:
                raise ValueError("PBKDF2 iteration count out of range")
            if self.p2 != 0 or self.p3 != 0:
                raise ValueError("Unused PBKDF2 parameters must be zero")
        else:
            raise ValueError("Unknown KDF identifier")


# Presets shown in the UI.  "Balanced" is a safe default for desktop hardware.
_PRESETS: dict[str, dict[str, KdfParams]] = {
    "argon2id": {
        "balanced": KdfParams.argon2id(3, 64 * 1024, 4),
        "strong": KdfParams.argon2id(4, 256 * 1024, 4),
        "paranoid": KdfParams.argon2id(5, 512 * 1024, 4),
    },
    "pbkdf2": {
        "balanced": KdfParams.pbkdf2(600_000),
        "strong": KdfParams.pbkdf2(1_200_000),
        "paranoid": KdfParams.pbkdf2(3_000_000),
    },
}


def get_preset(kdf: str = "argon2id", level: str = "balanced") -> KdfParams:
    """Return the preset for ``kdf`` ("argon2id" | "pbkdf2") at ``level``."""
    kdf, level = kdf.lower(), level.lower()
    if kdf == "argon2id" and not ARGON2_AVAILABLE:
        kdf = "pbkdf2"
    try:
        return _PRESETS[kdf][level]
    except KeyError as exc:
        raise ValueError(f"Unknown KDF preset: {kdf}/{level}") from exc


def default_kdf() -> KdfParams:
    return get_preset("argon2id" if ARGON2_AVAILABLE else "pbkdf2", "balanced")


def available_kdfs() -> list[str]:
    return ["argon2id", "pbkdf2"] if ARGON2_AVAILABLE else ["pbkdf2"]


# --------------------------------------------------------------------------- #
# Key derivation
# --------------------------------------------------------------------------- #
def normalize_password(password: str) -> bytes:
    """NFKC-normalise then UTF-8 encode.

    Normalisation makes the same visible password derive the same key regardless of
    which Unicode composition the keyboard/OS produced (e.g. ``é`` as one code
    point vs. ``e`` + combining accent).
    """
    if not isinstance(password, str) or password == "":
        raise ValueError("Password must be a non-empty string")
    return unicodedata.normalize("NFKC", password).encode("utf-8")


def derive_key(password: str, salt: bytes, params: KdfParams) -> bytes:
    """Derive a 256-bit key.  CPU/memory heavy by design – call from a worker thread."""
    params.validate()
    if len(salt) < 16:
        raise ValueError("Salt must be at least 128 bits")
    secret = normalize_password(password)

    if params.kdf_id == KDF_ARGON2ID:
        if not ARGON2_AVAILABLE:
            raise CipherPixelError(
                "This file uses Argon2id, but the 'argon2-cffi' package is not installed.",
                detail="argon2-cffi import failed",
            )
        return _argon2_raw(
            secret=secret,
            salt=salt,
            time_cost=params.p1,
            memory_cost=params.p2,
            parallelism=params.p3,
            hash_len=KEY_LEN,
            type=_Argon2Type.ID,
        )

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=KEY_LEN, salt=salt, iterations=params.p1)
    return kdf.derive(secret)
