#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import multiprocessing
import sys
import traceback

# Top-level exception handling, catch all import and runtime exceptions
try:
    # Multi-process protection - must be before all other imports
    if __name__ == '__main__':
        # Worker-mode support for packaged subprocesses: execute external script and exit
        import os
        run_script = os.getenv('ECBOT_RUN_SCRIPT')
        if run_script:
            try:
                with open(run_script, 'r', encoding='utf-8') as f:
                    code = f.read()
                exec(compile(code, run_script, 'exec'), {'__name__': '__main__'})
            finally:
                sys.exit(0)

        # Single-instance guard (bypass when explicitly requested for worker subprocesses)
        if os.getenv('ECBOT_BYPASS_SINGLE_INSTANCE') != '1':
            from utils.single_instance import install_single_instance
            install_single_instance()

        from utils.ecbot_crashlog import install_crash_logger
        install_crash_logger()

        # Set multiprocessing start method to spawn to avoid fork issues
        if hasattr(multiprocessing, 'set_start_method'):
            try:
                multiprocessing.set_start_method('spawn', force=True)
            except RuntimeError:
                pass  # Already set

        # Disable resource tracker to avoid duplicate startup issues
        try:
            import multiprocessing.resource_tracker
            multiprocessing.resource_tracker._resource_tracker = None
        except Exception:
            pass  # Ignore any errors
    else:
        # If not the main module, exit directly
        sys.exit(0)

    from utils.time_util import TimeUtil

    print(TimeUtil.formatted_now_with_ms() + " app start...")

    # Create QApplication and show themed splash as early as possible
    from gui.splash import init_startup_splash
    startup_splash = init_startup_splash()

    print(TimeUtil.formatted_now_with_ms() + " importing modules...")

    # Standard imports
    import asyncio
    import qasync
    from setproctitle import setproctitle

    # Basic configuration imports
    from config.app_info import app_info
    from config.app_settings import app_settings
    from utils.logger_helper import set_top_web_gui, logger_helper as logger
    from app_context import AppContext

    def fix_pyinstaller_environment():
        """Cross-platform PyInstaller environment fix"""
        if not getattr(sys, 'frozen', False):
            return

        try:
            import os

            # Only handle the most critical cv2 path issue
            if hasattr(sys, '_MEIPASS'):
                cv2_path = os.path.join(sys._MEIPASS, 'cv2')
                if os.path.exists(cv2_path) and cv2_path not in sys.path:
                    sys.path.insert(0, cv2_path)

                # Platform-specific library path fixes
                if sys.platform == 'win32':
                    # Windows: Add DLL directory (if supported)
                    try:
                        os.add_dll_directory(cv2_path)
                    except (OSError, AttributeError):
                        pass  # Python < 3.8 or not supported

                elif sys.platform == 'darwin':
                    # macOS: Set dynamic library path
                    try:
                        # Add cv2 library path to DYLD_LIBRARY_PATH
                        dyld_path = os.environ.get('DYLD_LIBRARY_PATH', '')
                        if cv2_path not in dyld_path:
                            if dyld_path:
                                os.environ['DYLD_LIBRARY_PATH'] = f"{cv2_path}:{dyld_path}"
                            else:
                                os.environ['DYLD_LIBRARY_PATH'] = cv2_path

                        # Also try to add to DYLD_FALLBACK_LIBRARY_PATH
                        fallback_path = os.environ.get('DYLD_FALLBACK_LIBRARY_PATH', '')
                        if cv2_path not in fallback_path:
                            if fallback_path:
                                os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = f"{cv2_path}:{fallback_path}"
                            else:
                                os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = cv2_path

                    except Exception:
                        pass  # Ignore macOS-specific errors

                elif sys.platform.startswith('linux'):
                    # Linux: Set LD_LIBRARY_PATH
                    try:
                        ld_path = os.environ.get('LD_LIBRARY_PATH', '')
                        if cv2_path not in ld_path:
                            if ld_path:
                                os.environ['LD_LIBRARY_PATH'] = f"{cv2_path}:{ld_path}"
                            else:
                                os.environ['LD_LIBRARY_PATH'] = cv2_path
                    except Exception:
                        pass  # Ignore Linux-specific errors

            print(f"[PYINSTALLER_FIX] Cross-platform environment fix applied for {sys.platform}")

        except Exception as e:
            print(f"[PYINSTALLER_FIX] Warning: {e}")
            # Don't prevent program startup due to fix failure

    # Fix environment before all imports
    fix_pyinstaller_environment()

    # Import other necessary modules
    import utils
    from gui.LoginoutGUI import Login
    from gui.WebGUI import WebGUI

    # Test modules (optional)
    # Do not import test modules in production build
    # try:
    #     from tests.unittests import *
    #     from tests.scraper_test import *
    # except ImportError:
    #     pass  # Ignore when test modules don't exist

    def main():
        """Main function"""
        print("🚀 Entering main function...")

        # Start hot reload monitoring (development mode)
        if app_settings.is_dev_mode:
            try:
                from utils.hot_reload import start_watching
                watch_paths = ['agent', 'bot', 'config', 'common', 'gui', 'skills', 'utils']
                start_watching(watch_paths, None)
            except ImportError:
                pass  # Ignore when hot reload module doesn't exist

        # Reuse early-initialized QApplication
        from PySide6.QtWidgets import QApplication as _QApp
        app = _QApp.instance()
        if not app:  # Fallback safety
            app = _QApp(sys.argv)

        # Set application info and icon (unified management)
        from utils.app_setup_helper import setup_application_info, set_app_icon, set_app_icon_delayed
        setup_application_info(app, logger)

        # Initialize global AppContext
        ctx = AppContext()
        ctx.set_app(app)
        ctx.set_logger(logger)
        ctx.set_config(app_settings)
        ctx.set_app_info(app_info)

        # Set application icon
        set_app_icon(app, logger)
        # Delay setting Windows taskbar icon (wait for main window creation)
        set_app_icon_delayed(app, logger)

        # Create event loop
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        # Create login component
        utils.logger_helper.login = Login()
        ctx.set_login(utils.logger_helper.login)

        # if utils.logger_helper.login.isCommander():
        #     print("run as commander......")
        #     utils.logger_helper.login.show()
        #     loop.create_task(runCommanderLAN(utils.logger_helper.login))
        #
        #     loop.run_forever()
        #
        # else:
        #     print("run as platoon...")
        #     wait_window = WaitWindow()
        #     # wait_window.show()
        #     utils.logger_helper.login.show()
        #     loop.create_task(runPlatoonLAN(utils.logger_helper.login, loop, wait_window))
        #
        #     loop.run_forever()

        utils.logger_helper.login.setLoop(loop)
        ctx.set_main_loop(loop)

        # Print current running mode
        if app_settings.is_dev_mode:
            logger.info("Running in development mode (Vite dev server)")
        else:
            logger.info("Running in production mode (built files)")

        # Create Web GUI (do not show yet; wait until resources are loaded)
        print("🚀 Starting to create WebGUI instance...")
        logger.info("Creating WebGUI instance...")
        web_gui = WebGUI(splash=startup_splash)
        print("✅ WebGUI instance created successfully")
        logger.info("WebGUI instance created successfully")

        ctx.set_web_gui(web_gui)
        set_top_web_gui(web_gui)

        utils.logger_helper.login.setTopGUI(web_gui)
        logger.info("WebGUI setup completed")

        # Run main loop
        loop.run_forever()

    if __name__ == '__main__':
        print(TimeUtil.formatted_now_with_ms() + " main function run start...")
        # Note: Don't reset process title here as it's already set to 'eCan'
        print(f"[PLATFORM] Running on {sys.platform}")
        if getattr(sys, 'frozen', False):
            print("[PYINSTALLER] Running from PyInstaller bundle")
        setproctitle('eCan')

    # test_eb_orders_scraper()
    # test_etsy_label_gen()
    # test_use_func_instructions()
    # test_multi_skills()
    # test_scrape_etsy_orders()
    # test_scrape_gs_labels()
    # test_processSearchWordline()
    # test_process7z()
    # test_basic()
    # test_coordinates()
    # test_rar()
    # test_UpdateBotADSProfileFromSavedBatchTxt()
    # test_batch_ads_profile_conversion()
    # test_run_group_of_tasks()
    # test_schedule_check()
    # test_pyautogui()
    # test_eb_orders_scraper()
    # print("all unit tests done...")
    # test_scrape_amz_buy_orders()
    # list_windows()
    # test_scrape_amz_product_details()
    # test_printer_print_sync()
    # test_selenium_amazon_shop()
    # test_selenium_GS()
    # test_selenium_amazon()
    # test_parse_xml()
    # test_pyzipunzip()
    # res = scrape_tests()

    try:
        main()
    except Exception as e:
        error_info = traceback.format_exc()
        print(f"\n❌ Application startup failed:")
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
    print(f"\n❌ Program import or initialization failed:")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")
    print(f"\nComplete exception stack:")
    print(error_info)
    sys.exit(1)
