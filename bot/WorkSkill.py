import os
from datetime import datetime

from PySide6.QtGui import QStandardItem, QIcon

from bot.Cloud import upload_file
from bot.Logger import log3


# valid refMethod: "Absolute", "Anchor Offset"
#  in case of "Anchor Offset", can list x/y relationship with up to 4 other images
#  described in json format, [{ "name" : anchor_name, "constraints" : {}...]
#    special anchor_name: ulc, urc, llc, lrc, lb, rb, tb, bb which represent "upper left corner" "left bound" etc.
#  constraints : { "xdir" : "within/beyond", "xtype" : "absolute/signed/abs percent/signed percent", "xval" : "10", "xunit":"pix/char height/char width/img size/win size/" .. y***
class ANCHOR(QStandardItem):
    def __init__(self, aname, atype, homepath):
        super().__init__()
        self.name = aname
        self.type = atype
        self.refMethod = 'Absolute'
        self.imgPath = ""
        self.refs = []
        self.setText('aname')
        self.homepath = homepath
        self.imgPath = ""
        self.icon = QIcon(homepath+'/resource/anchor2-64.png')
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

    def get_name(self):
        return self.name

# valid refMethod: "None", "Anchor Offset", "Anchor Bound", "Contains Anchor"
class USER_INFO(QStandardItem):
    def __init__(self, aname, homepath):
        super().__init__()
        self.name = aname
        self.homepath = homepath
        self.type = "Phrase"     # or "nlines", "paragraph", "text" , BTW, phase ideally shall not exceed 3 words.
        self.n = 1
        self.setText(aname)
        self.icon = QIcon(homepath+'/resource/focus0-64.png')
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

class PROCEDURAL_STEP(QStandardItem):
    def __init__(self, homepath, sname="browse"):
        super().__init__()
        self.Name = sname
        self.homepath = homepath
        self.number = 0
        self.setText(self.Name)
        self.icon = QIcon(homepath+'/resource/step0-50.png')
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


class PROCEDURAL_SKILL(QStandardItem):
    def __init__(self, parent):
        super().__init__()
        self.pageName = "AMZ"
        self.homepath = parent.homepath
        self.steps = None
        self.setText(self.pageName)
        self.icon = QIcon(self.homepath+'/resource/skills-78.png')
        self.runStepsFile= ""
        self.setIcon(self.icon)
        self.runConfig = None
        self.nameSpace = ""
        self.parent = parent
        self.path = "resource/skills/public/"

    def getRunStepsFile(self):
        return self.runStepsFile

    def setConfig(self, cfg):
        self.runConfig = cfg

    def getConfig(self):
        return self.runConfig

    def loadJson(self,jd):
        self.runConfig = jd["runConfig"]
        self.runStepsFile = jd["runStepsFile"]


class CLOUD_SKILL(QStandardItem):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.file = "resource/skills/public/"
        self.anchors = []

    def set_path(self, path):
        self.path = path

    def get_local_path(self):
        return self.path

    def get_anchors(self):
        return self.anchors

    def get_csk_file(self):
        return self.file

    def loadJson(self, jd):
        self.path = jd["path"]


