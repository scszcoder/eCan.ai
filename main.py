from utils.time_util import TimeUtil

print(TimeUtil.formatted_now_with_ms() + " app start...")
import asyncio
import sys
import traceback

import qasync
from PySide6.QtWidgets import QApplication
from setproctitle import setproctitle

from config.app_settings import app_settings
from gui.LoginoutGUI import Login
from gui.WaitGui import WaitWindow
from gui.WebGUI import WebGUI
from bot.network import runCommanderLAN, runPlatoonLAN
# from utils.logger_helper import logger_helper, login
import utils.logger_helper
from utils.logger_helper import set_top_web_gui

# from tests.unittests import *
from tests.unittests import *


# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

def main():
    app = QApplication.instance()
    if not app:  # If no instance, create a new QApplication
        app = QApplication(sys.argv)
    # app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    # global login
    # login = Login()
    utils.logger_helper.login = Login()

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
    
    # 打印当前运行模式
    if app_settings.is_dev_mode:
        print("Running in development mode (Vite dev server)")
    else:
        print("Running in production mode (built files)")

    # 创建并显示 Web GUI
    web_gui = WebGUI(utils.logger_helper.login)
    set_top_web_gui(web_gui)
    web_gui.show()

    utils.logger_helper.login.setTopGUI(web_gui)
    # 显示登录界面
    utils.logger_helper.login.show()
    loop.run_forever()

if __name__ == '__main__':
    print(TimeUtil.formatted_now_with_ms() + " main function run start...")
    setproctitle('ECBot')

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

    try:
        main()
    except Exception as e:
        error_info = traceback.format_exc()  # 获取完整的异常堆栈信息
        utils.logger_helper.error(error_info)

    # qasync.run(main())
