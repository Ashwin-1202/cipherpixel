"""About page."""

from __future__ import annotations

import platform

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from .base_page import BasePage
from .components.basics import Badge, Card, IconBadge, KeyValueRow, SectionHeader, hline, label
from .context import AppContext


class AboutPage(BasePage):
    key = "about"
    title = "About"
    crumbs = ["About"]

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx, max_width=900)
        from . import APP_VERSION

        card = Card(padding=28, spacing=14)
        head = QHBoxLayout()
        head.setSpacing(16)
        head.addWidget(IconBadge("fa5s.lock", "primary", size=64, icon_size=30))
        t = QVBoxLayout()
        t.setSpacing(2)
        t.addWidget(label("CipherPixel", "h1"))
        t.addWidget(label("Advanced Image Security System", "muted"))
        head.addLayout(t, 1)
        head.addWidget(Badge(f"v{APP_VERSION}", "info"), 0, Qt.AlignTop)
        card.body.addLayout(head)
        card.body.addWidget(hline())
        card.body.addWidget(label(
            "CipherPixel encrypts images with standard, peer-reviewed cryptography. It does not invent its own "
            "algorithms: AES-256-GCM (via the 'cryptography' library) provides authenticated encryption, and "
            "Argon2id or PBKDF2-HMAC-SHA256 derive the key from your password.", "muted", wrap=True))
        self.body.addWidget(card)

        card = Card()
        card.body.addWidget(SectionHeader("Cryptography"))
        for k, v in [("Cipher", "AES-256-GCM (authenticated)"), ("Key derivation", "Argon2id · PBKDF2-HMAC-SHA256"),
                     ("File format", "CipherPixel .cpx v1 – chunked, header-bound AEAD"),
                     ("Randomness", "Operating-system CSPRNG (secrets / os.urandom)")]:
            card.body.addWidget(KeyValueRow(k, v))
        self.body.addWidget(card)

        card = Card()
        card.body.addWidget(SectionHeader("Good to know"))
        for text in [
            "Passwords cannot be recovered. If you forget it, the image cannot be decrypted by anyone.",
            "Everything happens locally. Nothing is uploaded, and no network access is used.",
            "Encrypting does not delete your original image – remove it yourself once you've verified the .cpx file.",
            "Keep your OS and disk encryption (BitLocker / FileVault) enabled to protect temporary files.",
        ]:
            card.body.addWidget(label("•  " + text, "muted", wrap=True))
        card.body.addWidget(hline())
        card.body.addWidget(label(f"Python {platform.python_version()} · Qt for Python (PySide6)", "caption"))
        self.body.addWidget(card)
        self.body.addStretch(1)
