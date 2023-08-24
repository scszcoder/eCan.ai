from basicSkill import *


def genWinWiFiLocalReconnectLanSkill(worksettings, page, sect, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_wifi_all_op", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001",
                                          "File Open Dialog Handling for Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_wifi_local_list/reconnect_lan", "", this_step)
    psk_words = psk_words + step_words

    # extract screen info,
    this_step, step_words = genStepExtractInfo("", worksettings["root_path"], "screen_info", "all_reviews", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["free_trial_ended"], ["anchor text"], "any", "useless", "rar_trial_end_popped", "amz", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Wifi", "anchor icon", "", [0, 0], "center", [0, 0], "pixel", 2, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings["root_path"], "screen_info", "all_reviews", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["free_trial_ended"], ["anchor text"], "any", "useless", "rar_trial_end_popped", "amz", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Wifi_List", "anchor icon", "", [0, 0], "center", [0, 0], "pixel", 2, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings["root_path"], "screen_info", "all_reviews", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", worksettings["wifis"], ["anchor text"], "any", "useless", "wifi_found", "win", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Disconnect", "anchor icon", "Disconnect", [0, 0], "center", [0, 0], "pixel", 1, 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings["root_path"], "screen_info", "all_reviews", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", worksettings["wifis"], ["anchor text"], "any", "useless", "wifi_found", "win", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Connect", "anchor text", "Connect", [0, 0], "center", [0, 0], "pixel", 1, 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_wifi_local_list/reconnect_lan", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words
