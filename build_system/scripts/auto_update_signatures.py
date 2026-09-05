#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automatic Signature Update Script — DEPRECATED.

.. deprecated::
    This script is NOT part of the production OTA pipeline. The release
    workflows (``shared-{cos,s3}-appcast-generation.yml`` and the in-job
    OTA signing in ``build_system/signing_manager.py``) compute Ed25519
    signatures and upload ``.sig`` files directly alongside each artifact.
    The ``signatures_{version}.json`` written here is never read by the
    production appcast generator (``build_system/scripts/generate_appcast.py``),
    never uploaded, and never consulted by the client.

    Kept as a no-op shim so any stray developer invocation does not write
    misleading files. Remove this file entirely once we are confident no
    external automation references it.

    Replacement (if you need to recompute signatures outside CI):
        python -c "from build_system.signing_manager import create_ota_signing_manager; \
                   create_ota_signing_manager().sign_for_ota('<version>')"
"""

import sys
import warnings
from pathlib import Path

_DEPRECATION_MSG = (
    "build_system/scripts/auto_update_signatures.py is deprecated and will be removed. "
    "The production OTA pipeline writes per-artifact .sig files via "
    "build_system/signing_manager.py::OTASigningManager.sign_for_ota(); no JSON "
    "sidecar is produced or consumed. Use sign_for_ota() instead."
)

# `hashlib` is kept imported because historical callers may import
# `calculate_sha256` from this module. The deprecation shim does not invoke it,
# but removing the import would break callers we have not yet audited.
import hashlib  # noqa: F401  -- retained for backward compatibility


def calculate_sha256(file_path):
    """Deprecated. Retained for callers that imported it before this script
    was marked deprecated. Prefer ``build_system/signing_manager.py``."""
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def auto_update_signatures(dist_dir=None, version=None):
    """
    DEPRECATED no-op. Returns ``False`` and emits a deprecation warning.

    The historical behaviour (SHA-256 + dev appcast regeneration + JSON
    sidecar) has been fully replaced by Ed25519 signing in
    :class:`build_system.signing_manager.OTASigningManager`. The
    ``.sig`` files produced there are the single source of truth for OTA
    signatures.
    """
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    print(f"[DEPRECATED] {_DEPRECATION_MSG}")
    print(f"[DEPRECATED] Refusing to write {Path(__file__).parent / 'signatures_<version>.json'}.")
    print("[DEPRECATED] No-op return; use build_system/signing_manager.py::OTASigningManager.sign_for_ota() instead.")
    return False

    # ─── Deprecated body below, unreachable ────────────────────────────────
    # The code in this block was the historical implementation. It is kept
    # only so this module continues to parse and so anyone diffing the file
    # can still see what it used to do. Do NOT call into it; the function
    # returns False above before reaching any of these statements.
    if False:  # pragma: no cover -- deprecated
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent

        if dist_dir is None:
            dist_dir = project_root / "dist"
        else:
            dist_dir = Path(dist_dir)

        if version is None:
            version_file = project_root / "VERSION"
            if version_file.exists():
                version = version_file.read_text().strip()
            else:
                print("[ERROR] VERSION file not found, please specify version")
                return False

        print("=" * 60)
        print("[INFO] Automatic Signature Update")
        print("=" * 60)
        print(f"[INFO] Version: {version}")
        print(f"[INFO] Distribution directory: {dist_dir}")
        print(f"[INFO] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        if not dist_dir.exists():
            print(f"[ERROR] Distribution directory not found: {dist_dir}")
            return False

        sig_file = script_dir / f"signatures_{version}.json"
        print(f"[INFO] Signature file: {sig_file}")
        print()

        patterns = [
            "eCan-*-macos-*.pkg",
            "eCan-*-macos-*.dmg",
            "eCan-*-windows-*-Setup.exe",
            "eCan-*-windows-*.msi",
            "eCan-*-linux-*.tar.gz",
            "eCan-*-linux-*.AppImage",
        ]

        signatures = {}
        updated_count = 0

        for pattern in patterns:
            for pkg_file in dist_dir.glob(pattern):
                print(f"[INFO] Processing: {pkg_file.name}")

                file_size = pkg_file.stat().st_size
                size_mb = file_size / (1024 * 1024)
                size_gb = file_size / (1024 * 1024 * 1024)

                if size_gb >= 1:
                    size_str = f"{size_gb:.2f} GB"
                else:
                    size_str = f"{size_mb:.2f} MB"

                print(f"   [INFO] Size: {file_size:,} bytes ({size_str})")

                print(f"   [INFO] Calculating SHA256...")
                signature = calculate_sha256(pkg_file)
                print(f"   [OK] SHA256: {signature}")

                signatures[pkg_file.name] = {
                    "file_size": file_size,
                    "signature": signature,
                }
                updated_count += 1
                print()

        if updated_count == 0:
            print("[WARN] No package files found in dist directory")
            print(f"   Please ensure packages are built and placed in: {dist_dir}")
            print()
            print("   Expected file patterns:")
            for pattern in patterns:
                print(f"   • {pattern}")
            return False

        with open(sig_file, 'w') as f:
            json.dump(signatures, f, indent=4)

        print("=" * 60)
        print(f"[OK] Updated {updated_count} package signature(s)")
        print(f"[INFO] Saved to: {sig_file}")
        print("=" * 60)
        print()

        print("[INFO] Summary:")
        print()
        for pkg_name, info in signatures.items():
            size_mb = info['file_size'] / (1024 * 1024)
            size_gb = info['file_size'] / (1024 * 1024 * 1024)

            if size_gb >= 1:
                size_str = f"{size_gb:.2f} GB"
            else:
                size_str = f"{size_mb:.2f} MB"

            print(f"   [INFO] {pkg_name}")
            print(f"      Size: {info['file_size']:,} bytes ({size_str})")
            print(f"      SHA256: {info['signature']}")
            print()

        return True


def generate_appcast(version=None, base_url="http://localhost:8000"):
    """
    DEPRECATED dev appcast regenerator. Production appcasts are produced
    by ``build_system/scripts/generate_appcast.py`` invoked from the
    release workflows. This entry point only existed for the historical
    localhost developer server and is retained as a no-op shim.
    """
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    print(f"[DEPRECATED] {_DEPRECATION_MSG}")
    return False

    # ─── Deprecated body below, unreachable ────────────────────────────────
    if False:  # pragma: no cover -- deprecated
        try:
            from ota.server.appcast_generator import AppcastGenerator

            script_dir = Path(__file__).parent
            project_root = script_dir.parent.parent

            if version is None:
                version_file = project_root / "VERSION"
                if version_file.exists():
                    version = version_file.read_text().strip()
                else:
                    print("[ERROR] VERSION file not found")
                    return False

            print("=" * 60)
            print("[INFO] Generating Appcast")
            print("=" * 60)
            print(f"[INFO] Version: {version}")
            print(f"[INFO] Base URL: {base_url}")
            print()

            generator = AppcastGenerator(
                server_root=str(script_dir),
                signatures_dir=str(script_dir),
            )

            success = generator.generate_appcast(version, base_url)

            if success:
                print("[OK] Appcast generated successfully")
                print(f"[INFO] Location: {script_dir / 'appcast.xml'}")
            else:
                print("[ERROR] Failed to generate appcast")

            print("=" * 60)
            print()

            return success

        except Exception as e:
            print(f"[ERROR] Error generating appcast: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Deprecated CLI entry point. Prints a deprecation banner and exits."""
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    print(f"[DEPRECATED] {_DEPRECATION_MSG}")
    sys.exit(1)


if __name__ == "__main__":
    main()
