import json
from bs4 import BeautifulSoup
import pyautogui
import numpy as np
import re
import random
from calendar import isleap
import cv2

from slimit.parser import Parser
from slimit.visitors import nodevisitor
from slimit import ast


def ebay_seller_fetch_order_list(html_file,  orders):
    pagefull_of_orders = {"layout": "list", "index": 0, "ol": None}
    products = []

    js_parser = Parser()

    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')

        # all useful information are here:
        # extract all div tags which contains data-index attribute which is a indication of a product in the product list.
        prodItems = soup.findAll("script")
        print(len(prodItems))


        for item in prodItems:
            print("item: ", item)
            js_tree = js_parser.parse(item.text)

            for node in nodevisitor.visit(js_tree):
                if isinstance(node, ast.Identifier):
                    print(node.value)  # Outputs: i, i, i, console, log, i


            # found = re.findall("orderId.*feedbackScore", item.text)
            pattern = r'orderId.*?feedbackScore'
            found = re.findall(pattern, item.text)
            if found:
            # if "toShippingAddress" in item.text:
                print("matched....", len(found), ":::", found)

            #
            # if item.get('data-asin') != None and item.get('data-asin') != "":
            #     print(item.get('data-asin'))
            #
            #     sum_infos = item.findAll("span", attrs={"class": lambda t: t in (
            #     'a-size-medium a-color-base a-text-normal', 'a-size-base', 'a-icon-alt', 'a-size-base s-underline-text',
            #     'a-price', 'a-color-base', 'a-badge-text', 'a-offscreen')})
            #     print(sum_infos)
            #     summery = PRODUCT_SUMMERY()
            #     for sum_info in sum_infos:
            #         if sum_info.get('a-size-medium a-color-base a-text-normal') != None and sum_info.get(
            #                 'a-size-medium a-color-base a-text-normal') != "":
            #             summery.setTitle(sum_info.text)
            #         elif sum_info.get('a-size-base') != None and sum_info.get('a-size-base') != "":
            #             summery.setScore(sum_info.text)
            #         elif sum_info.get('a-size-base s-underline-text') != None and sum_info.get(
            #                 'a-size-base s-underline-text') != "":
            #             summery.setFeedbacks(convNFB(sum_info.text))
            #         elif sum_info.get('a-offscreen') != None and sum_info.get('a-offscreen') != "":
            #             summery.setPrice(convPrice(sum_info.text))
            #         elif sum_info.get('a-size-base a-color-secondary') != None and sum_info.get(
            #                 'a-size-base a-color-secondary') != "":
            #             summery.setWeekSales(convWeeklySales(sum_info.text))
            #         elif sum_info.get('a-color-base') != None and sum_info.get('a-color-base') != "":
            #             if re.search('FREE', sum_info.text):
            #                 summery.setFreeDelivery(True)
            #
            #     print(summery.toJson())
            #     product = PRODUCT()
            #     product.setSummery(summery)
            #     products.append(product.toJson())

    pagefull_of_orders["ol"] = orders
    print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print(json.dumps(pagefull_of_orders))
    print("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")
    return pagefull_of_orders