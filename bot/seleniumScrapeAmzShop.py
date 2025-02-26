import datetime
import json
import re
import os

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from bot.seleniumSkill import *


import json
import time
import shutil

# Initialize variables
search_phrase = "手机"  # Example search phrase, you can change this
url = "https://www.1688.com"
# Function to extract product details

import traceback

def scrapeTabs(driver):
    time.sleep(1)
    tabs = driver.find_elements(By.CSS_SELECTOR, "div.myo-spa-tab")

    order_summaries = {}

    for tab in tabs:
        try:
            tab_name_element = tab.find_element(By.TAG_NAME, "h4")
            tab_name = tab_name_element.text
            count_elements = tab_name_element.find_elements(By.CLASS_NAME, "myo-spa-highlight")
            count = count_elements[0].text.strip() if count_elements else '0'

            # Add debug logging
            print(f"Tab Name: {tab_name}, Count: {count}")

            order_summaries[tab_name] = count
        except Exception as e:
            print(f"Error processing tab: {e}")
    print("=======")
    return order_summaries

def scrapeTabs(driver):
    time.sleep(1)
    tabs = driver.find_elements(By.CSS_SELECTOR, "div.myo-spa-tab")

    order_summaries = {}

    for tab in tabs:
        try:
            tab_name_element = tab.find_element(By.TAG_NAME, "h4")
            tab_name = tab_name_element.text
            count_elements = tab_name_element.find_elements(By.CLASS_NAME, "myo-spa-highlight")
            count = count_elements[0].text.strip() if count_elements else '0'

            # Add debug logging
            print(f"Tab Name: {tab_name}, Count: {count}")

            order_summaries[tab_name] = count
        except Exception as e:
            print(f"Error processing tab: {e}")
    print("=======")
    return order_summaries

def scrapeOrdersHeading(driver):
    time.sleep(3)
    number_of_orders = -1
    try:
        orders_summary_loaded = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".a-row"))
        )

        total_orders_headings = driver.find_elements(By.CSS_SELECTOR, "div.total-orders-heading")
        for total_order_heading in total_orders_headings:
            print(total_order_heading.text)

            # Extract the number of orders from the first span element inside the 'total-orders-heading' div
            number_of_orders = total_order_heading.find_element(By.TAG_NAME, "span").text.strip()

            # Print the number of orders
            print(f"Number of orders: {number_of_orders}")
    except Exception as e:
        print(f"Error processing tab: {e}")

    return number_of_orders

def select_max_orders_per_page(driver):

    try:
        time.sleep(2)

        # Click the dropdown to show options
        dropdown_prompt = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span.a-dropdown-prompt"))
        )

        current_selection = driver.find_element(By.CSS_SELECTOR, "span.a-dropdown-prompt").text.strip()
        if "100" in current_selection:
            print("100 orders per page is already selected.")
            return

        dropdown_prompt.click()

        # Select the option with 100 orders per page
        max_orders_option = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//option[@value='100']"))
        )
        max_orders_option.click()

        # # Wait for the table to refresh
        # WebDriverWait(driver, 20).until(EC.staleness_of(dropdown_prompt))
        print("Selected 100 orders per page.")
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)

        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorScrapeOrderLists:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorScrapeOrderLists: traceback information not available:" + str(e)

        print(ex_stat)



