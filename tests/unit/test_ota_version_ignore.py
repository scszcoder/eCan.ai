"""
Unit tests for ``ota.core.version_ignore``.

Pins two safety properties that mirror the install_state guarantees
(see ``tests/unit/test_ota_path_safety.py``):

  * ``_save`` writes atomically so a power-loss mid-write can't
    corrupt the user's ignore list.
  * ``_load`` quarantines a corrupt JSON file so subsequent startups
    don't keep failing with the same JSON error.

Both are exercised without touching the real ``<appdata>/ota_ignored_versions.json``
file by monkeypatching ``app_info`` / config dir.
"""

import json
import os
import platform
import stat
import sys
import threading
from pathlib import Path

import pytest


def _import_version_ignore():
    """Import ``ota.core.version_ignore`` with PySide6 stubbed if needed."""
    try:
        import ota.core.version_ignore  # noqa: F401
        return __import__("ota.core.version_ignore", fromlist=["*"])
    except ImportError:
        # Same PySide6 stub as test_ota_path_safety.
        import types
        pyside6 = types.ModuleType("PySide6")
        qtcore = types.ModuleType("PySide6.QtCore")
        qtgui = types.ModuleType("PySide6.QtGui")
        qtwidgets = types.ModuleType("PySide6.QtWidgets")

        class _Stub:
            def __init__(self, *a, **kw):
                pass

            def __getattr__(self, name):
                return _Stub()

            def __call__(self, *a, **kw):
                return _Stub()

        for mod, names in [
            (qtcore, ["QObject", "Signal", "Qt", "QThread", "QTimer"]),
            (qtgui, ["QFont", "QIcon", "QPixmap"]),
            (qtwidgets, ["QDialog", "QMessageBox", "QProgressBar", "QCheckBox",
                         "QGridLayout", "QGroupBox", "QHBoxLayout", "QApplication",
                         "QPushButton", "QSpacerItem", "QSizePolicy", "QTextEdit",
                         "QVBoxLayout", "QLabel", "QFrame"]),
        ]:
            for n in names:
                setattr(mod, n, _Stub)

        pyside6.QtCore = qtcore
        pyside6.QtGui = qtgui
        pyside6.QtWidgets = qtwidgets
        sys.modules["PySide6"] = pyside6
        sys.modules["PySide6.QtCore"] = qtcore
        sys.modules["PySide6.QtGui"] = qtgui
        sys.modules["PySide6.QtWidgets"] = qtwidgets

        return __import__("ota.core.version_ignore", fromlist=["*"])


@pytest.fixture(scope="module")
def vi_module():
    return _import_version_ignore()


class TestVersionIgnoreAtomicSave:
    """``_save`` must write atomically so partial writes can't lose the ignore list."""

    @pytest.fixture
    def tmp_config(self, tmp_path, monkeypatch):
        """Pin the config dir to ``tmp_path`` so we don't touch the real file."""
        from config.envi import getECBotDataHome  # type: ignore
        monkeypatch.setattr(
            "config.envi.getECBotDataHome", lambda: str(tmp_path)
        )
        # Also drop the cached singleton so a fresh instance reads/writes
        # under tmp_path.
        vi = _import_version_ignore()
        vi._version_ignore_manager = None
        return tmp_path

    def test_save_creates_file_atomically(self, vi_module, tmp_config):
        mgr = vi_module.VersionIgnoreManager(config_dir=str(tmp_config))
        mgr.ignore_version("1.2.3")
        # File must exist after save.
        config_file = tmp_config / "ota_ignored_versions.json"
        assert config_file.is_file()
        # Partial file MUST be cleaned up after rename.
        partial = tmp_config / f".{config_file.name}.partial"
        assert not partial.exists(), (
            f"Atomic save left a .partial ghost at {partial}"
        )
        # File contents are valid JSON.
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert "1.2.3" in data["ignored_versions"]

    def test_save_overwrites_existing_file(self, vi_module, tmp_config):
        mgr = vi_module.VersionIgnoreManager(config_dir=str(tmp_config))
        mgr.ignore_version("1.0.0")
        mgr.ignore_version("2.0.0")
        mgr.unignore_version("1.0.0")

        config_file = tmp_config / "ota_ignored_versions.json"
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert "2.0.0" in data["ignored_versions"]
        assert "1.0.0" not in data["ignored_versions"]

    def test_save_uses_temp_file_then_rename(self, vi_module, tmp_config):
        """The save path MUST write to ``.partial`` then atomic-rename."""
        mgr = vi_module.VersionIgnoreManager(config_dir=str(tmp_config))

        # Patch _atomic_write_text to verify it's called (not raw write).
        calls = []
        real = vi_module._atomic_write_text

        def spy(path, content, encoding="utf-8"):
            calls.append((Path(path), content))
            return real(path, content, encoding)

        vi_module._atomic_write_text = spy
        try:
            mgr.ignore_version("9.9.9")
        finally:
            vi_module._atomic_write_text = real

        assert calls, "VersionIgnoreManager._save did not use atomic_write_text"
        # The destination must be the canonical config file, not a sibling.
        path_arg = calls[0][0]
        assert path_arg.name == "ota_ignored_versions.json"


