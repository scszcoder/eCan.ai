import asyncio
import inspect
import json
import os
import re
import time
from datetime import datetime
from difflib import SequenceMatcher

from basicSkill import processExternalHook
from bot.adsPowerSkill import processUpdateBotADSProfileFromSavedBatchTxt, processADSGenXlsxBatchProfiles, \
    processADSProfileBatches, processADSSaveAPISettings, processADSUpdateProfileIds
from bot.amzBuyerSkill import processAMZScrapePLHtml, processAMZBrowseDetails, \
    processAMZScrapeProductDetailsHtml, processAMZBrowseReviews, processAMZScrapeReviewsHtml, processAmzBuyCheckShipping, \
    processAMZMatchProduct, genStepAMZSearchReviews
from bot.basicSkill import symTab, processHalt, processWait, processSaveHtml, processTextToNumber, processExtractInfo, \
    processTextInput, processMouseClick, processMouseScroll, processKeyInput, processOpenApp, processCreateData, \
    processFillData, processLoadData, processSaveData, processCheckCondition, processRepeat, processGoto, \
    processCallFunction, processReturn, processUseSkill, processOverloadSkill, processStub, processCallExtern, \
    processExceptionHandler, processEndException, processSearchAnchorInfo, processSearchWordLine, processThink, \
    processFillRecipients, processSearchScroll, processScrollToLocation, process7z, processListDir, processCheckExistence, processCreateDir, \
    processSellCheckShipping, processGenRespMsg, processUpdateBuyMissionResult, processGoToWindow, processReportToBoss, \
    processExtractInfo8, DEFAULT_RUN_STATUS, WAIT_HIL_RESPONSE, p2p_distance, box_center, genStepMouseClick, genStepExtractInfo, \
    genStepWait, genStepCreateData, genStepLoop, genStepMouseScroll, genStepSearchAnchorInfo, genStepStub, \
    processCalcObjectsDistance, processAmzDetailsCheckPosition, rd_screen_count, processAmzPLCalcNCols, \
    processMoveDownloadedFileToDestination, processObtainReviews, processReqHumanInLoop, processCloseHumanInLoop,\
    processUseExternalSkill, processReportExternalSkillRunStatus, processReadJsonFile, processReadXlsxFile,\
    processGetDefault, processUploadFiles, processDownloadFiles, processWaitUntil, processZipUnzip, processReadFile, \
    processWriteFile, processDeleteFile, processWaitUntil8, processKillProcesses, processCheckAppRunning, \
    processBringAppToFront, processUpdateMissionStatus, processCheckAlreadyProcessed, processCheckSublist, \
    processPasteToData, processMouseMove, processGetWindowsInfo, processBringWindowToFront, \
    processExternalHook, processCreateRequestsSession

from bot.seleniumSkill import processWebdriverClick, processWebdriverScrollTo, processWebdriverKeyIn, processWebdriverComboKeys, \
    processWebdriverHoverTo, processWebdriverFocus, processWebdriverSelectDropDown, processWebdriverBack, \
    processWebdriverForward, processWebdriverGoToTab, processWebdriverNewTab, processWebdriverCloseTab, processWebdriverQuit, \
    processWebdriverExecuteJs, processWebdriverRefreshPage, processWebdriverScreenShot, processWebdriverStartExistingChrome, \
    processWebdriverStartExistingADS, processWebdriverStartNewChrome, processWebdriverExtractInfo, \
    processWebdriverWaitUntilClickable, processWebdriverWaitDownloadDoneAndTransfer, \
    processWebdriverWaitForVisibility, processWebdriverSwitchToFrame, processWebdriverSwitchToDefaultContent, \
    processWebdriverCheckConnection, processWebdriverCheckVisibility, processWebdriverGetValueFromWebElement
from bot.Logger import log3
from bot.etsySellerSkill import processEtsyGetOrderClickedStatus, processEtsySetOrderClickedStatus, \
    processEtsyFindScreenOrder, processEtsyRemoveAlreadyExpanded, processEtsyExtractTracking, processEtsyAddPageOfOrder, \
    processPrepGSOrder
from bot.ebaySellerSkill import processEbayGenShippingInfoFromOrderID
# from bot.browserEbaySellerSkill import process
from bot.labelSkill import processGSExtractZippedFileName, processPrepareGSOrder
from bot.printLabel import processPrintLabels
from bot.ecSkill import processGenShippingOrdersFromMsgResponses
from bot.scrapeGoodSupply import processGSScrapeLabels
from bot.scraperAmz import processAmzScrapeMsgList, processAmzScrapeCustomerMsgThread
from bot.scraperEbay import processEbayScrapeOrdersFromHtml, processEbayScrapeOrdersFromJss, processEbayScrapeMsgList, processEbayScrapeCustomerMsgThread
from bot.scraperEtsy import processEtsyScrapeOrders, processEtsyScrapeMsgLists, processEtsyScrapeMsgThread
from bot.seleniumScrapeAmz import processAMZBrowserScrapePL
from bot.envi import getECBotDataHome
import traceback

symTab["fout"] = ""
symTab["fin"] = ""
MAXNEST = 18                    # code level skill nest (skill calling skill)
MAXRECUR = 18                   # max level of recurrsion
MAXSTEPS = 2048                 # code level, maximum number of steps of any task. should never be more complicated.

nest_level = 0
steps = []
last_step = -1
next_step = 0
STEP_GAP = 5
first_step = 0
running_step_index = 0

running = False
net_connected = False
in_exception = False

sys_stack = []
exception_stack = []
breakpoints = []
skill_code = None
skill_table = {"nothing": ""}
function_table = {"nothing": ""}
skill_stack = []

hil_queue = asyncio.Queue()

# SC - 2023-03-07 files and dirs orgnization structure:
#
#     local image:  C:/Users/***/PycharmProjects/ecbot/runlogs/date/b0m0/win_chrome_amz_home/browse_search/images/scrnsongc_yahoo_1678175548.png"
#     local skill:  C:/Users/***/PycharmProjects/ecbot/resource/skills/public/win_chrome_amz_walk/scripts/skillname.psk
#

# SC - 2023-07-28 to make this instructionset extensible, make RAIS file based? if someone wants to extends the instruction set.
# simply add a file in certain DIR or add thru GUI settings section?
#
# for example, how does a customer supply its own label purchasing function? use patch scheme? create a function overload scheme? (a name to functions mapping tables of some sort)
# do we need code patch scheme?
# How to add an external skill to be called?
#

