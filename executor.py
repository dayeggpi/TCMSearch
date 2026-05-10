import ctypes
import ctypes.wintypes
import os
import shlex
import struct
import subprocess

from parser import Button

WM_COPYDATA = 0x004A
_EMC_DW = struct.unpack('<I', b'EMC\x00')[0]


class _COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [
        ('dwData', ctypes.wintypes.WPARAM),
        ('cbData', ctypes.wintypes.DWORD),
        ('lpData', ctypes.c_void_p),
    ]


def find_tc_hwnd() -> int:
    return ctypes.windll.user32.FindWindowW('TTOTAL_CMD', None)


def _find_tc_exe(tc_path: str) -> str:
    candidates = []
    if tc_path:
        candidates += [
            os.path.join(tc_path, 'TOTALCMD64.EXE'),
            os.path.join(tc_path, 'TOTALCMD.EXE'),
        ]
    candidates += ['TOTALCMD64.EXE', 'TOTALCMD.EXE', 'totalcmd64.exe', 'totalcmd.exe']
    for c in candidates:
        if os.path.isfile(c):
            return c
    # Try PATH
    import shutil
    for name in ('totalcmd64.exe', 'totalcmd.exe'):
        found = shutil.which(name)
        if found:
            return found
    return ''


def _send_wm_copydata(hwnd: int, cmd: str, param: str = ''):
    payload = cmd
    if param:
        payload += '\r' + param
    data = payload.encode('utf-8') + b'\x00'
    buf = ctypes.create_string_buffer(data)
    cds = _COPYDATASTRUCT(dwData=_EMC_DW, cbData=len(data),
                          lpData=ctypes.cast(buf, ctypes.c_void_p))
    ctypes.windll.user32.SendMessageW(hwnd, WM_COPYDATA, 0, ctypes.byref(cds))


def _run_tc_internal(cmd: str, param: str, tc_path: str):
    """Execute cm_/em_ command via totalcmd /C= or WM_COPYDATA fallback."""
    tc_exe = _find_tc_exe(tc_path)
    if tc_exe:
        command_str = cmd + ('\r' + param if param else '')
        try:
            subprocess.Popen(
                [tc_exe, '/O', '/S', f'/C={command_str}'],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            return
        except Exception:
            pass

    hwnd = find_tc_hwnd()
    if hwnd:
        _send_wm_copydata(hwnd, cmd, param)


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ('cbSize',         ctypes.wintypes.DWORD),
        ('fMask',          ctypes.wintypes.ULONG),
        ('hwnd',           ctypes.wintypes.HWND),
        ('lpVerb',         ctypes.wintypes.LPCWSTR),
        ('lpFile',         ctypes.wintypes.LPCWSTR),
        ('lpParameters',   ctypes.wintypes.LPCWSTR),
        ('lpDirectory',    ctypes.wintypes.LPCWSTR),
        ('nShow',          ctypes.c_int),
        ('hInstApp',       ctypes.wintypes.HINSTANCE),
        ('lpIDList',       ctypes.c_void_p),
        ('lpClass',        ctypes.wintypes.LPCWSTR),
        ('hkeyClass',      ctypes.wintypes.HKEY),
        ('dwHotKey',       ctypes.wintypes.DWORD),
        ('hIconOrMonitor', ctypes.wintypes.HANDLE),
        ('hProcess',       ctypes.wintypes.HANDLE),
    ]

_SEE_MASK_ASYNCOK = 0x00100000


def _split_cmd_args(cmd: str) -> tuple[str, str]:
    """Split 'C:\\path\\app.exe arg1 arg2' into (exe, args) for cmds with embedded args."""
    if os.path.isfile(cmd):
        return cmd, ''
    for ext in ('.exe', '.com', '.bat', '.cmd', '.pif', '.scr'):
        idx = cmd.lower().find(ext + ' ')
        if idx != -1:
            split = idx + len(ext)
            return cmd[:split], cmd[split:].strip()
    return cmd, ''


def _run_as_admin(exe: str, params: str, workdir: str | None) -> None:
    sei = _SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = _SEE_MASK_ASYNCOK
    sei.hwnd = find_tc_hwnd()  # parent UAC dialog to TC window so it comes to front
    sei.lpVerb = 'runas'
    sei.lpFile = exe
    sei.lpParameters = params or None
    sei.lpDirectory = workdir or None
    sei.nShow = 1  # SW_SHOWNORMAL
    ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
    if not ok:
        err = ctypes.windll.kernel32.GetLastError()
        raise OSError(f'ShellExecuteExW runas failed (error {err})')


def execute_button(btn: Button, tc_path: str = ''):
    commander_path = tc_path.strip()
    cmd = btn.cmd.strip().replace('%COMMANDER_PATH%', commander_path)
    param = btn.param.strip().replace('%COMMANDER_PATH%', commander_path)
    workdir_raw = btn.workdir.strip()
    workdir_raw = workdir_raw.replace('%COMMANDER_PATH%', commander_path)

    cmd = os.path.expandvars(cmd)
    param = os.path.expandvars(param)
    workdir = os.path.expandvars(workdir_raw) if workdir_raw else None

    # Ignore workdir if it doesn't exist (avoid Popen FileNotFoundError)
    if workdir and not os.path.isdir(workdir):
        workdir = None

    if cmd.lower().startswith(('cm_', 'em_')):
        _run_tc_internal(cmd, param, tc_path)
        return

    if not param and ' ' in cmd:
        cmd, param = _split_cmd_args(cmd)

    if btn.admin:
        _run_as_admin(cmd, param, workdir)
        return

    # Pass cmd directly as argv[0] — never shlex-split it, backslashes in
    # Windows paths would be eaten by shlex posix mode.
    args = [cmd]
    if param:
        try:
            args += shlex.split(param, posix=False)
        except Exception:
            args.append(param)

    try:
        subprocess.Popen(
            args,
            cwd=workdir,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except Exception:
        try:
            full = f'"{cmd}"' if ' ' in cmd else cmd
            if param:
                full += ' ' + param
            subprocess.Popen(full, cwd=workdir, shell=True)
        except Exception:
            pass  # surfaced to caller via tray notification
