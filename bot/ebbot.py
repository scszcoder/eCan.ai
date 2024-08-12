import asyncio
import platform
import json
from datetime import datetime, date
from bot.Logger import log3
from PySide6.QtGui import QStandardItem, QIcon

from common.models.bot import BotModel


# Every bot has a run schedule which is specified in the following parameters
# start time for the day, example: 7am pacific time.
# start time uncertainty give start time could be some many minutes earlier or late.
# repetiton time and unit, example: run every
# number of retry: if somehow mission is failed, how many times to retry.
# retry wait time: minimum wait time between retrys (in minutes).
class BOT_Schedule():
    def __init__(self):
        super().__init__()

        self.repetition_unit = "day"
        self.repetition_number = "90"
        self.start_time = "071530Z-8"
        self.start_time_uncertainty = 5
        self.num_retry = 3
        self.retry_wait_min = 1


# Here are supported tasks and their attributes.
# RANDOM_BROWSE, KW_SEARCH, CAT_SEARCH, BUY, RETURN, FEEDBACK
# common attributes:
#        duration: how long to work (minutes)
#
class BOT_Task():
    def __init__(self):
        super().__init__()

        self.name = "RANDOM_BROWSE "
        self.duration = "10"
        self.distraction = False
        self.distraction_time_limit = 10


class BOT_SETTINGS():
    def __init__(self):
        super().__init__()

        self.platform = platform.platform()
        self.os = platform.system()
        self.machine = platform.machine()
        self.browser = "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"
        self.tasks = []
        self.schedule = BOT_Schedule()

        # self.

    def loadJson(self, dj):
        if "platform" in dj:
            self.platform = dj["platform"]
        if "os" in dj:
            self.os = dj["os"]
        if "browser" in dj:
            self.browser = dj["browser"]
        if "machine" in dj:
            self.machine = dj["machine"]

    def setComputer(self, os, machine, browser):
        self.os = os
        self.machine = machine
        self.browser = browser

    def genJson(self):
        jd = {
            "platform": self.platform,
            "os": self.os,
            "machine": self.machine,
            "browser": self.browser
        }
        log3("genJson:" + json.dumps(jd))
        return jd


