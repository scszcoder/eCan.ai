import os

from PySide6.QtCore import QLocale, QTranslator, QCoreApplication
# import winreg
from PySide6.QtWidgets import QDialog
import botocore
from botocore.exceptions import ClientError
import boto3
from signio import *
from BorderLayout import *
import json
from os.path import exists
import locale
from MainGUI import *
from pycognito.aws_srp import AWSSRP
from envi import *
from Cloud import *
from config.app_info import app_info
from datetime import datetime

import asyncio
import qasync
from network import *

#ACCT_FILE =  os.environ.get('ECBOT_HOME') + "/resource/settings/uli.json"
# ecbhomepath = getECBotHome()
ecbhomepath = app_info.app_home_path
ecb_data_homepath = getECBotDataHome()


ACCT_FILE = ecb_data_homepath + "/uli.json"
ROLE_FILE = ecb_data_homepath + "/role.json"


class Login(QDialog):
    def __init__(self, parent=None):
        self.cog = None
        self.mainwin = None
        self.xport = None
        self.ip = commanderIP
        self.aws_client = boto3.client('cognito-idp', region_name='us-east-1')
        self.lang = "en"
        self.gui_net_msg_queue = asyncio.Queue()
        self.aws_srp = None

        self.mode = "Sign In"
        self.machine_role = "Platoon"
        self.read_role()
        super(Login, self).__init__(parent)
        self.banner = QLabel(self)
        pixmap = QPixmap(ecbhomepath + '/resource/images/icons/ecBot09.png')
        self.banner.setPixmap(pixmap)

        # self.linkFont = QFont('Arial', 8, QFont.Style.StyleItalic)
        self.linkFont = QFont('Arial', 8, italic=True)
        self.linkFont.setUnderline(True)

        self.mem_pw = True
        self.password_shown = False
        self.password_shown2 = False
        self.visibleIcon = QIcon(ecbhomepath + "/resource/images/icons/eye48.png")
        self.hiddenIcon = QIcon(ecbhomepath + "/resource/images/icons/hidden48.png")

        self.win_icon = QIcon(ecbhomepath + "/resource/images/icons/eye48.png")

        self.setWindowIcon(self.win_icon)
        self.setWindowTitle('AiPPS E-Commerce Bots')
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)

        self.__translator = QTranslator()

        self.lan_select = QComboBox(self)
        self.lan_select.addItem('English')
        self.lan_select.addItem('中文')
        self.lan_select.currentIndexChanged.connect(self.on_lan_selected)

        self.logo0 = QLabel(self)
        pixmap = QPixmap(ecbhomepath + '/resource/images/icons/maipps_logo192.png')
        self.logo0.setPixmap(pixmap)
        self.logo0.setAlignment(Qt.AlignTop)

        # self.login_label = QLabel(QLabel.tr("Login"))
        self.login_label = QLabel("Login")

        self.login_label.setFont(QFont('Arial', 20, QFont.Bold))
        self.user_label = QLabel(QApplication.translate("QLabel", "User Name(Email):"))
        self.user_label.setFont(QFont('Arial', 10))

        self.pw_label = QLabel(QApplication.translate("QLabel", "Password:"))
        self.pw_label.setFont(QFont('Arial', 10))

        self.confirm_pw_label = QLabel(QApplication.translate("QLabel", "Confirm Password:"))
        self.confirm_pw_label.setFont(QFont('Arial', 10))

        self.confirm_code_label = QLabel(QApplication.translate("QLabel", "Input Confirmation Code Retrieved From Your Email:"))
        self.confirm_code_label.setFont(QFont('Arial', 6))

        self.textName = QLineEdit(self)
        self.textConfirmCode = QLineEdit(self)
        self.textPass = QLineEdit(self)
        self.textPass.setEchoMode(QLineEdit.Password)

        self.textPass2 = QLineEdit(self)
        self.textPass2.setEchoMode(QLineEdit.Password)

        self.show_visibility = True
        self.show_visibility2 = True
        if self.show_visibility:
            # Add the password hide/shown toggle at the end of the edit box.
            self.textPass.togglepasswordAction = self.textPass.addAction(
                self.visibleIcon,
                QLineEdit.TrailingPosition
            )
            self.textPass.togglepasswordAction.triggered.connect(self.on_toggle_password_Action)

        if self.show_visibility2:
            # Add the password hide/shown toggle at the end of the edit box.
            self.textPass2.togglepasswordAction = self.textPass2.addAction(
                self.visibleIcon,
                QLineEdit.TrailingPosition
            )
            self.textPass2.togglepasswordAction.triggered.connect(self.on_toggle_password_Action2)



        # self.buttonLogin = QPushButton(QPushButton.tr('Login'), self)
        self.buttonLogin = QPushButton('Login', self)

        self.buttonLogin.clicked.connect(self.handleLogin)

        self.forget_label = QLabel(QApplication.translate("QLabel", "Forgot Password?"))
        self.forget_label.setFont(self.linkFont)
        self.forget_label.setAlignment(Qt.AlignRight)
        self.forget_label.setStyleSheet("color: blue;")
        self.forget_label.mouseReleaseEvent = self.on_forgot_password

        self.signup_label = QLabel(QApplication.translate("QLabel", "No account? Sign Up Here!"))
        self.signup_label.setFont(self.linkFont)
        self.signup_label.setAlignment(Qt.AlignRight)
        self.signup_label.mouseReleaseEvent = self.on_sign_up
        # now try to read the default acct file. if it doesn't exist or not having valid content, then move on,
        # otherwise, load the account info.
        if exists(ACCT_FILE):
            with open(ACCT_FILE, 'r') as file:
                data = json.load(file)
                self.textName.setText(data["user"])
                if data["pw"] in os.environ:
                    self.textPass.setText(self.descramble(os.environ[data["pw"]]))
                else:
                    self.textPass.setText("")
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

        self.mempw_cb = QCheckBox(QApplication.translate("QCheckBox", "Memorize Password"))
        if self.show_visibility:
            self.mempw_cb.setCheckState(Qt.Checked)
            # now try to load password
        else:
            self.mempw_cb.setCheckState(Qt.Unchecked)
        self.mempw_cb.setFont(self.linkFont)
        self.mempw_cb.setStyleSheet("color: blue;")

        print(self.mempw_cb.checkState())

        #self.signup_label.setStyleSheet("color: blue; background-color: yellow")
        self.signup_label.setStyleSheet("color: blue;")

        self.confirm_code_label.setVisible(False)
        self.textConfirmCode.setVisible(False)

        self.confirm_pw_label.setVisible(False)
        self.textPass2.setVisible(False)

        layout = QHBoxLayout(self)
        layout.addWidget(self.banner)
        # layout.addWidget(self.textName)
        log_layout = QVBoxLayout()
        self.reminder_layout = QHBoxLayout()
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

    # async def launchLAN(self):
    def get_mainwin(self):
        return self.mainwin

    def get_msg_queue(self):
        return self.gui_net_msg_queue

    def set_xport(self, xport):
        self.xport = xport

    def set_ip(self, ip):
        self.ip = ip

    def read_role(self):
        self.machine_role = "Platoon"

        if exists(ROLE_FILE):
            with open(ROLE_FILE, 'r') as file:
                mr_data = json.load(file)
                self.machine_role = mr_data["machine_role"]

    def get_role(self):
        # is function is for testing purpose only
        return self.machine_role

    def set_role(self, role):
        # is function is for testing purpose only
        self.machine_role = role

    def isCommander(self):
        if self.machine_role == "Commander" or self.machine_role == "CommanderOnly":
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
            self.lang = "zh"
            print("loading chinese fonts....", ecbhomepath + "/ecbot_zh.qm")
            locale = QLocale(QLocale.Chinese)
            self.__translator.load(QLocale.Chinese, ecbhomepath + "/ecbot_zh.qm")
            # self.__translator.load(ecbhomepath + "/ecbot_zh.qm")

            #self.__app.installTranslator(self.__translator)
            _app = QCoreApplication.instance()
            _app.installTranslator(self.__translator)
            #QCoreApplication.installTranslator(self.__translator)
            print("chinese translator loaded")
        else:
            self.lang = "en"
            _app = QApplication.instance()
            _app.removeTranslator(self.__translator)

    def changeEvent(self, event):
        print("event occured....", event.type())
        if event.type() == QEvent.LanguageChange:
            print("re-translating....")
            self.retranslateUi()
        #super(Login, self).changeEvent(event)


    def retranslateUi(self):
        self.buttonLogin.setText(QApplication.translate('QPushButton', 'Login'))
        self.login_label.setText(QApplication.translate('QLabel', 'Login'))


    def on_toggle_password_Action(self):
        if not self.password_shown:
            self.textPass.setEchoMode(QLineEdit.Normal)
            self.password_shown = True
            self.textPass.togglepasswordAction.setIcon(self.hiddenIcon)
        else:
            self.textPass.setEchoMode(QLineEdit.Password)
            self.password_shown = False
            self.textPass.togglepasswordAction.setIcon(self.visibleIcon)

    def on_toggle_password_Action2(self):
        if not self.password_shown2:
            self.textPass2.setEchoMode(QLineEdit.Normal)
            self.password_shown2 = True
            self.textPass2.togglepasswordAction.setIcon(self.hiddenIcon)
        else:
            self.textPass2.setEchoMode(QLineEdit.Password)
            self.password_shown2 = False
            self.textPass2.togglepasswordAction.setIcon(self.visibleIcon)


    def on_sign_up(self, event):
        self.buttonLogin.setText(QApplication.translate("QPushButton", "Sign Up"))
        self.confirm_pw_label.setVisible(True)
        self.textPass2.setVisible(True)
        self.login_label.setText(QApplication.translate("QLabel", "Sign Up A New Account"))
        self.buttonLogin.clicked.disconnect(self.handleLogin)
        self.buttonLogin.clicked.connect(self.handleSignUp)


    def on_forgot_password(self, event):
        self.buttonLogin.setText(QApplication.translate("QPushButton", "Recover Password"))
        self.textPass.setVisible(False)
        self.pw_label.setVisible(False)
        self.signup_label.setVisible(False)
        self.mempw_cb.setVisible(False)
        self.forget_label.setVisible(False)
        self.login_label.setText(QApplication.translate("QLabel", "Recover Password"))
        self.login_label.setAlignment(Qt.AlignTop)

        self.user_label.setText(QApplication.translate("QLabel", "Input Email Address To Recover Password:"))
        self.user_label.resize(200, 100);
        self.user_label.setAlignment(Qt.AlignTop)


        self.buttonLogin.clicked.disconnect(self.handleLogin)
        self.buttonLogin.clicked.connect(self.handleForgotPassword)

    def set_or_replace_env_variable_macos(self, var_name, var_value, shell=None):
        """
        Sets or replaces a permanent environment variable for the user on macOS.
        The variable will be set or updated for the default shell of the user (Bash or Zsh).

        :param var_name: Name of the environment variable
        :param var_value: Value of the environment variable
        :param shell: Optional, specify the shell (bash or zsh), otherwise auto-detect
        :return: Status message
        """
        # Auto-detect the shell if not specified
        if not shell:
            shell = os.path.basename(os.environ.get('SHELL', ''))

        # Determine the appropriate config file based on the shell
        if shell == 'bash':
            config_file = os.path.join(os.path.expanduser('~'), '.bash_profile')
            if not os.path.exists(config_file):
                # Fallback to .bashrc if .bash_profile does not exist
                config_file = os.path.join(os.path.expanduser('~'), '.bashrc')
        elif shell == 'zsh':
            config_file = os.path.join(os.path.expanduser('~'), '.zshrc')
        else:
            return "Unsupported shell. Please use Bash or Zsh."

        # Construct the command to add or update the environment variable
        env_var_command = f'export {var_name}="{var_value}"'
        variable_updated = False

        # Check if the variable is already in the file
        try:
            with open(config_file, 'r') as file:
                lines = file.readlines()

            with open(config_file, 'w') as file:
                for line in lines:
                    # If the variable exists, replace its value
                    if line.strip().startswith(f'export {var_name}='):
                        file.write(f'{env_var_command}\n')
                        variable_updated = True
                    else:
                        file.write(line)

                # If the variable was not found, add it to the file
                if not variable_updated:
                    file.write(f'\n{env_var_command}\n')

            print(f"Environment variable {var_name} {'updated' if variable_updated else 'set'} successfully in {config_file}.")
        except IOError as e:
            print(f"Error: Unable to open or write to {config_file} - {e}")

    def handleLogin(self):
        print("logging in....")
        global commanderServer
        global commanderXport

        try:
            self.aws_srp = AWSSRP(username=self.textName.text(), password=self.textPass.text(), pool_id=USER_POOL_ID, client_id=CLIENT_ID, client=self.aws_client)
            self.tokens = self.aws_srp.authenticate_user()

            # print("token: ", self.tokens)

            #cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com", botocore_config=Config(signature_version=UNSIGNED))
            #cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com")
            self.cog = Cognito(USER_POOL_ID, CLIENT_ID, username=self.textName.text(), access_token=self.tokens["AuthenticationResult"]["AccessToken"], refresh_token=self.tokens["AuthenticationResult"]["RefreshToken"], access_key='AKIAIOSFODNN7EXAMPLE', secret_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY')

            # print("cog access token:", self.cog.access_token)
            #self.cog.check_tokens()
            #response = self.cog.authenticate(password=self.textPass.text())

            time.sleep(1)
            # user = self.cog.get_user()
            time.sleep(1)
            # cog.check_tokens()  # Optional, if you want to maybe renew the tokens
            # self.cog.verify_tokens()
            # print(self.cog.id_token)
            # print(self.cog.access_token)
            # print(self.cog.refresh_token)
            # print(user)
            print("timezone:", datetime.now().astimezone().tzinfo)
            # now make this window dissappear and bring out the main windows.
            if platform.system() == 'Darwin':
                self.set_or_replace_env_variable_macos("SCECBOTPW", self.scramble(self.textPass.text()))
            else:
                os.environ["SCECBOTPW"] = self.scramble(self.textPass.text())
            data = {"mem_cb": True, "user": self.textName.text(), "pw": "SCECBOTPW", "lan": "EN"}
            if self.mempw_cb.checkState() == Qt.Unchecked:
                data["mem_cb"] = False

            print(data)
            with open(ACCT_FILE, 'w') as jsonfile:
                json.dump(data, jsonfile)
            self.hide()
            print("hello hello hello")

            if self.machine_role == "CommanderOnly" or self.machine_role == "Commander":
                global commanderServer

                self.mainwin = MainWindow(self.tokens, commanderServer, self.ip, self.textName.text(), ecbhomepath, self.gui_net_msg_queue, self.machine_role, self.lang)
                print("Running as a commander...", commanderServer)
                self.mainwin.setOwner(self.textName.text())
                self.mainwin.setCog(self.cog)
                self.mainwin.setCogClient(self.aws_client)
                self.mainwin.show()

            else:
                global commanderXport

                # self.platoonwin = PlatoonMainWindow(self.tokens, self.textName.text(), commanderXport)
                self.mainwin = MainWindow(self.tokens, self.xport, self.ip, self.textName.text(), ecbhomepath, self.gui_net_msg_queue, self.machine_role, self.lang)
                print("Running as a platoon...", self.xport)
                self.mainwin.setOwner(self.textName.text())
                self.mainwin.setCog(self.cog)
                self.mainwin.setCogClient(self.aws_client)
                self.mainwin.show()

        except botocore.errorfactory.ClientError as e:
            # except ClientError as e:
            print("Exception Error:", e)
            msgBox = QMessageBox()
            if "UserNotConfirmedException" in str(e):
                msgBox.setText(QApplication.translate("QMessageBox",
                                                 "User email confirmed is needed.  Try go to your email box and confirm the email first!"))
            elif "NotAuthorizedException" in str(e):
                msgBox.setText(QApplication.translate("QMessageBox", "Password Incorrect!"))
            else:
                msgBox.setText(QApplication.translate("QMessageBox", "Login Error.  Try again..."))

            ret = msgBox.exec()


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

            self.mainwin = MainWindow(self.tokens, self.xport, self.ip, self.textName.text(), ecbhomepath, self.machine_role, self.lang)
            print("faker...")
            self.mainwin.setOwner("Nobody")
            self.mainwin.show()



    def handleSignUp(self):
        print("Signing up...." + self.textName.text() + "...." + self.textPass.text())
        if (self.textPass.text() ==  self.textPass2.text()):
            try:

                response = self.aws_client.sign_up(
                    ClientId=CLIENT_ID,
                    Username=self.textName.text(),
                    Password=self.textPass.text(),
                    UserAttributes=[{"Name": "email", "Value": self.textName.text()}]
                )
                print(response)
                msgBox = QMessageBox()
                msgBox.setText(QApplication.translate("QMessageBox", "Please confirm that you have received the verification email and verified it."))

            except botocore.errorfactory.ClientError as e:
            # except ClientError as e:
                print("Exception Error:", type(e))
                msgBox = QMessageBox()
                if "UsernameExistsException" in str(e):
                    msgBox.setText(QApplication.translate("QMessageBox", "Oops! User already exists.  Try again..."))
                else:
                    msgBox.setText(QApplication.translate("QMessageBox", "Sign up Error.  Try again..."))

            #msgBox.setInformativeText("Do you want to save your changes?")
            #msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            #msgBox.setDefaultButton(QMessageBox.Save)
            ret = msgBox.exec()

            #now back to the standard login screen.
            self.cog.initiate_forgot_password()
            self.confirm_code_label.setVisible(False)
            self.textConfirmCode.setVisible(False)
            self.pw_label.setText(QApplication.translate("QLabel", "Password:"))
            self.login_label.setText(QApplication.translate("QLabel", "Login:"))
            self.signup_label.setVisible(True)
            self.mempw_cb.setVisible(True)
            self.forget_label.setVisible(True)

            self.confirm_pw_label.setVisible(False)
            self.textPass2.setVisible(False)

            self.buttonLogin.setText(QApplication.translate("QPushButton", "Login"))
            self.buttonLogin.clicked.disconnect(self.handleSignUp)
            self.buttonLogin.clicked.connect(self.handleLogin)

        else:
            QMessageBox.warning(
                self, 'Error', 'mismatched password')


    def handleForgotPassword(self):
        print("forgot password...." + self.textName.text())
        if (not self.textName.text() ==  ""):

            self.aws_client.forgot_password(ClientId=CLIENT_ID, Username=self.textName.text())

            self.confirm_code_label.setVisible(True)
            self.textConfirmCode.setVisible(True)

            self.pw_label.setText(QApplication.translate("QLabel", "Set New Password:"))
            self.pw_label.setVisible(True)
            self.textPass.setVisible(True)
            self.user_label.setText(QApplication.translate("QLabel", "Input Email Address:"))
            self.buttonLogin.setText(QApplication.translate("QLabel", "Confirm New Password"))
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
            QMessageBox.warning(
                self, 'Error', 'Invalid Email Address')

    def handleConfirmForgotPassword(self):
        print("forgot password...." + self.textPass.text())

        response = self.aws_client.confirm_forgot_password(ClientId=CLIENT_ID, Username=self.textName.text(), ConfirmationCode=self.textConfirmCode.text(), Password=self.textPass.text())

        self.confirm_code_label.setVisible(False)
        self.textConfirmCode.setVisible(False)
        self.pw_label.setText(QApplication.translate("QLabel", "Password:"))
        self.login_label.setText(QApplication.translate("QLabel", "Login"))
        self.signup_label.setVisible(True)
        self.mempw_cb.setVisible(True)
        self.forget_label.setVisible(True)

        self.buttonLogin.setText(QApplication.translate("QPushButton", "Login"))
        self.buttonLogin.clicked.disconnect(self.handleConfirmForgotPassword)
        self.buttonLogin.clicked.connect(self.handleLogin)

    def renew_access_token(self):
        """
        Sets a new access token on the User using the refresh token.
        """
        auth_params = {'REFRESH_TOKEN': self.refresh_token}
        self._add_secret_hash(auth_params, 'SECRET_HASH')
        refresh_response = self.client.initiate_auth(
            ClientId=self.client_id,
            AuthFlow='REFRESH_TOKEN',
            AuthParameters=auth_params,
        )

        self._set_attributes(
            refresh_response,
            {
                'access_token': refresh_response['AuthenticationResult']['AccessToken'],
                'id_token': refresh_response['AuthenticationResult']['IdToken'],
                'token_type': refresh_response['AuthenticationResult']['TokenType']
            }
        )

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