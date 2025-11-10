#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import traceback
import subprocess

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
    # This is a worker process - execute the script and exit immediately
    # DO NOT import anything else before this check!
    run_script = os.getenv('ECAN_RUN_SCRIPT')
    print(f"[Worker Process] Executing script: {run_script}")
    print("[Worker Process] Skipping main application imports to save memory...")
    
    try:
        with open(run_script, 'r', encoding='utf-8') as f:
            code = f.read()
        exec(compile(code, run_script, 'exec'), {'__name__': '__main__'})
    except Exception as e:
        print(f"[Worker Process] Script execution failed: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("[Worker Process] Script completed, exiting...")
        sys.exit(0)

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

        # Ensure Windows uses SelectorEventLoop to support subprocesses (e.g., Playwright)
        try:
            _asyncio = _import_asyncio_safely()
            if sys.platform.startswith('win'):
                _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
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
        """Print a beautiful startup banner"""
        try:
            version = getattr(app_info, 'version', '1.0.0')
            app_name = 'eCan.AI'
            platform_name = platform.system()
            platform_release = platform.release()
            python_version = platform.python_version()
            is_frozen = getattr(sys, 'frozen', False)
            build_mode = 'Production' if is_frozen else 'Development'
            startup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Format platform info
            platform_info = f"{platform_name} {platform_release}"
            
            # Calculate padding for centered text (box width is 78 chars)
            box_width = 78
            app_name_padding = (box_width - len(app_name)) // 2
            version_text = f"Version {version}"
            version_padding = (box_width - len(version_text)) // 2
            
            banner = f"""
╔{'═' * box_width}╗
║{' ' * box_width}║
║{' ' * app_name_padding}{app_name}{' ' * (box_width - app_name_padding - len(app_name))}║
║{' ' * box_width}║
║{' ' * version_padding}{version_text}{' ' * (box_width - version_padding - len(version_text))}║
║{' ' * box_width}║
╠{'═' * box_width}╣
║  Platform:     {platform_info:<61}║
║  Python:       {python_version:<61}║
║  Build Mode:   {build_mode:<61}║
║  Startup Time: {startup_time:<61}║
╚{'═' * box_width}╝
"""
            logger.info(banner)
        except Exception as e:
            # If banner printing fails, just log a simple startup message
            logger.info(f"eCan Application Starting... (Version: {getattr(app_info, 'version', '1.0.0')})")
            logger.debug(f"Failed to print startup banner: {e}")

    print(TimeUtil.formatted_now_with_ms() + " app start...")

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

    # Import other necessary modules
    progress_manager.update_progress(30, "Loading Login components...")
    from gui.LoginoutGUI import Login
    progress_manager.update_progress(32, "Loading WebGUI components...")
    from gui.WebGUI import WebGUI


    def main():
        """Main function"""
        print("Entering main function...")
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
        ctx = AppContext()
        ctx.set_app(app)
        ctx.set_logger(logger)
        ctx.set_config(app_settings)
        ctx.set_app_info(app_info)

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

        # Async preload will be started by WebGUI after event loop is running
        # This allows heavy modules to load in background during user login
        progress_manager.update_progress(58, "Preparing background preload...")
        logger.info("✅ [Startup] Async preload will start after event loop is ready")

        # Create login component
        progress_manager.update_progress(60, "Initializing login system...")
        login = Login()
        ctx.set_login(login)
        ctx.set_main_loop(loop)

        # Print current running mode
        progress_manager.update_progress(65, "Configuring runtime mode...")
        if app_settings.is_dev_mode:
            logger.info("Running in development mode (Vite dev server)")
        else:
            logger.info("Running in production mode (built files)")

        # Create Web GUI (do not show yet; wait until resources are loaded)
        logger.info("Creating WebGUI instance...")
        progress_manager.update_progress(70, "Creating main interface...")

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
