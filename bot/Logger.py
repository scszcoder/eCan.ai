from datetime import datetime
from bot.envi import getECBotDataHome
import os
import asyncio
import traceback
from app_context import AppContext

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
    "all": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processHalt": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processDone": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWait": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processExtractInfo": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processExtractInfo8": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processFillRecipients": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processTextInput": {"log": False, "py_console": True, "win_console": True, "range": "wan"},
    "processMouseClick": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "processMouseScroll": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "processKeyInput": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "processOpenApp": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "processCreateData": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processTextToNumber": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processFillData": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processEndException": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processExceptionHandler": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processCheckCondition": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processRepeat": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processLoadData": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processSaveData": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processCallExtern": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processCallExtern8": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processUseSkill": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processUseExternalSkill": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processReportExternalSkillRunStatus": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processOverloadSkill": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processCallFunction": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processReturn": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processStub": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processGoto": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processListDir": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processCheckExistence": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processCreateDir": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processReadFile": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWriteFile": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processDeleteFile": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processObtainReviews": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "process7z": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processSearchAnchorInfo": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processSearchWordLine": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processSearchScroll": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processScrollToLocation": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processSaveHtml": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processCheckAppRunning": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processBringAppToFront": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processThink": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processThink8": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processGenRespMsg": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processUpdateBuyMissionResult": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processSellCheckShipping": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processGoToWindow": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processReportToBoss": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processCalcObjectsDistance": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processAmzDetailsCheckPosition": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processAmzPLCalcNCols": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processMoveDownloadedFileToDestination": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processReqHumanInLoop": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processCloseHumanInLoop": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processReadJsonFile": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processReadXlsxFile": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processGetDefault": {"log": False, "py_console": True, "win_console": True, "range": "lan"},

    "wanSendMessage": {"log": False, "py_console": False, "win_console": False, "range": "lan"},
    "processWebdriverClick": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "processWebdriverStartExistingChrome": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverStartNewChrome": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverStartExistingADS": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverScrollTo": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "processWebdriverKeyIn": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "processWebdriverComboKeys": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "processWebdriverSelectDropDown": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "processWebdriverNewTab": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverCloseTab": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverGoToTab": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverRefreshPage": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverBack": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverForward": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverHoverTo": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverScreenShot": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverFocus": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverExecuteJs": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverExtractInfo": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverWaitUntilClickable": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverSwitchToDefaultContent": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverSwitchToFrame": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverWaitForVisibility": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverQuit": {"log": False, "py_console": True, "win_console": True, "range": "lan"},
    "processWebdriverWaitDownloadDoneAndTransfer": {"log": True, "py_console": True, "win_console": True, "range": "lan"},

    "processEbayScrapeOrdersFromHtml": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processEbayScrapeOrdersFromJss": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processEbayScrapeMsgList": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processEbayScrapeCustomerMsgThread": {"log": True, "py_console": True, "win_console": True, "range": "lan"},

    "processPrepareGSOrder": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "processGSExtractZippedFileName": {"log": True, "py_console": True, "win_console": True, "range": "lan"},

    "dailySkillsetUpdate": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "fetchSchedule": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "checkNextToRun": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "mainwinInit": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "mainGUI": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "TrainGUI": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "skillGUI": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "botGUI": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "missionGUI": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "gen_addresses": {"log": True, "py_console": False, "win_console": False, "range": "lan"},
    "formADSProfileBatchesFor1Vehicle": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "updateIndividualProfileFromBatchSavedTxt": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "genAdsProfileBatchs": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "serveCommander": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "rpaRunAllSteps": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "servePlatoons": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "assignWork": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "gatherFingerPrints": {"log": True, "py_console": True, "win_console": True, "range": "lan"},
    "runbotworks": {"log": True, "py_console": True, "win_console": True, "range": "wan"},
    "runmanagerworks": {"log": True, "py_console": True, "win_console": True, "range": "wan"}
}

def getLogUser():
    global login
    return login.getCurrentUser().split(".")[0].replace("@", "_")
# log messages into console, file, and GUI

def formatLogMessage(msg):
    return f'<span style="color: blue;">{msg}</span>'


def log2File(gui_main, msg):
    ecb_data_homepath = getECBotDataHome()
    now = datetime.now()  # current date and time
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    if gui_main:
        log_user = gui_main.log_user
    else:
        # global login
        if AppContext.login:
            log_user = AppContext.login.getLogUser()
            # print("LOG USER:" + log_user)
        else:
            log_user = "anonymous"

    dailyLogDir = ecb_data_homepath + "/{}/runlogs/{}/{}".format(log_user, log_user, year)
    dailyLogFile = ecb_data_homepath + "/{}/runlogs/{}/{}/log{}{}{}.txt".format(log_user, log_user, year, year, month,
                                                                                day)
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