def scrapeOrderLists(driver):
    try:
        # Wait for the orders summary element to be present
        print("wait for loading orders table ....")
        time.sleep(2)
        if True:
            all_orders = []
            while True:
                # Wait for the orders table to be present
                orders_table_loaded = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, "orders-table"))
                )
                print("orders table loaded....")
                if orders_table_loaded:
                    # Parse the page source with BeautifulSoup
                    soup = BeautifulSoup(driver.page_source, 'html.parser')

                    print("soup ready")

                    # Find the orders table
                    orders_table = soup.find('table', {'id': 'orders-table'})
                    if not orders_table:
                        break  # Exit if no table is found

                    # Extract orders from the table
                    rows = orders_table.find('tbody').find_all('tr')
                    print("n rows:", len(rows))
                    for row in rows:
                        print("parsing rows")
                        cells = row.find_all('td')
                        buyer_name_span = cells[2].find('span', text='Buyer name')
                        buyer_name = buyer_name_span.find_next('div').get_text(strip=True) if buyer_name_span else "N/A"


                        order = {
                            'Order date': cells[1].get_text(strip=True),
                            'Order ID': cells[2].find('a').get_text(strip=True),
                            'Buyer name': buyer_name,
                            'Fulfillment method': cells[2].find('span', text='Fulfillment method').find_next_sibling(
                                text=True).strip(),
                            'Sales channel': cells[2].find('span', text='Sales channel').find_next_sibling(
                                text=True).strip(),
                            'Product name': cells[4].find('a').get_text(strip=True),
                            'ASIN': cells[4].find('span', text='ASIN').find_next_sibling('b').get_text(strip=True),
                            'SKU': cells[4].find('span', text='SKU').find_next_sibling(text=True).strip(),
                            'Quantity': cells[4].find('span', text='Quantity').find_next_sibling('b').get_text(
                                strip=True),
                            'Item subtotal': cells[4].find('span', text='Item subtotal').find_next_sibling(
                                text=True).strip(),
                            'Order Status': cells[7].get_text(strip=True)
                        }
                        all_orders.append(order)

                    print("all_orders:", all_orders)

                    # # Check if the "Next" button is disabled
                    # next_button = driver.find_element(By.CSS_SELECTOR, '.a-pagination .a-last')
                    # if 'a-disabled' in next_button.get_attribute('class'):
                    #     break  # Exit the loop if the "Next" button is disabled
                    #
                    # # Click the "Next" button to go to the next page
                    # next_button.click()

                    # Wait for the next page to load
                    time.sleep(3)

                    while True:
                        # Wait for the orders table to be present
                        orders_table_loaded = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.ID, "orders-table"))
                        )
                        print("retest order table loaded.")
                        if orders_table_loaded:
                            # Select all orders
                            print("reassured loaded.")
                            # select_all_checkbox = driver.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                            select_all_checkbox = WebDriverWait(driver, 20).until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, "th[data-test-id='oth-cb'] input[type='checkbox']"))
                            )
                            # Move the mouse pointer to the "Select all" checkbox and wait for 3 seconds
                            actions = ActionChains(driver)
                            actions.move_to_element(select_all_checkbox).perform()

                            print("select_all_checkbox identified...", select_all_checkbox)
                            select_all_checkbox.click()
                            time.sleep(3)


                            # Click the "Buy shipping in bulk" button
                            buy_shipping_button = WebDriverWait(driver, 20).until(
                                EC.element_to_be_clickable(
                                    (By.CSS_SELECTOR, "span[data-test-id='ab-bulk-buy-shipping'] a"))
                            )

                            print("buy_shipping_button identified...", buy_shipping_button)
                            actions = ActionChains(driver)
                            actions.move_to_element(buy_shipping_button).perform()
                            time.sleep(1)
                            buy_shipping_button.click()
                            time.sleep(5)


                            # Wait for the bulk shipping page to load
                            # Wait for the price element to ensure the page has fully loaded
                            bulk_buy_page_loaded = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, "//h1[text()='Buy Shipping in bulk']"))
                            )

                            # Wait for the orders table to be fully loaded
                            bulk_shipping_table = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'a-bordered')]"))
                            )

                            # Wait for a reliable element within the table to ensure it's fully loaded
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.NAME, "weight.lb"))
                            )

                            # Parse the bulk shipping table
                            # bulk_shipping_table = driver.find_element(By.CSS_SELECTOR, "table.a-bordered")
                            # rows = bulk_shipping_table.find_elements(By.TAG_NAME, "tr")[1:]
                            rows = driver.find_elements(By.XPATH, "//table[contains(@class, 'a-bordered')]//tr[td]")
                            print("n rows detected:", len(rows))
                            print(rows)

                            for row in rows:
                                try:
                                    order_id_elements = row.find_elements(By.TAG_NAME, "a")
                                    if not order_id_elements:
                                        print("Order ID element not found in the row")
                                        continue
                                    order_id = order_id_element.text

                                    weight_lb_element = row.find_element(By.NAME, "weight.lb")
                                    weight_lb = int(weight_lb_element.get_attribute("value"))

                                    weight_oz_element = row.find_element(By.NAME, "weight.oz")
                                    weight_oz = int(weight_oz_element.get_attribute("value"))

                                    # If weight is zero, skip this row
                                    if weight_lb == 0 and weight_oz == 0:
                                        continue

                                    total_weight_oz = weight_lb * 16 + weight_oz

                                    shipping_service_element = row.find_element(By.XPATH,
                                                                                ".//td[4]//span[contains(@class, 'a-size-base-plus')]")
                                    shipping_service = shipping_service_element.text


                                    print(weight_lb, weight_oz, total_weight_oz, shipping_service)
                        #             if expected_service not in shipping_service:
                        #                 # If the shipping service is not correct, change it
                        #                 change_link = row.find_element(By.LINK_TEXT, "Change")
                        #                 change_link.click()
                        #                 time.sleep(1)
                        #
                        #                 # Select the correct shipping service
                        #                 new_service_option = driver.find_element(By.XPATH,
                        #                                                          f"//option[text()='{expected_service}']")
                        #                 new_service_option.click()
                        #                 time.sleep(1)
                        #
                                except Exception as e:
                                    print(f"Error processing row: {e}")

                            print(f"Processed {len(all_orders)} orders: {all_orders}")

                            # Scrape total price/cost information
                            total_price_element = driver.find_element(By.XPATH,
                                                                      "//span[contains(@class, 'a-size-medium a-color-price a-text-bold')]")
                            total_price = total_price_element.text
                            print(f"Total price: {total_price}")

                            try:
                                current_orientation_element = driver.find_element(By.XPATH,
                                                                                  "//div[contains(@class, 'a-radio') and .//input[@type='radio' and @checked]]/label/span[@class='a-label a-radio-label']")
                                current_orientation = current_orientation_element.text.strip()
                            except NoSuchElementException:
                                current_orientation = None

                            expected_orientation = "8.5 in x 11 in PDF With Receipt"

                            if current_orientation != expected_orientation:
                                # Select the label print orientation
                                orientation_dropdown_trigger = WebDriverWait(driver, 30).until(
                                    EC.element_to_be_clickable(
                                        (By.XPATH, "//a[contains(text(), 'Select Label Print Orientation')]"))
                                )
                                orientation_dropdown_trigger.click()

                                # Wait for the popover to appear and select the desired option
                                popover_content = WebDriverWait(driver, 30).until(
                                    EC.presence_of_element_located((By.CLASS_NAME, "a-popover-content"))
                                )

                                # Select the desired option (8.5 in x 11 in PDF With Receipt)
                                pdf_option = driver.find_element(By.XPATH,
                                                                 "//input[@value='PDF-LABEL_TO_THE_LEFT_WITH_RECEIPT-11_0-8_5']")
                                pdf_option_label = pdf_option.find_element(By.XPATH, "..")
                                pdf_option_label.click()

                            # Wait for the "Buy Shipping" button to be clickable
                            buy_shipping_button = WebDriverWait(driver, 30).until(
                                EC.element_to_be_clickable(
                                    (By.XPATH, "//span[contains(@id, 'announce') and text()='Buy Shipping']"))
                            )

                            print("Buy Shipping button is found")

                            driver.execute_script("arguments[0].scrollIntoView(true);", buy_shipping_button)

                            # Adding some delay to ensure visibility and avoid intercept issues
                            WebDriverWait(driver, 5).until(EC.visibility_of(buy_shipping_button))

                            print("Buy Shipping button is clickable")
                            buy_shipping_button.click()


                        #
                        #         # Rename and move the downloaded file
                        #         rename_and_move_latest_file("LastName", "FirstName", "ProductName", "Quantity")
                        #
                        # # Check if there is a "Next" button to go to the next page
                        # next_button = driver.find_element(By.XPATH, "//li[@class='a-last']/a")
                        # if next_button:
                        #     next_button.click()
                        #     time.sleep(5)  # Wait for the next page to load
                        # else:
                        #     break

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)

        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorScrapeOrderLists:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorScrapeOrderLists: traceback information not available:" + str(e)

        print(ex_stat)




