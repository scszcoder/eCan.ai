from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import requests
import time
import traceback
import os
from bot.adsAPISkill import startADSWebDriver

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


def startExistingChromeDriver():
    try:
        driver_path = 'C:/Users/songc/PycharmProjects/ecbot' + '/chromedriver-win64/chromedriver.exe'
        absolute_path = os.path.abspath(driver_path)
        print(f"Absolute path: {absolute_path}")
        if not os.path.isfile(driver_path):
            raise ValueError(f"The path is not a valid file: {driver_path}")

        # Set Chrome options if needed
        chrome_options = Options()
        # chrome_options.add_argument('--headless')
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        chrome_options.add_experimental_option('prefs', {
            'printing.print_preview_sticky_settings.appState': '{"version":2,"recentDestinations":[{"id":"Save as PDF","origin":"local","account":"","capabilities":{"printer":{"version":2,"display_name":"Save as PDF","printer":{"device_name":"Save as PDF","type":"PDF","supports_scaling":true}}}}],"selectedDestinationId":"Save as PDF","selectedDestinationOrigin":"local","selectedDestinationAccount":"","isCssBackgroundEnabled":true}',
            'savefile.default_directory': os.getcwd()  # Set your download directory here
        })
        chrome_options.add_argument('--kiosk-printing')

        # Initialize the WebDriver
        service = ChromeService(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorStartExistingChromeDriver:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorStartExistingChromeDriver: traceback information not available:" + str(e)
        print(ex_stat)

    return driver


def startNewChromeDriver():
    wdriver = webdriver.Chrome()
    return wdriver


def startExistingADSDriver():
    return startADSWebDriver


def quitDriver(driver):
    try:
        driver.quit()
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQuitDriver:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQuitDriver: traceback information not available:" + str(e)
        print(ex_stat)

def smoothScrollToElement(driver, element):
    try:
        y_position = element.location['y']
        scroll_height = 0
        increment = 50  # Pixels to scroll each time

        while scroll_height < y_position:
            driver.execute_script(f"window.scrollBy(0, {increment});")
            scroll_height += increment
            time.sleep(0.01)  # Pause to make scrolling smooth

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSmoothScrollToElement:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSmoothScrollToElement: traceback information not available:" + str(e)
        print(ex_stat)

def scrollTo(driver):
    try:
        print("waiting for pagination to load")
        time.sleep(5)
        # Wait until the pagination element is present
        pagination_element = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-cel-widget='MAIN-PAGINATION-72']"))
        )
        print("pagination LOADED")

        # Smoothly scroll to the pagination element
        smoothScrollToElement(driver, pagination_element)

        # Wait a bit to ensure the scrolling action is complete
        time.sleep(2)  # Short wait to ensure the scroll action is complete

        print("scrolled.")

        # Wait a bit to ensure the scrolling action is complete
        WebDriverWait(driver, 2).until(
            EC.visibility_of(pagination_element)
        )

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorScrollTo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorScrollTo: traceback information not available:" + str(e)
        print(ex_stat)


