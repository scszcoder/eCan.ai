import json
import os
from datetime import datetime

from bot.amzBuyerSkill import found_match
from bot.basicSkill import genStepHeader, genStepStub, genStepWait, genStepCreateData, genStepGoToWindow, \
    genStepCheckCondition, genStepUseSkill, genStepOpenApp, genStepCallExtern, genStepLoop, genStepExtractInfo, \
    genStepSearchAnchorInfo, genStepMouseClick, genStepMouseScroll, genStepCreateDir, genStepKeyInput, genStepTextInput, \
    STEP_GAP, DEFAULT_RUN_STATUS, symTab, genStepThink
from bot.Logger import log3
from bot.scraperEbay import ebay_seller_fetch_page_of_order_list
from config.app_info import app_info
from config.app_settings import ecb_data_homepath
from bot.etsySellerSkill import genStepEtsyFindScreenOrder

SAME_ROW_THRESHOLD = 16

site_url = "https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT"


# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinADSEbayFullfillOrdersSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY001",
                                          "Ebay Fullfill New Orders On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ebay_status", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "product_book", "NA", "sk_work_settings['products']", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCallExtern("global product_book\nprint('product_book:', product_book[0])", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words

    # mask out for testing purpose only....
    # this_step, step_words = genStepCreateData("expr", "ebay_orders", "NA", "[]", this_step)
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


    # this_step, step_words = genStepCreateData("expr", "open_profile_input", "NA", "[sk_work_settings['batch_profile']]", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("int", "scroll_resolution", "NA", 250, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("int", "retry_count", "NA", 5, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("bool", "mission_failed", "NA", False, this_step)
    # psk_words = psk_words + step_words
    #
    # # first call subskill to open ADS Power App, and check whether the user profile is already loaded?
    # this_step, step_words = genStepUseSkill("open_profile", "public/win_ads_local_open", "open_profile_input", "ads_up", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepWait(1, 0, 0, this_step)
    # psk_words = psk_words + step_words
    #
    # # now check the to be run bot's profile is already loaded, do this by examine whether bot's email appears on the ads page.
    # # scroll down half screen and check again if nothing found in the 1st glance.
    # this_step, step_words = genStepCreateData("expr", "bot_email", "NA", "sk_work_settings['b_email'].split('@')[0]+'@'", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("expr", "bemail", "NA", "sk_work_settings['b_email']", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("expr", "bpassword", "NA", "sk_work_settings['b_backup_email_pw']", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepSearchWordLine("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded", "ads", False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepSearchAnchorInfo("screen_info", "no_data", "direct", "anchor text", "any", "useless", "nothing_loaded", "", False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCheckCondition("not bot_loaded and not nothing_loaded", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # if not on screen, scroll down and check again.
    # this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 80, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepSearchWordLine("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded", "ads", False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepSearchAnchorInfo("screen_info", "no_data", "direct", "anchor text", "any", "useless", "nothing_loaded", "", False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepStub("end condition", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # if not found, call the batch load profile subskill to load the correct profile batch.
    # this_step, step_words = genStepCheckCondition("not bot_loaded", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("expr", "profile_name", "NA", "os.path.basename(sk_work_settings['batch_profile'])", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("expr", "profile_name_path", "NA", "os.path.dirname(sk_work_settings['batch_profile'])", this_step)
    # psk_words = psk_words + step_words
    #
    # # due to screen real-estate, some long email address might not be dispalyed in full, but usually
    # # it can display up until @ char on screen, so only use this as the tag.
    # this_step, step_words = genStepCreateData("expr", "bot_email", "NA", "sk_work_settings['b_email'].split('@')[0]+'@'", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("expr", "full_site", "NA", "sk_work_settings['full_site'].split('www.')[1]", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("expr", "machine_os", "NA", "sk_work_settings['platform']", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("expr", "batch_import_input", "NA", "['open', profile_name_path, profile_name, bot_email, full_site, machine_os]", this_step)
    # psk_words = psk_words + step_words
    #
    # # once the correct user profile is loaded, the open button corresponding to the user profile will be clicked to open the profile.
    # this_step, step_words = genStepUseSkill("batch_import", "public/win_ads_local_load", "batch_import_input", "browser_up", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepStub("end condition", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # wait 9 seconds for the browser to be brought up.
    # this_step, step_words = genStepWait(6, 1, 3, this_step)
    # psk_words = psk_words + step_words

    # following is for tests purpose. hijack the flow, go directly to browse....
    this_step, step_words = genStepGoToWindow("SunBrowser", "", "g2w_status", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genEbayLoginInSteps(this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not_logged_in == False", "", "", this_step)
    psk_words = psk_words + step_words

    # skname, skfname, in-args, output, step number
    this_step, step_words = genStepUseSkill("collect_orders", "public/win_chrome_ebay_orders", "dummy_in", "ebay_status", this_step)
    psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.
    # first organized order list data into 2 xls for bulk label purchase, and calcualte total funding requird for this action.

    # # from collected ebay orders, generate gs label purchase order files.
    # dtnow = datetime.now()
    # date_word = dtnow.strftime("%Y%m%d")
    # fdir = ecb_data_homepath + "/runlogs/"
    # fdir = fdir + date_word + "/"
    # this_step, step_words = genStepCreateData("str", "fdir", "NA", fdir, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCallExtern("fdir = fdir + 'b' + str(sk_work_settings['mid']) + m + str(sk_work_settings['bid']) + '/'", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCallExtern(
    #     "fdir = fdir + sk_work_settings['platform'] + '_' + sk_work_settings['app'] + '_' + sk_work_settings['site'] + '_' + sk_work_settings['page'] + '/skills/'",
    #     "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCallExtern("fdir = fdir + sk_work_settings['skname'] + '/'", "", "in_line", "",
    #                                           this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("expr", "current_seller", "NA", "sk_work_settings['seller']", this_step)
    # psk_words = psk_words + step_words
    #
    # # this is an app specific step.
    # this_step, step_words = genStepPrepGSOrder("etsy_orders", "gs_orders", "product_book", "current_seller", "fdir", this_step)
    # psk_words = psk_words + step_words
    #
    # homepath = app_info.app_home_path
    # if homepath[len(homepath) - 1] == "/":
    #     homepath = homepath[:len(homepath) - 1]
    # this_step, step_words = genStepCallExtern(
    #     "global gs_orders\ngs_orders = [{'service': 'USPS Priority V4', 'price': 4.5, 'num_orders': 1, 'dir': '" + homepath + "/runlogs/20230910/b3m3/win_chrome_etsy_orders/skills/fullfill_orders', 'file': 'etsyOrdersPriority092320230919.xls'}]\nprint('GS ORDERS', gs_orders)",
    #     "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCallExtern( "global gs_input\ngs_input = [etsy_orders, gs_orders, sevenZExe, rarExe]\nprint('GS input', gs_input)", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # purchase labels, gs_orders contains a list of [{"service": "usps ground", "file": xls file name}, ...]
    # # etsy_oders: will have tracking code and filepath filled
    # # buy_status will be "success" or "fail reason****"
    # # at the end of this skill, the shipping service and the tracking code section of "etsy_orders" should be updated.....
    # this_step, step_words = genStepUseSkill("bulk_buy", "public/win_chrome_goodsupply_label", "gs_input", "labels_dir", this_step)
    # psk_words = psk_words + step_words
    #
    this_step, step_words = genStepUseSkill("buy_shipping", "public/win_chrome_ebay_orders", "shipping_input", "labels_dir", this_step)
    psk_words = psk_words + step_words

    # # extract tracking code from labels and update them into etsy_orders data struture.
    #
    # # gen_etsy_test_data()
    #
    # # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]
    # # now update tracking coded back to the orderlist
    # this_step, step_words = genStepUseSkill("update_tracking", "public/win_ads_ebay_orders", "gs_input", "total_label_cost", this_step)
    # psk_words = psk_words + step_words
    #
    # # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    # this_step, step_words = genStepUseSkill("reformat_print", "public/win_printer_local_print", "label_list", "",
    #                                         this_step)
    # psk_words = psk_words + step_words
    #
    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words
    #
    # # close the browser and exit the skill, assuming at the end of genWinChromeAMZWalkSteps, the browser tab
    # # should return to top of the amazon home page with the search text box cleared.
    # this_step, step_words = genStepKeyInput("", True, "alt,f4", "", 3, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCheckCondition("mission_failed == False", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepGoToWindow("AdsPower", "", "g2w_status", this_step)
    # psk_words = psk_words + step_words
    #
    # # in case mission executed successfully, save profile, kind of an overkill or save all profiles, but simple to do.
    # this_step, step_words = genADSPowerExitProfileSteps(worksettings, this_step, theme)
    # psk_words = psk_words + step_words
    #
    # # end condition for "not_logged_in == False"
    # this_step, step_words = genStepStub("end condition", "", "", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words
    print("generating win ads ebay skill")
    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay order fullfill operation...." + psk_words)

    return this_step, psk_words


def genWinChromeEbayFullfillOrdersSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_ebay_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEEBAY001",
                                          "Ebay Fullfill New Orders On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_chrome_ebay_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_ebay_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words
    print("generating win chrome ebay skill")
    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome ebay order fullfill operation...." + psk_words)

    return this_step, psk_words

# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinADSEbayCollectOrderListSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_collect_orders", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY001",
                                          "Ebay Collect New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_ebay_orders/collect_orders", "", this_step)
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
    hfname = "ebayOrders" + dt_string + ".html"

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

    this_step, step_words = genStepLoop("endOfOrderList != True", "", "", "browseEbayOL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global endOfOrdersPage\nendOfOrdersPage = False", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # loop thru every "Ship to" on the page and click on it to show the full address. and record accumulatively #of "Ship to" being clicked.
    this_step, step_words = genStepLoop("endOfOrdersPage != True", "", "", "browseEbayOrderPage" + str(this_step), this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "orders", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # use this info, as it contains the name and address, as well as the ship_to anchor location.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["ship_to_summery"], "direct", ["info 2"], "any", "shipToSummeries", "useless", "ebay", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["ship_to"], "direct", ["anchor text"], "any", "shipTos", "useless", "ebay", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "numShipTos", "NA", "len(shipTos)-1", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepEtsyRemoveAlreadyExpanded("shipTos", "shipToSummeries", this_step)
    # psk_words = psk_words + step_words

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
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["ebay_inc"], "direct", ["anchor text"], "any", "endOfOrdersPage", "endOfOrdersPage", "ebay", False, this_step)
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

    homepath = os.environ.get("ECBOT_HOME")
    if homepath[len(homepath)-1]=="/":
        homepath = homepath[:len(homepath)-1]
    # html, pidx, outvar, statusvar, stepN):
    # hfile = homepath+'runlogs/20230825/b3m3/win_chrome_etsy_orders/skills/collect_orders/etsyOrders1692998813.html'
    # this_step, step_words = genStepEbayScrapeOrdersHtml(hfile, "currentPage", "pageOfOrders",  "", this_step)
    # hfile = homepath+"runlogs/20230904/b3m3/win_chrome_etsy_orders/skills/collect_orders/etsyOrders1693857164.html"


    this_step, step_words = genStepEbayScrapeOrdersHtml(hfname, "currentPage", "pageOfOrders", "", this_step)
    # this_step, step_words = genStepEbayScrapeOrdersHtml(hfile, "pageOfOrders", "fileStatus", "", this_step)
    psk_words = psk_words + step_words


    # this_step, step_words = genStepEbayAddPageOfOrder("etsy_orders", "pageOfOrders", this_step)
    # # this_step, step_words = genStepEbayScrapeOrdersHtml(hfile, "pageOfOrders", "fileStatus", "", this_step)
    # psk_words = psk_words + step_words

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

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/collect_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words

def genWinChromeEbayCollectOrderListSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_ebay_collect_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEEBAY002",
                                          "Ebay Collect New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_ebay_orders/collect_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_ebay_orders/collect_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome ebay collect orders operation...." + psk_words)

    return this_step, psk_words


def genWinADSEbayBuyShippingSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_buy_shipping", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSEBAY002",
                                          "Ebay Buy Shipping and Update Tracking On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_ebay_orders/buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads ebay buy shipping and update tracking...." + psk_words)

    return this_step, psk_words

def genWinADSEbayBuyShippingSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_ebay_buy_shipping", "win", "1.0", "AIPPS LLC",
                                          "PUBWINCHROMEEBAY002",
                                          "Ebay Buy Shipping and Update Tracking On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_ebay_orders/buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_ebay_orders/buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome ebay buy shipping and update tracking...." + psk_words)

    return this_step, psk_words

