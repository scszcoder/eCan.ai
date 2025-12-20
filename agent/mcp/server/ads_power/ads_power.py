import requests
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from utils.lazy_import import lazy
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from selenium.common.exceptions import InvalidArgumentException, WebDriverException
import sys, os, base64, json
import subprocess
import time, copy
from pathlib import Path
from utils.subprocess_helper import get_windows_creation_flags
from datetime import datetime

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

ADS_BATCH_SIZE = 2

FULL_SITE_MAP = {
    "amz": "amazon.com",
    "etsy": "etsy.com",
    "ebay": "ebay.com",
    "tiktok": "tiktok.com",
    "google": "google.com",
    "youtube": "youtube.com",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "ali": "aliexpress.com",
    "walmart": "walmart.com",
    "paypal": "paypal.com"
}

DEFAULT_SITE_LIST = ["google", "gmail", "amazon"]


def startAdspowerProfile(api_key, profile_id, port):
    url = f'http://local.adspower.net:{port}/api/v1/browser/start?user_id={profile_id}'
    print("URL:", url)

    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers, timeout=10)
    print("response:", response)
    if response.status_code == 200:
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to start Adspower profile', response.text)


def stopAdspowerProfile(api_key, profile_id, port):
    url = f'http://local.adspower.net:{port}/api/v1/browser/stop?user_id={profile_id}'
    print("URL:", url)

    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers, timeout=10)
    print("response:", response)
    if response.status_code == 200:
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to stop Adspower profile', response.text)


def checkAdspowerProfileBrowserStatus(api_key, profile_id, port):
    url = f'http://local.adspower.net:{port}/api/v1/browser/active?user_id={profile_id}'
    print("URL:", url, api_key, port)

    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers, timeout=10)
    print("response:", response)
    if response.status_code == 200:
        data = response.json()
        print("data:", data)
        return data["data"]["status"]
    else:
        raise Exception('Failed to stop Adspower profile', response.text)


def deleteAdspowerProfiles(api_key, users, port):
    # users is a list of string user IDs like ["uid1", "uid2"...]
    url = f'http://local.adspower.net:{port}/api/v1/user/delete'
    print("URL:", url)

    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.post(url, headers=headers, data=users, timeout=10)
    print("response:", response)
    if response.status_code == 200:
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to delete Adspower user profiles', response.text)


def createAdspowerProfile(api_key, port, profile):
    url = f'http://local.adspower.net:{port}/api/v1/user/create'
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
        "remark": profile["remark"],
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
            "proxy_type": profile["proxy"]["type"],  # http
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
    response = requests.request("POST", url, headers=headers, json=payload, timeout=10)
    print("response:", response)
    if response.status_code == 200:
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to create Adspower profile', response.text)


def createAdspowerGroup(api_key, port, group):
    url = f'http://local.adspower.net:{port}/api/v1/group/create'
    print("URL:", url)

    payload = {"group_name": group}

    headers = {
        # 'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, headers=headers, json=payload, timeout=10)
    print("response:", response)
    if response.status_code == 200:
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

    response = requests.request("POST", url, headers=headers, json=payload, timeout=10)
    print("response:", response)
    if response.status_code == 200:
        data = response.json()
        print("data:", data)
        return data
    else:
        raise Exception('Failed to stop Adspower profile', response.text)


def queryAdspowerProfile(api_key, port):
    url = f'http://local.adspower.net:{port}/api/v1/user/list'
    print("URL:", url)

    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    payload = {"page_size": 50}
    headers = {}

    try:
        # response = requests.get(url, headers=headers)
        response = requests.request("GET", url, headers=headers, params=payload, timeout=10)
        print("response:", response)

        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return []

        rj = response.json()
        if rj['code'] == 0:
            print("response:", rj)
            data = rj['data']
            print("data:", data)
            return data["list"]
        else:
            print(f"API Error: {rj['msg']}")
            return []

    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error: ADS Power service is not running or not accessible at {url}")
        print(f"Error details: {e}")
        return []
    except requests.exceptions.Timeout as e:
        print(f"Timeout Error: Request to ADS Power service timed out")
        print(f"Error details: {e}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Request Error: Failed to connect to ADS Power service")
        print(f"Error details: {e}")
        return []
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return []


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
    driver_path = local_api_info["data"]["webdriver"]
    if "data" in local_api_info:
        selenium_address = local_api_info['data']['ws']['selenium']
        debug_port = local_api_info['data']['debug_port']

        # Configure Chrome options
        chrome_options = Options()

        chrome_options.add_argument("--start-maximized")
        # set a common browser user-agent — not for evasion but for correct rendering
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36")

        # chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
        chrome_options.add_experimental_option("debuggerAddress", selenium_address)

        # Light anti-detection tweak compatible with remote debugging
        # Avoid unsupported experimental options entirely except debuggerAddress
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")

        # Create a Service object using the path to chromedriver
        service = Service(executable_path=driver_path, log_output=subprocess.DEVNULL)
        if sys.platform == "win32":
            try:
                service.creationflags = get_windows_creation_flags()
            except Exception:
                pass
        # service = Service(ChromeDriverManager().install())
        print("service", service, "options:", chrome_options, "driver_path:", driver_path, "selenium_address:",
              selenium_address)
        # Initialize WebDriver, with fallback if some options are rejected
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except InvalidArgumentException as e:
            logger.warning(f"Chromedriver rejected some chromeOptions; retrying with minimal options. Error: {e}")
            # Retry with only debuggerAddress (no extra args)
            chrome_options_fallback = Options()
            chrome_options_fallback.add_experimental_option("debuggerAddress", selenium_address)
            driver = webdriver.Chrome(service=service, options=chrome_options_fallback)

        try:
            logger.debug(
                f"Stealth mode settings: navigator.webdriver: {driver.execute_script('return navigator.webdriver')}, -- should be False")
            logger.debug(
                f"Stealth mode settings: navigator.plugins.length: {driver.execute_script('return navigator.plugins.length')}, -- should be > 0")
        except WebDriverException:
            pass

        # inject a tiny patch to prevent detection (guarded) (stealth mode)
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => false})"}
            )
        except WebDriverException:
            pass

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



