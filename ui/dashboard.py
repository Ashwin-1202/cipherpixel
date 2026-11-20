"""Overview dashboard."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QAbstractItemView

from .base_page import BasePage
from .components.basics import Badge, Card, EmptyState, ReflowGrid, SectionHeader, StatCard, button, label
from .context import AppContext
from core.security_utils import human_size


class DashboardPage(BasePage):
    key = "overview"
    title = "Overview"
    crumbs = ["Overview"]

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.body.addWidget(self._build_hero())

        self.grid = ReflowGrid([(1000, 4), (560, 2), (0, 1)], 16)
        self.s_enc = StatCard("fa5s.lock", "Total Images Encrypted", "0", "SUCCESSFUL OPERATIONS", "primary")
        self.s_dec = StatCard("fa5s.lock-open", "Total Images Decrypted", "0", "SUCCESSFUL OPERATIONS", "secondary")
        self.s_proc = StatCard("fa5s.layer-group", "Files Processed", "0", "ALL TIME", "success")
        self.s_algo = StatCard("fa5s.shield-alt", "Encryption Algorithm", "AES-256-GCM", "AUTHENTICATED ENCRYPTION", "warning")
        self.s_algo.value.setStyleSheet("font-size: 19px;")
        for c in (self.s_enc, self.s_dec, self.s_proc, self.s_algo):
            self.grid.add(c)
        self.body.addWidget(self.grid)

        self.body.addWidget(self._build_activity())
        self.body.addStretch(1)
        ctx.bus.history_changed.connect(self.refresh)
        self.refresh()

    def _build_hero(self) -> QFrame:
        hero = QFrame()
        hero.setObjectName("Hero")
        lay = QHBoxLayout(hero)
        lay.setContentsMargins(36, 32, 36, 32)
        text = QVBoxLayout()
        text.setSpacing(10)
        eyebrow = label("WELCOME TO CIPHERPIXEL", "caption")
        eyebrow.setObjectName("HeroEyebrow")
        title = QLabel("Your Images. Your Privacy. Your Control.")
        title.setObjectName("HeroTitle")
        title.setWordWrap(True)
        sub = QLabel("Military-grade AES-256-GCM encryption with password-derived keys. Everything runs "
                     "locally – your images and passwords never leave this computer.")
        sub.setObjectName("HeroText")
        sub.setWordWrap(True)
        text.addWidget(eyebrow)
        text.addWidget(title)
        text.addWidget(sub)
        text.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.enc_btn = button("Encrypt New Image", "primary", "fa5s.lock", size="lg")
        self.dec_btn = button("Decrypt Existing Image", "secondary", "fa5s.lock-open", size="lg")
        self.enc_btn.clicked.connect(lambda: self.ctx.navigate("encrypt"))
        self.dec_btn.clicked.connect(lambda: self.ctx.navigate("decrypt"))
        row.addWidget(self.enc_btn)
        row.addWidget(self.dec_btn)
        row.addStretch(1)
        text.addLayout(row)
        lay.addLayout(text, 1)
        orb = QFrame()
        orb.setObjectName("HeroOrb")
        orb.setFixedSize(140, 140)
        ol = QVBoxLayout(orb)
        ol.setContentsMargins(0, 0, 0, 0)
        glyph = QLabel()
        glyph.setAlignment(Qt.AlignCenter)
        from .icons import bind_icon

        bind_icon(glyph, "fa5s.shield-alt", "primary", size=56)
        ol.addWidget(glyph)
        lay.addWidget(orb, 0, Qt.AlignVCenter)
        self._orb = orb
        return hero

    def _build_activity(self) -> Card:
        card = Card(padding=22, spacing=12)
        head = SectionHeader("Recent Activity", "Your latest encryption and decryption operations")
        self.all_btn = button("View all", "ghost", "fa5s.angle-right")
        self.all_btn.clicked.connect(lambda: self.ctx.navigate("history"))
        head.right.addWidget(self.all_btn)
        card.body.addWidget(head)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["FILE", "OPERATION", "WHEN", "STATUS"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().setDefaultSectionSize(46)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 118)
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        card.body.addWidget(self.table)

        self.empty = EmptyState("fa5s.history", "No activity yet",
                                "Encrypt or decrypt an image and it will appear here.", "Encrypt your first image")
        self.empty.actionClicked.connect(lambda: self.ctx.navigate("encrypt"))
        card.body.addWidget(self.empty)
        return card

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        counts = self.ctx.history.counts()
        self.s_enc.set_value(f"{counts['encrypted']:,}")
        self.s_dec.set_value(f"{counts['decrypted']:,}")
        self.s_proc.set_value(f"{counts['processed']:,}")

        entries = self.ctx.history.list(limit=6)
        self.table.setVisible(bool(entries))
        self.empty.setVisible(not entries)
        self.table.setRowCount(len(entries))
        self.table.setFixedHeight(46 * len(entries) + self.table.horizontalHeader().height() + 4 if entries else 0)
        for row, e in enumerate(entries):
            name = QTableWidgetItem(e.file_name)
            name.setToolTip(e.file_name)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem("Encrypt" if e.operation == "encrypt" else "Decrypt"))
            self.table.setItem(row, 2, QTableWidgetItem(e.local_time.strftime("%b %d, %Y  %H:%M")))
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(8, 0, 8, 0)
            hl.addWidget(Badge("Success" if e.status == "success" else "Failed",
                               "success" if e.status == "success" else "error"), 0, Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setCellWidget(row, 3, holder)
