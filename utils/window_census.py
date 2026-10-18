"""Log every new visible top-level window that eCan or one of its child
processes owns (Windows only, read-only).

Customer report 2026-10-18: "浏览器打开过一段时间后（通常是1-3个小时内）会弹出3个
black空白窗口" -- nothing in the logs said which program opened them (console
windows from a child process? Chrome windows?). Once a minute this lists the
visible windows of eCan's process tree and logs each window it has not seen
before with the owning program, its parent, title and size, so the next log
names the culprit. It never touches a window.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Dict, Iterable, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

INTERVAL_SEC = 60

# (hwnd, pid) pairs already reported; windows are matched by handle + owner.
_seen: set = set()
_thread: Optional[threading.Thread] = None


def _tree_pids(root_pid: int) -> Dict[int, Tuple[str, int]]:
    """pid -> (exe name, parent pid) for root_pid and all its descendants."""
    import psutil
    out: Dict[int, Tuple[str, int]] = {}
    try:
        root = psutil.Process(root_pid)
        procs = [root] + root.children(recursive=True)
    except Exception:
        return out
    for p in procs:
        try:
            out[p.pid] = (p.name(), p.ppid())
        except Exception:
            continue
    return out


def _visible_windows() -> List[Tuple[int, int, str, int, int]]:
    """(hwnd, pid, title, width, height) for every visible top-level window."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found: List[Tuple[int, int, str, int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            found.append((int(hwnd), int(pid.value), buf.value,
                          int(rect.right - rect.left), int(rect.bottom - rect.top)))
        except Exception:
            pass
        return True

    user32.EnumWindows(_cb, 0)
    return found


# Programs that draw a console for another process. With Windows Terminal as
# the default console, a child's black console window belongs to
# WindowsTerminal.exe -- outside eCan's process tree -- and the child only owns
# a hidden 0x0 placeholder. Report new console-host windows too (their title is
# usually the console program's path).
CONSOLE_HOSTS = {"windowsterminal.exe", "openconsole.exe", "conhost.exe"}


def new_windows(windows: Iterable[Tuple[int, int, str, int, int]],
                tree: Dict[int, Tuple[str, int]],
                console_hosts: Optional[Dict[int, str]] = None) -> List[str]:
    """Log lines for windows of eCan's process tree (and new console-host
    windows) not reported before."""
    lines = []
    console_hosts = console_hosts or {}
    for hwnd, pid, title, w, h in windows:
        if (hwnd, pid) in _seen:
            continue
        if pid in tree:
            _seen.add((hwnd, pid))
            exe, ppid = tree[pid]
            parent = tree.get(ppid, ("?", 0))[0]
            lines.append(f"[WindowCensus] new window: exe={exe} pid={pid} parent={parent}({ppid}) "
                         f"size={w}x{h} title={title[:80]!r}")
        elif pid in console_hosts and w > 0 and h > 0:
            _seen.add((hwnd, pid))
            lines.append(f"[WindowCensus] new console window (may be an eCan child's): "
                         f"host={console_hosts[pid]} pid={pid} size={w}x{h} title={title[:80]!r}")
    return lines


def _console_host_pids() -> Dict[int, str]:
    import psutil
    out: Dict[int, str] = {}
    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = str(p.info.get("name") or "")
            if name.lower() in CONSOLE_HOSTS:
                out[int(p.info["pid"])] = name
        except Exception:
            continue
    return out


def check_once(root_pid: Optional[int] = None) -> List[str]:
    tree = _tree_pids(root_pid or os.getpid())
    lines = new_windows(_visible_windows(), tree, _console_host_pids())
    for line in lines:
        logger.info(line)
    return lines


def _run() -> None:
    import time
    first = True
    while True:
        try:
            lines = check_once()
            if first:
                logger.info(f"[WindowCensus] watching visible windows of eCan and its child "
                            f"processes every {INTERVAL_SEC}s ({len(lines)} at start)")
                first = False
        except Exception as e:
            logger.debug(f"[WindowCensus] check failed: {e}")
        time.sleep(INTERVAL_SEC)


def start_window_census() -> None:
    """Start the once-a-minute census thread (Windows only; no-op elsewhere)."""
    global _thread
    if sys.platform != "win32" or os.environ.get("ECAN_WINDOW_CENSUS", "1") == "0":
        return
    if _thread is not None and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run, name="WindowCensus", daemon=True)
    _thread.start()
