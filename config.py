import configparser
import os
import sys
import winreg
from pathlib import Path

_DEFAULTS = {
    'tc_path': '',
    'tc_only': 'true',
    'hotkey_mod': str(0x0002),   # MOD_CONTROL
    'hotkey_vk': str(0x20),      # VK_SPACE
    'window_width': '660',
    'window_height': '440',
    'window_x': '-1',            # -1 = auto-center over TC / screen
    'window_y': '-1',
}


def _find_tc_path() -> str:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Ghisler\Total Commander')
        for value_name in ('InstallDir', 'IniFileName'):
            try:
                val, _ = winreg.QueryValueEx(key, value_name)
                p = Path(val)
                candidate = p if p.is_dir() else p.parent
                if candidate.exists():
                    return str(candidate)
            except FileNotFoundError:
                continue
        winreg.CloseKey(key)
    except OSError:
        pass

    for fallback in (r'C:\wincmd', r'C:\totalcmd', os.path.expandvars(r'%APPDATA%\GHISLER')):
        if os.path.isdir(fallback):
            return fallback
    return ''


class Config:
    def __init__(self, path: Path | None = None):
        if path is None:
            # When frozen by PyInstaller, __file__ is inside the temp _MEIPASS
            # extraction dir which is gone after exit. Use the exe's own directory.
            if getattr(sys, 'frozen', False):
                base = Path(sys.executable).parent
            else:
                base = Path(__file__).parent
            path = base / 'config.ini'
        self.path = path
        self._cfg = configparser.ConfigParser()
        self._load()

    def _load(self):
        if self.path.exists():
            self._cfg.read(self.path, encoding='utf-8')
        if 'App' not in self._cfg:
            self._cfg['App'] = {}
        for k, v in _DEFAULTS.items():
            if k not in self._cfg['App']:
                self._cfg['App'][k] = v
        if not self._cfg['App']['tc_path']:
            self._cfg['App']['tc_path'] = _find_tc_path()

    def reload(self):
        self._cfg = configparser.ConfigParser()
        self._load()

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as fh:
            self._cfg.write(fh)

    def get(self, key: str, fallback: str = '') -> str:
        return self._cfg.get('App', key, fallback=fallback or _DEFAULTS.get(key, ''))

    def get_bool(self, key: str) -> bool:
        return self.get(key).lower() in ('1', 'true', 'yes')

    def get_int(self, key: str) -> int:
        try:
            return int(self.get(key), 0)
        except (ValueError, TypeError):
            return int(_DEFAULTS.get(key, '0'), 0)

    def set(self, key: str, value):
        self._cfg['App'][key] = str(value)
