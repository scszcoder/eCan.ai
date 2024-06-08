import json

import shutil
from datetime import datetime

from PySide6.QtGui import QStandardItem, QIcon

from bot.Logger import log3
import tzlocal

from bot.readSkill import runAllSteps
from globals.model import MissionModel

TIME_SLOT_MINS = 20
# Every bot has a run schedule which is specified in the following parameters
# start time for the day, example: 7am pacific time.
# start time uncertainty give start time could be some many minutes earlier or late.
# repetiton time and unit, example: run every
# number of retry: if somehow mission is failed, how many times to retry.
# retry wait time: minimum wait time between retrys (in minutes).
# mission parameters:
# mid,owner,botid,status,createon,(esd,ecd,asd,abd,aad,afd,acd),startt,esttime,runtime,cuspas,category,phrase,pseudoStore,pseudoBrand,pseudoASIN,type,config,skills,delDate
# cuspas: custom platform, application, site (for ex: windows, chrome, amazon)
class M_Assignment():
    def __init__(self):
        super().__init__()

        self.type = "NA"      # OPEN_SITE SEARCH_KW SEARCH_CATEGORY BROWSE_LIST BROWSE_DETAIL DISTRACT SHIP_ADDR GEN_LABEL_EBAY GEN_LABEL_EXT GEN_LABEL_EMAIL MARK_LABEL PRINT_LABEL
        self.skillId = "NA"
        self.status = "NA"
        self.search_kw = "NA"
        self.search_category = "NA"
        self.url = ""
        self.app = ""
        self.file = ""
        self.repeat = 0


class M_Action_Items():
    def __init__(self):
        super().__init__()

        self.tasks = []


class M_Private_Attributes():
    def __init__(self):
        super().__init__()
        self.item_number = "0"
        self.seller = "NA"
        self.brand = ""
        self.title = "NA"
        self.imglink = "NA"
        self.price = 0.0
        self.rating = ""
        self.rank = 0
        self.feedbacks = 0
        self.customer_id = ""
        self.customer_sm_id = ""
        self.customer_sm_platform = ""
        self.result = ""
        self.feedback_img_link = ""
        self.feedback_video_link = ""
        self.feedback_text = ""
        self.order_id = ""



    def setItem(self, inum, seller, title, imglink, rank, feedbacks, price):
        self.item_number = inum
        self.seller = seller
        self.title = title
        self.imglink = imglink
        self.rank = rank
        self.price = price
        # if price.replace(".", "").isnumeric():
        #     self.price = float(price)
        # else:
        #     self.price = 0.0

        self.feedbacks = feedbacks

    def setFeedbacks(self, fbs):
        self.feedbacks = fbs

    def setPrice(self, price):
        self.price = price

    def getFeedbacks(self):
        return self.feedbacks

    def getPrice(self):
        return self.price

    def loadJson(self, dj):
        self.item_number = dj["item_number"]
        self.seller = dj["seller"]
        self.title = dj["title"]
        self.imglink = dj["imglink"]
        self.price = dj["price"]
        self.rank = dj["rank"]
        self.feedbacks = dj["feedbacks"]
        self.result = dj["result"]

    def genJson(self):
        jd = {
                "item_number": self.item_number,
                "seller": self.seller,
                "title": self.title,
                "imglink": self.imglink,
                "price": self.price,
                "rank": self.rank,
                "feedbacks": self.feedbacks,
                "result": self.result
            }
        return jd

