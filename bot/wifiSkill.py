from bot.basicSkill import genStepHeader, genStepStub, genStepCreateData, genStepExtractInfo, genStepSearchAnchorInfo, \
    genStepMouseClick, genStepCallExtern
from bot.Logger import log3


def genWinWiFiLocalReconnectLanSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_wifi_all_op", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001",
                                          "File Open Dialog Handling for Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_wifi_local_list/reconnect_lan", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global scrn_options\nscrn_options = {'txt_attention_area':[0, 0, 1, 1], 'icon_attention_area':[0, 0, 1, 1], 'attention_targets':['@all']}\nprint('scrn_options', scrn_options)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # extract screen info,
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "all_reviews", "top", theme, stepN, None, "scrn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["free_trial_ended"], "direct", ["anchor text"], "any", "useless", "rar_trial_end_popped", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Wifi", "anchor icon", "", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global scrn_options\nscrn_options = {'txt_attention_area':[0, 0, 1, 1], 'icon_attention_area':[0, 0, 1, 1], 'attention_targets':['New Profile', 'Profiles', 'No Data', 'All groups']}\nprint('scrn_options', scrn_options)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "all_reviews", "top", theme, stepN, None, "scrn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["free_trial_ended"], "direct", ["anchor text"], "any", "useless", "rar_trial_end_popped", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Wifi_List", "anchor icon", "", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern(
        "global scrn_options\nscrn_options = {'txt_attention_area':[0, 0, 1, 1], 'icon_attention_area':[0, 0, 1, 1], 'attention_targets':['New Profile', 'Profiles', 'No Data', 'All groups']}\nprint('scrn_options', scrn_options)",
        "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "all_reviews", "top", theme, stepN, None, "scrn_options")
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "sk_work_settings['wifis']", "expr", ["anchor text"], "any", "useless", "wifi_found", "win", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Disconnect", "anchor icon", "Disconnect", [0, 0], "center", [0, 0], "pixel", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "all_reviews", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "sk_work_settings['wifis']", "expr", ["anchor text"], "any", "useless", "wifi_found", "win", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Connect", "anchor text", "Connect", [0, 0], "center", [0, 0], "pixel", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_wifi_local_list/reconnect_lan", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words
