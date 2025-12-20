import json
import traceback
import shutil
from datetime import datetime

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
import tzlocal

import ast

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
        self.variations = ""
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
        self.feedback_instructions = ""
        self.feedback_title = ""
        self.feedback_text = ""
        self.feedback_rating = ""
        self.order_id = ""
        self.original_req_file = ""
        self.follow_seller = ""
        self.follow_price = 0.0
        self.fingerprint_profile = ""
        self.note = ""
        self.use_gift_card = True
        self.use_coupon = True
        self.gift_balance = 0.0
        self.gift_card_number = ""
        self.ccard_numer = ""
        self.seller_feedback_title = ""
        self.seller_feedback_text = ""
        self.run_result = {}


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

    def setNote(self, note):
        self.note = note

    def getNote(self):
        return self.note

    def setFeedbacks(self, fbs):
        self.feedbacks = fbs

    def setPrice(self, price):
        self.price = price

    def getFeedbacks(self):
        return self.feedbacks

    def getPrice(self):
        return self.price

    def getOrderId(self):
        return self.order_id

    def setOrderId(self, oid):
        self.order_id = oid

    def setReqFile(self, rf):
        self.original_req_file = rf

    def getReqFile(self):
        return self.original_req_file

    def setUseGiftCard(self, ugc):
        self.use_gift_card = ugc

    def getUseGiftCard(self):
        return self.use_gift_card

    def setUseCoupon(self, uc):
        self.use_coupon = uc

    def getUseCoupon(self):
        return self.use_coupon

    def setVCCardNumber(self, vcn):
        self.ccard_numer = vcn

    def getVCCardNumber(self):
        return self.ccard_numer

    def loadJson(self, dj):
        self.item_number = dj.get("item_number", "")
        self.seller = dj.get("seller", "")
        self.title = dj.get("title", "")
        self.imglink = dj.get("imglink", "")
        self.price = dj.get("price", 0.0)
        self.rank = dj.get("rank", 0)
        self.feedbacks = dj.get("feedbacks", 0)
        self.result = dj.get("result", "")


        self.feedback_img_link = dj.get("feedback_img_link", "")
        self.feedback_video_link = dj.get("feedback_video_link", "")
        self.feedback_instructions = dj.get("feedback_instructions", "")
        self.feedback_title =dj.get("feedback_title", "")
        self.feedback_text = dj.get("feedback_text", "")
        self.feedback_rating = dj.get("feedback_rating", 0.0)
        self.order_id = dj.get("order_id", "")
        self.customer_id = dj.get("customer_id", "")
        self.follow_price = dj.get("follow_price", 0.0)
        self.follow_seller = dj.get("follow_seller", "")
        self.fingerprint_profile = dj.get("fingerprint_profile", "")
        self.original_req_file = dj.get("original_req_file", "")

    def genJson(self):
        jd = {
                "item_number": self.item_number,
                "seller": self.seller,
                "brand": self.brand,
                "follow_seller": self.follow_seller,
                "title": self.title,
                "variations": self.variations,
                "imglink": self.imglink,
                "price": self.price,
                "follow_price": self.follow_price,
                "rank": self.rank,
                "rating": self.rating,
                "feedbacks": self.feedbacks,
                "result": self.result,
                "feedback_img_link": self.feedback_img_link,
                "feedback_video_link": self.feedback_video_link,
                "feedback_instructions": self.feedback_instructions,
                "feedback_text": self.feedback_text,
                "feedback_rating": self.feedback_rating,
                "order_id": self.order_id,
                "fingerprint_profile": self.fingerprint_profile,
                "original_req_file": self.original_req_file,
                "customer_id": self.customer_id
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
        self.repeat_type = "none"
        self.repeat_unit = "second"
        self.repeat_number = 1
        self.repeat_on = "now"
        self.repeat_until = "2050-01-01"
        self.repeat_last = "2020-01-01 00:00:00"
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
        self.skills = ""
        self.current_sk_idx = 0
        self.platoon_id = ""
        self.buy_type = ""
        self.sell_type = ""
        self.as_server = False
        self.error = ""
        self.intermediate_data = None
        self.agent_id = ""

    def getAsServer(self):
        return self.as_server

    def setAsServer(self, ias):
        self.as_server = ias

    def setType(self, atype, mtype):
        self.assign_type = atype
        self.ms_type = mtype

    def getType(self):
        return self.ms_type

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
        self.skills = self.skills+","+str(sk)

    def get_all_steps(self):
        # load skill file.
        return self.all_steps

    def setError(self, err):
        self.error = err

    def getError(self):
        return self.error

    def setIntermediateData(self,idata):
        self.intermediate_data = idata

    def setRepeatType(self, rt):
        self.repeat_type = rt

    def setRepeatUnit(self, ru):
        self.repeat_unit = ru

    def setRepeatNumber(self, rn):
        self.repeat_number = rn

    def setRepeatOn(self, ro):
        self.repeat_on = ro

    def setRepeatUntil(self, ru):
        self.repeat_until = ru

    def setRepeatLast(self, rl):
        self.repeat_last = rl

    def setAgentId(self, aid):
        self.agent_id = aid

    def getRepeatType(self):
        return self.repeat_type

    def getRepeatUnit(self):
        return self.repeat_unit

    def getRepeatNumber(self):
        return self.repeat_number

    def getRepeatOn(self):
        return self.repeat_on

    def getRepeatUntil(self):
        return self.repeat_until

    def getRepeatLast(self):
        return self.repeat_last

    def getAgentId(self):
        return self.agent_id

    def loadJson(self, dj):
        self.missionId = dj.get("missionId", 0)
        self.ticket = dj.get("ticket", 0)
        self.ms_type = dj.get("ms_type", "")
        self.retry = int(dj.get("repeat", 1))
        self.bot_id = dj.get("bot_id", 0)
        self.status = dj.get("status", "")
        self.search_kw =dj.get("phrase", "")
        self.search_cat = dj.get("category", "")
        self.config = dj.get("config", "{}")
        self.esd = dj.get("esd", "")
        self.ecd = dj.get("ecd", "")
        self.asd = dj.get("asd", "")
        self.abd = dj.get("abd", "")
        self.aad = dj.get("aad", "")
        self.afd = dj.get("afd", "")
        self.acd = dj.get("acd", "")
        self.actual_run_time = dj.get("actual_run_time", 0)
        self.run_time = dj.get("est_run_time", 0)
        self.actual_start_time = dj.get("actual_start_time", 0)
        self.esttime = dj.get("est_start_time", 0)
        self.del_date = dj.get("del_date", "")
        self.pseudo_store = dj.get("pseudo_store")
        self.pseudo_brand = dj.get("pseudo_brand")
        self.pseudo_asin = dj.get("pseudo_asin")
        skills = dj.get("skills", "")
        if isinstance(skills, list):
            lsskills = [str(sk).strip() for sk in skills]
            skills = ",".join(lsskills)
        self.skills = skills
        self.cuspas = dj.get("cuspas", "")
        self.app_exe = dj.get("app_exe", "")
        self.platoon_id = dj.get("platoon_id", "")
        self.createon = dj.get("createon", "")
        self.as_server = dj.get("as_server", "")

    def loadNetRespJson(self, dj):
        self.missionId = dj.get("mid", 0)
        self.ticket = dj.get("ticket", 0)
        self.ms_type = dj.get("type", "")
        self.owner = dj.get("owner", "")
        self.retry = int(dj.get("trepeat", 1))
        self.bot_id = dj.get("botid", 0)
        self.status = dj.get("status", "")
        self.search_kw = dj.get("phrase", "")
        self.search_cat = dj.get("category", "")
        self.config = dj.get("config", "{}")
        self.esd = dj.get("esd", "")
        self.ecd = dj.get("ecd", "")
        self.asd = dj.get("asd", "")
        self.abd = dj.get("abd", "")
        self.aad = dj.get("aad", "")
        self.afd = dj.get("afd", "")
        self.acd = dj.get("acd", "")
        self.run_time = dj.get("runtime", 0)
        self.esttime = dj.get("esttime", 0)
        self.del_date = dj.get("delDate", "")
        self.pseudo_store = dj.get("pseudoStore")
        self.pseudo_brand = dj.get("pseudoBrand")
        self.pseudo_asin = dj.get("pseudoASIN")
        skills = dj.get("skills", "")
        if isinstance(skills, list):
            lsskills = [str(sk).strip() for sk in skills]
            skills = ",".join(lsskills)
        self.skills = skills
        self.cuspas = dj.get("cuspas", "")
        self.createon = dj.get("createon", "")
        cuspas = self.cuspas.split(",")
        self.platform = cuspas[0]
        self.app = cuspas[1]
        self.site = cuspas[2]
        self.as_server = dj.get("as_server", False)

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
                "app_exe": self.app_exe,
                "as_server": self.as_server
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


class EBMISSION:
    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win
        self.pubAttributes = M_Pub_Attributes()
        self.privateAttributes = M_Private_Attributes()
        self.tasks = M_Action_Items()
        self.main_win_settings = {"mission_id": self.pubAttributes.missionId,
                                "session": self.main_win.session,
                                "token": self.main_win.get_auth_token(),
                                "uid": self.main_win.uid}
        # self.destroyed.connect(lambda: print(f"{self} is being destroyed"))
        self.retry_records=[]
        self.failure_context = {}
        self.text = ""

    def __del__(self):
        print(f"EBMISSION {self.getMid()} is being deleted")

    def setText(self, txt):
        self.text = txt

    def setFingerPrintProfile(self, axpf):
        self.privateAttributes.fingerprint_profile = axpf

    def getFingerPrintProfile(self):
        return self.privateAttributes.fingerprint_profile

    def getMid(self):
        return self.pubAttributes.missionId

    def getParentSettings(self):
        return self.main_win_settings

    def get_main_win(self):
        return self.main_win

    def setMid(self, mid):
        self.pubAttributes.missionId = mid

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
        """
        Parses and sets the configuration JSON.
        - Accepts a dictionary or a string-encoded dictionary.
        - Uses JSON decoding for safety.
        """
        try:
            self.pubAttributes.config = cfg
            # print("cfg:", cfg, type(cfg))

            # If cfg is already a dictionary, use it directly
            if isinstance(cfg, dict):
                cfgJson = cfg
            elif isinstance(cfg, str):
                try:
                    # First, attempt to load it as JSON directly
                    cfgJson = json.loads(cfg)
                except json.JSONDecodeError as e:
                    print(f"[WARNING] JSON decoding failed: {e}. Trying alternative parsing...")

                    try:
                        # If JSON decoding fails, try evaluating it safely
                        cfgJson = ast.literal_eval(cfg)
                    except (ValueError, SyntaxError) as e:
                        raise ValueError(f"Invalid config format: {cfg}. Error: {e}")
            else:
                raise TypeError(f"Unsupported config type: {type(cfg)}")

            # Safely update attributes based on the keys in cfgJson
            self.pubAttributes.repeat_type = cfgJson.get("repeat_type", self.pubAttributes.repeat_type)
            self.pubAttributes.repeat_number = cfgJson.get("repeat_number", self.pubAttributes.repeat_number)
            self.pubAttributes.repeat_unit = cfgJson.get("repeat_unit", self.pubAttributes.repeat_unit)
            self.pubAttributes.repeat_on = cfgJson.get("repeat_on", self.pubAttributes.repeat_on)
            self.pubAttributes.repeat_until = cfgJson.get("repeat_until", self.pubAttributes.repeat_until)
            self.pubAttributes.repeat_last = cfgJson.get("repeat_last", self.pubAttributes.repeat_last)

            print(f"[OK] Config loaded successfully: {len(cfgJson.get('searches', []))} searches.")

        except (json.JSONDecodeError, ValueError, SyntaxError, TypeError) as e:
            raise ValueError(f"[ERROR] Invalid config format: {cfg}. Error: {e}")

    # def setConfig(self, cfg):
    #     try:
    #         self.pubAttributes.config = cfg
    #         # print("cfg:", cfg, type(cfg))
    #
    #         # Determine the type of cfg and process accordingly
    #         if isinstance(cfg, str):
    #             try:
    #                 # Safely evaluate string as a Python dictionary
    #                 cfgJson = ast.literal_eval(cfg)
    #             except (ValueError, SyntaxError):
    #                 # Fallback to replacing single quotes with double quotes for JSON compatibility
    #                 cfgJson = json.loads(cfg.replace("'", '"'))
    #         else:
    #             cfgJson = cfg  # Assume it's already a dictionary or valid structure
    #
    #         # Safely update attributes based on the keys in cfgJson
    #         if "repeat_type" in cfgJson:
    #             self.pubAttributes.repeat_type = cfgJson["repeat_type"]
    #
    #         if "repeat_number" in cfgJson:
    #             self.pubAttributes.repeat_number = cfgJson["repeat_number"]
    #
    #         if "repeat_unit" in cfgJson:
    #             self.pubAttributes.repeat_unit = cfgJson["repeat_unit"]
    #
    #         if "repeat_on" in cfgJson:
    #             self.pubAttributes.repeat_on = cfgJson["repeat_on"]
    #
    #         if "repeat_until" in cfgJson:
    #             self.pubAttributes.repeat_until = cfgJson["repeat_until"]
    #
    #         if "repeat_last" in cfgJson:
    #             self.pubAttributes.repeat_last = cfgJson["repeat_last"]
    #
    #         # print("Config loaded: # searches", len(cfgJson.get('searches', [])))
    #
    #     except (json.JSONDecodeError, ValueError, SyntaxError) as e:
    #         raise ValueError(f"Invalid config format: {cfg}. Error: {e}")

        # self.pubAttributes.config = cfg
        # print("cfg:", cfg, type(cfg))
        # if isinstance(cfg, str):
        #     cfgJson = json.loads(cfg.replace("'", '"'))
        # else:
        #     cfgJson = cfg
        # if "repeat_type" in cfgJson:
        #     self.pubAttributes.repeat_type = cfgJson["repeat_type"]
        #
        # if "repeat_number" in cfgJson:
        #     self.pubAttributes.repeat_number = cfgJson["repeat_number"]
        #
        # if "repeat_unit" in cfgJson:
        #     self.pubAttributes.repeat_unit = cfgJson["repeat_unit"]
        #
        # if "repeat_on" in cfgJson:
        #     self.pubAttributes.repeat_on = cfgJson["repeat_on"]
        #
        # if "repeat_until" in cfgJson:
        #     self.pubAttributes.repeat_until = cfgJson["repeat_until"]
        #
        # if "repeat_last" in cfgJson:
        #     self.pubAttributes.repeat_last = cfgJson["repeat_last"]


    def addRepeatToConfig(self):
        cfgJson = json.loads(self.pubAttributes.config)
        cfgJson["repeat_type"] = self.pubAttributes.repeat_type
        cfgJson["repeat_number"] = self.pubAttributes.repeat_number
        cfgJson["repeat_unit"] = self.pubAttributes.repeat_unit
        cfgJson["repeat_on"] = self.pubAttributes.repeat_on
        cfgJson["repeat_until"] = self.pubAttributes.repeat_until
        cfgJson["repeat_last"] = self.pubAttributes.repeat_last
        self.pubAttributes.config = json.dumps(cfgJson)

    def getSkills(self):
        return self.pubAttributes.skills

    def getResult(self):
        return self.privateAttributes.result

    def getOrderID(self):
        return self.privateAttributes.order_id

    def setOrderID(self, oid):
        self.privateAttributes.order_id = oid

    def getFeedbackImgLink(self):
        return self.privateAttributes.feedback_img_link

    def getFeedbackVideoLink(self):
        return self.privateAttributes.feedback_video_link

    def getFeedbackText(self):
        return self.privateAttributes.feedback_text

    def getFeedbackTitle(self):
        return self.privateAttributes.feedback_title

    def setFeedbackText(self, bf):
        self.privateAttributes.feedback_text = bf
        self.pubAttributes.config["feedback_text"] = bf

    def setFeedbackTitle(self, tf):
        self.privateAttributes.feedback_title = tf
        self.pubAttributes.config["feedback_title"] = tf

    def getSellerFeedbackText(self):
        return self.privateAttributes.seller_feedback_text

    def getSellerFeedbackTitle(self):
        return self.privateAttributes.seller_feedback_title

    def setSellerFeedbackText(self, bf):
        self.privateAttributes.seller_feedback_text = bf
        self.pubAttributes.config["seller_feedback_text"] = bf

    def setSellerFeedbackTitle(self, tf):
        self.privateAttributes.seller_feedback_title = tf
        self.pubAttributes.config["seller_feedback_title"] = tf

    def getFeedbackRating(self):
        return self.privateAttributes.feedback_rating

    def getFeedbackInstructions(self):
        return self.privateAttributes.feedback_instructions

    def setResult(self, result):
        self.privateAttributes.result = result
        try:
            if isinstance(result, str):
                if result is not None and result.strip() and result != "{}":
                    resultJson = json.loads(result)
            else:
                resultJson = result

            if "order_id" in resultJson:
                self.privateAttributes.order_id = resultJson["order_id"]

            if "feedback_img_link" in resultJson:
                self.privateAttributes.feedback_img_link = resultJson["feedback_img_link"]

            if "feedback_video_link" in resultJson:
                self.privateAttributes.feedback_video_link = resultJson["feedback_video_link"]

            if "feedback_text" in resultJson:
                self.privateAttributes.feedback_text = resultJson["feedback_text"]


        except Exception as e:
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSetResut:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSetResut traceback information not available:" + str(e)


    def getSkillNames(self):
        if self.pubAttributes.skills == "":
            skill_ids = []
        else:
            skill_ids = [int(skid_word) for skid_word in self.pubAttributes.skills.split(",")]
        logger.debug("mission skill ids: "+json.dumps(skill_ids))
        sk_names = []
        for s in skill_ids:
            skidx = next((i for i, sk in enumerate(self.main_win.skills) if sk.getSkid() == s), -1)
            if skidx >= 0:
                sk_names.append(self.main_win.skills[skidx].getName())
        logger.debug("skill names:"+json.dumps(sk_names))
        return sk_names

    def getPSKFileNames(self):
        if self.pubAttributes.skills == "":
            skill_ids = []
        else:
            skill_ids = [int(skid_word) for skid_word in self.pubAttributes.skills.split(",")]

        logger.debug("mission skill ids: "+json.dumps(skill_ids))
        psk_names = []
        for s in skill_ids:
            skidx = next((i for i, sk in enumerate(self.main_win.skills) if sk.getSkid() == s), -1)
            if skidx >= 0:
                psk_names.append(self.main_win.skills[skidx].getPskFileName())

        logger.debug("procedural skill names:"+json.dumps(psk_names))
        return psk_names

    def getCSKFileNames(self):
        if self.pubAttributes.skills == "":
            skill_ids = []
        else:
            skill_ids = [int(skid_word) for skid_word in self.pubAttributes.skills.split(",")]
        logger.debug("mission skill ids: "+json.dumps(skill_ids))
        csk_names = []
        for s in skill_ids:
            skidx = next((i for i, sk in enumerate(self.main_win.skills) if sk.getSkid() == s), -1)
            if skidx >= 0:
                csk_names.append(self.main_win.skills[skidx].getCskFileName())

        logger.debug("Content skill names:"+json.dumps(csk_names))
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
        if not asin:
            asin = ""
        self.privateAttributes.item_number = asin
        self.pubAttributes.pseudo_asin = self.main_win.generateShortHash(asin)

    def getStore(self):
        return self.privateAttributes.seller

    def setStore(self, store):
        if not store:
            store = ""
        self.privateAttributes.seller = store
        self.pubAttributes.pseudo_store = self.main_win.generateShortHash(store)

    def getBrand(self):
        return self.privateAttributes.brand

    def setBrand(self, brand):
        if not brand:
            brand = ""
        self.privateAttributes.brand = brand
        self.pubAttributes.pseudo_brand = self.main_win.generateShortHash(brand)

    def getImagePath(self):
        return self.privateAttributes.imglink

    def setImagePath(self, imgpath):
        self.privateAttributes.imglink = imgpath

    def getTitle(self):
        return self.privateAttributes.title

    def setTitle(self, title):
        self.privateAttributes.title = title

    def getVariations(self):
        return self.privateAttributes.variations

    def setVariations(self, variations):
        self.privateAttributes.variations = variations

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

    def setError(self, err):
        self.pubAttributes.setError(err)

    def getError(self):
        self.pubAttributes.getError()

    def setIntermediateData(self, idata):
        self.pubAttributes.setIntermediateData(idata)

    def getNRetries(self):
        return self.pubAttributes.n_retries

    def setNRetries(self, nrt):
        if isinstance(nrt, str):
            self.pubAttributes.n_retries = int(nrt)
        else:
            self.pubAttributes.n_retries = nrt

    def setPrice(self, price):
        self.privateAttributes.price = price

    def setFollowSeller(self, fseller):
        self.privateAttributes.follow_seller = fseller

    def setFollowPrice(self, fprice):
        self.privateAttributes.follow_price = fprice

    def getFollowSeller(self):
        return self.privateAttributes.follow_seller

    def getFollowPrice(self):
        return self.privateAttributes.follow_price

    def updateDisplay(self):
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def getAsServer(self):
        return self.pubAttributes.as_server

    def setAsServer(self, ias):
        self.pubAttributes.as_server = ias

    def setReqFile(self,rf):
        self.privateAttributes.setReqFile(rf)

    def getType(self):
        return self.pubAttributes.getType()

    def setRepeatType(self, rt):
        self.pubAttributes.repeat_type = rt

    def setRepeatUnit(self, ru):
        self.pubAttributes.repeat_unit = ru

    def setRepeatNumber(self, rn):
        self.pubAttributes.repeat_number = rn

    def setRepeatOn(self, ro):
        self.pubAttributes.repeat_on = ro

    def setRepeatUntil(self, ru):
        self.pubAttributes.repeat_until = ru

    def setRepeatLast(self, rl):
        self.pubAttributes.repeat_last = rl

    def updateRepeatLast(self):
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.pubAttributes.repeat_last = current_time_str

    def getRepeatType(self):
        return self.pubAttributes.repeat_type

    def getRepeatUnit(self):
        return self.pubAttributes.repeat_unit

    def getRepeatNumber(self):
        return self.pubAttributes.repeat_number

    def getRepeatOn(self):
        return self.pubAttributes.repeat_on

    def getRepeatUntil(self):
        return self.pubAttributes.repeat_until

    def getRepeatLast(self):
        return self.pubAttributes.repeat_last

    def setNote(self, note):
        self.privateAttributes.note = note

    def getNote(self):
        return self.privateAttributes.note

    def setReqFile(self, rf):
        self.privateAttributes.original_req_file = rf

    def getReqFile(self):
        return self.privateAttributes.original_req_file

    def setUseGiftCard(self, ugc):
        self.privateAttributes.use_gift_card = ugc

    def getUseGiftCard(self):
        return self.privateAttributes.use_gift_card

    def setUseCoupon(self, uc):
        self.privateAttributes.use_coupon = uc

    def getUseCoupon(self):
        return self.privateAttributes.use_coupon

    def setGiftBalance(self, ugc):
        self.privateAttributes.gift_balance = ugc

    def getGiftBalance(self):
        return self.privateAttributes.gift_balance


    def setGiftCardNumber(self, ugc):
        self.privateAttributes.gift_card_number = ugc

    def getGiftCardNumber(self):
        return self.privateAttributes.gift_card_number

    def setVCCardNumber(self, vcn):
        self.privateAttributes.ccard_numer = vcn
        self.pubAttributes.config["ccard_numer"] = vcn

    def getVCCardNumber(self):
        return self.privateAttributes.ccard_numer

    def getLastActionLink(self):
        return self.lastActionLink

    def setLastActionLink(self, link):
        self.lastActionLink = link

    def recordStartTime(self):
        st = datetime.now().strftime("%Y-%m-%d %H-%M-%S.%f")
        self.setActualStartTime(st)

    def recordEndTime(self):
        et = datetime.now().strftime("%Y-%m-%d %H-%M-%S.%f")
        if "Completed" in self.getStatus():
            self.setActualEndTime(et)
        else:
            self.retry_records.append({"ast": self.getActualStartTime(), "aet": et, "status": self.getStatus()})

    def setRunResult(self, result):
        self.privateAttributes.run_result = result

    def getRunResult(self):
        return self.privateAttributes.run_result

    def getRetryRecords(self):
        return self.retry_records

    def recordFailureContext(self, next_step_index, step, run_stack, step_stat, last_screen_shot_file):
        self.failure_context = {
            "step": step,
            "next_step_index": next_step_index,
            "run_stack": run_stack,
            "run_stat": step_stat,
            "last_screen_shot_file": last_screen_shot_file
        }

    def getFailureContext(self):
        return self.failure_context

    def getAgentId(self):
        return self.pubAttributes.agent_id

    def setAgentId(self, aid):
        self.pubAttributes.agent_id = aid

    # self.
    def setJsonData(self, ppJson):
        self.pubAttributes.loadJson(ppJson["pubAttributes"])
        self.privateAttributes.loadJson(ppJson["privateAttributes"])
        self.setText('mission' + str(self.getMid()) + ":Bot" + str(self.getBid()) + ":" + self.pubAttributes.ms_type + ":"+self.pubAttributes.site)

    def genJson(self):
        jsd = {
                "fingerprint_profile": self.privateAttributes.fingerprint_profile,
                "pubAttributes": self.pubAttributes.genJson(),
                "privateAttributes": self.privateAttributes.genJson()
                }
        return jsd

    def loadNetRespJson(self, jd):
        self.pubAttributes.loadNetRespJson(jd)

    def loadJson(self, jd):
        self.pubAttributes.loadJson(jd["pubAttributes"])
        self.privateAttributes.loadJson(jd["privateAttributes"])
        self.privateAttributes.fingerprint_profile = jd["fingerprint_profile"]
        # self.tasks = jd["tasks"]
        # self.main_win_settings["uid"] = jd["main_win_settings"]["uid"]

    def loadXlsxData(self, dj):
        self.setMid(dj.get("mid", 0))
        self.setTicket(dj.get("ticket", 0))
        self.setBid(dj.get("botid", 0))
        self.setEsd(dj.get("esd", ""))
        self.setEcd(dj.get("ecd", ""))
        self.setEstimatedStartTime(dj.get("est", 0))
        self.setEstimatedRunTime(dj.get("ert", 0))
        self.setNRetries((dj.get("retries", 0)))
        self.setCusPAS(dj.get("platform", "win")+","+dj.get("app", "ads")+","+dj.get("site", "amz"))
        self.setSearchCat(dj.get("search cat", ""))
        self.setSearchKW(dj.get("phrase", ""))
        # self.setPseudoStore(self.main_win.generateShortHash(dj.get("pseudoStore")))
        # self.setPseudoBrand(self.main_win.generateShortHash(dj.get("pseudoBrand")))
        # self.setPseudoASIN(self.main_win.generateShortHash(dj.get("pseudoASIN")))
        self.setMtype(dj.get("type", ""))
        self.setConfig(dj.get("config", "{}"))
        self.setSkills(dj.get("skills", "101"))
        self.setASIN(dj.get("asin", ""))                #this will auto set psudo_asin
        self.setStore(dj.get("stores", "NoneStore"))     #this will auto set psudo_store
        self.setBrand(dj.get("brand", "NoneBrand"))     #this will auto set psudo_brand
        self.setImagePath(dj.get("img", ""))
        self.setTitle(dj.get("title", ""))
        self.setVariations(dj.get("variations", ""))
        self.setRating(dj.get("rating", 0.0))
        self.setFeedbacks(dj.get("feedbacks", 0))
        self.setPrice(dj.get("price", 0.0))
        self.setCustomerID(dj.get("customer", ""))
        self.setPlatoon(dj.get("platoon", ""))
        self.setResult(dj.get("result", ""))
        self.setFollowSeller(dj.get("follow_seller", ""))
        self.setFollowPrice(dj.get("follow_price", 0.0))
        self.setFingerPrintProfile(dj.get("fingerprint_profile", ""))
        self.setAsServer(dj.get("as_server", False))
        self.setReqFile(dj.get("original_req_file", ""))

    def loadBusinessesDBData(self, dj):
        mid = dj.get("mid", 0)
        if mid == None or mid == "":
            mid = 0
        uid = dj.get("uid", 0)
        if uid == None or uid == "":
            uid = 0
        else:
            uid = int(uid)

        self.setMid(mid)
        self.setTicket(uid)
        self.setCusPAS(dj.get("platform", "win")+","+dj.get("app", "ads")+","+dj.get("site", "amz"))
        self.setSearchKW(dj.get("order_search_term", ""))
        # self.setPseudoStore(self.main_win.generateShortHash(dj.get("order_seller")))
        # self.setPseudoBrand(self.main_win.generateShortHash(dj.get("order_brand")))
        # self.setPseudoASIN(self.main_win.generateShortHash(dj.get("order_asin")))
        self.setMtype(dj.get("service1_type", ""))
        self.setSkills(dj.get("skills", "117"))
        self.setBD(dj.get("order_date"))
        self.setEsd(dj.get("order_date"))
        self.setNote(dj.get("order_note"))
        self.setASIN(dj.get("order_asin", ""))          # this will auto set pseudo_asin
        self.setStore(dj.get("order_seller"))           # this will auto set pseudo_store
        self.setBrand(dj.get("order_brand"))            # this will auto set pseudo_brand
        self.setTitle(dj.get("order_title", ""))
        self.setVariations(dj.get("order_variations", ""))
        self.setPrice(dj.get("order_price", 0.0))
        self.setCustomerID(dj.get("order_contact", ""))
        self.setFollowSeller(dj.get("order_follow_seller", ""))
        self.setFollowPrice(dj.get("order_follow_price", 0.0))
        self.setReqFile(dj.get("order_source", ""))


    def loadAMZReqData(self,jd, reqFile):
        self.setApp("ads")
        self.setSite("amz")
        self.setSearchKW(jd["search term"])

        if jd["fb1 type"] == "" or jd["fb type"] == "免评":
            self.setMtype("buy")
        elif jd["fb1 type"] == "点星":
            self.setMtype("goodRating")
        elif jd["fb1 type"] == "好评":
            self.setMtype("goodFB")

        self.setASIN(jd["asin"])        # this will auto set psudo_asin
        self.setStore(jd["stores"])      # this will auto set psudo_store
        self.setBrand(jd["brand"])      # this will auto set psudo_brand
        self.setTitle(jd["title"])

        # self.setPseudoASIN(self.main_win.generateShortHash(jd["asin"]))
        # self.setPseudoStore(self.main_win.generateShortHash(jd["stores"]))
        # self.setPseudoBrand(self.main_win.generateShortHash(jd["brand"]))

        self.setVariations(jd["variations"])
        if "rating" in jd:
            self.setRating(jd["rating"])

        if "feedbacks" in jd:
            self.setFeedbacks(jd["feedbacks"])

        self.setPrice(jd["price"])
        self.setCustomerID(jd["email"])
        self.setFollowSeller(jd["follow seller"])
        self.setFollowPrice(jd["follow price"])
        self.setReqFile(reqFile)


    def loadJsonData(self, jd):
        self.pubAttributes.loadJson(jd["pubAttributes"])
        self.privateAttributes.loadJson(jd["privateAttributes"])

    def genSummeryJson(self):
        jsd = {
            "mid": self.getMid(),
            "botid": self.getBid(),
            "type": self.getMtype(),
            "est_start_time": self.getEstimatedStartTime(),
            "est_run_time": self.getEstimatedRunTime(),
            "actual_start_time": self.getActualStartTime(),
            "actual_end_time": self.getActualEndTime(),
            "status": self.getStatus(),
            "retries": self.retry_records,
            "cause": self.failure_context
        }
        return jsd


        return run_result
