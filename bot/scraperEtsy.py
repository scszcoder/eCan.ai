import json
from bs4 import BeautifulSoup
import pyautogui
import numpy as np
import re
import random
from calendar import isleap
import cv2


def etsy_seller_fetch_order_list(html_file,  orders):

    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')

        # all useful information are here:
        # extract all div tags which contains data-index attribute which is a indication of a product in the product list.
        prodItems = soup.findAll("div", attrs={"data-index": True})
        print(len(prodItems))
        # ageuseful = soup.findAll('span', {"class": 'content-value'})
        # agewords = ageuseful[0].text.split(' ')
        # usr.birth_year = int(agewords[3][0:4])
        # usr.birth_month = get_birth_month(agewords[2][1:4])
        # days = get_month_days(usr.birth_year, usr.birth_month)
        # usr.birth_day = random.randrange(1, days+1)

        # print(agewords[0][1:4])     # ’age'
        # print(agewords[1])          # age in number
        # print(agewords[2][1:4])     # birth month
        # print(agewords[3][0:4])     # birth year

        for item in prodItems:
            if item.get('data-asin') != None and item.get('data-asin') != "":
                print(item.get('data-asin'))

                sum_infos = item.findAll("span", attrs={"class": lambda t: t in (
                    'a-size-medium a-color-base a-text-normal', 'a-size-base', 'a-icon-alt',
                    'a-size-base s-underline-text',
                    'a-price', 'a-color-base', 'a-badge-text', 'a-offscreen')})
                print(sum_infos)
                summery = PRODUCT_SUMMERY()
                for sum_info in sum_infos:
                    if sum_info.get('a-size-medium a-color-base a-text-normal') != None and sum_info.get(
                            'a-size-medium a-color-base a-text-normal') != "":
                        summery.setTitle(sum_info.text)
                    elif sum_info.get('a-size-base') != None and sum_info.get('a-size-base') != "":
                        summery.setScore(sum_info.text)
                    elif sum_info.get('a-size-base s-underline-text') != None and sum_info.get(
                            'a-size-base s-underline-text') != "":
                        summery.setFeedbacks(convNFB(sum_info.text))
                    elif sum_info.get('a-offscreen') != None and sum_info.get('a-offscreen') != "":
                        summery.setPrice(convPrice(sum_info.text))
                    elif sum_info.get('a-size-base a-color-secondary') != None and sum_info.get(
                            'a-size-base a-color-secondary') != "":
                        summery.setWeekSales(convWeeklySales(sum_info.text))
                    elif sum_info.get('a-color-base') != None and sum_info.get('a-color-base') != "":
                        if re.search('FREE', sum_info.text):
                            summery.setFreeDelivery(True)

                print(summery.toJson())
                product = PRODUCT()
                product.setSummery(summery)
                products.append(product.toJson())

    if len(products) < 54:
        pagefull_of_pl["layout"] = "list"
    pagefull_of_pl["pl"] = products
    print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print(json.dumps(pagefull_of_pl))
    print("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")
    return pagefull_of_pl