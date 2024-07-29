from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import json
import time

# Initialize variables
search_phrase = "手机"  # Example search phrase, you can change this
url = "https://www.1688.com"

# driver = webdriver.Chrome()
# Function to extract product details
def extract_product_details(product):
    try:
        title = product.find_element(By.CSS_SELECTOR, 'div[class^="title"]').text
    except:
        title = None

    try:
        image_link = product.find_element(By.CSS_SELECTOR, 'img').get_attribute('src')
    except:
        image_link = None

    try:
        ranking = product.find_element(By.CSS_SELECTOR, 'div[class^="ranking"]').text
    except:
        ranking = None

    try:
        sold_recently = product.find_element(By.CSS_SELECTOR, 'div[class^="sold"]').text
    except:
        sold_recently = None

    try:
        store_name = product.find_element(By.CSS_SELECTOR, 'a[class^="store"]').text
    except:
        store_name = None

    try:
        price = product.find_element(By.CSS_SELECTOR, 'div[class^="price"]').text
    except:
        price = None

    try:
        discount = product.find_element(By.CSS_SELECTOR, 'div[class^="discount"]').text
    except:
        discount = None

    return {
        "title": title,
        "image_link": image_link,
        "ranking": ranking,
        "# sold recently": sold_recently,
        "store name": store_name,
        "price": price,
        "discount": discount
    }


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

# Function to perform search and extract results
def search_and_extract_results(search_phrase):
    global url
    driver.get(url)
    # Wait for the page to load completely (adjust the timeout as needed)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

    close_popup(driver)

    print("closed pop up")

    search_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, 'home-header-searchbox'))
    )

    search_box.send_keys(search_phrase)
    time.sleep(5)
    search_box.send_keys(Keys.RETURN)

    time.sleep(15)  # Allow time for search results to load

    # search-offer-wrapper cardui-normal search-offer-item major-offer
    products = driver.find_elements(By.CSS_SELECTOR, 'a.search-offer-wrapper.cardui-normal.search-offer-item.major-offer')
    print("found N products:", len(products))
    product_list = []

    for product in products:
        try:
            # Extract the desired attributes
            title = product.find_element(By.CSS_SELECTOR, 'div.offer-title-row div.title-text').text
            url = product.get_attribute('href')
            image_url = product.find_element(By.CSS_SELECTOR, 'img.main-img').get_attribute('src')
            price = product.find_element(By.CSS_SELECTOR, 'div.price-item div.text-main').text
            shop_name = product.find_element(By.CSS_SELECTOR, 'div.offer-shop-row a div.desc-text').text
            items_sold = product.find_element(By.CSS_SELECTOR,
                                              'div.offer-price-row div.offer-desc-item div.desc-text').text
            tags = [tag.text for tag in
                    product.find_elements(By.CSS_SELECTOR, 'div.offer-tag-row div.offer-desc-item div.desc-text')]

            product_list.append({
                'title': title,
                'url': url,
                'image_url': image_url,
                'price': price,
                'shop_name': shop_name,
                'items_sold': items_sold,
                'tags': tags
            })
        except Exception as e:
            print(f"Error extracting product details: {e}")


    results = product_list

    return results

def stopDriver():
    driver.quit()
