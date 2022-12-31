import os
import winreg
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
import boto3
from signio import *
import time
import datetime
from BorderLayout import *
import json
from os.path import exists
import locale
from MainGUI import *
from PlatoonMainGUI import *
from pycognito.aws_srp import AWSSRP
from envi import *

import asyncio
import qasync
from network import *

#ACCT_FILE =  os.environ.get('ECBOT_HOME') + "/resource/settings/uli.json"
echomepath = getECBotHome()
ACCT_FILE = echomepath + "/resource/settings/uli.json"
ROLE_FILE = echomepath + "/resource/settings/role.json"


class Login(QtWidgets.QDialog):
    def __init__(self, inApp, cloop, parent=None):
        self.cog = None
        self.mainwin = None
        self.platoonwin = None
        self.mode = "Sign In"
        self.machine_role = "Platoon"
        self.get_role()
        super(Login, self).__init__(parent)
        self.banner = QtWidgets.QLabel(self)
        pixmap = QtGui.QPixmap('C:/Users/Teco/PycharmProjects/ecbot/resource/ecBot09.png')
        self.banner.setPixmap(pixmap)

        # self.linkFont = QtGui.QFont('Arial', 8, QtGui.QFont.Style.StyleItalic)
        self.linkFont = QtGui.QFont('Arial', 8, italic=True)
        self.linkFont.setUnderline(True)

        self.mem_pw = True
        self.password_shown = False
        self.password_shown2 = False
        self.visibleIcon = QtGui.QIcon("C:/Users/Teco/PycharmProjects/ecbot/resource/eye48.png")
        self.hiddenIcon = QtGui.QIcon("C:/Users/Teco/PycharmProjects/ecbot/resource/hidden48.png")

        self.win_icon = QtGui.QIcon("C:/Users/Teco/PycharmProjects/ecbot/resource/eye48.png")

        self.setWindowIcon(self.win_icon)
        self.setWindowTitle('AiPPS E-Commerce Bots')
        self.setWindowFlag(QtCore.Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(QtCore.Qt.WindowMaximizeButtonHint, True)

        self.__translator = QtCore.QTranslator()

        self.lan_select = QtWidgets.QComboBox(self)
        self.lan_select.addItem('English')
        self.lan_select.addItem('中文')
        self.lan_select.currentIndexChanged.connect(self.on_lan_selected)

        self.logo0 = QtWidgets.QLabel(self)
        pixmap = QtGui.QPixmap('C:/Users/Teco/PycharmProjects/ecbot/resource/logo00.png')
        self.logo0.setPixmap(pixmap)
        self.logo0.setAlignment(QtCore.Qt.AlignTop)

        self.login_label = QtWidgets.QLabel(QtWidgets.QLabel.tr("Login"))
        self.login_label.setFont(QtGui.QFont('Arial', 20, QtGui.QFont.Bold))

        self.user_label = QtWidgets.QLabel(QtWidgets.QLabel.tr("User Name/Email:"))
        self.user_label.setFont(QtGui.QFont('Arial', 10))

        self.pw_label = QtWidgets.QLabel(QtWidgets.QLabel.tr("Password:"))
        self.pw_label.setFont(QtGui.QFont('Arial', 10))

        self.confirm_pw_label = QtWidgets.QLabel(QtWidgets.QLabel.tr("Confirm Password:"))
        self.confirm_pw_label.setFont(QtGui.QFont('Arial', 10))

        self.confirm_code_label = QtWidgets.QLabel(QtWidgets.QLabel.tr("Input Confirmation Code Retrieved From Your Email:"))
        self.confirm_code_label.setFont(QtGui.QFont('Arial', 6))

        self.textName = QtWidgets.QLineEdit(self)
        self.textConfirmCode = QtWidgets.QLineEdit(self)
        self.textPass = QtWidgets.QLineEdit(self)
        self.textPass.setEchoMode(QtWidgets.QLineEdit.Password)

        self.textPass2 = QtWidgets.QLineEdit(self)
        self.textPass2.setEchoMode(QtWidgets.QLineEdit.Password)

        self.show_visibility = True
        self.show_visibility2 = True
        if self.show_visibility:
            # Add the password hide/shown toggle at the end of the edit box.
            self.textPass.togglepasswordAction = self.textPass.addAction(
                self.visibleIcon,
                QtWidgets.QLineEdit.TrailingPosition
            )
            self.textPass.togglepasswordAction.triggered.connect(self.on_toggle_password_Action)

        if self.show_visibility2:
            # Add the password hide/shown toggle at the end of the edit box.
            self.textPass2.togglepasswordAction = self.textPass2.addAction(
                self.visibleIcon,
                QtWidgets.QLineEdit.TrailingPosition
            )
            self.textPass2.togglepasswordAction.triggered.connect(self.on_toggle_password_Action2)



        self.buttonLogin = QtWidgets.QPushButton(QtWidgets.QPushButton.tr('Login'), self)
        self.buttonLogin.clicked.connect(self.handleLogin)

        self.forget_label = QtWidgets.QLabel(QtWidgets.QLabel.tr("Forgot Password?"))
        self.forget_label.setFont(self.linkFont)
        self.forget_label.setAlignment(QtCore.Qt.AlignRight)
        self.forget_label.setStyleSheet("color: blue;")
        self.forget_label.mouseReleaseEvent = self.on_forgot_password

        self.signup_label = QtWidgets.QLabel(QtWidgets.QLabel.tr("No account? Sign Up Here!"))
        self.signup_label.setFont(self.linkFont)
        self.signup_label.setAlignment(QtCore.Qt.AlignRight)
        self.signup_label.mouseReleaseEvent = self.on_sign_up
        # now try to read the default acct file. if it doesn't exist or not having valid content, then move on,
        # otherwise, load the account info.
        if exists(ACCT_FILE):
            with open(ACCT_FILE, 'r') as file:
                data = json.load(file)
                self.textName.setText(data["user"])
                self.textPass.setText(self.descramble(data["pw"]))
                self.lan = data["lan"]
                self.show_visibility = data["mem_cb"]
        else:
            self.show_visibility = True             #default
            localLan = locale.getdefaultlocale()
            print(localLan)
            if 'en_' in localLan[0]:
                self.lan = "EN"
            else:
                self.lan = "ZH"


        self.mempw_cb = QtWidgets.QCheckBox(QtWidgets.QCheckBox.tr("Memorize Password"))
        if self.show_visibility:
            self.mempw_cb.setCheckState(QtCore.Qt.Checked)
            # now try to load password
        else:
            self.mempw_cb.setCheckState(QtCore.Qt.Unchecked)
        self.mempw_cb.setFont(self.linkFont)
        self.mempw_cb.setStyleSheet("color: blue;")

        print(self.mempw_cb.checkState())

        #self.signup_label.setStyleSheet("color: blue; background-color: yellow")
        self.signup_label.setStyleSheet("color: blue;")

        self.confirm_code_label.setVisible(False)
        self.textConfirmCode.setVisible(False)

        self.confirm_pw_label.setVisible(False)
        self.textPass2.setVisible(False)

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(self.banner)
        # layout.addWidget(self.textName)
        log_layout = QtWidgets.QVBoxLayout(self)
        self.reminder_layout = QtWidgets.QHBoxLayout(self)
        self.reminder_layout.addWidget(self.mempw_cb)
        self.reminder_layout.addWidget(self.forget_label)
        log_layout.addWidget(self.lan_select)
        log_layout.addWidget(self.logo0)
        log_layout.addWidget(self.login_label)
        log_layout.addWidget(self.user_label)
        log_layout.addWidget(self.textName)

        log_layout.addWidget(self.confirm_code_label)
        log_layout.addWidget(self.textConfirmCode)

        log_layout.addWidget(self.pw_label)
        log_layout.addWidget(self.textPass)

        log_layout.addWidget(self.confirm_pw_label)
        log_layout.addWidget(self.textPass2)

        log_layout.addLayout(self.reminder_layout)
        log_layout.addWidget(self.buttonLogin)
        log_layout.addWidget(self.signup_label)
        layout.addLayout(log_layout)

        self.loop = cloop

    # async def launchLAN(self):

    def get_role(self):
        self.machine_role = "Platoon"

        if exists(ROLE_FILE):
            with open(ROLE_FILE, 'r') as file:
                mr_data = json.load(file)
                self.machine_role = mr_data["machine_role"]

    def isCommander(self):
        if self.machine_role == "Commander":
            return True
        else:
            return False

    def __setup_language(self):
        system_locale, _ = locale.getdefaultlocale()
        search_folder = os.path.dirname(__file__)
        search_folder = os.path.join(search_folder, "..", "translations")
        print(system_locale, search_folder)
        self.__translator.load(system_locale, search_folder)
        self.__app.installTranslator(self.__translator)

    def on_lan_selected(self, index):
        print("Index changed", index)

        if index == 1:
            self.__translator.load(QtCore.QLocale.Chinese, "C:/Users/Teco/PycharmProjects/ecbot/resource/translation/example_cn.qm")
            #self.__app.installTranslator(self.__translator)
            _app = QApplication.instance()
            _app.installTranslator(self.__translator)
            #QtCore.QCoreApplication.installTranslator(self.__translator)
        else:
            _app = QApplication.instance()
            _app.removeTranslator(self.__translator)

    def changeEvent(self, event):
        print("event occured....", event.type())
        if event.type() == QtCore.QEvent.LanguageChange:
            print("re-translating....")
            self.retranslateUi()
        #super(Login, self).changeEvent(event)


    def retranslateUi(self):
        self.buttonLogin.setText(QtWidgets.QApplication.translate('QtWidgets.QPushButton', 'Login'))
        self.login_label.setText(QtWidgets.QApplication.translate('QtWidgets.QLabel', 'Login'))


    def on_toggle_password_Action(self):
        if not self.password_shown:
            self.textPass.setEchoMode(QtWidgets.QLineEdit.Normal)
            self.password_shown = True
            self.textPass.togglepasswordAction.setIcon(self.hiddenIcon)
        else:
            self.textPass.setEchoMode(QtWidgets.QLineEdit.Password)
            self.password_shown = False
            self.textPass.togglepasswordAction.setIcon(self.visibleIcon)

    def on_toggle_password_Action2(self):
        if not self.password_shown2:
            self.textPass2.setEchoMode(QtWidgets.QLineEdit.Normal)
            self.password_shown2 = True
            self.textPass2.togglepasswordAction.setIcon(self.hiddenIcon)
        else:
            self.textPass2.setEchoMode(QtWidgets.QLineEdit.Password)
            self.password_shown2 = False
            self.textPass2.togglepasswordAction.setIcon(self.visibleIcon)


    def on_sign_up(self, event):
        self.buttonLogin.setText(QtWidgets.QPushButton.tr("Sign Up"))
        self.confirm_pw_label.setVisible(True)
        self.textPass2.setVisible(True)
        self.login_label.setText(QtWidgets.QLabel.tr("Sign Up A New Account"))
        self.buttonLogin.clicked.disconnect(self.handleLogin)
        self.buttonLogin.clicked.connect(self.handleSignUp)


    def on_forgot_password(self, event):
        self.buttonLogin.setText(QtWidgets.QPushButton.tr("Recover Password"))
        self.textPass.setVisible(False)
        self.pw_label.setVisible(False)
        self.signup_label.setVisible(False)
        self.mempw_cb.setVisible(False)
        self.forget_label.setVisible(False)
        self.login_label.setText(QtWidgets.QLabel.tr("Recover Password"))
        self.login_label.setAlignment(QtCore.Qt.AlignTop)

        self.user_label.setText("Input Email Address To Recover Password:")
        self.user_label.resize(200, 100);
        self.user_label.setAlignment(QtCore.Qt.AlignTop)


        self.buttonLogin.clicked.disconnect(self.handleLogin)
        self.buttonLogin.clicked.connect(self.handleForgotPassword)


    def handleLogin(self):
        print("logging in....")
        global commanderServer
        global commanderXport

        self.aws_client = boto3.client('cognito-idp', region_name='us-east-1')
        self.aws_srp = AWSSRP(username=self.textName.text(), password=self.textPass.text(), pool_id=USER_POOL_ID, client_id=CLIENT_ID, client=self.aws_client)
        self.tokens = self.aws_srp.authenticate_user()



        #cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com", botocore_config=Config(signature_version=UNSIGNED))
        #cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com")
        self.cog = Cognito(USER_POOL_ID, CLIENT_ID, username=self.textName.text(), refresh_token='optional-refresh-token', access_key='AKIAIOSFODNN7EXAMPLE', secret_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY')
        #self.cog.check_tokens()
        #response = self.cog.authenticate(password=self.textPass.text())
        time.sleep(1)
        #user = self.cog.get_user()
        time.sleep(1)
        #cog.check_tokens()  # Optional, if you want to maybe renew the tokens
        # self.cog.verify_tokens()
        #print(self.cog.id_token)
        #print(self.cog.access_token)
        #print(self.cog.refresh_token)
        #print(user)
        print("timezone:", datetime.now().astimezone().tzinfo)
        #now make this window dissappear and bring out the main windows.
        data = {"mem_cb": True, "user": self.textName.text(), "pw": self.scramble(self.textPass.text()), "lan": "EN"}
        if self.mempw_cb.checkState() == QtCore.Qt.Unchecked:
            data["mem_cb"] = False

        print(data)
        with open(ACCT_FILE, 'w') as jsonfile:
            json.dump(data, jsonfile)
        self.hide()
        print("hello hello hello")

        if self.machine_role == "Commander":
            self.mainwin = MainWindow(self.tokens, commanderServer, self.textName.text())
            print("Running as a commander...", commanderServer)
            self.mainwin.setOwner(self.textName.text())
            self.mainwin.show()
        else:
            self.platoonwin = PlatoonMainWindow(self.tokens, self.textName.text(), commanderXport)
            print("Running as a platoon...")
            self.platoonwin.setOwner(self.textName.text())
            self.platoonwin.show()

    def fakeLogin(self):
            print("logging in....")
            # cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com", botocore_config=Config(signature_version=UNSIGNED))
            # cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com")
            #self.cog = Cognito(USER_POOL_ID, CLIENT_ID, username=self.textName.text(),
            #                   access_key='AKIAIOSFODNN7EXAMPLE', secret_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY')
            #self.aws_client = boto3.client('cognito-idp', region_name='us-east-1')
            #self.aws_srp = AWSSRP(username=self.textName.text(), password=self.textPass.text(), pool_id=USER_POOL_ID,
            #                      client_id=CLIENT_ID, client=self.aws_client)
            #self.tokens = self.aws_srp.authenticate_user()
            self.tokens = {'ChallengeParameters': {}, 'AuthenticationResult': {'AccessToken': 'eyJraWQiOiJSd1J3MUV2bEowdzFMNm04QmVxWktTdjE5aGViN2didGtJalU2Ylh0XC9uWT0iLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJkYmNhYmVhMy0xZmNiLTQ2MWItYWJlOS1kZjU0NzIzZGI1ODIiLCJkZXZpY2Vfa2V5IjoidXMtZWFzdC0xXzhhZmUwOGFhLTMzZWMtNDY5OS05YWViLWY5YThhMzgwMjIwNSIsImlzcyI6Imh0dHBzOlwvXC9jb2duaXRvLWlkcC51cy1lYXN0LTEuYW1hem9uYXdzLmNvbVwvdXMtZWFzdC0xX3VVbUtKVWZCMyIsImNsaWVudF9pZCI6IjU0MDByOHE1cDlnZmRobG4yZmVxY3BsanNoIiwib3JpZ2luX2p0aSI6IjU4YzhhNGZjLTBiZTEtNDNkNS1iNDlhLTI5ZTM5MDBhMzZhZSIsImV2ZW50X2lkIjoiMGNlZTIwZjgtYzhkNy00ZDRkLWJhODAtOGExNjAyZGExMzBiIiwidG9rZW5fdXNlIjoiYWNjZXNzIiwic2NvcGUiOiJhd3MuY29nbml0by5zaWduaW4udXNlci5hZG1pbiIsImF1dGhfdGltZSI6MTY1ODEyNTU4MywiZXhwIjoxNjU4MTI5MTgzLCJpYXQiOjE2NTgxMjU1ODMsImp0aSI6ImMwZGYwYzY2LWIxYTUtNDQ3ZC1hZTcwLTg0Y2I2MjM3MmIxMyIsInVzZXJuYW1lIjoiZGJjYWJlYTMtMWZjYi00NjFiLWFiZTktZGY1NDcyM2RiNTgyIn0.MGbBld8XVSqoBSSJTxi6ptX4VJesmfaDmJwRoS480Fk2qrAGtskkzUkY133hj3iM8AscwpjS2rr1khBuvjbwPvK2T4Erf0eIsLhViEzE5RWShIHRdDV2FHXS9FpvP_T1jrRBZUcE5mbyHB1ZzCzGhNTLSb_3mqix_oRuKxHrkorqhLbPu_3rv9IJLHfWgZatLvMEjTn33uTSuzJ8MZGyUu0MQJ5FmKwrI4I0yX9jqIjq26xNNUyyw4LNkIwT9FD04mwB-4GtP_zfSYjK4OYumAHS-g6We_Z5guHBZmpSuPmEBPhtFkLusJMOHjuR8JHSrG52pK60YAZvNbL5zpyP7A', 'ExpiresIn': 3600, 'TokenType': 'Bearer', 'RefreshToken': 'eyJjdHkiOiJKV1QiLCJlbmMiOiJBMjU2R0NNIiwiYWxnIjoiUlNBLU9BRVAifQ.Ooz_MgLzRFVbewNH4_m7A3HKEWBOIrVNmUzrXd1msMhQoDyIMlq3hOJN5WipYUeJ_LceDp37be--Ot0QI4wQLGH-FnXEVhqY6WxYoAVJmOckfhO5tutPFo4o3nElQn3bUhPpGsW7A3Hz_KhsgNVTn6fhCEkt6aL_BYgTdLz9VWX1nbdGxjWv8W2QNtX34CAmIf-pga6MYb0EsqeDbk_-nfBOPOXpgK5qx-Zf5FTYk7zOPctXgZuqmmGbnbkw3chjaWRnJOEEIEpECHRUWSUNC2_K6Die-iWhmEsTxijnidGu6lmtvlAwGSx_uZdj6stUfOgQ9ucwAY-JlG_08WzMtg.KJBsKK42_IeYPVZt.kj4xRX9BCz8He30cN3lEdtgBQHlF16DDdH6hjZglt22kYObD60-GNIRc8Ncm8TP8am0HVKMV3BEk3_epSMiJ0fAPqevR_UjNmFPRZmriU9lA5I1ygJWKaoHKhkIE0QWzjNJQl6hy0gX1rMqXBdOeVwOTIn-aywyknyGO-zbmQmh6V9w9OImRKn-fdjy19mJ9xd1BwGVfOzh95v8uZamZyR6q2ZInReJrYlCJukKsuuWV9rCt_dpanmzTZ3zsrroF6TioQhEbJcpSQsfi_CIFpVWS8z0PShlW7vZ4B2EMwbJRPLwmJXKyP2LZvn2z4cdgktSR6txdPw8RwKSAH-unhB2evzDsLNJ5U3DGfmHg7s6VZQCfMQwQf1HkldwYvdHyXyJ4gNc9x6Xx__lgLc1wTuE1VDs5CDtJQB0b4NJ1REbSobBE_dK_Fzx_1ap7PT5Dxhxzt1jid0ujZQ4wNHjSZlVQK76HIBk_Jwh_ywj6KQI5IEO2PmwOIaPov_Kp_10EFHvYhSvrKGlan1K7h-04LjHCeHugxWzyFSnYyCo0Bq4nGQU5swhdmqJMcMP7p3AecgCAj1kgTvIBrLG-Vn9dJPyJgtm4AUKcMsZfrd3MZsuFWSiwKuN8M7f4f-bt2sRmGNRgemzXtCwM8xYpiRtr_c_GrmUUH5RJAuNCkr_dcT7H8VziJCyllCLBwN72MGpQ0LT2_oD4P1RSk0gjCqUW7OpSv8hlmf9ZSwYLmUeiVaRZ-PoPVW2QYGhNX83dkAel5Ke7nqIhTrXbibF2ZTdG1YFkc6yZyoGeVyW-uYbtAFZ_EV_Acomq7S_gVW68ppxUID1btoAusFQIIwCTAE_vWIxxf1whzuA_coIQJDjzhlBi8WZBz5xr9HSiBIo8m4XnHaudxmPZkv0b-T03d663zczuiixNJXNWKoqgu1hhxUZ3LxTWSN0hihvtdF-CMecF7qYvAPhJ60u6SQwdQiohM1GGEzCWHPIFTJNoEiFIb76RQjmXNnJJU6u_eVqWJmHrcJwxp6Fd6s3t1svUQewip8IiOLpkz4eCTP1kD4ASX-f6i0cflqtfDoJMEG_8qFG7Fd30-wvhxKLYvMXRz9GTURszOBVSFewukqksuXV6vFB8ymCQOAKJsQbKrfSZzdCok5oqZxcPWpT6bkMeF4wV9pnA-ydxRQEDMIsOgPPDixvdpmvVg2FKiPNZVlKGipEUpB20fELjIIqN4tmU1XB9brRDOuawhdaKoHDHDC7HCp_-v0_B-iUsMO_GqgSoGuEZy3ghSI8SiV0YoOJu5n5lISmG6R1nYhcrPewpyCN9MYUmWCaaa1-oZazJqzBSpAwO30ItleZRkKCgzEzak7soHsmvzD19CCjZWXqS77_Aib7huWcqOA7viXDJJ0xdTKMGd9LcsiHwVkCrRV6QJcBVZaNSRZ-lS3UU7v14uprz.cljsuZCktkNGeEdSZxWhPw', 'IdToken': 'eyJraWQiOiJQcHRQaVNMMVVha3NkVHYxRjMwdTdFYVBtT1UySXRwekhLMjNIb3Erd0FRPSIsImFsZyI6IlJTMjU2In0.eyJzdWIiOiJkYmNhYmVhMy0xZmNiLTQ2MWItYWJlOS1kZjU0NzIzZGI1ODIiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiaXNzIjoiaHR0cHM6XC9cL2NvZ25pdG8taWRwLnVzLWVhc3QtMS5hbWF6b25hd3MuY29tXC91cy1lYXN0LTFfdVVtS0pVZkIzIiwiY29nbml0bzp1c2VybmFtZSI6ImRiY2FiZWEzLTFmY2ItNDYxYi1hYmU5LWRmNTQ3MjNkYjU4MiIsIm9yaWdpbl9qdGkiOiI1OGM4YTRmYy0wYmUxLTQzZDUtYjQ5YS0yOWUzOTAwYTM2YWUiLCJhdWQiOiI1NDAwcjhxNXA5Z2ZkaGxuMmZlcWNwbGpzaCIsImV2ZW50X2lkIjoiMGNlZTIwZjgtYzhkNy00ZDRkLWJhODAtOGExNjAyZGExMzBiIiwidG9rZW5fdXNlIjoiaWQiLCJhdXRoX3RpbWUiOjE2NTgxMjU1ODMsImV4cCI6MTY1ODEyOTE4MywiaWF0IjoxNjU4MTI1NTgzLCJqdGkiOiI5YmU4MjU3MC01MWRhLTQ0NjQtOGQ2Ny1lZTkyZWRmNDYyMzgiLCJlbWFpbCI6InNvbmdjQHlhaG9vLmNvbSJ9.Xcw8TgDYdxHY_6OMfzFby3UMkrc6s0QGPTeCKALrQ1fNqMgnfOUPME94NW8aAz1jkkUX87buv4imYH37Sdv4NL8UX5YMZEXU22bbGncmMZCFAyUDbBQ6YMRX-WUlbbRBUcom0YzaHLrYN8QJygVYcnVYT2YzDUxS-L_bA71FRqoylDJe5oly9QmPmBDP08Fkp_IcMS_mSJ9CErSJpEJEezzudKRmVvof_YUdg6kEBGXGCQB_lOkXdUPE4sWP8ZpKCCkLa-VOLOTXp1Le9LOw5Ru38ofAL02DmXsoRkAMYl_YrU-I90HXNB4brnBZpNZ497TpiypbmJpYHeVCr8mAqg', 'NewDeviceMetadata': {'DeviceKey': 'us-east-1_8afe08aa-33ec-4699-9aeb-f9a8a3802205', 'DeviceGroupKey': '-iY8sjxdl'}}, 'ResponseMetadata': {'RequestId': '0cee20f8-c8d7-4d4d-ba80-8a1602da130b', 'HTTPStatusCode': 200, 'HTTPHeaders': {'date': 'Mon, 18 Jul 2022 06:26:23 GMT', 'content-type': 'application/x-amz-json-1.1', 'content-length': '4377', 'connection': 'keep-alive', 'x-amzn-requestid': '0cee20f8-c8d7-4d4d-ba80-8a1602da130b'}, 'RetryAttempts': 0}}

            print(self.tokens)

            self.mainwin = MainWindow(self.tokens, "songc@yahoo.com")
            print("faker...")
            self.mainwin.setOwner("Nobody")
            self.mainwin.show()

        #self..show()

        # client = boto3.client("cognito-idp", region_name="us-east-1", config=Config(signature_version=UNSIGNED))
        #
        # print(CLIENT_ID)
        #
        # # Initiating the Authentication,
        # response = client.initiate_auth(
        #     ClientId=CLIENT_ID,
        #     AuthFlow="USER_PASSWORD_AUTH",
        #     AuthParameters={"USERNAME": 'songc@yahoo.com', "PASSWORD": 'Sc12345!'},
        # )

        # if (self.textName.text() == 'foo' and
        #     self.textPass.text() == 'bar'):
        #     self.accept()
        # else:
        #     QtWidgets.QMessageBox.warning(
        #         self, 'Error', 'Bad user or password')


    def handleSignUp(self):
        print("logging up...." + self.textName.text() + "...." + self.textPass.text())
        if (self.textPass.text() ==  self.textPass2.text()):
            self.cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username=self.textName.text())
            self.cog.set_base_attributes(email=self.textName.text())
            response = self.cog.register(self.textName.text(), self.textPass.text())

            # response = auth_client.sign_up(
            #     ClientId=CLIENT_ID,
            #     Username="songc@yahoo.com",
            #     Password="Sc12345!",
            #     UserAttributes=[{"Name": "email", "Value": "songc@yahoo.com"}],
            # )
            print(response)

            msgBox = QtWidgets.QMessageBox()
            msgBox.setText("Please confirm that you have received the verification email and verified it.")
            #msgBox.setInformativeText("Do you want to save your changes?")
            #msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            #msgBox.setDefaultButton(QMessageBox.Save)
            ret = msgBox.exec()

            #now back to the standard login screen.
            self.cog.initiate_forgot_password()
            self.confirm_code_label.setVisible(False)
            self.textConfirmCode.setVisible(False)
            self.pw_label.setText(QtWidgets.QLabel.tr("Password:"))
            self.login_label.setText(QtWidgets.QLabel.tr("Login"))
            self.signup_label.setVisible(True)
            self.mempw_cb.setVisible(True)
            self.forget_label.setVisible(True)

            self.confirm_pw_label.setVisible(False)
            self.textPass2.setVisible(False)

            self.buttonLogin.setText(QtWidgets.QPushButton.tr("Login"))
            self.buttonLogin.clicked.disconnect(self.handleSignUp)
            self.buttonLogin.clicked.connect(self.handleLogin)

        else:
            QtWidgets.QMessageBox.warning(
                self, 'Error', 'mismatched password')


    def handleForgotPassword(self):
        print("forgot password...." + self.textName.text())
        if (not self.textName.text() ==  ""):
            self.cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username=self.textName.text())

            self.cog.initiate_forgot_password()
            self.confirm_code_label.setVisible(True)
            self.textConfirmCode.setVisible(True)
            self.pw_label.setText(QtWidgets.QLabel.tr("Set New Password:"))
            self.pw_label.setVisible(True)
            self.textPass.setVisible(True)
            self.user_label.setText(QtWidgets.QLabel.tr("Input Email Address:"))
            self.buttonLogin.setText(QtWidgets.QPushButton.tr("Confirm New Password"))
            self.buttonLogin.clicked.disconnect(self.handleForgotPassword)
            self.buttonLogin.clicked.connect(self.handleConfirmForgotPassword)

            # cog.admin_reset_password(self.textName.text())   # this API can only be called by administrator

            # response = auth_client.sign_up(
            #     ClientId=CLIENT_ID,
            #     Username="songc@yahoo.com",
            #     Password="Sc12345!",
            #     UserAttributes=[{"Name": "email", "Value": "songc@yahoo.com"}],
            # )
            # print(response)

        else:
            QtWidgets.QMessageBox.warning(
                self, 'Error', 'Invalid Email Address')

    def handleConfirmForgotPassword(self):
        print("forgot password...." + self.textPass.text())
        self.cog.confirm_forgot_password(self.textConfirmCode.text(), self.textPass.text())

        self.cog.initiate_forgot_password()
        self.confirm_code_label.setVisible(False)
        self.textConfirmCode.setVisible(False)
        self.pw_label.setText(QtWidgets.QLabel.tr("Password:"))
        self.login_label.setText(QtWidgets.QLabel.tr("Login"))
        self.signup_label.setVisible(True)
        self.mempw_cb.setVisible(True)
        self.forget_label.setVisible(True)

        self.buttonLogin.setText(QtWidgets.QPushButton.tr("Login"))
        self.buttonLogin.clicked.disconnect(self.handleConfirmForgotPassword)
        self.buttonLogin.clicked.connect(self.handleLogin)

    def scramble(self, word):
        min = 33
        max = 126
        wl = len(word)
        for i in range(wl):
            asc = ord(word[i]) - (i+1)
            if asc < min:
                asc = max - (min-asc) + 1
            word = word[0:i] + chr(asc) + word[i + 1:]
        print(word)
        return word

    def descramble(self, word):
        min = 33
        max = 126
        wl = len(word)
        for i in range(wl):
            asc = ord(word[i]) + (i + 1)
            if asc > max:
                asc = min + (asc - max) - 1
            word = word[0:i] + chr(asc) + word[i + 1:]
        print(word)
        return word