import ctypes
import ctypes.wintypes
import re
from typing import Callable

from PyQt6.QtCore import Qt, QEvent, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QKeyEvent, QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QTableView,
    QHeaderView, QAbstractItemView, QLabel, QApplication,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle,
)

from parser import Button

_STYLE = """
QDialog {
    background-color: #1e1e2e;
    border: 1px solid #585b70;
    border-radius: 8px;
}
QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 15px;
    font-family: 'Segoe UI', sans-serif;
    selection-background-color: #89b4fa;
}
QLineEdit:focus { border-color: #89b4fa; }
QTableView {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: none;
    gridline-color: #313244;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    outline: none;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}
QTableView::item {
    padding: 5px 8px;
    border-bottom: 1px solid #2a2a3e;
}
QTableView::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QHeaderView::section {
    background-color: #181825;
    color: #6c7086;
    border: none;
    border-bottom: 1px solid #313244;
    padding: 4px 8px;
    font-size: 11px;
    font-family: 'Segoe UI', sans-serif;
}
QLabel { color: #6c7086; font-size: 11px; font-family: 'Segoe UI', sans-serif; }
QScrollBar:vertical {
    background: #1e1e2e; width: 7px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #45475a; border-radius: 3px; min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

_BAR_COLOR = QColor('#585b70')
_BAR_FONT = QFont('Segoe UI', 10)
_HEADERS = ['Name', 'Command / Params', 'Bar']


class _BarDelegate(QStyledItemDelegate):
    """Renders the Bar column in muted color unless the row is selected."""
    def initStyleOption(self, option: QStyleOptionViewItem, index):
        super().initStyleOption(option, index)
        if not (option.state & QStyle.StateFlag.State_Selected):
            option.palette.setColor(option.palette.ColorRole.Text, _BAR_COLOR)


class _ButtonModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows: list[Button] = []

    def set_buttons(self, buttons: list[Button]):
        self.beginResetModel()
        self._rows = buttons
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 3

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        btn = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0: return btn.menu
            if col == 1: return btn.display_cmd
            if col == 2: return btn.source_bar

        if role == Qt.ItemDataRole.ToolTipRole:
            return btn.tooltip or btn.display_cmd

        if col == 2 and role == Qt.ItemDataRole.FontRole:
            return _BAR_FONT

        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _HEADERS[section]
        return None

    def button_at(self, row: int) -> Button | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class SearchOverlay(QDialog):
    def __init__(self, buttons: list[Button], execute_fn: Callable, parent=None):
        super().__init__(parent)
        self.all_buttons = buttons
        self._execute_fn = execute_fn
        self._model = _ButtonModel()
        self._build_ui()
        self._configure_window()

    def _configure_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setStyleSheet(_STYLE)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search button bars… (regex)')
        self.search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.search_input)

        self.table = QTableView()
        self.table.setModel(self._model)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setShowGrid(False)
        self.table.setItemDelegateForColumn(2, _BarDelegate(self.table))
        self.table.doubleClicked.connect(self._execute_selected)
        layout.addWidget(self.table)

        self.status = QLabel()
        layout.addWidget(self.status)

    def _on_text_changed(self, text: str):
        if not text:
            filtered = self.all_buttons
        else:
            try:
                pat = re.compile(text, re.IGNORECASE)
                match = pat.search
            except re.error:
                tl = text.lower()
                match = lambda s: tl in s.lower()  # noqa: E731

            filtered = [
                btn for btn in self.all_buttons
                if match(btn.menu) or match(btn.cmd) or (btn.tooltip and match(btn.tooltip))
            ]

        self._model.set_buttons(filtered)
        if filtered:
            self.table.selectRow(0)
        self.status.setText(f'{len(filtered)} of {len(self.all_buttons)} buttons')

    def _execute_selected(self):
        row = self.table.currentIndex().row()
        btn = self._model.button_at(row)
        if btn:
            self.hide()
            self._execute_fn(btn)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.hide()
        super().changeEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._execute_selected()
        elif key == Qt.Key.Key_Down:
            row = self.table.currentIndex().row()
            if row < self._model.rowCount() - 1:
                self.table.selectRow(row + 1)
        elif key == Qt.Key.Key_Up:
            row = self.table.currentIndex().row()
            if row > 0:
                self.table.selectRow(row - 1)
        else:
            super().keyPressEvent(event)

    def show_over_tc(self, width: int = 660, height: int = 440):
        self.resize(width, height)
        hwnd = ctypes.windll.user32.FindWindowW('TTOTAL_CMD', None)
        if hwnd:
            rc = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rc))
            x = rc.left + (rc.right - rc.left - width) // 2
            y = rc.top + (rc.bottom - rc.top - height) // 2
        else:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - width) // 2
            y = (screen.height() - height) // 2

        self.move(x, y)
        self.show()
        self.activateWindow()
        self.raise_()
        self.search_input.clear()
        self.search_input.setFocus()
        self._on_text_changed('')