def close_popup(driver):
    try:
        # Wait for the close button to appear (adjust the timeout as needed)
        close_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'turboCom-dialog-close'))
        )

        # Click the close button
        close_button.click()
        print("Pop-up ad closed successfully.")
    except Exception as e:
        print("No pop-up ad detected or unable to close it.")
        print(e)



def confirmShipment(driver, service, tracking, shipper="USPS"):
    wait = WebDriverWait(driver, 10)

    # Click on the "Confirm shipment" button
    confirm_shipment_button = table_row.find_element(By.XPATH, './/a[@data-test-id="ab-confirm-shipment"]')
    confirm_shipment_button.click()

    # Wait for the page to load and scroll to the required section
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//span[@data-test-id='confirm-shipment-heading']"))
    )

    # Scroll to the Confirm shipment section
    confirm_shipment_section = driver.find_element(By.XPATH, "//span[@data-test-id='confirm-shipment-heading']")
    driver.execute_script("arguments[0].scrollIntoView();", confirm_shipment_section)

    # Select Carrier
    carrier_dropdown = Select(driver.find_element(By.ID, "CarrierListDropdown-76524"))
    selected_carrier = carrier_dropdown.first_selected_option.text
    desired_carrier = "USPS"  # Change as needed
    if selected_carrier != desired_carrier:
        carrier_dropdown.select_by_visible_text(desired_carrier)

    # Select Shipping Service
    service_dropdown = Select(driver.find_element(By.ID, "shipping-service-dropdown1"))
    desired_service = "USPS Priority Mail"  # Change as needed
    service_dropdown.select_by_visible_text(desired_service)

    # Enter Tracking ID
    tracking_id_input = driver.find_element(By.XPATH, "//input[@data-test-id='text-input-tracking-id']")
    tracking_id = "YOUR_TRACKING_ID_HERE"  # Replace with actual tracking ID
    tracking_id_input.send_keys(tracking_id)

    # Submit the form (assuming there's a button to submit)
    submit_button = driver.find_element(By.XPATH, "//input[@value='Confirm shipment']")
    submit_button.click()

    # Optionally, add a wait here for the next page to load before continuing
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//span[@data-test-id='some-element-on-next-page']"))
    )




    # Scroll to the confirm shipment section
    confirm_shipment_section = wait.until(EC.presence_of_element_located((By.XPATH,
                                                                          "//div[contains(@class, 'a-box-inner')]//div[contains(@class, 'a-row a-spacing-micro a-spacing-top-micro')]/span[contains(text(), 'Edit shipment')]")))
    driver.execute_script("arguments[0].scrollIntoView(true);", confirm_shipment_section)
    time.sleep(2)  # Adjust the wait time as needed


    # check and select carrier if needed.
    carrier_dropdown = wait.until(EC.presence_of_element_located((By.ID, "CarrierListDropdown-559556")))
    select_carrier = Select(carrier_dropdown)
    selected_carrier = select_carrier.first_selected_option.text

    if selected_carrier != shipper:
        select_carrier.select_by_visible_text(shipper)


    # Select the correct shipping service from the dropdown
    shipping_service_dropdown = wait.until(EC.presence_of_element_located((By.ID, "shipping-service-dropdown3")))
    select = Select(shipping_service_dropdown)
    select.select_by_visible_text("USPS Priority Mail")  # Replace with the desired shipping service

    # Input the tracking code
    tracking_input = wait.until(
        EC.presence_of_element_located((By.XPATH, "//input[@data-test-id='text-input-tracking-id']")))
    tracking_input.clear()
    tracking_input.send_keys(tracking)  # Replace with the actual tracking code

    # Click the confirmation button
    confirm_button = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//input[@value='Confirm shipment']")))  # Adjust the button's XPath if necessary
    confirm_button.click()
    time.sleep(2)  # Adjust the wait time as needed

    # Go back to the orders page
    driver.back()



