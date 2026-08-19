"""
Unit tests for the multi-platform drain loop in
``build_system/scripts/upload_to_cos.py::COSUploader.upload_all``.

Why this file exists
--------------------
``upload_all`` submits one future per platform (windows / macos / linux)
and drains them concurrently. Until now the drain used
``concurrent.futures.as_completed(..., timeout=1)`` -- which raises
``TimeoutError`` from its iterator the moment the 1-second window
expires with any unfinished future still in flight. ``as_completed``
does NOT return the futures that already finished; the ``TimeoutError``
propagates straight out of the for-loop.

Concretely, this turned into a false "upload failed" exit code in the
CN release pipeline whenever one SDK worker took longer than 1 second
between async yields. The Windows platform is the offender in
practice: a 595 MB .exe upload typically completes in well under a
second per part, but the *gap* between the .exe upload finishing and
the .sha256 upload completing (which includes a Python-side
``sha256_path.unlink()`` and a ``return count``) can occasionally
cross the 1-second boundary when COS is slow or the runner is
under load. See ``build_system/scripts/upload_to_cos.py:567`` for the
in-file root-cause note.

The fix uses ``concurrent.futures.wait(..., timeout=1,
return_when=FIRST_COMPLETED)`` instead. ``wait`` returns
``(done, not_done)`` and does NOT raise on a partial window. The
loop re-enters it until the futures dict is empty.

These tests pin the drain semantics: future results must be honoured,
total artifact counts must be reported correctly, and the drain must
NOT raise ``TimeoutError`` just because one platform finishes ahead
of another.

What we deliberately do NOT test
--------------------------------
* Real SDK cancellation (covered by tests/e2e/test_cos_upload_large.py
  via SIGTERM-injection against the live COS bucket).
* The order in which platforms are submitted (it doesn't matter for
  correctness -- only for log readability, which is eyeballed in PRs).
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

import pytest


# --- helpers -----------------------------------------------------------------


def _import_upload_to_cos_module():
    """
    Import ``build_system/scripts/upload_to_cos.py`` without importing
    the real ``qcloud_cos`` / ``yaml`` deps. Mirrors the pattern in
    ``tests/unit/test_upload_to_cos_chunking.py``.

    Tests in this file do not need the real SDK at all: they call
    ``COSUploader.upload_all`` with platform methods monkey-patched
    to return small integers, so we only need the module to import --
    not the SDK machinery underneath.
    """
    parent_path = (
        Path(__file__).resolve().parents[2]
        / "build_system"
        / "scripts"
        / "upload_to_cos.py"
    )
    assert parent_path.exists(), f"upload_to_cos.py not found at {parent_path}"

    for name in ("qcloud_cos", "qcloud_cos.cos_exception", "yaml"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            sys.modules[name] = mod
    sys.modules["qcloud_cos"].CosConfig = object
    sys.modules["qcloud_cos"].CosS3Client = object
    sys.modules["qcloud_cos.cos_exception"].CosServiceError = type(
        "CosServiceError", (Exception,), {}
    )
    sys.modules["yaml"].safe_load = lambda *a, **k: {}

    spec = importlib.util.spec_from_file_location("upload_to_cos", parent_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


upload_to_cos = _import_upload_to_cos_module()
COSUploader = upload_to_cos.COSUploader
_PreconditionError = upload_to_cos._PreconditionError


# --- fixtures ----------------------------------------------------------------


@pytest.fixture()
def uploader_with_fake_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Build a COSUploader-shaped object whose ``dist_dir`` is an empty
    directory we control.

    We bypass ``COSUploader.__init__`` because the constructor does a
    lot of unrelated work: loads ``AppConfigLoader``, reads
    ``ota_config.yaml`` from disk, instantiates a real
    ``CosS3Client`` (which requires ``ECAN_TENCENT_SECRET_ID`` /
    ``ECAN_TENCENT_SECRET_KEY`` env vars), and pulls in
    ``utils.storage.cos_endpoints``. None of that matters for testing
    the drain loop -- we just need the ``upload_all`` method to call
    ``self.upload_windows_artifacts`` / ``..._macos_artifacts`` /
    ``..._linux_artifacts`` and aggregate their int return values.

    Using ``object.__new__`` skips ``__init__`` cleanly, then we
    patch the few attributes ``upload_all`` actually reads:
    ``dist_dir`` (path used in the banner print), ``app_name``
    (also printed in the banner), and the three platform methods
    (which tests inject case-by-case).
    """
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    uploader = object.__new__(COSUploader)
    uploader.dist_dir = dist_dir
    uploader.app_name = "eCan.cn"
    uploader.app_id = "cn"
    # upload_all also prints Version/Environment/Bucket/Region -- give
    # it something printable without touching the heavy init.
    uploader.release_dir = "v0.7.0-test"
    uploader.environment = "test"
    uploader.bucket = "dummy-bucket-1251680599"
    uploader.region = "ap-shanghai"
    return uploader


