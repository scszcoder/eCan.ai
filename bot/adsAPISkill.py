

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


import requests

# Replace with your actual Adspower API key and profile ID
API_KEY = 'your_adspower_api_key'
PROFILE_ID = 'your_adspower_profile_id'

def start_adspower_profile(api_key, profile_id):
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

webdriver_info = start_adspower_profile(API_KEY, PROFILE_ID)
print('WebDriver Info:', webdriver_info)


from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

webdriver_url = webdriver_info['url']
options = webdriver.ChromeOptions()
options.add_experimental_option('debuggerAddress', f"{webdriver_info['ip']}:{webdriver_info['port']}")


# Set up Selenium WebDriver
options = Options()
options.add_argument("--headless")  # Run in headless mode
options.add_argument("--disable-gpu")

driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)



# Connect to the Adspower browser instance
driver = webdriver.Remote(command_executor=webdriver_url, desired_capabilities=DesiredCapabilities.CHROME, options=options)

# Now you can control the Adspower browser with Selenium
driver.get('https://www.google.com')
print(driver.title)
driver.quit()