class BOT_PRIVATE_PROFILE():
    def __init__(self):
        super().__init__()

        self.name = ""
        self.first_name = "John"
        self.last_name = "Smith"
        self.email = ""
        self.email_pw = ""
        self.phone = ""
        self.backup_email = ""
        self.backup_email_site = ""
        self.acct_pw = ""
        self.file = ""
        self.birthday = ""
        self.birthdaydt = None
        self.addr = ""
        self.addrl1 = ""
        self.addrl2 = ""
        self.addrcity = ""
        self.addrstate = ""
        self.addrzip = ""
        self.shipping_addr = ""
        self.shipping_addrl1 = ""
        self.shipping_addrl2 = ""
        self.shipping_addrcity = ""
        self.shipping_addrstate = ""
        self.shipping_addrzip = ""
        self.createon = ""

    def setFirstLastName(self, fn, ln):
        self.name = fn + " " + ln
        self.first_name = fn
        self.last_name = ln

    def setName(self, nm):
        self.name = nm
        if nm is None:
            self.first_name = ""
            self.last_name = ""
        else:
            nm_words = nm.split()
            if len(nm_words) >= 2:
                self.first_name = nm_words[0]
                self.last_name = nm_words[len(nm_words) - 1]
            elif len(nm_words) == 0:
                self.first_name = ""
                self.last_name = ""
            else:
                self.first_name = nm_words[0]
                self.last_name = ""

    def setAddr(self, l1, l2, city, state, zip):
        self.addrl1 = l1
        if not l2:
            l2 = ""
        self.addrl2 = l2
        self.addrcity = city
        self.addrstate = state
        self.addrzip = zip
        self.addr = l1 + "\n" + l2 + "\n" + city + ", " + state + " " + zip

    def setAddr1(self, addr):
        self.addr = addr
        addr_lines = addr.split("\n")
        print("addr:", addr)
        print("addr lines#", len(addr_lines))
        if len(addr_lines) == 3:
            self.addrl1 = addr_lines[0]
            self.addrl2 = addr_lines[1]
            fields = addr_lines[2].split(",")
            self.addrcity = fields[0].strip()
            self.addrstate = fields[1].split()[0].strip()
            self.addrzip = fields[1].split()[1].strip()

    def setShippingAddr(self, l1, l2, city, state, zip):
        self.shipping_addrl1 = l1
        if not l2:
            l2 = ""
        self.shipping_addrl2 = l2
        self.shipping_addrcity = city
        self.shipping_addrstate = state
        self.shipping_addrzip = zip
        self.shipping_addr = l1 + "\n" + l2 + "\n" + city + ", " + state + " " + zip

    def setShippingAddr1(self, addr):
        self.shipping_addr = addr

        addr_lines = addr.split("\n")
        print("saddr:", addr)
        print("saddr lines#", len(addr_lines))

        if len(addr_lines) == 3:
            self.shipping_addrl1 = addr_lines[0]
            self.shipping_addrl2 = addr_lines[1]
            fields = addr_lines[2].split(",")
            self.shipping_addrcity = fields[0].strip()
            self.shipping_addrstate = fields[1].split()[0].strip()
            self.shipping_addrzip = fields[1].split()[1].strip()

    def setPhone(self, phone):
        self.phone = phone

    def setEmail(self, em):
        self.email = em

    def setEPW(self, epw):
        self.email_pw = epw

    def setBackEmail(self, em):
        self.backup_email = em

    def setEBPW(self, epw):
        self.acct_pw = epw

    def setBackEmailSite(self, site):
        self.backup_email_site = site

    def setBirthday(self, bdtxt):
        log3("SETTING BIRTHDAY:" + bdtxt)
        self.privateProfile.birthday = bdtxt
        format = '%Y-%m-%d'

        # convert from string format to datetime format
        self.privateProfile.birthdaydt = datetime.strptime(bdtxt, format)

    def getBirthday(self):
        return self.privateProfile.birthdaydt

    def getCreateOn(self):
        return self.createon

    def setCreateOn(self, createon):
        self.createon = createon

    def setAcct(self, email, epw, phone, back_email, acct_pw, back_email_site):
        self.email = email
        self.email_pw = epw
        self.phone = phone
        self.backup_email = back_email
        self.backup_email_site = back_email_site
        self.acct_pw = acct_pw


    def loadJson(self, dj):
        self.first_name = dj["first_name"]
        self.last_name = dj["last_name"]
        self.email = dj["email"]
        self.email_pw = dj["email_pw"]
        self.phone = dj["phone"]
        self.backup_email = dj["backup_email"]
        self.acct_pw = dj["acct_pw"]
        self.backup_email_site = dj["backup_email_site"]
        self.birthday = dj["birthday"]
        self.addrl1 = dj["addrl1"]
        self.addrl2 = dj["addrl2"]
        self.addrcity = dj["addrcity"]
        self.addrstate = dj["addrstate"]
        self.addrzip = dj["addrzip"]
        self.shipping_addrl1 = dj["shipaddrl1"]
        self.shipping_addrl2 = dj["shipaddrl2"]
        self.shipping_addrcity = dj["shipaddrcity"]
        self.shipping_addrstate = dj["shipaddrstate"]
        self.shipping_addrzip = dj["shipaddrzip"]


    def genJson(self):
        jd = {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "email_pw": self.email_pw,
            "phone": self.phone,
            "backup_email": self.backup_email,
            "backup_email_site": self.backup_email_site,
            "acct_pw": self.acct_pw,
            "birthday": self.birthday,
            "addrl1": self.addrl1,
            "addrl2": self.addrl2,
            "addrcity": self.addrcity,
            "addrstate": self.addrstate,
            "addrzip": self.addrzip,
            "shipaddrl1": self.shipping_addrl1,
            "shipaddrl2": self.shipping_addrl2,
            "shipaddrcity": self.shipping_addrcity,
            "shipaddrstate": self.shipping_addrstate,
            "shipaddrzip": self.shipping_addrzip
        }
        return jd