class WORKSKILL(QStandardItem):
    def __init__(self, parent, skname, skdir="/resource/skills/public/"):
        super().__init__()
        self.parent = parent
        self.name = skname
        self.setText(skname+"()")
        self.setFont(parent.std_item_font)
        self.skid = 0
        self.owner = ""
        self.price = 0
        self.parent = parent
        self.homepath = parent.homepath
        self.price_model = ""
        self.path = skdir
        print("skill home path::"+self.path)
        self.psk_file = ""
        self.csk_file = ""
        self.privacy = "public"
        self.platform = "win"
        self.app = "chrome"
        self.app_link = ""
        self.app_args = ""
        self.site_name = ""
        self.site = "amz"
        self.page = "home"
        self.main = "F"
        self.runtime = 1
        self.procedural_skill = PROCEDURAL_SKILL(parent)
        self.cloud_skill = CLOUD_SKILL(parent)
        self.setText('Skill'+str(self.getSkid()))
        self.icon = QIcon(parent.file_resource.skill_icon_path)
        self.setIcon(self.icon)
        self.createdOn = datetime.today().strftime('%Y-%m-%d')
        self.description = "This skill does great automation."
        self.generator = ""
        self.version = "0.0.1"

        self.setText(self.name)
        self.icon = QIcon(self.homepath + '/resource/images/icons/skills_78.png')
        self.setIcon(self.icon)
        self.dependencies = []

    def getDependencies(self):
        return self.dependencies

    def setDependencies(self, deps):
        self.dependencies = deps

    def add_procedural_skill(self, procedural_skill):
        self.procedural_skill = procedural_skill

    def getSteps(self):
        return self.procedural_skill.getSteps()

    def getRunConfig(self):
        return self.procedural_skill.getConfig()

    def get_run_steps_file(self):
        return self.procedural_skill.getRunStepsFile()

    def add_cloud_skill(self, info_skill):
        self.cloud_skill = info_skill

    def gen_psk_file(self):
        log3("generating psk file:")

    def gen_csk_file(self):
        log3("generating psk file:")

    def gen_skill_files(self):
        self.gen_csk_file()
        self.gen_psk_file()

    def getSkid(self):
        return self.skid

    def setSkid(self, skid):
        self.skid = skid
        self.setText(self.platform+"_"+self.app+"_"+self.site_name+"_"+self.page+"_"+self.name + "(" + str(self.skid) + ")")

    def getPskFileName(self):
        return self.path + self.platform+"_"+self.app+"_"+self.site_name+"_"+self.page+"/"+ self.name + ".psk"

    def setPskFileName(self, pskFile):
        self.psk_file = pskFile

    def getCskFileName(self):
        return self.path + self.platform+"_"+self.app+"_"+self.site_name+"_"+self.page+"/"+ self.name + "/scripts/" +self.name + ".csk"

    def setCskFileName(self, cskFile):
        self.csk_file = cskFile

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

    def getRunTime(self):
        return self.runtime

    def setPage(self, page):
        self.page = page

    def getSite(self):
        return self.site

    def getSiteName(self):
        return self.site_name

    def getName(self):
        return self.name

    def getUsers(self):
        return self.users

    def getCreatedOn(self):
        return self.createdOn

    def getDescription(self):
        return self.description

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
        if self.privacy == "private":
            self.path = "/resource/skills/my/"
        elif self.privacy == "subscribed":
            self.path = "/resource/skills/subscribed/"

    def setCreatedOn(self, co):
        self.createdOn = co

    def setDescription(self, ds):
        self.desription = ds

    def setMain(self, ismain):
        if ismain:
            self.main = "T"
        else:
            self.main = "F"

    def getMain(self):
        return self.main

    def getIsMain(self):
        if self.main == "T":
            return True
        else:
            return False

    def setPlatform(self, platform):
        self.platform = platform
        self.setText(self.platform + "_" + self.app + "_" + self.site_name + "_" + self.page + "_" + self.name + "(" + str(self.skid) + ")")

    def setSite(self, site):
        self.site = site
        self.setText(self.platform + "_" + self.app + "_" + self.site_name + "_" + self.page + "_" + self.name + "(" + str(self.skid) + ")")

    def setName(self, name):
        self.name = name
        self.setText(self.platform + "_" + self.app + "_" + self.site_name + "_" + self.page + "_" + self.name + "(" + str(self.skid) + ")")

    def setRunTime(self, rt):
        self.runtime = rt

    def setConfig(self, cfg):
        self.procedural_skill.setConfig(cfg)

    def setNetRespJsonData(self, nrjd):
        # self.pubAttributes.loadNetRespJson(nrjd)
        self.setText('skill' + str(nrjd['skid']))

    def setAppearance(self, qcolor, qfont):
        if self.main == "T":
            self.setForeground(qcolor)  # Blue color
            self.setFont(qfont)

    def loadJson(self, jd):
        self.name = jd["name"]
        self.skid = jd["skid"]
        self.owner = jd["owner"]
        self.createdOn = jd["createdOn"]
        self.platform = jd["platform"]
        self.app = jd["app"]
        self.site_name = jd["site_name"]
        self.site = jd["site"]
        self.page = jd["page"]
        self.setText(self.platform+"_"+self.app+"_"+self.site_name+"_"+self.page+"_"+self.name + "(" + str(self.skid) + ")")
        self.main = jd["main"]

        self.privacy = jd["privacy"]
        self.price_model = jd["price_model"]
        self.price = jd["price"]
        self.path = jd["path"]
        self.description = jd["description"]

        if "site_link" in jd:
            self.site = jd["site_link"]

        if "app_link" in jd:
            self.app_link = jd["app_link"]

        if "app_args" in jd:
            self.app_args = jd["app_args"]

        if "procedural_skill" in jd:
            self.procedural_skill.loadJson(jd["procedural_skill"])

        if "cloud_skill" in jd:
            self.cloud_skill.loadJson(jd["cloud_skill"])


    def genJson(self):
        jsd = {
            "name": self.name,
            "skid": self.skid,
            "owner": self.owner,
            "createdOn": self.createdOn,
            "platform": self.platform,
            "app": self.app,
            "app_link": self.app_link,
            "app_args": self.app_args,
            "site_name": self.site_name,
            "site": self.site,
            "page": self.page,
            "main": self.main,
            "privacy": self.privacy,
            "price_model": self.price_model,
            "price": self.price,
            "path": self.path,
            "dependencies": self.dependencies,
            "description": self.description,
        }
        return jsd

    def send_csk_to_cloud(self, session, token, csk):
        for ankf in self.cloud_skill.get_anchors():
            upload_file(session, ankf, token, "anchor")

        upload_file(session, self.cloud_skill.get_csk_file(), token, "csk")

    def matchPskFileName(self, skill_file_name):
        # return true only when platform, app, site, page, skill name all matched.
        # skill_file_name is in this full path format: public/" + sk_prefix + "/" + sk_name + ".psk"
        sk_name = os.path.basename(skill_file_name).split(".")[0]
        sk_prefix = os.path.basename(os.path.dirname(skill_file_name))
        input_skill_file_name = sk_prefix+"_"+sk_name
        correct_name = self.platform+"_"+self.app+"_"+self.site_name+"_"+self.page+"_"+self.name

        if correct_name == input_skill_file_name:
            return True
        else:
            return False

