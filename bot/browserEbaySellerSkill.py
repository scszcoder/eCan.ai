import copy
import os
from datetime import datetime

from bot.amzBuyerSkill import found_match
from bot.basicSkill import genStepHeader, genStepStub, genStepWait, genStepCreateData, genStepGoToWindow, \
    genStepCheckCondition, genStepUseSkill, genStepOpenApp, genStepCallExtern, genStepLoop, genStepExtractInfo, \
    genStepSearchAnchorInfo, genStepMouseClick, genStepMouseScroll, genStepCreateDir, genStepKeyInput, genStepTextInput, \
    STEP_GAP, DEFAULT_RUN_STATUS, symTab, genStepThink, genStepSearchWordLine, genStepCalcObjectsDistance, \
    genScrollDownUntilLoc, genStepMoveDownloadedFileToDestination
from bot.Logger import log3
from bot.scraperEbay import genStepEbayScrapeOrdersFromHtml, genStepEbayScrapeMsgList, genStepEbayScrapeOrdersFromJss
from bot.seleniumSkill import *
from bot.seleniumScrapeEBayShop import *
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


def genWinADSEbayBrowserFullfillOrdersSkill(worksettings, stepN, theme):
    print("fullfill using ebay labels")
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY011",
                                          "Selenium Ebay Fullfill New Orders On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/browser_fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinADSEbayBrowserInitializeSetup(worksettings, this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not_logged_in == False", "", "", this_step)
    psk_words = psk_words + step_words

    # skname, skfname, in-args, output, step number
    this_step, step_words = genStepUseSkill("browser_collect_orders", "public/win_ads_ebay_orders", "dummy_in", "ebay_orders", this_step)
    psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.
    # first organized order list data into 2 xls for bulk label purchase, and calcualte total funding requird for this action.


    this_step, step_words = genStepCreateData("expr", "buy_shipping_input", "NA", "['sale', ebay_orders, product_catelog]", this_step)
    psk_words = psk_words + step_words
    #
    # using ebay to purchase shipping label will auto update tracking code..... s
    this_step, step_words = genStepUseSkill("buy_shipping", "public/win_ads_ebay_orders", "buy_shipping_input", "labels_dir", this_step)
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
    this_step, step_words = genStepCreateData("expr", "reformat_print_input", "NA", "['one page', 'labels_dir', printer_name, ebay_orders, product_catelog]", this_step)
    psk_words = psk_words + step_words

    # # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    this_step, step_words = genStepUseSkill("reformat_print", "public/win_printer_local_print", "labels_dir", "", this_step)
    psk_words = psk_words + step_words
    #
    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words
    #
    # # close the browser and exit the skill, assuming at the end of genWinChromeEBAYWalkSteps, the browser tab
    # # should return to top of the ebay home page with the search text box cleared.
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

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_fullfill_orders", "", this_step)
    psk_words = psk_words + step_words
    print("generating win ads ebay skill")
    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay order browser fullfill operation...." + psk_words)

    return this_step, psk_words


def genWinADSEbayBrowserFullfillOrdersWithECBLabelsSkill(worksettings, stepN, theme):
    print("fullfill using ebay labels")
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_fullfill_orders", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSEBAY011",
                                          "Selenium Ebay Fullfill New Orders On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/browser_fullfill_orders", "",
                                        this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinADSEbayBrowserInitializeSetup(worksettings, this_step, theme)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCheckCondition("not_logged_in == False", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # skname, skfname, in-args, output, step number
    # this_step, step_words = genStepUseSkill("browser_collect_orders", "public/win_ads_ebay_orders", "dummy_in",
    #                                         "ebay_orders", this_step)
    # psk_words = psk_words + step_words
    #
    # # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.
    # # first organized order list data into 2 xls for bulk label purchase, and calcualte total funding requird for this action.
    #
    # this_step, step_words = genStepCreateData("expr", "buy_shipping_input", "NA",
    #                                           "['sale', ebay_orders, product_catelog]", this_step)
    # psk_words = psk_words + step_words
    # #
    # # using ebay to purchase shipping label will auto update tracking code..... s
    # this_step, step_words = genStepUseSkill("buy_shipping", "public/win_ads_ebay_orders", "buy_shipping_input",
    #                                         "labels_dir", this_step)
    # psk_words = psk_words + step_words
    #
    # # # extract tracking code from labels and update them into etsy_orders data struture.
    # #
    # # # gen_etsy_test_data()
    # #
    # # # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]
    # # # now update tracking coded back to the orderlist
    # # this_step, step_words = genStepUseSkill("update_tracking", "public/win_ads_ebay_orders", "gs_input", "total_label_cost", this_step)
    # # psk_words = psk_words + step_words
    # #
    # this_step, step_words = genStepCreateData("expr", "reformat_print_input", "NA",
    #                                           "['one page', 'labels_dir', printer_name, ebay_orders, product_catelog]",
    #                                           this_step)
    # psk_words = psk_words + step_words
    #
    # # # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    # this_step, step_words = genStepUseSkill("reformat_print", "public/win_printer_local_print", "labels_dir", "",
    #                                         this_step)
    # psk_words = psk_words + step_words
    # #
    # # end condition for "not_logged_in == False"
    # this_step, step_words = genStepStub("end condition", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # close the browser and exit the skill, assuming at the end of genWinChromeEBAYWalkSteps, the browser tab
    # # should return to top of the ebay home page with the search text box cleared.
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

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_fullfill_orders", "",
                                        this_step)
    psk_words = psk_words + step_words
    print("generating win ads ebay skill")
    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay order browser fullfill operation...." + psk_words)

    return this_step, psk_words

