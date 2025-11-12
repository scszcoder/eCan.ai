import requests
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from selenium.common.exceptions import InvalidArgumentException, WebDriverException
import sys
import subprocess
from utils.subprocess_helper import get_windows_creation_flags

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


