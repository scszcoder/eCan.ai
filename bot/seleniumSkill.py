from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from twocaptcha import TwoCaptcha

from selenium.webdriver.common.by import By
import requests
import time
from datetime import datetime, timedelta
import traceback
import os
from bot.adsAPISkill import startADSWebDriver
from bot.Logger import log3, log6
from bot.basicSkill import *
from config.app_info import app_info
from bot.seleniumScrapeAmzShop import search_phrase


def getChromeOpenTabs():
    response = requests.get('http://localhost:9222/json')
    return response.json()

def getTabWsUrl(tab_index=0):
    tabs = getChromeOpenTabs()
    if len(tabs) > tab_index:
        return tabs[tab_index]['webSocketDebuggerUrl']
    return None


def switchToFirstTab(driver):
    switchToNthTab(driver, 0)

def switchToLastTab(driver):
    switchToNthTab(driver, -1)

def switchToNthTab(driver,nth):
    try:
        window_handles = driver.window_handles
        if window_handles:
            driver.switch_to.window(window_handles[nth])
            print(f"Switched to the last tab with handle: {window_handles[nth]}")
        else:
            print("No open tabs found")
    except Exception as e:
        print(f"Error switching to the nth tab: {e}")


def genStepWebdriverClick(driver, clickable_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Click",
        "clickable": clickable_var,
        "driver_var": driver,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepWebdriverScrollTo(driver_var, target_var, wait_var, increment_var, loc_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Scroll To",
        # "element_type_var": element_type_var,
        # "element_var": element_var,
        "target_var": target_var,
        "driver_var": driver_var,  # anchor, info, text
        "wait_var": wait_var,
        "increment_var": increment_var,
        "loc_var": loc_var,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverCheckVisibility(driver_var, target_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Check Visibility",
        # "element_type_var": element_type_var,
        # "element_var": element_var,
        "target_var": target_var,
        "driver_var": driver_var,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverClick(driver, clickable_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Click",
        "clickable": clickable_var,
        "driver_var": driver,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))




def genStepWebdriverWaitUntilClickable(driver_var, wait_var, element_type_var, element_var, result_type, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Wait Until Clickable",
        "driver_var": driver_var,  # anchor, info, text
        "wait": wait_var,
        "element_type_var": element_type_var,
        "element_var": element_var,
        "result_type": result_type,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepWebdriverSwitchToFrame(driver_var, wait_var, element_type_var, element_var, result_type, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Switch To Frame",
        "driver_var": driver_var,  # anchor, info, text
        "wait": wait_var,
        "element_type_var": element_type_var,
        "element_var": element_var,
        "result_type": result_type,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepWebdriverSwitchToDefaultContent(driver_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Switch To Default Content",
        "driver_var": driver_var,  # anchor, info, text
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepWebdriverWaitForVisibility(driver_var, wait_var, element_type_var, element_var, result_type, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Wait For Visibility",
        "driver_var": driver_var,  # anchor, info, text
        "wait": wait_var,
        "element_type_var": element_type_var,
        "element_var": element_var,
        "result_type": result_type,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))




def genStepWebdriverClick(driver, clickable_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Click",
        "clickable": clickable_var,
        "driver_var": driver,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverKeyIn(driver_var, target_var, text_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Key In",
        "target_var": target_var,
        "driver_var": driver_var,  # anchor, info, text
        "text_var": text_var,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverComboKeys(driver_var, target_var, kl_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Combo Keys",
        "target_var": target_var,
        "driver_var": driver_var,  # anchor, info, text
        "kl_var": kl_var,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverSelectDropDown(driver_var, target_var, text_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Select Drop Down",
        "target_var": target_var,
        "driver_var": driver_var,  # anchor, info, text
        "text_var": text_var,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverNewTab(driver_var, url_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver New Tab",
        "driver_var": driver_var,  # anchor, info, text
        "url_var": url_var,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverCloseTab(driver_var, method_var, tab_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Close Tab",
        "method": method_var,
        "driver_var": driver_var,  # anchor, info, text
        "tab_var": tab_var,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverGoToTab(driver_var, text_var, site_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Go To Tab",
        "driver_var": driver_var,  # anchor, info, text
        "text_var": text_var,  # anchor, info, text
        "site_var": site_var,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverRefreshPage(driver_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Refresh Page",
        "driver_var": driver_var,  # anchor, info, text
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))




def genStepWebdriverBack(driver_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Back",
        "driver_var": driver_var,  # anchor, info, text
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverForward(driver_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Forward",
        "driver_var": driver_var,  # anchor, info, text
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverHoverTo(driver_var, target_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Hover To",
        "driver_var": driver_var,  # anchor, info, text
        "target_var": target_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepWebdriverFocus(driver_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Focus",
        "driver_var": driver_var,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverScreenShot(driver_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Screen Shot",
        "driver_var": driver_var,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverExecuteJs(driver_var, script_var, target_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Execute Js",
        "driver_var": driver_var,  # anchor, info, text
        "script_var": script_var,
        "target_var": target_var,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverQuit(driver_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Quit",
        "driver_var": driver_var,  # anchor, info, text
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepWebdriverStartExistingChrome(driver_path_var, debug_port, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Start Existing Chrome",
        "driver_path": driver_path_var,
        "debug_port": debug_port,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepWebdriverStartNewChrome(driver_path, port, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Start New Chrome",
        "driver_path": driver_path,
        "port": port,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

# local_api_key, port_var, profile_id_var, options):
def genStepWebdriverStartExistingADS(driver_var, ads_api_key_var, profile_id_var, port_var, driver_path_var, options_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Start Existing ADS",
        "driver_var": driver_var,  # anchor, info, text
        "ads_api_key_var": ads_api_key_var,
        "profile_id_var": profile_id_var,
        "port_var": port_var,
        "driver_path_var": driver_path_var,
        "options_var": options_var,
        "result_var": result_var,
        "flag_var": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepWebdriverExtractInfo(driver_var, source_var_type, source_var, wait_var, info_type_var, element_type_var, element_var, multi, result_type, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Extract Info",
        "driver_var": driver_var,  # anchor, info, text
        "wait": wait_var,
        "source_var_type": source_var_type,
        "source_var": source_var,
        "info_type_var": info_type_var,
        "element_type_var": element_type_var,
        "element_var": element_var,
        "multi": multi,
        "result_type": result_type,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverGetValueFromWebElement(driver_var, we_var, we_type, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Get Value",
        "driver_var": driver_var,  # anchor, info, text
        "we_var": we_var,
        "we_type": we_type,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverWaitDownloadDoneAndTransfer(driver_var, dl_dir_var, dl_file_var, current_dir_list_var, wait_var, target_file_var, dl_platform_var, temp_file_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Wait Download Done And Transfer",
        "driver_var": driver_var,  # anchor, info, text
        "wait": wait_var,
        "dl_dir_var": dl_dir_var,
        "dl_file_var": dl_file_var,
        "current_dir_list_var": current_dir_list_var,
        "target_file_var": target_file_var,
        "dl_platform_var": dl_platform_var,             # chrome, firfox, etc.
        "temp_file_var": temp_file_var,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverCheckConnection(driver_var, url_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Check Connection",
        "driver_var": driver_var,  # anchor, info, text
        "url": url_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWebdriverSolveCaptcha(driver_var, api_key_var, site_var, flag_var, stepN):
    stepjson = {
        "type": "Web Driver Solve Captcha",
        "driver_var": driver_var,  # anchor, info, text
        "api_key_var": api_key_var,
        "site_var": site_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# ====== now the processing routines for the step instructions.
def processWebdriverClick(step, i, mission):
    mainwin = mission.get_main_win()

    ex_stat = DEFAULT_RUN_STATUS
    try:
        if symTab[step["clickable"]]:
            symTab[step["clickable"]].click()

            log6("WebdriverClick:["+step["clickable"]+"] clicked", "wan_log", mainwin, mission, i)
        else:
            log6("WebdriverClick:[" + step["clickable"] + "] Error: target not found", "wan_log", mainwin, mission, i)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverClick:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverClick: traceback information not available:" + str(e)
        log6(ex_stat, "wan_log", mainwin, mission, i)

    return (i+1), ex_stat



def processWebdriverStartExistingChrome(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS

        driver_path = step["driver_path"]
        if driver_path == "":
            # default path.
            driver_path = app_info.app_home_path + '/chromedriver-win64/chromedriver.exe'
        elif "/" not in driver_path:            # this is a variable instead of direct path specification
            driver_path = symTab[step["driver_path"]]

        absolute_path = os.path.abspath(driver_path)
        print(f"AAbsolute path: {absolute_path}")
        if not os.path.isfile(driver_path):
            raise ValueError(f"The path is not a valid file: {driver_path}")

        if type(step['debug_port']) == int:
            port = step['debug_port']
        else:
            port = symTab[step['debug_port']]
        # Set Chrome options if needed
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        # chrome_options.add_argument('--no-sandbox --disable-gpu')
        chrome_options.add_argument("--disable-features=SharedStorage,InterestCohort")
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:"+str(port))
        # chrome_options.add_experimental_option('prefs', {
        #     'printing.print_preview_sticky_settings.appState': '{"version":2,"recentDestinations":[{"id":"Save as PDF","origin":"local","account":"","capabilities":{"printer":{"version":2,"display_name":"Save as PDF","printer":{"device_name":"Save as PDF","type":"PDF","supports_scaling":true}}}}],"selectedDestinationId":"Save as PDF","selectedDestinationOrigin":"local","selectedDestinationAccount":"","isCssBackgroundEnabled":true}',
        #     'savefile.default_directory': os.getcwd()  # Set your download directory here
        # })
        # chrome_options.add_argument('--kiosk-printing')

        # Initialize the WebDriver
        service = ChromeService(executable_path=driver_path)
        print("ready to drive.......")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("still alive?????.......")
        symTab[step["result"]] = driver

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorStartExistingChromeDriver:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorStartExistingChromeDriver: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


def processWebdriverStartNewChrome(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        chrome_options = Options()
        # chrome_options.add_argument('--headless')
        if step["port"] == "":
            step["port"] = "9226"       # set to default

        if step["port"].isdigit():
            port = step["port"]
        else:
            port = symTab[step["port"]]
        chrome_options.add_argument('--remote-debugging-port='+str(port))
        chrome_options.add_argument('--user-data-dir=C:\\chrome_data')
        chrome_options.add_argument("--disable-features=SharedStorage,InterestCohort")

        driver_path = step["driver_path"]
        if driver_path == "":
            # default path.
            driver_path = app_info.app_home_path + '/chromedriver-win64/chromedriver.exe'
        elif "/" not in driver_path:  # this is a variable instead of direct path specification
            driver_path = symTab[step["driver_path"]]

        absolute_path = os.path.abspath(driver_path)
        print(f"Absolute path: {absolute_path}")
        if not os.path.isfile(driver_path):
            raise ValueError(f"The path is not a valid file: {driver_path}")


        service = ChromeService(executable_path=driver_path)
        symTab[step["result"]] = webdriver.Chrome(service=service, options=chrome_options)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorStartNewChromeDriver:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorStartNewChromeDriver: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


def processWebdriverStartExistingADS(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        symTab[step["flag_var"]] = True
        api_key = symTab[step["ads_api_key_var"]]
        profile_id = symTab[step["profile_id_var"]]
        port = symTab[step["port_var"]]
        driver_path = symTab[step["driver_path_var"]]
        options = symTab[step["options_var"]]
        print("profile_id, port, api_key, options:", profile_id, port, api_key, options)
        symTab[step["driver_var"]],symTab[step["result_var"]]  = startADSWebDriver(api_key, port, profile_id, driver_path, options)

        if not symTab[step["driver_var"]]:
            symTab[step["flag_var"]] = False
        else:
            symTab[step["result_var"]] = {"api_key": api_key, "port": port, "profile_id": profile_id}

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverStartExistingADS:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverStartExistingADS: traceback information not available:" + str(e)
        print(ex_stat)
        symTab[step["driver_var"]] = None
        symTab[step["result_var"]] = ""
        symTab[step["flag_var"]] = False
    return (i + 1), ex_stat


def smoothScrollToElement(driver, element, y_offset, increment=50):
    try:
        current_scroll_position = driver.execute_script("return window.pageYOffset;") + y_offset
        target_position = element.location['y']
        scroll_height = 0
        MAX_SCROLL_COUNT = 48
        scroll_count = MAX_SCROLL_COUNT
        if current_scroll_position < target_position:
            # Scroll down
            while current_scroll_position < target_position and scroll_count:
                # Scroll by the increment
                driver.execute_script(f"window.scrollBy(0, {increment});")
                # Update the current scroll position
                current_scroll_position = driver.execute_script("return window.pageYOffset;") + y_offset
                # Optional: Add a small delay to make scrolling visible
                random_wait = random.randint(1, 100) / 100
                scroll_count = scroll_count - 1
                time.sleep(random_wait)
        else:
            # Scroll up
            while current_scroll_position > target_position and scroll_count:
                # Scroll by the increment (in the negative direction)
                driver.execute_script(f"window.scrollBy(0, -{increment});")
                # Update the current scroll position
                current_scroll_position = driver.execute_script("return window.pageYOffset;") + y_offset
                # Optional: Add a small delay to make scrolling visible
                random_wait = random.randint(1, 100)/100
                scroll_count = scroll_count - 1
                time.sleep(random_wait)

        if not scroll_count:
            print("WARNING: SCROLL TARGET NOT REACHED!")
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSmoothScrollToElement:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSmoothScrollToElement: traceback information not available:" + str(e)
        print(ex_stat)


def isDisplayed(driver, web_element):
    is_in_viewport = driver.execute_script("""
        var elem = arguments[0],
            bounding = elem.getBoundingClientRect();
        return (
            bounding.top >= 0 &&
            bounding.left >= 0 &&
            bounding.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            bounding.right <= (window.innerWidth || document.documentElement.clientWidth)
        );
    """, web_element)

    return is_in_viewport

def processWebdriverScrollTo(step, i, mission):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        mainwin = mission.get_main_win()
        driver = symTab[step["driver_var"]]
        # element_type = step["element_type_var"]
        # element_name = step["element_var"]
        target_element = symTab[step["target_var"]]
        wait = step["wait_var"]
        increment = step["increment_var"]
        loc = step["loc_var"]
        print("waiting for pagination to load")
        time.sleep(5)
        # Wait until the pagination element is present
        # target_element = WebDriverWait(driver, wait).until(
        #     # EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-cel-widget='MAIN-PAGINATION-72']"))
        #     EC.presence_of_element_located((element_type, element_name))
        # )
        print("pagination LOADED")

        # Smoothly scroll to the pagination element
        # smoothScrollToElement(driver, target_element, increment)

        # Smoothly scroll to the target element
        # driver.execute_script("arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", target_element)

        window_height = driver.execute_script("return window.innerHeight")
        print("window height:", window_height)

        # Calculate the offset to position the element 25% down from the top
        offset = window_height * loc
        print("offset:", offset)

        current_scroll_position = driver.execute_script("return window.pageYOffset;")
        print("current_scroll_position:", current_scroll_position)

        # Smoothly scroll to the element with the desired offset
        # driver.execute_script("""
        #     arguments[0].scrollIntoView({
        #         behavior: 'smooth',
        #         block: 'center'
        #     });
        #     window.scrollBy(0, arguments[1]);
        # """, target_element, offset)
        if target_element:
            target_position = target_element.location['y']
            print("target_position:", target_position, offset)
            # if not target_element.is_displayed():
            if not isDisplayed(driver, target_element):
                # driver.execute_script("arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", target_element)
                scroll_amount = random.randint(30, 80)
                smoothScrollToElement(driver, target_element, offset, scroll_amount)
                # Wait a bit to ensure the scrolling action is complete
                time.sleep(1)  # Short wait to ensure the scroll action is complete

                # Wait a bit to ensure the scrolling action is complete
                WebDriverWait(driver, 2).until(
                    EC.visibility_of(target_element)
                )
                log6("WebdriverScrollTo:[" + step["target_var"] + "]", "wan_log", mainwin, mission, i)
            else:
                log6("Warning No Action - WebdriverScrollTo:[" + step["target_var"] + "] already visible!",
                     "wan_log", mainwin, mission, i)

        else:
            log6("WARNING: WebdriverScrollTo:[" + step["target_var"] + "] NOT FOUND ON PAGE!", "wan_log", mainwin, mission, i)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverScrollTo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverScrollTo: traceback information not available:" + str(e)
        log6(ex_stat, "wan_log", mainwin, mission, i)

    return (i + 1), ex_stat

async def processWebdriverScrollTo8(step, i, mission):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        mainwin = mission.get_main_win()
        driver = symTab[step["driver_var"]]
        # element_type = step["element_type_var"]
        # element_name = step["element_var"]
        target_element = symTab[step["target_var"]]
        wait = step["wait_var"]
        increment = step["increment_var"]
        loc = step["loc_var"]
        print("async waiting for pagination to load")
        time.sleep(5)
        # Wait until the pagination element is present
        # target_element = WebDriverWait(driver, wait).until(
        #     # EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-cel-widget='MAIN-PAGINATION-72']"))
        #     EC.presence_of_element_located((element_type, element_name))
        # )
        print("pagination LOADED")

        # Smoothly scroll to the pagination element
        # smoothScrollToElement(driver, target_element, increment)

        # Smoothly scroll to the target element
        # driver.execute_script("arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", target_element)

        window_height = driver.execute_script("return window.innerHeight")
        print("window height:", window_height)

        # Calculate the offset to position the element 25% down from the top
        offset = window_height * loc
        print("offset:", offset)

        # Smoothly scroll to the element with the desired offset
        # driver.execute_script("""
        #     arguments[0].scrollIntoView({
        #         behavior: 'smooth',
        #         block: 'center'
        #     });
        #     window.scrollBy(0, arguments[1]);
        # """, target_element, offset)
        driver.execute_script("arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", target_element)


        # Wait a bit to ensure the scrolling action is complete
        time.sleep(1)  # Short wait to ensure the scroll action is complete

        # Wait a bit to ensure the scrolling action is complete
        WebDriverWait(driver, 2).until(
            EC.visibility_of(target_element)
        )
        await log6("WebdriverScrollTo:[" + step["target_var"] + "]", "wan_log", mainwin, mission, i)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverScrollTo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverScrollTo: traceback information not available:" + str(e)
        log3(ex_stat, "processWebdriverScrollTo", mainwin)

    return (i + 1), ex_stat


def processWebdriverKeyIn(step, i, mission):
    try:
        mainwin = mission.get_main_win()
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        target = symTab[step["target_var"]]
        text = symTab[step["text_var"]]
        log3("wait for target to load")
        wait = WebDriverWait(driver, 10)
        print("TEXT::", text)
        # wait.until(EC.presence_of_element_located(target))
        target.clear()

        if isinstance(text, list):
            if text[0]:
                text_tbki = " ".join(text)
            else:
                text_tbki = ""
        else:
            text_tbki = text

        target.send_keys(text_tbki)

        log6("WebdriverKeyIn:["+step["target_var"]+"]'"+text_tbki+"'", "wan_log", mainwin, mission, i)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverKeyIn:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverKeyIn: traceback information not available:" + str(e)
        log6(ex_stat, "wan_log", mainwin, mission, i)

    return (i + 1), ex_stat



def processWebdriverComboKeys(step, i, mission):
    try:
        mainwin = mission.get_main_win()
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        target = symTab[step["target_var"]]
        keys_list = symTab[step["kl_var"]]
        log6("WebdriverComboKeys:["+step["target_var"]+"]"+",".join(keys_list), "wan_log", mainwin, mission, i)
        wait = WebDriverWait(driver, 10)

        wait.until(EC.presence_of_element_located(target))

        # Create ActionChains object
        actions = ActionChains(driver)
        for key in keys_list:
            actions.key_down(key)
        for key in reversed(keys_list):
            actions.key_up(key)
        actions.perform()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverComboKeys:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverComboKeys: traceback information not available:" + str(e)
        log6(ex_stat, "wan_log", mainwin, mission, i)

    return (i + 1), ex_stat



def processWebdriverSelectDropDown(step, i, mission):
    try:
        mainwin = mission.get_main_win()
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        # target_type = symTab[step["target_type_var"]]
        dropdown = symTab[step["target_var"]]
        text = symTab[step["text_var"]]
        log3("wait for target to load")
        wait = WebDriverWait(driver, 10)

        # dropdown = wait.until(EC.presence_of_element_located((target_type, target)))
        select_menu = Select(dropdown)
        selected = select_menu.first_selected_option.text
        log6("WebdriverSelectDropDown:[" + step["target_var"] + "]<"+text+">", "wan_log", mainwin, mission, i)
        if selected != text:
            select_menu.select_by_visible_text(text)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverSelectDropDown:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverSelectDropDown: traceback information not available:" + str(e)
        log6(ex_stat, "wan_log", mainwin, mission, i)

    return (i + 1), ex_stat




def processWebdriverNewTab(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        url = step["url_var"]
        log3("opening a new tab")
        driver.switch_to.window(driver.window_handles[0])
        time.sleep(3)
        driver.execute_script(f"window.open('{url}', '_blank');")

        # Switch to the new tab
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(3)
        # Navigate to the new URL in the new tab
        if url:
            if "//" in url:
                driver.get(url)  # Replace with the new URL
                log3("with URL: "+url)
            else:
                driver.get(symTab[url])  # Replace with the new URL
                log3("with URL: "+symTab[url])
            # home_page_loaded = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//a[@href='/Dashboard/UploadBulk' and @data='UploadBulk']")))
            # if home_page_loaded:
            #     # Wait until the "Create Bulk" button is clickable
            #     create_bulk_button = WebDriverWait(driver, 10).until(
            #         EC.element_to_be_clickable((By.XPATH, "//a[@href='/Dashboard/UploadBulk' and @data='UploadBulk']"))
            #     )
            #     print(" bulk upload button found")
            #     # Click the "Create Bulk" button
            #     create_bulk_button.click()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverNewTab:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverNewTab: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat


# "method": method_var - "by name" or "by order"
# "driver_var": "chromedriver"
# "tab_var": tab_var,  # anchor, info, text
# "result": result_var,
# "flag": flag_var
def processWebdriverCloseTab(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]

        if step["method"] == "by name":
            tab_title_txt = symTab[step["tab_var"]]
            log3("closing tab")
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                if tab_title_txt in driver.current_url:
                    break
        else:
            # if not "by name", it'll be "by order"
            all_tabs = driver.window_handles

            # Switch to the second-last tab
            if type(step["tab_var"]) == int:
                driver.switch_to.window(all_tabs[step["tab_var"]])
                # Close the second-last tab

        driver.close()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverCloseTab:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverCloseTab: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat

# this step goes to a designated tab, if not found start a new tab.
def processWebdriverGoToTab(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        # tab_title_txt = symTab[step["text_var"]]
        tab_title_txt = step["text_var"]
        # url = symTab[step["site_var"]]
        if "http" in step["site_var"]:
            url = step["site_var"]
        elif "." not in step["site_var"]:
            url = symTab[step["site_var"]]
        else:
            url = symTab[step["site_var"]]

        log3("swtich to tab")
        found = False

        if not tab_title_txt.isdigit():
            # tab_title_txt = symTab[step["text_var"]]
            print('tab_title_txt:', tab_title_txt)
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                print("title, url:", driver.title, driver.current_url)
                if tab_title_txt in driver.current_url or tab_title_txt in driver.title:
                    found = True
                    break

            if not found:
                driver.execute_script("window.open('');")

                # Switch to the new tab
                driver.switch_to.window(driver.window_handles[-1])

                # Navigate to the new URL in the new tab
                if url:
                    driver.get(url)  # Replace with the new URL
            else:
                if url:
                    print("URL:", url)
                    driver.get(url)

        else:
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                print("win title:", driver.title)

            if int(tab_title_txt) < len(driver.window_handles):
                print("switching to nth tab:", int(tab_title_txt))
                driver.switch_to.window(driver.window_handles[int(tab_title_txt)])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverSwitchTab:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverSwitchTab: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat

def processWebdriverGoToURL(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        log3("refresh")
        if "/" in step["url_var"]:
            url = step["url_var"]
        else:
            url = symTab[step["url_var"]]

        if url:
            driver.get(url)  # Replace with the new URL

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverRefreshPage:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverRefreshPage: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat



def processWebdriverRefreshPage(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        log3("refresh")

        driver.refresh()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverRefreshPage:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverRefreshPage: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat


def processWebdriverBack(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        log3("go to previous page")

        driver.back()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverBackward:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverBackward: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat



def processWebdriverForward(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        log3("refresh")

        driver.forward()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverForward:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverForward: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat



def processWebdriverHoverTo(step, i, mission):
    try:
        mainwin = mission.get_main_win()
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        target = symTab[step["target_var"]]
        # element_to_hover_over = driver.find_element_by_xpath(target)  # Replace with the actual XPath

        # Create an instance of ActionChains
        actions = ActionChains(driver)

        # Perform the hover action
        actions.move_to_element(target).perform()
        log6("WebdriverHoverTo:["+step["target_var"]+"] moved to", "wan_log", mainwin, mission, i)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverHoverTo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverHoverTo: traceback information not available:" + str(e)
        log6(ex_stat, "wan_log", mainwin, mission, i)

    return (i + 1), ex_stat


def processWebdriverScreenShot(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        screenshot_path = symTab[step["screen_var"]]
        log3("taking a screen shot")

        driver.save_screenshot(screenshot_path)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverScreenShot:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverScreenShot: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat



def processWebdriverFocus(step, i, mission):
    try:
        mainwin = mission.get_main_win()
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        target = symTab[step["target_var"]]
        log3("set focus on")

        element_to_hover_over = driver.find_element_by_xpath(target)  # Replace with the actual XPath

        # Locate the input field
        input_field = driver.find_element_by_css_selector(target)  # Replace with the actual CSS selector

        # Focus on the input field using JavaScript
        driver.execute_script("arguments[0].focus();", input_field)
        log3("WebdriverFocus:["+step["target_var"]+"]", "processWebdriverFocus", mainwin)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverFocus:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverFocus: traceback information not available:" + str(e)
        log3(ex_stat, "processWebdriverFocus", mainwin)

    return (i + 1), ex_stat


def execute_js_script(driver, script, *args):
    """
    Execute JavaScript code in the context of the current page.

    :param driver: WebDriver instance.
    :param script: JavaScript code to execute.
    :param args: Arguments to pass to the JavaScript code.
    :return: Result of the JavaScript execution.
    """
    if args is None:
        args = ()

    return driver.execute_script(script, *args)

def processWebdriverExecuteJs(step, i, mission):
    try:
        start = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        mainwin = mission.get_main_win()
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        script = step["script_var"]
        if step["target_var"]:
            target = symTab[step["target_var"]]
        else:
            target = None
        # script_input = symTab[step["script_var"]]
        # script_output = symTab[step["script_var"]]
        log6("WebdriverExecuteJs:[" + step["target_var"] + "]{"+step["script_var"]+"}", "wan_log", mainwin, mission, i)

        # js_script = "return arguments[0] + arguments[1];"
        # param1 = 10
        # param2 = 20

        # Execute the JavaScript script
        result = execute_js_script(driver, script, target)
        print(f"Result of the JavaScript execution: {result}")
        regSteps(step["type"], "", start, True, mainwin)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverExJs:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverExJs: traceback information not available:" + str(e)

        log6(ex_stat, "wan_log", mainwin, mission, i)
        regSteps(step["type"], "", start, False, mainwin)

    return (i + 1), ex_stat



def processWebdriverExtractInfo(step, i, mission):
    try:
        start = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        mainwin = mission.get_main_win()
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        symTab[step["flag"]] = True
        print("driver on tab:", driver.title)
        if type(step["wait"]) == int:
            wait_time = step["wait"]
        else:
            wait_time = symTab[step["wait"]]

        info_type = symTab[step["info_type_var"]]

        element_type = step["element_type_var"]
        element_name = step["element_var"]
        print("element type:", element_type)
        print("element name:", element_name)
        log6(f"Webdriver Searching:[{element_type} {element_name}]", "wan_log", mainwin, mission, i)

        if element_type == "full page":
            if step["result_type"] == "var":
                symTab[step["result"]] = driver.page_source
            elif step["result_type"] == "expr":
                to_words = re.split(r'\[|\(|\{', step["result"])
                sink = to_words[0]
                exec(f"global {sink}\n{step['result']} = driver.page_source")
        else:
            placeholders = re.findall(r'\{(.*?)\}', element_name)

            # Replace each placeholder with the corresponding global variable value
            for placeholder in placeholders:
                if placeholder in globals():
                    element_name = element_name.replace(f'{{{placeholder}}}', str(globals()[placeholder]))
                else:
                    raise ValueError(f"Global variable '{placeholder}' not found.")

            print("updated element name:", element_name)


            if wait_time != 0:
                print("wait until:", wait_time)
                try:
                    wait = WebDriverWait(driver, wait_time)
                    if not step["multi"]:
                        web_element = wait.until(EC.presence_of_element_located((element_type, element_name)))
                    else:
                        web_elements = wait.until(EC.presence_of_all_elements_located((element_type, element_name)))
                except TimeoutException:
                    print(f"Element was not found within {wait_time} seconds.")
                    web_elements = []
                    web_element = None
                    symTab[step["flag"]] = False
                except NoSuchElementException:
                    print(f"Element was not found")
                    web_elements = []
                    web_element = None
                    symTab[step["flag"]] = False
            else:
                print("no wait....")
                try:
                    if step["source_var_type"] == "var" and step["source_var"] == "PAGE":
                        print("find in page")
                        if not step["multi"]:
                            web_element = driver.find_element(element_type, element_name)
                        else:
                            web_elements = driver.find_elements(element_type, element_name)
                    elif step["source_var_type"] == "var":
                        print("find within an element")
                        if not step["multi"]:
                            web_element = symTab[step["source_var"]].find_element(element_type, element_name)
                        else:
                            web_elements = symTab[step["source_var"]].find_elements(element_type, element_name)
                except TimeoutException:
                    print(f"Element was not found within {wait_time} seconds.")
                    web_elements = []
                    web_element = None
                    symTab[step["flag"]] = False
                except NoSuchElementException:
                    print(f"Element was not found")
                    web_elements = []
                    web_element = None
                    symTab[step["flag"]] = False

            if info_type == "text":
                if step["result_type"] == "var":
                    if web_element:
                        print("found text:", web_element.text)
                        symTab[step["result"]] = web_element.text
                    else:
                        symTab[step["result"]] = ""
                elif step["result_type"] == "expr":
                    to_words = re.split(r'\[|\(|\{', step["result"])
                    sink = to_words[0]
                    if step["source_var_type"] == "var" and step["source_var"] == "PAGE":
                        if web_element:
                            exec(f"global {sink}\n{step['result']} = web_element.text\nprint('element text', web_element.text)")
            elif info_type == "web element":
                if step["result_type"] == "var":
                    if not step["multi"]:
                        print("found web element.")
                        symTab[step["result"]] = web_element
                    else:
                        symTab[step["result"]] = web_elements
                        print("found n elements:", len(symTab[step["result"]]))
                elif step["result_type"] == "expr":
                    to_words = re.split(r'\[|\(|\{', step["result"])
                    sink = to_words[0]
                    print("result in expression format", sink)
                    if not step["multi"]:
                        exec(f"global {sink}\n{step['result']} = web_element\nprint('found element-', web_element)")
                    else:
                        exec(f"global {sink}\n{step['result']} = web_elements\nprint('found elements-', web_elements)")

        regSteps(step["type"], "", start, True, mainwin)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverQuit:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverQuit: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag"]] = False
        regSteps(step["type"], "", start, False, mainwin)

    return (i + 1), ex_stat


def processWebdriverWaitUntilClickable(step, i, mission):
    try:
        start = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        mainwin = mission.get_main_win()
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        symTab[step["flag"]] = True

        if type(step["wait"]) == int:
            wait_time = step["wait"]
        else:
            wait_time = symTab[step["wait"]]

        element_type = step["element_type_var"]
        element_name = step["element_var"]
        print("element type:", element_type)
        print("element name:", element_name)

        try:
            print("wait until:", wait_time)
            wait = WebDriverWait(driver, wait_time)

            symTab[step["result"]] = wait.until(EC.element_to_be_clickable((element_type, element_name)))
        except TimeoutException:
            print(f"Element was not found clickable within {wait_time} seconds.")
            symTab[step["result"]] = None
            symTab[step["flag"]] = False

        regSteps(step["type"], "", start, True, mainwin)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverWaitUntilClickable:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverWaitUntilClickable: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag"]] = False
        regSteps(step["type"], "", start, False, mainwin)

    return (i + 1), ex_stat


def processWebdriverSwitchToDefaultContent(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        symTab[step["flag"]] = True

        driver.switch_to.default_content()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverSwitchToDefaultContent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverSwitchToDefaultContent: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat


def processWebdriverSwitchToFrame(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        symTab[step["flag"]] = True

        if type(step["wait"]) == int:
            wait_time = step["wait"]
        else:
            wait_time = symTab[step["wait"]]

        element_type = step["element_type_var"]
        element_name = step["element_var"]
        print("element type:", element_type)
        print("element name:", element_name)


        print("wait until:", wait_time)
        wait = WebDriverWait(driver, wait_time)

        symTab[step["result"]] = wait.until(EC.frame_to_be_available_and_switch_to_it((element_type, element_name)))

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverSwitchToFrame:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverSwitchToFrame: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat


def processWebdriverWaitForVisibility(step, i, mission):
    try:
        start = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        mainwin = mission.get_main_win()
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        symTab[step["flag"]] = True

        if type(step["wait"]) == int:
            wait_time = step["wait"]
        else:
            wait_time = symTab[step["wait"]]

        element_type = step["element_type_var"]
        element_name = step["element_var"]
        print("element type:", element_type)
        print("element name:", element_name)


        print("wait until:", wait_time)
        wait = WebDriverWait(driver, wait_time)

        symTab[step["result"]] = wait.until(EC.visibility_of_element_located((element_type, element_name)))

        regSteps(step["type"], "", start, True, mainwin)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverWaitForVisibility:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverWaitForVisibility: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag"]] = False
        regSteps(step["type"], "", start, False, mainwin)

    return (i + 1), ex_stat



def processWebdriverQuit(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        log3("exiting driver")

        driver.quit()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverQuit:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverQuit: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat

def is_download_complete(file_path, check_interval=1, stable_checks=2):
    """
    Check if the download is complete by verifying that the file size remains stable
    for a specified number of consecutive checks.

    :param file_path: Path to the file being downloaded
    :param check_interval: Time interval (in seconds) between consecutive checks
    :param stable_checks: Number of consecutive checks with stable file size required
                          to consider the download complete
    :return: True if the download is complete, False otherwise
    """
    previous_size = -1
    stable_count = 0

    while True:
        if not os.path.exists(file_path):
            return False

        current_size = os.path.getsize(file_path)

        if current_size == previous_size:
            stable_count += 1
        else:
            stable_count = 0  # Reset counter if file size changes

        if stable_count >= stable_checks:
            return True

        previous_size = current_size
        time.sleep(check_interval)

def get_most_recent_files(directory, n=1, hours=24):
    """
    Get the most recently modified file within the last `hours` in the given directory.

    :param directory: Directory to search for files
    :param hours: Time window in hours to look back for recent files
    :return: The path to the most recent file found, or None if no file is found
    """
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(hours=hours)

    recent_files = []
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if file_mod_time > cutoff_time:
                recent_files.append((file_path, file_mod_time))

    if recent_files:
        # Return the most recently modified file
        sorted_time_files = sorted(recent_files, key=lambda f: f[1], reverse=True)
        if n == 1:
            return max(recent_files, key=lambda x: x[1])[0]
        else:
            return [f[0] for f in sorted_time_files]
    return None

def wait_for_download_completion(download_dir, prev_most_recent, download_file="", timeout=60, check_interval=1, stable_checks=2):
    """
    Wait for the most recent file download to complete by checking for the absence of temporary file extensions,
    ensuring the file exists, monitoring file size stability, and enforcing an overall timeout.

    :param download_dir: The directory where the file is being downloaded
    :param download_file: The file name of the file being downloaded
    :param timeout: Overall timeout in seconds to wait for the download to complete
    :param check_interval: Time interval (in seconds) between consecutive checks
    :param stable_checks: Number of consecutive checks with stable file size required
                          to consider the download complete
    :return: Path to the completed file if the download is successful, None otherwise
    """
    temp_extensions = ['.crdownload', '.part']
    start_time = time.time()

    while True:
        # Check for timeout
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout:
            print(f"Download timed out after {timeout} seconds.")
            return None

        # Get the most recent file in the directory within the last 24 hours
        if download_file:
            # os.listdir(download_dir)
            # recent_file = os.path.join(download_dir, download_file)
            recent_files = get_most_recent_files(download_dir,2)
            if any(download_file in fn for fn in recent_files):
                recent_file = get_most_recent_files(download_dir)
        else:
            recent_file = get_most_recent_files(download_dir)

        if recent_file != prev_most_recent:
            # Check if the file does not have a temporary extension
            if not any(recent_file.endswith(ext) for ext in temp_extensions):
                # File exists and no temp files; check for stability
                if is_download_complete(recent_file, check_interval, stable_checks):
                    return recent_file
            else:
                print(f"Temporary file detected: {recent_file}")
        else:
            print(f"No recent files found in the last 24 hours.")

        time.sleep(check_interval)


def processWebdriverWaitDownloadDoneAndTransfer(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        symTab[step["flag"]] = False

        if type(step["wait"]) == int:
            wait_time = step["wait"]
        else:
            wait_time = symTab[step["wait"]]

        if "/" in step["dl_dir_var"]:
            dl_dir = step["dl_dir_var"]
        else:
            dl_dir = symTab[step["dl_dir_var"]]

        if "/" in step["dl_file_var"]:
            dl_file = step["dl_file_var"][1:]
        else:
            dl_file = symTab[step["dl_file_var"]]

        if "/" in step["target_file_var"]:
            target_file = step["target_file_var"]
        else:
            if step["target_file_var"]:
                target_file = symTab[step["target_file_var"]]
            else:
                target_file = step["target_file_var"]

        dl_platform = step["dl_platform_var"]
        temp_file  = step["temp_file_var"]
        current_dir_list = symTab[step['current_dir_list_var']]
        prev_most_recent_file = current_dir_list[0]
        symTab[step["result"]] = None
        # wait for download to start.
        time.sleep(1)
        print("dl_dir, dl_file, target_file, dl_platform, temp_file:", dl_dir, dl_file, target_file, dl_platform, temp_file)
        completed_file = wait_for_download_completion(dl_dir, prev_most_recent_file, dl_file, timeout=60, check_interval=1, stable_checks=2)
        if os.path.exists(completed_file):
            print(f"Download completed: {completed_file}")
            symTab[step["flag"]] = True
            symTab[step["result"]] = completed_file

            target_dir = os.path.dirname(target_file)
            # Ensure the directory exists, and if not, create it
            os.makedirs(target_dir, exist_ok=True)

            os.rename(completed_file, target_file)
            print(f"file moved to:{target_file}")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverWaitDownloadDoneAndTransfer:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverWaitDownloadDoneAndTransfer: traceback information not available:" + str(e)
        log3(ex_stat, "processWebdriverWaitDownloadDoneAndTransfer")
        symTab[step["flag"]] = False

    return (i + 1), ex_stat


def processWebdriverCheckConnection(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        symTab[step["flag"]] = True

        # Check if session ID is present
        if driver.session_id:
            symTab[step["url"]] = driver.current_url
        else:
            symTab[step["url"]] = ""
            symTab[step["flag"]] = False

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverCheckConnection:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverCheckConnection: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat



def processWebdriverCheckVisibility(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        target_element = symTab[step["target_var"]]
        symTab[step["flag"]] = True
        symTab[step["result"]] = False

        if target_element:
            if isDisplayed(driver, target_element):
                symTab[step["result"]] = True
                print(step["target_var"] + "is visible", "processWebdriverCheckVisibility")
            else:
                print(step["target_var"] + " NOT visible!","processWebdriverCheckVisibility")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverCheckVisibility:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverCheckVisibility: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat



#         "type": "Web Driver Get Value",
#         "driver_var": driver_var,  # anchor, info, text
#         "we_var": we_var,
#         "we_type": we_type,
#         "result": result_var,
#         "flag": flag_var
def processWebdriverGetValueFromWebElement(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        target_element = symTab[step["we_var"]]
        symTab[step["flag"]] = True
        symTab[step["result"]] = None

        if target_element:
            symTab[step["result"]] = target_element.get_attribute("value")
            print(step["target_var"] + "is visible", "processWebdriverGetValueFromWebElement")
        else:
            print(step["we_var"]+" does NOT exist")
            symTab[step["flag"]] = False

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverGetValueFromWebElement:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverGetValueFromWebElement: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat



def processWebdriverSolveCaptcha(step, i):
    try:
        ex_stat = DEFAULT_RUN_STATUS
        driver = symTab[step["driver_var"]]
        api_key = symTab[step["api_key_var"]]
        site = step["site_var"]
        symTab[step["flag"]] = True
        symTab[step["result"]] = None

        if target_element:
            symTab[step["result"]] = target_element.get_attribute("value")
            print(step["target_var"] + "is visible", "processWebdriverSolveCaptcha")
        else:
            print(step["we_var"]+" does NOT exist")
            symTab[step["flag"]] = False

        if site.lower() == "gmail":
            solveGmailCaptcha(driver, api_key)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWebdriverSolveCaptcha:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWebdriverSolveCaptcha: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat

def solveGmailCaptcha(driver, api_key):
    iframe = driver.find_element(By.XPATH, "//iframe[contains(@src, 'recaptcha')]")
    driver.switch_to.frame(iframe)

    # Extract site-key from the page
    site_key = driver.find_element(By.ID, "recaptcha-anchor").get_attribute("data-sitekey")

    driver.switch_to.default_content()  # Switch back to the main page

    print(f"Extracted Site Key: {site_key}")

    # Step 1: Send CAPTCHA solving request to 2Captcha
    captcha_request_url = f"http://2captcha.com/in.php?key={api_key}&method=userrecaptcha&googlekey={site_key}&pageurl={driver.current_url}&json=1"

    response = requests.get(captcha_request_url)
    request_result = response.json()

    if request_result["status"] != 1:
        print("Error sending CAPTCHA to 2Captcha:", request_result)
        driver.quit()
        exit()

    captcha_id = request_result["request"]
    print(f"Captcha request sent! ID: {captcha_id}")

    # Step 2: Wait for the CAPTCHA to be solved
    time.sleep(15)  # Give time for solving

    captcha_result_url = f"http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1"

    while True:
        solution_response = requests.get(captcha_result_url)
        solution_result = solution_response.json()

        if solution_result["status"] == 1:
            captcha_solution = solution_result["request"]
            print(f"Solved CAPTCHA: {captcha_solution}")
            break
        else:
            print("Waiting for CAPTCHA solution...")
            time.sleep(5)

    # Step 3: Inject the CAPTCHA solution into the webpage
    driver.execute_script(f'document.getElementById("g-recaptcha-response").innerHTML="{captcha_solution}";')

    # Step 4: Submit the form
    submit_button = driver.find_element(By.XPATH, "//input[@type='submit']")  # Modify this selector as needed
    submit_button.click()

    print("Form submitted with solved CAPTCHA!")

    # Wait to observe results
    time.sleep(10)
