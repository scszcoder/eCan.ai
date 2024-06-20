import datetime
import json
import re


from bs4 import BeautifulSoup
from bot.Logger import log3
from bot.basicSkill import symTab, STEP_GAP, DEFAULT_RUN_STATUS
from bot.productsData import PRODUCT, PRODUCT_SUMMERY

# DEFAULT_RUN_STATUS = "Completed:0"

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
def amz_buyer_scrape_product_list(html_file, idx):

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
    log3("+++++++++++++++++++++"+str(len(pagefull_of_pl["pl"]))+"+++++++++++++++++++++++++++++")
    log3(json.dumps(pagefull_of_pl))
    log3("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")
    return pagefull_of_pl


def amz_buyer_scrape_product_details(html_file):
    product_details = {
        "title": "",
        "store": "",
        "variations": None,
        "varPrices": None,
        "default_price": "",
        "score": "",
        "rating": ""
    }
    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')

        titleTag = soup.find("div", attrs={"id": "titleSection"})
        if titleTag:
            titleHeaderTag = titleTag.find("h1", attrs={"id": "title"})
            if titleHeaderTag:
                product_details["title"] = titleHeaderTag.text.strip()


        storeTag = soup.find("a", attrs={"id": "bylineInfo"})
        if storeTag:
            pattern = r"Visit the (.*) Store"

            # Use re.search to find the match
            match = re.search(pattern, storeTag.text)

            if match:
                # Extract the store name from the match object
                product_details["store"] = match.group(1)
                # print(f"Store name: {product_details['store']}")
            # else:
                # print("No store match found.")

        ratingTag = soup.find("a", attrs={"id": "acrCustomerReviewLink"})
        if ratingTag:
            product_details["rating"] = ratingTag.text.strip()

        scoreSecTag = soup.find("div", attrs={"id": "averageCustomerReviews"})
        if scoreSecTag:
            scoreTag = scoreSecTag.find("span", attrs={"class": "a-size-base a-color-base"})
            if scoreTag:
                product_details["score"] = scoreTag.text.strip()


        priceSecTag = soup.find('div', id=re.compile(r'^corePrice'))
        if priceSecTag:
            priceTag = priceSecTag.find("span", attrs={"class": "a-offscreen"})
            if priceTag:
                product_details["default_price"] = priceTag.text

        varPriceNames = []
        varNamePriceSecTags = soup.findAll('div', attrs={"class": "twisterTextDiv text"})

        for varNamePriceSecTag in varNamePriceSecTags:
            pTags = varNamePriceSecTag.findAll('p')
            # there should be 2 p tags found here. the first one contains the variation name,
            # the second contains the price for this variation
            # print(pTags)
            if len(pTags) > 0:
                varPriceNames.append(pTags[0].text.strip())
        # print("varPriceNames:", varPriceNames)

        varPrices = []
        varPriceSecTags = soup.find_all('div', class_='twisterSlotDiv')
        # print(varPriceSecTags)
        varNamePrices = {}
        for varPriceSecTag in varPriceSecTags:
            pTags = varPriceSecTag.findAll('p')
            print(pTags)
            if len(pTags) > 0:
                varPrices.append(pTags[0].text.strip())
        # print("varPrices:", varPrices)

        for i in range(len(varPrices)):
            varNamePrices[varPriceNames[i]] = varPrices[i]

        product_details["varPrices"] = varNamePrices
        # print("varNamePrices:", varNamePrices)

        # obtain variations related info.
        script_tags = soup.findAll('script', text=re.compile(r'P\.register'))
        # If the script tag is found
        for script_tag in script_tags:
            # print("found P.register")

            # Extract the JavaScript code
            script_content = script_tag.string

            # Use a regular expression to find the JSON content of the abc variable
            match = re.search(r'var\s+dataToReturn\s*=\s*(\{.*?\});', script_content, re.DOTALL)

            if match:
                # Extract the JSON string
                # print("found match")
                json_str = match.group(1)

                # print(json_str)
                # print("===========================================================")

                pattern1 = r'"updateDivLists"\s*:\s*\{[^{}]*(\{[^{}]*\}[^{}]*)*\}\s*,?'

                # Use re.sub to replace the matched pattern with an empty string
                simplified_json_string = re.sub(pattern1, '', json_str, flags=re.DOTALL)
                simplified_json_string = re.sub(r',\s*}', '}', simplified_json_string)
                simplified_json_string = re.sub(r',\s*]', ']', simplified_json_string)

                # print(simplified_json_string)
                # Convert the JSON string to a Python dictionary
                rawVariationsJson = json.loads(simplified_json_string)

                # copy over the key values only.
                thisVar = {}
                if "num_total_variations" in rawVariationsJson:
                    # print("found num_total_variations")
                    thisVar["num_total_variations"] = rawVariationsJson["num_total_variations"]

                if "asinVariationValues" in rawVariationsJson:
                    # print("found asinVariationValues")
                    thisVar["asinVariationValues"] = rawVariationsJson["asinVariationValues"]

                if "selectedVariationValues" in rawVariationsJson:
                    # print("found selectedVariationValues")
                    thisVar["selectedVariationValues"] = rawVariationsJson["selectedVariationValues"]

                if "currentAsin" in rawVariationsJson:
                    # print("found currentAsin")
                    thisVar["currentAsin"] = rawVariationsJson["currentAsin"]

                if "parentAsin" in rawVariationsJson:
                    # print("found parentAsin")
                    thisVar["parentAsin"] = rawVariationsJson["parentAsin"]

                if "dimensionValuesDisplayData" in rawVariationsJson:
                    # print("found dimensionValuesDisplayData")
                    thisVar["dimensionValuesDisplayData"] = rawVariationsJson["dimensionValuesDisplayData"]

                if "variationDisplayLabels" in rawVariationsJson:
                    # print("found dimensionValuesDisplayData")
                    thisVar["variationDisplayLabels"] = rawVariationsJson["variationDisplayLabels"]

                if "variationValues" in rawVariationsJson:
                    # print("found dimensionValuesDisplayData")
                    thisVar["variationValues"] = rawVariationsJson["variationValues"]

                if "dimensionsDisplayType" in rawVariationsJson:
                    # print("found dimensionValuesDisplayData")
                    thisVar["dimensionsDisplayType"] = rawVariationsJson["dimensionsDisplayType"]


                # print("thisVar:", thisVar)
                product_details["variations"] = thisVar
                break
            else:
                print("Variable 'dataToReturn' not found in the script content.")
        else:
            print("Script tag containing 'P.register' not found.")

    print("product_details:", json.dumps(product_details, indent=4))
    return product_details

