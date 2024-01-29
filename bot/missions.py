from WorkSkill import *
from readSkill import *
from datetime import datetime

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

    def genJson(self):
        jd = {
                "item_number": self.item_number,
                "seller": self.seller,
                "title": self.title,
                "imglink": self.imglink,
                "price": self.price,
                "rank": self.rank,
                "feedbacks": self.feedbacks
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
        self.config = ""
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
        self.skill = sks

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
        self.run_time = dj["est_run_time"]
        self.esttime = dj["est_start_time"]
        self.del_date = dj["delDate"]
        self.pseudo_store = dj["pseudoStore"]
        self.pseudo_brand = dj["pseudoBrand"]
        self.pseudo_asin = dj["pseudoASIN"]
        self.skills = dj["skills"]
        self.cuspas = dj["cuspas"]
        self.createon = dj["createon"]

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
        self.setText('mission' + str(self.getMid()))
        self.icon = QIcon(parent.mission_icon_path)
        self.setIcon(self.icon)
        self.setFont(parent.std_item_font)

    def getMid(self):
        return self.pubAttributes.missionId

    def getParentSettings(self):
        return self.parent_settings

    def setMid(self, mid):
        self.pubAttributes.missionId = mid
        self.setText('mission' + str(mid))

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
            datetime_obj = datetime.fromtimestamp(ast, tz=datetime.timezone.utc)
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
            datetime_obj = datetime.fromtimestamp(aet, tz=datetime.timezone.utc)
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

    def getSkillNames(self):
        if self.pubAttributes.skills == "":
            skill_ids = []
        else:
            skill_ids = [int(skid_word) for skid_word in self.pubAttributes.skills.split(",")]
        print("mission skill ids: ", skill_ids)
        sk_names = []
        for s in skill_ids:
            skidx = next((i for i, sk in enumerate(self.parent.skills) if sk.getSkid() == s), -1)
            if skidx >= 0:
                sk_names.append(self.parent.skills[skidx].getName())
        print("skill names:", sk_names)
        return sk_names

    def getPSKFileNames(self):
        if self.pubAttributes.skills == "":
            skill_ids = []
        else:
            skill_ids = [int(skid_word) for skid_word in self.pubAttributes.skills.split(",")]

        print("mission skill ids: ", skill_ids)
        psk_names = []
        for s in skill_ids:
            skidx = next((i for i, sk in enumerate(self.parent.skills) if sk.getSkid() == s), -1)
            if skidx >= 0:
                psk_names.append(self.parent.skills[skidx].getPskFileName())

        print("procedural skill names:", psk_names)
        return psk_names

    def getCSKFileNames(self):
        if self.pubAttributes.skills == "":
            skill_ids = []
        else:
            skill_ids = [int(skid_word) for skid_word in self.pubAttributes.skills.split(",")]
        print("mission skill ids: ", skill_ids)
        csk_names = []
        for s in skill_ids:
            skidx = next((i for i, sk in enumerate(self.parent.skills) if sk.getSkid() == s), -1)
            if skidx >= 0:
                csk_names.append(self.parent.skills[skidx].getCskFileName())

        print("Content skill names:", csk_names)
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
        self.setText('mission' + str(self.getMid()))

    # self.
    def setJsonData(self, ppJson):
        self.pubAttributes.loadJson(ppJson["pubAttributes"])
        self.privateAttributes.loadJson(ppJson["privateAttributes"])
        self.setText('mission' + str(self.getMid()))

    def setNetRespJsonData(self, nrjd):
        self.pubAttributes.loadNetRespJson(nrjd)
        self.setText('mission' + str(self.getMid()))

    def genJson(self):
        jsd = {
                "pubAttributes": self.pubAttributes.genJson(),
                "privateAttributes": self.privateAttributes.genJson()
                }
        print("GENERATED JSON:", jsd)
        print("after dump:", json.dumps(jsd))
        return jsd

    def loadNetRespJson(self, jd):
        self.pubAttributes.loadNetRespJson(jd)

    def updateDisplay(self):
        self.setText('mission' + str(self.getMid()))

    def loadJson(self, jd):
        self.pubAttributes.loadJson(jd["pubAttributes"])
        self.privateAttributes.loadJson(jd["privateAttributes"])
        # self.tasks = jd["tasks"]
        # self.parent_settings["uid"] = jd["parent_settings"]["uid"]

    # load data from a row in sqlite DB.
    # "mid": [0]
    # "ticket": [1]
    # "botid": [2]
    # "owner": [3]
    # "status": [4]
    # "createon": [5]
    # "esd": [6]
    # "ecd": [7]
    # "asd": [8]
    # "abd": [9]
    # "aad": [10]
    # "afd": [11]
    # "acd": [12]
    # "eststartt": [13]
    # "startt": [14]
    # "esttime": [15]
    # "runtime": [16]
    # "cuspas": [17]
    # "search_cat": [18]
    # "search_kw": [19]
    # "pseudo_store": [20]
    # "pseudo_brand": [21]
    # "pseudo_asin": [22]
    # "repeat": [23]
    # "mtype": [24]
    # "mconfig": [25]
    # "skills": [26]
    # "delDate": [27]
    # "asin": [28]
    # "store": [29]
    # "brand": [30]
    # "image": [31]
    # "title": [32]
    # "rating": [33]
    # "feedbacks": [34]
    # "customer": [35]
    # "platoon": [36]
    def loadDBData(self, dbd):
        self.setMid(dbd[0])
        self.setTicket(dbd[1])
        self.setBid(dbd[2])
        self.setOwner(dbd[3])
        self.setStatus(dbd[4])
        self.setBD(dbd[5])
        self.setEsd(dbd[6])
        self.setEcd(dbd[7])
        self.setAsd(dbd[8])
        self.setAbd(dbd[9])
        self.setAad(dbd[10])
        self.setAfd(dbd[11])
        self.setAcd(dbd[12])
        self.setActualStartTime(dbd[13])
        self.setEstimatedStartTime(dbd[14])
        self.setActualRunTime(dbd[15])
        self.setEstimatedRunTime(dbd[16])
        self.setNRetries((dbd[16]))
        self.setCusPAS(dbd[17])
        self.setSearchCat(dbd[18])
        self.setSearchKW(dbd[19])
        self.setPseudoStore(dbd[20])
        self.setPseudoBrand(dbd[21])
        self.setPseudoASIN(dbd[22])
        self.setMtype(dbd[23])
        self.setConfig(dbd[24])
        self.setSkills(dbd[25])
        self.setDelDate(dbd[26])
        self.setASIN(dbd[27])
        self.setStore(dbd[28])
        self.setBrand(dbd[29])
        self.setImagePath(dbd[30])
        self.setTitle(dbd[31])
        self.setRating(dbd[32])
        self.setFeedbacks(dbd[33])
        self.setPrice(dbd[34])
        self.setCustomerID(dbd[35])
        self.setPlatoon(dbd[36])


    async def run(self):
        run_result = None
        print("running.....")
        for si in range(len(self.pubAttributes.skills)):
            print("si:", si)
            print("skill:", self.pubAttributes.skills[si])
            self.pubAttributes.skills[si].loadSkill()
            print("run all steps .....", self.pubAttributes.skills[si].get_all_steps())
            print("settings:", self.parent_settings)
            runAllSteps(self.pubAttributes.skills[si].get_all_steps(), self.parent_settings)

        return run_result
