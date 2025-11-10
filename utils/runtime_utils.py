#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Runtime utilities
- Keep minimal, but include essential runtime setup needed when running from a PyInstaller bundle.
- Preference: do as much as possible at build-time; only do critical runtime setup here.
"""

import os
import sys
import time
import subprocess as _subprocess
from pathlib import Path


def is_pyinstaller_environment() -> bool:
    """Check if running in PyInstaller environment."""
    return getattr(sys, 'frozen', False)


def _setup_qt_webengine_environment() -> None:
    """Minimal Qt WebEngine environment setup for macOS when frozen.

    Sets QTWEBENGINEPROCESS_PATH to a valid QtWebEngineProcess executable if found,
    sets QTWEBENGINE_RESOURCES_PATH when possible, and disables sandbox to avoid
    issues inside PyInstaller bundles.
    """
    try:
        if sys.platform != 'darwin' or not is_pyinstaller_environment():
            return

        # Base dir inside PyInstaller bundle
        if hasattr(sys, '_MEIPASS'):
            base_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        else:
            base_dir = Path(sys.executable).parent / '_internal'

        qt_dir = base_dir / 'PySide6' / 'Qt'
        framework = qt_dir / 'lib' / 'QtWebEngineCore.framework'

        # Candidate paths in priority order:
        proc_candidates = [
            # Standard expected path via framework-level Helpers symlink
            framework / 'Helpers' / 'QtWebEngineProcess.app' / 'Contents' / 'MacOS' / 'QtWebEngineProcess',
            # Versioned path (A)
            framework / 'Versions' / 'A' / 'Helpers' / 'QtWebEngineProcess.app' / 'Contents' / 'MacOS' / 'QtWebEngineProcess',
            # PyInstaller-common misplaced path (Resources/Helpers)
            framework / 'Versions' / 'Resources' / 'Helpers' / 'QtWebEngineProcess.app' / 'Contents' / 'MacOS' / 'QtWebEngineProcess',
        ]

        # Respect existing env var if already set and valid
        current_proc = os.environ.get('QTWEBENGINEPROCESS_PATH')
        if not (current_proc and Path(current_proc).exists()):
            for c in proc_candidates:
                if c.exists():
                    os.environ['QTWEBENGINEPROCESS_PATH'] = str(c)
                    break

        # Try to set resources path if resources exist
        res_candidates = [
            framework / 'Resources',
            qt_dir / 'resources',
        ]
        current_res = os.environ.get('QTWEBENGINE_RESOURCES_PATH')
        if not (current_res and Path(current_res).exists()):
            for r in res_candidates:
                if r.exists():
                    os.environ['QTWEBENGINE_RESOURCES_PATH'] = str(r)
                    break

        # Disable sandbox to avoid issues inside bundled environment
        os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = '1'

    except Exception:
        # Be silent on failure to avoid noisy logs in user environments
        pass


def initialize_runtime_environment() -> None:
    """
    Initialize the runtime environment.
    This function should be called as early as possible in application startup.
    Note: platform._syscmd_ver patch is done in main.py before any imports.
    """
    _install_global_subprocess_hiding()
    _setup_qt_webengine_environment()


def _install_global_subprocess_hiding() -> None:
    try:
        if sys.platform != 'win32':
            return
        try:
            from utils import subprocess_helper as _sh  # type: ignore
        except Exception:
            return

        creation_flags, startupinfo = _sh.get_subprocess_creation_flags()

        def _merge_kwargs(kwargs: dict) -> dict:
            kwargs = kwargs.copy() if kwargs else {}
            if 'creationflags' in kwargs:
                kwargs['creationflags'] |= creation_flags
            else:
                kwargs['creationflags'] = creation_flags
            if startupinfo is not None and 'startupinfo' not in kwargs:
                kwargs['startupinfo'] = startupinfo
            return kwargs

        # Patch Popen with a proper class wrapper to maintain subclassability
        _orig_popen = _subprocess.Popen
        class _PatchedPopen(_orig_popen):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **_merge_kwargs(kwargs))
        _subprocess.Popen = _PatchedPopen  # type: ignore[assignment]

        _orig_run = _subprocess.run
        def _patched_run(cmd, **kwargs):
            return _orig_run(cmd, **_sh.get_subprocess_kwargs(kwargs))
        _subprocess.run = _patched_run  # type: ignore[assignment]

        _orig_check_output = _subprocess.check_output
        def _patched_check_output(cmd, **kwargs):
            return _orig_check_output(cmd, **_sh.get_subprocess_kwargs(kwargs))
        _subprocess.check_output = _patched_check_output  # type: ignore[assignment]

        _orig_check_call = _subprocess.check_call
        def _patched_check_call(cmd, **kwargs):
            return _orig_check_call(cmd, **_sh.get_subprocess_kwargs(kwargs))
        _subprocess.check_call = _patched_check_call  # type: ignore[assignment]

        _orig_call = _subprocess.call
        def _patched_call(cmd, **kwargs):
            return _orig_call(cmd, **_sh.get_subprocess_kwargs(kwargs))
        _subprocess.call = _patched_call  # type: ignore[assignment]

        _orig_system = os.system
        def _patched_system(cmd):
            try:
                return _subprocess.call(cmd, shell=True, **_sh.get_subprocess_kwargs({}))
            except Exception:
                return _orig_system(cmd)
        os.system = _patched_system  # type: ignore[assignment]

    except Exception:
        pass