def genWinADSEbayBrowserBuyShippingSkill(worksettings, stepN, theme):
    print("fullfill using ebay labels")
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_fullfill_orders", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSEBAY011",
                                          "Selenium Ebay Fullfill New Orders On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/browser_fullfill_orders", "",
                                        this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinADSEbayBrowserInitializeSetup(worksettings, this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not_logged_in == False", "", "", this_step)
    psk_words = psk_words + step_words

    # skname, skfname, in-args, output, step number
    this_step, step_words = genStepUseSkill("browser_collect_orders", "public/win_ads_ebay_orders", "dummy_in",
                                            "ebay_orders", this_step)
    psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.
    # first organized order list data into 2 xls for bulk label purchase, and calcualte total funding requird for this action.

    this_step, step_words = genStepCreateData("expr", "buy_shipping_input", "NA",
                                              "['sale', ebay_orders, product_catelog]", this_step)
    psk_words = psk_words + step_words
    #
    # using ebay to purchase shipping label will auto update tracking code..... s
    this_step, step_words = genStepUseSkill("buy_shipping", "public/win_ads_ebay_orders", "buy_shipping_input",
                                            "labels_dir", this_step)
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
    this_step, step_words = genStepCreateData("expr", "reformat_print_input", "NA",
                                              "['one page', 'labels_dir', printer_name, ebay_orders, product_catelog]",
                                              this_step)
    psk_words = psk_words + step_words

    # # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    this_step, step_words = genStepUseSkill("reformat_print", "public/win_printer_local_print", "labels_dir", "",
                                            this_step)
    psk_words = psk_words + step_words
    #
    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words
    #
    # # close the browser and exit the skill, assuming at the end of genWinChromeEBAYWalkSteps, the browser tab
    # # should return to top of the ebay home page with the search text box cleared.
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

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_fullfill_orders", "",
                                        this_step)
    psk_words = psk_words + step_words
    print("generating win ads ebay skill")
    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay order browser fullfill operation...." + psk_words)

    return this_step, psk_words

def genWinADSEbayBrowserBuyECBLabelsSkill(worksettings, stepN, theme):
    print("fullfill using ebay labels")
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_buy_ecb_labels", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSEBAY031",
                                          "In-Browser Ebay Buy ECB labels using external skill.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/browser_fullfill_orders", "",
                                        this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinADSEbayBrowserInitializeSetup(worksettings, this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not_logged_in == False", "", "", this_step)
    psk_words = psk_words + step_words

    # skname, skfname, in-args, output, step number
    this_step, step_words = genStepUseSkill("browser_collect_orders", "public/win_ads_ebay_orders", "dummy_in",
                                            "ebay_orders", this_step)
    psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.
    # first organized order list data into 2 xls for bulk label purchase, and calcualte total funding requird for this action.

    this_step, step_words = genStepCreateData("expr", "buy_shipping_input", "NA",
                                              "['sale', ebay_orders, product_catelog]", this_step)
    psk_words = psk_words + step_words
    #
    # using ebay to purchase shipping label will auto update tracking code..... s
    this_step, step_words = genStepUseSkill("buy_shipping", "public/win_ads_ebay_orders", "buy_shipping_input",
                                            "labels_dir", this_step)
    psk_words = psk_words + step_words

    # # extract tracking code from labels and update them into etsy_orders data struture.
    #
    # # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]
    # # now update tracking coded back to the orderlist
    # this_step, step_words = genStepUseSkill("update_tracking", "public/win_ads_ebay_orders", "gs_input", "total_label_cost", this_step)
    # psk_words = psk_words + step_words
    #
    this_step, step_words = genStepCreateData("expr", "reformat_print_input", "NA",
                                              "['one page', 'labels_dir', printer_name, ebay_orders, product_catelog]",
                                              this_step)
    psk_words = psk_words + step_words

    # # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    this_step, step_words = genStepUseSkill("reformat_print", "public/win_printer_local_print", "labels_dir", "", this_step)
    psk_words = psk_words + step_words
    #
    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words
    #
    # # close the browser and exit the skill, assuming at the end of genWinChromeEBAYWalkSteps, the browser tab
    # # should return to top of the ebay home page with the search text box cleared.
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

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_fullfill_orders", "",
                                        this_step)
    psk_words = psk_words + step_words
    print("generating win ads ebay skill")
    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay order browser fullfill operation...." + psk_words)

    return this_step, psk_words

