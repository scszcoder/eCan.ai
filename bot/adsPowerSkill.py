import os

import pandas as pd

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
def formADSProfileBatches(vTasks, all_bots, all_profiles_xls, profiles_dir):
    # vTasks, allbots, all_profiles_csv, run_data_dir):

    try:
        all_tasks_by_bots = []
        for tz in vTasks.keys():
            all_tasks_by_bots = all_tasks_by_bots + vTasks[tz]
        print("all_tasks_by_bots:", all_tasks_by_bots)
        batch_idx = 0
        ads_batches=[]
        ads_batches_files = []
        ads_batch = []

        works_by_site={}
        sites_involved = []
        # note on the cloud side, the task groups are already divided by OS, i.e. windows, mac, linux
        # so vTasks will only need to be re-grouped by site.
        # for each bid:bw_works and bid:otherworks,
        for tasks in all_tasks_by_bots:
            if len(tasks["bw_works"]) > 0:
                for work in tasks["bw_works"]:
                    site = work["cuspas"].split(",")[2]
                    work["bid"] = tasks["bid"]
                    work["b_email"] = getBotEMail(work["bid"], all_bots)
                    if site in FULL_SITE_MAP:
                        work["full_site"] = FULL_SITE_MAP[site]
                    else:
                        work["full_site"] = site+".com"
                    if site not in sites_involved:
                        print("new bw site:", site)
                        works_by_site[site] = []
                        sites_involved.append(site)
                    print("bw Site:", site, "work:", work)
                    works_by_site[site].append(work)

            if len(tasks["other_works"]) > 0:
                for work in tasks["other_works"]:
                    site = work["cuspas"].split(",")[2]
                    work["bid"] = tasks["bid"]
                    work["b_email"] = getBotEMail(work["bid"], all_bots)
                    if site in FULL_SITE_MAP:
                        work["full_site"] = FULL_SITE_MAP[site]
                    else:
                        work["full_site"] = site+".com"
                    if site not in sites_involved:
                        print("new other site:", site)
                        works_by_site[site] = []
                        sites_involved.append(site)
                    print("other Site:", site, "work:", work)
                    works_by_site[site].append(work)

        print("works_by_site:", works_by_site)
        all_ads_batches = []
        for one_site in works_by_site.keys():
            works_by_site[one_site] = sorted(works_by_site[one_site], key=lambda x: x["start_time"], reverse=False)

            ads_batches = []
            start_idx = 0
            end_idx = 0
            # about to fill 1 batch
            while end_idx < len(works_by_site[one_site]):
                if (len(works_by_site[one_site]) - start_idx) >= (ADS_BATCH_SIZE - len(ads_batch)):
                    end_idx = start_idx + (ADS_BATCH_SIZE - len(ads_batch))
                    ads_batch = ads_batch + works_by_site[one_site][start_idx:end_idx]
                    start_idx = end_idx
                    print("SSstart_idx:", start_idx, "end_idx:", end_idx)
                    #increment batch counter, finish the batch
                    ads_batches.append(ads_batch)
                    batch_idx = batch_idx + 1
                    ads_batch = []
                else:
                    # down to the last batch.
                    ads_batch = ads_batch + works_by_site[one_site][start_idx:]
                    end_idx = len(works_by_site[one_site])
                    start_idx = end_idx
                    print("start_idx:", start_idx, "end_idx:", end_idx)
            # handle the last batch
            if len(ads_batch) > 0:
                ads_batches.append(ads_batch)
            print("ads_batches:", ads_batches)

            # now， ads_batches contains all batches for this site, for example amazon.com
            # now generate ADS profiles for each batch.
            for bi in range(len(ads_batches)):
                all_bids = [t["bid"] for t in ads_batches[bi]]
                bots_in_batch = [b for b in all_bots if b.getBid() in all_bids]
                ads_batch_file = profiles_dir + "/ads_profiles_" + one_site +"_"+str(bi)+".xls"
                print("allbids:", all_bids)
                print("all_profiles_csv:", all_profiles_xls, "ads_batch_file:", ads_batch_file, "bots length:", len(bots_in_batch))
                for t in ads_batches[bi]:
                    t["batch_file"] = ads_batch_file

                if os.path.isfile(all_profiles_xls):
                    extractBatchOfProfiles(bots_in_batch, all_profiles_xls, ads_batch_file)
                    ads_batches_files.append(ads_batch_file)

            all_ads_batches = all_ads_batches + ads_batches
        print("all_ads_batches:", all_ads_batches)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorKeyInput:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorKeyInput: traceback information not available:" + str(e)
        print(ex_stat)

    # sorted_all_ads_batches = sorted(all_ads_batches, key=lambda x: x["start_time"], reverse=False)
    flattened_ads_tasks = [item for one_ads_batch in all_ads_batches for item in one_ads_batch]
    return flattened_ads_tasks, ads_batches_files

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