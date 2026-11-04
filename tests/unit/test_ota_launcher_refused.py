"""When the launcher BAT may not run ([WinError 5], a customer 2026-11-02), the
installer is opened directly; if that is refused too, nothing claims success."""
from unittest import mock

from ota.core import installer as inst


def _mgr():
    return inst.InstallationManager.__new__(inst.InstallationManager)


def test_opens_the_installer_like_a_double_click():
    with mock.patch.object(inst.os, "startfile", create=True) as start:
        assert _mgr()._start_installer_directly(r"C:\dl\eCan.cn-Setup.exe", "C:\\Users\\a\\eCan.cn\\")
    path, verb, args = start.call_args[0]
    assert path.endswith("Setup.exe") and verb == "open"
    assert "/DIR=C:\\Users\\a\\eCan.cn" in args and "/SILENT" not in args


def test_refused_too_reports_false():
    with mock.patch.object(inst.os, "startfile", create=True, side_effect=PermissionError(5, "拒绝访问")):
        assert _mgr()._start_installer_directly(r"C:\dl\Setup.exe", r"C:\x") is False
