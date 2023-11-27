import platform
import sys
import random
import boto3
from crontab import CronTab
from PySide6 import QtCore, QtGui, QtWidgets
import json
from readSkill import *

# valid refMethod: "Absolute", "Anchor Offset"
#  in case of "Anchor Offset", can list x/y relationship with up to 4 other anchors
#  described in json format, [{ "name" : anchor_name, "constraints" : {}...]
#    special anchor_name: ulc, urc, llc, lrc, lb, rb, tb, bb which represent "upper left corner" "left bound" etc.
#  constraints : { "xdir" : "within/beyond", "xtype" : "absolute/signed/abs percent/signed percent", "xval" : "10", "xunit":"pix/char height/char width/img size/win size/" .. y***
class ANCHOR(QtGui.QStandardItem):
    def __init__(self, aname, atype, homepath):
        super().__init__()
        self.name = aname
        self.type = atype
        self.refMethod = 'Absolute'
        self.imgPath = ""
        self.refs = []
        self.setText('aname')
        self.homepath = homepath
        self.icon = QtGui.QIcon(homepath+'/resource/anchor2-64.png')
        self.setIcon(self.icon)

    def set_img(self, img_path):
        self.imgPath = ''

    def set_ref_method(self, ref_method):
        self.refMethod = ref_method

    def add_ref(self, ref_name, refx, refy):
        new_ref = { "name" : ref_name,
                    "constraints" : {
                        "xdir": refx["dir"],
                        "xtype": refx["type"],
                        "xval": refx["val"],
                        "xunit": refx["unit"],
                        "ydir": refy["dir"],
                        "ytype": refy["type"],
                        "xval": refy["val"],
                        "yunit": refy["unit"],
                    }
                }
        self.refs.append(new_ref)

    def get_type(self):
        return self.type

# valid refMethod: "None", "Anchor Offset", "Anchor Bound", "Contains Anchor"
class USER_INFO(QtGui.QStandardItem):
    def __init__(self, aname, homepath):
        super().__init__()
        self.name = aname
        self.homepath = homepath
        self.type = "Phrase"     # or "nlines", "paragraph", "text" , BTW, phase ideally shall not exceed 3 words.
        self.n = 1
        self.setText(aname)
        self.icon = QtGui.QIcon(homepath+'/resource/focus0-64.png')
        self.setIcon(self.icon)
        self.content_text = ""
        self.contentbb = (0.0, 0.0, 0.0, 0.0)
        self.anchorbb = ("None", "None", "None", "None")

    def setContent(self, intext):
        self.content_text = intext

    def set_ref_method(self, ref_method):
        self.refMethod = ref_method

    def set_nlines(self, in_n):
        self.n = in_n

    def set_type(self, in_type):
        self.type = in_type

    def add_ref(self, ref_name, refx, refy):
        new_ref = { "name" : ref_name,
                    "constraints" : {
                        "xdir": refx["dir"],
                        "xtype": refx["type"],
                        "xval": refx["val"],
                        "xunit": refx["unit"],
                        "ydir": refy["dir"],
                        "ytype": refy["type"],
                        "xval": refy["val"],
                        "yunit": refy["unit"],
                    }
                }
        self.refs.append(new_ref)

    def set_bb(self, tl, tr, bl, br):
        self.bb = (tl, tr, bl, br)

class PROCEDURAL_STEP(QtGui.QStandardItem):
    def __init__(self, homepath, sname="browse"):
        super().__init__()
        self.Name = sname
        self.homepath = homepath
        self.number = 0
        self.setText(self.Name)
        self.icon = QtGui.QIcon(homepath+'/resource/step0-50.png')
        self.setIcon(self.icon)

        self.dataName = ""

        self.loadData = ""
        self.saveData = ""

    def set_app_page(self, inapp, inpage):
        self.app = inapp
        self.page = inpage

    def set_data_name(self, indn):
        self.dataName = indn

    def set_data_file(self, indf):
        self.loadData = indf
        self.saveData = indf

    def set_mouse_action(self, inma, inma_amount):
        self.mouseAction = inma
        self.mouseActionAmount = inma_amount

    def set_keyboard_action(self, inkba):
        self.keyboardAction = inkba

    def set_condition_jump(self, incondition, step_on_true, step_on_false):
        self.condition = incondition
        self.stepTrue = step_on_true
        self.stepFalse = step_on_false

    def set_jump(self, injump):
        self.jump = injump

    def set_wait(self, inwait):
        self.wait = inwait

    def set_routine(self, inroutine):
        self.routine = inroutine

    def set_extern(self, inext):
        self.extern = inext


