"""
Unit tests for build_system/signing_manager.py.

Focuses on the pure-function helpers and the Ed25519 signing primitive.
These are the security-critical pieces:

  - `_is_system_dll` decides whether a Windows DLL should NOT be re-signed
    (Microsoft / vendor-signed binaries). Wrong classification either
    wastes time signing vendor DLLs (cosmetic) or signs a vendor DLL
    with our cert (corrupts signature chain → Win SmartScreen warning).

  - `_is_system_framework` is the macOS counterpart.

  - `sign_single_file_ed25519` is the OTA signing primitive. A bug here
    breaks every client-side signature verification. We exercise a
    round-trip: generate key, sign, verify with cryptography library.

The Azure / PFX paths need real subprocess invocations against real
binaries (nuget, signtool), so they are exercised only by the GHA
release pipeline, not unit tests.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

# signing_manager.py uses module-level `from cryptography...` imports
# inside functions. Make sure cryptography is available; pytest will
# skip the Ed25519 tests if not.
cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from build_system import signing_manager as sm  # noqa: E402


# ============================================================================
# _is_system_dll (module-level helper)
# ============================================================================


class TestIsSystemDll:
    @pytest.mark.parametrize(
        "filename",
        [
            "api-ms-win-core-file-l1-1-0.dll",
            "api-ms-win-crt-runtime-l1-1-0.dll",
            "ucrtbase.dll",
            "vcruntime140.dll",
            "vcruntime140_1.dll",
            "msvcp140.dll",
            "msvcp140_1.dll",
            "concrt140.dll",
            "vccorlib140.dll",
        ],
    )
    def test_system_dll_patterns_are_detected(self, filename, tmp_path):
        f = tmp_path / filename
        assert sm._is_system_dll(f) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "chrome.exe",
            "chrome.dll",
            "firefox.exe",
            "webkit.exe",
        ],
    )
    def test_third_party_apps_are_detected(self, filename, tmp_path):
        f = tmp_path / filename
        assert sm._is_system_dll(f) is True

    def test_third_party_dir_is_detected(self, tmp_path):
        # Path contains `third_party\\` (Windows style). The helper
        # does case-insensitive substring match on the full path.
        f = tmp_path / "third_party" / "foo" / "lib.dll"
        assert sm._is_system_dll(f) is True

    def test_ms_playwright_dir_is_detected(self, tmp_path):
        f = tmp_path / "ms-playwright" / "browser.dll"
        assert sm._is_system_dll(f) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "eCan.exe",
            "eCan.dll",
            "app.exe",
            "Qt6Core.dll",
            "libpython3.12.dll",
            "_internal.dll",
        ],
    )
    def test_app_binaries_are_not_flagged(self, filename, tmp_path):
        # These should be signed.
        f = tmp_path / filename
        assert sm._is_system_dll(f) is False


# ============================================================================
# _is_system_framework (macOS counterpart)
# ============================================================================


class TestIsSystemFramework:
    @pytest.mark.parametrize(
        "path",
        [
            "/System/Library/Frameworks/Foundation.framework/Versions/A/Foundation",
            "/Library/Frameworks/QtCore.framework/Versions/A/QtCore",
            "/Applications/MyApp.app/Contents/Frameworks/QtGui.framework/Versions/A/QtGui",
            "/Users/me/project/third_party/QtCore.framework",
            "/Users/me/project/ms-playwright/chromium.app",
        ],
    )
    def test_system_third_party_paths_are_detected(self, tmp_path, path):
        mgr = sm.SigningManager(project_root=tmp_path)
        assert mgr._is_system_framework(Path(path)) is True

    def test_qt_frameworks_are_detected(self, tmp_path):
        # Qt frameworks are signed by The Qt Company already; we must
        # not re-sign them.
        mgr = sm.SigningManager(project_root=tmp_path)
        f = tmp_path / "QtWebEngineCore.framework"
        assert mgr._is_system_framework(f) is True

    def test_third_party_apps_are_detected(self, tmp_path):
        mgr = sm.SigningManager(project_root=tmp_path)
        for n in ("chromium", "firefox", "webkit"):
            assert mgr._is_system_framework(tmp_path / n) is True

    def test_app_bundle_is_not_flagged(self, tmp_path):
        # The .app we built should be signed.
        mgr = sm.SigningManager(project_root=tmp_path)
        f = tmp_path / "eCan.app"
        assert mgr._is_system_framework(f) is False


# ============================================================================
# sign_single_file_ed25519: OTA signing primitive
# ============================================================================


@pytest.fixture
def ed25519_keypair(tmp_path):
    """Generate a fresh Ed25519 keypair on disk."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_path = tmp_path / "ed25519_private.pem"
    public_path = tmp_path / "ed25519_public.pem"

    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