# RAIS - Robotic Automation Instruction Set
# SC 08/05/2023 - to extend this instruction set, have user create an extended IS json file, we'll reading this json file and attached it to
# the existing one., the question really is about how to run it. the user would have a .py script file that contains the function
# processXXXX itself, the question is how to make our code recognize to call extern on that???
# solution, make instruction naming convention, like starts with "EXT:", then, at our run1step function,
# whenever we see EXT: in front of the name, we use call extern instead.
# Q: how to specify the extended instruction? it should be done locally on PC, per 1 user account. should cloud know anything about it?
# A: from what we know so far, cloud has no need to know the details of the private skill.
# where should the extension IS file be? - skills/my/is_extension.json this should be read in during initialization.
# Note: this extension file as well as the custom skill should be transported to networked vehicle machines, so that they can run it too.
#        then the question Q: is how we do that? A: during initiallization the commander machine archive the skills/my dir and send to all
#        networked machines.
# the development and testing of the IS should be done in-app or separately? if in app, need GUI support, where on GUI?
# A: preferrably in app, but not high priority, initially can get by without having it in-app.
RAIS = {
    "Halt": lambda x,y: processHalt(x, y),
    "Wait": lambda x,y: processWait(x, y),
    "Wait Until": lambda x,y: processWaitUntil(x, y),
    "Save Html": lambda x,y,z,k: processSaveHtml(x, y, z, k),
    "Browse": lambda x,y: processBrowse(x, y),
    "Text To Number": lambda x,y: processTextToNumber(x, y),
    "Extract Info": lambda x,y,z,k: processExtractInfo(x, y, z, k),
    "Text Input": lambda x,y,z: processTextInput(x, y, z),
    "Mouse Click": lambda x,y,z: processMouseClick(x, y, z),
    "Mouse Scroll": lambda x,y,z: processMouseScroll(x, y, z),
    "Mouse Move": lambda x,y,z: processMouseMove(x, y, z),
    "Get Windows Info": lambda x,y: processGetWindowsInfo(x, y),
    "Bring Window To Front": lambda x,y: processBringWindowToFront(x, y),
    "Calibrate Scroll": lambda x,y: processCalibrateScroll(x, y),
    "Text Line Location Record": lambda x,y: processRecordTxtLineLocation(x, y),
    "Key Input": lambda x,y,z: processKeyInput(x, y, z),
    "App Open": lambda x,y: processOpenApp(x, y),
    "Create Data": lambda x,y: processCreateData(x, y),
    "Fill Data": lambda x,y: processFillData(x, y),
    "Load Data": lambda x,y: processLoadData(x, y),
    "Save Data": lambda x,y: processSaveData(x, y),
    "Paste To Data": lambda x,y: processPasteToData(x, y),
    "Get Default": lambda x,y: processGetDefault(x, y),
    "Check Condition": lambda x,y,z: processCheckCondition(x, y, z),
    "Repeat": lambda x,y,z: processRepeat(x, y, z),
    "Goto": lambda x,y,z: processGoto(x, y, z),
    "Call Function": lambda x,y,z,v,w: processCallFunction(x, y, z, v, w),
    "Return": lambda x,y,z,w: processReturn(x, y, z, w),
    "Use Skill": lambda x,y,z,u,v,w: processUseSkill(x, y, z, u, v, w),
    "Overload Skill": lambda x,y,z,w: processOverloadSkill(x, y, z, w),
    "Use External Skill": lambda x,y,z: processUseExternalSkill(x, y, z),
    "Report External Skill Run Status": lambda x,y,z: processReportExternalSkillRunStatus(x, y, z),
    "Stub": lambda x,y,z,u,v,w: processStub(x, y, z, u, v, w),
    "Call Extern": lambda x,y: processCallExtern(x, y),
    "Exception Handler": lambda x,y,z,w: processExceptionHandler(x, y, z, w),
    "End Exception": lambda x,y,z,w: processEndException(x, y, z, w),
    "Search Anchor Info": lambda x,y: processSearchAnchorInfo(x, y),
    "External Hook": lambda x, y: processExternalHook(x, y),
    "Create Requests Session": lambda x, y: processCreateRequestsSession(x, y),
    "Search Word Line": lambda x, y: processSearchWordLine(x, y),
    "Think": lambda x, y, z: processThink(x, y, z),
    "FillRecipients": lambda x,y: processFillRecipients(x, y),
    "Search Scroll": lambda x,y: processSearchScroll(x, y),
    "Scroll To Location": lambda x,y: processScrollToLocation(x, y),
    "Calc Objs Distance": lambda x,y: processCalcObjectsDistance(x, y),
    "Seven Zip": lambda x,y: process7z(x, y),
    "Zip Unzip": lambda x,y: processZipUnzip(x, y),
    "List Dir": lambda x, y: processListDir(x, y),
    "Check Existence": lambda x, y: processCheckExistence(x, y),
    "Create Dir": lambda x, y: processCreateDir(x, y),
    "Read File": lambda x, y: processReadFile(x, y),
    "Write File": lambda x, y: processWriteFile(x, y),
    "Delete File": lambda x, y: processDeleteFile(x, y),
    "Kill Processes": lambda x, y: processKillProcesses(x, y),
    "print Label": lambda x, y: processPrintLabels(x, y),
    "Read Json File": lambda x, y: processReadJsonFile(x, y),
    "Read Xlsx File": lambda x,y: processReadXlsxFile(x, y),
    "ADS Batch Text To Profiles": lambda x,y,z: processUpdateBotADSProfileFromSavedBatchTxt(x, y,z),
    "ADS Gen XLSX Batch Profiles": lambda x,y: processADSGenXlsxBatchProfiles(x, y),
    "ADS Save API Settings": lambda x,y,z: processADSSaveAPISettings(x, y,z),
    "ADS Update Profile Ids": lambda x,y,z: processADSUpdateProfileIds(x, y,z),
    "AMZ Search Products": lambda x,y: processAMZSearchProducts(x, y),
    "AMZ Scrape PL Html": lambda x, y, z: processAMZScrapePLHtml(x, y, z),
    "AMZ Browser Scrape Products List": lambda x, y, z: processAMZBrowserScrapePL(x, y, z),
    "AMZ Browse Details": lambda x,y: processAMZBrowseDetails(x, y),
    "AMZ Scrape Product Details Html": lambda x, y, z: processAMZScrapeProductDetailsHtml(x, y, z),
    "AMZ Scrape Buy Orders Html": lambda x, y, z: processAMZScrapeBuyOrdersHtml(x, y, z),
    "AMZ Browse Reviews": lambda x,y: processAMZBrowseReviews(x, y),
    "AMZ Scrape Reviews Html": lambda x, y, z: processAMZScrapeReviewsHtml(x, y, z),
    "AMZ Scrape Sold Orders Html": lambda x, y, z: processAMZScrapeSoldOrdersHtml(x, y, z),
    "AMZ Scrape Msg Lists": lambda x, y, z: processAmzScrapeMsgList(x, y, z),
    "AMZ Buy Check Shipping": lambda x, y: processAmzBuyCheckShipping(x, y),
    "AMZ Details Check Position": lambda x, y: processAmzDetailsCheckPosition(x, y),
    "AMZ PL Calc Columns": lambda x, y: processAmzPLCalcNCols(x, y),
    "Sell Check Shipping": lambda x, y: processSellCheckShipping(x, y),
    "AMZ Scrape Customer Msg": lambda x, y, z: processAmzScrapeCustomerMsgThread(x, y, z),
    "EBAY Scrape Orders Html": lambda x, y, z: processEbayScrapeOrdersFromHtml(x, y, z),
    "EBAY Scrape Orders Javascript": lambda x, y, z: processEbayScrapeOrdersFromJss(x, y, z),
    "EBAY Scrape Msg Lists": lambda x, y, z: processEbayScrapeMsgList(x, y, z),
    "EBAY Scrape Customer Msg": lambda x, y, z: processEbayScrapeCustomerMsgThread(x, y, z),
    "Ebay Gen Shipping From Order ID": lambda x, y: processEbayGenShippingInfoFromOrderID(x, y),
    "Gen Resp Msg": lambda x, y: processGenRespMsg(x, y),
    "ETSY Scrape Orders": lambda x, y, z: processEtsyScrapeOrders(x, y, z),
    "Etsy Get Order Clicked Status": lambda x, y: processEtsyGetOrderClickedStatus(x, y),
    "Etsy Set Order Clicked Status": lambda x, y: processEtsySetOrderClickedStatus(x, y),
    "Etsy Find Screen Order": lambda x, y: processEtsyFindScreenOrder(x, y),
    "Etsy Remove Expanded": lambda x, y: processEtsyRemoveAlreadyExpanded(x, y),
    "Etsy Extract Tracking": lambda x, y: processEtsyExtractTracking(x, y),
    "Etsy Add Page Of Order": lambda x, y: processEtsyAddPageOfOrder(x, y),
    "ETSY Scrape Msg Lists": lambda x, y, z: processEtsyScrapeMsgLists(x, y, z),
    "ETSY Scrape Msg Thread": lambda x, y, z: processEtsyScrapeMsgThread(x, y, z),
    "Create ADS Profile Batches": lambda x, y, z: processADSProfileBatches(x, y, z),
    "Update Buy Mission Result": lambda x, y, z: processUpdateBuyMissionResult(x, y, z),
    "GS Scrape Labels": lambda x, y, z: processGSScrapeLabels(x, y, z),
    "GS Extract Zipped": lambda x, y: processGSExtractZippedFileName(x, y),
    "Prep GS Order": lambda x, y: processPrepGSOrder(x, y),
    "Prepare GS Order": lambda x, y: processPrepareGSOrder(x, y),
    "AMZ Match Products": lambda x, y, z: processAMZMatchProduct(x, y, z),
    "Obtain Reviews": lambda x, y, z: processObtainReviews(x, y, z),
    "Gen Shipping From Msg Responses": lambda x,y: processGenShippingOrdersFromMsgResponses(x, y),
    "Go To Window": lambda x,y: processGoToWindow(x, y),
    "Move Downloaded File": lambda x,y: processMoveDownloadedFileToDestination(x, y),
    "Report To Boss": lambda x,y: processReportToBoss(x, y),
    "Web Driver Click": lambda x,y,z: processWebdriverClick(x, y, z),
    "Web Driver Scroll To": lambda x,y,z: processWebdriverScrollTo(x, y, z),
    "Web Driver Key In": lambda x, y,z: processWebdriverKeyIn(x, y, z),
    "Web Driver Combo Keys": lambda x,y,z: processWebdriverComboKeys(x, y, z),
    "Web Driver Hover To": lambda x,y,z: processWebdriverHoverTo(x, y, z),
    "Web Driver Focus": lambda x, y,z: processWebdriverFocus(x, y, z),
    "Web Driver Select Drop Down": lambda x, y, z: processWebdriverSelectDropDown(x, y, z),
    "Web Driver Back": lambda x, y: processWebdriverBack(x, y),
    "Web Driver Forward": lambda x, y: processWebdriverForward(x, y),
    "Web Driver Go To Tab": lambda x, y: processWebdriverGoToTab(x, y),
    "Web Driver New Tab": lambda x, y: processWebdriverNewTab(x, y),
    "Web Driver Close Tab": lambda x, y: processWebdriverCloseTab(x, y),
    "Web Driver Quit": lambda x, y: processWebdriverQuit(x, y),
    "Web Driver Execute Js": lambda x, y, z: processWebdriverExecuteJs(x, y, z),
    "Web Driver Refresh Page": lambda x, y: processWebdriverRefreshPage(x, y),
    "Web Driver Screen Shot": lambda x, y: processWebdriverScreenShot(x, y),
    "Web Driver Start Existing Chrome": lambda x, y: processWebdriverStartExistingChrome(x, y),
    "Web Driver Start Existing ADS": lambda x, y: processWebdriverStartExistingADS(x, y),
    "Web Driver Start New Chrome": lambda x, y: processWebdriverStartNewChrome(x, y),
    "Web Driver Extract Info": lambda x, y, z: processWebdriverExtractInfo(x, y, z),
    "Web Driver Wait Until Clickable": lambda x, y, z: processWebdriverWaitUntilClickable(x, y, z),
    "Web Driver Wait For Visibility": lambda x, y, z: processWebdriverWaitForVisibility(x, y, z),
    "Web Driver Switch To Frame": lambda x, y: processWebdriverSwitchToFrame(x, y),
    "Web Driver Switch To Default Content": lambda x, y: processWebdriverSwitchToDefaultContent(x, y),
    "Web Driver Wait Download Done And Transfer": lambda x, y: processWebdriverWaitDownloadDoneAndTransfer(x, y),
    "Web Driver Check Connection": lambda x, y: processWebdriverCheckConnection(x, y),
    "Web Driver Check Visibility": lambda x, y: processWebdriverCheckVisibility(x, y),
    "Web Driver Get Value": lambda x, y: processWebdriverGetValueFromWebElement(x, y),
    "Request Human In Loop": lambda x, y, z, v: processReqHumanInLoop(x, y, z, v),
    "Close Human In Loop": lambda x, y, z, v: processCloseHumanInLoop(x, y, z, v),
    "Check App Running": lambda x, y: processCheckAppRunning(x, y),
    "Bring App To Front": lambda x, y: processBringAppToFront(x, y),
    "Upload Files": lambda x, y, z: processUploadFiles(x, y, z),
    "Download Files": lambda x, y, z: processDownloadFiles(x, y, z),
    "Check Sublist": lambda x, y: processCheckSublist(x, y),
    "Check Already Processed": lambda x, y: processCheckAlreadyProcessed(x, y),
    "Update Mission Status": lambda x, y, z: processUpdateMissionStatus(x, y, z)
}

