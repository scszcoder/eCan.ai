import platform
import sys
import random
import boto3
from crontab import CronTab
from datetime import datetime, date
from PySide6 import QtCore, QtGui, QtWidgets
import json


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
        self.tasks = dj["tasks"]

    def setComputer(self, platform, os, machine, browser):
        self.platform = platform
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
        print("genJson:", json.dumps(jd))
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

    def setName(self, n_first, n_last):
        self.first_name = n_first
        self.last_name = n_last


    def setAddr(self, l1, l2, city, state, zip):
        self.addrl1 = l1
        self.addrl2 = l2
        self.addrcity = city
        self.addrstate = state
        self.addrzip = zip
        if l2 != "":
            self.addr = l1 + "\n" + l2 + "\n" + city + ", " + state + " " + zip
        else:
            self.addr = l1 + "\n" + city + ", " + state + " " + zip

    def setAddr1(self, addr):
        self.addr = addr


    def setShippingAddr(self, l1, l2, city, state, zip):
        self.shipping_addrl1 = l1
        self.shipping_addrl1 = l2
        self.shipping_addrcity = city
        self.shipping_addrstate = state
        self.shipping_addrzip = zip
        if l2 != "":
            self.shipping_addr = l1 + "\n" + l2 + "\n" + city + ", " + state + " " + zip
        else:
            self.shipping_addr = l1 + "\n" + city + ", " + state + " " + zip

    def setShippingAddr1(self, addr):
        self.shipping_addr = addr

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

    def setBirthday(self, bdtxt):
        self.birthday = bdtxt
        format = '%m/%d/%Y'

        # convert from string format to datetime format
        self.birthdaydt = datetime.strptime(bdtxt, format)

    def getBirthday(self):
        return self.birthdaydt


    def setAcct(self, email, epw, phone, back_email, acct_pw):
        self.email = email
        self.email_pw = epw
        self.phone = phone
        self.backup_email = back_email
        self.acct_pw = acct_pw


    def loadJson(self, dj):
        self.first_name = dj["first_name"]
        self.last_name = dj["last_name"]
        self.email = dj["email"]
        self.email_pw = dj["email_pw"]
        self.phone = dj["phone"]
        self.backup_email = dj["backup_email"]
        self.acct_pw = dj["acct_pw"]
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


    def genJson(self, dj):
        jd = {
                "first_name": self.first_name,
                "last_name": self.last_name,
                "email": self.email,
                "email_pw": self.email_pw,
                "phone": self.phone,
                "backup_email": self.backup_email,
                "acct_pw": self.acct_pw,
                "birthday": self.birthday
            }
        return jd


