"""Input validation shared by the UI and the tests."""

from __future__ import annotations

import os

from core.errors import WeakPasswordError
from core.file_handler import SUPPORTED_EXTENSIONS
from core.security_utils import MIN_PASSWORD_LENGTH, estimate_strength


def is_supported_image_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS


def is_cpx_path(path: str) -> bool:
    return path.lower().endswith(".cpx")


def validate_new_password(password: str, confirm: str) -> None:
    """Raise :class:`WeakPasswordError` with a user-friendly message if unacceptable."""
    if not password:
        raise WeakPasswordError("Enter a password.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if password != confirm:
        raise WeakPasswordError("The passwords do not match.")
    if estimate_strength(password).score == 0:
        raise WeakPasswordError("This password is too easy to guess. Add length and variety.")


def password_ready(password: str, confirm: str) -> bool:
    try:
        validate_new_password(password, confirm)
        return True
    except WeakPasswordError:
        return False
