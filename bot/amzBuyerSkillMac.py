
import json
import random
from datetime import datetime


from bot.Logger import log3
from bot.basicSkill import DEFAULT_RUN_STATUS, symTab, STEP_GAP, genStepHeader, genStepStub, genStepCreateData, genStepUseSkill, genStepWait, \
    genStepCallExtern, genStepExtractInfo, genStepSearchWordLine, genStepSearchAnchorInfo, genStepCheckCondition, \
    genStepMouseScroll, genStepMouseClick, genStepKeyInput, genStepGoToWindow, genStepTextInput, genStepLoop, \
    genScrollDownUntil, genStepFillData, genStepOpenApp, genStepRecordTxtLineLocation, genStepReadFile, genStepWriteFile
from bot.adsPowerSkill import genADSPowerExitProfileSteps
from bot.amzBuyerSkill import genAMZBrowseProductLists
import re
from difflib import SequenceMatcher
import traceback
from bot.scraperAmz import genStepAmzScrapeBuyOrdersHtml, amz_buyer_scrape_product_list, amz_buyer_scrape_product_details, \
    amz_buyer_scrape_product_reviews

from bot.amzBuyerSkill import genAMZScrollProductListToTop, genAMZScrollProductListToBottom, genStepCalibrateScroll, \
    genAMZBrowseProductLists

SAME_ROW_THRESHOLD = 16



def genMacChromeAMZWalkSkill(worksettings, stepN, theme):
    psk_words = "{"
    site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("mac_chrome_amz_browse_search", "win", "1.0", "AIPPS LLC", "PUBMACCHROMEAMZBROWSE001",
                                          "Amazon Browsing On Mac Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/mac_chrome_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genMacChromeAMZWalkSteps("sk_work_settings", this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/mac_chrome_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for mac chrome amazon browsing...." + psk_words)

    return this_step, psk_words


