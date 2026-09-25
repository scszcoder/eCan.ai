"""
Test verifying the macOS PKG install fix (Bug 2026-09-24).

Bug summary: on macOS, OTA PKG installer failed silently because:
  1. _install_pkg did NOT call download_manager.set_installing(True), so
     WebGUI.closeEvent() popped an "Are you sure you want to exit?" dialog
     requiring manual user confirmation. On confirmation, the Python process
     exited and killed the osascript subprocess (which was launched in the
     same process group) before it could display the admin password prompt.
  2. subprocess.Popen(osa_cmd, ...) did NOT use start_new_session=True,
     so the osascript child process was terminated when the parent exited.
  3. InstallWorker is a QObject + QThread pair, with the thread cleaned up
     via ``finished → deleteLater`` so it doesn't block Python process exit
     (QThread has no ``setDaemon`` in PySide6 6.x; Qt-idiomatic cleanup is the
     equivalent).

This test pins the fix:
  * download_manager.set_installing(True) is called BEFORE terminating the
    app inside _install_pkg (matching what _install_exe / _install_msi do).
  * download_manager.set_installing(False) is called on all failure paths.
  * The osascript subprocess is launched with start_new_session=True so it
    survives the parent Python exit.
  * InstallWorker is a QObject + QThread pair, with the thread wired to
    ``deleteLater`` on ``finished`` for non-blocking process exit.
"""

import inspect
import subprocess
from unittest import mock

import pytest


def _pyside6_available() -> bool:
    """Return True if PySide6 is importable in the current test environment."""
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        return False


# We import the module fresh in every test so module-level state doesn't leak.
@pytest.fixture
def installer_module():
    import ota.core.installer as inst
    return inst


def test_install_pkg_calls_set_installing_true_before_terminate(installer_module):
    """``_install_pkg`` must set _ota_installing BEFORE terminating the app.

    This pins the 2026-09-24 macOS PKG install fix. The previous version
    forgot this call, which caused WebGUI.closeEvent() to show an
    "Are you sure you want to exit?" dialog and then kill the osascript
    child process before it could prompt for the admin password.
    """
    src = inspect.getsource(installer_module.InstallationManager._install_pkg)
    # The set_installing(True) call must appear BEFORE the
    # _terminate_macos_app invocation.
    set_installing_pos = src.find("download_manager.set_installing(True)")
    terminate_pos = src.find("_terminate_macos_app")
    assert set_installing_pos != -1, (
        "_install_pkg must call download_manager.set_installing(True) "
        "to suppress the WebGUI closeEvent confirmation dialog"
    )
    assert terminate_pos != -1, "_install_pkg must call _terminate_macos_app"
    assert set_installing_pos < terminate_pos, (
        "set_installing(True) must be called BEFORE _terminate_macos_app, "
        "so the closeEvent dialog is suppressed when the quit signal arrives"
    )


def test_install_pkg_popen_uses_start_new_session(installer_module):
    """``subprocess.Popen(osa_cmd, ...)`` inside _install_pkg must use start_new_session=True.

    Without it, when the Python parent exits, the osascript child process
    is killed via SIGHUP before it can show the admin password prompt.
    """
    src = inspect.getsource(installer_module.InstallationManager._install_pkg)
    # Locate the osascript Popen block (it's the one that takes osa_cmd).
    assert "osa_cmd" in src, "_install_pkg should build osa_cmd for osascript"
    assert "start_new_session=True" in src, (
        "subprocess.Popen for osascript must use start_new_session=True "
        "so it survives Python parent exit"
    )


def test_install_pkg_resets_set_installing_on_failure(installer_module):
    """``_install_pkg`` must reset ``_ota_installing`` on every failure path.

    Without this, a failed PKG install leaves the flag set, causing the
    closeEvent to silently exit the app on the next launch (suppressing
    the dialog for legitimate user-initiated exits too).
    """
    src = inspect.getsource(installer_module.InstallationManager._install_pkg)
    # Count occurrences of set_installing(False) inside _install_pkg's body.
    # We expect at least 3 failure-path resets (installer-failed,
    # TimeoutExpired, generic Exception, outer except).
    assert src.count("download_manager.set_installing(False)") >= 3, (
        "_install_pkg must reset download_manager.set_installing(False) "
        "on every failure path (timeout, exception, non-zero exit)"
    )


def test_install_pkg_calls_popen_via_subprocess_module(installer_module):
    """Sanity: the osascript launcher must go through subprocess.Popen, not a hand-rolled spawn.

    The actual bug fix relies on subprocess.Popen's start_new_session=True
    being honored by the platform's process-group semantics. Pin that the
    osascript subprocess is launched via subprocess.Popen with argv (not
    shell=True).
    """
    src = inspect.getsource(installer_module.InstallationManager._install_pkg)
    # The osa_cmd list must be passed to subprocess.Popen.
    assert "subprocess.Popen(" in src, (
        "_install_pkg must use subprocess.Popen to launch osascript"
    )
    assert "osa_cmd" in src, "_install_pkg should build osa_cmd for osascript"
    # And the osascript call must not use shell=True (which would bypass
    # argv quoting and break our path-safety guarantees).
    popen_osa_cmd_idx = src.find("subprocess.Popen(\n                        osa_cmd")
    assert popen_osa_cmd_idx != -1, (
        "_install_pkg must call subprocess.Popen(osa_cmd, ...)"
    )
    # Find the end of the Popen call (matching close paren on a new line).
    rest = src[popen_osa_cmd_idx:]
    # The closing paren comes after a newline + 20 spaces indent.
    closing = rest.find("\n                    )")
    assert closing != -1, "could not find closing paren of subprocess.Popen"
    popen_args = rest[:closing]
    assert "shell=True" not in popen_args, (
        "osascript subprocess.Popen must NOT use shell=True"
    )


