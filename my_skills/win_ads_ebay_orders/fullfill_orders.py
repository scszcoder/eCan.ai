


def genMyWinADSEbayFullfillOrdersSkill(worksettings, stepN, theme, pubSkills):
    psk_words = "{"

    this_step, step_words = pubSkills["genStepHeader"]("win_ads_ebay_fullfill_orders_my", "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY001",
                                          "Ebay Fullfill New Orders On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepStub"]("start skill main", "my_skills/win_ads_ebay_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepWait"](2, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("string", "ebay_status", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("expr", "product_book", "NA", "sk_work_settings['products']", this_step)
    psk_words = psk_words + step_words

    # mask out for testing purpose only....
    this_step, step_words = pubSkills["genStepCreateData"]("expr", "ebay_orders", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("expr", "dummy_in", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("int", "scroll_resolution", "NA", 253, this_step)
    psk_words = psk_words + step_words

     # hard default exe path code here just for testing purpose, eventually will be from input or settings....
    this_step, step_words = pubSkills["genStepCreateData"]("str", "sevenZExe", "NA", 'C:/Program Files/7-Zip/7z.exe', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("str", "rarExe", "NA", 'C:/Program Files/WinRaR/WinRaR.exe', this_step)
    psk_words = psk_words + step_words


    this_step, step_words = pubSkills["genStepCreateData"]("expr", "open_profile_input", "NA", "[sk_work_settings['batch_profile']]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("int", "scroll_resolution", "NA", 250, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("int", "retry_count", "NA", 5, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("bool", "mission_failed", "NA", False, this_step)
    psk_words = psk_words + step_words

    # first call subskill to open ADS Power App, and check whether the user profile is already loaded?
    this_step, step_words = pubSkills["genStepUseSkill"]("open_profile", "public/win_ads_local_open", "open_profile_input", "ads_up", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepWait"](1, 0, 0, this_step)
    psk_words = psk_words + step_words

    # now check the to be run bot's profile is already loaded, do this by examine whether bot's email appears on the ads page.
    # scroll down half screen and check again if nothing found in the 1st glance.
    this_step, step_words = pubSkills["genStepCreateData"]("expr", "bot_email", "NA", "sk_work_settings['b_email'].split('@')[0]+'@'", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("expr", "bemail", "NA", "sk_work_settings['b_email']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("expr", "bpassword", "NA", "sk_work_settings['b_backup_email_pw']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepSearchWordLine"]("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepSearchAnchorInfo"]("screen_info", "no_data", "direct", "anchor text", "any", "useless", "nothing_loaded", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCheckCondition"]("not bot_loaded and not nothing_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    # if not on screen, scroll down and check again.
    this_step, step_words = pubSkills["genStepMouseScroll"]("Scroll Down", "screen_info", 80, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepExtractInfo"]("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepSearchWordLine"]("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepSearchAnchorInfo"]("screen_info", "no_data", "direct", "anchor text", "any", "useless", "nothing_loaded", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepStub"]("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # if not found, call the batch load profile subskill to load the correct profile batch.
    this_step, step_words = pubSkills["genStepCheckCondition"]("not bot_loaded", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("expr", "profile_name", "NA", "os.path.basename(sk_work_settings['batch_profile'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("expr", "profile_name_path", "NA", "os.path.dirname(sk_work_settings['batch_profile'])", this_step)
    psk_words = psk_words + step_words

    # due to screen real-estate, some long email address might not be dispalyed in full, but usually
    # it can display up until @ char on screen, so only use this as the tag.
    this_step, step_words = pubSkills["genStepCreateData"]("expr", "bot_email", "NA", "sk_work_settings['b_email'].split('@')[0]+'@'", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("expr", "full_site", "NA", "sk_work_settings['full_site'].split('www.')[1]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("expr", "machine_os", "NA", "sk_work_settings['platform']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCreateData"]("expr", "batch_import_input", "NA", "['open', profile_name_path, profile_name, bot_email, full_site, machine_os]", this_step)
    psk_words = psk_words + step_words

    # once the correct user profile is loaded, the open button corresponding to the user profile will be clicked to open the profile.
    this_step, step_words = pubSkills["genStepUseSkill"]("batch_import", "public/win_ads_local_load", "batch_import_input", "browser_up", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepStub"]("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCallExtern"]("global dyn_options\ndyn_options = {'anchors': [{'anchor_name': 'bot_user', 'anchor_type': 'text', 'template': bot_email, 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'bot_open', 'anchor_type': 'text', 'template': 'Open', 'ref_method': '1', 'ref_location': [{'ref': 'bot_user', 'side': 'right', 'dir': '>', 'offset': '1', 'offset_unit': 'box'}]}], 'attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepExtractInfo"]("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None, "dyn_options")
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepMouseClick"]("Single Click", " ", True, "screen_info", "bot_open", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepStub"]("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # wait 9 seconds for the browser to be brought up.
    this_step, step_words = pubSkills["genStepWait"](8, 1, 3, this_step)
    psk_words = psk_words + step_words

    # following is for tests purpose. hijack the flow, go directly to browse....
    this_step, step_words = pubSkills["genStepGoToWindow"]("SunBrowser", "", "g2w_status", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genEbayLoginInSteps"](this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepCheckCondition"]("not_logged_in == False", "", "", this_step)
    psk_words = psk_words + step_words

    # skname, skfname, in-args, output, step number
    this_step, step_words = pubSkills["genStepUseSkill"]("collect_orders", "public/win_ads_ebay_orders", "dummy_in", "ebay_orders", this_step)
    psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.
    # first organized order list data into 2 xls for bulk label purchase, and calcualte total funding requird for this action.

    #
    # using ebay to purchase shipping label will auto update tracking code..... s
    this_step, step_words = pubSkills["genStepUseSkill"]("buy_shipping", "public/win_ads_ebay_orders", "ebay_orders", "labels_dir", this_step)
    psk_words = psk_words + step_words

    # # extract tracking code from labels and update them into etsy_orders data struture.
    #
    # # gen_etsy_test_data()
    #
    # # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]
    # # now update tracking coded back to the orderlist
    # this_step, step_words = pubSkills["genStepUseSkill"]("update_tracking", "public/win_ads_ebay_orders", "gs_input", "total_label_cost", this_step)
    # psk_words = psk_words + step_words
    #
    this_step, step_words = pubSkills["genStepCreateData"]("expr", "reformat_print_input", "NA", "['one page', 'label_dir', printer_name]", this_step)
    psk_words = psk_words + step_words

    # # now reformat and print out the shipping labels, label_list contains a list of { "orig": label pdf files, "output": outfilename, "note", note}
    this_step, step_words = pubSkills["genStepUseSkill"]("reformat_print", "public/win_printer_local_print", "label_dir", "", this_step)
    psk_words = psk_words + step_words
    #
    # end condition for "not_logged_in == False"
    this_step, step_words = pubSkills["genStepStub"]("end condition", "", "", this_step)
    psk_words = psk_words + step_words
    #
    # # close the browser and exit the skill, assuming at the end of genWinChromeEBAYWalkSteps, the browser tab
    # # should return to top of the ebay home page with the search text box cleared.
    # this_step, step_words = pubSkills["genStepKeyInput"]("", True, "alt,f4", "", 3, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = pubSkills["genStepCheckCondition"]("mission_failed == False", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = pubSkills["genStepGoToWindow"]("AdsPower", "", "g2w_status", this_step)
    # psk_words = psk_words + step_words
    #
    # # in case mission executed successfully, save profile, kind of an overkill or save all profiles, but simple to do.
    # this_step, step_words = pubSkills["genADSPowerExitProfileSteps"](worksettings, this_step, theme)
    # psk_words = psk_words + step_words
    #
    # # end condition for "not_logged_in == False"
    # this_step, step_words = pubSkills["genStepStub"]("end condition", "", "", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = pubSkills["genStepStub"]("end skill", "my_skills/win_ads_ebay_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words
    print("generating win ads ebay skill")
    psk_words = psk_words + "\"dummy\" : \"\"}"
    pubSkills["log3"]("DEBUG", "generated skill for windows ebay order fullfill operation using GS label provider...." + psk_words)

    return this_step, psk_words