# might need host name info... as group id?
def genInitialADSProfiles(dataJsons, api_key, port):
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
            "remark": dj["uid"],
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



def connect_to_adspower(mainwin, url):
    try:
        ads_settings = mainwin.config_manager.ads_settings
        webdriver_path = mainwin.getWebDriverPath()
        # global ads_config, local_api_key, local_api_port, sk_work_settings
        ads_port = ads_settings.ads_port
        ads_api_key = ads_settings.ads_api_key
        ads_chrome_version = ads_settings.chrome_version
        scraper_email = ads_settings.default_scraper_email
        print("[CONN To ADS]ads_settings:", ads_port, ads_api_key, ads_chrome_version, scraper_email, webdriver_path)
        web_driver_options = ""
        logger.debug(
            f'check_browser_and_drivers: ads_port: {ads_port}, ads_api_key: {ads_api_key}, ads_chrome_version: {ads_chrome_version}')
        profiles = queryAdspowerProfile(ads_api_key, ads_port)
        loaded_profiles = {}
        for profile in profiles:
            loaded_profiles[profile['username']] = {"uid": profile['user_id'], "remark": profile['remark']}

        ads_profile_id = loaded_profiles[scraper_email]['uid']
        ads_profile_remark = loaded_profiles[scraper_email]['remark']
        logger.debug(f'ads_profile_id, ads_profile_remark: {ads_profile_id}, {ads_profile_remark}')

        webdriver, result = startADSWebDriver(ads_api_key, ads_port, ads_profile_id, webdriver_path, web_driver_options)

        webdriver.switch_to.window(webdriver.window_handles[0])
        time.sleep(2)
        logger.debug(f"openning new tab with URL: {url}")
        webdriver.execute_script(f"window.open('{url}', '_blank');")
        time.sleep(2)
        # Switch to the new tab
        webdriver.switch_to.window(webdriver.window_handles[-1])
        time.sleep(3)
        # Navigate to the new URL in the new tab
        domTree = {}
        if url:
            if not url.startswith("file:///"):
                logger.debug(f"Navigating to live URL with .get(): {url}")
                webdriver.get(url)
                logger.info("opened live URL: " + url)
            else:
                logger.debug(f"Local file URL detected. Skipping webdriver.get() as it's already loaded.")

            # time.sleep(5)

    except Exception as e:
        err_trace = get_traceback(e, "ErrorConnectToAdspower")
        logger.error(err_trace)
        webdriver = None

    if webdriver:
        mainwin.setWebDriver(webdriver)
    return webdriver


def connect_to_existing_chrome(webdriver_path, url=None, debug_port=9222):
    """
    Connect to an existing Chrome browser instance via remote debugging.
    
    Chrome must be started with: --remote-debugging-port=9222
    Example: chrome.exe --remote-debugging-port=9222
    
    Args:
        mainwin: Main window instance with config_manager and setWebDriver method
        url: Optional URL to navigate to after connecting
        debug_port: Chrome remote debugging port (default: 9222)
    
    Returns:
        WebDriver instance or None if connection failed
    """
    driver = None
    try:
        # Get webdriver path from settings
        # webdriver_path = mainwin.getWebDriverPath()
        logger.info(f"[CONN To Chrome] Connecting to existing Chrome on port {debug_port}")
        logger.debug(f"[CONN To Chrome] WebDriver path: {webdriver_path}")

        # Configure Chrome options to connect to existing browser
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
        
        # Anti-detection tweaks
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")

        # Create service with the chromedriver path
        service = Service(executable_path=webdriver_path, log_output=subprocess.DEVNULL)
        if sys.platform == "win32":
            try:
                service.creationflags = get_windows_creation_flags()
            except Exception:
                pass

        # Connect to existing Chrome
        logger.debug(f"[CONN To Chrome] Attempting connection to 127.0.0.1:{debug_port}")
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except InvalidArgumentException as e:
            logger.warning(f"[CONN To Chrome] Chromedriver rejected options, retrying minimal: {e}")
            chrome_options_fallback = Options()
            chrome_options_fallback.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
            driver = webdriver.Chrome(service=service, options=chrome_options_fallback)

        logger.info(f"[CONN To Chrome] Connected successfully! Current URL: {driver.current_url}")
        logger.debug(f"[CONN To Chrome] Window handles: {len(driver.window_handles)}")

        # Inject stealth script
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => false})"}
            )
        except WebDriverException:
            pass

        # Navigate to URL if provided
        if url:
            # Switch to first tab
            driver.switch_to.window(driver.window_handles[0])
            time.sleep(1)
            
            if not url.startswith("file:///"):
                logger.debug(f"[CONN To Chrome] Opening new tab with URL: {url}")
                driver.execute_script(f"window.open('{url}', '_blank');")
                time.sleep(1)
                # Switch to the new tab
                driver.switch_to.window(driver.window_handles[-1])
                time.sleep(2)
                logger.debug(f"[CONN To Chrome] Navigating to: {url}")
                driver.get(url)
                logger.info(f"[CONN To Chrome] Opened URL: {url}")
            else:
                logger.debug(f"[CONN To Chrome] Local file URL detected, skipping navigation")

    except WebDriverException as e:
        err_trace = get_traceback(e, "ErrorConnectToExistingChrome")
        logger.error(f"[CONN To Chrome] WebDriver error - is Chrome running with --remote-debugging-port={debug_port}?")
        logger.error(err_trace)
        driver = None
    except Exception as e:
        err_trace = get_traceback(e, "ErrorConnectToExistingChrome")
        logger.error(err_trace)
        driver = None
        
    return driver


