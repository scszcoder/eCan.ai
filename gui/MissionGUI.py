import sys
import random
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *
from ebbot import *
from missions import *

class MissionNewWin(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(MissionNewWin, self).__init__(parent)
        self.text = "new mission"
        self.parent = parent
        self.newMission = None
        self.owner = None
        self.mainWidget = QtWidgets.QWidget()
        self.tabs = QtWidgets.QTabWidget()
        self.pubAttrWidget = QtWidgets.QWidget()
        self.prvAttrWidget = QtWidgets.QWidget()
        self.actItemsWidget = QtWidgets.QWidget()

        self.save_button = QtWidgets.QPushButton("Save")
        self.cancel_button = QtWidgets.QPushButton("Cancel")

        self.action_confirm_cancel_button = QtWidgets.QPushButton("Cancel")
        self.action_confirm_button = QtWidgets.QPushButton("Confirm")
        self.action_confirm_ok_button = QtWidgets.QPushButton("OK")

        self.layout = QtWidgets.QVBoxLayout(self)
        self.bLayout = QtWidgets.QHBoxLayout(self)
        # self.actionFrame.setLayout(self.bLayout)
        self.layout.addWidget(self.tabs)
        self.bLayout.addWidget(self.cancel_button)
        self.bLayout.addWidget(self.save_button)

        self.pubAttrWidget.layout = QtWidgets.QVBoxLayout(self)
        self.prvAttrWidget.layout = QtWidgets.QVBoxLayout(self)
        self.actItemsWidget.layout = QtWidgets.QVBoxLayout(self)

        self.text_label = QtWidgets.QLabel("Tag:", alignment=QtCore.Qt.AlignLeft)
        self.text_edit = QtWidgets.QLineEdit()
        self.text_edit.setPlaceholderText("input bot tag here")


        self.mission_type_label = QtWidgets.QLabel("Mission Type:", alignment=QtCore.Qt.AlignLeft)
        self.buy_rb = QtWidgets.QRadioButton("Buy Side")
        self.sell_rb = QtWidgets.QRadioButton("Sell Side")
        self.buy_rb.isChecked()

        self.buy_mission_type_label = QtWidgets.QLabel("Buy Mission Type:", alignment=QtCore.Qt.AlignLeft)
        self.buy_mission_type_sel = QtWidgets.QComboBox()
        self.buy_mission_type_sel.addItem('Simple Buy')
        self.buy_mission_type_sel.addItem('Feedback Rating')
        self.buy_mission_type_sel.addItem('Review')

        self.sell_mission_type_label = QtWidgets.QLabel("Sell Mission Type:", alignment=QtCore.Qt.AlignLeft)
        self.sell_mission_type_sel = QtWidgets.QComboBox()
        self.sell_mission_type_sel.addItem('Prepare Shipping Label')
        self.sell_mission_type_sel.addItem('Check Inventory')
        self.sell_mission_type_sel.addItem('Process Messages')
        self.sell_mission_type_sel.addItem('Handle Return')
        self.sell_mission_type_sel.addItem('Handle Replacement')
        self.sell_mission_type_sel.addItem('Handle Marketing')
        self.sell_mission_type_sel.addItem('Custom Work')
        self.sell_mission_type_sel.addItem('Other')

        self.repeat_label = QtWidgets.QLabel("# of time to be executed:", alignment=QtCore.Qt.AlignLeft)
        self.repeat_edit = QtWidgets.QLineEdit()
        self.repeat_edit.setPlaceholderText("1")

        self.search_kw_label = QtWidgets.QLabel("Search Phrase:", alignment=QtCore.Qt.AlignLeft)
        self.search_kw_edit = QtWidgets.QLineEdit()
        self.search_kw_edit.setPlaceholderText("Example: jump rope")

        self.search_cat_label = QtWidgets.QLabel("Search Category:", alignment=QtCore.Qt.AlignLeft)
        self.search_cat_edit = QtWidgets.QLineEdit()
        self.search_cat_edit.setPlaceholderText("Example: Home&Garden->Garden Tools")


        self.pseudo_store_label = QtWidgets.QLabel("Pseudo Store:", alignment=QtCore.Qt.AlignLeft)
        self.pseudo_store_edit = QtWidgets.QLineEdit()
        self.pseudo_store_edit.setPlaceholderText("Example: Jacks Shop, must be differrent from the actual store name.")

        self.pseudo_brand_label = QtWidgets.QLabel("Pseudo Brand:", alignment=QtCore.Qt.AlignLeft)
        self.pseudo_brand_edit = QtWidgets.QLineEdit()
        self.pseudo_brand_edit.setPlaceholderText("Example: abc, must be differrent from the actual brand name.")

        self.pseudo_asin_label = QtWidgets.QLabel("Pseudo ASIN code:", alignment=QtCore.Qt.AlignLeft)
        self.pseudo_asin_edit = QtWidgets.QLineEdit()
        self.pseudo_asin_edit.setPlaceholderText("Example: 123, must be differrent from the actual ASIN code/Serial code.")

        self.pubAttrLine1Layout = QtWidgets.QHBoxLayout(self)
        self.pubAttrLine1Layout.addWidget(self.text_label)
        self.pubAttrLine1Layout.addWidget(self.text_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine1Layout)

        self.pubAttrLine2Layout = QtWidgets.QHBoxLayout(self)
        self.pubAttrLine2Layout.addWidget(self.mission_type_label)
        self.pubAttrLine2Layout.addWidget(self.buy_rb)
        self.pubAttrLine2Layout.addWidget(self.sell_rb)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine2Layout)

        self.pubAttrLine3Layout = QtWidgets.QHBoxLayout(self)
        self.pubAttrLine3Layout.addWidget(self.repeat_label)
        self.pubAttrLine3Layout.addWidget(self.repeat_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine3Layout)

        self.pubAttrLine4Layout = QtWidgets.QHBoxLayout(self)
        self.pubAttrLine4Layout.addWidget(self.search_kw_label)
        self.pubAttrLine4Layout.addWidget(self.search_kw_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine4Layout)

        self.pubAttrLine5Layout = QtWidgets.QHBoxLayout(self)
        self.pubAttrLine5Layout.addWidget(self.search_cat_label)
        self.pubAttrLine5Layout.addWidget(self.search_cat_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine5Layout)


        self.pubAttrLine6Layout = QtWidgets.QHBoxLayout(self)
        self.pubAttrLine6Layout.addWidget(self.pseudo_store_label)
        self.pubAttrLine6Layout.addWidget(self.pseudo_store_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine6Layout)


        self.pubAttrLine7Layout = QtWidgets.QHBoxLayout(self)
        self.pubAttrLine7Layout.addWidget(self.pseudo_brand_label)
        self.pubAttrLine7Layout.addWidget(self.pseudo_brand_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine7Layout)


        self.pubAttrLine8Layout = QtWidgets.QHBoxLayout(self)
        self.pubAttrLine8Layout.addWidget(self.pseudo_asin_label)
        self.pubAttrLine8Layout.addWidget(self.pseudo_asin_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine8Layout)

        self.pubAttrWidget.setLayout(self.pubAttrWidget.layout)


        self.cus_fn_label = QtWidgets.QLabel("Customer First Name:", alignment=QtCore.Qt.AlignLeft)
        self.cus_fn_edit = QtWidgets.QLineEdit()
        self.cus_fn_edit.setPlaceholderText("input Customer First Name here")

        self.cus_ln_label = QtWidgets.QLabel("Customer Last Name:", alignment=QtCore.Qt.AlignLeft)
        self.cus_ln_edit = QtWidgets.QLineEdit()
        self.cus_ln_edit.setPlaceholderText("input Customer Last Name here")

        self.cus_nn_label = QtWidgets.QLabel("Customer Nick Name:", alignment=QtCore.Qt.AlignLeft)
        self.cus_nn_edit = QtWidgets.QLineEdit()
        self.cus_nn_edit.setPlaceholderText("input Customer Nick Name here")

        self.cus_id_label = QtWidgets.QLabel("Customer ID:", alignment=QtCore.Qt.AlignLeft)
        self.cus_id_edit = QtWidgets.QLineEdit()
        self.cus_id_edit.setPlaceholderText("Input Customer ID here")

        self.cus_sm_type_label = QtWidgets.QLabel("Customer Messenging Type:", alignment=QtCore.Qt.AlignLeft)
        self.cus_sm_type_sel = QtWidgets.QComboBox()
        self.cus_sm_type_sel.addItem('QQ')
        self.cus_sm_type_sel.addItem('WeChat')
        self.cus_sm_type_sel.addItem('Telegram')
        self.cus_sm_type_sel.addItem('WhatsApp')
        self.cus_sm_type_sel.addItem('Messenger')
        self.cus_sm_type_sel.addItem('Other')
        self.cus_sm_id_label = QtWidgets.QLabel("Customer Messenger ID:", alignment=QtCore.Qt.AlignLeft)
        self.cus_sm_id_edit = QtWidgets.QLineEdit()
        self.cus_sm_id_edit.setPlaceholderText("Customer Messenger ID here")

        self.cus_alt_sm_type_label = QtWidgets.QLabel("Customer Messenging Type:", alignment=QtCore.Qt.AlignLeft)
        self.cus_alt_sm_type_sel = QtWidgets.QComboBox()
        self.cus_alt_sm_type_sel.addItem('QQ')
        self.cus_alt_sm_type_sel.addItem('WeChat')
        self.cus_alt_sm_type_sel.addItem('Telegram')
        self.cus_alt_sm_type_sel.addItem('WhatsApp')
        self.cus_alt_sm_type_sel.addItem('Messenger')
        self.cus_alt_sm_type_sel.addItem('Other')
        self.cus_alt_sm_id_label = QtWidgets.QLabel("Customer Messenger ID:", alignment=QtCore.Qt.AlignLeft)
        self.cus_alt_sm_id_edit = QtWidgets.QLineEdit()
        self.cus_alt_sm_id_edit.setPlaceholderText("Customer Messenger ID here")
        self.cus_email_label = QtWidgets.QLabel("Customer Email:", alignment=QtCore.Qt.AlignLeft)
        self.cus_email_edit = QtWidgets.QLineEdit()
        self.cus_email_edit.setPlaceholderText("input Customer Email")
        self.cus_phone_label = QtWidgets.QLabel("Customer Contact Phone:", alignment=QtCore.Qt.AlignLeft)
        self.cus_phone_edit = QtWidgets.QLineEdit()
        self.cus_phone_edit.setPlaceholderText("input Customer Contact Phone here")
        self.asin_label = QtWidgets.QLabel("Product ASIN/ID:", alignment=QtCore.Qt.AlignLeft)
        self.asin_edit = QtWidgets.QLineEdit()
        self.asin_edit.setPlaceholderText("input product ASIN/ID here")
        self.title_label = QtWidgets.QLabel("Product Title:", alignment=QtCore.Qt.AlignLeft)
        self.title_edit = QtWidgets.QLineEdit()
        self.title_edit.setPlaceholderText("input product title here")
        self.seller_label = QtWidgets.QLabel("Product Seller:", alignment=QtCore.Qt.AlignLeft)
        self.seller_edit = QtWidgets.QLineEdit()
        self.seller_edit.setPlaceholderText("input seller here")
        self.rating_label = QtWidgets.QLabel("Rating:", alignment=QtCore.Qt.AlignLeft)
        self.rating_edit = QtWidgets.QLineEdit()
        self.rating_edit.setPlaceholderText("input rating here")
        self.product_image_label = QtWidgets.QLabel("Top Image:", alignment=QtCore.Qt.AlignLeft)
        self.product_image_edit = QtWidgets.QLineEdit()
        self.product_image_edit.setPlaceholderText("input image path here")

        self.prvAttrLine1Layout = QtWidgets.QHBoxLayout(self)
        self.prvAttrLine1Layout.addWidget(self.cus_id_label)
        self.prvAttrLine1Layout.addWidget(self.cus_id_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine1Layout)

        self.prvAttrLine2Layout = QtWidgets.QHBoxLayout(self)
        self.prvAttrLine2Layout.addWidget(self.cus_sm_id_label)
        self.prvAttrLine2Layout.addWidget(self.cus_sm_id_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine2Layout)

        self.prvAttrLine3Layout = QtWidgets.QHBoxLayout(self)
        self.prvAttrLine3Layout.addWidget(self.asin_label)
        self.prvAttrLine3Layout.addWidget(self.asin_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine3Layout)

        self.prvAttrLine4Layout = QtWidgets.QHBoxLayout(self)
        self.prvAttrLine4Layout.addWidget(self.title_label)
        self.prvAttrLine4Layout.addWidget(self.title_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine4Layout)

        self.prvAttrLine5Layout = QtWidgets.QHBoxLayout(self)
        self.prvAttrLine5Layout.addWidget(self.seller_label)
        self.prvAttrLine5Layout.addWidget(self.seller_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine5Layout)

        self.prvAttrLine6Layout = QtWidgets.QHBoxLayout(self)
        self.prvAttrLine6Layout.addWidget(self.rating_label)
        self.prvAttrLine6Layout.addWidget(self.rating_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine6Layout)

        self.prvAttrLine7Layout = QtWidgets.QHBoxLayout(self)
        self.prvAttrLine7Layout.addWidget(self.product_image_label)
        self.prvAttrLine7Layout.addWidget(self.product_image_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine7Layout)

        self.prvAttrLine8Layout = QtWidgets.QHBoxLayout(self)
        self.prvAttrLine8Layout.addWidget(self.buy_mission_type_label)
        self.prvAttrLine8Layout.addWidget(self.buy_mission_type_sel)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine8Layout)

        self.prvAttrLine9Layout = QtWidgets.QHBoxLayout(self)
        self.prvAttrLine9Layout.addWidget(self.sell_mission_type_label)
        self.prvAttrLine9Layout.addWidget(self.sell_mission_type_sel)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine9Layout)


        self.prvAttrWidget.setLayout(self.prvAttrWidget.layout)

        self.bought_label = QtWidgets.QLabel("Item Bought:", alignment=QtCore.Qt.AlignLeft)
        self.bought_cb = QtWidgets.QCheckBox()
        self.received_label = QtWidgets.QLabel("Item Received:", alignment=QtCore.Qt.AlignLeft)
        self.received_cb = QtWidgets.QCheckBox()
        self.fb_rated_label = QtWidgets.QLabel("Feedback Rated:", alignment=QtCore.Qt.AlignLeft)
        self.fb_rated_cb = QtWidgets.QCheckBox()
        self.fb_reviewed_label = QtWidgets.QLabel("Feedback Reviewed:", alignment=QtCore.Qt.AlignLeft)
        self.fb_reviewed_cb = QtWidgets.QCheckBox()


        self.actItemsLine1Layout = QtWidgets.QHBoxLayout(self)
        self.actItemsLine1Layout.addWidget(self.bought_label)
        self.actItemsLine1Layout.addWidget(self.bought_cb)
        self.actItemsWidget.layout.addLayout(self.actItemsLine1Layout)

        self.actItemsLine2Layout = QtWidgets.QHBoxLayout(self)
        self.actItemsLine2Layout.addWidget(self.received_label)
        self.actItemsLine2Layout.addWidget(self.received_cb)
        self.actItemsWidget.layout.addLayout(self.actItemsLine2Layout)

        self.actItemsLine3Layout = QtWidgets.QHBoxLayout(self)
        self.actItemsLine3Layout.addWidget(self.fb_rated_label)
        self.actItemsLine3Layout.addWidget(self.fb_rated_cb)
        self.actItemsWidget.layout.addLayout(self.actItemsLine3Layout)

        self.actItemsLine4Layout = QtWidgets.QHBoxLayout(self)
        self.actItemsLine4Layout.addWidget(self.fb_reviewed_label)
        self.actItemsLine4Layout.addWidget(self.fb_reviewed_cb)
        self.actItemsWidget.layout.addLayout(self.actItemsLine4Layout)

        self.actItemsWidget.setLayout(self.actItemsWidget.layout)


        self.tabs.addTab(self.pubAttrWidget, "Pub Attributes")
        self.tabs.addTab(self.prvAttrWidget, "Private Attributes")
        self.tabs.addTab(self.actItemsWidget, "Action Items")

        self.layout.addWidget(self.tabs)
        self.layout.addLayout(self.bLayout)

        # self.layout.addWidget(self.text)
        # self.layout.addRow(self.browser_path_label, self.browser_path_line_edit);
        # self.layout.addRow(self.date_time_label, self.date_time_start)
        # self.layout.addRow(self.task_settings_button)
        # self.layout.addRow(self.cancel_button, self.save_button)

        self.save_button.clicked.connect(self.saveMission)
        self.cancel_button.clicked.connect(self.close)

        self.mainWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainWidget)

    def saveMission(self):
        print("saving bot....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        self.newMission = EBMISSION()


        if self.repeat_edit.text().isnumeric():
            self.newMission.pubAttributes.setNex(int(self.repeat_edit.text()))
        self.newMission.pubAttributes.setSearch(self.search_kw_edit.text(), self.search_cat_edit.text())
        if self.buy_rb.isChecked():
            self.newMission.pubAttributes.setType(0, "user", "Sell")
        elif self.sell_rb.isChecked():
            self.newMission.pubAttributes.setType(0, "user", "Buy")
        else:
            self.newMission.pubAttributes.setType(0, "user", "NA")

        self.newMission.privateAttributes.setFbType(self.buy_mission_type_sel.currentText())
        self.newMission.privateAttributes.setItem(self.asin_edit.text(), self.seller_edit.text(), self.title_edit.text(), self.product_image_edit.text(), self.rating_edit.text())

        print("adding new mission....")
        self.parent.addNewMission(self.newMission)
        self.close()


    def selFile(self):
        # File actions
        fdir = self.fsel.getExistingDirectory()
        print(fdir)
        return fdir

    def setOwner(self, owner):
        self.owner = owner

    def setMission(self, mission):
        self.newMission = mission
