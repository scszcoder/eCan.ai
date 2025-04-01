import json
import random
from datetime import datetime

from bot.Logger import log3
from bot.basicSkill import DEFAULT_RUN_STATUS, symTab, STEP_GAP, genStepHeader, genStepStub, genStepCreateData, genStepUseSkill, genStepWait, \
    genStepCallExtern, genStepExtractInfo, genStepSearchWordLine, genStepSearchAnchorInfo, genStepCheckCondition, \
    genStepMouseScroll, genStepMouseClick, genStepKeyInput, genStepGoToWindow, genStepTextInput, genStepLoop, \
    genScrollDownUntil, genScrollUpUntil, genStepFillData, genStepOpenApp, genStepRecordTxtLineLocation, genStepReadFile, genStepWriteFile, \
    genStepAmzDetailsCheckPosition, genStepCalcObjectsDistance, genStepScrollToLocation, genStepAmzPLCalcNCols, \
    genScrollDownUntilLoc, genScrollUpUntilLoc
from bot.adsPowerSkill import genStepsADSPowerExitProfile
import re
from difflib import SequenceMatcher
import traceback
from bot.scraperAmz import genStepAmzScrapeBuyOrdersHtml, amz_buyer_scrape_product_list, amz_buyer_scrape_product_details, \
    amz_buyer_scrape_product_reviews
import time
import os
from fuzzywuzzy import fuzz

SAME_ROW_THRESHOLD = 16