class BOT_PUB_PROFILE():
    def __init__(self):
        super().__init__()
        self.bid = 0
        self.pseudo_name = "Jonny"
        self.nick_name = "Jonny"
        self.location = "CA"
        self.pubbirthday = "01/01/1992"
        self.gender = "M"
        self.interests = ""
        self.roles = ""
        self.owner = ""
        self.levels = ""
        self.status = ""
        self.createdon = ""
        self.delDate = ""
        self.levelStart = ""

    def setBid(self, bid):
        self.bid = bid

    def setOwner(self, owner):
        self.owner = owner

    def setRoles(self, roles):
        self.roles = roles

    def setPseudoName(self, pn):
        self.pseudo_name = pn

    def setNickName(self, nn):
        self.nick_name = nn

    def setLoc(self, loc):
        self.location = loc

    def setAgeFromBirthday(self, bd):
        today = date.today()
        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))

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

    def setPersonal(self, age_text, gender):
        if age_text.isnumeric():
            self.age = int(age_text)
        self.gender = gender

    def setInterests(self, interests):
        self.interests = interests

    def setStatus(self, stat):
        self.status = stat

    def loadJson(self, dj):
        self.bid = dj["bid"]
        self.pseudo_nick_name = dj["pseudo_nick_name"]
        self.pseudo_name = dj["pseudo_name"]
        self.location = dj["location"]
        self.pubbirthday = dj["pubbirthday"]
        self.gender = dj["gender"]
        self.interests = dj["interests"]
        self.roles = dj["roles"]
        self.levels = dj["levels"]
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
        self.delDate = dj["delDate"]

    def genJson(self, dj):
        jd = {
                "pseudo_nick_name": self.pseudo_nick_name,
                "location": self.location,
                "age": self.age,
                "mf": self.gender,
                "interests": self.interests,
                "roles": self.roles
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


class EBBOT(QtGui.QStandardItem):
    def __init__(self, icon_path):
        super().__init__()
        self.pubProfile = BOT_PUB_PROFILE()
        self.privateProfile = BOT_PRIVATE_PROFILE()
        self.settings = BOT_SETTINGS()

        self.ebType = "AMZ"
        self.setText('bot'+str(self.getBid()))
        self.icon = QtGui.QIcon(icon_path)
        self.setIcon(self.icon)

        self.seller_inventories = []


    def getBid(self):
        return self.pubProfile.bid

    def getRoles(self):
        return self.pubProfile.roles

    def getAge(self):
        return self.pubProfile.age

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

    def getPhone(self):
        return self.privateProfile.phone

    # sets--------------------------

    def setOwner(self, owner):
        self.pubProfile.owner = owner

    def setRoles(self, rw):
        self.pubProfile.roles = rw

    def setInterests(self, interests):
        self.pubProfile.setInterests(interests)



    # fill up data structure from json data.
    def setJsonData(self, nbJson):
        self.pubProfile.loadJson(nbJson["pubProfile"])
        self.privateProfile.loadJson(nbJson["privateProfile"])
        self.settings.loadJson(nbJson["settings"])
        self.setText('bot' + str(self.getBid()))

    def setNetRespJsonData(self, nrjd):
        self.pubProfile.loadNetRespJson(nrjd)
        self.setText('bot' + str(self.getBid()))

    def genJson(self):
        print("generating Json..........>>>>")
        jsd = {
                "pubProfile": self.pubProfile.genJson(),
                "privateProfile": self.privateProfile.genJson(),
                "settings": self.settings.genJson()
                }
        print(json.dumps(jsd))
        return jsd

    # fill data structure from a row in sqlite db fetchall result
    # "bid": [0]
    # "owner": [1]
    # "roles": [2]
    # "pubbirthday": [3]
    # "gender": [4]
    # "location": [5]
    # "levels": [6]
    # "birthday": [7]
    # "interests": [8]
    # "status": [9]
    # "delDate": [10]
    # "name": [11]
    # "pseudoname": [12]
    # "nickname": [13]
    # "addr": [14]
    # "shipaddr": [15]
    # "phone": [16]
    # "email": [17]
    # "epw": [18]
    # "backemail": [19]
    # "ebpw": [20]
    def loadDBData(self, dbd):
        self.pubProfile.setBid(dbd[0])
        self.pubProfile.setOwner(dbd[1])
        self.pubProfile.setRoles(dbd[2])
        self.pubProfile.setPubBirthday(dbd[3])
        self.pubProfile.setGender(dbd[4])
        self.pubProfile.setLoc(dbd[5])
        self.pubProfile.setLevels(dbd[6])
        self.privateProfile.setBirthday(dbd[7])
        self.pubProfile.setInterests(dbd[8])
        self.pubProfile.setStatus(dbd[9])
        self.pubProfile.setDelDate(dbd[10])
        self.privateProfile.setName(dbd[11])
        self.pubProfile.setPseudoName(dbd[12])
        self.pubProfile.setNickName(dbd[13])
        self.privateProfile.setAddr1(dbd[14])
        self.privateProfile.setShippingAddr1(dbd[15])
        self.privateProfile.setPhone(dbd[16])
        self.privateProfile.setEmail(dbd[17])
        self.privateProfile.setEPW(dbd[18])
        self.privateProfile.setBackEmail(dbd[19])
        self.privateProfile.setEBPW(dbd[20])

    def run(self):
        self.abc = 1



