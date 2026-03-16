import unittest
import os
import sys
import tempfile
import types
import logging
from pathlib import Path
from unittest.mock import patch


if "colorlog" not in sys.modules:
    colorlog_stub = types.ModuleType("colorlog")

    class ColoredFormatter(logging.Formatter):
        def __init__(self, *args, **kwargs):
            fmt = args[0] if args else kwargs.get("fmt", "%(message)s")
            super().__init__(fmt=fmt)

    colorlog_stub.ColoredFormatter = ColoredFormatter
    sys.modules["colorlog"] = colorlog_stub


class DummyManager:
    def __init__(self):
        self.app_home_path = os.getcwd()
        self.update_server_url = "http://127.0.0.1:8080"
        self.app_version = "1.0.0"


class DummyPM:
    def __init__(self):
        self.download_called = False
        self.verify_called = False
        self.install_called = False

    def download_package(self, *args, **kwargs):
        self.download_called = True
        return False

    def verify_package(self, *args, **kwargs):
        self.verify_called = True
        return False

    def install_package(self, *args, **kwargs):
        self.install_called = True
        return False


class TestGenericUpdaterPrecheck(unittest.TestCase):
    def test_rejects_installer_extensions_before_download(self):
        from ota.core.platforms import GenericUpdater
        mgr = DummyManager()
        gu = GenericUpdater(mgr)

        # Stub update info to .exe (also covers other installer types similarly)
        def stub_check(silent=False, return_info=False):
            info = {
                "latest_version": "1.2.3",
                "download_url": "https://example.com/app-1.2.3.exe",
                "file_size": 123,
                "signature": "",
                "description": "test"
            }
            return (True, info) if return_info else True

        gu.check_for_updates = stub_check  # type: ignore
        pm = DummyPM()
        ok = gu.install_update(package_manager=pm)
        self.assertFalse(ok)
        # Ensure we rejected before any package manager activity
        self.assertFalse(pm.download_called)
        self.assertFalse(pm.verify_called)
        self.assertFalse(pm.install_called)


class TestPackageManagerDevGating(unittest.TestCase):
    def test_installer_formats_return_false_when_dev_disabled(self):
        # Ensure dev mode is off for this test
        if "ECAN_DEV_MODE" in os.environ:
            del os.environ["ECAN_DEV_MODE"]
        from ota.core.package_manager import PackageManager

        pm = PackageManager()
        install_dir = tempfile.mkdtemp()
        # Choose suffix based on platform
        suffix = ".exe" if sys.platform.startswith("win") else ".dmg"
        fd, p = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            ok = pm._extract_and_install(Path(p), install_dir)
            self.assertFalse(ok)
        finally:
            try:
                os.remove(p)
            except Exception:
                pass


class TestWindowsOtaLauncherQuoting(unittest.TestCase):
    def test_windows_launcher_handles_users_path_safely(self):
        from ota.core.installer import InstallationManager

        with tempfile.TemporaryDirectory() as tmpdir:
            appdata_root = Path(tmpdir) / "appdata"
            appdata_root.mkdir(parents=True, exist_ok=True)

            template_text = (
                "@echo off\n"
                "setlocal\n"
                "timeout /t __DELAY_SECONDS__ /nobreak >nul\n"
                "echo [OTA] Launching installer: __INSTALLER_COMMAND__\n"
                "start \"\" __INSTALLER_COMMAND__\n"
            )

            writes = {}

            class DummyProcess:
                pid = 12345

            def fake_open(path, mode="r", encoding=None, newline=None):
                class _Writer:
                    def __enter__(self_inner):
                        return self_inner

                    def __exit__(self_inner, exc_type, exc, tb):
                        return False

                    def write(self_inner, content):
                        writes["path"] = str(path)
                        writes["encoding"] = encoding
                        writes["newline"] = newline
                        writes["content"] = content

                return _Writer()

            manager = InstallationManager()
            cmd = [
                r"C:\Users\26468\AppData\Local\eCan\ota_downloads\eCan-0.8.10.1-windows-amd64-Setup.exe",
                "/SILENT",
                '/DIR="C:\\Users\\26468\\AppData\\Local\\eCan"',
            ]

            with patch("ota.core.installer.sys.platform", "win32"), \
                 patch("config.app_info.app_info.appdata_path", str(appdata_root)), \
                 patch("ota.core.installer.Path.exists", return_value=True), \
                 patch("ota.core.installer.Path.read_text", return_value=template_text), \
                 patch("builtins.open", side_effect=fake_open), \
                 patch("ota.core.installer.subprocess.Popen", return_value=DummyProcess()):
                pid = manager._launch_windows_installer_delayed(cmd, delay_seconds=3)

            self.assertEqual(pid, 12345)
            self.assertEqual(writes["encoding"], "utf-8-sig")
            self.assertEqual(writes["newline"], "\r\n")
            self.assertIn(r'C:\Users\26468\AppData\Local\eCan\ota_downloads\eCan-0.8.10.1-windows-amd64-Setup.exe', writes["content"])
            self.assertIn('/DIR="C:\\Users\\26468\\AppData\\Local\\eCan"', writes["content"])
            self.assertIn('start ""', writes["content"])


if __name__ == "__main__":
    unittest.main()
