from basicSkill import *
from scraperEtsy import *

SAME_ROW_THRESHOLD = 16


# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinEtsyHandleOrderSkill(lieutenant, page, sect, stepN, theme):
    psk_words = ""

    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))

    this_step, step_words = genStepCreateData("bool", "endOfOrderList", "NA", "False", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "endOfOrdersPage", "NA", "False", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nNewOrders", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nOrderPages", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "currentPage", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "pagelist", "[]", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("endOfOrderList != True", "", "", "browseEtsyOL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global endOfOrdersPage\nendOfOrdersPage = False", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", lieutenant.homepath, "screen_info", "etsy_orders", "top", theme, this_step, None)
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
    this_step, step_words = genStepStub("else", "", this_step)
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

    this_step, step_words = genStepExtractInfo("", lieutenant.homepath, "screen_info", "etsy_orders", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # search "etsy, inc" and page list as indicators for the bottom of the order list page.
    this_step, step_words = genStepSearch("screen_info", ["page_num_list"], ["info text"], "any", "endOfOrdersPage", "pageList", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["etsy_inc"], ["anchor text"], "any", "endOfOrdersPage", "useless", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEtsySearchOrders("screen_info", "pageOfOrders", "errorPage", this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("end loop", "", this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("end condition", "", this_step)
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
    this_step, step_words = genStepStub("else", "", this_step)
    psk_words = psk_words + step_words

    # update currentPage counter
    this_step, step_words = genStepCallExtern("global currentPage\ncurrentPage = currentPage + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN enter the product details page.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "pl_need_attention[att_count]['txts']['box']", "expr", "", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    # # close bracket for condition ("currentPage == nOrderPages")
    this_step, step_words = genStepStub("end condition", "", this_step)
    psk_words = psk_words + step_words

    # end of loop for while (endOfOrderList != True)
    this_step, step_words = genStepStub("end loop", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.


    # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]

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


# puchase shipping labels....
def genWinEtsyObtainLabelsSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []

# fill in the order tracking number for each order, starting backward from the last order to the first order.
def genWinEtsyUpdateOrderSkill(lieutenant, bot_works, start_step, theme, stepN):
    psk_words = ""
    # assume the order data is in all_orders variable (tracking code already added to the data).
    # assume n_pages variable holds # of pages of the products.
    this_step, step_words = genStepCreateData("bool", "foundMark", "NA", "False", stepN)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("bool", "startOfOrdersPage", "NA", "False", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("int", "nTrackingUpdated", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nTrackingUpdated >= 0", "", "", "allTrackCodeUpdated" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global startOfOrdersPage\nstartOfOrdersPage = False", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # (action, action_args, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 75, "screen", "scroll_resolution", 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", lieutenant.homepath, "screen_info", "etsy_orders", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # search "etsy, inc" and page list as indicators for the bottom of the order list page.
    this_step, step_words = genStepSearch("screen_info", ["complete_order"], ["anchor icon"], "any", "foundMark", "useless", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["orders_per_page"], ["anchor text"], "any", "startOfOrdersPage", "useless", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("foundMark == True", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "enter_tracking_number", "expr", "", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "complete_order", "expr", "", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "USPS", "expr", "", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

def genWinEtsyHandleReturnSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []


# scrape the html for everything about the orders, except the street address which still needs to be grabbed by click+screen analysis.
def genWinEtsyScrapeOrderList():
    print("scraping etsy orders html")
