import json
from bs4 import BeautifulSoup
import pyautogui
import numpy as np
import re
import random
from calendar import isleap
import cv2
import esprima
from esprima.visitor import Visitor
from basicSkill import *
from ordersData import *



def ebay_seller_fetch_page_of_order_list(html_file,  pidx):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        pagefull_of_orders = {"page": pidx, "ol": None}
        orders = []

        # Use Esprima to parse your JavaScript code
        # esprima_output = context.eval("esprima.parse('{}')".format(js_code))

        # Output will be a dictionary representing the parsed JavaScript code
        # print(esprima_output)

        with open(html_file, 'rb') as fp:
            soup = BeautifulSoup(fp, 'html.parser')

            # all useful information are here:
            # extract all div tags which contains data-index attribute which is a indication of a product in the product list.
            prodItems = soup.findAll("script")
            print(len(prodItems))



            for item in prodItems:
                # print("item: ", item)

                # found = re.findall("orderId.*feedbackScore", item.text)
                pattern = r'orderId.*?feedbackScore'
                found = re.findall(pattern, item.text)
                if found:
                    tokens = esprima.tokenize(item.text)
                    # js_tree = esprima.visitor.Visitor(item.text)
                    print("js tree:", tokens)

                    usefull = [t for i, t in enumerate(tokens) if t.type != "Identifier" and t.type != "Punctuator" and t.value != "\"textSpans\"" and t.value != "\"text\""]
                    nindex = 0
                    in_order = False
                    node_stack = []
                    products = []
                    for node in usefull:
                        # print("node: ", node.value)
                        # stuff we want to grab out of...
                        # creationDate
                        # Ship by ....Jul 12
                        # totalQuantity
                        # displayTotalPrice
                        # orderLineItems -
                        # listingId - after listingSummary line
                        # "363861703280"
                        # title - after listingId
                        # "10W auto clamping car wireless charger - black"
                        # quantity - somewhere 1st appearance after title
                        # buyerDetails
                        # buyerid
                        # "caleb9190"
                        # "orderId"
                        # "05-10261-38305"
                        # "toShippingAddress"
                        # "street1"
                        # "209 Elmer St"
                        # "street2"
                        # "city"
                        # "Auburndale"
                        # "stateOrProvince"
                        # "FL"
                        # "fullName"
                        # "Gimberg Preval"
                        # "zipCode"
                        # "72764-7191"

                        # it is a sequential state machine, the start marker is: "creationDate" , the last marker is "zipCode"
                        if node.type == "String" and node.value == "\"creationDate\"":
                            in_order = True
                            order = ORDER("", "", "", "", "", "")
                        elif node.type == "String" and node.value == "\"displayTotalPrice\"":
                            product = OrderedProducts("", "", "", "")
                            product.setPrice(usefull[nindex + 1].value[2:-1])
                            # print("PRICE:", usefull[nindex + 1].value[2:-1])
                        elif node.type == "String" and node.value == "\"listingId\"":
                            product.setPid(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"title\"":
                            if in_order:
                                if usefull[nindex-2].value == "\"listingId\"":
                                    product.setPtitle(usefull[nindex+1].value[1:-1])
                        elif node.type == "String" and node.value == "\"quantity\"":
                            product.setQuantity(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"buyerid\"":
                            buyer = Buyer("", "", "", "", "", "")
                            buyer.setId(usefull[nindex+1].value[1:-1])
                        elif node.type == "String" and node.value == "\"toShippingAddress\"":
                            products.append(product)
                        elif node.type == "String" and node.value == "\"street1\"":
                            buyer.setStreet1(usefull[nindex+1].value[1:-1])
                        elif node.type == "String" and node.value == "\"street2\"":
                            if usefull[nindex+1] != "city":
                                buyer.setStreet2(usefull[nindex+1].value[1:-1])
                        elif node.type == "String" and node.value == "\"city\"":
                            buyer.setCity(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"stateOrProvince\"":
                            buyer.setState(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"fullName\"":
                            buyer.setFullName(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"Order number:\"":
                            order.setOid(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"zipCode\"":
                            buyer.setZip(usefull[nindex + 1].value[1:-1])
                            in_order = False

                            # buyer info collection completed, add buyer and products info to order data
                            order.setProducts(products)
                            order.setBuyer(buyer)
                            shipping = Shipping("", "", "", "", "", "", "", "")
                            order.setShipping(shipping)

                            products = []

                            # now that the order info collection is completed. added this order to the pagefull list of orders.
                            orders.append(order)

                        nindex = nindex + 1

                    # print(summery.toJson())
                    # product = OrderedProducts()
                    # order = ORDER()

                    # product.setSummery(summery)
                    # orders.append(order)

        pagefull_of_orders["ol"] = orders
        print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # print(json.dumps(pagefull_of_orders))
        print("# of orders:", len(orders))
        print([o.toJson() for o in orders])
        print("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")
    except Exception as e:
        print(f"Exception info:{e}")
        ex_stat = "ErrorEbaySellerFetchPageOfOrderList:" + str(pidx)

    return pagefull_of_orders