class M_Pub_Attributes():
    def __init__(self):
        super().__init__()
        self.missionId = -1
        self.ticket = 0
        self.owner = ""
        self.assign_type = "auto"         # user assigned or cloud auto assigned.
        self.search_kw = "yoga mats"               # search phrase
        self.search_cat = ""
        self.retry = 3                      # number of time this mission to repeated.
        self.n_retries = 0
        self.status = "NA"
        self.ms_type = "sell"             # buy/sell type of mission.
        self.config = "{}"
        self.bot_id = 0                   # the bot associated with a mission.
        self.esd = ""
        self.ecd = ""
        self.asd = ""
        self.aad = ""
        self.abd = ""
        self.afd = ""
        self.acd = ""
        self.esttime = 0                    # estimated start time.
        self.run_time = 0               #estimated run time.
        self.actual_run_time = 0
        self.createon = ""
        self.actual_start_time = ""
        self.actual_start_time_in_ms = 0
        self.actual_end_time = ""
        self.actual_end_time_in_ms = 0
        self.cuspas = "win,chrome,amz"
        self.app_exe = ""
        self.platform = "Windows"
        self.app = "chrome"
        self.site = "Amazon"
        self.site_html = "https://www.amazon.com"
        self.pseudo_store = ""
        self.pseudo_brand = ""
        self.pseudo_asin = ""
        self.del_date = ""
        self.skills = []
        self.current_sk_idx = 0
        self.platoon_id = ""
        self.buy_type = ""
        self.sell_type = ""


    def setType(self, atype, mtype):
        self.assign_type = atype
        self.ms_type = mtype

    def setBot(self, bid):
        self.bot_id = bid

    def setRetry(self, nRetry):
        self.retry = nRetry

    def setStatus(self, stat):
        self.status = stat

    def setSearch(self, kw, cat):
        self.search_kw = kw
        self.category = cat

    def setSkills(self, sks):
        self.skills = sks

    def addSkill(self, sk):
        self.skills.append(sk)

    def get_all_steps(self):
        # load skill file.
        return self.all_steps

    def loadJson(self, dj):
        self.missionId = dj["missionId"]
        self.ticket = dj["ticket"]
        self.ms_type = dj["ms_type"]
        self.retry = int(dj["repeat"])
        self.bot_id = dj["bot_id"]
        self.status = dj["status"]
        self.search_kw = dj["phrase"]
        self.search_cat = dj["category"]
        self.config = dj["config"]
        self.esd = dj["esd"]
        self.ecd = dj["ecd"]
        self.asd = dj["asd"]
        self.abd = dj["abd"]
        self.aad = dj["aad"]
        self.afd = dj["afd"]
        self.acd = dj["acd"]
        self.actual_run_time = dj["actual_run_time"]
        self.run_time = dj["est_run_time"]
        self.actual_start_time = dj["actual_start_time"]
        self.esttime = dj["est_start_time"]
        self.del_date = dj["del_date"]
        self.pseudo_store = dj["pseudo_store"]
        self.pseudo_brand = dj["pseudo_brand"]
        self.pseudo_asin = dj["pseudo_asin"]
        self.skills = dj["skills"]
        self.cuspas = dj["cuspas"]
        self.app_exe = dj["app_exe"]
        self.platoon_id = dj["platoon_id"]
        self.createon = dj["createon"]

    def loadNetRespJson(self, dj):
        self.missionId = dj["mid"]
        self.ticket = dj["ticket"]
        self.ms_type = dj["type"]
        self.owner = dj["owner"]
        self.retry = int(dj["trepeat"])
        self.bot_id = dj["botid"]
        self.status = dj["status"]
        self.search_kw = dj["phrase"]
        self.search_cat = dj["category"]
        self.config = dj["config"]
        self.esd = dj["esd"]
        self.ecd = dj["ecd"]
        self.asd = dj["asd"]
        self.abd = dj["abd"]
        self.aad = dj["aad"]
        self.afd = dj["afd"]
        self.acd = dj["acd"]
        self.run_time = dj["runtime"]
        self.esttime = dj["esttime"]
        self.del_date = dj["delDate"]
        self.pseudo_store = dj["pseudoStore"]
        self.pseudo_brand = dj["pseudoBrand"]
        self.pseudo_asin = dj["pseudoASIN"]
        self.skills = dj["skills"]
        self.cuspas = dj["cuspas"]
        self.createon = dj["createon"]
        cuspas = self.cuspas.split(",")
        self.platform = cuspas[0]
        self.app = cuspas[1]
        self.site = cuspas[2]

        if self.app == "ads":
            full_app_name = "AdsPower Global"
        else:
            full_app_name = self.app

        if "win" in self.cuspas:
            self.app_exe = shutil.which(full_app_name+".exe")
            if not self.app_exe:
                if self.app == "ads":
                    self.app_exe = 'C:/Program Files/AdsPower Global/AdsPower Global.exe'
                if self.app == "chrome":
                    self.app_exe = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
        else:
            self.app_exe = shutil.which(full_app_name)

        if "amz" in self.site.lower():
            self.site = "amazon"
            self.site_html = "https://www.amazon.com"
        elif "etsy" in self.cuspas.lower():
            self.site = "etsy"
            self.site_html = "https://www.etsy.com"
        elif "ebay" in self.cuspas.lower():
            self.site = "ebay"
            self.site_html = "https://www.ebay.com"
        elif "tiktok" in self.cuspas.lower():
            self.site = "tiktok"
            self.site_html = "https://www.tiktok.com"
        elif "youtube" in self.cuspas.lower():
            self.site = "youtube"
            self.site_html = "https://www.youtube.com"
        elif "facebook" in self.cuspas.lower():
            self.site = "facebook"
            self.site_html = "https://www.facebook.com"
        elif "instagram" in self.cuspas.lower():
            self.site = "youtube"
            self.site_html = "https://www.instagram.com"
        elif "temu" in self.cuspas.lower():
            self.site = "temu"
            self.site_html = "https://www.temu.com"
        elif "shein" in self.cuspas.lower():
            self.site = "shein"
            self.site_html = "https://www.shein.com"
        elif "walmart" in self.cuspas.lower():
            self.site = "walmart"
            self.site_html = "https://www.walmart.com"
        elif "ali" in self.cuspas.lower():
            self.site = "aliexpress"
            self.site_html = "https://www.aliexpress.com"

    def genJson(self):
        jd = {
                "missionId": self.missionId,
                "ticket": self.ticket,
                "assign_type": self.assign_type,
                "ms_type": self.ms_type,
                "config": self.config,
                "repeat": self.retry,
                "bot_id": self.bot_id,
                "status": self.status,
                "phrase": self.search_kw,
                "category": self.search_cat,
                "esd": self.esd,
                "ecd": self.ecd,
                "asd": self.asd,
                "abd": self.abd,
                "aad": self.aad,
                "afd": self.afd,
                "acd": self.acd,
                "pseudo_store": self.pseudo_store,
                "pseudo_brand": self.pseudo_brand,
                "pseudo_asin": self.pseudo_asin,
                "skills": self.skills,
                "cuspas": self.cuspas,
                "createon": self.createon,
                "actual_start_time": self.actual_start_time,
                "est_start_time": self.esttime,
                "actual_run_time": self.run_time,
                "est_run_time": self.run_time,
                "n_retries": 0,
                "del_date": self.del_date,
                "platoon_id": self.platoon_id,
                "app_exe": self.app_exe
            }
        return jd



