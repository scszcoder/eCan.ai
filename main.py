#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import traceback
import subprocess
import time
import warnings

# ============================================================================
# Suppress known third-party deprecation/compatibility warnings
# These are library issues (langchain, pydantic) not fixable in our code
# ============================================================================
warnings.filterwarnings("ignore", message=".*Pydantic V1.*Python 3.14.*", category=UserWarning)

# ============================================================================
# CRITICAL: Force UTF-8 encoding for all file operations (Windows compatibility)
# This must be set BEFORE any imports to prevent GBK encoding errors
# ============================================================================
os.environ['PYTHONUTF8'] = '1'

# ============================================================================
# CRITICAL: Configure browser_use timeouts BEFORE any browser_use imports
# These environment variables must be set before browser_use.browser.events is imported
# ============================================================================
os.environ.setdefault('TIMEOUT_ScreenshotEvent', '30')  # Increase from 8s to 30s
os.environ.setdefault('TIMEOUT_BrowserStartEvent', '90')  # Increase from 30s to 90s for slow browser initialization

# ============================================================================
# Increase Python recursion limit (general safety margin)
# ============================================================================
sys.setrecursionlimit(3000)

# ============================================================================
# CRITICAL: Patch LangGraph checkpoint serializer to handle ormsgpack TypeError.
# ormsgpack has a hardcoded recursion limit of 255 (in Rust). When LangGraph
# state contains deeply nested Pydantic models (browser sessions, MCP clients,
# LangChain messages), ormsgpack.packb raises TypeError("Recursion limit reached")
# which is NOT caught by the existing MsgpackEncodeError fallback. This patch
# extends the catch to include TypeError so it falls back to pickle.
# ============================================================================
def _patch_langgraph_checkpoint_serializer():
    """Patch LangGraph's checkpoint serializer to handle ormsgpack recursion limit.

    ormsgpack has a hardcoded Rust-level recursion limit of 255. When the
    LangGraph state contains deeply nested Pydantic models (browser sessions,
    MCP clients, LangChain messages), packb() raises TypeError("Recursion limit
    reached"). ormsgpack.MsgpackEncodeError IS TypeError (same class in the MRO),
    so the existing except clause catches it — but the original code only falls
    back to pickle when self.pickle_fallback is True (default: False).

    This patch forces pickle fallback for recursion-limit errors even when
    pickle_fallback is False. InMemorySaver runs same-process, so pickle is safe.
    """
    try:
        from langgraph.checkpoint.serde import jsonplus
        import ormsgpack
        import pickle
        import logging as _logging

        _patch_log = _logging.getLogger("eCan")

        _original_loads_typed = jsonplus.JsonPlusSerializer.loads_typed

        def _patched_dumps_typed(self, obj):
            if isinstance(obj, bytes):
                return "bytes", obj
            elif isinstance(obj, bytearray):
                return "bytearray", obj
            else:
                try:
                    return "msgpack", jsonplus._msgpack_enc(obj)
                except ormsgpack.MsgpackEncodeError as exc:
                    # ormsgpack.MsgpackEncodeError IS TypeError, so this
                    # catches both encoding errors and recursion-limit errors.
                    if "Recursion limit" in str(exc):
                        _patch_log.debug(
                            "[CheckpointPatch] ormsgpack recursion limit hit, "
                            "falling back to pickle"
                        )
                        return "pickle", pickle.dumps(obj)
                    if self.pickle_fallback:
                        return "pickle", pickle.dumps(obj)
                    raise exc

        def _patched_loads_typed(self, data):
            type_, data_ = data
            # Handle pickle even when pickle_fallback is False
            if type_ == "pickle":
                return pickle.loads(data_)
            return _original_loads_typed(self, data)

        jsonplus.JsonPlusSerializer.dumps_typed = _patched_dumps_typed
        jsonplus.JsonPlusSerializer.loads_typed = _patched_loads_typed
    except Exception:
        pass  # langgraph not installed or API changed — skip silently

_patch_langgraph_checkpoint_serializer()

# ============================================================================
# CRITICAL: Force UTF-8 encoding for browser-use file operations
# Patches browser-use to use UTF-8 instead of system default encoding (GBK on Windows)
# Prevents 'gbk' codec errors when handling emoji/Unicode characters
# ============================================================================
def _patch_browser_use_to_utf8():
    """
    Apply browser-use GBK encoding fix after imports are complete.
    
    Patches browser-use file operations to force UTF-8 encoding,
    preventing 'gbk' codec errors when handling emoji and Unicode characters.
    
    Error example: 'gbk' codec can't encode character '\U0001f339' (🌹)
    Root cause: file_path.write_text() uses system default encoding (GBK on Windows)
    """
    try:
        from browser_use.filesystem.file_system import BaseFile
        from pathlib import Path
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        # Patched sync method with UTF-8 encoding
        def patched_sync_to_disk_sync(self, path: Path) -> None:
            """Patched version that forces UTF-8 encoding."""
            file_path = path / self.full_name
            file_path.write_text(self.content, encoding='utf-8')
        
        # Patched async method with UTF-8 encoding
        async def patched_sync_to_disk(self, path: Path) -> None:
            """Patched async version that forces UTF-8 encoding."""
            file_path = path / self.full_name
            with ThreadPoolExecutor() as executor:
                await asyncio.get_event_loop().run_in_executor(
                    executor, 
                    lambda: file_path.write_text(self.content, encoding='utf-8')
                )
        
        # Apply patches
        BaseFile.sync_to_disk_sync = patched_sync_to_disk_sync
        BaseFile.sync_to_disk = patched_sync_to_disk
        
        print("[GBK_FIX] ✅ Successfully patched browser-use file operations to use UTF-8 encoding")
        
    except ImportError:
        # browser-use not installed or not imported yet - skip silently
        pass
    except Exception as e:
        # Non-critical - log but continue
        print(f"[GBK_FIX] Warning: Could not apply browser-use encoding fix: {e}")


