from basicSkill import *
from scraperEtsy import *
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from datetime import datetime
from envi import *
from config.app_info import app_info
from Logger import *


SAME_ROW_THRESHOLD = 16
tracking_code = ""

ecb_data_homepath = getECBotDataHome()
# this skill simply obtain a list of name/address/phone/order amount/products of the new orders
# 1） collect new orders from website
# 2） generate bulk buy order for label purchase website goodsupply(assume an user account already exists here)
# 3） get tracking code from labels and update them back to orders website
# 4)  reformat the shipping labels and print them.
def genWinChromeEtsyFullfillOrdersSkill(worksettings, stepN, theme):
    psk_words = "{"
    site_url = "https://www.etsy.com/your/orders/sold"

    this_step, step_words = genStepHeader("win_chrome_etsy_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEETSY001",
                                          "Etsy Fullfill New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_chrome_etsy_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(5, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "etsy_status", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "product_book", "NA", "sk_work_settings['products']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global product_book\nprint('product_book:', product_book[0])", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # mask out for testing purpose only....
    # this_step, step_words = genStepCreateData("expr", "etsy_orders", "NA", "[]", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "dummy_in", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_resolution", "NA", 253, this_step)
    psk_words = psk_words + step_words

     # hard default exe path code here just for testing purpose, eventually will be from input or settings....
    this_step, step_words = genStepCreateData("str", "sevenZExe", "NA", 'C:/Program Files/7-Zip/7z.exe', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("str", "rarExe", "NA", 'C:/Program Files/WinRaR/WinRaR.exe', this_step)
    psk_words = psk_words + step_words


    #skname, skfname, in-args, output, step number
    # this_step, step_words = genStepUseSkill("collect_orders", "public/win_chrome_etsy_orders", "dummy_in", "etsy_status", this_step)
    # psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.
    # first organized order list data into 2 xls for bulk label purchase, and calcualte total funding requird for this action.

    # from collected etsy orders, generate gs label purchase order files.
    dtnow = datetime.now()
    date_word = dtnow.strftime("%Y%m%d")
    fdir = ecb_data_homepath + "/runlogs/"
    fdir = fdir + date_word + "/"
    this_step, step_words = genStepCreateData("str", "fdir", "NA", fdir, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("fdir = fdir + 'b' + str(sk_work_settings['mid']) + m + str(sk_work_settings['bid']) + '/'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("fdir = fdir + sk_work_settings['platform'] + '_' + sk_work_settings['app'] + '_' + sk_work_settings['site'] + '_' + sk_work_settings['page'] + '/skills/'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("fdir = fdir + sk_work_settings['skname'] + '/'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "current_seller", "NA", "sk_work_settings['seller']", this_step)
    psk_words = psk_words + step_words

    # this is an app specific step.
    # this_step, step_words = genStepPrepGSOrder("etsy_orders", "gs_orders", "product_book", "current_seller", "fdir", this_step)
    # psk_words = psk_words + step_words

    homepath = app_info.app_home_path
    if homepath[len(homepath)-1] == "/":
        homepath = homepath[:len(homepath)-1]
    this_step, step_words = genStepCallExtern("global gs_orders\ngs_orders = [{'service': 'USPS Priority V4', 'price': 4.5, 'num_orders': 1, 'dir': '" + homepath + "/runlogs/20230910/b3m3/win_chrome_etsy_orders/skills/fullfill_orders', 'file': 'etsyOrdersPriority092320230919.xls'}]\nprint('GS ORDERS', gs_orders)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gs_input\ngs_input = [etsy_orders, gs_orders, sevenZExe, rarExe]\nprint('GS input', gs_input)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # purchase labels, gs_orders contains a list of [{"service": "usps ground", "file": xls file name}, ...]
    # etsy_oders: will have tracking code and filepath filled
    # buy_status will be "success" or "fail reason****"
    # at the end of this skill, the shipping service and the tracking code section of "etsy_orders" should be updated.....
    # this_step, step_words = genStepUseSkill("bulk_buy", "public/win_chrome_goodsupply_label", "gs_input", "labels_dir", this_step)
    # psk_words = psk_words + step_words

    #extract tracking code from labels and update them into etsy_orders data struture.

    gen_etsy_test_data()

    # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]
    # now update tracking coded back to the orderlist
    this_step, step_words = genStepUseSkill("update_tracking", "public/win_chrome_etsy_orders", "gs_input", "total_label_cost", this_step)
    psk_words = psk_words + step_words

    # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    this_step, step_words = genStepUseSkill("reformat_print", "public/win_printer_local_print", "label_list", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_etsy_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinChromeEtsyCollectOrderListSkill(worksettings, stepN, theme):
    psk_words = "{"
    site_url = "https://www.etsy.com/your/orders/sold"

    this_step, step_words = genStepHeader("win_chrome_etsy_collect_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEETSY001",
                                          "Etsy Collect New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_etsy_orders/collect_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepOpenApp("cmd", True, "browser", site_url, "", "", "expr", "sk_work_settings['cargs']", 5, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "currentPage", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "pageOfOrders", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "fileStatus", "NA", "None", this_step)
    psk_words = psk_words + step_words

    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))
    hfname = "etsyOrders" + dt_string + ".html"

    log3("SAVE HTML FILE: "+hfname)

    # this_step, step_words = genStepCreateDir("sk_work_settings['log_path']", "expr", "fileStatus", this_step)
    # psk_words = psk_words + step_words
    #

    this_step, step_words = genStepCallExtern("global pageOfOrders\nprint('PAGE OF ORDERS:', pageOfOrders)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "endOfOrderList", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "endOfOrdersPage", "NA", False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("expr", "shipToSummeries", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "shipTos", "NA", "[]", this_step)
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


    # loop thru every "Ship to" on the page and click on it to show the full address. and record accumulatively #of "Ship to" being clicked.
    this_step, step_words = genStepLoop("endOfOrdersPage != True", "", "", "browseEtsyOrderPage" + str(this_step), this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "orders", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # use this info, as it contains the name and address, as well as the ship_to anchor location.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["ship_to_summery"], "direct", ["info 2"], "any", "shipToSummeries", "useless", "etsy", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["ship_to"], "direct", ["anchor text"], "any", "shipTos", "useless", "etsy", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "numShipTos", "NA", "len(shipTos)-1", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEtsyRemoveAlreadyExpanded("shipTos", "shipToSummeries", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global shipTos\nprint('SHIP TOS:', shipTos)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # otherwise, try to go thru the orders....
    this_step, step_words = genStepCreateData("expr", "nthShipTo", "NA", "len(shipTos)-1", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "lastShipTo", "NA", "numShipTos - nthShipTo", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nthShipTo\nnthShipTo = numShipTos", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # loop thru every "Ship to" on the page and click on it to show the full address. and record accumulatively #of "Ship to" being clicked.
    this_step, step_words = genStepLoop("nthShipTo >= lastShipTo", "", "", "dummy" + str(stepN), this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "ship_to", "anchor text", "", "nthShipTo", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nthShipTo\nnthShipTo = nthShipTo - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # end loop for going thru all shiptos on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # SC - 2023-09-05 alternatively could finishing clicking all ship to on the html page, and re-scrape html again to
    # fill the detailed address. the benefit here is, no need to extract again which is expensive and time consuming...

    # don't get bottom page position until there is nothing to click, otherwise, the end of page will move.
    this_step, step_words = genStepCheckCondition("len(shipTos) == 0", "", "", this_step)
    psk_words = psk_words + step_words

    # check end of page information again
    # search "etsy, inc" and page list as indicators for the bottom of the order list page.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["etsy_inc"], "direct", ["anchor text"], "any", "endOfOrdersPage", "endOfOrdersPage", "etsy", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # now scroll to the next screen.
    # (action, action_args, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words


    #  end of loop for scoll till the endOfOrdersPage.
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    ##############################################################################################
    # at the end of the page, save html, now with detailed address info shown... and scrape html to
    # get all order information including the detailed address...
    ##############################################################################################

    this_step, step_words = genStepCreateDir("sk_work_settings['log_path']", "expr", "fileStatus", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "ctrl,s", "", 4, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("str", "profile_name", "NA", hfname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("str", "profile_name", "NA", hfname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "file_save_input", "NA", "['save', sk_work_settings['log_path'], hf_name]", this_step)
    psk_words = psk_words + step_words

    # save the html file.
    this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_save_input", "fileStatus", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(18, 0, 0, this_step)
    psk_words = psk_words + step_words

    homepath = ecb_data_homepath # os.environ.get("ECBOT_HOME")
    if homepath[len(homepath)-1]=="/":
        homepath = homepath[:len(homepath)-1]
    # html, pidx, outvar, statusvar, stepN):
    # hfile = homepath+'runlogs/20230825/b3m3/win_chrome_etsy_orders/skills/collect_orders/etsyOrders1692998813.html'
    # this_step, step_words = genStepEtsyScrapeOrders(hfile, "currentPage", "pageOfOrders",  "", this_step)
    # hfile = homepath+"runlogs/20230904/b3m3/win_chrome_etsy_orders/skills/collect_orders/etsyOrders1693857164.html"

    this_step, step_words = genStepEtsyScrapeOrders("sk_work_settings['log_path']", "expr", hfname, "currentPage", "pageOfOrders", "", this_step)
    # this_step, step_words = genStepEtsyScrapeOrders(hfile, "pageOfOrders", "fileStatus", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepEtsyAddPageOfOrder("etsy_orders", "pageOfOrders", this_step)
    # this_step, step_words = genStepEtsyScrapeOrders(hfile, "pageOfOrders", "fileStatus", "", this_step)
    psk_words = psk_words + step_words

    #########################end of re-scrape html to obtain recipient address details. ######################
    # now check to see whether there are more pages to visit. i.e. number of orders exceeds more than 1 page.
    # the number of pages and page index variable are already in the pageOfOrders variable.


    this_step, step_words = genStepCheckCondition("pageOfOrders['num_pages'] == pageOfOrders['page']", "", "", this_step)
    psk_words = psk_words + step_words

    # set the flag, we have completed collecting all orders information at this point.
    this_step, step_words = genStepCallExtern("global endOfOrderList\nendOfOrderList = True", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # else stub
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # go to the next page.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "next_page", "anchor icon", "", [0, 0], "center", [0, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    # # close bracket for condition (pageOfOrders['num_pages'] == pageOfOrders['page'])
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of loop for while (endOfOrderList !    this_step, step_words = genStepStub("end loop", "", "", this_step)= True)
    psk_words = psk_words + step_words


    # now all order collection is complete.

    this_step, step_words = genStepStub("end skill", "public/win_chrome_etsy_orders/collect_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words

def genWinADSEtsyBuyShippingSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_etsy_handle_messages", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSETSY002",
                                          "Etsy Buy Shipping and Update Tracking On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_etsy_orders/buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_etsy_orders/buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads etsy handle messages...." + psk_words)

    return this_step, psk_words


def genWinChromeEtsyBuyShippingSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_etsy_handle_messages", "win", "1.0", "AIPPS LLC",
                                          "PUBWINCHROMEETSY002",
                                          "Etsy Buy Shipping and Update Tracking On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_etsy_orders/buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_etsy_orders/buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome etsy handle messages...." + psk_words)

    return this_step, psk_words

def genWinADSEtsyHandleMessagesSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_etsy_handle_messages", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSETSY002",
                                          "Etsy Handle Messages On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_etsy_orders/handle_messages", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_etsy_orders/handle_messages", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads etsy handle messages...." + psk_words)

    return this_step, psk_words


def genWinChromeEtsyHandleMessagesSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_etsy_handle_messages", "win", "1.0", "AIPPS LLC",
                                          "PUBWINCHROMEETSY002",
                                          "Etsy Handle Messages On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_etsy_orders/handle_messages", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_etsy_orders/handle_messages", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome etsy handle messages...." + psk_words)

    return this_step, psk_words

def genStepEtsySearchOrders(screen, orderDataName, errFlagName, stepN):
    stepjson = {
        "type": "Search Etsy Orders",
        "screen": screen,
        "order_data": orderDataName,
        "error_flag": errFlagName
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# check whether there are orders
def processEtsySearchOrders(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Searching...."+step["target_types"])
        global in_exception
        scrn = symTab[step["screen"]]
        target_names = step["names"]           #contains anchor/info name, or the text string to matched against.
        target_types = step["target_types"]
        logic = step["logic"]
        fault_names = ["site_not_reached", "bad_request"]
        fault_found = []

        found = []
        n_targets_found = 0

        log3("status: "+symTab[step["status"]])

        # didn't find anything, check fault situation.
        if symTab[step["status"]] == False:
            fault_found = [e for i, e in enumerate(scrn) if e["name"] in fault_names and e["type"] == "anchor text"]
            site_conn = ping(step["site"])
            if len(fault_found) > 0 or (not site_conn):
                # exception has occured, flag it.
                in_exception = True
    except:
        ex_stat = "ErrorPrepGSOrder:" + str(i)

    return (i + 1), ex_stat



# this skill assumes tracking code ready in the orders list data structure, and update tracking code to the orders on website.
# all the tracking code should already be updated into etsy_orders data structure which is the sole input parameter.....
def genWinChromeEtsyUpdateShipmentTrackingSkill(worksettings, stepN, theme):
    psk_words = "{"
    site_url = "https://www.etsy.com/your/orders/sold"


    this_step, step_words = genStepHeader("win_chrome_etsy_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEETSY001",
                                          "Etsy Fullfill New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_etsy_orders/update_tracking", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    # open the order page again.
    this_step, step_words = genStepOpenApp("cmd", True, "browser", site_url, "", "", "expr", "sk_work_settings['cargs']", 5, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(5, 0, 0, this_step)
    psk_words = psk_words + step_words

    # go thru all orders, page by page, screen by screen. same nested loop as in collect orders...
    this_step, step_words = genStepCallExtern("global endOfOrderList\nendOfOrderList = False", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global currentPage\ncurrentPage = 0", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "update_order_index", "NA", -1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nMore2Update", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "orderIds", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "numCompletions", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthCompletion", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("endOfOrderList != True", "", "", "browseEtsyOL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global endOfOrdersPage\nendOfOrdersPage = False", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # loop thru every "Ship to" on the page and click on it to show the full address. and record accumulatively #of "Ship to" being clicked.
    this_step, step_words = genStepLoop("endOfOrdersPage != True", "", "", "browseEtsyOrderPage" + str(this_step), this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "orders", "completion", theme, this_step, None)
    psk_words = psk_words + step_words

    # use this info, as it contains the name and address, as well as the ship_to anchor location.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["complete_order"], "direct", ["anchor icon"], "any", "complete_buttons", "useless", "etsy", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["order_number"], "direct", ["info 1"], "any", "orderIds", "useless", "etsy", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global numCompletions\nnumCompletions = len(orderIds)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nthCompletion\nnthCompletion = 0", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # loop thru every "Ship to" on the page and click on it to show the full address. and record accumulatively #of "Ship to" being clicked.
    this_step, step_words = genStepLoop("nthCompletion < numCompletions", "", "", "dummy" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # use nth ship to to find its related ship-to-summery, use name, city, state in that summery to find this order's click status.
    # this_step, step_words = genStepEtsyGetOrderClickedStatus("shipTos", "nthShipTo", "pageOfOrders", "found_index", "nthChecked", this_step)
    # psk_words = psk_words + step_words

    # first, nthcompleteion related order number， then search this order number from the order data structure,
    # if found and its status is wait for completion, then return the order index number.
    # if the index number is invalid, then skip this item.

    this_step, step_words = genStepEtsyFindScreenOrder("nthCompletion", "complete_buttons", "orderIds", "etsy_orders", "update_order_index", "nMore2Update", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global update_order_index\nprint('update_order_index', update_order_index)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global fin\nprint('fin', fin)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("update_order_index >= 0", "", "", this_step)
    psk_words = psk_words + step_words


    # click on the complete order button
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "complete_order", "anchor icon", "", "nthCompletion", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "orders", "completion", theme, this_step, None)
    psk_words = psk_words + step_words

    # click and type USPS in carrier pull down menu
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "shipping_carrier", "anchor text", "", [0, 0], "bottom", [0, 2], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global shipping_service\nshipping_service = fin[0][update_order_index].getShippingService()[:3]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepTextInput("var", False, "shipping_service", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    # click and type in the tracking code.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "enter_tracking", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global track_code\ntrack_code = fin[0][update_order_index].getShippingTracking()", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "track_code", "direct", 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    # click the complete order button
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "complete_order_button", "anchor text", "", "nthCompletion", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words


    # end condition for checking whehter this order can to be completed.
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # now 1 order update is finished. update the counter
    this_step, step_words = genStepCallExtern("global nthCompletion\nnthCompletion = nthCompletion + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words



    # check end of page information again
    # search "etsy, inc" and page list as indicators for the bottom of the order list page.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["etsy_inc"], "direct", ["anchor text"], "any", "endOfOrdersPage", "endOfOrdersPage", "etsy", False, this_step)
    psk_words = psk_words + step_words

    # now scroll to the next screen.
    # (action, action_args, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 60, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(2, 0, 0, this_step)
    psk_words = psk_words + step_words


    #  end of loop for scoll till the endOfOrdersPage.
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    # now check to see whether there are more pages to visit. basically we have updated all possible tracking code
    # 1) no more order # found on current page.
    # 2) the last found order # on this page is not found in the purchased label order# list. - search returns 0 found.
    #    and there is no more orders to update (go to the order list and see whether there is more orders with tracking
    #    code ready but not yet updated....
    this_step, step_words = genStepCheckCondition("nMore2Update <= 0", "", "", this_step)
    psk_words = psk_words + step_words

    # set the flag, we have completed collecting all orders information at this point.
    this_step, step_words = genStepCallExtern("global endOfOrderList\nendOfOrderList = True", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # else stub
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # after updating tracking code for the page, reload the page, at this time, the ones updated will be gone,
    # the next batch will appear on the page.
    this_step, step_words = genStepKeyInput("", True, "f5", "", 4, this_step)
    psk_words = psk_words + step_words

    # # close bracket for condition (pageOfOrders['num_pages'] == pageOfOrders['page'])
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of loop for while (endOfOrderList != True)
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_chrome_etsy_orders/update_tracking", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genWinEtsyHandleReturnSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []


def genStepPrepGSOrder(order_var_name, gs_order_var_name, prod_book_var_name, seller, fpath, stepN):

    stepjson = {
        "type": "Prep GS Order",
        "ec_order": order_var_name,
        "gs_order": gs_order_var_name,
        "prod_book": prod_book_var_name,
        "file_path": fpath,
        "seller": seller
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def combine_duplicates(orders):
    merged_dict = {}
    for order in orders:
        key = (order.getRecipientName(), order.getRecipientAddrStreet1(), order.getRecipientAddrStreet2(), order.getRecipientAddrCity(), order.getRecipientAddrState())
        if key in merged_dict:
            merged_dict[key].products.extend(order.products)
        else:
            merged_dict[key] = copy.deepcopy(order)

    return list(merged_dict.values())

# ofname is the order file name, should be etsy_orders+Date.xls
def createLabelOrderFile(seller, weight_unit, orders, book, ofname):
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
            "Weight": o.getOrderWeightInOzs(book),
            "length": o.getOrderLengthInInches(book),
            "width": o.getOrderWidthInInches(book),
            "height": o.getOrderHeightInInches(book),
            "description": ""
        } for o in orders]
    else:
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
            "Weight": o.getOrderWeightInLbs(book),
            "length": o.getOrderLengthInInches(book),
            "width": o.getOrderWidthInInches(book),
            "height": o.getOrderHeightInInches(book),
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

    log3("saving to file: "+ofname)
    ofdir = os.path.dirname(ofname)
    if not os.path.exists(ofdir):
        os.makedirs(ofdir)
    # Save workbook
    wb.save(ofname)

# if 1 product is not FBS, then the whole order is FBS... requires manual work.....
def order_is_for_fbs(order, pbook):
    fbs = True
    for op in order.getProducts():
        prod = next((p for i, p in enumerate(pbook[0]["products"]) if p["title"] == op.getPTitle()), None)
        if prod:
            if prod["fullfiller"] != "self":
                fbs = False
                break
    return fbs



# ec_order data structure can be refered to scraperEtsy.py file.
# basically list of pages of orders: each
def processPrepGSOrder(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        gs_label_orders = []

        seller = symTab[step["seller"]]
        file_path = symTab[step["file_path"]]
        new_orders = symTab[step["ec_order"]]
        # collaps all pages of order list into a single list or orders.
        flatlist=[element for sublist in new_orders for element in sublist["ol"]]

        log3("FLAT LIST: "+json.dumps(flatlist))

        # combine orders into same person and address into 1 order.
        combined = combine_duplicates(flatlist)

        # filter out Non-USA orders. International Orders such as canadian and mexican should be treatly separately at this time.
        us_orders = [o for o in combined if o.getRecipientAddrState() != "Canada" and o.getRecipientAddrState() != "Mexico"]

        # don't put in the order that's not going to be fullfilled by the seller him/her self.
        fbs_orders = [o for o in us_orders if order_is_for_fbs(o, symTab[step["prod_book"]])]

        # group orders into two categories: weights less than 1lb and weights more than 1lb
        light_orders = [o for o in fbs_orders if o.getOrderWeightInLbs(symTab[step["prod_book"]]) < 1.0 ]
        regular_orders = [o for o in fbs_orders if o.getOrderWeightInLbs(symTab[step["prod_book"]]) >= 1.0]

        # ofname is the order file name, should be etsy_orders+Date.xls
        dt_string = datetime.now().strftime('%Y%m%d%H%M%S')

        if len(light_orders) > 0:
            ofname1 = file_path+"/etsyOrdersGround"+dt_string+".xls"
            ofname1_unzipped = file_path + "/etsyOrdersGround" + dt_string
            createLabelOrderFile(seller, "ozs", light_orders, symTab[step["prod_book"]], ofname1)
            gs_label_orders.append({"service":"USPS Ground Advantage (1-15oz)", "price": len(light_orders)*2.5, "num_orders": len(light_orders), "dir": os.path.dirname(ofname1), "file": os.path.basename(ofname1), "unzipped_dir": ofname1_unzipped})

            #create unziped label dir ahead of time.
            if not os.path.exists(ofname1_unzipped):
                os.makedirs(ofname1_unzipped)

        if len(regular_orders) > 0:
            ofname2 = file_path+"/etsyOrdersPriority"+dt_string+".xls"
            ofname2_unzipped =  file_path+"/etsyOrdersPriority"+dt_string

            createLabelOrderFile(seller, "lbs", regular_orders, symTab[step["prod_book"]], ofname2)
            gs_label_orders.append({"service":"USPS Priority V4", "price": len(regular_orders)*4.5, "num_orders": len(regular_orders), "dir": os.path.dirname(ofname2),  "file": os.path.basename(ofname2), "unzipped_dir": ofname2_unzipped})

            #create unziped label dir ahead of time.
            if not os.path.exists(ofname2_unzipped):
                os.makedirs(ofname2_unzipped)

        symTab[step["gs_order"]] = gs_label_orders

    except:
        ex_stat = "ErrorPrepGSOrder:" + str(i)

    return next_i, ex_stat




def genStepEtsyGetOrderClickedStatus(shipToVar, shipToIndexVar, ordersVar, foundOrderIndexVar, foundOrderClickedVar, stepN):
    stepjson = {
        "type": "Etsy Get Order Clicked Status",
        "shipTo": shipToVar,
        "shipToIndex": shipToIndexVar,
        "orders": ordersVar,
        "foundOrderIndex": foundOrderIndexVar,
        "foundOrderClicked": foundOrderClickedVar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepEtsySetOrderClickedStatus(ordersVar, foundOrderIndexVar, stepN):
    stepjson = {
        "type": "Etsy Set Order Clicked Status",
        "orders": ordersVar,
        "foundOrderIndex": foundOrderIndexVar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# given ShipTos and ShipToSummeries, remove the ShipTos that're already expanded.
# The way to determine whether it's expanded is to check # of lines below, and
# whether the city, state line contains the zip code.
# alternative, whether contains 2 lines below ship to, or 2 lines between "ship to" to any line contains "gift/Gift"
# Note Canada as special condition
def genStepEtsyRemoveAlreadyExpanded(shipToVar, shipToSummeryVar, stepN):
    stepjson = {
        "type": "Etsy Remove Expanded",
        "shipTos": shipToVar,
        "shipToSummeries": shipToSummeryVar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# add a page of orders to the total order list
def genStepEtsyAddPageOfOrder(fullOrdersVar, pageOfOrdersVar, stepN):
    stepjson = {
        "type": "Etsy Add Page Of Order",
        "fullOrders": fullOrdersVar,
        "pageOfOrders": pageOfOrdersVar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepEtsyExtractTracking(labels_dir_var, orders_var, stepN):
    stepjson = {
        "type": "Etsy Extract Tracking",
        "gs_orders": labels_dir_var,
        "fullOrders": orders_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepEtsyFindScreenOrder(nth_var, complete_buttons_var, order_ids_var, orders_var, found_index_var, n_more_var, stepN):
    stepjson = {
        "type": "Etsy Find Screen Order",
        "nth_var": nth_var,
        "orders_var": orders_var,
        "complete_buttons_var": complete_buttons_var,
        "order_ids_var": order_ids_var,
        "found_index_var": found_index_var,
        "n_more_var" : n_more_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def match_name(img_name, txt_name):
    matched = True

    img_name_words = img_name.split()
    for w in img_name_words:
        if w.strip() not in txt_name:
            matched = False
            break

    return matched

def processEtsyGetOrderClickedStatus(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Get Order Clicked Status .....")
        # first extract name, city, state from the text information
        txt_blocs = symTab[step["shipTo"]][symTab[step["shipToIndex"]]]["text"].split("\n")

        fullname = txt_blocs[0].strip()
        city_state = txt_blocs[1].strip().split(",")
        city = city_state[0].strip()
        state = city_state[1].strip()

        # then find a match of name, city, state from the orders data.
        symTab[step["foundOrderIndex"]] = next((idx for idx, x in enumerate(symTab[step["orders"]]) if match_name(fullname, x.getRecipientName()) and x.getRecipientCity() == city and x.getRecipientState() == state), -1)

        symTab[step["foundOrderClicked"]] = symTab[step["orders"]][symTab[step["foundOrderIndex"]]].getChecked()

    except:
        ex_stat = "ErrorEtsyGetOrderClickedStatus:" + str(i)

    return (i + 1), ex_stat

def processEtsySetOrderClickedStatus(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Opening App ....."+step["target_link"] + " " + step["cargs"])
        symTab[step["orders"]][symTab[step["foundOrderIndex"]]].setChecked(True)

    except:
        ex_stat = "ErrorEtsySetOrderClickedStatus:" + str(i)

    return (i + 1), ex_stat

def contains_states(line):
    us_addr_pattern = re.compile("[a-zA-Z ]+\, *[a-zA-Z][a-zA-Z] *$")
    ca_addr_pattern = re.compile("[a-zA-Z ]+\, *Canada *$")

    us_matched = us_addr_pattern.search(line)
    ca_matched = ca_addr_pattern.search(line)
    if us_matched or ca_matched:
        return True
    else:
        return False

def processEtsyRemoveAlreadyExpanded(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Remove expanded state .....")
        # first extract name, city, state from the text information
        # then find a match of name, city, state from the orders data.

        # log3("SUMMERY:", symTab[step["shipToSummeries"]])
        # log3("{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}{}")
        # log3("SHIP TO:", symTab[step["shipTos"]])

        for summery in symTab[step["shipToSummeries"]]:
            summery_lines = summery["text"].split("\n")
            # log3("summery lines:", summery_lines)
            state_line_number = next((idx for idx, l in enumerate(summery_lines) if contains_states(l)), -1)
            # log3("summery line number:", state_line_number)
            if state_line_number == -1:
                symTab[step["shipTos"]].pop(0)
            else:
                break

        # log3("SHIPTOnow becomes:"+json.dumps(symTab[step["shipTos"]]))

    except:
        ex_stat = "ErrorEtsyRemoveAlreadyExpanded:" + str(i)

    return (i + 1), ex_stat

def processEtsyAddPageOfOrder(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["fullOrders"]].append(symTab[step["pageOfOrders"]])

    except:
        ex_stat = "ErrorEtsyAddPageOfOrder:" + str(i)

    return (i + 1), ex_stat


# this func does 2 things:
# 1) get tracking code & status variable updated into the etsy_orders data structure.
# 2) need to
def processEtsyExtractTracking(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        gs_orders = symTab[step["gs_orders"]]
        etsy_orders = symTab[step["fullOrders"]]

            # {"service": "USPS Priority V4", "price": len(regular_orders) * 4.5, "dir": os.path.dirname(ofname2),
            #  "file": os.path.basename(ofname2), "unzipped_dir": ofname2_unzipped})
        idx = 0
        for grp in gs_orders:
            label_files = os.listdir(grp["unzipped_dir"])
            idx = idx + 1

    except:
        ex_stat = "ErrorEtsyExtractTracking:" + str(i)

    return (i + 1), ex_stat


# "nth_var": nth order id on screen.
# "orders_var": etsy orders variable
# "complete_buttons_var": complete_buttons_var,
# "order_ids_var": order_ids extracted from current screen.
# "found_index_var": found_index of the order in the orders list,
# "n_more_var": how many more orders to update
def processEtsyFindScreenOrder(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        found = -1
        orders = symTab[step["orders_var"]]
        nth = symTab[step["nth_var"]]
        log3("nth:"+str(nth)+"orders"+json.dumps(orders))

        template = symTab[step["order_ids_var"]][nth]["text"].strip()
        button_loc = symTab[step["complete_buttons_var"]][nth]["loc"]
        ref_loc = symTab[step["order_ids_var"]][nth]["associates"][0]["loc"]

        oid_template = template.split(" ")[0]
        log3("ALL orders:")
        for o in orders:
            log3("OID:"+str(o.getOid())+"!")

        log3("template:", "["+str(oid_template)+"]"+"button_loc:"+json.dumps(button_loc)+"ref_loc:"+json.dumps(ref_loc))
        # just for sanity cross-check
        if button_loc == ref_loc:
            found = next((idx for idx, order in enumerate(orders) if oid_template in order.getOid()), -1)
            log3("Found:"+json.dumps(found))
            if found > 0:
                orders[found].setStatus("TC updated")
        else:
            log3("ERROR: nth order number doesn't match nth complete order button....")

        tobeUpdated = [ o for o in orders if o.getStatus() == "label generated"]
        symTab[step["n_more_var"]] = len(tobeUpdated)

        symTab[step["found_index_var"]] = found

    except:
        ex_stat = "ErrorEtsyFindScreenOrder:" + str(i)
        log3(ex_stat)

    return (i + 1), ex_stat



def gen_etsy_test_data():
    testorders = []

    new_order = ORDER("", "", "", "", "", "", "")
    recipient = OrderPerson("", "", "", "", "", "", "")
    recipient.setFullName("Alex Fischman")

    products = []
    product = OrderedProduct("", "", "", "")
    product.setPTitle("abc")
    products.append(product)

    shipping = Shipping("", "", "", "", "", "", "", "")
    shipping.setService("USPS Ground Advantage (1-15oz)")
    new_order.setShipping(shipping)
    new_order.setProducts(products)
    new_order.setRecipient(recipient)
    testorders.append(new_order)

    new_order = ORDER("", "", "", "", "", "", "")
    recipient = OrderPerson("", "", "", "", "", "", "")
    recipient.setFullName("Grayson Gold-Garvey")

    products = []
    product = OrderedProduct("", "", "", "")
    product.setPTitle("abc")
    products.append(product)

    shipping = Shipping("", "", "", "", "", "", "", "")
    shipping.setService("USPS Priority V4")
    shipping.setTracking("92055432248005702218667163")
    new_order.setShipping(shipping)
    new_order.setProducts(products)
    new_order.setRecipient(recipient)
    new_order.setOid("#3019459539")
    testorders.append(new_order)

    symTab["etsy_orders"] = testorders
    #
    # return testorders