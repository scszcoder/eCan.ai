import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import json

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

def runEbayADS():
    webdriver_info = start_adspower_profile(API_KEY, PROFILE_ID)
    print('WebDriver Info:', webdriver_info)

    # Set up Selenium WebDriver with Adspower
    webdriver_url = webdriver_info['url']
    options = Options()
    options.add_experimental_option('debuggerAddress', f"{webdriver_info['ip']}:{webdriver_info['port']}")

    driver = webdriver.Remote(command_executor=webdriver_url, options=options)

    # Login to eBay and navigate to messages
    driver.get('https://mesg.ebay.com/mesgweb/ViewMessages/0/m2m')
    time.sleep(5)  # Adjust as needed for page load

    # Perform login if needed here
    # driver.find_element(By.ID, 'userid').send_keys('your_username')
    # driver.find_element(By.ID, 'pass').send_keys('your_password')
    # driver.find_element(By.ID, 'sgnBt').click()
    # time.sleep(5)

    driver.get('https://www.ebay.com/mys/bo/Messages/Inbox')
    time.sleep(5)  # Adjust as needed for page load

    # Scrape the messages list
    messages = driver.find_elements(By.CSS_SELECTOR, 'div.message')  # Adjust selector based on actual HTML
    message_data = []

    for message in messages:
        try:
            sender = message.find_element(By.CSS_SELECTOR, '.sender').text
            timestamp = message.find_element(By.CSS_SELECTOR, '.timestamp').text
            message_id = message.get_attribute('id')
            title = message.find_element(By.CSS_SELECTOR, '.title').text
            read_unread = 'unread' if 'unread' in message.get_attribute('class') else 'read'
            contents = message.find_element(By.CSS_SELECTOR, '.snippet').text
            attachments = message.find_element(By.CSS_SELECTOR, '.attachments').text if message.find_element(By.CSS_SELECTOR, '.attachments') else None
            order_id = message.find_element(By.CSS_SELECTOR, '.order-id').text if message.find_element(By.CSS_SELECTOR, '.order-id') else None

            message_data.append({
                'sender': sender,
                'timestamp': timestamp,
                'message_id': message_id,
                'title': title,
                'read_unread': read_unread,
                'contents': contents,
                'attachments': attachments,
                'order_id': order_id
            })
        except Exception as e:
            print(f"Error extracting message: {e}")

    # Filter and open unread messages to get the full thread
    unread_messages = [msg for msg in message_data if msg['read_unread'] == 'unread']
    message_threads = []

    for message in unread_messages:
        try:
            message_element = driver.find_element(By.ID, message['message_id'])
            message_element.click()
            time.sleep(3)  # Adjust as needed for page load

            # Scrape the message thread
            thread_elements = driver.find_elements(By.CSS_SELECTOR, 'div.thread-message')  # Adjust selector based on actual HTML
            thread = []

            for thread_element in thread_elements:
                try:
                    thread_sender = thread_element.find_element(By.CSS_SELECTOR, '.sender').text
                    thread_receiver = thread_element.find_element(By.CSS_SELECTOR, '.receiver').text
                    thread_message_id = thread_element.get_attribute('id')
                    thread_timestamp = thread_element.find_element(By.CSS_SELECTOR, '.timestamp').text
                    thread_title = thread_element.find_element(By.CSS_SELECTOR, '.title').text
                    thread_contents = thread_element.find_element(By.CSS_SELECTOR, '.contents').text
                    thread_attachments = thread_element.find_element(By.CSS_SELECTOR, '.attachments').text if thread_element.find_element(By.CSS_SELECTOR, '.attachments') else None
                    thread_order_id = thread_element.find_element(By.CSS_SELECTOR, '.order-id').text if thread_element.find_element(By.CSS_SELECTOR, '.order-id') else None

                    thread.append({
                        'sender': thread_sender,
                        'receiver': thread_receiver,
                        'message_id': thread_message_id,
                        'timestamp': thread_timestamp,
                        'title': thread_title,
                        'contents': thread_contents,
                        'attachments': thread_attachments,
                        'order_id': thread_order_id
                    })
                except Exception as e:
                    print(f"Error extracting thread message: {e}")

            message_threads.append({
                'original_message': message,
                'thread': thread
            })

            # Go back to messages list
            driver.back()
            time.sleep(3)  # Adjust as needed for page load
        except Exception as e:
            print(f"Error opening message thread: {e}")

def genWinADSEbayWebdriverFullfillOrdersSkill():
    print("fullfill using ebay labels")
