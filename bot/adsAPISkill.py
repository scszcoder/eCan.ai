
import requests
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
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
    profile_id = "kk63src"
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

def startADSWebDriver(local_api_key, port_string, profile_id, options):
    # webdriver_info = startAdspowerProfile(API_KEY, PROFILE_ID)
    webdriver_info = startAdspowerProfile(local_api_key, profile_id, port_string)
    print('WebDriver Info:', webdriver_info)
    driver_path = 'C:/Users/songc/PycharmProjects/ecbot' + '/chromedriver-win64/chromedriver.exe'
    driver_path = 'C:/Users/songc/PycharmProjects/ecbot' + '/chromedriver-win32/v92.0.4515.107/chromedriver.exe'
    selenium_address = webdriver_info['data']['ws']['selenium']
    debug_port = webdriver_info['data']['debug_port']

    # Configure Chrome options
    chrome_options = Options()
    # chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
    chrome_options.add_experimental_option("debuggerAddress", selenium_address)

    # Create a Service object using the path to chromedriver
    service = Service(executable_path=driver_path)
    # service = Service(ChromeDriverManager().install())

    # Initialize WebDriver with the specified options and service
    driver = webdriver.Chrome(service=service, options=chrome_options)


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
    #
    # # Merge desired capabilities with options
    # capabilities = DesiredCapabilities.CHROME.copy()
    # options.set_capability('browserName', capabilities['browserName'])
    #
    #
    # # Connect to the Adspower browser instance
    # # driver = webdriver.Remote(command_executor=webdriver_url, desired_capabilities=DesiredCapabilities.CHROME, options=options)
    # driver = webdriver.Remote(command_executor=webdriver_url, options=options)
    print("here it is...")
    print("DRIVER:", driver)
    return driver

