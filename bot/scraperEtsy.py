import json
from bs4 import BeautifulSoup
import pyautogui
import numpy as np
import re
import random
from calendar import isleap
import cv2
from ordersData import *
from basicSkill import *
import esprima
from esprima.visitor import Visitor

global symTab
global STEP_GAP

# html: html file name, pidx: page index,
def genStepEtsyScrapeOrders(html_dir, dir_name_type, html_file, pidx, outvar, statusvar, stepN):
    stepjson = {
        "type": "ETSY Scrape Orders",
        "pidx": pidx,
        "html_dir": html_dir,
        "html_dir_type": dir_name_type,
        "html_file": html_file,
        "result": outvar,
        "status": statusvar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# without address details
# # order id...... revenue(price) .... ship by date ..... break-word : product title    <li....> quantity  .... "break-word" - name, city, state....
# with address details
# order id...... revenue(price) .... ship by date ..... break-word : product title    <li....> quantity  .... "address break-word" - all name address details....
def processEtsyScrapeOrders(step, i):
    ex_stat = "success:0"
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

            # extract number of pages info
            pageItems = soup.findAll("div", attrs={"class": "wt-select wt-mr-xs-2"})
            option_tags = []
            if len(pageItems) > 0:
                print("found page items.")
                for pi in pageItems:
                    option_tags = pi.findAll("option")
                    print(option_tags)

            # extract page number info
            ahItems = soup.findAll("a", attrs={"class": "text-gray active"})
            page_number = 1
            for ah in ahItems:
                if "page=" in ah.get('href') and "order_id" in ah.get('href'):
                    pieces = ah.get('href').split("&")
                    for piece in pieces:
                        if "page" in piece:
                            page_number = int(piece.split("=")[1])
                            print("found page number: ", page_number)
                            break

                if page_number > 1:
                    break

            # extract total number of orders
            scriptItems = soup.findAll("script")
            for item in scriptItems:
                # print("item: ", item)

                # found = re.findall("orderId.*feedbackScore", item.text)
                pattern = r'order_count'
                found = re.findall(pattern, item.text)
                if found:
                    order_count = -1
                    tokens = esprima.tokenize(item.text)
                    usefull = [t for i, t in enumerate(tokens) if t.type != "Identifier" and t.type != "Punctuator" and t.value != "\"textSpans\"" and t.value != "\"text\""]
                    # print(usefull)
                    i = 0
                    useful_i = -9
                    for x in usefull:
                        if x.value == "\"order_count\"":
                            # print(x)
                            useful_i = i

                        if i == useful_i + 1 and x.type == "Numeric":
                            order_count = int(x.value)
                            print("order count: ", order_count)
                            break

                        i = i + 1

                    if order_count >= 0:
                        break

            # this is the true divisional tag that contains all info of an order on this html page..
            orderItems = soup.findAll("div", attrs={"panel-body-row has-hover-state pt-xs-0 pl-xs-0 pr-xs-0 pb-xs-3 pb-xl-4"})

            # divItems = soup.findAll("div", attrs={"class": "orders-full-width-panel-on-mobile panel panel-no-footer mb-xs-4"})
            for item in orderItems:
                # extract recipient info.

                # this is for expanded recipient address
                recipientDetailsItems = item.findAll("div", attrs={"class": "address break-word"})
                for ri in recipientDetailsItems:
                    order = ORDER("", "", "", "", "", "", "")
                    products = []
                    recipient = OrderPerson("", "", "", "", "", "", "")
                    recipient_name_tags = ri.findAll("span", attrs={"class": 'name'})
                    recipient_addr_1st_line_tags = ri.findAll("span", attrs={"class": 'first-line'})
                    recipient_addr_2nd_line_tags = ri.findAll("span", attrs={"class": 'second-line'})
                    recipient_addr_3rd_line_tags = ri.findAll("span", attrs={"class": 'third-line'})
                    recipient_addr_city_tags = ri.findAll("span", attrs={"class": 'city'})
                    recipient_addr_state_tags = ri.findAll("span", attrs={"class": 'state'})
                    recipient_addr_zip_tags = ri.findAll("span", attrs={"class": 'zip'})
                    recipient_addr_country_tags = ri.findAll("span", attrs={"class": 'country-name'})

                    if len(recipient_name_tags) > 0:
                        recipient.setFullName(recipient_name_tags[0].text)

                    if len(recipient_addr_1st_line_tags) > 0:
                        recipient.setStreet1(recipient_addr_1st_line_tags[0].text)

                    if len(recipient_addr_2nd_line_tags) > 0:
                        recipient.setStreet2(recipient_addr_2nd_line_tags[0].text)

                    if len(recipient_addr_3rd_line_tags) > 0:
                        recipient.setStreet3(recipient_addr_3rd_line_tags[0].text)

                    if len(recipient_addr_city_tags) > 0:
                        recipient.setCity(recipient_addr_city_tags[0].text)

                    if len(recipient_addr_state_tags) > 0:
                        recipient.setState(recipient_addr_state_tags[0].text)

                    if len(recipient_addr_zip_tags) > 0:
                        recipient.setZip(recipient_addr_zip_tags[0].text)

                    if len(recipient_addr_country_tags) > 0:
                        recipient.setCountry(recipient_addr_country_tags[0].text)


                # this is for unexpanded recipient address
                recipientItems = item.findAll("div", attrs={"class": "break-word"})
                for bi in recipientItems:
                    recipient_loc_tags = bi.findAll("span", attrs={"data-test-id": 'unsanitize'})

                    if len(recipient_loc_tags) == 3:
                        order = ORDER("", "", "", "", "", "", "")
                        products = []
                        print("recipient_loc_tags:", recipient_loc_tags)
                        recipient = OrderPerson("", "", "", "", "", "", "")
                        recipient.setFullName(recipient_loc_tags[0].text)
                        recipient.setCity(recipient_loc_tags[1].text)
                        recipient.setState(recipient_loc_tags[2].text)
                    else:
                        print("no unexpanded addr....")

                    # oid_tags = item.findAll("span", attrs={"data-test-id": 'unsanitize'})

                # extract product title info.
                aItems = item.findAll("a", attrs={"class": "text-gray-darkest break-word"})
                for aitem in aItems:
                    product = OrderedProduct("", "", "", "")
                    print("product title:", aitem["title"])
                    product.setPTitle(aitem['title'])
                    products.append(product)

                # <ul class="list-unstyled text-body-smaller"> this tag contains all the <li> tags. each product has a <ul>
                # <li> tags contains product quantity and variations, 1st one is always quantity, the rest are variations.
                pidx = 0
                ulItems = item.findAll("ul", attrs={"class": "list-unstyled text-body-smaller"})
                for ulItems in ulItems:
                    liItems = ulItems.findAll("li", attrs={"class": "clearfix"})
                    print(" # of products: ", len(products), "# of liItems:", len(liItems))
                    liidx = 0
                    for lii in liItems:
                        if liidx == 0:
                            qItems = lii.findAll("span", attrs={"class": 'strong'})
                            if len(qItems) > 0:
                                print("Quantity:", qItems[0].text, "pidx:", pidx)
                                if qItems[0].text.isnumeric():
                                    products[pidx].setQuantity(qItems[0].text)
                        else:
                            # <span class="mr-xs-1 text-gray-lighter">Color</span><span>Blue</span>
                            qItems = lii.findAll("span", attrs={"class": 'mr-xs-1 text-gray-lighter'})
                            var_key = qItems[0].text
                            qItems = lii.findAll("span", attrs={"class": None})
                            var_val = qItems[0].text
                            products[pidx].addVariation([var_key, var_val])

                        liidx = liidx + 1

                    pidx = pidx + 1

                # obtain order ID, each order will have only 1 of these.
                aItems = item.findAll("a", attrs={"aria-current": "page", "class": "text-gray active"})
                print("orderID: ", aItems[1].text)
                order.setOid(aItems[1].text)

                # obtain total price of the order, each order will have only 1 of these.
                aItems = item.findAll("span", attrs={"class": "display-inline-block"})
                print("total price: ", float(aItems[0].text[1:]))
                order.setTotalPrice(float(aItems[0].text[1:]))

                order.setProducts(products)
                order.setRecipient(recipient)
                shipping = Shipping("", "", "", "", "", "", "", "")
                order.setShipping(shipping)
                orders.append(order)

        pagefull_of_orders["ol"] = orders

        pagefull_of_orders["n_new_orders"] = orders

        pagefull_of_orders["page"] = page_number


        if len(option_tags) > 0:
            pagefull_of_orders["num_pages"] = int(option_tags[len(option_tags)-1].text)
        else:
            pagefull_of_orders["num_pages"] = 1
        print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # print(json.dumps(pagefull_of_orders))
        print("# of orders:", len(orders))
        for o in orders:
            print(o.toJson())
        print("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")

        symTab[step["result"]] = pagefull_of_orders

    except:
        ex_stat = "ErrorEtsyExtractTracking:" + str(i)

    return next_i, ex_stat