def genMacChromeAMZWalkSteps(worksettings, start_step, theme):
    psk_words = ""
    # this creates the local private skill file.
    #f = open(homepath+"resource/junk.txt", "a")
    # skill name should be some like: browse_search
    # find out skill ID from mission ID,


    # get parent settings which contains tokens to allow the machine to communicate with cloud side.
    site_url = "https://www.amazon.com"

    this_step, step_words = genStepWait(1, 0, 0, start_step)
    psk_words = psk_words + step_words

    # open the order page again.
    this_step, step_words = genStepOpenApp("cmd", True, "browser", site_url, "", "", "expr", "sk_work_settings['cargs']", 5, start_step)
    psk_words = psk_words + step_words


    # this url points to a product list page after a keyword search
    # url = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats1689147960.html"

    # this url points to a detail page.
    # url = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats168914805.html"

    # this url points to all review page.
    # url = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats168914806.html"



    this_step, step_words = genStepCallExtern("global scrn_options\nscrn_options = {'attention_area':[0, 0, 1, 0.5],'attention_targets':['Search', 'EN']}\nprint('scrn_options', scrn_options)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # extract the amazon home page info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, this_step, None, "scrn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global scroll_resolution\nscroll_resolution = sk_work_settings['scroll_resolution']\nprint('scroll_resolution from settings:', scroll_resolution)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # if screen resolution is default value, then needs calibration.
    this_step, step_words = genStepCheckCondition("scroll_resolution == 250", "", "", this_step)
    psk_words = psk_words + step_words

    # get the location of text "Search" nearest to the specified of the screen and store it in variable "cal_marker".
    # loc, txt, screen, tovar, stepN
    this_step, step_words = genStepRecordTxtLineLocation("middle", "", "screen_info", "cal_marker", this_step)
    psk_words = psk_words + step_words

    # now scroll down 30 unit.
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 1, "raw", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(2, 0, 0, this_step)
    psk_words = psk_words + step_words

    # extract the amazon home page info again.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # then calibrate the  # of pixels per scroll, the result is stored in scroll_resolution variable
    # sink, amount, screen, marker, prev_loc, filepath, stepN
    this_step, step_words = genStepCalibrateScroll("scroll_resolution", "1", "screen_info", "", "cal_marker", this_step)
    psk_words = psk_words + step_words

    # scroll back up so that we can start search.
    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 1, "raw", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # end condition for scroll_resolution == 250
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words
    # SC hacking for speed up the tests   ---- uncomment above.

    # this_step, step_words = genStepCreateData("bool", "position_reached", "NA", "False", this_step)
    # psk_words = psk_words + step_words

    ######## scroll calibration completed #### if skip above, just added the next 2 lines for speed
    this_step, step_words = genStepCreateData("string", "scroll_resolution", "NA", 250, this_step)
    psk_words = psk_words + step_words


    # go thru each entry path.this will be the only loop that we unroll, all other loops within the session will be generated
    # as part of the psk. do we have to unroll??????
    # run_config = worksettings["run_config"]
    this_step, step_words = genStepCreateData("expr", "run_config", "NA", "sk_work_settings['run_config']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global run_config\nprint('run_config', run_config)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "numSearchs", "NA", "len(run_config['searches'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthSearch", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nthSearch < numSearchs", "", "", "search" + str(start_step), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "search_buy", "NA", "run_config['searches'][nthSearch]['prodlist_pages'][0]['products'][0]['purchase']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("len(search_buy) == 0", "", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepWait(1, 0, 0, this_step)
    # psk_words = psk_words + step_words

    # if no purchase, it's got to be a browse, so go thru the typical browse process. even if there is in-cart type of
    # buy action, the purchase will never be put the 1st product to browse, the purchase in the following page will take care of itself
    # when we finishing browsing product details, it will check purchase and if there is , we'll do put in cart action there.
    # only non-in-cart type of buy action will be put in the 1st product on the list because there is no need for browsing....
    this_step, step_words = genStepCheckCondition("run_config['searches'][nthSearch]['entry_paths']['type'] == 'Top main menu'", "", "", this_step)
    psk_words = psk_words + step_words

    # old code run is run_config['searches'][nthSearch]
    this_step, step_words = genStepCreateData("expr", "top_menu_item", "NA", "run_config['searches'][nthSearch]['top_menu_item']", this_step)
    psk_words = psk_words + step_words

    # click the menu item and enter that page. \
    # (action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "top_menu_item", "var name", "", "1", "0", "right", "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    # much of this is not yet written....this could be somewhat complicated in that the product list entry might take a couple of screens in
    # which the contents could be changing by amazon...

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # entry by left main menu
    this_step, step_words = genStepCheckCondition("run_config['searches'][nthSearch]['entry_paths']['type'] == 'Left main menu'", "", "", this_step)
    psk_words = psk_words + step_words

    # click on the left main menu.
    # (action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "All", "anchor text", "All",
                                              [0, 0], "right", [1, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now scroll down and find the menu item.

    # much of this is not yet written....this could be somewhat complicated in that the product list entry might take a couple of screens in
    # which the contents could be changing by amazon...

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # default is the search by phrase.
    # click, type search phrase and hit enter.
    # action, txt, speed, loc, key_after, wait_after, stepN
    # genStepKeyboardAction(action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepMouseClick("Triple Click", "", True, "screen_info", "top_search", "anchor icon", "", [-1, 0], "left", [10, ], "box", 2, 0, [0, 0], this_step)
    # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "main_search", "anchor text", "Search Amazon", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "backspace", "", 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("list", False, "run_config['searches'][nthSearch]['entry_paths']['words']", "expr", 0.05, "enter", 2, this_step)
    psk_words = psk_words + step_words

    # (txt_type, saverb, txt, txt_ref_type, speed, key_after, wait_after, stepN):
    this_step, step_words = genStepTextInput("list", False, "run_config['searches'][nthSearch]['entry_paths']['words']", "expr", 0.05, "enter", 2, this_step)
    psk_words = psk_words + step_words

    # html_file_name, root, result_name, stepN):
    this_step, step_words = genStepCallExtern("print('run entry_paths words', run_config['searches'][nthSearch])", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "hfname", "NA", "run_config['searches'][nthSearch]['entry_paths']['words'][0].replace(' ', '_')", this_step)
    psk_words = psk_words + step_words

    # end condition for check whether entry by left main menu.
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end condition for check whether entry by top main menu.
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # no purchase, so regular browse.....
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # this is the case of non addCart procedure..... this will go directly into the cart or user account and go from there....

    # this_step, step_words = genStepCreateData("expr", "direct_buy", "NA", "search_buy[0]", this_step)
    # psk_words = psk_words + step_words
    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genDirectBuySteps("sk_work_settings", "search_buy", this_step, theme)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "numPLPages", "NA", "len(run_config['searches'][nthSearch]['prodlist_pages'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthPLPage", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # loop to go thru each page to be explored....
    this_step, step_words = genStepLoop("nthPLPage < numPLPages", "", "", "search" + str(start_step), this_step)
    psk_words = psk_words + step_words

    # process flow type, and browse the 1st page.
    this_step, step_words = genStepCreateData("expr", "flows", "NA", "run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage]['flow_type'].split(' ')", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('flows:', flows)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('run[prodlist_pages][i]:', nthPLPage, '--', run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage])", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # (fill_type, src, sink, result, stepN):
    this_step, step_words = genStepFillData("expr", "run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage]", "pl_page_config", "temp", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "lastone", "NA", "nthPLPage == numPLPages - 1", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genAMZBrowseProductLists("pl_page_config", "nthPLPage", "lastone", "flows", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('***********************DONE BROWSE 1 PRODUCT LIST ****************************')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # now click on the next page.
    # if not the last page yet, click and go to the next page, what if this product list happens has only 1 page? how to tell whether this is the
    # last page.Answer by SC - actually, never expect this happen on amazon....
    this_step, step_words = genStepCheckCondition("nthPLPage != numPLPages-1", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Next", "anchor text", "Next", [0, 0], "right", [1, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DEBUG', 'page count', nthPLPage, ' out of total [', numPLPages, '] of pages....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # now 1 order update is finished. update the counter
    this_step, step_words = genStepCallExtern("global nthPLPage\nnthPLPage = nthPLPage + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now 1 order update is finished. update the counter
    this_step, step_words = genStepCallExtern("global nthSearch\nnthSearch = nthSearch + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # just give it 30 scrolls to scroll to the top, usually, this should be good enough.
    this_step, step_words = genStepCallExtern("global down_cnt\ndown_cnt = 20", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genAMZScrollProductListToTop("down_cnt", this_step, worksettings)
    psk_words = psk_words + step_words

    # now scroll to top of the page and, take a screen read, get ready for the next round of search.

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    #finally handle the purchase, if there is any.
    # if len(run_config["purchases"]) > 0:
    #     # purchase could be done in multiple days usually (put in cart first, then finish payment in a few days)
    #     this_step, step_words = genPurchase(run_config)
    #     psk_words = psk_words + step_words

    log3("DEBUG", "ready to add stubs...." + psk_words)


    return this_step, psk_words