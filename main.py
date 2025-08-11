#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import multiprocessing
import sys
import traceback

# 最外层异常处理，捕获所有导入和运行时异常
try:
    # 多进程保护 - 必须在所有其他导入之前
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

        # 设置多进程启动方法为spawn，避免fork问题
        if hasattr(multiprocessing, 'set_start_method'):
            try:
                multiprocessing.set_start_method('spawn', force=True)
            except RuntimeError:
                pass  # 已经设置过了

        # 禁用资源跟踪器以避免重复启动问题
        try:
            import multiprocessing.resource_tracker
            multiprocessing.resource_tracker._resource_tracker = None
        except Exception:
            pass  # 忽略任何错误
    else:
        # 如果不是主模块，直接退出
        sys.exit(0)

    from utils.time_util import TimeUtil

    print(TimeUtil.formatted_now_with_ms() + " app start...")
    print(TimeUtil.formatted_now_with_ms() + " importing modules...")

    # 标准导入
    import asyncio
    import qasync
    from PySide6.QtWidgets import QApplication
    from setproctitle import setproctitle

    # 基础配置导入
    from config.app_info import app_info
    from config.app_settings import app_settings
    from utils.logger_helper import set_top_web_gui, logger_helper as logger
    from app_context import AppContext

    def fix_pyinstaller_environment():
        """跨平台的 PyInstaller 环境修复"""
        if not getattr(sys, 'frozen', False):
            return

        try:
            import os

            # 只处理最关键的 cv2 路径问题
            if hasattr(sys, '_MEIPASS'):
                cv2_path = os.path.join(sys._MEIPASS, 'cv2')
                if os.path.exists(cv2_path) and cv2_path not in sys.path:
                    sys.path.insert(0, cv2_path)

                # 平台特定的库路径修复
                if sys.platform == 'win32':
                    # Windows: 添加 DLL 目录（如果支持）
                    try:
                        os.add_dll_directory(cv2_path)
                    except (OSError, AttributeError):
                        pass  # Python < 3.8 或不支持

                elif sys.platform == 'darwin':
                    # macOS: 设置动态库路径
                    try:
                        # 添加 cv2 库路径到 DYLD_LIBRARY_PATH
                        dyld_path = os.environ.get('DYLD_LIBRARY_PATH', '')
                        if cv2_path not in dyld_path:
                            if dyld_path:
                                os.environ['DYLD_LIBRARY_PATH'] = f"{cv2_path}:{dyld_path}"
                            else:
                                os.environ['DYLD_LIBRARY_PATH'] = cv2_path

                        # 也尝试添加到 DYLD_FALLBACK_LIBRARY_PATH
                        fallback_path = os.environ.get('DYLD_FALLBACK_LIBRARY_PATH', '')
                        if cv2_path not in fallback_path:
                            if fallback_path:
                                os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = f"{cv2_path}:{fallback_path}"
                            else:
                                os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = cv2_path

                    except Exception:
                        pass  # 忽略 macOS 特定的错误

                elif sys.platform.startswith('linux'):
                    # Linux: 设置 LD_LIBRARY_PATH
                    try:
                        ld_path = os.environ.get('LD_LIBRARY_PATH', '')
                        if cv2_path not in ld_path:
                            if ld_path:
                                os.environ['LD_LIBRARY_PATH'] = f"{cv2_path}:{ld_path}"
                            else:
                                os.environ['LD_LIBRARY_PATH'] = cv2_path
                    except Exception:
                        pass  # 忽略 Linux 特定的错误

            print(f"[PYINSTALLER_FIX] Cross-platform environment fix applied for {sys.platform}")

        except Exception as e:
            print(f"[PYINSTALLER_FIX] Warning: {e}")
            # 不要因为修复失败而阻止程序启动

    # 在所有导入之前修复环境
    fix_pyinstaller_environment()

    # 导入其他必要模块
    import utils
    from gui.LoginoutGUI import Login
    from gui.WebGUI import WebGUI

    # 测试模块（可选）
    # Do not import test modules in production build
    # try:
    #     from tests.unittests import *
    #     from tests.scraper_test import *
    # except ImportError:
    #     pass  # 测试模块不存在时忽略

    def main():
        """主函数"""
        print("🚀 进入main函数...")

        # 启动热更新监控（开发模式）
        if app_settings.is_dev_mode:
            try:
                from utils.hot_reload import start_watching
                watch_paths = ['agent', 'bot', 'config', 'common', 'gui', 'skills', 'utils']
                start_watching(watch_paths, None)
            except ImportError:
                pass  # 热更新模块不存在时忽略

        # 创建应用程序实例
        app = QApplication.instance()
        if not app:  # If no instance, create a new QApplication
            app = QApplication(sys.argv)

        # 设置应用程序信息和图标（统一管理）
        from utils.app_setup_helper import setup_application_info, set_app_icon, set_app_icon_delayed
        setup_application_info(app, logger)

        # 初始化全局 AppContext
        ctx = AppContext()
        ctx.set_app(app)
        ctx.set_logger(logger)
        ctx.set_config(app_settings)
        ctx.set_app_info(app_info)

        # 设置应用程序图标
        set_app_icon(app, logger)
        # 延迟设置 Windows 任务栏图标（等待主窗口创建）
        set_app_icon_delayed(app, logger)

        # 创建事件循环
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        # 创建登录组件
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

        # 打印当前运行模式
        if app_settings.is_dev_mode:
            logger.info("Running in development mode (Vite dev server)")
        else:
            logger.info("Running in production mode (built files)")

        # 创建并显示 Web GUI
        print("🚀 开始创建WebGUI实例...")
        logger.info("Creating WebGUI instance...")
        web_gui = WebGUI()
        print("✅ WebGUI实例创建成功")
        logger.info("WebGUI instance created successfully")

        ctx.set_web_gui(web_gui)
        set_top_web_gui(web_gui)

        print("🖥️  显示WebGUI窗口...")
        logger.info("Showing WebGUI...")
        web_gui.show()
        print("✅ WebGUI窗口显示成功")
        logger.info("WebGUI shown successfully")

        utils.logger_helper.login.setTopGUI(web_gui)
        logger.info("WebGUI setup completed")

        # 运行主循环
        loop.run_forever()

    if __name__ == '__main__':
        print(TimeUtil.formatted_now_with_ms() + " main function run start...")
        # 注意：不要在这里重新设置进程标题，因为前面已经设置为'eCan'了
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
        print(f"\n❌ 应用程序启动失败:")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print(f"\n完整异常堆栈:")
        print(error_info)

        # 尝试记录到日志
        try:
            logger.error(f"应用程序启动失败: {str(e)}")
            logger.error(error_info)
        except:
            pass

        sys.exit(1)

except Exception as e:
    # 最外层异常处理，捕获所有导入异常
    error_info = traceback.format_exc()
    print(f"\n❌ 程序导入或初始化失败:")
    print(f"错误类型: {type(e).__name__}")
    print(f"错误信息: {str(e)}")
    print(f"\n完整异常堆栈:")
    print(error_info)
    sys.exit(1)
