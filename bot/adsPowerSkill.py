import os

import pandas as pd

from basicSkill import *

ADS_BATCH_SIZE = 3
#input
def genADSPowerLaunchSteps(worksettings, theme, stepN):
    psk_words = ""
    print("DEBUG", "genAMZBrowseDetails...")

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepOpenApp("run", True, "sk_work_settings['app_exe']", "", "", "", "expr", "sk_work_settings['cargs']", 3, this_step)
    psk_words = psk_words + step_words

    # some steps here to adjust window size and location here...

    # now read screen, if there is log in, then click on log in.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words


    # check whether there is any match of this page's product, if matched, click into it.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "login", "direct", "anchor text", "any", "useless", "loginwin", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("loginwin == True", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "login", "anchor text", "Log in", 1, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now that we have logged in, load profiles.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # close bracket
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # check whether there is any pop up ads, if so, close it .
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "new_profile", "direct", "anchor text", "any", "useless", "main_shown", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("main_shown != True", "", "", "browseEtsyOrderPage" + str(this_step), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "close", "anchor text", "", 1, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "mac_os", "direct", "anchor text", "any", "useless", "main_shown", "ads", False, this_step)
    psk_words = psk_words + step_words

    # close bracket
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words



    # now that we have logged in, load profiles.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "profiles", "anchor text", "",  1, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words


    return this_step, psk_words



# from given bots information, generate profiles for ADS power to load.
# assumption: there will be a large .xlsx that contains the correct profiles for all bots.
# and we will select x number of bots that are scheduled to run at this time,
# this skill assumes ADS power is already launched, and its main window opened......
def genWinADSBatchImportSkill(worksettings, stepN, theme):
    psk_words = "{"
    # site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_local_remove_profile", "win", "1.0", "AIPPS LLC", "PUBWINADSBATCHIMPORT001",
                                          "Windows ADS Power Batch Impor Profiles.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_local_load/batch_import", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "new_profile", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "batch_import", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # click on account platform,  and select amazon
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", "50", "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "specified_url", "anchor text", "", 0, "left", [3, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "mac_os", "direct", "anchor text", "any", "useless", "platform_found", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("platform_found != True", "", "", "browseEtsyOrderPage" + str(this_step), this_step)
    psk_words = psk_words + step_words

    # click on account platform,  and select amazon
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 2, "raw", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "mac_os", "direct", "anchor text", "any", "useless", "main_shown", "ads", False, this_step)
    psk_words = psk_words + step_words

    # close bracket
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now the target platform is found, click on the platform.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "target_platform", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # click on drag and drop
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "drag_drop", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # click and type through the file selector and select the xls file.
    # the presumption is the bots to be run in this batch are already grouped into a xls file as input to this function.
    # click OK to load the bot profiles.
    this_step, step_words = genStepCreateData("expr", "xls_path", "NA", 'fin[0]', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "xls_file", "NA", 'fin[1]', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "file_open_input", "NA", "['open', 'xls_path', 'xls_file']", this_step)
    psk_words = psk_words + step_words

    # save the html file.
    this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_open_input", "fileStatus", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "ok", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
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


def genBatchBasedOnADSSizeLimit(vTasks, allbots, all_profiles_csv, run_data_dir):
    try:
        all_tasks = []
        for tz in vTasks:
            all_tasks = all_tasks + vTasks[tz]
        print("all_tasks:", all_tasks)
        sorted_tasks = sorted(all_tasks, key=earliest_start)
        print("sorted_tasks:", sorted_tasks)
        batch_idx = 0
        start_idx = 0
        end_idx = 0
        ads_batches=[]
        ads_batch = []
        # about to fill 1 batch
        while end_idx < len(sorted_tasks):
            if (len(sorted_tasks) - start_idx) >= (ADS_BATCH_SIZE - len(ads_batch)):
                end_idx = start_idx + (ADS_BATCH_SIZE - len(ads_batch))
                ads_batch = ads_batch + sorted_tasks[start_idx:end_idx]
                start_idx = end_idx
                print("SSstart_idx:", start_idx, "end_idx:", end_idx)
                #increment batch counter, finish the batch
                ads_batches.append(ads_batch)
                batch_idx = batch_idx + 1
                ads_batch = []
            else:
                # down to the last batch.
                ads_batch = ads_batch + sorted_tasks[start_idx:]
                end_idx = len(sorted_tasks)
                start_idx = end_idx
                print("start_idx:", start_idx, "end_idx:", end_idx)

        if len(ads_batch) > 0:
            ads_batches.append(ads_batch)
        print("ads_batches:", ads_batches)

        for bi in range(len(ads_batches)):
            for t in ads_batches[bi]:
                t["batch_id"] = bi
            allbids = [t["bid"] for t in ads_batches[bi]]
            bots_in_batch = [b for b in allbots if b.getBid() in allbids]
            ads_batch_file = run_data_dir + "/ads_profiles_" + str(bi)+".xls"
            print("allbids:", allbids)
            print("all_profiles_csv:", all_profiles_csv, "ads_batch_file:", ads_batch_file, "bots length:", len(bots_in_batch))
            extractBatchOfProfiles(bots_in_batch, all_profiles_csv, ads_batch_file)

        print("ads_batches:", ads_batches)


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorKeyInput:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorKeyInput: traceback information not available:" + str(e)
        print(ex_stat)