def receivePlatoonAgentsADSProfileUpdateMessage(self, pMsg):
    file_name = self.my_ecb_data_homepath + pMsg["file_name"]           # msg["file_name"] should start with "/"
    file_name_wo_extension = os.path.basename(file_name).split(".")[0]
    file_name_dir = os.path.dirname(file_name)
    new_filename = file_name_dir + "/" + file_name_wo_extension + "_old.txt"
    os.rename(file_name, new_filename)

    file_type = pMsg["file_type"]
    file_contents = pMsg["file_contents"].encode('latin1')  # Encode string to binary data
    with open(file_name, 'wb') as file:
        file.write(file_contents)
        file.close()


def receiveAgentsADSProfilesBatchUpdateMessage(self, pMsg):
    """
    Receive multiple fingerprint profiles sent from the sender side.
    Args:
        pMsg: A dictionary containing:
              - "profiles": A list of dictionaries, each containing:
                  - "file_name": The name of the file to be saved
                  - "file_type": The type of the file (e.g., txt)
                  - "timestamp": The timestamp of the incoming file
                  - "file_contents": The base64-encoded content of the file
    """
    try:
        remote_outdated = []
        profiles = pMsg.get("profiles", [])
        if not profiles:
            logger.debug("ErrorReceiveBatchProfiles: No profiles received.")
            return

        for profile in profiles:
            # Resolve full file path
            file_name = os.path.basename(profile["file_name"])
            incoming_file_name = os.path.join(self.ads_profile_dir, file_name)
            incoming_file_timestamp = profile.get("timestamp")
            file_contents = base64.b64decode(profile["file_contents"])  # Decode base64-encoded binary data

            # Check if the file already exists
            if os.path.exists(incoming_file_name):
                # Compare timestamps
                existing_file_timestamp = os.path.getmtime(incoming_file_name)

                if incoming_file_timestamp > existing_file_timestamp:
                    # Incoming file is newer, replace the existing file
                    with open(incoming_file_name, "wb") as file:
                        file.write(file_contents)

                    os.utime(incoming_file_name, (incoming_file_timestamp, incoming_file_timestamp))
                    logger.debug(f"Updated profile: {incoming_file_name} (newer timestamp)")
                else:
                    # Incoming file is older, skip saving
                    if incoming_file_timestamp < existing_file_timestamp:
                        remote_outdated.append(incoming_file_name)
                    logger.debug(f"Skipped profile: {incoming_file_name} (existing file is newer or the same)")
            else:
                # File doesn't exist, save it
                with open(incoming_file_name, "wb") as file:
                    file.write(file_contents)
                # Optionally, set the timestamp to the incoming file's timestamp (if desired)
                os.utime(incoming_file_name, (incoming_file_timestamp, incoming_file_timestamp))
                logger.debug(f"Saved new profile: {incoming_file_name}")

            logger.debug(f"Successfully updated profile: {incoming_file_name}")
        return remote_outdated

    except Exception as e:
        # Handle and log errors
        err_trace = get_traceback(e, "ErrorReceiveBatchProfiles")
        logger.debug(err_trace)


def batch_send_ads_profiles_to_commander(self, commander_link, file_type, file_paths):
    try:
        if not commander_link:
            logger.debug("ErrorSendFilesToCommander: TCP link doesn't exist")
            return

        profiles = []
        for file_name_full_path in file_paths:
            if os.path.exists(file_name_full_path):
                logger.debug(f"Sending File [{file_name_full_path}] to commander: {self.commanderIP}")
                with open(file_name_full_path, 'rb') as fileTBSent:
                    binary_data = fileTBSent.read()
                    encoded_data = base64.b64encode(binary_data).decode('utf-8')

                    # Embed in JSON
                    file_timestamp = os.path.getmtime(file_name_full_path)
                    profiles.append({
                        "file_name": file_name_full_path,
                        "file_type": file_type,
                        "timestamp": file_timestamp,  # Include file timestamp
                        "file_contents": encoded_data
                    })
            else:
                logger.debug(f"ErrorSendFileToCommander: File [{file_name_full_path}] not found")
                # Send data
                json_data = json.dumps({
                    "type": "botsADSProfilesBatchUpdate",
                    "profiles": profiles
                })

        length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
        commander_link.write(length_prefix + json_data.encode('utf-8'))
        # await commander_link.drain()  # Uncomment if using asyncio
    except Exception as e:
        # Get the traceback information
        err_trace = get_traceback(e, "ErrorReceiveBatchProfiles")
        
        