class TestSignSingleFileEd25519:
    def test_writes_64_byte_signature(self, tmp_path, ed25519_keypair):
        priv, _ = ed25519_keypair
        target = tmp_path / "installer.deb"
        target.write_bytes(b"fake deb payload " * 100)

        assert sm.sign_single_file_ed25519(str(target), str(priv)) is True

        sig_path = target.with_suffix(target.suffix + ".sig")
        assert sig_path.exists()
        # Ed25519 signature is exactly 64 bytes (Sparkle protocol
        # requirement).
        assert sig_path.stat().st_size == 64

    def test_signature_verifies_with_public_key(self, tmp_path, ed25519_keypair):
        priv, pub = ed25519_keypair
        target = tmp_path / "installer.exe"
        payload = b"installer payload bytes"
        target.write_bytes(payload)

        assert sm.sign_single_file_ed25519(str(target), str(priv)) is True

        sig_path = target.with_suffix(target.suffix + ".sig")
        signature = sig_path.read_bytes()

        # Verify with the public key. This is what the OTA client does
        # at update time — if signature does not verify, client refuses
        # the update.
        public_key = serialization.load_pem_public_key(pub.read_bytes())
        public_key.verify(signature, payload)  # raises if invalid

    def test_signature_changes_when_payload_changes(self, tmp_path, ed25519_keypair):
        # Sanity check that we're signing actual content, not a fixed
        # blob — a regression that signs a constant would still
        # "verify" but allow replay attacks.
        priv, _ = ed25519_keypair

        f1 = tmp_path / "a.bin"; f1.write_bytes(b"first")
        f2 = tmp_path / "b.bin"; f2.write_bytes(b"second")

        sm.sign_single_file_ed25519(str(f1), str(priv))
        sm.sign_single_file_ed25519(str(f2), str(priv))

        sig1 = (f1.with_suffix(f1.suffix + ".sig")).read_bytes()
        sig2 = (f2.with_suffix(f2.suffix + ".sig")).read_bytes()

        assert sig1 != sig2

    def test_explicit_output_path(self, tmp_path, ed25519_keypair):
        priv, _ = ed25519_keypair
        target = tmp_path / "installer.pkg"
        target.write_bytes(b"pkg payload")
        custom_sig = tmp_path / "custom.sig"

        assert sm.sign_single_file_ed25519(
            str(target), str(priv), str(custom_sig)
        ) is True
        assert custom_sig.exists()
        assert custom_sig.stat().st_size == 64

    def test_missing_file_returns_false(self, tmp_path, ed25519_keypair):
        priv, _ = ed25519_keypair
        missing = tmp_path / "no_such_file.bin"

        assert sm.sign_single_file_ed25519(str(missing), str(priv)) is False

    def test_missing_key_returns_false(self, tmp_path):
        target = tmp_path / "installer.deb"
        target.write_bytes(b"payload")
        no_key = tmp_path / "no_key.pem"

        assert sm.sign_single_file_ed25519(str(target), str(no_key)) is False

    def test_wrong_key_algorithm_returns_false(self, tmp_path):
        # Write an RSA key where an Ed25519 key is expected.
        from cryptography.hazmat.primitives.asymmetric import rsa

        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rsa_path = tmp_path / "rsa.pem"
        rsa_path.write_bytes(
            rsa_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

        target = tmp_path / "installer.deb"
        target.write_bytes(b"payload")

        assert sm.sign_single_file_ed25519(str(target), str(rsa_path)) is False

    def test_large_file_signature_is_64_bytes(
        self, tmp_path, ed25519_keypair
    ):
        # Signing a large payload must still produce exactly 64 bytes
        # (Ed25519 is constant-size regardless of input). A regression
        # that hashes-then-signs could produce larger output.
        priv, _ = ed25519_keypair
        big = tmp_path / "big.bin"
        big.write_bytes(b"x" * (5 * 1024 * 1024))  # 5 MiB

        assert sm.sign_single_file_ed25519(str(big), str(priv)) is True
        sig = (big.with_suffix(big.suffix + ".sig")).read_bytes()
        assert len(sig) == 64


# ============================================================================
# Password resolution (env var ${VAR} form)
# ============================================================================


class TestResolvePassword:
    """Pin the ${ENV_VAR} -> os.getenv(ENV_VAR) -> default_password fallback chain."""

    def test_direct_password_returned_as_is(self, tmp_path, monkeypatch):
        mgr = sm.SigningManager(project_root=tmp_path)
        assert mgr._resolve_password("plain-pw", {}) == "plain-pw"

    def test_env_var_password_is_used(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_PW", "secret123")
        mgr = sm.SigningManager(project_root=tmp_path)
        assert mgr._resolve_password("${MY_PW}", {}) == "secret123"

    def test_env_var_missing_falls_back_to_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MISSING_PW", raising=False)
        cfg = {"default_password": "fallback"}
        mgr = sm.SigningManager(project_root=tmp_path)
        assert mgr._resolve_password("${MISSING_PW}", cfg) == "fallback"

    def test_empty_password_config_with_no_default_returns_empty(
        self, tmp_path, monkeypatch
    ):
        mgr = sm.SigningManager(project_root=tmp_path)
        assert mgr._resolve_password("", {}) == ""