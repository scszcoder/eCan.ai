import axios
import requests
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bot.basicSkill import DEFAULT_RUN_STATUS, STEP_GAP
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

def createAdspowerProfile(api_key, port, profile):

    url = f'http://localhost:{port}/api/v1/user/create'
    print("URL:", url)

    payload = {
        "name": profile["name"],
        "group_id": profile["group_id"],
        "domain_name": profile["domain_name"],
        # "open_urls": ["http://www.gmail.com", "http://www.amazon.com"],
        "repeat_config": ["0"],
        # "username": "",
        # "password": "",
        # "fakey": "",
        # "cookie": "",
        # "ignore_cookie_error": "",
        # "ip": "",
        "country": "us",
        # "region": "us",
        # "city": "us",
        # "remark": "us",
        # "ipchecker": "us",
        # "sys_app_cate_id": "us",
        # "proxyid": "us",
        "fingerprint_config": {
            "language": [
                "en-US"
            ],
            "ua": "Mozilla/5.0 (Linux; Android 8.0.0; BND-AL10 Build/HONORBND-AL10; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/63.0.3239.83 Mobile Safari/537.36 T7/11.5 baiduboxapp/11.5.0.10 (Baidu; P1 8.0.0)",
            "flash": "block",
            "scan_port_type": "1",
            "screen_resolution": "1024_600",
            "fonts": [
                "all"
            ],
            "longitude": "180",
            "latitude": "90",
            "webrtc": "proxy",
            "do_not_track": "true",
            "hardware_concurrency": "default",
            "device_memory": "default"
        },
        "user_proxy_config": {
            "proxy_soft": profile["proxy"]["provider"],
            "proxy_type": profile["proxy"]["type"],     # http
            "proxy_host": profile["proxy"]["host"],
            "proxy_port": profile["proxy"]["port"],
            "proxy_user": profile["proxy"]["user"],
            "proxy_password": profile["proxy"]["pw"]
        }
    }

    headers = {
        # 'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, headers=headers, json=payload)
    if response.status_code == 200:
        print("response:", response)
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to create Adspower profile', response.text)


def createAdspowerGroup(api_key, port, group):

    url = f'http://localhost:{port}/api/v1/group/create'
    print("URL:", url)

    payload = { "group_name": group }

    headers = {
        # 'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, headers=headers, json=payload)
    if response.status_code == 200:
        print("response:", response)
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to create Adspower group', response.text)



def regroupAdspowerProfiles(api_key, group_id, uids, port):
    url = f"http://local.adspower.net:{port}/api/v1/user/regroup"

    payload = {
        "user_ids": uids,
        "group_id": group_id
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    response = requests.request("POST", url, headers=headers, json=payload)

    if response.status_code == 200:
        print("response:", response)
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to stop Adspower profile', response.text)


def startADSWebDriver(local_api_key, port_string, profile_id, in_driver_path, options):
    # webdriver_info = startAdspowerProfile(API_KEY, PROFI LE_ID)
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
def genStepAPIADSCreateProfile(ads_cfg_var, ads_profile_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Create Profile",
        "ads_cfg_var": ads_cfg_var,
        "ads_profile_var": ads_profile_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepAPIADSCreateGroup(ads_cfg_var, group_name_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Create Profile",
        "ads_cfg_var": ads_cfg_var,
        "group_name_var": group_name_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepAPIADSStartProfile(ads_cfg_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Start Profile",
        "ads_cfg_var": ads_cfg_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepAPIADSStopProfile(ads_cfg_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Stop Profile",
        "ads_cfg_var": ads_cfg_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepAPIADSDeleteProfile(ads_cfg_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Delete Profile",
        "ads_cfg_var": ads_cfg_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepAPIADSRegroupProfiles(ads_cfg_var, group_id_var, uids_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "API ADS Regroup Profiles",
        "ads_cfg_var": ads_cfg_var,
        "group_id_var": group_id_var,
        "uids_var": uids_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def processAPIADSCreateProfile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        symTab[step["flag"]] = True
        ads_cfg = symTab[step["ads_cfg_var"]]
        ads_profile = symTab[step["ads_profile_var"]]

        # once works are dispatched, empty the report data for a fresh start.....
        result = createAdspowerProfile(ads_cfg["api_key"], ads_cfg["port"], ads_profile)
        symTab[step["result_var"]] = result

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in APIADSCreateProfile: {traceback.format_exc()} {str(e)}"
        print(f"Error APIADSCreateProfile: {ex_stat}")
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processAPIADSCreateGroup(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        symTab[step["flag"]] = True
        ads_cfg = symTab[step["ads_cfg_var"]]
        group = symTab[step["group_name_var"]]

        # once works are dispatched, empty the report data for a fresh start.....
        result = createAdspowerGroup(ads_cfg["api_key"], ads_cfg["port"], group)
        symTab[step["result_var"]] = result

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
        ads_cfg = symTab[step["ads_cfg_var"]]

        result = startAdspowerProfile(ads_cfg["api_key"], ads_cfg["profile_id"], ads_cfg["port"])
        symTab[step["result_var"]] = result

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
        ads_cfg = symTab[step["ads_cfg_var"]]

        # once works are dispatched, empty the report data for a fresh start.....
        result = stopAdspowerProfile(ads_cfg["api_key"], ads_cfg["profile_id"], ads_cfg["port"])
        symTab[step["result_var"]] = result

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
        ads_cfg = symTab[step["ads_cfg_var"]]

        # once works are dispatched, empty the report data for a fresh start.....
        result = startAdspowerProfile(ads_cfg["api_key"], ads_cfg["profile_id"], ads_cfg["port"])
        symTab[step["result_var"]] = result

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in APIADSCreateProfile: {traceback.format_exc()} {str(e)}"
        print(f"Error APIADSCreateProfile: {ex_stat}")
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS



def processAPIADSRegroupProfiles(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        symTab[step["flag"]] = True
        ads_cfg = symTab[step["ads_cfg_var"]]
        group_id = symTab[step["group_id_var"]]
        uids = symTab[step["uids_var"]]

        # once works are dispatched, empty the report data for a fresh start.....
        result = regroupAdspowerProfiles(ads_cfg["api_key"], group_id, uids, ads_cfg["port"])
        symTab[step["result_var"]] = result

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in APIADSRegroupProfiles: {traceback.format_exc()} {str(e)}"
        print(f"Error APIADSRegroupProfiles: {ex_stat}")
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS

# might need host name info... as group id?
def genInitialADSProfiles(dataJsons, api_Key, port):
    for dj in dataJsons:
        domain = "www.gmail.com"
        group = ""
        profile = {
            "name": dj["email"],
            "group_id": group,
            "domain_name": domain,
            # "open_urls": ["http://www.gmail.com", "http://www.amazon.com"],
            "repeat_config": ["0"],
            # "username": "",
            # "password": "",
            # "fakey": "",
            # "cookie": "",
            # "ignore_cookie_error": "",
            "ip": dj["ip"],
            "country": "us",
            # "region": "us",
            # "city": "us",
            # "remark": "us",
            "ipchecker": "ip2location",
            # "sys_app_cate_id": "us",
            # "proxyid": "us",
            "fingerprint": {
                "language": ["en-US"]
            },
            "proxy": {
                "provider": dj["proxy_provider"],
                "type": "http",  # http
                "host": dj["proxy_host"],
                "port": dj["proxy_port"],
                "user": dj["proxy_un"],
                "pw": dj["proxy_pw"]
            }
        }
        result = createAdspowerProfile(api_key, port, profile)
        # this is half done, correct?


