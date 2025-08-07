import multiprocessing
import sys
import os
import tempfile

# 多进程保护 - 必须在所有其他导入之前
if __name__ == '__main__':
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
import asyncio
import traceback

import qasync
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from setproctitle import setproctitle

from config.app_info import app_info
from config.app_settings import app_settings
from utils.logger_helper import set_top_web_gui, logger_helper as logger
from utils.hot_reload import start_watching

import utils
from gui.LoginoutGUI import Login
# from gui.WaitGui import WaitWindow
from gui.WebGUI import WebGUI
from bot.network import runCommanderLAN, runPlatoonLAN


from tests.unittests import *
from tests.scraper_test import *

from app_context import AppContext


# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

def main():
    # 启动热更新监控
    if app_settings.is_dev_mode:
        watch_paths = ['agent', 'bot', 'config', 'common', 'gui', 'skills', 'utils']
        # 在 GUI 应用中，事件循环由 Qt/qasync 管理，所以这里 loop 参数暂时不直接使用，
        # 但保留以备将来与 asyncio 事件循环更紧密的集成。
        start_watching(watch_paths, None)

    # 创建应用程序实例
    app = QApplication.instance()
    if not app:  # If no instance, create a new QApplication
        app = QApplication(sys.argv)
    
    # 设置应用程序信息和图标（统一管理）
    from utils.app_setup_helper import setup_application_info, set_app_icon, set_app_icon_delayed
    
    # 统一设置应用程序基本信息
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

    # app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    # global login
    # login = Login()
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
    web_gui = WebGUI()
    ctx.set_web_gui(web_gui)

    set_top_web_gui(web_gui)
    web_gui.show()

    utils.logger_helper.login.setTopGUI(web_gui)
    # 显示登录界面
    # utils.logger_helper.login.show()
    loop.run_forever()

if __name__ == '__main__':
    print(TimeUtil.formatted_now_with_ms() + " main function run start...")
    # 注意：不要在这里重新设置进程标题，因为前面已经设置为'eCan'了

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
        # print("main starts...")
        main()
    except Exception as e:
        error_info = traceback.format_exc()  # 获取完整的异常堆栈信息
        logger.error(error_info)

    # qasync.run(main())
