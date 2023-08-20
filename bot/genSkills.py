
from basicSkill import *
from amzBuyerSkill import *
from etsySellerSkill import *
from ebaySellerSkill import *
from fileSkill import *
from rarSkill import *
from labelSkill import *
from wifiSkill import *

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
    midx = next((i for i, mission in enumerate(lieutenant.missions) if mission.getMid() == mission_id), -1)

    print("mission_id: ", mission_id, "midx: ", midx)
    # get parent settings which contains tokens to allow the machine to communicate with cloud side.
    settings = lieutenant.missions[midx].getParentSettings()
    platform = lieutenant.missions[midx].getPlatform()
    site = lieutenant.missions[midx].getSite()
    app = lieutenant.missions[midx].getApp()
    app_exe = lieutenant.missions[midx].getAppExe()
    print("settings: ", settings)

    rpaConfig = works[tz][bidx][grp][idx]["config"]
    rpaName = works[tz][bidx][grp][idx]["name"]

    # required_skids = lieutenant.missions[works[tz][bidx][grp][idx]["mid"]].getSkills()
    # print("mission required skill IDs: ", required_skids)
    #
    # print("number of skills loade: ", len(lieutenant.skills))
    # print("first skill id: ", lieutenant.skills[0].getSkid())
    # iidx = (i for i, sk in enumerate(lieutenant.skills) if i >= 0)
    # print("is: ", iidx)
    #
    # # use skill ID to find the index of the skill among the list of skills.
    # skidx = next((i for i, sk in enumerate(lieutenant.skills) if sk.getSkid() == required_skids[0]), -1)
    # print("skidx: ", skidx)
    #
    # # derive full path skill file name.
    # skfname = lieutenant.homepath + "/" + lieutenant.skills[skidx].getPskFileName()
    #
    # skname = os.path.basename(lieutenant.skills[skidx].getName())
    # print("GENERATING STEPS into: ", skfname, "  skill name: ", skname)
    #
    # cargs = lieutenant.skills[skidx].getAppArgs()

    bot_id = works[tz][bidx]["bid"]
    bot_idx = next((i for i, bot in enumerate(lieutenant.bots) if bot.getBid() == bot_id), -1)


    name_space = "B" + str(bot_id) + "M" + str(mission_id) + "!" + "" + "!"

    run_config = works[tz][bidx][grp][idx]["config"]
    root_path = lieutenant.homepath

    return {
            "skname": "",
            "skfname": "",
            "cargs": "",
            "works": works,
            "botid": bot_id,
            "bot": lieutenant.bots[bot_idx],
            "mid": mission_id,
            "midx": midx,
            "run_config": run_config,
            "root_path": root_path,
            "settings": settings,
            "platform": platform,
            "site": site,
            "app": app,
            "app_exe": app_exe,
            "rpaConfig": rpaConfig,
            "rpaName": rpaName,
            "name_space": name_space
            }

def setWorkSettingsSkill(worksettings, sk):
    # derive full path skill file name.
    worksettings["skfname"] = worksettings["root_path"] + "/" + sk.getPskFileName()

    worksettings["skname"] = os.path.basename(sk.getName())
    print("GENERATING STEPS into: ", worksettings["skfname"], "  skill name: ", worksettings["skname"])

    worksettings["name_space"] = "B" + str(worksettings["botid"]) + "M" + str(worksettings["mid"]) + "!" + worksettings["skname"] + "!"

    worksettings["cargs"] = sk.getAppArgs()


