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
# outvar should be the variable that holds valued of how many labels tracking code are updated during this scrape ....
# since the labels are generated sequentially, any name not
def genStepScrapeGoodSupplyLabels(html, pidxvar, ordersvar, outvar, statusvar, stepN):
    stepjson = {
        "type": "GS Scrape Labels",
        "pidx": pidxvar,
        "allOrders": ordersvar,
        "html_file": html,
        "result": outvar,
        "status": statusvar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# get recipient name and tracking code list.
def processScrapeGoodSupplyLabels(step, i):
    next_i = i + 1
    html_file = step["html_file"]
    orders = symTab[step["allOrders"]]

    # for o in orders:
    #     print("order's name:", "["+o.getRecipientName()+"]")

    symTab[step["result"]] = True

    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')

        # extract number of pages info
        # <table id="datatable" class="dataTable table mb-0 position-relative cta-sticky table-mylabel">
        tableItems = soup.findAll("table", attrs={"class": "dataTable table mb-0 position-relative cta-sticky table-mylabel"})

        # < nav aria-label = "Page navigation " >
        pageNavItems = soup.findAll("nav", attrs={"aria-label": "Page navigation "})
        if len(pageNavItems) > 0:
            currents = pageNavItems[0].findAll("li", attrs={"class": "active"})
            if len(currents) > 0:
                actives = currents[0].findAll("a", attrs={"class": None})
                current_page_idx = actives[0].text
            else:
                # this means nothing is shown on the page.....
                current_page_idx = "0"

            others = pageNavItems[0].findAll("li", attrs={"class": None})
            if len(others) > 0:
                lastas = others[len(others)-1].findAll("a", attrs={"class": None})
                last_page_idx = lastas[0].text
            else:
                last_page_idx = "0"

            if int(last_page_idx) > int(current_page_idx):
                last_page = last_page_idx
            else:
                last_page = current_page_idx

            if last_page == current_page_idx:
                symTab[step["pidx"]] = "0"
            else:
                symTab[step["pidx"]] = str(int(current_page_idx) + 1)
        else:
            symTab[step["pidx"]] = "0"

        # print("page index:", symTab[step["pidx"]], "last page:", last_page, "current page idx:", current_page_idx)

        option_tags = []
        if len(tableItems) > 0:
            print("found table items.", len(tableItems))
            table = tableItems[0]           # there should be only 1 table anyways.
            rows = table.findAll("tr", attrs={"class": None})
            print("found table rows.", len(rows))
            symTab[step["result"]] = 0
            for row in rows:
                cols = row.findAll("td", attrs={"class": None})
                coltxts = [col.text for col in cols]

                recipient_name = coltxts[4]
                shipping_service = coltxts[2]
                tracking_code = coltxts[5]

                # print("row name, tc:", "["+recipient_name+"]", shipping_service, tracking_code)

                # SC 09/14/2023, maybe for sanity check, should confirm the services matches, but this shouldn't be a problem.
                # also this could be problem if a person places multiple orders, but this special situation should have been
                # taken care of during the order combining stage when collecting all orders.
                found_idx = next((idx for idx, x in enumerate(orders) if recipient_name == x.getRecipientName()), -1)
                # print("found name index:", found_idx)
                if found_idx >= 0:
                    if orders[found_idx].getShippingTracking() == "":
                        # update only if the tracking code is not yet available....
                        orders[found_idx].setShippingTracking(tracking_code)
                        orders[found_idx].setStatus("label generated")
                        symTab[step["result"]] = symTab[step["result"]] + 1
                        print("found name:", recipient_name, "tracking code tb updated:", tracking_code)
                else:
                    print("name not found:", recipient_name)
                    break

                if symTab[step["result"]] > 0:
                    symTab[step["status"]] = True
                else:
                    symTab[step["status"]] = False
    return next_i

# the purpose to scrape this page is to check whether the download button is available to download the zips
def processScrapeGoodSupplyZips(step, i):
    html_file = step["html_file"]
    with open(html_file, 'rb') as fp:
        soup = BeautifulSoup(fp, 'html.parser')

        # <table class="table mb-0 position-relative cta-sticky">
        tableItems = soup.findAll("table", attrs={"class": "table mb-0 position-relative cta-sticky"})
        option_tags = []
        if len(tableItems) > 0:
            print("found table items.")
            table = tableItems[0]  # there should be only 1 table anyways.
            tbodyItems = table.findAll("tbody", attrs={"class": None})

            if len(tbodyItems) > 0:
                tbody = tbodyItems[0]

                rows = tbody.findAll("tr", attrs={"class": None})
                for row in rows:
                    cols = row.findAll("td", attrs={"class": None})
                    coltxts = [col.text for col in cols]

                    zip_file_name = coltxts[0]
                    prefix = zip_file_name.split("_")[0]

                    # now if download button is available, then find prefix in gs_orders data structure

