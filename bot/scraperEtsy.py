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
def genStepEtsyScrapeOrders(html, pidx, outvar, statusvar, stepN):
    stepjson = {
        "type": "ETSY Scrape Orders",
        "pidx": pidx,
        "html_file": html,
        "result": outvar,
        "status": statusvar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def processEtsyScrapeOrders(step, i):
    pidx = step["pidx"]
    html_file = step["html_file"]
    pagefull_of_orders = {"page": pidx, "n_new_orders": 0, "num_pages": 0, "ol": None}
    orders = []
    option_tags = []

    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')

        # per order information blocks
        pageItems = soup.findAll("div", attrs={"class": "wt-select wt-mr-xs-2"})
        option_tags = []
        if len(pageItems) > 0:
            print("found page items.")
            for pi in pageItems:
                option_tags = pi.findAll("option")
                print(option_tags)

        ahItems = soup.findAll("a", attrs={"class": "text-gray active"})
        page_number = -1
        for ah in ahItems:
            if "page=" in ah.get('href') and "order_id" in ah.get('href'):
                pieces = ah.get('href').split("&")
                for piece in pieces:
                    if "page" in piece:
                        page_number = int(piece.split("=")[1])
                        print("found page number: ", page_number)
                        break

            if page_number > 0:
                break

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


        divItems = soup.findAll("div", attrs={"class": "orders-full-width-panel-on-mobile panel panel-no-footer mb-xs-4"})
        for item in divItems:
            # extract recipient info.
            order = ORDER("", "", "", "", "", "", "")
            products = []

            recipientItems = item.findAll("div", attrs={"class": "break-word"})
            for bi in recipientItems:
                recipient_loc_tags = bi.findAll("span", attrs={"data-test-id": 'unsanitize'})
                if len(recipient_loc_tags) == 3:
                    print("recipient_loc_tags:", recipient_loc_tags)
                    recipient = OrderPerson("", "", "", "", "", "", "")
                    recipient.setFullName(recipient_loc_tags[0].text)
                    recipient.setCity(recipient_loc_tags[1].text)
                    recipient.setState(recipient_loc_tags[2].text)

                # oid_tags = item.findAll("span", attrs={"data-test-id": 'unsanitize'})

            # extract product info.
            aItems = item.findAll("a", attrs={"class": "text-gray-darkest break-word"})
            for aitem in aItems:
                product = OrderedProducts("", "", "", "")
                print("product title:", aitem["title"])
                product.setPTitle(aitem['title'])
                products.append(product)


            liItems = item.findAll("li", attrs={"class": "clearfix"})
            pidx = 0
            print(" # of products: ", len(products), "# of liItems:", len(liItems))
            for lii in liItems:
                qItems = lii.findAll("span", attrs={"class": 'strong'})
                if len(qItems) > 0:
                    print("Quantity:", qItems[0].text, "pidx:", pidx)
                    products[pidx].setQuantity(qItems[0].text)

                pidx = pidx + 1

            aItems = item.findAll("a", attrs={"aria-current": "page", "class": "text-gray active"})
            print("orderID: ", aItems[1].text)
            order.setOid(aItems[1].text)

            aItems = item.findAll("span", attrs={"class": "display-inline-block"})
            print("total price: ", float(aItems[0].text[1:]))
            order.setTotalPrice(float(aItems[0].text[1:]))

            order.setProducts(products)
            order.setRecipient(recipient)
            shipping = Shipping("", "", "", "", "", "", "", "")
            order.setShipping(shipping)
            orders.append(order)

    pagefull_of_orders["ol"] = orders

    if len(option_tags) > 0:
        print(option_tags[len(option_tags)-1].text)
    else:
        print("all only 1 page.")
    print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    # print(json.dumps(pagefull_of_orders))
    print("# of orders:", len(orders))
    print([o.toJson() for o in orders])
    print("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")

    symTab[step["result"]] = pagefull_of_orders

    return i + 1