def genStepCalibrateScroll(sink, amount, screen, marker, prev_loc, stepN):
    stepjson = {
        "type": "Calibrate Scroll",
        "action": "Extract",
        "data_sink": sink,
        "amount": amount,
        "screen": screen,
        "last_record": prev_loc,
        "marker": marker
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


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
    # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

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

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'anchors': [{'anchor_name': 'bot_user', 'anchor_type': 'text', 'template': bot_email, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'bot_open', 'anchor_type': 'text', 'template': 'Open', 'ref_method': '1', 'ref_location': [{'ref': 'bot_user', 'side': 'right', 'dir': '>', 'offset': '1', 'offset_unit': 'box'}]}], 'txt_attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}", "", "in_line", "", this_step)
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

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'anchors': [{'anchor_name': 'bot_user', 'anchor_type': 'text', 'template': bot_email, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'bot_open', 'anchor_type': 'text', 'template': 'Open', 'ref_method': '1', 'ref_location': [{'ref': 'bot_user', 'side': 'right', 'dir': '>', 'offset': '1', 'offset_unit': 'box'}]}], 'txt_attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}", "", "in_line", "", this_step)
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


    this_step, step_words = genStepsAMZLoginIn(this_step, theme)
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
    this_step, step_words = genStepsADSPowerExitProfile(worksettings, this_step, theme)
    psk_words = psk_words + step_words

    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genStepsAMZLoginIn(stepN, theme):
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

    # retry a few times
    this_step, step_words = genStepLoop("retry_count > 0 and not ip_obtained", "", "", "connProxy" + str(stepN),
                                        this_step)
    psk_words = psk_words + step_words

    # just keep on refreshing....
    this_step, step_words = genStepKeyInput("", True, "f5", "", 3, this_step)
    psk_words = psk_words + step_words

    # wait some random time for proxy to connect
    this_step, step_words = genStepWait(0, 5, 8, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme,
                                               this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "usa", "direct", "anchor text", "any", "useless",
                                                    "ip_obtained", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "amazon_site", "direct", "anchor text", "any",
                                                    "useless", "site_loaded", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
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
    this_step, step_words = genStepTextInput("text", False, "www.amazon.com", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    # end condition for "site_loaded"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
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

# pagesize - the entire pages size in the unit of # of scroll units.
# this info should be calculated and available from the previous flow.
# at the moment this info is not used, but can be used in future optimization
# start - starting location on this screen in %, if start from the top, this would be 0,
#         if start from half of the product list, it would be 50, meaning 50% of the total page contents.
# SC - at moment this will just be a dumb function， just scroll x numbers of screens down
def genAMZScrollProductListToBottom(stepN, worksettings, start):
    psk_words = ""
    log3("DEBUG", "gen_psk_for_scroll_to_bottom...")

    # create loop count var
    lcvarname = "scrollDownProductList"+str(stepN)
    this_step, step_words = genStepCreateData("int", lcvarname, "NA", 0, stepN)
    psk_words = psk_words + step_words


    # give it a random value between 15 and 25 - magic number .  that's how many scrolls will have
    rand_count = random.randrange(15, 20)
    this_step, step_words = genStepCreateData("int", "down_cnt", "NA", rand_count, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('SCROLL DOWN PRODUCT LIST.....', down_cnt)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepLoop("", str(rand_count), "", lcvarname, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    # psk_words = psk_words + step_words
    #
    # # wait - sort of equivalent to screen read time
    # this_step, step_words = genStepWait(0, 1, 3, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepStub("end loop", "", "", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE SCROLL DOWN PRODUCT LIST.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    log3("scroll reached BOTTOM of the page")

    return this_step, psk_words, "down_cnt"

# this info should be calculated and available from the previous flow.
# at the moment this info is not used, but can be used in future optimization
# start - starting location on this screen in %, if start from the bottom, this would be 0,
#         if start from half of the product list, it would be 50, meaning 50% of the total page contents.
# this function has no screen read involved.....
def genAMZScrollProductListToTop(down_cnt, stepN, worksettings):
    psk_words = ""
    log3("DEBUG", "gen_psk_for_scroll_to_top...")


    this_step, step_words = genStepCallExtern("global "+down_cnt+", up_cnt\nup_cnt = int("+down_cnt+"* 1.5)", "", "in_line", "", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('SCROLL UP PRODUCT LIST.....', up_cnt)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # up must be preceeded by a down scroll, so the cnt is fixed :
    # this_step, step_words = genStepLoop("up_cnt > 0", "", "", "scrollUpProductList"+str(stepN), this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepMouseScroll("Scroll up", "screen_info", 100, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    # psk_words = psk_words + step_words
    #
    # # wait - sort of equivalent to screen read time
    # this_step, step_words = genStepWait(0, 1, 3, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCallExtern("global up_cnt\nup_cnt = up_cnt-1\nprint('up_cnt:::::', up_cnt)", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepStub("end loop", "", "", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE SCROLL UP PRODUCT LIST.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    log3("scroll reached TOP of the page")

    return this_step,psk_words


def genAMZScrollProductDetailsToTop(pagesize, stepN, work_settings):
    psk_words = ""
    log3("DEBUG", "genAMZScrollProductDetailsToTop...")
    this_step, step_words = genStepCreateData("bool", "at_pd_top", "NA", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('SCROLL PRODUCT DETAILS TO TOP.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("at_pd_top != True", "", "", "scrollUpProductDetails"+str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "top", "", this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["add_to_cart"], "direct", ["anchor text"], "any", "useless", "at_pd_top", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE SCROLL PRODUCT DETAILS TO TOP.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    log3("scroll reached TOP of the product details page")

    return this_step,psk_words

# result contains the location of center of the title area so that we can click onto it to enter the detail
# page
def genStepAMZMatchProduct(screen, product_list, result, flag, stepN):
    stepjson = {
        "type": "AMZ Match Products",
        "action": "AMZ Match Products",
        "screen": screen,
        "product_list": product_list,
        "result": result,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# the process of browsing a product list page all the way to the bottom of the page, if found product to be browsed in details,
# click into it and browse in details.
# flow_cfg = [ products ]
# page_cfg is the variable name that's pointed to page config,
# pl is the result of html scraping which should already contain
# the attention field, which are the ones to click into details on this page.....
def genAMZBrowseProductListToBottom(page_cfg, pl, ith, stepN, worksettings, theme):
    psk_words = ""
    prod_cnt = 0
    log3("DEBUG", "genAMZBrowseProductListToBottom...")

    this_step, step_words = genStepCreateData("int", "this_attention_index", "NA", 0, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_adjustment", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "this_attention_count", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "next_attention_index", "NA", pl+"['attention_indices'][0]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "atBottom", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('BROWSING DOWN PRODUCT LIST.....', this_attention_index, next_attention_index)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words



    # estimate row height only on the first search result product list page.
    this_step, step_words = genStepCheckCondition(ith+"== 0", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genAMZBrowseProductListEstimateRowHeight(pl, "row_height", "unit_row_scroll", this_step, worksettings, theme)
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
    this_step, step_words = genStepLoop("atBottom != True", "", "", "browsePL2Bottom"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # <<<<<comment out for now to speed up test.
    this_step, step_words = genAMZBrowseProductListScrollNearNextAttention(pl, "this_attention_index", "next_attention_index", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    # in case we have passed the last attention, simply scroll to the bottom
    this_step, step_words = genStepCheckCondition("next_attention_index == len("+pl+"['products']['pl'])-1 and this_attention_count >= len("+pl+"['attention'])", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genScrollDownUntil(["next", "previous", "need_help", "end_of_page"], "anchor text", "product_list", "body", this_step, worksettings, "amz", theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words


    # scroll page until the next product's bottom is near bottom 10% of the page height.
    this_step, step_words = genAMZBrowseProductListScrollDownToNextAttention(pl, this_step, worksettings, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('pl_need_attention===>',pl_need_attention)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # create a loop to browse attention details...
    this_step, step_words = genStepCreateData("expr", "att_count", "NA", "len(pl_need_attention)", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global att_count, this_attention_count\nthis_attention_count = this_attention_count + att_count\nprint('this_attention_count:', this_attention_count, att_count)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("print('att_count===>',att_count)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # iterate thru all matched attentions on this page.
    this_step, step_words = genStepLoop("att_count > 0", "", "", "browseAttens"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN enter the product details page.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "pl_need_attention[att_count-1]['loc']", "expr", "", [0, 0], "center", [0, 0], "box", 1, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "pur", "NA", "pl_need_attention[att_count-1]['purchase']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "det_lvl", "NA", "pl_need_attention[att_count-1]['detailLvl']", this_step)
    psk_words = psk_words + step_words

    # "pl_need_attention", "att_count"
    # lvl = atpl + "[" + tbb_index +"]['detailLvl']"
    # purchase = atpl + "[" + tbb_index + "]['purchase']"
    # create a loop here to click into the interested product list. Note: loop is inside genAMZBrowseDetail
    this_step, step_words = genAMZBrowseDetails("det_lvl", "pur", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    # update li counter
    this_step, step_words = genStepCallExtern("global att_count\natt_count = att_count - 1\nprint('att_count:', att_count)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # check if this attention count is still in range.
    this_step, step_words = genStepCheckCondition("this_attention_count >= 1 and this_attention_count < len("+pl+"['attention'])", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global att_count, this_attention_index, next_attention_index, this_attention_count\nthis_attention_index = "+pl+"['attention_indices'][this_attention_count-1]\nnext_attention_index = "+pl+"['attention_indices'][this_attention_count]\nprint('this_attention_count:', this_attention_count, this_attention_index, next_attention_index)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("this_attention_count >= len("+pl+"['attention'])", "", "", this_step)
    psk_words = psk_words + step_words

    # we're beyond the attenlist list.

    # if somehow this attention count is bigger than number of attentions, simpley set the next attention index to the last products.
    this_step, step_words = genStepCallExtern("global this_attention_index, next_attention_index\nthis_attention_index = next_attention_index\nnext_attention_index = len("+pl+"['products']['pl'])-1\nprint('next_attention_index:', next_attention_index, this_attention_index)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # this is the case where this_attention_count == 0, in such a case, this attention index is the first attention index.
    this_step, step_words = genStepCallExtern("global att_count, this_attention_index, next_attention_index, this_attention_count\nnext_attention_index = "+pl+"['attention_indices'][this_attention_count]\nprint('this_attention_count:', this_attention_count, this_attention_index, next_attention_index)", "", "in_line", "", this_step)
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

    # this_step, step_words = genAMZBrowseProductListScrollDownMatchProductTest(pl, this_step, worksettings, theme)
    # psk_words = psk_words + step_words

    # need now click into the target product.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["previous", "next"], "direct", ["anchor text", "anchor text"], "and", "useless", "atBottom", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not atBottom", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["end_of_page"], "direct", ["anchor text"], "any", "useless", "atBottom", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE BROWSING DOWN PRODUCT LIST.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    return this_step,psk_words


# the process of browsing a product list page all the way to the bottom of the page, if found product to be browsed in details,
# click into it and browse in details.
def genAMZBrowseProductListToLastAttention(page_cfg, pl, ith, stepN, worksettings, theme):
    psk_words = ""
    prod_cnt = 0
    log3("DEBUG", "genAMZBrowseProductListToLastAttention...")

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

    # estimate row height only on the first search result product list page.
    this_step, step_words = genStepCheckCondition(ith + "== 0", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'txt_attention_area':[0, 0, 1, 1], 'attention_targets':['Result']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None, "dyn_options", "SunBrowser")
    psk_words = psk_words + step_words

    this_step, step_words = genAMZBrowseProductListEstimateRowHeight(pl, "row_height", "unit_row_scroll", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # star a loop to travel to the bottom of the page, along the way, collect product data and see whether we need
    # to go into product details.
    this_step, step_words = genStepLoop("reachedLastAttention != True", "", "", "browsePL2Bottom" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genAMZBrowseProductListScrollNearNextAttention(pl, "this_attention_index",
                                                                           "next_attention_index", this_step,
                                                                           worksettings, theme)
    psk_words = psk_words + step_words


    # scroll page until the next product's bottom is near bottom 10% of the page height.
    this_step, step_words = genAMZBrowseProductListScrollDownToNextAttention(pl, this_step, worksettings, theme)
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
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "pl_need_attention[att_count-1]['loc']", "expr", "", [0, 0], "bottom", [0, 0], "box", 1, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "pur", "NA", "pl_need_attention[att_count-1]['purchase']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "det_lvl", "NA", "pl_need_attention[att_count-1]['detailLvl']", this_step)
    psk_words = psk_words + step_words

    # "pl_need_attention", "att_count"
    # lvl = atpl + "[" + tbb_index +"]['detailLvl']"
    # purchase = atpl + "[" + tbb_index + "]['purchase']"
    # create a loop here to click into the interested product list. Note: loop is inside genAMZBrowseDetail
    this_step, step_words = genAMZBrowseDetails("det_lvl", "pur", this_step, worksettings, theme)
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

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["previous", "next"], "direct",
                                                    ["anchor text", "anchor text"], "and", "useless", "reachedLastAttention", "amz",
                                                    False, this_step)
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


# assume we're at the top of the product list page, move anchor "Results" to top of the page, then
# measure the vertical distance between the anchor "Results" to "free delivery"
# this would give a rough conservative estimate of row size without considering row gap.
# from here on, we will use the is row height combined with the to-be-paid-attention item's index in
# the product list. to scroll thru the product list. This should optimize the scroll speed of the
# page, hopefully reduce the page browse time by at least 1/2
# also in this function, we will calculation out column count in case of a grid based layout. since
# depends on screen size, the number of columns in a page could be different (for example, either 3 or 4 columns)
# this would affect how we calculate how much to scroll to the target row.
def genAMZBrowseProductListEstimateRowHeight(pl, rh_var, urs_var, stepN, worksettings, theme):
    psk_words = ""

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "results", "direct", "anchor text", "any", "results_anchors", "found_result", "amz", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'txt_attention_area':[0, 0, 1, 1], 'attention_targets':['Result']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not found_result", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 2, "raw", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # position "Results" to be about 20% of the screen size from the top of the screen.
    this_step, step_words = genStepScrollToLocation("screen_info", "results", "anchor text", 20, "position_reached", "scroll_resolution", 0.5, "amz", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('BROWSING PRODUCT LISTS ESTIMATE ROW HEIGHT.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "n_cols", "NA", "0", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None, "dyn_options", "SunBrowser")
    psk_words = psk_words + step_words

    # obtain all free delivery
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "results", "direct", "anchor text", "any", "results_anchors", "found_result", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "sponsored", "direct", "anchor text", "any", "sp_anchors", "found_sp", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "delivery", "direct", "anchor text", "any", "fd_anchors", "found_fd", "amz", False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCheckCondition("len(fd_anchors) > 0", "", "", this_step)
    psk_words = psk_words + step_words

    # in case "Results" and "FREE delivery" appear on the same screen, then use their distance as a rough row height
    this_step, step_words = genStepCalcObjectsDistance("results_anchors", "anchor text", "fd_anchors", "anchor text", "min", "vertical", rh_var, "calc_flg", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global row_height\nprint('row_height:', row_height)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # in case "Results" and "FREE delivery" NOT appear on the same screen,
    # then do this in 2 steps:
    # 1) calculate distance between result and sponsored, then scroll down 2 unit,
    # 2) calculate distance btween result and sponsored, then sum the two.
    this_step, step_words = genStepCalcObjectsDistance("results_anchors", "anchor text", "sp_anchors", "anchor text", "max", "vertical", rh_var, "calc_flg", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global row_height\nprint('row_height:', row_height)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 2, "raw", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "sponsored", "direct", "anchor text", "any", "sp_anchors", "found_sp", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "delivery", "direct", "anchor text", "any", "fd_anchors", "found_fd", "amz", False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCalcObjectsDistance("sp_anchors", "anchor text", "fd_anchors", "anchor text", "min", "vertical", "sp_fd_distance", "calc_flg", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global sp_fd_distance\nprint('sp_fd_distance:', sp_fd_distance)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global sp_fd_distance, "+rh_var+"\n"+rh_var+" = "+rh_var+" + sp_fd_distance", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global row_height\nprint('row_height:', row_height)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global "+urs_var+", scroll_resolution,"+rh_var+"\n"+urs_var+" = int("+rh_var+"/scroll_resolution)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global unit_row_scroll\nprint('unit_row_scroll:', unit_row_scroll)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # position "Results" to be about 20% of the screen size from the top of the screen.
    this_step, step_words = genStepScrollToLocation("screen_info", "sponsored", "anchor text", 20, "position_reached", "scroll_resolution", 0.5, "amz", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'txt_attention_area':[0, 0, 1, 1], 'attention_targets':['Add to cart', 'options', 'Sponsored']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "sponsored", "direct", "anchor text", "any", "sp_anchors", "found_sp", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "delivery", "direct", "anchor text", "any", "fd_anchors", "found_fd", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "options", "direct", "anchor text", "any", "options_anchors", "found_ops", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "add_to_cart", "direct", "anchor text", "any", "carts_anchors", "found_carts", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAmzPLCalcNCols("sp_anchors", "carts_anchors", "options_anchors", "fd_anchors", "n_cols", "col_calced", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global n_cols\nprint('n_cols:', n_cols)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE BROWSING PRODUCT LISTS ESTIMATE ROW HEIGHT.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    return this_step,psk_words


# use title, # reviews, price, nearest to the middle of the screen to search its index in the product list.
# then calculate the index difference between this one and the next attentioned item on the list.
# then scroll #of rows equivalent of scrolls, since the row height is converstivate, so we actually won't
# reach the target, but come near the target.
def genAMZBrowseProductListScrollNearNextAttention(pl, here, there, stepN, worksettings, theme):
    psk_words = ""

    this_step, step_words = genStepCheckCondition(pl+"['products']['layout'] == 'grid'", "", "", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('BROWSING PRODUCT LISTS NEAR NEXT ATTENTION.....', "+here+", "+there+")", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global row_gap, "+there+", "+here+", n_cols\nimport math\nrow_gap = math.floor(("+there+" - "+here+")/n_cols)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('BROWSING PRODUCT LISTS NEAR NEXT ATTENTION LIST.....', "+here+", "+there+")", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global row_gap, "+there+", "+here+"\nrow_gap = "+there+" - "+here+"", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end condition for atBottom == True
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global scroll_count\nimport math\nscroll_count = math.floor((row_gap*row_height)/(3*scroll_resolution))", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global scroll_count, row_gap\nprint('scroll_count:', scroll_count, 'row_gap:', row_gap)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("scroll_count != 0", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("scroll_count > 0", "", "", "scroll2Near"+str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 3, "raw", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global scroll_count\nscroll_count = scroll_count - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('END OF BROWSING PRODUCT LISTS NEAR NEXT ATTENTION.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    return this_step,psk_words


# once we get near the target, we scroll 75% of the screen at a time, until we reach the target.
def genAMZBrowseProductListScrollDownToNextAttention(pl, stepN, worksettings, theme):
    psk_words = ""

    this_step, step_words = genStepCreateData("boolean", "found_attention", "NA", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('BROWSING PRODUCT LISTS TO NEXT ATTENTION.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_adjustment", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZMatchProduct("screen_info", pl, "pl_need_attention", "found_attention", this_step)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("not found_attention", "", "", "scroll2Attens"+str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("scroll_adjustment > 0", "", "", this_step)
    psk_words = psk_words + step_words

    # first scroll back to the location before the scroll down until adjustment is actually scroll up.
    # this ensures that we always scroll down some and avoid the possible
    # back and forth scroll infinite loop action due to a songle FREE Delivery
    # on top of the screen and a small screen size.
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", "scroll_adjustment", "raw", "scroll_resolution", 0, 0, 2, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # scroll screen down for 65% of the screen height
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 65, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None)
    psk_words = psk_words + step_words

    # screen down until either keywords "free deliver" or "previous" reaches. 80% of the screen height from the top. or 20%from the bottom.
    this_step, step_words = genScrollDownUntilLoc(["delivery", "previous", "need_help"], "anchor text", 80, "product_list", "body", "scroll_adjustment",
                                               this_step, worksettings, "amz", theme)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None)
    psk_words = psk_words + step_words

    # check whether there is any match of this page's product, if matched, click into it.
    # pl_need_attention contains a list of products that needs attention on this screen.
    # pl contains a list of products on this page and all the attentions to be paid on this page.
    this_step, step_words = genStepAMZMatchProduct("screen_info", pl, "pl_need_attention", "found_attention", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("print('DONE BROWSING PRODUCT LISTS TO NEXT ATTENTION.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    return this_step,psk_words


# a simple combo action of scroll, peek, and match product.
def genAMZBrowseProductListScrollDownMatchProductTest(pl, stepN, worksettings, theme):
    psk_words = ""

    this_step, step_words = genStepCallExtern("print('MATCH PRODUCT STEPS.....')", "", "in_line", "", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 65, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZMatchProduct("screen_info", pl, "pl_need_attention", "found_attention", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DONE MATCH PRODUCT STEPS.....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    return this_step,psk_words

# cfg is the flow config, machted is a list of matched product.
# pl is the complete product list on this page, where we'll update detailed info.
# tbBrowsed are a list of products that are to be browsed into details page.
# this function will run a loop, within the loop:
#    each iteration starts by clicking into the product tbBrowsed,
#    each iteration ends by hitting browser back button to go back to the product list page.
# Note: within the loop, depends on the detail level in the product browse config,
#       we could go further into the browse reviews page....
# if detail level = 1, then click up to 3 rv_expanders.  pseudo code:
# if detail level == 1:
#       max_expandables = 3
# else:
#       max_expandables = 0
# expandables_count = 0
# while expandables_count < max_expandables:
#    if expandables found == True:
#        click on expandable
#        expandables_count = expandables_count + 1
#        extract info again after click
#        search for expandable again
#        if expandables dissappear:
#           scroll down 1/2 screen.
#   else:
#       if end_of_detail == True:
#           break
#       scroll down 1/2 screen.
def genAMZBrowseDetails(lvl, purchase, stepN, worksettings, theme):
    psk_words = ""
    log3("DEBUG", "genAMZBrowseDetails...")

    # now, starts to browse into the product details page.......................................
    this_step, step_words = genStepCreateData("bool", "end_of_detail", "NA", False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('START BROWSING DETAILS')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_adjustment", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    #now hover mouse over image icons to view images.
    # this_step, step_words = genAMZBrowseDetailsViewImages(worksettings, this_step, theme)
    # psk_words = psk_words + step_words

    #directly goes down to past the review section. this is quick
    this_step, step_words = genAMZBrowseDetailsScrollPassReviews(worksettings, this_step, theme)
    psk_words = psk_words + step_words

    #now scroll back up to the beginning of the review section.
    this_step, step_words = genScrollUpUntilLoc("from_us", "anchor text", 20, "product_details", "top", "scroll_adjustment", this_step, worksettings, "amz", theme)
    psk_words = psk_words + step_words

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

    this_step, step_words = genStepKeyInput("", True, "ctrl,s", "", 6, this_step)
    psk_words = psk_words + step_words

    # save the html file.
    this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_save_input", "fileStatus",
                                            this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "current_html_file", "NA", "sk_work_settings['log_path']+hf_name", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZScrapeProductDetailsHtml("current_html_file", purchase, "prod_details", this_step)
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

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "bottom", theme, this_step, None)
    psk_words = psk_words + step_words

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

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "top", theme, this_step, None)
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
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "bottom", theme, this_step, None)
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


    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "bottom", theme, this_step, None)
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
    this_step, step_words = genAMZBrowseAllReviewsPage("detail_level", this_step, worksettings, theme)
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
    this_step, step_words = genWinChromeAMZBuySteps("sk_work_settings", "buy_ops", "buy_result", "buy_step_flag",this_step, theme)
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


def genAMZBrowseDetailsViewImages(settings_var_name, stepN, theme):
    #simply move the mouse pointer around to simulate viewing images.
    psk_words = ""

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 2, "raw", "scroll_resolution", 0, 0, 2, False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", settings_var_name, "screen_info", "product_details", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "back_to_results", "direct", "anchor text", "any", "btr_avail", "back_loc", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "roll_over", "direct", "anchor text", "any", "ro_avail", "ro_loc", "amz", False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCheckCondition("ro_avail", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("No Click", "", False, "screen_info", "roll_over", "anchor text", "", [0, 0], "top", [0, -5], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("No Click", "", False, "screen_info", "roll_over", "anchor text", "", [0, 0], "bottom", [-2, 3], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("No Click", "", False, "screen_info", "roll_over", "anchor text", "", [0, 0], "bottom", [3, 3], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("No Click", "", False, "screen_info", "roll_over", "anchor text", "", [0, 0], "right", [10, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    return this_step, psk_words


def genAMZBrowseDetailsScrollDownSome(n_word, stepN):
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


def genAMZBrowseDetailsScrollPassReviews(settings_var_name, stepN, theme):
    psk_words = ""

    this_step, step_words = genStepCreateData("string", "scrn_position", "NA", "before", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("scrn_position != 'on' and scrn_position != 'after'", "", "", "", this_step)
    psk_words = psk_words + step_words

    # scroll 5 full screen worth of contents
    this_step, step_words = genAMZBrowseDetailsScrollDownSome("5", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_details", "bottom", theme, this_step, None)
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
def genAMZBrowseAllReviewsPage(level, stepN, settings_var_name, theme):
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
    this_step, step_words = genStepExtractInfo("", settings_var_name, "screen_info", "all_reviews", "top", theme, this_step, None)
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

    this_step, step_words = genStepExtractInfo("", settings_var_name, "screen_info", "all_reviews", "top", theme, this_step, None)
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
def genAMZBuySelectVariations(pd_var_name, stepN, theme):
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

    this_step, step_words = genScrollDownUntilLoc("var_txt", "text var", 30, "product_details", "top", "scroll_adjustment", this_step, settings_string, "amz", theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("var_display_type == 'dropdown'", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "var_txt", "var name", "", "1", "0", "bottom", "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    his_step, step_words = genStepLoop("(not var_target_found) and (scroll_cnt < 10)", "", "", "findVar" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", settings_var_name, "screen_info", "product_details", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "var_target_txt", "direct", "anchor text", "any", "useless", "var_target_found", "amz", False, this_step)
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

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "var_target_txt", "var name", "", "1", "0", "bottom", "box", 1, 1, [0, 0], this_step)
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

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'anchors': [{'anchor_name': 'this_var', 'anchor_type': 'text', 'template': var_target_txt, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'next_var', 'anchor_type': 'text', 'template': next_var_target_txt, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'swatch', 'anchor_type': 'polygon', 'template': '', 'ref_method': '1', 'ref_location': [{'ref': 'this_var', 'side': 'bottom', 'dir': '>', 'offset': '0', 'offset_unit': 'box'}]}, {'ref': 'this_var', 'side': 'right', 'dir': '>', 'offset': '-1', 'offset_unit': 'box'}]}, {'ref': 'next_var', 'side': 'top', 'dir': '<', 'offset': '0', 'offset_unit': 'box'}]}, {'ref': 'quantity', 'side': 'left', 'dir': '>', 'offset': '0', 'offset_unit': 'box'}]}], 'txt_attention_area':[0.35, 0, 0.85, 1], 'attention_targets':['@all']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # first figure out n row and n columns of all selection icons
    this_step, step_words = genStepExtractInfo("", settings_var_name, "screen_info", "product_details", "top", theme, this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    # then extrapolate the target‘s row number and column number， also calculate out the neighbors to hover over to check
    # in case something wrong, basically go 2 to left and 2 to the right，
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "swatch", "direct", "shape", "any", "swatch_icons", "swtches_found", "amz", False, this_step)
    psk_words = psk_words + step_words

    his_step, step_words = genStepLoop("(not var_target_found) and (scroll_cnt < 10)", "", "", "findVar" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # then hover over to the center of the icon，then extract and double check the selection text is there，
    # if not, hover neighbors to double check
    this_step, step_words = genStepMouseClick("No Click", "", True, "screen_info", "icon_loc", "var name", "", "1", "0", "bottom", "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", settings_var_name, "screen_info", "product_details", "top", theme, this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "var_target_text", "direct", "shape", "any", "swatch_icons", "var_target_found", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("var_target_found", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "var_target_txt", "var name", "", "1", "0", "bottom", "box", 1, 1, [0, 0], this_step)
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

def genStepAMZScrapePLHtml(html_file_var_name, pl, page_num, page_cfg, stepN):
    stepjson = {
        "type": "AMZ Scrape PL Html",
        "action": "Scrape PL",
        "html_var": html_file_var_name,
        "product_list": pl,
        "page_num": page_num,
        "page_cfg": page_cfg
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# browse a product list page.
# lastone is True/False, tells whether ith is the last one on the list, this determins whether browsing will
# scoll all the way to the bottom.....
def genAMZBrowseProductLists(pageCfgsName, ith, lastone, flows, stepN, worksettings, theme):
    page_cnt = 0
    psk_words = ""

    # before browsing, first obtain the html code of the page, at the moment, result is not being used...
    # html_file_name, template, root, sink, page, sect, stepN, page_data, option=""
    # ("", lieutenant.homepath, "screen_info", "amazon_home", "top", this_step, None)


    this_step, step_words = genStepCallExtern("from datetime import datetime\nglobal hf_name\nhf_name= 'pl'+ str(int(datetime.now().timestamp()))+'_'+str("+ith+")+'.html'\nprint('hf_name:',hf_name,datetime.now())", "", "in_line", "", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "file_save_input", "NA", "['save', sk_work_settings['log_path'], hf_name]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "ctrl,s", "", 6, this_step)
    psk_words = psk_words + step_words

    # save the html file.
    this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_save_input", "fileStatus", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepWait(18, 0, 0, this_step)
    # psk_words = psk_words + step_words

    # SC hacking for speed up the tests
    # homepath = os.environ.get("ECBOT_HOME")
    # if homepath[len(homepath)-1] == "/":
    #   homepath=homepath[:len(homepath)-1]
    # hfname = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats1689147960.html"
    # this_step = stepN
    this_step, step_words = genStepCreateData("expr", "current_html_file", "NA", "sk_work_settings['log_path']+hf_name", this_step)
    psk_words = psk_words + step_words
    # this_step, step_words = genStepCreateData("string", "scroll_resolution", "NA", 250, this_step)
    # psk_words = psk_words + step_words
    # this_step, step_words = genStepCreateData("data", "screen_info", "NA", [{"loc": [0, 0, 2030, 3330]}, {"loc": []}], this_step)
    # psk_words = psk_words + step_words

    # very important info saved in "plSearchResult" variable.
    # and extract all useful contents from the html file, the useful contents can also assist the
    # screen read.
    # (html_file_var_name, pl, page_num, page_cfg, stepN):
    # SC hacked for quick testing other procedures.

    log3("gen flow: "+json.dumps(flows))

    this_step, step_words = genStepCallExtern("global numFlows\nnumFlows = len("+flows+")", "", "in_line", "", this_step)
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
    this_step, step_words = genStepCallExtern("global nthFlow, numFlows\nprint('000: nthFlow, numFlows', nthFlow, numFlows)",  "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nthFlow < numFlows", "", "", "browseAmzPL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nthFlow, numFlows\nprint('nthFlow, numFlows', nthFlow, numFlows)",  "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition(flows+"[nthFlow] == 'down'", "", "", this_step)
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

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None, "scrn_options", "SunBrowser")
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZScrapePLHtml("current_html_file", "plSearchResult", ith, pageCfgsName, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words


    # if this is the last page of this search, then no need to scroll to the bottom, simply scroll to whatever
    # the last attention point. If there is no attention needed, simply scroll a few times and be done.
    this_step, step_words = genAMZBrowseProductListToLastAttention(pageCfgsName, "plSearchResult", ith, this_step, worksettings, theme)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "product_list", "body", theme, this_step, None, "scrn_options", "SunBrowser")
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZScrapePLHtml("current_html_file", "plSearchResult", ith, pageCfgsName, this_step)
    psk_words = psk_words + step_words


    # plSearchResult contains a list of products on this page as well as all the products we should pay attention to.
    # pageCfgName contains the page configuration
    this_step, step_words = genAMZBrowseProductListToBottom(pageCfgsName, "plSearchResult", ith, this_step, worksettings, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # simply scroll to the bottom, ....no browsing along the way
    this_step, step_words, down_count_var = genAMZScrollProductListToBottom(this_step, worksettings, 0)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "down_cnt", "NA", 20, this_step)
    psk_words = psk_words + step_words

    # back up is always a quick scroll, will never browse along the way.
    this_step, step_words = genAMZScrollProductListToTop("down_cnt", this_step, worksettings)
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


# create a process skill(.psk) file content for the client side execution.
#  at this point, several things should have been decided:
#  1) os-app-site
#     entrance path - search phrase, menu/category name
#  2) entrance method- search/category(side main menu)/top main menu/
#  3) how to go thru a list of search results:
#       flow - simple flow down, quick flow down then back up to targets,
#       # of pages to go thru (no more than 3)
#       # on each page, how many products and which products.(each page is different.)
#       # of products -
#                   order of browsing: 1st product (amazon choice, best seller, highest reviewer, highest price/review ratio, lowest price, randomly)
#           user on the client side may modify the random product code put in their own. the client side code will know from mission id that
#           what to do the replace random product code.
#       # level of details (glance only top and skip rest, glance thru, glance thru with glaces on 7 images and details)
#       # whether there is purchase action and what action(s)
#
#   type: task.name,
#   site: task.cuspas.split(",")[2],
#   os: task.cuspas.split(",")[0],
#   app: task.cuspas.split(",")[1],
#   runs: [                                        # a run is a search and browse session.
#                                                  # a search will result number of pages, then we'll select
#                                                  # number of pages to view(ususally top 3 pages)
#                                                  # then for each pages will, will determines how many times to
#                                                  # flow thru the page. (down then up , or down up down etc.)
#                                                  # during each flow, will determine how many products to
#                                                  # browse into details page and level of details.
#                                                  # another variable during the detail browsing is how many
#                                                  # reviews to browse, top N good reviews and top M bad reviews.
#                                                  #
#   entry_paths: {
#         type:  gen_entry_type(),                  # could be from "top main menu", "left main menu", or "search"
#         words: [],                                #why list of words here, because category->subcategory->subsubcategory...., need a list of words.
#   },
#   prodlist_pages: [],                                             # list of configurations for the # of product list pages to browse. min: 1, max: 3, only browse up to top 3 pages.
#   ]    -- end of array of run
# #     purchase: [] #[] contains sequential steps needed to get a purchase done, such as "cart", "order", "pay"
# };
# each elemet of prodlist_pages[] = [{
#     flow_type: "",
#     products: [{
#     selType: gen_prod_sel(),    # ["ac", "bs", "op", "mr", "mhr", "cp", "cus" ]; best seller/amazon choice/most rviews/most high ranks/cheapest price/customer defined.
#     detailLvl: gen_detail_lvl(), #1: pick top 5 reviews and expand them, 2: click into all reviews and examine top 5 bad reviews.
#     }]
#    }, ..... ] --> the array/list is list of flows for each page. on each flow there are #of products to pay attention to on that flow.
#                  it's up to the cloud side to arrange no products in the 1st flow down.
#   for the detailLvl, the data structure is as following:
#   { level: 1~5, seeAll : true/false, allPos: true/false, allNeg: true/false, nPosExpand: , nNegExpand:,  nPosPages: , nNegPages: }
# (step, i, mission, skill)
def genWinChromeAMZWalkSteps(worksettings, start_step, theme):
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
    # this_step, step_words = genStepOpenApp("cmd", True, "browser", site_url, "expr", "sk_work_settings['cargs']", "topWin", 5, "actionSuccess", start_step)
    # psk_words = psk_words + step_words

    # unit test browse details
    # unit test browse details

    # this url points to a product list page after a keyword search
    # url = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats1689147960.html"

    # this url points to a detail page.
    # url = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats168914805.html"

    # this url points to all review page.
    # url = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats168914806.html"



    this_step, step_words = genStepCallExtern("global scrn_options\nscrn_options = {'txt_attention_area':[0, 0, 1, 0.5],'attention_targets':['Search', 'EN']}\nprint('scrn_options', scrn_options)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # extract the amazon home page info.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, this_step, None, "scrn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global scroll_resolution\nscroll_resolution = sk_work_settings['scroll_resolution']\nprint('scroll_resolution from settings:', scroll_resolution)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # if screen resolution is default value, then needs calibration.
    this_step, step_words = genStepCheckCondition("int(scroll_resolution) == 250", "", "", this_step)
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
    # this_step, step_words = genStepCreateData("int", "scroll_resolution", "NA", 250, this_step)
    # psk_words = psk_words + step_words

    log3("DEBUG", "hello???")

    # go thru each entry path.this will be the only loop that we unroll, all other loops within the session will be generated
    # as part of the psk. do we have to unroll??????
    # run_config = worksettings["run_config"]
    this_step, step_words = genStepCreateData("expr", "run_config", "NA", "sk_work_settings['run_config']", this_step)
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
    # this_step, step_words = genStepTextInput("list", False, "run_config['searches'][nthSearch]['entry_paths']['words']", "expr", 0.05, "enter", 2, this_step)
    # psk_words = psk_words + step_words

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


    this_step, step_words = genStepCreateData("expr", "direct_buy", "NA", "search_buy[0]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genDirectBuySteps("sk_work_settings", "search_buy", this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "numPLPages", "NA", "len(run_config['searches'][nthSearch]['prodlist_pages'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthPLPage", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "row_height", "NA", 750, this_step)            # default in pixel
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "unit_row_scroll", "NA", 3, this_step)            # default in pixel
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


    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "next", "anchor text", "Next", [0, 0], "right", [0, 0], "box", 2, 5, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('DEBUG', 'page count', nthPLPage, ' out of total [', numPLPages, '] of pages....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # now 1 order update is finished. update the counter
    this_step, step_words = genStepCallExtern("global nthPLPage\nnthPLPage = nthPLPage + 1\nprint('nthPLPage:', nthPLPage)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now scroll back to top of the page so that the next search can be done.
    this_step, step_words = genStepScrollToProductListTop(this_step, theme)
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



def genStepScrollToProductListTop(stepN, theme):
    psk_words = ""

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "orders", "direct", "anchor text", "any", "useless", "on_amz_top", "", False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepLoop("not on_amz_top", "", "", "directbuy" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global dyn_options\ndyn_options = {'anchors': [{'anchor_name': 'bot_user', 'anchor_type': 'text', 'template': bot_email, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'bot_open', 'anchor_type': 'text', 'template': 'Open', 'ref_method': '1', 'ref_location': [{'ref': 'bot_user', 'side': 'right', 'dir': '>', 'offset': '1', 'offset_unit': 'box'}]}], 'txt_attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "amazon_home", "top", theme, this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "orders", "direct", "anchor text", "any", "useless", "on_amz_top", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genStepScrollDown(stepN, theme):
    psk_words = ""

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words


    return this_step, psk_words

def genWinADSAMZBuySkill(worksettings, start_step, theme):
    psk_words = "{"
    site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_amz_buy_product", "win", "1.0", "AIPPS LLC", "PUBWINADSAMZBUY001",
                                          "Amazon Buy with ADS.", start_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_amz_home/buy_product", "", this_step)
    psk_words = psk_words + step_words

    # 1）, do all the browsing as usual

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "open_profile_input", "NA", "[sk_work_settings['batch_profile']]",
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
    this_step, step_words = genStepCreateData("expr", "bot_email", "NA",
                                              "sk_work_settings['b_email'].split('@')[0]+'@'", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "bemail", "NA", "sk_work_settings['b_email']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "bpassword", "NA", "sk_work_settings['b_backup_email_pw']",
                                              this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchWordLine("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded",
                                                  "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not bot_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    # if not on screen, scroll down and check again.
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 80, "screen", "scroll_resolution", 0, 2,
                                               0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme,
                                               this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchWordLine("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded",
                                                  "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # if not found, call the batch load profile subskill to load the correct profile batch.
    this_step, step_words = genStepCheckCondition("not bot_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "profile_name", "NA",
                                              "os.path.basename(sk_work_settings['batch_profile'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "profile_name_path", "NA",
                                              "os.path.dirname(sk_work_settings['batch_profile'])", this_step)
    psk_words = psk_words + step_words

    # due to screen real-estate, some long email address might not be dispalyed in full, but usually
    # it can display up until @ char on screen, so only use this as the tag.
    this_step, step_words = genStepCreateData("expr", "bot_email", "NA",
                                              "sk_work_settings['b_email'].split('@')[0]+'@'", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "full_site", "NA",
                                              "sk_work_settings['full_site'].split('www.')[1]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "machine_os", "NA", "sk_work_settings['platform']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "batch_import_input", "NA",
                                              "['open', profile_name_path, profile_name, bot_email, full_site, machine_os]",
                                              this_step)
    psk_words = psk_words + step_words

    # once the correct user profile is loaded, the open button corresponding to the user profile will be clicked to open the profile.
    this_step, step_words = genStepUseSkill("batch_import", "public/win_ads_local_load", "batch_import_input",
                                            "browser_up", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # wait 9 seconds for the browser to be brought up.
    this_step, step_words = genStepWait(9, 1, 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepsAMZLoginIn(this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not_logged_in == False", "", "", this_step)
    psk_words = psk_words + step_words

    # now call the amz chrome browse sub-skill to go thru the walk process.
    this_step, step_words = genWinChromeAMZWalkSteps("sk_work_settings", this_step, theme)
    psk_words = psk_words + step_words

    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # close the browser and exit the skill
    this_step, step_words = genStepKeyInput("", True, "alt,f4", "", 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("mission_failed == False", "", "", this_step)
    psk_words = psk_words + step_words

    # in case mission executed successfully, save profile, kind of an overkill or save all profiles, but simple to do.
    this_step, step_words = genStepsADSPowerExitProfile(worksettings, this_step, theme)
    psk_words = psk_words + step_words

    # end condition for "not_logged_in == False"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_amz_home/buy_product", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # log3("DEBUG", "generated skill for windows ADS amazon buy operation...." + psk_words)

    return this_step, psk_words


# assume we're on amazon site. first - make sure we're on the top of the page, if not scroll to it.
def genDirectBuySteps(settings_var_name, buy_var_name, stepN, theme):
    psk_words = ""

    this_step, step_words = genStepScrollToProductListTop(stepN, theme)
    psk_words = psk_words + step_words

    # at this point, we should be on top of the amazon page, so that we can now click into returns&orders or Cart depends on the buy action
    this_step, step_words = genWinChromeAMZBuySteps(settings_var_name, buy_var_name, "buy_result", "buy_step_flag", this_step, theme)
    psk_words = psk_words + step_words

    return this_step, psk_words



# assumption for these steps, the browser should already be in the account's amazon home page (on top)
# or in case of a browse, the browse should already being done and we're at the top of the
# product details page. also buyop is not empty
def genWinChromeAMZBuySteps(settings_string, buyop_var_name, buy_result_name, buy_flag_name, stepN, theme):
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

    this_step, step_words = genWinChromeAMZBuyAddCartSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'pay'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyPaySteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'checkShipping'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyCheckShippingSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'rate'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyGiveRatingSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'feedback'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyGiveFeedbackSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("buy_cmd == 'checkFB'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZBuyCheckFeedbackSteps(settings_string, "buy_cmd", buy_result_name, buy_flag_name, this_step, theme)
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


def genWinChromeAMZBuyAddCartSteps(settings_string, buy_cmd_name, buy_result_name, buy_flag_name, stepN, theme):
    psk_words = ""

    # check whether this is
    this_step, step_words = genStepAMZPeekAndClick(settings_string, "one_time_purchase", "buy_box_available", "pac_result", stepN, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZPeekAndClick(settings_string, "buy_now", "buy_box_available", "pac_result", this_step, theme)
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



def genWinChromeAMZBuyPaySteps(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN, theme):
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


    this_step, step_words = genStepAMZPeekAndClick(settings_string, "proceed_to_checkout", "check_out_top", "cart_top", this_step, theme)
    psk_words = psk_words + step_words

    # when will we see this page?
    this_step, step_words = genStepAMZPeekAndClick(settings_string, "continue_to_checkout", "in_cart_transition", "pac_result", this_step, theme)
    psk_words = psk_words + step_words

    # there might be a page to to ask you to beceom prime member, need to click on "no thanks" if shows up....
    this_step, step_words = genStepAMZPeekAndClick(settings_string, "no_thanks", "sign_prime_page", "check_out_top", this_step, theme)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepAMZPeekAndClick(settings_string, "place_your_order", "pay_page", "check_out_top", this_step, theme)
    # psk_words = psk_words + step_words



    # this_step, step_words = genStepAMZPeekAndClick(settings_string, "place_your_order", "pay_page", "pac_result", this_step, theme)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepAMZPeekAndConfirm(settings_string, "order_placed", "pay_page", "pac_result", this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZPeekAndClick(settings_string, "review_recent_orders", "pay_page", "pac_result", this_step, theme)
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

def genWinChromeAMZBuyCheckShippingSteps(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN, theme):
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

def genWinChromeAMZBuyGiveRatingSteps(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN, theme):
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

    this_step, step_words = genScrollDownUntil("order_id", "text var", "my_orders", "top", this_step, settings_string, "amz", theme)
    psk_words = psk_words + step_words

    # click on the product which will lead into the product page. click on "write a product review"
    this_step, step_words = genStepAMZPeekAndClick(settings_string, "write_review", "pay_page", "pac_result", this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZPeekAndClick(settings_string, "all_star", "pay_page", "pac_result", this_step, theme)
    psk_words = psk_words + step_words

    return this_step, psk_words

def genWinChromeAMZBuyGiveFeedbackSteps(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN, theme):
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

    this_step, step_words = genStepAMZPeekAndClick(settings_string, "write_review", "pay_page", "pac_result", this_step, theme)
    psk_words = psk_words + step_words

    #product, instructions, review, result_var, stepN
    # this_step, step_words = genStepObtainReviews("product", "instructions", "review", "review_obtained", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "review", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words



    return this_step, psk_words

def genWinChromeAMZBuyCheckFeedbackSteps(settings_string,  buy_cmd_name, buy_result_name, buy_flag_name, stepN, theme):
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
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "my_orders", "anchor text", "Search Amazon", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], stepN)
    psk_words = psk_words + step_words

    # now we're in order page, search for the order placed,


    # click on the product which will lead into the product page. click on "# ratings"


    # click "top reviews" and switch to "most recent"


    # now save html file, and scrape html file to see whether the FB appears.


    return this_step, psk_words



def genStepAMZPeekAndClick(settings_string, target, flag, prev_result, start_step, theme):
    psk_words = ""

    # only do it if the previous result is good, otherwise, just fall out.
    this_step, step_words = genStepCheckCondition(prev_result, "", "", start_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", settings_string, "screen_info", "my_orders", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", target, "direct", "anchor text", "any", "useless", flag, "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition(flag, "", "", this_step)
    psk_words = psk_words + step_words

    # click on add_to_cart button.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", target, "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genStepAMZPeekAndConfirm(settings_string, target, flag, result, start_step, theme):
    psk_words = ""
    this_step, step_words = genStepExtractInfo("", settings_string, "screen_info", "ads_power", "top", theme, start_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", target, "direct", "anchor text", "any", "useless", flag, "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition(flag, "", "", this_step)
    psk_words = psk_words + step_words

    # set a flag
    this_step, step_words = genStepCreateData("string", flag, "NA", "on target", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # set a flag
    this_step, step_words = genStepCreateData("string", result, "NA", "no target", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words

# save orders page into html and scrape it.
def genStepAMZVerifyOrder(stepN, theme):
    psk_words = ""

    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))
    hfname = "verify_order"+dt_string

    this_step, step_words = genStepCreateData("expr", "hf_name", "NA", "'"+hfname+"'+'_'+'"+str(stepN)+"'+'.html'", stepN)
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

    # obtain the 1st order on the list, make sure product title match, then save order ID.


    return this_step, psk_words




# for the detail config:
# #   { level: 1~5, seeAll : true/false, allPos: true/false, allNeg: true/false, nExpand: ,nPosPages: , nNegPages: }
# seeAll: whether to click on seeAll
# allPos: whether to click on all positive review link.
# allNeg: whether to click on all negative review link
# nPosExpand: max number of times to expand to see a very long positive reviews
# nNegExpand: max number of times to expand to see a very long negative reviews
# nPosPages: number of positive review pages to browse thru.
# nPosPages: number of negative review pages to browse thru.
# pseudo code:
#    if seeAll:
#       click on seeAll which will take us to the all review page.
#       if allPos:
#           click on all positive reviews, this will take us to the all positive review page.
#           for i in range(nPosPages):
#               while not reached bottom:
#                   view all review, (tricky, could have long reviews which span multiple screen without images)
#                   scroll down
#                   check whether reached bottom
#           whether we have reached the last page
#               if so:
#                   go back. there are two strategy here, A: browse previous page. B: scroll to top and click on the product again.
#               else:
#                   click on "Next page"
#
#    else:
#        while not reached bottom:
#            extract screen info.
#            if there is expand mark,
#                if  nPosExand > 0:
#                   click on "read more",
#                   view expanded review, (tricky, could span multiple screen without images)
#                   scroll till the end of this review.
#                   nPosExand = nPosExand - 1
#            are we at the bottom of the page.
#
#  SC - 20230506 - this routine is kind of useless for now..............

def genStepAMZBrowseReviews(screen, detail_cfg, stepN, worksettings, page, sect, theme):
    psk_words = ""
    # grab location of the title of the "matchedProducts" and put it into variable "product_title"
    #(action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "See All Reviews", "anchor text", "See All Reviews", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    if detail_cfg.seeAll:
        #(action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
        this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "See All Reviews", "anchor text", "See All Reviews", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(3, 0, 0, this_step)
        psk_words = psk_words + step_words

        if detail_cfg.allPos:
            # (action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
            this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "All positive Reviews", "anchor text", "All positive Reviews", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
            psk_words = psk_words + step_words

            this_step, step_words = genStepWait(3, 0, 0, this_step)
            psk_words = psk_words + step_words

            # screen, np, nn, stepN, root, page, sect):
            this_step, step_words = genBrowseAllReviewsPage("screen_info", 1, 1, this_step, worksettings, "all reviews", "top")

        if detail_cfg.allNeg:
            # (action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
            this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "All negative Reviews", "anchor text", "All negative Reviews", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
            psk_words = psk_words + step_words

            this_step, step_words = genStepWait(3, 0, 0, this_step)
            psk_words = psk_words + step_words

            this_step, step_words = genBrowseAllReviewsPage("screen_info", 1, 1, this_step, worksettings, "all reviews", "top")

    else:
        # now simply scroll down
        this_step, step_words = genStepCreateData("bool", "endOfReviews", "NA", False, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepLoop("endOfReviews != True", "", "", "browseReviews"+str(stepN), this_step)
        psk_words = psk_words + step_words

        # (action, screen, amount, unit, stepN):
        this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", "50", "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
        psk_words = psk_words + step_words

        # check whether there is any match of this page's product, if matched, click into it.
        this_step, step_words = genStepSearchAnchorInfo("screen_info", detail_cfg.products, "direct", "text", "any", "matchedProducts", "expandable", False, this_step)
        psk_words = psk_words + step_words

        if detail_cfg.nExpand > 0:
            # (action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
            this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "read more", "anchor text", "read more", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
            psk_words = psk_words + step_words

            #now scroll until the end of this review.

            detail_cfg.nExpand = detail_cfg.nExpand-1

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

    # click into the product title.
    # (action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "1 star", "anchor text", "1 star", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    ## browse all the way down, until seeing "No customer reviews" or "See all reviews"
    this_step, step_words = genStepLoop("reviews_eop != True", "", "", "browseListOfDetails"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # (action, screen, amount, unit, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", "50", "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZSearchReviews("screen_info", "prod_details", "atbottom", this_step)
    psk_words = psk_words + step_words

    # here, if need to click open half hidden long reviews.....
    this_step, step_words = genStepSearchAnchorInfo("screen_info","See all details", "direct", "screen_info", "any", "eop_review", "reviews_eop", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genBrowseAllReviewsPage(screen, detail_cfg, stepN, worksettings, page, sect, theme):
    psk_words = ""
    this_step = stepN
    return this_step, psk_words

def genStepAMZScrapeProductDetailsHtml(html_file_var_name, purchase_var_name, sink, stepN):
    stepjson = {
        "type": "AMZ Scrape Product Details Html",
        "action": "Scrape Product Details",
        "html_var": html_file_var_name,
        "purchase_var": purchase_var_name,
        "result": sink
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepAMZScrapeReviewsHtml(html_file_name, html_file_var_name, sink, stepN):
    stepjson = {
        "type": "AMZ Scrape PL Html",
        "action": "Scrape PL",
        "local": html_file_name,
        "html_var": html_file_var_name,
        "result": sink
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))




#this is kind of a customized step just for e-commerce.
def genStepAMZSearchProducts(screen, sink, stepN):
    stepjson = {
        "type": "AMZ Search Products",
        "action": "AMZ Search Products",
        "screen": screen,
        "sink": sink
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

# this is kind of a customized step just for e-commerce. extract detailed review page for a product.
## but this can be done in a much easier way, simply click on bad reviews and fake it.
#
def genStepAMZBrowseDetails(screen, sink, flag, stepN):
    stepjson = {
        "type": "AMZ Browse Details",
        "action": "AMZ Browse Details",
        "screen": screen,
        "sink": sink,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson,indent=4) + ",\n"))

# this is kind of a customized step just for e-commerce. extract relavant information in the detail page.
# mainly check product's store, asin, size, weight, category ranking, Q&A, review information.
def genStepAMZSearchReviews(screen, sink, flag, stepN):
    stepjson = {
        "type": "AMZ Search Reviews",
        "action": "AMZ Search Reviews",
        "screen": screen,
        "sink": sink,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step "+ str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepAmzBuyCheckShipping(orderTBC, orderList, arrived_flag, status, stepN):
    stepjson = {
        "type": "AMZ Buy Check Shipping",
        "orderTBC": orderTBC,
        "orderList": orderList,
        "arrived_flag": arrived_flag,
        "status": status
    }

    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# process product detail pages on screen, basically this function searches.
# for reviews to click.
def processAMZBrowseDetails(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Searching...."+step["target"])

        scrn = symTab[step["screen"]]
        rvs = extractAMZProductsFromScreen(scrn)

        # search for details on this screen.

        # search result should be put into the result variable.
        symTab[step["sink"]] = None
    except:
        ex_stat = "ErrorAMZBrowseDetails:" + str(i)

    return (i + 1), ex_stat


def processAMZBrowseReviews(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Searching...."+step["target"])

        scrn = symTab[step["screen"]]

        found = []

        # search for reviews on this screen.

        # search result should be put into the result variable.
        symTab[step["sink"]] = found
    except:
        ex_stat = "ErrorAMZBrowseReviews:" + str(i)

    return (i + 1), ex_stat


# screen is a list of clickables, we'll need to search thru the clickables to find extracted product list.
# CLICKABLE("product_list", json.dumps(ps), loc[0], loc[1], loc[2], loc[3], "summery", [])
def extractAMZProductsFromScreen(screen):
    products = []
    pl = list(filter(lambda c: c["name"] == "product_list", screen))

    if len(pl) > 0:
        product_summery = [json.loads(ps["text"]) for ps in pl]
        products.append(product_summery)

    return products

# when majority of the words matched.
def title_matched(template_words, scrn_txt_words):
    s = set(scrn_txt_words)
    diff = [i for i in template_words if i not in s]

    # screen text detection should be accurate enough that, there is at most 1 mistake on words, perhaps due to special char or some
    if len(diff) > 2:
        return False
    else:
        return True


# p is screen product.
# tbM is a list of products to be matched against for what's captured on screen right now...
# before tbM, the list of all product on the page has already being extracted from html file and
# filtered with today's walk/buy execution plan to extract out a list of products that fit today's
# plan, now all we need to do is to match the title, price, and number of feedbacks.
# the essence is title match
def prod_matched(ps, tbM):
    matched = False
    ps_words = ps["title"].split()
    for tbM_prod in tbM:
        tbM_title_words = tbM_prod["title"].split()
        matched = title_matched(tbM_title_words, ps_words) and (ps["reviews"] == tbM_prod["reviews"]) and (ps["price"] == tbM_prod["price"])
        if matched:
            break
    return matched



# SC - the hard part is a long title, where on screen, you see only part of that long title with "..." representing
#      what's on screen is not a complete title, in such a case, need to find these ... and
#      2023-07-25 the big assumption is that the product tile is bounded into a paragraph.
#
def match_product(summery, screen_data):
    # the criterial is that > 80% of the words in title, should be matched.
    matched = False
    lines = []
    matched_lines = []
    pmatchs = []
    match_count = 0
    ps = [element for index, element in enumerate(screen_data) if element["name"] == "paragraph"]
    title = re.sub(" +", " ", summery["title"])
    title_word_count = len(title.split())
    # log3("initial title word count: "+str(title_word_count))
    eot = False

    # collect all lines.
    # for p in ps:
    #     lines.extend(p["txt_struct"])

    # sort lines by text length, match the longest ones's first.
    # len_sorted_lines = sorted(lines, key=lambda x: len(x["text"]), reverse=True)

    # for l in len_sorted_lines:
        # go thru each line seg

    for p in ps:
        log3("START PARAGRAPH=========================================================")
        # log3("paragraph text:::"+p["text"])
        # log3(">>>> end of paragraph text......")
        lines = p["txt_struct"]

        # sorted_lines = sorted(lines, key=lambda x: len(x["text"]), reverse=True)
        sorted_lines = lines
        tail = ""
        matched_lines = []
        match_count = 0

        # ttbm - title to be matched is a copy of title.
        ttbm = (title + '.')[:-1]
        # log3("TTBM BEFORE: "+ttbm)
        shortened = ttbm
        for l in sorted_lines:
            log3("LINE: "+l["text"])
            #if a line segment contains 5 or more words and are contained in the title.
            eot = False         # end of title flag
            seg = l["text"].strip()
            seg = re.sub(" +", " ", seg)
            if "..." in seg:
                seg = seg.replace("...", "")
                eot = True

            match = SequenceMatcher(None, seg, ttbm, ).find_longest_match(alo=0, ahi=len(seg), blo=0, bhi=len(ttbm))
            log3(seg, "("+json.dumps(seg[match[0]:match[0]+match[2]])+") and "+ttbm+" (("+json.dumps(ttbm[match[1]:match[1]+match[2]])+"))")
            matched_word = seg[match[0]:match[0]+match[2]]
            matched_word = re.sub(r'([()\[\].:!])', r'\\\1', matched_word)

            matched_words = seg[match[0]:match[0]+match[2]].split()
            log3("matched_word:"+json.dumps(matched_word)+"<=>"+ttbm)
            log3("matched_words:["+json.dumps(matched_words)+"]"+str(len(matched_words)))

            if len(matched_words) > 0:
                if not eot:
                    ttbm = re.sub(matched_word, '', ttbm)     # carve out the matched part.
                    ttbm = re.sub(" +", " ", ttbm)            # again remove redundant white spaces.

                    matched_lines.append(matched_word)
                    match_count = match_count + len(matched_words)
                    # log3("title matched: ", l["text"], "#: ", len(l["words"]))
                else:
                    last_matched_phrase = matched_words[len(matched_words) - 2] + " " + matched_words[len(matched_words) - 1]
                    # in case screen title is shorter than actual title, represented by ... in title.
                    # cut off the title part post ...
                    matched_lines.append(matched_word)
                    match_count = match_count + len(matched_words)

                    index = ttbm.find(last_matched_phrase)

                    if index != -1:  # Check if the pattern was found in the text
                        # Curtail the text string to remove characters after the pattern
                        shortened = ttbm[:index] + last_matched_phrase

                    break

        title_word_count = len(shortened.split())
        pmatchs.append({"p": p, "mls": matched_lines, "mwc": match_count, "twc": title_word_count})

    log3("ALL matches:: "+json.dumps(pmatchs))
    ptmatched = sorted(pmatchs, key=lambda x: x["mwc"], reverse=True)

    pt_best_matched = ptmatched[0]
    log3("BEST matched:: "+json.dumps(pt_best_matched))
    if pt_best_matched["mwc"] > pt_best_matched["twc"]-3:
        matched = True
    log3("matched flag:: " + str(matched))
    return matched, pt_best_matched["p"]

# match screen content against the scraped html result.
def processAMZMatchProduct(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        scrn = symTab[step["screen"]]

        tbMatched = symTab[step["product_list"]]["attention"]   # contains anchor/info name, or the text string to matched against.
        # tbMatched = symTab[step["product_list"]]["products"]["pl"]          # contains anchor/info name, or the text string to matched against.
        log3("find to be paid attention: "+json.dumps(tbMatched))

        # now extract all products from the screen capture: scrn
        matched = []
        matched_tbm = []
        if len(tbMatched) > 0:
            for tbm in tbMatched:
                print("matching title:", tbm["summery"]["title"])
                # title_matched, matched_paragraph = match_product(tbm["summery"], scrn)        #for testing
                title_matched, matched_paragraph, matched_location = match_product_title(tbm["summery"], scrn)
                if title_matched:
                    # first, figure out the longest text line in this paragraph,
                    # then use this longest line's bound box to calculate the location.
                    line_lens = [len(line["text"]) for line in matched_paragraph["txt_struct"]]
                    longest_li = line_lens.index(max(line_lens))

                    # swap x-y in prep for the mouse click function.....
                    tempy0 = matched_paragraph["txt_struct"][longest_li]["box"][1]
                    tempy1 = matched_paragraph["txt_struct"][longest_li]["box"][3]

                    matched_paragraph["txt_struct"][longest_li]["box"][1] = matched_paragraph["txt_struct"][longest_li]["box"][0]
                    matched_paragraph["txt_struct"][longest_li]["box"][3] = matched_paragraph["txt_struct"][longest_li]["box"][2]
                    matched_paragraph["txt_struct"][longest_li]["box"][0] = tempy0
                    matched_paragraph["txt_struct"][longest_li]["box"][2] = tempy1

                    matched.append({"txts": matched_paragraph["txt_struct"][longest_li], "loc": matched_location, "detailLvl": tbm["detailLvl"], "purchase": tbm["purchase"]})
                    # matched.append({"txts": matched_paragraph["txt_struct"][longest_li], "detailLvl": 1, "purchase":[]})        #for testing
                    matched_tbm.append(tbm)


        log3(">>>>>>>>matched_tbm: "+json.dumps(matched_tbm))
        log3("--------->matched locations: "+json.dumps(matched))
        #for the matched ones, remove from the attention list.
        for tbm in matched_tbm:
            symTab[step["product_list"]]["attention"].remove(tbm)
            # symTab[step["product_list"]]["products"]["pl"].remove(tbm)        #for testing

        # log3("<<<<>>>>>>>>>>>>remaining attention: "+json.dumps(symTab[step["product_list"]]["attention"]))
        # see whether current screen contains the product to be cliced into.
        symTab[step["result"]] = matched
        # search result should be put into the result variable.
        if len(matched) > 0:
            symTab[step["flag"]] = True
        else:
            symTab[step["flag"]] = False

        log3("RESULT of match product check: "+step["flag"]+" :: "+str(symTab[step["flag"]]))


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

def combine_lines(sentences):
    combined_text = ""
    for sentence in sentences:
        if '...' in sentence:
            combined_text += sentence["text"].split('...')[0]
            break
        combined_text += sentence["text"] + " "
    return combined_text.strip()

def match_title_against_paragraph(title, paragraph, tolerance=66):
    matched = False
    lines = paragraph["txt_struct"]

    combined_line = (paragraph["text"].replace("\n", " ")).split("...")[0]

    combined_line2 = combine_lines(lines)
    # print("combined_lines:", combined_line)
    print("combined_lines2:", combined_line)
    # Tokenize both title and combined text
    title_tokens = title.split()
    combined_tokens = combined_line2.split()
    # print("=========# combined_tokens:", len(combined_tokens), "# title_tokens:", len(title_tokens), "====================")

    # Use a sliding window approach to check for fuzzy matches
    if len(combined_tokens) > len(title_tokens) - 1:
        best_ratio = -1
        for i in range(len(combined_tokens) - len(title_tokens) + 1):
            window = combined_tokens[i:i + len(title_tokens)]
            window_text = " ".join(window)

            # Fuzzy match window with title
            ratio = fuzz.partial_ratio(title, window_text)
            if ratio > best_ratio:
                best_win = window
                best_win_text = window_text
                best_ratio = ratio

            # print("fuzz ratio:", ratio, tolerance, window_text)
            if ratio >= tolerance:
                print("successfully matched fuzz ratio:", ratio, tolerance, window_text)
                matched = True
                break

        # Allow for partial matches with up to 3 incorrect words
        if not matched:
            print("best matched fuzz ratio:", best_ratio, tolerance, best_win_text)
            print("lines:", combined_line2)
            max_incorrect_words = 3
            incorrect_words = sum(1 for t, w in zip(title_tokens, best_win) if fuzz.ratio(t, w) < 80)  # Adjust threshold as needed
            print("incorrect_words:", incorrect_words)

            if incorrect_words <= max_incorrect_words  and len(combined_tokens) > len(title_tokens)/2:
                print("successfully matched by words count:", ratio, incorrect_words, window_text)
                matched = True
    else:
        window_text = " ".join(combined_tokens)
        ratio = fuzz.partial_ratio(title, window_text)
        if ratio >= tolerance and len(combined_tokens) > len(title_tokens)/5:
            print("successfully partial matched fuzz ratio:", ratio, tolerance, len(combined_tokens), (title_tokens), window_text, "||||", title)
            matched = True
        else:
            # Allow for partial matches with up to 3 incorrect words
            max_incorrect_words = 3
            incorrect_words = sum(1 for t, w in zip(title_tokens[:len(combined_tokens)], combined_tokens) if fuzz.ratio(t, w) < 80)
            if ratio > 40 and len(combined_tokens) > len(title_tokens)/5:
                print("not matched partial fuzz ratio:", ratio, tolerance, incorrect_words, window_text)
                print("lines:", combined_line2)
    return matched


def match_title_against_paragraph2(title, paragraph, tolerance=66):
    matched = False, "", [0, 0, 0, 0]
    matched_flag = False
    matched_loc = [0, 0, 0, 0]          # left, top, right, bottom
    lines = paragraph["txt_struct"]
    combined_words = []
    for line in lines:
        combined_words = combined_words + line["words"]
    combined_line = (paragraph["text"].replace("\n", " "))

    combined_line2 = combine_lines(lines)
    # print("combined_lines:", combined_line)
    print("combined_lines2:", combined_line)
    # Tokenize both title and combined text

    # Check if the paragraph contains '...'
    ellipsis_match = re.search(r'\.\.\.', combined_line2)
    if ellipsis_match:
        ellipsis_index = ellipsis_match.start()
        pre_ellipsis_tokens = combined_line2[:ellipsis_index].strip().split()[-3:]  # Get the last 3 tokens/words before '...'
        pre_ellipsis_text = " ".join(pre_ellipsis_tokens)

        # Find the match of the curtailed portion in the title
        title_tokens = title.split()
        max_ratio = 0
        match_index = -1

        if len(title_tokens) > len(pre_ellipsis_tokens):      # this will almost surely be true as title should be longer than 3 words.
            for i in range(len(title_tokens) - len(pre_ellipsis_tokens), -1, -1):  # Start from the end
                window = title_tokens[i:i + len(pre_ellipsis_tokens)]
                window_text = ' '.join(window)
                ratio = fuzz.ratio(pre_ellipsis_text, window_text)
                if ratio > max_ratio:
                    max_ratio = ratio
                    match_index = i

        # If a match is found within the tolerance
        # If a match is found within the tolerance
        if max_ratio >= tolerance and match_index != -1:
            # Curtail the title up to the matched location
            curtailed_title = ' '.join(title_tokens[:match_index + len(pre_ellipsis_text.split())])
            paragraph_up_to_ellipsis = combined_line2[:ellipsis_index].strip()  # Up to '...'
            start_word_index = len(paragraph_up_to_ellipsis.split()) - len(curtailed_title.split())
            matched_flag = fuzz.partial_ratio(paragraph_up_to_ellipsis, curtailed_title) >= tolerance
            if matched_flag:
                matched_words = combined_words[start_word_index:len(paragraph_up_to_ellipsis.split())]
                left_most = 100000
                right_most = 0
                top_most = 1000000
                bottom_most = 0
                for w in matched_words:
                    if len(w["text"]) < 32:            # wierd long string won't count, like an web address somehow....
                        if w["box"][0] < left_most:
                            left_most = w["box"][0]
                        if w["box"][2] > left_most:
                            right_most = w["box"][2]
                        if w["box"][1] < top_most:
                            top_most = w["box"][1]
                        if w["box"][3] > bottom_most:
                            bottom_most = w["box"][3]

                vmiddle = int((bottom_most + top_most)/2)

                # now find a line that's nearest to the middle of the title boundbox
                #sort all lines based on their vertical distance to center of the matched boundbox
                vsorted = sorted(lines, key=lambda l: abs(l["box"][1] - vmiddle), reverse=False)
                l_center = vsorted[0]
                matched_loc = [l_center["box"][1], l_center["box"][0], l_center["box"][3], l_center["box"][2]]   # format according mouse click order. not consistent

            matched = matched_flag, curtailed_title, matched_loc
    else:
        # If no '...', perform standard fuzzy matching
        max_ratio = 0
        best_match = ''

        paragraph_tokens = combined_line2.split()
        title_tokens = title.split()

        if len(paragraph_tokens) > 3 and len(paragraph_tokens) >= len(title_tokens):
            for i in range(len(paragraph_tokens) - len(title_tokens) + 1):
                window = paragraph_tokens[i:i + len(title_tokens)]
                window_text = ' '.join(window)

                # Fuzzy match window with title
                ratio = fuzz.ratio(title, window_text)
                if ratio > max_ratio:
                    max_ratio = ratio
                    best_match = window_text
                    best_index = i

            if max_ratio >= tolerance:
                # found a match and calculate boundbox of the matched lines.

                matched_words = combined_words[best_index: best_index + len(title_tokens)]
                print("best match:", max_ratio, i, len(title_tokens), window_text, matched_words)
                left_most = 100000
                right_most = 0
                top_most = 1000000
                bottom_most = 0
                for w in matched_words:
                    if len(w["text"]) < 32:             # wierd long string won't count, like an web address somehow....
                        if w["box"][0] < left_most:
                            left_most = w["box"][0]
                        if w["box"][2] > left_most:
                            right_most = w["box"][2]
                        if w["box"][1] < top_most:
                            top_most = w["box"][1]
                        if w["box"][3] > bottom_most:
                            bottom_most = w["box"][3]

                vmiddle = int((bottom_most + top_most)/2)

                # now find a line that's nearest to the middle of the title boundbox
                #sort all lines based on their vertical distance to center of the matched boundbox
                vsorted = sorted(lines, key=lambda l: abs(l["box"][1] - vmiddle), reverse=False)
                l_center = vsorted[0]
                matched_loc = [l_center["box"][1], l_center["box"][0], l_center["box"][3], l_center["box"][2]]   # format according mouse click order. not consistent


            matched = max_ratio >= tolerance, best_match, matched_loc

    return matched


def match_product_title(summery, screen_data):
    # the criterial is that > 80% of the words in title, should be matched.
    matched = False
    ps = [element for index, element in enumerate(screen_data) if element["name"] == "paragraph"]
    title = re.sub(" +", " ", summery["title"])
    matched_p = None
    matched_loc = [0, 0, 0, 0]

    for p in ps:
        # log3("START MATCHING TITLE AGAINST PARAGRAPH========>"+p["text"]+"::"+title)
        matched, matched_text, matched_loc = match_title_against_paragraph2(title, p)
        if matched:
            print("found a match for:", title, ">>against:", matched_text, ">> at location:", matched_loc)
            matched_p = p
            break

    if not matched:
        print("failed to match anything for this title:", title)

    log3("matched flag:: " + str(matched))
    return matched, matched_p, matched_loc


def processExtractPurchaseOrder(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Searching....", step["target"])

        scrn = symTab[step["screen"]]
        template = step["template"]  # contains anchor/info name, or the text string to matched against.

        if step["target"] == "Anchor":
            log3("")
        elif step["target"] == "Info":
            log3("")
        elif step["target"] == "Text":
            template = step["template"]
            log3("")

        # search result should be put into the result variable.
        symTab[step["result"]] = None

    except:
        ex_stat = "ErrorExtractPurchaseOrder:" + str(i)

    return (i + 1), ex_stat



# check whether a paragraph contains the keyword
# doesn't cover the special case of keyword sitting on two lines.
def textContains(p, txt):
    found = False
    found = txt in p["text"]
    return found

# check whether two product related text are on a same row.
# input: boundbox of the row of text (left, top, right, bottom)
def amzProductsOnSameRow(p1_txt_box, p2_txt_box):
    same_row = abs(p1_txt_box[1] - p2_txt_box[1]) < (p1_txt_box[3] - p1_txt_box[1])*SAME_ROW_THRESHOLD
    return same_row

# this one calculate the layout of the search result product list page, the result will be 2 variables:
# one in step["pl_page_layout" and step["pl_product_screen_size"]
# The algorithm analyze keyword "Free Shipping" to the next "Free Shipping" Assumption is there are
# at lease 2 free shipping on the page, and
def processAMZCalcProductLayout(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        vdistance = 0                         #unit in pixel.
        scrn = symTab[step["screen"]]

        # first get all info paragraphs out
        ps = [element for index, element in enumerate(scrn["data"]) if element["name"] == "paragraph" and element["type"] == "info"]

        #then search for the one contains the Free Shipping
        found = [element for index, element in enumerate(ps) if textContains(element["name"], "FREE delivery")]
        foundBoxes = []

        if len(found) > 2:
            for p in found:
                for l in p["txt_struct"]:
                    if textContains(l["text"], "FREE delivery"):
                        foundBoxes.append(l["box"])
                        break

            # that check the location of the boxes.
            # if the last two occurances have the on-par vertical location and distinct horiznotal location, that means it's a grid type of layout.
            #
            if amzProductsOnSameRow(foundBoxes[len(foundBoxes)-1], foundBoxes[len(foundBoxes)-2]) or amzProductsOnSameRow(foundBoxes[len(foundBoxes) - 2], foundBoxes[len(foundBoxes) - 3]):
                symTab[step["pl_page_layout"]] = "grid"
            else:
                symTab[step["pl_page_layout"]] = "list"
        elif len(found) == 2:
            # if grid layout, we should never catch only 2 "free delivery" key phrases.
            symTab[step["pl_page_layout"]] = "list"
        else:
            # this is inconclusive, should re-scroll and check.....
            log3("WARNING: inconclusive on the layout")


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZCalcProductLayout:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAMZCalcProductLayout traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat




# from a product list, check whether any product matches the search criteria p
#     products: [{
#     selType: gen_prod_sel(),    # ["ac", "op", "bs", "mr", "mhr", "cp", "cus" ]; best seller/amazon choice/most rviews/most high ranks/cheapest price/customer defined.
#     detailLvl: gen_detail_lvl(), #1: pick top 5 reviews and expand them, 2: click into all reviews and examine top 5 bad reviews.
#     }]

# pick a product from pl.
def found_match(p, pl):
    matches = []
    if pl:
        if p["selType"] == "ac":
            # amazon's choice.
            matches = [pr for index, pr in enumerate(pl) if pr["summery"]["ac"]]
        elif p["selType"] == "op":
            # amazon's best overall pick.
            matches = [pr for index, pr in enumerate(pl) if pr["summery"]["op"]]
        elif p["selType"] == "bs":
            # amazon's best seller.
            matches = [pr for index, pr in enumerate(pl) if pr["summery"]["bs"]]
        elif p["selType"] == "mr":
            # most reviews
            rvsorted = sorted(pl, key=lambda x: x["summery"]["feedbacks"], reverse=True)
            matches = [rvsorted[0]]
            log3("MOST REVIEWS:", matches)
        elif p["selType"] == "mhr":
            # highest star ranking....
            rvsorted = sorted(pl, key=lambda x: x["summery"]["score"], reverse=True)
            matches = [rvsorted[0]]
            log3("HIGHEST RATED:", matches)
        elif p["selType"] == "ms":
            # most past week sales
            rvsorted = sorted(pl, key=lambda x: x["summery"]["weekly_sales"], reverse=True)
            matches = [rvsorted[0]]
            log3("MOST WEEK SALES:"+json.dumps(matches))
        elif p["selType"] == "cp":
            # cheapest price
            rvsorted = sorted(pl, key=lambda x: x["summery"]["price"], reverse=False)
            matches = [rvsorted[0]]
            log3("CHEAPEST PRICE:"+json.dumps(matches))
        elif p["selType"] == "cus":
            matches = [pr for index, pr in enumerate(pl) if p["purchase"][0]["title"] == pr["summery"]["title"]]
        else:
            #randomly pick one.
            k = random.randint(0, len(pl)-1)
            matches = [pl[k]]

    found_index = -1
    if len(matches) > 0:
        found_index = pl.index(matches[0])
        for m in matches:
            m["detailLvl"] = p["detailLvl"]
            m["purchase"] = p["purchase"]


        found = matches[0]
    else:
        found = None

    return found, found_index


# "hfname": html_file_name,
# "result": sink
# this function scrape amz product search result product list page html file, and
# put results in product list data structure, then it compares the product list with
# this mission's config file to extract the "attention" product list that the user
# will "pay attention to" (i.e. click into it to browse more details).
# Note: this is the place, to swap the custom product to the actual to be swiped product.
def processAMZScrapePLHtml(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Extract Product List from HTML: ", step)

        hfile = symTab[step["html_var"]]
        log3("hfile: ", hfile)

        download_time_out = 48
        log3(">>>>>>>>>>>>>>>>>>>>>file scrape stamp0: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

        wait_count = 0
        while not os.path.exists(hfile) and wait_count < download_time_out:
            wait_count = wait_count + 1
            time.sleep(1)

        log3(">>>>>>>>>>>>>>>>>>>>>file scrape stamp1: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

        if wait_count < download_time_out:
            pl = amz_buyer_scrape_product_list(hfile, symTab[step["page_num"]])

            att_pl = []
            att_pl_indices = []

            # go thru all products in configuration
            for p in symTab[step["page_cfg"]]["products"]:
                log3("current page config: "+json.dumps(p))
                found, fi = found_match(p, pl["pl"])
                if found:
                    # remove found from the pl
                    log3("FOUND product:"+json.dumps(found))
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
                        log3("Buy Swapped:" + json.dumps(found))

                    att_pl.append(found)
                    att_pl_indices.append(fi)

            if not step["product_list"] in symTab:
                # if new, simply assign the result.
                symTab[step["product_list"]] = {"products": pl, "attention": att_pl, "attention_indices": att_pl_indices}
            else:
                # otherwise, extend the list with the new results.
                # symTab[step["product_list"]].append({"products": pl, "attention": att_pl})
                symTab[step["product_list"]]["products"] = pl
                symTab[step["product_list"]]["attention"] = att_pl
                symTab[step["product_list"]]["attention_indices"] = att_pl_indices


            log3("var step['product_list']: "+json.dumps(symTab[step["product_list"]]))

        else:
            raise Exception('Error - to be scraped html file not found!')

        log3(">>>>>>>>>>>>>>>>>>>>>file scrape stamp2: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZScrapePLHtml:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAMZScrapePLHtml traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat

def processAMZScrapeProductDetailsHtml(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Extract Product Details from HTML")

        hfile = symTab[step["html_var"]]
        log3("hfile: "+hfile)


        wait_count = 0
        while not os.path.exists(hfile) and wait_count < 90:
            wait_count = wait_count + 1
            time.sleep(1)

        if wait_count < 90:
            details = amz_buyer_scrape_product_details(hfile)
            details["variations"]["variationTargets"] = {}
            details["variations"]["variationTargetsIndex"] = {}
            for var_name in details["variations"]["variationValues"]:
                details["variations"]["variationTargets"][var_name] = ""
                details["variations"]["variationTargetsIndex"][var_name] = -1

            if len(step["purchase_var"]) > 0:
                purchase = symTab[step["purchase_var"]]
                var_string = purchase[0]["variations"]

                if var_string != "":
                    vars_parts = var_string.splilt(",")
                    vars = [x.strip() for x in vars_parts]
                    for v in vars:
                        found = False
                        for var_name in details["variations"]["variationValues"]:
                            if v in details["variations"]["variationValues"][var_name]:
                                details["variations"]["variationTargets"][var_name] = v
                                details["variations"]["variationTargetsIndex"][var_name] = details["variations"]["variationValues"][var_name].index(v)
                                found = True
                                break

                        if not found:
                            print("ERROR: to be purchased product variation value "+v+" NOT found")

            symTab[step["result"]] = details
        else:
            symTab[step["result"]] = None

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZScrapeDetailsHtml:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAMZScrapeDetailsHtml traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat

def processAMZScrapeReviewsHtml(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Extract Product Reviews from HTML")

        hfile = symTab[step["html_var"]]
        log3("hfile: "+hfile)

        if step["result"] in symTab:
            # if new, simply assign the result.
            symTab[step["result"]] = amz_buyer_scrape_product_reviews(hfile)
        else:
            # otherwise, extend the list with the new results.
            symTab[step["result"]] = symTab[step["result"]] + amz_buyer_scrape_product_reviews(hfile)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZScrapeReviewsHtml:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorAMZScrapeReviewsHtml traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat


def processAmzBuyCheckShipping(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("given order ID，check order arrival status")

        orderTBC = symTab[step["orderTBC"]]
        orderList = symTab[step["orderList"]]
        found = False
        for order in orderList:
            if order["order_id"] == orderTBC:
                found = True
                found_order = order
                break

        if found:
            symTab[step["status"]] = found_order["delivery_status"]
            if "Arrived" in found_order["delivery_status"]:
                symTab[step["arrived_flag"]] = True
            else:
                symTab[step["arrived_flag"]] = False

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAmzBuyCheckShipping:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorAmzBuyCheckShipping traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat