from PySide6.QtGui import QStandardItem, QIcon
from datetime import timedelta, datetime

class VEHICLE(QStandardItem):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.bot_ids = []
        self.arch = ""
        self.os = parent.os_short
        self.name = ""
        self.ip = ""
        self.id = ""
        self.setText('vehicle' + str(self.getVid()))
        self.icon = QIcon(parent.file_resource.vehicle_icon_path)
        self.setIcon(self.icon)
        self.setFont(parent.std_item_font)
        self.status = "running_idle"
        self.last_update_time = datetime.strptime("1900-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
        self.mstats = []
        self.field_link = None
        self.daily_mids = []
        self.CAP = 56*3


    def getFieldLink(self):
        return self.field_link

    def setFieldLink(self, fl):
        self.field_link = fl

    def getVid(self):
        return self.id

    def setVid(self, vid):
        self.id = vid
        self.setText('vehicle' + str(self.id))

    def getStatus(self):
        return self.status

    def setStatus(self, stat):
        self.status = stat
        self.last_update_time = datetime.now()

    def getLastUpdateTime(self):
        return self.last_update_time

    def setMStats(self, mstats):
        self.mstats = mstats

    def getMStats(self):
        return self.mstats

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

    def addBot(self, bid):
        if len(self.getBotIds()) < self.CAP:
            self.bot_ids.append(bid)
            nAdded = 1
        else:
            nAdded = 0

        return nAdded

    def removeBot(self, bid):
        self.bot_ids.remove(bid)


    def setBotIds(self, bot_ids):
        self.bot_ids = bot_ids

    def getBotsOverCapStatus(self):
        return (len(self.bot_ids) > self.CAP)

    def getMids(self):
        return self.daily_mids

    def setMids(self, mids):
        self.daily_mids = mids


    def genJson(self):
        jsd = {
                "vid": self.id,
                "ip": self.ip,
                "name": self.name,
                "os": self.os,
                "arch": self.arch,
                "bot_ids": self.bot_ids,
                "status": self.status,
                "last_update_time": self.last_update_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]
                }
        return jsd


    def loadJson(self, dj):
        self.id = dj.get("vid", -1)
        self.ip = dj.get("ip", "")
        self.name = dj.get("name", "")
        self.os = dj.get("os", "")
        self.arch = dj.get("arch", "")  # Default to empty string if "arch" is missing
        self.status = dj.get("status", "")
        self.bot_ids = dj.get("bot_ids", [])
        self.last_update_time = datetime.strptime(dj.get("last_update_time", "1970-01-01 00:00:00.000"), "%Y-%m-%d %H:%M:%S.%f")
