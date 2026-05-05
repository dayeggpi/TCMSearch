import configparser
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Button:
    menu: str
    cmd: str
    param: str = ''
    workdir: str = ''
    source_bar: str = ''
    tooltip: str = ''

    @property
    def display_cmd(self) -> str:
        return (self.cmd + ' ' + self.param).strip()


def _raw_cfg() -> configparser.RawConfigParser:
    return configparser.RawConfigParser(strict=False)


def find_bar_files(tc_path: str) -> list[str]:
    if not tc_path or not os.path.isdir(tc_path):
        return []

    found: list[str] = []
    seen: set[str] = set()

    def add(p: str):
        p = os.path.normpath(p)
        if p not in seen and os.path.isfile(p):
            seen.add(p)
            found.append(p)

    # Parse wincmd.ini for explicit bar file references
    for ini_name in ('wincmd.ini', 'WINCMD.INI'):
        ini_path = os.path.join(tc_path, ini_name)
        if not os.path.isfile(ini_path):
            continue
        cfg = _raw_cfg()
        try:
            cfg.read(ini_path, encoding='utf-8')
        except Exception:
            continue
        for section in cfg.sections():
            for key, val in cfg.items(section):
                if val.lower().endswith('.bar'):
                    candidate = val if os.path.isabs(val) else os.path.join(tc_path, val)
                    add(candidate)

    # Glob all .bar files in TC dir tree
    for f in glob.glob(os.path.join(tc_path, '**', '*.bar'), recursive=True):
        add(f)

    return found


def parse_bar_file(bar_path: str) -> list[Button]:
    cfg = _raw_cfg()
    for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            cfg.read(bar_path, encoding=enc)
            break
        except Exception:
            cfg = _raw_cfg()
            continue

    section = next((s for s in cfg.sections() if s.lower() == 'buttonbar'), None)
    if section is None:
        return []

    try:
        count = int(cfg.get(section, 'buttoncount', fallback='0'))
    except (ValueError, configparser.Error):
        return []

    bar_name = Path(bar_path).stem
    buttons: list[Button] = []
    # TC .bar files use 1-based indices (menu1..menuN)
    for i in range(1, count + 1):
        try:
            cmd = cfg.get(section, f'cmd{i}', fallback='').strip()
            if not cmd or cmd.lower().endswith('.bar'):
                continue
            menu = cfg.get(section, f'menu{i}', fallback='').strip() or cmd
            param = cfg.get(section, f'param{i}', fallback='').strip()
            workdir = cfg.get(section, f'path{i}', fallback='').strip()
            tooltip = cfg.get(section, f'tooltip{i}', fallback='').strip()
            buttons.append(Button(menu, cmd, param, workdir, bar_name, tooltip))
        except Exception:
            continue
    return buttons


def load_all_buttons(tc_path: str) -> list[Button]:
    buttons: list[Button] = []
    for bar_file in find_bar_files(tc_path):
        buttons.extend(parse_bar_file(bar_file))
    return buttons
