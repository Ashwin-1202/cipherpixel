"""File History page: search, filter, sort, delete, clear, export."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from core.history import DECRYPT, ENCRYPT, HistoryEntry
from core.security_utils import human_size

from . import dialogs
from .base_page import BasePage
from .components.basics import Badge, Card, EmptyState, button, label
from .context import AppContext
from .icons import bind_icon


class HistoryPage(BasePage):
    key = "history"
    title = "File History"
    crumbs = ["File History"]

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self._entries: list[HistoryEntry] = []
        self.body.addWidget(label(
            "Only metadata is kept here – file name, type, size, time and result. Passwords, keys and image "
            "contents are never stored.", "muted", wrap=True))

        card = Card(padding=20, spacing=14)
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by file name…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Filter the list by file name")
        from PySide6.QtGui import QAction

        s_act = QAction(self.search)
        bind_icon(s_act, "fa5s.search", "muted")
        self.search.addAction(s_act, QLineEdit.LeadingPosition)
        self.filter = QComboBox()
        self.filter.addItem("All operations", None)
        self.filter.addItem("Encryption only", ENCRYPT)
        self.filter.addItem("Decryption only", DECRYPT)
        self.sort = QComboBox()
        self.sort.addItem("Newest first", True)
        self.sort.addItem("Oldest first", False)
        self.export_btn = button("Export CSV", "secondary", "fa5s.file-export", tooltip="Export the visible rows to a CSV file")
        self.delete_btn = button("Delete selected", "secondary", "fa5s.trash-alt")
        self.clear_btn = button("Clear history", "danger", "fa5s.trash-alt")
        bar.addWidget(self.search, 1)
        bar.addWidget(self.filter)
        bar.addWidget(self.sort)
        bar.addWidget(self.export_btn)
        bar.addWidget(self.delete_btn)
        bar.addWidget(self.clear_btn)
        card.body.addLayout(bar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["FILE NAME", "TYPE", "OPERATION", "DATE & TIME", "SIZE", "STATUS"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setMinimumHeight(360)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 5):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 118)
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        card.body.addWidget(self.table)

        self.empty = EmptyState("fa5s.history", "No history yet",
                                "Operations you perform will be listed here.", "Encrypt an image")
        self.empty.actionClicked.connect(lambda: self.ctx.navigate("encrypt"))
        card.body.addWidget(self.empty)
        self.count_label = label("", "muted")
        card.body.addWidget(self.count_label)
        self.body.addWidget(card)
        self.body.addStretch(1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(180)
        self._debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _t: self._debounce.start())
        self.filter.currentIndexChanged.connect(self.refresh)
        self.sort.currentIndexChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.export_btn.clicked.connect(self._export)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.clear_btn.clicked.connect(self._clear)
        ctx.bus.history_changed.connect(self.refresh)
        self.refresh()

    def on_show(self) -> None:
        self.refresh()

    def _selected_ids(self) -> list[int]:
        rows = {i.row() for i in self.table.selectedItems()}
        return [self._entries[r].id for r in rows if r < len(self._entries)]

    def _update_buttons(self) -> None:
        has_rows = bool(self._entries)
        self.delete_btn.setEnabled(bool(self._selected_ids()))
        self.export_btn.setEnabled(has_rows)
        any_history = bool(self.ctx.history.list(limit=1))
        self.clear_btn.setEnabled(any_history)

    def refresh(self) -> None:
        self._entries = self.ctx.history.list(
            search=self.search.text(), operation=self.filter.currentData(), newest_first=bool(self.sort.currentData()))
        entries = self._entries
        total = len(self.ctx.history.list())
        filtering = bool(self.search.text().strip()) or self.filter.currentData() is not None
        self.table.setVisible(bool(entries))
        self.empty.setVisible(not entries)
        if not entries and total:
            self.empty.title.setText("No matching entries")
            self.empty.text.setText("Try a different search term or filter.")
            self.empty.button.hide() if hasattr(self.empty, "button") else None
        else:
            self.empty.title.setText("No history yet")
            self.empty.text.setText("Operations you perform will be listed here.")
            if hasattr(self.empty, "button"):
                self.empty.button.show()

        self.table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            cells = [e.file_name, e.file_type, "Encrypt" if e.operation == ENCRYPT else "Decrypt",
                     e.local_time.strftime("%b %d, %Y  %H:%M:%S"), human_size(e.file_size), None]
            for col, text in enumerate(cells):
                if text is None:
                    continue
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, col, item)
            self.table.setItem(row, 5, QTableWidgetItem(""))
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(8, 0, 8, 0)
            ok = e.status == "success"
            hl.addWidget(Badge("Success" if ok else "Failed", "success" if ok else "error"),
                         0, Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setCellWidget(row, 5, holder)
        self.count_label.setText(
            f"Showing {len(entries)} of {total} entr{'y' if total == 1 else 'ies'}" if total else "")
        self._update_buttons()

    # ---- actions ----------------------------------------------------------------------
    def _export(self) -> None:
        if not self._entries:
            return
        default = os.path.join(self.ctx.settings.export_dir, "cipherpixel-history.csv")
        path = dialogs.save_file(self, "Export history", default, "CSV files (*.csv)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".csv"
        try:
            n = self.ctx.history.export_csv(path, self._entries)
        except OSError:
            self.ctx.toast("error", "Export failed", "The file could not be written. Check the location and permissions.")
            return
        self.ctx.toast("success", "History exported", f"{n} entr{'y' if n == 1 else 'ies'} saved to {os.path.basename(path)}")

    def _delete_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        if dialogs.confirm(self, "Delete selected entries?", f"{len(ids)} entr{'y' if len(ids) == 1 else 'ies'} will be "
                           "removed from the history list. Your files are not affected.", "Delete", danger=True):
            self.ctx.history.delete(ids)
            self.refresh()
            self.ctx.bus.history_changed.emit()
            self.ctx.toast("info", "Entries deleted")

    def _clear(self) -> None:
        if dialogs.confirm(self, "Clear all history?", "Every history entry will be permanently removed. "
                           "Dashboard totals are kept. This cannot be undone.", "Clear history", danger=True):
            self.ctx.history.clear()
            self.refresh()
            self.ctx.bus.history_changed.emit()
            self.ctx.toast("success", "History cleared")
