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


def execute_button(btn: Button, tc_path: str = ''):
    cmd = btn.cmd.strip()
    param = btn.param.strip()
    workdir = btn.workdir.strip() or None

    # Ignore workdir if it doesn't exist (avoid Popen FileNotFoundError)
    if workdir and not os.path.isdir(workdir):
        workdir = None

    if cmd.lower().startswith(('cm_', 'em_')):
        _run_tc_internal(cmd, param, tc_path)
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
