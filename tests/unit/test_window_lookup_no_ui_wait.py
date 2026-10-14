"""Finding a window by title must not wait on this process's UI thread
(alpha yv 2026-10-12: a 千牛 send waited 8 s in the window lookup --
pygetwindow's GetWindowTextW sends WM_GETTEXT to our own busy Qt windows)."""
import sys
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 window enumeration")


def test_lookup_does_not_wait_for_a_busy_ui_thread_of_this_process():
    tk = pytest.importorskip("tkinter")
    from agent.mcp.server.wechat import platform_utils as pu
    try:
        root = tk.Tk()
    except Exception as exc:           # no desktop session
        pytest.skip(f"no Tk window: {exc}")
    root.title("QN-HANG-TEST-接待中心")
    root.update()
    res = {}

    def lookup():
        t = time.monotonic()
        found = pu._find_windows_win32(["QN-HANG-TEST"])
        res["s"], res["n"] = time.monotonic() - t, len(found)

    th = threading.Thread(target=lookup)
    th.start()
    th.join(3)                         # the UI thread pumps no messages meanwhile
    root.update()
    th.join(5)
    root.destroy()
    assert res.get("n") == 1 and res["s"] < 1.0
