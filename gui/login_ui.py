"""
UI class for login interface - handles all Qt widgets and user interactions.
This class is responsible only for the user interface and delegates business logic to AuthService.
"""

import json
import locale
import os
from os.path import exists
from typing import Optional, Callable

from PySide6.QtCore import QLocale, QTranslator, QCoreApplication, Qt, QEvent, QSettings
from PySide6.QtGui import QPixmap, QFont, QIcon
from PySide6.QtWidgets import (QDialog, QLabel, QComboBox, QApplication, QLineEdit, 
                              QPushButton, QCheckBox, QHBoxLayout, QVBoxLayout, QMessageBox)

from config.app_info import app_info
from bot.envi import getECBotDataHome
from utils.fernet import encrypt_password, decrypt_password
from utils.logger_helper import logger_helper as logger


class LoginUI(QDialog):
    """UI class for login interface - handles all Qt widgets and user interactions."""
    
    def __init__(self, parent=None):
        super(LoginUI, self).__init__(parent)
        
        # Configuration
        self.ecbhomepath = app_info.app_home_path
        self.ecb_data_homepath = getECBotDataHome()
        self.acct_file = self.ecb_data_homepath + "/uli.json"
        
        # UI state
        self.password_shown = False
        self.password_shown2 = False
        self.show_visibility = True
        self.show_visibility2 = True
        self.lang = "en"
        
        # Role and schedule mode options
        self.role_list = ["Staff Officer", "Commander", "Commander Only", "Platoon"]
        self.schedule_mode_list = ["manual", "auto"]
        
        # Callback functions (to be set by parent)
        self.on_login_callback: Optional[Callable] = None
        self.on_signup_callback: Optional[Callable] = None
        self.on_forgot_password_callback: Optional[Callable] = None
        self.on_confirm_forgot_password_callback: Optional[Callable] = None
        
        # Initialize UI
        self._setup_ui()
        self._setup_translations()
        self._load_saved_settings()
    
    def _setup_ui(self):
        """Initialize all UI components."""
        # Window setup
        self.win_icon = QIcon(self.ecbhomepath + "/resource/images/icons/eye48.png")
        self.setWindowIcon(self.win_icon)
        self.setWindowTitle('AiPPS My E-Commerce Agents')
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        
        # Icons
        self.visibleIcon = QIcon(self.ecbhomepath + "/resource/images/icons/eye48.png")
        self.hiddenIcon = QIcon(self.ecbhomepath + "/resource/images/icons/hidden48.png")
        
        # Fonts
        self.linkFont = QFont('Arial', 12, italic=True)
        self.linkFont.setUnderline(True)
        
        # Settings
        self.settings = QSettings("ecbot")
        self.pwd_key = "encrypted_password"
        
        # Banner
        self.banner = QLabel(self)
        pixmap = QPixmap(self.ecbhomepath + '/resource/images/icons/ecBot09.png')
        self.banner.setPixmap(pixmap)
        
        # Logo
        self.logo0 = QLabel(self)
        pixmap = QPixmap(self.ecbhomepath + '/resource/images/icons/maipps_logo192.png')
        self.logo0.setPixmap(pixmap)
        self.logo0.setAlignment(Qt.AlignTop)
        
        # Language selection
        self.lan_label = QLabel(QApplication.translate("QLabel", "Language"))
        self.lan_select = QComboBox(self)
        self.lan_select.addItem('English')
        self.lan_select.addItem('中文')
        self.lan_select.currentIndexChanged.connect(self._on_language_changed)
        
        # Role selection
        self.role_label = QLabel(QApplication.translate("QLabel", "Role"), alignment=Qt.AlignRight)
        self.role_select = QComboBox(self)
        for role in self.role_list:
            self.role_select.addItem(QApplication.translate("QComboBox", role))
        self.role_select.setCurrentIndex(1)  # Default to Commander
        
        # Schedule mode selection
        self.schedule_mode_label = QLabel(QApplication.translate("QLabel", "Schedule Mode"), alignment=Qt.AlignLeft)
        self.schedule_mode_select = QComboBox(self)
        for schedule_mode in self.schedule_mode_list:
            self.schedule_mode_select.addItem(QApplication.translate("QComboBox", schedule_mode))
        self.schedule_mode_select.setCurrentIndex(0)  # Default to manual
        
        # Login form labels
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
        
        # Input fields
        self.textName = QLineEdit(self)
        self.textConfirmCode = QLineEdit(self)
        
        self.textPass = QLineEdit(self)
        self.textPass.setEchoMode(QLineEdit.Password)
        
        self.textPass2 = QLineEdit(self)
        self.textPass2.setEchoMode(QLineEdit.Password)
        
        # Password visibility toggles
        if self.show_visibility:
            self.textPass.togglepasswordAction = self.textPass.addAction(
                self.visibleIcon, QLineEdit.TrailingPosition
            )
            self.textPass.togglepasswordAction.triggered.connect(self._toggle_password_visibility)
        
        if self.show_visibility2:
            self.textPass2.togglepasswordAction = self.textPass2.addAction(
                self.visibleIcon, QLineEdit.TrailingPosition
            )
            self.textPass2.togglepasswordAction.triggered.connect(self._toggle_password_visibility2)
        
        # Buttons and links
        self.buttonLogin = QPushButton('Login', self)
        self.buttonLogin.clicked.connect(self._on_login_clicked)
        
        self.forget_label = QLabel(QApplication.translate("QLabel", "Forgot Password?"))
        self.forget_label.setFont(self.linkFont)
        self.forget_label.setAlignment(Qt.AlignRight)
        self.forget_label.setStyleSheet("color: #409eff;")
        self.forget_label.mouseReleaseEvent = self._on_forgot_password_clicked
        
        self.signup_label = QLabel(QApplication.translate("QLabel", "No account? Sign Up Here!"))
        self.signup_label.setFont(self.linkFont)
        self.signup_label.setAlignment(Qt.AlignRight)
        self.signup_label.setStyleSheet("color: #409eff;")
        self.signup_label.mouseReleaseEvent = self._on_signup_clicked
        
        # Remember password checkbox
        self.mempw_cb = QCheckBox(QApplication.translate("QCheckBox", "Memorize Password"))
        self.mempw_cb.setCheckState(Qt.Checked if self.show_visibility else Qt.Unchecked)
        self.mempw_cb.stateChanged.connect(self._on_remember_password_changed)
        self.mempw_cb.setFont(self.linkFont)
        self.mempw_cb.setStyleSheet("color: #409eff;")
        
        # Initially hide signup and forgot password fields
        self.confirm_code_label.setVisible(False)
        self.textConfirmCode.setVisible(False)
        self.confirm_pw_label.setVisible(False)
        self.textPass2.setVisible(False)
        
        # Layout
        self._setup_layout()
    
    def _setup_layout(self):
        """Setup the layout of UI components."""
        layout = QHBoxLayout(self)
        layout.addWidget(self.banner)
        
        log_layout = QVBoxLayout()
        
        # Header layouts
        headline_layout = QHBoxLayout()
        headline_layout.addWidget(self.lan_label)
        headline_layout.addWidget(self.lan_select)
        headline_layout.addWidget(self.role_label)
        headline_layout.addWidget(self.role_select)
        
        headline2_layout = QHBoxLayout()
        headline2_layout.setSpacing(0)
        headline2_layout.setAlignment(self.schedule_mode_select, Qt.AlignLeft)
        headline2_layout.addWidget(self.schedule_mode_label)
        headline2_layout.addWidget(self.schedule_mode_select)
        
        # Remember password and forgot password layout
        reminder_layout = QHBoxLayout()
        reminder_layout.addWidget(self.mempw_cb)
        reminder_layout.addWidget(self.forget_label)
        
        # Add all components to main layout
        log_layout.addLayout(headline_layout)
        log_layout.addLayout(headline2_layout)
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
        log_layout.addLayout(reminder_layout)
        log_layout.addWidget(self.buttonLogin)
        log_layout.addWidget(self.signup_label)
        
        layout.addLayout(log_layout)
    
    def _setup_translations(self):
        """Setup translation system."""
        self.__translator = QTranslator()
    
    def _load_saved_settings(self):
        """Load saved user settings from file."""
        if exists(self.acct_file):
            try:
                with open(self.acct_file, 'r') as file:
                    data = json.load(file)
                    logger.info(f"Loaded account data from {self.acct_file}")
                    
                    self.show_visibility = data.get("mem_cb", True)
                    self.textName.setText(data.get("user", ""))
                    
                    if self.show_visibility:
                        stored_encrypted_password = bytes.fromhex(self.settings.value(self.pwd_key, ""))
                        if stored_encrypted_password:
                            decrypted_password = decrypt_password(stored_encrypted_password)
                            self.textPass.setText(decrypted_password)
                    
                    self.lang = data.get("lan", "EN")
                    
                    # Update checkbox state
                    self.mempw_cb.setCheckState(Qt.Checked if self.show_visibility else Qt.Unchecked)
                    
            except Exception as e:
                logger.error(f"Error loading saved settings: {e}")
        else:
            logger.info(f"Account file {self.acct_file} does not exist")
            # Set default language based on system locale
            local_lan = self._get_system_locale()
            self.lang = "EN" if 'en_' in local_lan[0] else "ZH"
    
    def _get_system_locale(self):
        """Get system locale."""
        try:
            locale.setlocale(locale.LC_ALL, '')
            current_locale = locale.getlocale()
            if current_locale[0] is None:
                raise ValueError("Locale not set properly")
            return current_locale
        except Exception as e:
            logger.warning(f"Error getting locale: {e}")
            return 'en_US', 'UTF-8'
    
    # Event handlers
    def _on_language_changed(self, index):
        """Handle language selection change."""
        if index == 1:
            self.lang = "zh"
            logger.info("Loading Chinese fonts...")
            locale_obj = QLocale(QLocale.Chinese)
            self.__translator.load(QLocale.Chinese, self.ecbhomepath + "/ecbot_zh.qm")
            app = QCoreApplication.instance()
            app.installTranslator(self.__translator)
        else:
            self.lang = "en"
            app = QApplication.instance()
            app.removeTranslator(self.__translator)
    
    def _on_remember_password_changed(self, state):
        """Handle remember password checkbox change."""
        self.show_visibility = (state == Qt.Checked.value)
    
    def _toggle_password_visibility(self):
        """Toggle password visibility for main password field."""
        if not self.password_shown:
            self.textPass.setEchoMode(QLineEdit.Normal)
            self.password_shown = True
            self.textPass.togglepasswordAction.setIcon(self.hiddenIcon)
        else:
            self.textPass.setEchoMode(QLineEdit.Password)
            self.password_shown = False
            self.textPass.togglepasswordAction.setIcon(self.visibleIcon)
    
    def _toggle_password_visibility2(self):
        """Toggle password visibility for confirm password field."""
        if not self.password_shown2:
            self.textPass2.setEchoMode(QLineEdit.Normal)
            self.password_shown2 = True
            self.textPass2.togglepasswordAction.setIcon(self.hiddenIcon)
        else:
            self.textPass2.setEchoMode(QLineEdit.Password)
            self.password_shown2 = False
            self.textPass2.togglepasswordAction.setIcon(self.visibleIcon)
    
    def _on_login_clicked(self):
        """Handle login button click."""
        if self.on_login_callback:
            username = self.textName.text()
            password = self.textPass.text()
            role = self.role_select.currentText()
            schedule_mode = self.schedule_mode_select.currentText()
            
            self.on_login_callback(username, password, role, schedule_mode)
    
    def _on_signup_clicked(self, event):
        """Handle signup link click."""
        self._switch_to_signup_mode()
    
    def _on_forgot_password_clicked(self, event):
        """Handle forgot password link click."""
        self._switch_to_forgot_password_mode()
    
    def _switch_to_signup_mode(self):
        """Switch UI to signup mode."""
        self.buttonLogin.setText(QApplication.translate("QPushButton", "Sign Up"))
        self.confirm_pw_label.setVisible(True)
        self.textPass2.setVisible(True)
        self.login_label.setText(QApplication.translate("QLabel", "Sign Up A New Account"))
        
        # Disconnect old handler and connect new one
        self.buttonLogin.clicked.disconnect()
        self.buttonLogin.clicked.connect(self._on_signup_button_clicked)
    
    def _switch_to_forgot_password_mode(self):
        """Switch UI to forgot password mode."""
        self.buttonLogin.setText(QApplication.translate("QPushButton", "Recover Password"))
        self.textPass.setVisible(False)
        self.pw_label.setVisible(False)
        self.signup_label.setVisible(False)
        self.mempw_cb.setVisible(False)
        self.forget_label.setVisible(False)
        self.login_label.setText(QApplication.translate("QLabel", "Recover Password"))
        self.login_label.setAlignment(Qt.AlignTop)
        self.user_label.setText(QApplication.translate("QLabel", "Input Email Address To Recover Password:"))
        self.user_label.setAlignment(Qt.AlignTop)
        
        # Disconnect old handler and connect new one
        self.buttonLogin.clicked.disconnect()
        self.buttonLogin.clicked.connect(self._on_forgot_password_button_clicked)
    
    def _on_signup_button_clicked(self):
        """Handle signup button click."""
        if self.on_signup_callback:
            username = self.textName.text()
            password = self.textPass.text()
            confirm_password = self.textPass2.text()
            
            if password != confirm_password:
                self.show_error_message("Passwords do not match!")
                return
            
            self.on_signup_callback(username, password)
    
    def _on_forgot_password_button_clicked(self):
        """Handle forgot password button click."""
        if self.on_forgot_password_callback:
            username = self.textName.text()
            if not username:
                self.show_error_message("Please enter your email address!")
                return
            
            self.on_forgot_password_callback(username)
    
    def _on_confirm_forgot_password_button_clicked(self):
        """Handle confirm forgot password button click."""
        if self.on_confirm_forgot_password_callback:
            username = self.textName.text()
            confirm_code = self.textConfirmCode.text()
            new_password = self.textPass.text()
            
            if not all([username, confirm_code, new_password]):
                self.show_error_message("Please fill in all fields!")
                return
            
            self.on_confirm_forgot_password_callback(username, confirm_code, new_password)
    
    # Public methods for external control
    def set_login_callback(self, callback: Callable):
        """Set callback for login action."""
        self.on_login_callback = callback
    
    def set_signup_callback(self, callback: Callable):
        """Set callback for signup action."""
        self.on_signup_callback = callback
    
    def set_forgot_password_callback(self, callback: Callable):
        """Set callback for forgot password action."""
        self.on_forgot_password_callback = callback
    
    def set_confirm_forgot_password_callback(self, callback: Callable):
        """Set callback for confirm forgot password action."""
        self.on_confirm_forgot_password_callback = callback
    
    def show_success_message(self, message: str):
        """Show success message to user."""
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText(message)
        msgBox.setWindowTitle("Success")
        msgBox.exec()
    
    def show_error_message(self, message: str):
        """Show error message to user."""
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Critical)
        msgBox.setText(message)
        msgBox.setWindowTitle("Error")
        msgBox.exec()
    
    def show_info_message(self, message: str):
        """Show info message to user."""
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText(message)
        msgBox.setWindowTitle("Information")
        msgBox.exec()
    
    def get_username(self) -> str:
        """Get entered username."""
        return self.textName.text()
    
    def get_password(self) -> str:
        """Get entered password."""
        return self.textPass.text()
    
    def get_role(self) -> str:
        """Get selected role."""
        return self.role_select.currentText()
    
    def get_schedule_mode(self) -> str:
        """Get selected schedule mode."""
        return self.schedule_mode_select.currentText()
    
    def get_language(self) -> str:
        """Get selected language."""
        return self.lang
    
    def save_user_settings(self, username: str):
        """Save user settings to file."""
        try:
            data = {
                "mem_cb": self.show_visibility,
                "user": username,
                "pw": "SCECBOTPW",
                "lan": "EN",
                "schedule_mode": self.get_schedule_mode()
            }
            
            # Handle password storage
            if self.mempw_cb.checkState() == Qt.Unchecked:
                data["mem_cb"] = False
                if self.settings.contains(self.pwd_key):
                    self.settings.remove(self.pwd_key)
            else:
                encrypted_password = encrypt_password(self.get_password())
                self.settings.setValue(self.pwd_key, encrypted_password.hex())
            
            with open(self.acct_file, 'w') as jsonfile:
                json.dump(data, jsonfile)
            
            logger.info(f"User settings saved to {self.acct_file}")
            
        except Exception as e:
            logger.error(f"Error saving user settings: {e}")
    
    def reset_to_login_mode(self):
        """Reset UI back to login mode."""
        self.buttonLogin.setText(QApplication.translate("QPushButton", "Login"))
        self.login_label.setText(QApplication.translate("QLabel", "Login"))
        self.user_label.setText(QApplication.translate("QLabel", "User Name(Email):"))
        
        # Show/hide appropriate fields
        self.textPass.setVisible(True)
        self.pw_label.setVisible(True)
        self.signup_label.setVisible(True)
        self.mempw_cb.setVisible(True)
        self.forget_label.setVisible(True)
        self.confirm_pw_label.setVisible(False)
        self.textPass2.setVisible(False)
        self.confirm_code_label.setVisible(False)
        self.textConfirmCode.setVisible(False)
        
        # Reset alignment
        self.login_label.setAlignment(Qt.AlignLeft)
        self.user_label.setAlignment(Qt.AlignLeft)
        
        # Reconnect login handler
        self.buttonLogin.clicked.disconnect()
        self.buttonLogin.clicked.connect(self._on_login_clicked)
    
    def changeEvent(self, event):
        """Handle change events like language changes."""
        if event.type() == QEvent.LanguageChange:
            logger.info("Re-translating UI...")
            self._retranslate_ui()
        super().changeEvent(event)
    
    def _retranslate_ui(self):
        """Re-translate UI elements."""
        self.buttonLogin.setText(QApplication.translate('QPushButton', 'Login'))
        self.login_label.setText(QApplication.translate('QLabel', 'Login'))
