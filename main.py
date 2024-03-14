from LoginoutGUI import *
from MainGUI import *
from WaitGui import *
from network import *
from unittests import *
from config.app_settings import app_settings
import asyncio
from qasync import QEventLoop
from envi import *

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.


def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.



def run(mainApp):
    #mainWidget = MainWidget()
    mainWidget = MainWindow()
    mainWidget.show()
    quit(mainApp)


def quit(mainApp):
    sys.exit(mainApp.exec())

# app = None
# login = None

async def main():
    # info = cpuinfo.get_cpu_info()
    # print(info)
    loop = asyncio.get_event_loop()
    future = asyncio.Future()

    global app
    app = QApplication(sys.argv)

    # run(app)
    global login
    login = Login(app)
    login.show()
    # login.fakeLogin()
    # allsteps = []
    await future
    return True

def windowlauncher():
    app = QApplication(sys.argv)

    loop = QEventLoop(app)
    # asyncio.set_event_loop(loop)

    global login
    login = Login(app, loop)
    # login.show()
    # loop.create_task(udpBroadcaster())
    # loop.create_task(tcpServer())

    if login.isCommander():
        print("run as commander......")
        loop.create_task(runCommanderLAN(login))
        login.show()
        # w = MainWindow()
        # w.show()
        loop.run_forever()
    else:
        print("run as platoon...")
        wait_window = WaitWindow()
        wait_window.show()
        # Create a thread for the UDP receiver
        # udp_thread = threading.Thread(target=udp_receiver)
        # udp_thread.daemon = True  # Make it a daemon thread to exit when the main program exits
        # udp_thread.start()

        loop.create_task(runPlatoonLAN(login, loop, wait_window))
        # w = MainWindow()
        # w.show()
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

    # print("all unit test done...")


    windowlauncher()



    # try:
    #     asyncio.run(main())
    # except asyncio.exceptions.CancelledError:
    #     sys.exit(0)

    # quit(app)

    print("ECBot Finished.")