#Notes:
# Bot will never visit the user profile page will reveals critical account information.
# review will be done manually, and the GUI should have a place for user to confirm review completion and record review date.
# same thing with the purchase? BOT can put itmes into the shopping cart, but should never complete the buy action, instead
# should let human operator complete that task. (again, to prevent sensitive information leak).
# BOT can do above only at user consent? let user click disclaimer and OK to continue.


# cloud's task - read screen and output clickable. -- input: screen image, task, settings (distraction ON?)
#              - schedule robot's daily routine? -- input: shuadan tasks, output: routines, task assignment and schedules.
#              - add/modify/delete/enable/disable bots. -- public profile, user instructed settings.
#              - register bot events. -- confirmation of buy , review (for human operator operated)
#              - query today's todos, and
#              - obtain account info.


# GUI blocks：
# main buttons: bots, missions, settings, log, my account, help, exit,
#
# create bot (icon, right click drop menu, delete, edit, enable/disable, clone)
#                (bot list panel, right click  menu: add bot, refresh, listing mode, icon mode, sort by creation date,
#                 sort by name, sort by location, sort by mf, sort by age, sort by race?)
# add/modify/delete bot to cloud
# schedule operation (crontab, at certain time, call cloud API to get fetch schedule of the day for all bots)
# create a todo-mission, (buttons: add mission, view pending missions, view completed missions, find missions by date? by asin? by keywords?)
# view today's action items for human operator.
# view local/cloud logs
# view account information (from cloud, billing, keys, order information)
# Settings: button scheduler -> view and set cloud scheduler tunable parameters;
# make multi-lingual - how?
# help --


