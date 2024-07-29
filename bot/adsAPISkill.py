
import requests
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.options import Options
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

def startAdspowerProfile(api_key, profile_id):
    url = f'http://localhost:50325/api/v1/browser/start?user_id={profile_id}'
    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data['data']['webdriver']
    else:
        raise Exception('Failed to start Adspower profile', response.text)

def startADSWebDriver():
    webdriver_info = startAdspowerProfile(API_KEY, PROFILE_ID)
    print('WebDriver Info:', webdriver_info)

    webdriver_url = webdriver_info['url']
    options = webdriver.ChromeOptions()
    options.add_experimental_option('debuggerAddress', f"{webdriver_info['ip']}:{webdriver_info['port']}")

    # Set up Selenium WebDriver
    options = Options()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")

    # Connect to the Adspower browser instance
    driver = webdriver.Remote(command_executor=webdriver_url, desired_capabilities=DesiredCapabilities.CHROME, options=options)

    return driver