def test_install_worker_uses_qobject_plus_qthread_daemon_pattern():
    """InstallWorker must be a QObject + QThread pair (NOT a QThread subclass).

    The previous design was a QThread subclass, which forces the thread's
    lifecycle to be tied to QApplication exit. When the app closes, the
    QThread is force-terminated and any blocking ``process.communicate()``
    inside the worker is killed mid-flight — before the osascript subprocess
    can prompt for the admin password.

    The new design is the standard Qt "worker object moved to thread"
    pattern: ``InstallWorker(QObject)`` + an internal ``QThread`` member,
    with ``finished → deleteLater`` wired so the QThread self-destructs and
    does not block Python process exit (the Qt-idiomatic equivalent of
    ``thread.setDaemon(True)``; ``QThread.setDaemon`` was removed in
    PySide6 6.x).

    Note: this test reads the source file directly instead of importing
    the module, because importing ``ota.gui.update_dialog`` transitively
    imports PySide6, which is not always available in CI. The static
    source check is sufficient to pin the design.
    """
    # Read the source without importing PySide6 (which may not be installed
    # in the CI unit-test environment). Pin the design via static analysis.
    src_path = "ota/gui/update_dialog.py"
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()
    # Extract just the InstallWorker class block.
    cls_start = src.find("class InstallWorker")
    assert cls_start != -1, "InstallWorker class not found in update_dialog.py"
    cls_end = src.find("\n\nclass ", cls_start + 1)
    if cls_end == -1:
        cls_end = len(src)
    worker_src = src[cls_start:cls_end]

    assert "class InstallWorker(QObject):" in worker_src, (
        "InstallWorker must inherit from QObject so its Qt signals are "
        "delivered through the worker thread's loop"
    )
    assert "class InstallWorker(QThread):" not in worker_src, (
        "InstallWorker must NOT inherit from QThread; the thread is "
        "managed via composition (a QThread member) so it can self-cleanup"
    )
    # Qt-idiomatic daemon-style cleanup: wire finished → deleteLater so the
    # QThread does not block Python process exit. (PySide6 6.x removed
    # ``QThread.setDaemon``, so the Qt event-loop cleanup is the right
    # pattern here.)
    assert "self._thread.finished.connect(self._thread.deleteLater)" in worker_src, (
        "InstallWorker must wire QThread.finished → QThread.deleteLater "
        "so the thread self-destructs after work completes and does not "
        "block Python process exit (Qt-idiomatic equivalent of daemon=True)"
    )
    # Regression guard: a previous incarnation added ``setDaemon(True)`` to
    # satisfy this test, but PySide6 6.x does not expose that method. The
    # test must not pin the old, broken pattern again.
    assert "self._thread.setDaemon(True)" not in worker_src, (
        "InstallWorker must NOT call QThread.setDaemon(True) — that method "
        "does not exist on PySide6 6.x and raises AttributeError at runtime. "
        "Use ``self._thread.finished.connect(self._thread.deleteLater)`` "
        "instead."
    )
    assert "def start(" in worker_src, "InstallWorker must expose a start() method"
    assert "def isRunning(" in worker_src, "InstallWorker must expose an isRunning() method"
    assert "self._thread.started.connect(self._do_work)" in worker_src, (
        "InstallWorker must wire the QThread's started signal to its work method"
    )

    # The previous incarnation of this fix forgot to add ``QObject`` to the
    # ``from PySide6.QtCore import ...`` line. The source-level "class
    # InstallWorker(QObject):" assertion above passed, but the runtime
    # failed with NameError at import time. Pin the import explicitly so
    # the next refactor of the import line can't quietly reintroduce it.
    qtcore_import_match = "from PySide6.QtCore import"
    if qtcore_import_match in src:
        import_line = src[src.find(qtcore_import_match):]
        import_line_end = import_line.find("\n")
        import_line = import_line[:import_line_end]
        assert "QObject" in import_line, (
            "update_dialog.py imports from PySide6.QtCore but does not "
            "include QObject; class InstallWorker(QObject): will raise "
            "NameError at import time. Add QObject to the import list."
        )


@pytest.mark.skipif(
    not _pyside6_available(),
    reason="PySide6 not installed in this environment; "
    "static source-level assertions above are sufficient.",
)
def test_install_worker_constructs_without_runtime_error():
    """Runtime check: InstallWorker must actually instantiate.

    The static source assertions above pin the design, but the original
    bug (``QThread.setDaemon`` does not exist in PySide6 6.x, and
    ``QObject`` was missing from the import line) only manifested at
    runtime. This test exercises the constructor end-to-end so the same
    regression class cannot slip past source-only checks again.

    The test imports ``ota.gui.update_dialog``, which is a heavy import
    (it pulls in app_info, logger_helper, the entire ota package). It is
    gated by ``_pyside6_available`` so CI environments without PySide6
    don't fail on import errors unrelated to this fix.
    """
    import sys
    import os
    from pathlib import Path

    # Use offscreen platform so we don't need a real display.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QCoreApplication  # noqa: F401
    from ota.gui.update_dialog import InstallWorker

    # If a QCoreApplication already exists (pytest may have created one
    # via another test), reuse it; otherwise create one.
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    try:
        worker = InstallWorker(Path("/tmp/_pkg_install_test.pkg"), {"silent": True})
        assert worker._thread.isRunning() is False
        assert worker._thread.objectName() == "InstallWorkerThread"
    finally:
        # Best-effort: do NOT call worker._thread.wait() — that would
        # exercise the very code path this fix is meant to avoid.
        pass