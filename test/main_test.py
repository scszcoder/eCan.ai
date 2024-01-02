import os
import threading
import time

import main
from envi import getECBotDataHome


def thread_func(callback):
    current_thread = threading.current_thread()
    print("thread_func Current Thread:", current_thread)
    time.sleep(3)
    callback()


def callback_func():
    current_thread = threading.current_thread()
    print("callback_func Current Thread:", current_thread)
    main.login.handleLogin()


# 运行测试
if __name__ == '__main__':
    ecb_data_homepath = getECBotDataHome()
    runlogs_dir = ecb_data_homepath + "/runlogs"
    if not os.path.isdir(runlogs_dir):
        os.mkdir(runlogs_dir)

    # t = threading.Thread(target=thread_func, args=(callback_func,))
    # t.start()

    main.windowlauncher()

    # t.join()

    print("ECBot Finished.")
