import os

import pandas as pd
import copy

from basicSkill import *

ADS_BATCH_SIZE = 3

FULL_SITE_MAP = {
    "amz": "amazon.com",
    "etsy": "etsy.com",
    "ebay": "ebay.com",
    "tiktok": "tiktok.com",
    "google": "google.com",
    "youtube": "youtube.com",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "ali": "aliexpress.com",
    "walmart": "walmart.com",
    "paypal": "paypal.com"
}

DEFAULT_SITE_LIST = ["google", "gmail", "amazon"]


#input
def genADSPowerLaunchSteps(worksettings, stepN, theme):
    psk_words = ""
    print("DEBUG", "genAMZBrowseDetails...", worksettings, "stepN:", stepN)

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global sk_work_settings\nprint('SK_WORK_SETTINGS:',sk_work_settings)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepOpenApp("run", True, "sk_work_settings['app_exe']", "", "", "", "expr", "sk_work_settings['cargs']", 3, this_step)
    psk_words = psk_words + step_words

    # wait till the main window shows up
    this_step, step_words = genStepWait(6, 0, 0, this_step)
    psk_words = psk_words + step_words

    # now read screen, if there is log in, then click on log in.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words


    # check whether this is the login window, if so, assume user name password already auto filled in, simply click on "Log in" button.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "login", "direct", "anchor text", "any", "useless", "loginwin", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("loginwin == True", "", "", this_step)
    psk_words = psk_words + step_words

    # click on the 2nd log in on the screen (index start at 0, so 1 is the 2nd one)
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "login", "anchor text", "Log in", 1, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # wait 3 seconds till it logs in....
    this_step, step_words = genStepWait(3, 0, 0, this_step)
    psk_words = psk_words + step_words

    # now that we have logged in, load profiles.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "login", "direct", "anchor text", "any", "useless", "loginwin", "ads", False, this_step)
    psk_words = psk_words + step_words
    # close bracket
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # check one more time, if for some reason still in log in windows, that means somehow username and password is incorrect,
    # in such a case, we should quit and claim failer.
    this_step, step_words = genStepCheckCondition("loginwin != True", "", "", this_step)
    psk_words = psk_words + step_words


    # check whether there is any pop up ads, there might be multiple advertising pop ups, if so, close it one by one until we see the
    # adspower's main home screen. The indication of whether the main screen is shown is to to check whether the button "All groups" is
    # found on screen, if not that means some pop up(s) block it.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "all_groups", "direct", "anchor text", "any", "useless", "main_shown", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("main_shown != True", "", "", "browseEtsyOrderPage" + str(this_step), this_step)
    psk_words = psk_words + step_words

    # Click on the close icon, but make sure close the lower most one. because the main window has a close icon too...
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "close", "anchor icon", "", 1, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "all_groups", "direct", "anchor text", "any", "useless", "main_shown", "ads", False, this_step)
    psk_words = psk_words + step_words

    # close bracket
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    # now that we have logged in, load default profiles.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "profiles", "anchor text", "",  0, "center", [0, 0], "box", 2, 2, [7, 2], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # set output to ERROR.
    this_step, step_words = genStepCallExtern("global fout\nfout = 'ERROR: Unable To Log Into ADS Power!'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words



    # close bracket for if loginwin != True
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words



# from given bots information, generate profiles for ADS power to load.
# assumption: there will be a large .xlsx that contains the correct profiles for all bots.
# and we will select x number of bots that are scheduled to run at this time,
# this skill assumes ADS power is already launched, and its main window opened......
# input to this skill: profile file name, os, site,
# output of this skill: whether the profile file is loaded.
# steps:
# 1) delete all existing profiles.
# 2) load a current profile.
def genWinADSBatchImportSkill(worksettings, stepN, theme):
    psk_words = "{"
    # site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_local_load_batch_import", "win", "1.0", "AIPPS LLC", "PUBWINADSBATCHIMPORT001",
                                          "Windows ADS Power Batch Import Profiles.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_local_load/batch_import", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    # assume profile file is ready.
    this_step, step_words = genStepCallExtern("global in_file_op\nin_file_op = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global current_profile_path\ncurrent_profile_path = fin[1]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # os is like windows, macos, linux...
    this_step, step_words = genStepCallExtern("global current_profile_name\ncurrent_profile_name = fin[2]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # site is like amazon, ebay, etcs....
    this_step, step_words = genStepCallExtern("global in_bot_email\nin_bot_email = fin[3]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global in_full_site\nin_full_site = fin[4]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global in_os\nin_os = fin[5]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "profiles", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [7, 2], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearchAnchorInfo("screen_info", "no_data", "direct", "anchor text", "any", "useless", "no_profiles", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not no_profiles", "", "", this_step)
    psk_words = psk_words + step_words


    # here should delete existing loaded profiles first.
    # first click on select All.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "checkbox", "anchor icon", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "trash0", "anchor icon", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    #read screen for the confirmation pop up.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # click on the confirmation popup.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "ok", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now do the batch import
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "new_profile", "anchor text", "", 0, "center", [0, 0], "box", 2, 5, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now do the batch import
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "batch_import", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [1, 5], this_step)
    psk_words = psk_words + step_words

    # first, confirm browser selection
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearchAnchorInfo("screen_info", "chrome_kernel", "direct", "anchor text", "any", "useless", "sun_selected", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not sun_selected", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "browser_sun", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # now select OS

    this_step, step_words = genStepCheckCondition("in_os == 'win'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "windows_checked", "direct", "anchor text", "any", "useless", "win_selected", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not win_selected", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "os_windows", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # else of "in_os == 'win'"
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("in_os == 'mac'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "mac_checked", "direct", "anchor text", "any", "useless", "mac_selected", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not mac_selected", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "os_mac", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # end of "not mac_selected"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # else of "in_os == 'mac'"
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("in_os == 'linux'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "linux_checked", "direct", "anchor text", "any", "useless", "linux_selected", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not linux_selected", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "os_linux", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # end of "not linux_selected"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of "in_os == 'linux'"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of "in_os == 'mac'"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of "in_os == 'win'"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # now select website.

    # now scroll down a bit and click on account platform,  and select and correct site.
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 50, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # this should bring out a list of web site choices
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "specified_url", "anchor text", "", 0, "left", [2, 0], "box", 2, 2, [0, 5], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchWordLine("screen_info", "in_full_site", "direct", "any", "useless", "site_found", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "other", "direct", "anchor text", "any", "useless", "site_list_ended", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("not (site_found or site_list_ended)", "", "", "search_site" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # give 2 scoll steps
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 2, "raw", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchWordLine("screen_info", "in_full_site", "direct", "any", "useless", "site_found", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "other", "direct", "anchor text", "any", "useless", "site_list_ended", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # check whether the site is found
    this_step, step_words = genStepCheckCondition("site_found", "", "", this_step)
    psk_words = psk_words + step_words

    # make sure the OS is selected correctly.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "in_full_site", "anchor text", "", 0, "left", [3, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # else for condition "site_found"
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # the site is not in the list, so type it in
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "other", "anchor text", "", 0, "left", [3, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "enter_platform", "anchor text", "", 0, "left", [3, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "in_full_site", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # now start file open routine.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "drag_drop", "anchor text", "", 0, "left", [3, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # get rid to call open_save_as sub skill
    this_step, step_words = genStepCreateData("expr", "file_open_input", "NA", "['open', current_profile_path, current_profile_file]", this_step)
    psk_words = psk_words + step_words

    # now open the profile
    this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_open_input", "fileStatus", this_step)
    psk_words = psk_words + step_words

    # wait for batch import to fully load
    this_step, step_words = genStepWait(10, 0, 0, this_step)
    psk_words = psk_words + step_words

    # now get ready to click OK button
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "ok", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words


    # now that the new profile is loaded. double check to make sure the designated bot profile is loaded from this batch.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchWordLine("screen_info", "in_bot_email", "direct", "any", "useless", "bot_found", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not bot_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    # if not on screen, scroll down and check again.
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 50, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchWordLine("screen_info", "in_bot_email", "expr", "any", "useless", "bot_loaded", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("bot_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "bot_open", "expr", "anchor text", "any", "bot_open_button", "bot_loaded", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_local_load/batch_import", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows ads power batch import profiles....." + psk_words)

    return this_step, psk_words



def genWinADSRemoveProfilesSkill(worksettings, stepN, theme):
    psk_words = "{"
    # site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_local_remove_profile", "win", "1.0", "AIPPS LLC", "PUBWINADSREMOVE001",
                                          "Windows ADS Power Remove Profile.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_local_open/remove_profile", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genADSPowerLaunchSteps(worksettings, this_step, theme)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_local_open/open_profile", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows ads power profile remove....." + psk_words)

    return this_step, psk_words


def genWinADSOpenProfileSkill(worksettings, stepN, theme):
    psk_words = "{"
    # site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_local_open_profile", "win", "1.0", "AIPPS LLC", "PUBWINADSOPEN001",
                                          "Windows ADS Power Open Profile.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_local_open/open_profile", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genADSPowerLaunchSteps(worksettings, this_step, theme)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_local_open/open_profile", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows ads power open...." + psk_words)

    return this_step, psk_words


def genStepSetupADS(all_fname, tbr_fname, exe_link, ver, stepN):
    stepjson = {
        "type": "setup ads",
        "action": "setup ads",
        "all_f_name": all_fname,
        "tbr_f_name": tbr_fname,
        "exe": exe_link,
        "version": ver
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# all_profiles_csv is the csv file name containing all user profiles.
# batch_csv is the resulting csv file name that will contain only bots associated profiles.
def extractBatchOfProfiles(bots, all_profiles_xls, batch_xls):
    try:
        # df = pd.read_csv(all_profiles_csv)
        df = pd.read_excel(all_profiles_xls)

        # Filter rows based on user name key in each dictionary
        this_batch_of_rows = []
        for bot in bots:
            this_batch_of_rows.append(df[df['username'].str.strip() == bot.getEmail()])

        # Concatenate filtered rows into a new DataFrame
        new_df = pd.concat(this_batch_of_rows)

        # Save the new DataFrame to a CSV file
        # new_df.to_csv(batch_xls, index=False)
        new_df.to_excel(batch_xls, index=False)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorKeyInput:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorKeyInput: traceback information not available:" + str(e)
        print(ex_stat)


# for All tasks, divide them into batches based on ADS batch limit, for example, low cost ADS supports
# loading 10 profiles at a time only.
# 1) flatten all tasks
# 2) sort all tasks by earliest scheduled start time of all the assigned mission/tasks.
# 3) group them into batches.
def earliest_start(task):
    # Example: Sorting based on the sum of attributes a and b
    if len(task["other_works"]) > 0:
        if len(task["bw_works"]) > 0:
            return min(task["other_works"][0]["start_time"], task["bw_works"][0]["start_time"])
        else:
            return task["other_works"][0]["start_time"]
    else:
        return task["bw_works"][0]["start_time"]

def task_start_time(task):
    return task["start_time"]


def processADSProfileBatches(step, i, mission):
    vTasks = step["task_group"]
    profiles_dir = step["profiles_dir"]
    all_profiles = step["all_profiles"]
    results_files_name = step["result"]
    ex_stat = ""
    return (i + 1), ex_stat

def getBotEMail(bid, bots):
    found = [b for b in bots if b.getBid() == bid]
    if len(found) > 0:
        return found[0].getEmail()
    else:
        return ""

# input: all bot tasks on 1 vehicle.
# output: a flattend list of tasks with 4 new attributes/keys added to task: bid, b_email, full_site, batch_file
# so in the code of executing tasks one by one, when it's time to run, it will check which profile
# Note: no all tasks involves using ADS, so could very well be that out of N bots, there will be less than N lines in
#       profiles.
def formADSProfileBatches(vTasks, commander):
    # vTasks, allbots, all_profiles_csv, run_data_dir):
    try:
        tgbs = []

        # flatten across time zone
        for tz in vTasks.keys():
            tgbs = tgbs + vTasks[tz]

        all_works = []
        for tgb in tgbs:
            bid = tgb["bid"]

            for bw in tgb["bw_works"]:
                bw["bid"] = bid
                all_works.append(bw)

            for other in tgb["other_works"]:
                other["bid"] = bid
                all_works.append(other)

        time_ordered_works = sorted(all_works, key=lambda x: x["start_time"], reverse=False)

        ads_profile_batches_fnames = gen_ads_profile_batchs(commander, commander.getIP(), time_ordered_works)

        print("all_ads_batches:", ads_profile_batches_fnames)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorformADSProfileBatches:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorformADSProfileBatches: traceback information not available:" + str(e)
        print(ex_stat)

    # sorted_all_ads_batches = sorted(all_ads_batches, key=lambda x: x["start_time"], reverse=False)
    # flattened_ads_tasks = [item for one_ads_batch in all_ads_batches for item in one_ads_batch]
    return time_ordered_works, ads_profile_batches_fnames

# taskgroup will be the full task group on a vehicle.
# profiles_dir is the path name that will hold the resulting files
# all_profiles is the file full path name of the .xls file that contains all available profiles.
# result_list is the variable string name that will holds the result which will be a list of profile file names.
def genStepCreateADSProfileBatches(taskgroup, profiles_dir, all_profiles, result_list, stepN):
    stepjson = {
        "type": "Create ADS Profile Batches",
        "task_group": taskgroup,
        "profiles_dir": profiles_dir,
        "all_profiles": all_profiles,
        "result": result_list
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# gather 10 profiles into 1 and use this combined file for batch import.
def combineProfilesXlsx(xlsProfilesToBeLoaded):
    # Replace with the path to your files
    ads_profile_dir = 'path_to_your_excel_files'

    # List to hold dataframes
    dfs = []

    # Iterate over the files in the directory
    for filename in xlsProfilesToBeLoaded:
        if filename.endswith('.xlsx'):
            file_path = os.path.join(ads_profile_dir, filename)
            # Read the excel file and append it to the list
            dfs.append(pd.read_excel(file_path))

    # Concatenate all dataframes
    combined_df = pd.concat(dfs, ignore_index=True)

    this_batch = os.path.join(ads_profile_dir, 'this_batch.xlsx')
    # Write the combined dataframe to a new excel file
    combined_df.to_excel(this_batch, index=False)



# this functionr reads an ADS power saved profile in text format and return a json object that contains the file contents.
def readTxtProfile(fname):
    pfJsons = []
    pfJson = {}
    nl = 0
    with open(fname, 'r') as file:
        for line in file:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                if key == "acc_id":
                    if nl > 0:
                        pfJsons.append(pfJson)
                        pfJson = {}

                    pfJson[key] = value
                elif key == "cookie":
                    pfJson[key] = json.loads(value)
                else:
                    pfJson[key] = value

                nl = nl + 1

        if len(pfJson.keys()) > 0:
            pfJsons.append(pfJson)
    print("["+str(len(pfJsons))+"] profiles read.....")
    file.close()
    return pfJsons

# read in multiple files, returns a list of jsons
def readTxtProfiles(fnames):
    pfJsons = []
    for fname in fnames:
        pfJsons = pfJsons + readTxtProfile(fname)

    return pfJsons


# this function removes useless cookies from a ADS Power profile object, so that the cookie is short enough to fit into
# an excel file cell (32768 Byte), and enough to let one log into the target web site, typically 1 gamil + 1 other site.
def removeUselessCookies(pfJson, site_list):
    qualified_cookies = list(filter(lambda x: any(site in x["domain"] for site in site_list), pfJson["cookie"]))
    pfJson["cookie"] = qualified_cookies

# this function takes a pfJson and writes back to a xlsx file so that ADS power can import it.
def genProfileXlsx(pfJsons, fname, batch_bot_mid_keys, site_lists):
    # Convert JSON data to a DataFrame
    new_pfJsons = []

    for one_profile in batch_bot_mid_keys:
        one_un = one_profile.split("_")[0]
        found_match = False
        for original_pfJson in pfJsons:
            un = original_pfJson["username"].split("@")[0]
            if un == one_un:
                found_match = True
                break

        if found_match:
            if one_profile in site_lists.keys():
                site_list = site_lists[one_profile]
            else:
                # just use some default list.
                site_list = DEFAULT_SITE_LIST
            print("found a match, filter a json cookie....")
            pfJson = copy.deepcopy(original_pfJson)
            removeUselessCookies(pfJson, site_list)
            pfJson["cookie"]=json.dumps(pfJson["cookie"])
            new_pfJsons.append(pfJson)

    df = pd.DataFrame(new_pfJsons)
    print("writing to:", fname)
    # Write DataFrame to Excel file
    df.to_excel(fname, index=False)



def agggregateProfileTxts2Xlsx(profile_names, xlsx_name, site_lists):
    # Convert JSON data to a DataFrame
    pfJsons = readTxtProfiles(profile_names)
    for pfJson in pfJsons:
        un = pfJson["username"].split("@")[0]
        if un in site_lists.keys():
            site_list = site_lists[un]
        else:
            # just use some default list.
            site_list = DEFAULT_SITE_LIST
        removeUselessCookies(pfJson, site_list)
        pfJson["cookie"]=json.dumps(pfJson["cookie"])
    df = pd.DataFrame(pfJsons)
    print("writing to:", xlsx_name)
    # Write DataFrame to Excel file
    df.to_excel(xlsx_name, index=False)



def genProfileTxt(pfJsons, fname):
    # Convert JSON data to a DataFrame
    with open(fname, 'w') as f:
        for pfJson in pfJsons:
            f.write("\n")
            pfJson["cookie"]=json.dumps(pfJson["cookie"])

            for pfkey in pfJson.keys():
                f.write(pfkey+"="+pfJson[pfkey]+"\n")
    f.close()

# this function takes a pfJson and writes back to a xlsx file so that ADS power can import it.
# site_lists is in the format "{email_before@ : ["google", "gmail", "amazon"]}, .... }
# the reason we need this is full cookie is too large to fit into an excel cell, and
# ads batch import only recognize a xlsx file input. so the cookie field should be
# filtered to contain only sites that a mission needs.
def genProfileXlsxs(pfJsons, fnames, site_lists):
    for pfJson, fname in zip(pfJsons, fnames):
        genProfileXlsx(pfJson, fname, site_lists)

# this function takes a pfJson and writes back to a xlsx file so that ADS power can import it.
def covertTxtProfiles2XlsxProfiles(fnames, site_lists):
    pf_idx = 0
    for fname in fnames:
        basename = os.path.basename(fname)
        dirname = os.path.dirname(fname)
        xls_name = dirname + "/" + basename.split(".")[0]+".xlsx"
        pfjsons = readTxtProfile(fname)
        print("reading in # jsons:", len(pfjsons))
        genProfileXlsx(pfjsons, xls_name, site_lists.keys(), site_lists)
        pf_idx = pf_idx + 1

# create bot ads profiles in batches. each batch can have at most batch_size number of profiles.
# assume each bot already has a txt version of the profile there.

def gen_ads_profile_batchs(commander, host_ip, task_groups):
    print("commander ads batch size:", commander.getADSBatchSize())

    print("time_ordered_works:", task_groups)
    pfJsons_batches = []
    bot_pfJsons=[]
    v_ads_profile_batch_xlsxs = []
    batch_idx = 0
    batch_file = "Host" + host_ip + "B" + str(batch_idx) + "profile.xlsx"
    w_idx = 0
    batch_bot_mids = []
    batch_bot_profiles_read = []
    for bot_work in task_groups:
        bid = bot_work["bid"]
        found_bots = list(filter(lambda cbot: cbot.getBid() == bid, commander.bots))

        mid = bot_work["mid"]

        found_missions = list(filter(lambda cm: cm.getMid() == mid, commander.missions))
        if len(found_missions) > 0:
            found_mision = found_missions[0]
            bot_work["ads_xlsx_profile"] = batch_file
            found_mision.setADSXlsxProfile(batch_file)

        if len(found_bots) > 0:
            found_bot = found_bots[0]
            bot_txt_profile_name = commander.getADSProfileDir() + "/" + found_bot.getEmail().split("@")[0]+".txt"
            bot_mid_key = found_bot.getEmail().split("@")[0]+"_m"+str(found_mision.getMid()) + ".txt"

            if os.path.exists(bot_txt_profile_name) and bot_txt_profile_name not in batch_bot_profiles_read:
                newly_read = readTxtProfile(bot_txt_profile_name)
                batch_bot_profiles_read.append(bot_txt_profile_name)
            else:
                newly_read = []

            batch_bot_mids.append(bot_mid_key)

            bot_pfJsons = bot_pfJsons + newly_read

            if w_idx >= commander.getADSBatchSize():
                genProfileXlsx(bot_pfJsons, batch_file, batch_bot_mids, commander.getCookieSiteLists())
                v_ads_profile_batch_xlsxs.append(batch_file)
                w_idx = 0
                bot_pfJsons = []
                batch_bot_mids = []
                batch_bot_profiles_read = []
                batch_idx = batch_idx + 1
                batch_file = "Host" + host_ip + "B" + str(batch_idx) + "profile.xlsx"
            else:
                w_idx = w_idx + 1


    return v_ads_profile_batch_xlsxs

# after a batch save, grab individual profiles in the batch and update
# each profile individually both txt and xlsx version so that time
# a batch can be done easily.
def update_individual_profile_from_batch_saved_txt(batch_profiles_txt, site_list):
    pfJsons = readTxtProfile(batch_profiles_txt)
    pf_dir = os.path.dirname(batch_profiles_txt)
    for pfJson in pfJsons:
        # xlsx_file_path = pf_dir + "/" + pfJson["username"].split("@")[0]+".xlsx"
        txt_file_path = pf_dir + "/" + pfJson["username"].split("@")[0] + ".txt"
        # genProfileXlsx([pfJson], xlsx_file_path, site_list)
        existing = readTxtProfile(txt_file_path)
        existing_cookies = existing["cookie"]
        new_cookies = pfJson["cookie"]
        pfJson["cookie"] = merge_cookies(existing_cookies, new_cookies)
        genProfileTxt([pfJson], txt_file_path)

# for a list of existing cookies, find matching in name and domain and path, if matched all three in newones,
# replace the existing cookie with the one in newones, otherwise, simply add newones into the existing ones.
def merge_cookies(existing, new_ones):
    merged_cookies = existing.copy()

    for new_cookie in new_ones:
        matched_index = None
        for i, existing_cookie in enumerate(merged_cookies):
            if (existing_cookie['name'] == new_cookie['name'] and
                existing_cookie['domain'] == new_cookie['domain'] and
                existing_cookie['path'] == new_cookie['path']):
                matched_index = i
                break

        if matched_index is not None:
            merged_cookies[matched_index] = new_cookie
        else:
            merged_cookies.append(new_cookie)

    return merged_cookies