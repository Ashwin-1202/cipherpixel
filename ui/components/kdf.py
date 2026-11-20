"""Key-derivation selector (algorithm + security level) used on the Encrypt and Settings pages."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QWidget

from core.key_manager import KdfParams, available_kdfs, get_preset

from .basics import label

KDF_LABELS = {"argon2id": "Argon2id (memory-hard)", "pbkdf2": "PBKDF2-HMAC-SHA256"}
LEVEL_LABELS = {"balanced": "Balanced (recommended)", "strong": "Strong", "paranoid": "Maximum"}
LEVEL_HINTS = {
    "balanced": "Fast on any modern PC while resisting offline password guessing.",
    "strong": "Noticeably slower to unlock, much costlier for an attacker to brute-force.",
    "paranoid": "Needs ~0.5 GB RAM with Argon2id. Best for high-value images and strong hardware.",
}


class KdfSelector(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        self.kdf_combo = QComboBox()
        for name in available_kdfs():
            self.kdf_combo.addItem(KDF_LABELS[name], name)
        self.level_combo = QComboBox()
        for name, text in LEVEL_LABELS.items():
            self.level_combo.addItem(text, name)
        self.summary = label("", "mono", wrap=True)
        self.hint = label("", "muted", wrap=True)

        grid.addWidget(label("Key derivation", "muted"), 0, 0)
        grid.addWidget(self.kdf_combo, 0, 1)
        grid.addWidget(label("Security level", "muted"), 1, 0)
        grid.addWidget(self.level_combo, 1, 1)
        grid.addWidget(self.summary, 2, 0, 1, 2)
        grid.addWidget(self.hint, 3, 0, 1, 2)
        self.kdf_combo.setToolTip("Argon2id is memory-hard and recommended. PBKDF2 is a widely supported fallback.")
        self.level_combo.setToolTip("Higher levels make password guessing slower for attackers (and slightly slower for you).")

        self.kdf_combo.currentIndexChanged.connect(self._on_change)
        self.level_combo.currentIndexChanged.connect(self._on_change)
        self._on_change()

    def kdf_name(self) -> str:
        return self.kdf_combo.currentData()

    def level(self) -> str:
        return self.level_combo.currentData()

    def params(self) -> KdfParams:
        return get_preset(self.kdf_name(), self.level())

    def set_values(self, kdf: str, level: str) -> None:
        for combo, value in ((self.kdf_combo, kdf), (self.level_combo, level)):
            idx = combo.findData(value)
            if idx >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)
        self._update_text()

    def _update_text(self) -> None:
        self.summary.setText(self.params().describe())
        self.hint.setText(LEVEL_HINTS[self.level()])

    def _on_change(self) -> None:
        self._update_text()
        self.changed.emit()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
