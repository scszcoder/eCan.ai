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
from bot.scraperEbay import genStepEbayScrapeOrdersFromHtml, genStepEbayScrapeMsgList, genStepEbayScrapeOrdersFromJss, \
    genStepEbayScrapeCustomerMsgThread
from bot.seleniumSkill import *
from bot.ecSkill import genStepGenShippingOrdersFromMsgResponses
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


def genWinChromeAMZWalkSkill(worksettings, stepN, theme):
    psk_words = "{"
    site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_chrome_amz_browse_search", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEAMZBROWSE001",
                                          "Amazon Browsing On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_chrome_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZWalkSteps("sk_work_settings", this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genStubWinADSAMZWalkSkill(worksettings, stepN, theme):
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



def genWinADSAMZWalkSkill(worksettings, stepN, theme):
    log3("GENERATING WinADSAMZWalkSkill======>")
    psk_words = "{"
    site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_amz_browse_search", "win", "1.0", "AIPPS LLC",
                                          "PUBWINADSAMZBROWSE001",
                                          "AMZ Browse On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_amz_home/browse_search", "", this_step)
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

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None, "dyn_options")
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

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None, "dyn_options")
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


    this_step, step_words = genAMZLoginInSteps(this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not_logged_in == False", "", "", this_step)
    psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepWait(1, 0, 0, this_step)
    # psk_words = psk_words + step_words

    #now call the amz chrome browse sub-skill to go thru the walk process.
    this_step, step_words = genWinChromeAMZWalkSteps("sk_work_settings", this_step, theme)
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
    this_step, step_words = genADSPowerExitProfileSteps(worksettings, this_step, theme)
    psk_words = psk_words + step_words

    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words
