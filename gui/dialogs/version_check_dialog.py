from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, 
                               QFrame, QHBoxLayout, QWidget)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from config.app_info import app_info
from gui.messages import get_message
import os

class VersionCheckDialog(QDialog):
    def __init__(self, parent=None, is_latest=True, version="1.0.0", error_msg=None):
        super().__init__(parent)
        self.is_latest = is_latest
        self.version = version
        self.error_msg = error_msg
        
        self.setWindowTitle(get_message('check_updates_title'))
        self.setFixedSize(450, 300)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        self.setup_ui()
        self.apply_styles()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 35, 40, 30)
        main_layout.setSpacing(0)

        # Logo - horizontal logoWhite22.png
        logo_label = QLabel()
        logo_path = self._get_logo_path()
        if logo_path and os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            print(f"[VersionCheckDialog] Logo loaded, isNull: {pixmap.isNull()}, size: {pixmap.size()}")
            if not pixmap.isNull():
                # Scale to height of 50px for smaller dialog
                scaled_pixmap = pixmap.scaledToHeight(50, Qt.SmoothTransformation)
                print(f"[VersionCheckDialog] Scaled logo size: {scaled_pixmap.size()}")
                logo_label.setPixmap(scaled_pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(logo_label)

        main_layout.addSpacing(30)

        # Status Text
        status_label = QLabel()
        status_label.setObjectName("statusLabel")
        status_label.setAlignment(Qt.AlignCenter)
        
        if self.error_msg:
            status_label.setText(get_message('check_failed'))
            status_label.setStyleSheet("color: #f85149; font-size: 18px; font-weight: 600;") # Red
        elif self.is_latest:
            status_label.setText(get_message('update_latest_title'))
            status_label.setStyleSheet("color: #3fb950; font-size: 18px; font-weight: 600;") # Green
        else:
            status_label.setText(get_message('update_available_title'))
            status_label.setStyleSheet("color: #58a6ff; font-size: 18px; font-weight: 600;") # Blue

        main_layout.addWidget(status_label)

        main_layout.addSpacing(15)

        # Detail Text
        detail_label = QLabel()
        detail_label.setObjectName("detailLabel")
        detail_label.setAlignment(Qt.AlignCenter)
        detail_label.setWordWrap(True)
        
        if self.error_msg:
            detail_label.setText(self.error_msg)
        elif self.is_latest:
            detail_label.setText(get_message('update_latest_desc', version=self.version))
        
        main_layout.addWidget(detail_label)

        main_layout.addStretch()

        main_layout.addSpacing(20)

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
        # Use horizontal logo
        resource_path = app_info.app_resources_path
        logo_path = os.path.join(resource_path, "images", "logos", "logoWhite22.png")
        print(f"[VersionCheckDialog] Checking logo path: {logo_path}, exists: {os.path.exists(logo_path)}")
        if os.path.exists(logo_path):
            print(f"[VersionCheckDialog] Using logo: {logo_path}")
            return logo_path
        print("[VersionCheckDialog] Logo not found!")
        return None

    def apply_styles(self):
        # Simple clean dark theme matching About dialog
        style = """
        QDialog {
            background-color: #1e2936;
        }
        QLabel {
            color: #e6edf3;
        }
        QLabel#detailLabel {
            font-size: 13px;
            color: #8b949e;
            line-height: 1.5;
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