def amz_buyer_scrape_product_reviews(html_file,  product):
    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')


        # <div id="R3VF13DMD8PFJZ" data-hook="review" class="a-section review aok-relative"><div id="R3VF13DMD8PFJZ-review-card" class="a-row a-spacing-none"><div id="customer_review-R3VF13DMD8PFJZ" class="a-section celwidget" data-csa-c-id="s99elt-vxx68-8om5f9-4flpns" data-cel-widget="customer_review-R3VF13DMD8PFJZ"><div data-hook="genome-widget" class="a-row a-spacing-mini"><a href="https://www.amazon.com/gp/profile/amzn1.account.AGXMO2DNFAXE4TGTOWTBO2O4CJOQ/ref=cm_cr_arp_d_gw_btm?ie=UTF8" class="a-profile" data-a-size="small"><div aria-hidden="true" class="a-profile-avatar-wrapper"><div class="a-profile-avatar"><img src="./mugsreviews0_files/31333236-2f56-4804-95e6-306eae3ec814._CR36,0,428,428_SX48_.jpg" class="" data-src="https://images-na.ssl-images-amazon.com/images/S/amazon-avatars-global/31333236-2f56-4804-95e6-306eae3ec814._CR36,0,428,428_SX48_.jpg"><noscript><img src="https://images-na.ssl-images-amazon.com/images/S/amazon-avatars-global/31333236-2f56-4804-95e6-306eae3ec814._CR36,0,428,428_SX48_.jpg"/></noscript></div></div><div class="a-profile-content"><span class="a-profile-name">Barry K.</span></div></a></div><div class="a-row"><a class="a-link-normal" title="4.0 out of 5 stars" href="https://www.amazon.com/gp/customer-reviews/R3VF13DMD8PFJZ/ref=cm_cr_arp_d_rvw_ttl?ie=UTF8&amp;ASIN=B08P8DJHHD"><i data-hook="review-star-rating" class="a-icon a-icon-star a-star-4 review-rating"><span class="a-icon-alt">4.0 out of 5 stars</span></i></a><span class="a-letter-space"></span><a data-hook="review-title" class="a-size-base a-link-normal review-title a-color-base review-title-content a-text-bold"
        # <span> title </span>
        # <span data-hook="review-date" class="a-size-base a-color-secondary review-date">
        # <div class="a-row a-spacing-small review-data"><span data-hook="review-body" class="a-size-base review-text review-text-content"> <span> review body </span> </div>

        # the key point is <div id="R1NROJHEJAQPNM" data-hook="review" ....

    return product


