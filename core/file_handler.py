"""File-system helpers: image validation, atomic writes, free-space checks, temp storage."""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from typing import Callable, Iterator

from PIL import Image, UnidentifiedImageError

from .errors import (
    CipherPixelError,
    EmptyFileError,
    FileAccessError,
    InsufficientStorageError,
    OperationCancelled,
    UnsupportedImageError,
)

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
SUPPORTED_FORMATS = {"PNG", "JPEG", "BMP", "TIFF"}  # Pillow's content-based format names
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
CPX_FILTER = "CipherPixel encrypted files (*.cpx)"

_FREE_SPACE_MARGIN = 1 * 1024 * 1024


@dataclass(frozen=True)
class ImageInfo:
    path: str
    name: str
    size: int
    format: str  # PNG | JPEG | BMP | TIFF
    width: int
    height: int
    mode: str


def translate_oserror(exc: OSError) -> CipherPixelError:
    """Map low-level OS errors to user-presentable errors (details only in ``detail``)."""
    if exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) == 112:
        return InsufficientStorageError(detail=repr(exc))
    return FileAccessError(detail=f"{type(exc).__name__}: errno={exc.errno}")


def inspect_image(path: str) -> ImageInfo:
    """Validate that ``path`` is a real, non-empty, supported image and return its facts.

    Validation is content-based (Pillow sniffs the bytes), not just extension-based, so
    a renamed text file is rejected.  Only the header is parsed; pixels are never decoded,
    so very large images are handled without large memory use.
    """
    try:
        if not os.path.isfile(path):
            raise FileAccessError("The selected file does not exist or is not a regular file.")
        size = os.path.getsize(path)
    except OSError as exc:
        raise translate_oserror(exc) from exc

    if size == 0:
        raise EmptyFileError()
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedImageError()

    previous = Image.MAX_IMAGE_PIXELS
    try:
        # We only read the header here; lifting the decompression-bomb limit is safe
        # because no pixel data is decoded.
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(path) as img:
            fmt = (img.format or "").upper()
            width, height = img.size
            mode = img.mode
    except (UnidentifiedImageError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise UnsupportedImageError(detail=type(exc).__name__) from exc
    except OSError as exc:
        # Pillow raises OSError for truncated/invalid image headers as well as I/O errors.
        raise UnsupportedImageError(detail=type(exc).__name__) from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous

    if fmt not in SUPPORTED_FORMATS:
        raise UnsupportedImageError()
    return ImageInfo(path, os.path.basename(path), size, fmt, width, height, mode)


def same_file(a: str, b: str) -> bool:
    try:
        return os.path.exists(b) and os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)


def ensure_free_space(directory: str, needed: int) -> None:
    try:
        free = shutil.disk_usage(directory or ".").free
    except OSError:
        return  # cannot determine; real write errors are still handled
    if free < needed + _FREE_SPACE_MARGIN:
        raise InsufficientStorageError(
            f"Not enough free disk space: about {needed / (1024 * 1024):.1f} MB required, "
            f"{free / (1024 * 1024):.1f} MB available."
        )


@contextlib.contextmanager
def atomic_write(dst: str) -> Iterator:
    """Write to a temporary file beside ``dst`` and atomically move it into place on success.

    On *any* failure (including cancellation or an authentication error part-way
    through decryption) the partial file is removed, and ``dst`` is left untouched.
    """
    directory = os.path.dirname(os.path.abspath(dst))
    success = False
    tmp = None
    try:
        if not os.path.isdir(directory):
            raise FileAccessError("The destination folder does not exist.")
        fd, tmp = tempfile.mkstemp(prefix=".cipherpixel-", suffix=".part", dir=directory)
        with os.fdopen(fd, "wb") as fh:
            yield fh
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dst)
        success = True
    except OSError as exc:
        raise translate_oserror(exc) from exc
    finally:
        if not success and tmp:
            with contextlib.suppress(OSError):
                os.remove(tmp)


def export_copy(
    src: str,
    dst: str,
    *,
    progress: Callable[[str, float], None] | None = None,
    cancel: threading.Event | None = None,
) -> str:
    """Copy ``src`` to ``dst`` atomically (used for 'Save'/'Export' buttons)."""
    if same_file(src, dst):
        raise FileAccessError("The source and destination are the same file.")
    try:
        total = os.path.getsize(src)
        ensure_free_space(os.path.dirname(os.path.abspath(dst)), total)
        done = 0
        with open(src, "rb") as fin, atomic_write(dst) as fout:
            while True:
                if cancel is not None and cancel.is_set():
                    raise OperationCancelled()
                block = fin.read(4 * 1024 * 1024)
                if not block:
                    break
                fout.write(block)
                done += len(block)
                if progress and total:
                    progress("saving", done / total)
    except OSError as exc:
        raise translate_oserror(exc) from exc
    if progress:
        progress("saving", 1.0)
    return dst


class SessionTempDir:
    """A private (0700 on POSIX) scratch directory for the current app session.

    Holds encrypted output awaiting 'Save' and decrypted images awaiting 'Export'.
    Cleared whenever a new file is loaded and removed on exit.

    Note: deleting a file does not guarantee the bytes are unrecoverable from the
    storage device (SSD wear-levelling, journaling, snapshots).  Full-disk encryption
    is the right defence against forensic recovery of temporary plaintext.
    """

    def __init__(self, prefix: str = "cipherpixel-") -> None:
        self.path = tempfile.mkdtemp(prefix=prefix)

    def new_path(self, suffix: str = "") -> str:
        fd, p = tempfile.mkstemp(dir=self.path, suffix=suffix)
        os.close(fd)
        return p

    def remove(self, path: str | None) -> None:
        if path and os.path.dirname(os.path.abspath(path)) == os.path.abspath(self.path):
            with contextlib.suppress(OSError):
                os.remove(path)

    def clear(self) -> None:
        for name in os.listdir(self.path):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(self.path, name))

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