class TestVersionIgnoreCorruptQuarantine:
    """``_load`` must move a corrupt JSON file out of the way so subsequent
    startups start with a clean ignore list rather than failing forever."""

    @pytest.fixture
    def tmp_config(self, tmp_path, monkeypatch):
        from config.envi import getECBotDataHome  # type: ignore
        monkeypatch.setattr(
            "config.envi.getECBotDataHome", lambda: str(tmp_path)
        )
        vi = _import_version_ignore()
        vi._version_ignore_manager = None
        return tmp_path

    def test_corrupt_file_is_quarantined(self, vi_module, tmp_config):
        config_file = tmp_config / "ota_ignored_versions.json"
        config_file.write_text("{not valid json", encoding="utf-8")

        # Loading a corrupt file MUST NOT raise — and MUST quarantine it.
        mgr = vi_module.VersionIgnoreManager(config_dir=str(tmp_config))
        assert mgr.ignored_versions == set(), (
            "Corrupt file should yield an empty ignore list, "
            "not propagate the parse error"
        )
        # The active slot must be empty (or quarantined).
        assert not config_file.exists() or any(
            p.name.startswith(".ota_ignored_versions.json.corrupt-")
            for p in config_file.parent.iterdir()
        ), (
            "Corrupt file was NOT moved out of the active slot. "
            "Next startup would re-read it and crash again."
        )

    def test_valid_file_loads_cleanly(self, vi_module, tmp_config):
        config_file = tmp_config / "ota_ignored_versions.json"
        config_file.write_text(
            json.dumps({"ignored_versions": ["1.0.0", "2.0.0"]}),
            encoding="utf-8",
        )

        mgr = vi_module.VersionIgnoreManager(config_dir=str(tmp_config))
        assert mgr.ignored_versions == {"1.0.0", "2.0.0"}

    def test_empty_file_treated_as_empty_ignore_list(self, vi_module, tmp_config):
        config_file = tmp_config / "ota_ignored_versions.json"
        config_file.write_text("", encoding="utf-8")

        # Empty file is technically not valid JSON; the loader MUST treat it
        # as "no ignore list" rather than crashing.
        mgr = vi_module.VersionIgnoreManager(config_dir=str(tmp_config))
        assert mgr.ignored_versions == set()


class TestVersionIgnoreThreadSafety:
    """Two concurrent ``get_version_ignore_manager`` calls must return the
    same instance (not two managers writing the same file from different
    memory states).
    """

    def test_concurrent_get_returns_same_instance(self, vi_module, tmp_path, monkeypatch):
        from config.envi import getECBotDataHome  # type: ignore
        monkeypatch.setattr(
            "config.envi.getECBotDataHome", lambda: str(tmp_path)
        )

        # Reset the cached singleton so we exercise the init path.
        vi_module._version_ignore_manager = None

        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(vi_module.get_version_ignore_manager())

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads must observe the SAME singleton instance.
        ids = {id(m) for m in results}
        assert len(ids) == 1, (
            f"get_version_ignore_manager returned {len(ids)} distinct "
            f"instances under contention — concurrent writers would "
            f"silently lose each other's updates."
        )


class TestVersionIgnoreBasicApi:
    """Round-trip the basic add/remove/check API."""

    @pytest.fixture
    def tmp_config(self, tmp_path, monkeypatch):
        from config.envi import getECBotDataHome  # type: ignore
        monkeypatch.setattr(
            "config.envi.getECBotDataHome", lambda: str(tmp_path)
        )
        vi = _import_version_ignore()
        vi._version_ignore_manager = None
        return tmp_path

    def test_ignore_then_check(self, vi_module, tmp_config):
        mgr = vi_module.VersionIgnoreManager(config_dir=str(tmp_config))
        assert mgr.is_ignored("1.0.0") is False
        mgr.ignore_version("1.0.0")
        assert mgr.is_ignored("1.0.0") is True

    def test_ignore_empty_string_is_noop(self, vi_module, tmp_config):
        """An empty version string MUST NOT create a phantom entry."""
        mgr = vi_module.VersionIgnoreManager(config_dir=str(tmp_config))
        mgr.ignore_version("")
        mgr.ignore_version(None)  # type: ignore[arg-type]
        assert mgr.ignored_versions == set()

    def test_clear_all(self, vi_module, tmp_config):
        mgr = vi_module.VersionIgnoreManager(config_dir=str(tmp_config))
        mgr.ignore_version("1.0.0")
        mgr.ignore_version("2.0.0")
        mgr.clear_all()
        assert mgr.ignored_versions == set()
