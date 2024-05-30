
from basicSkill import *
from amzBuyerSkill import *
from etsySellerSkill import *
from ebaySellerSkill import *
from fileSkill import *
from rarSkill import *
from labelSkill import *
from wifiSkill import *
from printLabel import *
from envi import *
import os
import traceback
from Logger import *

ecb_data_homepath = getECBotDataHome()

PUBLIC = {
    'genStepHeader': genStepHeader,
    'genStepOpenApp': genStepOpenApp,
    'genStepSaveHtml': genStepSaveHtml,
    'genStepExtractInfo': genStepExtractInfo,
    'genStepFillRecipients': genStepFillRecipients,
    'genStepSearchAnchorInfo': genStepSearchAnchorInfo,
    'genStepSearchWordLine': genStepSearchWordLine,
    'genStepSearchScroll': genStepSearchScroll,
    'genStepRecordTxtLineLocation': genStepRecordTxtLineLocation,
    'genStepMouseClick': genStepMouseClick,
    'genStepKeyInput': genStepKeyInput,
    'genStepTextInput': genStepTextInput,
    'genStepCheckCondition': genStepCheckCondition,
    'genStepGoto': genStepGoto,
    'genStepLoop': genStepLoop,
    'genStepStub': genStepStub,
    'genStepListDir': genStepListDir,
    'genStepCheckExistence': genStepCheckExistence,
    'genStepCreateDir': genStepCreateDir,
    'genStep7z': genStep7z,
    'genStepTextToNumber': genStepTextToNumber,
    'genStepEndException': genStepEndException,
    'genStepExceptionHandler': genStepExceptionHandler,
    'genStepWait': genStepWait,
    'genStepCallExtern': genStepCallExtern,
    'genStepCallFunction': genStepCallFunction,
    'genStepReturn': genStepReturn,
    'genStepUseSkill': genStepUseSkill,
    'genStepOverloadSkill': genStepOverloadSkill,
    'genStepCreateData': genStepCreateData,
    'genStepCheckAppRunning': genStepCheckAppRunning,
    'genStepBringAppToFront': genStepBringAppToFront,
    'genStepFillData': genStepFillData,
    'genStepThink': genStepThink,
    'genException': genException,
    'genWinChromeEtsyCollectOrderListSkill': genWinChromeEtsyCollectOrderListSkill,
    'genStepEtsySearchOrders': genStepEtsySearchOrders,
    'genWinChromeEtsyUpdateShipmentTrackingSkill': genWinChromeEtsyUpdateShipmentTrackingSkill,
    'genWinEtsyHandleReturnSkill': genWinEtsyHandleReturnSkill,
    'combine_duplicates': combine_duplicates,
    'createLabelOrderFile': createLabelOrderFile,
    'genStepEtsyScrapeOrders': genStepEtsyScrapeOrders,
    'genWinRARLocalUnzipSkill': genWinRARLocalUnzipSkill,
    'genStepPrintLabels': genStepPrintLabels,
    'genWinFileLocalOpenSaveSkill': genWinFileLocalOpenSaveSkill,
    'genWinADSEbayFullfillOrdersSkill': genWinADSEbayFullfillOrdersSkill,
    'genWinADSEbayCollectOrderListSkill': genWinADSEbayCollectOrderListSkill,
    'genWinADSEbayUpdateShipmentTrackingSkill': genWinADSEbayUpdateShipmentTrackingSkill,
    'genStepEbayScrapeOrdersHtml': genStepEbayScrapeOrdersHtml,
    'genStepSetupADS': genStepSetupADS,
    'genWinADSOpenProfileSkill': genWinADSOpenProfileSkill,
    'genWinADSRemoveProfilesSkill': genWinADSRemoveProfilesSkill,
    'genWinADSBatchImportSkill': genWinADSBatchImportSkill,
    'genADSLoadAmzHomePage': genADSLoadAmzHomePage,
    'genADSPowerConnectProxy': genADSPowerConnectProxy,
    'genADSPowerExitProfileSteps': genADSPowerExitProfileSteps,
    'genADSPowerLaunchSteps': genADSPowerLaunchSteps,
    'genWinChromeAMZWalkSkill': genWinChromeAMZWalkSkill,
    'genWinADSAMZWalkSkill': genWinADSAMZWalkSkill,
    'genAMZScrollProductListToBottom': genAMZScrollProductListToBottom,
    'genAMZScrollProductListToTop': genAMZScrollProductListToTop,
    'genAMZScrollProductDetailsToTop': genAMZScrollProductDetailsToTop,
    'genStepAMZMatchProduct': genStepAMZMatchProduct,
    'genAMZBrowseProductListToBottom': genAMZBrowseProductListToBottom,
    'genAMZBrowseProductListToLastAttention': genAMZBrowseProductListToLastAttention,
    'genAMZBrowseDetails': genAMZBrowseDetails,
    'genAMZBrowseAllReviewsPage': genAMZBrowseAllReviewsPage,
    'genScroll1StarReviewsPage': genScroll1StarReviewsPage,
    'genStepAMZScrapePLHtml': genStepAMZScrapePLHtml,
    'genAMZBrowseProductLists': genAMZBrowseProductLists,
    'genWinChromeAMZWalkSteps': genWinChromeAMZWalkSteps,
    'genStepAMZScrapeDetailsHtml': genStepAMZScrapeDetailsHtml,
    'genStepAMZScrapeReviewsHtml': genStepAMZScrapeReviewsHtml,
    'genStepAMZSearchProducts': genStepAMZSearchProducts,
    'genStepReportToBoss': genStepReportToBoss,
    'genStepUpdateBotADSProfileFromSavedBatchTxt': genStepUpdateBotADSProfileFromSavedBatchTxt,
    'genWinPrinterLocalReformatPrintSkill': genWinPrinterLocalReformatPrintSkill
}