# this function sends request to all on-line platoons and request they send back
# all the latest finger print profiles of the troop members on that team.
# we will store them onto the local dir, if there is existing ones, compare the time stamp of incoming file and existing file,
# if the incoming file has a later time stamp, then overwrite the existing one.
def syncFingerPrintRequest(self):
    try:
        if self.machine_role == "Commander":
            logger.debug("syncing finger prints")

            reqMsg = {"cmd": "reqSyncFingerPrintProfiles", "contents": "now"}

            # send over scheduled tasks to platton.
            for vehicle in self.vehicles:
                if vehicle.getFieldLink() and "running" in vehicle.getStatus():
                    logger.debug(get_printable_datetime() + "SENDING [" + vehicle.getName() + "]PLATOON[" + vehicle.getFieldLink()[
                        "ip"] + "]: " + json.dumps(reqMsg))

                    self.send_json_to_platoon(vehicle.getFieldLink(), reqMsg)

    except Exception as e:
        # Get the traceback information
        ex_stat = get_traceback(e, "ErrorSyncFingerPrintRequest")
        logger.debug(ex_stat)


# this function updates latest finger prints on this vehicle.
# 1) go to ads dir, look for all xlsx, gather unique emails from username column
# 2) then string part before "@" will be the user name to use.
#    in the finger prints directory, there could be three types of files:
#    i) individual user's text version of finger print profile named {username}.txt for example, JohnSmith.txt, (may or may not exist)
#    ii) text version of batched finger print profiles which starts with "profiles", for example profiles*.txt file, this file could contains multiple individual user's finger print profile
#    iii) xlsx version of batched finger print profiles which starts with "profiles", for example profiles*.txt file, this file could contains multiple individual user's finger print profile (may or may not exist)
# 3) a individual's profile could exist in all three type of files.
# 4) is it easier to just call batch to singles?
def gatherFingerPrints(self):
    try:
        updated_profiles = []
        if self.machine_role == "Platoon":
            logger.debug("gathering finger pritns....")

            # Define the directory containing profiles*.txt and individual profiles

            # Get all profiles*.txt files, sorted by timestamp (latest first)
            batch_files = sorted(
                [
                    os.path.join(self.ads_profile_dir, f)
                    for f in os.listdir(self.ads_profile_dir)
                    if f.startswith("profiles") and f.endswith(".txt")
                ],
                key=os.path.getmtime,
                reverse=True,
            )
            print("time sorted batch_files:", batch_files)

            # Track already updated usernames
            updated_usernames = set()

            # Process each batch file
            for batch_file in batch_files:
                logger.debug(f"Processing batch file: {batch_file}")

                # Extract usernames from the batch file
                with open(batch_file, "r") as bf:
                    batch_content = bf.readlines()

                usernames = set(
                    line.split("=")[1].strip().split("@")[0]  # Extract username before "@"
                    for line in batch_content
                    if line.startswith("username=")
                )
                print("usernames in this batch file:", batch_file, usernames)
                # Exclude already updated usernames when processing this batch
                remaining_usernames = usernames - updated_usernames
                if remaining_usernames:
                    logger.debug(f"Updating profiles for: {remaining_usernames}")
                    updateIndividualProfileFromBatchSavedTxt(self, batch_file,
                                                                  excludeUsernames=list(updated_usernames))
                    # Add updated profiles to the list
                    for username in remaining_usernames:
                        individual_profile_path = os.path.join(self.ads_profiles_dir, f"{username}.txt")
                        updated_profiles.append(individual_profile_path)

                logger.debug(f"ErrorSendFileToCommander: TCP link doesn't exist")
    except Exception as e:
        # Get the traceback information
        ex_stat = get_traceback(e, "ErrorGatherFingerPrints")
        logger.debug(ex_stat)




# all_profiles_csv is the csv file name containing all user profiles.
# batch_csv is the resulting csv file name that will contain only bots associated profiles.
def extractBatchOfProfiles(bots, all_profiles_xls, batch_xls):
    try:
        # df = lazy.pd.read_csv(all_profiles_csv)
        df = lazy.pd.read_excel(all_profiles_xls)

        # Filter rows based on user name key in each dictionary
        this_batch_of_rows = []
        for bot in bots:
            this_batch_of_rows.append(df[df['username'].str.strip() == bot.getEmail()])

        # Concatenate filtered rows into a new DataFrame
        new_df = lazy.pd.concat(this_batch_of_rows)

        # Save the new DataFrame to a CSV file
        # new_df.to_csv(batch_xls, index=False)
        new_df.to_excel(batch_xls, index=False)

    except Exception as e:
        # Get the traceback information
        ex_stat = get_traceback(e, "ErrorExtractBatchOfProfiles")
        logger.debug(ex_stat)


# for All tasks, divide them into batches based on ADS batch limit, for example, low cost ADS supports
# loading 10 profiles at a time only.
# 1) flatten all tasks
# 2) sort all tasks by earliest scheduled start time of all the assigned mission/tasks.
# 3) group them into batches.
def earliest_start(task):
    # Example: Sorting based on the sum of attributes a and b
    if len(task["other_works"]) > 0:
        if len(task["bw_works"]) > 0:
            return min(task["other_works"][0]["start_time"], task["bw_works"][0]["start_time"])
        else:
            return task["other_works"][0]["start_time"]
    else:
        return task["bw_works"][0]["start_time"]

