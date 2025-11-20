import unittest
import os
import sys
import tempfile
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
