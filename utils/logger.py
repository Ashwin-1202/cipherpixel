"""Privacy-preserving logging.

Policy: logs may contain operation names, byte counts, durations and exception *class
names*.  They must never contain passwords, keys, image bytes, or full file paths.
A filter additionally redacts anything that looks like a filesystem path as a safety net.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from .paths import data_dir

_PATHLIKE = re.compile(r"([A-Za-z]:\\[^\s'\"]+|/(?:[\w.\- ]+/)+[\w.\- ]+)")


class _RedactPaths(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _PATHLIKE.sub("<path>", str(record.getMessage()))
        record.args = ()
        return True


def get_logger(name: str = "cipherpixel") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        log_dir = data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            log_dir / "cipherpixel.log", maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(_RedactPaths())
    logger.addHandler(handler)
    return logger
