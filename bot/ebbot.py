import platform
import sys
import random
import boto3
from crontab import CronTab
import datetime
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

    def run(self):
        self.abc = 1


    def loadJson(self, dj):
        self.platform = dj.platform
        self.os = dj.os
        self.machine = dj.machine
        self.browser = dj.browser
        self.tasks = dj.tasks
        self.schedule = dj.schedule

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

        self.first_name = "John"
        self.last_name = "Smith"
        self.email = ""
        self.email_pw = ""
        self.phone = ""
        self.backup_email = ""
        self.acct_pw = ""
        self.file = ""

    def setName(self, n_first, n_last):
        self.first_name = n_first
        self.last_name = n_last


    def setAcct(self, email, epw, phone, back_email, acct_pw):
        self.email = email
        self.email_pw = epw
        self.phone = phone
        self.backup_email = back_email
        self.acct_pw = acct_pw


    def loadJson(self, dj):
        self.first_name = dj.first_name
        self.last_name = dj.last_name
        self.email = dj.email
        self.email_pw = dj.email_pw
        self.phone = dj.phone
        self.backup_email = dj.backup_email
        self.acct_pw = dj.acct_pw
        self.file = dj.file

    def genJson(self, dj):
        jd = {
                "first_name": self.first_name,
                "last_name": self.last_name,
                "email": self.email,
                "email_pw": self.email_pw,
                "phone": self.phone,
                "backup_email": self.backup_email,
                "acct_pw": self.acct_pw,
                "file": self.file
            }
        return jd


class BOT_PUB_PROFILE():
    def __init__(self):
        super().__init__()
        self.id = 0
        self.pseudo_nick_name = "Jonny"
        self.location = "CA"
        self.age = 0
        self.gender = "M"
        self.interests = "NA"
        self.role = "Buyer"
        self.owner = "NA"
        self.level = "NA"

    def setPseudoName(self, p_nick):
        self.pseudo_nick_name = p_nick

    def setLoc(self, loc):
        self.location = loc

    def setPersonal(self, age_text, gender):
        if age_text.isnumeric():
            self.age = int(age_text)
        self.gender = gender

    def setInterests(self, interests):
        self.interests = interests


    def loadJson(self, dj):
        self.pseudo_nick_name = dj.pseudo_nick_name
        self.location = dj.location
        self.age = dj.age
        self.gender = dj.gender
        self.interests = dj.interests
        self.role = dj.role

    def genJson(self, dj):
        jd = {
                "pseudo_nick_name": self.pseudo_nick_name,
                "location": self.location,
                "age": self.age,
                "mf": self.gender,
                "interests": self.interests,
                "role": self.role
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
    def __init__(self):
        super().__init__()
        self.ebType = "AMZ"
        self.setText('bot')
        self.icon = QtGui.QIcon('C:/Users/Teco/PycharmProjects/ecbot/resource/c_robot64_0.png')
        self.setIcon(self.icon)

        self.pubProfile = BOT_PUB_PROFILE()
        self.privateProfile = BOT_PRIVATE_PROFILE()
        self.settings = BOT_SETTINGS()

    def getBid(self):
        return self.pubProfile.id

    def getRole(self):
        return self.pubProfile.role

    def getAge(self):
        return self.pubProfile.age

    def getGender(self):
        return self.pubProfile.gender

    def getLocation(self):
        return self.pubProfile.location

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

    def getFirstName(self):
        return self.pubProfile.location

    def getLastName(self):
        return self.pubProfile.interests

    def getOwner(self):
        return self.pubProfile.owner

    def getOS(self):
        return self.settings.os

    def getBrowser(self):
        return self.settings.browser

    def getLevel(self):
        return self.pubProfile.level

    def getLn(self):
        return self.privateProfile.last_name

    def getFn(self):
        return self.privateProfile.first_name

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
        self.pubProfile.level = owner

        # self.
    def setJsonData(self, ppJson):
        self.pubProfile.loadJson(ppJson.pubProfile)
        self.privateProfile.loadJson(ppJson.privateProfile)
        self.settings.loadJson(ppJson.settings)

    def genJson(self):
        print("generating Json..........>>>>")
        jsd = {
                "pubProfile": self.pubProfile.genJson,
                "privateProfile": self.privateProfile.genJson,
                "settings": self.settings.genJson
                }
        print(json.dumps(jsd))
        return jsd


    def run(self):
        self.abc = 1



