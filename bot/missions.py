import platform
import sys
import random
import boto3
from crontab import CronTab
import datetime
from PySide6 import QtCore, QtGui, QtWidgets
import json
from readSkill import *
import os

# Every bot has a run schedule which is specified in the following parameters
# start time for the day, example: 7am pacific time.
# start time uncertainty give start time could be some many minutes earlier or late.
# repetiton time and unit, example: run every
# number of retry: if somehow mission is failed, how many times to retry.
# retry wait time: minimum wait time between retrys (in minutes).
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
        self.repetition


class M_Action_Items():
    def __init__(self):
        super().__init__()

        self.tasks = []

        # self.

    def run(self):
        self.abc = 1


class M_Skill():
    def __init__(self):
        super().__init__()

        self.skill_name = "browse_search_kw"
        self.all_steps = []
        self.psk = "C:/Users/Teco/PycharmProjects/ecbot/resource/skills/enter_amz/enter_amz.psk"
        self.csk = ""

        # self.

    def run(self):
        self.abc = 1

    def get_all_steps(self):
        return self.all_steps

    def loadSkill(self):
        # load skill file.
        name_pf = "generic"
        skill_file = self.psk
        print("load skill file:", skill_file)
        self.all_steps = readSkillFile(name_pf, skill_file)



class M_Private_Attributes():
    def __init__(self):
        super().__init__()
        self.item_number = "0"
        self.seller = "NA"
        self.title = "NA"
        self.imglink = "NA"
        self.rank = 0
        self.fb_type = "NA"
        self.skills = []
        self.skills.append(M_Skill())
        self.current_sk_idx = 0
        # "C:/Users/Teco/PycharmProjects/ecbot/resource/skills/enter_amz/enter_amz.psk"


    def setItem(self, inum, seller, title, imglink, rank):
        self.item_number = inum
        self.seller = seller
        self.title = title
        self.imglink = imglink
        self.rank = rank

    def setSkills(self, sks):
        self.skill = sks

    def addSkill(self, sk):
        self.skills.append(sk)


    def get_all_steps(self):
        # load skill file.
        return self.all_steps

    def setFbType(self, fbtype):
        self.fb_type = fbtype

    def loadJson(self, dj):
        self.item_number = dj.item_number
        self.seller = dj.seller
        self.title = dj.title
        self.imglink = dj.imglink
        self.rank = dj.rank
        self.fb_type = dj.fb_type

    def genJson(self, dj):
        jd = {
                "item_number": self.item_number,
                "seller": self.seller,
                "title": self.title,
                "imglink": self.imglink,
                "rank": self.rank,
                "fb_type": self.fb_type
            }
        return jd

class M_Pub_Attributes():
    def __init__(self):
        super().__init__()
        self.missionId = 0
        self.assign_type = "USER"         # user assigned or cloud auto assigned.
        self.search_kw = ""               # search phrase
        self.search_cat = "NA"
        self.nex = 1                      # number of time this mission to repeated.
        self.status = "NA"
        self.ms_type = "SELL"             # buy/sell type of mission.
        self.bot_id = 0                   # the bot associated with a mission.


    def setType(self, mid, atype, mtype):
        self.missionId = mid
        self.assign_type = atype
        self.ms_type = mtype

    def setBot(self, bid):
        self.bot_id = bid

    def setNex(self, nRetry):
        self.nex = nRetry

    def setStatus(self, stat):
        self.status = stat

    def setSearch(self, kw, cat):
        self.search_kw = kw
        self.category = cat

    def loadJson(self, dj):
        self.missionId = dj.missionId
        self.assign_type = dj.assign_type
        self.ms_type = dj.ms_type
        self.nex = dj.nex
        self.bot_id = dj.bot_id
        self.status = dj.status
        self.search_kw = dj.search_kw
        self.category = dj.category

    def genJson(self, dj):
        jd = {
                "missionId": self.missionId,
                "assign_type": self.assign_type,
                "ms_type": self.ms_type,
                "nex": self.nex,
                "bot_id": self.bot_id,
                "status": self.status,
                "search_kw": self.search_kw,
                "category": self.category
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


class EBMISSION(QtGui.QStandardItem):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setText('mission')
        self.icon = QtGui.QIcon('C:/Users/Teco/PycharmProjects/ecbot/resource/c_mission96_1.png')
        self.setIcon(self.icon)

        self.pubAttributes = M_Pub_Attributes()
        self.privateAttributes = M_Private_Attributes()
        self.tasks = M_Action_Items()
        self.parent_settings = {"mission_id": self.pubAttributes.missionId,
                                "session": self.parent.session,
                                "token": self.parent.tokens['AuthenticationResult']['IdToken'],
                                "psk": self.privateAttributes.skills[self.privateAttributes.current_sk_idx].psk,
                                "csk": self.privateAttributes.skills[self.privateAttributes.current_sk_idx].csk,
                                "skill_name": self.privateAttributes.skills[self.privateAttributes.current_sk_idx].skill_name,
                                "uid": self.parent.uid}

    def getMid(self):
        return self.pubAttributes.missionId

    def getSearchKW(self):
        return self.pubAttributes.search_kw

    def getSearchCat(self):
        return self.pubAttributes.search_cat

    def getRepeat(self):
        return self.pubAttributes.nex

    def getMtype(self):
        return self.pubAttributes.ms_type

    def getBid(self):
        return self.pubAttributes.bot_id

    def getStatus(self):
        return self.pubAttributes.status

    def setOwner(self, owner):
        self.pubAttributes.owner = owner

    # self.
    def setJsonData(self, ppJson):
        self.pubAttributes.loadJson(ppJson.pubAttributes)
        self.privateAttributes.loadJson(ppJson.privateAttributes)

    def genJson(self):
        print("generating Json..........>>>>")
        jsd = {
                "pubProfile": self.pubProfile.genJson,
                "privateProfile": self.privateProfile.genJson
                }
        print(json.dumps(jsd))
        return jsd

    async def run(self):
        run_result = None
        print("running.....")
        for si in range(len(self.privateAttributes.skills)):
            print("si:", si)
            print("skill:", self.privateAttributes.skills[si])
            self.privateAttributes.skills[si].loadSkill()
            print("run all steps .....", self.privateAttributes.skills[si].get_all_steps())
            print("settings:", self.parent_settings)
            runAllSteps(self.privateAttributes.skills[si].get_all_steps(), self.parent_settings)

        return run_result