class BOT_PUB_PROFILE():
    def __init__(self):
        super().__init__()
        self.bid = 0
        self.pseudo_name = ""
        self.pseudo_first_name = ""
        self.pseudo_last_name = ""
        self.nick_name = ""
        self.location = ""
        self.pubbirthday = ""
        self.age = ""
        self.gender = ""
        self.interests = ""
        self.roles = ""
        self.owner = ""
        self.levels = ""
        self.status = "active"
        self.delDate = "2121-01-01"
        self.levelStart = ""
        self.vid = ""
        self.vehicle = ""


    def setBid(self, bid):
        self.bid = bid

    def setOwner(self, owner):
        self.owner = owner

    def setRoles(self, roles):
        self.roles = roles

    def setPseudoFirstLastName(self, pfn, pln):
        self.pseudo_first_name = pfn
        self.pseudo_last_name = pln
        self.pseudo_name = pfn + " " + pln

    def setPseudoName(self, pn):
        if pn is None:
            self.pseudo_first_name = ""
            self.pseudo_last_name = ""
        else:
            name_words = pn.split()
            log3("name_words" + str(len(name_words)) + ":" + json.dumps(name_words))
            if len(name_words) >= 2:
                self.pseudo_first_name = name_words[0]
                self.pseudo_last_name = name_words[len(name_words) - 1]
            elif len(name_words) == 1:
                self.pseudo_first_name = name_words[0]
                self.pseudo_last_name = ""
            else:
                self.pseudo_first_name = ""
                self.pseudo_last_name = ""
        self.pseudo_name = pn

    def setNickName(self, nn):
        self.nick_name = nn

    def setLoc(self, loc):
        self.location = loc

    def setAgePubBirthday(self, age_txt):
        age = int(age_txt)
        if age != self.age:
            delta_age = age - self.age
            if delta_age > 0:
                self.pubbirthdaydt = self.pubbirthdaydt + datetime.timedelta(days=delta_age)
            else:
                self.pubbirthdaydt = self.pubbirthdaydt + datetime.timedelta(days=-delta_age)

            self.pubbirthday = self.pubbirthdaydt.strftime("%Y-%m-%d")

    def setLevels(self, levels):
        self.levels = levels

    def setLevelStart(self, ls):
        self.levelStart = ls

    def setDelDate(self, deldate):
        self.delDate = deldate

    def setGender(self, gender):
        self.gender = gender

    def setPubBirthday(self, pbbd):
        self.pubbirthday = pbbd
        format = '%Y-%m-%d'
        try:
            # convert from string format to datetime format
            self.pubbirthdaydt = datetime.strptime(pbbd, format)

            today = date.today()
            self.age = today.year - self.pubbirthdaydt.year - (
                        (today.month, today.day) < (self.pubbirthdaydt.month, self.pubbirthdaydt.day))
        except ValueError:
            self.pubbirthday = "2000-01-01"
            self.pubbirthdaydt = datetime.strptime("2000-01-01", format)
            today = date.today()
            self.age = today.year - self.pubbirthdaydt.year - (
                    (today.month, today.day) < (self.pubbirthdaydt.month, self.pubbirthdaydt.day))

    def setPersonal(self, gender):
        self.gender = gender

    def setInterests(self, interests):
        self.interests = interests

    def setStatus(self, stat):
        self.status = stat

    def setVid(self, vid):
        self.vid = vid

    def setVehicle(self, vehicle):
        self.vehicle = vehicle

    def getVid(self):
        return self.vid

    def getVehicle(self):
        return self.vehicle


    def loadJson(self, dj):
        self.bid = dj["bid"]
        self.nick_name = dj["pseudo_nick_name"]
        self.pseudo_name = dj["pseudo_name"]
        self.location = dj["location"]
        self.pubbirthday = dj["pubbirthday"]
        self.gender = dj["gender"]
        self.interests = dj["interests"]
        self.roles = dj["roles"]
        self.levels = dj["levels"]
        self.levelStart = dj["levelStart"]
        self.vname = dj["vehicle"]
        self.status = dj["status"]

    def loadNetRespJson(self, dj):
        self.location = dj["location"]
        self.pubbirthday = dj["birthday"]
        self.gender = dj["gender"]
        self.interests = dj["interests"]
        self.roles = dj["roles"]
        self.levels = dj["levels"]
        self.status = dj["status"]
        self.bid = dj["bid"]
        self.owner = dj["owner"]
        self.levelStart = dj["levelStart"]
        self.vehicle = dj["vehicle"]
        self.delDate = dj["delDate"]

    def genJson(self):
        jd = {
            "pseudo_nick_name": self.nick_name,
            "pseudo_name": self.pseudo_name,
            "location": self.location,
            "pubbirthday": self.pubbirthday,
            "mf": self.gender,
            "interests": self.interests,
            "roles": self.roles,
            "levels": self.levels,
            "bid": self.bid,
            "vehicle": self.vehicle,
            "gender": self.gender,
            "status": self.status
        }
        return jd