# async RAIS - this one should be used to prevent blocking GUI and other tasks.
ARAIS = {
    "Halt": lambda x,y: processHalt(x, y),
    "Wait": lambda x,y: processWait(x, y),
    # "Wait Until": lambda x,y: processWaitUntil8(x, y),
    "Wait Until": processWaitUntil8,
    "Save Html": lambda x,y,z,k: processSaveHtml(x, y, z, k),
    "Browse": lambda x,y: processBrowse(x, y),
    "Text To Number": lambda x,y: processTextToNumber(x, y),
    # "Extract Info": lambda x,y,z,k: processExtractInfo8(x, y, z, k),
    "Extract Info": processExtractInfo8,
    "Text Input": lambda x,y,z: processTextInput(x, y, z),
    "Mouse Click": lambda x,y,z: processMouseClick(x, y, z),
    "Mouse Scroll": lambda x,y,z: processMouseScroll(x, y, z),
    "Mouse Move": lambda x,y,z: processMouseMove(x, y, z),
    "Get Windows Info": lambda x, y: processGetWindowsInfo(x, y),
    "Bring Window To Front": lambda x, y: processBringWindowToFront(x, y),
    "Calibrate Scroll": lambda x,y: processCalibrateScroll(x, y),
    "Text Line Location Record": lambda x,y: processRecordTxtLineLocation(x, y),
    "Key Input": lambda x,y,z: processKeyInput(x, y, z),
    "App Open": lambda x,y: processOpenApp(x, y),
    "Create Data": lambda x,y: processCreateData(x, y),
    "Fill Data": lambda x,y: processFillData(x, y),
    "Load Data": lambda x,y: processLoadData(x, y),
    "Save Data": lambda x,y: processSaveData(x, y),
    "Paste To Data": lambda x,y: processPasteToData(x, y),
    "Get Default": lambda x,y: processGetDefault(x, y),
    "Check Condition": lambda x,y,z: processCheckCondition(x, y, z),
    "Repeat": lambda x,y,z: processRepeat(x, y, z),
    "Goto": lambda x,y,z: processGoto(x, y, z),
    "Call Function": lambda x,y,z,v,w: processCallFunction(x, y, z, v, w),
    "Return": lambda x,y,z,w: processReturn(x, y, z, w),
    "Use Skill": lambda x,y,z,u,v,w: processUseSkill(x, y, z, u, v, w),
    "Overload Skill": lambda x,y,z,w: processOverloadSkill(x, y, z, w),
    "Use External Skill": lambda x, y, z: processUseExternalSkill(x, y, z),
    "Report External Skill Run Status": lambda x, y, z: processReportExternalSkillRunStatus(x, y, z),
    "Stub": lambda x,y,z,u,v,w: processStub(x, y, z, u, v, w),
    "Call Extern": lambda x,y: processCallExtern(x, y),
    "Exception Handler": lambda x,y,z,w: processExceptionHandler(x, y, z, w),
    "End Exception": lambda x,y,z,w: processEndException(x, y, z, w),
    "Search Anchor Info": lambda x,y: processSearchAnchorInfo(x, y),
    "External Hook": lambda x,y: processExternalHook(x, y),
    "Create Requests Session": lambda x,y: processCreateRequestsSession(x, y),
    "Search Word Line": lambda x, y: processSearchWordLine(x, y),
    "Think": lambda x, y, z: processThink8(x, y, z),
    "FillRecipients": lambda x,y: processFillRecipients(x, y),
    "Search Scroll": lambda x,y: processSearchScroll(x, y),
    "Scroll To Location": lambda x,y: processScrollToLocation(x, y),
    "Calc Objs Distance": lambda x,y: processCalcObjectsDistance(x, y),
    "Seven Zip": lambda x,y: process7z(x, y),
    "Zip Unzip": lambda x,y: processZipUnzip(x, y),
    "List Dir": lambda x, y: processListDir(x, y),
    "Check Existence": lambda x, y: processCheckExistence(x, y),
    "Create Dir": lambda x, y: processCreateDir(x, y),
    "Read File": lambda x, y: processReadFile(x, y),
    "Write File": lambda x, y: processWriteFile(x, y),
    "Delete File": lambda x, y: processDeleteFile(x, y),
    "Kill Processes": lambda x, y: processKillProcesses(x, y),
    "print Label": lambda x,y: processPrintLabels(x, y),
    "Read Json File": lambda x,y: processReadJsonFile(x, y),
    "Read Xlsx File": lambda x,y: processReadXlsxFile(x, y),
    "ADS Batch Text To Profiles": lambda x,y,z: processUpdateBotADSProfileFromSavedBatchTxt(x, y,z),
    "ADS Gen XLSX Batch Profiles": lambda x,y: processADSGenXlsxBatchProfiles(x, y),
    "ADS Save API Settings": lambda x,y,z: processADSSaveAPISettings(x, y, z),
    "ADS Update Profile Ids": lambda x,y,z: processADSUpdateProfileIds(x, y,z),
    "AMZ Search Products": lambda x,y: processAMZSearchProducts(x, y),
    "AMZ Scrape PL Html": lambda x, y, z: processAMZScrapePLHtml(x, y, z),
    "AMZ Browser Scrape Products List": lambda x, y, z: processAMZBrowserScrapePL(x, y, z),
    "AMZ Browse Details": lambda x,y: processAMZBrowseDetails(x, y),
    "AMZ Scrape Product Details Html": lambda x, y, z: processAMZScrapeProductDetailsHtml(x, y, z),
    "AMZ Scrape Buy Orders Html": lambda x, y, z: processAMZScrapeBuyOrdersHtml(x, y, z),
    "AMZ Browse Reviews": lambda x,y: processAMZBrowseReviews(x, y),
    "AMZ Scrape Reviews Html": lambda x, y, z: processAMZScrapeReviewsHtml(x, y, z),
    "AMZ Scrape Sold Orders Html": lambda x, y, z: processAMZScrapeSoldOrdersHtml(x, y, z),
    "AMZ Scrape Msg Lists": lambda x, y, z: processAmzScrapeMsgList(x, y, z),
    "AMZ Buy Check Shipping": lambda x, y: processAmzBuyCheckShipping(x, y),
    "AMZ Details Check Position": lambda x, y: processAmzDetailsCheckPosition(x, y),
    "AMZ PL Calc Columns": lambda x, y: processAmzPLCalcNCols(x, y),
    "Sell Check Shipping": lambda x, y: processSellCheckShipping(x, y),
    "AMZ Scrape Customer Msg": lambda x, y, z: processAmzScrapeCustomerMsgThread(x, y, z),
    "EBAY Scrape Orders Html": lambda x, y, z: processEbayScrapeOrdersFromHtml(x, y, z),
    "EBAY Scrape Orders Javascript": lambda x, y, z: processEbayScrapeOrdersFromJss(x, y, z),
    "EBAY Scrape Msg Lists": lambda x, y, z: processEbayScrapeMsgList(x, y, z),
    "EBAY Scrape Customer Msg": lambda x, y, z: processEbayScrapeCustomerMsgThread(x, y, z),
    "Ebay Gen Shipping From Order ID": lambda x, y: processEbayGenShippingInfoFromOrderID(x, y),
    "Gen Resp Msg": lambda x, y: processGenRespMsg(x, y),
    "ETSY Scrape Orders": lambda x, y, z: processEtsyScrapeOrders(x, y, z),
    "Etsy Get Order Clicked Status": lambda x, y: processEtsyGetOrderClickedStatus(x, y),
    "Etsy Set Order Clicked Status": lambda x, y: processEtsySetOrderClickedStatus(x, y),
    "Etsy Find Screen Order": lambda x, y: processEtsyFindScreenOrder(x, y),
    "Etsy Remove Expanded": lambda x, y: processEtsyRemoveAlreadyExpanded(x, y),
    "Etsy Extract Tracking": lambda x, y: processEtsyExtractTracking(x, y),
    "Etsy Add Page Of Order": lambda x, y: processEtsyAddPageOfOrder(x, y),
    "ETSY Scrape Msg Lists": lambda x, y, z: processEtsyScrapeMsgLists(x, y, z),
    "ETSY Scrape Msg Thread": lambda x, y, z: processEtsyScrapeMsgThread(x, y, z),
    "Create ADS Profile Batches": lambda x, y, z: processADSProfileBatches(x, y, z),
    "Update Buy Mission Result": lambda x, y, z: processUpdateBuyMissionResult(x, y, z),
    "GS Scrape Labels": lambda x, y, z: processGSScrapeLabels(x, y, z),
    "GS Extract Zipped": lambda x, y: processGSExtractZippedFileName(x, y),
    "Prep GS Order": lambda x, y: processPrepGSOrder(x, y),
    "Prepare GS Order": lambda x, y: processPrepareGSOrder(x, y),
    "AMZ Match Products": lambda x,y: processAMZMatchProduct(x, y),
    "Obtain Reviews": lambda x, y, z: processObtainReviews(x, y, z),
    "Gen Shipping From Msg Responses": lambda x,y: processGenShippingOrdersFromMsgResponses(x, y),
    "Go To Window": lambda x,y: processGoToWindow(x, y),
    "Move Downloaded File": lambda x,y: processMoveDownloadedFileToDestination(x, y),
    "Report To Boss": lambda x,y: processReportToBoss(x, y),
    "Web Driver Click": lambda x,y, z: processWebdriverClick(x, y, z),
    "Web Driver Scroll To": lambda x,y, z: processWebdriverScrollTo(x, y, z),
    "Web Driver Key In": lambda x, y, z: processWebdriverKeyIn(x, y, z),
    "Web Driver Combo Keys": lambda x, y, z: processWebdriverComboKeys(x, y, z),
    "Web Driver Hover To": lambda x, y, z: processWebdriverHoverTo(x, y, z),
    "Web Driver Focus": lambda x, y, z: processWebdriverFocus(x, y, z),
    "Web Driver Select Drop Down": lambda x, y, z: processWebdriverSelectDropDown(x, y, z),
    "Web Driver Back": lambda x, y: processWebdriverBack(x, y),
    "Web Driver Forward": lambda x, y: processWebdriverForward(x, y),
    "Web Driver Go To Tab": lambda x, y: processWebdriverGoToTab(x, y),
    "Web Driver New Tab": lambda x, y: processWebdriverNewTab(x, y),
    "Web Driver Close Tab": lambda x, y: processWebdriverCloseTab(x, y),
    "Web Driver Quit": lambda x, y: processWebdriverQuit(x, y),
    "Web Driver Execute Js": lambda x, y, z: processWebdriverExecuteJs(x, y, z),
    "Web Driver Refresh Page": lambda x, y: processWebdriverRefreshPage(x, y),
    "Web Driver Screen Shot": lambda x, y: processWebdriverScreenShot(x, y),
    "Web Driver Start Existing Chrome": lambda x, y: processWebdriverStartExistingChrome(x, y),
    "Web Driver Start Existing ADS": lambda x, y: processWebdriverStartExistingADS(x, y),
    "Web Driver Start New Chrome": lambda x, y: processWebdriverStartNewChrome(x, y),
    "Web Driver Extract Info": lambda x, y, z: processWebdriverExtractInfo(x, y, z),
    "Web Driver Wait Until Clickable": lambda x, y, z: processWebdriverWaitUntilClickable(x, y, z),
    "Web Driver Wait For Visibility": lambda x, y, z: processWebdriverWaitForVisibility(x, y, z),
    "Web Driver Switch To Frame": lambda x, y: processWebdriverSwitchToFrame(x, y),
    "Web Driver Switch To Default Content": lambda x, y: processWebdriverSwitchToDefaultContent(x, y),
    "Web Driver Wait Download Done And Transfer": lambda x, y: processWebdriverWaitDownloadDoneAndTransfer(x, y),
    "Web Driver Check Connection": lambda x, y: processWebdriverCheckConnection(x, y),
    "Web Driver Check Visibility": lambda x, y: processWebdriverCheckVisibility(x, y),
    "Web Driver Get Value": lambda x, y: processWebdriverGetValueFromWebElement(x, y),
    "Request Human In Loop": lambda x, y, z, v: processReqHumanInLoop(x, y, z, v),
    "Close Human In Loop": lambda x, y, z, v: processCloseHumanInLoop(x, y, z, v),
    "Check App Running": lambda x, y: processCheckAppRunning(x, y),
    "Bring App To Front": lambda x, y: processBringAppToFront(x, y),
    "Upload Files": lambda x, y, z: processUploadFiles(x, y, z),
    "Download Files": lambda x, y, z: processDownloadFiles(x, y, z),
    "Check Sublist": lambda x, y: processCheckSublist(x, y),
    "Check Already Processed": lambda x, y: processCheckAlreadyProcessed(x, y),
    "Update Mission Status": lambda x, y, z: processUpdateMissionStatus(x, y, z)
}

