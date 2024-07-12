import json

from PySide6.QtCore import QEvent, QStringListModel, Qt
from PySide6.QtGui import QStandardItemModel, QColor, QPalette, QIcon, QAction, QStandardItem, QScreen
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QTabWidget, QVBoxLayout, QLineEdit, \
    QCompleter, QComboBox, QScrollArea, QHBoxLayout, QRadioButton, QFileDialog, QButtonGroup, QStyledItemDelegate, \
    QListView, QLabel, QFrame, QMenu
import traceback
import time

from bot.missions import TIME_SLOT_MINS, EBMISSION
from gui.tool.MainGUITool import StaticResource
from utils.logger_helper import logger_helper


class SkillListView(QListView):
    def __init__(self, mission_win):
        super(SkillListView, self).__init__()
        self.selected_row = None
        self.mission_win = mission_win
        self.homepath = mission_win.homepath

    # def mousePressEvent(self, e):
    #     if e.type() == QEvent.MouseButtonPress:
    #         if e.button() == Qt.LeftButton:
    #             self.mission_win.showMsg("row:"+str(self.indexAt(e.pos()).row()))
    #             self.selected_row = self.indexAt(e.pos()).row()
    #             # self.mission_win.updateSelectedSkill(self.selected_row)


class MWORKSKILL(QStandardItem):
    def __init__(self, homepath, platform, app, applink, site, sitelink, action):
        super().__init__()
        self.platform = platform
        self.app = app
        self.applink = applink
        self.site = site
        self.homepath = homepath
        self.sitelink = sitelink
        self.action = action
        self.name = platform + "_" + app + "_" + site + "_" + action

        self.setText(self.name)
        self.icon = QIcon(homepath + '/resource/images/icons/skills-78.png')
        self.setIcon(self.icon)

    def getData(self):
        return self.platform, self.app, self.applink, self.site, self.sitelink, self.action


class CustomDelegate(QStyledItemDelegate):
    def __init__(self, mission_win):
        super(CustomDelegate, self).__init__(mission_win)
        self.mission_win = mission_win

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # Check the item's text for customization
        item_text = index.data(Qt.DisplayRole)
        # if item_text == "5" or item_text == "11":
        if self.mission_win.checkIsMain(item_text):
            option.font.setBold(True)
            option.palette.setColor(QPalette.Text, QColor(0, 0, 255))  # Blue color


