"""Exception hierarchy for CipherPixel.

Every error that can reach the user derives from :class:`CipherPixelError` and
carries a ``user_message`` that is safe to display: it never contains key
material, passwords, or low-level cryptographic details.
"""

from __future__ import annotations


class CipherPixelError(Exception):
    """Base class for all expected, user-presentable errors."""

    default_message = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.user_message = message or self.default_message
        #: Technical detail for the (sanitised) log file only; never shown in the UI.
        self.detail = detail
        super().__init__(self.user_message)


class FileAccessError(CipherPixelError):
    default_message = "The file could not be read or written. Check that it exists and that you have permission."


class InsufficientStorageError(CipherPixelError):
    default_message = "There is not enough free disk space to complete this operation."


class EmptyFileError(CipherPixelError):
    default_message = "The selected file is empty."


class UnsupportedImageError(CipherPixelError):
    default_message = "Unsupported or invalid image. Supported formats: PNG, JPG, JPEG, BMP and TIFF."


class InvalidFormatError(CipherPixelError):
    default_message = "This is not a valid CipherPixel (.cpx) file, or it was created by an unsupported version."


class AuthenticationError(CipherPixelError):
    """Raised when the key check fails: wrong password *or* a modified header."""

    default_message = "Decryption failed. The password is incorrect, or the file has been modified."


class IntegrityError(CipherPixelError):
    """Raised when authenticated data fails verification after the password was accepted."""

    default_message = "Integrity check failed. The file is corrupted, truncated, or has been tampered with."


class WeakPasswordError(CipherPixelError):
    default_message = "The password does not meet the minimum requirements."


class OperationCancelled(CipherPixelError):
    default_message = "The operation was cancelled."