# Notes:
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

class CircularMessageQueue:
    def __init__(self, max_size=8000):
        self.queue = []
        self.max_size = max_size

    def add_message(self, message):
        if len(self.queue) >= self.max_size:
            self.queue.pop(0)
        self.queue.append(message)

    def get_messages(self):
        return self.queue

    def delete_messages(self, idx):
        self.queue.pop(idx)


# a light weight twin of the EB_BOT
class EBBOT_AGENT(QStandardItem):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.chat_histories = []
        self.bid = 0

    def setBid(self, bid):
        self.bid = bid

    def getBid(self):
        return self.bid

    # msg has a strict format of timestamp>sender>recipient>message
    def addChat(self, msg):
        msg_parts = msg.split(">")
        sender = msg_parts[1]
        if str(sender) not in self.chat_histories:
            # if this is a new conversation
            self.chat_histories[str(sender)] = CircularMessageQueue()

        self.chat_histories[str(sender)].add_message(msg)

    def deleteChat(self, msgTBD):
        msg_parts = msgTBD.split(">")
        sender = msg_parts[1]
        # find the message index
        if str(sender) in self.chat_histories:
            found_idx = next(
                (i for i, msg in enumerate(self.chat_histories[str(sender)].get_messages()) if msg == msgTBD), -1)
            self.chat_histories[sender].delete_messages(found_idx)

    def getChat(self, sender):
        if str(sender) in self.chat_histories:
            return self.chat_history.get_messages()
        else:
            return []


