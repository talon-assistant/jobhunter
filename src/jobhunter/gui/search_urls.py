"""Search URL manager tab (PySide6)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QMessageBox,
)

from jobhunter.core.job_db import JobDB
from jobhunter.core.scraper import detect_board

_BOARD_CHOICES = ["linkedin", "dice", "builtin", "glassdoor", "other"]


class SearchURLsTab(QWidget):
    def __init__(self, job_db: JobDB, *, status_callback=None) -> None:
        super().__init__()
        self.db = job_db
        self._status_cb = status_callback
        self._build_ui()
        self._refresh()

    def _set_status(self, msg: str) -> None:
        if self._status_cb:
            self._status_cb(msg)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        heading = QLabel("Manage Search URLs")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        # Add URL bar
        add_row = QHBoxLayout()
        self._board_combo = QComboBox()
        self._board_combo.addItems(_BOARD_CHOICES)
        add_row.addWidget(self._board_combo)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("Paste search URL...")
        self._url_input.returnPressed.connect(self._on_add)
        add_row.addWidget(self._url_input, stretch=1)

        self._label_input = QLineEdit()
        self._label_input.setPlaceholderText("Label (optional)")
        add_row.addWidget(self._label_input)

        btn_add = QPushButton("Add")
        btn_add.setProperty("primary", True)
        btn_add.clicked.connect(self._on_add)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        # URL list
        self._list = QListWidget()
        layout.addWidget(self._list)

    def _refresh(self) -> None:
        self._list.clear()
        urls = self.db.list_search_urls()
        if not urls:
            item = QListWidgetItem("No search URLs configured")
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            return

        for entry in urls:
            uid = entry["id"]
            board = entry.get("board", "other")
            url = entry.get("url", "")
            label = entry.get("label", "")
            enabled = bool(entry.get("enabled", 1))
            last = entry.get("last_scraped", "never")

            display = label if label else (url[:80] + "..." if len(url) > 80 else url)
            check = "✓" if enabled else "✗"
            text = f"  {check}  [{board}]  {display}  (last: {last or 'never'})"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, uid)
            self._list.addItem(item)

        # Context menu would go here in a polish pass

    def _on_add(self) -> None:
        url = self._url_input.text().strip()
        if not url.startswith("http"):
            QMessageBox.warning(self, "Invalid URL", "URL must start with http")
            return

        board = self._board_combo.currentText()
        detected = detect_board(url)
        if detected != "other":
            board = detected

        label = self._label_input.text().strip()
        self.db.add_search_url(board, url, label)
        self._url_input.clear()
        self._label_input.clear()
        self._refresh()
        self._set_status(f"Search URL added ({board})")
