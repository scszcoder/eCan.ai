import os
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTextBrowser, QPushButton, 
                               QHBoxLayout, QFrame, QLabel, QWidget)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from config.app_info import app_info
from gui.messages import get_message, get_current_language

class UserManualDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(get_message('user_manual_title'))
        self.resize(800, 600)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        self.setup_ui()
        self.load_content()
        self.apply_styles()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        title_label = QLabel(get_message('user_manual_title'))
        title_label.setObjectName("titleLabel")
        header_layout.addWidget(title_label)
        
        main_layout.addWidget(header_frame)

        # Content
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setFrameShape(QFrame.NoFrame)
        main_layout.addWidget(self.text_browser)

        # Footer
        footer_frame = QFrame()
        footer_frame.setObjectName("footerFrame")
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        
        close_button = QPushButton(get_message('close'))
        close_button.setFixedSize(100, 32)
        close_button.setCursor(Qt.PointingHandCursor)
        close_button.clicked.connect(self.accept)
        
        footer_layout.addStretch()
        footer_layout.addWidget(close_button)
        
        main_layout.addWidget(footer_frame)

    def load_content(self):
        # Show a styled page with link to online manual
        manual_url = "https://www.ecan.ai/docs/user_manual.html"
        
        # Get internationalized text
        page_title = get_message('user_manual_page_title')
        page_subtitle = get_message('user_manual_page_subtitle')
        open_button = get_message('user_manual_open_button')
        feature_1 = get_message('user_manual_feature_1')
        feature_2 = get_message('user_manual_feature_2')
        feature_3 = get_message('user_manual_feature_3')
        feature_4 = get_message('user_manual_feature_4')
        
        content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    color: #24292f;
                    padding: 80px 40px;
                    max-width: 700px;
                    margin: 0 auto;
                    text-align: center;
                }}
                .icon {{
                    font-size: 64px;
                    margin-bottom: 20px;
                }}
                h1 {{
                    font-size: 32px;
                    font-weight: 700;
                    color: #1f2328;
                    margin-bottom: 16px;
                }}
                .subtitle {{
                    font-size: 16px;
                    color: #57606a;
                    margin-bottom: 40px;
                    line-height: 1.6;
                }}
                .link-button {{
                    display: inline-block;
                    padding: 14px 28px;
                    background-color: #238636;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 16px;
                    transition: all 0.2s;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.12);
                }}
                .link-button:hover {{
                    background-color: #2ea043;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
                    transform: translateY(-1px);
                }}
                .url-box {{
                    margin-top: 40px;
                    padding: 16px 20px;
                    background-color: #f6f8fa;
                    border: 1px solid #d0d7de;
                    border-radius: 8px;
                    font-family: 'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace;
                    font-size: 13px;
                    color: #0969da;
                    word-break: break-all;
                }}
                .features {{
                    margin-top: 50px;
                    text-align: left;
                    padding: 0 20px;
                }}
                .feature-item {{
                    margin-bottom: 16px;
                    padding-left: 28px;
                    position: relative;
                    color: #57606a;
                    font-size: 14px;
                    line-height: 1.6;
                }}
                .feature-item:before {{
                    content: "✓";
                    position: absolute;
                    left: 0;
                    color: #238636;
                    font-weight: bold;
                    font-size: 16px;
                }}
            </style>
        </head>
        <body>
            <div class="icon">📖</div>
            <h1>{page_title}</h1>
            <p class="subtitle">{page_subtitle}</p>
            <a href="{manual_url}" class="link-button">{open_button}</a>
            <div class="url-box">{manual_url}</div>
            
            <div class="features">
                <div class="feature-item">{feature_1}</div>
                <div class="feature-item">{feature_2}</div>
                <div class="feature-item">{feature_3}</div>
                <div class="feature-item">{feature_4}</div>
            </div>
        </body>
        </html>
        """
        
        self.text_browser.setHtml(content)

    def apply_styles(self):
        style = """
        QDialog {
            background-color: #ffffff;
        }
        QFrame#headerFrame {
            background-color: #f6f8fa;
            border-bottom: 1px solid #d0d7de;
        }
        QLabel#titleLabel {
            font-size: 18px;
            font-weight: 600;
            color: #1f2328;
        }
        QTextBrowser {
            background-color: #ffffff;
            border: none;
        }
        QFrame#footerFrame {
            background-color: #f6f8fa;
            border-top: 1px solid #d0d7de;
        }
        QPushButton {
            background-color: #238636;
            color: white;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            font-size: 13px;
            padding: 6px 16px;
        }
        QPushButton:hover {
            background-color: #2ea043;
        }
        QPushButton:pressed {
            background-color: #1a7f37;
        }
        """
        self.setStyleSheet(style)
