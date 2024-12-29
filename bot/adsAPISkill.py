
import requests
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from basicSkill import DEFAULT_RUN_STATUS, STEP_GAP
import traceback
from bot.Logger import log3


API_CONN = "http://local/adspower.net:50360"


ads_api_conns = [
    {
        "host name": "abc",
        "host ip": "192.168.8.12",
        "api_conn": "http://local/adspower.net:50360"
    },
    {
        "host name": "cde",
        "host ip": "192.168.8.15",
        "api_conn": "http://local/adspower.net:50361"
    }
]

# Replace with your actual Adspower API key and profile ID
API_KEY = 'your_adspower_api_key'
PROFILE_ID = 'your_adspower_profile_id'
PORT = 50325

def startAdspowerProfile(api_key, profile_id, port):

    url = f'http://localhost:{port}/api/v1/browser/start?user_id={profile_id}'
    print("URL:", url)

    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("response:", response)
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to start Adspower profile', response.text)

def stopAdspowerProfile(api_key, profile_id, port):

    url = f'http://localhost:{port}/api/v1/browser/stop?user_id={profile_id}'
    print("URL:", url)

    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("response:", response)
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to stop Adspower profile', response.text)

def createAdspowerProfile(api_key, profile_id, port):

    url = f'http://localhost:{port}/api/v1/user/create'
    print("URL:", url)

    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("response:", response)
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to stop Adspower profile', response.text)


def startADSWebDriver(local_api_key, port_string, profile_id, in_driver_path, options):
    # webdriver_info = startAdspowerProfile(API_KEY, PROFILE_ID)
    result = ""
    local_api_info = startAdspowerProfile(local_api_key, profile_id, port_string)
    print('WebDriver Info:', local_api_info)
    print('WebDriver full path:', in_driver_path)
    # driver_path = 'C:/Users/songc/PycharmProjects/ecbot' + '/chromedriver-win64/chromedriver.exe'
    driver_path = 'C:/Users/songc/PycharmProjects/ecbot' + '/chromedriver-win32/v92.0.4515.107/chromedriver.exe'
    # driver_path = 'C:/Users/songc/PycharmProjects/ecbot' + '/chromedriver-win64/v128.0.6613.86/chromedriver.exe'
    driver_path = in_driver_path
    if "data" in local_api_info:
        selenium_address = local_api_info['data']['ws']['selenium']
        debug_port = local_api_info['data']['debug_port']

        # Configure Chrome options
        chrome_options = Options()
        # chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
        chrome_options.add_experimental_option("debuggerAddress", selenium_address)

        # Create a Service object using the path to chromedriver
        service = Service(executable_path=driver_path)
        # service = Service(ChromeDriverManager().install())

        # Initialize WebDriver with the specified options and service
        driver = webdriver.Chrome(service=service, options=chrome_options)

    elif "msg" in local_api_info:
        if local_api_info['msg'] == 'user account does not exist':
            driver = None
            result = local_api_info['msg']
    else:
        driver = None
        result = "port or driver"

    # webdriver_url = 'http://'+selenium_address+'/wd/hub'
    # options = webdriver.ChromeOptions()
    # # options.add_experimental_option('debuggerAddress', f"{webdriver_info['ip']}:{webdriver_info['port']}")
    # options.add_experimental_option('debuggerAddress', selenium_address)
    #
    # # Set up Selenium WebDriver
    # options = Options()
    # # options.add_argument("--headless")  # Run in headless mode
    # options.add_argument("--disable-gpu")
    #
    # # Merge desired capabilities with options
    # capabilities = DesiredCapabilities.CHROME.copy()
    # options.set_capability('browserName', capabilities['browserName'])
    #
    # # Connect to the Adspower browser instance
    # # driver = webdriver.Remote(command_executor=webdriver_url, desired_capabilities=DesiredCapabilities.CHROME, options=options)
    # driver = webdriver.Remote(command_executor=webdriver_url, options=options)
    print("here it is...DRIVER:", driver)
    return driver, result

