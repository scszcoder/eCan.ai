
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

ecb_data_homepath = getECBotDataHome()
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

    print("works:", works)
    print("tz: ", tz, "grp: ", grp, "bidx: ", bidx, "widx: ", widx, "oidx: ", oidx, "idx: ", idx)

    print("bot_works: ", bot_works)
    mission_id = works[tz][bidx][grp][idx]["mid"]
    midx = next((i for i, mission in enumerate(lieutenant.missions) if str(mission.getMid()) == mission_id), -1)
    for m in lieutenant.missions:
        print("MissionIDs:", m.getMid())
    if midx < 0 or midx >= len(lieutenant.missions):
        print("ERROR: Designated Mission " + str(mission_id) + "(out of " + str(len(lieutenant.missions)) + " missions) not found!!!!")

    print("mission_id: ", mission_id, "midx: ", midx)
    # get parent settings which contains tokens to allow the machine to communicate with cloud side.
    # settings = lieutenant.missions[midx].getParentSettings()
    platform = lieutenant.missions[midx].getPlatform()
    site = lieutenant.missions[midx].getSite()
    app = lieutenant.missions[midx].getApp()
    app_exe = lieutenant.missions[midx].getAppExe()
    # print("settings: ", settings)

    rpaName = works[tz][bidx][grp][idx]["name"]

    # cargs = lieutenant.skills[skidx].getAppArgs()

    bot_id = works[tz][bidx]["bid"]
    print("bot_id: ", bot_id)

    inventory = lieutenant.getBotsInventory(bot_id)
    if inventory:
        products = []
        for p in inventory.getProducts():
            products.append(p.genJson())
    else:
        print("no inventory found")
        products = []

    for b in lieutenant.bots:
        print("BID:", b.getBid())
    bot_idx = next((i for i, bot in enumerate(lieutenant.bots) if str(bot.getBid()) == str(bot_id)), -1)
    if bot_idx < 0 or bot_idx >= len(lieutenant.bots):
        print("ERROR: Designated BOT " + str(bot_id) + "(out of "+str(len(lieutenant.bots))+" bots) not found!!!!")
    print("bot_idx: ", bot_idx)


    name_space = "B" + str(bot_id) + "M" + str(mission_id) + "!" + "" + "!"

    run_config = works[tz][bidx][grp][idx]["config"]
    root_path = lieutenant.home_path

    dtnow = datetime.now()

    date_word = dtnow.strftime("%Y%m%d")
    print("date word:", date_word)

    fdir = ecb_data_homepath + "/runlogs/" + date_word + "/"
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
            "rpaName": rpaName,
            "wifis" : lieutenant.getWifis(),
            "options": "{}",
            "name_space": name_space
            }


# set skill related setting items in worksettings.
def setWorkSettingsSkill(worksettings, sk):
    # derive full path skill file name.
    print(">>>>>>>getting psk file name:", sk.getPskFileName())
    worksettings["skfname"] = worksettings["root_path"] + "/" + sk.getPskFileName()
    worksettings["platform"] = sk.getPlatform()
    worksettings["app"] = sk.getApp()
    worksettings["app_exe"] = sk.getAppLink()
    worksettings["site"] = sk.getSiteName()

    worksettings["page"] = sk.getPage()

    worksettings["skname"] = os.path.basename(sk.getName())
    print("GENERATING STEPS into: ", worksettings["skfname"], "  skill name: ", worksettings["skname"])

    worksettings["log_path"] = worksettings["log_path_prefix"] + worksettings["platform"] + "_" + worksettings["app"] + "_" + worksettings["site"] + "_" + worksettings["page"] + "/skills/" + worksettings["skname"] + "/"
    print("LOG PATH: ", worksettings["log_path"])
    pas = sk.getNameSapcePrefix()

    worksettings["name_space"] = "B" + str(worksettings["botid"]) + "M" + str(worksettings["mid"]) + "!" + pas + "!" + worksettings["skname"] + "!"

    worksettings["cargs"] = sk.getAppArgs()