def _wait_for_port_ready(port: int, host: str = '127.0.0.1', timeout_s: float = 8.0) -> bool:
    start_ts = time.time()
    while (time.time() - start_ts) < timeout_s:
        try:
            import socket
            sock = socket.create_connection((host, int(port)), timeout=0.3)
            sock.close()
            return True
        except Exception:
            time.sleep(0.05)
    return False
# Note: _apply_browser_use_encoding_fix() will be called after GUI imports

# ============================================================================
# CRITICAL: Patch platform._syscmd_ver BEFORE any imports that use it
# This prevents the 'ver' command from being called, which causes window flashes
# ============================================================================
if sys.platform == 'win32':
    try:
        import platform

        def _syscmd_ver_no_console(system='', release='', version='', csd='', ptype=''):
            """Replacement for platform._syscmd_ver that doesn't call 'ver' command."""
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    r'SOFTWARE\Microsoft\Windows NT\CurrentVersion')
                try:
                    major = winreg.QueryValueEx(key, 'CurrentMajorVersionNumber')[0]
                    minor = winreg.QueryValueEx(key, 'CurrentMinorVersionNumber')[0]
                    build = winreg.QueryValueEx(key, 'CurrentBuildNumber')[0]
                    version = f'{major}.{minor}.{build}'
                except (OSError, ValueError):
                    version = winreg.QueryValueEx(key, 'CurrentVersion')[0]
                    build = winreg.QueryValueEx(key, 'CurrentBuildNumber')[0]
                    version = f'{version}.{build}'
                finally:
                    winreg.CloseKey(key)
                return system, release, version, csd, ptype
            except Exception:
                return system, release, version, csd, ptype

        platform._syscmd_ver = _syscmd_ver_no_console
    except Exception:
        pass

# Configure UTF-8 encoding for Windows console to prevent UnicodeEncodeError
# This must be done before any print statements that might contain Unicode characters
if sys.platform == 'win32':
    try:
        # Try to set stdout and stderr to UTF-8 encoding
        if sys.stdout.encoding != 'utf-8':
            # Reconfigure stdout/stderr to use UTF-8
            import io
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        # If reconfiguration fails, continue anyway
        # The emoji characters have been replaced with ASCII-safe alternatives
        pass

# ============================================================================
# CRITICAL: Worker Script Execution - MUST be at the very top!
# This allows child processes (like LightRAG server) to run their scripts
# WITHOUT loading the entire eCan application (saves ~200-300 MB memory)
# ============================================================================
if __name__ == '__main__' and os.getenv('ECAN_RUN_SCRIPT'):
    # This is a worker process - execute the script and let it run to completion
    # DO NOT import anything else before this check!
    run_script = os.getenv('ECAN_RUN_SCRIPT')
    print(f"[Worker Process] Executing script: {run_script}")
    print("[Worker Process] Skipping main application imports to save memory...")

    try:
        with open(run_script, 'r', encoding='utf-8') as f:
            code = f.read()
        exec(compile(code, run_script, 'exec'), {'__name__': '__main__'})
        # Script completed successfully - let it continue running (e.g., uvicorn server)
        # DO NOT sys.exit(0) here as it would kill long-running servers
    except Exception as e:
        print(f"[Worker Process] Script execution failed: {e}")
        traceback.print_exc()
        sys.exit(1)

# ============================================================================
# Main Application Code (only runs if not a worker process)
# ============================================================================

# Diagnostic hooks (enabled only when EC_DIAG=1)
IS_WIN = sys.platform == 'win32'
EC_DIAG = os.environ.get('EC_DIAG') == '1'
EC_DIAG_LOG = os.environ.get('EC_DIAG_LOG')

