import sys

from PySide6 import QtWidgets
from PySide6.QtWidgets import QApplication, QMainWindow

from SkillGUI import SkillGUI
from config.app_settings import app_settings


class SkillWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.skill_gui = SkillGUI(self)
        self.skill_gui.showMaximized()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SkillWindow()
    # window.show()
    sys.exit(app.exec())