def task_start_time(task):
    return task["start_time"]



def getBotEMail(bid, bots):
    found = [b for b in bots if b.getBid() == bid]
    if len(found) > 0:
        return found[0].getEmail()
    else:
        return ""

# input vTasks: all bot tasks on 1 vehicle.
# input commander: the commander data structure which links to all bots, missions, etc.
# output: input bot tasks are updated with 4 new attributes/keys added to task: bid, b_email, full_site, batch_file
#         a list of batch profile xlsx file names,
# so in the code of executing tasks one by one, when it's time to run, it will check which profile
# Note: no all tasks involves using ADS, so could very well be that out of N bots, there will be less than N lines in
#       profiles.
def formADSProfileBatchesFor1Vehicle(vTasks, vehicle, commander):
    # vTasks, allbots, all_profiles_csv, run_data_dir):
    try:

        all_works = vTasks
        logger.debug("all_works:"+json.dumps(all_works), "formADSProfileBatchesFor1Vehicle", commander)
        logger.debug("after flatten and aggregation, total of "+str(len(all_works))+"tasks in this group!", "formADSProfileBatchesFor1Vehicle", commander)
        time_ordered_works = sorted(all_works, key=lambda x: x["start_time"], reverse=False)
        logger.debug("time_ordered_works:"+json.dumps(time_ordered_works), "formADSProfileBatchesFor1Vehicle", commander)
        logger.debug("fp profiles of commander sent missions1:"+json.dumps([m.getFingerPrintProfile() for m in commander.missions]), "formADSProfileBatchesFor1Vehicle", commander)

        ads_profile_batches_fnames = genAdsProfileBatchs(commander, vehicle.getIP(), time_ordered_works)

        logger.debug("all_ads_batches===>"+json.dumps(ads_profile_batches_fnames), "formADSProfileBatchesFor1Vehicle", commander)
        logger.debug("time_ordered_works===>"+json.dumps(time_ordered_works), "formADSProfileBatchesFor1Vehicle", commander)

    except Exception as e:
        # Get the traceback information
        ex_stat = get_traceback(e, "ErrorFormADSProfileBatchesFor1Vehicle")
        logger.debug(ex_stat)
        ads_profile_batches_fnames=[]

    # sorted_all_ads_batches = sorted(all_ads_batches, key=lambda x: x["start_time"], reverse=False)
    # flattened_ads_tasks = [item for one_ads_batch in all_ads_batches for item in one_ads_batch]
    return time_ordered_works, ads_profile_batches_fnames


def formADSProfileBatches(AllVTasks, commander):
    for vname in AllVTasks:
        vehicle = commander.getVehicleByName(vname)
        if vehicle:
            formADSProfileBatchesFor1Vehicle(AllVTasks['vname'], vehicle, commander)
        else:
            logger.debug("ERROR: Vehicle NOT FOUND:" + vname, "formADSProfileBatches", commander)

# taskgroup will be the full task group on a vehicle.
# profiles_dir is the path name that will hold the resulting files
# all_profiles is the file full path name of the .xls file that contains all available profiles.
# result_list is the variable string name that will holds the result which will be a list of profile file names.


# gather 10 profiles into 1 and use this combined file for batch import.
def combineProfilesXlsx(xlsProfilesToBeLoaded):
    # Replace with the path to your files
    ads_profile_dir = 'path_to_your_excel_files'

    # List to hold dataframes
    dfs = []

    # Iterate over the files in the directory
    for filename in xlsProfilesToBeLoaded:
        if filename.endswith('.xlsx'):
            file_path = os.path.join(ads_profile_dir, filename)
            # Read the excel file and append it to the list
            dfs.append(lazy.pd.read_excel(file_path))

    # Concatenate all dataframes
    combined_df = lazy.pd.concat(dfs, ignore_index=True)

    this_batch = os.path.join(ads_profile_dir, 'this_batch.xlsx')
    # Write the combined dataframe to a new excel file
    combined_df.to_excel(this_batch, index=False)



# this functionr reads an ADS power saved profile in text format and return a json object that contains the file contents.
def readTxtProfile(fname, thisHost):
    pfJsons = []
    pfJson = {}
    nl = 0
    logger.debug(f"reading profile....{fname}", "gatherFingerPrints", thisHost)
    eqcount = 0
    with open(fname, 'r') as file:
        for line in file:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                if key == "acc_id":
                    if nl > 0:
                        pfJsons.append(pfJson)
                        pfJson = {}

                    pfJson[key] = value
                elif key == "cookie":
                    if value.strip():
                        pfJson[key] = json.loads(value)
                    else:
                        pfJson[key] = []
                else:
                    pfJson[key] = value

                nl = nl + 1

        if len(pfJson.keys()) > 0:
            pfJsons.append(pfJson)
    logger.debug("["+str(len(pfJsons))+"] profiles read.....")
    file.close()
    return pfJsons

# read in multiple files, returns a list of jsons
def readTxtProfiles(fnames, host):
    pfJsons = []
    for fname in fnames:
        pfJsons = pfJsons + readTxtProfile(fname, host)

    return pfJsons


# this function removes useless cookies from a ADS Power profile object, so that the cookie is short enough to fit into
# an excel file cell (32768 Byte), and enough to let one log into the target web site, typically 1 gamil + 1 other site.
def removeUselessCookies(pfJson, site_list):
    # for pfJson in pfJsons:
    qualified_cookies = list(filter(lambda x: any(site in x["domain"] for site in site_list), pfJson["cookie"]))
    pfJson["cookie"] = qualified_cookies

