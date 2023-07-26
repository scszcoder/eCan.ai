import logging
import random
import sys
import time
import os
from PySide6 import QtCore, QtWidgets, QtGui, QtStateMachine
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
import pyautogui
from Logger import *

import pygetwindow as gw
import subprocess
import xlrd
import pathlib
from transitions import Machine
import random
from Cloud import *
import urllib3.request
from pynput.mouse import Button, Controller


# from QtCore import QRunnable, Qt, QThreadPool
# Get environment variables
USER = os.getenv('API_USER')
mouse = Controller()

# a task is a sequence of ehActions.
class EHACTION():
    def __init__(self, n):
        super().__init__()
        # set thread ID
        self.type = n
        Done = False
        self.fsm = QtStateMachine.QStateMachine()

class SCRN_READ_REQEST():
    def __init__(self, rid = "0", app="na", domain="na", req_type="na", intent="uk", last_move="uk", image_file="uk"):
        super().__init__()
        # set thread ID
        self.id = rid
        self.app = app
        self.domain = domain
        self.req_type = req_type
        self.intent = intent
        self.last_move = last_move
        self.image_file = image_file



# a task is a sequence of ehActions.
class Task(QtCore.QRunnable):
    def __init__(self, n):
        super().__init__()
        # set thread ID
        actSeq = []
        Done = False
        self.states = ['ready', 'browsing', 'searching', 'found', 'buying', 'checking', 'paused', 'end']
        self.transitions = [['start', 'ready', 'browsing'],
                            ['time_is_not_up', 'browsing', 'browsing'],
                       {'trigger': 'network_error', 'source': '*', 'dest': 'paused',
                        'before': 'change_into_super_secret_costume'},
                       {'trigger': 'time_is_up', 'source': '*', 'dest': 'end',
                        'after': 'update_journal'}]
        self.fsm = Machine(self, states=self.states, transitions=self.transitions, initial='ready', send_event=True)


    def run(self):
        # run is a sequence of ehActions.
        read_time = 0
        n_missions2bd = 0
        missions2bd = []
        while not self.Done:
            self.performAction()
            self.openBrowser()
            self.enterSite()
            while not self.time_is_up() and not self.network_in_tact():
                self.browse()
                time.sleep(read_time)
                # if there is a mission assignment.
                if n_missions2bd > 0:
                    for m in missions2bd:
                        if m.type == "search":
                            # do product search.
                            self.search()
                        elif m.type == "buy":
                            self.buy()
                        elif m.type == "check_shipping":
                            self.check_shipping()
                        elif m.type == "feedback":
                            self.feedback()



    def openBrowser(self, wh=100, ww=100, wloc=(60, 60)):
        open_ads(wh, ww, wloc)
        print("opening Browser")


    def enterSite(self, url, htm_dir, htm_file):
        open_url_then_save_page((60, 60), url, htm_dir, htm_file)
        print("Entering Site")

    # read speed in words per minute, default is the average.
    # this dictates how fast to scroll down, of course, this is not
    # the only element, also depends on where in the page.
    # if lots of images, could spend time on images as well.
    #
    def browse(self, scroll_cnt,  readspeed=250, length=3):
        mouse.scroll(0, scroll_cnt)
        print("Entering Site")

    def search(self, readspeed=250):
        print("Entering Site")

    def buy(self, readspeed=250):
        print("Entering Site")

    def check_shipping(self, readspeed=250):
        print("check shipping")

    def feedback(self, readspeed=250):
        print("feedback")

    def gen_shipping_labels(self):
        print("get shipping labels")

    def check_inventories(self):
        print("check inventories")

    def market_research(self):
        print("do market research")

    def time_is_up(self):
        print("get shipping labels")

    def network_in_tact(self):
        print("check inventories")

    def market_research(self):
        print("do market research")

    # the walk process is a series of
    #  *) capture screen, upload screen, get response back
    #      the response is in the form of clickables.
    #  *) capture html file. make sure html file changed.
    #  *) from html file, and screen analysis output, figure out next move.
    #  *) log action.
        #time.sleep(random.randint(700, 2500) / 1000)

def wait(sec):
    time.sleep(sec)


def net_connected(host='http://google.com'):
    try:
        urllib3.request.urlopen(host) #Python 3.x
        return True
    except:
        return False


