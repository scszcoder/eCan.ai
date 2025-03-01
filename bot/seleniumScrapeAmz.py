import datetime
import json
import re
import os

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException

import json
import time
import shutil
import random
from bot.Logger import log3
import traceback
from bot.seleniumSkill import switchToNthTab, switchToLastTab, switchToFirstTab
from bot.basicSkill import DEFAULT_RUN_STATUS, symTab, STEP_GAP
from bot.scraperAmz import amz_buyer_scrape_product_list, amz_buyer_scrape_product_details, amz_buyer_scrape_orders_list
from bot.amzBuyerSkill import found_match

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
                                    order_id_element = order_id_elements[0]
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

def jiggle_mouse(driver, duration, frequency, max_offset):
    actions = ActionChains(driver)
    end_time = time.time() + duration

    while time.time() < end_time:
        try:
            actions = ActionChains(driver)
            end_time = time.time() + duration

            while time.time() < end_time:
                # Generate random scroll offsets
                offset_x = random.randint(-max_offset, max_offset)
                offset_y = random.randint(-max_offset, max_offset)

                # Execute JavaScript to scroll the window by the random offsets
                driver.execute_script(f"window.scrollBy({offset_x}, {offset_y});")

                # Wait before the next jiggle
                time.sleep(frequency)

        except Exception as e:
            print(f"An error occurred: {e}")



def searchProduct(driver, search_phrase="dumb bells"):
    try:
        # Extract the search text input box
        search_input = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "twotabsearchtextbox"))
        )

        # Print debug statements
        print("Search input field is present")

        # Ensure the element is present and interactable
        if search_input:
            print("Search input field is interactable")

            driver.execute_script("arguments[0].click();", search_input)
            time.sleep(1)  # Adding a small delay to ensure the input box is ready

            # Enter search text using JavaScript
            driver.execute_script("arguments[0].value = arguments[1];", search_input, search_phrase)
            print("Search text entered")

            # Wait for the search button to be present and clickable
            search_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, "nav-search-submit-button"))
            )
            print("Search button found")

            # Click the search button using JavaScript
            driver.execute_script("arguments[0].click();", search_button)
            print("Search button clicked")

        # Check if the user is logged in
        user_greeting = driver.find_element(By.ID, 'nav-link-accountList-nav-line-1').text
        is_logged_in = user_greeting.startswith('Hello, ')
        print("user_greeting:", user_greeting, is_logged_in)

        # Get the number of items in the cart
        cart_count = driver.find_element(By.ID, 'nav-cart-count').text
        print("cart_count:", cart_count)

        # search_input_box.clear()  # Clear any existing text in the search box
        # search_input_box.send_keys(search_phrase)  # Enter the search phrase
        # search_input_box.send_keys(Keys.RETURN)  # Hit enter to start the search

        # Wait for the search results page to load
        driver.implicitly_wait(10)


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorsearchProduct:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorsearchProduct: traceback information not available:" + str(e)
        print(ex_stat)