def processAmzSeleniumObtainTrackingsAndLabels(driver):
    # tsum = scrapeTabs(driver)
    # ohead = scrapeOrdersHeading(driver)
    # Maximize the window (optional)
    # driver.maximize_window()

    # Define wait time
    wait = WebDriverWait(driver, 20)

    # Wait until the table is present
    wait.until(EC.presence_of_element_located((By.ID, "orders-table")))

    # Pause to ensure all content is loaded
    time.sleep(5)

    # Extract data from the table
    orders = []
    row_elements = driver.find_elements(By.XPATH, "//table[@id='orders-table']//tbody/tr")
    print(f"Found {len(row_elements)} rows")

    # Interact with buttons (Edit shipment, Refund order, Print packing slip)
    for row_element in row_elements:
        order_id = row_element.find_element(By.XPATH, ".//td[3]//a").text

        # Click on Edit Shipment
        edit_shipment_button = row_element.find_element(By.XPATH, ".//a[contains(@href, 'edit-shipment')]")
        edit_shipment_button.click()
        print(f"Clicked Edit shipment for Order ID: {order_id}")
        time.sleep(2)  # Adjust the wait time as needed

        # now try to scroll to the shipping section of order detils, scrape it and click on reprint labels.

        driver.get(order['orderLink'])
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "a-box-group")))

        # Scroll to the shipping info section
        shipping_info_section = driver.find_element(By.XPATH,
                                                    "//div[contains(@class, 'a-box-group')]//div[contains(@class, 'a-box') and not(contains(@class, 'a-color-alternate-background'))]")
        actions = ActionChains(driver)
        actions.move_to_element(shipping_info_section).perform()
        time.sleep(2)

        # Scrape the tracking code
        tracking_code = driver.find_element(By.XPATH, "//a[@data-test-id='tracking-id-value']").text
        print(f"Tracking Code: {tracking_code}")

        # Click on the "Reprint Label" button
        reprint_label_button = driver.find_element(By.XPATH,
                                                   "//span[contains(@class, 'a-button')]/input[@value='Reprint Label']")
        reprint_label_button.click()
        print(f"Clicked Reprint Label for Order ID: {order['orderID']}")
        time.sleep(2)  # Adjust the wait time as needed

        # Go back to the orders page
        driver.back()


        # # Click on Refund Order
        # refund_order_button = row_element.find_element(By.XPATH, ".//a[contains(@href, 'refund')]")
        # refund_order_button.click()
        # print(f"Clicked Refund order for Order ID: {order_id}")
        # time.sleep(2)  # Adjust the wait time as needed
        #
        # driver.back()  # Go back to the orders page
        # wait.until(EC.presence_of_element_located((By.ID, "orders-table")))
        #
        # # Click on Print Packing Slip
        # print_packing_slip_button = row_element.find_element(By.XPATH, ".//span[@data-test-id='print-packingslip']")
        # print_packing_slip_button.click()
        # print(f"Clicked Print packing slip for Order ID: {order_id}")
        # time.sleep(2)  # Adjust the wait time as needed
        #
        # driver.back()  # Go back to the orders page
        # wait.until(EC.presence_of_element_located((By.ID, "orders-table")))


