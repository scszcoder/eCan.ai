import sys
import random
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *
from ebbot import *
from missions import *


class SkillListView(QtWidgets.QListView):
    def __init__(self, parent):
        super(SkillListView, self).__init__()
        self.selected_row = None
        self.parent = parent
        self.homepath = parent.homepath

    def mousePressEvent(self, e):
        if e.type() == QtCore.QEvent.MouseButtonPress:
            if e.button() == QtCore.Qt.LeftButton:
                print("row:", self.indexAt(e.pos()).row())
                self.selected_row = self.indexAt(e.pos()).row()
                self.parent.updateSelectedSkill(self.selected_row)



class WORKSKILL(QtGui.QStandardItem):
    def __init__(self, homepath, platform, app, applink, site, sitelink, action):
        super().__init__()
        self.platform = platform
        self.app = app
        self.applink = applink
        self.site = site
        self.homepath = homepath
        self.sitelink = sitelink
        self.action = action
        self.name = platform+"_"+app+"_"+site+"_"+action

        self.setText(self.name)
        self.icon = QtGui.QIcon(homepath+'/resource/images/icons/skills-78.png')
        self.setIcon(self.icon)

    def getData(self):
        return self.platform, self.app, self.applink, self.site, self.sitelink, self.action


class MissionNewWin(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(MissionNewWin, self).__init__(parent)
        self.text = "new mission"
        self.parent = parent
        self.homepath = parent.homepath
        self.newMission = None
        self.owner = None

        self.selected_skill_row = None
        self.selected_skill_item = None

        self.selected_skill_platform = "Windows"
        self.selected_skill_app = "Chrome"
        self.selected_skill_app_link = ""
        self.selected_skill_site = "Amazon"
        self.selected_skill_site_link = ""
        self.selected_skill_action = "Browse"

        self.mainWidget = QtWidgets.QWidget()
        self.tabs = QtWidgets.QTabWidget()
        self.pubAttrWidget = QtWidgets.QWidget()
        self.prvAttrWidget = QtWidgets.QWidget()
        self.actItemsWidget = QtWidgets.QWidget()

        self.skillPanel = QtWidgets.QFrame()
        self.skillPanelLayout = QtWidgets.QVBoxLayout(self)

        self.skillListView = SkillListView(self)
        self.skillListView.installEventFilter(self)


        self.skillModel = QtGui.QStandardItemModel(self.skillListView)

        self.skillListView.setModel(self.skillModel)
        self.skillListView.setViewMode(QtWidgets.QListView.IconMode)
        self.skillListView.setMovement(QtWidgets.QListView.Snap)


        self.skillNameLabel = QtWidgets.QLabel("Skill Name:", alignment=QtCore.Qt.AlignLeft)
        self.skillNameEdit = QtWidgets.QLineEdit("")
        self.skillNameList = QtCore.QStringListModel()
        self.skillNameCompleter = QtWidgets.QCompleter(self.skillNameList, self)
        self.skillNameCompleter.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.skillNameEdit.setCompleter(self.skillNameCompleter)

        self.skillPlatformLabel = QtWidgets.QLabel("Skill Platform:", alignment=QtCore.Qt.AlignLeft)
        self.skill_platform_sel = QtWidgets.QComboBox()
        self.skill_platform_sel.addItem('Windows')
        self.skill_platform_sel.addItem('Mac')
        self.skill_platform_sel.addItem('Linux')
        self.skill_platform_sel.currentTextChanged.connect(self.skillPlatformSel_changed)


        self.skillAppLabel = QtWidgets.QLabel("Skill App:", alignment=QtCore.Qt.AlignLeft)
        self.skill_app_sel = QtWidgets.QComboBox()
        self.skill_app_sel.addItem('Chrome')
        self.skill_app_sel.addItem('ADS Power')
        self.skill_app_sel.addItem('Multi-Login')
        self.skill_app_sel.addItem('FireFox')
        self.skill_app_sel.addItem('Edge')
        self.skill_app_sel.addItem('Custom')
        self.skill_app_sel.currentTextChanged.connect(self.skillAppSel_changed)

        self.skillCustomAppNameLabel = QtWidgets.QLabel("Custome App:", alignment=QtCore.Qt.AlignLeft)
        self.skillCustomAppNameEdit = QtWidgets.QLineEdit("")

        self.skillCustomAppLinkLabel = QtWidgets.QLabel("Custome App Path:", alignment=QtCore.Qt.AlignLeft)
        self.skillCustomAppLinkEdit = QtWidgets.QLineEdit("")
        self.skillCustomAppLinkButton = QtWidgets.QPushButton("...")
        self.skillCustomAppLinkButton.clicked.connect(self.chooseAppLinkDir)

        self.skillSiteLabel = QtWidgets.QLabel("Skill Site:", alignment=QtCore.Qt.AlignLeft)
        self.skill_site_sel = QtWidgets.QComboBox()
        self.skill_site_sel.addItem('Amazon')
        self.skill_site_sel.addItem('Ebay')
        self.skill_site_sel.addItem('Etsy')
        self.skill_site_sel.addItem('Walmart')
        self.skill_site_sel.addItem('Wish')
        self.skill_site_sel.addItem('AliExpress')
        self.skill_site_sel.addItem('Wayfair')
        self.skill_site_sel.addItem('Custom')
        self.skill_site_sel.currentTextChanged.connect(self.skillSiteSel_changed)

        self.skillCustomSiteNameLabel = QtWidgets.QLabel("Custom Site:", alignment=QtCore.Qt.AlignLeft)
        self.skillCustomSiteNameEdit = QtWidgets.QLineEdit("")
        self.skillCustomSiteLinkLabel = QtWidgets.QLabel("Custom Site Html:", alignment=QtCore.Qt.AlignLeft)
        self.skillCustomSiteLinkEdit = QtWidgets.QLineEdit("")

        self.skillActionLabel = QtWidgets.QLabel("Skill Action:", alignment=QtCore.Qt.AlignLeft)
        self.skill_action_sel = QtWidgets.QComboBox()
        self.skill_action_sel.addItem('BuyOnly')
        self.skill_action_sel.addItem('BuyWithPositiveFeedback')
        self.skill_action_sel.addItem('Browse')
        self.skill_action_sel.addItem('ManageOffers')
        self.skill_action_sel.addItem('ManageReturnRequest')
        self.skill_action_sel.addItem('BuyShippingLabel')
        self.skill_action_sel.addItem('FillShippingTracking')
        self.skill_action_sel.addItem('ManageReplacements')
        self.skill_action_sel.addItem('ManageRefund')
        self.skill_action_sel.addItem('Custom')
        self.skill_action_sel.currentTextChanged.connect(self.skillActionSel_changed)

        self.skillCustomActionLabel = QtWidgets.QLabel("Custom Action:", alignment=QtCore.Qt.AlignLeft)
        self.skillCustomActionEdit = QtWidgets.QLineEdit("")

        self.skillScrollLabel = QtWidgets.QLabel("Required Skills:", alignment=QtCore.Qt.AlignLeft)
        self.skillScroll = QtWidgets.QScrollArea()
        self.skillScroll.setWidget(self.skillListView)
        self.skillScrollArea = QtWidgets.QWidget()
        self.skillScrollLayout = QtWidgets.QVBoxLayout(self)

        self.skillScrollLayout.addWidget(self.skillScrollLabel)
        self.skillScrollLayout.addWidget(self.skillScroll)
        self.skillScrollArea.setLayout(self.skillScrollLayout)

        self.skillButtonsArea = QtWidgets.QWidget()
        self.skillButtonsLayout = QtWidgets.QVBoxLayout(self)
        self.skill_add_button = QtWidgets.QPushButton("Add Skill")
        self.skill_add_button.clicked.connect(self.addSkill)

        self.skill_remove_button = QtWidgets.QPushButton("Remove Skill")
        self.skill_remove_button.clicked.connect(self.removeSkill)

        self.skillButtonsLayout.addWidget(self.skill_add_button)
        self.skillButtonsLayout.addWidget(self.skill_remove_button)
        self.skillButtonsArea.setLayout(self.skillButtonsLayout)

        self.skillArea = QtWidgets.QWidget()
        self.skillAreaLayout = QtWidgets.QHBoxLayout(self)
        self.skillAreaLayout.addWidget(self.skillScrollArea)
        self.skillAreaLayout.addWidget(self.skillButtonsArea)
        self.skillArea.setLayout(self.skillAreaLayout)


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

        self.ticket_label = QtWidgets.QLabel("Ticket Number:", alignment=QtCore.Qt.AlignLeft)
        self.ticket_edit = QtWidgets.QLineEdit()
        self.ticket_edit.setReadOnly(True)

        self.mid_label = QtWidgets.QLabel("Mission ID:", alignment=QtCore.Qt.AlignLeft)
        self.mid_edit = QtWidgets.QLineEdit()
        self.mid_edit.setReadOnly(True)


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
        self.pubAttrLine1Layout.addWidget(self.ticket_label)
        self.pubAttrLine1Layout.addWidget(self.ticket_edit)
        self.pubAttrLine1Layout.addWidget(self.mid_label)
        self.pubAttrLine1Layout.addWidget(self.mid_edit)
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

        self.pubpflLine9Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine9Layout.addWidget(self.skillPlatformLabel)
        self.pubpflLine9Layout.addWidget(self.skill_platform_sel)
        self.pubpflLine9Layout.addWidget(self.skillAppLabel)
        self.pubpflLine9Layout.addWidget(self.skill_app_sel)
        self.pubpflLine9Layout.addWidget(self.skillSiteLabel)
        self.pubpflLine9Layout.addWidget(self.skill_site_sel)
        self.pubpflLine9Layout.addWidget(self.skillActionLabel)
        self.pubpflLine9Layout.addWidget(self.skill_action_sel)
        self.skillPanelLayout.addLayout(self.pubpflLine9Layout)


        self.pubpflLine11Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine11Layout.addWidget(self.skillCustomAppNameLabel)
        self.pubpflLine11Layout.addWidget(self.skillCustomAppNameEdit)
        self.pubpflLine11Layout.addWidget(self.skillCustomAppLinkLabel)
        self.pubpflLine11Layout.addWidget(self.skillCustomAppLinkEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine11Layout)

        self.pubpflLine12Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine12Layout.addWidget(self.skillCustomSiteNameLabel)
        self.pubpflLine12Layout.addWidget(self.skillCustomSiteNameEdit)
        self.pubpflLine12Layout.addWidget(self.skillCustomSiteLinkLabel)
        self.pubpflLine12Layout.addWidget(self.skillCustomSiteLinkEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine12Layout)

        self.pubpflLine13Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine13Layout.addWidget(self.skillCustomActionLabel)
        self.pubpflLine13Layout.addWidget(self.skillCustomActionEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine13Layout)

        self.hide_skill_custom_app()
        self.hide_skill_custom_site()
        self.hide_skill_custom_action()

        self.skillPanelLayout.addWidget(self.skillArea)
        self.skillPanel.setLayout(self.skillPanelLayout)

        self.skillPanel.setFrameStyle(QtWidgets.QFrame.Panel|QtWidgets.QFrame.Raised)

        self.pubAttrWidget.layout.addWidget(self.skillPanel)

        self.skillPanel = QtWidgets.QFrame()
        self.skillPanelLayout = QtWidgets.QVBoxLayout(self)




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


    def skillPlatformSel_changed(self):
        self.selected_skill_platform = self.skill_platform_sel.currentText()


    def skillAppSel_changed(self):
        print("app changed....")
        if self.skill_app_sel.currentText() != 'Custom':
            self.hide_skill_custom_app()
            self.selected_skill_app = self.skill_app_sel.currentText()
            self.selected_skill_app_link = ""

        else:
            self.show_skill_custom_app()
            self.selected_skill_app = self.skillCustomAppNameEdit.text()
            self.selected_skill_app_link = self.skillCustomAppLinkEdit.text()

    def skillSiteSel_changed(self):
        if self.skill_site_sel.currentText() != 'Custom':
            self.hide_skill_custom_site()
            self.selected_skill_site = self.skill_site_sel.currentText()
            self.selected_skill_site_link = ""

        else:
            self.show_skill_custom_site()
            self.selected_skill_site = self.skillCustomSiteNameEdit.text()
            self.selected_skill_site_link = self.skillCustomSiteLinkEdit.text()

    def skillActionSel_changed(self):
        if self.skill_action_sel.currentText() != 'Custom':
            self.hide_skill_custom_action()
            self.selected_skill_action = self.skill_action_sel.currentText()
        else:
            self.show_skill_custom_action()
            self.selected_skill_action = self.skillCustomActionEdit.text()




    def hide_skill_custom_app(self):
        self.skillCustomAppNameLabel.setVisible(False)
        self.skillCustomAppNameEdit.setVisible(False)
        self.skillCustomAppLinkLabel.setVisible(False)
        self.skillCustomAppLinkEdit.setVisible(False)

    def show_skill_custom_app(self):
        self.skillCustomAppNameLabel.setVisible(True)
        self.skillCustomAppNameEdit.setVisible(True)
        self.skillCustomAppLinkLabel.setVisible(True)
        self.skillCustomAppLinkEdit.setVisible(True)


    def hide_skill_custom_site(self):
        self.skillCustomSiteNameLabel.setVisible(False)
        self.skillCustomSiteNameEdit.setVisible(False)
        self.skillCustomSiteLinkLabel.setVisible(False)
        self.skillCustomSiteLinkEdit.setVisible(False)


    def show_skill_custom_site(self):
        self.skillCustomSiteNameLabel.setVisible(True)
        self.skillCustomSiteNameEdit.setVisible(True)
        self.skillCustomSiteLinkLabel.setVisible(True)
        self.skillCustomSiteLinkEdit.setVisible(True)

    def hide_skill_custom_action(self):
        self.skillCustomActionLabel.setVisible(False)
        self.skillCustomActionEdit.setVisible(False)

    def show_skill_custom_action(self):
        self.skillCustomActionLabel.setVisible(True)
        self.skillCustomActionEdit.setVisible(True)

    def chooseAppLinkDir(self):
        self.skillCustomAppLinkEdit.setText(str(QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory")))
        self.selected_skill_app_link = self.skillCustomAppLinkEdit.text()

    def addSkill(self):
        if self.skill_app_sel.currentText() == 'Custom':
            self.selected_skill_app = self.skillCustomAppNameEdit.text()
            self.selected_skill_app_link = self.skillCustomAppLinkEdit.text()

        if self.skill_site_sel.currentText() == 'Custom':
            self.selected_skill_site = self.skillCustomSiteNameEdit.text()
            self.selected_skill_site_link = self.skillCustomSiteLinkEdit.text()

        if self.skill_action_sel.currentText() == 'Custom':
            self.selected_skill_action = self.skillCustomActionEdit.text()

        self.newSKILL = WORKSKILL(self.selected_skill_platform, self.selected_skill_app, self.selected_skill_app_link, self.selected_skill_site, self.selected_skill_site_link, self.selected_skill_action)
        self.skillModel.appendRow(self.newSKILL)

    def removeSkill(self):
        self.skillModel.removeRow(self.selected_skill_item.row())


    def _createSkillDeleteAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Delete")
        return new_action


    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.ContextMenu and source is self.skillListView:
            #print("bot RC menu....")
            self.popMenu = QtWidgets.QMenu(self)
            #self.rcbotCloneAction = self._createBotRCCloneAction()
            self.skillDeleteAction = self._createSkillDeleteAction()

            #self.popMenu.addAction(self.rcbotEditAction)
            #self.popMenu.addAction(self.rcbotCloneAction)
            #self.popMenu.addSeparator()
            self.popMenu.addAction(self.skillDeleteAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_skill_row = source.indexAt(event.pos()).row()
                self.selected_skill_item = self.skillModel.item(self.selected_skill_row)
                if selected_act == self.skillDeleteAction:
                    self.removeSkill()
            return True

            ##print(event.)

        # else:
        #     print("unknwn.... RC menu....", source, " EVENT: ", event)
        return super().eventFilter(source, event)


    def updateSelectedSkill(self, row):
        self.selected_skill_row = row
        self.selected_skill_item = self.skillModel.item(self.selected_skill_row)
        platform, app, applink, site, sitelink, action = self.selected_skill_item.getData()

        self.skill_platform_sel.setCurrentText(platform)

        if self.skill_app_sel.findText(app) < 0:
            print("set custom app")
            self.skill_app_sel.setCurrentText("Custom")
            self.skillCustomAppNameEdit.setText(app)
            self.skillCustomAppLinkEdit.setText(applink)
        else:
            print("set menu app")
            self.skill_app_sel.setCurrentText(app)
            self.skillCustomActionEdit.setText("")

        if self.skill_site_sel.findText(site) < 0:
            self.skill_site_sel.setCurrentText("Custom")
            self.skillCustomSiteNameEdit.setText(site)
            self.skillCustomSiteLinkEdit.setText(sitelink)
        else:
            self.skill_site_sel.setCurrentText(site)
            self.skillCustomActionEdit.setText("")


        if self.skill_action_sel.findText(action) < 0:
            self.skill_action_sel.setCurrentText("Custom")
            self.skillCustomActionEdit.setText(action)
        else:
            self.skill_action_sel.setCurrentText(action)
            self.skillCustomActionEdit.setText("")

    def genNewTicket(self):
        # get a new ticket using parent's DB connection.
        print("new ticket number is: ")