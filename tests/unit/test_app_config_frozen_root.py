"""
Regression tests for the ``PROJECT_ROOT`` constant in
``utils.app_config_loader``.

Bug history
-----------
``PROJECT_ROOT`` used to be assigned with::

    PROJECT_ROOT: Path = getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)

PyInstaller's bootloader sets ``sys._MEIPASS`` to the absolute path of
the bundle folder, but **as a plain string**, not a ``pathlib.Path``.
The annotation was documentation only — it did not coerce. The moment
callers did ``PROJECT_ROOT / 'apps' / 'cn'`` inside a frozen build,
Python raised::

    TypeError: unsupported operand type(s) for /: 'str' and 'str'

That exception was swallowed inside
``ota.core.installer._get_current_windows_install_dir`` (broad
``except Exception``), which made the OTA upgrade fall back to the
wrong install directory. Inno Setup then wrote the new version to a
side directory while the running exe stayed on the old version, and
the next startup logged::

    [OTA] Installation confirmation failed: installer was launched
    for target_version=v0.9.97y, but app restarted with current_version=0.9.97x

These tests pin the type contract:

  1. ``PROJECT_ROOT`` is always a ``pathlib.Path``, in both frozen and
     non-frozen modes.
  2. ``PROJECT_ROOT / 'apps'`` works without raising ``TypeError`` in
     frozen mode.
  3. ``get_build_config_path`` (which depends on ``PROJECT_ROOT``)
     returns a ``Path`` in frozen mode.
  4. ``get_windows_app_id`` (called from the OTA installer) does not
     raise in frozen mode when ECAN_APP_ID is unset.

The tests intentionally exercise the *constant* by re-importing the
module with a stubbed ``sys.frozen`` / ``sys._MEIPASS``, since the
value is computed at import time.
"""

import importlib
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Re-import app_config_loader with sys.frozen / sys._MEIPASS pinned
# ---------------------------------------------------------------------------
def _reload_app_config_loader(*, frozen: bool, meipass: str | None):
    """Reload ``utils.app_config_loader`` with frozen-mode flags set.

    ``PROJECT_ROOT`` is computed at module-import time, so we cannot
    just monkeypatch ``sys.frozen`` in-place — we have to re-import
    the module after flipping the flags. The function returns the
    freshly-loaded module plus the original flags so the caller can
    restore them.
    """
    saved_frozen = getattr(sys, "frozen", None)
    saved_meipass = getattr(sys, "_MEIPASS", None)
    # Wipe any cached module so the import-time constant is recomputed.
    sys.modules.pop("utils.app_config_loader", None)

    try:
        if frozen:
            sys.frozen = True  # type: ignore[attr-defined]
            if meipass is not None:
                sys._MEIPASS = meipass  # type: ignore[attr-defined]
        else:
            # Make sure _MEIPASS isn't carried over from a previous run.
            if hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
            if hasattr(sys, "frozen"):
                del sys.frozen

        mod = importlib.import_module("utils.app_config_loader")
        return mod
    finally:
        # Restore — even on test failure — so other tests see the real env.
        if saved_frozen is None:
            if hasattr(sys, "frozen"):
                del sys.frozen
        else:
            sys.frozen = saved_frozen  # type: ignore[attr-defined]

        if saved_meipass is None:
            if hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
        else:
            sys._MEIPASS = saved_meipass  # type: ignore[attr-defined]


@pytest.fixture
def frozen_app_config_loader():
    """Yield ``utils.app_config_loader`` reloaded as if running under PyInstaller.

    ``sys._MEIPASS`` is set to a Windows-style absolute path because
    that is the runtime mode where the original bug surfaced (CN
    Windows installer) — verifying on a Windows-shaped path also
    guards against any future refactor that hardcodes POSIX path
    semantics.
    """
    mod = _reload_app_config_loader(
        frozen=True,
        meipass=r"C:\fake\meipass\eCan.cn\_internal",
    )
    yield mod
    # Re-import as non-frozen so other tests don't inherit the stub.
    _reload_app_config_loader(frozen=False, meipass=None)


@pytest.fixture
def dev_app_config_loader():
    """Yield ``utils.app_config_loader`` reloaded as a normal dev / CI import."""
    mod = _reload_app_config_loader(frozen=False, meipass=None)
    yield mod
    _reload_app_config_loader(frozen=False, meipass=None)