def processAmzSeleniumScrapeOrders(driver):
    # tsum = scrapeTabs(driver)
    # ohead = scrapeOrdersHeading(driver)
    select_max_orders_per_page(driver)
    scrapeOrderLists(driver)



def processAmzSeleniumConfirmShipments(driver):
    print("")

def processAmzSeleniumBulkBuyLabels(driver):
    print("")

def processAmzSeleniumScrapeMessages(driver):
    print("")

# Function to perform search and extract results
def processAmzSeleniumScrapeOrdersBuyLabels(driver=None):
    if not driver:
        # driver = webdriver.Chrome()

        driver_path = '"C:/Users/songc/PycharmProjects/ecbot'+'/chromedriver-win64/chromedriver.exe'
        download_dir = "/path/to/your/download/dir"
        labels_dir = "/path/to/your/labels/dir"

        # Initialize Chrome options
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

        driver_path = r"C:\Users\songc\PycharmProjects\ecbot\chromedriver-win64\chromedriver.exe"

        if not os.path.isfile(driver_path):
            raise ValueError(f"The path is not a valid file: {driver_path}")

        # Set Chrome options if needed
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", "localhost:9222")

        # Initialize the WebDriver
        service = ChromeService(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Initialize the WebDriver with the existing Chrome session
        # driver = webdriver.Chrome(service=ChromeService(driver_path), options=chrome_options)

    url = "https://sellercentral.amazon.com/orders-v3?page=1"
    result = None
    driver.get(url)

    processAmzSeleniumScrapeOrders(driver)

    # processAmzSeleniumBulkBuyLabels(driver)
    # processAmzSeleniumConfirmShipments(driver)

    return result


def genWinChromeAMZWebdriverFullfillOrdersSkill(worksettings, stepN, theme):
    print("Default fullfill using amazon labels")
    psk_words = "{"
    site_url = "https://sellercentral.amazon.com/orders-v3/mfn/unshipped?page=1"

    this_step, step_words = genStepHeader("win_ads_amz_webdriver_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINADSAMZ005", "Amazon Webdriver Fullfill New Orders On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_amz_orders/webdriver_fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_amz_orders/webdriver_fullfill_orders", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_amz_orders/webdriver_fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # log3("DEBUG", "generated skill for windows chrome webdriver amazon order fullfill..." + psk_words)

    return this_step, psk_words