import platform
import sys
import random
from crontab import CronTab
import pyautogui

from Cloud import *

# this function send screen image to cloud, call the API to process the image and obtain the clickables.
class Clickables():
    def __init__(self):
        super(ScreenInfo, self).__init__()
        self.loc = (0, 0)
        self.type = "Close"
        self.level = "window"


class ScreenInfo():
    def __init__(self):
        super(ScreenInfo, self).__init__()
        self.allInfo = {"topwin": [], "Sections": []}


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def readScreen(purpose, region, session, bucket="winrpa"):
    # screen capture and save it to a file
    # region=(0, 0, 300, 400)
    im1 = pyautogui.screenshot(region)
    #im1.save(r"c:\path\to\my\screenshot.png")
    screen_file = ""
    im = pyautogui.screenshot(screen_file, region)

    # send the file to S3
    stat  = send_screen(screen_file, bucket)

    # call API for screen analysis
    result = req_cloud_read_screen(session, screen_file, purpose)

    # to save diskspace, remove the file
    # cleanup after procesing...
    #shutil.rmtree(temp_page_dir)
    os.remove(screen_file)
    # return the response
    return result