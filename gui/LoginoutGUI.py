from app_context import AppContext
from utils.logger_helper import logger_helper as logger
from utils.time_util import TimeUtil

print(TimeUtil.formatted_now_with_ms() + " load LoginoutGui start...")
import asyncio
import json
import os
import platform
import time
from datetime import datetime
from os.path import exists
from pycognito import Cognito, AWSSRP
from pycognito.utils import RequestsSrpAuth
import traceback
import base64
import hmac
import hashlib

import boto3
from PySide6.QtCore import QLocale, QTranslator, QCoreApplication, Qt, QEvent, QSettings
from PySide6.QtGui import QPixmap, QFont, QIcon
from PySide6.QtWidgets import QDialog, QLabel, QComboBox, QApplication, QLineEdit, QPushButton, QCheckBox, QHBoxLayout, \
    QVBoxLayout, QMessageBox
import botocore
import locale

from gui.MainGUI import MainWindow
# from gui.BrowserGUI import BrowserWindow

from bot.signio import CLIENT_ID, USER_POOL_ID, CLIENT_SECRET
from config.app_info import app_info
from bot.envi import getECBotDataHome
from bot.network import commanderIP, commanderServer, commanderXport
from utils.fernet import encrypt_password, decrypt_password
from jwt.algorithms import RSAAlgorithm
import requests

from urllib.parse import urlencode
from flask import Flask, request, session, redirect, abort
import jwt
import secrets
from utils.logger_helper import get_traceback


print(TimeUtil.formatted_now_with_ms() + " load LoginoutGui finished...")

# ACCT_FILE =  os.environ.get('ECBOT_HOME') + "/resource/settings/uli.json"
# ecbhomepath = getECBotHome()
ecbhomepath = app_info.app_home_path
ecb_data_homepath = getECBotDataHome()

ACCT_FILE = ecb_data_homepath + "/uli.json"
ROLE_FILE = ecb_data_homepath + "/role.json"
MAX_RETRIES = 5

REGION = "us-east-1"
# USER_POOL_ID = "us-east-1_uUmKJUfB3"
# CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")  # app client enabled for Google
DOMAIN = "https://maipps.auth.us-east-1.amazoncognito.com"
REDIRECT_URI = "http://localhost:5000/auth/callback"  # must match app client
AUTH_URL = f"{DOMAIN}/oauth2/authorize"
TOKEN_URL = f"{DOMAIN}/oauth2/token"
JWKS_URL = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"


