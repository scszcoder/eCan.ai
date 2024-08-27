from datetime import datetime
from bot.envi import getECBotDataHome
import os
import asyncio

# con = sqlite3.connect("mylog.db")
# cur = con.cursor()
# res = cur.execute("CREATE TABLE runHis(action, bid, mid)")
# con.commit()
# cur.executemany()
#
# sql_statement = "INSERT INTO *** VALUES (), (), ()"
# sql_statement = "SELECT score, abc FROM movies ORDER BY year"
#
# res.fetchone()
# res.fetchall()
# res.fetchmany()
# con.close()


LOG_SWITCH_BOARD = {
    "all": {"log": True, "range": "lan"},
    "processHalt": {"log": False, "range": "lan"},
    "processDone": {"log": False, "range": "lan"},
    "processWait": {"log": False, "range": "lan"},
    "processExtractInfo": {"log": True, "range": "lan"},
    "processExtractInfo8": {"log": True, "range": "lan"},
    "processFillRecipients": {"log": False, "range": "lan"},
    "processTextInput": {"log": False, "range": "wan"},
    "processMouseClick": {"log": True, "range": "wan"},
    "processMouseScroll": {"log": True, "range": "wan"},
    "processKeyInput": {"log": True, "range": "wan"},
    "processOpenApp": {"log": True, "range": "wan"},
    "processCreateData": {"log": False, "range": "lan"},
    "processTextToNumber": {"log": False, "range": "lan"},
    "processFillData": {"log": False, "range": "lan"},
    "processEndException": {"log": False, "range": "lan"},
    "processExceptionHandler": {"log": False, "range": "lan"},
    "processCheckCondition": {"log": False, "range": "lan"},
    "processRepeat": {"log": False, "range": "lan"},
    "processLoadData": {"log": False, "range": "lan"},
    "processSaveData": {"log": False, "range": "lan"},
    "processCallExtern": {"log": False, "range": "lan"},
    "processCallExtern8": {"log": False, "range": "lan"},
    "processUseSkill": {"log": True, "range": "lan"},
    "processUseExternalSkill": {"log": False, "range": "lan"},
    "processReportExternalSkillRunStatus": {"log": False, "range": "lan"},
    "processOverloadSkill": {"log": False, "range": "lan"},
    "processCallFunction": {"log": False, "range": "lan"},
    "processReturn": {"log": False, "range": "lan"},
    "processStub": {"log": False, "range": "lan"},
    "processGoto": {"log": False, "range": "lan"},
    "processListDir": {"log": False, "range": "lan"},
    "processCheckExistence": {"log": False, "range": "lan"},
    "processCreateDir": {"log": False, "range": "lan"},
    "processReadFile": {"log": False, "range": "lan"},
    "processWriteFile": {"log": False, "range": "lan"},
    "processDeleteFile": {"log": False, "range": "lan"},
    "processObtainReviews": {"log": True, "range": "lan"},
    "process7z": {"log": True, "range": "lan"},
    "processSearchAnchorInfo": {"log": False, "range": "lan"},
    "processSearchWordLine": {"log": False, "range": "lan"},
    "processSearchScroll": {"log": True, "range": "lan"},
    "processScrollToLocation": {"log": False, "range": "lan"},
    "processSaveHtml": {"log": False, "range": "lan"},
    "processCheckAppRunning": {"log": False, "range": "lan"},
    "processBringAppToFront": {"log": False, "range": "lan"},
    "processThink": {"log": True, "range": "lan"},
    "processThink8": {"log": True, "range": "lan"},
    "processGenRespMsg": {"log": False, "range": "lan"},
    "processUpdateBuyMissionResult": {"log": False, "range": "lan"},
    "processSellCheckShipping": {"log": False, "range": "lan"},
    "processGoToWindow": {"log": True, "range": "lan"},
    "processReportToBoss": {"log": False, "range": "lan"},
    "processCalcObjectsDistance": {"log": False, "range": "lan"},
    "processAmzDetailsCheckPosition": {"log": False, "range": "lan"},
    "processAmzPLCalcNCols": {"log": False, "range": "lan"},
    "processMoveDownloadedFileToDestination": {"log": False, "range": "lan"},
    "processReqHumanInLoop": {"log": True, "range": "lan"},
    "processCloseHumanInLoop": {"log": True, "range": "lan"},
    "processReadJsonFile": {"log": False, "range": "lan"},
    "processReadXlsxFile": {"log": False, "range": "lan"},
    "processGetDefault": {"log": False, "range": "lan"},


    "processWebdriverClick": {"log": True, "range": "wan"},
    "processWebdriverStartExistingChrome": {"log": False, "range": "lan"},
    "processWebdriverStartNewChrome": {"log": False, "range": "lan"},
    "processWebdriverStartExistingADS": {"log": False, "range": "lan"},
    "processWebdriverScrollTo": {"log": True, "range": "wan"},
    "processWebdriverKeyIn": {"log": True, "range": "wan"},
    "processWebdriverComboKeys": {"log": True, "range": "wan"},
    "processWebdriverSelectDropDown": {"log": True, "range": "wan"},
    "processWebdriverNewTab": {"log": False, "range": "lan"},
    "processWebdriverCloseTab": {"log": True, "range": "lan"},
    "processWebdriverGoToTab": {"log": True, "range": "lan"},
    "processWebdriverRefreshPage": {"log": True, "range": "lan"},
    "processWebdriverBack": {"log": False, "range": "lan"},
    "processWebdriverForward": {"log": False, "range": "lan"},
    "processWebdriverHoverTo": {"log": False, "range": "lan"},
    "processWebdriverScreenShot": {"log": False, "range": "lan"},
    "processWebdriverFocus": {"log": False, "range": "lan"},
    "processWebdriverExecuteJs": {"log": True, "range": "lan"},
    "processWebdriverExtractInfo": {"log": False, "range": "lan"},
    "processWebdriverWaitUntilClickable": {"log": False, "range": "lan"},
    "processWebdriverSwitchToDefaultContent": {"log": False, "range": "lan"},
    "processWebdriverSwitchToFrame": {"log": True, "range": "lan"},
    "processWebdriverWaitForVisibility": {"log": False, "range": "lan"},
    "processWebdriverQuit": {"log": False, "range": "lan"},
    "processWebdriverWaitDownloadDoneAndTransfer": {"log": True, "range": "lan"},

    "processEbayScrapeOrdersFromHtml": {"log": True, "range": "lan"},
    "processEbayScrapeOrdersFromJss": {"log": True, "range": "lan"},
    "processEbayScrapeMsgList": {"log": True, "range": "lan"},
    "processEbayScrapeCustomerMsgThread": {"log": True, "range": "lan"},

    "processPrepareGSOrder": {"log": True, "range": "lan"},
    "processGSExtractZippedFileName": {"log": True, "range": "lan"},

    "dailySkillsetUpdate": {"log": True, "range": "lan"},
    "fetchSchedule": {"log": True, "range": "wan"},
    "checkNextToRun": {"log": True, "range": "wan"},
    "mainwinInit": {"log": True, "range": "lan"},
    "mainGUI": {"log": True, "range": "lan"},
    "TrainGUI": {"log": True, "range": "lan"},
    "skillGUI": {"log": True, "range": "lan"},
    "botGUI": {"log": True, "range": "lan"},
    "missionGUI": {"log": True, "range": "lan"},

    "serveCommander": {"log": True, "range": "lan"},
    "runAllSteps": {"log": True, "range": "lan"},
    "servePlatoons": {"log": True, "range": "lan"},
    "assignWork": {"log": True, "range": "lan"},
    "runbotworks": {"log": True, "range": "wan"}

}

