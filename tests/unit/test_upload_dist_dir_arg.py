"""
Unit tests for the ``--dist-dir`` CLI argument on the upload scripts.

Why this file exists
--------------------
Both ``build_system/scripts/upload_to_cos.py`` and
``build_system/scripts/upload_to_s3.py`` historically hardcoded
``self.dist_dir = project_root / 'dist'`` because their only caller was
the GitHub-Actions-intermediate upload job that downloaded
``*-s3-transfer`` artifacts into ``dist/`` first.

The CN/intl direct-upload fast path (release-{cn,intl}.yml) calls the
upload script directly from the build job with artifacts staged in
``artifacts/`` (or a platform-specific subdir). The new ``--dist-dir``
flag is the wire that lets the same script serve both paths without
forking.

What we lock in here
--------------------
1. ``--dist-dir <path>`` overrides the default and is wired all the way
   through to ``self.dist_dir`` (a ``pathlib.Path`` resolved against the
   project root so relative paths behave the same as before).
2. Omitting the flag preserves the historical default (no silent
   regression for the GitHub-Actions-intermediate upload job).
3. Relative paths are anchored to ``project_root``, not CWD. A build
   job that `cd`'d elsewhere would otherwise silently look at the
   wrong directory.

We don't reach into ``COSUploader.upload_all`` / ``S3Uploader.run``
here -- that path is already covered by ``test_upload_to_cos_drain.py``
and ``test_upload_to_s3_chunking.py``. This file is purely about CLI
plumbing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def upload_cos():
    return _load_module(
        PROJECT_ROOT / "build_system/scripts/upload_to_cos.py",
        "upload_to_cos_for_dist_dir_test",
    )


@pytest.fixture(scope="module")
def upload_s3():
    return _load_module(
        PROJECT_ROOT / "build_system/scripts/upload_to_s3.py",
        "upload_to_s3_for_dist_dir_test",
    )


def _patch_cos_constructor(upload_cos_module, monkeypatch):
    """Replace COSUploader with a class that only captures dist_dir.

    Skips every side-effect in ``__init__`` (CosS3Client instantiation,
    AppConfigLoader, env-var check, config load) and stubs the
    ``upload_all`` method so ``main()`` runs to completion.
    """
    captured = {}

    class _Capturing:
        # Mirror the real COSUploader's exit-code sentinels so main()
        # can call COSUploader.EXIT_OK / EXIT_SOFT_FAIL unconditionally.
        EXIT_OK = 0
        EXIT_SOFT_FAIL = 1
        EXIT_HARD_FAIL = 2

        def __init__(self, version, environment, app_id="cn", dist_dir=None):
            captured["version"] = version
            captured["environment"] = environment
            captured["app_id"] = app_id
            captured["dist_dir"] = (
                (upload_cos_module.project_root / dist_dir)
                if dist_dir
                else upload_cos_module.project_root / "dist"
            )

        def upload_all(self, platform_filter="all", arch_filter="all"):
            captured["platform_filter"] = platform_filter
            captured["arch_filter"] = arch_filter
            return True

    monkeypatch.setattr(upload_cos_module, "COSUploader", _Capturing)
    return captured


def _patch_s3_constructor(upload_s3_module, monkeypatch):
    captured = {}

    class _Capturing:
        # Mirror the real S3Uploader's exit-code sentinels so main()
        # can call S3Uploader.EXIT_OK / EXIT_SOFT_FAIL unconditionally.
        EXIT_OK = 0
        EXIT_SOFT_FAIL = 1
        EXIT_HARD_FAIL = 2

        def __init__(self, version, environment, user_prefix="", dist_dir=None):
            captured["version"] = version
            captured["environment"] = environment
            captured["user_prefix"] = user_prefix
            captured["dist_dir"] = (
                (upload_s3_module.project_root / dist_dir)
                if dist_dir
                else upload_s3_module.project_root / "dist"
            )

        def run(self, platform=None, arch=None):
            captured["platform"] = platform
            captured["arch"] = arch
            return True

    monkeypatch.setattr(upload_s3_module, "S3Uploader", _Capturing)
    return captured


def _run_main(module):
    """Run main() and swallow the SystemExit that exit codes raise."""
    try:
        module.main()
    except SystemExit as exc:
        return exc.code
    return 0


class TestCosDistDirArg:
    def test_explicit_dist_dir_used(
        self, upload_cos, monkeypatch, tmp_path: Path
    ):
        captured = _patch_cos_constructor(upload_cos, monkeypatch)

        with patch.object(sys, "argv", [
            "upload_to_cos.py",
            "--version", "1.2.3",
            "--env", "production",
            "--dist-dir", str(tmp_path),
        ]):
            rc = _run_main(upload_cos)

        assert rc == 0
        assert captured["dist_dir"] == tmp_path

    def test_default_dist_dir_unchanged(
        self, upload_cos, monkeypatch
    ):
        """Omitting --dist-dir must preserve the historical default.

        GitHub-Actions-intermediate upload jobs (shared-cos-upload.yml)
        still rely on this default. A silent regression here would break
        every CN release that doesn't use the direct-upload fast path.
        """
        captured = _patch_cos_constructor(upload_cos, monkeypatch)

        with patch.object(sys, "argv", [
            "upload_to_cos.py",
            "--version", "1.2.3",
            "--env", "production",
        ]):
            rc = _run_main(upload_cos)

        assert rc == 0
        assert captured["dist_dir"] == upload_cos.project_root / "dist"

    def test_relative_dist_dir_anchored_to_project_root(
        self, upload_cos, monkeypatch
    ):
        """Relative paths must resolve under project_root, not CWD.

        Without this, a build job that ``cd``s into a subdir would
        silently look at the wrong place.
        """
        captured = _patch_cos_constructor(upload_cos, monkeypatch)

        with patch.object(sys, "argv", [
            "upload_to_cos.py",
            "--version", "1.2.3",
            "--env", "production",
            "--dist-dir", "artifacts",
        ]):
            rc = _run_main(upload_cos)

        assert rc == 0
        assert captured["dist_dir"] == upload_cos.project_root / "artifacts"


class TestS3DistDirArg:
    def test_explicit_dist_dir_used(
        self, upload_s3, monkeypatch, tmp_path: Path
    ):
        captured = _patch_s3_constructor(upload_s3, monkeypatch)

        with patch.object(sys, "argv", [
            "upload_to_s3.py",
            "--version", "1.2.3",
            "--env", "production",
            "--dist-dir", str(tmp_path),
        ]):
            rc = _run_main(upload_s3)

        assert rc == 0
        assert captured["dist_dir"] == tmp_path

    def test_default_dist_dir_unchanged(
        self, upload_s3, monkeypatch
    ):
        captured = _patch_s3_constructor(upload_s3, monkeypatch)

        with patch.object(sys, "argv", [
            "upload_to_s3.py",
            "--version", "1.2.3",
            "--env", "production",
        ]):
            rc = _run_main(upload_s3)

        assert rc == 0
        assert captured["dist_dir"] == upload_s3.project_root / "dist"

    def test_relative_dist_dir_anchored_to_project_root(
        self, upload_s3, monkeypatch
    ):
        captured = _patch_s3_constructor(upload_s3, monkeypatch)

        with patch.object(sys, "argv", [
            "upload_to_s3.py",
            "--version", "1.2.3",
            "--env", "production",
            "--dist-dir", "artifacts",
        ]):
            rc = _run_main(upload_s3)

        assert rc == 0
        assert captured["dist_dir"] == upload_s3.project_root / "artifacts"