SkillGeneratorTable = {
    "win_chrome_amz_home_browse_search": lambda x,y,z: genWinChromeAMZWalkSkill(x, y, z),
    "win_chrome_amz_orders_fullfill_orders": lambda x,y,z: genWinChromeAMZFullfillOrdersSkill(x, y, z),
    "win_chrome_amz_orders_collect_orders": lambda x,y,z: genWinChromeAMZCollectOrdersSkill(x, y, z),
    "win_chrome_amz_orders_update_tracking": lambda x,y,z: genWinChromeAMZUpdateShipmentTrackingSkill(x, y, z),
    "win_chrome_amz_orders_handle_messages": lambda x,y,z: genWinChromeAMZHandleMessagesSkill(x, y, z),
    # "win_ads_amz_home_browse_search": lambda x,y,z: genStubWinADSAMZWalkSkill(x, y, z),
    "win_ads_amz_home_browse_search": lambda x, y, z: genWinADSAMZWalkSkill(x, y, z),
    "win_ads_amz_home_buy_product": lambda x, y, z: genWinADSAMZBuySkill(x, y, z),
    "win_ads_ebay_orders_fullfill_orders": lambda x,y,z: genWinADSEbayFullfillOrdersSkill(x, y, z),
    "win_ads_ebay_orders_collect_orders": lambda x, y, z: genWinADSEbayCollectOrderListSkill(x, y, z),
    "win_ads_ebay_orders_update_tracking": lambda x, y, z: genWinADSEbayUpdateShipmentTrackingSkill(x, y, z),
    "win_chrome_ebay_orders_fullfill_orders": lambda x, y, z: genWinChromeEbayFullfillOrdersSkill(x, y, z),
    "win_chrome_ebay_orders_collect_orders": lambda x, y, z: genWinChromeEbayCollectOrderListSkill(x, y, z),
    "win_chrome_ebay_orders_update_tracking": lambda x, y, z: genWinChromeEbayUpdateShipmentTrackingSkill(x, y, z),
    "win_chrome_ebay_orders_handle_messages": lambda x, y, z: genWinChromeEbayHandleMessagesSkill(x, y, z),
    "win_ads_local_open_open_profile": lambda x,y,z: genWinADSOpenProfileSkill(x, y, z),
    "win_ads_local_load_batch_import": lambda x,y,z: genWinADSBatchImportSkill(x, y, z),
    "win_chrome_etsy_orders_fullfill_orders": lambda x,y,z: genWinChromeEtsyFullfillOrdersSkill(x, y, z),
    "win_chrome_etsy_orders_collect_orders": lambda x,y,z: genWinChromeEtsyCollectOrderListSkill(x, y, z),
    "win_chrome_etsy_orders_update_tracking": lambda x,y,z: genWinChromeEtsyUpdateShipmentTrackingSkill(x, y, z),
    "win_chrome_etay_orders_handle_messages": lambda x, y, z: genWinChromeEtsyHandleMessagesSkill(x, y, z),
    "win_ads_etsy_orders_fullfill_orders": lambda x, y, z: genWinADSEtsyFullfillOrdersSkill(x, y, z),
    "win_ads_etsy_orders_collect_orders": lambda x, y, z: genWinADSEtsyCollectOrderListSkill(x, y, z),
    "win_ads_etsy_orders_update_tracking": lambda x, y, z: genWinADSEtsyUpdateShipmentTrackingSkill(x, y, z),
    "win_file_local_op_open_save_as": lambda x,y,z: genWinFileLocalOpenSaveSkill(x, y, z),
    "win_printer_local_print_reformat_print": lambda x,y,z: genWinPrinterLocalReformatPrintSkill(x, y, z),
    "win_rar_local_unzip_unzip_archive": lambda x,y,z: genWinRARLocalUnzipSkill(x, y, z),
    "win_wifi_local_list_reconnect_lan": lambda x,y,z: genWinWiFiLocalReconnectLanSkill(x, y, z),
    "win_test_local_loop_run_simple_loop": lambda x,y,z: genTestRunSimpleLoopSkill(x, y, z)
}



