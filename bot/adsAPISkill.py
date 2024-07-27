
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import re

import traceback
import time

API_CONN = "http://local/adspower.net:50360"


ads_api_conns = [
    {
        "host name": "DESKTOP-DLLV0",
        "host ip": "192.168.0.18",
        "api key": "f355595416815a7e237f1250723b121e",
        "api conn": "http://local.adspower.net:50360"
    },
    {
        "host name": "DESKTOP-KA6HM83",
        "host ip": "192.168.0.3",
        "api key": "f355595416815a7e237f1250723b121e",
        "api conn": "http://local/adspower.net:50361"
    },
    {
        "host name": "HP-ECBOT",
        "host ip": "192.168.0.3",
        "api key": "f355595416815a7e237f1250723b121e",
        "api conn": "http://local/adspower.net:50361"
    }
]


import requests

# Replace with your actual Adspower API key and profile ID
API_KEY = 'your_adspower_api_key'
PROFILE_ID = 'your_adspower_profile_id'


def scrape_message_list(driver):
    messages = []
    try:
        # Locate the table body containing the message rows
        tbody = driver.find_element(By.XPATH, "//tbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")

        for row in rows:
            message = {}
            message['id'] = row.get_attribute('id')
            message['from'] = row.find_element(By.XPATH, ".//td[contains(@id, '-from')]//div").text
            message['subject'] = row.find_element(By.XPATH, ".//td[contains(@id, '-sub')]//div").text
            message['received'] = row.find_element(By.XPATH, ".//td[contains(@id, '-msg-recvd')]//div").text
            messages.append(message)

    except Exception as e:
        print(f"Error: {e}")

    return messages


# Function to scrape the message details
def scrape_message_details(driver):
    details = {}
    try:
        details['from'] = driver.find_element(By.XPATH, "//div[@id='msg-desc']//span[2]").text
        details['to'] = driver.find_element(By.XPATH, "//div[@id='msg-desc']//span[4]").text
        details['sent'] = driver.find_element(By.XPATH, "//div[@id='msg-desc']//span[6]").text
        details['subject'] = driver.find_element(By.XPATH, "//div[@id='msg-desc']/h2").text

        # Assume the message body is in an iframe
        iframe = driver.find_element(By.ID, "email_iframe")
        driver.switch_to.frame(iframe)
        details['body'] = driver.find_element(By.XPATH, "//body").text
        driver.switch_to.default_content()

    except Exception as e:
        print(f"Error: {e}")

    return details


def reply_to_message(driver):
    try:
        # Click the reply button
        reply_button = driver.find_element(By.XPATH, "//span[@id='reply-btn']/a")
        reply_button.click()

        # Wait for the reply form to be visible
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "replyForm"))
            # Adjust the selector based on the actual reply form ID or class
        )

        # Fill in the reply form
        reply_textarea = driver.find_element(By.ID,
                                             "replyTextarea")  # Adjust the selector based on the actual textarea ID or class
        reply_textarea.send_keys("This is a sample reply message.")

        # Click the send button
        send_button = driver.find_element(By.ID,
                                          "sendButton")  # Adjust the selector based on the actual send button ID or class
        send_button.click()

    except Exception as e:
        print(f"Error: {e}")


