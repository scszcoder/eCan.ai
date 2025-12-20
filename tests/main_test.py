import os
import threading
import time

from scipy.stats import weibull_min

import main
from envi import getECBotDataHome
from tests.unittests import *


def thread_func(callback):
    current_thread = threading.current_thread()
    print("thread_func Current Thread:", current_thread)
    time.sleep(3)
    callback()


def callback_func():
    current_thread = threading.current_thread()
    print("callback_func Current Thread:", current_thread)
    main.login.handleLogin()


def run_default_tests(mwin, test_setup=None):
    print("run_default_tests with setup:", test_setup)
    results = None
    # results = testLongLLMTask(mwin, test_setup)
    results = testLightRAG(mwin)
    return results



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