# locate the correct mission to work on....
def getWorkSettings(lieutenant, bot_works):
    works = bot_works["works"]
    tz = bot_works["current tz"]
    grp = bot_works["current grp"]
    bidx = bot_works["current bidx"]  # buy task index
    widx = bot_works["current widx"]  # walk task index
    oidx = bot_works["current oidx"]  # other task index
    if grp == "other_works":
        idx = oidx
    else:
        idx = widx

    log3("works:"+json.dumps(works))
    log3("tz: "+tz+"grp: "+grp+"bidx: "+str(bidx)+"widx: "+str(widx)+"oidx: "+str(oidx)+"idx: "+str(idx))

    log3("bot_works: "+json.dumps(bot_works))
    mission_id = works[tz][bidx][grp][idx]["mid"]
    midx = next((i for i, mission in enumerate(lieutenant.missions) if str(mission.getMid()) == str(mission_id)), -1)

    log3("MissionIDs:"+json.dumps([m.getMid() for m in lieutenant.missions]))

    if midx < 0 or midx >= len(lieutenant.missions):
        log3("ERROR: Designated Mission " + str(mission_id) + "(out of " + str(len(lieutenant.missions)) + " missions) not found!!!!")

    log3("mission_id: "+str(mission_id)+"midx: "+str(midx))
    # get parent settings which contains tokens to allow the machine to communicate with cloud side.
    # settings = lieutenant.missions[midx].getParentSettings()
    platform = lieutenant.missions[midx].getPlatform()
    site = lieutenant.missions[midx].getSite()
    app = lieutenant.missions[midx].getApp()
    app_exe = lieutenant.missions[midx].getAppExe()
    # log3("settings: "+json.dumps(settings))

    rpa_name = works[tz][bidx][grp][idx]["name"]
    m_status = works[tz][bidx][grp][idx]["status"]

    # cargs = lieutenant.skills[skidx].getAppArgs()

    bot_id = works[tz][bidx]["bid"]
    log3("bot_id: "+str(bot_id))

    inventory = lieutenant.getBotsInventory(bot_id)
    if inventory:
        products = []
        for p in inventory.getProducts():
            products.append(p.genJson())
    else:
        log3("no inventory found")
        products = []

    # for b in lieutenant.bots:
    #     log3("BID:", b.getBid())
    bot_idx = next((i for i, bot in enumerate(lieutenant.bots) if str(bot.getBid()) == str(bot_id)), -1)
    if bot_idx < 0 or bot_idx >= len(lieutenant.bots):
        log3("ERROR: Designated BOT " + str(bot_id) + "(out of "+str(len(lieutenant.bots))+" bots) not found!!!!")
    log3("bot_idx: "+str(bot_idx))


    name_space = "B" + str(bot_id) + "M" + str(mission_id) + "!" + "" + "!"

    run_config = works[tz][bidx][grp][idx]["config"]
    root_path = lieutenant.homepath

    dtnow = datetime.now()

    date_word = dtnow.strftime("%Y%m%d")
    log3("date word:"+date_word)
    fdir = ecb_data_homepath.replace("\\", "/")
    fdir = fdir + "/runlogs/" + date_word + "/"
    log_path_prefix = fdir + "b" + str(bot_id) + "m" + str(mission_id) + "/"

    bot = lieutenant.bots[bot_idx]

    #create seller information json for seller related work in case
    sij = {
        "No": "1",
        "FromName": bot.getName(),
        "PhoneFrom": bot.getPhone(),
        "Address1From": bot.getAddrStreet1(),
        "CompanyFrom": "",
        "Address2From": bot.getAddrStreet2(),
        "CityFrom": bot.getAddrCity(),
        "StateFrom": bot.getAddrState(),
        "ZipCodeFrom": bot.getAddrZip()
    }

    return {
            "skname": "",
            "skfname": "",
            "cargs": "",
            # "works": works,
            "botid": bot_id,
            "seller": sij,
            "mid": mission_id,
            "midx": midx,
            "run_config": run_config,
            "root_path": root_path,
            "log_path_prefix": log_path_prefix,
            "log_path": "",
            # "settings": settings,
            "platform": platform,
            "site": site,
            "app": app,
            "app_exe": app_exe,
            "page": "",
            "products": products,
            "rpa_name": rpa_name,
            "m_status": m_status,
            "wifis" : lieutenant.getWifis(),
            "options": "{}",
            "name_space": name_space
            }

