import unittest
import builtins
import tempfile
import os
from pathlib import Path
import importlib.util


class TestErrorsPermissionMapping(unittest.TestCase):
    def test_permission_error_mapping(self):
        from ota.core.errors import create_error_from_exception, UpdateErrorCode
        exc = builtins.PermissionError("no permission")
        err = create_error_from_exception(exc, context="unit-test")
        self.assertEqual(err.code, UpdateErrorCode.PERMISSION_DENIED)


@unittest.skipIf(importlib.util.find_spec('flask') is None, "Flask not available")
class TestSemverComparison(unittest.TestCase):
    def setUp(self):
        from ota.server.update_server import app
        self.client = app.test_client()

    def _check(self, version: str, expected_update_available: bool):
        resp = self.client.get(f"/api/check?version={version}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(bool(data.get("update_available")), expected_update_available, msg=f"version={version}")

    def test_versions(self):
        # latest_version is 1.1.0 in the demo server
        cases = [
            ("1.0.0", True),
            ("1.1.0", False),
            ("1.10.0", False),
            ("0.9", True),
            ("1.1", False),
            ("1.1.0+build1", False),
            ("1.1.0-alpha", False),
        ]
        for v, exp in cases:
            with self.subTest(version=v):
                self._check(v, exp)


class TestEd25519Signature(unittest.TestCase):
    @unittest.skipIf(importlib.util.find_spec('cryptography') is None, "cryptography not available")
    def test_ed25519_verify(self):
        # Import inside test to avoid hard dependency if cryptography is missing
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
        import base64

        from ota.core.package_manager import PackageManager

        # Prepare temp file content
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / "payload.bin"
            file_path.write_bytes(b"hello-ota-ed25519")

            # Generate ed25519 key pair
            private_key = ed25519.Ed25519PrivateKey.generate()
            public_key = private_key.public_key()

            # Write public key to PEM file
            pub_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            pub_path = Path(td) / "pub.pem"
            pub_path.write_bytes(pub_pem)

            # Sign file
            signature = private_key.sign(file_path.read_bytes())
            signature_b64 = base64.b64encode(signature).decode('ascii')

            pm = PackageManager()
            ok = pm._verify_digital_signature(file_path, signature_b64, str(pub_path))
            self.assertTrue(ok)

            # Tamper signature (negative test)
            bad_sig_b64 = base64.b64encode(signature[:-1] + b"\x00").decode('ascii')
            ok2 = pm._verify_digital_signature(file_path, bad_sig_b64, str(pub_path))
            self.assertFalse(ok2)


if __name__ == "__main__":
    unittest.main()