# read an psk fill into steps (json data structure)
# input: steps - data structure to hold the results.
#        name_prefix - name to add to front of step # to make step name unique.
#                       typically this is the cascade of userID, skill name.
#       skill_file - full path file name of the .psk file.
# output: None (sort of in step already)
# step name should be in the form of "B"+BotID+"M" + MissionID + "!" + skillname + "!" + level # + step number
# Note:
def readPSkillFile(name_space, skill_file, lvl = 0):
    global steps
    step_keys = []
    global skill_code
    this_skill_code = {}
    try:
        if os.path.exists(skill_file):
            log3("reading skill file:" + skill_file)

            with open(skill_file, "r") as json_as_string:
                # inj = json.load(json_as_string)
                # Call this as a recursive function if your json is highly nested

                # get rid of comments.
                # lines = [re.sub("^\s*#.*", "", one_object.rstrip()) for one_object in json_as_string.readlines()]
                lines = [re.sub(r"^\s*#.*", "", one_object.rstrip()) for one_object in json_as_string.readlines()]
                json_as_string.close()

                # get rid of empty lines.
                #new_list = list(filter(lambda x: x != '', list_with_empty_strings))
                useful_lines = list(filter(lambda x: x.rstrip(), lines))
                slines = ""
                key = ""
                # reg = re.compile("step +[0-9]")
                # reg = re.compile(r'"([^"]*)"')
                # #if reg.match('aaa"step 123":'):
                # if len(re.findall(r'"([^"]*)"', 'aaa"step 123":')) > 0:
                #     log3("FOUND MATCH")
                # else:
                #     log3("NO MATCH")
                log3("NUM USEFUL:"+str(len(useful_lines)))
                for l in useful_lines:
                    #need to create prefix and add the step name.
                    # l = adressAddNameSpace(l, name_space, lvl)            # will do this later.

                    #log3("USEFUL: "+l)
                    slines = slines + l + "\n"

                # log3("SLINES:"+slines)
                this_skill_code = json.loads(slines)

                # call the sub skills
                step_keys = list(this_skill_code.keys())
                for key in step_keys:
                    if key == "header" or key == "dummy":
                        del this_skill_code[key]
                # log3("=============================================================")
                # log3("SKILL CODE:"+str(len(this_skill_code.keys()))+json.dumps(this_skill_code))
    except OSError as err:
        log3("ERROR: Read PSK Error!"+str(err))

    return this_skill_code