# this skill assumes tracking code ready in the orders list data structure, and update tracking code to the orders on website.
# all the tracking code should already be updated into etsy_orders data structure which is the sole input parameter.....
def genWinADSEbayUpdateShipmentTrackingSkill(worksettings, stepN, theme):
    psk_words = "{"


    this_step, step_words = genStepHeader("win_ads_ebay_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY001",
                                          "Ebay Fullfill New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_ebay_orders/update_tracking", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    # open the order page again.
    this_step, step_words = genStepCallExtern("global blurl\nblurl = 'https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    # hit ctrl-t to open a new tab.
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # type in bulk buy label URL address.
    this_step, step_words = genStepTextInput("var", False, "blurl", "direct", 1, "", 2, this_step)
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
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "order_pulldown", "anchor icon", "", "nthCompletion", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "orders", "completion", theme, this_step, None)
    psk_words = psk_words + step_words

    # click and type USPS in carrier pull down menu
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "add_tracking", "anchor text", "", [0, 0], "bottom", [0, 2], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global shipping_service\nshipping_service = fin[0][update_order_index].getShippingService()[:3]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepTextInput("var", False, "shipping_service", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    # click and type in the tracking code.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "add_tracking", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global track_code\ntrack_code = fin[0][update_order_index].getShippingTracking()", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "tracking_number", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "track_code", "direct", 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "carrier", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "current_carrier", "var", 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "save_continue", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now refresh the page, the just completed order should dissappear (moved to completed list)
    this_step, step_words = genStepKeyInput("", True, "ctrl,f5", "", 4, this_step)
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


    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/update_tracking", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words

def genWinADSEbayHandleMessagesSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_handle_messages", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSEBAY002",
                                          "Ebay Buy Shipping and Update Tracking On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_ebay_orders/handle_messages", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/handle_messages", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads ebay handle messages...." + psk_words)

    return this_step, psk_words


def genWinChromeEbayHandleMessagesSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_ebay_handle_messages", "win", "1.0", "AIPPS LLC",
                                          "PUBWINCHROMEEBAY002",
                                          "Ebay Buy Shipping and Update Tracking On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_ebay_orders/handle_messages", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("n_message_needs_process != n_message_processed", "", "", "browseEtsyOL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # obtain response from LLM model, sends to cloud lambda
    this_step, step_words = genStepGenRespMsg("openai", "chatgpt4o", "parameters", "products", "setup", "query", "response", "chat_result", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("chat_result", "", "", this_step)
    psk_words = psk_words + step_words

    # type in the response.
    this_step, step_words = genStepTextInput("var", False, "response_text", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    # click on the send button.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "send", "anchor text", "", "nthCompletion", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global n_message_processed\nn_message_processed = n_message_processed+1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("response_action == 'resend'", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_ebay_orders/handle_messages", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome ebay handle messages...." + psk_words)

    return this_step, psk_words

# input: a list of items to be returned: item, quantity, size weight, sender.
def genStepCreateReturnLabels(stepN):
    psk_words = "{"

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads ebay purchase shipping labels...." + psk_words)

    return this_step, psk_words

# input: a list of items to be resend: item, quantity, size weight, recipient.
def genStepCreateResends(stepN):
    psk_words = "{"

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads ebay purchase shipping labels...." + psk_words)

    return this_step, psk_words

# input: a list of orders to be refunded: order id, amount to refund (%), amount to refund (value), pre-condition (return received?), when?.
def genStepHandleRefunds(stepN):
    psk_words = "{"

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads ebay purchase shipping labels...." + psk_words)

    return this_step, psk_words

# buy and download labels from EBAY using USPS, Steps:
#  1) go to https://www.ebay.com/gslblui/bulk/ for bulk purchase.
#  2) go thru each item make sure it's cheapest shipper, unless otherwise noted in product list.
#  3) click on review purchase,
#  4) make sure price is right, purchase method is right, then click on confirm.
#  5) move downloaded labels into destinated dir, unpack, reformat the labels, and print.
#  note: one advantage is purchasing labels from ebay will auto update tracking, so this step
#        is saved. the disadvantge is labels might not be the cheapest.
def genWinADSEbayBuyShippingLabelsSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_buy_labelss", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY003",
                                          "Ebay Buy Shipping On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_ebay_orders/buy_labels", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global blurl\nblurl = 'https://www.ebay.com/gslblui/bulk/'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    # hit ctrl-t to open a new tab.
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # type in bulk buy label URL address.
    this_step, step_words = genStepTextInput("var", False, "blurl", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    # go thru all orders, page by page, screen by screen. same nested loop as in collect orders...
    this_step, step_words = genStepCallExtern("global buyLabelsDone\nbuyLabelsDone = False", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global currentPage\ncurrentPage = 0", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "update_order_index", "NA", -1, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepLoop("endOfOrderList != True", "", "", "browseEtsyOL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global endOfOrdersPage\nendOfOrdersPage = False", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    # loop thru every "Ship to" on the page and click on it to show the full address. and record accumulatively #of "Ship to" being clicked.
    this_step, step_words = genStepLoop("buyLabelsDone != True", "", "", "browseEtsyOrderPage" + str(this_step), this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "orders", "completion", theme,
                                               this_step, None)
    psk_words = psk_words + step_words

    # use this info, as it contains the name and address, as well as the ship_to anchor location.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["usps"], "direct", ["anchor text"], "any",
                                                    "complete_buttons", "useless", "etsy", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["order_number"], "direct", ["info 1"], "any",
                                                    "orderIds", "useless", "etsy", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global numCompletions\nnumCompletions = len(orderIds)", "", "in_line",
                                              "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nthCompletion\nnthCompletion = 0", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # loop thru every "Ship to" on the page and click on it to show the full address. and record accumulatively #of "Ship to" being clicked.
    this_step, step_words = genStepLoop("nthCompletion < numCompletions", "", "", "dummy" + str(stepN), this_step)
    psk_words = psk_words + step_words



    this_step, step_words = genStepEtsyFindScreenOrder("nthCompletion", "complete_buttons", "orderIds", "etsy_orders",
                                                       "update_order_index", "nMore2Update", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global update_order_index\nprint('update_order_index', update_order_index)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global fin\nprint('fin', fin)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("update_order_index >= 0", "", "", this_step)
    psk_words = psk_words + step_words

    # click on the complete order button
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "standard_insurance", "anchor icon",
                                              "", "nthCompletion", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "orders", "completion", theme,
                                               this_step, None)
    psk_words = psk_words + step_words

    # click and type USPS in carrier pull down menu
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "shipping_carrier",
                                              "anchor text", "", [0, 0], "bottom", [0, 2], "box", 2, 2, [0, 0],
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global shipping_service\nshipping_service = fin[0][update_order_index].getShippingService()[:3]", "",
        "in_line", "", this_step)
    psk_words = psk_words + step_words



    # end condition for checking whehter this order can to be completed.
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # now 1 order update is finished. update the counter
    this_step, step_words = genStepCallExtern("global nthCompletion\nnthCompletion = nthCompletion + 1", "", "in_line",
                                              "", this_step)
    psk_words = psk_words + step_words


    # now scroll to the next screen.
    # (action, action_args, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 60, "screen", "scroll_resolution", 0, 0,
                                               0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    #  end of loop for scoll till the endOfOrdersPage.
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    # end of loop for while (endOfOrderList != True)
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/update_tracking", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads ebay purchase shipping labels...." + psk_words)

    return this_step, psk_words


def genStepEbayScrapeOrdersHtml(html_var, page_cfg, page_num, product_list, stepN):
    stepjson = {
        "type": "Key Input",
        "html_var": html_var,
        "page_cfg": page_cfg,
        "page_num": page_num,
        "product_list": product_list
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def processEbayScrapeOrdersHtml(step, i, mission, skill):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Extract Order List from HTML: "+json.dumps(step))

        hfile = symTab[step["html_var"]]
        log3("hfile: "+hfile)

        pl = ebay_seller_fetch_page_of_order_list(hfile, step["page_num"])
        log3("scrape product list result: "+json.dumps(pl))

        att_pl = []

        for p in step["page_cfg"]["products"]:
            log3("current page config: "+json.dumps(p))
            found = found_match(p, pl["pl"])
            if found:
                # remove found from the pl
                if found["summery"]["title"] != "CUSTOM":
                    pl["pl"].remove(found)
                else:
                    # now swap in the swipe product.
                    found = {"summery": {
                                "title": mission.getTitle(),
                                "rank": mission.getRating(),
                                "feedbacks": mission.getFeedbacks(),
                                "price": mission.getPrice()
                                },
                        "detailLvl": p["detailLvl"],
                        "purchase": p["purchase"]
                    }

                att_pl.append(found)

        if not step["product_list"] in symTab:
            # if new, simply assign the result.
            symTab[step["product_list"]] = {"products": pl, "attention": att_pl}
        else:
            # otherwise, extend the list with the new results.
            symTab[step["product_list"]].append({"products": pl, "attention": att_pl})

        log3("var step['product_list']: "+json.dumps(symTab[step["product_list"]]))
    except:
        ex_stat = "ErrorEbayScrapeOrdersHtml:" + str(i)
        log3(ex_stat)

    return (i + 1), ex_stat


def genWinADSEbayHandleReturnsSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_handle_returns", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY001",
                                          "Ebay Handle Return Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/handle_returns", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(5, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ebay_status", "NA", "", this_step)
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

    # gen_etsy_test_data()

    # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]
    # now update tracking coded back to the orderlist
    this_step, step_words = genStepUseSkill("update_tracking", "public/win_ads_ebay_orders", "gs_input", "total_label_cost", this_step)
    psk_words = psk_words + step_words

    # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    this_step, step_words = genStepUseSkill("reformat_print", "public/win_printer_local_print", "label_list", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/handle_returns", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay handle return operation...." + psk_words)

    return this_step, psk_words



def genWinADSEbayHandleMsgsSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_handle_msgs", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY002",
                                          "Ebay Handle Return Messages On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/handle_returns", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(5, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ebay_status", "NA", "", this_step)
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

    # gen_etsy_test_data()

    # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]
    # now update tracking coded back to the orderlist
    this_step, step_words = genStepUseSkill("update_tracking", "public/win_ads_ebay_orders", "gs_input", "total_label_cost", this_step)
    psk_words = psk_words + step_words

    # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    this_step, step_words = genStepUseSkill("reformat_print", "public/win_printer_local_print", "label_list", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/handle_returns", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepThink("end skill", "public/win_ads_ebay_orders/handle_returns", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "blurl", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "shipping_carrier",
                                              "anchor text", "", [0, 0], "bottom", [0, 2], "box", 2, 2, [0, 0],
                                              this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay handle return operation...." + psk_words)

    return this_step, psk_words

def genEbayLoginInSteps(stepN, theme):
    psk_words = ""

    # check the 1st tab to make sure the connection to internet thru proxy is normal, the way to check
    # is to check wither there is a valid IP address, there is IPV4 and IPV6, and/or the green dot around
    # the typical web site.
    this_step, step_words = genStepKeyInput("", True, "ctrl,1", "", 3, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "usa", "direct", "anchor text", "any", "useless", "ip_obtained", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("ip_obtained", "", "", this_step)
    psk_words = psk_words + step_words

    # if so, then check whether the site page is opened? if not, search "Amazon.com"  above "start.adspower.net",
    # if there is, click on "Amazon.com"
    # open the site page.

    # this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "amazon_site", "direct", "anchor text", "any", "useless", "site_loaded", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("site_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "amazon_site", "anchor text", "", [0, 0], "center", [0, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words


    # open a new tab with hot-key ctrl-t
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # since the mouse cursor will be automatiall put at the right location, just start typing.... www.amazcon.com
    this_step, step_words = genStepTextInput("var", False, "www.amazon.com", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    # end condition for "site_loaded"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end condition for "ip_obtained"
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # retry a few times
    this_step, step_words = genStepLoop("retry_count > 0 and not ip_obtained", "", "", "connProxy"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # just keep on refreshing....
    this_step, step_words = genStepKeyInput("", True, "f5", "", 3, this_step)
    psk_words = psk_words + step_words

    # wait some random time for proxy to connect
    this_step, step_words = genStepWait(0, 5, 8, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "amazon_site", "direct", "anchor text", "any", "useless", "site_loaded", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCheckCondition("not ip_obtained", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global mission_failed\nmission_failed = True", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end condition for "ip_obtained"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words
    #
    # make sure logged in. by check whether there is "sign in" to the right of "Hello"(info ref_method=1), if so, move mouse over to "hello", then
    #  click on "sign in" button below, then type in "email" and hit "continue" button, then type in password and hit "Sign in" button
    # once in, double check the Hello - sign in relation ship again to double check. then, calibrate screen.
    # typically its expected that the account is already setup on ADS, so that the account should be logged in directly...
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["sign_in"], "direct", ["anchor text"], "any", "useless", "not_logged_in", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not_logged_in", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "hello", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "email", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "bemail", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "continue", "anchor text", "", "0", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "password", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "bpassword", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "sign_in_button", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["sign_in"], "direct", ["info 1"], "any", "useless", "not_logged_in", "", False, this_step)
    psk_words = psk_words + step_words


    # end condition for "not_logged_in"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words