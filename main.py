import sys
import asyncio
import qasync
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget, QLabel, QTextEdit
import os
import socket

from LoginoutGUI import *
# from MainGUI import *
from WaitGui import *
from network import *
from unittests import *
from config.app_settings import app_settings
import asyncio
from qasync import QEventLoop
from envi import *

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.


def main():
    app = QApplication.instance()
    if not app:  # If no instance, create a new QApplication
        app = QApplication(sys.argv)
    # app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    global login
    login = Login()

    if login.isCommander():
        print("run as commander......")
        login.show()
        loop.create_task(runCommanderLAN(login))

        loop.run_forever()

    else:
        print("run as platoon...")
        wait_window = WaitWindow()
        wait_window.show()

        loop.create_task(runPlatoonLAN(login, loop, wait_window))

        loop.run_forever()

if __name__ == '__main__':
    ecb_data_homepath = getECBotDataHome()
    runlogs_dir = ecb_data_homepath + "/runlogs"
    if not os.path.isdir(runlogs_dir):
        os.mkdir(runlogs_dir)
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
    # test_batch_ads_profile_conversion()
    # test_run_group_of_tasks()
    # test_schedule_check()
    # test_pyautogui()
    # test_eb_orders_scraper()
    # print("all unit test done...")

    main()
    # qasync.run(main())
