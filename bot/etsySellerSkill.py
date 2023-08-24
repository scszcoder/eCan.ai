import copy
from basicSkill import *
from scraperEtsy import *
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from datetime import datetime

SAME_ROW_THRESHOLD = 16
tracking_code = ""


# this skill simply obtain a list of name/address/phone/order amount/products of the new orders
# 1） collect new orders from website
# 2） generate bulk buy order for label purchase website goodsupply(assume an user account already exists here)
# 3） get tracking code from labels and update them back to orders website
# 4)  reformat the shipping labels and print them.
def genWinChromeEtsyFullfillOrdersSkill(worksettings, page, sect, stepN, theme):
    psk_words = "{"
    site_url = "https://www.etsy.com/your/orders/sold"

    this_step, step_words = genStepHeader("win_chrome_etsy_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEETSY001",
                                          "Etsy Fullfill New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_etsy_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepOpenApp("cmd", True, "browser", site_url, "", "", worksettings["cargs"], 5, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "etsy_status", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "etsy_orders", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "dummy_in", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    #skname, skfname, in-args, output, step number
    this_step, step_words = genStepUseSkill("collect_orders", "public/win_chrome_etsy_orders", "dummy_in", "etsy_status", this_step)
    psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.
    # first organized order list data into 2 xls for bulk label purchase, and calcualte total funding requird for this action.

    # from collected etsy orders, generate gs label purchase order files.
    dtnow = datetime.now()
    date_word = dtnow.strftime("%Y%m%d")
    fdir = worksettings["root_path"] + "/resource/runlogs/"
    fdir = fdir + date_word + "/"

    fdir = fdir + "b" + str(worksettings["mid"]) + "m" + str(worksettings["botid"]) + "/"
    fdir = fdir + worksettings["platform"] + "_" + worksettings["app"] + "_" + worksettings["site"] + "_" + page + "/skills/"
    fdir = fdir + worksettings["skname"] + "/"

    this_step, step_words = genStepPrepGSOrder("etsy_orders", "gs_orders", worksettings["seller"], fdir, this_step)
    psk_words = psk_words + step_words

    # purchase labels, gs_orders contains a list of [{"service": "usps ground", "file": xls file name}, ...]
    # etsy_oders: will have tracking code and filepath filled
    # buy_status will be "success" or "fail reason****"
    this_step, step_words = genStepUseSkill("win_chrome_goodsupply_bulk_buy", "public", ["gs_orders", "etsy_orders"], "buy_status", this_step)
    psk_words = psk_words + step_words

    # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]
    # now update tracking coded back to the orderlist
    this_step, step_words = genStepUseSkill("win_chrome_etsy_update_tracking", "public", "USPS Priority Signature v4", "total_label_cost", this_step)
    psk_words = psk_words + step_words

    # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    this_step, step_words = genStepUseSkill("win_printer_print_reformat_print", "public", "label_list", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_etsy_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinEtsyCollectOrderListSkill(worksettings, page, sect, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_etsy_collect_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEETSY001",
                                          "Etsy Collect New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_etsy_orders/collect_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "endOfOrderList", "NA", "False", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "endOfOrdersPage", "NA", "False", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nNewOrders", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nOrderPages", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "currentPage", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "pagelist", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    # Pseudo code algorithm for obtain all orderi information.
    #   read and obtain # of orders and # of pages.
    #   while all order info not full obtained:
    #       scrape currnt page htmle into data structure.
    #       read screen
    #       read order info to fill in data structure
    #       while not end of page:
    #           scroll
    #           read a screen full of data
    #           fill in data structure
    #           search end of page
    #       if end of page but not end of all order list:
    #       find next page index
    #       click on next page.


    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("endOfOrderList != True", "", "", "browseEtsyOL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global endOfOrdersPage\nendOfOrdersPage = False", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", worksettings["root_path"], "screen_info", "etsy_orders", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # extract the number of new orders on the page.
    this_step, step_words = genStepSearch("screen_info", ["n_new_orders"], ["info text"], "any", "useless", "nNewOrders", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["page_index"], ["info text"], "any", "endOfOrdersPage", "currentPage", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["n_pages"], ["info text"], "any", "useless", "nOrderPages", "etsy", this_step)
    psk_words = psk_words + step_words

    # if nNewOrders == 0:
    #   endOfOrderList = True
    # else:
    #   #scroll till end of page.
    #   search end of page anchors
    #   search order info
    #   while not end of page:
    #       scroll
    #       extract
    #       search end of page anchors
    #       search order info

    this_step, step_words = genStepCheckCondition("nNewOrders == 0", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global endOfOrderList\nendOfOrderList = True", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # else stub
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # search "etsy, inc" and page list as indicators for the bottom of the order list page.
    this_step, step_words = genStepSearch("screen_info", ["page_num_list"], ["info text"], "any", "endOfOrdersPage", "pageList", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["etsy_inc"], ["anchor text"], "any", "endOfOrdersPage", "useless", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEtsySearchOrders("screen_info", "pageOfOrders", "errorPage", this_step)
    psk_words = psk_words + step_words

    # the scroll to the bottom of the page.
    this_step, step_words = genStepLoop("endOfOrdersPage != True", "", "", "browseEtsyOL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # (action, action_args, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings["root_path"], "screen_info", "etsy_orders", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # search "etsy, inc" and page list as indicators for the bottom of the order list page.
    this_step, step_words = genStepSearch("screen_info", ["page_num_list"], ["info text"], "any", "endOfOrdersPage", "pageList", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["etsy_inc"], ["anchor text"], "any", "endOfOrdersPage", "useless", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEtsySearchOrders("screen_info", "pageOfOrders", "errorPage", this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # if currentPage == nOrderPages:
    #      endOfList == True
    # else:
    #       click on the next page
    # condition, count, end, lc_name, stepN):

    this_step, step_words = genStepCheckCondition("currentPage == nOrderPages", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global endOfOrderList\nendOfOrderList = True", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # else stub
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # update currentPage counter
    this_step, step_words = genStepCallExtern("global currentPage\ncurrentPage = currentPage + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN enter the product details page.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "pl_need_attention[att_count]['txts']['box']", "expr", "", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    # # close bracket for condition ("currentPage == nOrderPages")
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of loop for while (endOfOrderList != True)
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.
    # first organized order list data into 2 xls for bulk label purchase, and calcualte total funding requird for this action.

    # purchase labels
    this_step, step_words = genStepCreateData("expr", "label_service", "NA", "['USPS Ground Advantage Signature']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepUseSkill("win_chrome_gslabel_buy", "public", "label_service", "total_label_cost", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global label_service\nlabel_service = ['USPS Priority Signature v4']", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepUseSkill("win_chrome_gslabel_buy", "public", "label_service", "total_label_cost", this_step)
    psk_words = psk_words + step_words

    # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]
    # now update tracking coded back to the orderlist
    this_step, step_words = genStepUseSkill("win_chrome_gslabel_buy", "public", "USPS Priority Signature v4", "total_label_cost", this_step)
    psk_words = psk_words + step_words

    # now reformat and print out the shipping labels.

    this_step, step_words = genStepStub("end skill", "public/win_chrome_etsy_orders/collect_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genStepEtsySearchOrders(screen, orderDataName, errFlagName, stepN):
    stepjson = {
        "type": "Search Etsy Orders",
        "screen": screen,
        "order_data": orderDataName,
        "error_flag": errFlagName
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def processEtsySearchOrders(step, i):
    print("Searching....", step["target_types"])
    global in_exception
    scrn = symTab[step["screen"]]
    target_names = step["names"]           #contains anchor/info name, or the text string to matched against.
    target_types = step["target_types"]
    logic = step["logic"]
    fault_names = ["site_not_reached", "bad_request"]
    fault_found = []

    found = []
    n_targets_found = 0

    print("status: ", symTab[step["status"]])

    # didn't find anything, check fault situation.
    if symTab[step["status"]] == False:
        fault_found = [e for i, e in enumerate(scrn) if e["name"] in fault_names and e["type"] == "anchor text"]
        site_conn = ping(step["site"])
        if len(fault_found) > 0 or (not site_conn):
            # exception has occured, flag it.
            in_exception = True

    return i + 1



# this skill assumes tracking code ready in the orders list data structure, and update tracking code to the orders on website.
def genWinEtsyUpdateShipmentTrackingSkill(worksettings, page, sect, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_etsy_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEETSY001",
                                          "Etsy Fullfill New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_etsy_orders/update_tracking", "", this_step)
    psk_words = psk_words + step_words

    # assume the order data is in all_orders variable (tracking code already added to the data).
    # assume n_pages variable holds # of pages of the products.
    this_step, step_words = genStepCreateData("bool", "foundMark", "NA", "False", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("bool", "startOfOrdersPage", "NA", "False", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "totoalVisited", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nTrackingUpdated", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nTrackingUpdated >= 0", "", "", "allTrackCodeUpdated" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global startOfOrdersPage\nstartOfOrdersPage = False", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings["root_path"], "screen_info", "etsy_orders", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # search "etsy, inc" and page list as indicators for the bottom of the order list page.
    this_step, step_words = genStepSearch("screen_info", ["complete_order"], ["anchor icon"], "any", "complete_buttons", "useless", "etsy", this_step)
    psk_words = psk_words + step_words

    lcvarname = "ud_count" + str(stepN)
    this_step, step_words = genStepCreateData("expr", lcvarname, "NA", "len[complete_buttons]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("ud_count>0", "", "", lcvarname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "enter_tracking_number", "expr", "", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    # obtain tracking code.
    this_step, step_words = genStepCallExtern("global tracking_code\ntracking_code = etsyOrders[track_idx]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # type in the trackingcode.
    this_step, step_words = genStepTextInput("type", False, tracking_code, 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "complete_order", "expr", "", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global totoalVisited\ntotoalVisited = totoalVisited+1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # update loop counter
    this_step, step_words = genStepCallExtern("global "+lcvarname+"\n"+lcvarname+" = "+lcvarname+"+1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end of loop, updated all tracking code on the current screen.
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # if not reached page bottom, keep on scrolling down.
    this_step, step_words = genStepCheckCondition("reached_bottom == False", "", "", this_step)
    psk_words = psk_words + step_words

    # (action, action_args, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    #now we reached bottom, check to see whether there is next page to walk into.
    this_step, step_words = genStepCheckCondition("totoalVisited == nOrders", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "word", "word", "current_page_index", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_etsy_orders/update_tracking", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genWinEtsyHandleReturnSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []


def genStepPrepGSOrder(order_var_name, gs_order_var_name, seller, fpath, stepN):

    stepjson = {
        "type": "Prep GS Order",
        "ec_order": order_var_name,
        "gs_order": gs_order_var_name,
        "file_path": fpath,
        "seller": seller
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def combine_duplicates(orders):
    merged_dict = {}
    for order in orders:
        key = (order.getShippingName(), order.getShippingAddrStreet1(), order.getShippingAddrStreet2(), order.getShippingAddrCity(), order.getShippingAddrState())
        if key in merged_dict:
            merged_dict[key].products.extend(order.products)
        else:
            merged_dict[key] = copy.deepcopy(order)

    return list(merged_dict.values())

# ofname is the order file name, should be etsy_orders+Date.xls
def createLabelOrderFile(seller, weight_unit, orders, ofname):
    if weight_unit == "ozs":
        allorders = [{
            "No": "1",
            "FromName": seller["FromName"],
            "PhoneFrom": seller["PhoneFrom"],
            "Address1From": seller["Address1From"],
            "CompanyFrom": "",
            "Address2From": seller["Address2From"],
            "CityFrom": seller["CityFrom"],
            "StateFrom": seller["StateFrom"],
            "ZipCodeFrom": seller["ZipCodeFrom"],
            "NameTo": o.getRecipientName(),
            "PhoneTo": o.getRecipientPhone(),
            "Address1To": o.getRecipientAddrStreet1(),
            "CompanyTo": "",
            "Address2To": o.getRecipientAddrStreet2(),
            "CityTo": o.getRecipientAddrCity(),
            "StateTo": o.getRecipientAddrState(),
            "ZipTo": o.getRecipientAddrZip(),
            "Weight": o.getOrderWeightInOzs(),
            "length": o.getOrderLengthInInchs(),
            "width": o.getOrderWidthInInchs(),
            "height": o.getOrderHeightInInchs(),
            "description": ""
        } for o in orders]
    else:
        allorders = [{
            "No": "1",
            "FromName": seller.getName(),
            "PhoneFrom": seller.getPhone(),
            "Address1From": seller.getAddrStreet1(),
            "CompanyFrom": "",
            "Address2From": seller.getAddrStreet2(),
            "CityFrom": seller.getAddrCity(),
            "StateFrom": seller.getAddrState(),
            "ZipCodeFrom": seller.getAddrZip(),
            "NameTo": o.getRecipientName(),
            "PhoneTo": o.getRecipientPhone(),
            "Address1To": o.getRecipientAddrStreet1(),
            "CompanyTo": "",
            "Address2To": o.getRecipientAddrStreet2(),
            "CityTo": o.getRecipientAddrCity(),
            "StateTo": o.getRecipientAddrState(),
            "ZipTo": o.getRecipientAddrZip(),
            "Weight": o.getOrderWeightInLbs(),
            "length": o.getOrderLengthInInchs(),
            "width": o.getOrderWidthInInchs(),
            "height": o.getOrderHeightInInchs(),
            "description": ""
        } for o in orders]

    df = pd.DataFrame(allorders)

    # Save to .xls file
    # Create a new workbook and select the active worksheet
    wb = Workbook()
    ws = wb.active

    # Write data to worksheet
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)

    # Iterate through rows in column 2 (the 'age' column)
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        for cell in row:
            cell.number_format = '@'  # text format

    # Save workbook
    wb.save(ofname)


# ec_order data structure can be refered to scraperEtsy.py file.
# basically list of pages of orders: each
def processPrepGSOrder(step, i):
    next_i = i + 1
    gs_label_orders = []

    seller = step["seller"]
    new_orders = symTab[step["ec_order"]]
    # collaps all pages of order list into a single list or orders.
    flatlist=[element for sublist in new_orders for element in sublist]

    # combine orders into same person and address into 1 order.
    combined = combine_duplicates(flatlist)

    # filter out Non-USA orders. International Orders such as canadian and mexican should be treatly separately at this time.
    us_orders = [o for o in combined if o.getShippingAddrState() != "Canada" and o.getShippingAddrState() != "Mexico"]

    # group orders into two categories: weights less than 1lb and weights more than 1lb
    light_orders = [o for o in us_orders if o.getShippingWeightsInLbs() < 1.0 ]
    regular_orders = [o for o in us_orders if o.getShippingWeightsInLbs() >= 1.0]

    # ofname is the order file name, should be etsy_orders+Date.xls
    if len(light_orders) > 0:
        dtnow = datetime.now()
        dt_string = str(int(dtnow.timestamp()))
        ofname1 = step["file_path"]+"/etsyOrdersGround"+dt_string+".xls"
        createLabelOrderFile(seller, "ozs", light_orders, ofname1)
        gs_label_orders.append({"service":"USPS Ground Advantage (1-15oz)", "file": ofname1})

    if len(regular_orders) > 0:
        dtnow = datetime.now()
        dt_string = str(int(dtnow.timestamp()))
        ofname2 = step["file_path"]+"/etsyOrdersPriority"+dt_string+".xls"
        createLabelOrderFile(seller, "lbs", regular_orders, ofname2)

        gs_label_orders.append({"service":"USPS Priority V4", "file": ofname2})

    symTab[step["gs_order"]] = gs_label_orders

    return next_i