class EBMISSION(QStandardItem):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.pubAttributes = M_Pub_Attributes()
        self.privateAttributes = M_Private_Attributes()
        self.tasks = M_Action_Items()
        self.parent_settings = {"mission_id": self.pubAttributes.missionId,
                                "session": self.parent.session,
                                "token": self.parent.tokens['AuthenticationResult']['IdToken'],
                                "uid": self.parent.uid}
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":"+self.pubAttributes.ms_type + ":"+self.pubAttributes.site)
        self.icon = QIcon(parent.file_resouce.mission_icon_path)
        self.setIcon(self.icon)
        self.setFont(parent.std_item_font)
        self.ads_xlsx_profile = ""

    def setADSXlsxProfile(self, axpf):
        self.ads_xlsx_profile = axpf

    def getADSXlsxProfile(self):
        return self.ads_xlsx_profile

    def setMissionIcon(self, icon):
        self.icon = icon
        self.setIcon(self.icon)

    def getMid(self):
        return self.pubAttributes.missionId

    def getParentSettings(self):
        return self.parent_settings

    def getParent(self):
        return self.parent
    def setMid(self, mid):
        self.pubAttributes.missionId = mid
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def getTicket(self):
        return self.pubAttributes.ticket

    def setTicket(self, ticket):
        self.pubAttributes.ticket = ticket

    def getSearchKW(self):
        return self.pubAttributes.search_kw

    def setSearchKW(self, skw):
        self.pubAttributes.search_kw = skw

    def getSearchCat(self):
        return self.pubAttributes.search_cat

    def setSearchCat(self, scat):
        self.pubAttributes.search_cat = scat

    def getRetry(self):
        return self.pubAttributes.retry

    def setRetry(self, retry):
        self.pubAttributes.retry = retry

    def getMtype(self):
        return self.pubAttributes.ms_type

    def setMtype(self, mtype):
        self.pubAttributes.ms_type = mtype
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def setBuyType(self, buy_type):
        self.pubAttributes.buy_type = buy_type

    def setSellType(self, stype):
        self.pubAttributes.sell_type = stype

    def getBuyType(self):
        return self.pubAttributes.buy_type

    def getSellType(self):
        return self.pubAttributes.sell_type

    def getAssignmentType(self):
        return self.pubAttributes.assign_type

    def setAssignmentType(self, astype):
        self.pubAttributes.assign_type = astype

    def getBid(self):
        return self.pubAttributes.bot_id

    def setBid(self, bid):
        self.pubAttributes.bot_id = bid
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def getStatus(self):
        return self.pubAttributes.status

    def setStatus(self, stat):
        self.pubAttributes.status = stat

    def setOwner(self, owner):
        self.pubAttributes.owner = owner

    def getOwner(self):
        return self.pubAttributes.owner

    def getBD(self):
        return self.pubAttributes.createon

    def setBD(self, bd):
        self.pubAttributes.createon = bd

    def getEsd(self):
        return self.pubAttributes.esd

    def setEsd(self, esd):
        self.pubAttributes.esd = esd

    def getEcd(self):
        return self.pubAttributes.ecd

    def setEcd(self, ecd):
        self.pubAttributes.ecd = ecd

    def getAsd(self):
        return self.pubAttributes.asd

    def setAsd(self, asd):
        self.pubAttributes.asd = asd

    def getAbd(self):
        return self.pubAttributes.abd

    def setAbd(self, abd):
        self.pubAttributes.abd = abd

    def getAad(self):
        return self.pubAttributes.aad

    def setAad(self, aad):
        self.pubAttributes.aad = aad

    def getAfd(self):
        return self.pubAttributes.afd

    def setAfd(self, afd):
        self.pubAttributes.afd = afd

    def getAcd(self):
        return self.pubAttributes.acd

    def setAcd(self, acd):
        self.pubAttributes.acd = acd

    def getActualStartTime(self):
        return self.pubAttributes.actual_start_time

    def setActualStartTime(self, ast):
        if type(ast) == int:
            self.pubAttributes.actual_start_time_in_ms = ast
            datetime_obj = datetime.fromtimestamp(ast, tz=tzlocal.get_localzone())
            # Format the datetime object as a string in AWS datetime format
            aws_datetime_str = datetime_obj.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            self.pubAttributes.actual_start_time = aws_datetime_str
        elif type(ast) == str:
            self.pubAttributes.actual_start_time = ast
            try:
                datetime_obj = datetime.strptime(ast, "%Y-%m-%dT%H:%M:%S.%fZ")
                # Convert the datetime object to epoch time in seconds
                epoch_time = int(datetime_obj.timestamp())
                self.pubAttributes.actual_start_time_in_ms = epoch_time
            except ValueError:
                datetime_obj = datetime.strptime("2050-01-01T00:00:00.00Z", "%Y-%m-%dT%H:%M:%S.%fZ")
                # Convert the datetime object to epoch time in seconds
                epoch_time = int(datetime_obj.timestamp())
                self.pubAttributes.actual_start_time_in_ms = epoch_time

    def getActualEndTime(self):
        return self.pubAttributes.actual_end_time

    def setActualEndTime(self, aet):
        if type(aet) == int:
            self.pubAttributes.actual_end_time_in_ms = aet
            datetime_obj = datetime.fromtimestamp(aet, tz=tzlocal.get_localzone())
            # Format the datetime object as a string in AWS datetime format
            aws_datetime_str = datetime_obj.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            self.pubAttributes.actual_end_time = aws_datetime_str
        elif type(aet) == str:
            self.pubAttributes.actual_end_time = aet
            try:
                datetime_obj = datetime.strptime(aet, "%Y-%m-%dT%H:%M:%S.%fZ")
                # Convert the datetime object to epoch time in seconds
                epoch_time = int(datetime_obj.timestamp())
                self.pubAttributes.actual_end_time_in_ms = epoch_time
            except ValueError:
                datetime_obj = datetime.strptime("2050-01-01T00:00:00.00Z", "%Y-%m-%dT%H:%M:%S.%fZ")
                # Convert the datetime object to epoch time in seconds
                epoch_time = int(datetime_obj.timestamp())
                self.pubAttributes.actual_end_time_in_ms = epoch_time

    def getActualRunTime(self):
        return self.pubAttributes.actual_run_time

    def setActualRunTime(self, art):
        self.actual_run_time = art

    def getEstimatedStartTime(self):
        return self.pubAttributes.esttime

    def setEstimatedStartTime(self, est):
        self.pubAttributes.esttime = est


    def getEstimatedRunTime(self):
        return self.pubAttributes.run_time

    def setEstimatedRunTime(self, ert):
        self.pubAttributes.run_time = ert

    def getCusPAS(self):
        return self.pubAttributes.cuspas

    def setCusPAS(self, cuspas):
        self.pubAttributes.cuspas = cuspas

    def getAppExe(self):
        return self.pubAttributes.app_exe

    def setAppExe(self, appexe):
        self.pubAttributes.app_exe = appexe

    def getPlatform(self):
        return self.pubAttributes.platform

    def setPlatform(self, platform):
        self.pubAttributes.platform = platform

    def getApp(self):
        return self.pubAttributes.app

    def setApp(self, app):
        self.pubAttributes.app = app

    def getSite(self):
        return self.pubAttributes.site

    def setSite(self, site):
        self.pubAttributes.site = site

    def setSiteHTML(self, sl):
        self.pubAttributes.site_html = sl

    def getSiteHTML(self):
        return self.pubAttributes.site_html

    def getPseudoStore(self):
        return self.pubAttributes.pseudo_store

    def setPseudoStore(self, pstore):
        self.pubAttributes.pseudo_store = pstore

    def getPseudoBrand(self):
        return self.pubAttributes.pseudo_brand

    def setPseudoBrand(self, pbrand):
        self.pubAttributes.pseudo_brand = pbrand

    def getPseudoASIN(self):
        return self.pubAttributes.pseudo_asin

    def setPseudoASIN(self, pasin):
        self.pubAttributes.pseudo_asin = pasin

    def getConfig(self):
        return self.pubAttributes.config

    def setConfig(self, cfg):
        self.pubAttributes.config = cfg

    def getSkills(self):
        return self.pubAttributes.skills

    def getResult(self):
        return self.privateAttributes.result

    def getOrderID(self):
        return self.privateAttributes.order_id

    def getFeedbackImgLink(self):
        return self.privateAttributes.feedback_img_link

    def getFeedbackVideoLink(self):
        return self.privateAttributes.feedback_video_link

    def getFeedbackText(self):
        return self.privateAttributes.feedback_text

    def setResult(self, result):
        self.privateAttributes.result = result
        if result is not None and result != "" and result != "{}":
            resultJson = json.loads(result)

            if "order_id" in resultJson:
                self.privateAttributes.order_id = resultJson["order_id"]

            if "feedback_img_link" in resultJson:
                self.privateAttributes.feedback_img_link = resultJson["feedback_img_link"]

            if "feedback_video_link" in resultJson:
                self.privateAttributes.feedback_video_link = resultJson["feedback_video_link"]

            if "feedback_text" in resultJson:
                self.privateAttributes.feedback_text = resultJson["feedback_text"]


    def getSkillNames(self):
        if self.pubAttributes.skills == "":
            skill_ids = []
        else:
            skill_ids = [int(skid_word) for skid_word in self.pubAttributes.skills.split(",")]
        log3("mission skill ids: "+json.dumps(skill_ids))
        sk_names = []
        for s in skill_ids:
            skidx = next((i for i, sk in enumerate(self.parent.skills) if sk.getSkid() == s), -1)
            if skidx >= 0:
                sk_names.append(self.parent.skills[skidx].getName())
        log3("skill names:"+json.dumps(sk_names))
        return sk_names

    def getPSKFileNames(self):
        if self.pubAttributes.skills == "":
            skill_ids = []
        else:
            skill_ids = [int(skid_word) for skid_word in self.pubAttributes.skills.split(",")]

        log3("mission skill ids: "+json.dumps(skill_ids))
        psk_names = []
        for s in skill_ids:
            skidx = next((i for i, sk in enumerate(self.parent.skills) if sk.getSkid() == s), -1)
            if skidx >= 0:
                psk_names.append(self.parent.skills[skidx].getPskFileName())

        log3("procedural skill names:"+json.dumps(psk_names))
        return psk_names

    def getCSKFileNames(self):
        if self.pubAttributes.skills == "":
            skill_ids = []
        else:
            skill_ids = [int(skid_word) for skid_word in self.pubAttributes.skills.split(",")]
        log3("mission skill ids: "+json.dumps(skill_ids))
        csk_names = []
        for s in skill_ids:
            skidx = next((i for i, sk in enumerate(self.parent.skills) if sk.getSkid() == s), -1)
            if skidx >= 0:
                csk_names.append(self.parent.skills[skidx].getCskFileName())

        log3("Content skill names:"+json.dumps(csk_names))
        return csk_names


    def setSkills(self, skills):
        self.pubAttributes.skills = skills

    def getDelDate(self):
        return self.pubAttributes.del_date

    def setDelDate(self, deldate):
        self.pubAttributes.del_date = deldate

    def getASIN(self):
        return self.privateAttributes.item_number

    def setASIN(self, asin):
        self.privateAttributes.item_number = asin

    def getStore(self):
        return self.privateAttributes.seller

    def setStore(self, store):
        self.privateAttributes.seller = store

    def getBrand(self):
        return self.privateAttributes.brand

    def setBrand(self, brand):
        self.privateAttributes.brand = brand

    def getImagePath(self):
        return self.privateAttributes.imglink

    def setImagePath(self, imgpath):
        self.privateAttributes.imglink = imgpath

    def getTitle(self):
        return self.privateAttributes.title

    def setTitle(self, title):
        self.privateAttributes.title = title

    def getRating(self):
        return self.privateAttributes.rating

    def setRating(self, rating):
        self.privateAttributes.rating = rating

    def getFeedbacks(self):
        return self.privateAttributes.feedbacks

    def setFeedbacks(self, fbs):
        self.privateAttributes.feedbacks = fbs

    def getPrice(self):
        return self.privateAttributes.price

    def getCustomerID(self):
        return self.privateAttributes.customer_id

    def setCustomerID(self, cid):
        self.privateAttributes.customer_id = cid

    def getCustomerSMID(self):
        return self.privateAttributes.customer_sm_id

    def setCustomerSMID(self, cid):
        self.privateAttributes.customer_sm_id = cid


    def getCustomerSMPlatform(self):
        return self.privateAttributes.customer_sm_platform

    def setCustomerSMPlatform(self, smp):
        self.privateAttributes.customer_sm_platform = smp

    def getPlatoonID(self):
        return self.pubAttributes.platoon_id

    def setPlatoon(self, pid):
        self.pubAttributes.platoon_id = pid

    def getNRetries(self):
        return self.pubAttributes.n_retries

    def setNRetries(self, nrt):
        self.pubAttributes.n_retries = nrt

    def setPrice(self, price):
        self.privateAttributes.price = price

    def updateDisplay(self):
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    # self.
    def setJsonData(self, ppJson):
        self.pubAttributes.loadJson(ppJson["pubAttributes"])
        self.privateAttributes.loadJson(ppJson["privateAttributes"])
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def genJson(self):
        jsd = {
                "ads_xlsx_profile": self.ads_xlsx_profile,
                "pubAttributes": self.pubAttributes.genJson(),
                "privateAttributes": self.privateAttributes.genJson()
                }
        return jsd

    def loadNetRespJson(self, jd):
        self.pubAttributes.loadNetRespJson(jd)
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def updateDisplay(self):
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def loadJson(self, jd):
        self.pubAttributes.loadJson(jd["pubAttributes"])
        self.privateAttributes.loadJson(jd["privateAttributes"])
        self.ads_xlsx_profile = jd["ads_xlsx_profile"]
        # self.tasks = jd["tasks"]
        # self.parent_settings["uid"] = jd["parent_settings"]["uid"]

    # load data from a row in sqlite DB.
    def loadDBData(self, dbd: MissionModel):
        self.setMid(dbd.mid)
        self.setTicket(dbd.ticket)
        self.setBid(dbd.botid)
        self.setOwner(dbd.owner)
        self.setStatus(dbd.status)
        self.setBD(dbd.createon)
        self.setEsd(dbd.esd)
        self.setEcd(dbd.ecd)
        self.setAsd(dbd.asd)
        self.setAbd(dbd.abd)
        self.setAad(dbd.aad)
        self.setAfd(dbd.afd)
        self.setAcd(dbd.acd)
        self.setActualStartTime(dbd.actual_start_time)
        self.setEstimatedStartTime(dbd.est_start_time)
        self.setActualRunTime(dbd.actual_runtime)
        self.setEstimatedRunTime(dbd.est_runtime)
        self.setNRetries(dbd.n_retries)
        self.setCusPAS(dbd.cuspas)
        self.setSearchCat(dbd.category)
        self.setSearchKW(dbd.phrase)
        self.setPseudoStore(dbd.pseudoStore)
        self.setPseudoBrand(dbd.pseudoBrand)
        self.setPseudoASIN(dbd.pseudoASIN)
        self.setMtype(dbd.type)
        self.setConfig(dbd.config)
        self.setSkills(dbd.skills)
        self.setDelDate(dbd.delDate)
        self.setASIN(dbd.asin)
        self.setStore(dbd.store)
        self.setBrand(dbd.brand)
        self.setImagePath(dbd.img)
        self.setTitle(dbd.title)
        self.setRating(dbd.rating)
        self.setFeedbacks(dbd.feedbacks)
        self.setPrice(dbd.price)
        self.setCustomerID(dbd.customer)
        self.setPlatoon(dbd.platoon)
        self.setResult(dbd.result)
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def loadXlsxData(self, jd):
        self.setMid(jd["mid"])
        self.setTicket(jd["ticket"])
        self.setBid(jd["botid"])
        self.setEsd(jd["esd"])
        self.setEcd(jd["ecd"])
        self.setEstimatedStartTime(jd["est"])
        self.setEstimatedRunTime(jd["ert"])
        self.setNRetries((jd["retries"]))
        self.setCusPAS(jd["platform"]+","+jd["app"]+","+jd["site"])
        self.setSearchCat(jd["search cat"])
        self.setSearchKW(jd["search phrase"])
        self.setPseudoStore(jd["pseudo store"])
        self.setPseudoBrand(jd["pseudo brand"])
        self.setPseudoASIN(jd["pseudo asin"])
        self.setMtype(jd["type"])
        self.setConfig(jd["config"])
        self.setSkills(jd["skills"])
        self.setASIN(jd["asin"])
        self.setStore(jd["store"])
        self.setBrand(jd["brand"])
        self.setImagePath(jd["img dir"])
        self.setTitle(jd["title"])
        self.setRating(jd["rating"])
        self.setFeedbacks(jd["feedbacks"])
        self.setPrice(jd["price"])
        self.setCustomerID(jd["customer"])
        self.setPlatoon(jd["platoon"])
        self.setResult(jd["result"])
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def loadJsonData(self, jd):
        self.pubAttributes.loadJson(jd["pubAttributes"])
        self.privateAttributes.loadJson(jd["privateAttributes"])



    async def run(self):
        run_result = None
        log3("running.....")
        for si in range(len(self.pubAttributes.skills)):
            log3("si:"+str(si))
            log3("skill:"+json.dumps(self.pubAttributes.skills[si]))
            self.pubAttributes.skills[si].loadSkill()
            log3("run all steps ....."+json.dumps(self.pubAttributes.skills[si].get_all_steps()))
            log3("settings:"+json.dumps(self.parent_settings))
            await runAllSteps(self.pubAttributes.skills[si].get_all_steps(), self.parent_settings)

        return run_result
