import platform
import sys
import random
import boto3
from crontab import CronTab
from PySide6 import QtCore, QtGui, QtWidgets
import json
from WorkSkill import *
from readSkill import *
import os
from ebbot import *



class VEHICLE(QtGui.QStandardItem):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.bot_ids = []
        self.arch = ""
        self.os = ""
        self.name = ""
        self.ip = ""
        self.id = ""
        self.setText('vehicle' + str(self.getVid()))
        self.icon = QtGui.QIcon(parent.vehicle_icon_path)
        self.setIcon(self.icon)
        self.setFont(parent.std_item_font)
        self.status = "Idle";

    def getVid(self):
        return self.id

    def setVid(self, vid):
        self.id = vid
        self.setText('vehicle' + self.id)

    def getStatus(self):
        return self.status

    def setStatus(self, stat):
        self.status = stat

    def getIP(self):
        return self.ip

    def setIP(self, ip):
        self.ip = ip

    def getName(self):
        return self.name

    def setName(self, name):
        self.name = name

    def getArch(self):
        return self.arch

    def setArch(self, arch):
        self.arch = arch

    def getOS(self):
        return self.os

    def setOS(self, vos):
        self.os = vos

    def getBotIds(self):
        return self.bot_ids

    def setBotIds(self, bot_ids):
        self.bot_ids = bot_ids


    def genJson(self):
        print("generating Json..........>>>>")
        jsd = {
                "vid": self.id,
                "ip": self.ip,
                "name": self.name,
                "os": self.os,
                "arch": self.arch,
                "bot_ids": self.bot_ids,
                "status": self.status
                }
        print(json.dumps(jsd))
        return jsd


    def loadJson(self, dj):
        self.id = dj["vid"]
        self.ip = dj["ip"]
        self.name = dj["name"]
        self.os = dj["os"]
        self.arch = dj["arch"]
        self.status = dj["status"]
        self.bot_ids = dj["bots"]