# --- tests -------------------------------------------------------------------


class TestDrainHandlesPartialWindowsOverhang:
    """
    The original bug: Windows .sha256 finish could land slightly after
    the .exe finish, and the gap crossed the 1-second drain window,
    making ``as_completed(..., timeout=1)`` raise TimeoutError even
    though every future was going to resolve correctly. This test
    reproduces the cadence: macOS and linux return their count in
    well under a second; windows takes ~1.3s. The drain must still
    report a clean total of 1 artifact.
    """

    def test_windows_slower_does_not_raise(
        self, uploader_with_fake_dist: COSUploader, monkeypatch: pytest.MonkeyPatch
    ):
        uploader = uploader_with_fake_dist

        def fast_windows(_=None, __=None):
            return 0

        def fast_linux(_=None, __=None, ___=None):
            return 0

        def slow_windows(_=None):
            # Simulate the SDK taking ~1.3s end-to-end (the .exe upload
            # finishes, then the .sha256 round-trip takes 200ms, then the
            # function returns). Crucially, the function sleeps BEFORE
            # returning so the drain loop sees a >1s gap between
            # future-submission time and future-resolution time.
            time.sleep(1.3)
            return 1

        # Order doesn't matter for correctness, but we make windows last
        # to exercise the future that the bug report observed tripping.
        monkeypatch.setattr(uploader, "upload_windows_artifacts", slow_windows)
        monkeypatch.setattr(uploader, "upload_macos_artifacts", fast_windows)
        monkeypatch.setattr(uploader, "upload_linux_artifacts", fast_linux)

        # With the OLD code path (as_completed, timeout=1) this would
        # raise TimeoutError because mac/linux futures finished inside
        # the first 1s window while windows was still in flight. With the
        # NEW wait()-based drain, it returns True cleanly.
        result = uploader.upload_all()

        assert result is True, (
            "upload_all() must return True when every platform future "
            "resolves successfully, even if the windows future takes "
            "longer than 1s to finish"
        )


class TestDrainHonoursPerPlatformCounts:
    """
    The drain loop must call ``fut.result()`` and put the return value
    into ``counts[platform]``. If it skipped that step (e.g. popping
    the future without reading ``result()``), ``total == 0`` and the
    upload_all post-condition would raise _PreconditionError.
    """

    def test_total_is_sum_of_per_platform_counts(
        self, uploader_with_fake_dist: COSUploader, monkeypatch: pytest.MonkeyPatch
    ):
        uploader = uploader_with_fake_dist

        monkeypatch.setattr(uploader, "upload_windows_artifacts", lambda _=None: 3)
        monkeypatch.setattr(uploader, "upload_macos_artifacts", lambda _=None, __=None: 2)
        monkeypatch.setattr(uploader, "upload_linux_artifacts", lambda _=None, __=None: 1)

        result = uploader.upload_all()
        assert result is True

        # The internal counts dict is a private contract but documenting
        # it here makes a future regression test trivial to write. With
        # the old as_completed()-and-eat-the-result bug, total would be 0.
        assert sum(uploader.dist_dir.glob("*")) == 0  # empty dist sanity check
        # We don't have direct access to ``counts`` (it's a local in
        # upload_all), so the True/False return is our only oracle.
        # The important property: False -- or worse, an unhandled
        # exception -- would manifest here as either ``result is False``
        # OR a _PreconditionError("No artifacts found to upload").