def genWinADSEbayBrowserInitializeSetup(worksettings, stepN, theme):
    psk_words = ""

    this_step, step_words = genStepCreateData("string", "ebay_status", "NA", "", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "web_driver", "NA", None, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "product_book", "NA", "sk_work_settings['products']", this_step)
    psk_words = psk_words + step_words

    # mask out for testing purpose only....
    this_step, step_words = genStepCreateData("expr", "ebay_orders", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "dummy_in", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_resolution", "NA", 253, this_step)
    psk_words = psk_words + step_words

    # hard default exe path code here just for testing purpose, eventually will be from input or settings....
    this_step, step_words = genStepCreateData("str", "sevenZExe", "NA", 'C:/Program Files/7-Zip/7z.exe', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("str", "rarExe", "NA", 'C:/Program Files/WinRaR/WinRaR.exe', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "open_profile_input", "NA", "[sk_work_settings['batch_profile']]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ads_port", "NA", "sk_work_settings['batch_profile']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ads_profile_id", "NA", "sk_work_settings['batch_profile']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ads_api_key", "NA", "sk_work_settings['batch_profile']",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_resolution", "NA", 250, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "retry_count", "NA", 5, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "mission_failed", "NA", False, this_step)
    psk_words = psk_words + step_words

    # first call subskill to open ADS Power App, and check whether the user profile is already loaded?
    this_step, step_words = genStepUseSkill("open_profile", "public/win_ads_local_open", "open_profile_input", "ads_up",
                                            this_step)
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

    this_step, step_words = genStepSearchWordLine("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "no_data", "direct", "anchor text", "any", "useless", "nothing_loaded", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not bot_loaded and not nothing_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    # if not on screen, scroll down and check again.
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 80, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
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

    this_step, step_words = genStepCreateData("expr", "product_catelog", "NA", "sk_work_settings['products']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "machine_os", "NA", "sk_work_settings['platform']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "batch_import_input", "NA", "['open', profile_name_path, profile_name, bot_email, full_site, machine_os]", this_step)
    psk_words = psk_words + step_words

    # once the correct user profile is loaded, the open button corresponding to the user profile will be clicked to open the profile.
    this_step, step_words = genStepUseSkill("batch_import", "public/win_ads_local_load", "batch_import_input",
                                            "browser_up", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern( "global dyn_options\ndyn_options = {'anchors': [{'anchor_name': 'bot_user', 'anchor_type': 'text', 'template': bot_email, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'bot_open', 'anchor_type': 'text', 'template': 'Open', 'ref_method': '1', 'ref_location': [{'ref': 'bot_user', 'side': 'right', 'dir': '>', 'offset': '1', 'offset_unit': 'box'}]}], 'attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # wait 9 seconds for the browser to be brought up.
    this_step, step_words = genStepWait(8, 1, 3, this_step)
    psk_words = psk_words + step_words

    # use web driver to open the profile.
    this_step, step_words = genStepWebdriverStartExistingADS("web_driver", "ads_api_key", "ads_profile_id", "ads_port",
                                                             "web_driver_options", "web_driver_successful", this_step)
    psk_words = psk_words + step_words

    # now open the target web site.
    this_step, step_words = genStepWebdriverGoToTab("web_driver", "tab_text", "site", "site_result", "site_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genEbayLoginInSteps(this_step, theme)
    psk_words = psk_words + step_words

    return this_step, psk_words



# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinADSEbayBrowserCollectOrdersSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_collect_orders", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY021",
                                          "in Browser Ebay Collect New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_ebay_orders/browser_collect_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepOpenApp("cmd", True, "browser", site_url, "", "", "expr", "sk_work_settings['cargs']", 5, this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "currentPage", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "pageOfOrders", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "fileStatus", "NA", "None", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("from datetime import datetime\nglobal hf_name\nhf_name= 'ebayOrders'+ str(int(datetime.now().timestamp()))+'.html'\nprint('hf_name:',hf_name,datetime.now())", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


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


    this_step, step_words = genStepWait(2, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("endOfOrderList != True", "", "", "browseEbayOL" + str(stepN), this_step)
    psk_words = psk_words + step_words


    ##############################################################################################
    # at the end of the page, save html, now with detailed address info shown... and scrape html to
    # get all order information including the detailed address...
    ##############################################################################################

    this_step, step_words = genStepCreateDir("sk_work_settings['log_path']", "expr", "fileStatus", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", 'table-grid-component', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "src_type", "NA", 'var', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "result_type", "NA", 'var', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "info_type", "NA", 'web element', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ele_type", "NA", By.CLASS_NAME, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ele_type", "NA", By.CLASS_NAME, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "order_table", "NA", None, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "order_summary", "NA", None, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "extract_flag", "NA", True, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "PAGE", 10, "info_type", "ele_type", "ele_name", "result_type", "order_table", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'text'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ele_type", "NA", By.CSS_SELECTOR, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", '.summary-h2 .summary-content', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "PAGE", 0, "info_type", "ele_type", "ele_name", "result_type", "order_summary", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "n_orders", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # Get the order summary details
    this_step, step_words = genStepCreateData("string", "ele_name", "NA", '#totalOrdersCount', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "PAGE", 0, "info_type", "ele_type", "ele_name", "result_type", "n_orders", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "order_rows", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", 'tr.order-info', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "order_table", 0, "info_type", "ele_type", "ele_name", "result_type", "order_rows", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "n_orders_collected", "NA", 0, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepLoop("n_orders_collected < len(order_rows)", "", "", "BrCollectOrd" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global order_row, order_rows, n_orders_collected\norder_row = order_rows[n_orders_collected]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "order_id", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", '.order-details a', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'text'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "order_row", 0, "info_type", "ele_type", "ele_name", "result_type", "order_id", "extract_flag", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("expr", "customer_name", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", '.user-name', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "order_row", 0, "info_type", "ele_type", "ele_name", "result_type", "customer_name", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "addr_zip", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", '.zip-code', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "order_row", 0, "info_type", "ele_type", "ele_name", "result_type", "addr_zip", "extract_flag", this_step)
    psk_words = psk_words + step_words

    #        # Find the corresponding item details row
    #         item_info_row = driver.find_element(By.ID, f'orderid_{order_number}__item-info_0')
    #         product_name = item_info_row.find_element(By.CSS_SELECTOR, '.item-title a').text
    #         product_id = item_info_row.find_element(By.CSS_SELECTOR, '.item-itemID').text
    #         quantity = order_row.find_element(By.CSS_SELECTOR, '.quantity strong').text
    #         date_sold = order_row.find_element(By.CSS_SELECTOR, '.date-column .sh-default').text

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ele_type", "NA", By.ID, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "item_info_row", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ele_name", "NA", "'orderid_'+order_id+'__item-info_0'", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "PAGE", 0, "info_type", "ele_type", "ele_name", "result_type", "item_info_row", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ele_type", "NA", By.CSS_SELECTOR, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "product_name", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", '.item-title a', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "item_info_row", 0, "info_type", "ele_type", "ele_name", "result_type", "product_name", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "product_id", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", '.item-itemID', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "item_info_row", 0, "info_type", "ele_type", "ele_name", "result_type", "product_id", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "quantity", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", '.quantity strong', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "item_info_row", 0, "info_type", "ele_type", "ele_name", "result_type", "quantity", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "date_sold", "NA", "None", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", '.date-column .sh-default', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "item_info_row", 0, "info_type", "ele_type", "ele_name", "result_type", "date_sold", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global n_orders_collected\nn_orders_collected = n_orders_collected + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global n_orders_collected\nn_orders_collected = n_orders_collected + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # wait = WebDriverWait(driver, 10)
    #     wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, 'script')))
    # Step 2: Extract JavaScript Source Code
    # Locate the script tags and extract their content. You need to find the script that contains the order details.
    #
    # python
    # 复制代码
    #     # Extract all script elements
    #     scripts = driver.find_elements(By.TAG_NAME, 'script')

    this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "ele_type", "NA", By.TAG_NAME, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ele_name", "NA", 'script', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("web_driver", "src_type", "PAGE", 10, "info_type", "ele_type", "ele_name", "result_type", "jss", "extract_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEbayScrapeOrdersFromJss("jss", "var", "pidx", "page_of_orders", "scrape_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    #########################end of re-scrape html to obtain recipient address details. ######################
    # now check to see whether there are more pages to visit. i.e. number of orders exceeds more than 1 page.
    # the number of pages and page index variable are already in the pageOfOrders variable.

    this_step, step_words = genStepCheckCondition("pageOfOrders['n_new_orders'] > 0 and pageOfOrders['num_pages'] > 1", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("pageOfOrders['num_pages'] == pageOfOrders['page']+1", "", "", this_step)
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

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global endOfOrderList\nendOfOrderList = True", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # end of loop for while (endOfOrderList != True)
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now all order collection is complete.

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_collect_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads ebay in browser collect orders...." + psk_words)

    return this_step, psk_words

def genWinChromeEbayBrowserCollectOrderListSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_ebay_browser_collect_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEEBAY002",
                                          "Ebay Collect New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_ebay_orders/browser_collect_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_ebay_orders/browser_collect_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome ebay in browser collect orders...." + psk_words)

    return this_step, psk_words


def genWinChromeEbayBuyShippingSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_ebay_browser_buy_shipping", "win", "1.0", "AIPPS LLC",
                                          "PUBWINCHROMEEBAY013",
                                          "in Browser Ebay Buy Shipping On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_ebay_orders/browser_buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_ebay_orders/browser_buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads ebay buy shipping and update tracking...." + psk_words)

    return this_step, psk_words

def genWinADSEbayBuyShippingSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_buy_shipping", "win", "1.0", "AIPPS LLC",
                                          "PUBWINCHROMEEBAY012",
                                          "in Browser Ebay Buy Shipping and Update Tracking On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_ebay_orders/browser_buy_shipping", "", this_step)
    psk_words = psk_words + step_words


    # input ['sale', sender, ebay_orders, product_catelog]
    this_step, step_words = genStepCallExtern("global ship_op\nship_op = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global labels_dir\nlabels_dir = "+worksettings+"['log_path_prefix']+'ebay_labels'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("global orders\norders = fin[1]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global catelog\ncatelog = fin[2]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global n_orders\nn_orders = sum(len(page['ol']) for page in orders)\nprint('n_orders:', n_orders)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("n_orders > 0", "", "", this_step)
    psk_words = psk_words + step_words

    # now create all label in bulk here: https://www.ebay.com/gslblui/bulk?_trkparms=lblmgmt
    this_step, step_words = genStepCallExtern("global bulkurl\nbulkurl = 'https://www.ebay.com/gslblui/bulk?_trkparms=lblmgmt'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # hit ctrl-t to open a new tab.
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # type in bulk buy label URL address.
    this_step, step_words = genStepTextInput("var", False, "bulkurl", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "n_labels_checked", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 1, "raw", "scroll_resolution", 0, 0, 2, False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("bool", "allReviewed", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("n_labels_checked == n_orders)", "", "", "buyShipping"+str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ebay_bulk_labels", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "ground_advantage", "direct", "anchor text", "any", "ga_locs", "used_ground_advantage", "ebay", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not used_ground_advantage", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "standard_insurance", "anchor text", "", 0, "left", [1, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ebay_bulk_labels", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "ground_advantage", "anchor text", "", 0, "left", [1, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global n_labels_checked\nn_labels_checked = n_labels_checked + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("n_labels_checked < n_orders", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCalcObjectsDistance("standard_insurance", "anchor text", "materials", "anchor text", "min", "vertical", "row_height", "calc_flg", this_step)
    psk_words = psk_words + step_words

    # 0.73 is a magic number based on observation and measurement.
    this_step, step_words = genStepCallExtern("import math\nglobal row_height\nprint('row height:', row_height, scroll_resolution)\nrow_height = math.floor((row_height/0.73)/scroll_resolution)\n\nprint('row height:', row_height)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", "row_height", "raw", "scroll_resolution", 0, 0, 2, False, this_step)
    psk_words = psk_words + step_words
    # 0.73
    this_step, step_words = genScrollDownUntilLoc(["materials"], "anchor text", 80, "ebay_bulk_labels", "top", "scroll_adjustment",
                                               this_step, worksettings, "amz", theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    #no need dto scroll to the top,

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ebay_bulk_labels", "top", theme, this_step, None)
    psk_words = psk_words + step_words
    #
    # # use this info, as it contains the name and address, as well as the ship_to anchor location.
    # this_step, step_words = genStepSearchAnchorInfo("screen_info", ["review_purchase"], "direct", ["anchor text"], "any", "complete_buttons", "useless", "ebay", False, this_step)
    # psk_words = psk_words + step_words

    # click on Review purchase
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "review_purchase", "anchor icon", "", "nthCompletion", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ebay_bulk_labels", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # really should do checking here, such as payment method. but for now just assume default is what we want here....
    # and also the label print setting is set at 1 label per page.

    # use this info, as it contains the name and address, as well as the ship_to anchor location.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["confirm_and_pay"], "direct", ["anchor text"], "any", "complete_buttons", "useless", "ebay", False, this_step)
    psk_words = psk_words + step_words

    # make sure your funds is selected and make sure pdf is 1 label per page.(easier for post processing)

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "confirm_and_pay", "anchor icon", "", "nthCompletion", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    #now make sure labels are generated successfully by checking the word "successfully" and then click "download labels"
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ebay_bulk_labels", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "successfully", "direct", "anchor text", "any", "complete_buttons", "useless", "ebay", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "download_labels", "anchor icon", "", "nthCompletion", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    # now go the default download directory and fetch the most recent "ebay-bulk-labels-*.pdf"
    this_step, step_words = genStepMoveDownloadedFileToDestination("ebay-bulk-labels", "pdf", "labels_dir", "move_done", this_step)
    psk_words = psk_words + step_words

    # end of if len(orders) > 0
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_buy_shipping", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome in browser ebay buy shipping and update tracking...." + psk_words)

    return this_step, psk_words

# this skill assumes tracking code ready in the orders list data structure, and update tracking code to the orders on website.
# all the tracking code should already be updated into etsy_orders data structure which is the sole input parameter.....
def genWinADSEbayBrowserUpdateTrackingSkill(worksettings, stepN, theme):
    psk_words = "{"


    this_step, step_words = genStepHeader("win_ads_ebay_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY001",
                                          "in Browser Ebay Fullfill New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_ebay_orders/browser_update_tracking", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    # open the order page again.
    this_step, step_words = genStepCallExtern("global blurl\nblurl = 'https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepsWinChromeEbayUpdateShipmentTrackingSkill(worksettings, this_step, theme)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_update_tracking", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome in browser update tracking info on ebay...." + psk_words)

    return this_step, psk_words


def genWinChromeEbayBrowserUpdateTrackingSkill(worksettings, stepN, theme):
    psk_words = "{"


    this_step, step_words = genStepHeader("win_chrome_ebay_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEEBAY001",
                                          "in Browser Ebay Fullfill New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_ebay_orders/browser_update_tracking", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    # open the order page again.
    this_step, step_words = genStepCallExtern("global blurl\nblurl = 'https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT'", "", "in_line", "",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepsWinChromeEbayUpdateShipmentTrackingSkill(worksettings, this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_ebay_orders/browser_update_tracking", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome in browser update tracking info on ebay...." + psk_words)

    return this_step, psk_words


def genStepsWinChromeEbayUpdateShipmentTrackingSkill(worksettings, stepN, theme):
    psk_words = ""


    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, stepN)
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


    return this_step, psk_words



def genWinADSEbayBrowserRespondMessagesSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_handle_messages", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSEBAY002",
                                          "in Browser Ebay Buy Shipping and Update Tracking On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_ebay_orders/browser_handle_messages", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_handle_messages", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ads in browser ebay handle messages...." + psk_words)

    return this_step, psk_words


def genWinChromeEbayBrowserRespondMessagesSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_chrome_ebay_handle_messages", "win", "1.0", "AIPPS LLC",
                                          "PUBWINCHROMEEBAY002",
                                          "in Browser Ebay Buy Shipping and Update Tracking On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_ebay_orders/browser_handle_messages", "", this_step)
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

    this_step, step_words = genStepStub("end skill", "public/win_chrome_ebay_orders/browser_handle_messages", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows chrome in browser ebay handle messages...." + psk_words)

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

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "ebay_logo0", "direct", "anchor icon", "any", "useless", "site_loaded", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("site_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "ebay_logo0", "anchor icon", "", [0, 0], "center", [0, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words


    # open a new tab with hot-key ctrl-t
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # since the mouse cursor will be automatiall put at the right location, just start typing.... www.amazcon.com
    this_step, step_words = genStepTextInput("text", False, "https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT", "direct", 0.05, "enter", 1, this_step)
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

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "ebay_logo0", "direct", "anchor icon", "any", "useless", "site_loaded", "", False, this_step)
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
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ebay_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["sign_in"], "direct", ["anchor text"], "any", "useless", "not_logged_in", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not_logged_in", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "hello", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ebay_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "user_name", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "bemail", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "continue", "anchor text", "", "0", "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ebay_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "password", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "bpassword", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "sign_in_button", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ebay_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["sign_in"], "direct", ["info 1"], "any", "useless", "not_logged_in", "", False, this_step)
    psk_words = psk_words + step_words


    # end condition for "not_logged_in"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genStepEbayGenShippingInfoFromOrderID(order_id, orders, catelog, result, flag, stepN):
    stepjson = {
        "type": "Ebay Gen Shipping From Order ID",
        "action": "Ebay Gen Shipping",
        "order_id": order_id,
        "orders": orders,
        "catelog": catelog,
        "result": result,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genLabelName(oinfo, first_name, last_name):
    label_file_name = "ebay_" + first_name + "_" + last_name + "_"
    for pi, p in enumerate(oinfo):
        label_file_name = label_file_name + p["short name"] + "_"
        for vn in p["variations"]:
            vval = p["variations"][vn]["val"]
            cvval = vval[0].upper()+vval[1:]
            label_file_name = label_file_name +cvval
        label_file_name = label_file_name+"_"+str(p["quantity"])
        if pi != len(oinfo)-1:
            label_file_name = label_file_name + "_"
    label_file_name = label_file_name + ".pdf"
    return label_file_name

def genLabelNote(oinfo):
    note=""
    for pi, p in enumerate(oinfo):
        note = note + p["note name"] + " "
        for vn in p["variations"]:
            vval = p["variations"][vn]["val_note"]
            note = note +vval+" "
        note = note+" x "+str(p["quantity"])+p["unit note"]
        if pi != len(oinfo)-1:
            note = note + "\n"

    return note

def findMinContainerDimensions(total_volume):
    # Generate a list of potential dimensions
    max_dimension = math.ceil(total_volume ** (1/3) * 2)
    dimensions = range(1, max_dimension + 1)

    min_volume = float('inf')
    best_dimensions = None

    # Iterate through possible combinations of length, width, and height
    for length, width, height in itertools.product(dimensions, repeat=3):
        volume = length * width * height
        if volume >= total_volume and volume < min_volume:
            min_volume = volume
            best_dimensions = (length, width, height)

    return best_dimensions


def processEbayGenShippingInfoFromOrderID(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        ordered_prod_shipping_info = None
        order = next((ord for i, ord in enumerate(symTab[step["orders"]]) if ord.getOid() == symTab[step["order_id"]]), None)
        if order:
            ordered_products = order.getProducts()
            ordered_prod_shipping_info = []
            for op in ordered_products:
                found_in_book = False
                for p in symTab[step["catelog"]]:
                    for l in p['listings']:
                        if l["platform"] == "ebay":
                            if l["title"] == op.getPTitle():
                                #now found the product, its shipping info
                                for p_item in l["inventories"]:
                                    if p_item["variations"] == op.getVariations():
                                        shipping_info = copy.deepcopy(p_item)
                                        # grab note for variation for shipping label printing
                                        for vname in shipping_info["variations"]:
                                            vval = shipping_info["variations"][vname]
                                            shipping_info["variations"][vname] = {
                                                "note": l["variations"][vname]["note_text"],
                                                "val": vval,
                                                "val_note": l["variations"][vname]["vals"][vval]["note_text"]
                                            }
                                        found_in_book = True
                                        break
                if found_in_book:
                    ordered_prod_shipping_info.append(shipping_info)

            total_weight = sum(item['quantity'] * item['weight'] for item in ordered_prod_shipping_info)
            total_volume = sum(
                item['quantity'] * (item['size'][0] * item['size'][1] * item['size'][2]) for item in ordered_prod_shipping_info
            )

            min_container_size = findMinContainerDimensions(total_volume)

            order_shipping_info = order.getShipping()
            order_shipping_info.setWeight(total_weight)
            order_shipping_info.setDimension(min_container_size)

            first_name = order.getRecipientName().split()[0]
            nw = len(order.getRecipientName().split())
            last_name = order.getRecipientName().split()[nw-1]
            order_shipping_info.setLabelFileName(genLabelName(ordered_prod_shipping_info, first_name, last_name))
            order_shipping_info.setLabelNote(genLabelNote(ordered_prod_shipping_info))

        symTab[step["result"]] = ordered_prod_shipping_info

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZMatchProduct:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAMZMatchProduct traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat


def genWinADSEbayRespondMessagesSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_respond_messages", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY005",
                                          "Ebay Respond To Customer Messages On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/respond_messages", "", this_step)
    psk_words = psk_words + step_words


    # now create all label in bulk here: https://www.ebay.com/gslblui/bulk?_trkparms=lblmgmt
    this_step, step_words = genStepCallExtern("global msgurl\nmsgurl = 'https://mesg.ebay.com/mesgweb/ViewMessages/0'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # hit ctrl-t to open a new tab.
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # type in bulk buy label URL address.
    this_step, step_words = genStepTextInput("var", False, "bulkurl", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "hf_path", "NA", "sk_work_settings['log_path']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEbayScrapeMsgList("hf_path", "var", "hf_name", "currentPage", "pageOfMessages", "scrape_stat", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepThink("openai", "chatgpt4o", parameters, products, setup, query, response, result, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/respond_messages", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay handle return operation...." + psk_words)

    return this_step, psk_words

def genWinADSEbayBrowserHandleOffersSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_handle_offers", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY015",
                                          "In-Browser Ebay Respond To Customer Offers On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/browser_handle_offers", "", this_step)
    psk_words = psk_words + step_words


    # now create all label in bulk here: https://www.ebay.com/gslblui/bulk?_trkparms=lblmgmt
    this_step, step_words = genStepCallExtern("global msgurl\nmsgurl = 'https://mesg.ebay.com/mesgweb/ViewMessages/0'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # hit ctrl-t to open a new tab.
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # type in bulk buy label URL address.
    this_step, step_words = genStepTextInput("var", False, "bulkurl", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "hf_path", "NA", "sk_work_settings['log_path']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEbayScrapeMsgList("hf_path", "var", "hf_name", "currentPage", "pageOfMessages", "scrape_stat", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_handle_offers", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay handle respoding to offers using in-browser automation skills...." + psk_words)

    return this_step, psk_words

def genWinADSEbayBrowserHandleReturnSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_handle_return", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY005",
                                          "Ebay Respond To Customer Messages On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/browser_handle_return", "", this_step)
    psk_words = psk_words + step_words


    # now create all label in bulk here: https://www.ebay.com/gslblui/bulk?_trkparms=lblmgmt
    this_step, step_words = genStepCallExtern("global msgurl\nmsgurl = 'https://mesg.ebay.com/mesgweb/ViewMessages/0'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # hit ctrl-t to open a new tab.
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # type in bulk buy label URL address.
    this_step, step_words = genStepTextInput("var", False, "bulkurl", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "hf_path", "NA", "sk_work_settings['log_path']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEbayScrapeMsgList("hf_path", "var", "hf_name", "currentPage", "pageOfMessages", "scrape_stat", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_handle_return", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay handle return with ebay labels using in-browser automation skills...." + psk_words)

    return this_step, psk_words



def genWinADSEbayBrowserHandleReturnWithECBLabelsSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_handle_return_with_ecb_labels", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY005",
                                          "In-Browser Ebay handles return with ecb labels On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/browser_handle_return_with_ecb_labels", "", this_step)
    psk_words = psk_words + step_words


    # now create all label in bulk here: https://www.ebay.com/gslblui/bulk?_trkparms=lblmgmt
    this_step, step_words = genStepCallExtern("global msgurl\nmsgurl = 'https://mesg.ebay.com/mesgweb/ViewMessages/0'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # hit ctrl-t to open a new tab.
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # type in bulk buy label URL address.
    this_step, step_words = genStepTextInput("var", False, "bulkurl", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "hf_path", "NA", "sk_work_settings['log_path']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEbayScrapeMsgList("hf_path", "var", "hf_name", "currentPage", "pageOfMessages", "scrape_stat", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_handle_return_with_ecb_labels", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay handle return with ECB generated labels using in-browser automation skills...." + psk_words)

    return this_step, psk_words

def genWinADSEbayBrowserHandleReplacementSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_handle_replacement", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY005",
                                          "Ebay Respond To Customer Messages On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/browser_handle_replacement", "", this_step)
    psk_words = psk_words + step_words


    # now create all label in bulk here: https://www.ebay.com/gslblui/bulk?_trkparms=lblmgmt
    this_step, step_words = genStepCallExtern("global msgurl\nmsgurl = 'https://mesg.ebay.com/mesgweb/ViewMessages/0'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # hit ctrl-t to open a new tab.
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # type in bulk buy label URL address.
    this_step, step_words = genStepTextInput("var", False, "bulkurl", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "hf_path", "NA", "sk_work_settings['log_path']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEbayScrapeMsgList("hf_path", "var", "hf_name", "currentPage", "pageOfMessages", "scrape_stat", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_handle_replacement", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay handle sending replacement using in-browser automation skills...." + psk_words)

    return this_step, psk_words

def genWinADSEbayBrowserHandleRefundSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_ebay_browser_handle_refund", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY005",
                                          "Ebay Respond To Customer Messages On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/browser_handle_refund", "", this_step)
    psk_words = psk_words + step_words


    # now create all label in bulk here: https://www.ebay.com/gslblui/bulk?_trkparms=lblmgmt
    this_step, step_words = genStepCallExtern("global msgurl\nmsgurl = 'https://mesg.ebay.com/mesgweb/ViewMessages/0'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # hit ctrl-t to open a new tab.
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # type in bulk buy label URL address.
    this_step, step_words = genStepTextInput("var", False, "bulkurl", "direct", 1, "", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "hf_path", "NA", "sk_work_settings['log_path']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEbayScrapeMsgList("hf_path", "var", "hf_name", "currentPage", "pageOfMessages", "scrape_stat", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/browser_handle_refund", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay handle refund using in-browser automation skills...." + psk_words)

    return this_step, psk_words