class EBBOT(QStandardItem):
    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win
        self.pubProfile = BOT_PUB_PROFILE()
        self.privateProfile = BOT_PRIVATE_PROFILE()
        self.settings = BOT_SETTINGS()

        self.ebType = "AMZ"
        if len(self.getFn()) > 1:
            self.icon_text = 'bot' + str(self.getBid()) + ":" + self.getFn()[
                                                                :1] + " " + self.getLn() + ":" + self.getLocation()
            self.setText(self.icon_text)
        else:
            self.icon_text = 'bot' + str(
                self.getBid()) + ":" + self.getFn() + " " + self.getLn() + ":" + self.getLocation()
            self.setText(self.icon_text)
        self.setFont(self.main_win.std_item_font)
        self.setBotIcon(self.main_win.file_resouce.bot_icon_path)
        self.seller_inventories = []
        self.msg_queue = asyncio.Queue()  # this is the messaging queue for the bot.

    def getMsgQ(self):
        return self.msg_queue

    def setEmail(self, em):
        self.privateProfile.email = em

    def setBotIcon(self, icon):
        self.icon = icon
        self.setIcon(QIcon(icon))

    def getBotIcon(self):
        return self.icon

    def getBid(self):
        return self.pubProfile.bid

    def getRoles(self):
        return self.pubProfile.roles

    def getAge(self):
        if self.pubProfile.pubbirthday != "":
            birthday = datetime.strptime(self.pubProfile.pubbirthday, '%Y-%m-%d')
            # Get the current date
            today = datetime.today()
            # Calculate the age
            age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
            return age
        return ""

    def getInventories(self):
        return self.seller_inventories

    def setInventories(self, invs):
        self.seller_inventories = invs

    def getPubBirthday(self):
        return self.pubProfile.pubbirthday

    def getBirthdayTxt(self):
        return self.privateProfile.birthday

    def getBirthday(self):
        return self.privateProfile.birthdaydt

    def getGender(self):
        return self.pubProfile.gender

    def getLocation(self):
        return self.pubProfile.location

    def getAddrStreet1(self):
        return self.privateProfile.shipping_addrl1

    def getAddrStreet2(self):
        return self.privateProfile.shipping_addrl2

    def getAddrCity(self):
        return self.privateProfile.shipping_addrcity

    def getAddrState(self):
        return self.privateProfile.shipping_addrstate

    def getAddrZip(self):
        return self.privateProfile.shipping_addrzip

    def getAddr(self):
        return self.privateProfile.addr

    def getShippingAddr(self):
        return self.privateProfile.shipping_addr

    def getShippingAddrStreet1(self):
        return self.privateProfile.shipping_addrl1

    def getShippingAddrStreet2(self):
        return self.privateProfile.shipping_addrl2

    def getShippingAddrCity(self):
        return self.privateProfile.shipping_addrcity

    def getShippingAddrState(self):
        return self.privateProfile.shipping_addrstate

    def getShippingAddrZip(self):
        return self.privateProfile.shipping_addrzip

    def getAddrShippingAddrSame(self):
        if self.privateProfile.shipping_addrzip == self.privateProfile.addrzip and \
                self.privateProfile.shipping_addrstate == self.privateProfile.addrstate and \
                self.privateProfile.shipping_addrcity == self.privateProfile.addrcity and \
                self.privateProfile.shipping_addrl2 == self.privateProfile.addrl2 and \
                self.privateProfile.shipping_addrl1 == self.privateProfile.addrl1:
            return True
        else:
            return False

    def getInterests(self):
        return self.pubProfile.interests

    def getMachine(self):
        return self.settings.machine

    def getPlatform(self):
        return self.settings.platform

    def getOS(self):
        return self.settings.os

    def getBrowser(self):
        return self.settings.browser

    def getStatus(self):
        return self.pubProfile.status

    def getPseudoName(self):
        return self.pubProfile.pseudo_name

    def getPseudoFirstName(self):
        return self.pubProfile.pseudo_first_name

    def getPseudoLastName(self):
        return self.pubProfile.pseudo_last_name

    def getNickName(self):
        return self.pubProfile.nick_name

    def getOwner(self):
        return self.pubProfile.owner

    def getBrowser(self):
        return self.settings.browser

    def getLevels(self):
        return self.pubProfile.levels

    def getLn(self):
        return self.privateProfile.last_name

    def getFn(self):
        return self.privateProfile.first_name

    def getName(self):
        return self.privateProfile.first_name + " " + self.privateProfile.last_name

    def getEmail(self):
        return self.privateProfile.email

    def getEmPW(self):
        return self.privateProfile.email_pw

    def getBackEm(self):
        return self.privateProfile.backup_email

    def getAcctPw(self):
        return self.privateProfile.acct_pw

    def getBackEmSite(self):
        return self.privateProfile.backup_email_site

    def setBackEmSite(self, site):
        self.privateProfile.backup_email_site = site

    def getPhone(self):
        return self.privateProfile.phone

    def getPubBirthday(self):
        return self.pubProfile.pubbirthday

    def getCreateOn(self):
        return self.privateProfile.createon
    # sets--------------------------

    def setBid(self, bid):
        self.pubProfile.bid = bid
        if len(self.getFn()) > 1:
            self.setText(
                'bot' + str(self.getBid()) + ":" + self.getFn()[:1] + " " + self.getLn() + ":" + self.getLocation())
        else:
            self.setText(
                'bot' + str(self.getBid()) + ":" + self.getFn() + " " + self.getLn() + ":" + self.getLocation())

    def setOwner(self, owner):
        self.pubProfile.owner = owner

    def setLevels(self, levels):
        self.pubProfile.levels = levels

    def setRoles(self, rw):
        self.pubProfile.roles = rw

    def setInterests(self, interests):
        self.pubProfile.setInterests(interests)

    # fill up data structure from json data.
    def loadJson(self, nbJson):
        self.pubProfile.loadJson(nbJson["pubProfile"])
        self.privateProfile.loadJson(nbJson["privateProfile"])
        self.settings.loadJson(nbJson["settings"])
        if len(self.getFn()) > 1:
            self.setText(
                'bot' + str(self.getBid()) + ":" + self.getFn()[:1] + " " + self.getLn() + ":" + self.getLocation())
        else:
            self.setText(
                'bot' + str(self.getBid()) + ":" + self.getFn() + " " + self.getLn() + ":" + self.getLocation())

    def getVid(self):
        return self.pubProfile.vid

    def getVehicle(self):
        return self.pubProfile.vehicle

    def setNetRespJsonData(self, nrjd):
        self.pubProfile.loadNetRespJson(nrjd)
        if len(self.getFn()) > 1:
            self.setText(
                'bot' + str(self.getBid()) + ":" + self.getFn()[:1] + " " + self.getLn() + ":" + self.getLocation())
        else:
            self.setText(
                'bot' + str(self.getBid()) + ":" + self.getFn() + " " + self.getLn() + ":" + self.getLocation())

    def genJson(self):
        # log3("generating Json..........>>>>")
        jsd = {
            "pubProfile": self.pubProfile.genJson(),
            "privateProfile": self.privateProfile.genJson(),
            "settings": self.settings.genJson()
        }
        # log3(json.dumps(jsd))
        return jsd

    def updateDisplay(self):
        if len(self.getFn()) > 1:
            self.setText(
                'bot' + str(self.getBid()) + ":" + self.getFn()[:1] + " " + self.getLn() + ":" + self.getLocation())
        else:
            self.setText(
                'bot' + str(self.getBid()) + ":" + self.getFn() + " " + self.getLn() + ":" + self.getLocation())

    def loadDBData(self, dbd: BotModel):
        self.pubProfile.setBid(dbd.botid)
        self.pubProfile.setOwner(dbd.owner)
        self.pubProfile.setLevels(dbd.levels)
        self.pubProfile.setGender(dbd.gender)
        self.pubProfile.setPubBirthday(dbd.birthday)
        self.pubProfile.setInterests(dbd.interests)
        self.pubProfile.setLoc(dbd.location)
        self.pubProfile.setRoles(dbd.roles)
        self.pubProfile.setStatus(dbd.status)
        self.pubProfile.setDelDate(dbd.delDate)
        self.pubProfile.setVehicle(dbd.vehicle)
        self.privateProfile.setName(dbd.name)
        self.pubProfile.setPseudoName(dbd.pseudoname)
        self.pubProfile.setNickName(dbd.nickname)
        self.privateProfile.setAddr1(dbd.addr)
        self.privateProfile.setShippingAddr1(dbd.shipaddr)
        self.privateProfile.setPhone(dbd.phone)
        self.privateProfile.setEmail(dbd.email)
        self.privateProfile.setEPW(dbd.epw)
        self.privateProfile.setBackEmail(dbd.backemail)
        self.privateProfile.setEBPW(dbd.ebpw)
        self.privateProfile.setCreateOn(dbd.createon)
        self.privateProfile.setBackEmailSite(dbd.backemail_site)
        self.setText('bot' + str(self.getBid()) + ":" + self.getFn() + " " + self.getLn() + ":" + self.getLocation())

    def loadXlsxData(self, jd):
        # location, roles, status, delDate, name, pseudoname, nickname, addr, shipaddr
        self.pubProfile.setLevels(jd["Levels"])
        self.pubProfile.setGender(jd["Gender"])
        self.pubProfile.setPubBirthday(jd["DoB"])
        self.pubProfile.setInterests(jd["Interests"])
        self.pubProfile.setLoc(jd["Proxy City"] + "," + jd["State"])
        self.pubProfile.setRoles(jd["Roles"])
        self.pubProfile.setStatus("")
        self.pubProfile.setDelDate("2121-01-01")
        self.privateProfile.setName(jd["New First Name"] + " " + jd["Last Name"])
        self.pubProfile.setPseudoName(jd["PseudoFN"] + " " + jd["PseudoLN"])
        self.pubProfile.setNickName("")
        self.pubProfile.setVehicle(jd["vehicle"])
        self.privateProfile.setAddr(jd["Addr Str1"], jd["Addr Str2"], jd["City"], jd["State"], jd["Zip"])
        self.privateProfile.setShippingAddr(jd["Addr Str1"], jd["Addr Str2"], jd["City"], jd["State"], jd["Zip"])
        self.privateProfile.setPhone(jd["IP phone"])
        self.privateProfile.setEmail(jd["Email"])
        self.privateProfile.setEPW(jd["PW"])
        self.privateProfile.setBackEmail(jd["Backup Email"])
        self.privateProfile.setEBPW(jd["Back PW"])
        self.privateProfile.setBackEmailSite(jd["BackEmailSite"])
        self.setText('bot' + str(self.getBid()) + ":" + self.getFn() + " " + self.getLn() + ":" + self.getLocation())
