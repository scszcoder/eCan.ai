import json
from bs4 import BeautifulSoup
import pyautogui
import numpy as np
import re
import random
from calendar import isleap
import cv2
from ordersData import *


def etsy_seller_fetch_order_list(html_file,  pidx):
    pagefull_of_orders = {"page": pidx, "ol": None}
    orders = []

    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')

        # per order information blocks
        divItems = soup.findAll("div", attrs={"class": "orders-full-width-panel-on-mobile panel panel-no-footer mb-xs-4"})
        for item in divItems:
            # extract buyer info.
            order = ORDER("", "", "", "", "", "")
            products = []

            buyerItems = item.findAll("div", attrs={"class": "break-word"})
            for bi in buyerItems:
                buyer_loc_tags = bi.findAll("span", attrs={"data-test-id": 'unsanitize'})
                if len(buyer_loc_tags) == 3:
                    print("buyer_loc_tags:", buyer_loc_tags)
                    buyer = Buyer("", "", "", "", "", "")
                    buyer.setFullName(buyer_loc_tags[0].text)
                    buyer.setCity(buyer_loc_tags[1].text)
                    buyer.setState(buyer_loc_tags[2].text)

                # oid_tags = item.findAll("span", attrs={"data-test-id": 'unsanitize'})

            # extract product info.
            aItems = item.findAll("a", attrs={"class": "text-gray-darkest break-word"})
            for aitem in aItems:
                product = OrderedProducts("", "", "", "")
                print("product title:", aitem["title"])
                product.setPtitle(aitem['title'])
                products.append(product)

            liItems = item.findAll("li", attrs={"class": "clearfix"})
            pidx = 0
            for lii in liItems:
                qItems = lii.findAll("span", attrs={"class": 'strong'})
                if len(qItems) > 0:
                    print("Quantity:", qItems[0].text)
                    products[pidx].setQuantity(qItems[0].text)
                pidx = pidx + 1

            aItems = item.findAll("a", attrs={"aria-current": "page", "class": "text-gray active"})
            print("orderID: ", aItems[1].text)
            order.setOid(aItems[1].text)

            aItems = item.findAll("span", attrs={"class": "display-inline-block"})
            print("total price: ", float(aItems[0].text[1:]))
            order.setTotalPrice(float(aItems[0].text[1:]))

            order.setProducts(products)
            order.setBuyer(buyer)
            shipping = Shipping("", "", "", "", "", "", "", "")
            order.setShipping(shipping)
            orders.append(order)

    pagefull_of_orders["ol"] = orders
    print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    # print(json.dumps(pagefull_of_orders))
    print("# of orders:", len(orders))
    print([o.toJson() for o in orders])
    print("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")
    return pagefull_of_orders