def _diag_write(msg: str):
    try:
        target = EC_DIAG_LOG or os.path.join(os.getenv('TEMP', os.getcwd()), 'ecan_diag.log')
        with open(target, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')
    except Exception:
        pass

if EC_DIAG:
    try:
        import threading
        import time
        import ctypes
        from ctypes import wintypes

        _diag_write('[DIAG] enabled')

        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200

        _orig_run = subprocess.run
        _orig_popen = subprocess.Popen
        _orig_call = subprocess.call
        _orig_check_call = subprocess.check_call
        _orig_check_output = subprocess.check_output
        _orig_system = os.system

        def _ensure_hidden_kwargs(kwargs):
            if IS_WIN:
                si = kwargs.get('startupinfo')
                if si is None:
                    si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs['startupinfo'] = si
                flags = kwargs.get('creationflags', 0)
                flags |= (CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
                kwargs['creationflags'] = flags
            return kwargs

        def _log_stack(prefix, cmd):
            try:
                stack = ''.join(traceback.format_stack(limit=8))
                _diag_write(f"[SUBPROC] {prefix}: {cmd}\n{stack}")
            except Exception:
                pass

        def run_hidden(*args, **kwargs):
            _log_stack('run', args[0] if args else kwargs.get('args'))
            kwargs = _ensure_hidden_kwargs(kwargs)
            return _orig_run(*args, **kwargs)

        class PopenHidden(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                _log_stack('Popen', args[0] if args else kwargs.get('args'))
                kwargs = _ensure_hidden_kwargs(kwargs)
                super().__init__(*args, **kwargs)

        def call_hidden(*args, **kwargs):
            _log_stack('call', args[0] if args else kwargs.get('args'))
            kwargs = _ensure_hidden_kwargs(kwargs)
            return _orig_call(*args, **kwargs)

        def check_call_hidden(*args, **kwargs):
            _log_stack('check_call', args[0] if args else kwargs.get('args'))
            kwargs = _ensure_hidden_kwargs(kwargs)
            return _orig_check_call(*args, **kwargs)

        def check_output_hidden(*args, **kwargs):
            _log_stack('check_output', args[0] if args else kwargs.get('args'))
            kwargs = _ensure_hidden_kwargs(kwargs)
            return _orig_check_output(*args, **kwargs)

        def system_hidden(cmd):
            _log_stack('os.system', cmd)
            return _orig_system(cmd)

        subprocess.run = run_hidden
        subprocess.Popen = PopenHidden
        subprocess.call = call_hidden
        subprocess.check_call = check_call_hidden
        subprocess.check_output = check_output_hidden
        os.system = system_hidden

        def _win_monitor(duration_sec=8):
            if not IS_WIN:
                return
            user32 = ctypes.windll.user32
            GetWindowTextW = user32.GetWindowTextW
            GetWindowTextLengthW = user32.GetWindowTextLengthW
            GetClassNameW = user32.GetClassNameW
            GetWindowThreadProcessId = user32.GetWindowThreadProcessId
            IsWindowVisible = user32.IsWindowVisible
            EnumWindows = user32.EnumWindows

            windows_seen = set()

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def enum_handler(hwnd, lParam):
                if not IsWindowVisible(hwnd):
                    return True
                length = GetWindowTextLengthW(hwnd)
                title = ctypes.create_unicode_buffer(length + 1)
                GetWindowTextW(hwnd, title, length + 1)
                cls = ctypes.create_unicode_buffer(256)
                GetClassNameW(hwnd, cls, 256)
                pid = wintypes.DWORD()
                GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                key = (int(ctypes.c_size_t(hwnd).value), pid.value)
                if key not in windows_seen:
                    windows_seen.add(key)
                    _diag_write(f"[WIN] pid={pid.value} hwnd={key[0]} cls={cls.value} title={title.value}")
                return True

            end = time.time() + duration_sec
            while time.time() < end:
                try:
                    EnumWindows(enum_handler, 0)
                except Exception:
                    pass
                time.sleep(0.05)

        threading.Thread(target=_win_monitor, args=(8,), daemon=True).start()
    except Exception:
        pass

# Global QApplication instance
_global_app = None


def _import_asyncio_safely():
    """Import asyncio (asyncio issues have been fixed in stdlib)."""
    import asyncio as _asyncio
    return _asyncio


def _is_multiprocessing_bootstrap() -> bool:
    """Detect PyInstaller/Windows multiprocessing helper launches and ProcessPoolExecutor workers"""
    try:
        # PyInstaller passes --multiprocessing-<mode> to helper processes
        # Also check for ProcessPoolExecutor worker processes
        for arg in sys.argv[1:]:
            if arg.startswith('--multiprocessing-'):
                return True
            # ProcessPoolExecutor workers have specific command line patterns
            if 'multiprocessing.spawn' in arg:
                return True
        return False
    except Exception:
        # Fail safe: assume regular launch
        return False


def _prepare_multiprocessing_runtime() -> bool:
    """Run freeze_support and tell caller whether this is a helper process."""
    try:
        import multiprocessing as mp
    except Exception:
        mp = None

    if mp and hasattr(mp, 'freeze_support'):
        try:
            mp.freeze_support()
        except Exception as exc:
            print(f"[MULTIPROCESSING] freeze_support failed: {exc}")

    return _is_multiprocessing_bootstrap()

def _configure_multiprocessing():
    """
    Configure multiprocessing settings for better process management.
    This helps prevent unwanted subprocess creation and resource conflicts.
    """
    try:
        import multiprocessing as mp

        # Set multiprocessing start method for better PyInstaller compatibility
        if hasattr(mp, 'set_start_method'):
            try:
                current_method = mp.get_start_method(allow_none=True)

                # Platform-specific multiprocessing configuration
                if sys.platform == 'win32':
                    # Windows: Always use spawn (default and required)
                    if current_method != 'spawn':
                        mp.set_start_method('spawn', force=True)
                        print(f"[MULTIPROCESSING] Windows: Set start method to 'spawn' (was: {current_method})")
                    else:
                        print("[MULTIPROCESSING] Windows: Start method already 'spawn'")
                elif sys.platform == 'darwin':
                    # macOS: Use spawn for better PyInstaller and WebEngine compatibility
                    if current_method is None:
                        mp.set_start_method('spawn', force=True)
                        print("[MULTIPROCESSING] macOS: Set start method to 'spawn' for PyInstaller compatibility")
                    elif current_method != 'spawn':
                        print(f"[MULTIPROCESSING] macOS: Start method is '{current_method}', recommend 'spawn' for PyInstaller")
                    else:
                        print("[MULTIPROCESSING] macOS: Start method already 'spawn'")
                else:
                    # Linux: Use spawn for better isolation
                    if current_method != 'spawn':
                        mp.set_start_method('spawn', force=True)
                        print(f"[MULTIPROCESSING] Linux: Set start method to 'spawn' (was: {current_method})")
                    else:
                        print("[MULTIPROCESSING] Linux: Start method already 'spawn'")

            except RuntimeError as e:
                print(f"[MULTIPROCESSING] Start method already set: {e}")

        print("[MULTIPROCESSING] Configuration completed")

    except Exception as e:
        print(f"[MULTIPROCESSING] Configuration failed: {e}")
        # Don't exit on multiprocessing config failure

# Top-level exception handling, catch all import and runtime exceptions
try:
    # Multi-process protection - must be before all other imports
    if __name__ == '__main__':
        # Multi-process protection - exit if this is a multiprocessing bootstrap process
        # Worker processes (with ECAN_RUN_SCRIPT) should continue to execute their scripts
        if not os.getenv('ECAN_RUN_SCRIPT') and _prepare_multiprocessing_runtime():
            # This is a true multiprocessing bootstrap, should exit
            sys.exit(0)

        # Apply PyInstaller fixes early
        try:
            from utils.runtime_utils import initialize_runtime_environment
            initialize_runtime_environment()
        except Exception as e:
            print(f"Warning: Runtime initialization failed: {e}")

        # Proxy initialization will be done after splash screen (to avoid blocking startup)

        # Ensure Windows uses SelectorEventLoop to support Qt/qasync integration
        try:
            _asyncio = _import_asyncio_safely()
            if sys.platform.startswith('win'):
                # Suppress deprecation warnings for WindowsSelectorEventLoopPolicy
                # This is intentional for Qt/qasync compatibility on Windows
                import warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=DeprecationWarning, 
                                          message=".*WindowsSelectorEventLoopPolicy.*|.*set_event_loop_policy.*")
                    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
                # Apply subprocess patch for Windows SelectorEventLoop
                # This allows browser-use/Playwright to launch Chrome despite SelectorEventLoop limitations
                try:
                    from utils.win_subproc import patch_asyncio_subprocess_for_windows
                    patch_asyncio_subprocess_for_windows()
                except Exception as patch_err:
                    print(f"[WARNING] Failed to apply Windows subprocess patch: {patch_err}")
            # Cache asyncio to avoid later re-import quirks
            globals()['ASYNCIO'] = _asyncio
        except Exception:
            pass

        # Single-instance guard (bypass when explicitly requested for worker subprocesses)
        if os.getenv('ECAN_BYPASS_SINGLE_INSTANCE') != '1':
            from utils.single_instance import install_single_instance
            install_single_instance()

        from utils.logger_helper import install_crash_logger
        install_crash_logger()

        # Configure multiprocessing for better process management
        _configure_multiprocessing()


    else:
        # If not the main module, exit directly
        sys.exit(0)

    from utils.time_util import TimeUtil
    import platform
    from datetime import datetime

    def _print_startup_banner(logger, app_info):
        """Print a beautiful startup banner using unified build_info module"""
        try:
            from config.build_info import get_startup_banner
            
            # Get and display the unified startup banner
            # Note: Banner already shows "(Local Dev)" if using fallback data
            banner = get_startup_banner()
            logger.info("\n" + banner)
        except Exception as e:
            # If banner printing fails, just log a simple startup message
            logger.info(f"eCan Application Starting... (Version: {getattr(app_info, 'version', '1.0.0')})")
            logger.debug(f"Failed to print startup banner: {e}")

    print(TimeUtil.formatted_now_with_ms() + " app start...")

    # Linux: Check display server availability BEFORE creating QApplication
    if sys.platform.startswith('linux'):
        print(TimeUtil.formatted_now_with_ms() + " [Linux] Checking display server...")
        try:
            from gui.utils.display_detector import (
                is_gui_available, 
                get_display_info,
                check_pyside6_compatibility
            )
            
            display_info = get_display_info()
            print(f"[Linux] Display info: {display_info}")
            
            if not is_gui_available():
                print("[Linux] No display server detected, switching to web mode")
                os.environ['ECAN_MODE'] = 'web'
                
                # Redirect to web server
                print("[Linux] Starting web server mode...")
                from web_server import main as web_main
                sys.exit(web_main())
            
            # Check PySide6 compatibility
            can_run, message = check_pyside6_compatibility()
            print(f"[Linux] PySide6 compatibility: {message}")
            
            if not can_run:
                print("\n" + "="*60)
                print("ERROR: GUI cannot run on this system")
                print("="*60)
                print(message)
                print("\nOptions:")
                print("  1. Install required system packages (see requirements-linux.txt)")
                print("  2. Run in web mode: ECAN_MODE=web python main.py")
                print("  3. Use deployment script: ./scripts/deploy-ubuntu.sh")
                print("="*60 + "\n")
                sys.exit(1)
            
            # Check system dependencies
            try:
                from utils.linux_permissions import get_missing_dependencies
                missing = get_missing_dependencies()
                if missing:
                    print("\n" + "="*60)
                    print("WARNING: Missing system dependencies")
                    print("="*60)
                    for item in missing:
                        print(f"  ⚠️  {item}")
                    print("\nSome features may not work properly.")
                    print("Run: python -m utils.linux_permissions")
                    print("="*60 + "\n")
            except Exception as e:
                print(f"[Linux] Could not check dependencies: {e}")
                
        except Exception as e:
            print(f"[Linux] Display detection failed: {e}")
            print("[Linux] Continuing with GUI startup...")

    # Create QApplication FIRST - this is the single point of creation
    print(TimeUtil.formatted_now_with_ms() + " creating QApplication...")
    from PySide6.QtWidgets import QApplication as _QApp

    # Use global variable to store QApplication instance, ensuring access throughout the module
    _global_app = _QApp.instance()
    if not _global_app:
        _global_app = _QApp(sys.argv)
        print(TimeUtil.formatted_now_with_ms() + " QApplication created")
    else:
        print(TimeUtil.formatted_now_with_ms() + " QApplication already exists")

    # Linux: set desktop file name from config so WM_CLASS matches .desktop StartupWMClass
    if sys.platform.startswith("linux"):
        try:
            from config.constants import APP_NAME
            from PySide6.QtGui import QGuiApplication
            desktop_id = APP_NAME.lower()
            if hasattr(QGuiApplication, "setDesktopFileName"):
                QGuiApplication.setDesktopFileName(desktop_id)
                print(TimeUtil.formatted_now_with_ms() + f" [Linux] setDesktopFileName({desktop_id})")
        except Exception as e:
            print(f"[Linux] setDesktopFileName failed: {e}")

    # Set application icon early for macOS/Linux (Windows taskbar icon needs window handle, set later)
    # This prevents showing the default Python icon during startup
    print(TimeUtil.formatted_now_with_ms() + " setting application icon...")
    try:
        from utils.icon_manager import get_icon_manager
        icon_mgr = get_icon_manager()

        # Set QApplication icon (works for all platforms)
        if icon_mgr.set_application_icon(_global_app):
            print(TimeUtil.formatted_now_with_ms() + " application icon set successfully")
        else:
            print(TimeUtil.formatted_now_with_ms() + " application icon setup warning")

        # Note: Windows taskbar icon requires window handle and will be set later in main()
        # when the main window is visible (especially important for frozen/packaged builds)
    except Exception as e:
        print(f"Failed to set early application icon: {e}")

    # Process events to ensure Qt is fully initialized
    print(TimeUtil.formatted_now_with_ms() + " processing Qt events...")
    _global_app.processEvents()



    # Show minimal splash IMMEDIATELY - this gives instant visual feedback
    # Import only the minimal splash function (lightweight, doesn't load full splash)
    print(TimeUtil.formatted_now_with_ms() + " showing minimal splash...")
    minimal_splash = None
    try:
        from gui.splash import init_minimal_splash
        minimal_splash = init_minimal_splash()
        if minimal_splash:
            print(TimeUtil.formatted_now_with_ms() + " minimal splash shown")
            # Force immediate display
            _global_app.processEvents()
    except Exception as e:
        print(f"Failed to show minimal splash: {e}")
        import traceback
        traceback.print_exc()

    # Now load the full splash screen (this can take a bit longer)
    # The minimal splash is already visible, so user sees immediate feedback
    print(TimeUtil.formatted_now_with_ms() + " importing full splash...")
    # Process events to keep minimal splash responsive during import
    if minimal_splash:
        _global_app.processEvents()

    try:
        from gui.splash import init_startup_splash, create_startup_progress_manager

        startup_splash = init_startup_splash()
        print(TimeUtil.formatted_now_with_ms() + " full splash initialized")

        # Smoothly transition from minimal to full splash
        if minimal_splash and startup_splash:
            try:
                # Hide minimal splash after full splash is shown
                # Use deleteLater for safe cleanup
                minimal_splash.hide()
                minimal_splash.deleteLater()
                minimal_splash = None
                # Process events to ensure smooth transition
                _global_app.processEvents()
            except Exception:
                pass

        progress_manager = create_startup_progress_manager(startup_splash)
    except Exception as e:
        print(f"Failed to initialize full splash screen: {e}")
        import traceback
        traceback.print_exc()
        # Keep minimal splash if full splash failed
        startup_splash = minimal_splash
        # Create a dummy progress manager to continue startup
        class DummyProgressManager:
            def update_progress(self, progress, status=None):
                print(f"Progress: {progress}% - {status}")
            def update_status(self, status):
                print(f"Status: {status}")
            def finish(self, main_window=None):
                pass
        progress_manager = DummyProgressManager()
        if not startup_splash:
            startup_splash = None

    progress_manager.update_progress(5, "Loading core modules...")

    # Standard imports
    asyncio = globals().get('ASYNCIO')
    if asyncio is None:
        asyncio = _import_asyncio_safely()
        globals()['ASYNCIO'] = asyncio
    import qasync
    progress_manager.update_progress(10, "Importing standard libraries...")

    # Basic configuration imports
    from config.app_info import app_info
    from config.app_settings import app_settings
    from utils.logger_helper import logger_helper as logger
    from app_context import AppContext
    progress_manager.update_progress(15, "Loading configuration...")

    # Print startup banner
    _print_startup_banner(logger, app_info)

    try:
        from utils.crash_boundary import (
            report_previous_process_boundary,
            set_crash_boundary_phase,
            start_crash_boundary_heartbeat,
        )
        set_crash_boundary_phase("startup:configuration_loaded")
        previous_boundary = report_previous_process_boundary()
        if previous_boundary.get("unexpected"):
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.delivery_durability import abort_pending_from_previous_process
                abort_pending_from_previous_process()
            except Exception as e:
                logger.warning(f"[FEIGE-DURABILITY] startup abort scan failed: {e}")
        start_crash_boundary_heartbeat()
    except Exception as e:
        logger.warning(f"[CrashBoundary] startup monitor failed: {e}")

    try:
        from ota.core.install_state import handle_pending_install_cleanup
        handle_pending_install_cleanup(current_version=getattr(app_info, 'version', '1.0.0'), logger=logger)
    except Exception as e:
        logger.warning(f"[OTA] Failed to handle pending installation cleanup on startup: {e}")

    # Configure third-party package loggers to use unified logger
    try:
        from utils.thirdparty_logger_config import configure_all_thirdparty_loggers
        configure_all_thirdparty_loggers()
    except Exception as e:
        logger.warning(f"Failed to configure third-party loggers: {e}")

    # Runtime environment is already initialized above
    progress_manager.update_progress(20, "Setting up environment...")

    # Load shell environment variables early (for non-terminal launches)
    progress_manager.update_progress(22, "Loading environment variables...")
    try:
        from utils.env import load_shell_environment
        loaded_count = load_shell_environment()
        if loaded_count > 0:
            print(f"Loaded {loaded_count} environment variables from shell configuration")
        else:
            print("No additional environment variables loaded")
    except Exception as e:
        print(f"Warning: Failed to load shell environment variables: {e}")

    # Enforce baseline: start in direct-connection mode unless ProxyManager later verifies a reachable system proxy
    try:
        from agent.ec_skills.system_proxy import apply_direct_connection_baseline
        cleared = apply_direct_connection_baseline()
        if cleared:
            print("Cleared proxy env vars; set NO_PROXY='*' (direct connection baseline)")
        else:
            print("Set NO_PROXY='*' (direct connection baseline)")
    except Exception as e:
        print(f"Warning: Failed to enforce direct-connection baseline: {e}")

    progress_manager.update_progress(28, "Starting local server...")
    try:
        from gui.LocalServer import start_local_server_early
        local_server_port = int(os.environ.get('ECAN_LOCAL_SERVER_PORT', os.environ.get('VITE_LOCAL_SERVER_PORT', '4668')))
        start_local_server_early(local_server_port)
        if not _wait_for_port_ready(local_server_port):
            print(f"Warning: local server not ready on 127.0.0.1:{local_server_port}")
    except Exception as e:
        print(f"Warning: Failed to start local server early: {e}")

    # Import other necessary modules
    progress_manager.update_progress(30, "Loading Login components...")
    from gui.LoginoutGUI import Login
    progress_manager.update_progress(32, "Loading WebGUI components...")
    from gui.WebGUI import WebGUI
    
    # Patch browser-use to use UTF-8 encoding
    progress_manager.update_progress(33, "Patching browser-use to UTF-8...")
    _patch_browser_use_to_utf8()

    # Compatibility shim: httpx >= 0.20 renamed TimeoutError → TimeoutException.
    # browser-use still catches httpx.TimeoutError in its retry loop;
    # without this alias every LLM call fails with AttributeError.
    try:
        import httpx
        if not hasattr(httpx, 'TimeoutError'):
            httpx.TimeoutError = httpx.TimeoutException
            print("[HTTPX_FIX] ✅ httpx.TimeoutError alias added for browser-use compatibility")
    except Exception as _httpx_e:
        print(f"[HTTPX_FIX] Warning: Could not add httpx.TimeoutError alias: {_httpx_e}")




    def main():
        """Main function"""
        print("Entering main function...")
        try:
            from utils.crash_boundary import set_crash_boundary_phase
            set_crash_boundary_phase("startup:main_entered")
        except Exception:
            pass
        progress_manager.update_progress(35, "Initializing application...")

        # Start hot reload monitoring (development mode)
        # if app_settings.is_dev_mode:
        #     try:
        #         progress_manager.update_status("Setting up hot reload...")
        #         from utils.hot_reload import start_watching
        #         watch_paths = ['agent', 'bot', 'config', 'common', 'gui', 'skills', 'utils']
        #         start_watching(watch_paths, None)
        #     except ImportError:
        #         pass  # Ignore when hot reload module doesn't exist

        # Get the already-created QApplication instance
        app = _global_app
        if not app:  # This should never happen now
            print("ERROR: QApplication instance not found in main()!")
            raise RuntimeError("QApplication was not properly initialized")

        # Set application info and icon (unified management)
        progress_manager.update_progress(40, "Setting up application info...")
        from utils.app_setup_helper import setup_application_info
        setup_application_info(app, logger)

        # Initialize global AppContext
        progress_manager.update_progress(45, "Initializing application context...")
        try:
            from utils.crash_boundary import set_crash_boundary_phase
            set_crash_boundary_phase("startup:app_context")
        except Exception:
            pass
        ctx = AppContext()
        ctx.set_app(app)
        ctx.set_logger(logger)
        ctx.set_config(app_settings)
        ctx.set_app_info(app_info)

        # Handle deferred OTA installer cleanup after successful upgrade
        try:
            from ota.core.install_state import handle_pending_install_cleanup
            handle_pending_install_cleanup(current_version=app_info.version, logger=logger)
        except Exception as e:
            logger.warning(f"[OTA] Failed to handle pending install cleanup on startup: {e}")

        # Initialize GUI dispatcher to ensure it's created on the main thread
        from utils.gui_dispatch import init_gui_dispatch
        init_gui_dispatch()

        # Verify application icon (already set early for macOS/Linux)
        progress_manager.update_progress(50, "Verifying application icons...")
        from utils.icon_manager import get_icon_manager
        icon_mgr = get_icon_manager()
        icon_mgr.set_logger(logger)

        if icon_mgr.is_icon_set():
            logger.info("[IconManager] ✅ Application icon set (early startup)")
        else:
            # Fallback: set icon now if early setup failed
            success = icon_mgr.set_application_icon(app)
            if success:
                logger.info("[IconManager] ✅ Application icon set successfully (fallback)")
            else:
                logger.warning("[IconManager] ⚠️ Application icon setup failed")

        # Windows taskbar icon will be set by WebGUI after window is visible
        # (requires window handle, especially important for frozen/packaged builds)

        # Create event loop
        progress_manager.update_progress(55, "Creating event loop...")
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        # Install power monitor for sleep/wake detection (cross-platform)
        try:
            from utils.power_monitor import get_power_monitor
            power_monitor = get_power_monitor()
            power_monitor.install()
            logger.info("[Startup] Power monitor installed — sleep/wake detection active")
        except Exception as e:
            logger.warning(f"[Startup] Power monitor install failed (non-critical): {e}")

        # Async preload will be started by WebGUI after event loop is running
        # This allows heavy modules to load in background during user login
        progress_manager.update_progress(58, "Preparing background preload...")
        logger.info("✅ [Startup] Async preload will start after event loop is ready")

        # Create login component
        progress_manager.update_progress(60, "Initializing login system...")
        login = Login()
        ctx.set_login(login)
        ctx.set_main_loop(loop)

        # Start memory monitor (background thread, logs to memory.log)
        # Enable tracemalloc only when ECAN_TRACEMALLOC=1 for on-demand diagnosis;
        # it adds measurable CPU overhead so is off by default.
        try:
            from utils.memory_monitor import start_memory_monitor
            import os as _os
            # NOTE (2026-05-16): tried defaulting tracemalloc=ON for leak
            # forensics, but with 60+ skills × thousands of allocations during
            # skill build the per-allocation hook turned a 15s Batch 3 into
            # 3-5 min. Reverted to opt-in via env var. To capture forensics on
            # the next slow run: set ECAN_TRACEMALLOC=1 before launching.
            _tracemalloc = _os.environ.get("ECAN_TRACEMALLOC", "0") == "1"
            try:
                from utils.crash_boundary import set_crash_boundary_phase
                set_crash_boundary_phase("startup:memory_monitor")
            except Exception:
                pass
            start_memory_monitor(
                enable_tracemalloc=_tracemalloc,
                tracemalloc_frames=8,
                interval=30,        # check every 30s instead of 60s
                snapshot_interval=120,  # diff every 2 min instead of 5 min
                growth_warn_mb_per_min=30,  # warn earlier (was 50)
            )
            if _tracemalloc:
                logger.info("[MemoryMonitor] tracemalloc enabled for leak detection")
                logger.warning("[MemoryMonitor] ⚠️ ECAN_TRACEMALLOC=1 is set — this adds significant CPU/memory overhead. Consider running without this flag for normal operation.")
        except Exception as e:
            logger.warning(f"Failed to start memory monitor: {e}")

        # Print current running mode
        progress_manager.update_progress(65, "Configuring runtime mode...")
        if app_settings.is_dev_mode:
            logger.info("Running in development mode (Vite dev server)")
        else:
            logger.info("Running in production mode (built files)")

        # Create Web GUI (do not show yet; wait until resources are loaded)
        logger.info("Creating WebGUI instance...")
        progress_manager.update_progress(70, "Creating main interface...")
        try:
            from utils.crash_boundary import set_crash_boundary_phase
            set_crash_boundary_phase("startup:webgui")
        except Exception:
            pass

        # Create progress callback for WebGUI
        def webgui_progress_callback(progress, status):
            progress_manager.update_progress(progress, status)

        web_gui = WebGUI(splash=startup_splash, progress_callback=webgui_progress_callback)
        logger.info("WebGUI instance created successfully")

        progress_manager.update_progress(80, "Setting up URL scheme handling...")

        # Setup URL scheme handling
        try:
            from utils.url_scheme_handler import setup_url_scheme_handling
            url_scheme_handler = setup_url_scheme_handling(web_gui, auto_register=True)
            ctx.set_url_scheme_handler(url_scheme_handler)
            logger.info("URL scheme handling setup completed")
        except Exception as e:
            logger.warning(f"URL scheme setup failed: {e}")

        progress_manager.update_progress(85, "Finalizing setup...")
        ctx.set_web_gui(web_gui)

        # Set UI references for login controller (WebGUI is the "login window")
        login.set_ui_references(login_window=web_gui, login_progress_dialog=None)
        logger.info("WebGUI setup completed")

        # Start OTA auto-check in a fully non-blocking way (double background threads)
        try:
            from ota.core.updater import OTAUpdater

            OTAUpdater.start_auto_check_in_background(ctx=ctx, logger_instance=logger)
        except Exception as e:
            logger.warning(f"[OTA] Failed to schedule auto check: {e}")

        # Setup cleanup for OTA updater and sleep inhibitor on application exit
        def _cleanup_on_quit():
            logger.info("Application is about to quit. Cleaning up resources...")
            if hasattr(ctx, 'ota_updater') and ctx.ota_updater:
                logger.info("Stopping OTA auto check thread...")
                ctx.ota_updater.stop_auto_check()
            else:
                logger.info("No active OTA updater found to stop.")
            # Release sleep inhibitor so OS can sleep normally after app exit
            try:
                from utils.sleep_inhibitor import get_sleep_inhibitor
                get_sleep_inhibitor().force_release()
            except Exception:
                pass
            # Unregister LAN zeroconf services so peers see us as gone
            # immediately instead of waiting for TTL expiry. Non-fatal if
            # discovery wasn't started in this run.
            try:
                from agent.a2a.discovery import stop_lan_discovery
                stop_lan_discovery()
            except Exception:
                pass
            # Same for the WAN cloud directory — explicit delete mutations
            # let peers see us drop immediately.
            try:
                from agent.a2a.discovery import stop_cloud_directory
                stop_cloud_directory()
            except Exception:
                pass

        app.aboutToQuit.connect(_cleanup_on_quit)
        logger.info("Registered OTA updater cleanup on application quit.")

        # Finish splash screen
        progress_manager.update_progress(100, "Ready to launch!")
        progress_manager.finish(web_gui)

        # Initialize proxy environment after splash (non-blocking, in background)
        # This avoids blocking startup UI and allows splash to complete smoothly
        def init_proxy_after_splash():
            """Initialize proxy environment in background after splash completes."""
            try:
                logger.info("🌐 Initializing proxy environment (after splash)...")
                from agent.ec_skills.system_proxy import initialize_proxy_environment

                # Check if proxy management is explicitly disabled
                import os
                if os.getenv('ECAN_PROXY_ENABLED', 'true').lower() in ['false', '0', 'no']:
                    logger.info("⏭️  Proxy management disabled via ECAN_PROXY_ENABLED env var")
                    return

                initialize_proxy_environment()
                logger.info("✅ Proxy environment initialized")
            except Exception as e:
                logger.warning(f"⚠️  Proxy initialization failed: {e}")
                # Clear any potentially broken proxy settings
                import os
                for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
                    if proxy_var in os.environ:
                        logger.warning(f"   Clearing broken proxy: {proxy_var}={os.environ[proxy_var]}")
                        del os.environ[proxy_var]

        # Schedule proxy initialization in background thread
        import threading
        proxy_init_thread = threading.Thread(
            target=init_proxy_after_splash,
            name="ProxyInitAfterSplash",
            daemon=True
        )
        proxy_init_thread.start()

        # Run main loop
        try:
            from utils.crash_boundary import set_crash_boundary_phase
            set_crash_boundary_phase("main_loop:running")
        except Exception:
            pass
        loop.run_forever()

    if __name__ == '__main__':
        print(TimeUtil.formatted_now_with_ms() + " main function run start...")
        # Note: Don't reset process title here as it's already set to 'eCan'
        print(f"[PLATFORM] Running on {sys.platform}")



    try:
        main()
    except Exception as e:
        error_info = traceback.format_exc()
        print(f"\nApplication startup failed:")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print(f"\nComplete exception stack:")
        print(error_info)

        # Try to log to file
        try:
            logger.error(f"Application startup failed: {str(e)}")
            logger.error(error_info)
        except:
            pass

        sys.exit(1)
    finally:
        # Cleanup async preloader
        try:
            from gui.async_preloader import cleanup_async_preloader
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(cleanup_async_preloader())
            else:
                asyncio.run(cleanup_async_preloader())
        except Exception:
            pass

except Exception as e:
    # Top-level exception handling, catch all import exceptions
    error_info = traceback.format_exc()
    print(f"\nProgram import or initialization failed:")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")
    print(f"\nComplete exception stack:")
    print(error_info)
    sys.exit(1)