def addNameSpaceToAddress(stepsJson, name_space, lvl):
    # add name space to json step names.
    steps_keys = list(stepsJson.keys())
    log3("name space:"+name_space)
    # log3("STEP KEYS::::"+json.dumps(steps_keys))
    for old_key in steps_keys:
        new_key = adressAddNameSpace(old_key, name_space, lvl)
        # log3("New Key:"+json.dumps(new_key))
        stepsJson[new_key] = stepsJson[old_key]
        stepsJson.pop(old_key)


def adressAddNameSpace(l, name_space, lvl):
    if len(re.findall(r'step [0-9]+', l)) > 0:

        # need to handle "Use Skill" calling to sub-skill files.
        # +json.dumps(("STEP line:"+l)
        step_word = re.findall(r'([^"]*)', l)[0]
        # log3("STEP word:"+step_word)
        sn = step_word.split(' ')[1]
        global_sn = name_space + str(lvl) + "!" + sn
        # log3("GLOBAL NS:"+global_sn)
        # re.sub(r'"([^"]*)"', global_sn, l)
        l = re.sub(r'[0-9]+', global_sn, l)

    return l

# settings contains the following info:
# reading_speed - words per minute
# pay attention amazon's choice, best seller, sponsored, top N reviews, price, price review rating ratio, particular brands - Yes/No
# browse sequence, - straight down, go thru to bottom first, back up and go thru down again slowly.
# which section spends extra time browsing?
# total time spent limit for this routine
# num of good reviews to read
# num of bad reviews to read
# num of products to browse,
# all of the above should be decided on the cloud and send to the client in form a list of psk to finish. each psk should be a
# very small section of the entire mission.
#
# on psk side, what's fundamental instructions to support above:
#

async def runAllSteps(steps, mission, skill, in_msg_queue, out_msg_queue, mode="normal"):
    global last_step
    global next_step
    global rd_screen_count
    run_result = DEFAULT_RUN_STATUS
    step_stat = DEFAULT_RUN_STATUS
    last_step = -1
    next_step = 0
    next_step_index = 0
    global running
    run_stack = []
    log3("running all steps....."+json.dumps(mission.genJson()))
    last_error_stat = "None"
    stepKeys = list(steps.keys())
    rd_screen_count = 0
    running= True
    # for k in stepKeys:
    #     log3("steps: "+str(k)+" -> "+json.dumps(steps[k]))
    log3("====================================="+str(len(stepKeys)))
    while next_step_index <= len(stepKeys)-1:
        if running:
            last_step = next_step_index
            running_step_index = next_step_index
            next_step_index, step_stat = await run1step8(steps, next_step_index, mission, skill, run_stack)

            if step_stat == DEFAULT_RUN_STATUS:

                # debugging mode. if the next instruction is one of the breakpoints, then stop and pendin for
                # keyboard input. (should fix later to support GUI button press.....)
                if next_step_index in breakpoints:
                    cmd = input("cmd for next action('<Space>' to step, 'c' to continue to run, 'q' to abort. \n")
                    if cmd == "c":
                        mode = "normal"
                    elif cmd == "q":
                        break

                # in case an exeption occurred, handle the exception.
                if in_exception:
                    log3("EXCEPTION THROWN:")
                    # push next_step_index onto exception stack.
                    exception_stack.append(next_step_index)

                    # set the next_step_index to be the start of the exception handler, which always starts @8000000
                    next_step_index = stepKeys.index("step8000000")

                if mode == "debug":
                    input("hit any key to continue")

                log3("next_step_index: "+str(next_step_index)+"len(stepKeys)-1: "+str(len(stepKeys)-1))
            elif step_stat == WAIT_HIL_RESPONSE:
                # suspend the run if we're waiting for human to help
                running = False
            else:
                last_error_stat = step_stat+":"+stepKeys[last_step]


        # check whether there is any msging handling need.
        log3("listening to message queue......")
        if not in_msg_queue.empty():
            message = await in_msg_queue.get()
            log3(f"Rx RunAllSteps message: {message}")
            msg = json.loads(message["contents"])
            if msg["cmd"] == "reqCancelAllMissions":
                # set program counter to the end, this shall stop it.
                print("STOPPING ALL Missions by directly jump to the end.....")
                step_stat = "ABORTEDByKey"
                next_step_index = len(stepKeys)
            elif msg["cmd"] == "cancel missions" and msg["target"] == "all" :
                next_step_index = len(stepKeys)
            elif msg["cmd"] == "halt missions":
                print("RPA HALTed", next_step_index, len(stepKeys), step_stat)
                running = False
            elif msg["cmd"] == "HIL response":           # real time human in the loop response.
                print("Human Response Received.")
                result, next_i  = processCloseHumanInLoop(msg, mission, -1)
                if result == DEFAULT_RUN_STATUS:
                    running = True
                else:
                    running = False
            elif msg["cmd"] == "resume missions":
                print("RPA RESUMEd")
                running = True
            elif msg["cmd"] == "show status":
                # send back current running status based on msg["content"]
                # basically sends back str(next_step_index)
                rpa_stat_msg = json.dumps({"type": "rpa_running_status", "mid": mission.getMid(), "step": stepKeys[next_step_index], "last error": last_error_stat})
                sendGUIMessage(out_msg_queue, rpa_stat_msg)

            in_msg_queue.task_done()

        print("current step stat:"+step_stat)
        if step_stat != DEFAULT_RUN_STATUS:
            break

        if not running:
            await asyncio.sleep(1)

    if step_stat != DEFAULT_RUN_STATUS:
        log3("RUN Error!")
        run_result = "Incomplete:"+step_stat+":"+str(last_step)
        # should close the current app here, make room for the next retry, and other tasks...

    return run_result


def sendGUIMessage(msg_queue, msg_data):
    asyncio.create_task(msg_queue.put(msg_data))

def runNSteps(steps, prev_step, i_step, e_step, mission, skill, run_stack):
    global last_step
    global next_step
    last_step = prev_step
    next_step = i_step
    running = True
    log3("running N steps.....")
    while next_step <= e_step and running:
        log3("len steps:", len(steps), "next step:", next_step)
        run1step(steps, mission, skill, run_stack)


def run1step(steps, si, mission, skill, stack):
    global next_step
    global last_step
    # settings = mission.parent_settings
    i = next_step
    stepKeys = list(steps.keys())
    step = steps[stepKeys[si]]
    last_si = si
    log3("============>running step ["+str(si)+"]: "+json.dumps(step))

    if "type" in step:
        if step["type"] == "Halt":
            # run step using the funcion look up table.
            si,isat = RAIS[step["type"]](step, si)
        elif step["type"] == "Goto" or step["type"] == "Check Condition" or step["type"] == "Repeat":
            # run step using the funcion look up table.
            si,isat = RAIS[step["type"]](step, si, stepKeys)
        elif step["type"] == "Extract Info" or step["type"] == "Save Html":
            si,isat = RAIS[step["type"]](step, si, mission, skill)
        elif step["type"] == "Create ADS Profile Batches" or step["type"] == "Web Driver Extract Info" or \
            step["type"] == "Ask LLM" or step["type"] == "Web Driver Click" or step["type"] == "Upload Files" or \
            step["type"] == "Web Driver Scroll To" or step["type"] == "Web Driver Execute Js" or \
            step["type"] == "Web Driver Wait Until Clickable" or step["type"] == "AMZ Browser Scrape Products List" or \
            step["type"] == "Text Input" or "Scrape" in step["type"] or step["type"] == "Web Driver Wait For Visibility" or\
            step["type"] == "Web Driver Focus" or  step["type"] == "Web Driver Hover To" or step["type"] == "Download Files" or \
            step["type"] == "Use External Skill" or step["type"] == "Report External Skill Run Status" or \
            step["type"] == "Update Mission Status" or step["type"] == "ADS Save API Settings" or \
            step["type"] == "ADS Update Profile Ids" or step["type"] == "ADS Batch Text To Profiles" or \
            step["type"] == "Web Driver Select Drop Down" or "Mouse" in step["type"] or "Key" in step["type"]:
            si,isat = RAIS[step["type"]](step, si, mission)
        elif step["type"] == "End Exception" or step["type"] == "Exception Handler" or step["type"] == "Return":
            si,isat = RAIS[step["type"]](step, si, stack, stepKeys)
        elif step["type"] == "Stub" or step["type"] == "Use Skill":
            si,isat = RAIS[step["type"]](step, si, stack, skill_stack, skill_table, stepKeys)
        elif step["type"] == "Call Function":
            si,isat = RAIS[step["type"]](step, si, stack, function_table, stepKeys)
        elif "My " in step["type"]:
            si,isat = RAIS[step["type"]](step, si, symTab, mission)
        else:
            print("step type:"+step["type"])
            if step["type"] in RAIS:
                si,isat = RAIS[step["type"]](step, si)
            else:
                si = si + 1
                isat = "ErrorInstructionNotFoundType:404"
                print("ERROR: UNKNOWN instruction: "+step["type"])
    else:
        si = si + 1
        isat = "ErrorInstructionNotType:400"

    return si, isat


