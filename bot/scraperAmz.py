import json
from bs4 import BeautifulSoup
import pyautogui
import numpy as np
import re
import random
from calendar import isleap
import cv2
from productsData import *
from Logger import *


def convNFB(nfb_txt):
    if "(" in nfb_txt:
        nfb_num_txt = nfb_txt.split("(")[1]
        nfb_num_txt = nfb_num_txt.split(")")[0]
    else:
        nfb_num_txt = nfb_txt

    numb_num_parts = nfb_num_txt.split(",")
    nfb_word = ''.join(numb_num_parts)
    # log3("nfb: " + str(nfb_word))
    return int(nfb_word)

def convPrice(price_txt):
    price_num_txt = price_txt.split("$")[1].replace(",", "")
    # log3("converted price: " + price_num_txt)
    return float(price_num_txt)


def convWeeklySales(ws_txt):
    ws_word = ws_txt.split(" ")[0]
    ws_nword = ws_word.split("+")[0]
    ws_word = ws_nword.split("K")[0]
    if "K" in ws_txt:
        nsales = int(ws_word)*1000
    else:
        nsales = int(ws_word)
    # log3("weekly sales: "+str(nsales))
    return nsales

#idx - which page out of all pages of search result.
def amz_buyer_fetch_product_list(html_file, idx):

    pagefull_of_pl = {"layout": "grid", "index": idx, "pl": None}
    products = []
    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')

        # all useful information are here:
        #extract all div tags which contains data-index attribute which is a indication of a product in the product list.
        prodItems = soup.findAll("div", attrs={"data-index":True})
        log3("# of div tags: "+str(len(prodItems)))
        # ageuseful = soup.findAll('span', {"class": 'content-value'})
        # agewords = ageuseful[0].text.split(' ')
        # usr.birth_year = int(agewords[3][0:4])
        # usr.birth_month = get_birth_month(agewords[2][1:4])
        # days = get_month_days(usr.birth_year, usr.birth_month)
        # usr.birth_day = random.randrange(1, days+1)

        # log3(agewords[0][1:4])     # ’age'
        # log3(agewords[1])          # age in number
        # log3(agewords[2][1:4])     # birth month
        # log3(agewords[3][0:4])     # birth year

        for item in prodItems:
            if item.get('data-asin') != None and item.get('data-asin') != "":
                # log3(item.get('data-asin'))

                sum_infos = item.findAll("span", attrs={"class": lambda t: t in ('a-size-base-plus a-color-base a-text-normal', 'a-size-medium a-color-base a-text-normal', 'a-size-base', 'a-icon-alt', 'a-size-base s-underline-text', 'a-price', 'a-color-base', 'a-badge-text', 'a-offscreen')})
                # log3("SUM INFO::: "+json.dumps(sum_infos))
                price_set = False
                weekly_set = False
                # log3("LEN SUM_INFOS: "+str(len(sum_infos)))
                summery = PRODUCT_SUMMERY()
                for sum_info in sum_infos:
                    # log3("class: "+sum_info.get('class'))
                    if " ".join(sum_info.get('class')) == 'a-size-base-plus a-color-base a-text-normal' or " ".join(sum_info.get('class')) == 'a-size-medium a-color-base a-text-normal':
                        summery.setTitle(sum_info.text)
                        # log3("Title: "+sum_info.text)
                    elif sum_info.get('class')[0] == 'a-icon-alt':
                        summery.setScore(float(sum_info.text.split(" ")[0]))
                        # log3("Score: "+sum_info.text)
                    elif " ".join(sum_info.get('class')) == 'a-size-base s-underline-text':
                        summery.setFeedbacks(convNFB(sum_info.text))
                        # log3("Feedback: "+sum_info.text)
                    elif sum_info.get('class')[0] == 'a-offscreen':
                        if price_set == False:
                            summery.setPrice(convPrice(sum_info.text))
                            price_set = True
                            # log3("Price: "+sum_info.text)

                    elif " ".join(sum_info.get('class')) == 'a-size-base a-color-secondary':
                        if weekly_set == False:
                            # log3("weekly: "+sum_info.text)
                            if "bought in" in sum_info.text:
                                summery.setWeekSales(convWeeklySales(sum_info.text))
                            else:
                                summery.setWeekSales(-1)
                            weekly_set = True
                    elif sum_info.get('class')[0] == 'a-badge-text':
                            log3("Found A Badge::: "+sum_info.text)
                            if sum_info.text == "Amazon's ":
                                summery.addBadge("Amazon's Choice")
                            elif sum_info.text != "Choice":
                                if sum_info.text == "Best Seller":
                                    summery.addBadge("Best Seller")
                                elif "Overall Pick" in sum_info.text:
                                    summery.addBadge("Overall Pick")
                                elif "Popular Brand Pick" in sum_info.text:
                                    summery.addBadge("Popular Brand Pick")

                    elif sum_info.get('class')[len(sum_info.get('class'))-1] == 'a-color-base':
                        if re.search('FREE', sum_info.text):
                            summery.setFreeDelivery(True)
                            # log3("free delivery: "+sum_info.text)


                # log3(json.dumps(summery.toJson()))
                product = PRODUCT()
                product.setSummery(summery)
                products.append(product.toJson())

    if len(products) < 54:
        pagefull_of_pl["layout"] = "list"
    pagefull_of_pl["pl"] = products
    log3("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    log3(json.dumps(pagefull_of_pl))
    log3("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")
    return pagefull_of_pl


def amz_buyer_fetch_product_details(html_file,  product):
    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')

        # <div id="titleSection" ...> contains the store information,

        # < div id = "featurebullets_feature_div" ..> about this item, start of the 7 bullets.
        # <li><span class="a-list-item"> Dou....> 7 bullets

        # < h2 > Product Description < / h2 > A+
        # look for h3, h4, h5 for sub section title and <p class="a-spacing-base"> for contents....

        # <h2> Product information </h2>
        # <table id="productDetails_detailBullets_sections1" class="a-keyvalue prodDetTable" role="presentation">

        # <h2 class="a-spacing-base a-color-base askWidgetTitle"> Customer questions &amp; answers </h2>

        # <h3 data-hook="lighthut-title" class="a-spacing-base">Read reviews that mention</h3>

        #<h3 data-hook="dp-local-reviews-header" class="a-spacing-medium a-spacing-top-large"> Top reviews from the United States </h3>

        #<a id="customer-reviews-content" aria-label="Top reviews" class="a-link-normal celwidget"
        #<a class="a-link-normal" title="5.0 out of 5 stars"
        # <a data-hook="review-title"
        # <span data-hook="review-date" class="a-size-base a-color-secondary review-date">
        # <span data-hook="review-body" class="a-size-base review-text"><div d

        #    <h3 data-hook="dp-global-reviews-header" class="a-spacing-base"> Top reviews from other countries </h3>

        # <div id="RBI0846G9G7XH-review-card" class="a-row a-spacing-none"><div id="customer_review_foreign-RBI0846G9G7XH"
        # <span class="cr-original-review-content">


    return product

def amz_buyer_fetch_product_reviews(html_file,  product):
    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')


        # <div id="R3VF13DMD8PFJZ" data-hook="review" class="a-section review aok-relative"><div id="R3VF13DMD8PFJZ-review-card" class="a-row a-spacing-none"><div id="customer_review-R3VF13DMD8PFJZ" class="a-section celwidget" data-csa-c-id="s99elt-vxx68-8om5f9-4flpns" data-cel-widget="customer_review-R3VF13DMD8PFJZ"><div data-hook="genome-widget" class="a-row a-spacing-mini"><a href="https://www.amazon.com/gp/profile/amzn1.account.AGXMO2DNFAXE4TGTOWTBO2O4CJOQ/ref=cm_cr_arp_d_gw_btm?ie=UTF8" class="a-profile" data-a-size="small"><div aria-hidden="true" class="a-profile-avatar-wrapper"><div class="a-profile-avatar"><img src="./mugsreviews0_files/31333236-2f56-4804-95e6-306eae3ec814._CR36,0,428,428_SX48_.jpg" class="" data-src="https://images-na.ssl-images-amazon.com/images/S/amazon-avatars-global/31333236-2f56-4804-95e6-306eae3ec814._CR36,0,428,428_SX48_.jpg"><noscript><img src="https://images-na.ssl-images-amazon.com/images/S/amazon-avatars-global/31333236-2f56-4804-95e6-306eae3ec814._CR36,0,428,428_SX48_.jpg"/></noscript></div></div><div class="a-profile-content"><span class="a-profile-name">Barry K.</span></div></a></div><div class="a-row"><a class="a-link-normal" title="4.0 out of 5 stars" href="https://www.amazon.com/gp/customer-reviews/R3VF13DMD8PFJZ/ref=cm_cr_arp_d_rvw_ttl?ie=UTF8&amp;ASIN=B08P8DJHHD"><i data-hook="review-star-rating" class="a-icon a-icon-star a-star-4 review-rating"><span class="a-icon-alt">4.0 out of 5 stars</span></i></a><span class="a-letter-space"></span><a data-hook="review-title" class="a-size-base a-link-normal review-title a-color-base review-title-content a-text-bold"
        # <span> title </span>
        # <span data-hook="review-date" class="a-size-base a-color-secondary review-date">
        # <div class="a-row a-spacing-small review-data"><span data-hook="review-body" class="a-size-base review-text review-text-content"> <span> review body </span> </div>

        # the key point is <div id="R1NROJHEJAQPNM" data-hook="review" ....



    return product


def processAmzScrapeOrders(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        pidx = step["pidx"]

        if step["html_dir_type"] == "direct":
            html_dir = step["html_dir"]
        else:
            exec("html_dir = "+step["html_dir"])

        html_file = html_dir + "/" + step["html_file"]
        pagefull_of_orders = {"page": pidx, "n_new_orders": 0, "num_pages": 0, "ol": None}
        orders = []
        option_tags = []

        with open(html_file, 'rb') as fp:
            soup = BeautifulSoup(fp, 'html.parser')

            li_tag = soup.find('li', class_='a-last')

            # Extract the page number from the href attribute of the <a> tag
            if li_tag:
                a_tag = li_tag.find('a')
                if a_tag:
                    href = a_tag['href']
                    page_number = href.split('=')[-1].split('#')[0]
                    log3("Current Page Number:"+str(page_number))
                else:
                    log3("No <a> tag found within the <li> tag.")
            else:
                log3("No <li> tag with class 'a-last' found.")


            # extract number of pages info
            orderItems = soup.findAll("tr")
            orderList = []
            if len(orderItems) > 0:
                log3("found page items.")

                for oi in orderItems:
                    oneOrder={}
                    # Extracting product ASIN
                    oneOrder["asin"] = oi.select_one('div:has(> span:contains("ASIN")) b').text

                    # Extracting order datetime
                    oneOrder["datetime"] = oi.select_one('div:has(> div:contains("days ago"))').text.strip()

                    # Extracting order number
                    oneOrder["orderId"] = oi.select_one(
                        'div:has(> a[href^="https://sellercentral.amazon.com/orders-v3/order/"])').text.strip()

                    orderedProducts = []
                    product_info_divs = oi.select('div:has(> span:contains("ASIN"))')  # Assuming each product info is contained in a div with ASIN
                    for product_info_div in product_info_divs:
                        product_name = product_info_div.previous_sibling.previous_sibling.text.strip()
                        product_quantity = product_info_div.find_next('div', string='Quantity').find_next(
                            'b').text.strip()
                        orderedProducts.append({"name": product_name, "quantity": product_quantity})

                    # Extracting total order price
                    oneOrder["total"] = oi.select_one('div:has(> span:contains("Item subtotal"))').text.split(':')[-1].strip()
                    orderList.append(oneOrder)


        pagefull_of_orders["ol"] = orderList

        pagefull_of_orders["n_new_orders"] = len(orderList)

        pagefull_of_orders["page"] = page_number


        if len(option_tags) > 0:
            pagefull_of_orders["num_pages"] = int(option_tags[len(option_tags)-1].text)
        else:
            pagefull_of_orders["num_pages"] = 1
        log3("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # log3(json.dumps(pagefull_of_orders))
        log3("# of orders:"+str(len(orders)))
        for o in orders:
            log3(json.dumps(o.toJson()))
        log3("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")

        symTab[step["result"]] = pagefull_of_orders


    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEtsyExtractTracking:" + str(i)
        log3(ex_stat)

    return next_i, ex_stat


def processAmzScrapeShipToAddress(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        pidx = step["pidx"]

        if step["html_dir_type"] == "direct":
            html_dir = step["html_dir"]
        else:
            exec("html_dir = "+step["html_dir"])

        html_file = html_dir + "/" + step["html_file"]
        pagefull_of_orders = {"page": pidx, "n_new_orders": 0, "num_pages": 0, "ol": None}
        shipTo = {}

        with open(html_file, 'rb') as fp:
            soup = BeautifulSoup(fp, 'html.parser')

            recipient_name = soup.find('span', {'data-test-id': 'shipping-section-recipient-name'}).text.strip()

            # Extract address lines
            address_lines = [line.strip() for line in
                             soup.find('div', {'data-test-id': 'shipping-section-buyer-address'}).stripped_strings]

            # Extract contact phone
            contact_phone = soup.find('span', {'data-test-id': 'shipping-section-phone'}).text.strip()

            # Extract other address information such as city, state, zip, etc. (if available)
            # Here, I assume that address lines contain all the required information, you may need to further parse it if needed

            # Printing extracted information
            log3("Recipient's Name:"+recipient_name)
            log3("Address Line 1:"+address_lines[0])
            log3("Address Line 2:"+(address_lines[1] if len(address_lines) > 1 else ""))  # Assuming there are at most 2 lines for the address
            log3("City, State, Zip:"+address_lines[2])
            log3("Contact Phone:"+contact_phone)

            city_state_zip = address_lines[-1].split(',')

            shipTo["recipient"] = recipient_name
            shipTo["phone"] = contact_phone
            shipTo["city"] = city_state_zip[0].strip()
            state_zip = city_state_zip[1].strip().split()
            shipTo["state"] = state_zip[0].upper()
            shipTo["zip"] = state_zip[1].strip()


        if len(option_tags) > 0:
            pagefull_of_orders["num_pages"] = int(option_tags[len(option_tags)-1].text)
        else:
            pagefull_of_orders["num_pages"] = 1
        log3("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # log3(json.dumps(pagefull_of_orders))
        log3("# of orders:"+str(len(orders)))
        for o in orders:
            log3(json.dumps(o.toJson()))
        log3("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")

        symTab[step["result"]] = pagefull_of_orders


    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEtsyExtractTracking:" + str(i)
        log3(ex_stat)

    return next_i, ex_stat


def genStepAmzScrapeMsgLists(html_dir, dir_name_type, html_file, pidx, outvar, statusvar, stepN):
    stepjson = {
        "type": "AMZ Scrape Msg Lists",
        "pidx": pidx,
        "html_dir": html_dir,
        "html_dir_type": dir_name_type,
        "html_file": html_file,
        "result": outvar,
        "status": statusvar
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepAmzScrapeCustomerMsgThread(html_dir, dir_name_type, html_file, pidx, outvar, statusvar, stepN):
    stepjson = {
        "type": "AMZ Scrape Customer Msg",
        "pidx": pidx,
        "html_dir": html_dir,
        "html_dir_type": dir_name_type,
        "html_file": html_file,
        "result": outvar,
        "status": statusvar
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def processAmzScrapeMsgList(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        pidx = step["pidx"]

        if step["html_dir_type"] == "direct":
            html_dir = step["html_dir"]
        else:
            exec("html_dir = "+step["html_dir"])

        html_file = html_dir + "/" + step["html_file"]
        pagefull_of_orders = {"page": pidx, "n_new_orders": 0, "num_pages": 0, "ol": None}
        shipTo = {}

        with open(html_file, 'rb') as fp:
            soup = BeautifulSoup(fp, 'html.parser')

            message_components = soup.find_all(class_=re.compile(r'message-component'))

            # Initialize list to store messages
            messages = []

            # Iterate through message components
            for component in message_components:
                msg_from = "customer" if "received" in component['class'] else "myself"
                msg_body = component.find(class_='message-body-text').get_text(strip=True)
                msg_date_str = component.find(class_='case-message-view-message-date').get_text(strip=True)

                # Convert date string to datetime object
                msg_date = datetime.datetime.strptime(msg_date_str, "%b %d, %Y %I:%M %p")

                # Append message to list
                messages.append({"msgFrom": msg_from, "msgBody": msg_body, "timeStamp": msg_date.strftime("%Y-%m-%d %H:%M:%S")})

            # Sort messages chronologically
            messages.sort(key=lambda x: x["timeStamp"])

            # Print the messages
            for message in messages:
                log3(json.dumps(message))


        if len(option_tags) > 0:
            pagefull_of_orders["num_pages"] = int(option_tags[len(option_tags)-1].text)
        else:
            pagefull_of_orders["num_pages"] = 1
        log3("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # log3(json.dumps(pagefull_of_orders))
        log3("# of orders:"+str(len(orders)))
        for o in orders:
            log3(json.dumps(o.toJson()))
        log3("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")

        symTab[step["result"]] = pagefull_of_orders


    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEtsyExtractTracking:" + str(i)
        log3(ex_stat)

    return next_i, ex_stat


def processAmzScrapeCustomerMsgThread(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        pidx = step["pidx"]

        if step["html_dir_type"] == "direct":
            html_dir = step["html_dir"]
        else:
            exec("html_dir = "+step["html_dir"])

        html_file = html_dir + "/" + step["html_file"]
        pagefull_of_orders = {"page": pidx, "n_new_orders": 0, "num_pages": 0, "ol": None}
        shipTo = {}

        with open(html_file, 'rb') as fp:
            soup = BeautifulSoup(fp, 'html.parser')

            message_components = soup.find_all(class_=re.compile(r'message-component'))

            # Initialize list to store messages
            messages = []

            # Iterate through message components
            for component in message_components:
                msg_from = "customer" if "received" in component['class'] else "myself"
                msg_body = component.find(class_='message-body-text').get_text(strip=True)
                msg_date_str = component.find(class_='case-message-view-message-date').get_text(strip=True)

                # Convert date string to datetime object
                msg_date = datetime.datetime.strptime(msg_date_str, "%b %d, %Y %I:%M %p")

                # Append message to list
                messages.append({"msgFrom": msg_from, "msgBody": msg_body, "timeStamp": msg_date.strftime("%Y-%m-%d %H:%M:%S")})

            # Sort messages chronologically
            messages.sort(key=lambda x: x["timeStamp"])

            # Print the messages
            for message in messages:
                log3(json.dumps(message))


        if len(option_tags) > 0:
            pagefull_of_orders["num_pages"] = int(option_tags[len(option_tags)-1].text)
        else:
            pagefull_of_orders["num_pages"] = 1
        log3("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # log3(json.dumps(pagefull_of_orders))
        log3("# of orders:"+str(len(orders)))
        for o in orders:
            log3(json.dumps(o.toJson()))
        log3("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")

        symTab[step["result"]] = pagefull_of_orders


    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEtsyExtractTracking:" + str(i)
        log3(ex_stat)

    return next_i, ex_stat