# local API instructions
def genStepAPIADSCreateProfile(schedule_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Create Profile",
        "schedule_var": schedule_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepAPIADSStartProfile(schedule_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Start Profile",
        "schedule_var": schedule_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepAPIADSStopProfile(schedule_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Stop Profile",
        "schedule_var": schedule_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepAPIADSDeleteProfile(schedule_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Delete Profile",
        "schedule_var": schedule_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepAPIADSRegroupProfile(schedule_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Regroup Profile",
        "schedule_var": schedule_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def processAPIADSCreateProfile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        symTab[step["flag"]] = True
        symTab[step["result_var"]] = mainWin.handleCloudScheduledWorks(symTab[step["schedule_var"]])

        # once works are dispatched, empty the report data for a fresh start.....
        if len(mainWin.todays_work["tbd"]) > 0:
            mainWin.todays_work["tbd"][0]["status"] = ex_stat
            # now that a new day starts, clear all reports data structure
            mainWin.todaysReports = []
        else:
            log3("WARNING!!!! no work TBD after fetching schedule...", "fetchSchedule", mainWin)


    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in APIADSCreateProfile: {traceback.format_exc()} {str(e)}"
        print(f"Error APIADSCreateProfile: {ex_stat}")
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processAPIADSStartProfile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        symTab[step["flag"]] = True
        symTab[step["result_var"]] = mainWin.handleCloudScheduledWorks(symTab[step["schedule_var"]])

        # once works are dispatched, empty the report data for a fresh start.....
        if len(mainWin.todays_work["tbd"]) > 0:
            mainWin.todays_work["tbd"][0]["status"] = ex_stat
            # now that a new day starts, clear all reports data structure
            mainWin.todaysReports = []
        else:
            log3("WARNING!!!! no work TBD after fetching schedule...", "fetchSchedule", mainWin)


    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in APIADSCreateProfile: {traceback.format_exc()} {str(e)}"
        print(f"Error APIADSCreateProfile: {ex_stat}")
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS



def processAPIADSStopProfile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        symTab[step["flag"]] = True
        symTab[step["result_var"]] = mainWin.handleCloudScheduledWorks(symTab[step["schedule_var"]])

        # once works are dispatched, empty the report data for a fresh start.....
        if len(mainWin.todays_work["tbd"]) > 0:
            mainWin.todays_work["tbd"][0]["status"] = ex_stat
            # now that a new day starts, clear all reports data structure
            mainWin.todaysReports = []
        else:
            log3("WARNING!!!! no work TBD after fetching schedule...", "fetchSchedule", mainWin)


    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in APIADSCreateProfile: {traceback.format_exc()} {str(e)}"
        print(f"Error APIADSCreateProfile: {ex_stat}")
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS



def processAPIADSDeleteProfile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        symTab[step["flag"]] = True
        symTab[step["result_var"]] = mainWin.handleCloudScheduledWorks(symTab[step["schedule_var"]])

        # once works are dispatched, empty the report data for a fresh start.....
        if len(mainWin.todays_work["tbd"]) > 0:
            mainWin.todays_work["tbd"][0]["status"] = ex_stat
            # now that a new day starts, clear all reports data structure
            mainWin.todaysReports = []
        else:
            log3("WARNING!!!! no work TBD after fetching schedule...", "fetchSchedule", mainWin)


    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in APIADSCreateProfile: {traceback.format_exc()} {str(e)}"
        print(f"Error APIADSCreateProfile: {ex_stat}")
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS



def processAPIADSRegroupProfile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        symTab[step["flag"]] = True
        symTab[step["result_var"]] = mainWin.handleCloudScheduledWorks(symTab[step["schedule_var"]])

        # once works are dispatched, empty the report data for a fresh start.....
        if len(mainWin.todays_work["tbd"]) > 0:
            mainWin.todays_work["tbd"][0]["status"] = ex_stat
            # now that a new day starts, clear all reports data structure
            mainWin.todaysReports = []
        else:
            log3("WARNING!!!! no work TBD after fetching schedule...", "fetchSchedule", mainWin)


    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in APIADSCreateProfile: {traceback.format_exc()} {str(e)}"
        print(f"Error APIADSCreateProfile: {ex_stat}")
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS
