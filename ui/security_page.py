"""Security Center: live engine status, self-test, and educational content."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.selftest import SelfTestResult

from .base_page import BasePage
from .components.basics import Badge, Card, IconBadge, KeyValueRow, ReflowGrid, ResponsiveRow, SectionHeader, button, hline, label
from .context import AppContext

LESSONS: list[tuple[str, str, str, str]] = [
    ("fa5s.microchip", "primary", "How AES-256-GCM works",
     "AES is a block cipher that scrambles data with a 256-bit key – a search space of 2²⁵⁶ possibilities. "
     "GCM mode turns it into a stream cipher and, in the same pass, computes an authentication tag. That is "
     "'authenticated encryption': the data is both hidden and tamper-evident. CipherPixel encrypts your image "
     "in 1 MiB chunks, each with its own tag, so even very large images are processed safely."),
    ("fa5s.key", "secondary", "Why password-based key derivation is necessary",
     "A password is not a key: it is short, guessable and not 256 bits long. A key-derivation function (KDF) "
     "stretches your password into a uniformly random 256-bit key – deliberately slowly. Argon2id also needs "
     "lots of memory, which makes large-scale GPU guessing very expensive. A strong, unique password still "
     "matters: the KDF slows attackers down, it can't rescue 'password123'."),
    ("fa5s.certificate", "success", "What authentication tags do",
     "Each chunk carries a 128-bit tag computed over the ciphertext and over associated data (the file header, "
     "chunk position and 'last chunk' flag). If a single bit is changed, a chunk is reordered, removed or "
     "appended, the tag no longer matches and decryption stops – CipherPixel never hands you modified data. "
     "Verification uses the cryptography library's constant-time comparison."),
    ("fa5s.random", "warning", "Why salts and nonces are important",
     "The salt is 128 random bits mixed into the KDF so that the same password produces a different key for "
     "every file, defeating precomputed (rainbow-table) attacks. The nonce is a value that must never repeat "
     "under one key; AES-GCM breaks catastrophically if it does. Each chunk uses a random 64-bit per-file "
     "prefix plus a 32-bit counter, and the key itself is unique per file, so a (key, nonce) pair never repeats."),
]


class SecurityPage(BasePage):
    key = "security"
    title = "Security Center"
    crumbs = ["Security Center"]

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.body.addWidget(label(
            "Everything CipherPixel does to protect your images – verified live on this machine. No keys or "
            "passwords are ever displayed.", "muted", wrap=True))

        row = ResponsiveRow(980, 22)
        row.add(self._build_config(), 1)
        row.add(self._build_selftest(), 1)
        self.body.addWidget(row)

        self.body.addWidget(SectionHeader("How it works", "The cryptography behind CipherPixel, in plain language"))
        grid = ReflowGrid([(900, 2), (0, 1)], 16)
        for icon, accent, title, text in LESSONS:
            card = Card(padding=22, spacing=10)
            top = QHBoxLayout()
            top.setSpacing(12)
            top.addWidget(IconBadge(icon, accent))
            top.addWidget(label(title, "h3", wrap=True), 1)
            card.body.addLayout(top)
            card.body.addWidget(label(text, "muted", wrap=True))
            grid.add(card)
        self.body.addWidget(grid)
        self.body.addStretch(1)

        ctx.bus.selftest_done.connect(self.show_results)
        ctx.bus.settings_changed.connect(lambda _k: self._refresh_config())
        if ctx.selftest_results is not None:
            self.show_results(ctx.selftest_results)
        self._refresh_config()

    def _build_config(self) -> Card:
        card = Card()
        card.body.addWidget(SectionHeader("Active protection", "Current cryptographic configuration"))
        self.rows = {
            "algo": KeyValueRow("Encryption algorithm", "AES-256-GCM"),
            "kdf": KeyValueRow("Key derivation"),
            "key": KeyValueRow("Key size", "256 bits"),
            "auth": KeyValueRow("Authentication", "128-bit GCM tag per chunk"),
            "method": KeyValueRow("Methodology", "Chunked streaming AEAD (1 MiB)"),
            "salt": KeyValueRow("Random salt", "128-bit, OS CSPRNG, per file"),
            "nonce": KeyValueRow("Nonce", "96-bit: random prefix + counter"),
            "integrity": KeyValueRow("Integrity verification", "Per-chunk tags + SHA-256 of image"),
            "binding": KeyValueRow("Header binding", "Header authenticated as AAD"),
        }
        for r in self.rows.values():
            card.body.addWidget(r)
            card.body.addWidget(hline())
        return card

    def _refresh_config(self) -> None:
        self.rows["kdf"].set_value(self.ctx.settings.kdf_params().describe())

    def _build_selftest(self) -> Card:
        card = Card()
        head = SectionHeader("Live engine verification", "Runs the real encryption code on a generated test image")
        self.run_btn = button("Run self-test", "secondary", "fa5s.vial")
        self.run_btn.clicked.connect(self._run)
        head.right.addWidget(self.run_btn)
        card.body.addWidget(head)
        self.summary = Badge("Not run yet", "neutral")
        card.body.addWidget(self.summary)
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(6)
        card.body.addLayout(self.list_layout)
        card.body.addStretch(1)
        return card

    def _run(self) -> None:
        self.run_btn.setEnabled(False)
        self.run_btn.setText("Running…")
        self.summary.setText("Running…")
        self.summary.set_kind("info")
        self.ctx.run_selftest()

    def show_results(self, results: list[SelfTestResult]) -> None:
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run self-test")
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        passed = sum(r.passed for r in results)
        ok = passed == len(results) and bool(results)
        self.summary.setText(f"All {len(results)} checks passed" if ok else f"{len(results) - passed} of {len(results)} checks FAILED")
        self.summary.set_kind("success" if ok else "error")
        for r in results:
            line = QWidget()
            hl = QHBoxLayout(line)
            hl.setContentsMargins(0, 3, 0, 3)
            hl.setSpacing(10)
            badge = Badge("PASS" if r.passed else "FAIL", "success" if r.passed else "error")
            badge.setFixedWidth(52)
            hl.addWidget(badge)
            hl.addWidget(label(r.name), 1)
            if r.detail:
                hl.addWidget(label(r.detail, "muted"))
            self.list_layout.addWidget(line)
