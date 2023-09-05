import os

import pandas as pd

from basicSkill import *


def genLaunchADSPower(adsPowerLink, url, aargs, theme, root, stepN):
    psk_words = ""
    print("DEBUG", "genAMZBrowseDetails...")

    this_step, step_words = genStepOpenApp("run", True, adsPowerLink, url, "", "", aargs, 3, stepN)
    psk_words = psk_words + step_words

    # some steps here to adjust window size and location here...


    # now read screen, if there is log in, then click on log in.
    this_step, step_words = genStepExtractInfo("", root, "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # check whether there is any match of this page's product, if matched, click into it.
    this_step, step_words = genStepSearch("screen_info", "log_in", "anchor text", "any", "useless", "loginwin", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("loginwin == True", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "log_in", "anchor text", "Log in", [0, 0], "center", [0, 0], "pixel", 2, 2, this_step)
    psk_words = psk_words + step_words

    # now that we have logged in, load profiles.
    this_step, step_words = genStepExtractInfo("", root, "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # close bracket
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # now that we have logged in, load profiles.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "new_profile", "anchor text", "See All Reviews",  [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", root, "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "batch_import", "anchor text", "See All Reviews", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    # click on account platform,  and select amazon
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", "50", "screen", "scroll_resolution", False, this_step)
    psk_words = psk_words + step_words



    # click on drag and drop


    # click and type through the file selector and select the xls file.
    # the presumption is the bots to be run in this batch are already grouped into a xls file as input to this function.
    # click OK to load the bot profiles.
    this_step, step_words = genStepMouseClick("Single Click", "", False, "screen_info", "amazon", "anchor text", "See All Reviews", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", False, "screen_info", "amazon", "anchor text", "See All Reviews", [0, 0], "right", [1, 0], "box",  2, 0, this_step)
    psk_words = psk_words + step_words

    # click OK to load the bot profiles.
    this_step, step_words = genStepMouseClick("Single Click", "", False, "screen_info", "ok", "anchor text", "See All Reviews", [0, 0], "right", [1, 0], "box",  2, 0, this_step)
    psk_words = psk_words + step_words



# from given bots information, generate profiles for ADS power to load.
# assumption: there will be a large .xlsx that contains the correct profiles for all bots.
# and we will select x number of bots that are scheduled to run at this time,
def genWinADSBatchImportSkill(xlsfile):
    print("ADS: load profiles")

    # click on Batch Import

    #  extract screen

    #  fill out Group, Tag info, double check

    # scroll down 1/2 screen

    # fill account platform (amz, ebay, ....)

    # load xls file

    # hit OK



def genWinADSRemoveProfilesSkill(cfg):
    print("ADS: remove all profiles")

    # Click on Profiles

    # click on the top check box

    # click on the trash can icon to remove.


def genWinADSOpenSkill(cfg):
    print("ADS: open profile.(assume profiles already loaded.)")

    # find bot profile and its corresponding Open button,

    # click on Open

    # Wait a little while

    # if nothing goes wrong the browser will be up.



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