def processAmzScrapeBuyOrdersHtml(step, i):
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

            page_sections = soup.find_all('ul', class_="a-pagination")
            if len(page_sections) > 0:
                page_list = page_sections[0].find_all('li')
                n_pages = len(page_list)-2
            else:
                n_pages = 0
            print("total page:", n_pages)


            order_box_sections = soup.find_all('div', class_=lambda x: x and x.startswith("a-box-group a-spacing-base"))
            for order_box in order_box_sections:
                order_info = {}
                order_sections = order_box.find_all('div', class_=lambda x: x and x.startswith('a-box a-color-offset-background'))
                print("n order sections:", len(order_sections))
                for order_section in order_sections:
                    # Extract order ID
                    spans = order_section.find_all('span')
                    print("n spans", len(spans))
                    for i, span in enumerate(spans):
                        if "Order #" in span.get_text(strip=True):
                            order_id = spans[i + 1].get_text(strip=True)
                            order_info['order_id'] = order_id
                            print("order id:", order_id)

                    # Extract order date
                    order_date_section = order_section.find("div", class_="a-column a-span3")
                    if order_date_section:
                        order_date_label = order_date_section.find("span", class_=lambda x: x and x.startswith('a-color-secondary'))
                        if order_date_label and order_date_label.get_text(strip=True) == "Order placed":
                            order_date = order_date_section.find("span", class_=lambda x: x in ["a-size-base a-color-secondary", "a-color-secondary value"]).get_text(strip=True)
                            order_info["order_date"] = order_date

                    # Extract order dollar amount
                    order_dollar_sections = order_section.find_all("div", class_=lambda x: x and x.startswith("a-column a-span2"))
                    print("span2:::", len(order_dollar_sections))
                    # order_dollar_section = order_section.find("div", class_="a-column a-span2")
                    order_dollar_section = order_section.find("div", class_="a-column a-span2")
                    alt_order_dollar_section = order_section.find("div", class_="a-column a-span2 yohtmlc-order-total")
                    if order_dollar_section.get_text(strip=True):
                        print("checking dollar")
                        order_dollar_label = order_dollar_section.find("span", class_=lambda x: x and x.startswith('a-color-secondary'))
                        if order_dollar_label and order_dollar_label.get_text(strip=True) == "Total":
                            order_dollar = order_dollar_section.find("span", class_=lambda x: x in ["a-size-base a-color-secondary", "a-color-secondary value"]).get_text(strip=True)
                            order_info["order_dollar"] = order_dollar
                    elif alt_order_dollar_section.get_text(strip=True):
                        print("checking alt dollar")
                        order_dollar_label = alt_order_dollar_section.find("span", class_=lambda x: x and x.startswith('a-color-secondary'))
                        if order_dollar_label and order_dollar_label.get_text(strip=True) == "Total":
                            order_dollar = alt_order_dollar_section.find("span", class_=lambda x: x in ["a-size-base a-color-secondary", "a-color-secondary value"]).get_text(strip=True)
                            order_info["order_dollar"] = order_dollar

                delivery_sections = order_box.find_all('div', class_=lambda x: x in ['a-box shipment', 'a-box delivery-box'])
                items = []
                for delivery_section in delivery_sections:
                    item = {}
                    # Extract delivery status
                    delivery_status_section = delivery_section.find("span", class_=lambda x: x in ["a-size-medium delivery-box__primary-text a-text-bold", "a-size-medium a-color-base a-text-bold"])
                    if delivery_status_section:
                        delivery_status = delivery_status_section.get_text(strip=True)
                        item["delivery_status"] = delivery_status
                        print("deliver status:", delivery_status)

                    # Extract product title   "yohtmlc-product-title"
                    product_title_section = delivery_section.find("div", class_="a-fixed-left-grid-col yohtmlc-item a-col-right")
                    if product_title_section:
                        product_title = product_title_section.find("a", class_="a-link-normal").get_text(strip=True)
                        item["product_title"] = product_title
                        print("product title:", product_title)

                    product_title_section = delivery_section.find("div", class_="yohtmlc-product-title")
                    if product_title_section:
                        product_title = product_title_section.get_text(strip=True)
                        item["product_title"] = product_title
                        print("product title:", product_title)

                    if item:
                        items.append(item)

                order_info["items"] = items

                if order_info:
                    orders.append(order_info)

        print("all orders:", orders)
        pagefull_of_orders["ol"] = orders

        pagefull_of_orders["n_orders"] = len(orders)

        pagefull_of_orders["page"] = pidx


        pagefull_of_orders["num_pages"] = n_pages
        log3("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")

        symTab[step["result"]] = pagefull_of_orders


    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorAmzScrapeBuyOrdersHtml:" + str(i)
        log3(ex_stat)

    return next_i, ex_stat