# from utils.logger_helper import login
import utils.logger_helper
def getLogUser():
    global login
    return login.getCurrentUser().split(".")[0].replace("@", "_")
# log messages into console, file, and GUI
def log3(msg, mask='all', log_user='anonymous', gui_main=None, range='lan'):
    log_enabled = False
    wan_enabled = False
    if mask in LOG_SWITCH_BOARD:
        if LOG_SWITCH_BOARD[mask]["log"]:
            log_enabled = True
        if LOG_SWITCH_BOARD[mask]["range"] == "wan" and gui_main:
            wan_enabled = True

    if log_enabled:
        ecb_data_homepath = getECBotDataHome()
        now = datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        if gui_main:
            log_user = gui_main.log_user
        else:
            # global login
            if utils.logger_helper.login:
                log_user = utils.logger_helper.login.getLogUser()
                print("LOG USER:" + log_user)
            else:
                print("NO LOG USER")

        dailyLogDir = ecb_data_homepath + "/{}/runlogs/{}/{}".format(log_user, log_user, year)
        dailyLogFile = ecb_data_homepath + "/{}/runlogs/{}/{}/log{}{}{}.txt".format(log_user, log_user, year, year, month, day)
        time = now.strftime("%H:%M:%S - ")
        if os.path.isfile(dailyLogFile):
            file1 = open(dailyLogFile, "a", encoding='utf-8')  # append mode

            file1.write(time + msg + "\n")
            file1.close()
        else:
            if not os.path.exists(dailyLogDir):
                os.makedirs(dailyLogDir)

            file1 = open(dailyLogFile, "w", encoding='utf-8')  # append mode

            file1.write(time + msg + "\n")
            file1.close()

        # read details from the page.
        print(msg)

        if gui_main:
            gui_main.appendNetLogs([msg])

        if wan_enabled:
            gui_main.wan_send_log((":<mlog>"+msg+"</mlog>"))