# this function takes a pfJson and writes back to a xlsx file so that ADS power can import it.
def genProfileXlsx(pfJsons, fname, batch_bot_mid_keys, site_lists, thisHost):
    # Convert JSON data to a DataFrame
    new_pfJsons = []
    # logger.debug("batch_bot_mid_keys:"+str(len(pfJsons))+" " + json.dumps(batch_bot_mid_keys))
    for one_profile in batch_bot_mid_keys:
        one_un = one_profile.split("_")[0]

        found_match = False
        un = "none"
        for original_pfJson in pfJsons:
            un = original_pfJson["username"].split("@")[0]
            logger.debug("searching user name. "+un+" "+one_un+" from:"+fname, "genProfileXlsx", thisHost)
            if un == one_un:
                found_match = True
                break

        if found_match:
            if one_profile in site_lists.keys():
                site_list = site_lists[one_profile]
            else:
                # just use some default list.
                site_list = DEFAULT_SITE_LIST
            logger.debug("found a match, filter a json cookie....", "genProfileXlsx", thisHost)
            pfJson = copy.deepcopy(original_pfJson)
            removeUselessCookies(pfJson, site_list)
            if pfJson["cookie"]:
                pfJson["cookie"]=json.dumps(pfJson["cookie"])
            else:
                pfJson["cookie"] = ""
            new_pfJsons.append(pfJson)
        else:
            logger.debug("WARNING: user not found in ADS profile txt..."+one_un+"  "+un, "genProfileXlsx", thisHost)

    df = lazy.pd.DataFrame(new_pfJsons)
    logger.debug("genProfileXlsx writing to xlsx:"+fname, "genProfileXlsx", thisHost)
    # Write DataFrame to Excel file
    df.to_excel(fname, index=False)


def genDefaultProfileXlsx(pfJsons, fname):
    # Convert JSON data to a DataFrame
    new_pfJsons = []
    # log3("batch_bot_mid_keys:"+str(len(pfJsons))+" " + json.dumps(batch_bot_mid_keys))

    for original_pfJson in pfJsons:
        site_list = DEFAULT_SITE_LIST
        pfJson = copy.deepcopy(original_pfJson)
        removeUselessCookies(pfJson, site_list)
        if pfJson["cookie"]:
            pfJson["cookie"]=json.dumps(pfJson["cookie"])
        else:
            pfJson["cookie"] = ""
        new_pfJsons.append(pfJson)


    df = lazy.pd.DataFrame(new_pfJsons)
    logger.debug(">>writing to xlsx:"+fname)
    # Write DataFrame to Excel file
    df.to_excel(fname, index=False)



def agggregateProfileTxts2Xlsx(profile_names, xlsx_name, site_lists, thisHost):
    # Convert JSON data to a DataFrame
    logger.debug("read txt profiles:" + json.dumps(profile_names))
    pfJsons = readTxtProfiles(profile_names, thisHost)
    for pfJson in pfJsons:
        un = pfJson["username"].split("@")[0]
        logger.debug("aggregate profile searching user name:" + un)
        if un in site_lists.keys():
            site_list = site_lists[un]
        else:
            # just use some default list.
            site_list = DEFAULT_SITE_LIST
        removeUselessCookies(pfJson, site_list)
        pfJson["cookie"]=json.dumps(pfJson["cookie"])
    df = lazy.pd.DataFrame(pfJsons)
    logger.debug("xlsx writing to:"+xlsx_name)
    # Write DataFrame to Excel file
    df.to_excel(xlsx_name, index=False)



# turn cooke which is a list of json dicts into a string, then overwrite every thing to the file
def genProfileTxt(pfJsons, fname):
    # Convert JSON data to a DataFrame

    with open(fname, 'w') as f:
        for pfJson in pfJsons:
            f.write("\n")
            pfJson["cookie"]=json.dumps(pfJson["cookie"])

            for pfkey in pfJson.keys():
                f.write(pfkey+"="+pfJson[pfkey]+"\n")
    f.close()

# this function takes a pfJson and writes back to a xlsx file so that ADS power can import it.
# site_lists is in the format "{email_before@ : ["google", "gmail", "amazon"]}, .... }
# the reason we need this is full cookie is too large to fit into an excel cell, and
# ads batch import only recognize a xlsx file input. so the cookie field should be
# filtered to contain only sites that a mission needs.
def genProfileXlsxs(pfJsons, fnames, site_lists, thisHost):
    for pfJson, fname in zip(pfJsons, fnames):
        # pfJsons, fname, batch_bot_mid_keys, site_lists, thisHost
        genProfileXlsx(pfJson, fname, site_lists.keys(), site_lists, thisHost)


# this function takes a pfJson and writes back to a xlsx file so that ADS power can import it.
def convertTxtProfiles2XlsxProfiles(fnames, site_lists, thisHost):
    pf_idx = 0
    for fname in fnames:
        basename = os.path.basename(fname)
        dirname = os.path.dirname(fname)
        xls_name = dirname + "/" + basename.split(".")[0]+".xlsx"
        pfjsons = readTxtProfile(fname, thisHost)
        logger.debug("reading in # jsons:"+str(len(pfjsons)))
        genProfileXlsx(pfjsons, xls_name, site_lists.keys(), site_lists, thisHost)
        pf_idx = pf_idx + 1