async def run1step8(steps, si, mission, skill, stack):
    global next_step
    global last_step
    # settings = mission.parent_settings
    try:
        i = next_step
        stepKeys = list(steps.keys())
        step = steps[stepKeys[si]]
        last_si = si
        log3("============>running step ["+str(si)+"]: "+json.dumps(step))

        if "type" in step:
            if step["type"] == "Halt":
                # run step using the funcion look up table.
                if inspect.iscoroutinefunction(ARAIS[step["type"]]):
                    si,isat = await ARAIS[step["type"]](step, si)
                else:
                    si,isat = await asyncio.to_thread(ARAIS[step["type"]], step, si)

            elif step["type"] == "Goto" or step["type"] == "Check Condition" or step["type"] == "Repeat":
                # run step using the funcion look up table.
                if inspect.iscoroutinefunction(ARAIS[step["type"]]):
                    si,isat = await ARAIS[step["type"]](step, si, stepKeys)
                else:
                    si,isat = await asyncio.to_thread(ARAIS[step["type"]], step, si, stepKeys)

            elif step["type"] == "Extract Info" or step["type"] == "Save Html":
                if inspect.iscoroutinefunction(ARAIS[step["type"]]):
                    si,isat = await ARAIS[step["type"]](step, si, mission, skill)
                else:
                    si,isat = await asyncio.to_thread(ARAIS[step["type"]], step, si, mission, skill)

            elif step["type"] == "Create ADS Profile Batches" or step["type"] == "Web Driver Extract Info" or \
                 step["type"] == "Ask LLM" or step["type"] == "Web Driver Click" or step["type"] == "Upload Files" or \
                 step["type"] == "Web Driver Execute Js" or step["type"] == "Web Driver Focus" or step["type"] == "Download Files" or \
                 step["type"] == "Web Driver Hover To"  or step["type"] == "Web Driver Scroll To" or  step["type"] == "ADS Save API Settings" or \
                 step["type"] == "Text Input" or "Scrape" in step["type"] or step["type"] == "Web Driver Wait Until Clickable" or \
                 step["type"] == "Web Driver Wait For Visibility" or step["type"] == "Update Mission Status" or \
                 step["type"] == "AMZ Browser Scrape Products List" or step["type"] == "ADS Update Profile Ids" or \
                 step["type"] == "Use External Skill" or step["type"] == "Report External Skill Run Status" or \
                 step["type"] == "ADS Batch Text To Profiles" or \
                 step["type"] == "Web Driver Select Drop Down" or "Mouse" in step["type"] or "Key" in step["type"]:
                if inspect.iscoroutinefunction(ARAIS[step["type"]]):
                    si,isat = await ARAIS[step["type"]](step, si, mission)
                else:
                    si,isat = await asyncio.to_thread(ARAIS[step["type"]], step, si, mission)

            elif step["type"] == "End Exception" or step["type"] == "Exception Handler" or step["type"] == "Return":
                if inspect.iscoroutinefunction(ARAIS[step["type"]]):
                    si,isat = await ARAIS[step["type"]](step, si, stack, stepKeys)
                else:
                    si,isat = await asyncio.to_thread(ARAIS[step["type"]], step, si, stack, stepKeys)

            elif step["type"] == "Stub" or step["type"] == "Use Skill":
                if inspect.iscoroutinefunction(ARAIS[step["type"]]):
                    si,isat = await ARAIS[step["type"]](step, si, stack, skill_stack, skill_table, stepKeys)
                else:
                    si,isat = await asyncio.to_thread(ARAIS[step["type"]], step, si, stack, skill_stack, skill_table, stepKeys)

            elif step["type"] == "Call Function":
                if inspect.iscoroutinefunction(ARAIS[step["type"]]):
                    si,isat = await ARAIS[step["type"]](step, si, stack, function_table, stepKeys)
                else:
                    si,isat = await asyncio.to_thread(ARAIS[step["type"]], step, si, stack, function_table, stepKeys)

            elif step["type"] == "Request Human In Loop" or step["type"] == "Close Human In Loop":
                if inspect.iscoroutinefunction(ARAIS[step["type"]]):
                    si,isat = await ARAIS[step["type"]](step, si, mission, hil_queue)
                else:
                    si,isat = await asyncio.to_thread(ARAIS[step["type"]], step, si, mission, hil_queue)

            elif "My " in step["type"]:
                # this is an extension instruction, execute differently, simply call extern. as to what to actually call, it's all
                # embedded in the step dictionary.
                si,isat = await asyncio.to_thread(RAIS[step["type"]], step, si, symTab, mission)
            else:
                print("step type:"+step["type"])
                if step["type"] in RAIS:
                    print("instruction found....")
                    if inspect.iscoroutinefunction(ARAIS[step["type"]]):
                        print("coroutine found....")
                        si, isat = await ARAIS[step["type"]](step, si)
                    else:
                        print("not coroutine found....")
                        si, isat = await asyncio.to_thread(ARAIS[step["type"]], step, si)
                else:
                    si = si + 1
                    isat = "ErrorInstructionNotFoundType:404"
                    print("ERROR: UNKNOWN instruction: "+step["type"])


        else:
            si = si + 1
            isat = "ErrorInstructionNotType:400"

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in run1step8: {traceback.format_exc()} {str(e)}"
        print(f"Error while executing hook: {ex_stat}")

    return si, isat


def cancelRun():
    global next_step
    global last_step
    global running

    running = False
    last_step = -1
    next_step = 0

def pauseRun():
    global running
    running = False

def continueRun(steps, settings):
    global next_step
    global last_step
    global running
    i = next_step
    running = True
    while i <= len(steps)-1 and running:
        i = run1step(steps, settings)



