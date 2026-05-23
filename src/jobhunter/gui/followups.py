"""Follow-ups/reminders tab (PySide6)."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
)

from jobhunter.core.job_db import JobDB


class FollowupsTab(QWidget):
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

        heading = QLabel("Follow-up Reminders")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        btns = QHBoxLayout()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh)
        btns.addWidget(btn_refresh)
        btn_set = QPushButton("Set Follow-up")
        btn_set.clicked.connect(self._on_set_followup)
        btns.addWidget(btn_set)
        btns.addStretch()
        layout.addLayout(btns)

        # Overdue
        overdue_label = QLabel("OVERDUE")
        overdue_label.setStyleSheet("color: #c62828; font-weight: bold;")
        layout.addWidget(overdue_label)
        self._overdue_list = QListWidget()
        layout.addWidget(self._overdue_list)

        # Upcoming
        upcoming_label = QLabel("UPCOMING (next 7 days)")
        upcoming_label.setStyleSheet("color: #ef6c00; font-weight: bold;")
        layout.addWidget(upcoming_label)
        self._upcoming_list = QListWidget()
        layout.addWidget(self._upcoming_list)

    def _refresh(self) -> None:
        self._overdue_list.clear()
        overdue = self.db.get_overdue_followups()
        if not overdue:
            item = QListWidgetItem("No overdue follow-ups")
            item.setFlags(Qt.NoItemFlags)
            self._overdue_list.addItem(item)
        else:
            for app in overdue:
                days = (date.today() - date.fromisoformat(app["follow_up_date"])).days
                text = f"[{days}d overdue]  {app['company']} — {app['position']}  (due: {app['follow_up_date']})"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, app["id"])
                self._overdue_list.addItem(item)

        self._upcoming_list.clear()
        upcoming = self.db.get_upcoming_followups(days=7)
        if not upcoming:
            item = QListWidgetItem("No upcoming follow-ups")
            item.setFlags(Qt.NoItemFlags)
            self._upcoming_list.addItem(item)
        else:
            for app in upcoming:
                days = (date.fromisoformat(app["follow_up_date"]) - date.today()).days
                text = f"[in {days}d]  {app['company']} — {app['position']}  (due: {app['follow_up_date']})"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, app["id"])
                self._upcoming_list.addItem(item)

    def _on_set_followup(self) -> None:
        app_id, ok = QInputDialog.getInt(self, "Set Follow-up", "Application ID:")
        if not ok:
            return
        days, ok = QInputDialog.getInt(self, "Set Follow-up", "Days from now:", 3, 1, 90)
        if not ok:
            return

        due = (date.today() + timedelta(days=days)).isoformat()
        self.db.update_application(app_id, follow_up_date=due)
        self.db.add_event(app_id, "note", f"Follow-up set for {due}")
        self._refresh()
        self._set_status(f"Follow-up set for {due}")