def scroll_then_snap(loc, cnt, fn):
    # read details from the page.
    pyautogui.moveTo(loc[0], loc[1])
    pyautogui.click()
    mouse.scroll(0, cnt)
    im = pyautogui.screenshot('fn', region=(0,0, 300, 400))


def click_then_snap(loc, fn):
    # read details from the page.
    pyautogui.moveTo(loc[0], loc[1])
    pyautogui.click()
    im = pyautogui.screenshot('fn', region=(0, 0, 300, 400))


# input: already found clickables.
# output: on the screen saving image, find and return the location of the file name input box.
def find_dir_name_box(clickables):
    loc = (0, 0)
    for c in clickables:
        if (c.type == "WIN_FS_DIALOG_DIR_NAME_BOX"):
            loc = c.loc
    return loc



# input: already found clickables.
# output: on the screen saving image, find and return the location of the file name input box.
def find_file_name_box(clickables):
    loc = (0, 0)
    for c in clickables:
        if (c.type == "WIN_FS_DIALOG_FILE_NAME_BOX"):
            loc = c.loc
    return loc


def find_Save_Button(clickables):
    loc = (0, 0)
    for c in clickables:
        if (c.type == "WIN_FS_DIALOG_SAVE_BUTTON"):
            loc = c.loc
    return loc


# input: already found clickables.
# output: on the screen saving image, find and return the location of the file name input box.
def find_file_type_box(clickables):
    loc = (0, 0)
    for c in clickables:
        if (c.type == "WIN_FS_DIALOG_FILE_NAME_BOX"):
            loc = c.loc
    return loc

def close_browser_tab():
    # close the tab, back to where it was.
    pyautogui.hotkey('ctrl', 'w')
    time.sleep(3)

# this function assume a browser window is already brought to the front, the windows location is
# pointed at the html address input field location.
def open_url_then_save_page(win_loc, url, html_path, html_file_name):
    # ss stands for screen save
    log_1(html_path)
    log_1(html_file_name)
    fn = 'C:/CrawlerData/fftemplates/ff_save_as_dialog.png'
    # first, open a html file.
    pyautogui.hotkey('ctrl', 't')
    pyautogui.write(url)
    pyautogui.hotkey('enter')
    time.sleep(8)

    # now save the web page into a file.
    pyautogui.hotkey('ctrl', 's')
    time.sleep(3)

    win_titles = gw.getAllTitles()
    saveas_diag_titles = [i for i in win_titles if 'Save As' in i]

    if len(saveas_diag_titles) >= 1:
        saveas_diag_title = saveas_diag_titles[len(saveas_diag_titles)-1]
        print("window title:", saveas_diag_title)
    else:
        print("Something is Wrong, Save As Not Started.")

    save_file(win_loc, saveas_diag_title, html_path, html_file_name)



# this function assume a browser window is already brought to the front, the windows location is
# pointed at the html address input field location.
def save_file(win_loc, saveas_diag_title, html_path, html_file_name, session):
    fn = 'C:/CrawlerData/fftemplates/ff_save_as_dialog.png'
    saveas_diag_win = gw.getWindowsWithTitle(saveas_diag_title)[0]
    saveas_diag_win.moveTo(win_loc[0], win_loc[0])
    time.sleep(5)

    req = SCRN_READ_REQEST("00", "na", "na", "win_dialog", "save_file", "save_key", fn)

    pyautogui.screenshot(fn, region=(win_loc[0], win_loc[1], 1600, 900))

    results = req_cloud_read_screen_text(session, req)

    dir_loc = find_dir_name_box(results.clickables)
    # log_1(dir_loc)
    pyautogui.moveTo(dir_loc[1], dir_loc[0])
    time.sleep(1)
    pyautogui.click()
    time.sleep(1)
    pyautogui.press('backspace')
    time.sleep(1)
    # log_1(str(pathlib.PureWindowsPath(html_path)))
    pyautogui.write(str(pathlib.PureWindowsPath(html_path)))
    time.sleep(1)
    pyautogui.press('enter')
    time.sleep(1)

    loc = find_file_name_box(results.clickables)
    # log_1(loc)
    pyautogui.moveTo(loc[1], loc[0])
    time.sleep(1)
    pyautogui.click()
    time.sleep(1)
    pyautogui.press('backspace')
    time.sleep(2)
    pyautogui.write(html_file_name)
    time.sleep(2)

    button_image = find_Save_Button(results.clickables)
    pyautogui.click(button_image)
    time.sleep(5)



