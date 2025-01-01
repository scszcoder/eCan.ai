# hr skills
import json
import random
from datetime import datetime

from bot.Logger import log3
from bot.basicSkill import DEFAULT_RUN_STATUS, symTab, STEP_GAP, genStepHeader, genStepStub, genStepCreateData, genStepUseSkill, genStepWait, \
    genStepCallExtern, genStepExtractInfo, genStepSearchWordLine, genStepSearchAnchorInfo, genStepCheckCondition, \
    genStepLoop, genStepECBScreenBotCandidates, genStepECBCreateBots, genStepExternalHook, genStepECBDeleteBots
from bot.adsPowerSkill import genStepsADSPowerExitProfile
import re
from difflib import SequenceMatcher
import traceback
from bot.scraperAmz import genStepAmzScrapeBuyOrdersHtml, amz_buyer_scrape_product_list, amz_buyer_scrape_product_details, \
    amz_buyer_scrape_product_reviews
import time
import os
from fuzzywuzzy import fuzz



def genWinChromeECBHrRecruitSkill(worksettings, stepN, theme):

    log3("GENERATING genWinChromeECBHrRecruitSkill======>")
    this_step = stepN
    psk_words = "{"
    site_url = "https://www.maipps.com/"

    try:
        this_step, step_words = genStepHeader("win_chrome_ecb_hr_recruit", "win", "1.0", "AIPPS LLC",
                                              "PUBWINCHROMECBHRRECRUIT001",
                                              "Recuit Agents.", stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("start skill main", "public/win_chrome_ecb_home/hr_recruit", "", this_step)
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


        # this_step, step_words = genStepCreateData("string", "file_path", "NA", "daily_prep_hook.py", this_step)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "file_prefix", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global file_name, file_prefix, sk_work_settings\nfile_prefix=sk_work_settings['local_data_path']+'/my_skills/hooks'\nfile_name = 'hr_recruit_get_candidates_hook.py'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "params", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("import utils.logger_helper\nglobal params, symTab\nparams={}\nparams['symTab']=symTab\nparams['login']=utils.logger_helper.login", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("string", "ts_name", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "forceful", "NA", "false", this_step)
        psk_words = psk_words + step_words

        # obtain candidates this is organization specific so call an external hook.
        this_step, step_words = genStepExternalHook("var", "file_prefix", "file_name","params", "candidates", "prep_success", this_step)
        psk_words = psk_words + step_words

        # now screen candidates
        this_step, step_words = genStepECBScreenBotCandidates("candidates", "qualifiedCandidates", "op_success", this_step)
        psk_words = psk_words + step_words

        # now turn candidates into internal bots/agents
        this_step, step_words = genStepECBCreateBots("qualifiedCandidates", "newBots", "recruit_success", this_step)
        psk_words = psk_words + step_words

        # now create a loop to generate ADS profile on each bots.
        this_step, step_words = genStepCreateData("int", "nth_bot", "NA", 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "profile_created", "NA", False, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "create_profile_input", "NA", [], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepLoop("nth_bot < len(newBots)", "", "", "newADS"+str(stepN+1), this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCallExtern("global current_expandable\ncurrent_expandable = read_mores[nth_expandable]", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepUseSkill("create_profile", "public/win_ads_local_open", "create_profile_input", "profile_created", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global nth_bot\nnth_bot = nth_bot + 1", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        # close for loop: nth_expandable < expandables_count, finished click on all expandables on this screen.
        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end skill", "public/win_chrome_ecb_home/hr_recruit", "", this_step)
        psk_words = psk_words + step_words

        psk_words = psk_words + "\"dummy\" : \"\"}"
        # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genWinChromeECBHrRecruitSkill: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genWinChromeECBHrRecruitSkill: {ex_stat}")

    return this_step, psk_words



def genWinChromeECBHrLayoffSkill(worksettings, stepN, theme):

    log3("GENERATING genWinChromeECBHrLayoffSkill======>")
    this_step = stepN
    psk_words = "{"
    site_url = "https://www.maipps.com/"

    try:
        this_step, step_words = genStepHeader("win_chrome_ecb_hr_layoff", "win", "1.0", "AIPPS LLC",
                                              "PUBWINCHROMECBHRLAYOFF001",
                                              "Layoff Agents.", stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("start skill main", "public/win_chrome_ecb_home/hr_layoff", "", this_step)
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


        # this_step, step_words = genStepCreateData("string", "file_path", "NA", "daily_prep_hook.py", this_step)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "file_prefix", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global file_name, file_prefix, sk_work_settings\nfile_prefix=sk_work_settings['local_data_path']+'/my_skills/hooks'\nfile_name = 'hr_layoff_remove_accounts_hook.py'", "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "params", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("import utils.logger_helper\nglobal params, symTab\nparams={}\nparams['symTab']=symTab\nparams['login']=utils.logger_helper.login", "", "in_line", "", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCreateData("string", "ts_name", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "forceful", "NA", "false", this_step)
        psk_words = psk_words + step_words

        # obtain candidates this is organization specific so call an external hook.
        this_step, step_words = genStepExternalHook("var", "file_prefix", "file_name","params", "works_ready_to_dispatch", "prep_success", this_step)
        psk_words = psk_words + step_words

        # now screen candidates


        # now turn candidates into internal bots/agents
        this_step, step_words = genStepECBDeleteBots("botJsons", "newBots", "layoff_success", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end skill", "public/win_chrome_ecb_home/hr_layoff", "", this_step)
        psk_words = psk_words + step_words

        psk_words = psk_words + "\"dummy\" : \"\"}"
        # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genWinChromeECBHrLayoffSkill: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genWinChromeECBHrLayoffSkill: {ex_stat}")

    return this_step, psk_words