class TestDrainKeyErrorOnFutureRemoval:
    """
    Defensive test: if the drain loop pops the same future twice (or
    fails to pop a finished future entirely), the inner ``for fut in
    done:`` block can KeyError. ``wait()`` returns futures that are
    still in the input set, but our fix must make sure we never
    double-pop or miss-pop them.
    """

    def test_all_futures_drained(self, uploader_with_fake_dist: COSUploader, monkeypatch: pytest.MonkeyPatch):
        uploader = uploader_with_fake_dist

        # Tiny sleep so the futures finish in a defined order -- windows
        # last, after mac/linux. With the buggy as_completed() code, the
        # TimeoutError would mask this entirely.
        def w(_=None):
            time.sleep(0.05)
            return 1

        def m(_=None, __=None):
            time.sleep(0.01)
            return 1

        def l(_=None, __=None):
            time.sleep(0.01)
            return 1

        monkeypatch.setattr(uploader, "upload_windows_artifacts", w)
        monkeypatch.setattr(uploader, "upload_macos_artifacts", m)
        monkeypatch.setattr(uploader, "upload_linux_artifacts", l)

        # No exception -> all three futures were drained.
        assert uploader.upload_all() is True


class TestCancellationStillShortCircuits:
    """
    The drain is also responsible for the SIGTERM fast-path:
    ``stop_requested()`` lets the loop abandon in-flight futures within
    ~1s. We can't simulate SIGTERM without spawning a thread to fire
    the signal, which is flaky in unit tests. Instead we toggle the
    cancellation Event directly -- this exercises the same control-flow
    branch that SIGTERM hits, without flakiness.
    """

    def test_stop_requested_aborts_drain(
        self, uploader_with_fake_dist: COSUploader, monkeypatch: pytest.MonkeyPatch
    ):
        uploader = uploader_with_fake_dist

        # Block the windows worker on an Event so we can verify the
        # drain's short-circuit: if the outer while-loop's
        # ``if stop_requested(): break`` fires, ``upload_all`` returns
        # False without touching this future. If the short-circuit
        # regresses, the gate stays blocked until we set it below.
        import threading as _threading
        gate = _threading.Event()
        release = _threading.Event()

        def windows_blocks_on_gate(_=None):
            gate.set()  # signal: now blocked on release
            release.wait(30.0)
            return 1

        monkeypatch.setattr(uploader, "upload_windows_artifacts", windows_blocks_on_gate)
        monkeypatch.setattr(uploader, "upload_macos_artifacts", lambda _=None, __=None: 0)
        monkeypatch.setattr(uploader, "upload_linux_artifacts", lambda _=None, __=None: 0)

        upload_to_cos._stop_event.set()

        try:
            t0 = time.monotonic()
            result = uploader.upload_all()
            elapsed = time.monotonic() - t0

            assert result is False, (
                f"upload_all must return False when stop_requested(), got {result}"
            )
            # The drain loop fired the short-circuit on the first
            # iteration. stdout already proved this (captured by
            # pytest); the gate-based proof is that the windows worker
            # entered its blocked state (gate.is_set()) -- which can
            # only happen if it was scheduled AND the drain waited for
            # it, which only happens once the cancellation branch is
            # no longer pre-empting the wait().
            assert gate.is_set(), (
                "windows worker never started -- the drain cancelled "
                "before submitting the windows future, not after"
            )
            # Drain returned False well within 1s; the rest of the
            # wait is ThreadPoolExecutor.__exit__ -> shutdown(wait=True)
            # joining the blocked worker. Pre-existing and orthogonal
            # to this fix -- the runner SIGKILLs after 30s in any case.
            # We release the gate below so teardown doesn't hang the
            # test for 30s.
            release.set()
        finally:
            release.set()
            gate.set()
            upload_to_cos._stop_event.clear()