def convertTxtProfiles2DefaultXlsxProfiles(fnames, host):
    pf_idx = 0
    for fname in fnames:
        basename = os.path.basename(fname)
        dirname = os.path.dirname(fname)
        xls_name = dirname + "/" + basename.split(".")[0]+".xlsx"
        pfjsons = readTxtProfile(fname, host)
        logger.debug("reading in # jsons:"+str(len(pfjsons)))
        genDefaultProfileXlsx(pfjsons, xls_name)
        pf_idx = pf_idx + 1


# create bot ads profiles in batches. each batch can have at most batch_size number of profiles.
# assume each bot already has a txt version of the profile there.
# group by minimize # of batches or maximize # of batches.
# in case of "min batches" will fill a batch to its max capacity first before filling the next batch.
# in case of "max batches" will fill as many batches as possible, this is more for testing purpose.
def genAdsProfileBatchs(thisHost, target_vehicle_ip, task_groups):
    logger.debug("host ads batch size:"+str(thisHost.getADSBatchSize()), "genAdsProfileBatchs", thisHost)
    ads_profile_dir = thisHost.getADSProfileDir()
    method = thisHost.getADSBatchMethod()
    # ads_profile_dir = "C:/AmazonSeller/SelfSwipe/ADSProfiles"
    logger.debug("time_ordered_works:"+json.dumps(task_groups), "genAdsProfileBatchs", thisHost)
    pfJsons_batches = []
    bot_pfJsons=[]
    v_ads_profile_batch_xlsxs = []
    batch_idx = 0
    batch_file = "Host" + target_vehicle_ip + "B" + str(batch_idx) + "profile.xlsx"
    batch_file = ads_profile_dir + "/" + batch_file
    w_idx = 0
    batch_bot_mids = []
    batch_bot_profiles_read = []
    for bot_work in task_groups:
        bid = bot_work["bid"]
        found_bots = list(filter(lambda cbot: cbot.getBid() == bid, thisHost.bots))
        logger.debug("genAdsProfileBatchs found # bots:" + str(len(found_bots)), "genAdsProfileBatchs", thisHost)
        mid = bot_work["mid"]

        found_missions = list(filter(lambda cm: cm.getMid() == mid, thisHost.missions))
        logger.debug("genAdsProfileBatchs found # missions:" + str(len(found_missions)), "genAdsProfileBatchs", thisHost)

        found_mision = None
        if len(found_missions) > 0:
            found_mision = found_missions[0]
            bot_work["fingerprint_profile"] = batch_file
            found_mision.setFingerPrintProfile(batch_file)
            logger.debug("reset found mission fingerprint profile:"+found_mision.getFingerPrintProfile(), "genAdsProfileBatchs", thisHost)
        else:
            bot_work["fingerprint_profile"] = ""

        logger.debug("bot fingerprint_profile:" + bot_work["fingerprint_profile"] + ">", "genAdsProfileBatchs", thisHost)
        print("bot fingerprint_profile:" + bot_work["fingerprint_profile"] + ">")

        if len(found_bots) > 0 and found_mision:
            found_bot = found_bots[0]
            if found_bot.getEmail():
                bot_txt_profile_name = ads_profile_dir + "/" + found_bot.getEmail().split("@")[0]+".txt"
                bot_mid_key = found_bot.getEmail().split("@")[0]+"_m"+str(found_mision.getMid()) + ".txt"
                logger.debug("bot_mid_key: "+bot_mid_key+" bot_txt_profile_name:"+bot_txt_profile_name, "genAdsProfileBatchs", thisHost)

                logger.debug("batch_bot_profiles_read:"+json.dumps(batch_bot_profiles_read), "genAdsProfileBatchs", thisHost)
                if os.path.exists(bot_txt_profile_name) and bot_txt_profile_name not in batch_bot_profiles_read:
                    newly_read = readTxtProfile(bot_txt_profile_name, thisHost)
                    batch_bot_profiles_read.append(bot_txt_profile_name)
                else:
                    # if not thisHost.isPlatoon():
                    print("bot_txt_profile_name doesn't exist!"+bot_txt_profile_name)

                    logger.debug("bot_txt_profile_name doesn't exist!"+bot_txt_profile_name, "genAdsProfileBatchs", thisHost)
                    if not os.path.exists(batch_file):
                        logger.debug("batched xlsx file doesn't exist either!", "genAdsProfileBatchs", thisHost)
                        found_mision.setFingerPrintProfile("")

                    newly_read = []

                batch_bot_mids.append(bot_mid_key)

                bot_pfJsons = bot_pfJsons + newly_read

                # if not thisHost.isPlatoon():
                found_bot.setADSProfile(bot_pfJsons)

                if method == "min batches":
                    if w_idx >= thisHost.getADSBatchSize()-1:
                        # if not thisHost.isPlatoon():
                        genProfileXlsx(bot_pfJsons, batch_file, batch_bot_mids, thisHost.getCookieSiteLists(), thisHost)
                        v_ads_profile_batch_xlsxs.append(batch_file)
                        w_idx = 0
                        bot_pfJsons = []
                        batch_bot_mids = []
                        batch_bot_profiles_read = []
                        batch_idx = batch_idx + 1
                        batch_file = "Host" + target_vehicle_ip + "B" + str(batch_idx) + "profile.xlsx"
                        batch_file = ads_profile_dir + "/" + batch_file
                        logger.debug("batch_file:" + batch_file, "genAdsProfileBatchs", thisHost)
                    else:
                        w_idx = w_idx + 1

                elif method == "max batches":
                    # Every bot gets its own batch (or as many batches as possible)
                    genProfileXlsx(newly_read, batch_file, [bot_mid_key], thisHost.getCookieSiteLists(), thisHost)
                    v_ads_profile_batch_xlsxs.append(batch_file)
                    batch_idx += 1
                    batch_file = f"{ads_profile_dir}/Host{target_vehicle_ip}B{batch_idx}profile.xlsx"

    # take care of the last batch.
    if method == "min batches" and bot_pfJsons:
    # if len(bot_pfJsons) > 0:
        # if not thisHost.isPlatoon():
        genProfileXlsx(bot_pfJsons, batch_file, batch_bot_mids, thisHost.getCookieSiteLists(), thisHost)
        v_ads_profile_batch_xlsxs.append(batch_file)

    return v_ads_profile_batch_xlsxs

