import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import json
import traceback
from bot.basicSkill import DEFAULT_RUN_STATUS, STEP_GAP
from bot.Logger import log3

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


def genStepSeleniumScrapeEbayOrders(orders_var, driver_var, stepN):
    stepjson = {
        "type": "Selenium Scrape Ebay Messages",
        "driver_var": driver_var,
        "orders_var": orders_var
    }

    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepSeleniumScrapeEbayMessages(driver_var, msgs_var, stepN):
    stepjson = {
        "type": "Selenium Scrape Ebay Messages",
        "driver_var": driver_var,
        "msgs_var": msgs_var
    }

    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# this is for Search Ebay Orders By UserNames.
# in some ebay message exchange with customers, the associated order info is not
# present, so we have to search for based on user name to see the purchase info.
def genStepSeleniumScrapeEbayOrderByUserNames(driver_var, users_var, date_range_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Selenium Scrape Ebay Orders By Users",
        "driver_var": driver_var,
        "users_var": users_var,
        "date_range_var": date_range_var,       # should be a list of two strings, each in yyyy-mm-dd format, first is the start date, the second is the end date
        "result_var": result_var,
        "flag_var": flag_var
    }

    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def processSeleniumScrapeEbayMessages(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    try:
        driver = symTab[step["driver_var"]]
        # Scrape the messages list
        messages = driver.find_elements(By.CSS_SELECTOR, 'div.message')  # Adjust selector based on actual HTML
        message_data = []

        for message in messages:
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

        # Filter and open unread messages to get the full thread
        unread_messages = [msg for msg in message_data if msg['read_unread'] == 'unread']
        message_threads = []

        for message in unread_messages:
            message_element = driver.find_element(By.ID, message['message_id'])
            message_element.click()
            time.sleep(3)  # Adjust as needed for page load

            # Scrape the message thread
            thread_elements = driver.find_elements(By.CSS_SELECTOR, 'div.thread-message')  # Adjust selector based on actual HTML
            thread = []

            for thread_element in thread_elements:
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

            message_threads.append({
                'original_message': message,
                'thread': thread
            })

            # Go back to messages list
            driver.back()
            time.sleep(3)  # Adjust as needed for page load



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSeleniumScrapeOrders:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSeleniumScrapeOrders traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat


def processSeleniumScrapeMessages(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        global symTab
        # Scrape the messages list
        driver = symTab[step["driver_var"]]
        messages = driver.find_elements(By.CSS_SELECTOR, 'div.message')  # Adjust selector based on actual HTML
        message_data = []

        for message in messages:
            sender = message.find_element(By.CSS_SELECTOR, '.sender').text
            timestamp = message.find_element(By.CSS_SELECTOR, '.timestamp').text
            message_id = message.get_attribute('id')
            title = message.find_element(By.CSS_SELECTOR, '.title').text
            read_unread = 'unread' if 'unread' in message.get_attribute('class') else 'read'
            contents = message.find_element(By.CSS_SELECTOR, '.snippet').text
            attachments = message.find_element(By.CSS_SELECTOR, '.attachments').text if message.find_element(
                By.CSS_SELECTOR, '.attachments') else None
            order_id = message.find_element(By.CSS_SELECTOR, '.order-id').text if message.find_element(By.CSS_SELECTOR,
                                                                                                       '.order-id') else None

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

        # Filter and open unread messages to get the full thread
        unread_messages = [msg for msg in message_data if msg['read_unread'] == 'unread']
        message_threads = []

        for message in unread_messages:
            message_element = driver.find_element(By.ID, message['message_id'])
            message_element.click()
            time.sleep(3)  # Adjust as needed for page load

            # Scrape the message thread
            thread_elements = driver.find_elements(By.CSS_SELECTOR,
                                                   'div.thread-message')  # Adjust selector based on actual HTML
            thread = []

            for thread_element in thread_elements:
                thread_sender = thread_element.find_element(By.CSS_SELECTOR, '.sender').text
                thread_receiver = thread_element.find_element(By.CSS_SELECTOR, '.receiver').text
                thread_message_id = thread_element.get_attribute('id')
                thread_timestamp = thread_element.find_element(By.CSS_SELECTOR, '.timestamp').text
                thread_title = thread_element.find_element(By.CSS_SELECTOR, '.title').text
                thread_contents = thread_element.find_element(By.CSS_SELECTOR, '.contents').text
                thread_attachments = thread_element.find_element(By.CSS_SELECTOR,
                                                                 '.attachments').text if thread_element.find_element(
                    By.CSS_SELECTOR, '.attachments') else None
                thread_order_id = thread_element.find_element(By.CSS_SELECTOR,
                                                              '.order-id').text if thread_element.find_element(
                    By.CSS_SELECTOR, '.order-id') else None

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

            message_threads.append({
                'original_message': message,
                'thread': thread
            })

            # Go back to messages list
            driver.back()
            time.sleep(3)  # Adjust as needed for page load



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSeleniumScrapeMessages:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSeleniumScrapeMessages traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat



def processSeleniumScrapeEbayOrderByUserNames(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        global symTab
        # Scrape the messages list
        driver = symTab[step["driver_var"]]
        users = symTab[step["users_var"]]
        start_date = symTab[step["date_range_var"]][0]
        end_date = symTab[step["date_range_var"]][0]
        symTab[step["flag_var"]] = True
        symTab[step["result_var"]] = {}

        for user in users:
            order_info = {}
            # bring out the order search page.

            # key in user name, and start search.


            # search result and see if user is found.

            symTab[step["result_var"]][user] = order_info



            # Go back to search page
            driver.back()
            time.sleep(3)  # Adjust as needed for page load



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSeleniumScrapeEbayOrderByUserNames:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSeleniumScrapeEbayOrderByUserNames traceback information not available:" + str(e)
        symTab[step["flag_var"]] = False
        log3(ex_stat)

    return (i + 1), ex_stat