def parse_message_body(body):
    # print("===================================================")
    # print(body)
    # print("*******************************************************")
    sender_match = re.search(r'New message from: (\S+)', body)
    sender_username = sender_match.group(1) if sender_match else 'unknown_sender'


    item_id_match = re.search(r'Item ID: (\d+)', body)
    quantity_remaining_match = re.search(r'Quantity Remaining: (\d+)', body)
    order_number_match = re.search(r'Order Number: ([\d-]+)', body)
    transaction_id_match = re.search(r'Transaction ID: ([\d-]+)', body)
    email_reference_match = re.search(r'Email reference id: \[#(.+?)#\]', body)

    item_id = item_id_match.group(1) if item_id_match else None
    quantity_remaining = quantity_remaining_match.group(1) if quantity_remaining_match else None
    order_number = order_number_match.group(1) if order_number_match else None
    transaction_id = transaction_id_match.group(1) if transaction_id_match else None
    email_reference = email_reference_match.group(1) if email_reference_match else None

    body = re.sub(r'Get to know the buyer.*$', '', body, flags=re.DOTALL)

    # First pass: Count the number of messages
    lines = body.split('\n')
    message_count = 0

    for line in lines:
        line = line.strip()
        if line.startswith('New message') or line.startswith('Your previous message') or line.startswith(
                f'{sender_username}:'):
            message_count += 1

    # Second pass: Capture the messages up to the last message
    cleaned_body = []
    current_message_count = 0
    inside_thread = False
    empty_line_count = 0

    for line in lines:
        line = line.strip()
        if line:
            # print("NE line:", line)
            empty_line_count = 0
            if inside_thread:
                cleaned_body.append(line)
                if line.startswith('New message') or line.startswith('Your previous message') or line.startswith(
                        f'{sender_username}:'):
                    # print("in thread now....")
                    current_message_count = current_message_count + 1

            elif line.startswith('New message') or line.startswith('Your previous message') or line.startswith(
                    f'{sender_username}:'):
                # print("in thread now....")
                inside_thread = True
                cleaned_body.append(line)
                current_message_count = current_message_count + 1

            # print("counters", message_count, current_message_count, empty_line_count)
        else:
            # print("empty", message_count, current_message_count, empty_line_count)
            empty_line_count += 1
            if current_message_count == message_count and empty_line_count > 3:
                break
            if inside_thread:
                cleaned_body.append(line)

    # Remove empty lines and irrelevant system messages
    cleaned_body = [line for line in cleaned_body if
                    line and not line.startswith(('Item ID:', 'Quantity Remaining:', 'Email reference id:'))]
    # print("cleaned body", cleaned_body)
    # Divide messages into a thread
    thread = []
    current_message = []
    current_sender = None

    for line in cleaned_body:
        if line.startswith('New message') or line.startswith('Your previous message'):
            if current_message and current_sender:
                thread.append({
                    'from': current_sender,
                    'msg': '\n'.join(current_message).strip()
                })
                current_message = []
            current_sender = 'You'
            # Skip "New message:" part
            if line.startswith('New message:'):
                line = line[len('New message:'):].strip()
                if line:
                    current_message.append(line)
        elif line.startswith(f'{sender_username}:'):
            if current_message and current_sender:
                thread.append({
                    'from': current_sender,
                    'msg': '\n'.join(current_message).strip()
                })
                current_message = []
            current_sender = sender_username
            # Skip "sender_username:" part
            if line.startswith(f'{sender_username}:'):
                line = line[len(f'{sender_username}:'):].strip()
                if line:
                    current_message.append(line)
        else:
            current_message.append(line)

    if current_message and current_sender:
        thread.append({
            'from': current_sender,
            'msg': '\n'.join(current_message).strip()
        })

    conversation = {
        "item id": item_id,
        "order number": order_number,
        "transaction id": transaction_id,
        "quantity remaining": quantity_remaining,
        "email reference": email_reference,
        "thread": thread
    }

    return conversation