def getWorkRunSettings(lieutenant, bot_works):
    works = bot_works["works"]
    widx = bot_works["current widx"]  # walk task index

    log3("works:"+json.dumps(works))
    log3("widx: "+str(widx)+" mid:"+str(works[widx]["mid"]))

    log3("bot_works: "+json.dumps(works[widx]))
    mission_id = works[widx]["mid"]
    midx = next((i for i, mission in enumerate(lieutenant.missions) if str(mission.getMid()) == str(mission_id)), -1)
    log3("MissionIDs:"+json.dumps([m.getMid() for m in lieutenant.missions])+" midx:"+str(midx))

    if midx < 0 or midx >= len(lieutenant.missions):
        log3("ERROR: Designated Mission " + str(mission_id) + "(out of " + str(len(lieutenant.missions)) + " missions) not found!!!!")

    log3("mission_id: "+str(mission_id)+"midx: "+str(midx))
    # get parent settings which contains tokens to allow the machine to communicate with cloud side.
    # settings = lieutenant.missions[midx].getParentSettings()
    platform = lieutenant.missions[midx].getPlatform()
    site = lieutenant.missions[midx].getSite()
    full_site = lieutenant.missions[midx].getSiteHTML()
    app = lieutenant.missions[midx].getApp()
    app_exe = lieutenant.missions[midx].getAppExe()
    log3("settings setting app_exe: "+app+app_exe+platform+site)

    rpa_name = works[widx]["name"]
    # m_status = works[widx]["status"]

    # cargs = lieutenant.skills[skidx].getAppArgs()

    bot_id = works[widx]["bid"]
    log3("bot_id: "+str(bot_id))

    inventory = lieutenant.getBotsInventory(bot_id)
    if inventory:
        products = []
        for p in inventory.getProducts():
            products.append(p.genJson())
    else:
        log3("no inventory found")
        products = []

    # for b in lieutenant.bots:
    #     log3("BID:"+str(b.getBid()))
    bot_idx = next((i for i, bot in enumerate(lieutenant.bots) if str(bot.getBid()) == str(bot_id)), -1)
    if bot_idx < 0 or bot_idx >= len(lieutenant.bots):
        log3("ERROR: Designated BOT " + str(bot_id) + "(out of "+str(len(lieutenant.bots))+" bots) not found!!!!")
    log3("bot_idx: "+str(bot_idx))


    name_space = "B" + str(bot_id) + "M" + str(mission_id) + "!" + "" + "!"

    run_config = works[widx]["config"]
    root_path = lieutenant.homepath

    dtnow = datetime.now()

    date_word = dtnow.strftime("%Y%m%d")
    log3("date word:"+date_word)
    fdir = ecb_data_homepath.replace("\\", "/")
    fdir = fdir + "/runlogs/" + date_word + "/"
    log_path_prefix = fdir + "b" + str(bot_id) + "m" + str(mission_id) + "/"

    bot = lieutenant.bots[bot_idx]

    #create seller information json for seller related work in case
    sij = {
        "No": "1",
        "FromName": bot.getName(),
        "PhoneFrom": bot.getPhone(),
        "Address1From": bot.getAddrStreet1(),
        "CompanyFrom": "",
        "Address2From": bot.getAddrStreet2(),
        "CityFrom": bot.getAddrCity(),
        "StateFrom": bot.getAddrState(),
        "ZipCodeFrom": bot.getAddrZip()
    }

    return {
            "skname": "",
            "skfname": "",
            "cargs": "",
            # "works": works,
            "botid": bot_id,
            "b_email": bot.getEmail(),
            "b_email_pw": bot.getEmPW(),
            "b_backup_email": bot.getBackEm(),
            "b_backup_email_pw": bot.getAcctPw(),
            "b_backup_email_site": bot.getBackEmSite(),
            "batch_profile": works[widx]["ads_xlsx_profile"],
            "full_site": full_site,
            "seller": sij,
            "mid": mission_id,
            "midx": midx,
            "run_config": run_config,
            "root_path": root_path,
            "log_path_prefix": log_path_prefix,
            "log_path": "",
            # "settings": settings,
            "platform": platform,
            "site": site,
            "app": app,
            "app_exe": app_exe,
            "page": "",
            "products": products,
            "rpa_name": rpa_name,
            # "m_status": m_status,
            "wifis" : lieutenant.getWifis(),
            "options": "{}",
            "self_ip": lieutenant.ip,
            "machine_name": lieutenant.machine_name,
            # "commander_link": lieutenant.commanderXport,
            "name_space": name_space
            }