def processBrowse(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("browsing the page....")
    except:
        ex_stat = "ErrorBrowse:" + str(i)
        log3(ex_stat)

    return (i + 1), ex_stat

def is_uniq(word, allwords):
    matched = [x for x in allwords if word in x["text"]]
    log3("# matched: "+str(len(matched)))
    if len(matched) == 1:
        return True
    else:
        return False

# this function finds a unique line of text nearest to the specified target location on the screen.
def find_phrase_at_target(screen_data, target_loc):
    log3("finding text around target loc: "+json.dumps(target_loc))
    found_phrase = ""
    found_box = [0, 0, 0, 0]
    # first, filter out all shapes and non text contents.
    paragrphs = [x for x in screen_data if x['name'] == 'paragraph']

    allwords = []

    for p in paragrphs:
        for l in p["txt_struct"]:
            for w in l["words"]:
                allwords.append(w)

    sorted_words = sorted(allwords, key=lambda w: p2p_distance(box_center(w["box"]), target_loc), reverse=False)

    log3("found paragraphs: "+str(len(paragrphs)))

    # then sort by paragraph center's distance to target location.
    # box: (left, top, right, bottom)
    # paragrphs = sorted(paragrphs, key=lambda x: p2p_distance(loc_center(x["loc"]), target_loc), reverse=False)
    time.sleep(1)
    log3("w0: "+json.dumps(sorted_words[0])+" dist: "+json.dumps(p2p_distance(box_center(sorted_words[0]["box"]), target_loc)))
    log3("w1: "+json.dumps(sorted_words[1])+" dist: "+json.dumps(p2p_distance(box_center(sorted_words[1]["box"]), target_loc)))
    log3("w2: "+json.dumps(sorted_words[2])+" dist: "+json.dumps(p2p_distance(box_center(sorted_words[2]["box"]), target_loc)))
    # then find an unique line in that paragraph, if none found, go the next paragraph until find one.
    for w in sorted_words:
        # now filter out lines contains non alphabetical chars. and non-unique phrases.
        # afterstrip = [x['text'].lstrip() for x in lines]
        actual_w = w["text"].strip()
        if len(actual_w) >= 6:
            if is_uniq(actual_w, sorted_words):
                log3("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                found_phrase = actual_w
                found_box = w['box']
                log3("found the implicit marker: "+found_phrase+" loc: "+json.dumps(found_box))
                break

    return(found_phrase, found_box)

def find_marker_on_screen(screen_data, target_word):
    # first, filter out all shapes and non text contents.
    log3("finding......."+target_word)
    paragraphs = [x for x in screen_data if x['name'] == 'paragraph']
    found_box = []
    found_loc = None
    for p in paragraphs:
        for l in p["txt_struct"]:
            for w in l["words"]:
                if w["text"].strip() == target_word:
                    found_box = w["box"]
                    break
            if found_box:
                break
        if found_box:
            break
    # no need to worry about multiple findings, there should be either 1 or 0 occurance.

    return(found_box)


# record the location of a specific text on screen, the result will be used to calibrate scroll amount.
# loc: location on screen, could take value "", "middle" "bottome" "top" - meaning take some unique text that's nearest the location of the screen.
#       the resulting text is defauly putinto the variable "ResolutionCalibrationMarker"
# txt: text to record the location. - caller can also directly specify the text to be extracted, in such a case, loc = ""
# screen: variable that contains the screen content data structure.
# to: put result in this varable name.
def processRecordTxtLineLocation(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        loc_word = step["location"]
        scrn = step["screen"]
        marker_text = step["text"]
        marker_loc = step["to"]
        found_line = None
        found_text = None
        screen_data = symTab[scrn]
        symTab["last_screen_cal01"] = screen_data
        screen_size = (screen_data[len(screen_data) - 2]['loc'][3], screen_data[len(screen_data) - 2]['loc'][2])
        log3("screen_size: "+json.dumps(screen_size))

        if marker_text == "":
            # this means just grab any line closest to the target location.
            if loc_word == "middle":
                # now go thru scrn data structure to find a line that's nearest to middle of the screen.
                # grab the full screen item in the symTab[scrn] which should always be present.
                target_loc = (int(screen_size[0]*2/3), int(screen_size[1]*2/3))
                found_phrase, found_box = find_phrase_at_target(screen_data, target_loc)

                log3("FOUND implicit marker: ["+found_phrase+"] at location: "+json.dumps(found_box))

                #mid = int(abc.get_box()[1] + 0.5*abc.get_box()[3])
                # now filter out all lines above mid point and leave only text lines below the mid point,
                # sort them based on vertical position, and then take the 1st item which is vertically nearest to the mid point.
                symTab["InternalMarker"] = found_phrase

        else:
            log3("FINDINg text: "+marker_text+" ............ ")
            if loc_word.isnumeric():
                # percentage deal
                target_loc = (int(screen_size[0] / 2), int(screen_size[1] * (int(loc_word)/100)))
            else:
                if loc_word == "top":
                    target_loc = (int(screen_size[0]/2), 0)
                    # find the template text that's nearest to refvloc
                elif loc_word == "middle":
                    target_loc = (int(screen_size[0] / 2), int(screen_size[1] / 2))
                elif loc_word == "bottom":
                    target_loc = (int(screen_size[0] / 2), int(screen_size[1]))
                else:
                    target_loc = (int(screen_size[0] / 2), 0)

            log3("target_loc: "+json.dumps(target_loc))

            found_box = find_marker_on_screen(screen_data, marker_text)
            log3("found_loc: "+json.dumps(found_box))

        # symTab[marker_loc] = box_center(found_paragraph["loc"])
        symTab[marker_loc] = box_center(found_box)
        log3("found text at loc: "+json.dumps(found_box)+"stored in var: "+json.dumps(marker_loc)+" with box center: "+json.dumps(symTab[marker_loc]))

    except:
        ex_stat = "ErrorRecordTxtLineLocation:" + str(i)

    return (i + 1), ex_stat



def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

# find a paragraph on screen that matches the target paragraph.
def find_paragraph_match(target, screen_data):
    paragrphs = [x for x in screen_data if x['name'] == 'paragraph']
    log3("find_paragraph_match:"+json.dumps(paragrphs))
    log3("Target:"+json.dumps(target))
    # then sort by paragraph center's distance to target location.
    # box: (left, top, right, bottom)
    similarity = [similar(target['text'],  x['text']) for x in paragrphs]
    log3(str(similarity.index(max(similarity))) + ","+str(similarity[similarity.index(max(similarity))])+", "+paragrphs[similarity.index(max(similarity))]['text'])
    log3("similarity: "+json.dumps(similarity))
    matched = [x for x in paragrphs if similar(target['text'],  x['text']) > 0.95]
    log3("matched:"+json.dumps(matched))

    if len(matched) > 0:
        return matched[0]
    else:
        return None

# sink, amount, screen, marker, stepN
# "data_sink": sink
# "amount": amount
# "screen": screen
# "marker": marker
def processCalibrateScroll(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        screen_resolution = 30
        marker_text = step["marker"]
        scroll_amount = int(step["amount"])
        resolution = step["data_sink"]
        prev_loc = symTab[step["last_record"]]
        screen = step["screen"]
        found_line = None

        screen_data = symTab[screen]
        screen_size = (screen_data[len(screen_data) - 2]['loc'][3], screen_data[len(screen_data) - 2]['loc'][2])

        target_loc = (int(screen_size[0] / 2), 0)
        log3("FINDing near target loc: "+json.dumps(target_loc))
        # find the template text that's nearest to refvloc
        if marker_text == "":
            marker_text = symTab["InternalMarker"]
            log3("finding implicit marker: ["+symTab["InternalMarker"]+"]")
        found_box = find_marker_on_screen(screen_data, marker_text)
        log3("calibration scroll found location:: "+json.dumps(found_box)+" vs. previous location::"+json.dumps(prev_loc)+" in var: "+json.dumps(step["last_record"]))
        # matched_paragraph = find_paragraph_match(marker_paragraph, screen)

        if found_box:
            delta_v = abs(box_center(found_box)[1] - prev_loc[1])
            log3("abs delta v: "+str(delta_v)+" for scrool_amount: "+str(scroll_amount))
            scroll_resolution = delta_v/scroll_amount
        else:
            scroll_resolution = 0
            log3("ERROR: scroll calibration FAILED!!!!")

        symTab[resolution] = scroll_resolution
        symTab[screen] = symTab["last_screen_cal01"]

        scroll_resolution_file = getECBotDataHome() + "/scroll_resolution.json"
        with open(scroll_resolution_file, 'w') as fileTBW:
            json.dump({"resolution": scroll_resolution}, fileTBW)

            fileTBW.close()

        log3("scroll resolution is found as: "+str(scroll_resolution)+" stored in var: "+str(resolution))

    except:
        ex_stat = "ErrorCalibrateScroll:" + str(i)

    return (i + 1), ex_stat



def getPrevStepName(sName):
    prev = int(sName[4, len(sName)]) - STEP_GAP
    return "step"+str(prev)

def getNextStepName(sName):
    next = int(sName[4, len(sName)]) + STEP_GAP
    return "step"+str(next)

def gen_addresses(stepcodes, nth_pass):
    global skill_table
    global function_table
    temp_stack = []
    log3("nth pass: "+str(nth_pass))
    # go thruthe program as we see condition / loop / function def , push them onto stack, then pop them off as we see
    # else, end - if, end - loop, end - function....until at last the stack is empty again.
    # sk
    # skcode = json.loads(sk)
    stepkeys = list(stepcodes.keys())
    log3("total " + str(len(stepkeys)) + " steps.")
    # print("step keys:::", stepkeys)

    if nth_pass == 1:
        # parse thru the json objects and work on stubs.
        for i in range(len(stepkeys)):
            stepName = stepkeys[i]
            log3("working on: ["+str(i)+"] "+stepName+" "+stepcodes[stepName]["type"])

            if i != 0:
                prevStepName = stepkeys[i - 1]
            else:
                prevStepName = stepName

            if i != len(stepkeys) - 1:
                nextStepName = stepkeys[i + 1]
            else:
                nextStepName = stepName

            # print("i:"+str(i)+" next step name: "+nextStepName)

            if stepcodes[stepName]["type"] == "Stub":
                # code block
                # print("STUB NAME:"+stepcodes[stepName]["stub_name"])
                # build up function table, and skill table.
                if "start skill" in stepcodes[stepName]["stub_name"]:
                    # this effectively includes the skill overload function. - SC
                    log3("ADDING TO SKILL TABLE: ["+str(i)+"]"+json.dumps(stepcodes[stepName]["func_name"])+" "+json.dumps(nextStepName))
                    skill_table[stepcodes[stepName]["func_name"]] = nextStepName
                elif stepcodes[stepName]["stub_name"] == "start function":
                    # this effectively includes the skill overload function. - SC
                    log3(json.dumps(stepcodes[stepName]["func_name"]))
                    function_table[stepcodes[stepName]["func_name"]] = nextStepName

    elif nth_pass == 2:
        # parse thru the json objects and work on stubs.
        for i in range(len(stepkeys)):
            stepName = stepkeys[i]


            if i != 0:
                prevStepName = stepkeys[i-1]
            else:
                prevStepName = stepName

            if i != len(stepkeys)-1:
                nextStepName = stepkeys[i+1]
            else:
                nextStepName = stepName


            if stepcodes[stepName]["type"] == "Stub":
                #code block

                if stepcodes[stepName]["stub_name"] == "else":
                    # pop from stack, modify else, then push back, assume condition step will be pushed onto stack. as it executes.
                    tempStepName = temp_stack.pop()
                    log3("poped out due to else step["+str(len(temp_stack))+"]: "+json.dumps(tempStepName)+" ("+json.dumps(stepcodes[tempStepName])+")")

                    stepcodes[tempStepName]["if_else"] = nextStepName
                    # now replace with current stub with a goto statement and push this onto stack.

                    log3("replacing else with an empty Goto which will be filled up later...")
                    stepcodes[stepName] = {"type": "Goto", "goto": ""}

                    temp_stack.append(stepName)
                    log3("pushed step["+str(len(temp_stack))+"]: "+json.dumps(stepName)+"("+json.dumps(stepcodes[stepName])+")")

                elif stepcodes[stepName]["stub_name"] == "end condition":
                    # pop from stack
                    # log3("before popped out due to end condition step[", len(temp_stack), "]: ", tempStepName, "(", stepcodes[tempStepName], ")")

                    tempStepName = temp_stack.pop()
                    log3("popped out due to end condition step["+str(len(temp_stack))+"]: "+json.dumps(tempStepName)+"("+json.dumps(stepcodes[tempStepName])+")")

                    if (stepcodes[tempStepName]["type"] == "Goto"):
                        # in case that this is a check condition with an else stub....
                        log3("popped goto.....")
                        stepcodes[tempStepName]["goto"] = nextStepName
                    elif ( stepcodes[tempStepName]["type"] == "Check Condition"):
                        # in case that this is a check condition without else stub....
                        stepcodes[tempStepName]["if_else"] = nextStepName
                        log3("replace if_else to:"+json.dumps(nextStepName))
                        # so stub "else" will be replaced by a "Goto" step instead.
                        # stepcodes[stepName] = {"type": "Goto", "goto": nextStepName}
                elif stepcodes[stepName]["stub_name"] == "break":
                    # push on to stack
                    temp_stack.append(stepName)
                    log3("pushed step["+str(len(temp_stack))+"]: "+json.dumps(stepName)+"("+json.dumps(stepcodes[stepName])+")")
                elif stepcodes[stepName]["stub_name"] == "end loop":
                    # pop from stack
                    loop_start_found = False
                    fi = 0
                    log3("working on: "+prevStepName+" ("+json.dumps(stepcodes[prevStepName])+")")
                    while not loop_start_found:
                        tempStepName = temp_stack.pop()
                        log3("popped out due to end looop step["+str(len(temp_stack))+"]: "+str(fi)+" :: "+json.dumps(tempStepName)+"("+json.dumps(stepcodes[tempStepName])+")")
                        fi = fi + 1
                        if stepcodes[tempStepName]["type"] == "Repeat":
                            stepcodes[tempStepName]["end"] = nextStepName
                            loop_start_found = True
                            # now replace with current stub with a goto statement and push this onto stack.
                            stepcodes[stepName] = { "type": "Goto", "goto": tempStepName }
                        elif stepcodes[tempStepName]["type"] == "Stub":
                            if stepcodes[tempStepName]["stub_name"] == "break":
                                stepcodes[tempStepName] = {"type": "Goto", "goto": nextStepName}

                elif stepcodes[stepName]["stub_name"] == "def function":
                    # add function name and address pair to stepcodes - kind of a symbal table here.
                    stepcodes[symTab[stepName]["name"]] = nextStepName
                elif stepcodes[stepName]["stub_name"] == "end skill":
                    # add function name and address pair to stepcodes - kind of a symbal table here.
                    log3("END OF SKILL - do nothing..."+json.dumps(stepcodes[stepName]["func_name"]))
                elif stepcodes[stepName]["stub_name"] == "tag":
                    # this is for Goto statement, so that goto doesn't have to goto an explicict address,
                    # but can goto a String name instead. if any step is the goto target, just add
                    # a stub step with "tag" and "whatever you like to name the tag name"
                    # simply add tag and previous step address to the hash address space
                    symTab[stepcodes[stepName]["func_name"]] = prevStepName
            elif stepcodes[stepName]["type"] == "Check Condition":
                # push ont stack
                temp_stack.append(stepName)
                log3("pushed step["+str(len(temp_stack))+"]: "+stepName+"("+json.dumps(stepcodes[stepName])+")")

            elif stepcodes[stepName]["type"] == "Repeat":
                # push on to stack
                temp_stack.append(stepName)
                log3("pushed step["+str(len(temp_stack))+"]: "+stepName+"("+json.dumps(stepcodes[stepName])+")")

    elif nth_pass == 3:
        #on 3nd pass replace all function call address. -- SC 2023/03/27 I don't think we need this pass anymore....at least for now..
        for i in range(len(stepkeys)):
            stepName = stepkeys[i]
            if i != 0:
                prevStepName = stepkeys[i-1]
            else:
                prevStepName = stepName

            if i != len(stepkeys)-1:
                nextStepName = stepkeys[i+1]
            else:
                nextStepName = stepName

            if stepcodes[stepName]["type"] == "Call Function":
                stepcodes[stepName]["addr"] = stepcodes[stepcodes[stepName]["name"]]
            elif stepcodes[stepName]["type"] == "Use Skill":
                stepcodes[stepName]["addr"] = stepcodes[stepcodes[stepName]["name"]]


def prepRun1Skill(name_space, skill_file, lvl = 0):
    global skill_code
    global function_table
    run_steps = readPSkillFile(name_space, skill_file, lvl)
    log3("DONE reading skill file...")

    # generate real address for stubs and functions. (essentially update the addresses or the closing brackets...)
    gen_addresses(run_steps, 1)
    # 2nd pass: resolve overload.
    gen_addresses(run_steps, 2)
    log3("DONE generating addressess...")
    log3("READY2RUN1: "+json.dumps(run_steps))
    log3(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    log3("function table:"+json.dumps(function_table))
    return run_steps


# load all runnable skill files into memeory space, and start to assemble them into runnable instructions.
def prepRunSkill(all_skill_codes):
    global skill_code
    # need to clear from previous runs first.
    skill_code = []

    for sk in all_skill_codes:
        log3("READING SKILL CODE:"+sk["ns"]+" "+sk["skfile"])

        # f = open(sk["skfile"])
        # run_steps = json.load(f)
        # f.close()
        run_steps = readPSkillFile("", sk["skfile"], 0)
        # print("run steps:", run_steps)


        if skill_code:
            skill_code.update(run_steps)       # merge run steps.
            # skill_code = skill_code + run_steps
        else:
            skill_code = run_steps

    # 1st pass: get obvious addresses defined. if else end-if, loop end-loop,
    gen_addresses(skill_code, 1)
    # print("skill code after pass 1:", skill_code)
    #2nd pass: resolve overload.
    gen_addresses(skill_code, 2)
    # print("skill code after pass 2:", skill_code)
    # log3("READY2RUN: ", skill_code)
    log3(">>>>>>>>>>>DONE generating addressess>>>>>>>>>>>>>>")
    return skill_code

def genNextStepNumber(currentN, steps=1):
    nextStepN = currentN + STEP_GAP * steps
    return nextStepN





def get_printable_datetime():
    now = datetime.now()

    # Format the datetime as a string, including milliseconds
    formatted_now = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]
    return formatted_now