# after a batch save, grab individual profiles in the batch and update
# each profile individually both txt and xlsx version so that next time
# a batch can be done easily.
# input: batch_profiles_txt: just saved batch of profiles in txt format:
# site_list:
def updateIndividualProfileFromBatchSavedTxt(mainwin, batch_profiles_txt, settings_var_name="", excludeUsernames=[]):
    pfJsons = readTxtProfile(batch_profiles_txt, mainwin)
    pf_dir = os.path.dirname(batch_profiles_txt)
    # log3("pf_dir:"+pf_dir)
    # log3("pfJsons:"+json.dumps(pfJsons))

    # each pfJson is a full pfJson for a bot
    for pfJson in pfJsons:
        # each pfJson is a json for the bot-mission pair
        # xlsx_file_path = pf_dir + "/" + pfJson["username"].split("@")[0]+".xlsx"
        userInFile = pfJson["username"].split("@")[0]
        txt_file_path = pf_dir + "/" + userInFile + ".txt"
        # logger.debug("txt_file_path:"+txt_file_path)
        # genProfileXlsx([pfJson], xlsx_file_path, site_list)
        if userInFile not in excludeUsernames:
            # existing is a bot's current profile, the cookie section contains all cookies this bot has collected so far.
            if os.path.exists(txt_file_path):
                existing = readTxtProfile(txt_file_path, mainwin)
                # logger.debug("existing:"+json.dumps(existing), "updateIndividualProfileFromBatchSavedTxt", mainwin)
                if existing:
                    existing_cookies = existing[0]["cookie"]
                else:
                    logger.debug("WARNING: existing_cookies empty", "updateIndividualProfileFromBatchSavedTxt", mainwin)
                    existing_cookies = []

                new_cookies = pfJson["cookie"]

                # now merge the new cookies into all cookies.
                pfJson["cookie"] = merge_cookies(existing_cookies, new_cookies)
            else:
                # if the individual bot's profile doesn't even exist, create one.
                logger.debug("Warning: bot text profile doesn't exist - "+txt_file_path, "updateIndividualProfileFromBatchSavedTxt", mainwin)
                with open(txt_file_path, 'w') as file:
                    pass

            #now update txt version of the profile of the bot
            logger.debug("pfJson updating :"+txt_file_path, "updateIndividualProfileFromBatchSavedTxt", mainwin)
            genProfileTxt([pfJson], txt_file_path)

            # find the bot related to this fingerprint and update it.
            found_bot = next((bot for i, bot in enumerate(mainwin.bots) if bot.getEmail() == pfJson["username"]), None)
            if found_bot:
                found_bot.setADSProfile([pfJson])
                # also need to update settings, make sure the ads profile id
                if settings_var_name:
                    symTab[settings_var_name]["ads_profile_id"] = pfJson["id"]
            else:
                logger.debug("Warning: Bot corresponding to pfJson -" + pfJson["username"] + " not found.(no data structure to set value to)", "updateIndividualProfileFromBatchSavedTxt", mainwin)


# for a list of existing cookies, find matching in name and domain and path, if matched all three in newones,
# replace the existing cookie with the one in newones, otherwise, simply add newones into the existing ones.
def merge_cookies(existing, new_ones):
    if existing:
        merged_cookies = existing.copy()

        for new_cookie in new_ones:
            matched_index = None
            for i, existing_cookie in enumerate(merged_cookies):
                if (existing_cookie['name'] == new_cookie['name'] and
                    existing_cookie['domain'] == new_cookie['domain'] and
                    existing_cookie['path'] == new_cookie['path']):
                    matched_index = i
                    break

            if matched_index is not None:
                merged_cookies[matched_index] = new_cookie
            else:
                merged_cookies.append(new_cookie)
    else:
        merged_cookies = new_ones

    return merged_cookies




def updateBatchedProfilesDueToUnknownBatchSave(settings_name, savedPfJsons):
    missionBatchXlsx = symTab[settings_name]["batch_profile"]
    directory = Path(missionBatchXlsx)
    fileParts = missionBatchXlsx.split("B")
    batchPrefix = fileParts[0]+"B"
    xlsxFiles = list(directory.glob(batchPrefix+'*.xlsx'))

    # now read each file in xlsxFiles see whether the xlsx contains any entry of savedPfJsons
    # if so, regenerate the row in xlsxFile .


def get_printable_datetime():
    now = datetime.now()

    # Format the datetime as a string, including milliseconds
    formatted_now = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]
    return formatted_now