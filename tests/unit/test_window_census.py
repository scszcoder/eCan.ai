"""The window census reports each new visible window of eCan's process tree
once, with the owning program (customer: "3 black blank windows" after 1-3 h,
no clue in the logs which program opened them)."""
import subprocess
import sys
import time

import pytest

from utils import window_census as wc


def test_reports_only_windows_of_the_process_tree_and_only_once():
    wc._seen.clear()
    tree = {100: ("eCan.exe", 1), 200: ("chrome.exe", 100), 300: ("cmd.exe", 100)}
    wins = [(1, 200, "", 800, 600), (2, 300, "C:\\Windows\\system32\\cmd.exe", 1000, 500),
            (3, 999, "Notepad", 300, 200)]                       # 999: not ours
    lines = wc.new_windows(wins, tree)
    assert len(lines) == 2
    assert "exe=chrome.exe" in lines[0] and "parent=eCan.exe(100)" in lines[0] and "800x600" in lines[0]
    assert "exe=cmd.exe" in lines[1]
    assert wc.new_windows(wins, tree) == []                        # already reported


def test_console_host_window_is_reported_but_not_its_hidden_placeholder():
    wc._seen.clear()
    lines = wc.new_windows([(5, 400, "C:\\Windows\\system32\\cmd.exe", 1150, 615),
                            (6, 400, "", 0, 0)], {}, {400: "WindowsTerminal.exe"})
    assert len(lines) == 1 and "host=WindowsTerminal.exe" in lines[0] and "cmd.exe" in lines[0]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows window enumeration")
def test_a_childs_console_window_is_seen():
    wc._seen.clear()
    wc.check_once()                                                # baseline
    p = subprocess.Popen(["cmd.exe", "/c", "ping -n 6 127.0.0.1 >nul"],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    try:
        lines = []
        for _ in range(20):
            time.sleep(0.25)
            lines += wc.check_once()
            if lines:
                break
        # Classic console: owned by cmd/conhost in our tree. Windows Terminal:
        # a console-host window titled with cmd.exe's path.
        assert any("exe=cmd.exe" in l or "exe=conhost.exe" in l
                   or ("console window" in l and "cmd.exe" in l) for l in lines), lines
    finally:
        p.kill()