# Function to perform search and extract results
def processAmzSeleniumScrapeSearchResults(driver=None):
    if not driver:
        driver_path = '"C:/Users/songc/PycharmProjects/ecbot'+'/chromedriver-win64/chromedriver.exe'
        download_dir = "/path/to/your/download/dir"
        labels_dir = "/path/to/your/labels/dir"


        driver_path = r"C:\Users\songc\PycharmProjects\ecbot\chromedriver-win64\chromedriver.exe"

        if not os.path.isfile(driver_path):
            raise ValueError(f"The path is not a valid file: {driver_path}")

        # Set Chrome options if needed
        chrome_options = Options()
        # chrome_options.add_argument('--headless')
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

        # Initialize the WebDriver
        service = ChromeService(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        # driver = webdriver.Chrome(options=chrome_options)

        # Initialize the WebDriver with the existing Chrome session
        # driver = webdriver.Chrome(service=ChromeService(driver_path), options=chrome_options)

    url = "https://www.amazon.com/s?k=resistance+bands&crid=BZKJRDOCKGJ9&sprefix=resistance+bands%2Caps%2C165&ref=nb_sb_noss_1"
    url = "https://www.amazon.com"
    result = None
    driver.get(url)
    print("connected to amazon")
    searchProduct(driver)
    time.sleep(1)
    scrollTo(driver)

    # processAmzSeleniumBulkBuyLabels(driver)
    # processAmzSeleniumConfirmShipments(driver)

    return result


def genStepAMZBrowserScrapePL(web_driver, pl, page_num, page_cfg, flag_var, stepN):
    stepjson = {
        "type": "AMZ Browser Scrape Products List",
        "page_num": page_num,
        "web_driver_var": web_driver,
        "product_list": pl,
        "page_cfg": page_cfg,
        "flag_var": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def processAMZBrowserScrapePL(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        page_num = symTab[step["page_num"]]
        symTab[step["flag_var"]] = True
        webdriver = symTab[step["web_driver_var"]]

        pl = amz_buyer_scrape_product_list(webdriver, page_num)


        att_pl = []
        att_pl_indices = []

        # go thru all products in configuration
        for p in symTab[step["page_cfg"]]["products"]:
            log3("current page config: "+json.dumps(p))
            found, fi = found_match(p, pl["pl"])
            if found:
                # remove found from the pl
                log3("FOUND product:"+json.dumps(found))
                if found["summery"]["title"] != "CUSTOM":
                    pl["pl"].remove(found)
                else:
                    # now swap in the swipe product.
                    found = {"summery": {
                                "title": mission.getTitle(),
                                "rank": mission.getRating(),
                                "feedbacks": mission.getFeedbacks(),
                                "price": mission.getPrice()
                                },
                        "detailLvl": p["detailLvl"],
                        "purchase": p["purchase"]
                    }
                    log3("Buy Swapped:" + json.dumps(found))

                att_pl.append(found)
                att_pl_indices.append(fi)

        if not step["product_list"] in symTab:
            # if new, simply assign the result.
            symTab[step["product_list"]] = {"products": pl, "attention": att_pl, "attention_indices": att_pl_indices}
        else:
            # otherwise, extend the list with the new results.
            # symTab[step["product_list"]].append({"products": pl, "attention": att_pl})
            symTab[step["product_list"]]["products"] = pl
            symTab[step["product_list"]]["attention"] = att_pl
            symTab[step["product_list"]]["attention_indices"] = att_pl_indices


        log3("var step['product_list']: "+json.dumps(symTab[step["product_list"]]))




    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZBrowserScrapePL:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAMZBrowserScrapePL: traceback information not available:" + str(e)
        log3(ex_stat)
        symTab[step["flag_var"]] = False

    return (i + 1), ex_stat



def genStepAMZBrowserScrapeProductDetails(web_driver, outvar, statusvar, stepN):
    stepjson = {
        "type": "AMZ Browser Scrape Product Details",
        "web_driver_var": web_driver,
        "result": outvar,
        "status": statusvar
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def processAMZBrowserScrapeProductDetails(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        webdriver = symTab[step["web_driver_var"]]

        # product_details = amz_buyer_scrape_product_details(webdriver)
        product_details = extract_details(webdriver)

        # at the end , the product_details should include web elements of:
        # product title, asin, main image, 7 thumnb image, buybox,
        # coupon checkbox if any, variations, reviews, full review link,
        # A+ section images,
        # section of Q&A, direct review link, asin,
        symTab[step["result"]] = product_details


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZBrowserScrapeProductDetails:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAMZBrowserScrapeProductDetails: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat



def genStepAMZBrowserScrapeOrdersList(web_driver, outvar, statusvar, stepN):
    stepjson = {
        "type": "AMZ Browser Scrape Orders List",
        "web_driver_var": web_driver,
        "result": outvar,
        "status": statusvar
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def processAMZBrowserScrapeOrdersList(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        webdriver = symTab[step["web_driver_var"]]

        pagefull_of_orders, n_pages = amz_buyer_scrape_orders_list(webdriver)

        symTab[step["result"]] = pagefull_of_orders


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZBrowserScrapeProductDetails:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAMZBrowserScrapeProductDetails: traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat



def extract_variations(driver):
    variations = {}

    # Find variation sections (Amazon labels them with class 'a-form-label')
    variation_labels = driver.find_elements(By.CSS_SELECTOR, ".a-form-label")

    for label in variation_labels:
        variation_name = label.text.strip().replace(":", "")  # Get variation name (e.g., "Size", "Color", "Material")

        # Look for dropdown next to label
        try:
            dropdown = label.find_element(By.XPATH, "./following-sibling::span//select")
            select = Select(dropdown)
            options = [option.text.strip() for option in select.options if option.get_attribute("value") != "-1"]
            variations[variation_name] = {"type": "dropdown", "options": options, "element": dropdown}
            continue  # Skip to next variation after detecting dropdown
        except:
            pass

        # Look for swatch buttons (e.g., color thumbnails)
        try:
            swatches = label.find_element(By.XPATH, "./following-sibling::span")
            swatch_items = swatches.find_elements(By.CSS_SELECTOR, "li[data-csa-c-item-id]")
            swatch_options = {}

            for item in swatch_items:
                swatch_name = item.get_attribute("title").replace("Click to select ", "").strip()
                try:
                    image_url = item.find_element(By.TAG_NAME, "img").get_attribute("src")
                except:
                    image_url = None  # Some swatches may not have images
                swatch_options[swatch_name] = image_url

            if swatch_options:
                variations[variation_name] = {"type": "thumbnails", "options": swatch_options, "elements": swatch_items}
        except:
            pass

    return variations


# Function to select a variation dynamically
def select_variation(variation_name, selection, variations):
    if variation_name not in variations:
        print(f"Variation '{variation_name}' not found.")
        return

    variation_data = variations[variation_name]

    # Select from dropdown
    if variation_data["type"] == "dropdown":
        try:
            select = Select(variation_data["element"])
            select.select_by_visible_text(selection)
            print(f"Selected {variation_name}: {selection}")
        except:
            print(f"Option '{selection}' not found for {variation_name}")

    # Click swatch button
    elif variation_data["type"] == "thumbnails":
        try:
            for item in variation_data["elements"]:
                swatch_name = item.get_attribute("title").replace("Click to select ", "").strip()
                if swatch_name.lower() == selection.lower():
                    item.click()
                    print(f"Selected {variation_name}: {selection}")
                    time.sleep(2)  # Allow time for selection
                    break
        except:
            print(f"Option '{selection}' not found for {variation_name}")



def extract_details(driver):
    product_details = {}
    # get title
    title_element = driver.find_element(By.ID, "productTitle")
    product_details["product_title"] = title_element.text.strip()

    # get rating
    rating_element = driver.find_element(By.ID, "acrPopover")
    product_details["rating"] = rating_element.get_attribute("title")  # Extract the tooltip title

    #get N reviews
    review_count_element = driver.find_element(By.ID, "acrCustomerReviewText")
    product_details["review_count"] = review_count_element.text  # Extract text: "13 ratings"

    product_details["variations"] = extract_variations(driver)

    # get price
    price_symbol = driver.find_element(By.CLASS_NAME, "a-price-symbol").text  # "$"
    price_whole = driver.find_element(By.CLASS_NAME, "a-price-whole").text  # "41"
    price_decimal = driver.find_element(By.CLASS_NAME, "a-price-decimal").text  # "."
    price_fraction = driver.find_element(By.CLASS_NAME, "a-price-fraction").text  # "99"

    product_details["price"] = f"{price_symbol}{price_whole}{price_decimal}{price_fraction}"

    # get coupon
    coupon_element = driver.find_element(By.XPATH, "//span[contains(text(), 'coupon')]")
    coupon = {}
    coupon["text"] = coupon_element.text.strip()

    coupon["checkbox"] = driver.find_element(By.XPATH, "//input[contains(@id, 'checkbox')]")

    # Click the coupon checkbox
    # ActionChains(driver).move_to_element(coupon_checkbox).click().perform()

    product_details["add_cart_button"] = driver.find_element(By.ID, "add-to-cart-button")

    # Click the button
    # ActionChains(driver).move_to_element(add_to_cart_button).click().perform()

    product_details["buy_now_button"] = driver.find_element(By.ID, "buy-now-button")

    product_details["summery_expand_icon"] = driver.find_element(By.XPATH, "//a[@data-action='a-expander-toggle']")

    # Scroll to the element (if needed)
    # ActionChains(driver).move_to_element(expand_button).perform()

    # Click the "See More" button
    # expand_button.click()



    # get asin
    asin_element = driver.find_element(By.XPATH, "//li[span/span[contains(text(),'ASIN')]]/span/span[last()]")
    product_details["asin"] = asin_element.text.strip()

    product_details["bullet_elements"] = driver.find_elements(By.CSS_SELECTOR,
                                           "ul.a-unordered-list.a-vertical.a-spacing-small li span.a-list-item")

    # Find all review elements
    reviews = driver.find_elements(By.CSS_SELECTOR, "li[data-hook='review']")

    # Extract data from each review
    pd_reviews = []
    one_review = {}
    for review in reviews:
        one_review["review"] = review
        try:
            one_review["reviewer"] = review.find_element(By.CSS_SELECTOR, "span.a-profile-name").text
        except:
            one_review["reviewer"] = "N/A"

        try:
            one_review["rating"] = review.find_element(By.CSS_SELECTOR, "i[data-hook='review-star-rating'] span").text
        except:
            one_review["rating"] = "N/A"

        try:
            one_review["title"] = review.find_element(By.CSS_SELECTOR, "a[data-hook='review-title'] span").text
        except:
            one_review["title"] = "N/A"

        try:
            one_review["review_date"] = review.find_element(By.CSS_SELECTOR, "span[data-hook='review-date']").text
        except:
            one_review["review_date"] = "N/A"

        try:
            one_review["size_color"] = review.find_element(By.CSS_SELECTOR, "span[data-hook='format-strip-linkless']").text
        except:
            one_review["size_color"] = "N/A"

            # Expand the "Read More" if available
        try:
            one_review["read_more_button"] = review.find_element(By.CSS_SELECTOR, "a[data-hook='expand-collapse-read-more-less']")
            # driver.execute_script("arguments[0].click();", one_review["read_more_button"])
            time.sleep(1)  # Wait for content to expand
        except:
            pass  # If no "Read More" button, continue

        try:
            one_review["review_text"] = review.find_element(By.CSS_SELECTOR, "span[data-hook='review-body']").text
        except:
            one_review["review_text"] = "N/A"

        pd_reviews.append(one_review)

    product_details["reviews"] = pd_reviews