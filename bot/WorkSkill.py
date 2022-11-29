import platform
import sys
import random
import boto3
from crontab import CronTab
import datetime
from PySide6 import QtCore, QtGui, QtWidgets
import json

# valid refMethod: "Absolute", "Anchor Offset"
#  in case of "Anchor Offset", can list x/y relationship with up to 4 other anchors
#  described in json format, [{ "name" : anchor_name, "constraints" : {}...]
#    special anchor_name: ulc, urc, llc, lrc, lb, rb, tb, bb which represent "upper left corner" "left bound" etc.
#  constraints : { "xdir" : "within/beyond", "xtype" : "absolute/signed/abs percent/signed percent", "xval" : "10", "xunit":"pix/char height/char width/img size/win size/" .. y***
class ANCHOR(QtGui.QStandardItem):
    def __init__(self, aname, atype):
        super().__init__()
        self.name = aname
        self.type = atype
        self.refMethod = 'Absolute'
        self.imgPath = ""
        self.refs = []
        self.setText('aname')
        self.icon = QtGui.QIcon('C:/Users/Teco/PycharmProjects/ecbot/resource/anchor2-64.png')
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
    def __init__(self, aname):
        super().__init__()
        self.name = aname
        self.type = "Phrase"     # or "nlines", "paragraph", "text" , BTW, phase ideally shall not exceed 3 words.
        self.n = 1
        self.setText(aname)
        self.icon = QtGui.QIcon('C:/Users/Teco/PycharmProjects/ecbot/resource/focus0-64.png')
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
                        "xtype": refx["dir"],
                        "xval": refx["dir"],
                        "xunit": refx["dir"],
                        "ydir": refy["dir"],
                        "ytype": refy["dir"],
                        "xval": refy["dir"],
                        "yunit": refy["dir"],
                    }
                }
        self.refs.append(new_ref)

    def set_bb(self, tl, tr, bl, br):
        self.bb = (tl, tr, bl, br)

class PROCEDURAL_STEP(QtGui.QStandardItem):
    def __init__(self, sname="browse"):
        super().__init__()
        self.Name = sname
        self.number = 0
        self.setText(self.Name)
        self.icon = QtGui.QIcon('C:/Users/Teco/PycharmProjects/ecbot/resource/step0-50.png')
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
    def __init__(self):
        super().__init__()
        self.pageName = "AMZ"
        self.steps = []
        self.setText(self.pageName)
        self.icon = QtGui.QIcon('C:/Users/Teco/PycharmProjects/ecbot/resource/skills-78.png')
        self.setIcon(self.icon)

    def addStep(self, new_step):
        self.steps.append(new_step)

    def getSteps(self):
        return self.steps


class INFO_SKILL(QtGui.QStandardItem):
    def __init__(self):
        super().__init__()
        self.pageName = "AMZ"
        self.anchors = []
        self.targets = []

    def set_name(self, page_name):
        self.pageName = page_name

    def add_anchor(self, new_anchor):
        self.anchors.append(new_anchor)

    def add_target(self, new_target):
        self.targets.append(new_target)


class WORKSKILL(QtGui.QStandardItem):
    def __init__(self, skname):
        super().__init__()
        self.name = skname
        self.local_skill = None
        self.cloud_skill = None

    def add_local_skill(self, procedural_skill):
        self.local_skill = procedural_skill

    def get_steps(self):
        return self.local_skill.getSteps()

    def add_cloud_skill(self, info_skill):
        self.cloud_skill = info_skill

    def gen_lsk_file(self):
        print("generating lsk file:")

    def gen_csk_file(self):
        print("generating lsk file:")

    def gen_skill_files(self):
        self.gen_csk_file()
        self.gen_lsk_file()