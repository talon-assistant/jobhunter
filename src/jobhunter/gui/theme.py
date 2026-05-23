"""PySide6 dark theme and color constants."""

from __future__ import annotations

# -- Fit score colors (R, G, B) --
FIT_GREEN = (46, 125, 50)
FIT_ORANGE = (239, 108, 0)
FIT_RED = (198, 40, 40)
FIT_GRAY = (136, 136, 136)

# -- Status colors --
STATUS_COLORS = {
    "new": (100, 181, 246),
    "reviewing": (255, 213, 79),
    "applied": (129, 199, 132),
    "interviewing": (255, 183, 77),
    "offer": (76, 175, 80),
    "rejected": (239, 83, 80),
    "withdrawn": (158, 158, 158),
    "archived": (97, 97, 97),
}

PRIORITY_STRONG = (76, 175, 80)
PRIORITY_NORMAL = (200, 200, 200)
PRIORITY_WEAK = (158, 158, 158)


def fit_score_color(score: int) -> tuple[int, int, int]:
    """Return the RGB color for a given fit score."""
    if score >= 80:
        return FIT_GREEN
    elif score >= 60:
        return FIT_ORANGE
    elif score >= 1:
        return FIT_RED
    return FIT_GRAY


DARK_STYLESHEET = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "SF Pro Display", "Ubuntu", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #1e1e2e;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    background-color: #1e1e2e;
}

QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    background-color: #45475a;
}

QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: none;
    padding: 6px 16px;
    border-radius: 4px;
    min-height: 24px;
}

QPushButton:hover {
    background-color: #585b70;
}

QPushButton:pressed {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QPushButton:disabled {
    background-color: #313244;
    color: #585b70;
}

QPushButton[primary="true"] {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
}

QPushButton[primary="true"]:hover {
    background-color: #74c7ec;
}

QPushButton[danger="true"] {
    background-color: #f38ba8;
    color: #1e1e2e;
}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 5px 8px;
    border-radius: 4px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #89b4fa;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
    border: 1px solid #45475a;
}

QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    padding: 6px;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
}

QTableView {
    background-color: #1e1e2e;
    alternate-background-color: #232336;
    gridline-color: #313244;
    selection-background-color: #45475a;
    border: 1px solid #45475a;
}

QTableView::item {
    padding: 4px;
}

QTableView::item:selected {
    background-color: #45475a;
}

QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #1e1e2e;
    height: 10px;
}

QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 5px;
    min-width: 30px;
}

QSplitter::handle {
    background-color: #45475a;
}

QGroupBox {
    border: 1px solid #45475a;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 16px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #89b4fa;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #45475a;
    border-radius: 3px;
    background-color: #313244;
}

QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

QLabel[heading="true"] {
    font-size: 16px;
    font-weight: bold;
    color: #89b4fa;
}

QLabel[subheading="true"] {
    font-size: 14px;
    color: #a6adc8;
}

QLabel[dim="true"] {
    color: #6c7086;
}

QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
}

QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
    min-height: 20px;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 4px;
}

QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 4px;
}

QDialog {
    background-color: #1e1e2e;
}

QListWidget {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 4px;
}

QListWidget::item {
    padding: 6px;
}

QListWidget::item:selected {
    background-color: #45475a;
}

QListWidget::item:hover {
    background-color: #313244;
}
"""
