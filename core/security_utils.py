"""Security helpers: password strength, password generation, filename safety, hashing."""

from __future__ import annotations

import hashlib
import math
import re
import secrets
import string
from dataclasses import dataclass
from typing import Callable

_COMMON = {
    "password", "passw0rd", "p@ssw0rd", "123456", "12345678", "123456789", "qwerty", "qwertyuiop",
    "abc123", "letmein", "welcome", "admin", "iloveyou", "monkey", "dragon", "football", "baseball",
    "111111", "000000", "123123", "login", "master", "hello", "freedom", "whatever", "trustno1",
    "cipherpixel", "changeme", "secret", "princess", "sunshine", "shadow", "superman", "batman",
}
_SEQUENCES = ("abcdefghijklmnopqrstuvwxyz", "qwertyuiopasdfghjklzxcvbnm", "0123456789")

SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?"
MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class PasswordStrength:
    score: int  # 0 (very weak) .. 4 (excellent)
    label: str
    entropy_bits: float
    feedback: str


def _pool_size(pw: str) -> int:
    pool = 0
    if re.search(r"[a-z]", pw):
        pool += 26
    if re.search(r"[A-Z]", pw):
        pool += 26
    if re.search(r"\d", pw):
        pool += 10
    if re.search(r"[^\w\s]|_", pw):
        pool += 32
    if re.search(r"\s", pw):
        pool += 1
    if re.search(r"[^\x00-\x7f]", pw):
        pool += 64
    return max(pool, 1)


def _has_sequence(pw: str, run: int = 4) -> bool:
    low = pw.lower()
    for seq in _SEQUENCES:
        for i in range(len(seq) - run + 1):
            chunk = seq[i : i + run]
            if chunk in low or chunk[::-1] in low:
                return True
    return False


def estimate_strength(password: str) -> PasswordStrength:
    """Heuristic strength estimate (a rough guide, not a guarantee)."""
    if not password:
        return PasswordStrength(0, "Enter a password", 0.0, "Use at least 12 characters with mixed types.")

    low = password.lower()
    unique = len(set(password))
    # Effective length discounts repeated characters.
    effective_len = min(len(password), unique * 1.6)
    entropy = effective_len * math.log2(_pool_size(password))

    notes: list[str] = []
    if low in _COMMON or any(low.startswith(c) and len(low) <= len(c) + 3 for c in _COMMON if len(c) >= 6):
        entropy = min(entropy, 14.0)
        notes.append("This is a very common password.")
    if _has_sequence(password):
        entropy *= 0.75
        notes.append("Avoid keyboard or alphabet sequences.")
    if re.search(r"(.)\1{2,}", password):
        entropy *= 0.85
        notes.append("Avoid repeated characters.")
    if len(password) < 12:
        notes.append("Use at least 12 characters.")

    if entropy < 28:
        score, label = 0, "Very weak"
    elif entropy < 40:
        score, label = 1, "Weak"
    elif entropy < 60:
        score, label = 2, "Fair"
    elif entropy < 80:
        score, label = 3, "Strong"
    else:
        score, label = 4, "Excellent"
    if len(password) < MIN_PASSWORD_LENGTH:
        score = min(score, 0)
        label = "Too short"

    feedback = " ".join(notes) if notes else ("Great – this password resists guessing well." if score >= 3 else "Add length and variety.")
    return PasswordStrength(score, label, round(entropy, 1), feedback)


def generate_password(length: int = 20) -> str:
    """Generate a random password with the OS CSPRNG, guaranteed to include all classes."""
    if length < 12:
        raise ValueError("Generated passwords must be at least 12 characters")
    classes = [string.ascii_lowercase, string.ascii_uppercase, string.digits, SYMBOLS]
    chars = [secrets.choice(c) for c in classes]
    alphabet = "".join(classes)
    chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


# --------------------------------------------------------------------------- #
# Filenames & hashing
# --------------------------------------------------------------------------- #
_RESERVED_WIN = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, fallback: str = "recovered_image") -> str:
    """Make an untrusted (decrypted) filename safe to use on Windows/macOS/Linux.

    Strips any path components (defends against ``../`` tricks inside metadata),
    replaces illegal characters, avoids reserved Windows device names, and limits length.
    """
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    name = _BAD_CHARS.sub("_", name).strip(" .")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    if not stem:
        stem = fallback
    if stem.upper() in _RESERVED_WIN:
        stem = f"_{stem}"
    stem = stem[:120]
    ext = ext[:10]
    return f"{stem}.{ext}" if ext else stem


def sha256_file(path: str, *, chunk: int = 1 << 20, check: Callable[[], None] | None = None) -> str:
    """Hex SHA-256 of a file; ``check`` (if given) is called per block for cancellation."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
            if check:
                check()
    return h.hexdigest()


def human_size(num: float) -> str:
    """Format a byte count, e.g. ``1.5 MB``."""
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0 or unit == "TB":
            return f"{int(num)} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"  # pragma: no cover
