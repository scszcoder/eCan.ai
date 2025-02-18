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
from bot.browserGmailSkill import genWinADSGmailBrowserRefreshSkill
import math
import itertools
import json
import traceback
from bot.basicSkill import DEFAULT_RUN_STATUS
from bot.Logger import log3
from bot.amzBuyerSkill import genStepsAMZLoginIn
from bot.adsPowerSkill import genStepsADSPowerExitProfile, genStepsADSPowerObtainLocalAPISettings, \
    genStepADSSaveAPISettings, genStepsADSBatchExportProfiles
from bot.adsAPISkill import genStepAPIADSListProfiles, genStepAPIADSStopProfile, \
    genStepAPIADSCheckProfileBrowserStatus

import utils.logger_helper

# the flow is adapted from the same routine in amzBuyerSkill
# except all screen read becomes in-browser webdriver based read which is much much easier...
def genStepsWinChromeAMZBrowserWalk(worksettings, stepN):
    try:
        psk_words = ""

        this_step, step_words = genStepCreateData("expr", "run_config", "NA", "sk_work_settings['run_config']", stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "numSearchs", "NA", "len(run_config['searches'])", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "nthSearch", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepLoop("nthSearch < numSearchs", "", "", "search" + str(stepN), this_step)
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
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.LINK_TEXT, ':top_menu_item', True, "var", "top_menus", "extract_flag", this_step)
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

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-hamburger-menu', False, "var", "all_menu", "extract_flag", this_step)
        psk_words = psk_words + step_words
        #
        # time.sleep(2)  # Wait for the menu to expand
        #
        # # (Optional) Find and interact with a submenu item
        # # Example: Click on "Echo & Alexa" submenu inside the "All" menu
        # submenu_item = driver.find_element(By.LINK_TEXT, "Echo & Alexa")
        # submenu_item.click()
        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.LINK_TEXT, 'nav-hamburger-menu', False, "var", "all_menu", "extract_flag", this_step)
        # psk_words = psk_words + step_words


        this_step, step_words = genStepCheckCondition(
            "run_config['searches'][nthSearch]['entry_paths']['type'] == 'Left main menu'", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type",
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
        this_step, step_words = genStepCreateData("obj", "action_result", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "action_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
                                                            'twotabsearchtextbox', False, "var", "search_box",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "search_phrase", "NA", "yoga ball", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global search_phrase, nthSearch, run_config\nsearch_phrase= run_config['searches'][nthSearch]['entry_paths']['words']", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverKeyIn("web_driver", "search_box", "search_phrase", "action_result",
                                                      "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
                                                            'nav-search-submit-button', False, "var", "search_button",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "search_button", "action_result", "action_flag",
                                                      this_step)
        psk_words = psk_words + step_words

        # now wait for search results to load.

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.CSS_SELECTOR,
                                                            'span.s-pagination-strip', False, "var", "pagination",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words





        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-cart', False, "var", "top_cart", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-orders', False, "var", "returns_and_orders", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-link-accountList', False, "var", "account_list", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.LINK_TEXT, 'Account', False, "var", "account_menu_item", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.LINK_TEXT, 'Sign In', False, "var", "sign_in_menu_item", "extract_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global search_term, nthSearch, run_config\nsearch_term = run_config['searches'][nthSearch]['entry_paths']['words']\nprint('search_term', search_term)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words



        # html_file_name, root, result_name, stepN):
        this_step, step_words = genStepCallExtern("print('run entry_paths words', run_config['searches'][nthSearch])", "",
                                                  "in_line", "", this_step)
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

        # make sure this is a direct buy
        this_step, step_words = genStepsBrowserPerformBuyRelated("sk_work_settings", "search_buy", this_step)
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
        this_step, step_words = genStepLoop("nthPLPage < numPLPages", "", "", "search" + str(stepN), this_step)
        psk_words = psk_words + step_words

        # process flow type, and browse the 1st page.
        this_step, step_words = genStepCreateData("expr", "flows", "NA",
                                                  "run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage]['flow_type'].split(' ')",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('flows:', flows, 'numPLPages:', numPLPages, 'nthSearch:', nthSearch, 'nthPLPage:', nthPLPage)", "", "in_line", "", this_step)
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

        # find and click on "next" in the pagination strip to go to the next search result page.
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, 'a.s-pagination-next', False, "var", "next_button", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, 'a.s-pagination-previous', False, "var", "previous_button", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "next_button", "action_result", "action_flag", this_step)
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
        this_step, step_words = genStepCheckCondition("len() > 0", "", "", this_step)
        psk_words = psk_words + step_words

        #buyop_var_name = "run_config['searches'][nthSearch]['prodlist_pages'][0]['purchase']"
        this_step, step_words = genStepCreateData("obj", "buy_actions", "NA", None, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global buy_actions\nbuy_actions = run_config['searches'][nthSearch]['prodlist_pages'][0]['purchase']\nprint('buy_actions: ', buy_actions)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepsBrowserPerformBuyRelated(worksettings, "buy_actions", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        log3("DEBUG", "ready to add stubs...." + psk_words)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinChromeAMZBrowserWalk: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinChromeAMZBrowserWalk: {ex_stat}")

    return this_step, psk_words


# assume we're on amazon site. first - make sure we're on the top of the page, if not scroll to it.
def genStepsBrowserPerformBuyRelated(settings_var_name, buy_var_name, stepN):
    try:
        psk_words = ""

        this_step, step_words = genStepsAMZBrowserScrollProductListToTop(stepN)
        psk_words = psk_words + step_words

        # at this point, we should be on top of the amazon page, so that we can now click into returns&orders or Cart depends on the buy action
        this_step, step_words = genStepsWinChromeAMZBrowserBuy(settings_var_name, buy_var_name, "buy_result", "buy_step_flag", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsBrowserPerformBuyRelated: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsBrowserPerformBuyRelated: {ex_stat}")
    return this_step, psk_words


def genStepsBrowserDirectBuy(settings_var_name, buy_var_name, stepN):
    try:
        psk_words = ""

        this_step, step_words = genStepsAMZBrowserScrollProductListToTop(stepN)
        psk_words = psk_words + step_words

        # at this point, we should be on top of the amazon page, so that we can now click into returns&orders or Cart depends on the buy action
        this_step, step_words = genStepsWinChromeAMZBrowserBuy(settings_var_name, buy_var_name, "buy_result", "buy_step_flag", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsBrowserDirectBuy: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsBrowserDirectBuy: {ex_stat}")

    return this_step, psk_words



def genStepsAMZBrowserScrollProductListToTop(stepN):
    try:
        psk_words = ""
        log3("DEBUG", "gen_psk_for_scroll_to_top...")


        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-cart', False, "var", "top_cart", "extract_flag", stepN)
        psk_words = psk_words + step_words

        # simply scroll to cart that's all there is.....
        this_step, step_words = genStepWebdriverScrollTo("web_driver", "top_cart", 10, 30, 0.25, "dummy_in","element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('DONE SCROLL UP PRODUCT LIST.....')", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        log3("scroll reached TOP of the page")

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserScrollProductListToTop: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserScrollProductListToTop: {ex_stat}")

    return this_step,psk_words


def genStepsAMZBrowserScrollPDToTop(stepN):
    try:
        psk_words = ""
        log3("DEBUG", "genStepsAMZBrowserScrollPDToTop...")


        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-cart', False, "var", "top_cart", "extract_flag", stepN)
        psk_words = psk_words + step_words

        # easy act, just scroll to the top menu, with cart button
        this_step, step_words = genStepWebdriverScrollTo("web_driver", "top_cart", 10, 30, 0.25, "dummy_in",
                                                         "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('DONE SCROLL PRODUCT DETAILS TO TOP.....')", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        log3("scroll reached TOP of the product details page")

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserScrollPDToTop: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserScrollPDToTop: {ex_stat}")

    return this_step,psk_words


def genStepsAMZBrowserBrowseProductLists(pageCfgsName, ith, lastone, flows, stepN, worksettings):
    try:
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


        this_step, step_words = genStepAMZBrowserScrapePL("web_driver", "plSearchResult", ith, pageCfgsName, "action_flag", this_step)
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


        this_step, step_words = genStepAMZBrowserScrapePL("web_driver", "plSearchResult", ith, pageCfgsName, "action_flag", this_step)
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

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserBrowseProductLists: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserBrowseProductLists: {ex_stat}")

    return this_step, psk_words




def genStepsAMZBrowserBrowsePLToBottom(page_cfg, pl, ith, stepN, worksettings):
    try:
        psk_words = ""
        prod_cnt = 0
        log3("DEBUG", "genStepsAMZBrowserBrowsePLToBottom...")

        this_step, step_words = genStepCreateData("int", "this_attention_index", "NA", 0, stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "scroll_adjustment", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "this_attention_count", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "near_offset", "NA", 0, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("integer", "next_attention_index", "NA", -1, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCheckCondition("len(" + pl + "['attention_indices'])> 0", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global near_offset\nnear_offset = random.randint(4, 8)\nprint('near_offset:', near_offset)", "", "in_line", "",
            this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition(pl + "['attention_indices'][0] > near_offset", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("expr", "next_attention_index", "NA", pl + "['attention_indices'][0] - near_offset", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("expr", "next_attention_index", "NA", pl + "['attention_indices'][0]", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("bool", "atBottom", "NA", False, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "attention_title_txt", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "found_titles", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "print('BROWSING DOWN PRODUCT LIST.....', this_attention_index, next_attention_index)", "", "in_line", "",
            this_step)
        psk_words = psk_words + step_words

        # estimate row height only on the first search result product list page.
        this_step, step_words = genStepCheckCondition(ith + "== 0", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # star a loop to travel to the bottom of the page, along the way, collect product data and see whether we need
        # to go into product details.
        this_step, step_words = genStepLoop("atBottom != True", "", "", "browsePL2Bottom" + str(stepN), this_step)
        psk_words = psk_words + step_words

        # <<<<<comment out for now to speed up test.
        this_step, step_words = genStepsAMZBrowseScrollNearNextAttention(pl, "this_attention_index", "next_attention_index", this_step, worksettings)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('this_attention_count',this_attention_count, len(" + pl + "['products']['pl']), len(" + pl + "['attention']))", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # in case we have passed the last attention, simply scroll to the bottom
        this_step, step_words = genStepCheckCondition(
            "next_attention_index == len(" + pl + "['products']['pl'])-1 and this_attention_count >= len(" + pl + "['attention'])",
            "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "span.navFooterBackToTopText", False, "var", "bottom_header", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverScrollTo("web_driver", "bottom_header", 10, 30, 0.25, "dummy_in", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        #now scroll to the target item.
        this_step, step_words = genStepCallExtern(
            "global next_attention_index\nnext_attention_index = " + pl + "['attention_indices'][0]\nprint('next_attention_index::',next_attention_index)", "", "in_line", "",
            this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global next_attention_index, target_title_txt, "+pl+"\ntarget_title_txt = " + pl + "['products']['pl'][next_attention_index]['summery']['title']\nprint('target_title_txt::',target_title_txt)", "", "in_line", "",
            this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "title_elements", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "attention_title_texts", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "pl_need_attention", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, 'h2.a-size-mini.a-spacing-none.a-color-base.s-line-clamp-4 a', True, "var", "title_elements", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global found_titles, target_title_txt, title_elements\nattention_titles= [te for te in title_elements if te.text in target_title_txt]", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global attention_titles, attention_title_texts\nattention_title_texts= [te.text for te in attention_titles]\nprint('attention_title_texts:',attention_title_texts)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words



        this_step, step_words = genStepCheckCondition("len(found_titles) > 0", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global target_title, found_titles\ntarget_title = found_titles[0]\nprint('target_title::',target_title)", "", "in_line", "",
            this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverScrollTo("web_driver", "target_title", 10, 30, 0.25, "dummy_in", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern(
            "global this_attention_count\nthis_attention_count = this_attention_count + 1\nprint('this_attention_count:', this_attention_count)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        # click to the next target.... action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN enter the product details page.
        this_step, step_words = genStepWebdriverClick("web_driver", "title_tbc", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global pl_need_attention, "+pl+"\npl_need_attention = "+ pl + "['attention']\nprint('pl_need_attention:', pl_need_attention)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "pur", "NA", "pl_need_attention[this_attention_count-1]['purchase']",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "det_lvl", "NA", "pl_need_attention[this_attention_count-1]['detailLvl']",
                                                  this_step)
        psk_words = psk_words + step_words

        # "pl_need_attention", "att_count"
        # lvl = atpl + "[" + tbb_index +"]['detailLvl']"
        # purchase = atpl + "[" + tbb_index + "]['purchase']"
        # create a loop here to click into the interested product list. Note: loop is inside genAMZBrowseDetail
        this_step, step_words = genAMZBrowserBrowseDetails("det_lvl", "pur", this_step, worksettings)
        psk_words = psk_words + step_words


        # check if this attention count is still in range.
        this_step, step_words = genStepCheckCondition(
            "this_attention_count >= 1 and this_attention_count < len(" + pl + "['attention'])", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global this_attention_index, next_attention_index, this_attention_count\nthis_attention_index = " + pl + "['attention_indices'][this_attention_count-1]\nnext_attention_index = " + pl + "['attention_indices'][this_attention_count]\nprint('this_attention_count:', this_attention_count, this_attention_index, next_attention_index)",
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
            "global this_attention_index, next_attention_index, this_attention_count\nnext_attention_index = " + pl + "['attention_indices'][this_attention_count]\nprint('this_attention_count:', this_attention_count, this_attention_index, next_attention_index)",
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
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME,
                                                            "s-pagination-strip", False, "var",
                                                            "pagination_element", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not atBottom", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME,
                                                            "s-pagination-strip", False, "var",
                                                            "pagination_element", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('DONE BROWSING DOWN PRODUCT LIST.....')", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserBrowsePLToBottom: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserBrowsePLToBottom: {ex_stat}")


    return this_step, psk_words



def genStepsAMZBrowserScrollPLToBottom(stepN, worksettings, start):
    try:
        psk_words = ""
        log3("DEBUG", "gen_psk_for_scroll_to_bottom...")

        # this bottom is marked by pagination element (even though this is not necessary 100% right)
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME,
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

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserScrollPLToBottom: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserScrollPLToBottom: {ex_stat}")

    return this_step, psk_words, "down_cnt"

def genStepsAMZBrowserBrowsePLToLastAttention(page_cfg, pl, ith, stepN, worksettings):
    try:
        psk_words = ""
        prod_cnt = 0
        log3("DEBUG", "genStepsAMZBrowserBrowsePLToLastAttention...")

        this_step, step_words = genStepCreateData("int", "this_attention_index", "NA", 0, stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('BROWSE TO LAST ATTENTION. ', scroll_resolution)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "this_attention_count", "NA", 0, this_step)
        psk_words = psk_words + step_words

        # check whether there is anything to pay attention to on this page.
        this_step, step_words = genStepCheckCondition("len(" + pl + "['attention_indices']) > 0", "", "",
                                                      this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "next_attention_index", "NA", pl + "['attention_indices'][0]",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        # set index to -1 which is the last item on this page, so we're essentially going to the bottom of the page.
        this_step, step_words = genStepCreateData("integer", "next_attention_index", "NA", -1,
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
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


        this_step, step_words = genStepCallExtern(
            "global this_attention_count\nthis_attention_count = this_attention_count + 1\nprint('this_attention_count:', this_attention_count)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern(
            "global pl_need_attention, "+pl+"\npl_need_attention = "+ pl + "['attention']\nprint('pl_need_attention:', pl_need_attention)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words



        this_step, step_words = genStepCheckCondition("this_attention_count < len(pl_need_attention)", "", "", this_step)
        psk_words = psk_words + step_words


        # action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN enter the product details page.
        this_step, step_words = genStepWebdriverClick("web_driver", "title_tbc", "click_result", "click_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("expr", "pur", "NA", "pl_need_attention[this_attention_count-1]['purchase']", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "det_lvl", "NA", "pl_need_attention[this_attention_count-1]['detailLvl']", this_step)
        psk_words = psk_words + step_words

        # "pl_need_attention", "att_count"
        # lvl = atpl + "[" + tbb_index +"]['detailLvl']"
        # purchase = atpl + "[" + tbb_index + "]['purchase']"
        # create a loop here to click into the interested product list. Note: loop is inside genAMZBrowseDetail
        this_step, step_words = genAMZBrowserBrowseDetails("det_lvl", "pur", this_step, worksettings)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
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

        this_step, step_words = genStepCheckCondition("len(" + pl + "['attention_indices']) > 0", "", "",
                                                      this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global this_attention_index, next_attention_index, this_attention_count\nthis_attention_index = " + pl + "['attention_indices'][this_attention_count-1]\nnext_attention_index = " + pl + "['attention_indices'][this_attention_count]\nprint('this_attention_count:', this_attention_count, this_attention_index, next_attention_index)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # after checking whethere there is anything interesting to click into details page.
        # check whether we have reached the end of the page.

        # need now click into the target product.
        this_step, step_words = genStepCheckCondition("not reachedLastAttention", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME,
                                                            "s-pagination-strip", False, "var",
                                                            "pagination_element", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverCheckVisibility("web_driver", "pagination_element", "reachedLastAttention", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # end of loop for going thru all designated attention item on this page.
        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('DONE BROWSE TO LAST ATTENTION. ')", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # we can easily add a few more dumb scroll down actions here.

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserBrowsePLToLastAttention: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserBrowsePLToLastAttention: {ex_stat}")

    return this_step,psk_words


# this would be really easy with webdriver, just scroll to the target.
def genStepsAMZBrowserBrowsePLScrollToNextAttention(pl, stepN, worksettings):
    try:
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

        this_step, step_words = genStepCreateData("obj", "target_title_texts", "NA", [], this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global target_title_texts, "+pl+"\ntarget_title_texts= [te['summery']['title'] for te in "+pl+"['attention']]\nprint('target_title_texts:', target_title_texts)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("obj", "title_elements", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "target_title", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "attention_titles", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "attention_title_texts", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, 'h2.a-size-mini.a-spacing-none.a-color-base.s-line-clamp-4 a', True, "var", "title_elements", "extract_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global attention_titles, target_title_texts, title_elements\nattention_titles= [te for te in title_elements if te.text in target_title_texts]", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global attention_titles, attention_title_texts\nattention_title_texts= [te.text for te in attention_titles]\nprint('attention_title_texts:',attention_title_texts)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global title_elements\nprint('title_elements', attention_titles, len(attention_titles))", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCheckCondition("len(attention_titles) > 0", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global attention_titles, title_tbc\ntitle_tbc = attention_titles[0]", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global attention_titles, title_tbc\nprint('attention_titles:', attention_titles, 'title_tbc:', title_tbc.text)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # sc - 11/05/24 this is no longer needed for selenium based scheme as we know exactly where to go to.
        # this_step, step_words = genStepAMZMatchProduct("screen_info", pl, "pl_need_attention", "found_attention", this_step)
        # psk_words = psk_words + step_words

        # now scroll down and find the menu item.
        # driver.execute_script("arguments[0].scrollIntoView(true);", dropdown_button)
        this_step, step_words = genStepWebdriverScrollTo("web_driver", "title_tbc", 10, 30, 0.25, "dummy_in",
                                                         "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserBrowsePLScrollToNextAttention: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserBrowsePLScrollToNextAttention: {ex_stat}")

    return this_step, psk_words



# assumption for these steps, the browser should already be in the account's amazon home page (on top)
# or in case of a browse, the browse should already being done and we're at the top of the
# product details page. also buyop is not empty
def genStepsWinChromeAMZBrowserBuy(settings_string, buyop_var_name, buy_result_name, buy_flag_name, stepN):
    try:
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

        this_step, step_words = genStepsWinChromeAMZBuyAddCart(this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("buy_cmd == 'pay'", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepsWinChromeAMZBuyPay(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("buy_cmd == 'checkShipping'", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepsWinChromeAMZBuyCheckShipping(this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("buy_cmd == 'rate'", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepsWinChromeAMZBuyGiveProductRating(this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("buy_cmd == 'feedback'", "", "", this_step)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepsWinChromeAMZBuyGiveProductFeedback(this_step)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("buy_cmd == 'checkFB'", "", "", this_step)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepsWinChromeAMZBrowserCheckProductFeedbacks(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step)
        # psk_words = psk_words + step_words

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

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinChromeAMZBrowserBuy: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinChromeAMZBrowserBuy: {ex_stat}")

    return this_step, psk_words


def genStepsWinChromeAMZBuyAddCart(stepN):
    try:
        psk_words = ""
        this_step = stepN

        # check whether this is
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'add-to-cart-button', False, "var", "add_cart_button", "buy_box_available", this_step)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.ID, "buy-now-button", "buy_now_button", this_step)
        # psk_words = psk_words + step_words


        this_step, step_words = genStepCheckCondition("buy_box_available", "", "", this_step)
        psk_words = psk_words + step_words

        # find add_to_cart button.
        this_step, step_words = genStepWebdriverClick("web_driver", "add_cart_button", "action_result", "action_flag",
                                                      this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # output of this funciton is buy_box_available flag.

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinChromeAMZBuyAddCart: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinChromeAMZBuyAddCart: {ex_stat}")

    return this_step, psk_words



def genStepsWinChromeAMZBuyPay(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN):
    try:
        psk_words = ""

        this_step, step_words = genStepSearchAnchorInfo("screen_info", "orders", "direct", "anchor text", "any", "useless", "on_page_top", "", False, stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("on_page_top", "", "", this_step)
        psk_words = psk_words + step_words



        # # find buy_now button.
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'buy-now-button', False, "var", "buy_now_button", "extract_flag", this_step)
        psk_words = psk_words + step_words

        # click on buy_now button.
        this_step, step_words = genStepWebdriverClick("web_driver", "buy_now_button", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # target, flag, prev_result

        # # find buy_now button. don't go this route, always go the cart, make thing simpler?
        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
        #                                                     'turbo-checkout-iframe', False, "var", "buy_popup",
        #                                                     "extract_flag", this_step)
        # psk_words = psk_words + step_words
        #
        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
        #                                                     'a-popover-5', False, "var", "buy_iframe",
        #                                                     "extract_flag", this_step)
        # psk_words = psk_words + step_words
        #
        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
        #                                                     'turbo-checkout-pyo-button', False, "var", "place_order_button",
        #                                                     "extract_flag", this_step)
        # psk_words = psk_words + step_words
        #
        # # click on buy_now button.
        # this_step, step_words = genStepWebdriverClick("web_driver", "place_order_button", "action_result", "action_flag",
        #                                               this_step)
        # psk_words = psk_words + step_words


        # proceed to checkout
        this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.ID, "sc-buy-box-ptc-button", "checkout_button", this_step)
        psk_words = psk_words + step_words

        # place the order.
        # this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.ID, "placeOrder", "place_order_button", this_step)
        # psk_words = psk_words + step_words



    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinChromeAMZBuyPay: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinChromeAMZBuyPay: {ex_stat}")

    return this_step, psk_words




def genStepsWinChromeAMZBuyFromCart(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN):
    psk_words = ""

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "orders", "direct", "anchor text", "any", "useless", "on_page_top", "", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("on_page_top", "", "", this_step)
    psk_words = psk_words + step_words



    # # find buy_now button.
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'buy-now-button', False, "var", "buy_now_button", "extract_flag", this_step)
    psk_words = psk_words + step_words


    # target, flag, prev_result

    # # find proceed_to_checkout_button.
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, '#sc-buy-box-ptc-button input.a-button-input', False, "var", "proceed_to_checkout_button", "extract_flag", this_step)
    psk_words = psk_words + step_words

    # click on proceed_to_checkout_button
    this_step, step_words = genStepWebdriverClick("web_driver", "proceed_to_checkout_button", "action_result", "action_flag", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepsAMZBrowserPagePeekAndClick(settings_string, "proceed_to_checkout", "check_out_top", "cart_top", this_step)
    psk_words = psk_words + step_words

    # when will we see this page?
    this_step, step_words = genStepsAMZBrowserPagePeekAndClick(settings_string, "continue_to_checkout", "in_cart_transition", "pac_result", this_step)
    psk_words = psk_words + step_words

    # there might be a page to to ask you to beceom prime member, need to click on "no thanks" if shows up....
    this_step, step_words = genStepsAMZBrowserPagePeekAndClick(settings_string, "no_thanks", "sign_prime_page", "check_out_top", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepsAMZBrowserPagePeekAndClick(settings_string, "place_your_order", "pay_page", "check_out_top", this_step)
    # psk_words = psk_words + step_words


    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
                                                        'placeOrder', False, "var", "place_order_button",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    # click on buy_now button.
    this_step, step_words = genStepWebdriverClick("web_driver", "place_order_button", "action_result", "action_flag",
                                                  this_step)
    psk_words = psk_words + step_words
    # this_step, step_words = genStepsAMZBrowserPagePeekAndClick(settings_string, "place_your_order", "pay_page", "pac_result", this_step)
    # psk_words = psk_words + step_words

    # this_step, step_words = genStepAMZPeekAndConfirm(settings_string, "order_placed", "pay_page", "pac_result", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepsAMZBrowserPagePeekAndClick(settings_string, "review_recent_orders", "pay_page", "pac_result", this_step)
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


# try:
#     # Extract all orders on the page
#     order_cards = driver.find_elements(By.XPATH, '//div[contains(@class, "order-card")]')
#
#     for order_card in order_cards:
#         # Extract order number
#         order_number = order_card.find_element(By.XPATH, './/div[@class="yohtmlc-order-id"]/span[2]').text
#         print(f"Order Number: {order_number}")
#
#         # Extract all products in the current order
#         product_elements = order_card.find_elements(By.XPATH, './/div[contains(@class, "yohtmlc-product-title")]/a')
#         products = [product.text for product in product_elements]
#         print("Ordered Products:")
#         for product in products:
#             print(f"- {product}")
#
#         # Extract delivery status
#         delivery_status_element = order_card.find_element(By.XPATH, './/div[contains(@class, "yohtmlc-shipment-status-primaryText")]/h3/span')
#         delivery_status = delivery_status_element.text
#         print(f"Delivery Status: {delivery_status}")
#
#         # Extract delivery or expected delivery date
#         if "Delivered" in delivery_status:
#             delivery_date = delivery_status.replace("Delivered", "").strip()
#             print(f"Delivery Date: {delivery_date}")
#         else:
#             try:
#                 expected_delivery_date_element = order_card.find_element(By.XPATH, './/div[contains(@class, "yohtmlc-shipment-status-secondaryText")]/span')
#                 expected_delivery_date = expected_delivery_date_element.text
#                 print(f"Expected Delivery Date: {expected_delivery_date}")
#             except:
#                 print("Expected delivery date not found.")
#
#         # Locate "Leave seller feedback" button and click it
#         try:
#             leave_feedback_button = order_card.find_element(By.XPATH, './/a[contains(text(), "Leave seller feedback")]')
#             leave_feedback_button.click()
#             print("Clicked 'Leave seller feedback' button")
#         except:
#             print("'Leave seller feedback' button not found.")
#
#         # Locate "Write a product review" button and click it
#         try:
#             write_review_button = order_card.find_element(By.XPATH, './/a[contains(text(), "Write a product review")]')
#             write_review_button.click()
#             print("Clicked 'Write a product review' button")
#         except:
#             print("'Write a product review' button not found.")

# input to this function is an order ID.
def genStepsWinChromeAMZBuyCheckShipping(stepN):
    psk_words = ""
    this_step = stepN

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.ID,
                                                        'nav-orders', False, "var", "returns_and_orders_link",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverClick("web_driver", "returns_and_orders_link", "action_result", "action_flag",
                                                  this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.XPATH,
                                                        '//div[contains(@class, "order-card")]', True, "var", "order_cards",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("boolean", "order_found", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("boolean", "order_delivered", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "order_delivery_date", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("integer", "nthCard", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("not order_found and nthCard < len(order_cards)", "", "", "checkShipping" + str(stepN + 1), this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("global order_card, order_cards, nthCard\norder_card=order_cards[nthCard]", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'text'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    # click on add_to_cart button, don't use "Cart" since it's not reliable and OCR gets confused by the cart icon.
    #         order_number = order_card.find_element(By.XPATH, './/div[@class="yohtmlc-order-id"]/span[2]').text
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "order_card", 0, "info_type", By.XPATH,
                                                        './/div[@class="yohtmlc-order-id"]/span[2]', False, "var", "order_id",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("order_id == check_shipping_order_id", "", "", this_step)
    psk_words = psk_words + step_words

    # click on add_to_cart button, don't use "Cart" since it's not reliable and OCR gets confused by the cart icon.
    this_step, step_words = genStepCallExtern("global order_found\norder_found=True", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nthCard\nnthCard= nthCard + 1", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # by now, the order_card is found, now extract the shipping info.
    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'text'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "error_alert", 0, "info_type",
                                                        By.XPATH,
                                                        './/div[contains(@class, "yohtmlc-shipment-status-primaryText")]/h3/span', False, "var", "delivery_status",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("'Delivered' in delivery_status", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global order_delivered\norder_delivered= True", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global order_delivery_date\norder_delivery_date= delivery_status.replace('Delivered', '').strip()", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global order_delivered\norder_delivered= False", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    return this_step, psk_words

def genStepsWinChromeAMZBuyGiveProductRating(stepN):
    psk_words = ""
    this_step = stepN

    this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.XPATH, "(//button[@data-hook='ryp-star'])[5]", "five_star", this_step)
    psk_words = psk_words + step_words


    return this_step, psk_words

def genStepsWinChromeAMZBuyGiveProductFeedback(stepN):
    psk_words = ""
    this_step = stepN

    this_step, step_words = genStepCreateData("string", "product", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "instructions", "NA", "1", this_step)
    psk_words = psk_words + step_words

    #product, instructions, review, result_var, stepN
    this_step, step_words = genStepObtainReviews("product", "instructions", "review_body", "review_title", "store_feedback", "review_obtained", this_step)
    psk_words = psk_words + step_words

    # find review text box
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.ID,
                                                        "scarface-review-title-label", False, "var", "review_title_text_box",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    # key in the review text.
    this_step, step_words = genStepWebdriverKeyIn("web_driver", "review_title_text_box", "review_title", "action_result", "action_flag", this_step)
    psk_words = psk_words + step_words

    # find review text box
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.ID,
                                                        "scarface-review-text-card-title", False, "var", "review_body_text_box",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    # key in the review text.
    this_step, step_words = genStepWebdriverKeyIn("web_driver", "review_body_text_box", "review_body", "action_result", "action_flag", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.XPATH, "//span[@data-hook='ryp-review-submit-button']//button", "review_submit_button", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words



def genStepsWinChromeAMZBuyGiveSellerRating(stepN):
    psk_words = ""
    this_step = stepN

    # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME,
    #                                                     "rating", False, "var", "rating_section ",
    #                                                     "extract_flag", this_step)
    # psk_words = psk_words + step_words


    # click on 5 star
    # this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.XPATH, "//input[@name='star-rating' and @value='5']",
    #                                                            "star_5", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.XPATH, "//label[@name='star5']", "star_5", this_step)
    psk_words = psk_words + step_words


    # click on yes radio button for item as described,.
    # this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.XPATH, "//div[@data-a-input-name='ItemAsDescribed']",
    #                                                            "item_as_described_yes", this_step)
    # psk_words = psk_words + step_words
    this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.XPATH, "//input[@name='ItemAsDescribed' and @value='1']",
                                                               "item_as_described_yes", this_step)
    psk_words = psk_words + step_words

    # find review text box
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.NAME,
                                                        "feedback-text", False, "var", "review_text_box",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    # key in the review text.
    this_step, step_words = genStepWebdriverKeyIn("web_driver", "review_text_box", "store_feed_back", "action_result", "action_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
                                                        "a-autoid-2-announce", False, "var", "feedback_submit_button",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    # click on feedback_submit_button.
    this_step, step_words = genStepWebdriverClick("web_driver", "feedback_submit_button", "action_result", "action_flag",
                                                  this_step)
    psk_words = psk_words + step_words


    return this_step, psk_words


def genStepsWinChromeAMZBuyGiveSellerFeedback(stepN):
    psk_words = ""
    this_step = stepN

    this_step, step_words = genStepsAMZBrowserPagePeekAndClick(By.XPATH,
                                                               "//input[@name='ItemAsDescribed' and @value='1']",
                                                               "item_as_described_yes", this_step)
    psk_words = psk_words + step_words

    # find review text box
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.NAME,
                                                        "feedback-text", False, "var", "review_text_box",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "product", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "instructions", "NA", "2", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepObtainReviews("product", "instructions", "review_body", "review_title", "store_feedback", "review_obtained", this_step)
    psk_words = psk_words + step_words

    # key in the review text.
    this_step, step_words = genStepWebdriverKeyIn("web_driver", "review_text_box", "store_feedback", "action_result",
                                                  "action_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
                                                        "a-autoid-2-announce", False, "var", "feedback_submit_button",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    # click on feedback_submit_button.
    this_step, step_words = genStepWebdriverClick("web_driver", "feedback_submit_button", "action_result",
                                                  "action_flag",
                                                  this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genStepsWinChromeAMZFeedbackCheckAlert(stepN):
    psk_words = ""
    this_step = stepN

    # # Locate the error alert box using its data-hook attribute
    # error_alert = driver.find_element(By.CSS_SELECTOR, 'div[data-hook="ryp-icon-alert"]')
    #
    # # Extract the text of the error message
    # error_message = error_alert.find_element(By.CSS_SELECTOR, 'span.a-color-error').text

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.CSS_SELECTOR,
                                                        'div[data-hook="ryp-icon-alert"]', False, "var", "error_alert",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'text'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "error_alert", 0, "info_type", By.CSS_SELECTOR,
                                                        'span.a-color-error', False, "var", "error_message",
                                                        "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("'not met the minimum eligibility' in error_message", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global review_eligible\nreview_eligible= False", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("'this account will no longer' in error_message", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global review_banned\nreview_banned= True", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words



def genStepsWinChromeAMZBuyGiveDirectReview(stepN):
    psk_words = ""
    # now we're in order page, search for the order placed,
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "orders", "direct", "anchor text", "any", "useless",
                                                    "on_page_top", "", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("on_page_top", "", "", this_step)
    psk_words = psk_words + step_words

    #     review_button = driver.find_element(By.XPATH, '//a[contains(@class, "a-button-text") and contains(text(), "Write a customer review")]')
    #
    #     # Scroll into view if necessary (optional)
    #     ActionChains(driver).move_to_element(review_button).perform()
    #
    #     # Click the button
    #     review_button.click()

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    # click on write_direct_review button
    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.XPATH, '//a[contains(@class, "a-button-text") and contains(text(), "Write a customer review")]', False, "var", "direct_review_button", "extract_flag", this_step)
    psk_words = psk_words + step_words

    #
    this_step, step_words = genStepWebdriverClick("web_driver", "direct_review_button", "action_result", "action_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # check to see if there is any error message warning this item is not direct reviewable...
    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'text'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR,
                                                        "div[data-hook='ryp-error-page-text']", False, "var",
                                                        "direct_review_button", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("on_page_top", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global direct_reviewable\ndirect_reviewable=False\nprint('direct_reviewable:', direct_reviewable)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global direct_reviewable\ndirect_reviewable=True\nprint('direct_reviewable:', direct_reviewable)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    #product, instructions, review, result_var, stepN
    this_step, step_words = genStepCreateData("string", "product", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "instructions", "NA", "5", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepObtainReviews("product", "instructions", "review_body", "review_title", "store_feedback", "review_obtained", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "review", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words





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



def genWinADSAMZBrowserBrowseSearchSkill(worksettings, stepN, theme):
    try:
        log3("GENERATING genWinADSAMZBrowserBrowseSearchSkill===101===>")
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

        this_step, step_words = genStepCreateData("string", "drive_result", "NA", "", this_step)
        psk_words = psk_words + step_words


        # first call subskill to open ADS Power App, and check whether the user profile is already loaded?
        # Note: this skill simply opens the profiles button, whether the target profile is loaded is yet to be determined.
        this_step, step_words = genStepUseSkill("open_profile", "public/win_ads_local_open", "open_profile_input", "ads_up", this_step)
        psk_words = psk_words + step_words
        #
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


        this_step, step_words = genStepCreateData("obj", "vers", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "gmail_refresh_stat", "NA", "Completed:0", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "gmail_input", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "ads_ver", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepBringAppToFront("AdsPower", "ads_win_info", "action_flag", this_step)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepGetWindowsInfo(0, "ads_win_info", "action_flag", this_step)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global ads_win_info, ads_ver\nver_parts=ads_win_info['title'].split('|')\nads_ver=ver_parts[1].strip()+':'+ver_parts[2].strip()\nprint('ads_ver:', ads_ver)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global sk_work_settings, ads_ver\nsk_work_settings['fp_browser_settings']['ads_version'] = ads_ver", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global ads_ver, ads_main_ver_parts\nads_main_ver_parts = ads_ver.split(':')[0].split('.')", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global ads_main_ver_parts, ads_main_ver_num\nads_main_ver_num = int(ads_main_ver_parts[0])*10000+int(ads_main_ver_parts[1])*100+int(ads_main_ver_parts[2])*1\nprint('ads_main_ver_num: ', ads_main_ver_num)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # now simply try to open the bot's profile with profile id, if it failed, that means the current
        # batch doesn't contain the bot, so it's time to batch import the batch that contains the
        # bot's profile.
        # however do note, that once the batch is loaded, the profile id will be changed by ADS,
        # will will have to update profile id on all bots in this batch

        this_step, step_words = genStepsLoadRightBatchForBot(worksettings, this_step, theme)
        psk_words = psk_words + step_words


        #  at this point all webdriver connection to ADS issue should have been cleared. and profiles loaded.
        #  also ads api port should already be made sure to be correct.
        #  and the correct batch should be loaded too at this point, and we should be able to just
        #  go straight into actions with selenium web driver all the way.....

        # wait 9 seconds for the browser to be brought up.
        this_step, step_words = genStepWait(5, 1, 3, this_step)
        psk_words = psk_words + step_words
        #
        #
        # # following is for tests purpose. hijack the flow, go directly to browse....
        # # this_step, step_words = genStepGoToWindow("SunBrowser", "", "g2w_status", this_step)
        # # this_step, step_words = genStepGoToWindow("Chrome", "", "g2w_status", this_step)
        # # psk_words = psk_words + step_words
        #
        # this_step, step_words = genStepWait(3, 1, 3, this_step)
        # psk_words = psk_words + step_words
        #
        # now that the profile is loaded, we connect webdriver to ADS power.
        # this_step, step_words = genStepWebdriverNewTab("web_driver", "https://www.amazon.com/", "site_result", "site_flag", this_step)
        # psk_words = psk_words + step_words

        # now open the target amazon web site，(this step will internall check whether the tab is already open, if open, simply switch to it)
        # this_step, step_words = genStepWebdriverGoToTab("web_driver", "amazon", "https://www.amazon.com", "site_result", "site_flag", this_step)
        # this_step, step_words = genStepWebdriverGoToTab("web_driver", "amazon", "https://www.amazon.com/iMBAPrice-Sealing-Tape-Shipping-Packaging/dp/B072MD8W9Q?th=1", "site_result", "site_flag", this_step)
        # psk_words = psk_words + step_words

        # #####################Before doing anything on Amazon, first refresh gmail.#######################
        this_step, step_words = genStepCreateData("expr", "bot_email", "NA", "sk_work_settings['b_email']", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "bot_email_pw", "NA", "sk_work_settings['b_email_pw']", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global gmail_input, bot_email, bot_email_pw\ngmail_input=[bot_email, bot_email_pw]\nprint('gmail_input:', gmail_input)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepUseSkill("browser_refresh", "public/win_ads_gmail_home", "gmail_input", "gmail_refresh_stat", this_step)
        psk_words = psk_words + step_words

        #################### done refresh gamil ###############################

        this_step, step_words = genStepsAMZBrowserLoginIn(this_step, theme)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not_logged_in == False", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(3, 0, 0, this_step)
        psk_words = psk_words + step_words

        #now call the amz chrome browse sub-skill to go thru the walk process.
        # this_step, step_words = genStepsWinChromeAMZBrowserWalk("sk_work_settings", this_step)
        # this_step, step_words = genStubWinChromeAMZBrowserWalk("sk_work_settings", this_step)
        # psk_words = psk_words + step_words

        # end condition for "not_logged_in == False"
        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        #
        # close the browser and exit the skill, assuming at the end of genWinChromeAMZWalkSteps, the browser tab
        # should return to top of the amazon home page with the search text box cleared.
        this_step, step_words = genStepKeyInput("", True, "alt,f4", "", 3, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepGoToWindow("AdsPower", "", "g2w_status", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global bot_email, current_batch\nuseless=current_batch.pop(bot_email, None)\nprint('current_batch:', current_batch)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("sk_work_settings['last_one'] or sk_work_settings['retry']", "", "", this_step)
        psk_words = psk_words + step_words

        # in case mission executed successfully, save profile, kind of an overkill or save all profiles, but simple to do.
        # only do the save when current profile is at the end of the list.
        this_step, step_words = genStepsADSPowerExitProfile(worksettings, this_step, theme)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end skill", "public/win_ads_amz_home/browser_browse_search", "", this_step)
        psk_words = psk_words + step_words

        psk_words = psk_words + "\"dummy\" : \"\"}"
        # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGenWinADSAMZBrowserBrowseSearchSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGenWinADSAMZBrowserBrowseSearchSkill: traceback information not available:" + str(e)
        log3(ex_stat)

    return this_step, psk_words


def genStubWinChromeAMZBrowserWalk(settings_var, stepN):
    try:
        psk_words = ""

        this_step, step_words = genStepWait(1, 0, 0, stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "action_result", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "action_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # search first...
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'twotabsearchtextbox', False, "var", "search_box", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "search_phrase", "NA", "yoga ball", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverKeyIn("web_driver", "search_box", "search_phrase", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-search-submit-button', False, "var", "search_button", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "search_button", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(6, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "nthPage", "NA", 0, this_step)
        psk_words = psk_words + step_words

        # scrape search result product list...
        this_step, step_words = genStepAMZBrowserScrapePL("web_driver", "plSearchResult", 'nthPLPage', 'pl_page_config', "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "target_title_txts", "NA", ["Pharmedoc Yoga Ball Chair, Exercise Ball Chair with Base & Bands for Home Gym Workout, Pregnancy Ball, Birthing Ball, Stability Ball & Balance Ball Seat, Exercise Equipment"], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "title_elements", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "target_title", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "attention_titles", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "attention_title_texts", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, 'h2.a-size-mini.a-spacing-none.a-color-base.s-line-clamp-4 a', True, "var", "title_elements", "extract_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global attention_titles, target_title_txts, title_elements\nattention_titles= [te for te in title_elements if te.text in target_title_txts]", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global attention_titles, attention_title_texts\nattention_title_texts= [te.text for te in attention_titles]\nprint('attention_title_texts:',attention_title_texts)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global title_elements\nprint('title_elements',attention_titles, len(attention_titles))", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("len(attention_titles) > 0", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global attention_titles, title_tbc\ntitle_tbc = attention_titles[0]", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "title_tbc", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(6, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("integer", "det_lvl", "NA", 2, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("obj", "pur", "NA", [], this_step)
        psk_words = psk_words + step_words

        # https://www.amazon.com/iMBAPrice-Sealing-Tape-Shipping-Packaging/dp/B072MD8W9Q?th=1
        this_step, step_words = genAMZBrowserBrowseDetails("det_lvl", "pur", this_step, settings_var)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStubWinChromeAMZBrowserWalk: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStubWinChromeAMZBrowserWalk: {ex_stat}")

    return this_step, psk_words

def genStepsLoadRightBatchForBot(worksettings, stepN, theme):
    try:
        psk_words = ""
        log3("DEBUG", "genStepsLoadRightBatchForBot...")

        # first try to load bot's profile using selenium webdriver
        this_step, step_words = genStepCreateData("string", "web_driver_options", "NA", "", stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "ads_config", "NA", {}, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "loaded_profiles", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "action_flag", "NA", False, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global ads_config, local_api_key, local_api_port, sk_work_settings\nlocal_api_port = sk_work_settings['fp_browser_settings']['ads_port']\nlocal_api_key = sk_work_settings['fp_browser_settings']['ads_api_key']\nads_config['port']=local_api_port\nads_config['api_key']=local_api_key\nprint('local_api_port:', local_api_port)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepAPIADSListProfiles("ads_config", "loaded_profiles", "action_flag",  this_step)
        psk_words = psk_words + step_words

        # check whether the bot in this mission is loaded in ADS already
        this_step, step_words = genStepCheckCondition("sk_work_settings['b_email'] in loaded_profiles", "", "", this_step)
        psk_words = psk_words + step_words

        # if already loaded, try to use web driver to open it and run with it.
        this_step, step_words = genStepCreateData("string", "ads_profile_id", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "ads_profile_remark", "NA", "", this_step)
        psk_words = psk_words + step_words
        #
        # this_step, step_words = genStepCallExtern(
        #     "global ads_profile_id, sk_work_settings\nads_profile_id = sk_work_settings['b_email']\nprint('ads_profile_id:', ads_profile_id)",
        #     "", "in_line", "", this_step)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global ads_profile_id, ads_profile_remark, loaded_profiles, sk_work_settings\nads_profile_id = loaded_profiles[sk_work_settings['b_email']]['uid']\nads_profile_remark = loaded_profiles[sk_work_settings['b_email']]['remark']\nprint('ads_profile_id, ads_profile_remark:', ads_profile_id, ads_profile_remark)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "ads_chrome_version", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global ads_chrome_version, sk_work_settings\nads_chrome_version = sk_work_settings['fp_browser_settings']['chrome_version']\nprint('ads_chrome_version:', ads_chrome_version)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "web_driver_path", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global web_driver_path, ads_chrome_version, sk_work_settings\nweb_driver_path =  sk_work_settings['root_path'] + '/' + sk_work_settings['fp_browser_settings']['chromedriver_lut'][ads_chrome_version]\nprint('web_driver_path:', web_driver_path)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverStartExistingADS("web_driver", "local_api_key", "ads_profile_id",
                                                                 "local_api_port", "web_driver_path", "web_driver_options",
                                                                 "drive_result", "web_driver_successful", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not web_driver_successful", "", "", this_step)
        psk_words = psk_words + step_words

        # this could be the case where the ads power's local api port and api key has changed, so try re-obtain it.
        this_step, step_words = genStepsADSPowerObtainLocalAPISettings(worksettings, this_step, theme)
        psk_words = psk_words + step_words

        # now try to connec to ads power again
        this_step, step_words = genStepWebdriverStartExistingADS("web_driver", "local_api_key", "ads_profile_id",
                                                                 "local_api_port", "web_driver_path", "web_driver_options",
                                                                 "drive_result", "web_driver_successful", this_step)
        psk_words = psk_words + step_words

        # no reason to fail again...

        # end condition for (drive_result == 'user account does not exist')
        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        # else - if bot email not in loaded_profiles , then need to save/export current batch,
        # and then load the right batch.
        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        #before saving the current profiles need to close them first. so here we
        # loop thru "loaded_profiles" and check each to see whether that
        # profile is "active" if so, close it.

        # loop to go thru each profile....

        this_step, step_words = genStepCreateData("integer", "profile_idx", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "profile_status", "NA", "Inactive", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "users", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "profile_id", "NA", "[]", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global loaded_profiles, users\nusers = list(loaded_profiles.keys())\nprint('users:', users)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepLoop("profile_idx < len(loaded_profiles)", "", "", "amzbuy" + str(stepN), this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global profile_id, loaded_profiles, users, profile_idx\nprofile_id = loaded_profiles[users[profile_idx]]['uid']\nprint('profile id:', profile_id)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepAPIADSCheckProfileBrowserStatus("ads_config", "profile_id", "profile_status", "web_driver_successful", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("profile_status == 'active'", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepAPIADSStopProfile("ads_config", "profile_id", "stop_result", "web_driver_successful", this_step)
        psk_words = psk_words + step_words

        # end of check condition for checkFB
        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global profile_idx\nprofile_idx = profile_idx + 1", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words


        # in case connecting to ads failed due to account not currently loaded, now it's time to load in the correct batch of profiles.
        # now exit current batch which will save the current batch, note this saving will penerate
        # to update each individual bot's profile in this batch, as well as each bot's ads profile parameter.
        # and the next profile batch xlxs file .
        this_step, step_words = genStepsADSBatchExportProfiles(worksettings, theme, this_step)
        psk_words = psk_words + step_words

        # set up to import the right batch profile
        this_step, step_words = genStepCreateData("expr", "profile_name", "NA", "os.path.basename(sk_work_settings['batch_profile'])", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "profile_name_path", "NA", "os.path.dirname(sk_work_settings['batch_profile'])", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "bot_email", "NA", "sk_work_settings['b_email'].split('@')[0]+'@'", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "full_site", "NA", "sk_work_settings['full_site'].split('www.')[1]", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "machine_os", "NA", "sk_work_settings['platform']", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("expr", "batch_import_input", "NA", "['open', profile_name_path, profile_name, bot_email, full_site, machine_os, ads_main_ver_num]", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('batch_import_input::', batch_import_input)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepUseSkill("batch_import", "public/win_ads_local_load", "batch_import_input", "browser_up", this_step)
        psk_words = psk_words + step_words

        # after batch import, get the right profile id.
        # use ads api to query loaded profiles, which returns a dictionary of profile id with email as key
        this_step, step_words = genStepAPIADSListProfiles("ads_config", "loaded_profiles", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "import copy\nglobal loaded_profiles, current_batch\ncurrent_batch = copy.deepcopy(loaded_profiles)\nprint('current_batch:', current_batch)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # end condition  for "bot email not in loaded_profiles"
        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # now update profile id, now we should have the correct profile id loaded into ADS.
        this_step, step_words = genStepCallExtern(
            "global ads_profile_id, ads_profile_remark, loaded_profiles, sk_work_settings\nads_profile_id = loaded_profiles[sk_work_settings['b_email']]['uid']\nads_profile_remark = loaded_profiles[sk_work_settings['b_email']]['remark']\nprint('ads_profile_id, ads_profile_remark:', ads_profile_id, ads_profile_remark)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern(
            "global ads_chrome_version, sk_work_settings\nads_chrome_version = sk_work_settings['fp_browser_settings']['chrome_version']\nprint('ads_chrome_version:', ads_chrome_version)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern(
            "global web_driver_path, ads_chrome_version, sk_work_settings\nweb_driver_path =  sk_work_settings['root_path'] + '/' + sk_work_settings['fp_browser_settings']['chromedriver_lut'][ads_chrome_version]\nprint('web_driver_path:', web_driver_path)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverStartExistingADS("web_driver", "local_api_key", "ads_profile_id",
                                                                 "local_api_port", "web_driver_path", "web_driver_options",
                                                                 "drive_result", "web_driver_successful", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("print('DONE Loading bots correct profile.....')", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsLoadRightBatchForBot: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsLoadRightBatchForBot: {ex_stat}")


    return this_step,psk_words


def genAMZBrowserBrowseDetails(lvl, purchase, stepN, worksettings):
    try:
        psk_words = ""
        log3("DEBUG", "genAMZBrowserBrowseDetails...")

        # now, starts to browse into the product details page.......................................
        this_step, step_words = genStepCreateData("bool", "end_of_detail", "NA", False, stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('START BROWSING DETAILS')", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "scroll_adjustment", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "about_this_item", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "h1.a-size-base-plus.a-text-bold", True, "var", "h1headers", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global h1headers\nprint('h1 headers:', len(h1headers))\nprint('h1 headers txt:', [h.text for h in h1headers])", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global about_this_item, h1headers\nabout_this_item = next((obj for obj in h1headers if obj.text == 'About this item'), None)\nprint('about_this_item:', about_this_item.text)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        #scroll to about item, and at this point the thumbnails and the landing image should appear on display
        this_step, step_words = genStepWebdriverScrollTo("web_driver", "about_this_item", 10, 30, 0.25, "dummy_in","element_present", this_step)
        psk_words = psk_words + step_words

        #now hover mouse over image icons to view images.
        this_step, step_words = genStepsAMZBrowseDetailsViewImages(this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME, "prodDetAttrValue", False, "var", "prod_details_attributes", "extract_flag", this_step)
        psk_words = psk_words + step_words

        # scroll to parameters section which should contains the ASIN number for double verification
        this_step, step_words = genStepWebdriverScrollTo("web_driver", "prod_details_attributes", 10, 30, 0.25, "dummy_in","element_present", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.XPATH, "//tr[th[contains(text(), 'ASIN')]]", False, "var", "asin_row", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverScrollTo("web_driver", "asin_row", 10, 30, 0.25, "dummy_in","element_present", this_step)
        psk_words = psk_words + step_words

        # scroll to the begining of the review section.
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.XPATH, "//h3[@data-hook='dp-local-reviews-header']", False, "var", "review_header", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverScrollTo("web_driver", "review_header", 10, 30, 0.25, "dummy_in","element_present", this_step)
        psk_words = psk_words + step_words



        #if there is purchase action, save the page, scrape it and confirm the title, store, ASIN, price, feedbacks, rating.
        this_step, step_words = genStepCheckCondition("len("+purchase+") != 0", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        # now go thru review browsing ....... based on specified detail level.
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

        # read_more_buttons = driver.find_elements("css selector", "a[data-hook='expand-collapse-read-more-less']")
        # obtain all the "Read more" expandables.....
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "a[data-hook='expand-collapse-read-more-less']", True, "var", "rv_expandables", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "read_mores", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "see_all_review", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global read_mores, rv_expandables\nread_mores = [obj for obj in rv_expandables if obj.text == 'Read more']", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # expandables_count = 0
        this_step, step_words = genStepCreateData("int", "expandables_count", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "nth_expandable", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global expandables_count, read_mores\nexpandables_count = len(read_mores)", "", "in_line", "", this_step)
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

        this_step, step_words = genStepCallExtern("global expandables_count, nth_expandable, max_expandables\nprint('max_expandables: ', max_expandables, 'expandables_count: ', expandables_count, [obj.text for obj in read_mores], 'nth_expandable: ', nth_expandable)", "", "in_line", "", this_step)
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

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.XPATH, "//span[@data-hook='top-customer-reviews-title']", False, "var", "review_end", "extract_flag", this_step)
        psk_words = psk_words + step_words

        # browse all the way down, until seeing "No customer reviews" or "See all reviews"
        this_step, step_words = genStepLoop("end_of_detail != True", "", "", "browseDetails"+str(stepN+1), this_step)
        psk_words = psk_words + step_words

        #(action, screen, amount, unit, stepN):
        this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWait(1, 0, 0, this_step)
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


        this_step, step_words = genStepCheckCondition("expandables_count > max_expandables", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global expandables_count, max_expandables\nexpandables_count = max_expandables\nprint( 'updated expandables_count: ', expandables_count)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepLoop("nth_expandable < expandables_count", "", "", "browseDetails"+str(stepN+1), this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global current_expandable\ncurrent_expandable = read_mores[nth_expandable]", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverScrollTo("web_driver", "current_expandable", 10, 30, 0.25, "dummy_in","element_present", this_step)
        psk_words = psk_words + step_words

        # # click into "Read more"
        this_step, step_words = genStepWebdriverClick("web_driver", "current_expandable", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global nth_expandable\nnth_expandable = nth_expandable + 1", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # close for loop: nth_expandable < expandables_count, finished click on all expandables on this screen.
        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

        # after click on "Read more", now scroll to the end of reviews.
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "a[data-hook='see-all-reviews-link-foot']", True, "var", "see_all_reviews", "element_present", this_step)
        # this_step, step_words = genStepWebdriverCheckVisibility("web_driver", "also_bought_header", "end_of_reviews", "action_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global see_all_reviews\nprint('see_all_reviews',[obj.text for obj in see_all_reviews])", "",
                                                  "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("len(see_all_reviews) > 0", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global see_all_review, see_all_reviews\nsee_all_review = see_all_reviews[0]", "",
                                                  "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverScrollTo("web_driver", "see_all_review", 10, 30, 0.25, "dummy_in","element_present", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "span[data-hook='top-customer-reviews-title']", False, "var", "no_review", "element_present", this_step)
        # this_step, step_words = genStepWebdriverCheckVisibility("web_driver", "also_bought_header", "end_of_reviews", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words
        # histogram_section = driver.find_element(By.ID, "cm_cr_dp_d_rating_histogram")
        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, "cm_cr_dp_d_rating_histogram", False, "var", "review_stars_section", "element_present", this_step)
        # psk_words = psk_words + step_words
        #
        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "span.navFooterBackToTopText", False, "var", "bottom_header", "element_present", this_step)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global end_of_detail\nend_of_detail = True", "","in_line", "", this_step)
        psk_words = psk_words + step_words

        # close for loop: end_of_detail != True
        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words



        # # check for whether we have reached end of product details. page.
        # # for level 1 details, will view all the way till the end of reviews
        # # for level 2 details, will view till end of all reviews and open hidden long reviews along the way (click on "see all").
        # # but if this product has no review or has all short reviews where there is no "see all", then this is equivalent to
        # # level 1
        this_step, step_words = genStepCheckCondition("detail_level >= 2 and not no_review", "", "", this_step)
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
        this_step, step_words = genStepWebdriverClick("web_driver", "see_all_review", "action_result", "action_flag", this_step)
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



        #==== Now that we have completed browsing the product details page. ========
        # check whether there is an buy action here, if there is, scroll to top and perform the buy actions.
        # purchase = page_cfg + "['products'][li]['purchase']"
        this_step, step_words = genStepCheckCondition("len(buy_ops) >  0", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("print('Perform Buy steps here....')", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # do the buy operation
        this_step, step_words = genStepsBrowserPerformBuyRelated(worksettings, "buy_ops", this_step)
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

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genAMZBrowserBrowseDetails: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genAMZBrowserBrowseDetails: {ex_stat}")

    return this_step,psk_words


def genStepsAMZBrowseDetailsViewImages(stepN):
    try:
        #simply move the mouse pointer around to simulate viewing images.
        psk_words = ""

        this_step, step_words = genStepCallExtern("print('viewing thumbnails.....')", "", "in_line", "", stepN)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, ".a-button-thumbnail img, .imageThumbnail img", True, "var", "product_thumbnails", "element_present", this_step)
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "li.a-spacing-small.item.imageThumbnail.a-declarative", True, "var", "product_thumbnails", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "thumbnail", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("integer", "nThumbnails", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global nThumbnails, product_thumbnails\nnThumbnails = len(product_thumbnails)\nprint('nThumbnails:', nThumbnails)",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "idxs2view", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("integer", "n2view", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global idxs2view, nThumbnails\nidxs2view = [random.randint(1, nThumbnails-1) for _ in range(random.randint(1, nThumbnails-1))]\nprint('idxs2view:', idxs2view)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepLoop("n2view < len(idxs2view)", "", "", "viewImg", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global thumbnail, idxs2view, product_thumbnails\nthumbnail = product_thumbnails[idxs2view[n2view]]\nprint('thumbnail:', thumbnail)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverHoverTo("web_driver", "thumbnail", "action_flag", this_step)
        psk_words = psk_words + step_words

        #now move to landing image and jitter around

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, "landingImage", False, "var", "landing_image", "element_present", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverHoverTo("web_driver", "thumbnail", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepsMouseJitter(this_step)
        psk_words = psk_words + step_words

        # decrement loop counter.
        this_step, step_words = genStepCallExtern("global n2view\nn2view = n2view + 1\nprint('n2view:', n2view)", "",
                                                  "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowseDetailsViewImages: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowseDetailsViewImages: {ex_stat}")

    return this_step, psk_words


def genStepsMouseJitter(stepN):
    try:
        psk_words = ""
        # will do this for as much as 5 seconds
        this_step, step_words = genStepCreateData("int", "nMoves", "NA", 5, stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global nMoves\nnMoves = random.randint(1, 5)\nprint('nMoves:', nMoves)", "",
                                                  "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "maxx", "NA", 80, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "maxy", "NA", 80, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "minx", "NA", -80, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "miny", "NA", -80, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "min_wait", "NA", 50, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "max_wait", "NA", 200, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "random_wait", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "x_offset", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "y_offset", "NA", 0, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepLoop("nMoves > 0", "", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global x_offset\nx_offset = random.randint(minx, maxx)\nprint('x_offset:', x_offset)", "",
                                                  "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global y_offset\ny_offset = random.randint(miny, maxy)\nprint('y_offset:', y_offset)", "",
                                                  "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepMouseMove("x_offset", "y_offset", "", "", 0, False, this_step)
        psk_words = psk_words + step_words

        # decrement loop counter.
        this_step, step_words = genStepCallExtern("global nMoves\nnMoves = nMoves - 1\nprint('nMoves:', nMoves)", "",
                                                  "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global random_wait\nrandom_wait =random.randint(min_wait, max_wait)/100\nprint('random_wait:', random_wait)", "",
                                                  "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait("random_wait", 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsMouseJitter: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsMouseJitter: {ex_stat}")

    return this_step, psk_words


def genStepsAMZBrowserScrollDownSome(n_word, stepN):
    try:
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

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserScrollDownSome: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserScrollDownSome: {ex_stat}")

    return this_step,psk_words


def genAMZBrowseDetailsScrollPassReviews(settings_var_name, stepN):
    try:
        psk_words = ""

        this_step, step_words = genStepCreateData("string", "scrn_position", "NA", "before", stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepLoop("scrn_position != 'on' and scrn_position != 'after'", "", "", "", this_step)
        psk_words = psk_words + step_words

        # scroll 5 full screen worth of contents
        this_step, step_words = genStepsAMZBrowserScrollDownSome("5", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "bottom_header", False, "var", "five_star_link", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepAmzDetailsCheckPosition("screen_info", "reviewed", "scrn_position", "position_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genAMZBrowseDetailsScrollPassReviews: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genAMZBrowseDetailsScrollPassReviews: {ex_stat}")

    return this_step,psk_words

# extract review information from the current screen.
def genExtractReview(scrn, stepN):
    # there are better ways to do this, like reading directly from html, so not going to do this the dumb way...
    log3("nop")
    psk_words = ""
    this_step = stepN
    return this_step,psk_words

# this function generate code to scroll N pages of full reviews.
def genAMZBrowseAllReviewsPage(level, stepN, settings_var_name):
    try:
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

        this_step, step_words = genStepCreateData("obj", "one_star_link", "NA", None, this_step)
        psk_words = psk_words + step_words
        this_step, step_words = genStepCreateData("obj", "five_star_link", "NA", None, this_step)
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

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "a.histogram-row-container[aria-label*='5 stars']", False, "var", "five_star_link", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "a.histogram-row-container[aria-label*='1 stars']", False, "var", "one_star_link", "element_present", this_step)
        psk_words = psk_words + step_words


        #  read all five star reviews
        this_step, step_words = genStepWebdriverClick("web_driver", "five_star_link", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        # read positive reviews if level is even number
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

        #  read all one star reviews
        this_step, step_words = genStepWebdriverClick("web_driver", "one_star_link", "action_result", "action_flag", this_step)
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

        # this_step, step_words = genStepWebdriverExtractInfo("", settings_var_name, "screen_info", "all_reviews", "top", this_step, None)
        # psk_words = psk_words + step_words

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

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genAMZBrowseAllReviewsPage: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genAMZBrowseAllReviewsPage: {ex_stat}")

    return this_step, psk_words


def genScroll1StarReviewsPage(stepN, start):
    try:
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

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genScroll1StarReviewsPage: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genScroll1StarReviewsPage: {ex_stat}")

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
    try:
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

        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.XPATH, "//span[text()='{correct_carrier}']/ancestor::button", False, "var", "correct_carrier_option", "element_present", this_step)
        # psk_words = psk_words + step_words

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

        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.XPATH, "//span[text()='{correct_carrier}']/ancestor::button", False, "var", "correct_carrier_option", "element_present", this_step)
        # psk_words = psk_words + step_words

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
        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.XPATH, "//span[text()='{correct_carrier}']/ancestor::button", False, "var", "correct_carrier_option", "element_present", this_step)
        # psk_words = psk_words + step_words

        his_step, step_words = genStepLoop("(not var_target_found) and (scroll_cnt < 10)", "", "", "findVar" + str(stepN), this_step)
        psk_words = psk_words + step_words

        # then hover over to the center of the icon，then extract and double check the selection text is there，
        # if not, hover neighbors to double check
        this_step, step_words = genStepWebdriverClick("web_driver", "correct_carrier_option", "click_result", "click_flag", this_step)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "row", 0, "info_type", By.XPATH, "//span[text()='{correct_carrier}']/ancestor::button", False, "var", "correct_carrier_option", "element_present", this_step)
        # psk_words = psk_words + step_words

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

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genAMZBuySelectVariations: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genAMZBuySelectVariations: {ex_stat}")

    return this_step, psk_words


def genStepsAMZBrowserLoginIn(stepN, theme):
    try:
        psk_words = ""

        # check the 1st tab to make sure the connection to internet thru proxy is normal, the way to check
        # is to check wither there is a valid IP address, there is IPV4 and IPV6, and/or the green dot around
        # the typical web site.

        this_step, step_words = genStepCreateData("string", "web_tab", "NA", "", stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global web_tab, ads_profile_remark\nweb_tab = '-'+ads_profile_remark\nprint('web_tab:', web_tab)", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverGoToTab("web_driver", "web_tab", "", "site_result", "site_flag", this_step)
        psk_words = psk_words + step_words

        # Locate the element containing the IP address
        # ip_element = driver.find_element(By.CSS_SELECTOR, "span._header__ip_k1rq8_55")
        # ip_address = ip_element.text
        #
        # # Locate the element containing the location information
        # location_element = driver.find_element(By.CSS_SELECTOR, "div._header__location_k1rq8_93")
        # location = location_element.text
        #
        # print("IP Address:", ip_address)
        # print("Location:", location)

        this_step, step_words = genStepCallExtern("global not_logged_in\nnot_logged_in = False", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("int", "num_tries", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "location_info1", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "location_info2", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "email_filled", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "pw_filled", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "pw_field", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "email_field", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "continue_button", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "signin_button", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # retry a few times
        this_step, step_words = genStepLoop("'USA' not in location_info1 and 'USA' not in location_info2 and num_tries < 5", "", "", "connProxy" + str(stepN), this_step)
        psk_words = psk_words + step_words

        # just keep on refreshing....

        # refresh the page with selenium
        this_step, step_words = genStepWebdriverRefreshPage("web_driver", "site_flag", this_step)
        psk_words = psk_words + step_words

        # wait some random time for proxy to connect
        this_step, step_words = genStepWait(0, 5, 8, this_step)
        psk_words = psk_words + step_words


        # after page load, find the location info. some times it's like this,
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, "div._header__location_k1rq8_93", False, "var", "location_info1", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not location_info1", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global location_info1\nlocation_info1= ''", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # Locate the element containing the text, other times, it's like this,
        # element = driver.find_element(By.CSS_SELECTOR, ".locales")

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'text'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, ".locales", False, "var", "location_info2", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not location_info2", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global location_info2\nlocation_info2 = ''", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # update loop counter
        this_step, step_words = genStepCallExtern("num_tries = num_tries + 1", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("'USA' in location_info1 or 'USA' in location_info2", "", "", this_step)
        psk_words = psk_words + step_words

        # if internet is conencted, to amazon site
        # if there is, click on "Amazon.com"
        # open the site page.

        # this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global web_tab, ads_profile_remark\nweb_tab = 'amazon'\nprint('web_tab:', web_tab)", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverGoToTab("web_driver", "web_tab", "https://www.amazon.com", "site_result", "site_flag", this_step)
        psk_words = psk_words + step_words


        # else condition for "ip_obtained"
        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global mission_failed\nmission_failed = True", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # end condition for "ip_obtained"
        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words
        #
        # make sure logged in. by check whether there is "sign in" to the right of "Hello"(info ref_method=1), if so, move mouse over to "hello", then
        #  click on "sign in" button below, then type in "email" and hit "continue" button, then type in password and hit "Sign in" button
        # once in, double check the Hello - sign in relation ship again to double check. then, calibrate screen.
        # typically its expected that the account is already setup on ADS, so that the account should be logged in directly...

        # greeting_element = driver.find_element(By.ID, "nav-link-accountList-nav-line-1")
        # greeting_text = greeting_element.text
        #
        # # Determine login status based on the greeting
        # if "Hello, " in greeting_text and "Sign in" not in greeting_text:
        #     print("You are logged in as:", greeting_text.split("Hello, ")[1])
        # else:
        #     print("You are not logged in.")

        this_step, step_words = genStepCheckCondition("not mission_failed", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-link-accountList-nav-line-1', True, "var", "greeting_text", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("'Sign in' in greeting_text", "", "", this_step)
        psk_words = psk_words + step_words

        # Check if the user is already logged in by looking for "Sign in" text
        # sign_in_text = driver.find_element(By.XPATH, "//span[@class='nav-action-inner' and contains(text(), 'Sign in')]")
        #
        # # If found, proceed with hover and click actions
        # if sign_in_text.is_displayed():
        #     # Locate the "Account & Lists" element
        #     account_lists = driver.find_element(By.XPATH,
        #                                         "//span[@class='nav-line-2 ' and contains(text(), 'Account & Lists')]")
        #
        #     # Hover over "Account & Lists" to trigger the drop-down
        #     ActionChains(driver).move_to_element(account_lists).perform()
        #     time.sleep(2)  # Wait for the drop-down to fully appear
        #
        #     # Click the "Sign in" button in the drop-down
        #     sign_in_button = driver.find_element(By.XPATH,
        #                                          "//span[@class='nav-action-inner' and contains(text(), 'Sign in')]")
        #     sign_in_button.click()
        #
        #     # Optional: wait for the login page to load
        #     time.sleep(2)
        # else:
        #     print("Already logged in.")

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-link-accountList-nav-line-1', True, "var", "greeting_text", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverHoverTo("web_driver", "account_lists", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-link-accountList-nav-line-1', True, "var", "greeting_text", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "signin_button", "click_result", "click_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(2, 0, 0, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'ap_email', True, "var", "email_field", "extract_flag", this_step)
        psk_words = psk_words + step_words

        # if the user email fill-in page appears.....
        this_step, step_words = genStepCheckCondition("extract_flag", "", "", this_step)
        psk_words = psk_words + step_words

        # check if pw field is already filled in with default pw, if not, key in the pw
        this_step, step_words = genStepWebdriverGetValueFromWebElement("web_driver", "email_field", "", "email_filled", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not email_filled", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverKeyIn("web_driver", "email_field", "user_email", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'continue', True, "var", "continue_button", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "continue_button", "click_result", "click_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # now work on the pw part....
        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'ap_password', True, "var", "pw_field", "extract_flag", this_step)
        psk_words = psk_words + step_words

        # check if pw field is already filled in with default pw, if not, key in the pw
        this_step, step_words = genStepWebdriverGetValueFromWebElement("web_driver", "pw_field", "", "pw_filled", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not pw_filled", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverKeyIn("web_driver", "pw_field", "user_pw", "action_result", "extract_flag",  this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # click the sign in button to sign in after pw is filled.
        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'signInSubmit', True, "var", "signin_button", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "signin_button", "click_result", "click_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        # Click on the password field to bring up the saved password suggestions
        # password_field = driver.find_element(By.ID, "ap_password")
        # password_field.click()
        #
        # # Small delay to allow password manager to display suggestions (adjust if necessary)
        # time.sleep(2)
        #
        # # Use arrow keys to navigate to the correct suggestion, then hit Enter
        # password_field.send_keys(Keys.ARROW_DOWN)  # Adjust ARROW_DOWN or ARROW_UP as needed
        # password_field.send_keys(Keys.ENTER)
        #
        # # Optionally wait and check if the password is filled
        # time.sleep(1)
        # filled_password = password_field.get_attribute("value")
        # if filled_password:
        #     print("Password autofilled successfully.")
        # else:
        #     print("Autofill did not complete as expected.")

        # Locate the sign-in button by its ID and click it
        # sign_in_button = driver.find_element(By.ID, "signInSubmit")
        # sign_in_button.click()

        # finally after signing in, do a sanity check.
        this_step, step_words = genStepWait(0, 5, 8, this_step)
        psk_words = psk_words + step_words

        # look at header greeting text again....
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID, 'nav-link-accountList-nav-line-1', True, "var", "greeting_text", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not greeting_text or 'Sign in' not in greeting_text", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global not_logged_in\nnot_logged_in = True", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        # end condition for need to sign in
        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("else", "", "", this_step)
        psk_words = psk_words + step_words

        # set not logged in because internet is not available
        this_step, step_words = genStepCallExtern("global not_logged_in\nnot_logged_in = True", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # end condition for if not mission_failed. (internet is connected)
        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserLoginIn: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserLoginIn: {ex_stat}")

    return this_step, psk_words


# near attention would be 1~2 rows above the target, a save bet would get a randome offset int between 4 and 8
# the minus this offset number from the target index. and scroll to that item.
def genStepsAMZBrowseScrollNearNextAttention(pl, here, there, stepN, worksettings):
    try:
        psk_words = ""

        this_step, step_words = genStepCreateData("obj", "near_target_title", "NA", None, stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global near_target_title, "+there+", "+pl+"\nnear_target_title = "+pl+"['products']['pl']["+there+"]['summery']['title']", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("obj", "title_elements", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "attention_title_texts", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR, 'h2.a-size-mini.a-spacing-none.a-color-base.s-line-clamp-4 a', True, "var", "title_elements", "extract_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global attention_titles, near_target_title, title_elements\nattention_titles= [te for te in title_elements if te.text in near_target_title]", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global attention_titles, attention_title_texts\nattention_title_texts= [te.text for te in attention_titles]\nprint('attention_title_texts:',attention_title_texts)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global title_elements\nprint('title_elements', attention_titles, len(attention_titles))", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("len(attention_titles) > 0", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global attention_titles, title_tbc\ntitle_tbc = attention_titles[0]", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global attention_titles, title_tbc\nprint('attention_titles:', attention_titles, 'title_tbc:', title_tbc.text)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        #smoothl scroll to the target item which is near the to be attended item.
        this_step, step_words = genStepWebdriverScrollTo("web_driver", "title_tbc", 10, 30, 0.25, "dummy_in", "element_present", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("print('END OF BROWSING PRODUCT LISTS NEAR NEXT ATTENTION.....',"+there+", title_tbc.text)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowseScrollNearNextAttention: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowseScrollNearNextAttention: {ex_stat}")

    return this_step,psk_words



def genStepsWinChromeAMZBrowserCheckProductFeedbacks(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN, theme):
    try:
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


        # assume already logged in, click on "& Orders"
        this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "my_orders", "anchor text", "Search Amazon", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
        psk_words = psk_words + step_words

        # now we're in order page, search for the order placed,


        # click on the product which will lead into the product page. click on "# ratings"


        # click "top reviews" and switch to "most recent"


        # now save html file, and scrape html file to see whether the FB appears.

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinChromeAMZBrowserCheckProductFeedbacks: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinChromeAMZBrowserCheckProductFeedbacks: {ex_stat}")

    return this_step, psk_words



def genStepsWinChromeAMZBrowserCheckSellerFeedbacks(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN, theme):
    try:
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


        # assume already logged in, click on "& Orders"
        this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "my_orders", "anchor text", "Search Amazon", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
        psk_words = psk_words + step_words

        # now we're in order page, search for the order placed,


        # click on the product which will lead into the product page. click on "# ratings"


        # click "top reviews" and switch to "most recent"


        # now save html file, and scrape html file to see whether the FB appears.

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinChromeAMZBrowserCheckSellerFeedbacks: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinChromeAMZBrowserCheckSellerFeedbacks: {ex_stat}")

    return this_step, psk_words


def genStepsAMZBrowserPagePeekAndClick(eleType, eleName, resultName, stepN):
    try:
        psk_words = ""

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", eleType, eleName, False, "var", resultName, "element_present", stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", resultName, "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsAMZBrowserPagePeekAndClick: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsAMZBrowserPagePeekAndClick: {ex_stat}")

    return this_step, psk_words


def genWinChromeAMZTeamPrepSkill(worksettings, stepN, theme):

    log3("GENERATING genWinChromeAMZTeamPrepSkill======>")
    this_step = stepN
    psk_words = "{"

    try:
        this_step, step_words = genStepHeader("win_chrome_amz_browse_search", "win", "1.0", "AIPPS LLC",
                                              "PUBWINCHROMEAMZTEAMPREP005",
                                              "AMZ Daily Prep On Windows Chrome.", stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("start skill main", "public/win_chrome_amz_home/team_prep", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "daily_schedule", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "fetch_success", "NA", False, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "prep_success", "NA", False, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "dispatch_success", "NA", False, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "profiles_updated", "NA", False, this_step)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepCreateData("string", "file_path", "NA", "daily_prep_hook.py", this_step)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "file_prefix", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global file_name, file_prefix, sk_work_settings\nfile_prefix=sk_work_settings['local_data_path']+'/my_skills/hooks'\nfile_name = 'team_prep_hook.py'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "params", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("import utils.logger_helper\nglobal params, symTab\nparams={}\nparams['symTab']=symTab\nparams['login']=utils.logger_helper.login\nparams['test_mode']=False", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "ts_name", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "forceful", "NA", "false", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "hook_result", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "works_ready_to_dispatch", "NA", None, this_step)
        psk_words = psk_words + step_words

        # fetch daily schedule
        this_step, step_words = genStepECBFetchDailySchedule("ts_name", "forceful", "daily_schedule", "fetch_success", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepECBCollectBotProfiles("op_results", "profiles_updated", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global params, daily_schedule\nparams['daily_schedule']=daily_schedule\n", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # do some external work - basically do a round of filtering (filter out the accounts not suitable to run)
        # 1) check whether an account has enough resource to do the job(funding)
        # 2）for the ones qualified to run, fill in buy details.
        this_step, step_words = genStepExternalHook("var", "file_prefix", "file_name","params", "hook_result", "prep_success", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global works_ready_to_dispatch, hook_result\nworks_ready_to_dispatch=hook_result['result']\n", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # dispatch the works to the worker agents.
        this_step, step_words = genStepECBDispatchTroops("works_ready_to_dispatch", "dispatch_result", "dispatch_success", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end skill", "public/win_chrome_amz_home/team_prep", "", this_step)
        psk_words = psk_words + step_words

        psk_words = psk_words + "\"dummy\" : \"\"}"
        # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genWinChromeAMZTeamPrepSkill: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genWinChromeAMZTeamPrepSkill: {ex_stat}")

    return this_step, psk_words

def genWinChromeAMZDailyHousekeepingSkill(worksettings, stepN, theme):
    log3("GENERATING genWinChromeAMZDailyHousekeepingSkill======>")
    this_step = stepN
    psk_words = "{"
    site_url = "https://www.amazon.com/"
    try:

        this_step, step_words = genStepHeader("win_ads_amz_browse_search", "win", "1.0", "AIPPS LLC",
                                              "PUBWINCHROMEAMZDAILYHOUSEKEEPING006",
                                              "AMZ Daily Housekeeping On Windows Chrome.", stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("start skill", "public/win_chrome_amz_home/daily_housekeeping", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global file_name, file_prefix\nfile_prefix=''\nfile_name = 'daily_housekeeping.py'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "file_name", "NA", "daily_prep_hook.py", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "daily_report_data", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "file_prefix", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global file_name, file_prefix, sk_work_settings\nfile_prefix=sk_work_settings['local_data_path']+'/my_skills/hooks'\nfile_name = 'daily_housekeeping_hook.py'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "params", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("import utils.logger_helper\nglobal params, symTab\nparams={}\nparams['symTab']=symTab\nparams['login']=utils.logger_helper.login\nparams['test_mode']=False", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepExternalHook("var", "file_prefix", "file_name","params", "daily_report_data", "prep_success", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end skill", "public/win_chrome_amz_home/daily_housekeeping", "", this_step)
        psk_words = psk_words + step_words

        psk_words = psk_words + "\"dummy\" : \"\"}"
        # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genWinChromeAMZDailyHousekeepingSkill: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genWinChromeAMZDailyHousekeepingSkill: {ex_stat}")

    return this_step, psk_words

def genStepsWinADSAMZDetectRiskFlagged(worksettings, stepN, theme):

    log3("GENERATING genStepsWinADSAMZDetectRiskFlagged======>")
    this_step = stepN
    psk_words = ""

    try:
        this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "action_result", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "action_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        # check key words like "locked", "misuse"
        # button = driver.find_element(By.CSS_SELECTOR, "#prime-interstitial-accept-button .a-button-input")
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR,
                                                            '#prime-interstitial-accept-button .a-button-input', False, "var", "buy_prime_button",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        # click on buy prime membership only if there is a buy button, and there is enough money to do it.
        # even thought 1st month is free, but do make sure we have $16 on the balance.
        this_step, step_words = genStepCheckCondition("buy_prime_button", "", "", this_step)
        psk_words = psk_words + step_words

        # click on buy_prime_button button,
        this_step, step_words = genStepWebdriverClick("web_driver", "buy_prime_button", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinADSAMZDetectRiskFlagged: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinADSAMZDetectRiskFlagged: {ex_stat}")

    return this_step, psk_words


# after hit the buy button, will check whether need to buy prime membership
#if there is such option, then buy it.
def genStepsWinADSAMZBuyPrimeMembership(worksettings, stepN, theme):

    log3("GENERATING genStepsWinADSAMZBuyPrimeMembership======>")
    this_step = stepN
    psk_words = ""

    try:
        this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "action_result", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "action_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
                                                            'twotabsearchtextbox', False, "var", "search_box",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "search_phrase", "NA", "yoga ball", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global search_phrase, nthSearch, run_config\nsearch_phrase= run_config['searches'][nthSearch]['entry_paths']['words']",
            "", "in_line", "",
            this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverKeyIn("web_driver", "search_box", "search_phrase", "action_result",
                                                      "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        # button = driver.find_element(By.CSS_SELECTOR, "#prime-interstitial-accept-button .a-button-input")
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR,
                                                            '#prime-interstitial-accept-button .a-button-input', False, "var", "buy_prime_button",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        # click on buy prime membership only if there is a buy button, and there is enough money to do it.
        # even thought 1st month is free, but do make sure we have $16 on the balance.
        this_step, step_words = genStepCheckCondition("buy_prime_button", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("enough_fund", "", "", this_step)
        psk_words = psk_words + step_words

        # click on buy_prime_button button,
        this_step, step_words = genStepWebdriverClick("web_driver", "buy_prime_button", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words



        this_step, step_words = genStepCreateData("boolean", "profiles_updated", "NA", False, this_step)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepCreateData("string", "file_path", "NA", "daily_prep_hook.py", this_step)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "file_prefix", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global file_name, file_prefix, sk_work_settings\nfile_prefix=sk_work_settings['local_data_path']+'/my_skills/hooks'\nfile_name = 'record_subscription_hook.py'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "params", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("import utils.logger_helper\nglobal params, symTab\nparams={}\nparams['symTab']=symTab\nparams['login']=utils.logger_helper.login\nparams['test_mode']=True", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "hook_result", "NA", None, this_step)
        psk_words = psk_words + step_words


        # do some external work - record the prime membership subscription, so that later on we can
        # check to make sure card has enough fund on this date every month.....
        this_step, step_words = genStepExternalHook("var", "file_prefix", "file_name","params", "hook_result", "prep_success", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinADSAMZBuyPrimeMembership: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinADSAMZBuyPrimeMembership: {ex_stat}")

    return this_step, psk_words


# this is for detecting offer to join prime at page header entering product details page.
# this section is inside the buy box.
def genStepsWinADSAMZDetectNonePrime(stepN):

    log3("GENERATING genStepsWinADSAMZDetectNonePrime======>")
    this_step = stepN
    psk_words = ""

    try:
        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("obj", "buy_box_secondary_delivery_msg", "NA", None, this_step)
        psk_words = psk_words + step_words

        # delivery_block = WebDriverWait(driver, 10).until(
        #     EC.presence_of_element_located((By.ID, "mir-layout-DELIVERY_BLOCK-slot-SECONDARY_DELIVERY_MESSAGE_LARGE"))
        # )
        #
        # # Extract delivery details
        # delivery_date = delivery_block.find_element(By.CSS_SELECTOR, "span.a-text-bold").text
        # order_cutoff = delivery_block.find_element(By.ID, "ftCountdown").text
        # prime_info = delivery_block.find_element(By.CSS_SELECTOR, "span[style*='color:#0064F9']").text
        #
        # # Extract link for joining Prime
        # join_prime_link = delivery_block.find_element(By.CSS_SELECTOR, "a.prime-signup-ingress").get_attribute("href")

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.ID,
                                                            'mir-layout-DELIVERY_BLOCK-slot-SECONDARY_DELIVERY_MESSAGE_LARGE', False, "var", "buy_box_secondary_delivery_msg",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "join_prime_link", "NA", None, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "buy_box_secondary_delivery_msg", 0, "info_type", By.CSS_SELECTOR,
                                                            'a.prime-signup-ingress', False, "var", "join_prime_link",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        # the output if this function is the global var "join_prime_link" other code can
        # check this object to know whether the user already has prime membership.

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinADSAMZDetectNonePrime: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinADSAMZDetectNonePrime: {ex_stat}")

    return this_step, psk_words


# this is for detecting offer to join prime after clicking on "proceed to checkout" button.
def genStepsWinADSAMZDetectPrimeOffer(stepN):

    log3("GENERATING genStepsWinADSAMZDetectPrimeOffer======>")
    this_step = stepN
    psk_words = ""

    try:
        this_step, step_words = genStepCreateData("obj", "savings_message", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "prime_offer_message", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "prime_offer", "NA", None, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        # # Locate and extract the "save $6.99" message
        # savings_message = driver.find_element(By.CSS_SELECTOR, "p.headline-upsell-message").text
        # print(f"Savings Message: {savings_message.strip()}")
        #
        # # Locate and extract the Prime membership offer message
        # prime_offer_message = driver.find_element(By.CSS_SELECTOR, "p.a-spacing-top-small.a-joinPrime-msg b").text
        # print(f"Prime Offer Message: {prime_offer_message.strip()}")

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.CSS_SELECTOR,
                                                            'p.headline-upsell-message', False, "var", "savings_message",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.CSS_SELECTOR,
                                                            'p.a-spacing-top-small.a-joinPrime-msg b', False, "var", "prime_offer_message",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words


        # # Locate the main container with the class "a-column a-span6 prime-updp-mobile-table-column a-span-last"
        # container = driver.find_element(By.CSS_SELECTOR, ".a-column.a-span6.prime-updp-mobile-table-column.a-span-last")
        #
        # # Extract individual rows containing the Prime benefits
        # rows = container.find_elements(By.CSS_SELECTOR, ".prime-updp-mobile-table-prime-option-content .a-column.a-span11")

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR,
                                                            '.a-column.a-span6.prime-updp-mobile-table-column.a-span-last', False, "var", "prime_offer",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "prime_benefits", "NA", [], this_step)
        psk_words = psk_words + step_words

        # the characteristic output of this function is the presence of "prime_offer" web element,
        # if it's present then, we know we need to buy prime membership, otherwise, already an member.

        this_step, step_words = genStepCheckCondition("prime_offer", "", "", this_step)
        psk_words = psk_words + step_words

        # check the benefits bullet items.,

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "prime_offer", 0, "info_type",
                                                            By.CSS_SELECTOR,
                                                            '.prime-updp-mobile-table-prime-option-content .a-column.a-span11',
                                                            False, "var", "prime_benefits",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words



    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinADSAMZDetectPrimeOffer: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinADSAMZDetectPrimeOffer: {ex_stat}")

    return this_step, psk_words



# this is gather all in-cart items, we might want to delete them
def genStepsWinADSAMZExtractInCartItems(stepN):

    log3("GENERATING genStepsWinADSAMZExtractInCartItems======>")
    this_step = stepN
    psk_words = ""

    try:
        this_step, step_words = genStepCreateData("obj", "cart_items", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "cart_form", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "select_all_checkbox", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        # select_all_checkbox = driver.find_element(By.CSS_SELECTOR,
        #                                           "input[type='checkbox'][aria-label='Select all items']")

        # WebDriverWait(driver, 10).until(
        #     EC.presence_of_element_located((By.ID, "activeCartViewForm"))
        # )

        # make sure the form is loaded.
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
                                                            'activeCartViewForm', False, "var", "cart_form",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        # extract the select all box, this will be used if we want to empty the cart quick.
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR,
                                                            "input[type='checkbox'][aria-label='Select all items']", False, "var", "select_all_checkbox",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR,
                                                            "div[data-name='Active Items'] .sc-list-item", False, "var", "cart_items",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        # cart_items = driver.find_elements(By.CSS_SELECTOR, "[data-name='Active Items'] .sc-list-item")
        # for index, item in enumerate(cart_items, start=1):
        #     print(f"\nItem {index}:")
        #
        #     # Extract item checkbox
        #     item_checkbox = item.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
        #
        #     # Extract product name
        #     product_name = item.find_element(By.CSS_SELECTOR, ".sc-product-title").text
        #
        #     # Extract quantity
        #     quantity = item.find_element(By.CSS_SELECTOR, "[aria-label^='Quantity is']").get_attribute("aria-valuenow")
        #
        #     # Extract price
        #     price = item.find_element(By.CSS_SELECTOR, ".sc-item-price-block .a-price .a-offscreen").text
        #
        #     # Extract delete button
        #     delete_button = item.find_element(By.CSS_SELECTOR, "input[type='submit'][value='Delete']")

        this_step, step_words = genStepCreateData("integer", "nthItem", "NA", 0, this_step)
        psk_words = psk_words + step_words

        his_step, step_words = genStepLoop("nthItem < len(cart_items)", "", "", "getCart" + str(stepN), this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global cart_item, nthItem, cart_items\ncart_item= cart_items[nthItem]", "", "in_line", "",
            this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "cart_item", 0, "info_type", By.CSS_SELECTOR,
                                                            "input[type='checkbox']", False, "var", "checkbox",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "cart_item", 0, "info_type", By.CSS_SELECTOR,
                                                            ".sc-product-title", False, "var", "title",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "cart_item", 0, "info_type", By.CSS_SELECTOR,
                                                            "[aria-label^='Quantity is']", False, "var", "quantity",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "cart_item", 0, "info_type", By.CSS_SELECTOR,
                                                            ".sc-item-price-block .a-price .a-offscreen", False, "var", "price",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "cart_item", 0, "info_type", By.CSS_SELECTOR,
                                                            "input[type='submit'][value='Delete']", False, "var", "del_button",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global nthItem\nnthItem = nthItem + 1\nprint('nthItem:', nthItem)", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words


    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinADSAMZExtractInCartItems: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinADSAMZExtractInCartItems: {ex_stat}")

    return this_step, psk_words


# this is for deleting items from cart, the input is a list of web elements in cart
# the name of this web element should be "cartItems"
# this function will click on each item's checkbox, and click on delete link .
# the input should be a list of index from largest to smallest, i.e. we'll
# delete from the tail of the list, because, each delete will refersh the list
# on the page with the deleted item disappeared.
#  while True:
#         # Wait for the cart items to load
#         WebDriverWait(driver, 10).until(
#             EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".sc-list-item"))
#         )
#
#         # Find all cart items
#         cart_items = driver.find_elements(By.CSS_SELECTOR, ".sc-list-item")
#         if not cart_items:
#             print("All items have been deleted from the cart.")
#             break
#
#         # Process the first item in the cart
#         first_item = cart_items[0]
#
#         # Ensure the checkbox is selected (if present)
#         try:
#             checkbox = first_item.find_element(By.CSS_SELECTOR, ".sc-item-check-checkbox-selector input[type='checkbox']")
#             if not checkbox.is_selected():
#                 checkbox.click()
#         except:
#             print("No checkbox found for this item. Proceeding to delete.")
#
#         # Click the delete button
#         delete_button = first_item.find_element(By.CSS_SELECTOR, "input[data-action='delete']")
#         delete_button.click()
#         print("Deleted one item from the cart.")
#
#         # Wait for the page to refresh after deletion
#         time.sleep(2)

# "del_indices" is the variable that contains the list of indeces, it could be string "All" which means to delete all.
def genStepsWinADSAMZRemoveItemsFromCart(stepN):

    log3("GENERATING genStepsWinADSAMZRemoveItemsFromCart======>")
    this_step = stepN
    psk_words = ""

    try:
        this_step, step_words = genStepCreateData("obj", "action_result", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "action_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR,
                                                            '.sc-list-item', False, "var", "cart_items",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not isinstance(del_indices, list)", "", "", this_step)
        psk_words = psk_words + step_words

        # indices_reversed = list(range(len(my_list) - 1, -1, -1))
        this_step, step_words = genStepCallExtern("global del_indices\ndel_indices= list(range(len(cart_items) - 1, -1, -1))", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        his_step, step_words = genStepLoop("del_indices", "", "", "getCart" + str(stepN), this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global cart_item, cart_items, del_indices\ncart_item= cart_items[del_indices[0]]", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "cart_item", 0, "info_type", By.CSS_SELECTOR,
                                                            ".sc-item-check-checkbox-selector input[type='checkbox']", False, "var", "item_checkbox",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not item_checkbox.is_selected()", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "item_checkbox", "action_result", "action_flag",
                                                      this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "cart_item", 0, "info_type", By.CSS_SELECTOR,
                                                            "input[data-action='delete']", False, "var", "item_delete",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "item_delete", "action_result", "action_flag",
                                                      this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR,
                                                            '.sc-list-item', False, "var", "cart_items",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global del_indices\ndel_indices.pop(0)", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinADSAMZRemoveItemsFromCart: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinADSAMZRemoveItemsFromCart: {ex_stat}")

    return this_step, psk_words



# this function check whether the cart is empty or not...
def genStepsWinADSAMZCheckEmptyCart(stepN):

    log3("GENERATING genStepsWinADSAMZCheckEmptyCart======>")
    this_step = stepN
    psk_words = ""

    try:
        # subtotal_label = driver.find_element(By.ID, "sc-subtotal-label-activecart")
        this_step, step_words = genStepCreateData("obj", "subtotal_label", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("integer", "nCartItems", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.ID,
                                                            'sc-subtotal-label-activecart', False, "var", "subtotal_label",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        # Example: "Subtotal (2 items):"
        this_step, step_words = genStepCallExtern(
            "global nCartItems, subtotal_label\nnCartItems= int(subtotal_label.split('(')[1].split(')')[0].split()[0].strip())",
            "", "in_line", "",
            this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinADSAMZCheckEmptyCart: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinADSAMZCheckEmptyCart: {ex_stat}")

    return this_step, psk_words
