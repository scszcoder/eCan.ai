from LoginoutGUI import *
from MainGUI import *
from network import *
from unittests import *
import asyncio
from qasync import QApplication, QEventLoop


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
    # readSkillFile(allsteps, "", "C:/Users/Teco/PycharmProjects/ecbot/resource/skills/enter_amz/enter_amz.ski", 0)
    await future
    return True

def windowlauncher():
    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    global login
    login = Login(app, loop)
    login.show()
    #loop.create_task(udpBroadcaster())
    #loop.create_task(tcpServer())

    if login.isCommander():
        print("run as commander...")
        loop.create_task(runCommanderLAN(login))
        # w = MainWindow()
        # w.show()
        loop.run_forever()
    else:
        print("run as platoon...")
        loop.create_task(runPlatoonLAN())
        # w = MainWindow()
        # w.show()
        loop.run_forever()


if __name__ == '__main__':
    # test_eb_orders_scraper()
    # test_etsy_label_gen()
    # print("all unit test done...")


    windowlauncher()

    # try:
    #     asyncio.run(main())
    # except asyncio.exceptions.CancelledError:
    #     sys.exit(0)

    # quit(app)