def processAmzScrapeSoldOrdersHtml(step, i):
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

            ordered_list_section = soup.find('div', class_='myo-table-container')

            # Extract the page number from the href attribute of the <a> tag
            if ordered_list_section:
                a_tag = ordered_list_section.find('a')
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
                    cbt_divs = oi.find_all('div', class_="cell-body-title")
                    print("ndivs:", len(cbt_divs))
                    if len(cbt_divs) > 0:
                        divs = oi.find_all('div')
                        for div in divs:
                            spans = div.find_all('span')
                            atags = div.find_all('a')
                            for span in spans:
                                if span:
                                    if span.get_text() == "ASIN":
                                        asin_tag = div.find('b')
                                        if asin_tag:
                                            asin = asin_tag.get_text()
                                            print("asin:", asin)
                                    elif span.get_text() == "Quantity":
                                        qty_tag = div.find('b')
                                        if qty_tag:
                                            quantity = qty_tag.get_text()
                                            print("quantity:", quantity)
                                    elif span.get_text() == "Item subtotal":
                                        subtotal = div.get_text()
                                        print("subtotal:", subtotal.split("$")[1])


                            for atag in atags:
                                if atag:
                                    if len(atag.contents) == 1 and isinstance(atag.contents[0], NavigableString):
                                        href = a_tag.get('href')
                                        print("HREF:", href)
                                        if href:
                                            print("HREF TXT", atag.get_text())
                                            if "orders-v3" in href and "shipment" not in href:
                                                oid = atag.get_text()
                                                print("oid:", oid)



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
        ex_stat = "ErrorAmzScrapeSoldOrdersHtml:" + str(i)
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

            recipient_name = soup.find('span', {'data-tests-id': 'shipping-section-recipient-name'}).text.strip()

            # Extract address lines
            address_lines = [line.strip() for line in
                             soup.find('div', {'data-tests-id': 'shipping-section-buyer-address'}).stripped_strings]

            # Extract contact phone
            contact_phone = soup.find('span', {'data-tests-id': 'shipping-section-phone'}).text.strip()

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

def genStepAmzScrapeBuyOrdersHtml(html_dir, dir_name_type, html_file, pidx, outvar, statusvar, stepN):
    stepjson = {
        "type": "AMZ Scrape Buy Orders Html",
        "pidx": pidx,
        "html_dir": html_dir,
        "html_dir_type": dir_name_type,
        "html_file": html_file,
        "result": outvar,
        "status": statusvar
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepAmzScrapeSoldOrdersHtml(html_dir, dir_name_type, html_file, pidx, outvar, statusvar, stepN):
    stepjson = {
        "type": "AMZ Scrape Sold Orders Html",
        "pidx": pidx,
        "html_dir": html_dir,
        "html_dir_type": dir_name_type,
        "html_file": html_file,
        "result": outvar,
        "status": statusvar
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



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