async def log4(msg, mask='all', log_user='anonymous', gui_main=None, range='lan'):
    log_enabled = False
    wan_enabled = False
    if mask in LOG_SWITCH_BOARD:
        if LOG_SWITCH_BOARD[mask]["log"]:
            log_enabled = True
        if LOG_SWITCH_BOARD[mask]["range"] == "wan" and gui_main:
            wan_enabled = True

    if log_enabled:
        ecb_data_homepath = getECBotDataHome()
        now = datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        if gui_main:
            log_user = gui_main.log_user
        dailyLogDir = ecb_data_homepath + "/{}/runlogs/{}/{}".format(log_user, log_user, year)
        dailyLogFile = ecb_data_homepath + "/{}/runlogs/{}/{}/log{}{}{}.txt".format(log_user, log_user, year, year, month, day)
        time = now.strftime("%H:%M:%S - ")
        if os.path.isfile(dailyLogFile):
            file1 = open(dailyLogFile, "a", encoding='utf-8')  # append mode

            file1.write(time + msg + "\n")
            file1.close()
        else:
            if not os.path.exists(dailyLogDir):
                os.makedirs(dailyLogDir)

            file1 = open(dailyLogFile, "w", encoding='utf-8')  # append mode

            file1.write(time + msg + "\n")
            file1.close()

        # read details from the page.
        print(msg)

        if gui_main:
            gui_main.appendNetLogs([msg])

        if wan_enabled:
            loop = asyncio.get_event_loop()
            await gui_main.wan_send_log8((":<mlog>"+msg+"</mlog>"))
        #     # loop.run_until_complete(gui_main.gui_monitor_msg_queue.put((":<wanlog>"+msg+"</wanlog>")))
        #     # asyncio.ensure_future(gui_main.wan_send_log((":<mlog>"+msg+"</mlog>")))


def log2file(msg, category='None', mask='None', file='None'):
    # read details from the page.
    if file == 'None':
        print(msg)
    else:
        file1 = open(file, "a")
        print(msg)
        file1.write(msg)
        file1.close()


def getLogMasks():
    return LOG_SWITCH_BOARD.keys()

def setLogMask(mask, log_flag, lan_wan):
    LOG_SWITCH_BOARD[mask]["log"] = log_flag
    LOG_SWITCH_BOARD[mask]["range"] = lan_wan
    if mask == "all":
        for key in LOG_SWITCH_BOARD:
            LOG_SWITCH_BOARD[key]["log"] = log_flag
            LOG_SWITCH_BOARD[key]["range"] = lan_wan