# set skill related setting items in worksettings.
def setWorkSettingsSkill(worksettings, sk):
    # derive full path skill file name.
    log3(">>>>>>>getting psk file name:"+sk.getPskFileName())
    worksettings["skfname"] = worksettings["root_path"] + "" + sk.getPskFileName()
    worksettings["platform"] = sk.getPlatform()
    worksettings["app"] = sk.getApp()
    # worksettings["app_exe"] = sk.getAppLink()

    worksettings["site"] = sk.getSiteName()

    worksettings["page"] = sk.getPage()
    log3("settings skill app_exe: "+worksettings["app_exe"]+" "+worksettings["app"]+" "+worksettings["platform"]+" "+worksettings["site"]+" "+worksettings["page"])

    worksettings["skname"] = os.path.basename(sk.getName())
    log3("GENERATING STEPS into: "+" "+worksettings["skfname"]+" "+"  skill name: "+" "+worksettings["skname"])

    worksettings["log_path"] = worksettings["log_path_prefix"] + worksettings["platform"] + "_" + worksettings["app"] + "_" + worksettings["site"] + "_" + worksettings["page"] + "/skills/" + worksettings["skname"] + "/"
    log3("LOG PATH: "+" "+worksettings["log_path"])
    pas = sk.getNameSapcePrefix()

    worksettings["name_space"] = "B" + str(worksettings["botid"]) + "M" + str(worksettings["mid"]) + "!" + pas + "!" + worksettings["skname"] + "!"

    worksettings["cargs"] = sk.getAppArgs()

# generate pubilc skills on windows platform.
def genSkillCode(sk_full_name, privacy, root_path, start_step, theme):
    this_step = start_step
    sk_parts = sk_full_name.split("_")
    sk_prefix = "_".join(sk_parts[:4])
    sk_name = "_".join(sk_parts[4:])
    log3("sk_prefix"+" "+sk_prefix+" "+"sk_name: "+sk_name)
    if privacy == "public":
        sk_file_name = root_path + "/resource/skills/public/" + sk_prefix+"/"+sk_name+".psk"
    else:
        sk_file_name = ecb_data_homepath + "/my_skills/" + sk_prefix + "/" + sk_name + ".psk"

    sk_file_dir = os.path.dirname(sk_file_name)
    os.makedirs(sk_file_dir, exist_ok=True)

    log3("sk_file_dir"+sk_file_dir+" sk_full_name: "+sk_full_name)
    log3("opening skill file: "+sk_file_name+" start_step: "+json.dumps(start_step))

    try:
        if sk_full_name in SkillGeneratorTable.keys():
            if privacy == "public":
                this_step, step_words = SkillGeneratorTable[sk_full_name](None, start_step, theme)
            else:
                log3("gen private.....")
                this_step, step_words = SkillGeneratorTable[sk_full_name](None, start_step, theme, PUBLIC)

            with open(sk_file_name, 'w+') as skf:
                skf.write("\n")
                psk_words = ""

                psk_words = psk_words + step_words

                # generate addresses for all subroutines.
                # log3("DEBUG", "Created PSK: " + psk_words)

                skf.write(psk_words)
                skf.close()
        else:
            log3("Private Skill: "+sk_full_name)
            # for private skill, skill are build locally, psk should have been there, but for safety, regenerate if missing.
            # regenerate should be from a .skd (skill diagram file), or alternatively, execute private .py file which uses
            # python script to generate PSK file.

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)

        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            file_name, line_number, _, _ = traceback_info[-1]

            # log3 the file name and line number
            ex_stat = "ErrorWritePSK:" + file_name + " " + str(line_number) + " " + str(e)
        else:
            ex_stat = "ErrorWritePSK traceback information not available"

        log3(ex_stat)

    return this_step, sk_file_name


