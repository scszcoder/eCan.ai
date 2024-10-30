import copy
import os
from datetime import datetime

from bot.amzBuyerSkill import found_match
from bot.basicSkill import genStepHeader, genStepStub, genStepWait, genStepCreateData, genStepGoToWindow, \
    genStepCheckCondition, genStepUseSkill, genStepOpenApp, genStepCallExtern, genStepLoop, genStepExtractInfo, \
    genStepSearchAnchorInfo, genStepMouseClick, genStepMouseScroll, genStepCreateDir, genStepKeyInput, genStepTextInput, \
    STEP_GAP, DEFAULT_RUN_STATUS, symTab, genStepThink, genStepSearchWordLine, genStepCalcObjectsDistance, \
    genScrollDownUntilLoc, genStepMoveDownloadedFileToDestination, genStepReadXlsxFile, genStepReadJsonFile, \
    genStepUploadFiles, genStepDownloadFiles
from bot.Logger import log3
from bot.etsySellerSkill import genStepPrepGSOrder
from bot.labelSkill import genStepPrepareGSOrder
from bot.scraperAmz import amz_buyer_scrape_product_list, amz_buyer_scrape_product_details
from bot.seleniumSkill import *
from bot.ecSkill import genStepGenShippingOrdersFromMsgResponses
from bot.seleniumScrapeAmz import *
from bot.ordersData import Shipping
from config.app_info import app_info
from config.app_settings import ecb_data_homepath
from bot.etsySellerSkill import genStepEtsyFindScreenOrder
import math
import itertools
import json
import traceback
from bot.basicSkill import DEFAULT_RUN_STATUS
from bot.Logger import log3
from bot.amzBuyerSkill import genAMZLoginInSteps
from bot.adsPowerSkill import genStepsADSPowerExitProfile