class PROCEDURAL_SKILL(QtGui.QStandardItem):
    def __init__(self, parent):
        super().__init__()
        self.pageName = "AMZ"
        self.homepath = parent.homepath
        self.steps = None
        self.setText(self.pageName)
        self.icon = QtGui.QIcon(self.homepath+'/resource/skills-78.png')
        self.runStepsFile= ""
        self.setIcon(self.icon)
        self.runConfig = None
        self.nameSpace = ""
        self.parent = parent
        self.path = "resource/skills/public/"
        self.homepath = self.parent.homepath


    def getSteps(self):
        self.steps = readSkillFile(self.homepath, self.runStepsFile)
        return self.steps

    def getRunStepsFile(self):
        return self.runStepsFile

    def setConfig(self, cfg):
        self.runConfig = cfg

    def getConfig(self):
        return self.runConfig

    def loadJson(self,jd):
        self.runConfig = jd["runConfig"]
        self.runStepsFile = jd["runStepsFile"]


class CLOUD_SKILL(QtGui.QStandardItem):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.path = "resource/skills/public/"

    def set_path(self, path):
        self.path = path

    def get_local_path(self):
        return self.path

    def loadJson(self, jd):
        self.path = jd["path"]


class WORKSKILL(QtGui.QStandardItem):
    def __init__(self, parent, skname="default skill"):
        super().__init__()
        self.name = skname
        self.setText(self.name)
        self.setFont(parent.std_item_font)
        self.skid = 0
        self.owner = 0
        self.price = 0
        self.parent = parent
        self.homepath = parent.homepath
        self.price_model = ""
        self.price_model = ""
        self.path = "/resource/skills/public/"
        self.privacy = ""
        self.platform = ""
        self.app = ""
        self.app_link = ""
        self.app_args = ""
        self.site_name = ""
        self.site = ""
        self.page = ""
        self.private_skill = PROCEDURAL_SKILL(parent)
        self.cloud_skill = CLOUD_SKILL(parent)
        self.setText('Skill'+str(self.getSkid()))
        self.icon = QtGui.QIcon(parent.skill_icon_path)
        self.setIcon(self.icon)

    def add_private_skill(self, procedural_skill):
        self.private_skill = procedural_skill

    def getSteps(self):
        return self.private_skill.getSteps()

    def getRunConfig(self):
        return self.private_skill.getConfig()

    def get_run_steps_file(self):
        return self.private_skill.getRunStepsFile()

    def add_cloud_skill(self, info_skill):
        self.cloud_skill = info_skill

    def gen_psk_file(self):
        print("generating psk file:")

    def gen_csk_file(self):
        print("generating psk file:")

    def gen_skill_files(self):
        self.gen_csk_file()
        self.gen_psk_file()

    def getSkid(self):
        return self.skid

    def getPskFileName(self):
        return self.path + self.platform+"_"+self.app+"_"+self.site_name+"_"+self.page+"/"+ self.name + ".psk"

    def getCskFileName(self):
        return self.path + self.platform+"_"+self.app+"_"+self.site_name+"_"+self.page+"/"+ self.name + ".csk"

    def getNameSapcePrefix(self):
        return self.platform + "_" + self.app + "_" + self.site_name + "_" + self.page

    def getOwner(self):
        return self.owner

    def getPlatform(self):
        return self.platform

    def getApp(self):
        return self.app

    def getAppLink(self):
        return self.app_link

    def getAppArgs(self):
        return self.app_args

    def setAppLink(self, al):
        self.app_link = al

    def setAppArgs(self, aa):
        self.app_args = aa

    def getPage(self):
        return self.page

    def setPage(self, page):
        self.page = page

    def getSite(self):
        return self.site

    def getSiteName(self):
        return self.site_name

    def getName(self):
        return self.name

    def getPath(self):
        return self.path

    def setPath(self, path):
        self.path = path

    def getPriceModel(self):
        return self.price_model

    def setPriceModel(self, pm):
        self.price_model = pm

    def getPrice(self):
        return self.price

    def setPrice(self, price):
        self.price = price

    def getPrivacy(self):
        return self.privacy

    def setPrivacy(self, priv):
        self.privacy = priv


    def setConfig(self, cfg):
        self.private_skill.setConfig(cfg)

    def setNetRespJsonData(self, nrjd):
        self.pubAttributes.loadNetRespJson(nrjd)
        self.setText('mission' + str(self.getMid()))

    def loadJson(self, jd):
        self.name = jd["name"]
        self.setText(self.name)

        self.skid = jd["skid"]
        self.owner = jd["owner"]
        self.platform = jd["platform"]
        self.app = jd["app"]
        self.app_link = jd["app_link"]
        self.app_args = jd["app_args"]
        self.site_name = jd["site_name"]
        self.site = jd["site"]
        self.page = jd["page"]
        self.privacy = jd["privacy"]
        self.price_model = jd["price_model"]
        self.price = jd["price"]
        self.path = jd["path"]
        self.private_skill.loadJson(jd["private_skill"])
        self.cloud_skill.loadJson(jd["cloud_skill"])