def start_adspower_profile(hostname, profile_id="kk63src"):
    driver = None
    host_ads = next((conn for i, conn in enumerate(ads_api_conns) if conn["host name"] == hostname), None)
    if host_ads:
        url = f'{host_ads["api conn"]}/api/v1/browser/start?user_id={profile_id}&open_tabs=1'
        headers = {
            'Authorization': f'Bearer {host_ads["api key"]}'
        }
        # response = requests.get(url, headers=headers)
        response = requests.get(url)
        print("ADS power connection status:", response.json())
        if response.status_code == 200:
            try:
                data = response.json()
                webdriver_info = data['data']
                chrome_driver = webdriver_info["webdriver"]
                service = ChromeService(executable_path=chrome_driver)
                webdriver_url = f"http://{webdriver_info['ws']['selenium']}"
                print("webdriver_url:", webdriver_url)
                options = Options()
                options.add_experimental_option('debuggerAddress', webdriver_info['ws']['selenium'])
                # driver = webdriver.Remote(command_executor=webdriver_url, options=options)
                driver = webdriver.Chrome(service=service, options=options)

                driver.get('https://mesg.ebay.com/mesgweb/ViewMessages/0/m2m')

                time.sleep(10)
                message_threads = []
                messages = []
                unique_senders = set()

                message_rows = driver.find_elements(By.XPATH, "//tr[contains(@class, 'msg-read')]")
                tbody = driver.find_element(By.XPATH, "//tbody")
                # message_rows = tbody.find_elements(By.TAG_NAME, "tr")

                # Iterate over the rows and extract data
                for index, row in enumerate(message_rows):
                    try:

                        message = {}
                        message['id'] = row.get_attribute('id')
                        message['from'] = row.find_element(By.XPATH, ".//td[contains(@id, '-from')]//div").text
                        message['subject'] = row.find_element(By.XPATH, ".//td[contains(@id, '-sub')]//div").text
                        message['received'] = row.find_element(By.XPATH, ".//td[contains(@id, '-msg-recvd')]//div").text
                        message['is_read'] = True if 'msg-read' in row.get_attribute('class') else False
                        message['attachment'] = bool(
                            row.find_element(By.XPATH, ".//td[contains(@id, '-attach')]//div").get_attribute(
                                'innerHTML').strip())
                        message['timestamp'] = row.find_element(By.XPATH,
                                                                ".//td[contains(@id, '-msg-recvd')]//div").text
                        print(message)
                        messages.append(message)
                    except Exception as e:
                        traceback_info = traceback.extract_tb(e.__traceback__)
                        # Extract the file name and line number from the last entry in the traceback
                        if traceback_info:
                            ex_stat = "ErrorWebDriver:" + traceback.format_exc() + " " + str(e)
                        else:
                            ex_stat = "ErrorWebDriver: traceback information not available:" + str(e)
                        print(ex_stat)

                for message in messages:
                    try:
                        if message['is_read']:
                            # Click the message to open it
                            # row.find_element(By.XPATH, ".//td[contains(@id, '-sub')]//div").click()
                            message_element = driver.find_element(By.ID, message['id'])
                            message_element.click()

                            # Wait until the message details are loaded
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, "//div[@id='msg-desc']"))
                            )
                            details = {}
                            details['from'] = driver.find_element(By.XPATH, "//div[@id='msg-desc']/div[1]/span[2]").text
                            details['to'] = driver.find_element(By.XPATH, "//div[@id='msg-desc']/div[2]/span[2]").text
                            details['sent'] = driver.find_element(By.XPATH, "//div[@id='msg-desc']/div[3]/span[2]").text
                            details['subject'] = driver.find_element(By.XPATH, "//div[@id='msg-desc']/h2").text


                            page_source = driver.page_source

                            # Use regular expressions to extract the product info
                            # product_info_regex = re.compile(r'td class="product-bids".*?td', re.DOTALL)
                            product_info_regex = re.compile(r'product-bids.*?td', re.DOTALL)
                            product_infos = product_info_regex.findall(page_source)
                            # print(product_infos)
                            item_id_regex = re.compile(r'Item ID: (\d+)')
                            quantity_remaining_regex = re.compile(r'Quantity Remaining: (\d+)')
                            order_number_regex = re.compile(r'Order number: (\d+)')
                            transaction_id_regex = re.compile(r'Transaction ID: (\d+)')

                            item_ids = [item_id_regex.search(info).group(1) if item_id_regex.search(info) else None for
                                        info in product_infos]
                            details['item_id'] = item_ids[0]

                            order_numbers = [order_number_regex.search(info).group(1) if order_number_regex.search(info) else None for
                                        info in product_infos]
                            details['order_number'] = order_numbers[0]

                            transaction_ids = [transaction_id_regex.search(info).group(1) if transaction_id_regex.search(info) else None for
                                        info in product_infos]
                            details['transaction_id'] = transaction_ids[0]

                            quantities_remaining = [quantity_remaining_regex.search(info).group(1) if quantity_remaining_regex.search(
                                    info) else None for info in product_infos ]
                            details['quantities_remaining'] = quantities_remaining[0]

                            # Assume the message body is in an iframe
                            iframe = driver.find_element(By.ID, "email_iframe")
                            driver.switch_to.frame(iframe)
                            details['body'] = driver.find_element(By.XPATH, "//body").text
                            driver.switch_to.default_content() # Wait for the page to load, adjust the sleep time as necessary

                            msg_details = parse_message_body(details['body'])

                            print("-->",msg_details)


                            # Go back to the main message list page
                            driver.back()
                            time.sleep(2)  # Wait for the page to load, adjust the sleep time as necessary

                            message_threads.append(message)
                        # print(message)
                        message_threads.append(message)
                    except Exception as e:
                        traceback_info = traceback.extract_tb(e.__traceback__)
                        # Extract the file name and line number from the last entry in the traceback
                        if traceback_info:
                            ex_stat = "ErrorWebDriver:" + traceback.format_exc() + " " + str(e)
                        else:
                            ex_stat = "ErrorWebDriver: traceback information not available:" + str(e)
                        print(ex_stat)
                # Print the list of message threads
                for thread in message_threads:
                    print(thread)

                print("Total msgs fetched:", len(message_threads))
                time.sleep(5)

            except Exception as e:
                traceback_info = traceback.extract_tb(e.__traceback__)
                # Extract the file name and line number from the last entry in the traceback
                if traceback_info:
                    ex_stat = "ErrorWebDriver:" + traceback.format_exc() + " " + str(e)
                else:
                    ex_stat = "ErrorWebDriver: traceback information not available:" + str(e)
                print(ex_stat)
        else:
            raise Exception('Failed to start Adspower profile', response.text)

    return driver

