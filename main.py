#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import multiprocessing
import sys
import os
import traceback

# Global QApplication instance
_global_app = None

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
        # Apply PyInstaller fixes early
        try:
            from utils.runtime_utils import initialize_runtime_environment
            initialize_runtime_environment()
        except Exception as e:
            print(f"Warning: Runtime initialization failed: {e}")

        # Worker-mode support for packaged subprocesses: execute external script and exit
        run_script = os.getenv('ECAN_RUN_SCRIPT')
        if run_script:
            try:
                with open(run_script, 'r', encoding='utf-8') as f:
                    code = f.read()
                exec(compile(code, run_script, 'exec'), {'__name__': '__main__'})
            finally:
                sys.exit(0)

        # Ensure Windows uses SelectorEventLoop to support subprocesses (e.g., Playwright)
        try:
            if sys.platform.startswith('win'):
                import asyncio as _asyncio
                _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
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

    # Process events to ensure Qt is fully initialized
    print(TimeUtil.formatted_now_with_ms() + " processing Qt events...")
    _global_app.processEvents()

    # Create and show themed splash as early as possible
    print(TimeUtil.formatted_now_with_ms() + " importing gui.splash...")
    try:
        from gui.splash import init_startup_splash, create_startup_progress_manager

        startup_splash = init_startup_splash()
        print(TimeUtil.formatted_now_with_ms() + " startup splash initialized")

        progress_manager = create_startup_progress_manager(startup_splash)
    except Exception as e:
        print(f"Failed to initialize splash screen: {e}")
        import traceback
        traceback.print_exc()
        # Create a dummy progress manager to continue startup
        class DummyProgressManager:
            def update_progress(self, progress, status=None):
                print(f"Progress: {progress}% - {status}")
            def update_status(self, status):
                print(f"Status: {status}")
            def finish(self, main_window=None):
                pass
        progress_manager = DummyProgressManager()
        startup_splash = None

    progress_manager.update_progress(5, "Loading core modules...")

    # Standard imports
    import asyncio
    import qasync
    progress_manager.update_progress(10, "Importing standard libraries...")

    # Basic configuration imports
    from config.app_info import app_info
    from config.app_settings import app_settings
    from utils.logger_helper import logger_helper as logger
    from app_context import AppContext
    progress_manager.update_progress(15, "Loading configuration...")

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
        from utils.app_setup_helper import setup_application_info, set_app_icon, set_app_icon_delayed
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

        # Set application icon
        progress_manager.update_progress(50, "Setting up application icons...")
        set_app_icon(app, logger)
        # Delay setting Windows taskbar icon (wait for main window creation)
        set_app_icon_delayed(app, logger)

        # Create event loop
        progress_manager.update_progress(55, "Creating event loop...")
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

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
        print("Starting to create WebGUI instance...")
        logger.info("Creating WebGUI instance...")
        progress_manager.update_progress(70, "Creating main interface...")

        # Create progress callback for WebGUI
        def webgui_progress_callback(progress, status):
            progress_manager.update_progress(progress, status)

        web_gui = WebGUI(splash=startup_splash, progress_callback=webgui_progress_callback)
        print("WebGUI instance created successfully")
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
        logger.info("WebGUI setup completed")

        # Finish splash screen
        progress_manager.update_progress(100, "Ready to launch!")
        progress_manager.finish(web_gui)

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

except Exception as e:
    # Top-level exception handling, catch all import exceptions
    error_info = traceback.format_exc()
    print(f"\nProgram import or initialization failed:")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")
    print(f"\nComplete exception stack:")
    print(error_info)
    sys.exit(1)