class MissionNewWin(QMainWindow):
    def __init__(self, main_win):
        super(MissionNewWin, self).__init__(main_win)
        self.static_resource = StaticResource()
        self.text = QApplication.translate("QMainWindow", "new mission")
        self.main_win = main_win
        self.homepath = main_win.homepath
        self.newMission = EBMISSION(main_win)
        self.owner = None
        self.mode = "new"
        self.selected_skill_row = None
        self.selected_skill_item = None

        self.selected_mission_platform = "Windows"
        self.selected_mission_app = "Chrome"
        self.selected_mission_app_link = ""
        self.selected_mission_site = "Amazon"
        self.selected_mission_site_link = ""
        self.selected_skill_action = "Browse"

        self.mainWidget = QWidget()
        self.tabs = QTabWidget()
        self.pubAttrWidget = QWidget()
        self.prvAttrWidget = QWidget()
        self.actItemsWidget = QWidget()

        self.skillPanel = QFrame()
        self.skillPanelLayout = QVBoxLayout(self)

        self.skillListView = SkillListView(self)
        # self.skillListView.installEventFilter(self)

        self.skillModel = QStandardItemModel(self.skillListView)

        self.skillListView.setModel(self.skillModel)
        self.skillListView.setViewMode(QListView.ListMode)
        self.skillListView.setMovement(QListView.Snap)

        QApplication.translate("QLabel", "Skill Platform:")
        self.skillNameLabel = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Skill Name:</b>"),
                                     alignment=Qt.AlignLeft)
        self.skillNameEdit = QLineEdit("")
        self.skillNameList = QStringListModel()
        self.skillNameCompleter = QCompleter(self.skillNameList, self)
        self.skillNameCompleter.setCaseSensitivity(Qt.CaseInsensitive)
        self.skillNameEdit.setCompleter(self.skillNameCompleter)

        self.missionPlatformLabel = QLabel(
            QApplication.translate("QLabel", "<b style='color:red;'>Mission Platform:</b>"), alignment=Qt.AlignLeft)
        self.mission_platform_sel = QComboBox()
        for p in self.static_resource.PLATFORMS:
            self.mission_platform_sel.addItem(QApplication.translate("QComboBox", p))
        self.mission_platform_sel.currentTextChanged.connect(self.missionPlatformSel_changed)

        self.missionAppLabel = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Mission App:</b>"),
                                      alignment=Qt.AlignLeft)
        self.mission_app_sel = QComboBox()
        for app in self.static_resource.APPS:
            self.mission_app_sel.addItem(QApplication.translate("QComboBox", app))
        self.mission_app_sel.currentTextChanged.connect(self.missionAppSel_changed)

        QApplication.translate("QLabel", "Skill Site:")
        self.missionCustomAppNameLabel = QLabel(QApplication.translate("QLabel", "Custome App:"),
                                                alignment=Qt.AlignLeft)
        self.missionCustomAppNameEdit = QLineEdit("")

        self.missionCustomAppLinkLabel = QLabel(QApplication.translate("QLabel", "Custome App Path:"),
                                                alignment=Qt.AlignLeft)
        self.missionCustomAppLinkEdit = QLineEdit("")
        self.missionCustomAppLinkButton = QPushButton("...")
        self.missionCustomAppLinkButton.clicked.connect(self.chooseAppLinkDir)

        self.missionSiteLabel = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Mission Site:</b>"),
                                       alignment=Qt.AlignLeft)
        self.mission_site_sel = QComboBox()
        for site in self.static_resource.SITES:
            self.mission_site_sel.addItem(QApplication.translate("QComboBox", site))
        self.mission_site_sel.currentTextChanged.connect(self.missionSiteSel_changed)

        self.missionCustomSiteNameLabel = QLabel(QApplication.translate("QLabel", "Custom Site:"),
                                                 alignment=Qt.AlignLeft)
        self.missionCustomSiteNameEdit = QLineEdit("")
        self.missionCustomSiteLinkLabel = QLabel(QApplication.translate("QLabel", "Custom Site Html:"),
                                                 alignment=Qt.AlignLeft)
        self.missionCustomSiteLinkEdit = QLineEdit("")

        self.skillActionLabel = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Skill Action:</b>"),
                                       alignment=Qt.AlignLeft)
        self.skill_action_sel = QComboBox()
        # self.skill_action_sel.setModel(self.main_win.SkillManagerWin.skillModel)
        self.styleDelegate = CustomDelegate(self.main_win)

        self.buildSkillSelList()
        self.skill_action_sel.setItemDelegate(self.styleDelegate)

        self.skill_action_sel.currentTextChanged.connect(self.skillActionSel_changed)

        self.skillCustomActionLabel = QLabel(QApplication.translate("QLabel", "Custom Action:"), alignment=Qt.AlignLeft)
        self.skillCustomActionEdit = QLineEdit("")

        self.skillScrollLabel = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Required Skills:</b>"),
                                       alignment=Qt.AlignLeft)
        self.skillNoteLabel = QLabel(QApplication.translate("QLabel", ""), alignment=Qt.AlignLeft)
        self.skillScroll = QScrollArea()
        self.skillScroll.setWidget(self.skillListView)
        self.skillScrollArea = QWidget()
        self.skillScrollLayout = QVBoxLayout(self)
        self.skillLabelLayout = QHBoxLayout(self)
        self.skillLabelLayout.addWidget(self.skillScrollLabel)
        self.skillLabelLayout.addWidget(self.skillNoteLabel)
        self.skillScrollLayout.addLayout(self.skillLabelLayout)
        self.skillScrollLayout.addWidget(self.skillScroll)
        self.skillScrollArea.setLayout(self.skillScrollLayout)

        self.skillButtonsArea = QWidget()
        self.skillButtonsLayout = QVBoxLayout(self)

        self.skill_add_button = QPushButton(QApplication.translate("QPushButton", "Add Skill"))
        self.skill_add_button.clicked.connect(self.addSkill)

        self.skill_remove_button = QPushButton(QApplication.translate("QPushButton", "Remove Skill"))
        self.skill_remove_button.clicked.connect(self.removeSkill)

        self.skillButtonsLayout.addWidget(self.skill_add_button)
        self.skillButtonsLayout.addWidget(self.skill_remove_button)
        self.skillButtonsArea.setLayout(self.skillButtonsLayout)

        self.skillArea = QWidget()
        self.skillAreaLayout = QHBoxLayout(self)
        self.skillAreaLayout.addWidget(self.skillScrollArea)
        self.skillAreaLayout.addWidget(self.skillButtonsArea)
        self.skillArea.setLayout(self.skillAreaLayout)

        self.save_button = QPushButton(QApplication.translate("QPushButton", "Save"))
        self.cancel_button = QPushButton(QApplication.translate("QPushButton", "Cancel"))

        self.action_confirm_cancel_button = QPushButton(QApplication.translate("QPushButton", "Cancel"))
        self.action_confirm_button = QPushButton(QApplication.translate("QPushButton", "Confirm"))
        self.action_confirm_ok_button = QPushButton(QApplication.translate("QPushButton", "OK"))

        self.layout = QVBoxLayout(self)
        self.bLayout = QHBoxLayout(self)
        self.bLayout.addWidget(self.cancel_button)
        self.bLayout.addWidget(self.save_button)

        self.pubAttrWidget.layout = QVBoxLayout(self)
        self.prvAttrWidget.layout = QVBoxLayout(self)
        self.actItemsWidget.layout = QVBoxLayout(self)

        self.ticket_label = QLabel(QApplication.translate("QLabel", "Ticket Number:"), alignment=Qt.AlignLeft)
        self.ticket_edit = QLineEdit()
        self.ticket_edit.setReadOnly(True)

        self.mid_label = QLabel(QApplication.translate("QLabel", "Mission ID:"), alignment=Qt.AlignLeft)
        self.mid_edit = QLineEdit()
        self.mid_edit.setReadOnly(True)

        self.mission_type_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Mission Type:</b>"),
                                         alignment=Qt.AlignLeft)
        self.buy_rb = QRadioButton(QApplication.translate("QPushButton", "Buy Side"))
        self.buy_rb.toggled.connect(self.buy_rb_checked_state_changed)

        self.sell_rb = QRadioButton(QApplication.translate("QPushButton", "Sell Side"))
        self.sell_rb.toggled.connect(self.sell_rb_checked_state_changed)
        self.op_rb = QRadioButton(QApplication.translate("QPushButton", "Operation Side"))
        self.op_rb.toggled.connect(self.op_rb_checked_state_changed)

        self.mission_auto_assign_label = QLabel(QApplication.translate("QLabel", "Assignment Type:"),
                                                alignment=Qt.AlignLeft)
        self.manual_rb = QRadioButton(QApplication.translate("QPushButton", "Manual Assign(Bot and Schedule)"))
        self.auto_rb = QRadioButton(QApplication.translate("QPushButton", "Auto Assign(Bot and Schedule)"))

        self.bid_label = QLabel(QApplication.translate("QLabel", "Assigned Bot ID:"), alignment=Qt.AlignLeft)
        self.bid_edit = QLineEdit()
        self.ert_label = QLabel(QApplication.translate("QLabel", "Estimated Duration Time(Sec):"),
                                alignment=Qt.AlignLeft)
        self.ert_edit = QLineEdit()
        self.est_label = QLabel(QApplication.translate("QLabel", "Estimated Start Time(hh:mm:ss):"),
                                alignment=Qt.AlignLeft)
        self.est_edit = QLineEdit()

        self.buy_mission_type_label = QLabel(
            QApplication.translate("QLabel", "<b style='color:red;'>Buy Mission Type:</b>"), alignment=Qt.AlignLeft)
        self.buy_mission_type_sel = QComboBox()
        self.buy_sub_mission_type_label = QLabel(QApplication.translate("QLabel", "Buy Sub-Mission Type:"),
                                                 alignment=Qt.AlignLeft)
        self.buy_sub_mission_type_sel = QComboBox()

        for bt in self.static_resource.BUY_TYPES:
            self.buy_mission_type_sel.addItem(QApplication.translate("QComboBox", bt))

        for bt in self.static_resource.SUB_BUY_TYPES:
            self.buy_sub_mission_type_sel.addItem(QApplication.translate("QComboBox", bt))

        self.sell_mission_type_label = QLabel(
            QApplication.translate("QLabel", "<b style='color:red;'>Sell Mission Type:</b>"), alignment=Qt.AlignLeft)
        self.sell_mission_type_sel = QComboBox()
        self.sell_sub_mission_type_label = QLabel(QApplication.translate("QLabel", "Sell Sub Mission Type:"),
                                                  alignment=Qt.AlignLeft)
        self.sell_sub_mission_type_sel = QComboBox()

        for st in self.static_resource.SELL_TYPES:
            self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", st))
        for st in self.static_resource.SUB_SELL_TYPES:
            self.sell_sub_mission_type_sel.addItem(QApplication.translate("QComboBox", st))

        self.op_mission_type_label = QLabel(
            QApplication.translate("QLabel", "<b style='color:red;'>Operation Mission Type:</b>"),
            alignment=Qt.AlignLeft)
        self.op_mission_type_sel = QComboBox()
        self.op_mission_type_custome_label = QLabel(QApplication.translate("QLabel", "Custom Operation Mission Type:"),
                                                    alignment=Qt.AlignLeft)
        self.op_mission_type_custome_edit = QLineEdit()

        for st in self.static_resource.OP_TYPES:
            self.op_mission_type_sel.addItem(QApplication.translate("QComboBox", st))

        self.repeat_label = QLabel(QApplication.translate("QLabel", "Repeat every:"), alignment=Qt.AlignLeft)
        self.repeat_edit = QLineEdit()
        self.repeat_edit.setPlaceholderText("1")

        # self.repeat_interval_label = QLabel(QApplication.translate("QLabel", " "), alignment=Qt.AlignLeft)
        # self.repeat_interval_sel = QComboBox()
        #
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Day(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Week(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Month(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Year(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Hour(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Minute(s)"))

        self.search_kw_label = QLabel(QApplication.translate("QLabel", "Search Phrase:"), alignment=Qt.AlignLeft)
        self.search_kw_edit = QLineEdit()

        self.search_kw_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Example: jump rope"))

        self.search_cat_label = QLabel(QApplication.translate("QLabel", "Search Category:"), alignment=Qt.AlignLeft)
        self.search_cat_edit = QLineEdit()

        self.search_cat_edit.setPlaceholderText(
            QApplication.translate("QLineEdit", "Example: Home&Garden->Garden Tools"))

        self.pseudo_store_label = QLabel(QApplication.translate("QLabel", "Pseudo Store:"), alignment=Qt.AlignLeft)
        self.pseudo_store_edit = QLineEdit()
        self.pseudo_store_edit.setPlaceholderText(
            QApplication.translate("QLineEdit", "Example: Jacks Shop, must be differrent from the actual store name."))

        self.pseudo_brand_label = QLabel(QApplication.translate("QLabel", "Pseudo Brand:"), alignment=Qt.AlignLeft)
        self.pseudo_brand_edit = QLineEdit()
        self.pseudo_brand_edit.setPlaceholderText(
            QApplication.translate("QLineEdit", "Example: abc, must be differrent from the actual brand name."))

        self.pseudo_asin_label = QLabel(QApplication.translate("QLabel", "Pseudo ASIN code:"), alignment=Qt.AlignLeft)
        self.pseudo_asin_edit = QLineEdit()
        self.pseudo_asin_edit.setPlaceholderText(QApplication.translate("QLineEdit",
                                                                        "Example: 123, must be differrent from the actual ASIN code/Serial code."))

        self.pubAttrLine1Layout = QHBoxLayout(self)
        self.pubAttrLine1Layout.addWidget(self.ticket_label)
        self.pubAttrLine1Layout.addWidget(self.ticket_edit)
        self.pubAttrLine1Layout.addWidget(self.mid_label)
        self.pubAttrLine1Layout.addWidget(self.mid_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine1Layout)

        self.buy_sell_button_group = QButtonGroup()
        self.buy_sell_button_group.addButton(self.buy_rb)
        self.buy_sell_button_group.addButton(self.sell_rb)
        self.buy_sell_button_group.addButton(self.op_rb)
        # self.buy_sell_button_group.setExclusive(False)

        self.pubAttrLine2Layout = QHBoxLayout(self)
        self.pubAttrLine2Layout.addWidget(self.mission_type_label)
        self.pubAttrLine2Layout.addWidget(self.buy_rb)
        self.pubAttrLine2Layout.addWidget(self.sell_rb)
        self.pubAttrLine2Layout.addWidget(self.op_rb)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine2Layout)

        self.auto_manual_button_group = QButtonGroup()
        self.auto_manual_button_group.addButton(self.manual_rb)
        self.auto_manual_button_group.addButton(self.auto_rb)

        self.pubAttrLine2ALayout = QHBoxLayout(self)
        self.pubAttrLine2ALayout.addWidget(self.mission_auto_assign_label)
        self.pubAttrLine2ALayout.addWidget(self.manual_rb)
        self.pubAttrLine2ALayout.addWidget(self.auto_rb)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine2ALayout)

        self.pubAttrLine2BLayout = QHBoxLayout(self)
        self.pubAttrLine2BLayout.addWidget(self.bid_label)
        self.pubAttrLine2BLayout.addWidget(self.bid_edit)
        self.pubAttrLine2BLayout.addWidget(self.ert_label)
        self.pubAttrLine2BLayout.addWidget(self.ert_edit)
        self.pubAttrLine2BLayout.addWidget(self.est_label)
        self.pubAttrLine2BLayout.addWidget(self.est_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine2BLayout)

        self.pubAttrLine3Layout = QHBoxLayout(self)
        self.pubAttrLine3Layout.addWidget(self.repeat_label)
        self.pubAttrLine3Layout.addWidget(self.repeat_edit)
        # self.pubAttrLine3Layout.addWidget(self.repeat_interval_label)
        # self.pubAttrLine3Layout.addWidget(self.repeat_interval_sel)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine3Layout)

        self.pubAttrLine4Layout = QHBoxLayout(self)
        self.pubAttrLine4Layout.addWidget(self.search_kw_label)
        self.pubAttrLine4Layout.addWidget(self.search_kw_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine4Layout)

        self.pubAttrLine5Layout = QHBoxLayout(self)
        self.pubAttrLine5Layout.addWidget(self.search_cat_label)
        self.pubAttrLine5Layout.addWidget(self.search_cat_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine5Layout)

        self.pubAttrLine6Layout = QHBoxLayout(self)
        self.pubAttrLine6Layout.addWidget(self.pseudo_store_label)
        self.pubAttrLine6Layout.addWidget(self.pseudo_store_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine6Layout)

        self.pubAttrLine7Layout = QHBoxLayout(self)
        self.pubAttrLine7Layout.addWidget(self.pseudo_brand_label)
        self.pubAttrLine7Layout.addWidget(self.pseudo_brand_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine7Layout)

        self.pubAttrLine8Layout = QHBoxLayout(self)
        self.pubAttrLine8Layout.addWidget(self.pseudo_asin_label)
        self.pubAttrLine8Layout.addWidget(self.pseudo_asin_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine8Layout)

        self.pubpflLine9Layout = QHBoxLayout(self)
        self.pubpflLine9Layout.addWidget(self.missionPlatformLabel)
        self.pubpflLine9Layout.addWidget(self.mission_platform_sel)
        self.pubpflLine9Layout.addWidget(self.missionAppLabel)
        self.pubpflLine9Layout.addWidget(self.mission_app_sel)
        self.pubpflLine9Layout.addWidget(self.missionSiteLabel)
        self.pubpflLine9Layout.addWidget(self.mission_site_sel)
        self.pubpflLine9Layout.addWidget(self.skillActionLabel)
        self.pubpflLine9Layout.addWidget(self.skill_action_sel)
        self.skillPanelLayout.addLayout(self.pubpflLine9Layout)

        self.pubpflLine11Layout = QHBoxLayout(self)
        self.pubpflLine11Layout.addWidget(self.missionCustomAppNameLabel)
        self.pubpflLine11Layout.addWidget(self.missionCustomAppNameEdit)
        self.pubpflLine11Layout.addWidget(self.missionCustomAppLinkLabel)
        self.pubpflLine11Layout.addWidget(self.missionCustomAppLinkEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine11Layout)

        self.pubpflLine12Layout = QHBoxLayout(self)
        self.pubpflLine12Layout.addWidget(self.missionCustomSiteNameLabel)
        self.pubpflLine12Layout.addWidget(self.missionCustomSiteNameEdit)
        self.pubpflLine12Layout.addWidget(self.missionCustomSiteLinkLabel)
        self.pubpflLine12Layout.addWidget(self.missionCustomSiteLinkEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine12Layout)

        self.pubpflLine13Layout = QHBoxLayout(self)
        self.pubpflLine13Layout.addWidget(self.skillCustomActionLabel)
        self.pubpflLine13Layout.addWidget(self.skillCustomActionEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine13Layout)

        self.hide_mission_custom_app()
        self.hide_mission_custom_site()
        self.hide_skill_custom_action()

        self.skillPanelLayout.addWidget(self.skillArea)
        self.skillPanel.setLayout(self.skillPanelLayout)

        self.skillPanel.setFrameStyle(QFrame.Panel | QFrame.Raised)

        self.pubAttrWidget.layout.addWidget(self.skillPanel)

        self.skillPanel = QFrame()
        self.skillPanelLayout = QVBoxLayout(self)

        self.pubAttrWidget.setLayout(self.pubAttrWidget.layout)

        self.cus_fn_label = QLabel(QApplication.translate("QLabel", "Customer First Name:"), alignment=Qt.AlignLeft)
        self.cus_fn_edit = QLineEdit()
        self.cus_fn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer First Name here"))

        self.cus_ln_label = QLabel(QApplication.translate("QLabel", "Customer Last Name:"), alignment=Qt.AlignLeft)
        self.cus_ln_edit = QLineEdit()
        self.cus_ln_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer Last Name here"))

        self.cus_nn_label = QLabel(QApplication.translate("QLabel", "Customer Nick Name:"), alignment=Qt.AlignLeft)
        self.cus_nn_edit = QLineEdit()
        self.cus_nn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer Nick Name here"))

        self.cus_id_label = QLabel(QApplication.translate("QLabel", "Customer ID:"), alignment=Qt.AlignLeft)
        self.cus_id_edit = QLineEdit()
        self.cus_id_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer ID here"))

        self.veriations_label = QLabel(QApplication.translate("QLabel", "Veriations:"), alignment=Qt.AlignLeft)
        self.veriations_edit = QLineEdit()
        self.veriations_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Veriations here"))

        self.follow_price_label = QLabel(QApplication.translate("QLabel", "Follow Price:"), alignment=Qt.AlignLeft)
        self.follow_price_edit = QLineEdit()
        self.follow_price_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Follow Price here"))

        self.follow_seller_label = QLabel(QApplication.translate("QLabel", "Follow Seller:"), alignment=Qt.AlignLeft)
        self.follow_seller_edit = QLineEdit()
        self.follow_seller_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Follow Seller here"))

        self.fingerprint_profile_label = QLabel(QApplication.translate("QLabel", "Fingerprint Profile:"), alignment=Qt.AlignLeft)
        self.fingerprint_profile_edit = QLineEdit()
        self.fingerprint_profile_edit.setReadOnly(True)
        self.fingerprint_profile_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Please select files of type Text, xls, xlsx or csv."))
        self.fingerprint_profile_button = QPushButton("...")
        self.fingerprint_profile_button.clicked.connect(self.fingerprint_profile_file)
        self.cus_sm_type_label = QLabel(QApplication.translate("QLabel", "Customer Messenging Type:"),
                                        alignment=Qt.AlignLeft)
        self.cus_sm_type_sel = QComboBox()

        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "QQ"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "WeChat"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "Telegram"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "WhatsApp"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "Messenger"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "Other"))

        self.cus_sm_id_label = QLabel(QApplication.translate("QLabel", "Customer Messenger ID:"),
                                      alignment=Qt.AlignLeft)
        self.cus_sm_id_edit = QLineEdit()
        self.cus_sm_id_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Customer Messenger ID here"))

        self.cus_alt_sm_type_label = QLabel(QApplication.translate("QLabel", "Customer Messenging Type:"),
                                            alignment=Qt.AlignLeft)
        self.cus_alt_sm_type_sel = QComboBox()
        for sm in self.static_resource.SM_PLATFORMS:
            self.cus_alt_sm_type_sel.addItem(QApplication.translate("QComboBox", sm))

        self.cus_alt_sm_id_label = QLabel(QApplication.translate("QLabel", "Customer Messenger ID:"),
                                          alignment=Qt.AlignLeft)
        self.cus_alt_sm_id_edit = QLineEdit()

        self.cus_alt_sm_id_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Customer Messenger ID here"))
        self.cus_email_label = QLabel(QApplication.translate("QLabel", "Customer Email:"), alignment=Qt.AlignLeft)
        self.cus_email_edit = QLineEdit()
        self.cus_email_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer Email"))
        self.cus_phone_label = QLabel(QApplication.translate("QLabel", "Customer Contact Phone:"),
                                      alignment=Qt.AlignLeft)
        self.cus_phone_edit = QLineEdit()
        self.cus_phone_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer Contact Phone here"))
        self.asin_label = QLabel(QApplication.translate("QLabel", "Product ASIN/ID:"), alignment=Qt.AlignLeft)
        self.asin_edit = QLineEdit()
        self.asin_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input product ASIN/ID here"))
        self.title_label = QLabel(QApplication.translate("QLabel", "Product Title:"), alignment=Qt.AlignLeft)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input product title here"))
        self.seller_label = QLabel(QApplication.translate("QLabel", "Product Seller:"), alignment=Qt.AlignLeft)
        self.seller_edit = QLineEdit()
        self.seller_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input seller here"))
        self.rating_label = QLabel(QApplication.translate("QLabel", "Rating:"), alignment=Qt.AlignLeft)
        self.rating_edit = QLineEdit()
        self.rating_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input rating here"))

        self.feedbacks_label = QLabel(QApplication.translate("QLabel", "# of feedbacks:"), alignment=Qt.AlignLeft)
        self.feedbacks_edit = QLineEdit()
        self.feedbacks_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input # feedbacks here"))

        self.price_label = QLabel(QApplication.translate("QLabel", "Selling Price:"), alignment=Qt.AlignLeft)
        self.price_edit = QLineEdit()
        self.price_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input selling price here, ex. 12.99"))

        self.product_image_label = QLabel(QApplication.translate("QLabel", "Top Image:"), alignment=Qt.AlignLeft)
        self.product_image_edit = QLineEdit()
        self.product_image_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input image path here"))

        self.prvAttrLine1Layout = QHBoxLayout(self)
        self.prvAttrLine1Layout.addWidget(self.cus_id_label)
        self.prvAttrLine1Layout.addWidget(self.cus_id_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine1Layout)

        self.prvAttrLine2Layout = QHBoxLayout(self)
        self.prvAttrLine2Layout.addWidget(self.cus_sm_id_label)
        self.prvAttrLine2Layout.addWidget(self.cus_sm_id_edit)
        self.prvAttrLine2Layout.addWidget(self.cus_alt_sm_type_label)
        self.prvAttrLine2Layout.addWidget(self.cus_alt_sm_type_sel)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine2Layout)

        self.prvAttrLine3Layout = QHBoxLayout(self)
        self.prvAttrLine3Layout.addWidget(self.asin_label)
        self.prvAttrLine3Layout.addWidget(self.asin_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine3Layout)

        self.prvAttrLine4Layout = QHBoxLayout(self)
        self.prvAttrLine4Layout.addWidget(self.title_label)
        self.prvAttrLine4Layout.addWidget(self.title_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine4Layout)

        self.prvAttrLine5Layout = QHBoxLayout(self)
        self.prvAttrLine5Layout.addWidget(self.seller_label)
        self.prvAttrLine5Layout.addWidget(self.seller_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine5Layout)

        self.prvAttrLine6Layout = QHBoxLayout(self)
        self.prvAttrLine6Layout.addWidget(self.rating_label)
        self.prvAttrLine6Layout.addWidget(self.rating_edit)
        self.prvAttrLine6Layout.addWidget(self.feedbacks_label)
        self.prvAttrLine6Layout.addWidget(self.feedbacks_edit)
        self.prvAttrLine6Layout.addWidget(self.price_label)
        self.prvAttrLine6Layout.addWidget(self.price_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine6Layout)

        self.prvAttrLine7Layout = QHBoxLayout(self)
        self.prvAttrLine7Layout.addWidget(self.product_image_label)
        self.prvAttrLine7Layout.addWidget(self.product_image_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine7Layout)

        self.prvAttrLine8Layout = QHBoxLayout(self)
        self.prvAttrLine8Layout.addWidget(self.buy_mission_type_label)
        self.prvAttrLine8Layout.addWidget(self.buy_mission_type_sel)
        self.prvAttrLine8Layout.addWidget(self.buy_sub_mission_type_label)
        self.prvAttrLine8Layout.addWidget(self.buy_sub_mission_type_sel)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine8Layout)

        self.prvAttrLine9Layout = QHBoxLayout(self)
        self.prvAttrLine9Layout.addWidget(self.sell_mission_type_label)
        self.prvAttrLine9Layout.addWidget(self.sell_mission_type_sel)
        self.prvAttrLine9Layout.addWidget(self.sell_sub_mission_type_label)
        self.prvAttrLine9Layout.addWidget(self.sell_sub_mission_type_sel)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine9Layout)

        self.prvAttrLine10Layout = QHBoxLayout(self)
        self.prvAttrLine10Layout.addWidget(self.op_mission_type_label)
        self.prvAttrLine10Layout.addWidget(self.op_mission_type_sel)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine10Layout)

        self.prvAttrLine11Layout = QHBoxLayout(self)
        self.prvAttrLine10Layout.addWidget(self.op_mission_type_custome_label)
        self.prvAttrLine10Layout.addWidget(self.op_mission_type_custome_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine11Layout)

        self.prvAttrLine12Layout = QHBoxLayout(self)
        self.prvAttrLine12Layout.addWidget(self.veriations_label)
        self.prvAttrLine12Layout.addWidget(self.veriations_edit)
        self.prvAttrLine12Layout.addWidget(self.follow_seller_label)
        self.prvAttrLine12Layout.addWidget(self.follow_seller_edit)
        self.prvAttrLine12Layout.addWidget(self.follow_price_label)
        self.prvAttrLine12Layout.addWidget(self.follow_price_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine12Layout)

        self.prvAttrLine13Layout = QHBoxLayout(self)
        self.prvAttrLine13Layout.addWidget(self.fingerprint_profile_label)
        self.prvAttrLine13Layout.addWidget(self.fingerprint_profile_edit)
        self.prvAttrLine13Layout.addWidget(self.fingerprint_profile_button)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine13Layout)

        self.prvAttrWidget.setLayout(self.prvAttrWidget.layout)

        self.mission_status_label = QLabel(QApplication.translate("QLabel", "Mission Status:"), alignment=Qt.AlignLeft)
        self.mission_status_sel = QComboBox()
        self.mission_error_label = QLabel(QApplication.translate("QLabel", "Mission Error Reason:"),
                                          alignment=Qt.AlignLeft)
        self.mission_error_edit = QLineEdit()
        self.mission_status_sel.currentTextChanged.connect(self.missionStatusSel_changed)

        for st in self.static_resource.STATUS_TYPES:
            self.mission_status_sel.addItem(QApplication.translate("QComboBox", st))

        self.actItemsLine1Layout = QHBoxLayout(self)
        self.actItemsLine1Layout.addWidget(self.mission_status_label)
        self.actItemsLine1Layout.addWidget(self.mission_status_sel)
        self.actItemsWidget.layout.addLayout(self.actItemsLine1Layout)

        self.actItemsLine2Layout = QHBoxLayout(self)
        self.actItemsLine2Layout.addWidget(self.mission_error_label)
        self.actItemsLine2Layout.addWidget(self.mission_error_edit)
        self.actItemsWidget.layout.addLayout(self.actItemsLine2Layout)

        self.actItemsWidget.setLayout(self.actItemsWidget.layout)

        self.tabs.addTab(self.pubAttrWidget, QApplication.translate("QTabWidget", "Pub Attributes"))
        self.tabs.addTab(self.prvAttrWidget, QApplication.translate("QTabWidget", "Private Attributes"))
        self.tabs.addTab(self.actItemsWidget, QApplication.translate("QTabWidget", "Status"))

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
        self.setWindowTitle("Mission Editor")

        self.buy_rb.setChecked(False)
        self.buy_rb.setChecked(True)

    def setMode(self, mode):
        self.mode = mode
        if self.mode == "new":
            self.setWindowTitle('Adding a new mission')
            current_time_nanoseconds = time.time_ns()
            # Convert to milliseconds
            current_time_milliseconds = current_time_nanoseconds // 1_000_000
            self.newMission.setTicket(current_time_milliseconds)
            self.ticket_edit.setText(str(self.newMission.getTicket()))
        elif self.mode == "update":
            self.setWindowTitle('Updating a mission')

    def fingerprint_profile_file(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            'Select File',
            '',
            '*.txt *.xls *.xlsx',
            options=options
        )
        if file_name:
            self.fingerprint_profile_edit.setText(file_name)

    def saveMission(self):
        self.main_win.showMsg("saving bot....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.

        if self.manual_rb.isChecked():
            if int(self.bid_edit.text()) != self.newMission.getBid():
                self.newMission.setBid(int(self.bid_edit.text()))
                est_edit_text = self.est_edit.text()
                if est_edit_text is not None:
                    hours, minutes, seconds = map(int, self.est_edit.text().split(':'))
                    # Calculate total minutes
                    total_minutes = hours * 60 + minutes
                    slots = int(total_minutes / TIME_SLOT_MINS) + 1

                    runtime = int(int(self.ert_edit.text()) / (60 * TIME_SLOT_MINS)) + 1

                    self.newMission.setEstimatedStartTime(slots)
                    self.newMission.setEstimatedRunTime(runtime)

            self.newMission.setConfig(
                json.dumps({"bid": int(self.bid_edit.text()), "start_time": slots, "estRunTime": runtime}))
            self.newMission.setAssignmentType("manual")
        else:
            self.newMission.setAssignmentType("auto")
            self.newMission.setConfig("{}")

        if self.repeat_edit.text().isnumeric():
            self.newMission.setRetry(int(self.repeat_edit.text()))

        if self.buy_rb.isChecked():
            if self.buy_mission_type_sel.currentText() == "browse":
                self.newMission.setMtype(self.buy_mission_type_sel.currentText())
            else:
                self.newMission.setMtype(
                    self.buy_mission_type_sel.currentText() + "_" + self.buy_sub_mission_type_sel.currentText())
        elif self.sell_rb.isChecked():
            self.newMission.setMtype(self.sell_mission_type_sel.currentText())
        elif self.op_rb.isChecked():
            if self.op_mission_type_sel.currentText() == "opCustom":
                self.newMission.setMtype("opCustom_" + self.op_mission_type_custome_edit.text())
            else:
                self.newMission.setMtype(self.op_mission_type_sel.currentText())

        self.newMission.setBuyType(self.buy_mission_type_sel.currentText())
        self.newMission.setSellType(self.sell_mission_type_sel.currentText())

        self.newMission.privateAttributes.setItem(self.asin_edit.text(), self.seller_edit.text(),
                                                  self.title_edit.text(), self.product_image_edit.text(),
                                                  self.rating_edit.text(), self.feedbacks_edit.text(),
                                                  self.price_edit.text())

        self.newMission.setCustomerID(self.cus_email_edit.text())
        self.newMission.setFollowPrice(self.follow_price_edit.text())
        self.newMission.setFollowSeller(self.follow_seller_edit.text())
        self.newMission.setVariations(self.veriations_edit.text())
        self.newMission.setFingerPrintProfile(self.fingerprint_profile_edit.text())
        self.newMission.setCustomerSMID(self.cus_sm_id_edit.text())
        self.newMission.setCustomerSMPlatform(self.cus_alt_sm_type_sel.currentText())

        self.newMission.pubAttributes.setSearch(self.search_kw_edit.text(), self.search_cat_edit.text())

        self.newMission.setPseudoStore(self.pseudo_store_edit.text())
        self.newMission.setPseudoBrand(self.pseudo_brand_edit.text())
        self.newMission.setPseudoASIN(self.pseudo_asin_edit.text())

        self.missionStatusSel_changed()

        platform_text = self.mission_platform_sel.currentText()
        platform_sh = self.main_win.translatePlatform(platform_text)
        self.newMission.setPlatform(platform_text)

        if self.mission_app_sel.currentText() == 'Custom':
            app_text = self.missionCustomAppNameEdit.text()
        else:
            app_text = self.mission_app_sel.currentText()

        app_sh = app_text
        self.newMission.setApp(app_text)

        if self.mission_site_sel.currentText() == 'Custom':
            site_text = self.missionCustomSiteNameEdit.text()
        else:
            site_text = self.mission_site_sel.currentText()

        site_sh = self.main_win.translateSiteName(site_text)
        self.newMission.setSite(site_text)

        self.main_win.showMsg("Setting CusPAS:" + platform_sh + "," + app_sh + "," + site_sh)
        self.newMission.setCusPAS(platform_sh + "," + app_sh + "," + site_sh)
        self.fillSkills()

        self.newMission.updateDisplay()
        # public: type,

        if self.mode == "new":
            self.main_win.showMsg("adding new mission....")
            self.main_win.addNewMissions([self.newMission])
        elif self.mode == "update":
            self.main_win.showMsg("update a mission....")
            self.main_win.updateMissions([self.newMission])

        self.close()

    def loadSkills(self, mission):
        skp_options = ['win', 'mac', 'linux']
        skapp_options = ['chrome', 'edge', 'firefox', 'safari', 'ads', 'multilogin']
        sksite_options = ['amz', 'etsy', 'ebay']
        all_skids = mission.getSkills().split(",")

        for skidw in all_skids:
            skid = skidw.strip()
            this_skill = next((x for x in self.main_win.skills if x.getSkid() == skid), None)

            if this_skill:
                self.skillModel.appendRow(this_skill)

        self.selected_skill_row = 0
        self.selected_skill_item = self.skillModel.item(self.selected_skill_row)

    def fillSkills(self):
        sk_word = ""
        for i in range(self.skillModel.rowCount()):
            self.selected_skill_item = self.skillModel.item(i)
            skid = self.selected_skill_item.getSkid()
            sk_word = sk_word + "," + str(skid)

        self.main_win.showMsg("skills>>>>>" + sk_word)

        self.newMission.setSkills(sk_word)

    def selFile(self):
        # File actions
        fdir = self.fsel.getExistingDirectory()
        self.main_win.showMsg(fdir)
        return fdir

    def setOwner(self, owner):
        self.owner = owner
        self.newMission.setOwner(owner)

    def setMission(self, mission):

        try:
            self.newMission = mission
            self.mid_edit.setText(str(self.newMission.getMid()))
            self.ticket_edit.setText(str(self.newMission.getTicket()))
            self.bid_edit.setText(str(self.newMission.getBid()))
            self.est_edit.setText(str(self.newMission.getEstimatedStartTime()))
            self.ert_edit.setText(str(self.newMission.getEstimatedRunTime()))

            self.repeat_edit.setText(str(self.newMission.getRetry()))
            if "browse" in self.newMission.getMtype() or "buy" in self.newMission.getMtype() or "Rating" in self.newMission.getMtype() or "FB" in self.newMission.getMtype():
                self.buy_rb.setChecked(True)
                self.buy_mission_type_sel.setCurrentText(self.newMission.getMtype().split("_")[0])
                if "buy" in self.newMission.getMtype() or "Rating" in self.newMission.getMtype() or "FB" in self.newMission.getMtype():
                    if "_" in self.newMission.getMtype():
                        self.buy_sub_mission_type_sel.setCurrentText(self.newMission.getMtype().split("_")[1])
            elif "sell" in self.newMission.getMtype():
                self.sell_rb.setChecked(True)
                self.sell_mission_type_sel.setCurrentText(self.newMission.getMtype().split("_")[0])
            elif "op" in self.newMission.getMtype():
                self.op_rb.setChecked(True)
                self.op_mission_type_sel.setCurrentText(self.newMission.getMtype().split("_")[0])
                if self.newMission.getMtype().split("_")[0] == "opCustom":
                    if "_" in self.newMission.getMtype():
                        self.op_mission_type_custome_edit.setText("_".join(self.newMission.getMtype().split("_")[1:]))
            self.mission_status_sel.setCurrentText(self.newMission.getStatus().split(":")[0])

            if self.newMission.getAssignmentType() == "auto":
                self.auto_rb.setChecked(True)
            else:
                self.manual_rb.setChecked(True)
                cfg = json.loads(self.newMission.getConfig())
                if "start_time" in cfg:
                    hr = int((cfg["start_time"] - 1) * TIME_SLOT_MINS / 60)
                    min = (cfg["start_time"] - 1) * TIME_SLOT_MINS - hr * 60
                    self.est_edit.setText("{:02d}".format(hr) + ":" + "{:02d}".format(min) + ":00")

                if "estRunTime" in cfg:
                    self.ert_edit.setText(str((cfg["estRunTime"]) * 60 * TIME_SLOT_MINS))

                if "bid" in cfg:
                    self.bid_edit.setText(cfg["bid"])

            if self.newMission.getBuyType() in self.static_resource.BUY_TYPES:
                self.buy_mission_type_sel.setCurrentText(self.newMission.getBuyType())
            else:
                self.buy_mission_type_sel.setCurrentText("goodFB")

            if self.newMission.getSellType() in self.static_resource.SELL_TYPES:
                self.sell_mission_type_sel.setCurrentText(self.newMission.getSellType())
            else:
                self.sell_mission_type_sel.setCurrentText("sellFullfill")

            self.asin_edit.setText(self.newMission.getASIN())
            self.seller_edit.setText(self.newMission.getStore())
            self.title_edit.setText(self.newMission.getTitle())
            self.product_image_edit.setText(self.newMission.getImagePath())
            self.rating_edit.setText(str(self.newMission.getRating()))
            self.feedbacks_edit.setText(str(self.newMission.getFeedbacks()))
            self.price_edit.setText(str(self.newMission.getPrice()))
            self.cus_email_edit.setText(self.newMission.getCustomerID())
            self.cus_sm_id_edit.setText(self.newMission.getCustomerSMID())

            if self.newMission.getCustomerSMPlatform() in self.static_resource.SM_PLATFORMS:
                self.cus_alt_sm_type_sel.setCurrentText(self.newMission.getCustomerSMPlatform())
            else:
                self.cus_alt_sm_type_sel.setCurrentText("Custom")

            self.search_kw_edit.setText(self.newMission.getSearchKW())
            self.search_cat_edit.setText(self.newMission.getSearchCat())
            self.pseudo_store_edit.setText(self.newMission.getPseudoStore())
            self.pseudo_brand_edit.setText(self.newMission.getPseudoBrand())
            self.pseudo_asin_edit.setText(self.newMission.getPseudoASIN())

            self.mission_platform_sel.setCurrentText(self.newMission.getPlatform())
            if self.newMission.getApp() in self.static_resource.APPS:
                self.mission_app_sel.setCurrentText(self.newMission.getApp())
            else:
                self.mission_app_sel.setCurrentText('Custom')
                self.missionCustomAppNameEdit.setText(self.newMission.getApp())
                self.missionCustomAppLinkEdit.setText(self.newMission.getAppExe())

            if self.newMission.getSite() in self.static_resource.SITES:
                self.mission_site_sel.setCurrentText(self.newMission.getSite())
            else:
                self.mission_site_sel.setCurrentText('Custom')
                self.missionCustomAppNameEdit.setText(self.newMission.getSite())
                self.missionCustomAppLinkEdit.setText(self.newMission.getSiteHTML())

            self.loadSkills(mission)
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSetMission:" + json.dumps(traceback_info, indent=4) + " " + str(e)
            else:
                ex_stat = "ErrorSetMission: traceback information not available:" + str(e)
            logger_helper.debug(ex_stat)

    def missionPlatformSel_changed(self):
        self.missionCustomAppLinkEdit = self.mission_platform_sel.currentText()

    def missionAppSel_changed(self):
        self.main_win.showMsg("app changed....")
        if self.mission_app_sel.currentText() != 'Custom':
            self.hide_mission_custom_app()
            self.selected_mission_app = self.mission_app_sel.currentText()
            self.selected_mission_app_link = ""

        else:
            self.show_mission_custom_app()
            self.selected_mission_app = self.missionCustomAppNameEdit.text()
            self.selected_mission_app_link = self.missionCustomAppLinkEdit.text()

    def missionSiteSel_changed(self):
        if self.mission_site_sel.currentText() != 'Custom':
            self.hide_mission_custom_site()
            self.selected_mission_site = self.mission_site_sel.currentText()
            self.selected_mission_site_link = ""
        else:
            self.show_mission_custom_site()
            self.selected_mission_site = self.missionCustomSiteNameEdit.text()
            self.selected_mission_site_link = self.missionCustomSiteLinkEdit.text()

    def skillActionSel_changed(self):
        if self.skill_action_sel.currentText() != 'Custom':
            self.hide_skill_custom_action()
            self.selected_skill_action = self.skill_action_sel.currentText()
        else:
            self.show_skill_custom_action()
            self.selected_skill_action = self.skillCustomActionEdit.text()

    def missionStatusSel_changed(self):
        self.newMission.setStatus(self.mission_status_sel.currentText())

    def hide_mission_custom_app(self):
        self.missionCustomAppNameLabel.setVisible(False)
        self.missionCustomAppNameEdit.setVisible(False)
        self.missionCustomAppLinkLabel.setVisible(False)
        self.missionCustomAppLinkEdit.setVisible(False)

    def show_mission_custom_app(self):
        self.missionCustomAppNameLabel.setVisible(True)
        self.missionCustomAppNameEdit.setVisible(True)
        self.missionCustomAppLinkLabel.setVisible(True)
        self.missionCustomAppLinkEdit.setVisible(True)

    def hide_mission_custom_site(self):
        self.missionCustomSiteNameLabel.setVisible(False)
        self.missionCustomSiteNameEdit.setVisible(False)
        self.missionCustomSiteLinkLabel.setVisible(False)
        self.missionCustomSiteLinkEdit.setVisible(False)

    def show_mission_custom_site(self):
        self.missionCustomSiteNameLabel.setVisible(True)
        self.missionCustomSiteNameEdit.setVisible(True)
        self.missionCustomSiteLinkLabel.setVisible(True)
        self.missionCustomSiteLinkEdit.setVisible(True)

    def hide_skill_custom_action(self):
        self.skillCustomActionLabel.setVisible(False)
        self.skillCustomActionEdit.setVisible(False)

    def show_skill_custom_action(self):
        self.skillCustomActionLabel.setVisible(True)
        self.skillCustomActionEdit.setVisible(True)

    def chooseAppLinkDir(self):
        self.missionCustomAppLinkEdit.setText(str(QFileDialog.getExistingDirectory(self, "Select Directory")))
        self.selected_skill_app_link = self.missionCustomAppLinkEdit.text()

    def addSkill(self):
        if self.mission_app_sel.currentText() == 'Custom':
            self.selected_skill_app = self.skillCustomAppNameEdit.text()
            self.selected_skill_app_link = self.skillCustomAppLinkEdit.text()

        if self.mission_site_sel.currentText() == 'Custom':
            self.selected_skill_site = self.skillCustomSiteNameEdit.text()
            self.selected_skill_site_link = self.skillCustomSiteLinkEdit.text()

        sk_words = self.skill_action_sel.currentText().split("_")
        sk_platform = sk_words[0]
        sk_app = sk_words[1]
        sk_site = sk_words[2]
        sk_page = sk_words[3]
        sk_name = "_".join(sk_words[4:])

        this_skill = next((x for x in self.main_win.skills if
                           x.getPlatform() == sk_platform and x.getApp() == sk_app and x.getSite() == sk_site and x.getPage() == sk_page and x.getName() == sk_name),
                          None)
        if this_skill:
            self.skillNoteLabel.setText("")
            self.skillModel.appendRow(this_skill)

            # automatically add dependency skills to the list as well
            sk_dep = this_skill.getDependencies()
            if len(sk_dep) > 0:
                for skid in sk_dep:
                    dep_skill = next((x for x in self.main_win.skills if x.getSkid() == skid), None)
                    self.skillModel.appendRow(dep_skill)
        else:
            self.skillNoteLabel.setText("Skill not available to use: " + sk_name)

    def removeSkill(self):
        # a bit complicated here, need to make sure if the skill is a dependent skill, then it's not removable.
        # if it's a main skill, then removing it will remove all of its dependency , and even more tricky is
        # if one of this main skill's dependency is also another main skill's dependency, then this item is also
        # not removable.
        rows_to_be_removed = [self.skillListView.selected_row]
        all_mission_skills = [self.skillModel.item(row) for row in range(self.skillModel.rowCount())]
        other_main_skills = list(
            filter(lambda sk: sk.getIsMain() and sk.getSkid() != self.selected_skill_item.getSkid(),
                   all_mission_skills))

        if self.selected_skill_item is not None and self.selected_skill_item.getIsMain():
            # first go thru its dependencies and check whether a skill is
            deps = self.selected_skill_item.getDependencies()
            for dep in deps:
                dependent_to_others = False
                for other in other_main_skills:
                    if dep in other.getDependencies():
                        dependent_to_others = True
                        break

                if not dependent_to_others:
                    dep_row = next((i for i, item in enumerate(all_mission_skills) if item.getSkid() == dep), -1)
                    rows_to_be_removed.append(dep_row)
                    break

            sorted_rows_to_be_removed = rows_to_be_removed.sort(reverse=True)
            # finally remove items from bottom to top.
            for row in sorted_rows_to_be_removed:
                self.skillModel.removeRow(row)

    def _createSkillDeleteAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Delete"))
        return new_action

    def _createSkillUpdateAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Update"))
        return new_action

    def eventFilter(self, source, event):
        if event.type() == QEvent.ContextMenu and source is self.skillListView:
            # self.main_win.showMsg("bot RC menu....")
            self.popMenu = QMenu(self)
            self.skillUpdateAction = self._createSkillUpdateAction()
            self.skillDeleteAction = self._createSkillDeleteAction()

            self.popMenu.addAction(self.skillUpdateAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.skillDeleteAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_skill_row = source.indexAt(event.pos()).row()
                self.selected_skill_item = self.skillModel.item(self.selected_skill_row)
                if selected_act == self.skillDeleteAction:
                    self.removeSkill()
                elif selected_act == self.skillUpdateAction:
                    self.updateSelectedSkill(self.selected_skill_row)
            return True

            ##self.main_win.showMsg(event.)

        # else:
        #     self.main_win.showMsg("unknwn.... RC menu....", source, " EVENT: ", event)
        return super().eventFilter(source, event)

    def updateSelectedSkill(self, row):
        self.selected_skill_row = row
        self.selected_skill_item = self.skillModel.item(self.selected_skill_row)
        if self.selected_skill_item:
            platform, app, applink, site, sitelink, action = self.selected_skill_item.getData()

            self.mission_platform_sel.setCurrentText(platform)

            if self.mission_app_sel.findText(app) < 0:
                self.main_win.showMsg("set custom app")
                self.mission_app_sel.setCurrentText(QApplication.translate("QComboBox", "Custom"))
                self.skillCustomAppNameEdit.setText(app)
                self.skillCustomAppLinkEdit.setText(applink)
            else:
                self.main_win.showMsg("set menu app")
                self.mission_app_sel.setCurrentText(app)
                self.skillCustomActionEdit.setText("")

            if self.mission_site_sel.findText(site) < 0:
                self.mission_site_sel.setCurrentText(QApplication.translate("QComboBox", "Custom"))
                self.skillCustomSiteNameEdit.setText(site)
                self.skillCustomSiteLinkEdit.setText(sitelink)
            else:
                self.mission_site_sel.setCurrentText(site)
                self.skillCustomActionEdit.setText("")

            if self.skill_action_sel.findText(action) < 0:
                self.skill_action_sel.setCurrentText(QApplication.translate("QComboBox", "Custom"))
                self.skillCustomActionEdit.setText(action)
            else:
                self.skill_action_sel.setCurrentText(action)
                self.skillCustomActionEdit.setText("")

    def genNewTicket(self):
        # get a new ticket using main_win's DB connection.
        self.main_win.showMsg("new ticket number is: ")

    def buildSkillSelList(self):
        for sk in self.main_win.skills:
            self.skill_action_sel.addItem(QApplication.translate("QComboBox",
                                                                 sk.getPlatform() + "_" + sk.getApp() + "_" + sk.getSiteName() + "_" + sk.getPage() + "_" + sk.getName()))

    def buy_rb_checked_state_changed(self):
        if self.buy_rb.isChecked():
            self.main_win.showMsg("buy mission is selected....")
            self.show_buy_attributes()
            self.hide_sell_attributes()
            self.hide_op_attributes()
        else:
            self.hide_buy_attributes()

    def sell_rb_checked_state_changed(self):
        if self.sell_rb.isChecked():
            self.main_win.showMsg("sell mission is selected....")
            self.show_sell_attributes()
            self.hide_buy_attributes()
            self.hide_op_attributes()
        else:
            self.hide_sell_attributes()

    def op_rb_checked_state_changed(self):
        if self.op_rb.isChecked():
            self.main_win.showMsg("sell mission is selected....")
            self.show_op_attributes()
            self.hide_buy_attributes()
            self.hide_sell_attributes()
        else:
            self.hide_op_attributes()

    def show_buy_attributes(self):
        self.pseudo_store_label.setVisible(True)
        self.pseudo_store_edit.setVisible(True)
        self.pseudo_brand_label.setVisible(True)
        self.pseudo_brand_edit.setVisible(True)
        self.pseudo_asin_label.setVisible(True)
        self.pseudo_asin_edit.setVisible(True)
        self.seller_label.setVisible(True)
        self.seller_edit.setVisible(True)
        self.rating_label.setVisible(True)
        self.rating_edit.setVisible(True)
        self.feedbacks_label.setVisible(True)
        self.feedbacks_edit.setVisible(True)
        self.price_label.setVisible(True)
        self.price_edit.setVisible(True)
        self.title_label.setVisible(True)
        self.title_edit.setVisible(True)
        self.search_kw_label.setVisible(True)
        self.search_kw_edit.setVisible(True)
        self.search_cat_label.setVisible(True)
        self.search_cat_edit.setVisible(True)
        self.buy_mission_type_label.setVisible(True)
        self.buy_mission_type_sel.setVisible(True)
        self.buy_sub_mission_type_label.setVisible(True)
        self.buy_sub_mission_type_sel.setVisible(True)
        self.asin_label.setVisible(True)
        self.asin_edit.setVisible(True)
        self.product_image_label.setVisible(True)
        self.product_image_edit.setVisible(True)

    def hide_buy_attributes(self):
        self.pseudo_store_label.setVisible(False)
        self.pseudo_store_edit.setVisible(False)
        self.pseudo_brand_label.setVisible(False)
        self.pseudo_brand_edit.setVisible(False)
        self.pseudo_asin_label.setVisible(False)
        self.pseudo_asin_edit.setVisible(False)
        self.seller_label.setVisible(False)
        self.seller_edit.setVisible(False)
        self.rating_label.setVisible(False)
        self.rating_edit.setVisible(False)
        self.feedbacks_label.setVisible(False)
        self.feedbacks_edit.setVisible(False)
        self.price_label.setVisible(False)
        self.price_edit.setVisible(False)
        self.title_label.setVisible(False)
        self.title_edit.setVisible(False)
        self.search_kw_label.setVisible(False)
        self.search_kw_edit.setVisible(False)
        self.search_cat_label.setVisible(False)
        self.search_cat_edit.setVisible(False)
        self.buy_mission_type_label.setVisible(False)
        self.buy_mission_type_sel.setVisible(False)
        self.buy_sub_mission_type_label.setVisible(False)
        self.buy_sub_mission_type_sel.setVisible(False)
        self.asin_label.setVisible(False)
        self.asin_edit.setVisible(False)
        self.product_image_label.setVisible(False)
        self.product_image_edit.setVisible(False)

    def show_sell_attributes(self):
        self.sell_mission_type_label.setVisible(True)
        self.sell_mission_type_sel.setVisible(True)

    def hide_sell_attributes(self):
        self.sell_mission_type_label.setVisible(False)
        self.sell_mission_type_sel.setVisible(False)

    def show_op_attributes(self):
        self.op_mission_type_label.setVisible(True)
        self.op_mission_type_sel.setVisible(True)

        self.op_mission_type_custome_label.setVisible(True)
        self.op_mission_type_custome_edit.setVisible(True)

    def hide_op_attributes(self):
        self.op_mission_type_label.setVisible(False)
        self.op_mission_type_sel.setVisible(False)
        self.op_mission_type_custome_label.setVisible(False)
        self.op_mission_type_custome_edit.setVisible(False)