def genWinSkillCode(worksettings, start_step, theme):

    skf = open(worksettings["skfname"], "w")
    skf.write("\n")

    psk_words = "{"
    # create header section.
    if worksettings["app"] == "ads" and worksettings["site"] == "amz" and worksettings["rpaName"] == "walk_routine":
        this_step, step_words = genStepHeader(worksettings["skname"], "win", "1.0", "AIPPS LLC", "PUBWINADSAMZ0000001",
                                                       "Walk skill on amazon with ADSPower for Windows.", start_step)
        site_url = "https://www.amazon.com"
    elif worksettings["app"] == "chrome" and worksettings["site"] == "amz" and worksettings["rpaName"] == "walk_routine":
        this_step, step_words = genStepHeader(worksettings["skname"], "win", "1.0", "AIPPS LLC", "PUBWINCHROMEAMZ0000001",
                                                       "Walk skill on amazon with Chrome for Windows.", start_step)
        site_url = "https://www.amazon.com"
    elif worksettings["app"] == "ads" and worksettings["site"] == "ebay" and worksettings["rpaName"] == "sell":
        this_step, step_words = genStepHeader(worksettings["skname"], "win", "1.0", "AIPPS LLC", "PUBWINADSEBAY0000001",
                                                       "sell skill on ebay with Chrome for Windows.", start_step)
        site_url = "https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT"
    elif worksettings["app"] == "chrome" and worksettings["site"] == "etsy" and worksettings["rpaName"] == "sell":
        this_step, step_words = genStepHeader(worksettings["skname"], "win", "1.0", "AIPPS LLC", "PUBWINCHROMEETSY0000001",
                                                       "sell skill on etsy with Chrome for Windows.", start_step)
        site_url = "https://www.etsy.com/your/orders/sold"
    elif worksettings["app"] == "chrome" and worksettings["site"] == "ebay" and worksettings["rpaName"] == "sell":
        this_step, step_words = genStepHeader(worksettings["skname"], "win", "1.0", "AIPPS LLC", "PUBWINCHROMEEBAY0000001",
                                                       "sell skill on ebay with Chrome for Windows.", start_step)
        site_url = "https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT"

    psk_words = psk_words + step_words

    this_step, step_words = genStepOpenApp("cmd", True, "browser", site_url, "", "", worksettings["cargs"], 5, this_step)
    psk_words = psk_words + step_words


    if worksettings["app"] == "ads" and worksettings["site"] == "amz" and worksettings["rpaName"] == "walk_routine":
        this_step, step_words = genWinADSAMZWalkSkill(worksettings, this_step, theme)
    elif worksettings["app"] == "chrome" and worksettings["site"] == "amz" and worksettings["rpaName"] == "walk_routine":
        this_step, step_words = genWinChromeAMZWalkSkill(worksettings, this_step, theme)
    elif worksettings["app"] == "ads" and worksettings["site"] == "ebay" and worksettings["rpaName"] == "sell":
        this_step, step_words = genWinEbayHandleOrderSkill(worksettings, "ebay_orders", "top", this_step, theme)
    elif worksettings["app"] == "chrome" and worksettings["site"] == "etsy" and worksettings["rpaName"] == "sell":
        this_step, step_words = genWinChromeEtsyFullfillOrdersSkill(worksettings, "etsy_orders", "top", this_step, theme)
    elif worksettings["app"] == "rar" and worksettings["site"] == "local" and worksettings["rpaName"] == "zip_unzip_archive":
        this_step, step_words = genWinRARLocalUnzipSkill(worksettings, "winrar", "top", this_step, theme)
    elif worksettings["app"] == "ads" and worksettings["site"] == "local" and worksettings["rpaName"] == "open_profile":
        this_step, step_words = genWinADSOpenSkill(worksettings, "file_dialog", "top", this_step, theme)
    elif worksettings["app"] == "ads" and worksettings["site"] == "local" and worksettings["rpaName"] == "batch_import_xls":
        this_step, step_words = genWinADSBatchImportSkill(worksettings, "file_dialog", "top", this_step, theme)
    elif worksettings["app"] == "file" and worksettings["site"] == "local" and worksettings["rpaName"] == "open":
        this_step, step_words = genWinFileLocalOpenSaveSkill(worksettings, "file_dialog", "top", this_step, theme)
    elif worksettings["app"] == "wifi" and worksettings["site"] == "local" and worksettings["rpaName"] == "reconnect_lan":
        this_step, step_words = genWinWiFiLocalReconnectLanSkill(worksettings, "wifi", "top", this_step, theme)
    else:
        this_step, step_words = genWinCustomSkill(worksettings, "custom", "top", this_step, theme)

    psk_words = psk_words + step_words

    # finally handle the purchase, if there is any.
    # if len(run_config["purchases"]) > 0:
    #     # purchase could be done in multiple days usually (put in cart first, then finish payment in a few days)
    #     this_step, step_words = genPurchase(run_config)
    #     psk_words = psk_words + step_words

    # generate exceptino code, must have.... and this must be at the final step of skill.
    # this_step, step_words = genException()
    # psk_words = psk_words + step_words

    # generate addresses for all subroutines.
    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "ready to add stubs...." + psk_words)

    skf.write(psk_words)
    skf.close()

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