# the flow is adapted from the same routine in amzBuyerSkill
# except all screen read becomes in-browser webdriver based read which is much much easier...
def genStepsWinChromeAMZBrowserWalk(worksettings, stepN):
    psk_words = ""

    this_step, step_words = genStepCreateData("expr", "run_config", "NA", "sk_work_settings['run_config']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "numSearchs", "NA", "len(run_config['searches'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthSearch", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nthSearch < numSearchs", "", "", "search" + str(start_step), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "search_buy", "NA",
                                              "run_config['searches'][nthSearch]['prodlist_pages'][0]['products'][0]['purchase']",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("len(search_buy) == 0", "", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepWait(1, 0, 0, this_step)
    # psk_words = psk_words + step_words

    # if no purchase, it's got to be a browse, so go thru the typical browse process. even if there is in-cart type of
    # buy action, the purchase will never be put the 1st product to browse, the purchase in the following page will take care of itself
    # when we finishing browsing product details, it will check purchase and if there is , we'll do put in cart action there.
    # only non-in-cart type of buy action will be put in the 1st product on the list because there is no need for browsing....
    this_step, step_words = genStepCheckCondition(
        "run_config['searches'][nthSearch]['entry_paths']['type'] == 'Top main menu'", "", "", this_step)
    psk_words = psk_words + step_words

    # old code run is run_config['searches'][nthSearch]
    this_step, step_words = genStepCreateData("expr", "top_menu_item", "NA",
                                              "run_config['searches'][nthSearch]['top_menu_item']", this_step)
    psk_words = psk_words + step_words

    # click the menu item and enter that page. \
    # (action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN):
    # amazon_basics_link = driver.find_element(By.LINK_TEXT, ":top_menu_item")
    # amazon_basics_link.click()
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_table", 0, "info_type", By.LINK_TEXT, ':top_menu_item', True, "var", "target_top_menu", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverClick("web_driver", "target_top_menu", "click_result", "click_flag", this_step)
    psk_words = psk_words + step_words

    # much of this is not yet written....this could be somewhat complicated in that the product list entry might take a couple of screens in
    # which the contents could be changing by amazon...

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # entry by left main menu
    # 4. Open the "All" menu on the left-most side to reveal submenus
    # all_menu_button = driver.find_element(By.ID, "nav-hamburger-menu")
    # all_menu_button.click()
    #
    # time.sleep(2)  # Wait for the menu to expand
    #
    # # (Optional) Find and interact with a submenu item
    # # Example: Click on "Echo & Alexa" submenu inside the "All" menu
    # submenu_item = driver.find_element(By.LINK_TEXT, "Echo & Alexa")
    # submenu_item.click()


    this_step, step_words = genStepCheckCondition(
        "run_config['searches'][nthSearch]['entry_paths']['type'] == 'Left main menu'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_table", 0, "info_type",
                                                        By.LINK_TEXT, ':top_menu_item', True, "var", "left_main_menu",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverClick("web_driver", "left_main_menu", "click_result", "click_flag",
                                                  this_step)
    psk_words = psk_words + step_words


    # now scroll down and find the menu item.
    # driver.execute_script("arguments[0].scrollIntoView(true);", dropdown_button)
    this_step, step_words = genStepWebdriverScrollTo("web_driver", "left_menu_lvl0_element", 10, 30, 0.25, "dummy_in", "element_present", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverClick("web_driver", "left_main_menu", "click_result", "click_flag",
                                                  this_step)
    psk_words = psk_words + step_words

    # click level1 item if configured so......

    # much of this is not yet written....this could be somewhat complicated in that the product list entry might take a couple of screens in
    # which the contents could be changing by amazon...

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # default is the search by phrase.
    # click, type search phrase and hit enter.
    # action, txt, speed, loc, key_after, wait_after, stepN
    # genStepKeyboardAction(action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_table", 0, "info_type", By.ID, 'twotabsearchtextbox', True, "var", "search_input", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_table", 0, "info_type", By.ID, 'nav-cart', True, "var", "top_cart", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_table", 0, "info_type", By.ID, 'nav-orders', True, "var", "returns_and_orders", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_table", 0, "info_type", By.ID, 'nav-link-accountList', True, "var", "account_list", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_table", 0, "info_type", By.LINK_TEXT, 'Account', True, "var", "account_menu_item", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_table", 0, "info_type", By.LINK_TEXT, 'Sign In', True, "var", "sign_in_menu_item", "extract_flag", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("global search_term, nthSearch, run_config\nsearch_term = run_config['searches'][nthSearch]['entry_paths']['words']\nprint('search_term', search_term)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverKeyIn("web_driver", "search_input", "search_term", "action_result", "action_flag", this_step)
    psk_words = psk_words + step_words

    # (txt_type, saverb, txt, txt_ref_type, speed, key_after, wait_after, stepN):
    # this_step, step_words = genStepTextInput("list", False, "run_config['searches'][nthSearch]['entry_paths']['words']", "expr", 0.05, "enter", 2, this_step)
    # psk_words = psk_words + step_words

    # html_file_name, root, result_name, stepN):
    this_step, step_words = genStepCallExtern("print('run entry_paths words', run_config['searches'][nthSearch])", "",
                                              "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "hfname", "NA",
                                              "run_config['searches'][nthSearch]['entry_paths']['words'][0].replace(' ', '_')",
                                              this_step)
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

    this_step, step_words = genStepCreateData("expr", "direct_buy", "NA", "search_buy[0]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepsBrowserDirectBuy("sk_work_settings", "search_buy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "numPLPages", "NA",
                                              "len(run_config['searches'][nthSearch]['prodlist_pages'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthPLPage", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "row_height", "NA", 750, this_step)  # default in pixel
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "unit_row_scroll", "NA", 3, this_step)  # default in pixel
    psk_words = psk_words + step_words

    # loop to go thru each page to be explored....
    this_step, step_words = genStepLoop("nthPLPage < numPLPages", "", "", "search" + str(start_step), this_step)
    psk_words = psk_words + step_words

    # process flow type, and browse the 1st page.
    this_step, step_words = genStepCreateData("expr", "flows", "NA",
                                              "run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage]['flow_type'].split(' ')",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('flows:', flows)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "print('run[prodlist_pages][i]:', nthPLPage, '--', run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage])",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # (fill_type, src, sink, result, stepN):
    this_step, step_words = genStepFillData("expr", "run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage]",
                                            "pl_page_config", "temp", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "lastone", "NA", "nthPLPage == numPLPages - 1", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepsAMZBrowserBrowseProductLists("pl_page_config", "nthPLPage", "lastone", "flows", this_step,
                                                     worksettings)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "print('***********************DONE BROWSE 1 PRODUCT LIST ****************************')", "", "in_line", "",
        this_step)
    psk_words = psk_words + step_words

    # now click on the next page.
    # if not the last page yet, click and go to the next page, what if this product list happens has only 1 page? how to tell whether this is the
    # last page.Answer by SC - actually, never expect this happen on amazon....
    this_step, step_words = genStepCheckCondition("nthPLPage != numPLPages-1", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "next", "anchor text", "Next",
                                              [0, 0], "right", [0, 0], "box", 2, 5, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "print('DEBUG', 'page count', nthPLPage, ' out of total [', numPLPages, '] of pages....')", "", "in_line", "",
        this_step)
    psk_words = psk_words + step_words

    # now 1 order update is finished. update the counter
    this_step, step_words = genStepCallExtern(
        "global nthPLPage\nnthPLPage = nthPLPage + 1\nprint('nthPLPage:', nthPLPage)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now scroll back to top of the page so that the next search can be done.
    this_step, step_words = genStepsAMZBrowserScrollProductListToTop(this_step)
    psk_words = psk_words + step_words

    # now 1 order update is finished. update the counter
    this_step, step_words = genStepCallExtern("global nthSearch\nnthSearch = nthSearch + 1", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    # just give it 30 scrolls to scroll to the top, usually, this should be good enough.
    this_step, step_words = genStepCallExtern("global down_cnt\ndown_cnt = 20", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepsAMZBrowserScrollProductListToTop(this_step)
    psk_words = psk_words + step_words


    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # finally handle the purchase, if there is any.
    # if len(run_config["purchases"]) > 0:
    #     # purchase could be done in multiple days usually (put in cart first, then finish payment in a few days)
    #     this_step, step_words = genPurchase(run_config)
    #     psk_words = psk_words + step_words

    log3("DEBUG", "ready to add stubs...." + psk_words)

    return this_step, psk_words


# assume we're on amazon site. first - make sure we're on the top of the page, if not scroll to it.
def genStepsBrowserDirectBuy(settings_var_name, buy_var_name, stepN):
    psk_words = ""

    this_step, step_words = genStepsAMZBrowserScrollProductListToTop(stepN)
    psk_words = psk_words + step_words

    # at this point, we should be on top of the amazon page, so that we can now click into returns&orders or Cart depends on the buy action
    this_step, step_words = genStepsWinChromeAMZBrowserBuy(settings_var_name, buy_var_name, "buy_result", "buy_step_flag", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genStepsAMZBrowserScrollProductListToTop(stepN):
    psk_words = ""
    log3("DEBUG", "gen_psk_for_scroll_to_top...")

    # simply scroll to cart that's all there is.....
    this_step, step_words = genStepWebdriverScrollTo("web_driver", "top_cart", 10, 30, 0.25, "dummy_in","element_present", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE SCROLL UP PRODUCT LIST.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    log3("scroll reached TOP of the page")

    return this_step,psk_words


def genStepsAMZBrowserScrollPDToTop(stepN):
    psk_words = ""
    log3("DEBUG", "genStepsAMZBrowserScrollPDToTop...")

    # easy act, just scroll to the top menu, with cart button
    this_step, step_words = genStepWebdriverScrollTo("web_driver", "top_cart", 10, 30, 0.25, "dummy_in",
                                                     "element_present", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE SCROLL PRODUCT DETAILS TO TOP.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    log3("scroll reached TOP of the product details page")

    return this_step,psk_words


def genStepsAMZBrowserBrowseProductLists(pageCfgsName, ith, lastone, flows, stepN, worksettings):
    psk_words = ""

    this_step, step_words = genStepCallExtern(
        "from datetime import datetime\nglobal hf_name\nhf_name= 'pl'+ str(int(datetime.now().timestamp()))+'_'+str(" + ith + ")+'.html'\nprint('hf_name:',hf_name,datetime.now())",
        "", "in_line", "", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "file_save_input", "NA",
                                              "['save', sk_work_settings['log_path'], hf_name]", this_step)
    psk_words = psk_words + step_words


    log3("gen flow: " + json.dumps(flows))

    this_step, step_words = genStepCallExtern("global numFlows\nnumFlows = len(" + flows + ")", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthFlow", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # algorithm goes like this:
    # for each search result, config will tell you how many product list pages to browse thru,
    # usually less than 3 pages, mostly just 1 or 2 pages.
    # for each page, one can scroll down and up and back down and back up several times.
    # for our algorithm, one will only browse page in details on a downward browse flow.
    # even though a real human could browse in details on an upward flow as well...
    #
    # so the algorithm goes: scroll up is always just scroll without browsing in any details.
    #             scroll down at the inital flow is also simply scroll down without browsing details.
    #             only at the last scroll, it pays attention to details and grab screen contents.
    #  while nthFlow < numFlows:
    #      if this is a scroll down browse flow:
    #           if this is before 2nd to the last flow:
    #               if this is the last product list page:
    #                   browse till the last attention     # at the last page, no need to scroll all the way down
    #               else:
    #                   browse to the bottom of the page.
    #           else:
    #               scroll to the bottom of the page, without browsing.
    #       else if this is a scroll up browse flow:
    #           scroll up to the top without browsi
    #       nthFLow = nthFlow + 1
    this_step, step_words = genStepCallExtern(
        "global nthFlow, numFlows\nprint('000: nthFlow, numFlows', nthFlow, numFlows)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nthFlow < numFlows", "", "", "browseAmzPL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nthFlow, numFlows\nprint('nthFlow, numFlows', nthFlow, numFlows)",
                                              "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition(flows + "[nthFlow] == 'down'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("nthFlow >= numFlows - 2", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    # is this the last product list page?
    this_step, step_words = genStepCheckCondition(lastone, "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZBrowserScrapePL("web_driver", "plSearchResult", ith, pageCfgsName, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    # if this is the last page of this search, then no need to scroll to the bottom, simply scroll to whatever
    # the last attention point. If there is no attention needed, simply scroll a few times and be done.
    this_step, step_words = genStepsAMZBrowserBrowsePLToLastAttention(pageCfgsName, "plSearchResult", ith, this_step,
                                                                   worksettings)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepAMZBrowserScrapePL("web_driver", "plSearchResult", ith, pageCfgsName, this_step)
    psk_words = psk_words + step_words

    # plSearchResult contains a list of products on this page as well as all the products we should pay attention to.
    # pageCfgName contains the page configuration
    this_step, step_words = genStepsAMZBrowserBrowsePLToBottom(pageCfgsName, "plSearchResult", ith, this_step,
                                                            worksettings)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # simply scroll to the bottom, ....no browsing along the way
    this_step, step_words, down_count_var = genStepsAMZBrowserScrollPLToBottom(this_step, worksettings, 0)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "down_cnt", "NA", 20, this_step)
    psk_words = psk_words + step_words

    # back up is always a quick scroll, will never browse along the way.
    this_step, step_words = genStepsAMZBrowserScrollProductListToTop(this_step)
    psk_words = psk_words + step_words

    # # close bracket for condition (pageOfOrders['num_pages'] == pageOfOrders['page'])
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nthFlow\nnthFlow = nthFlow + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words

    return this_step, psk_words





def genStpesBrowserDirectBuy(settings_var_name, buy_var_name, stepN):
    psk_words = ""

    this_step, step_words = genStepsAMZBrowserScrollProductListToTop(stepN)
    psk_words = psk_words + step_words

    # at this point, we should be on top of the amazon page, so that we can now click into returns&orders or Cart depends on the buy action
    this_step, step_words = genStepsWinChromeAMZBrowserBuy(settings_var_name, buy_var_name, "buy_result", "buy_step_flag", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words



def genStepsAMZBrowserBrowsePLToBottom(page_cfg, pl, ith, stepN, worksettings):
    psk_words = ""
    prod_cnt = 0
    log3("DEBUG", "genStepsAMZBrowserBrowsePLToBottom...")

    this_step, step_words = genStepCreateData("int", "this_attention_index", "NA", 0, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_adjustment", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "this_attention_count", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "next_attention_index", "NA", pl + "['attention_indices'][0]",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "atBottom", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "print('BROWSING DOWN PRODUCT LIST.....', this_attention_index, next_attention_index)", "", "in_line", "",
        this_step)
    psk_words = psk_words + step_words

    # estimate row height only on the first search result product list page.
    this_step, step_words = genStepCheckCondition(ith + "== 0", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genAMZBrowseProductListEstimateRowHeight(pl, "row_height", "unit_row_scroll", this_step,
                                                                     worksettings)
    psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("int", "row_height", "NA", 500, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("int", "unit_row_scroll", "NA", 3, this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # star a loop to travel to the bottom of the page, along the way, collect product data and see whether we need
    # to go into product details.
    this_step, step_words = genStepLoop("atBottom != True", "", "", "browsePL2Bottom" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # <<<<<comment out for now to speed up test.
    this_step, step_words = genAMZBrowseProductListScrollNearNextAttention(pl, "this_attention_index",
                                                                           "next_attention_index", this_step,
                                                                           worksettings)
    psk_words = psk_words + step_words

    # in case we have passed the last attention, simply scroll to the bottom
    this_step, step_words = genStepCheckCondition(
        "next_attention_index == len(" + pl + "['products']['pl'])-1 and this_attention_count >= len(" + pl + "['attention'])",
        "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genScrollDownUntil(["next", "previous", "need_help", "end_of_page"], "anchor text",
                                               "product_list", "body", this_step, worksettings, "amz")
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # scroll page until the next product's bottom is near bottom 10% of the page height.
    this_step, step_words = genAMZBrowseProductListScrollDownToNextAttention(pl, this_step, worksettings)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('pl_need_attention===>',pl_need_attention)", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    # create a loop to browse attention details...
    this_step, step_words = genStepCreateData("expr", "att_count", "NA", "len(pl_need_attention)", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global att_count, this_attention_count\nthis_attention_count = this_attention_count + att_count\nprint('this_attention_count:', this_attention_count, att_count)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('att_count===>',att_count)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # iterate thru all matched attentions on this page.
    this_step, step_words = genStepLoop("att_count > 0", "", "", "browseAttens" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN enter the product details page.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "pl_need_attention[att_count-1]['loc']",
                                              "expr", "", [0, 0], "center", [0, 0], "box", 1, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "pur", "NA", "pl_need_attention[att_count-1]['purchase']",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "det_lvl", "NA", "pl_need_attention[att_count-1]['detailLvl']",
                                              this_step)
    psk_words = psk_words + step_words

    # "pl_need_attention", "att_count"
    # lvl = atpl + "[" + tbb_index +"]['detailLvl']"
    # purchase = atpl + "[" + tbb_index + "]['purchase']"
    # create a loop here to click into the interested product list. Note: loop is inside genAMZBrowseDetail
    this_step, step_words = genAMZBrowserBrowseDetails("det_lvl", "pur", this_step, worksettings)
    psk_words = psk_words + step_words

    # update li counter
    this_step, step_words = genStepCallExtern(
        "global att_count\natt_count = att_count - 1\nprint('att_count:', att_count)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # check if this attention count is still in range.
    this_step, step_words = genStepCheckCondition(
        "this_attention_count >= 1 and this_attention_count < len(" + pl + "['attention'])", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global att_count, this_attention_index, next_attention_index, this_attention_count\nthis_attention_index = " + pl + "['attention_indices'][this_attention_count-1]\nnext_attention_index = " + pl + "['attention_indices'][this_attention_count]\nprint('this_attention_count:', this_attention_count, this_attention_index, next_attention_index)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("this_attention_count >= len(" + pl + "['attention'])", "", "",
                                                  this_step)
    psk_words = psk_words + step_words

    # we're beyond the attenlist list.

    # if somehow this attention count is bigger than number of attentions, simpley set the next attention index to the last products.
    this_step, step_words = genStepCallExtern(
        "global this_attention_index, next_attention_index\nthis_attention_index = next_attention_index\nnext_attention_index = len(" + pl + "['products']['pl'])-1\nprint('next_attention_index:', next_attention_index, this_attention_index)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # this is the case where this_attention_count == 0, in such a case, this attention index is the first attention index.
    this_step, step_words = genStepCallExtern(
        "global att_count, this_attention_index, next_attention_index, this_attention_count\nnext_attention_index = " + pl + "['attention_indices'][this_attention_count]\nprint('this_attention_count:', this_attention_count, this_attention_index, next_attention_index)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # "this_attention_count >= len("+pl+"['attention'])"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # this_attention_count >= 1 and this_attention_count < len("+pl+"['attention'])
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # next_attention_index == len("+pl+"['products']['pl'])-1 and this_attention_count >= len("+pl+"['attention'])
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # >>> end of comment out for testing.

    # after checking whethere there is anything interesting to click into details page.
    # check whether we have reached the end of the page.

    # this_step, step_words = genAMZBrowseProductListScrollDownMatchProductTest(pl, this_step, worksettings)
    # psk_words = psk_words + step_words

    # need now click into the target product.
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.CLASS_NAME,
                                                        "s-pagination-strip", False, "var",
                                                        "pagination_element", "element_present", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not atBottom", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.CLASS_NAME,
                                                        "s-pagination-strip", False, "var",
                                                        "pagination_element", "element_present", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE BROWSING DOWN PRODUCT LIST.....')", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words

def genStepsAMZBrowserScrollPLToBottom(stepN, worksettings, start):
    psk_words = ""
    log3("DEBUG", "gen_psk_for_scroll_to_bottom...")

    # this bottom is marked by pagination element (even though this is not necessary 100% right)
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.CLASS_NAME,
                                                        "s-pagination-strip", False, "var",
                                                        "pagination_element", "element_present", stepN)
    psk_words = psk_words + step_words

    # simply scroll to
    # pagination_element = driver.find_element(By.CLASS_NAME, "s-pagination-strip")
    this_step, step_words = genStepWebdriverScrollTo("web_driver", "pagination_element", 10, 30, 0.25, "dummy_in", "element_present", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE SCROLL DOWN PRODUCT LIST.....')", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    log3("scroll reached BOTTOM of the page")

    return this_step, psk_words, "down_cnt"

def genStepsAMZBrowserBrowsePLToLastAttention(page_cfg, pl, ith, stepN, worksettings):
    psk_words = ""
    prod_cnt = 0
    log3("DEBUG", "genStepsAMZBrowserBrowsePLToLastAttention...")

    this_step, step_words = genStepCreateData("int", "this_attention_index", "NA", 0, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('BROWSE TO LAST ATTENTION. ', scroll_resolution)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "this_attention_count", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "next_attention_index", "NA", pl + "['attention_indices'][0]",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "reachedLastAttention", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "print('BROWSING DOWN PRODUCT LIST TO LAST ATTENTION.....', this_attention_index, next_attention_index)", "", "in_line", "",
        this_step)
    psk_words = psk_words + step_words

    #unlike screen read version, there is no need to get row height here....

    # star a loop to travel to the bottom of the page, along the way, collect product data and see whether we need
    # to go into product details.
    this_step, step_words = genStepLoop("reachedLastAttention != True", "", "", "browsePL2Bottom" + str(stepN), this_step)
    psk_words = psk_words + step_words


    # scroll page until the next product's bottom is near bottom 10% of the page height.
    this_step, step_words = genStepsAMZBrowserBrowsePLScrollToNextAttention(pl, this_step, worksettings)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('pl_need_attention===>',pl_need_attention)", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    # create a loop to browse attention details...
    this_step, step_words = genStepCreateData("expr", "att_count", "NA", "len(pl_need_attention)", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global att_count, this_attention_count\nthis_attention_count = this_attention_count + att_count\nprint('this_attention_count:', this_attention_count, att_count)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('att_count===>',att_count)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("att_count > 0", "", "", "browseAttens" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN enter the product details page.
    this_step, step_words = genStepWebdriverClick("web_driver", "target_title", "click_result", "click_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "pur", "NA", "pl_need_attention[att_count-1]['purchase']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "det_lvl", "NA", "pl_need_attention[att_count-1]['detailLvl']", this_step)
    psk_words = psk_words + step_words

    # "pl_need_attention", "att_count"
    # lvl = atpl + "[" + tbb_index +"]['detailLvl']"
    # purchase = atpl + "[" + tbb_index + "]['purchase']"
    # create a loop here to click into the interested product list. Note: loop is inside genAMZBrowseDetail
    this_step, step_words = genAMZBrowserBrowseDetails("det_lvl", "pur", this_step, worksettings)
    psk_words = psk_words + step_words

    # update li counter
    this_step, step_words = genStepCallExtern(
        "global att_count\natt_count = att_count - 1\nprint('att_count:', att_count)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end of loop on going thru all attentions found on this screen.
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global this_attention_count, "+pl+"\nprint('num all attentions:', len("+pl+"['attention']), this_attention_count)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("this_attention_count >= len(" + pl + "['attention'])", "", "",
                                                  this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global reachedLastAttention\nreachedLastAttention = True", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global att_count, this_attention_index, next_attention_index, this_attention_count\nthis_attention_index = " + pl + "['attention_indices'][this_attention_count-1]\nnext_attention_index = " + pl + "['attention_indices'][this_attention_count]\nprint('this_attention_count:', this_attention_count, this_attention_index, next_attention_index)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # after checking whethere there is anything interesting to click into details page.
    # check whether we have reached the end of the page.

    # need now click into the target product.
    this_step, step_words = genStepCheckCondition("not reachedLastAttention", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.CLASS_NAME,
                                                        "s-pagination-strip", False, "var",
                                                        "pagination_element", "element_present", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of loop for going thru all designated attention item on this page.
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE BROWSE TO LAST ATTENTION. ')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # we can easily add a few more dumb scroll down actions here.

    return this_step,psk_words


# this would be really easy with webdriver, just scroll to the target.
def genStepsAMZBrowserBrowsePLScrollToNextAttention(pl, stepN, worksettings):
    psk_words = ""

    this_step, step_words = genStepCreateData("boolean", "found_attention", "NA", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('BROWSING PRODUCT LISTS TO NEXT ATTENTION.....')", "",
                                              "in_line", "", this_step)
    psk_words = psk_words + step_words

    # product_title = driver.find_element(By.CSS_SELECTOR, ".s-result-item[data-asin='B0B9SL4F4D'] h2 .a-link-normal")
    # # Scroll into view if necessary (optional)
    # driver.execute_script("arguments[0].scrollIntoView();", product_title)
    # # Click on the product title
    # product_title.click()

    # screen down until either keywords "free deliver" or "previous" reaches. 80% of the screen height from the top. or 20%from the bottom.
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_table", 0, "info_type",
                                                        By.CSS_SELECTOR, ".s-result-item[data-asin='B0B9SL4F4D'] h2 .a-link-normal", True, "var", "target_title",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    # now scroll down and find the menu item.
    # driver.execute_script("arguments[0].scrollIntoView(true);", dropdown_button)
    this_step, step_words = genStepWebdriverScrollTo("web_driver", "target_title", 10, 30, 0.25, "dummy_in",
                                                     "element_present", this_step)
    psk_words = psk_words + step_words


    return this_step, psk_words



# assumption for these steps, the browser should already be in the account's amazon home page (on top)
# or in case of a browse, the browse should already being done and we're at the top of the
# product details page. also buyop is not empty
def genStepsWinChromeAMZBrowserBuy(settings_string, buyop_var_name, buy_result_name, buy_flag_name, stepN):
    psk_words = ""
    # this creates the local private skill file.
    #f = open(homepath+"resource/junk.txt", "a")
    # skill name should be some like: browse_search
    # find out skill ID from mission ID,

    # so check sub steps and act based on which sub step it is.
    site_url = "https://www.amazon.com"
    this_step, step_words = genStepCreateData("int", "buy_step_cnt", "NA", 0, stepN)
    psk_words = psk_words + step_words

    # buyop_var_name = "run_config['searches'][nthSearch]['prodlist_pages'][0]['purchase']"

    this_step, step_words = genStepCreateData("expr", "buy_cmd", "NA", buyop_var_name+"[0]['action']", this_step)
    psk_words = psk_words + step_words

    # loop to go thru each page to be explored....
    this_step, step_words = genStepLoop("buy_step_cnt < len("+buyop_var_name+")", "", "", "amzbuy" + str(stepN), this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("buy_cmd == "+buyop_var_name+"[buy_step_cnt]['action']", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCheckCondition("buy_cmd == 'addCart'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyAddCartSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'pay'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyPaySteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'checkShipping'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyCheckShippingSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'rate'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyGiveRatingSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'feedback'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyGiveFeedbackSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'checkFB'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyCheckFeedbackSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step)
    psk_words = psk_words + step_words

    # end of check condition for checkFB
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of check condition for feedback
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of check condition for rate
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of check condition for checkShipping
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of check condition for pay
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of check condition for addCart
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("buy_step_cnt == buy_step_cnt + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genWinChromeAMZBuyAddCartSteps(settings_string, buy_cmd_name, buy_result_name, buy_flag_name, stepN):
    psk_words = ""

    # check whether this is
    this_step, step_words = genStepAMZPeekAndClick(settings_string, "one_time_purchase", "buy_box_available", "pac_result", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZPeekAndClick(settings_string, "buy_now", "buy_box_available", "pac_result", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearchWordLine("screen_info", "add_to_cart", "expr", "any", "useless", "buy_box_available", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_box_available", "", "", this_step)
    psk_words = psk_words + step_words

    # click on add_to_cart button.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "add_to_cart", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    # set a flag
    this_step, step_words = genStepCreateData("string", "buy_status", "NA", "inCart", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # set a flag
    this_step, step_words = genStepCreateData("string", "buy_status", "NA", "noBuyBox", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words



def genWinChromeAMZBuyPaySteps(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN):
    psk_words = ""

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "orders", "direct", "anchor text", "any", "useless", "on_page_top", "", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("on_page_top", "", "", this_step)
    psk_words = psk_words + step_words

    # click on add_to_cart button, don't use "Cart" since it's not reliable and OCR gets confused by the cart icon.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "orders", "anchor text", "", [0, 0], "right", [1, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # target, flag, prev_result


    this_step, step_words = genStepAMZPeekAndClick(settings_string, "proceed_to_checkout", "check_out_top", "cart_top", this_step)
    psk_words = psk_words + step_words

    # when will we see this page?
    this_step, step_words = genStepAMZPeekAndClick(settings_string, "continue_to_checkout", "in_cart_transition", "pac_result", this_step)
    psk_words = psk_words + step_words

    # there might be a page to to ask you to beceom prime member, need to click on "no thanks" if shows up....
    this_step, step_words = genStepAMZPeekAndClick(settings_string, "no_thanks", "sign_prime_page", "check_out_top", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepAMZPeekAndClick(settings_string, "place_your_order", "pay_page", "check_out_top", this_step)
    # psk_words = psk_words + step_words



    # this_step, step_words = genStepAMZPeekAndClick(settings_string, "place_your_order", "pay_page", "pac_result", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepAMZPeekAndConfirm(settings_string, "order_placed", "pay_page", "pac_result", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZPeekAndClick(settings_string, "review_recent_orders", "pay_page", "pac_result", this_step)
    psk_words = psk_words + step_words

    # set a flag
    this_step, step_words = genStepCreateData("string", "buy_status", "NA", "inCart", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepStub("else", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # set a flag
    # this_step, step_words = genStepCreateData("string", "buy_status", "NA", "noBuyBox", this_step)
    # psk_words = psk_words + step_words

    # this_step, step_words = genStepStub("end condition", "", "", this_step)
    # psk_words = psk_words + step_words

    return this_step, psk_words

def genWinChromeAMZBuyCheckShippingSteps(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN):
    psk_words = ""

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "orders", "direct", "anchor text", "any", "useless", "on_page_top", "", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("on_page_top", "", "", this_step)
    psk_words = psk_words + step_words

    # click on add_to_cart button, don't use "Cart" since it's not reliable and OCR gets confused by the cart icon.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "orders", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))
    hfname = "check_shipping"+dt_string

    this_step, step_words = genStepCreateData("expr", "hf_name", "NA", "'" + hfname + "'+'_'+'" + str(stepN) + "'+'.html'", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "file_save_input", "NA", "['save', sk_work_settings['log_path'], hf_name]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "ctrl,s", "", 4, this_step)
    psk_words = psk_words + step_words

    # save the html file.
    this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_save_input", "fileStatus", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepAmzScrapeBuyOrdersHtml(html_dir, dir_name_type, html_file, 0, outvar, statusvar, this_step)
    # psk_words = psk_words + step_words
    #
    # # search the list against recalled order ID, once found, check deliver status. should make a step
    # this_step, step_words = genStepAmzBuyCheckShipping(orderTBC, orderList, arrived_flag, status, this_step)
    # psk_words = psk_words + step_words

    return this_step, psk_words

def genWinChromeAMZBuyGiveRatingSteps(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN):
    psk_words = ""

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "orders", "direct", "anchor text", "any", "useless",
                                                    "on_page_top", "", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_adjustment", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("on_page_top", "", "", this_step)
    psk_words = psk_words + step_words

    # click on add_to_cart button, don't use "Cart" since it's not reliable and OCR gets confused by the cart icon.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "orders", "anchor text", "",
                                              [0, 0], "center", [0, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "order_id", "NA", buy_cmd_name+"['order_id']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genScrollDownUntil("order_id", "text var", "my_orders", "top", this_step, settings_string, "amz")
    psk_words = psk_words + step_words

    # click on the product which will lead into the product page. click on "write a product review"
    this_step, step_words = genStepAMZPeekAndClick(settings_string, "write_review", "pay_page", "pac_result", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZPeekAndClick(settings_string, "all_star", "pay_page", "pac_result", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words

def genWinChromeAMZBuyGiveFeedbackSteps(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN):
    psk_words = ""
    # now we're in order page, search for the order placed,
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "orders", "direct", "anchor text", "any", "useless",
                                                    "on_page_top", "", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("on_page_top", "", "", this_step)
    psk_words = psk_words + step_words

    # click on add_to_cart button, don't use "Cart" since it's not reliable and OCR gets confused by the cart icon.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "orders", "anchor text", "",
                                              [0, 0], "center", [0, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZPeekAndClick(settings_string, "write_review", "pay_page", "pac_result", this_step)
    psk_words = psk_words + step_words

    #product, instructions, review, result_var, stepN
    # this_step, step_words = genStepObtainReviews("product", "instructions", "review", "review_obtained", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "review", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words




def genStubWinADSAMZWalkSkill(worksettings, stepN):
    log3("GENERATING WinADSAMZWalkSkill======>")

    psk_words = "{"
    site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_amz_browse_search", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSAMZBROWSE001",
                                          "AMZ Browse On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words



def genWinADSAMZBrowserBrowseSearchSkill(worksettings, stepN):
    log3("GENERATING genWinADSAMZBrowserBrowseSearchSkill======>")
    psk_words = "{"
    site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_amz_browser_browse_search", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSAMZBROWSE011",
                                          "AMZ Webdriver Browse On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_amz_home/browser_browse_search", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "open_profile_input", "NA", "[sk_work_settings['batch_profile']]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_resolution", "NA", 250, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "retry_count", "NA", 5, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "mission_failed", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "not_logged_in", "NA", False, this_step)
    psk_words = psk_words + step_words

    # first call subskill to open ADS Power App, and check whether the user profile is already loaded?
    this_step, step_words = genStepUseSkill("open_profile", "public/win_ads_local_open", "open_profile_input", "ads_up", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    # now check the to be run bot's profile is already loaded, do this by examine whether bot's email appears on the ads page.
    # scroll down half screen and check again if nothing found in the 1st glance.
    this_step, step_words = genStepCreateData("expr", "bot_email", "NA", "sk_work_settings['b_email'].split('@')[0]+'@'", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("expr", "bemail", "NA", "sk_work_settings['b_email']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "bpassword", "NA", "sk_work_settings['b_backup_email_pw']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'anchors': [{'anchor_name': 'bot_user', 'anchor_type': 'text', 'template': bot_email, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'bot_open', 'anchor_type': 'text', 'template': 'Open', 'ref_method': '1', 'ref_location': [{'ref': 'bot_user', 'side': 'right', 'dir': '>', 'offset': '1', 'offset_unit': 'box'}]}], 'attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchWordLine("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "no_data", "direct", "anchor text", "any", "useless", "nothing_loaded", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not bot_loaded and not nothing_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    # if not on screen, scroll down and check again.
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 80, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'anchors': [{'anchor_name': 'bot_user', 'anchor_type': 'text', 'template': bot_email, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'bot_open', 'anchor_type': 'text', 'template': 'Open', 'ref_method': '1', 'ref_location': [{'ref': 'bot_user', 'side': 'right', 'dir': '>', 'offset': '1', 'offset_unit': 'box'}]}], 'attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchWordLine("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "no_data", "direct", "anchor text", "any", "useless", "nothing_loaded", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # if not found, call the batch load profile subskill to load the correct profile batch.
    this_step, step_words = genStepCheckCondition("not bot_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "profile_name", "NA", "os.path.basename(sk_work_settings['batch_profile'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "profile_name_path", "NA", "os.path.dirname(sk_work_settings['batch_profile'])", this_step)
    psk_words = psk_words + step_words

    # due to screen real-estate, some long email address might not be dispalyed in full, but usually
    # it can display up until @ char on screen, so only use this as the tag.
    this_step, step_words = genStepCreateData("expr", "bot_email", "NA", "sk_work_settings['b_email'].split('@')[0]+'@'", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "full_site", "NA", "sk_work_settings['full_site'].split('www.')[1]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "machine_os", "NA", "sk_work_settings['platform']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "batch_import_input", "NA", "['open', profile_name_path, profile_name, bot_email, full_site, machine_os]", this_step)
    psk_words = psk_words + step_words

    # once the correct user profile is loaded, the open button corresponding to the user profile will be clicked to open the profile.
    this_step, step_words = genStepUseSkill("batch_import", "public/win_ads_local_load", "batch_import_input", "browser_up", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", " ", True, "screen_info", "bot_open", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # wait 9 seconds for the browser to be brought up.
    this_step, step_words = genStepWait(5, 1, 3, this_step)
    psk_words = psk_words + step_words

    # following is for tests purpose. hijack the flow, go directly to browse....
    # this_step, step_words = genStepGoToWindow("SunBrowser", "", "g2w_status", this_step)
    # this_step, step_words = genStepGoToWindow("Chrome", "", "g2w_status", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 1, 3, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genAMZLoginInSteps(this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not_logged_in == False", "", "", this_step)
    psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepWait(1, 0, 0, this_step)
    # psk_words = psk_words + step_words

    #now call the amz chrome browse sub-skill to go thru the walk process.
    this_step, step_words = genStepsWinChromeAMZBrowserWalk("sk_work_settings", this_step)
    psk_words = psk_words + step_words

    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # close the browser and exit the skill, assuming at the end of genWinChromeAMZWalkSteps, the browser tab
    # should return to top of the amazon home page with the search text box cleared.
    this_step, step_words = genStepKeyInput("", True, "alt,f4", "", 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("mission_failed == False", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepGoToWindow("AdsPower", "", "g2w_status", this_step)
    psk_words = psk_words + step_words

    # in case mission executed successfully, save profile, kind of an overkill or save all profiles, but simple to do.
    this_step, step_words = genStepsADSPowerExitProfile(worksettings, this_step)
    psk_words = psk_words + step_words

    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_amz_home/browser_browse_search", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words



def genAMZBrowserBrowseDetails(lvl, purchase, stepN, worksettings):
    psk_words = ""
    log3("DEBUG", "genAMZBrowserBrowseDetails...")

    # now, starts to browse into the product details page.......................................
    this_step, step_words = genStepCreateData("bool", "end_of_detail", "NA", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('START BROWSING DETAILS')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_adjustment", "NA", 0, this_step)
    psk_words = psk_words + step_words



    #now hover mouse over image icons to view images.
    # this_step, step_words = genAMZBrowseDetailsViewImages(worksettings, this_step)
    # psk_words = psk_words + step_words

    #scroll to the the review section. this is quick
    # reviews_header = driver.find_element(By.XPATH, "//h3[@data-hook='dp-local-reviews-header']")


    #if there is purchase action, save the page, scrape it and confirm the title, store, ASIN, price, feedbacks, rating.
    this_step, step_words = genStepCheckCondition("len("+purchase+") != 0", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("from datetime import datetime\nglobal hf_name\nhf_name= 'pd'+ str(int(datetime.now().timestamp()))+'.html'\nprint('hf_name:',hf_name,datetime.now())", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # this_step, step_words = genStepCreateData("expr", "hf_name", "NA", "'" + hfname + "'+'.html'", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "file_save_input", "NA",
                                              "['save', sk_work_settings['log_path'], hf_name]", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # now go thru review browsing....... based on specified detail level.
    this_step, step_words = genStepCreateData("bool", "rv_expandable", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "no_reviews", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('BROWSING PRODUCT DETAILS.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("expr", "detail_level", "NA", lvl, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global detail_level\nprint('detail_level: ', detail_level)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCallExtern("global detail_level, "+tbb_index+"\ndetail_level = "+lvl, "", "in_line", "", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "buy_ops", "NA", purchase, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global buy_ops\nprint('buy_ops: ', buy_ops)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # expandables_count = 0
    this_step, step_words = genStepCreateData("int", "expandables_count", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # if detail level == 1:
    #       max_expandables = 3
    # else:
    #       max_expandables = 0
    this_step, step_words = genStepCheckCondition("detail_level == 1", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "max_expandables", "NA", 2, this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "max_expandables", "NA", 5, this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # see_more_reviews_link = driver.find_element(By.XPATH, "//a[@data-hook='see-all-reviews-link-foot']")
    #
    # # Click on the link if it is found
    # see_more_reviews_link.click()

    # no_reviews_span = driver.find_element(By.XPATH, "//span[@data-hook='top-customer-reviews-title']")
    #
    # # Check if the text is "No customer reviews"
    # if no_reviews_span.text == "No customer reviews":
    #     print("Detected: No customer reviews")

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["see_all_reviews", "see_more_reviews", "no_customer_reviews", "conditions_of_use"], "direct", ["anchor text", "anchor text", "anchor text", "anchor text"], "any", "see_reviews", "end_of_detail", "amz", False, this_step)
    psk_words = psk_words + step_words

    # browse all the way down, until seeing "No customer reviews" or "See all reviews"
    this_step, step_words = genStepLoop("end_of_detail != True", "", "", "browseDetails"+str(stepN+1), this_step)
    psk_words = psk_words + step_words

    #(action, screen, amount, unit, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "top", this_step, None)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearchAnchorInfo("screen_info", "read_more", "direct", "anchor text", "any", "rv_expanders", "rv_expandable", "amz", False, this_step)
    psk_words = psk_words + step_words

    # while end of detail not reached:
    #   scroll down 1/2 screen
    #   extract screen
    #   search expandables
    #   while expandables_count < max_expandables:
    #       if expandables found == True:
    #           click on expandable
    #           expandables_count = expandables_count + 1
    #           extract info again after click
    #           search expandable again
    #       else:
    #           search for end of details
    #           if end_of_detail == True:
    #               expandables_count = max_expandables
    #           else:
    #               scroll down 1/2 screen.
    #               extract screen info
    #               search expandable again
    #           endif
    #
    #   search for end of details
    this_step, step_words = genStepLoop("expandables_count < max_expandables", "", "", "browseDetails"+str(stepN+1), this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCheckCondition("rv_expandable == True", "", "", this_step)
    psk_words = psk_words + step_words


    # # click into "Read more"
    this_step, step_words = genStepMouseClick("Single Click", "", False, "screen_info", "read_more", "anchor text", "", [0, 0], "center", [0, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global expandables_count\nexpandables_count = expandables_count + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # after click on "Read more", capture screen again, at this time "Read More" should have dissappear, if there is more, then
    # let the loop takes care of it, if there is no more "Read More" on screen, scroll down a screen....
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "bottom", this_step, None)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearchAnchorInfo("screen_info", "read_more", "direct", "anchor text", "any", "rv_expanders", "rv_expandable", "amz", False, this_step)
    psk_words = psk_words + step_words

    #close bracket for if rv_expandable == True
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["see_all_reviews", "see_more_reviews", "no_customer_reviews", "conditions_of_use"], "direct", ["anchor text", "anchor text", "anchor text", "anchor text"], "any", "see_reviews", "end_of_detail", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("end_of_detail == True", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global expandables_count, max_expandables\nexpandables_count = max_expandables", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepWait(1, 0, 0, this_step)
    # psk_words = psk_words + step_words


    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "bottom", this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "read_more", "direct", "anchor text", "any", "rv_expanders", "rv_expandable", "amz", False, this_step)
    psk_words = psk_words + step_words

    # # close bracket: end_of_detail == True
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # close for loop: expandables_count < max_expandables, finished click on all expandables on this screen.
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["see_all_reviews", "see_more_reviews", "no_customer_reviews", "conditions_of_use"], "direct", ["anchor text", "anchor text", "anchor text", "anchor text"], "any", "see_reviews", "end_of_detail", "amz", False, this_step)
    psk_words = psk_words + step_words


    # close for loop: end_of_detail != True
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["back_to_top", "conditions_of_use"], "direct", ["anchor text", "anchor text"], "any", "useless", "end_of_page", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not end_of_page", "", "", this_step)
    psk_words = psk_words + step_words

    # # check for whether we have reached end of product details. page.
    # # for level 1 details, will view all the way till the end of reviews
    # # for level 2 details, will view till end of all reviews and open hidden long reviews along the way (click on "see all").
    # # but if this product has no review or has all short reviews where there is no "see all", then this is equivalent to
    # # level 1
    this_step, step_words = genStepCheckCondition("detail_level >= 2 and not no_reviews", "", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepWait(1, 0, 0, this_step)
    # psk_words = psk_words + step_words

    # # for level 3 and beyond details, will click into read all reviews and examine all reviews
    # # ncv = number of customer review
    # # pseudo code:
    # #   if (ncv == None) {
    # #     click on see all reviews.
    # #     gen steps to browse all reviews.
    # #   } else {
    # #    set flag done.
    # #   }
    #
    # this_step, step_words = genStepCheckCondition("len[ncv] == 0", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # for level 3 details, click on see_all_reviews and
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "see_reviews[0]['loc']", "expr", "", 0, "center", [0, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words
    # #
    # # # go into all reviews.
    # # # this_step, step_words = genStepAMZBrowseReviews("screen_info", lvl, this_step)
    this_step, step_words = genAMZBrowseAllReviewsPage("detail_level", this_step, worksettings)
    psk_words = psk_words + step_words

    #
    # this_step, step_words = genStepStub("else", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # set flag to mark the end of the product detail browsing....
    # this_step, step_words = genStepFillData("direct", "True", "detail_done", "", stepN)
    # psk_words = psk_words + step_words
    #
    # # close on check len(ncv)
    # this_step, step_words = genStepStub("end condition", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # close on check level <= 2
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    #==== Now that we have completed browsing the product details page. ========
    # check whether there is an buy action here, if there is, scroll to top and perform the buy actions.
    # purchase = page_cfg + "['products'][li]['purchase']"
    this_step, step_words = genStepCheckCondition("len(buy_ops) >  0", "", "", this_step)
    psk_words = psk_words + step_words

    # scroll to top
    # pagesize, stepN, worksettings, page, sect
    this_step, step_words = genAMZScrollProductDetailsToTop([0, 0], this_step, worksettings)
    psk_words = psk_words + step_words


    # if action is add-to-cart, then click on add-to-cart
    this_step, step_words = genWinChromeAMZBuySteps("sk_work_settings", "buy_ops", "buy_result", "buy_step_flag",this_step)
    psk_words = psk_words + step_words

    # close on check purchase + "[0] == 'add cart'"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # close on len(buy_ops) >  0
    # this_step, step_words = genStepStub("end condition", "", "", this_step)
    # psk_words = psk_words + step_words

    # back to produc list page...
    # now go back to the previous browser page. by press alt-left
    this_step, step_words = genStepKeyInput("", True, "alt,left", "", 3, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("print('DONE BROWSING PRODUCT DETAILS.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    return this_step,psk_words


def genAMZBrowseDetailsViewImages(settings_var_name, stepN):
    #simply move the mouse pointer around to simulate viewing images.
    psk_words = ""

    # main_image = driver.find_element(By.ID, "landingImage")
    # thumbnails = driver.find_elements(By.CSS_SELECTOR, ".a-button-thumbnail img, .imageThumbnail img")
    #
    # # Hover over each thumbnail image found
    # for thumbnail in thumbnails:
    #     actions.move_to_element(thumbnail).perform()
    #     time.sleep(1)  # Brief pause to observe hover effect
    # asin_row = driver.find_element(By.XPATH, "//tr[th[contains(text(), 'ASIN')]]")
    #
    # # Locate the <td> element within that row and extract the ASIN text
    # asin_value = asin_row.find_element(By.CLASS_NAME, "prodDetAttrValue").text


    return this_step, psk_words


def genStepsAMZBrowserScrollDownSome(n_word, stepN):
    psk_words = ""

    this_step, step_words = genStepCreateData("expr", "nscroll", "NA", n_word, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nscroll > 0", "", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 2,
                                               False, this_step)
    psk_words = psk_words + step_words

    # decrement loop counter.
    this_step, step_words = genStepCallExtern("global nscroll\nnscroll = nscroll - 1\nprint('nscroll:', nscroll)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step,psk_words


def genAMZBrowseDetailsScrollPassReviews(settings_var_name, stepN):
    psk_words = ""

    this_step, step_words = genStepCreateData("string", "scrn_position", "NA", "before", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("scrn_position != 'on' and scrn_position != 'after'", "", "", "", this_step)
    psk_words = psk_words + step_words

    # scroll 5 full screen worth of contents
    this_step, step_words = genStepsAMZBrowserScrollDownSome("5", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "bottom", this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAmzDetailsCheckPosition("screen_info", "reviewed", "scrn_position", "position_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    return this_step,psk_words

# extract review information from the current screen.
def genExtractReview(scrn, stepN):
    # there are better ways to do this, like reading directly from html, so not going to do this the dumb way...
    log3("nop")

# this function generate code to scroll N pages of full reviews.
def genAMZBrowseAllReviewsPage(level, stepN, settings_var_name):
    # now simply scroll down to the end, there is not even review expansion to click on.... since all are
    # fully expanded anyways.
    # now the question is whether to scroll all the way till the end? or end the scroll by either by # of
    # reviews or number of words.....
    # or even simpler, simply do randome # of scrolls, but need to get to the bottom anyways if need to advance
    # to the next page?
    # OK decided, will flip through
    # SC - 2023-06-09, pseudo code:
    # if level is even number, will scoll down some then back up to view some bad reviews, or if level is odd number
    # will directly scroll thru some bad reviews and then go back....
    psk_words = ""
    #
    this_step, step_words = genStepCreateData("expr", "nNRP", "NA", "random.randint(1, 5)", stepN)
    psk_words = psk_words + step_words

    #
    this_step, step_words = genStepCreateData("expr", "nPRP", "NA", "random.randint(3, 7)", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "nPRP_up", "NA", "nPRP+3", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('BROWSE ALL REVIEWS.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nNRP, nPRP, nPRP_up\nprint('nNRP, nPRP, nPRP_up:', nNRP, nPRP, nPRP_up)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('LLlevel:', int(" + level + ")%2)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # extract screen info,
    # one_star_link = driver.find_element(By.CSS_SELECTOR, "a.histogram-row-container[aria-label*='1 stars']")
    # one_star_link.click()

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.CSS_SELECTOR, "a.histogram-row-container[aria-label*='1 stars']", False, "var", "correct_carrier_option", "element_present", this_step)
    psk_words = psk_words + step_words


    #         correct_carrier_option.click()
    this_step, step_words = genStepWebdriverClick("web_driver", "correct_carrier_option", "click_result", "click_flag", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCheckCondition("int(" + level + ")%2 == 0", "", "", this_step)
    psk_words = psk_words + step_words

    # do some overall review scroll, should be mostly positive.
    this_step, step_words = genStepLoop("nPRP > 0", "", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 70, "screen", "scroll_resolution", 0, 0, 2, False, this_step)
    psk_words = psk_words + step_words

    # decrement loop counter.
    this_step, step_words = genStepCallExtern("global nPRP\nnPRP = nPRP - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nPRP_up > 0", "", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 2, False, this_step)
    psk_words = psk_words + step_words

    # decrement loop counter.
    this_step, step_words = genStepCallExtern("global nPRP_up\nnPRP_up = nPRP_up - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # scroll back up to the top.
    # end bracket for if int(level)%2 == 0
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "all_critical_reviews", "direct", "anchor text", "any", "useless", "hasNegativeReviews", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("hasNegativeReviews", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", False, "screen_info", "all_critical_reviews", "anchor text", "", [0, 0], "center", [0, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # click on 1 star
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "one_star", "direct", "anchor text", "any",
                                                    "useless", "hasNegativeReviews", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("hasNegativeReviews", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", False, "screen_info", "one_star", "anchor text", "",
                                              [0, 0], "center", [0, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now scroll back to top, no need really
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # now scroll back to top, no need really
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepLoop("nNRP > 0", "", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # wait - sort of equivalent to screen read time
    this_step, step_words = genStepWait(0, 1, 3, this_step)
    psk_words = psk_words + step_words

    # decrement loop counter.
    this_step, step_words = genStepCallExtern("global nNRP\nnNRP = nNRP - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    # now simply go back to the previous browser page. by press alt-left
    this_step, step_words = genStepKeyInput("", True, "alt,left", "", 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", settings_var_name, "screen_info", "all_reviews", "top", this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "sort_by", "direct", "anchor text", "any",
                                                    "useless", "onReviewsPageTop", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("onReviewsPageTop", "", "", this_step)
    psk_words = psk_words + step_words

    # we're here due to clicking on 1 star，so back one more time to get back to product details page
    this_step, step_words = genStepKeyInput("", True, "alt,left", "", 3, this_step)
    psk_words = psk_words + step_words

    # now scroll back to top, no need really
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("print('DONE BROWSE ALL REVIEWS.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genScroll1StarReviewsPage(stepN, start):
    psk_words = ""
    log3("DEBUG", "genBrowse1StarReviewsPage...")

    # create loop count var
    lcvarname = "scroll1Star" + str(stepN)
    this_step, step_words = genStepCreateData("int", lcvarname, "NA", 0, stepN)
    psk_words = psk_words + step_words

    # give it a random value between 15 and 25 - magic number .  that's how many scrolls will have
    rand_count = random.randrange(3, 10)

    # genStepLoop(condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("", str(rand_count), "", lcvarname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # wait - sort of equivalent to screen read time
    this_step, step_words = genStepWait(0, 1, 3, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    log3("scroll reached BOTTOM of the page")

    return this_step, psk_words, rand_count

# go thru product_details["dimensions"]
# product_details["dimensionsDisplayType"] will guide the types of display methods or the variations, could be:
#  "swatch" : icons, "dropdown" : dropdown list, "singleton" : single choice, "unavailable", "etdd","vodd"
# so the strategy is:
# 1) go thru product_details["variationDisplayLabels"], key is vairation name, value is variation displayed text.
#    find the txt on screen, scroll so that it's on 30% from top of screen,
# 2) based on display type and #of variation values, if swatch, simply search oct shapes below variation display text. can speed up by
#                                                       using target variation's index to find the box center. and hover over to
#                                                       double confirm.
#                                                    if dropdown, then click on drop down menu and seach selection, scroll if needed.
#    after selection,
def genAMZBuySelectVariations(pd_var_name, stepN):
    psk_words = ""

    this_step, step_words = genStepCreateData("expr", "n_var", "NA", "len("+pd_var_name+"['dimensions'])", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "var_txt", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "var_name", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "next_var_name", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "var_index", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "var_target_txt", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "next_var_target_txt", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "var_target_index", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "n_var_choices", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_cnt", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_adjustment", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "var_display_type", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("boolean", "var_target_found", "NA", False, this_step)
    psk_words = psk_words + step_words

    # genStepLoop(condition, count, end, lc_name, stepN):
    his_step, step_words = genStepLoop("n_var > 0", "", "", "selVar" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("var_name = "+pd_var_name+"['dimensions'][var_index]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("var_txt = "+pd_var_name+"['variationDisplayLabels'][var_name]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("var_target_txt = "+pd_var_name+"['variationTargets'][var_name]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("var_target_index = "+pd_var_name+"['variationTargetsIndex'][var_name]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("n_var_choices = len("+pd_var_name+"['variationValues'][var_name])", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # dropdown = driver.find_element(By.ID, "native_dropdown_selected_size_name")
    # select = Select(dropdown)

    # # Extract and print the available size options
    # for option in select.options:
    #     size_text = option.text.strip()
    #     asin = option.get_attribute("value").split(",")[1] if "," in option.get_attribute("value") else "N/A"
    #     print(f"Size: {size_text}, ASIN: {asin}")
    #
    # # 2. Click on the dropdown to reveal options
    # dropdown.click()
    # sleep(1)  # Allow

    # button = driver.find_element(By.ID, "a-autoid-16-announce")
    # button.click()
    # print("Button clicked successfully.")




    this_step, step_words = genStepCheckCondition("var_display_type == 'dropdown'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.XPATH, "//span[text()='{correct_carrier}']/ancestor::button", False, "var", "correct_carrier_option", "element_present", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "var_txt", "var name", "", "1", "0", "bottom", "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    his_step, step_words = genStepLoop("(not var_target_found) and (scroll_cnt < 10)", "", "", "findVar" + str(stepN), this_step)
    psk_words = psk_words + step_words



    # if this is the last var, then the next var will be bottom of the page.
    this_step, step_words = genStepCheckCondition("var_index < len("+pd_var_name+"['dimensions'])-1", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("next_var_name = "+pd_var_name+"['dimensions'][var_index+1]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("next_var_target_txt = "+pd_var_name+"['variationTargets'][next_var_name]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    #'BOS' stands for bottom of the screen
    this_step, step_words = genStepCallExtern("next_var_target_txt = 'BOS'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCheckCondition("var_target_found", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.XPATH, "//span[text()='{correct_carrier}']/ancestor::button", False, "var", "correct_carrier_option", "element_present", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverClick("web_driver", "correct_carrier_option", "click_result", "click_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 2, "raw", "scroll_resolution", 0, 2, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("scroll_cnt = scroll_cnt + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("var_display_type == 'swatch'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("search_indices = [var_target_index, var_target_index-1, var_target_index+1, var_target_index-2, var_target_index+2, var_target_index-3, var_target_index+3, var_target_index-4, var_target_index+4]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'anchors': [{'anchor_name': 'this_var', 'anchor_type': 'text', 'template': var_target_txt, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'next_var', 'anchor_type': 'text', 'template': next_var_target_txt, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'swatch', 'anchor_type': 'polygon', 'template': '', 'ref_method': '1', 'ref_location': [{'ref': 'this_var', 'side': 'bottom', 'dir': '>', 'offset': '0', 'offset_unit': 'box'}]}, {'ref': 'this_var', 'side': 'right', 'dir': '>', 'offset': '-1', 'offset_unit': 'box'}]}, {'ref': 'next_var', 'side': 'top', 'dir': '<', 'offset': '0', 'offset_unit': 'box'}]}, {'ref': 'quantity', 'side': 'left', 'dir': '>', 'offset': '0', 'offset_unit': 'box'}]}], 'attention_area':[0.35, 0, 0.85, 1], 'attention_targets':['@all']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # first figure out n row and n columns of all selection icons
    # button = driver.find_element(By.ID, "a-autoid-16-announce")
    # button.click()

    # then extrapolate the target‘s row number and column number， also calculate out the neighbors to hover over to check
    # in case something wrong, basically go 2 to left and 2 to the right，
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.XPATH, "//span[text()='{correct_carrier}']/ancestor::button", False, "var", "correct_carrier_option", "element_present", this_step)
    psk_words = psk_words + step_words

    his_step, step_words = genStepLoop("(not var_target_found) and (scroll_cnt < 10)", "", "", "findVar" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # then hover over to the center of the icon，then extract and double check the selection text is there，
    # if not, hover neighbors to double check
    this_step, step_words = genStepWebdriverClick("web_driver", "correct_carrier_option", "click_result", "click_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.XPATH, "//span[text()='{correct_carrier}']/ancestor::button", False, "var", "correct_carrier_option", "element_present", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "var_target_text", "direct", "shape", "any", "swatch_icons", "var_target_found", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("var_target_found", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverClick("web_driver", "correct_carrier_option", "click_result", "click_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("scroll_cnt = swatch_icons[search_indices[scroll_cnt + 1]]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("scroll_cnt = scroll_cnt + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # now scroll back to top, no need really
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # now scroll back to top, no need really
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words



    # update loop counter
    this_step, step_words = genStepCallExtern("n_var = n_var - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("var_index = var_index + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    return this_step, psk_words