# generate pubilc skills on Mac platform.
def genMacSkillCode(worksettings, start_step, theme):
    log3("No Mac Skills Found.")

def genLinuxSkillCode(worksettings, start_step, theme):
    log3("No Linux Skills Found.")

def genChromeOSSkillCode(worksettings, start_step, theme):
    log3("No ChromeOS Skills Found.")




def genWinTestSkill(worksettings, start_step):
    skf = open(worksettings["skfname"], "w")
    skf.write("\n")

    psk_words = "{"
    this_step, step_words = genStepHeader("test skill", "win", "1.0", "AIPPS LLC", "PUBWINADSAMZ0000001", "test skill for Windows.", start_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "counter1", "NA", 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "tresult", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCallFunction("doubler", "counter1", "tresult", this_step)
    this_step, step_words = genStepUseSkill("doubler", "", "counter1", "tresult", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global tresult\nprint('tresut....',tresult)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "test skill", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepStub("start function", "doubler", "", this_step)
    this_step, step_words = genStepStub("start skill", "doubler", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global fin, dout\nprint('fin....',fin)\ndout = fin * 2", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepReturn("dout", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "doubler", "dout", this_step)
    psk_words = psk_words + step_words

    # generate exceptino code, must have.... and this must be at the final step of skill.
    this_step, step_words = genException()
    psk_words = psk_words + step_words

    # generate addresses for all subroutines.
    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "ready to add stubs...." + psk_words)

    skf.write(psk_words)
    skf.close()


def genWinTestSkill1(worksettings, start_step):
    skf = open(worksettings["skfname"], "w")
    skf.write("\n")

    psk_words = "{"
    this_step, step_words = genStepHeader("test_skill1", "win", "1.0", "AIPPS LLC", "PUBWINADSAMZ0000001", "test skill for Windows.", start_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepStub("start function", "doubler", "", this_step)
    this_step, step_words = genStepStub("start skill", "test_skill1", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "counter1", "NA", 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "tresult", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCallFunction("doubler", "counter1", "tresult", this_step)
    this_step, step_words = genStepUseSkill("doubler", "", "counter1", "tresult", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global tresult\nprint('tresut....',tresult)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "test skill", "", this_step)
    psk_words = psk_words + step_words


    # generate exceptino code, must have.... and this must be at the final step of skill.
    this_step, step_words = genException()
    psk_words = psk_words + step_words

    # generate addresses for all subroutines.
    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "ready to add stubs...." + psk_words)

    skf.write(psk_words)
    skf.close()

def genWinTestSkill2(worksettings, start_step):
    skf = open(worksettings["skfname"], "w")
    skf.write("\n")

    psk_words = "{"
    this_step, step_words = genStepHeader("doubler", "win", "1.0", "AIPPS LLC", "PUBWINADSAMZ0000001", "test skill for Windows.", start_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepStub("start function", "doubler", "", this_step)
    this_step, step_words = genStepStub("start skill", "doubler", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global fin, dout\nprint('fin....',fin)\ndout = fin * 2", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepReturn("dout", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "doubler", "dout", this_step)
    psk_words = psk_words + step_words

    # generate exceptino code, must have.... and this must be at the final step of skill.
    this_step, step_words = genException()
    psk_words = psk_words + step_words

    # generate addresses for all subroutines.
    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "ready to add stubs...." + psk_words)

    skf.write(psk_words)
    skf.close()


def genTestRunSimpleLoopSkill(worksettings, stepN, theme):

    psk_words = "{"

    this_step, step_words = genStepHeader("win_test_local_run_simple_loop", "win", "1.0", "AIPPS LLC", "PUBWINTESTOP001",
                                          "Simple Loop Test On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_test_local_loop/run_simple_loop", "", this_step)
    psk_words = psk_words + step_words


    # delete everything there
    # do some overall review scroll, should be mostly positive.
    lcvarname = "test" + str(stepN)
    this_step, step_words = genStepCreateData("int", lcvarname, "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("", "15", "", lcvarname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(2, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_test_local_loop/run_simple_loop", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # log3("DEBUG", "generated skill for windows loop test...." + psk_words)

    return this_step, psk_words