"""QAbstractTableModel for the job dashboard — renders only visible rows."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QColor

from jobhunter.gui.theme import fit_score_color, STATUS_COLORS

_COLUMNS = [
    ("ID", "id"),
    ("Fit", "fit_score"),
    ("Company", "company"),
    ("Position", "position"),
    ("Location", "location"),
    ("Source", "source"),
    ("Found", "date_found"),
    ("Status", "status"),
]


class JobTableModel(QAbstractTableModel):
    """Model backing the job dashboard table.

    Holds a flat list of application dicts from the database.
    The view only asks for data for visible rows — no widget creation per row.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[dict[str, Any]] = []

    def set_data(self, rows: list[dict[str, Any]]) -> None:
        """Replace all data and notify the view."""
        self.beginResetModel()
        self._data = list(rows)
        self.endResetModel()

    def get_app(self, row: int) -> dict[str, Any] | None:
        """Get the application dict for a row index."""
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def get_app_id(self, row: int) -> int | None:
        app = self.get_app(row)
        return app["id"] if app else None

    # ------------------------------------------------------------------
    # QAbstractTableModel interface
    # ------------------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_COLUMNS)

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _COLUMNS[section][0]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        if row >= len(self._data):
            return None

        app = self._data[row]
        col_key = _COLUMNS[col][1]
        value = app.get(col_key, "")

        if role == Qt.DisplayRole:
            if col_key == "fit_score":
                return str(value) if value else "--"
            if col_key == "date_found" and value:
                return value[:10]  # just the date part
            return str(value) if value is not None else ""

        if role == Qt.ForegroundRole:
            if col_key == "fit_score":
                r, g, b = fit_score_color(value if isinstance(value, int) else 0)
                return QColor(r, g, b)
            if col_key == "status":
                rgb = STATUS_COLORS.get(str(value), (200, 200, 200))
                return QColor(*rgb)

        if role == Qt.TextAlignmentRole:
            if col_key in ("id", "fit_score"):
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        if role == Qt.UserRole:
            # Return the full app dict for custom access
            return app

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


class JobFilterProxy(QSortFilterProxyModel):
    """Proxy model for filtering and sorting the job table."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._status_filter = ""
        self._source_filter = ""
        self._min_score = 0
        self._search_text = ""
        self._show_archived = False
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    def set_filters(
        self,
        *,
        status: str = "",
        source: str = "",
        min_score: int = 0,
        search: str = "",
        show_archived: bool = False,
    ) -> None:
        self._status_filter = status
        self._source_filter = source
        self._min_score = min_score
        self._search_text = search.lower()
        self._show_archived = show_archived
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, JobTableModel):
            return True

        app = model.get_app(source_row)
        if not app:
            return False

        status = app.get("status", "")

        # Archived filter
        if status == "archived" and not self._show_archived:
            if self._status_filter != "archived":
                return False

        # Status filter
        if self._status_filter and self._status_filter != "all":
            if status != self._status_filter:
                return False

        # Source filter
        if self._source_filter and self._source_filter != "all":
            if app.get("source", "") != self._source_filter:
                return False

        # Score filter
        if self._min_score > 0:
            if (app.get("fit_score") or 0) < self._min_score:
                return False

        # Text search
        if self._search_text:
            searchable = " ".join([
                str(app.get("company", "")),
                str(app.get("position", "")),
                str(app.get("location", "")),
            ]).lower()
            if self._search_text not in searchable:
                return False

        return True