def log3(msg, mask='all', gui_main=None):
    try:
        if gui_main:
            log_switches = gui_main.log_settings
        else:
            log_switches = LOG_SWITCH_BOARD

        file_log_enabled = False
        py_console_log_enabled = False
        win_console_log_enabled = False
        wan_enabled = False

        log_flags = log_switches.get(mask, {"log": False, "py_console": False, "win_console": True, "range": "lan"})
        # print("log_flags:", mask, log_flags)
        if log_flags["log"]:
            file_log_enabled = True

        if log_flags["py_console"]:
            py_console_log_enabled = True

        if log_flags["win_console"]:
            win_console_log_enabled = True

        if log_flags["range"] == "wan" and gui_main:
            wan_enabled = True



        if file_log_enabled:
            log2File(gui_main, msg)

        # read details from the page.
        if py_console_log_enabled:
            print(msg)

        if win_console_log_enabled and gui_main:
            gui_main.appendNetLogs([formatLogMessage(msg)])

        # if wan_enabled:
        #     gui_main.wan_send_log((":<mlog>"+msg+"</mlog>"))

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLog3:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLog3: traceback information not available:" + str(e)
        log2File(gui_main, ex_stat)

# this is super log with local log + 2 types remote log method, it will send message thru LAN(commander) and WAN(staff officer).
def log6(msg, mask='all', gui_main=None, mission=None, stepIdx=0, msgType="Action"):
    if gui_main:
        log_switches = gui_main.log_settings
    else:
        log_switches = LOG_SWITCH_BOARD

    log_enabled = False
    wan_enabled = True
    if mask in log_switches:
        if log_switches[mask]["log"]:
            log_enabled = True
        if log_switches[mask]["range"] == "wan" and gui_main:
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
        # print("log6 msg:", msg)
        # forming a "|"separated string for remote monitoring...
        if gui_main:
            gui_main.appendNetLogs([msg])
            if mission:
                mid = mission.getMid()
                bid = mission.getBid()
            else:
                mid = 0
                bid = 0
            wanMsg = gui_main.machine_name + ":" + gui_main.os_short + "|" + gui_main.log_user + "|"
            wanMsg = wanMsg + "M" + str(mid) + "|" + "B" + str(bid) + "|"
            wanMsg = wanMsg + "S-" + str(stepIdx) + "-" + gui_main.working_state + "|" + msgType + "|"
            wanMsg = wanMsg + msg


            if wan_enabled:
                # loop = asyncio.get_event_loop()
                #
                ek = gui_main.generate_key_from_string(gui_main.main_key)
                encryptedWanMsg = gui_main.encrypt_string(ek, wanMsg)
                gui_main.wan_send_log((encryptedWanMsg))

            # send to commander as well
            runlog = {"type": "runLog", "ip": gui_main.ip, "content": wanMsg}
            # gui_main.send_json_to_commander(gui_main.commanderXport, runlog)

        #     # loop.run_until_complete(gui_main.gui_monitor_msg_queue.put((":<wanlog>"+msg+"</wanlog>")))
        #     # asyncio.ensure_future(gui_main.wan_send_log((":<mlog>"+msg+"</mlog>")))


async def log68(msg, mask='all', gui_main=None, mission=None, stepIdx=0, msgType="Action"):
    log_enabled = False
    wan_enabled = True
    if gui_main:
        log_switches = gui_main.log_settings
    else:
        log_switches = LOG_SWITCH_BOARD

    if mask in log_switches:
        if log_switches[mask]["log"]:
            log_enabled = True
        if log_switches[mask]["range"] == "wan" and gui_main:
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
        # forming a "|"separated string for remote monitoring...
        if gui_main:
            gui_main.appendNetLogs([msg])
            if mission:
                mid = mission.getMid()
                bid = mission.getBid()
            else:
                mid = 0
                bid = 0
            wanMsg = gui_main.machine_name + ":" + gui_main.os_short + "|" + gui_main.log_user + "|"
            wanMsg = wanMsg + "M" + str(mid) + "|" + "B" + str(bid) + "|"
            wanMsg = wanMsg + "S-" + str(stepIdx) + "-" + gui_main.working_state + "|" + msgType + "|"
            wanMsg = wanMsg + msg


            if wan_enabled:
                loop = asyncio.get_event_loop()
                #
                ek = gui_main.generate_key_from_string(gui_main.main_key)
                encryptedWanMsg = gui_main.encrypt_string(ek, wanMsg)
                await gui_main.wan_send_log8((encryptedWanMsg))

            # send to commander as well
            runlog = {"type": "runLog", "ip": gui_main.ip, "content": wanMsg}
            # await gui_main.send_json_to_commander8(gui_main.commanderXport, runlog)

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