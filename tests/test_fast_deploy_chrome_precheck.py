"""Fast Deploy (douyin_cs) Chrome pre-check: install detection with download
link, PATH registration, desktop-shortcut retargeting to the debug flags."""

import os
import platform
import sys

import pytest

from cli.deploy import chrome_precheck as cp


def test_not_installed_fails_with_download_link(monkeypatch):
    import agent.mcp.server.chrome_launcher as cl
    monkeypatch.setattr(cl, "find_chrome", lambda: {"found": False, "path": "", "in_path": False})
    ok, log, msg = cp.run_chrome_precheck()
    assert ok is False
    assert cp.CHROME_DOWNLOAD_URL in msg
    assert any(cp.CHROME_DOWNLOAD_URL in line for line in log)
    assert any("未检测到" in line for line in log)  # bilingual instruction


def test_found_adds_path_and_updates_shortcuts(monkeypatch, tmp_path):
    import agent.mcp.server.chrome_launcher as cl
    fake_chrome = str(tmp_path / "Application" / "chrome.exe")
    monkeypatch.setattr(cl, "find_chrome", lambda: {"found": True, "path": fake_chrome, "in_path": False})
    calls = {}
    monkeypatch.setattr(cl, "add_chrome_to_path",
                        lambda p: calls.setdefault("path", p) and {"added": True, "detail": "test"})
    monkeypatch.setattr(cp, "update_chrome_shortcuts",
                        lambda p, desktop_dirs=None: {"updated": ["Desktop\\Google Chrome.lnk"], "skipped": [], "detail": ""})
    ok, log, msg = cp.run_chrome_precheck()
    assert ok is True and msg == ""
    assert calls["path"] == fake_chrome
    joined = "\n".join(log)
    assert "Added Chrome directory to PATH" in joined
    if platform.system() == "Windows":
        assert "Google Chrome.lnk" in joined
        assert cp.CHROME_DEBUG_ARGS in joined


def test_precheck_never_raises_from_shortcut_step(monkeypatch):
    import agent.mcp.server.chrome_launcher as cl
    monkeypatch.setattr(cl, "find_chrome", lambda: {"found": True, "path": r"C:\x\chrome.exe", "in_path": True})
    monkeypatch.setattr(cp, "update_chrome_shortcuts",
                        lambda p, desktop_dirs=None: {"updated": [], "skipped": [], "detail": "pywin32 unavailable: x"})
    ok, log, _ = cp.run_chrome_precheck()
    assert ok is True
    if platform.system() == "Windows":
        assert any("No desktop Chrome shortcut found" in line for line in log)


@pytest.mark.skipif(platform.system() != "Windows", reason="real .lnk editing is Windows-only")
def test_real_shortcut_retarget(tmp_path):
    win32com = pytest.importorskip("win32com.client")
    shell = win32com.Dispatch("WScript.Shell")
    chrome = str(tmp_path / "chrome.exe")
    (tmp_path / "chrome.exe").write_bytes(b"")
    desk = tmp_path / "Desktop"
    desk.mkdir()
    # A Chrome shortcut with default args, and an unrelated shortcut that must be left alone.
    sc = shell.CreateShortcut(str(desk / "Google Chrome.lnk"))
    sc.TargetPath = chrome
    sc.Arguments = ""
    sc.Save()
    other = shell.CreateShortcut(str(desk / "Notepad.lnk"))
    other.TargetPath = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "notepad.exe")
    other.Arguments = "keep"
    other.Save()

    r = cp.update_chrome_shortcuts(chrome, desktop_dirs=[str(desk)])
    assert r["updated"] == [str(desk / "Google Chrome.lnk")]
    assert shell.CreateShortcut(str(desk / "Google Chrome.lnk")).Arguments == cp.CHROME_DEBUG_ARGS
    assert shell.CreateShortcut(str(desk / "Notepad.lnk")).Arguments == "keep"
    # Idempotent: second run skips, does not re-write.
    r2 = cp.update_chrome_shortcuts(chrome, desktop_dirs=[str(desk)])
    assert r2["updated"] == [] and len(r2["skipped"]) == 1
