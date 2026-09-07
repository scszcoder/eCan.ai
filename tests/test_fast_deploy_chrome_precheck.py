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
                        lambda p, desktop_dirs=None, debug_args=None: {"updated": ["Desktop\\Google Chrome.lnk"], "skipped": [], "detail": ""})
    ok, log, msg = cp.run_chrome_precheck()
    assert ok is True and msg == ""
    assert calls["path"] == fake_chrome
    joined = "\n".join(log)
    assert "Added Chrome directory to PATH" in joined
    if platform.system() == "Windows":
        assert "Google Chrome.lnk" in joined
        assert cp.chrome_debug_args() in joined


def test_precheck_never_raises_from_shortcut_step(monkeypatch):
    import agent.mcp.server.chrome_launcher as cl
    monkeypatch.setattr(cl, "find_chrome", lambda: {"found": True, "path": r"C:\x\chrome.exe", "in_path": True})
    monkeypatch.setattr(cp, "update_chrome_shortcuts",
                        lambda p, desktop_dirs=None, debug_args=None: {"updated": [], "skipped": [], "detail": "pywin32 unavailable: x"})
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
    assert shell.CreateShortcut(str(desk / "Google Chrome.lnk")).Arguments == cp.chrome_debug_args()
    assert shell.CreateShortcut(str(desk / "Notepad.lnk")).Arguments == "keep"
    # Idempotent: second run skips, does not re-write.
    r2 = cp.update_chrome_shortcuts(chrome, desktop_dirs=[str(desk)])
    assert r2["updated"] == [] and len(r2["skipped"]) == 1


def test_find_chrome_scans_non_c_drives(monkeypatch):
    """A portable Chrome on D:\ (no App Paths entry, not on PATH) is still found
    by the fixed-drive scan fallback."""
    import agent.mcp.server.chrome_launcher as cl
    if platform.system() != "Windows":
        return
    monkeypatch.setattr(cl, "_which_chrome", lambda: None)
    monkeypatch.setattr(cl, "_WINDOWS_CHROME_PATHS", [])
    monkeypatch.setattr(cl, "_chrome_from_desktop_shortcut", lambda: None)
    monkeypatch.setattr(cl, "_fixed_drive_roots", lambda: ["D:\\"])
    dchrome = r"D:\chrome\chrome.exe"
    monkeypatch.setattr(cl.os.path, "isfile", lambda p: p == dchrome)
    # neutralize the App Paths registry branch (no HKCU/HKLM entry)
    import winreg
    def _boom(*a, **k):
        raise OSError()
    monkeypatch.setattr(winreg, "OpenKey", _boom)
    info = cl.find_chrome()
    assert info["found"] is True
    assert info["path"] == dchrome


def test_find_chrome_via_desktop_shortcut(monkeypatch):
    """A desktop Chrome shortcut pointing at a non-C: exe is found even when the
    fixed-drive scan would miss it (user tip 2026-09-07)."""
    import agent.mcp.server.chrome_launcher as cl
    if platform.system() != "Windows":
        return
    monkeypatch.setattr(cl, "_which_chrome", lambda: None)
    monkeypatch.setattr(cl, "_WINDOWS_CHROME_PATHS", [])
    monkeypatch.setattr(cl, "_scan_fixed_drives_for_chrome", lambda: None)
    monkeypatch.setattr(cl, "_chrome_from_desktop_shortcut", lambda: r"E:\Portable\chrome.exe")
    import winreg
    monkeypatch.setattr(winreg, "OpenKey", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    info = cl.find_chrome()
    assert info["found"] is True and info["path"] == r"E:\Portable\chrome.exe"


def test_resolve_user_data_dir_falls_back_off_c(monkeypatch):
    import cli.deploy.chrome_precheck as cp
    import shutil as _sh
    from collections import namedtuple
    Usage = namedtuple("Usage", "total used free")
    # C: nearly full, D: roomy.
    def fake_usage(path):
        if path.upper().startswith("C"):
            return Usage(0, 0, int(0.1 * 1024 ** 3))   # 0.1 GB free
        return Usage(0, 0, int(500 * 1024 ** 3))
    monkeypatch.setattr(_sh, "disk_usage", fake_usage)
    monkeypatch.setattr(cp.os.path, "isdir", lambda p: True)
    import agent.mcp.server.chrome_launcher as cl
    monkeypatch.setattr(cl, "_fixed_drive_roots", lambda: ["C:\\", "D:\\"])
    udd = cp.resolve_user_data_dir()
    assert udd.upper().startswith("D:")
    assert cp.chrome_debug_args(udd).count(udd) == 1


def test_resolve_user_data_dir_prefers_c_when_spacious(monkeypatch):
    import cli.deploy.chrome_precheck as cp
    import shutil as _sh
    from collections import namedtuple
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(_sh, "disk_usage", lambda p: Usage(0, 0, int(50 * 1024 ** 3)))
    monkeypatch.setattr(cp.os.path, "isdir", lambda p: True)
    assert cp.resolve_user_data_dir() == r"C:\chrome_data"