# open ADS power, resize the window to the specified size, and move the window to the specified location.
# input: window location, window size
# output: status (whether the window is opened or not)
def open_ads(win_height, win_width, win_loc):
    p_adspower = subprocess.Popen(['C:/Program Files (x86)/AdsPower/AdsPower.exe'])
    time.sleep(8)
    win_titles = gw.getAllTitles()
    wins = gw.getAllWindows()

    ads_titles = [i for i in win_titles if 'AdsPower' in i]
    if len(ads_titles) == 1:
        ads_title = ads_titles[0]
        print("window title:", ads_title)
    else:
        print("Something is Wrong, ADS Power Not Started.")

    ads_idx = [idx for idx, s in enumerate(win_titles) if 'AdsPower' in s][0]

    ads_win = gw.getWindowsWithTitle(ads_title)[0]
    ads_win.resizeTo(win_width, win_height)
    ads_win.moveTo(win_loc[0], win_loc[0])
    time.sleep(5)
    scr = pyautogui.screenshot('c:/my_screenshot.png', region=(win_loc[0], win_loc[0], win_width, win_height))


# open ADS power, resize the window to the specified size, and move the window to the specified location.
# input: window location, window size
# output: status (whether the window is opened or not)
def open_portable_firefox(win_height, win_width, win_loc):
    p_firefox = subprocess.Popen(['C:/Users/scadmin/Downloads/FirefoxPortable/FireFoxPortable.exe'])
    time.sleep(5)
    win_titles = gw.getAllTitles()
    wins = gw.getAllWindows()

    ff_titles = [i for i in win_titles if 'Mozilla Firefox' in i]
    log_1(ff_titles)
    if len(ff_titles) >= 1:
        ff_title = ff_titles[0]
        print("window title:", ff_title)
    else:
        print("Something is Wrong, Firefox Not Started.")

    ff_idx = [idx for idx, s in enumerate(win_titles) if 'Mozilla Firefox' in s][0]

    ff_win = gw.getWindowsWithTitle(ff_title)[0]
    ff_win.resizeTo(win_width, win_height)
    ff_win.moveTo(win_loc[0], win_loc[0])
    time.sleep(3)
    scr = pyautogui.screenshot('c:/CrawlerData/my_screenshot.png', region=(win_loc[0], win_loc[0], win_width, win_height))

def open_chrome(win_height, win_width, win_loc):
    p_firefox = subprocess.Popen(['C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'])
    time.sleep(5)
    win_titles = gw.getAllTitles()
    wins = gw.getAllWindows()

    ff_titles = [i for i in win_titles if 'Chrome' in i]
    log_1(ff_titles)
    if len(ff_titles) >= 1:
        ff_title = ff_titles[0]
        print("window title:", ff_title)
    else:
        print("Something is Wrong, Chrome Not Started.")

    ff_idx = [idx for idx, s in enumerate(win_titles) if 'Chrome' in s][0]

    ff_win = gw.getWindowsWithTitle(ff_title)[0]
    ff_win.resizeTo(win_width, win_height)
    ff_win.moveTo(win_loc[0], win_loc[0])
    time.sleep(3)


# load an account profile list file into ADS, then, open these account into terminals,
# return a list of window handlers.
def load_ads(pfile):
    winhs = []

    # in ads,
    # match 'batch import' and click
    # in the pop up, run tesseract, match 'Click or drag file here to upload' and click,
    # in the pop up, locate file directory path input box, write the file path.
    #               locate file type 'Custom Files' and click, select 'All Files',
    #                in file list, in file name input box, type in file name.
    #               then, click 'open' button
    # in ADS, locate select all check box (next to 'serial number'), click on it, and click on all open icon.


    return winhs

# for each account's opened browser windows, set the widow position and size,
# type in 'Ctrl-T' to open a new tab, after this action, the mouse will be automatically put into the html box, and
# we can type right there.
# return: all of the position and size , and html input box's locations of the windows that are successfully connected.
def set_up_window(url, cwin):
    winp = []
    pyautogui.hotkey('ctrl', 't')
    pyautogui.write(url)
    pyautogui.hotkey('enter')
    # the following sequence brings a window to the front.
    cwin.minimize()
    cwin.restore()
    cwin.activate()