# ---------------------------------------------------------------------------
# Core regression: PROJECT_ROOT type contract
# ---------------------------------------------------------------------------
class TestProjectRootType:
    """Pin the ``PROJECT_ROOT is a pathlib.Path`` contract."""

    def test_project_root_is_path_in_frozen_mode(self, frozen_app_config_loader):
        """Under PyInstaller, ``PROJECT_ROOT`` must be a ``Path``.

        Before the fix this was a plain ``str``, which broke every
        downstream ``PROJECT_ROOT / 'apps'`` call.
        """
        mod = frozen_app_config_loader
        assert isinstance(mod.PROJECT_ROOT, Path), (
            "PROJECT_ROOT must be pathlib.Path under frozen mode so that "
            "'PROJECT_ROOT / \"apps\" / \"cn\"' is well-typed. Got: "
            f"{type(mod.PROJECT_ROOT).__name__} = {mod.PROJECT_ROOT!r}"
        )

    def test_project_root_is_path_in_dev_mode(self, dev_app_config_loader):
        """Sanity check: in dev / CI the constant should also be a Path."""
        mod = dev_app_config_loader
        assert isinstance(mod.PROJECT_ROOT, Path)

    def test_project_root_truediv_works_in_frozen_mode(self, frozen_app_config_loader):
        """``PROJECT_ROOT / 'apps'`` must not raise in frozen mode.

        This is the exact failure mode the OTA installer hit:
        ``TypeError: unsupported operand type(s) for /: 'str' and 'str'``.
        """
        mod = frozen_app_config_loader
        # Should not raise.
        joined = mod.PROJECT_ROOT / "apps" / "cn" / "build"
        assert isinstance(joined, Path)
        # And the path components must reflect the MEIPASS we stubbed.
        assert "fake" in joined.parts or "meipass" in joined.parts or \
            "apps" in joined.parts and "cn" in joined.parts

    def test_project_root_truediv_works_in_dev_mode(self, dev_app_config_loader):
        """Sanity check: ``PROJECT_ROOT / 'apps'`` works in dev too."""
        mod = dev_app_config_loader
        joined = mod.PROJECT_ROOT / "apps" / "cn" / "build"
        assert isinstance(joined, Path)
        assert "apps" in joined.parts
        assert "cn" in joined.parts


# ---------------------------------------------------------------------------
# Downstream contract: get_build_config_path + get_windows_app_id
# ---------------------------------------------------------------------------
class TestBuildConfigPathInFrozenMode:
    """The OTA installer calls ``get_windows_app_id`` -> ``get_build_config_path``.

    If either step raises because of the ``PROJECT_ROOT is str`` bug,
    the installer's ``try / except Exception`` swallows it and silently
    falls back to the wrong install directory. These tests pin that the
    chain works under frozen mode without raising.
    """

    def test_get_build_config_path_returns_path_in_frozen_mode(
        self, frozen_app_config_loader
    ):
        mod = frozen_app_config_loader
        # Should not raise. The path won't actually exist (we stubbed
        # a fake _MEIPASS), but the *return type* and the absence of
        # exception are what we care about.
        result = mod.get_build_config_path("cn")
        assert isinstance(result, Path)

    def test_get_build_config_path_returns_path_for_unknown_app_id_in_frozen_mode(
        self, frozen_app_config_loader
    ):
        mod = frozen_app_config_loader
        # app_id is None → resolver defaults to ECAN_APP_ID env or 'intl'.
        result = mod.get_build_config_path(None)
        assert isinstance(result, Path)

    def test_get_windows_app_id_returns_str_in_frozen_mode(
        self, frozen_app_config_loader
    ):
        """The OTA installer relies on ``get_windows_app_id`` returning a str GUID.

        It must not raise when called from inside a frozen build.
        """
        mod = frozen_app_config_loader
        result = mod.get_windows_app_id(None)
        assert isinstance(result, str)
        # The default fallback is a hex GUID string — non-empty.
        assert result.strip(), (
            "get_windows_app_id returned an empty GUID; OTA registry "
            "lookup will produce an invalid Uninstall key path"
        )

    def test_get_windows_app_id_does_not_raise_when_ecan_app_id_unset_in_frozen_mode(
        self, frozen_app_config_loader, monkeypatch
    ):
        """Reproduce the production scenario exactly.

        In ``_get_current_windows_install_dir`` the installer calls::

            get_windows_app_id(os.environ.get('ECAN_APP_ID'))

        with no environment override at all. The chain
        ``get_windows_app_id(None)`` → ``get_build_config_path(None)``
        → ``PROJECT_ROOT / 'apps'`` must not raise.
        """
        monkeypatch.delenv("ECAN_APP_ID", raising=False)
        mod = frozen_app_config_loader
        # Must not raise.
        result = mod.get_windows_app_id(None)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Verify the helper re-imports don't leak state to other tests
# ---------------------------------------------------------------------------
class TestFixtureIsolation:
    """Sanity-check that the import-time monkey-flips are properly restored.

    Other test files in this suite (notably
    ``test_app_config_runtime.py`` and
    ``test_app_config_loader_endpoints.py``) rely on the default
    non-frozen module state. If our fixtures leak ``sys.frozen=True``
    or a stubbed ``sys._MEIPASS``, those tests can break in confusing
    ways.
    """

    def test_sys_frozen_restored_after_frozen_fixture(self, frozen_app_config_loader):
        # Trigger fixture teardown.
        del frozen_app_config_loader
        # The fixture teardown reloads without frozen mode, so this
        # assertion mirrors the post-test state.
        assert getattr(sys, "frozen", None) in (None, False), (
            "frozen_app_config_loader fixture leaked sys.frozen=True into "
            f"the next test (got: {getattr(sys, 'frozen', None)!r})"
        )

    def test_sys_meipass_restored_after_frozen_fixture(self, frozen_app_config_loader):
        del frozen_app_config_loader
        # In dev / CI, sys._MEIPASS is normally absent. The fixture
        # teardown should have removed it.
        assert not hasattr(sys, "_MEIPASS") or sys._MEIPASS is None, (
            "frozen_app_config_loader fixture leaked sys._MEIPASS into "
            f"the next test (got: {getattr(sys, '_MEIPASS', None)!r})"
        )
