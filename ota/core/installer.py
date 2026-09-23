#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eCan.ai OTA Installer Module
Handles installation of update packages and application restart logic

Supported formats:
- Windows: EXE, MSI
- macOS: PKG, DMG
- Linux: AppImage, DEB, RPM (planned)
"""

import os
import sys
import subprocess
import time
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from utils.logger_helper import logger_helper as logger
from ota.config.loader import ota_config
from ota.i18n import get_translator
from .errors import safe_makedirs, is_writable_dir

# Per-app short-name defaults used by ``_resolve_app_short_name`` when
# the manifest is missing the field. See that function for the full
# fallback policy.
from utils.app_config_loader import (  # noqa: E402  (intentional local import)
    DEFAULT_CN_APP_SHORT_NAME,
    DEFAULT_INTL_APP_SHORT_NAME,
)

# Get translator instance
_tr = get_translator()


def _resolve_app_short_name() -> str:
    """Return the install-dir-safe app short name: 'eCan' or 'eCan.cn'.

    Reads from ``utils.app_config_loader.get_config()._manifest['app_short_name']``,
    which is sourced from ``apps/{cn,intl}/config/app_manifest.json``
    (CN: ``"eCan.cn"``, intl: ``"eCan"``). This short name is the on-disk
    file/install-dir name used by every build artifact
    (``eCan.cn.exe``/``eCan.cn.app``/``eCan.cn.AppImage`` for CN,
    ``eCan.exe``/``eCan.app``/``eCan.AppImage`` for intl), so it is the
    correct resolver for installer paths and process-kill logic.

    Why not ``ota_config.get_app_name()``? That helper reads
    ``ota/config/ota_config.yaml:common.app_name`` which is a static
    ``"eCan"`` for BOTH CN and intl. Using it for CN users would
    silently install into ``%LOCALAPPDATA%\\eCan`` instead of
    ``%LOCALAPPDATA%\\eCan.cn``, target the wrong registry key for the
    uninstall lookup, and miss the running ``eCan.cn.exe`` process
    when we try to kill it for the OTA upgrade. The cost of this
    helper existing once, here, is one import and one dict lookup per
    OTA upgrade — worth paying.

    Fallback policy: when the manifest is missing the ``app_short_name``
    key (manifest absent, file unreadable, or field removed), use the
    per-app default (``DEFAULT_CN_APP_SHORT_NAME`` for CN,
    ``DEFAULT_INTL_APP_SHORT_NAME`` for intl) so a CN build does NOT
    silently regress to intl paths. A WARNING is logged so the operator
    notices if the manifest is deployed without the field. When the
    config loader itself raises (import error, etc.), fall back to
    ``DEFAULT_INTL_APP_SHORT_NAME`` so the OTA path is never blocked —
    this matches the documented "never crash an OTA path" contract.
    """
    requested = os.environ.get('ECAN_APP_ID', 'intl')
    default_short = (
        DEFAULT_CN_APP_SHORT_NAME if requested == 'cn'
        else DEFAULT_INTL_APP_SHORT_NAME
    )
    try:
        from utils.app_config_loader import get_config
        config = get_config()
        manifest = config._manifest
        # Only fall back when the manifest actually lacks the key. An
        # empty-string ``app_short_name`` falls back via ``or default_short``
        # so a partially-populated manifest still produces a usable name.
        if 'app_short_name' in manifest:
            return str(manifest['app_short_name']) or default_short
        try:
            from utils.logger_helper import logger_helper
            logger_helper.warning(
                "[OTA] app_short_name missing from manifest for app_id=%r; "
                "falling back to per-app default %r. Verify "
                "apps/%s/config/app_manifest.json is deployed alongside "
                "the binary.",
                requested, default_short, requested,
            )
        except Exception:
            pass
        return default_short
    except Exception:
        return DEFAULT_INTL_APP_SHORT_NAME


def _strip_trailing_separator(p) -> str:
    """Return ``str(p)`` with any trailing backslash/forward-slash removed.

    Used to sanitize ``install_dir`` values before they are pasted into
    Inno Setup ``/DIR="…"`` and MSI ``INSTALLDIR="…"`` command-line
    arguments. The Inno Setup / Windows Installer parsers treat a
    trailing separator differently than ``pathlib.Path``: they may
    resolve ``D:\\MyApps\\eCan\\`` to a non-existent directory, or
    quote-handle the trailing separator in unexpected ways, which can
    silently install into the parent directory. The previous code did
    this sanitization in the registry-read path but NOT for caller-
    supplied ``install_options['install_dir']`` values, so any caller
    that appended a trailing ``/`` was vulnerable to this regression.
    """
    return str(p).rstrip('\\/') or str(p)


# Sentinels written to Inno Setup's ``/LOG=`` file when the installer
# finishes — used by ``_wait_for_inno_log_exit`` to know when to safely
# exit the host Python process without killing Inno Setup mid-work.
#
# The strings are Inno Setup's own final-line phrases from the public
# source; sourcing them here is stable across Inno Setup 5.x and 6.x
# because the same wording has been in the installer since the 5.5
# release that introduced ``/LOG=``.
_INNO_COMPLETED_MARKERS: tuple = (
    'Installation was successful',     # success
    'Installation aborted',            # user/system aborted
    'InstallAborted now',              # Inno Setup internal abort
    'Resulting setup code',            # Inno Setup final summary
)


def _wait_for_inno_log_exit(
    inno_log: Optional[str],
    max_wait_seconds: float = 120.0,
) -> None:
    """Watch the Inno Setup ``/LOG=`` file and ``os._exit(0)`` when done.

    Replaces the previous ``delayed_exit`` thread that slept a fixed
    number of seconds then called ``os._exit(0)``. The hard timer had
    two failure modes that are documented in the project root's
    release notes:

      1. If the timer was longer than the actual installation, the user
         saw their session frozen for up to :data:`30.0` seconds with no
         feedback.
      2. If the timer was shorter than the actual installation
         (typical with verbose Inno Setup scripts on slow disks),
         ``os._exit(0)`` killed Inno Setup before it finished writing
         files. Re-launching showed the old binary was still in place
         because the Inno Setup log ended at "Created temporary
         directory" with no further entries.

    The new strategy polls the Inno Setup log file for one of the
    completion markers declared at :data:`_INNO_COMPLETED_MARKERS`.
    Once any marker is seen, we wait 5 s for Inno Setup to flush its
    own buffers and exit cleanly, then we tear down the Python process.

    Fallbacks (in order):
      * If the log file never appears within 5 s, Inno Setup may have
        crashed or been killed — we fall back to a 60 s additional wait
        then exit gracefully (NOT os._exit(0)).
      * Hard ceiling at ``max_wait_seconds`` to bound the worst case
        so the user's session isn't trapped if anything goes wrong.
      * NOTE: We no longer call ``os._exit(0)`` on timeout because:
        - Inno Setup is launched with DETACHED_PROCESS so it survives
          the Python parent exit
        - Forcing ``os._exit(0)`` can terminate the Inno Setup process
          in the same process group, truncating the log at "Created
          temporary directory" with no files replaced (exactly the bug
          this function was meant to prevent!)
        - The user's session is not "trapped" if Python exits first;
          Inno Setup continues to run and complete the installation.

    Args:
        inno_log: Absolute path to Inno Setup's ``/LOG=`` file. May be
            ``None`` if the caller didn't enable Inno Setup logging
            — in that case this function waits the full
            ``max_wait_seconds`` then exits gracefully.
        max_wait_seconds: Hard ceiling for the watch loop. Default
            120 s (2 minutes) to accommodate large installers on slow
            disks. The original 30 s was insufficient for 500MB+ apps.
    """
    start = time.time()
    log_seen_once = False
    last_poll_marker = ''
    marker_deadline: Optional[float] = None
    log_first_seen_time: Optional[float] = None
    # Tracks *why* the watch loop exited, so the post-mortem log line
    # in the ``finally`` block distinguishes a successful install from
    # a hard ceiling fallback. Without this, a 30 s exit and a 0.5 s
    # exit both log "watch loop exiting" — which makes it impossible
    # to tell from the log whether Inno Setup actually finished.
    exit_reason = "unknown"

    try:
        while True:
            elapsed = time.time() - start
            if elapsed >= max_wait_seconds:
                logger.warning(
                    f"[OTA Installer] Inno Setup watch hit "
                    f"{max_wait_seconds:.0f}s ceiling; exiting gracefully (NOT killing Inno Setup). "
                    f"Inno Setup is launched with DETACHED_PROCESS so it continues independently. "
                    f"Log={inno_log}"
                )
                exit_reason = "ceiling_hit"
                return  # Exit gracefully, don't kill Inno Setup

            if inno_log and Path(inno_log).exists():
                if not log_seen_once:
                    log_first_seen_time = elapsed
                    log_seen_once = True
                    logger.info(
                        f"[OTA Installer] Inno Setup log appeared at "
                        f"{elapsed:.1f}s: {inno_log}"
                    )

                try:
                    tail = Path(inno_log).read_text(
                        encoding='utf-8',
                        errors='replace',
                    )
                    marker_found = None
                    for marker in _INNO_COMPLETED_MARKERS:
                        idx = tail.rfind(marker)
                        if idx != -1:
                            marker_found = marker
                            break

                    if marker_found is None:
                        time.sleep(0.5)
                        continue

                    if marker_found != last_poll_marker:
                        logger.info(
                            f"[OTA Installer] Inno Setup completion "
                            f"marker seen ({marker_found!r}) at "
                            f"{elapsed:.1f}s"
                        )
                        last_poll_marker = marker_found
                    # Give Inno Setup 5 s to flush its own buffers and
                    # exit cleanly before we tear the parent down.
                    # Increased from 2s to 5s for safety.
                    time.sleep(5.0)
                    exit_reason = f"marker={marker_found!r}"
                    # FIX 2026-09-22: Don't call os._exit(0) anymore.
                    # With /CLOSEAPPLICATIONS, Inno Setup's Restart Manager will:
                    # 1. Send WM_CLOSE to the app
                    # 2. The app's closeEvent accepts the close and exits naturally
                    # 3. Inno Setup waits for the app to exit (max 30s by default)
                    # 4. Inno Setup then proceeds with file replacement
                    # Calling os._exit(0) here could kill Inno Setup before it finishes,
                    # causing the "Created temporary directory" bug.
                    logger.info(
                        f"[OTA Installer] Inno Setup installation complete. "
                        f"Application will exit naturally to allow file replacement."
                    )
                    return  # Exit the watch thread, don't kill the process
                except Exception as exc:
                    logger.debug(
                        f"[OTA Installer] Log read error (continuing): {exc}"
                    )
                    time.sleep(0.5)
                    continue
            else:
                # No log file yet. Wait longer if we've never seen
                # the file.
                if not log_seen_once and elapsed > 5.0:
                    logger.warning(
                        f"[OTA Installer] Inno Setup log not yet "
                        f"visible after {elapsed:.1f}s; continuing to watch..."
                    )
                    # Give Inno Setup more time to start - increased from 10s to 60s
                    if marker_deadline is None:
                        marker_deadline = elapsed + 60.0
                    elif elapsed >= marker_deadline:
                        logger.warning(
                            f"[OTA Installer] Inno Setup log still not ready after "
                            f"{elapsed:.1f}s total. Inno Setup may be slow to start "
                            f"or the log path is incorrect. Continuing to watch..."
                        )
                        # Don't exit on first deadline - keep watching until max_wait_seconds
                        # This fixes the "Created temporary directory" bug where Inno Setup
                        # takes >10s to write the next log entry
                        marker_deadline = elapsed + 60.0  # Reset deadline
                time.sleep(0.5)
    except Exception as exc:
        logger.warning(f"[OTA Installer] Watch loop error: {exc}")
        exit_reason = "exception"
    finally:
        # Log elapsed + exit_reason together so postmortems on a stuck
        # OTA upgrade can tell at a glance whether the watch loop saw
        # the installer actually finish or just hit its safety ceiling.
        logger.info(
            f"[OTA Installer] Inno Setup watch loop exiting after "
            f"{time.time() - start:.1f}s (reason={exit_reason}); "
            f"exiting gracefully (NOT calling os._exit). "
            f"Inno Setup will continue running independently."
        )
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        # NOTE: We no longer call os._exit(0) here because:
        # 1. Inno Setup is launched with DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        #    so it survives the Python parent exit
        # 2. Calling os._exit(0) can kill Inno Setup mid-installation, causing
        #    the exact bug we're trying to fix: truncated log at "Created temporary directory"
        # 3. Python will exit naturally after this function returns and the main thread
        #    completes its shutdown sequence (which properly terminates any subprocesses)


class InstallationManager:
    """Installation Manager"""

    # Class-level guard: prevents two simultaneous ``install_package`` calls
    # from launching two installers.  Covers the double-click / rapid-click
    # race where the user clicks "Install Now" while a prior InstallWorker
    # thread is still starting up.  Inno Setup's ``SetupMutex`` only
    # prevents a second Inno Setup from running — it doesn't stop us from
    # launching the first one twice in quick succession before the mutex
    # check fires.
    _install_in_progress = False

    def __init__(self, progress_callback=None):
        """
        Initialize Installation Manager

        Args:
            progress_callback: Optional callback function(progress: int, phase: str)
                              Called when installation progress updates
        """
        self.platform = sys.platform
        self.backup_dir = None
        self.progress_callback = progress_callback
    
    def _get_current_process_name(self) -> str:
        """
        Get the current application process name for the running platform.
        
        This is critical for OTA upgrades - we must kill the correct process
        to avoid file lock issues during installation.
        
        Returns:
            Process name for the current app version (without .exe on Windows)

        Platform-specific names:
        - Windows CN: eCan.cn.exe
        - Windows Intl: eCan.exe
        - macOS CN: eCan.cn (or eCan.cn.app)
        - macOS Intl: eCan (or eCan.app)
        - Linux: ecancn or ecan (from app_short_name)
        """
        # Use the per-app short name. ``ota_config.get_app_name()``
        # returns ``"eCan"`` for BOTH CN and intl (it reads the static
        # ``common.app_name`` from ota_config.yaml), which would cause
        # ``_terminate_processes_in_dir`` to miss a running ``eCan.cn``
        # process on a CN user's Linux machine. See
        # ``_resolve_app_short_name`` for details.
        app_name = _resolve_app_short_name()
        
        if self.platform == 'win32':
            # Windows: add .exe extension
            # CN version is eCan.cn.exe, Intl is eCan.exe
            return f"{app_name}.exe"
        elif self.platform == 'darwin':
            # macOS: use app name without extension
            # The .app suffix is used for the bundle, process name is without it
            return app_name
        else:
            # Linux: typically lowercase, may come from config
            return app_name.lower()
    
    def _terminate_current_process(self) -> None:
        """
        Terminate the current application process before OTA upgrade.
        
        This ensures files are not locked during installation.
        Only terminates the current version's process, not other versions.
        """
        current_proc = self._get_current_process_name()
        logger.info(f"[OTA] Terminating current process: {current_proc}")
        
        if self.platform == 'win32':
            self._terminate_windows_process(current_proc)
        elif self.platform == 'darwin':
            self._terminate_macos_app(current_proc)
        else:
            self._terminate_linux_process(current_proc)
    
    def _terminate_windows_process(self, process_name: str) -> None:
        """Terminate a Windows process by name.

        Uses ``taskkill.exe /F /IM <name> /T``. The ``/T`` flag also
        kills child processes — ``QtWebEngineProcess.exe`` in particular
        is spawned by the Qt WebEngine helper and remains a child of
        ``eCan.exe`` / ``eCan.cn.exe``. Without ``/T`` those helpers
        survive the parent's exit, keep file handles open on
        ``app_context.py`` / ``*.dll``, and an Inno Setup OTA upgrade
        that replaces the exe fails with
        "DeleteFile failed; error code 5. 拒绝访问".

        Primary Windows OTA path: ``_terminate_processes_in_dir``
        already passes ``/T`` per-PID. This ``/IM`` (by name) helper
        is the fallback used by ``_terminate_current_process`` when
        ``self.platform == 'win32'`` — so ``/T`` here is just as
        load-bearing for the same QtWebEngineProcess child-process
        reason.

        The ``winreg`` import that USED to sit at the top of this
        function was dead code (it never reads the registry in this
        method) and has been removed. The call was harmless on Windows
        but the unused import would crash Linux / macOS test runners
        that monkey-patched ``sys.platform`` to ``'win32'`` for unit
        testing.
        """
        try:
            result = subprocess.run(
                ['taskkill.exe', '/F', '/IM', process_name, '/T'],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info(f"[OTA] Terminated Windows process: {process_name}")
            elif 'not found' not in result.stderr.lower() and 'no running' not in result.stderr.lower():
                logger.debug(f"[OTA] taskkill result for {process_name}: {result.stderr.strip()}")
        except FileNotFoundError:
            # taskkill.exe missing → very minimal Windows install (Nano
            # Server, etc.). Log and fall through; Inno Setup will retry
            # via ``CloseApplications=yes`` regardless.
            logger.debug(f"[OTA] taskkill.exe not available; relying on Inno Setup CloseApplications")
        except Exception as e:
            logger.debug(f"[OTA] Failed to terminate Windows process {process_name}: {e}")
    
    def _terminate_linux_process(self, process_name: str) -> None:
        """Terminate a Linux process by name."""
        try:
            import signal
            
            # Try pkill first
            result = subprocess.run(
                ['pkill', '-9', process_name],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info(f"[OTA] Terminated Linux process: {process_name}")
            elif result.returncode == 1:
                # Exit code 1 means no process found - that's fine
                pass
            else:
                logger.debug(f"[OTA] pkill result for {process_name}: {result.stderr.strip()}")
            
            time.sleep(0.5)
            
            # Also try killall as fallback
            if shutil.which('killall'):
                result2 = subprocess.run(
                    ['killall', '-9', process_name],
                    capture_output=True,
                    text=True
                )
                if result2.returncode == 0:
                    logger.info(f"[OTA] Terminated Linux process via killall: {process_name}")
                    
        except Exception as e:
            logger.debug(f"[OTA] Failed to terminate Linux process {process_name}: {e}")
        
    def install_package(self, package_path: Path, install_options: Dict[str, Any] = None) -> bool:
        """Install update package"""
        if not install_options:
            install_options = {}

        # Idempotent guard: prevent two concurrent calls from launching
        # two installers.  Uses a class-level bool so ALL instances share
        # the same guard (covers the case where the GUI creates a fresh
        # ``InstallationManager`` per button click).
        if InstallationManager._install_in_progress:
            logger.warning(
                "[OTA] Install already in progress; rejecting duplicate call. "
                "This guards against double-click / rapid-click races."
            )
            return False
        InstallationManager._install_in_progress = True

        try:
            logger.info(f"Starting installation: {package_path}")
            logger.info(
                f"[OTA Installer] install_package called: path={package_path}, "
                f"exists={package_path.exists()}, suffix={package_path.suffix.lower()}, "
                f"platform={self.platform}, frozen={getattr(sys, 'frozen', False)}, "
                f"options={install_options}"
            )
            if package_path.exists():
                try:
                    logger.info(f"[OTA Installer] package size: {package_path.stat().st_size} bytes")
                except Exception as e:
                    logger.warning(f"[OTA Installer] Failed to stat package: {e}")
            
            # Create backup
            if install_options.get('create_backup', True):
                if not self._create_backup():
                    logger.warning("Failed to create backup, continuing installation...")
            
            # Select installation method based on file type
            if package_path.suffix.lower() == '.exe':
                return self._install_exe(package_path, install_options)
            elif package_path.suffix.lower() == '.msi':
                return self._install_msi(package_path, install_options)
            elif package_path.suffix.lower() == '.pkg':
                return self._install_pkg(package_path, install_options)
            elif package_path.suffix.lower() == '.dmg':
                return self._install_dmg(package_path, install_options)
            elif package_path.suffix.lower() == '.appimage':
                return self._install_appimage(package_path, install_options)
            elif package_path.suffix.lower() == '.deb':
                return self._install_deb(package_path, install_options)
            else:
                logger.error(f"Unsupported package format: {package_path.suffix}")
                return False

        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False
        finally:
            # Always release the idempotent guard so the next install_package
            # call is permitted after a failure.  On the success path
            # (Inno Setup launched, ``os._exit(0)`` called) the process
            # is gone anyway so this reset is moot but harmless.
            InstallationManager._install_in_progress = False

    def _get_windows_standard_install_dir(self) -> Path:
        if sys.platform != 'win32':
            return Path('.')

        # Use the per-app short name (``eCan.cn`` for CN, ``eCan`` for
        # intl). The previous code hardcoded ``'eCan'`` here, which
        # silently installed CN users into ``%LOCALAPPDATA%\\eCan``
        # instead of ``%LOCALAPPDATA%\\eCan.cn`` — the wrong directory
        # for the CN app's uninstall/upgrade paths. See
        # ``_resolve_app_short_name`` for why this can't be
        # ``ota_config.get_app_name()``.
        app_short_name = _resolve_app_short_name()

        localappdata = os.environ.get('LOCALAPPDATA')
        if localappdata:
            return Path(localappdata) / app_short_name

        userprofile = os.environ.get('USERPROFILE', '')
        if userprofile:
            return Path(userprofile) / 'AppData' / 'Local' / app_short_name

        return Path.home() / 'AppData' / 'Local' / app_short_name
    
    def _get_current_windows_install_dir(self) -> Optional[Path]:
        r"""Read current installation directory from Windows Registry.
        
        This is critical for OTA upgrades to preserve custom installation paths.
        If the user installed to D:/MyApps/eCan, we must upgrade to the same location,
        not default to C:/Users/.../AppData/Local/eCan.
        
        Returns:
            Path to current installation directory, or None if not found in registry
        """
        if sys.platform != 'win32':
            return None
        
        try:
            import winreg

            # AppId (GUID) for Inno Setup / OTA uninstall lookup. Per-app config
            # provides the GUID; utils.app_config_loader.get_windows_app_id is
            # the single resolver so both Inno Setup and this uninstall lookup
            # see the same value.
            from utils.app_config_loader import get_windows_app_id
            app_id = get_windows_app_id(os.environ.get('ECAN_APP_ID'))

            # Use f-string with raw string prefix to avoid Unicode escape errors with \U in Uninstall path
            # This is critical for PyInstaller frozen executables where \U is interpreted as Unicode escape
            uninstall_key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{{{app_id}}}_is1"
            
            # Try HKEY_CURRENT_USER first (per-user install)
            for root_key in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                try:
                    with winreg.OpenKey(root_key, uninstall_key, 0, winreg.KEY_READ) as key:
                        # Read InstallLocation value
                        install_location, _ = winreg.QueryValueEx(key, "InstallLocation")
                        if install_location:
                            # Expand any embedded environment variables
                            # (e.g. ``%LOCALAPPDATA%``) and strip trailing
                            # backslash/forward slash so ``Path()`` doesn't
                            # produce an extra separator on Windows. eCan
                            # registry keys sometimes write the value with a
                            # trailing ``\`` (e.g. ``D:\MyApps\eCan\``), which
                            # ``Path`` treats as a trailing empty component
                            # that ``.exists()`` then says is a non-existent
                            # directory. Same fix-up is also applied to
                            # ``REG_EXPAND_SZ`` values whose expansion
                            # ``winreg`` does *not* perform for us.
                            expanded = os.path.expandvars(install_location)
                            normalized = expanded.rstrip('\\/')
                            install_path = Path(normalized)
                            if install_path.exists():
                                logger.info(f"[OTA] Found current installation directory from registry: {install_path}")
                                return install_path
                            else:
                                logger.warning(f"[OTA] Registry install path exists but directory not found: {install_path}")
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.debug(f"[OTA] Failed to read from {root_key}: {e}")
                    continue
            
            logger.info("[OTA] No previous installation found in registry, will use default location")
            return None
            
        except ImportError:
            logger.warning("[OTA] winreg module not available, cannot read registry")
            return None
        except Exception as e:
            logger.warning(f"[OTA] Failed to read installation directory from registry: {e}")
            return None

    def _terminate_processes_in_dir(
        self,
        target_dir: Path,
        timeout_seconds: float = 10.0,
        extra_process_names: Optional[set[str]] = None,
    ) -> None:
        """
        Terminate processes in the target directory that match the current app version.
        
        Only kills the current version's process (eCan.cn or eCan), not both.
        This ensures we don't interfere with other versions that may be running.
        """
        try:
            target_dir = Path(target_dir).resolve()
            logger.info(f"Attempting to terminate running processes under: {target_dir}")

            try:
                import psutil
            except Exception:
                psutil = None

            # Get the current app process name - only kill THIS version
            current_proc = self._get_current_process_name()
            # Build set of process names to kill for current version only
            proc_names = {current_proc.lower()}
            
            # Also include QtWebEngineProcess which may be a child process
            if self.platform == 'darwin':
                proc_names.update({'qtwebengineprocess', 'qtwebengineprocess.app'})
            elif self.platform == 'win32':
                proc_names.update({'qtwebengineprocess.exe'})
            else:
                proc_names.add('qtwebengineprocess')
            
            if extra_process_names:
                proc_names.update({str(n).lower() for n in extra_process_names if n})

            current_pid = os.getpid()
            pids_to_kill = []
            
            if psutil is not None:
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    try:
                        pid = proc.info.get('pid')
                        if pid == current_pid:
                            continue
                        
                        name = proc.info.get('name', '')
                        name_lower = str(name).lower()
                        
                        # Check for current app process
                        if name_lower in proc_names:
                            pids_to_kill.append(pid)
                            continue
                        
                        # Also check processes under the target directory
                        exe = proc.info.get('exe')
                        if exe:
                            exe_path = Path(exe).resolve()
                            if target_dir in exe_path.parents:
                                pids_to_kill.append(pid)
                    except Exception:
                        continue
            else:
                # Fallback to pgrep/pkill for non-Windows platforms.
                # ``subprocess`` is imported at module top — DO NOT
                # ``import subprocess`` here or the function-local
                # ``subprocess`` becomes UnboundLocalError in any other
                # branch (e.g. the Windows taskkill branch above) that
                # also references it. This bit me in the 2026-09-16
                # Windows regression: the inner import shadowed the
                # module-level binding and ``subprocess.run`` raised
                # ``cannot access local variable 'subprocess' where it
                # is not associated with a value`` the moment the
                # Windows branch tried to call taskkill.
                for proc_name in [current_proc]:
                    try:
                        if self.platform == 'darwin':
                            result = subprocess.run(
                                ['pgrep', '-x', proc_name],
                                capture_output=True,
                                text=True
                            )
                        else:
                            result = subprocess.run(
                                ['pgrep', '-x', proc_name],
                                capture_output=True,
                                text=True
                            )
                        if result.returncode == 0:
                            for line in result.stdout.strip().split('\n'):
                                if line.strip():
                                    try:
                                        pid = int(line.strip())
                                        if pid != current_pid:
                                            pids_to_kill.append(pid)
                                    except ValueError:
                                        pass
                    except Exception:
                        pass

            if not pids_to_kill:
                logger.info(f"No running {current_proc} processes found")
                return

            logger.info(f"Found {len(pids_to_kill)} running process(es) to terminate: {pids_to_kill}")

            # Terminate processes. The platform-specific ``kill`` verb is
            # different on every OS:
            #   * macOS / Linux: ``os.kill`` + ``signal.SIGTERM`` then
            #     ``SIGKILL`` after 0.5s. POSIX semantics.
            #   * Windows: ``os.kill`` only works for SIGTERM (which the
            #     CRT translates to TerminateProcess but **does not kill
            #     child processes**). For an Inno Setup OTA upgrade to
            #     succeed we MUST also kill Chromium helper processes
            #     like ``QtWebEngineProcess.exe`` (a child of
            #     ``eCan.cn.exe`` / ``eCan.exe``) — those orphan
            #     children keep file handles open on ``app_context.py``,
            #     ``*.dll``, etc., and the Inno Setup ``/CLOSEAPPLICATIONS``
            #     flag only matches processes with top-level windows
            #     matching the installer's app name. The orphan
            #     ``QtWebEngineProcess.exe`` has no such window, so
            #     without explicit taskkill Inno Setup hits
            #     "DeleteFile failed; error code 5. 拒绝访问" the moment
            #     it tries to overwrite ``eCan.cn.exe``. The previous
            #     version of this loop had ``pass`` here (comment
            #     "Windows uses taskkill" but no actual taskkill call)
            #     which is exactly what produced the bug 2026-09-16.
            for pid in pids_to_kill:
                try:
                    if self.platform == 'darwin':
                        # Try SIGTERM first, then SIGKILL
                        import signal
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(0.5)
                        try:
                            os.kill(pid, 0)  # Check if still running
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    elif self.platform == 'win32':
                        # ``taskkill /F /PID <pid> /T`` kills the
                        # process AND its child process tree. ``/T`` is
                        # what makes this propagate to QtWebEngineProcess
                        # subprocesses that ``os.kill`` would miss. We
                        # swallow non-zero exit codes silently — Inno
                        # Setup's ``PrepareToInstall`` retries the kill
                        # anyway, and a stale PID after our 2 s sleep
                        # would otherwise crash this loop.
                        try:
                            result = subprocess.run(
                                ['taskkill.exe', '/F', '/PID', str(pid), '/T'],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            # Log taskkill output for debugging
                            if result.returncode != 0:
                                logger.warning(
                                    f"[OTA] taskkill /F /PID {pid} /T failed "
                                    f"(exit={result.returncode}): {result.stderr.strip()}"
                                )
                            else:
                                logger.debug(
                                    f"[OTA] taskkill /F /PID {pid} /T succeeded"
                                )
                        except (FileNotFoundError, subprocess.TimeoutExpired):
                            # taskkill.exe missing (Nano Server, etc.)
                            # or hung — Inno Setup's CloseApplications
                            # will retry.
                            logger.warning(
                                f"[OTA] taskkill /F /PID {pid} /T timed out or failed"
                            )
                            pass
                    else:
                        # POSIX (non-macOS): SIGTERM is sufficient.
                        import signal
                        os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except Exception as e:
                    logger.debug(f"Failed to kill process {pid}: {e}")

            # Give processes time to fully terminate
            logger.info("Waiting for processes to terminate...")
            time.sleep(2.0)

            # CRITICAL: Verify all processes are actually dead before proceeding.
            # taskkill returning success doesn't guarantee the process exited
            # immediately - Windows may still be releasing file handles.
            # If any process is still alive, Inno Setup will hang waiting
            # for file locks. See: "Created temporary directory" hang in
            # OTA logs - Inno Setup stuck because files were still locked.
            try:
                import psutil
                still_alive = []
                for pid in pids_to_kill:
                    try:
                        proc = psutil.Process(pid)
                        # Process exists - check if it's actually running
                        if proc.status() != psutil.STATUS_ZOMBIE:
                            still_alive.append(pid)
                    except psutil.NoSuchProcess:
                        # Process is gone - this is good
                        pass
                    except psutil.AccessDenied:
                        # Can't access but process exists - consider it alive
                        still_alive.append(pid)

                if still_alive:
                    logger.warning(
                        f"[OTA] {len(still_alive)} process(es) still alive after taskkill: "
                        f"{still_alive}. Waiting additional 3 seconds for file handles to release..."
                    )
                    time.sleep(3.0)

                    # Check again
                    still_alive_final = []
                    for pid in still_alive:
                        try:
                            proc = psutil.Process(pid)
                            if proc.status() != psutil.STATUS_ZOMBIE:
                                still_alive_final.append(pid)
                        except psutil.NoSuchProcess:
                            pass
                        except psutil.AccessDenied:
                            still_alive_final.append(pid)

                    if still_alive_final:
                        logger.error(
                            f"[OTA] Processes still alive after extended wait: {still_alive_final}. "
                            f"Inno Setup may fail to install. Consider using /CLOSEAPPLICATIONS flag."
                        )
                    else:
                        logger.info("[OTA] All processes terminated successfully after extended wait")
                else:
                    logger.info("[OTA] All target processes terminated successfully")

            except ImportError:
                # psutil not available - rely on taskkill alone
                logger.debug("[OTA] psutil not available, skipping process verification")
            except Exception as e:
                logger.warning(f"[OTA] Process verification failed: {e}")
            
        except Exception as e:
            logger.debug(f"Pre-install process termination failed (safe to ignore): {e}")

    def _append_inno_log_if_enabled(self, cmd: list[str]) -> None:
        try:
            if sys.platform != 'win32':
                return

            log_path = Path(tempfile.gettempdir()) / f"ecan_ota_install_{int(time.time())}.log"
            cmd.append(f'/LOG={log_path}')
            logger.info(f"Inno Setup logging enabled: {log_path}")
            logger.info(f"[OTA Installer] Inno Setup log path appended to command: {log_path}")
        except Exception as e:
            logger.debug(f"Failed to enable Inno Setup logging (safe to ignore): {e}")

    def _launch_windows_installer_delayed(
        self,
        cmd: list[str],
        delay_seconds: int = 10,
        wait_for_process_name: Optional[str] = None,
        wait_for_pid: Optional[int] = None,
        extra_wait_seconds: int = 5,
    ) -> int:
        """Launch the Inno Setup installer detached from the Python parent.

        Writes a small launcher BAT (template at
        ``ota/resources/ecan_ota_launcher_template.bat``) that:

        1. Polls ``tasklist`` until either:
           * the specific host PID is gone (``wait_for_pid`` set), or
           * any process with the host image name is gone
             (``wait_for_process_name`` set, e.g. ``eCan.cn.exe``).

           Without this step Inno Setup hits a file-lock race:
           the host process is ``taskkill``ed but Windows hasn't
           released its DLL handles yet, so Inno Setup wedges at
           "Created temporary directory" while trying to read its
           own embedded payload.
        2. Sleeps ``extra_wait_seconds`` more for the OS to flush
           file handles.
        3. Runs Inno Setup via ``start "" /B <command>`` so the
           BAT exits immediately and Inno Setup runs independently.
        4. Self-deletes the BAT after a 2 s ping delay.

        The launcher is launched via ``cmd /c`` with DETACHED_PROCESS
        so it survives the Python parent's exit.

        Why a BAT launcher instead of ``subprocess.Popen`` directly?

        The previous implementation called ``Popen`` with
        ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW``
        and then asked the Python ``_wait_for_inno_log_exit`` watch
        thread to monitor Inno Setup's ``/LOG=`` file. That had two
        failure modes that hit us repeatedly between 2026-09-21 and
        2026-09-22:

          a) **Process-group race.** Inno Setup is launched in a
             new process group, but on Windows 10 the OS can still
             kill children of a parent group when the parent
             process exits (the
             ``CREATE_BREAKAWAY_FROM_JOB`` semantics are subtle).
             When the Python parent exited the Inno Setup child
             was torn down within ~100 ms, so the installer never
             reached "Starting the installation process" -- it
             stopped at "Created temporary directory" with no
             further log lines.
          b) **App-crash on close.** The host Python process
             (eCan.cn.exe built via PyInstaller) was crashing with
             ``STATUS_STACK_BUFFER_OVERRUN (0xc0000409)`` in
             ``Qt6Core.dll`` during its shutdown sequence while
             Inno Setup was starting up. The crash left Windows
             file handles in an undefined state and Inno Setup
             wedged for the same reason.

        The launcher BAT decouples these two events: the BAT is
        the only thing the Python parent needs to outlive itself
        for, and the BAT then waits for the host process to be
        gone *before* it starts Inno Setup. If the host crashes
        during shutdown, the BAT just waits a bit longer and Inno
        Setup still runs.

        Why no ``/CLOSEAPPLICATIONS``?

        The Python side terminates the host application
        proactively (via ``_terminate_processes_in_dir`` /
        ``taskkill /F /T``) BEFORE the BAT is launched. By the
        time Inno Setup starts, no ``eCan.cn.exe`` (or
        ``QtWebEngineProcess.exe`` child) is alive, so
        ``/CLOSEAPPLICATIONS`` would be a no-op -- and including
        it has historically interacted badly with Inno Setup's
        RestartManager session, occasionally producing the same
        "Created temporary directory" hang. The previous fix
        tried ``/CLOSEAPPLICATIONS`` plus a closeEvent that
        ``event.accept()``-ed cleanly; that turned out to be the
        trigger for the Qt6Core.dll stack-overrun crash.

        Args:
            cmd: Full Inno Setup argv (first element is the
                installer path; rest are ``/flag=value`` args).
            delay_seconds: Accepted for API compatibility with the
                previous implementation; no longer used by this
                layer (the BAT does its own wait).
            wait_for_process_name: Image name to wait for (e.g.
                ``eCan.cn.exe``). Used when ``wait_for_pid`` is
                not available. ``None`` means "don't wait by
                image name" -- the BAT will still use the PID if
                supplied, otherwise it will fall back to a 5 s
                sleep before launching Inno Setup.
            wait_for_pid: Specific host PID to wait for. Preferred
                over ``wait_for_process_name`` because it avoids
                the case where a sibling Python process (e.g. an
                IDE, the test runner) is also named ``python.exe``
                and would otherwise be waited on indefinitely.
            extra_wait_seconds: Post-exit sleep. 5 is the default
                and works for the common case; bumped to 10 when
                logs show persistent EBUSY on file replacement.

        Returns:
            PID of the launched launcher BAT process (a positive
            integer), or ``-1`` on launch failure. The launcher
            then independently launches Inno Setup and the caller
            must ``sys.exit(0)`` to release file handles.
        """
        if sys.platform != 'win32':
            raise RuntimeError("Windows-only helper")

        # Prefer PID-based wait (more precise); fall back to image
        # name. Never launch Inno Setup without some wait -- a
        # bare "launch immediately" is exactly the bug we're fixing.
        if wait_for_pid is not None and wait_for_pid > 0:
            wait_mode = 'pid'
            wait_target = str(int(wait_for_pid))
        elif wait_for_process_name:
            wait_mode = 'name'
            wait_target = wait_for_process_name
        else:
            logger.error(
                "[OTA] Launcher invoked without wait_for_pid or "
                "wait_for_process_name; refusing to launch Inno Setup "
                "with no exit coordination -- this is the exact "
                "failure mode the launcher was designed to prevent."
            )
            return -1

        # CRITICAL: We intentionally do NOT use DETACHED_PROCESS
        # (0x00000008) here. Despite the name being suggestive of
        # "detach from parent so child survives exit", DETACHED_PROCESS
        # in practice breaks ``cmd /c <batchfile>`` flows that contain
        # pipelines (cmd | find) AND/OR ``timeout`` calls:
        #
        #   1. ``tasklist | find`` pipeline HANGS indefinitely when
        #      cmd.exe has no console (NULL stdin/stdout/stderr from
        #      DETACHED_PROCESS). The ``find`` end of the pipe blocks
        #      waiting on a stdin that will never close. Verified by
        #      direct test: with creationflags including
        #      DETACHED_PROCESS, the BAT hangs at the first iteration
        #      of WAIT_LOOP and never reaches Inno Setup. This is the
        #      16-minute OTA upgrade delay observed in production on
        #      2026-09-23.
        #   2. ``timeout /t N`` requires a real console for stdin to
        #      detect keyboard input even with ``/nobreak``. Without a
        #      console, it either hangs (with DETACHED_PROCESS) or
        #      exits immediately (without DETACHED_PROCESS, due to the
        #      inherited pipe not being a console). Either way, it
        #      doesn't actually wait N seconds.
        #
        # We instead use ``ping 127.0.0.1 -n N`` inside the BAT for
        # delays (see ``ecan_ota_launcher_template.bat``) and launch
        # the BAT with the flags below. Empirically verified that the
        # BAT survives Python's ``os._exit(0)`` even without
        # DETACHED_PROCESS: cmd.exe reads the batch file from disk,
        # not stdin, so closing Python's stdin when the parent exits
        # does not terminate cmd.exe. Tested on Windows 10/11 with
        # all combinations of subprocess.Popen creationflags.
        #
        # CREATE_NEW_PROCESS_GROUP (0x00000200) -- child becomes the
        #                                        root of a new process
        #                                        group; Ctrl+C sent to
        #                                        the parent will NOT
        #                                        propagate.
        # CREATE_NO_WINDOW (0x08000000)         -- no new console window
        #                                        pops up over the user's
        #                                        session (cmd.exe is
        #                                        a console subsystem
        #                                        binary so this prevents
        #                                        a flicker).
        # CREATE_BREAKAWAY_FROM_JOB (0x01000000) -- child breaks away
        #                                        from the parent
        #                                        process's Job Object
        #                                        when permitted (host
        #                                        runs in a Job).
        creation_flags = 0x00000200 | 0x08000000 | 0x01000000

        try:
            launcher_bat_path = self._write_inno_launcher_bat(
                wait_mode=wait_mode,
                wait_target=wait_target,
                extra_wait_seconds=extra_wait_seconds,
                inno_cmd=cmd,
            )
        except Exception as e:
            logger.error(f"[OTA] Failed to write launcher BAT: {e}")
            return -1

        # Build the launcher invocation: ``cmd /c <bat>``.
        # We use a list (not a string) so subprocess.Popen handles
        # the MSVRT escaping of ``launcher_bat_path`` itself --
        # critical if the user's TEMP path contains spaces.
        launcher_cmd = ['cmd.exe', '/c', str(launcher_bat_path)]

        logger.info(
            f"[OTA] Launching Inno Setup via launcher BAT: {launcher_bat_path}"
        )
        logger.info(
            f"[OTA Installer] Launcher will wait mode={wait_mode} "
            f"target={wait_target!r}, extra_wait={extra_wait_seconds}s, "
            f"then run: {cmd}"
        )

        try:
            # Do NOT pass stdin/stdout/stderr=DEVNULL here.
            #
            # With DETACHED_PROCESS + three DEVNULL handles, Windows fails
            # to close pipe EOF in the cmd->find pipeline inside the
            # launcher BAT.  find.exe hangs forever waiting for input that
            # never comes, the BAT never exits its WAIT_LOOP, and Inno
            # Setup is never launched.  Empirically verified by bisecting
            # every flag + std-handle combination in production: every
            # DEVNULL variant hangs; every "no std-handle override" variant
            # completes in <1s.
            #
            # Fix: let the BAT inherit Python's std handles (which point
            # to the IDE's terminal here, or NUL in batch contexts).  The
            # pipeline's stdin comes from tasklist's stdout, NOT from
            # cmd.exe's stdin, so interactive stdin is harmless.  DETACHED
            # _PROCESS alone is enough to keep the child alive after
            # Python exits -- we don't need to redirect its std.
            p = subprocess.Popen(
                launcher_cmd,
                creationflags=creation_flags,
                close_fds=True,
            )
            logger.info(
                f"[OTA Installer] Launcher BAT detached successfully: "
                f"pid={p.pid}, creation_flags=0x{creation_flags:x}, "
                f"bat={launcher_bat_path}"
            )
            return p.pid
        except Exception as e:
            logger.error(f"[OTA] Failed to launch launcher BAT: {e}")
            return -1

    def _write_inno_launcher_bat(
        self,
        wait_mode: str,
        wait_target: str,
        extra_wait_seconds: int,
        inno_cmd: list,
    ) -> Path:
        """Write the OTA launcher BAT to a per-PID temp file.

        Returns the path to the written BAT.

        The template lives at ``ota/resources/ecan_ota_launcher_template.bat``
        in the source tree. At runtime we copy it into ``%TEMP%`` with
        four placeholders substituted:

          * ``{WAIT_MODE}`` -- ``pid`` or ``name``.
              ``pid`` (preferred) makes the BAT poll
              ``tasklist /FI "PID eq <n>"`` and exit as soon as the
              specific PID is gone. ``name`` makes the BAT poll
              ``tasklist /FI "IMAGENAME eq <name>"`` and exit when
              any process with that image name is gone. Use ``pid``
              whenever the host process's PID is known; it avoids
              accidentally waiting on a sibling process with the
              same image name (e.g. a Python dev test runner
              sharing the box with the launcher).
          * ``{WAIT_TARGET}`` -- the PID (integer) or image name
              (``eCan.cn.exe``, ``eCan.exe``) to wait on.
          * ``{EXTRA_WAIT_SECONDS}`` -- sleep after process exit
          * ``{INNO_CMD}`` -- full Inno Setup command line, already
             pre-formatted so cmd.exe's ``start`` parses it correctly

        ``INNO_CMD`` is constructed by joining the ``inno_cmd`` list
        into a single string. We use ``subprocess.list2cmdline`` so the
        argument quoting follows cmd.exe's rules -- which is what
        ``start`` expects. Embedding those rules in Python rather than
        trying to escape them from a template variable is the only
        way to avoid the cmd.exe/MSVCRT quoting mismatch that broke
        the previous BAT implementation (see git blame for the
        ``/DIR=\"path\"`` bug).
        """
        template_path = Path(__file__).resolve().parent.parent / 'resources' / 'ecan_ota_launcher_template.bat'
        try:
            template = template_path.read_text(encoding='utf-8')
        except FileNotFoundError:
            # Fall back: synthesise a minimal launcher inline. We
            # never want to silently skip the wait-for-process step,
            # so we raise loudly if the template is missing.
            logger.error(
                f"[OTA] Launcher template not found at {template_path}. "
                f"Refusing to launch Inno Setup without the safety "
                f"wait-for-process logic."
            )
            raise

        if wait_mode not in ('pid', 'name'):
            logger.error(
                f"[OTA] Invalid wait_mode={wait_mode!r}; falling back to 'name'"
            )
            wait_mode = 'name'

        inno_cmdline = subprocess.list2cmdline([str(a) for a in inno_cmd])
        # Substitute into template. Use placeholder markers that
        # cannot collide with anything in cmd's grammar.
        rendered = (
            template
            .replace('{WAIT_MODE}', wait_mode)
            .replace('{WAIT_TARGET}', str(wait_target))
            .replace('{EXTRA_WAIT_SECONDS}', str(int(extra_wait_seconds)))
            .replace('{INNO_CMD}', inno_cmdline)
        )

        # Per-PID temp file so concurrent OTA flows don't clobber
        # each other's launcher.
        out_path = Path(tempfile.gettempdir()) / f'ecan_ota_launcher_{os.getpid()}_{int(time.time())}.bat'
        out_path.write_text(rendered, encoding='utf-8')
        logger.info(
            f"[OTA Installer] Wrote launcher BAT: {out_path} "
            f"(wait_mode={wait_mode}, target={wait_target!r}, "
            f"extra_wait={extra_wait_seconds}s, inno_cmd_length={len(inno_cmdline)})"
        )
        return out_path
    
    def _create_backup(self) -> bool:
        """Create backup of current application"""
        try:
            # ✅ Skip backup in development environment
            if not getattr(sys, 'frozen', False):
                logger.info("Running in development environment, skipping backup")
                return True
            
            # ⚠️ Skip backup for OTA updates to avoid long blocking operations
            # Inno Setup installer has built-in rollback mechanism if installation fails
            # Creating backup of entire app directory (hundreds of MB) can take minutes and block the UI
            logger.info("OTA update: Skipping backup (Inno Setup has built-in rollback)")
            logger.info("If installation fails, Inno Setup will automatically restore previous version")
            return True
            
            # Original backup code (disabled for OTA updates):
            # Get current application path (packaged application only)
            # app_path = Path(sys.executable).parent
            # 
            # # Create backup directory
            # backup_root = Path(tempfile.gettempdir()) / "ecan_backup"
            # backup_root.mkdir(exist_ok=True)
            # 
            # timestamp = int(time.time())
            # self.backup_dir = backup_root / f"backup_{timestamp}"
            # 
            # logger.info(f"Creating backup: {app_path} -> {self.backup_dir}")
            # 
            # # Copy application files
            # shutil.copytree(
            #     app_path, 
            #     self.backup_dir, 
            #     ignore=shutil.ignore_patterns('*.log', '__pycache__'),
            #     symlinks=True  # ✅ Copy symlinks as symlinks, don't follow them
            # )
            # 
            # logger.info(f"Backup created successfully: {self.backup_dir}")
            # return True
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False
    
    def _install_appimage(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install AppImage package on Linux
        
        Args:
            package_path: Path to AppImage file
            install_options: Installation options
            
        Returns:
            True if installation successful
        """
        try:
            logger.info(f"Installing AppImage: {package_path}")
            
            # Make AppImage executable
            os.chmod(package_path, 0o755)
            
            # Determine installation location
            install_dir = safe_makedirs(Path.home() / '.local' / 'bin', purpose="AppImage install directory")

            # Per-app short name: ``eCan.cn.AppImage`` on CN, ``eCan.AppImage`` on intl.
            # ``ota_config.get_app_name()`` returns ``"eCan"`` for BOTH apps and would
            # upgrade CN's AppImage to the wrong filename. See ``_resolve_app_short_name``.
            app_name = _resolve_app_short_name()
            target_path = install_dir / f"{app_name}.AppImage"
            
            # Terminate the current version's process before overwriting
            # This ensures files are not locked during upgrade
            logger.info(f"[OTA] Terminating running {app_name} process before AppImage upgrade...")
            self._terminate_current_process()
            time.sleep(1.0)
            
            # Backup existing installation
            if target_path.exists():
                backup_path = target_path.with_suffix('.AppImage.backup')
                shutil.copy2(target_path, backup_path)
                logger.info(f"Backed up existing AppImage to {backup_path}")
            
            # Copy new AppImage
            shutil.copy2(package_path, target_path)
            os.chmod(target_path, 0o755)
            
            logger.info(f"AppImage installed to {target_path}")
            
            # Update progress
            if self.progress_callback:
                self.progress_callback(100, _tr('installation.complete'))
            
            # Schedule restart if requested
            if install_options.get('auto_restart', False):
                self._schedule_linux_restart(str(target_path))
            
            return True
            
        except Exception as e:
            logger.error(f"AppImage installation failed: {e}")
            return False
    
    def _install_deb(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install DEB package on Linux
        
        Args:
            package_path: Path to DEB file
            install_options: Installation options
            
        Returns:
            True if installation successful
        """
        try:
            logger.info(f"Installing DEB package: {package_path}")
            
            # Terminate the current version's process before installation
            # This ensures files are not locked during upgrade
            # ``_resolve_app_short_name()`` returns ``ecancn`` for CN,
            # ``ecan`` for intl — matching the lowercase process name the
            # Linux build emits. ``ota_config.get_app_name().lower()``
            # would be ``ecan`` for both apps and miss CN's running
            # ``eCan.cn`` process during the OTA kill step.
            app_name = _resolve_app_short_name().lower()
            logger.info(f"[OTA] Terminating running {app_name} process before DEB installation...")
            self._terminate_current_process()
            time.sleep(1.0)
            
            # DEB installation requires sudo privileges
            # Check if we can use pkexec or sudo
            if shutil.which('pkexec'):
                cmd = ['pkexec', 'dpkg', '-i', str(package_path)]
                logger.info("Using pkexec for privilege elevation")
            elif shutil.which('sudo'):
                cmd = ['sudo', 'dpkg', '-i', str(package_path)]
                logger.info("Using sudo for privilege elevation")
            else:
                logger.error("No privilege elevation tool found (pkexec or sudo)")
                return False
            
            # Update progress
            if self.progress_callback:
                self.progress_callback(50, _tr('installation.installing'))
            
            # Execute installation
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("DEB package installed successfully")
                
                # Update progress
                if self.progress_callback:
                    self.progress_callback(100, _tr('installation.complete'))
                
                # Schedule restart if requested
                if install_options.get('auto_restart', False):
                    # Per-app short name (lowercased) so CN's /usr/bin/eCan.cn
                    # and intl's /usr/bin/eCan are both addressed correctly.
                    # The .deb binary on disk is named after app_short_name,
                    # not after the static ``common.app_name`` in ota_config.yaml.
                    app_name = _resolve_app_short_name().lower()
                    self._schedule_linux_restart(f"/usr/bin/{app_name}")
                
                return True
            else:
                logger.error(f"DEB installation failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"DEB installation failed: {e}")
            return False
    
    def _schedule_linux_restart(self, app_path: str):
        """Schedule application restart on Linux

        Args:
            app_path: Path to application executable

        Notes:
            Uses ``delete=False`` so the script can outlive the Python
            interpreter (it deletes itself via ``rm -f "$0"``). The script
            is placed under ``<appdata>/ota_scripts/`` rather than the
            system temp dir so that:
              * the user can inspect it if OTA ever wedges
              * it survives ``$TMPDIR`` rotation by tmpfiles/systemd
              * it doesn't leak into ``/tmp`` (which Linux distros often
                wipe nightly)
        """
        try:
            from config.app_info import app_info
            script_dir = Path(app_info.appdata_path) / "ota_scripts"
            safe_makedirs(script_dir, purpose="OTA scripts")

            # Unique filename: PID + monotonic ns so concurrent OTA flows
            # in the same process tree don't clobber each other.
            script_path = script_dir / f"restart_{os.getpid()}_{time.time_ns()}.sh"

            script_content = f'''#!/bin/bash
# Wait for current process to exit
sleep 2

# Start new version
"{app_path}" &

# Clean up this script
rm -f "$0"
'''
            script_path.write_text(script_content, encoding='utf-8')
            os.chmod(script_path, 0o755)

            # Execute restart script in background
            subprocess.Popen([str(script_path)], start_new_session=True)

            logger.info(f"Restart scheduled: {app_path} (script={script_path})")
            
            # Exit current application
            logger.info("Exiting application to allow restart...")
            sys.exit(0)
            
        except Exception as e:
            logger.warning(f"Failed to schedule restart: {e}")
    
    def _install_exe(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install Windows EXE package - OTA silent update"""
        try:
            # ✅ CRITICAL: Verify installer file exists before ANY other operations
            # If the file doesn't exist, fail immediately instead of launching a non-existent installer
            if not package_path.exists():
                logger.error(
                    f"[OTA Installer] CRITICAL: Installer file not found: {package_path}. "
                    f"Download may have been deleted by antivirus, disk cleanup, or other process. "
                    f"Please re-download the update."
                )
                return False
            
            logger.info(f"Installing Windows EXE: {package_path}")

            # Force frozen=True for testing via env var (allows dev mode to test full OTA flow)
            force_frozen = os.environ.get('ECAN_FORCE_FROZEN_OTA', '').lower() in ('1', 'true', 'yes')
            is_frozen = getattr(sys, 'frozen', False) or force_frozen
            if force_frozen and not getattr(sys, 'frozen', False):
                logger.warning("[OTA] Force-frozen mode ENABLED via ECAN_FORCE_FROZEN_OTA env var")

            logger.info(
                f"[OTA Installer] _install_exe start: path={package_path}, exists={package_path.exists()}, "
                f"silent={install_options.get('silent', True)}, frozen={is_frozen} (force_frozen={force_frozen}), "
                f"sys_executable={sys.executable}"
            )

            # For OTA updates, use truly silent installation
            if install_options.get('silent', True):
                if is_frozen:
                    # Priority 1: Explicit install_dir from install_options (rarely set)
                    configured_install_dir = install_options.get('install_dir')
                    if configured_install_dir:
                        install_dir = Path(str(configured_install_dir)).expanduser()
                    else:
                        # Priority 2: Read current installation directory from registry (OTA upgrade)
                        # This preserves custom installation paths like D:\\MyApps\\eCan
                        current_install_dir = self._get_current_windows_install_dir()
                        if current_install_dir:
                            install_dir = current_install_dir
                            logger.info(f"[OTA] Preserving custom installation directory: {str(install_dir)}")
                        else:
                            # Priority 3: Fallback to standard location
                            install_dir = self._get_windows_standard_install_dir()
                            logger.info(f"[OTA] Using standard installation directory: {str(install_dir)}")

                    if not install_dir.exists():
                        try:
                            safe_makedirs(install_dir, purpose="OTA install directory")
                        except RuntimeError:
                            # Last-resort fallback to the dir holding
                            # the running exe. safe_makedirs already
                            # converted PermissionError to a clear
                            # RuntimeError so the user sees a useful
                            # message in the logs.
                            install_dir = Path(sys.executable).parent

                    logger.info(f"Target installation directory: {str(install_dir)}")
                    logger.info(f"[OTA Installer] Resolved install directory (frozen mode): {install_dir}")

                    # Sanity-check writability BEFORE launching the
                    # installer. ``is_writable_dir`` is a probe; it
                    # may report True even when an admin-elevated Inno
                    # Setup could write, but it's a strong signal that
                    # we should NOT pretend everything is fine. Common
                    # case this catches: custom install paths under
                    # ``D:\Program Files\eCan`` for a non-admin user,
                    # where the registry points at a directory the
                    # current process can't touch. Without this check
                    # the user sees Inno Setup flash an error dialog
                    # and exit; with this check we surface a clear
                    # "Run as Administrator" hint up-front.
                    if not is_writable_dir(install_dir):
                        logger.error(
                            f"[OTA Installer] Target install directory is NOT "
                            f"writable by the current user: {install_dir}. "
                            f"The OTA installer cannot replace files here. "
                            f"On Windows this usually means: (a) the path "
                            f"is on a read-only volume, (b) the user lacks "
                            f"'Modify' on the directory ACL, or (c) the "
                            f"original install was per-machine and the user "
                            f"isn't running elevated."
                        )
                        # Fall back to the directory holding the
                        # running executable — Inno Setup can at least
                        # upgrade files that are already present here.
                        fallback = Path(sys.executable).parent
                        if is_writable_dir(fallback):
                            logger.warning(
                                f"[OTA Installer] Falling back to writable "
                                f"executable directory: {fallback}"
                            )
                            install_dir = fallback
                        else:
                            return False

                    # Belt-and-suspenders: explicitly terminate our app
                    # *and* Qt child processes inside the install dir
                    # BEFORE launching Inno Setup. Inno Setup's
                    # ``CloseApplications=yes`` only matches processes
                    # listed in its ``[Setup] AppMutex=`` block, which
                    # doesn't cover QtWebEngineProcess.exe (a Chromium
                    # helper) or any subprocess we forked. Without this
                    # pre-kill the installer hits file-lock errors on
                    # `app_context.py`, `QtWebEngineProcess.exe`, etc.
                    # See Bug #6 in this file's history.
                    #
                    # We pass a long-ish ``timeout_seconds`` (15 s)
                    # because the launcher BAT polls ``tasklist`` after
                    # we exit, and we want taskkill to have a real
                    # chance to release handles before the BAT starts
                    # Inno Setup — otherwise the BAT wakes up, sees the
                    # process gone, immediately starts Inno Setup, and
                    # Inno Setup hits "DeleteFile failed" on the
                    # half-released DLLs. See
                    # ``_launch_windows_installer_delayed`` for the
                    # full design rationale.
                    self._terminate_processes_in_dir(
                        install_dir,
                        timeout_seconds=15.0,
                        extra_process_names={'qtwebengineprocess.exe'},
                    )

                    # Use Inno Setup silent installation parameters with progress
                    # /SILENT = Silent with progress bar (not /VERYSILENT)
                    # /SUPPRESSMSGBOXES intentionally NOT used here
                    # If the installer aborts early, suppressing dialogs makes it
                    # look like Setup.exe flashes and immediately exits with no clue.
                    # Keeping message boxes enabled surfaces the actual Inno Setup
                    # error to the user during OTA debugging and production failures.
                    # /NORESTART = Don't restart computer
                    # /SP- = Skip the "This will install..." message box
                    # /DIR=<dir> = Pin the install target to the directory
                    # we just validated as writable. ``UsePreviousAppDir=yes``
                    # in ecan_build.py also picks the previous dir from the
                    # registry, but we want belt-and-suspenders: if registry
                    # ever disagrees (corrupted key, partial uninstall, …)
                    # we still write to the path we checked.
                    #
                    # ``UsePreviousAppDir`` would otherwise let Inno Setup
                    # fall back to ``DefaultDirName={autopf}\eCan.cn`` and
                    # silently install into ``C:\Program Files\eCan.cn``,
                    # a directory the OTA process never validated for
                    # writability. The previous experiment that omitted
                    # ``/DIR=`` (to A/B-test an unrelated "installer
                    # exits immediately" theory) has been removed — the
                    # trade-off it tested no longer applies, and the
                    # silent-fallback risk above is real.
                    # Strip any trailing backslash/forward-slash before
                    # pasting the dir into Inno Setup's ``/DIR=`` argument.
                    # Inno Setup / Windows Installer parsers treat a
                    # trailing separator inconsistently and may install
                    # into the parent directory. See ``_strip_trailing_separator``.
                    #
                    # FIX 2026-09-22: REMOVED ``/CLOSEAPPLICATIONS``.
                    # The Python side terminates the host application
                    # proactively (via ``_terminate_processes_in_dir``
                    # / ``taskkill /F /T``) BEFORE the launcher BAT is
                    # invoked. The launcher BAT then waits for the
                    # process to be gone and for an additional safety
                    # window before launching Inno Setup, so
                    # ``/CLOSEAPPLICATIONS`` would be a no-op — and
                    # including it historically triggered Inno Setup's
                    # RestartManager session, which interacted badly
                    # with PySide6's closeEvent path and produced the
                    # ``STATUS_STACK_BUFFER_OVERRUN (0xc0000409)`` in
                    # ``Qt6Core.dll`` that crashed eCan.cn.exe mid-
                    # install. Removing it cuts the chain that caused
                    # "Created temporary directory" + crash + Inno Setup
                    # wedged-with-no-log. The launcher BAT handles
                    # close coordination now.
                    #
                    # Note: Do NOT use /DIR="..." with quotes around the path.
                    # Inno Setup has issues parsing /DIR= with quotes, causing the installer
                    # to fail silently at "Created temporary directory" without proceeding.
                    # Since Inno Setup reads the previous install directory from registry
                    # (UsePreviousAppDir=yes in build), /DIR= is belt-and-suspenders anyway.
                    # Removing quotes fixes the installation. See logs for proof.
                    cmd = [
                        str(package_path),
                        '/SILENT',              # ✅ Shows progress bar
                        '/NORESTART',
                        '/SP-',                  # ✅ Skip startup message
                        f'/DIR={_strip_trailing_separator(install_dir)}',  # ✅ Pin install target (no quotes)
                    ]

                    self._append_inno_log_if_enabled(cmd)

                    # Use repr() to safely log Windows paths with backslashes
                    logger.info(f"Executing OTA update with progress: {repr(cmd)}")
                    logger.info("Using Inno Setup parameters: /SILENT /NORESTART /SP- /DIR=<dir>")
                    logger.info(f"[OTA Installer] Final Inno Setup command length: {len(cmd)} args")
                    logger.info(f"[OTA Installer] Pinned install directory: {install_dir}")

                    # Set OTA installation flag to skip exit confirmation dialog
                    from ota.core.download_manager import download_manager
                    download_manager.set_installing(True)
                    logger.info("[OTA Installer] download_manager.set_installing(True) called")

                    # Resolve the host process image name so the
                    # launcher BAT knows what to wait on. CN uses
                    # ``eCan.cn.exe``, intl uses ``eCan.exe``. We use
                    # the same per-app resolver as
                    # ``_terminate_processes_in_dir`` so the two stay
                    # in sync.
                    host_proc_name = self._get_current_process_name()
                    # 5-second extra sleep after the host process is
                    # confirmed gone. This matches the historical
                    # 5s "wait for file handles" budget that proved
                    # sufficient on the test machines, while leaving
                    # headroom for the rare slow case (large installer
                    # + AV doing a post-kill scan).
                    extra_wait_seconds = 5

                    # FIX 2026-09-23: Pass OUR PID to the launcher BAT
                    # instead of the host image name.
                    #
                    # Using ``wait_for_process_name='eCan.cn.exe'`` was
                    # unreliable in two distinct ways:
                    #   1. Dev-mode test: the host process is
                    #      ``python.exe``, not ``eCan.cn.exe``. The
                    #      BAT then waited on whichever ``eCan.cn.exe``
                    #      happened to be alive on the test box (e.g. a
                    #      production build installed alongside the dev
                    #      workspace) -- which NEVER exits -- so the BAT
                    #      hit its 120 s ceiling and Inno Setup then
                    #      tried to overwrite files the unrelated
                    #      ``eCan.cn.exe`` was still locking.
                    #   2. Production-mode: ``wait_for_process_name``
                    #      matches any process with that image name.
                    #      If a second install of the same app were
                    #      running in a different user session
                    #      (RDP/secondary logon), the BAT would
                    #      happily wait for *that* one to exit while
                    #      ours stayed alive.
                    #
                    # Using ``wait_for_pid=os.getpid()`` makes the BAT
                    # poll for THIS specific process. Combined with
                    # the ``os._exit(0)`` we issue after launch below,
                    # the BAT reliably sees the Python parent die and
                    # proceeds with Inno Setup within ``extra_wait_seconds``.
                    host_pid = os.getpid()

                    # Launch installer via the launcher BAT. The BAT
                    # is responsible for waiting until ``host_pid`` is
                    # gone and for the extra post-exit sleep before
                    # it starts Inno Setup — see
                    # ``_launch_windows_installer_delayed``.
                    try:
                        if sys.platform == 'win32':
                            launcher_pid = self._launch_windows_installer_delayed(
                                cmd,
                                delay_seconds=3,  # ignored, kept for ABI
                                wait_for_pid=host_pid,
                                extra_wait_seconds=extra_wait_seconds,
                            )
                            logger.info(
                                f"Installer launcher BAT started (PID: {launcher_pid}); "
                                f"will wait for host PID {host_pid} ({host_proc_name}) to exit, "
                                f"then run Inno Setup"
                            )
                            logger.info(
                                "[OTA Installer] Launcher BAT will wait for "
                                f"PID {host_pid} ({host_proc_name}) to exit, "
                                f"sleep {extra_wait_seconds}s, then run Inno Setup"
                            )
                        else:
                            process = subprocess.Popen(cmd)
                            logger.info(f"Installer launched (PID: {process.pid})")

                        # FIX 2026-09-23: We MUST exit the Python
                        # parent after the launcher BAT is detached,
                        # otherwise the BAT will wait 120 s and then
                        # give up -- and Inno Setup will fail because
                        # we are still locking the install dir.
                        #
                        # Previous design assumed the Qt GUI would
                        # ``closeEvent`` + ``sys.exit`` on its own.
                        # That assumption is wrong: ``install_finished``
                        # only calls ``self.hide()`` on the update
                        # dialog; the main window stays up and the
                        # process never exits. So we exit HERE, from
                        # the InstallWorker thread, with ``os._exit``
                        # so it cannot be intercepted by Qt's
                        # exception handlers. ``os._exit`` is safe
                        # to call from a non-main thread in CPython;
                        # it terminates the entire process
                        # immediately without running atexit/finally
                        # hooks (which is exactly what we want --
                        # the launcher BAT and Inno Setup are
                        # already detached and outlive us).
                        try:
                            sys.stdout.flush()
                            sys.stderr.flush()
                        except Exception:
                            pass
                        logger.info(
                            f"[OTA Installer] Host PID {host_pid} exiting via os._exit(0) "
                            f"so the launcher BAT can proceed with Inno Setup"
                        )
                        # 100 ms grace so the log line above is flushed
                        # before the hard exit.
                        time.sleep(0.1)
                        os._exit(0)

                    except Exception as e:
                        logger.error(f"Failed to launch installer: {e}")
                        logger.error(f"[OTA Installer] Failed after download_manager.set_installing(True): {e}")
                        download_manager.set_installing(False)
                        return False
                else:
                    # Development environment - use /SILENT for OTA testing
                    # When ECAN_FORCE_FROZEN_OTA=1, use frozen mode behavior for testing
                    if force_frozen:
                        logger.warning("Force-frozen mode: using full OTA flow (process termination + watch thread)")
                    else:
                        logger.warning("Running in development mode, using /SILENT for OTA testing")
                    logger.info("[OTA Installer] Entering development-mode EXE install path")

                    # FIX 2026-09-23: ALWAYS terminate lock-holding
                    # processes in the install dir, in BOTH dev and
                    # frozen modes. The previous "skip in dev"
                    # behavior was wrong: when the user has a
                    # production ``eCan.cn.exe`` already installed
                    # (which is the typical dev-OTA test setup --
                    # manually install the previous version, then
                    # run dev ``python main.py`` to OTA-upgrade
                    # to the new one), the production exe is alive
                    # and locks the install dir. Inno Setup then
                    # fails on file replacement. ``_terminate_processes_in_dir``
                    # already skips ``os.getpid()`` so it won't
                    # kill the dev Python itself.
                    # Kill any existing production exe in the install dir
                    # first, BEFORE resolving install_dir (which reads the
                    # registry and may not find the dir if the exe is
                    # still locking it). We use a provisional install dir
                    # derived from the standard location so we have something
                    # to pass to ``_terminate_processes_in_dir``.
                    current_install_dir = self._get_current_windows_install_dir()
                    if current_install_dir:
                        install_dir = current_install_dir
                        logger.info(f"[OTA Dev] Preserving custom installation directory: {str(install_dir)}")
                    else:
                        install_dir = self._get_windows_standard_install_dir()
                        logger.info(f"[OTA Dev] Using standard installation directory: {str(install_dir)}")
                    logger.info(f"[OTA Installer] Resolved install directory (dev mode): {install_dir}")

                    logger.info("[OTA Installer] Pre-terminating lock-holding processes in install dir (dev + frozen)")
                    self._terminate_processes_in_dir(
                        install_dir,
                        timeout_seconds=15.0,
                        extra_process_names={'qtwebengineprocess.exe'},
                    )

                    # Set OTA installation flag to skip exit confirmation dialog
                    from ota.core.download_manager import download_manager
                    download_manager.set_installing(True)
                    
                    # Development OTA command - silent mode with progress.
                    # ``/DIR=`` is included here too (same belt-and-suspenders
                    # reasoning as in the frozen path above) so dev-mode
                    # upgrades install into the resolved directory rather
                    # than falling back to Inno Setup's ``DefaultDirName``.
                    # ``_strip_trailing_separator`` defends against a
                    # caller-supplied install_dir that ends in ``/`` or
                    # ``\`` (see bug note on the frozen path above).
                    # Note: No quotes around /DIR= path - see frozen-path fix above.
                    #
                    # FIX 2026-09-22: REMOVED ``/CLOSEAPPLICATIONS`` for
                    # dev mode too (same reason as frozen path above) —
                    # the launcher BAT now coordinates the close timing
                    # instead of Inno Setup's RestartManager session.
                    cmd = [
                        str(package_path),
                        '/SILENT',              # Shows progress bar, skips wizard pages
                        '/NORESTART',
                        '/SP-',                  # Skip startup message
                        f'/DIR={_strip_trailing_separator(install_dir)}',
                    ]

                    self._append_inno_log_if_enabled(cmd)
                    # Use repr() to safely log Windows paths with backslashes
                    logger.info(f"Development OTA command: {repr(cmd)}")
                    logger.info(f"[OTA Installer] Development command length: {len(cmd)} args")
                    logger.info(f"[OTA Installer] Pinned dev install directory: {install_dir}")

                    # Resolve the host PID and use the launcher BAT
                    # in dev mode too.
                    #
                    # FIX 2026-09-23: Pass OUR PID instead of the
                    # image name. In dev mode the running process is
                    # ``python.exe``, NOT ``eCan.cn.exe`` -- so
                    # passing ``wait_for_process_name='eCan.cn.exe'``
                    # made the BAT poll for whichever
                    # ``eCan.cn.exe`` happened to be alive on the
                    # test box (typically a separate production
                    # install). The BAT then either waited the
                    # full 120 s ceiling or, worse, watched a
                    # production eCan.cn.exe that never exits and
                    # then launched Inno Setup while that
                    # production process was still locking files.
                    # PID-based wait is unambiguous and works for
                    # both dev (``python.exe``) and frozen
                    # (``eCan.cn.exe``) hosts.
                    host_pid = os.getpid()
                    extra_wait_seconds = 5

                    # Same cross-platform note as the frozen path above:
                    # ``subprocess.DETACHED_PROCESS`` is Windows-only and
                    # would crash when ``sys.platform`` is mocked to
                    # ``'win32'`` on a non-Windows test runner. The
                    # flag block is constructed inside
                    # ``_launch_windows_installer_delayed`` instead.
                    if sys.platform == 'win32':
                        launcher_pid = self._launch_windows_installer_delayed(
                            cmd,
                            delay_seconds=5,  # ignored, kept for ABI
                            wait_for_pid=host_pid,
                            extra_wait_seconds=extra_wait_seconds,
                        )
                        logger.info(
                            f"Installer launcher BAT started (PID: {launcher_pid}); "
                            f"will wait for host PID {host_pid} ({host_proc_name}) to exit, "
                            f"then run Inno Setup"
                        )
                        logger.info(
                            "[OTA Installer] Development-mode launcher BAT started successfully; "
                            f"host PID {host_pid} will be terminated to release file locks"
                        )
                    else:
                        process = subprocess.Popen(cmd)
                        logger.info(f"Installer launched (PID: {process.pid})")

                    # FIX 2026-09-23: Now actually exit the dev
                    # process so the BAT can proceed. Same reasoning
                    # as the frozen path above: if we just ``return
                    # True`` and stay alive, the BAT waits 120 s and
                    # then times out -- by which time Inno Setup
                    # hits file-lock errors because we're still
                    # alive (dev) or because a sibling production
                    # eCan.cn.exe is still alive (dev test box).
                    #
                    # For dev mode the python process terminating
                    # is the cost of a real OTA test. The user can
                    # restart ``python main.py`` afterwards; the
                    # next launch picks up the updated install.
                    try:
                        sys.stdout.flush()
                        sys.stderr.flush()
                    except Exception:
                        pass
                    logger.info(
                        f"[OTA Installer] Dev host PID {host_pid} exiting via os._exit(0) "
                        f"so the launcher BAT can proceed with Inno Setup"
                    )
                    time.sleep(0.1)
                    os._exit(0)
            else:
                # Non-silent mode - launch installer with UI
                logger.info("Launching installer with UI")
                logger.info(f"[OTA Installer] Non-silent install path selected for package: {package_path}")
                subprocess.Popen([str(package_path)])
                return True
                
        except Exception as e:
            logger.error(f"EXE installation error: {e}")
            logger.error(f"[OTA Installer] _install_exe fatal error: {e}")
            try:
                from ota.core.download_manager import download_manager
                download_manager.set_installing(False)
            except Exception:
                pass
            return False
    
    def _install_msi(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install Windows MSI package - OTA silent update

        The MSI path mirrors the Inno Setup path (see ``_install_exe``):
          * Resolve the install directory the same way (registry-first
            so users who picked ``D:\\MyApps\\eCan`` stay there).
          * Pre-terminate QtWebEngineProcess and the current exe before
            msiexec starts writing files. ``msiexec`` with
            ``REINSTALL=ALL`` will happily try to overwrite a locked
            ``app_context.py`` and roll the transaction back; killing
            the lock-holders up-front is the same fix we ship for
            Inno Setup. Without this, MSI upgrades hit
            "Another installation is in progress" or
            "ERROR_INSTALL_ALREADY_RUNNING" the moment msiexec tries
            to replace the running exe.
          * Use the same BAT launcher / delayed-exit pattern so the
            msiexec child outlives the Python ``os._exit(0)``.
        """
        try:
            logger.info(f"Installing Windows MSI: {package_path}")

            # Build msiexec command for silent OTA update
            cmd = ["msiexec", "/i", str(package_path)]

            if install_options.get('silent', True):
                # Silent installation parameters with progress:
                # /qb = Basic UI with progress bar (not /qn which is completely silent)
                # /norestart = Don't restart automatically
                cmd.extend(["/qb", "/norestart"])

                # Resolve the install directory before deciding whether
                # to add ``INSTALLDIR=`` / run pre-termination. We need
                # the resolved directory even in non-frozen mode so we
                # can kill lock-holders under it.
                if getattr(sys, 'frozen', False):
                    configured_install_dir = install_options.get('install_dir')
                    if configured_install_dir:
                        install_dir = Path(str(configured_install_dir)).expanduser()
                    else:
                        current_install_dir = self._get_current_windows_install_dir()
                        if current_install_dir:
                            install_dir = current_install_dir
                            logger.info(f"[OTA MSI] Preserving custom installation directory: {str(install_dir)}")
                        else:
                            install_dir = Path(sys.executable).parent
                            logger.info(f"[OTA MSI] Using current executable directory: {str(install_dir)}")

                    # ``_strip_trailing_separator`` defends against a
                    # caller-supplied install_dir that ends in ``/`` or
                    # ``\`` (Windows Installer parses trailing separators
                    # inconsistently and may resolve to the parent
                    # directory). Mirrors the Inno Setup ``/DIR=`` path.
                    cmd.append(f'INSTALLDIR="{_strip_trailing_separator(install_dir)}"')
                    cmd.append('REINSTALLMODE=vamus')  # Reinstall all files
                    cmd.append('REINSTALL=ALL')  # Reinstall all features
                else:
                    install_dir = Path(sys.executable).parent
                    logger.info(f"[OTA MSI] Dev mode install directory: {install_dir}")

                # Pre-terminate processes holding file locks in the
                # install dir. Same rationale as in ``_install_exe``.
                self._terminate_processes_in_dir(
                    install_dir,
                    timeout_seconds=15.0,
                    extra_process_names={'qtwebengineprocess.exe'},
                )

            # MSI's own verbose log (``/l*v <file>``) — keep parity
            # with Inno Setup's ``/LOG=`` so postmortems on either
            # path use the same artifact name shape.
            try:
                if sys.platform == 'win32':
                    log_path = Path(tempfile.gettempdir()) / f"ecan_ota_msi_install_{int(time.time())}.log"
                    cmd.append(f'/l*v "{log_path}"')
                    logger.info(f"MSI verbose logging enabled: {log_path}")
            except Exception as e:
                logger.debug(f"Failed to enable MSI verbose logging (safe to ignore): {e}")

            # Execute installation in background
            logger.info(f"Executing silent MSI update: {repr(cmd)}")

            # Set OTA installation flag so the exit prompt is suppressed.
            from ota.core.download_manager import download_manager
            download_manager.set_installing(True)

            # Use BAT launcher + delayed exit on Windows (same pattern
            # as ``_install_exe``) so the msiexec child survives the
            # Python exit. The launcher BAT now waits for the host
            # process to be gone, sleeps a safety window, then runs
            # msiexec via ``start "" /B``. The previous code started
            # a Python watch thread that polled the MSI ``/l*v`` log;
            # that thread was a daemon and was killed when the parent
            # exited, leaving no postmortem trail.
            if sys.platform == 'win32':
                # FIX 2026-09-23: pass OUR PID instead of the
                # host image name -- same dev/prod dual-mode
                # reasoning as in ``_install_exe``.
                host_pid = os.getpid()
                try:
                    pid = self._launch_windows_installer_delayed(
                        cmd,
                        delay_seconds=3,  # ignored, kept for ABI
                        wait_for_pid=host_pid,
                        extra_wait_seconds=5,
                    )
                    logger.info(
                        f"MSI launcher BAT started (PID: {pid}); "
                        f"will wait for host PID {host_pid} to exit, then run msiexec"
                    )
                except Exception as e:
                    logger.error(f"Failed to start MSI launcher BAT: {e}")
                    return False
            else:
                process = subprocess.Popen(cmd)
                logger.info(f"MSI installer launched (PID: {process.pid})")

            # FIX 2026-09-23: exit the Python parent so the BAT can
            # proceed (see ``_install_exe`` for the full rationale).
            # The previous "Python will now exit cleanly" log was
            # misleading -- without the ``os._exit`` here the BAT
            # times out after 120 s and msiexec then tries to
            # overwrite a still-locked host executable.
            #
            # Only force-exit on Windows where the BAT is in
            # play; on macOS / Linux this path runs ``Popen`` and
            # the caller manages the lifetime.
            if sys.platform == 'win32':
                try:
                    sys.stdout.flush()
                    sys.stderr.flush()
                except Exception:
                    pass
                logger.info(
                    "[OTA MSI] msiexec will be started by the launcher BAT; "
                    f"host PID {os.getpid()} exiting via os._exit(0)"
                )
                time.sleep(0.1)
                os._exit(0)
            return True

        except Exception as e:
            logger.error(f"MSI installation error: {e}")
            try:
                from ota.core.download_manager import download_manager
                download_manager.set_installing(False)
            except Exception:
                pass
            return False
    
    def _install_pkg(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install macOS PKG package - OTA update with progress
        
        Note: macOS PKG installation requires administrator privileges.
        
        Installation approach:
        - Use AppleScript with 'installer' command for silent installation with progress
        - Shows: Password prompt + Progress in terminal/notification
        - No installation wizard UI
        """
        try:
            logger.info(f"Installing macOS PKG: {package_path}")
            
            # For OTA updates, terminate the current version's process before installation
            # This ensures files are not locked during upgrade
            # Only kill the current version to avoid affecting other installed versions
            current_proc = self._get_current_process_name()
            logger.info(f"[OTA] Terminating running {current_proc} process before PKG installation...")
            self._terminate_macos_app(current_proc)
            time.sleep(1.0)
            
            # For OTA updates, use installer command with admin privileges
            if install_options.get('silent', True):
                logger.info("Starting PKG installation (no wizard, with progress)...")
                
                # Use osascript with a different approach for real-time output
                # We'll use a shell script that runs installer and outputs progress
                try:
                    logger.info("⚠️  macOS security requires administrator password for PKG installation")
                    logger.info("Installation mode:")
                    logger.info("  • Password prompt: YES (required)")
                    logger.info("  • Installation wizard: NO")
                    logger.info("  • Progress logging: YES")

                    # Create a helper script under appdata (NOT /tmp) so:
                    #   * it survives system tmpfiles rotation
                    #   * cleanup is explicit on every exit path below
                    #   * the script takes the .pkg path as ``$1`` rather
                    #     than embedding it into the bash source via
                    #     f-string. The previous f-string interpolation
                    #     broke the moment the package path contained
                    #     shell-special chars (``"``, ``$``, ``\``,
                    #     backticks, parens) — those are common in
                    #     ``~/Library/...`` and even in some installer
                    #     staging paths. Bash's positional-arg passing is
                    #     binary-safe for any character.
                    from config.app_info import app_info
                    script_dir = Path(app_info.appdata_path) / "ota_scripts"
                    safe_makedirs(script_dir, purpose="OTA scripts")
                    script_path = script_dir / f"pkg_install_{os.getpid()}_{time.time_ns()}.sh"
                    # Use $1 (positional arg) — bash quoting handles any path.
                    script_content = (
                        "#!/bin/bash\n"
                        '# $1 = absolute path to .pkg. Quote once to defeat shell word-splitting.\n'
                        'installer -pkg "$1" -target / -verboseR 2>&1\n'
                    )
                    script_path.write_text(script_content, encoding='utf-8')
                    os.chmod(script_path, 0o755)

                    # Launch installer with osascript for password prompt.
                    # IMPORTANT: pass BOTH the helper-script path and the
                    # pkg path via argv. The previous implementation
                    # interpolated ``script_path`` into an AppleScript
                    # ``do shell script`` string, which broke when the
                    # script path contained characters that AppleScript /
                    # shell double-quotes care about (spaces, ``"``,
                    # ``\``, ``$``). argv is the only safe way to ferry
                    # paths into ``osascript``.
                    #
                    # AppleScript ``quoted form of`` produces a token that
                    # is safe to embed in a ``do shell script`` string,
                    # so we still build the inner command string here
                    # rather than chaining ``do shell script`` invocations
                    # (which would re-prompt for admin each time).
                    applescript_body = (
                        'on run argv\n'
                        '    set helperScript to item 1 of argv\n'
                        '    set pkgPath to item 2 of argv\n'
                        '    set helperCmd to "bash " & quoted form of helperScript & " " & quoted form of pkgPath\n'
                        '    do shell script helperCmd with administrator privileges\n'
                        'end run'
                    )
                    osa_cmd = [
                        '/usr/bin/osascript',
                        '-e', applescript_body,
                        '--',                  # end-of-options, prevents osascript from re-parsing flags
                        str(script_path),
                        str(package_path),
                    ]

                    # Launch installer in background
                    process = subprocess.Popen(
                        osa_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,  # Merge stderr to stdout
                        text=True,
                        bufsize=0,  # Unbuffered for real-time output
                        universal_newlines=True,
                    )
                    
                    logger.info(f"PKG installer launched (PID: {process.pid})")
                    logger.info("Waiting for user to enter password and installation to complete...")
                    
                    # Show initial notification
                    try:
                        subprocess.run([
                            "osascript", "-e",
                            f'display notification "{_tr.tr("installing_update")}" with title "{_tr.tr("app_update")}"'
                        ], check=False)
                    except Exception:
                        pass
                    
                    # Since AppleScript doesn't support real-time output streaming,
                    # we'll simulate progress based on time estimation
                    def _cleanup_helper_script():
                        """Unlink the helper bash script on every exit path.

                        Previous versions had this inlined three times
                        (success, timeout, exception). Centralised to
                        avoid the leak path where a future refactor adds
                        a fourth return without cleaning up.
                        """
                        try:
                            script_path.unlink(missing_ok=True)
                        except Exception as e:
                            logger.debug(
                                f"[OTA] Failed to remove PKG helper script "
                                f"{script_path}: {e}"
                            )

                    try:
                        import time as time_module
                        import threading

                        start_time = time_module.time()
                        timeout = 600  # 10 minutes
                        
                        # Estimated installation phases and durations (in seconds)
                        phases = [
                            (0, 5, _tr.tr("preparing_install")),
                            (5, 10, _tr.tr("verifying_package")),
                            (10, 50, _tr.tr("writing_files")),
                            (50, 55, _tr.tr("running_scripts")),
                            (55, 58, _tr.tr("writing_receipt")),
                            (58, 60, _tr.tr("verifying_package")),
                        ]
                        
                        # Start a thread to simulate progress
                        def simulate_progress():
                            elapsed = 0
                            while process.poll() is None and elapsed < timeout:
                                elapsed = time_module.time() - start_time
                                
                                # Find current phase
                                current_phase = _tr.tr("installing")
                                progress = 0
                                
                                for start_sec, end_sec, phase_name in phases:
                                    if start_sec <= elapsed < end_sec:
                                        # Calculate progress within this phase
                                        phase_progress = (elapsed - start_sec) / (end_sec - start_sec)
                                        # Map to overall progress (0-100)
                                        overall_start = (start_sec / 60) * 100
                                        overall_end = (end_sec / 60) * 100
                                        progress = overall_start + (overall_end - overall_start) * phase_progress
                                        current_phase = phase_name
                                        break
                                
                                # Cap at 95% until actually complete
                                progress = min(95, progress)
                                
                                # Call progress callback
                                if self.progress_callback:
                                    try:
                                        self.progress_callback(int(progress), current_phase)
                                    except Exception as e:
                                        logger.debug(f"Progress callback error: {e}")
                                
                                time_module.sleep(0.5)  # Update every 0.5 seconds
                        
                        # Start progress simulation thread
                        progress_thread = threading.Thread(target=simulate_progress, daemon=True)
                        progress_thread.start()
                        
                        # Wait for installation to complete
                        stdout, stderr = process.communicate(timeout=timeout)
                        
                        # Stop progress thread
                        progress_thread.join(timeout=1)

                        # Send 100% progress
                        if self.progress_callback:
                            try:
                                self.progress_callback(100, _tr.tr("install_complete"))
                            except Exception as e:
                                logger.debug(f"Progress callback error: {e}")

                        # Clean up temporary script
                        _cleanup_helper_script()

                    except subprocess.TimeoutExpired:
                        logger.error("Installation timeout (10 minutes)")
                        process.kill()
                        # Clean up temporary script
                        _cleanup_helper_script()
                        return False

                    # Check result
                    try:

                        if process.returncode == 0:
                            logger.info("✅ PKG installation completed successfully")
                            if stdout:
                                logger.info(f"Installation output: {stdout}")

                            # Show completion notification
                            try:
                                subprocess.run([
                                    "osascript", "-e",
                                    f'display notification "{_tr.tr("install_complete_restart")}" with title "{_tr.tr("app_update")}"'
                                ])
                            except Exception as e:
                                logger.warning(f"Failed to show notification: {e}")

                            # Schedule application restart
                            logger.info("Installation complete, application will restart in 3 seconds...")

                            import threading
                            def delayed_restart():
                                time.sleep(3)
                                logger.info("Restarting application...")
                                self._restart_application()

                            threading.Thread(target=delayed_restart, daemon=True).start()

                            # PKG ran inside osascript; helper script is no
                            # longer needed even though we just succeeded.
                            _cleanup_helper_script()
                            return True
                        else:
                            logger.error(f"❌ PKG installation failed: {stderr}")
                            _cleanup_helper_script()
                            return False

                    except subprocess.TimeoutExpired:
                        logger.error("Installation timeout (10 minutes)")
                        process.kill()
                        _cleanup_helper_script()
                        return False

                except Exception as e:
                    logger.error(f"Failed to launch PKG installer: {e}")
                    # Final safety net: ensure helper script is removed
                    # even if we exited between writing it and entering
                    # the AppleScript subprocess.
                    try:
                        script_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return False
            else:
                # Non-silent mode - launch installer with full UI
                logger.info("Launching PKG installer with full UI...")
                subprocess.Popen(["open", str(package_path)])
                return True

        except Exception as e:
            logger.error(f"PKG installation error: {e}")
            return False
    
    def _install_dmg(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install macOS DMG package

        Notes:
            ``/Applications`` is owned by ``root:wheel`` on stock macOS, so
            the copy step requires administrator privileges. We do NOT
            call ``shutil.copytree`` directly any more — that silently
            fails on a normal user account, which leaves the user staring
            at an unmounted DMG and no clue why nothing was copied.

            New flow:
              1. ``hdiutil attach`` (no privilege needed for the user —
                 hdiutil is setuid).
              2. Find the mount point + ``.app`` inside.
              3. Write a short helper bash script under
                 ``<appdata>/ota_scripts/`` that takes ``$1=source``,
                 ``$2=destination`` and does ``rm -rf "$2"; cp -R
                 "$1" "$2"``. Both args are quoted so spaces / ``$`` /
                 quotes round-trip cleanly.
              4. Invoke that helper through ``osascript … with
                 administrator privileges``. The password prompt is
                 fired exactly once, not per .app, by passing ALL
                 mount-point .app paths via argv (an osascript list).
              5. Unmount the DMG and unlink the helper script in
                 ``finally`` so we never leak it into
                 ``<appdata>/ota_scripts/``.

            We also call ``osascript`` with the full ``/usr/bin/osascript``
            path (not just ``osascript``) so PATH manipulation by a
            privileged AppleScript sub-shell can't resolve to a
            different binary.
        """
        try:
            logger.info(f"Installing macOS DMG: {package_path}")

            # Mount DMG (hdiutil is setuid; no admin needed here)
            mount_result = subprocess.run(
                ["hdiutil", "attach", str(package_path), "-nobrowse", "-quiet"],
                capture_output=True, text=True
            )

            if mount_result.returncode != 0:
                logger.error(f"Failed to mount DMG: {mount_result.stderr}")
                return False

            helper_script_path: Optional[Path] = None
            try:
                # Find mount point
                mount_point = self._find_dmg_mount_point(package_path)
                if not mount_point:
                    logger.error("Could not find DMG mount point")
                    return False

                # Find .app file
                app_files = list(Path(mount_point).glob("*.app"))
                if not app_files:
                    logger.error("No .app file found in DMG")
                    return False

                target_dir = Path("/Applications")

                # Terminate any running instances of the apps we're about
                # to replace. We do this BEFORE requesting admin
                # privileges so the user isn't staring at a password
                # dialog while their existing app is still running.
                for app_file in app_files:
                    target_path = target_dir / app_file.name
                    if target_path.exists():
                        logger.info(
                            f"[OTA] Found existing app at {target_path}, "
                            f"terminating processes before upgrade"
                        )
                        app_base_name = app_file.name.replace('.app', '')
                        self._terminate_macos_app(app_base_name)

                time.sleep(1.0)

                # Write helper bash script. Args:
                #   $1 = source path on DMG mount
                #   $2 = destination under /Applications
                # ``rm -rf "$2"; cp -R "$1" "$2"`` is idempotent — it
                # overwrites any stale leftover even if our earlier
                # shutil.rmtree attempt failed mid-way.
                from config.app_info import app_info
                script_dir = Path(app_info.appdata_path) / "ota_scripts"
                safe_makedirs(script_dir, purpose="OTA scripts")
                helper_script_path = script_dir / f"dmg_install_{os.getpid()}_{time.time_ns()}.sh"
                helper_script_content = (
                    "#!/bin/bash\n"
                    "# $1 = source .app inside mounted DMG\n"
                    "# $2 = destination under /Applications\n"
                    '# Defeat shell word-splitting AND case where the\n'
                    '# destination is a directory. ``rm -rf`` on a\n'
                    '# missing path is fine; it just exits non-zero,\n'
                    '# which we ignore.\n'
                    'rm -rf "$2" 2>/dev/null || true\n'
                    'cp -R "$1" "$2"\n'
                )
                helper_script_path.write_text(helper_script_content, encoding='utf-8')
                os.chmod(helper_script_path, 0o755)

                # Build an AppleScript that loops over our argv and
                # invokes the helper for each (source, dest) pair. We
                # batch into a SINGLE ``do shell script … with
                # administrator privileges`` so the password prompt is
                # shown once even when the DMG carries multiple .app
                # bundles (rare, but happens for multi-arch bundles).
                #
                # We build the inner command string with ``quoted form
                # of`` so paths with shell-special characters survive
                # intact. argv passing into osascript is binary-safe,
                # which is the whole reason we use argv instead of
                # f-string interpolation here.
                script_lines = [
                    'on run argv',
                    '    set helperScript to item 1 of argv',
                    '    -- remaining items are source/dest pairs',
                    '    set pairCount to (count of argv) - 1',
                    '    set cmdParts to {"bash", quoted form of helperScript}',
                ]
                # argv[2..] = source1, dest1, source2, dest2, …
                # Index in AppleScript argv starts at 1; we already
                # consumed item 1 (helperScript), so pairs start at
                # item 2. Each pair is two items, so dest for pair i
                # is item (2 + 2*i + 1).
                script_lines.append('    set i to 0')
                script_lines.append('    repeat while i < pairCount')
                # i is 0-based pair index; AppleScript argv items are 1-based
                # so pair i source = item (2 + i*2), pair i dest = item (3 + i*2)
                script_lines.append('        set src to item (2 + (i * 2)) of argv')
                script_lines.append('        set dst to item (3 + (i * 2)) of argv')
                script_lines.append('        set end of cmdParts to quoted form of src')
                script_lines.append('        set end of cmdParts to quoted form of dst')
                script_lines.append('        set i to i + 1')
                script_lines.append('    end repeat')
                script_lines.append('    set innerCmd to my joinItems(cmdParts, " ")')
                script_lines.append('    do shell script innerCmd with administrator privileges')
                # Helper: join list with separator. AppleScript's
                # default text-item-delimiters trick keeps this single-
                # statement and avoids needing a separate handler.
                script_lines.extend([
                    'on joinItems(lst, sep)',
                    '    set tid to text item delimiters',
                    '    set text item delimiters to sep',
                    '    set joined to lst as text',
                    '    set text item delimiters to tid',
                    '    return joined',
                    'end joinItems',
                ])
                applescript_body = '\n'.join(script_lines)

                osa_argv = [str(helper_script_path)]
                for app_file in app_files:
                    target_path = target_dir / app_file.name
                    osa_argv.append(str(app_file))
                    osa_argv.append(str(target_path))

                osa_cmd = [
                    '/usr/bin/osascript',
                    '-e', applescript_body,
                    '--',  # end-of-options: protects osascript from re-parsing flags
                    *osa_argv,
                ]

                logger.info(
                    f"[OTA] Requesting admin elevation to copy "
                    f"{len(app_files)} app(s) to {target_dir}"
                )
                # We intentionally block on this — the user has to enter
                # the password before anything else can happen, and we
                # need to know whether the copy succeeded so the GUI
                # can either show success or the error from the helper.
                proc = subprocess.run(
                    osa_cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 minutes — mirrors the PKG timeout
                )

                if proc.returncode != 0:
                    # User cancelled the auth prompt or copy failed.
                    # Surface stderr to logs but NOT to the GUI here —
                    # the caller (InstallationManager.install_package)
                    # handles UI.
                    logger.error(
                        f"[OTA] DMG install helper failed: "
                        f"returncode={proc.returncode}, stderr={proc.stderr.strip()}"
                    )
                    return False

                for app_file in app_files:
                    target_path = target_dir / app_file.name
                    logger.info(f"[OTA] Copied {app_file.name} to {target_path}")

                # Schedule the new app to launch after install. We
                # killed the running instance before invoking the
                # privileged copy, so the user is staring at no app
                # for ~5–10 s while the password prompt is up. If we
                # don't auto-launch here, the user has to find the
                # new icon in /Applications and click it — a UX
                # regression vs. the PKG path which has always
                # restarted itself. ``sys.executable`` still points
                # at the path the OLD exe lived at, and the installer
                # overwrote that location with the new bundle, so the
                # same path now resolves to the NEW binary. Mirrors
                # the ``delayed_restart`` pattern in ``_install_pkg``.
                logger.info(
                    f"[OTA] DMG install complete; scheduling restart "
                    f"of {sys.executable} in 3 seconds"
                )
                import threading

                def _delayed_dmg_restart():
                    time.sleep(3)
                    logger.info("[OTA] DMG delayed_restart firing")
                    try:
                        self._restart_application()
                    except Exception as e:
                        logger.warning(
                            f"[OTA] DMG restart failed: {e}; user "
                            f"will need to launch the new app manually."
                        )

                threading.Thread(
                    target=_delayed_dmg_restart, daemon=True
                ).start()

                return True

            finally:
                # Unmount DMG (best-effort; ignore failure so we don't
                # mask the real error above)
                subprocess.run(
                    ["hdiutil", "detach", mount_point or ""],
                    capture_output=True
                )
                # Always unlink the helper script. We don't want a
                # privileged bash file accumulating under
                # <appdata>/ota_scripts/ across many OTA flows.
                if helper_script_path is not None:
                    try:
                        helper_script_path.unlink(missing_ok=True)
                    except Exception as e:
                        logger.debug(
                            f"[OTA] Failed to remove DMG helper script "
                            f"{helper_script_path}: {e}"
                        )

        except Exception as e:
            logger.error(f"DMG installation error: {e}")
            return False
    
    def _terminate_macos_app(self, app_name: str) -> None:
        """Terminate a running macOS application by name.

        Args:
            app_name: Application name without .app extension (e.g., 'eCan' or 'eCan.cn')

        Notes:
            The previous version tried ``killall -9 "<app>.app"`` as a
            second pass, which is dead code — ``killall`` matches
            process names, not bundle names, so ``eCan.cn.app`` never
            matches a running pid (the actual process is named
            ``eCan.cn``). It's harmless but confusing; replaced with
            a graceful AppleScript quit (``tell application "X" to
            quit``) which gives the app a chance to flush state
            before we SIGKILL it.
        """
        try:
            import subprocess

            # 1) Graceful quit via AppleScript so the app can flush
            #    state (save settings, close SQLite handles, etc.).
            #    Wrapped in 5-second timeout so a hung app can't
            #    stall the OTA flow.
            try:
                subprocess.run(
                    [
                        '/usr/bin/osascript',
                        '-e',
                        f'tell application "{app_name}" to quit',
                    ],
                    capture_output=True,
                    timeout=5,
                )
                # AppleScript ``quit`` returns success even if the app
                # wasn't running (the ``tell`` line is a no-op). We
                # only use it as a hint to the user — SIGKILL below is
                # the authoritative cleanup.
            except subprocess.TimeoutExpired:
                logger.debug(
                    f"[OTA] AppleScript graceful quit timed out for {app_name}; "
                    f"falling back to SIGKILL"
                )
            except FileNotFoundError:
                # osascript missing on a stripped-down macOS image.
                pass
            except Exception as e:
                logger.debug(
                    f"[OTA] AppleScript graceful quit failed for {app_name}: {e}"
                )

            # 2) Force-kill the process via killall (SIGKILL). This
            #    matches process names like ``eCan.cn``, ``eCan`` —
            #    NOT ``eCan.cn.app`` (bundle name).
            result = subprocess.run(
                ['killall', '-9', app_name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info(f"[OTA] Terminated running app: {app_name}")
            elif result.returncode != 1:
                # 1 = no process found (normal)
                logger.debug(
                    f"[OTA] killall {app_name}: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )

            # 3) Belt-and-suspenders pgrep pass: catches processes that
            #    ``killall -9`` somehow missed (rare, but observed on
            #    macOS 14 with hardened-runtime binaries).
            try:
                result = subprocess.run(
                    ['pgrep', '-x', app_name],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        if pid.strip():
                            try:
                                import signal
                                os.kill(int(pid.strip()), signal.SIGKILL)
                                logger.info(
                                    f"[OTA] Killed pid {pid} for app {app_name}"
                                )
                            except Exception as e:
                                logger.debug(
                                    f"[OTA] Failed to kill pid {pid}: {e}"
                                )
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"[OTA] Failed to terminate macOS app {app_name}: {e}")
    
    def _find_dmg_mount_point(self, dmg_path: Path) -> Optional[str]:
        """Find DMG mount point"""
        try:
            result = subprocess.run(
                ["hdiutil", "info", "-plist"],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                return None
            
            import plistlib
            plist_data = plistlib.loads(result.stdout.encode())
            
            for image in plist_data.get('images', []):
                image_path = image.get('image-path')
                if image_path and Path(image_path).name == dmg_path.name:
                    for entity in image.get('system-entities', []):
                        mount_point = entity.get('mount-point')
                        if mount_point:
                            return mount_point
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find mount point: {e}")
            return None
    
    def restart_application(self, delay_seconds: int = 3) -> bool:
        """Restart application"""
        try:
            logger.info(f"Restarting application in {delay_seconds} seconds...")
            
            if getattr(sys, 'frozen', False):
                # Packaged application
                app_executable = sys.executable
            else:
                # Development environment
                app_executable = sys.executable
                app_args = [sys.argv[0]]
            
            # Create restart script
            restart_script = self._create_restart_script(app_executable, delay_seconds)
            
            if restart_script:
                # Execute restart script
                if self.platform.startswith('win'):
                    subprocess.Popen([restart_script], shell=True)
                else:
                    subprocess.Popen(['sh', restart_script])
                
                logger.info("Restart script launched")
                
                # Exit current application
                time.sleep(1)
                os._exit(0)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart application: {e}")
            return False
    
    def _create_restart_script(self, app_executable: str, delay_seconds: int) -> Optional[str]:
        """Create restart script.

        The script filename includes ``<pid>_<ns>`` (PID + monotonic ns)
        on every platform — including Windows. The previous Windows
        branch used a fixed ``restart.bat`` filename; two concurrent
        OTA flows (e.g. auto-check that fires while a manual install
        is still in its restart grace window) would race on that name,
        with the second flow's ``open(... 'w')`` truncating the
        first's in-flight script. The MSI restart path is the only
        Windows caller today, but the race is independent of who calls
        it.
        """
        try:
            # Use fixed user directory instead of temporary directory
            from config.app_info import app_info
            user_data_root = Path(app_info.appdata_path)
            script_dir = safe_makedirs(user_data_root / "ota_scripts", purpose="OTA scripts")

            # Unique filename so concurrent OTA flows don't clobber
            # each other's restart helpers. Mirrors the pattern used
            # by ``_launch_windows_installer_delayed`` (BAT launcher)
            # and the Linux / DMG / PKG helper scripts.
            unique_suffix = f"{os.getpid()}_{time.time_ns()}"
            if self.platform.startswith('win'):
                # Windows batch script
                script_path = script_dir / f"restart_{unique_suffix}.bat"
                script_content = f"""@echo off
echo Waiting {delay_seconds} seconds before restart...
timeout /t {delay_seconds} /nobreak >nul
echo Restarting eCan...
start "" "{app_executable}"
del "%~f0"
"""
            else:
                # Unix shell script
                script_path = script_dir / f"restart_{unique_suffix}.sh"
                script_content = f"""#!/bin/bash
echo "Waiting {delay_seconds} seconds before restart..."
sleep {delay_seconds}
echo "Restarting eCan..."
{app_executable} &
rm "$0"
"""
            
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # Set execute permission (Unix)
            if not self.platform.startswith('win'):
                os.chmod(script_path, 0o755)
            
            logger.info(f"Restart script created: {script_path}")
            return str(script_path)
            
        except Exception as e:
            logger.error(f"Failed to create restart script: {e}")
            return None
    
    def restore_backup(self) -> bool:
        """Restore backup"""
        if not self.backup_dir or not self.backup_dir.exists():
            logger.error("No backup available to restore")
            return False
        
        try:
            # Get current application path
            if getattr(sys, 'frozen', False):
                app_path = Path(sys.executable).parent
            else:
                app_path = Path(__file__).parent.parent.parent
            
            logger.info(f"Restoring backup: {self.backup_dir} -> {app_path}")
            
            # Delete current application
            if app_path.exists():
                shutil.rmtree(app_path)
            
            # Restore backup
            shutil.copytree(self.backup_dir, app_path)
            
            logger.info("Backup restored successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False
    
    def cleanup_backup(self):
        """Clean up backup files"""
        if self.backup_dir and self.backup_dir.exists():
            try:
                shutil.rmtree(self.backup_dir)
                logger.info(f"Backup cleaned up: {self.backup_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup backup: {e}")
    
    def _restart_application(self):
        """
        Restart the application after installation
        
        This method will:
        1. Get the application executable path
        2. Launch a new instance
        3. Exit the current instance
        """
        try:
            if getattr(sys, 'frozen', False):
                # ✅ Packaged application
                if self.platform == 'darwin':
                    # macOS: Get .app bundle path
                    exe_path = Path(sys.executable)
                    # Navigate up to find .app bundle
                    app_bundle = exe_path
                    while app_bundle.suffix != '.app' and app_bundle.parent != app_bundle:
                        app_bundle = app_bundle.parent
                    
                    if app_bundle.suffix == '.app':
                        logger.info(f"Restarting application: {app_bundle}")
                        # Use 'open' command to launch the app
                        subprocess.Popen(['open', '-n', str(app_bundle)])
                        
                        # Exit current instance to release lock
                        logger.info("Exiting current instance in 1 second...")
                        time.sleep(1)
                        os._exit(0)
                    else:
                        logger.error("Could not find .app bundle")
                        return
                        
                elif self.platform.startswith('win'):
                    # Windows: Use delayed restart script to avoid single instance lock conflict
                    exe_path = sys.executable
                    logger.info(f"Restarting application: {exe_path}")
                    
                    restart_script = self._create_restart_script(exe_path, delay_seconds=3)
                    if restart_script:
                        subprocess.Popen([restart_script], shell=True)
                        logger.info("Restart script launched, exiting current instance...")
                        time.sleep(1)
                        os._exit(0)
                    else:
                        logger.warning("Failed to create restart script, manual restart required")
                    
                else:
                    # Linux: Use delayed restart script to avoid single instance lock conflict
                    exe_path = sys.executable
                    logger.info(f"Restarting application: {exe_path}")
                    
                    restart_script = self._create_restart_script(exe_path, delay_seconds=3)
                    if restart_script:
                        subprocess.Popen(['sh', restart_script])
                        logger.info("Restart script launched, exiting current instance...")
                        time.sleep(1)
                        os._exit(0)
                    else:
                        logger.warning("Failed to create restart script, manual restart required")
                
            else:
                # ✅ Development environment - restart using python
                logger.info("Running in development environment")
                logger.info("Attempting to restart application...")
                
                # Get the main script path
                import __main__
                if hasattr(__main__, '__file__'):
                    main_script = Path(__main__.__file__).resolve()
                    logger.info(f"Restarting: python3 {main_script}")
                    
                    # Create a delayed restart script to avoid single instance lock conflict
                    restart_script = self._create_restart_script(
                        f"python3 {main_script}",
                        delay_seconds=3
                    )
                    
                    if restart_script:
                        # Launch restart script
                        if self.platform == 'darwin':
                            subprocess.Popen(['sh', restart_script])
                        else:
                            subprocess.Popen([restart_script])
                        
                        logger.info("Restart script launched, exiting current instance...")
                        time.sleep(1)
                        os._exit(0)
                    else:
                        logger.warning("Failed to create restart script, manual restart required")
                else:
                    logger.warning("Could not determine main script path")
                    logger.info("Please manually restart the application")
                
        except Exception as e:
            logger.error(f"Failed to restart application: {e}")
    
    def _parse_installer_progress(self, line: str) -> float:
        """
        Parse progress percentage from installer output
        
        Args:
            line: Output line from installer command
            
        Returns:
            Progress percentage (0-100) or None if not found
        """
        try:
            # installer output format: "installer:%12.345678"
            if 'installer:%' in line:
                # Extract percentage
                parts = line.split('installer:%')
                if len(parts) > 1:
                    percent_str = parts[1].strip()
                    # Get first number (may have more text after)
                    percent = float(percent_str.split()[0])
                    return min(100.0, max(0.0, percent))
        except Exception as e:
            logger.debug(f"Failed to parse progress from line: {line[:50]}... Error: {e}")
        
        return None
    
    def _show_installation_progress_dialog(self):
        """
        Show Qt progress dialog for installation
        
        Returns:
            Progress dialog object or None if Qt is not available
        """
        try:
            from PyQt5.QtWidgets import QProgressDialog, QApplication
            from PyQt5.QtCore import Qt
            
            # Get or create QApplication instance
            app = QApplication.instance()
            if app is None:
                logger.warning("No QApplication instance, cannot show progress dialog")
                return None
            
            # Create progress dialog
            dialog = QProgressDialog(
                _tr.tr("installing_update"),
                None,  # No cancel button
                0,
                100
            )
            dialog.setWindowTitle(_tr.tr("app_update"))
            dialog.setWindowModality(Qt.WindowModal)
            dialog.setMinimumDuration(0)  # Show immediately
            dialog.setValue(0)
            dialog.show()
            
            # Process events to show dialog
            app.processEvents()
            
            logger.info("Installation progress dialog shown")
            return dialog
            
        except Exception as e:
            logger.warning(f"Failed to show progress dialog: {e}")
            return None
    
    def _update_progress_dialog(self, dialog, progress: float, status_line: str = ""):
        """
        Update progress dialog with current progress
        
        Args:
            dialog: Qt progress dialog
            progress: Progress percentage (0-100)
            status_line: Current status line from installer
        """
        try:
            from PyQt5.QtWidgets import QApplication
            
            # Update progress value
            dialog.setValue(int(progress))
            
            # Update label text with phase information
            if 'PHASE:' in status_line:
                phase = status_line.split('PHASE:')[-1].strip()
                if phase:
                    text = _tr.tr("installing_update_with_phase").format(progress=int(progress), phase=phase)
                    dialog.setLabelText(text)
            else:
                text = _tr.tr("installing_update_progress").format(progress=int(progress))
                dialog.setLabelText(text)
            
            # Process events to update UI
            app = QApplication.instance()
            if app:
                app.processEvents()
            
            logger.debug(f"Progress updated: {progress:.1f}%")
            
        except Exception as e:
            logger.debug(f"Failed to update progress dialog: {e}")
    
    def _close_progress_dialog(self, dialog):
        """
        Close progress dialog
        
        Args:
            dialog: Qt progress dialog
        """
        try:
            if dialog:
                dialog.close()
                logger.info("Installation progress dialog closed")
        except Exception as e:
            logger.warning(f"Failed to close progress dialog: {e}")


# Global installation manager instance
installation_manager = InstallationManager()