# generate pubilc skills on windows platform.
def genWinSkillCode(worksettings, start_step, theme):
    print("opening skill file: ", worksettings["skfname"], worksettings["app"], worksettings["site"])
    skf = open(worksettings["skfname"], "w+")
    skf.write("\n")
    psk_words = ""

    if worksettings["app"] == "ads" and worksettings["site"] == "amz" and worksettings["skname"] == "browse_search":
        this_step, step_words = genWinADSAMZWalkSkill(worksettings, start_step, theme)
    elif worksettings["app"] == "chrome" and worksettings["site"] == "amz" and worksettings["skname"] == "browse_search":
        this_step, step_words = genWinChromeAMZWalkSkill(worksettings, start_step, theme)
    elif worksettings["app"] == "ads" and worksettings["site"] == "ebay" and worksettings["skname"] == "sell":
        this_step, step_words = genWinEbayHandleOrderSkill(worksettings, start_step, theme)
    elif worksettings["app"] == "chrome" and worksettings["site"] == "etsy" and worksettings["skname"] == "fullfill_orders":
        this_step, step_words = genWinChromeEtsyFullfillOrdersSkill(worksettings, "orders", "top", start_step, theme)
    elif worksettings["app"] == "chrome" and worksettings["site"] == "etsy" and worksettings["skname"] == "collect_orders":
        this_step, step_words = genWinEtsyCollectOrderListSkill(worksettings, "orders", "top", start_step, theme)
    elif worksettings["app"] == "chrome" and worksettings["site"] == "etsy" and worksettings["skname"] == "update_tracking":
        this_step, step_words = genWinEtsyUpdateShipmentTrackingSkill(worksettings, "orders", "top", start_step, theme)
    elif worksettings["app"] == "chrome" and worksettings["site"] == "goodsupply" and worksettings["skname"] == "bulk_buy":
        this_step, step_words = genWinChromeGSLabelBulkBuySkill(worksettings, "label", "top", start_step, theme)
    elif worksettings["app"] == "rar" and worksettings["site"] == "local" and worksettings["skname"] == "unzip_archive":
        this_step, step_words = genWinRARLocalUnzipSkill(worksettings, "winrar", "top", start_step, theme)
    elif worksettings["app"] == "ads" and worksettings["site"] == "local" and worksettings["skname"] == "open_profile":
        this_step, step_words = genWinADSOpenSkill(worksettings, "file_dialog", "top", start_step, theme)
    elif worksettings["app"] == "ads" and worksettings["site"] == "local" and worksettings["skname"] == "batch_import":
        this_step, step_words = genWinADSBatchImportSkill(worksettings, "file_dialog", "top", start_step, theme)
    elif worksettings["app"] == "file" and worksettings["site"] == "local" and worksettings["skname"] == "open_save_as":
        this_step, step_words = genWinFileLocalOpenSaveSkill(worksettings, "file_dialog", "top", start_step, theme)
    elif worksettings["app"] == "printer" and worksettings["site"] == "local" and worksettings["skname"] == "reformat_print":
        this_step, step_words = genWinPrinterLocalReformatPrintSkill(worksettings, "file_dialog", "top", start_step, theme)
    elif worksettings["app"] == "wifi" and worksettings["site"] == "local" and worksettings["skname"] == "reconnect_lan":
        this_step, step_words = genWinWiFiLocalReconnectLanSkill(worksettings, "wifi", "top", start_step, theme)
    elif worksettings["app"] == "test" and worksettings["site"] == "local" and worksettings["skname"] == "run_simple_loop":
        this_step, step_words = genTestRunSimpleLoopSkill(start_step)
    else:
        this_step, step_words = genWinCustomSkill(worksettings, "custom", "top", start_step, theme)

    psk_words = psk_words + step_words


    # generate addresses for all subroutines.
    # print("DEBUG", "Created PSK: " + psk_words)

    skf.write(psk_words)
    skf.close()


# generate pubilc skills on Mac platform.
def genMacSkillCode(worksettings, start_step, theme):
    print("hello")


# nothing to return. (skname, skfname,  worksTBD, first_step, "light")
def genSkillCode(worksettings, start_step, theme):

    if worksettings["platform"] == "win":
        genWinSkillCode(worksettings, start_step, theme)
    elif worksettings["platform"] == "mac":
        genMacSkillCode(worksettings, start_step, theme)



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
    print("DEBUG", "ready to add stubs...." + psk_words)

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
    print("DEBUG", "ready to add stubs...." + psk_words)

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
    print("DEBUG", "ready to add stubs...." + psk_words)

    skf.write(psk_words)
    skf.close()


def genTestRunSimpleLoopSkill(stepN):

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
    print("DEBUG", "generated skill for windows loop test...." + psk_words)

    return this_step, psk_words