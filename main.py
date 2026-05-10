"""TCMSearch — Total Commander button bar quick-search launcher."""

import ctypes
import ctypes.wintypes
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QAbstractNativeEventFilter, QAbstractEventDispatcher
from PyQt6.QtGui import QIcon, QAction, QPixmap, QColor
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog, QVBoxLayout, QLabel, QMessageBox
from PyQt6.QtCore import Qt

from config import Config
from executor import execute_button, find_tc_hwnd
from gui import SearchOverlay
from parser import load_all_buttons

HOTKEY_ID = 1
WM_HOTKEY = 0x0312


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._cb = callback

    def nativeEventFilter(self, event_type, message):
        if event_type == b'windows_generic_MSG':
            msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._cb()
                return True, 0
        return False, 0


class _AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('About TCMSearch')
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setFixedSize(300, 110)
        self.setStyleSheet("""
            QDialog  { background: #1e1e2e; }
            QLabel   { color: #cdd6f4; font-family: 'Segoe UI'; font-size: 13px; }
            QLabel a { color: #89b4fa; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        title = QLabel('<b>TCMSearch</b>  <span style="font-size:11px; color:#6c7086;">v0.1.3</span>')
        title.setStyleSheet('font-size: 15px; color: #cdd6f4;')
        layout.addWidget(title)

        author = QLabel('Author: <b>dayeggpi</b>')
        layout.addWidget(author)

        link = QLabel('<a href="https://github.com/dayeggpi">github.com/dayeggpi</a>')
        link.setOpenExternalLinks(True)
        layout.addWidget(link)


def _resource(name: str) -> Path:
    # PyInstaller onefile: bundled files land in sys._MEIPASS at runtime.
    # Dev mode: look next to this script.
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    p = base / name
    if p.exists():
        return p
    # Final fallback: next to the running exe
    return Path(sys.executable).parent / name


def _make_icon() -> QIcon:
    p = _resource('app.ico')
    if p.exists():
        return QIcon(str(p))
    pix = QPixmap(32, 32)
    pix.fill(QColor('#89b4fa'))
    return QIcon(pix)


class TCMSearch:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName('TCMSearch')
        self.app.setQuitOnLastWindowClosed(False)

        self.config = Config()
        self.buttons = []
        self.overlay: SearchOverlay | None = None
        self._hotkey_filter: _HotkeyFilter | None = None

        self._setup_tray()
        self._reload_buttons()
        self._register_hotkey()
        self._build_overlay()

    # ── tray ───────────────────────────────────────────────────────────────

    def _setup_tray(self):
        icon = _make_icon()
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip('TCMSearch')

        menu = QMenu()
        a_reload = QAction('Reload Bars and config', menu)
        a_reload.triggered.connect(self._reload_buttons)
        menu.addAction(a_reload)

        a_settings = QAction('Settings (open config.ini)', menu)
        a_settings.triggered.connect(self._open_settings)
        menu.addAction(a_settings)

        a_about = QAction('About', menu)
        a_about.triggered.connect(self._show_about)
        menu.addAction(a_about)

        menu.addSeparator()

        a_exit = QAction('Exit', menu)
        a_exit.triggered.connect(self._exit)
        menu.addAction(a_exit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_overlay()

    def _open_settings(self):
        if not self.config.path.exists():
            self.config.save()
        os.startfile(str(self.config.path))

    def _show_about(self):
        dlg = _AboutDialog()
        dlg.exec()

    # ── buttons ────────────────────────────────────────────────────────────

    def _reload_buttons(self):
        self.config.reload()
        tc_path = self.config.get('tc_path')
        os.environ['COMMANDER_PATH'] = tc_path or ''
        self.buttons = load_all_buttons(tc_path)
        if self.overlay:
            self.overlay.all_buttons = self.buttons
        self.tray.setToolTip(f'TCMSearch — {len(self.buttons)} buttons')
        print(f'Loaded {len(self.buttons)} buttons from: {tc_path or "(not found)"}')

    # ── hotkey ─────────────────────────────────────────────────────────────

    def _register_hotkey(self):
        mod = self.config.get_int('hotkey_mod')
        vk = self.config.get_int('hotkey_vk')
        ok = ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, mod, vk)
        if not ok:
            self.tray.showMessage(
                'TCMSearch',
                'Could not register Ctrl+Space hotkey (already in use).\n'
                'Edit config.ini to change the hotkey.',
                QSystemTrayIcon.MessageIcon.Warning,
                4000,
            )

        self._hotkey_filter = _HotkeyFilter(self._on_hotkey)
        QAbstractEventDispatcher.instance().installNativeEventFilter(self._hotkey_filter)

    def _on_hotkey(self):
        if self.config.get_bool('tc_only'):
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            cls = ctypes.create_unicode_buffer(64)
            ctypes.windll.user32.GetClassNameW(hwnd, cls, 64)
            if cls.value != 'TTOTAL_CMD':
                return
        self._toggle_overlay()

    # ── overlay ────────────────────────────────────────────────────────────

    def _build_overlay(self):
        self.overlay = SearchOverlay(self.buttons, self._run_button)
        self.overlay.position_changed.connect(self._save_position)

    def _save_position(self, x: int, y: int):
        self.config.set('window_x', x)
        self.config.set('window_y', y)
        self.config.save()

    def _toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show_over_tc(
                self.config.get_int('window_width') or 660,
                self.config.get_int('window_height') or 440,
                self.config.get_int('window_x'),
                self.config.get_int('window_y'),
            )

    def _run_button(self, btn):
        try:
            execute_button(btn, self.config.get('tc_path'))
        except Exception as exc:
            if btn.admin:
                QMessageBox.critical(None, 'TCMSearch', f'Failed to run as admin:\n{btn.cmd}\n\n{exc}')
            else:
                self.tray.showMessage(
                    'TCMSearch', f'Failed to run:\n{btn.cmd}\n\n{exc}',
                    QSystemTrayIcon.MessageIcon.Warning, 4000,
                )
        if not btn.admin:
            hwnd = find_tc_hwnd()
            if hwnd:
                ctypes.windll.user32.SetForegroundWindow(hwnd)

    # ── lifecycle ──────────────────────────────────────────────────────────

    def _exit(self):
        ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        if self._hotkey_filter:
            QAbstractEventDispatcher.instance().removeNativeEventFilter(self._hotkey_filter)
        self.tray.hide()
        self.app.quit()

    def run(self):
        if not self.config.path.exists():
            self.config.save()
        sys.exit(self.app.exec())


if __name__ == '__main__':
    app = TCMSearch()
    app.run()
