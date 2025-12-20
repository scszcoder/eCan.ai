import unittest
import os
import tempfile
from pathlib import Path
import hashlib
import json
import importlib.util
from unittest import mock


class TestHashSignatureVerification(unittest.TestCase):
    def test_sha256_signature_positive_negative(self):
        from ota.core.package_manager import PackageManager, UpdatePackage
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / 'file.zip'
            # create a real zip file
            with zipfile.ZipFile(fp, 'w') as z:
                z.writestr('a.txt', 'hello-hash')
            # compute sha256 of the zip bytes
            h = hashlib.sha256(fp.read_bytes()).hexdigest()
            pkg = UpdatePackage('1.0.0', 'http://example.com/file.zip', 0, h)
            pkg.download_path = fp
            pkg.is_downloaded = True
            pm = PackageManager()
            self.assertTrue(pm.verify_package(pkg))
            # negative
            pkg2 = UpdatePackage('1.0.0', 'http://example.com/file.zip', 0, '0'*64)
            pkg2.download_path = fp
            pkg2.is_downloaded = True
            self.assertFalse(pm.verify_package(pkg2))


class TestPackageFormatAndScan(unittest.TestCase):
    def test_zip_with_dangerous_path(self):
        from ota.core.package_manager import PackageManager
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            zp = Path(td) / 'bad.zip'
            with zipfile.ZipFile(zp, 'w') as z:
                z.writestr('../evil.txt', 'bad')
            pm = PackageManager()
            self.assertFalse(pm._verify_package_format(zp))

    def test_disallowed_extension_and_size(self):
        from ota.core.package_manager import PackageManager
        from types import SimpleNamespace
        pm = PackageManager()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x.bin'
            p.write_bytes(b'0')
            # disallowed extension
            self.assertFalse(pm._basic_malware_scan(p))
            # large size
            with mock.patch('pathlib.Path.stat', return_value=SimpleNamespace(st_size=600*1024*1024)):
                p2 = Path(td) / 'x.zip'
                p2.write_bytes(b'0')
                self.assertFalse(pm._basic_malware_scan(p2))


@unittest.skipIf(importlib.util.find_spec('requests') is None, 'requests not available')
class TestGenericUpdaterNetwork(unittest.TestCase):
    def setUp(self):
        # Ensure not in dev mode for HTTPS requirement test
        if 'ECAN_DEV_MODE' in os.environ:
            del os.environ['ECAN_DEV_MODE']
        from ota.core.config import ota_config
        # point to insecure server to trigger HTTPS check
        ota_config.set('update_server', 'http://insecure.example.com')

    def test_https_required_in_prod(self):
        from ota.core.platforms import GenericUpdater
        from ota.core.updater import OTAUpdater
        from ota.core.errors import NetworkError
        u = OTAUpdater()
        u.platform_updater = GenericUpdater(u)
        with self.assertRaises(NetworkError):
            u.platform_updater.check_for_updates(silent=True, return_info=True)

    @mock.patch('requests.get')
    def test_200_update_available(self, mget):
        from ota.core.platforms import GenericUpdater
        from ota.core.updater import OTAUpdater
        from ota.core.config import ota_config
        # allow http in dev
        os.environ['ECAN_DEV_MODE'] = '1'
        ota_config.set('dev_update_server', 'http://localhost')
        u = OTAUpdater()
        u.platform_updater = GenericUpdater(u)
        class R:
            status_code = 200
            def json(self):
                return {
                    'update_available': True,
                    'latest_version': '1.2.3',
                    'download_url': 'http://localhost/file.zip',
                    'file_size': 1,
                    'signature': ''
                }
        mget.return_value = R()
        has, info = u.platform_updater.check_for_updates(silent=True, return_info=True)
        self.assertTrue(has)
        self.assertIsInstance(info, dict)
        self.assertEqual(info.get('latest_version'), '1.2.3')

    @mock.patch('requests.get')
    def test_404_no_update(self, mget):
        from ota.core.platforms import GenericUpdater
        from ota.core.updater import OTAUpdater
        os.environ['ECAN_DEV_MODE'] = '1'
        u = OTAUpdater()
        u.platform_updater = GenericUpdater(u)
        class R:
            status_code = 404
            text = ''
            def json(self):
                return {}
        mget.return_value = R()
        has, info = u.platform_updater.check_for_updates(silent=True, return_info=True)
        self.assertFalse(has)
        self.assertIsNone(info)


class TestUpdaterDevModeForcing(unittest.TestCase):
    def test_dev_mode_forces_generic(self):
        os.environ['ECAN_DEV_MODE'] = '1'
        from ota.core.updater import OTAUpdater
        from ota.core.platforms import GenericUpdater
        u = OTAUpdater()
        self.assertIsInstance(u.platform_updater, GenericUpdater)


if __name__ == '__main__':
    unittest.main()