class Login(QDialog):
    def __init__(self, parent=None):
        self.cog = None
        self.xport = None
        self.ip = commanderIP
        self.main_win = None
        self.top_gui = None
        self.aws_client = boto3.client('cognito-idp', region_name='us-east-1')
        self.lang = "en"
        self.gui_net_msg_queue = asyncio.Queue()
        self.aws_srp = None
        self.role_list = ["Staff Officer", "Commander", "Commander Only", "Platoon"]
        self.schedule_mode_list = ["manual", "auto"]
        self.schedule_mode = "manual"
        self.mode = "Sign In"
        self.machine_role = "Platoon"
        self.read_role()
        self.current_user = ""
        self.mainLoop = None
        super(Login, self).__init__(parent)
        self.banner = QLabel(self)
        pixmap = QPixmap(ecbhomepath + '/resource/images/icons/ecBot09.png')
        self.banner.setPixmap(pixmap)

        # self.linkFont = QFont('Arial', 8, QFont.Style.StyleItalic)
        self.linkFont = QFont('Arial', 12, italic=True)
        self.linkFont.setUnderline(True)

        self.mem_pw = True
        self.password_shown = False
        self.password_shown2 = False
        self.visibleIcon = QIcon(ecbhomepath + "/resource/images/icons/eye48.png")
        self.hiddenIcon = QIcon(ecbhomepath + "/resource/images/icons/hidden48.png")

        self.win_icon = QIcon(ecbhomepath + "/resource/images/icons/eye48.png")
        self.settings = QSettings("ecbot")

        self.setWindowIcon(self.win_icon)
        self.setWindowTitle('AiPPS My E-Commerce Agents')
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)

        self.__translator = QTranslator()
        self.lan_label = QLabel(QApplication.translate("QLabel", "Lauguage"))
        self.lan_select = QComboBox(self)
        self.lan_select.addItem('English')
        self.lan_select.addItem('中文')
        self.lan_select.currentIndexChanged.connect(self.on_lan_selected)

        self.role_label = QLabel(QApplication.translate("QLabel", "Role"), alignment=Qt.AlignRight)
        self.role_select = QComboBox(self)
        for role in self.role_list:
            self.role_select.addItem(QApplication.translate("QComboBox", role))

        found_role_idx = next((i for i, role in enumerate(self.role_list) if role == self.machine_role), -1)
        if found_role_idx > 0:
            self.role_select.setCurrentIndex(found_role_idx)
        else:
            self.role_select.setCurrentIndex(1)         #commander will be set if file based machine role is unknown
        self.role_select.currentIndexChanged.connect(self.on_role_selected)

        self.schedule_mode_label = QLabel(QApplication.translate("QLabel", "Schedule Mode"), alignment=Qt.AlignLeft)
        self.schedule_mode_select = QComboBox(self)
        for schedule_mode in self.schedule_mode_list:
            self.schedule_mode_select.addItem(QApplication.translate("QComboBox", schedule_mode))

        found_schedule_mode_idx = next((i for i, smode in enumerate(self.schedule_mode_list) if smode == self.schedule_mode), -1)
        if found_schedule_mode_idx > 0:
            self.schedule_mode_select.setCurrentIndex(found_schedule_mode_idx)
        else:
            self.schedule_mode_select.setCurrentIndex(1)         #commander will be set if file based machine role is unknown
        self.schedule_mode_select.currentIndexChanged.connect(self.on_schedule_mode_selected)


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

        self.confirm_code_label = QLabel(
            QApplication.translate("QLabel", "Input Confirmation Code Retrieved From Your Email:"))
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

        # self.buttonLogin.clicked.connect(self.handleLogin)
        self.buttonLogin.clicked.connect(self.fakeLogin)

        self.forget_label = QLabel(QApplication.translate("QLabel", "Forgot Password?"))
        self.forget_label.setFont(self.linkFont)
        self.forget_label.setAlignment(Qt.AlignRight)
        self.forget_label.setStyleSheet("color: #409eff;")
        self.forget_label.mouseReleaseEvent = self.on_forgot_password

        self.signup_label = QLabel(QApplication.translate("QLabel", "No account? Sign Up Here!"))
        self.signup_label.setFont(self.linkFont)
        self.signup_label.setAlignment(Qt.AlignRight)
        self.signup_label.mouseReleaseEvent = self.on_sign_up
        # now try to read the default acct file. if it doesn't exist or not having valid content, then move on,
        # otherwise, load the account info.
        self.pwd_key = "encrypted_password"
        if exists(ACCT_FILE):
            with open(ACCT_FILE, 'r') as file:
                data = json.load(file)
                print("acct data:", data, ACCT_FILE)
                self.show_visibility = data["mem_cb"]
                self.textName.setText(data["user"])
                if "schedule_mode" in data:
                    self.schedule_mode = data["schedule_mode"]
                if self.show_visibility:
                    stored_encrypted_password = bytes.fromhex(self.settings.value(self.pwd_key, ""))
                    if stored_encrypted_password is not None and len(stored_encrypted_password) > 0:
                        decrypted_password = decrypt_password(stored_encrypted_password)
                        self.textPass.setText(decrypted_password)
                    else:
                        self.textPass.setText("")
                else:
                    self.textPass.setText("")
                self.lan = data["lan"]
        else:
            logger.info(f"acct file {ACCT_FILE} is not existed!")
            self.show_visibility = True  # default
            localLan = self.get_locale()
            print(localLan)
            if 'en_' in localLan[0]:
                self.lan = "EN"
            else:
                self.lan = "ZH"

        self.mempw_cb = QCheckBox(QApplication.translate("QCheckBox", "Memorize Password"))
        if self.show_visibility:
            self.mempw_cb.setCheckState(Qt.Checked)
        else:
            self.mempw_cb.setCheckState(Qt.Unchecked)

        self.mempw_cb.stateChanged.connect(self.checkState)
        self.mempw_cb.setFont(self.linkFont)
        self.mempw_cb.setStyleSheet("color: #409eff;")

        print(self.mempw_cb.checkState())

        # self.signup_label.setStyleSheet("color: blue; background-color: yellow")
        self.signup_label.setStyleSheet("color: #409eff;")

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

        self.headline_layout = QHBoxLayout(self)
        self.headline_layout.addWidget(self.lan_label)
        self.headline_layout.addWidget(self.lan_select)
        self.headline_layout.addWidget(self.role_label)
        self.headline_layout.addWidget(self.role_select)

        self.headline2_layout = QHBoxLayout(self)
        self.headline2_layout.setSpacing(0)
        self.headline2_layout.setAlignment(self.schedule_mode_select, Qt.AlignLeft)
        self.headline2_layout.addWidget(self.schedule_mode_label)
        self.headline2_layout.addWidget(self.schedule_mode_select)


        log_layout.addLayout(self.headline_layout)
        log_layout.addLayout(self.headline2_layout)
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
        self.signed_in = False

    # async def launchLAN(self):
    def checkState(self, state):
        # 判断复选框的状态
        if state == Qt.Checked.value:
            self.show_visibility = True
        else:
            self.show_visibility = False

    def setTopGUI(self, web_gui):
        self.top_gui = web_gui

    def get_gui_msg_queue(self):
        return self.gui_net_msg_queue

    def set_xport(self, xport):
        self.xport = xport
        if self.main_win:
            self.main_win.setCommanderXPort(xport)

    def set_ip(self, ip):
        self.ip = ip

    def set_wan_connected(self, wan_status):
        self.main_win.set_wan_connected(wan_status)

    def read_role(self):
        self.machine_role = "Platoon"
        print("ROLE FILE: " + ROLE_FILE)
        if exists(ROLE_FILE):
            with open(ROLE_FILE, 'r') as file:
                mr_data = json.load(file)
                self.machine_role = mr_data["machine_role"]
                print("role file contents:", mr_data)
        else:
            logger.info(f"role file {ROLE_FILE} is not existed!")

    def get_role(self):
        # is function is for testing purpose only
        return self.machine_role

    def set_role(self, role):
        # is function is for testing purpose only
        self.machine_role = role
        
        # set role_select to the item that matches role here.
        found_role_idx = self.role_select.findText(role)
        if found_role_idx != -1:
            self.role_select.setCurrentIndex(found_role_idx)
        else:
            print(f"Role '{role}' not found in role_select combobox.")


    def isCommander(self):
        if self.machine_role == "Commander" or self.machine_role == "Commander Only":
            return True
        else:
            return False

    def get_locale(self):
        try:
            # 设置区域设置为系统默认设置
            locale.setlocale(locale.LC_ALL, '')
            current_locale = locale.getlocale()
            if current_locale[0] is None:
                raise ValueError("Locale not set properly")
            return current_locale
        except Exception as e:
            print(f"Error getting locale: {e}")
            return 'en_US', 'UTF-8'

    def __setup_language(self):
        system_locale, _ = self.get_locale()
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

            # self.__app.installTranslator(self.__translator)
            _app = QCoreApplication.instance()
            _app.installTranslator(self.__translator)
            # QCoreApplication.installTranslator(self.__translator)
            print("chinese translator loaded")
        else:
            self.lang = "en"
            _app = QApplication.instance()
            _app.removeTranslator(self.__translator)

    def on_role_selected(self, index):
        print("Index changed", index)
        self.machine_role = self.role_select.currentText()
        print("new role selected: "+self.machine_role)


    def on_schedule_mode_selected(self, index):
        print("Index changed", index)
        self.schedule_mode = self.schedule_mode_select.currentText()
        print("new schedule mode selected: "+self.schedule_mode)


    def changeEvent(self, event):
        # print("event occured....", event.type())
        if event.type() == QEvent.LanguageChange:
            print("re-translating....")
            self.retranslateUi()
        # super(Login, self).changeEvent(event)

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

            print(
                f"Environment variable {var_name} {'updated' if variable_updated else 'set'} successfully in {config_file}.")
        except IOError as e:
            print(f"Error: Unable to open or write to {config_file} - {e}")

    def setLoop(self, loop):
        self.mainLoop = loop

    def getCurrentUser(self):
        return self.current_user

    def getLogUser(self):
        # print("current user:", self.current_user)
        return self.current_user.split("@")[0] + "_" + self.current_user.split("@")[1].replace(".", "_")

    def decode_jwt(self, token):
        """Decodes a JWT and returns the payload as a dictionary."""
        # Split the token and take the payload part (second part of the JWT)
        payload_part = token.split('.')[1]
        # JWT uses base64url encoding, which requires proper padding
        padding = '=' * (4 - len(payload_part) % 4)
        # Decode the payload
        decoded_bytes = base64.urlsafe_b64decode(payload_part + padding)
        # Convert the decoded bytes into a dictionary
        payload = json.loads(decoded_bytes.decode('utf-8'))
        return payload

    def get_secret_hash(self, username):
        """
        Generate a secret hash using the username, client ID, and client secret.
        """
        message = username + CLIENT_ID
        dig = hmac.new(CLIENT_SECRET.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
        secret_hash = base64.b64encode(dig).decode()
        return secret_hash

    def getSignedIn(self):
        return self.signed_in

    def authenticate_with_backoff(self, inAwsSRP, max_retries=MAX_RETRIES):
        """改进的 AWS 认证重试机制，包含超时处理"""
        for attempt in range(max_retries):
            try:
                logger.info(f"AWS authentication attempt {attempt + 1}/{max_retries}")
                
                # 设置更长的超时时间
                import boto3
                from botocore.config import Config
                
                # 创建带有超时配置的客户端
                config = Config(
                    connect_timeout=60,  # 连接超时60秒
                    read_timeout=60,    # 读取超时60秒
                    retries={'max_attempts': 3}
                )
                
                # 如果 inAwsSRP 有 client 属性，更新其配置
                if hasattr(inAwsSRP, 'client') and inAwsSRP.client:
                    inAwsSRP.client.config = config
                
                return inAwsSRP.authenticate_user()
                
            except botocore.exceptions.ClientError as e:
                error_code = e.response['Error']['Code']
                logger.warning(f"AWS authentication error (attempt {attempt + 1}): {error_code}")
                
                if error_code == 'TooManyRequestsException':
                    wait_time = min(2 ** attempt, 30)  # 最大等待30秒
                    logger.info(f"Too many requests, retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                elif error_code == 'NetworkError':
                    wait_time = min(2 ** attempt, 15)  # 网络错误等待时间
                    logger.info(f"Network error, retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Unrecoverable AWS error: {error_code}")
                    raise e
                    
            except Exception as e:
                logger.error(f"Unexpected error during authentication (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise e
                wait_time = min(2 ** attempt, 10)
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        
        raise Exception(f"Max retries ({max_retries}) exceeded for AWS authentication")

    def _check_network_connection(self):
        """检查网络连接状态"""
        try:
            import socket
            import requests
            
            # 检查基本网络连接
            socket.create_connection(("8.8.8.8", 53), timeout=10)
            
            # 检查 AWS 服务可用性
            try:
                response = requests.get("https://cognito-idp.us-east-1.amazonaws.com", timeout=10)
                return response.status_code < 500  # 只要不是服务器错误就认为可用
            except:
                # 如果 AWS 检查失败，至少基本网络是通的
                return True
                
        except Exception as e:
            logger.warning(f"Network connection check failed: {e}")
            return False

    def handleGetLastLogin(self):
        return {"machine_role": self.machine_role, "username": self.textName.text(), "password": self.textPass.text()}


    def handleLogin(self, uname="", pw="", mrole = ""):
        logger.info("logging in....", self.textPass.text())
        
        # 首先检查网络连接
        if not self._check_network_connection():
            logger.error("Network connection check failed")
            return "NetworkError"
        
        # global commanderServer
        # global commanderXport

        try:
            # self.aws_srp = AWSSRP(username=self.textName.text(), password=self.textPass.text(), pool_id=USER_POOL_ID,
            #                       client_id=CLIENT_ID, client_secret=CLIENT_SECRET, client=self.aws_client)
            if not uname:
                uname = self.textName.text()
            else:
                self.textName.setText(uname)
            if not pw:
                pw = self.textPass.text()
            else:
                self.textPass.setText(pw)
                
            self.aws_srp = AWSSRP(username=uname, password=pw, pool_id=USER_POOL_ID,
                                  client_id=CLIENT_ID, client=self.aws_client)

            if mrole is not None:
                self.machine_role = mrole

            # self.tokens = self.aws_srp.authenticate_user()

            self.tokens = self.authenticate_with_backoff(self.aws_srp)

            # print("token: ", self.tokens)
            # Decode the ID Token to extract user information
            self.id_token = self.tokens['AuthenticationResult']['IdToken']
            self.old_access_token = self.tokens["AuthenticationResult"]["AccessToken"]
            refresh_token = self.tokens["AuthenticationResult"]["RefreshToken"]
            decoded_id_token = self.decode_jwt(self.id_token)

            # Extract the Cognito User ID (sub claim)
            self.cognito_user_id = decoded_id_token.get('sub')

            DecodedUsername = decoded_id_token["cognito:username"]
            print("DecodeUserName:", DecodedUsername, decoded_id_token)

            # cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com", botocore_config=Config(signature_version=UNSIGNED))
            # cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com")
            # self.cog = Cognito(USER_POOL_ID, CLIENT_ID, username=self.textName.text(),
            #                    access_token=self.tokens["AuthenticationResult"]["AccessToken"],
            #                    refresh_token=self.tokens["AuthenticationResult"]["RefreshToken"],
            #                    access_key='AKIAIOSFODNN7EXAMPLE', secret_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY')

            # self.cog = Cognito(USER_POOL_ID, CLIENT_ID,  client_secret=CLIENT_SECRET, username=self.cognito_user_id, refresh_token=refresh_token)
            self.cog = Cognito(USER_POOL_ID, CLIENT_ID,  username=self.cognito_user_id, refresh_token=refresh_token)
            # print("cog access token:", self.cog.access_token)
            # self.cog.check_tokens()
            # response = self.cog.authenticate(password=self.textPass.text())
            # time.sleep(1)
            # user = self.cog.get_user()
            # time.sleep(1)
            # cog.check_tokens()  # Optional, if you want to maybe renew the tokens
            # self.cog.verify_tokens()
            # print(self.cog.id_token)
            # print(self.cog.access_token)
            refresh_token = self.cog.refresh_token

            # print(user)
            print("timezone:", datetime.now().astimezone().tzinfo)
            # now make this window dissappear and bring out the main windows.
            if platform.system() == 'Darwin':
                self.set_or_replace_env_variable_macos("SCECBOTPW", self.scramble(self.textPass.text()))
            else:
                os.environ["SCECBOTPW"] = self.scramble(self.textPass.text())
            data = {"mem_cb": self.show_visibility, "user": self.textName.text(), "pw": "SCECBOTPW", "lan": "EN"}
            if self.mempw_cb.checkState() == Qt.Unchecked:
                data["mem_cb"] = False
                if self.settings.contains(self.pwd_key):
                    self.settings.remove(self.pwd_key)
            else:
                encrypted_password = encrypt_password(self.textPass.text())
                self.settings.setValue(self.pwd_key, encrypted_password.hex())

            with open(ACCT_FILE, 'w') as jsonfile:
                json.dump(data, jsonfile)
            self.hide()
            logger.info("hello hello hello")
            main_key = self.scramble(self.textPass.text())
            self.current_user = self.textName.text()
            self.current_user_pw = self.textPass.text()
            self.signed_in = True


            if self.machine_role == "Commander Only" or self.machine_role == "Commander":
                # global commanderServer

                self.main_win = MainWindow(self, main_key, self.tokens, self.mainLoop, self.ip,
                                           self.textName.text(), ecbhomepath,
                                           self.gui_net_msg_queue, self.machine_role, self.schedule_mode, self.lang)
                # self.new_main_win = BrowserWindow()
                # gui_port = 4000
                # new_gui_url = f"http://localhost:{gui_port}"
                # self.new_main_win.loadURL(new_gui_url)
                # self.new_main_win.show()        #coment this out if using old GUI

                logger.info("Running as a commander...", commanderServer)
                self.main_win.setOwner(self.textName.text())
                self.main_win.setCog(self.cog)
                self.main_win.setCogClient(self.aws_client)
                self.main_win.set_top_gui(self.top_gui)
                # self.main_win.show()            #comment this out if using new GUI
            else:
                # global commanderXport
                # self.platoonwin = PlatoonMainWindow(self.tokens, self.textName.text(), commanderXport)
                self.main_win = MainWindow(self, main_key, self.tokens, self.mainLoop, self.ip,
                                           self.textName.text(), ecbhomepath,
                                           self.gui_net_msg_queue, self.machine_role, self.schedule_mode, self.lang)
                logger.info("Running as a platoon...", self.xport)
                self.main_win.setOwner(self.textName.text())
                self.main_win.setCog(self.cog)
                self.main_win.setCogClient(self.aws_client)
                self.main_win.set_top_gui(self.top_gui)
                # self.main_win.show()
                # no-op here; defer LightRAG start after common init

            # 统一在主窗体就绪后异步启动 LightRAG（非阻塞）
            self._start_lightrag_deferred()

            app_ctx = AppContext()
            app_ctx.set_main_window(self.main_win)

            # print("refrsh tokeN:", refresh_token)
            asyncio.create_task(self.refresh_tokens_periodically(refresh_token))
            # self.refresh_tokens_periodically(refresh_token, CLIENT_ID, self.aws_client, self.cognito_user_id)
            return "Successful"
        # except botocore.errorfactory.ClientError as e:
        except Exception as e:
            # except ClientError as e:
            ex_stat = f"Error in handleLogin: {traceback.format_exc()} {str(e)}"
            logger.error("Exception Error:", ex_stat)
            msgBox = QMessageBox()
            if "UserNotConfirmedException" in str(e):
                msgBox.setText(QApplication.translate("QMessageBox",
                                                      "User email confirmed is needed.  Try go to your email box and confirm the email first!"))
            elif "NotAuthorizedException" in str(e):
                msgBox.setText(QApplication.translate("QMessageBox", "Password Incorrect!"))
            else:
                msgBox.setText(QApplication.translate("QMessageBox", "Login Error.  Try again..."))

            ret = msgBox.exec()
            return str(e)
        except Exception as e:
            ex_stat = f"Error in handleLogin: {traceback.format_exc()} {str(e)}"

            logger.error("Exception Error:", ex_stat)
            return str(e)

    async def refresh_tokens_periodically(self, refresh_token, interval=2700):
        """Refresh tokens periodically using the refresh token (async version)"""

        while True:
            await asyncio.sleep(interval)  # Wait for 55 minutes (3300 seconds)

            secret_hash = self.get_secret_hash(self.cognito_user_id)

            try:
                response = self.aws_client.initiate_auth(
                    ClientId=CLIENT_ID,
                    AuthFlow='REFRESH_TOKEN_AUTH',
                    AuthParameters={
                        'REFRESH_TOKEN': refresh_token
                        # 'REFRESH_TOKEN': refresh_token,
                        # "USERNAME": self.cognito_user_id,
                        # "SECRET_HASH": secret_hash
                    }
                )

                # self.cog.renew_access_token()
                # print("refresh response:", response)
                # Get the new tokens
                if 'AuthenticationResult' in response:
                    self.tokens["AuthenticationResult"]["IdToken"] = response['AuthenticationResult']['IdToken']
                    self.tokens["AuthenticationResult"]["AccessToken"] = response['AuthenticationResult']['AccessToken']
                else:
                    raise Exception("AuthenticationResult not found in the response")

                if self.main_win:
                    self.main_win.updateTokens(self.tokens)

                # Use the new tokens for your logic
                # For example, update the headers in your requests with the new access token
            except Exception as e:
                # Get the traceback information
                traceback_info = traceback.extract_tb(e.__traceback__)
                # Extract the file name and line number from the last entry in the traceback
                if traceback_info:
                    ex_stat = "ErrorPeriodicRefreshingToken:" + traceback.format_exc() + " " + str(e)
                else:
                    ex_stat = "ErrorPeriodicRefreshingToken: traceback information not available:" + str(e)
                print(ex_stat)

    def getCurrentUser(self):
        return self.current_user

    def fakeLogin(self):
        print("logging in....")
        # cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com", botocore_config=Config(signature_version=UNSIGNED))
        # cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com")
        # self.cog = Cognito(USER_POOL_ID, CLIENT_ID, username=self.textName.text(),
        #                   access_key='AKIAIOSFODNN7EXAMPLE', secret_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY')
        # self.aws_client = boto3.client('cognito-idp', region_name='us-east-1')
        # self.aws_srp = AWSSRP(username=self.textName.text(), password=self.textPass.text(), pool_id=USER_POOL_ID,
        #                      client_id=CLIENT_ID, client=self.aws_client)
        # self.tokens = self.aws_srp.authenticate_user()
        self.tokens = {'ChallengeParameters': {}, 'AuthenticationResult': {
            'AccessToken': 'eyJraWQiOiJSd1J3MUV2bEowdzFMNm04QmVxWktTdjE5aGViN2didGtJalU2Ylh0XC9uWT0iLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJkYmNhYmVhMy0xZmNiLTQ2MWItYWJlOS1kZjU0NzIzZGI1ODIiLCJkZXZpY2Vfa2V5IjoidXMtZWFzdC0xXzhhZmUwOGFhLTMzZWMtNDY5OS05YWViLWY5YThhMzgwMjIwNSIsImlzcyI6Imh0dHBzOlwvXC9jb2duaXRvLWlkcC51cy1lYXN0LTEuYW1hem9uYXdzLmNvbVwvdXMtZWFzdC0xX3VVbUtKVWZCMyIsImNsaWVudF9pZCI6IjU0MDByOHE1cDlnZmRobG4yZmVxY3BsanNoIiwib3JpZ2luX2p0aSI6IjU4YzhhNGZjLTBiZTEtNDNkNS1iNDlhLTI5ZTM5MDBhMzZhZSIsImV2ZW50X2lkIjoiMGNlZTIwZjgtYzhkNy00ZDRkLWJhODAtOGExNjAyZGExMzBiIiwidG9rZW5fdXNlIjoiYWNjZXNzIiwic2NvcGUiOiJhd3MuY29nbml0by5zaWduaW4udXNlci5hZG1pbiIsImF1dGhfdGltZSI6MTY1ODEyNTU4MywiZXhwIjoxNjU4MTI5MTgzLCJpYXQiOjE2NTgxMjU1ODMsImp0aSI6ImMwZGYwYzY2LWIxYTUtNDQ3ZC1hZTcwLTg0Y2I2MjM3MmIxMyIsInVzZXJuYW1lIjoiZGJjYWJlYTMtMWZjYi00NjFiLWFiZTktZGY1NDcyM2RiNTgyIn0.MGbBld8XVSqoBSSJTxi6ptX4VJesmfaDmJwRoS480Fk2qrAGtskkzUkY133hj3iM8AscwpjS2rr1khBuvjbwPvK2T4Erf0eIsLhViEzE5RWShIHRdDV2FHXS9FpvP_T1jrRBZUcE5mbyHB1ZzCzGhNTLSb_3mqix_oRuKxHrkorqhLbPu_3rv9IJLHfWgZatLvMEjTn33uTSuzJ8MZGyUu0MQJ5FmKwrI4I0yX9jqIjq26xNNUyyw4LNkIwT9FD04mwB-4GtP_zfSYjK4OYumAHS-g6We_Z5guHBZmpSuPmEBPhtFkLusJMOHjuR8JHSrG52pK60YAZvNbL5zpyP7A',
            'ExpiresIn': 3600, 'TokenType': 'Bearer',
            'RefreshToken': 'eyJjdHkiOiJKV1QiLCJlbmMiOiJBMjU2R0NNIiwiYWxnIjoiUlNBLU9BRVAifQ.Ooz_MgLzRFVbewNH4_m7A3HKEWBOIrVNmUzrXd1msMhQoDyIMlq3hOJN5WipYUeJ_LceDp37be--Ot0QI4wQLGH-FnXEVhqY6WxYoAVJmOckfhO5tutPFo4o3nElQn3bUhPpGsW7A3Hz_KhsgNVTn6fhCEkt6aL_BYgTdLz9VWX1nbdGxjWv8W2QNtX34CAmIf-pga6MYb0EsqeDbk_-nfBOPOXpgK5qx-Zf5FTYk7zOPctXgZuqmmGbnbkw3chjaWRnJOEEIEpECHRUWSUNC2_K6Die-iWhmEsTxijnidGu6lmtvlAwGSx_uZdj6stUfOgQ9ucwAY-JlG_08WzMtg.KJBsKK42_IeYPVZt.kj4xRX9BCz8He30cN3lEdtgBQHlF16DDdH6hjZglt22kYObD60-GNIRc8Ncm8TP8am0HVKMV3BEk3_epSMiJ0fAPqevR_UjNmFPRZmriU9lA5I1ygJWKaoHKhkIE0QWzjNJQl6hy0gX1rMqXBdOeVwOTIn-aywyknyGO-zbmQmh6V9w9OImRKn-fdjy19mJ9xd1BwGVfOzh95v8uZamZyR6q2ZInReJrYlCJukKsuuWV9rCt_dpanmzTZ3zsrroF6TioQhEbJcpSQsfi_CIFpVWS8z0PShlW7vZ4B2EMwbJRPLwmJXKyP2LZvn2z4cdgktSR6txdPw8RwKSAH-unhB2evzDsLNJ5U3DGfmHg7s6VZQCfMQwQf1HkldwYvdHyXyJ4gNc9x6Xx__lgLc1wTuE1VDs5CDtJQB0b4NJ1REbSobBE_dK_Fzx_1ap7PT5Dxhxzt1jid0ujZQ4wNHjSZlVQK76HIBk_Jwh_ywj6KQI5IEO2PmwOIaPov_Kp_10EFHvYhSvrKGlan1K7h-04LjHCeHugxWzyFSnYyCo0Bq4nGQU5swhdmqJMcMP7p3AecgCAj1kgTvIBrLG-Vn9dJPyJgtm4AUKcMsZfrd3MZsuFWSiwKuN8M7f4f-bt2sRmGNRgemzXtCwM8xYpiRtr_c_GrmUUH5RJAuNCkr_dcT7H8VziJCyllCLBwN72MGpQ0LT2_oD4P1RSk0gjCqUW7OpSv8hlmf9ZSwYLmUeiVaRZ-PoPVW2QYGhNX83dkAel5Ke7nqIhTrXbibF2ZTdG1YFkc6yZyoGeVyW-uYbtAFZ_EV_Acomq7S_gVW68ppxUID1btoAusFQIIwCTAE_vWIxxf1whzuA_coIQJDjzhlBi8WZBz5xr9HSiBIo8m4XnHaudxmPZkv0b-T03d663zczuiixNJXNWKoqgu1hhxUZ3LxTWSN0hihvtdF-CMecF7qYvAPhJ60u6SQwdQiohM1GGEzCWHPIFTJNoEiFIb76RQjmXNnJJU6u_eVqWJmHrcJwxp6Fd6s3t1svUQewip8IiOLpkz4eCTP1kD4ASX-f6i0cflqtfDoJMEG_8qFG7Fd30-wvhxKLYvMXRz9GTURszOBVSFewukqksuXV6vFB8ymCQOAKJsQbKrfSZzdCok5oqZxcPWpT6bkMeF4wV9pnA-ydxRQEDMIsOgPPDixvdpmvVg2FKiPNZVlKGipEUpB20fELjIIqN4tmU1XB9brRDOuawhdaKoHDHDC7HCp_-v0_B-iUsMO_GqgSoGuEZy3ghSI8SiV0YoOJu5n5lISmG6R1nYhcrPewpyCN9MYUmWCaaa1-oZazJqzBSpAwO30ItleZRkKCgzEzak7soHsmvzD19CCjZWXqS77_Aib7huWcqOA7viXDJJ0xdTKMGd9LcsiHwVkCrRV6QJcBVZaNSRZ-lS3UU7v14uprz.cljsuZCktkNGeEdSZxWhPw',
            'IdToken': 'eyJraWQiOiJQcHRQaVNMMVVha3NkVHYxRjMwdTdFYVBtT1UySXRwekhLMjNIb3Erd0FRPSIsImFsZyI6IlJTMjU2In0.eyJzdWIiOiJkYmNhYmVhMy0xZmNiLTQ2MWItYWJlOS1kZjU0NzIzZGI1ODIiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiaXNzIjoiaHR0cHM6XC9cL2NvZ25pdG8taWRwLnVzLWVhc3QtMS5hbWF6b25hd3MuY29tXC91cy1lYXN0LTFfdVVtS0pVZkIzIiwiY29nbml0bzp1c2VybmFtZSI6ImRiY2FiZWEzLTFmY2ItNDYxYi1hYmU5LWRmNTQ3MjNkYjU4MiIsIm9yaWdpbl9qdGkiOiI1OGM4YTRmYy0wYmUxLTQzZDUtYjQ5YS0yOWUzOTAwYTM2YWUiLCJhdWQiOiI1NDAwcjhxNXA5Z2ZkaGxuMmZlcWNwbGpzaCIsImV2ZW50X2lkIjoiMGNlZTIwZjgtYzhkNy00ZDRkLWJhODAtOGExNjAyZGExMzBiIiwidG9rZW5fdXNlIjoiaWQiLCJhdXRoX3RpbWUiOjE2NTgxMjU1ODMsImV4cCI6MTY1ODEyOTE4MywiaWF0IjoxNjU4MTI1NTgzLCJqdGkiOiI5YmU4MjU3MC01MWRhLTQ0NjQtOGQ2Ny1lZTkyZWRmNDYyMzgiLCJlbWFpbCI6InNvbmdjQHlhaG9vLmNvbSJ9.Xcw8TgDYdxHY_6OMfzFby3UMkrc6s0QGPTeCKALrQ1fNqMgnfOUPME94NW8aAz1jkkUX87buv4imYH37Sdv4NL8UX5YMZEXU22bbGncmMZCFAyUDbBQ6YMRX-WUlbbRBUcom0YzaHLrYN8QJygVYcnVYT2YzDUxS-L_bA71FRqoylDJe5oly9QmPmBDP08Fkp_IcMS_mSJ9CErSJpEJEezzudKRmVvof_YUdg6kEBGXGCQB_lOkXdUPE4sWP8ZpKCCkLa-VOLOTXp1Le9LOw5Ru38ofAL02DmXsoRkAMYl_YrU-I90HXNB4brnBZpNZ497TpiypbmJpYHeVCr8mAqg',
            'NewDeviceMetadata': {'DeviceKey': 'us-east-1_8afe08aa-33ec-4699-9aeb-f9a8a3802205',
                                  'DeviceGroupKey': '-iY8sjxdl'}},
                       'ResponseMetadata': {'RequestId': '0cee20f8-c8d7-4d4d-ba80-8a1602da130b', 'HTTPStatusCode': 200,
                                            'HTTPHeaders': {'date': 'Mon, 18 Jul 2022 06:26:23 GMT',
                                                            'content-type': 'application/x-amz-json-1.1',
                                                            'content-length': '4377', 'connection': 'keep-alive',
                                                            'x-amzn-requestid': '0cee20f8-c8d7-4d4d-ba80-8a1602da130b'},
                                            'RetryAttempts': 0}}

        print(self.tokens)
        main_key = ""
        self.current_user = self.textName.text()
        self.current_user_pw = self.textPass.text()
        print("faking...", main_key, self.tokens, self.ip, self.textName, ecbhomepath, self.machine_role, self.schedule_mode, self.lang)
        self.main_win = MainWindow(self, main_key, self.tokens, self.mainLoop, self.ip,
                                   self.textName.text(),  ecbhomepath,
                                   self.gui_net_msg_queue, self.machine_role, self.schedule_mode, self.lang)

        print("faker...")
        self.main_win.setOwner("Nobody")
        self.main_win.set_top_gui(self.top_gui)
        self.main_win.show()

        # using new GUI
        # self.new_main_win = BrowserWindow()
        # gui_port = 4000
        # new_gui_url = f"http://localhost:{gui_port}"
        # self.new_main_win.loadURL(new_gui_url)
        # self.new_main_win.show()

    def handleLogout(self):
        self.cog.logout()
        self.main_win.stop_lightrag_server()
        return True

    def get_mainwin(self):
        return self.main_win

    def _start_lightrag_deferred(self):
        """统一的 LightRAG 延迟启动（非阻塞，不影响登录流程）"""
        try:
            from knowledge.lightrag_server import LightragServer
            if self.main_win is None:
                return
            self.main_win.lightrag_server = LightragServer(extra_env={"APP_DATA_PATH": ecb_data_homepath + "/lightrag_data"})
            self.main_win.lightrag_server.start(wait_ready=False)
            logger.info("LightRAG server started (deferred, non-blocking)")
        except Exception as _e:
            logger.warning(f"Deferred LightRAG start failed: {_e}")

    def handleSignUp(self, uname="", pw=""):
        print("Signing up...." + uname + "...." + pw)
        # if (self.textPass.text() == self.textPass2.text()):
        try:
            # if not uname:
            #     uname = self.textName.text()

            # if not pw:
            #     pw = self.textPass.text()

            response = self.aws_client.sign_up(
                ClientId=CLIENT_ID,
                Username=uname,
                Password=pw,
                UserAttributes=[{"Name": "email", "Value": uname}]
            )
            print(response)
            return True, "Please confirm that you have received the verification email and verified it."
            # msgBox = QMessageBox()
            # msgBox.setText(QApplication.translate("QMessageBox",
                                                #   "Please confirm that you have received the verification email and verified it."))

        # except botocore.errorfactory.ClientError as e:
        except Exception as e:
            # except ClientError as e:
            ex_stat = f"Error in handleLogin: {traceback.format_exc()} {str(e)}"

            print("Exception Error:", ex_stat)
            # msgBox = QMessageBox()

            if "UsernameExistsException" in str(e):
                # msgBox.setText(QApplication.translate("QMessageBox", "Oops! User already exists.  Try again..."))
                message = "Oops! User already exists.  Try again..."
            else:
                # msgBox.setText(QApplication.translate("QMessageBox", "Sign up Error.  Try again..."))
                message = "Sign up Error.  Try again..."

            return False, message

            # msgBox.setInformativeText("Do you want to save your changes?")
            # msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            # msgBox.setDefaultButton(QMessageBox.Save)
            # ret = msgBox.exec()

            # # now back to the standard login screen.
            # self.cog.initiate_forgot_password()
            # self.confirm_code_label.setVisible(False)
            # self.textConfirmCode.setVisible(False)
            # self.pw_label.setText(QApplication.translate("QLabel", "Password:"))
            # self.login_label.setText(QApplication.translate("QLabel", "Login:"))
            # self.signup_label.setVisible(True)
            # self.mempw_cb.setVisible(True)
            # self.forget_label.setVisible(True)

            # self.confirm_pw_label.setVisible(False)
            # self.textPass2.setVisible(False)

            # self.buttonLogin.setText(QApplication.translate("QPushButton", "Login"))
            # self.buttonLogin.clicked.disconnect(self.handleSignUp)
            # self.buttonLogin.clicked.connect(self.handleLogin)

        # else:
        #     QMessageBox.warning(
        #         self, 'Error', 'mismatched password')

    def handleForgotPassword(self, username):
        print("forgot password...." + username)
        # if (not self.textName.text() == ""):

        try:
            self.aws_client.forgot_password(ClientId=CLIENT_ID, Username=username)

            return True
            # self.confirm_code_label.setVisible(True)
            # self.textConfirmCode.setVisible(True)

            # self.pw_label.setText(QApplication.translate("QLabel", "Set New Password:"))
            # self.pw_label.setVisible(True)
            # self.textPass.setVisible(True)
            # self.user_label.setText(QApplication.translate("QLabel", "Input Email Address:"))
            # self.buttonLogin.setText(QApplication.translate("QLabel", "Confirm New Password"))
            # self.buttonLogin.clicked.disconnect(self.handleForgotPassword)
            # self.buttonLogin.clicked.connect(self.handleConfirmForgotPassword)

            # cog.admin_reset_password(self.textName.text())   # this API can only be called by administrator

            # response = auth_client.sign_up(
            #     ClientId=CLIENT_ID,
            #     Username="songc@yahoo.com",
            #     Password="Sc12345!",
            #     UserAttributes=[{"Name": "email", "Value": "songc@yahoo.com"}],
            # )
            # print(response)
        except Exception as e:
            ex_stat = f"Error in handle forgot password: {traceback.format_exc()} {str(e)}"

            print("Exception Error:", ex_stat)
            return False, "Error in Handle forgot password"

        # else:
        #     QMessageBox.warning(
        #         self, 'Error', 'Invalid Email Address')

    def handleConfirmForgotPassword(self, username, confirm_code, new_password):
        print("confirm forgot password...." + username)

        response = self.aws_client.confirm_forgot_password(ClientId=CLIENT_ID, Username=username,
                                                           ConfirmationCode=confirm_code,
                                                           Password=new_password)
        return True
        # self.confirm_code_label.setVisible(False)
        # self.textConfirmCode.setVisible(False)
        # self.pw_label.setText(QApplication.translate("QLabel", "Password:"))
        # self.login_label.setText(QApplication.translate("QLabel", "Login"))
        # self.signup_label.setVisible(True)
        # self.mempw_cb.setVisible(True)
        # self.forget_label.setVisible(True)

        # self.buttonLogin.setText(QApplication.translate("QPushButton", "Login"))
        # self.buttonLogin.clicked.disconnect(self.handleConfirmForgotPassword)
        # self.buttonLogin.clicked.connect(self.handleLogin)

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
            asc = ord(word[i]) - (i + 1)
            if asc < min:
                asc = max - (min - asc) + 1
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


    def b64u(self,b: bytes) -> str:
        return base64.urlsafe_b64encode(b).decode().rstrip("=")


    # User           React + TSX (GUI)         Python Backend (Flask/FastAPI)         Cognito Hosted UI         Google
    #  |                     |                              |                              |                      |
    #  |--- Click "Login" -->|                              |                              |                      |
    #  |                     |--- Call /login/google -----> |                              |                      |
    #  |                     |                              |-- login_google() ------------|                      |
    #  |                     |                              |   builds PKCE, state         |                      |
    #  |                     |                              |   redirect → /authorize      |                      |
    #  |                     |<-- Redirect response --------|                              |                      |
    #  |                     |--- Browser navigates -------------------------------------->|                      |
    #  |                     |   https://<DOMAIN>/oauth2/authorize?client_id=...           |                      |
    #  |                     |                              |                              |                      |
    #  |                     |                              |                              |-- Redirect to ------>|
    #  |                     |                              |                              |   Google login page  |
    #  |                     |                              |                              |                      |
    #  |                     |                              |                              |<-- User enters creds |
    #  |                     |                              |                              |                      |
    #  |                     |                              |                              |<-- Redirect back ----|
    #  |                     |                              |                              |   to Cognito w/ code |
    #  |                     |                              |                              |                      |
    #  |                     |<-- Redirect to REDIRECT_URI -|                              |                      |
    #  |                     |   (e.g. /auth/callback?code=...)                             |                      |
    #  |                     |--- Call /auth/callback ----->|                              |                      |
    #  |                     |                              |-- auth_callback() -----------|                      |
    #  |                     |                              |   validate state, exchange   |                      |
    #  |                     |                              |   /oauth2/token ------------>|                      |
    #  |                     |                              |                              |                      |
    #  |                     |                              |<-- JSON tokens (id/access) --|                      |
    #  |                     |                              | verify ID token (JWKS)       |                      |
    #  |                     |                              | store session, set cookie    |                      |
    #  |                     |<-- Redirect /app ------------|                              |                      |
    #  |--- Logged in ------>|                              |                              |                      |
    def login_google(self):
        try:
            # Generate PKCE + state, store server-side (e.g., session or DB)
            verifier = self.b64u(os.urandom(32))
            challenge = self.b64u(hashlib.sha256(verifier.encode()).digest())
            state = secrets.token_urlsafe(24)
            session["pkce_verifier"] = verifier
            session["oauth_state"] = state

            params = {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": "openid email profile",
                "identity_provider": "Google",      # deep-link straight to Google
                "code_challenge_method": "S256",
                "code_challenge": challenge,
                "state": state,
            }
            return redirect(f"{AUTH_URL}?{urlencode(params)}")

        except Exception as e:
            err_trace = get_traceback(e, "ErrorLoginGoogle")
            logger.debug(err_trace)
            return err_trace


    def auth_callback(self):
        try:
            if request.args.get("state") != session.get("oauth_state"):
                return abort(400, "bad state")

            code = request.args.get("code")
            if not code: return abort(400, "missing code")

            data = {
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,          # public client (no secret) for browser flows
                "redirect_uri": REDIRECT_URI,
                "code": code,
                "code_verifier": session.pop("pkce_verifier", ""),
            }
            tok = requests.post(
                TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            ).json()

            id_token = tok["id_token"]
            # Verify ID token
            jwks = requests.get(JWKS_URL, timeout=10).json()
            keys = {k["kid"]: RSAAlgorithm.from_jwk(json.dumps(k)) for k in jwks["keys"]}
            header = jwt.get_unverified_header(id_token)
            claims = jwt.decode(
                id_token, key=keys[header["kid"]], algorithms=["RS256"],
                audience=CLIENT_ID,
                issuer=f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}",
            )

            # Create your own session (httpOnly, Secure, SameSite=Lax/None)
            # e.g., set a signed session cookie that references a server-side session
            session["user"] = {
                "sub": claims["sub"],
                "email": claims.get("email"),
                "name": claims.get("name"),
                "id_token": id_token,
                "expires_at": int(time.time()) + tok.get("expires_in", 3600),
                "refresh_token": tok.get("refresh_token")  # store server-side only
            }

            # Redirect back to the SPA (now authenticated by your cookie)
            return redirect("/app")

        except Exception as e:
            err_trace = get_traceback(e, "ErrorLoginGoogleAuthCallback")
            logger.debug(err_trace)
            return err_trace