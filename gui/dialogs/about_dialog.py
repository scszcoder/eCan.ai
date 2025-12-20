import sys
import os
from PySide6.QtWidgets import (QDialog, QLabel, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QFrame, QWidget)
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QPixmap, QFont, QIcon, QDesktopServices
from config.app_info import app_info
from gui.messages import get_message

class AboutDialog(QDialog):
    def __init__(self, parent=None, version="1.0.0"):
        super().__init__(parent)
        self.version = version
        self.setWindowTitle(get_message('about_title'))
        self.setFixedSize(500, 450)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        # Setup UI
        self.setup_ui()
        
        # Apply styles
        self.apply_styles()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 35)
        main_layout.setSpacing(0)

        # Logo - horizontal logoWhite22.png
        logo_label = QLabel()
        logo_path = self._get_logo_path()
        if logo_path and os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            print(f"[AboutDialog] Logo loaded, isNull: {pixmap.isNull()}, size: {pixmap.size()}")
            if not pixmap.isNull():
                # Scale to height of 60px to fit nicely, width auto-adjusts
                scaled_pixmap = pixmap.scaledToHeight(60, Qt.SmoothTransformation)
                print(f"[AboutDialog] Scaled logo size: {scaled_pixmap.size()}")
                logo_label.setPixmap(scaled_pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(logo_label)

        main_layout.addSpacing(25)

        # Version
        version_label = QLabel(get_message('version_label', version=self.version))
        version_label.setObjectName("versionLabel")
        version_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(version_label)

        main_layout.addSpacing(20)

        # Description
        desc_label = QLabel(get_message('about_desc'))
        desc_label.setObjectName("descLabel")
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)

        main_layout.addSpacing(20)

        # Website Link
        link_label = QLabel('<a href="https://www.ecan.ai" style="color: #58a6ff; text-decoration: none;">www.ecan.ai</a>')
        link_label.setObjectName("linkLabel")
        link_label.setAlignment(Qt.AlignCenter)
        link_label.setOpenExternalLinks(True)
        link_label.setCursor(Qt.PointingHandCursor)
        main_layout.addWidget(link_label)

        main_layout.addStretch()

        # Team Info
        team_label = QLabel(get_message('about_designed_by'))
        team_label.setObjectName("teamLabel")
        team_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(team_label)

        main_layout.addSpacing(5)

        # Copyright
        copyright_label = QLabel(get_message('about_copyright'))
        copyright_label.setObjectName("copyrightLabel")
        copyright_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(copyright_label)
        
        main_layout.addSpacing(25)

        # OK Button
        ok_button = QPushButton(get_message('ok'))
        ok_button.setCursor(Qt.PointingHandCursor)
        ok_button.setFixedSize(120, 38)
        ok_button.clicked.connect(self.accept)
        
        # Center button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

    def _get_logo_path(self):
        """Get horizontal logo path - use logoWhite22.png"""
        resource_path = app_info.app_resources_path
        # Use the horizontal logo
        logo_path = os.path.join(resource_path, "images", "logos", "logoWhite22.png")
        print(f"[AboutDialog] Checking logo path: {logo_path}, exists: {os.path.exists(logo_path)}")
        if os.path.exists(logo_path):
            print(f"[AboutDialog] Using logo: {logo_path}")
            return logo_path
        print("[AboutDialog] Logo not found!")
        return None

    def apply_styles(self):
        # Simple clean dark theme
        style = """
        QDialog {
            background-color: #1e2936;
        }
        QLabel {
            color: #e6edf3;
        }
        QLabel#versionLabel {
            font-size: 14px;
            color: #8b949e;
        }
        QLabel#descLabel {
            font-size: 13px;
            color: #c9d1d9;
            line-height: 1.5;
        }
        QLabel#linkLabel {
            font-size: 14px;
        }
        QLabel#teamLabel {
            font-size: 11px;
            color: #7d8590;
        }
        QLabel#copyrightLabel {
            font-size: 11px;
            color: #7d8590;
        }
        QPushButton {
            background-color: #238636;
            color: white;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            font-size: 13px;
        }
        QPushButton:hover {
            background-color: #2ea043;
        }
        QPushButton:pressed {
            background-color: #1a7f37;
        }
        """
        self.setStyleSheet(style)
