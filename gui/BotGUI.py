import sys
import random
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *
from ebbot import *

class BotNewWin(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(BotNewWin, self).__init__(parent)

        self.newBot = None

    # def __init__(self):
    #     super().__init__()
        self.mainWidget = QtWidgets.QWidget()
        self.parent = parent
        self.text = "new bot"
        self.pubpflWidget = QtWidgets.QWidget()
        self.prvpflWidget = QtWidgets.QWidget()
        self.setngsWidget = QtWidgets.QWidget()
        self.statWidget = QtWidgets.QWidget()
        self.tabs = QtWidgets.QTabWidget()
        self.actionFrame = QtWidgets.QFrame()

        self.fsel = QtWidgets.QFileDialog()
        self.mode = "new"

        self.save_button = QtWidgets.QPushButton("Save")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.text = QtWidgets.QLabel("Hello World", alignment=QtCore.Qt.AlignCenter)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.bLayout = QtWidgets.QHBoxLayout(self)
        # self.actionFrame.setLayout(self.bLayout)
        self.layout.addWidget(self.tabs)
        self.bLayout.addWidget(self.cancel_button)
        self.bLayout.addWidget(self.save_button)


        self.pubpflWidget.layout = QtWidgets.QVBoxLayout(self)
        self.prvpflWidget.layout = QtWidgets.QVBoxLayout(self)
        self.setngsWidget.layout = QtWidgets.QVBoxLayout(self)
        self.statWidget.layout = QtWidgets.QVBoxLayout(self)

        self.tag_label = QtWidgets.QLabel("Tag:", alignment=QtCore.Qt.AlignLeft)
        self.tag_edit = QtWidgets.QLineEdit("")
        self.tag_edit.setPlaceholderText("input bot tag here")

        self.icon_label = QtWidgets.QLabel("Icon Image:")
        self.icon_path_edit = QtWidgets.QLineEdit("")
        self.icon_path_edit.setPlaceholderText("input icon img file path here")

        self.icon_fs_button = QtWidgets.QPushButton("...")
        self.icon_fs_button.clicked.connect(self.selFile)

        # needs to add icon for better UE

        self.pfn_label = QtWidgets.QLabel("Pseudo First Name:", alignment=QtCore.Qt.AlignLeft)
        self.pfn_edit = QtWidgets.QLineEdit()
        self.pfn_edit.setPlaceholderText("input Pseudo First Name here")
        self.pln_label = QtWidgets.QLabel("Pseudo Last Name:", alignment=QtCore.Qt.AlignLeft)
        self.pln_edit = QtWidgets.QLineEdit()
        self.pln_edit.setPlaceholderText("input Pseudo Last Name here")
        self.pnn_label = QtWidgets.QLabel("Pseudo Nick Name:", alignment=QtCore.Qt.AlignLeft)
        self.pnn_edit = QtWidgets.QLineEdit()
        self.pnn_edit.setPlaceholderText("input Pseudo Nick Name here")
        self.loccity_label = QtWidgets.QLabel("Location City:", alignment=QtCore.Qt.AlignLeft)
        self.loccity_edit = QtWidgets.QLineEdit()
        self.loccity_edit.setPlaceholderText("input City here")
        self.locstate_label = QtWidgets.QLabel("Location State:", alignment=QtCore.Qt.AlignLeft)
        self.locstate_edit = QtWidgets.QLineEdit()
        self.locstate_edit.setPlaceholderText("input State here")
        self.age_label = QtWidgets.QLabel("Age:", alignment=QtCore.Qt.AlignLeft)
        self.age_edit = QtWidgets.QLineEdit()
        self.pfn_edit.setPlaceholderText("input age here")
        self.mf_label = QtWidgets.QLabel("Gender:", alignment=QtCore.Qt.AlignLeft)
        self.m_rb = QtWidgets.QRadioButton("Male")
        self.f_rb = QtWidgets.QRadioButton("Female")
        self.gna_rb = QtWidgets.QRadioButton("Unknown")
        self.gna_rb.isChecked()

        self.pubpflLine1Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine1Layout.addWidget(self.tag_label)
        self.pubpflLine1Layout.addWidget(self.tag_edit)
        self.pubpflWidget.layout.addLayout(self.pubpflLine1Layout)

        self.pubpflLine2Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine2Layout.addWidget(self.icon_label)
        self.pubpflLine2Layout.addWidget(self.icon_path_edit)
        self.pubpflLine2Layout.addWidget(self.icon_fs_button)
        self.pubpflWidget.layout.addLayout(self.pubpflLine2Layout)

        self.pubpflLine3Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine3Layout.addWidget(self.pfn_label)
        self.pubpflLine3Layout.addWidget(self.pfn_edit)
        self.pubpflLine3Layout.addWidget(self.pln_label)
        self.pubpflLine3Layout.addWidget(self.pln_edit)
        self.pubpflWidget.layout.addLayout(self.pubpflLine3Layout)

        self.pubpflLine4Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine4Layout.addWidget(self.pnn_label)
        self.pubpflLine4Layout.addWidget(self.pnn_edit)
        self.pubpflWidget.layout.addLayout(self.pubpflLine4Layout)

        self.pubpflLine5Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine5Layout.addWidget(self.loccity_label)
        self.pubpflLine5Layout.addWidget(self.loccity_edit)
        self.pubpflLine5Layout.addWidget(self.locstate_label)
        self.pubpflLine5Layout.addWidget(self.locstate_edit)
        self.pubpflWidget.layout.addLayout(self.pubpflLine5Layout)

        self.pubpflLine6Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine6Layout.addWidget(self.age_label)
        self.pubpflLine6Layout.addWidget(self.age_edit)
        self.pubpflWidget.layout.addLayout(self.pubpflLine6Layout)

        self.pubpflLine7Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine7Layout.addWidget(self.mf_label)
        self.pubpflLine7Layout.addWidget(self.m_rb)
        self.pubpflLine7Layout.addWidget(self.f_rb)
        self.pubpflLine7Layout.addWidget(self.gna_rb)
        self.pubpflWidget.layout.addLayout(self.pubpflLine7Layout)

        # self.pubpflLine8Layout = QtWidgets.QHBoxLayout(self)
        # self.pubpflLine8Layout.addWidget(self.pnn_label)
        # self.pubpflLine8Layout.addWidget(self.pnn_edit)
        # self.pubpflWidget.layout.addLayout(self.pubpflLine8Layout)

        self.pubpflWidget.setLayout(self.pubpflWidget.layout)

        self.fn_label = QtWidgets.QLabel("First Name:", alignment=QtCore.Qt.AlignLeft)
        self.fn_edit = QtWidgets.QLineEdit()
        self.fn_edit.setPlaceholderText("input First Name here")
        self.ln_label = QtWidgets.QLabel("Last Name:", alignment=QtCore.Qt.AlignLeft)
        self.ln_edit = QtWidgets.QLineEdit()
        self.ln_edit.setPlaceholderText("input Last Name here")
        self.phone_label = QtWidgets.QLabel("Contact Phone:", alignment=QtCore.Qt.AlignLeft)
        self.phone_edit = QtWidgets.QLineEdit()
        self.phone_edit.setPlaceholderText("(optional) contact phone number here")
        self.em_label = QtWidgets.QLabel("Email:", alignment=QtCore.Qt.AlignLeft)
        self.em_edit = QtWidgets.QLineEdit()
        self.em_edit.setPlaceholderText("input email here")
        self.empw_label = QtWidgets.QLabel("Email Password:", alignment=QtCore.Qt.AlignLeft)
        self.empw_edit = QtWidgets.QLineEdit()
        self.empw_edit.setPlaceholderText("input Email Password here")
        self.backem_label = QtWidgets.QLabel("Back Up Email:", alignment=QtCore.Qt.AlignLeft)
        self.backem_edit = QtWidgets.QLineEdit()
        self.backem_edit.setPlaceholderText("(optional) back up email here")
        self.acctpw_label = QtWidgets.QLabel("E-Business Account Password:", alignment=QtCore.Qt.AlignLeft)
        self.acctpw_edit = QtWidgets.QLineEdit("")
        self.acctpw_edit.setPlaceholderText("(optional) E-Business Account Password here")

        self.prvpflLine1Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1Layout.addWidget(self.fn_label)
        self.prvpflLine1Layout.addWidget(self.fn_edit)
        self.prvpflLine1Layout.addWidget(self.ln_label)
        self.prvpflLine1Layout.addWidget(self.ln_edit)
        self.prvpflWidget.layout.addLayout(self.prvpflLine1Layout)

        self.prvpflLine2Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine2Layout.addWidget(self.phone_label)
        self.prvpflLine2Layout.addWidget(self.phone_edit)
        self.prvpflWidget.layout.addLayout(self.prvpflLine2Layout)

        self.prvpflLine3Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine3Layout.addWidget(self.em_label)
        self.prvpflLine3Layout.addWidget(self.em_edit)
        self.prvpflLine3Layout.addWidget(self.empw_label)
        self.prvpflLine3Layout.addWidget(self.empw_edit)
        self.prvpflWidget.layout.addLayout(self.prvpflLine3Layout)

        self.prvpflLine4Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine4Layout.addWidget(self.backem_label)
        self.prvpflLine4Layout.addWidget(self.backem_edit)
        self.prvpflWidget.layout.addLayout(self.prvpflLine4Layout)

        self.prvpflLine5Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine5Layout.addWidget(self.acctpw_label)
        self.prvpflLine5Layout.addWidget(self.acctpw_edit)
        self.prvpflWidget.layout.addLayout(self.prvpflLine5Layout)

        self.prvpflWidget.setLayout(self.prvpflWidget.layout)

        self.browser_label = QtWidgets.QLabel("App Name:", alignment=QtCore.Qt.AlignLeft)
        self.browser_sel = QtWidgets.QComboBox()
        self.browser_sel.addItem('ADS')
        self.browser_sel.addItem('Multi-Login')
        self.browser_sel.addItem('SuperBrowser')
        self.browser_sel.addItem('Chrome')
        self.browser_sel.addItem('Firefox')
        self.browser_sel.addItem('Edge')
        self.browser_sel.addItem('Other')

        self.os_label = QtWidgets.QLabel("OS Type:", alignment=QtCore.Qt.AlignLeft)
        self.os_sel = QtWidgets.QComboBox()
        self.os_sel.addItem('Windows')
        self.os_sel.addItem('MacOS')
        self.os_sel.addItem('ChromeOS')
        self.os_sel.addItem('Linux')
        self.machine_label = QtWidgets.QLabel("Machine Type:", alignment=QtCore.Qt.AlignLeft)
        self.machine_sel = QtWidgets.QComboBox()
        self.machine_sel.addItem('Mac')
        self.machine_sel.addItem('Intel')
        self.ebtype_label = QtWidgets.QLabel("EBusiness Type:", alignment=QtCore.Qt.AlignLeft)
        self.ebtype_sel = QtWidgets.QComboBox()
        self.ebtype_sel.addItem('Amazon')
        self.ebtype_sel.addItem('EBay')
        self.ebtype_sel.addItem('Wish')
        self.ebtype_sel.addItem('Shopify')

        self.setngsLine1Layout = QtWidgets.QHBoxLayout(self)
        self.setngsLine1Layout.addWidget(self.machine_label)
        self.setngsLine1Layout.addWidget(self.machine_sel)
        self.setngsWidget.layout.addLayout(self.setngsLine1Layout)

        self.setngsLine2Layout = QtWidgets.QHBoxLayout(self)
        self.setngsLine2Layout.addWidget(self.os_label)
        self.setngsLine2Layout.addWidget(self.os_sel)
        self.setngsWidget.layout.addLayout(self.setngsLine2Layout)

        self.setngsLine3Layout = QtWidgets.QHBoxLayout(self)
        self.setngsLine3Layout.addWidget(self.browser_label)
        self.setngsLine3Layout.addWidget(self.browser_sel)
        self.setngsWidget.layout.addLayout(self.setngsLine3Layout)

        self.setngsLine4Layout = QtWidgets.QHBoxLayout(self)
        self.setngsLine4Layout.addWidget(self.ebtype_label)
        self.setngsLine4Layout.addWidget(self.ebtype_sel)
        self.setngsWidget.layout.addLayout(self.setngsLine4Layout)

        self.setngsWidget.setLayout(self.setngsWidget.layout)

        self.state_label = QtWidgets.QLabel("Enabled:", alignment=QtCore.Qt.AlignLeft)
        self.state_en = QtWidgets.QCheckBox()
        self.state_en.setCheckState(QtCore.Qt.CheckState.Checked)
        self.level_label = QtWidgets.QLabel("Level:", alignment=QtCore.Qt.AlignLeft)
        self.level_sel = QtWidgets.QComboBox()
        self.level_sel.addItem('Green')
        self.level_sel.addItem('Normal')

        self.statLine1Layout = QtWidgets.QHBoxLayout(self)
        self.statLine1Layout.addWidget(self.state_label)
        self.statLine1Layout.addWidget(self.state_en)
        self.statWidget.layout.addLayout(self.statLine1Layout)

        self.statLine2Layout = QtWidgets.QHBoxLayout(self)
        self.statLine2Layout.addWidget(self.level_label)
        self.statLine2Layout.addWidget(self.level_sel)
        self.statWidget.layout.addLayout(self.statLine2Layout)

        self.statWidget.setLayout(self.statWidget.layout)

        self.tabs.addTab(self.pubpflWidget, "Pub Profile")
        self.tabs.addTab(self.prvpflWidget, "Private Profile")
        self.tabs.addTab(self.setngsWidget, "Settings")
        self.tabs.addTab(self.statWidget, "Status")

        self.layout.addWidget(self.tabs)
        self.layout.addLayout(self.bLayout)

        # self.layout.addWidget(self.text)
        # self.layout.addRow(self.browser_path_label, self.browser_path_line_edit);
        # self.layout.addRow(self.date_time_label, self.date_time_start)
        # self.layout.addRow(self.task_settings_button)
        # self.layout.addRow(self.cancel_button, self.save_button)

        self.save_button.clicked.connect(self.saveBot)
        self.cancel_button.clicked.connect(self.close)

        self.mainWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainWidget)

    def setBot(self, bot):
        self.newBot = bot
        #now populate the GUI to reflect info in this bot.
        self.acctpw_edit.setText(bot.getAcctPw())
        self.age_edit.setText(str(bot.getAge()))
        self.backem_edit.setText(bot.getBackEm())
        self.loccity_edit.setText(bot.getLocation())
        self.em_edit.setText(bot.getEmail())
        self.empw_edit.setText(bot.getEmPW())
        self.fn_edit.setText(bot.getFn())
        self.ln_edit.setText(bot.getLn())
        #self.pln_edit.setText()
        #self.pfn_edit.setText()
        #self.pnn_edit.setText()
        self.phone_edit.setText(bot.getPhone())
        self.locstate_edit.setText(bot.getLocation())
        # self.icon_path_edit.setText(bot.getIconLink())
        #self.tag_edit.setText()
        if bot.getGender() == "Male":
            self.m_rb.setChecked(True)
        elif bot.getGender() == "Female":
            self.f_rb.setChecked(True)
        else:
            self.gna_rb.setChecked(True)
        self.ebtype_sel.setCurrentText(bot.getPlatform())
        self.os_sel.setCurrentText(bot.getOS())
        self.browser_sel.setCurrentText(bot.getBrowser())
        self.machine_sel.setCurrentText(bot.getMachine())
        self.level_sel.setCurrentText(bot.getLevel())

    def setOwner(self, owner):
        self.owner = owner
        self.newBot.setOwner(owner)

    def saveBot(self):
        print("saving bot....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        if self.mode == "new":
            self.newBot = EBBOT()

        self.newBot.pubProfile.setPseudoName(self.pnn_edit.text())
        self.newBot.pubProfile.setLoc(self.loccity_edit.text() + "|" + self.locstate_edit.text())
        if self.m_rb.isChecked():
            self.newBot.pubProfile.setPersonal(self.age_edit.text(), "Male")
        elif self.f_rb.isChecked():
            self.newBot.pubProfile.setPersonal(self.age_edit.text(), "Female")
        else:
            self.newBot.pubProfile.setPersonal(self.age_edit.text(), "NA")


        self.newBot.privateProfile.setName(self.fn_edit.text(), self.ln_edit.text())
        self.newBot.privateProfile.setAcct(self.em_edit.text(), self.empw_edit.text(), self.phone_edit.text(), self.backem_edit.text(), self.acctpw_edit.text())

        self.newBot.settings.setComputer(self.ebtype_sel.currentText(), self.os_sel.currentText(), self.machine_sel.currentText(), self.browser_sel.currentText())
        if self.mode == "new":
            print("adding new bot....")
            self.parent.addNewBot(self.newBot)
        elif self.mode == "update":
            print("update a bot....")
            self.parent.updateABot(self.newBot)

        self.close()
        # print(self.parent)

    def selFile(self):
        # File actions
        fdir = self.fsel.getExistingDirectory()
        print(fdir)
        return fdir

    def setMode(self, mode):
        self.mode = mode
        if self.mode == "new":
            self.setWindowTitle('Adding a new bot')
        elif self.mode == "update":
            self.setWindowTitle('Updating a new bot')




