import json
import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog

from SkillGUI import SkillGUI
from config.app_settings import app_settings


class SkillWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        SkillGUI.Debug = True
        self.skill_gui = SkillGUI(self)
        # self.skill_gui.showMaximized()
        self.skill_gui.show()

        self.create_menu()

        self.load_json_file()

    def create_menu(self):
        # 创建菜单栏
        menubar = self.skill_gui.menuBar()

        # 创建文件菜单
        file_menu = menubar.addMenu('File')

        # 创建保存动作
        save_action = QAction('Save', self)
        save_action.triggered.connect(self.save_json)
        file_menu.addAction(save_action)

        # 创建打开动作
        open_action = QAction('Open', self)
        open_action.triggered.connect(self.open_json)
        file_menu.addAction(open_action)

    def save_json(self):
        data = self.skill_gui.skFCWidget.encode_json(indent=4)
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save JSON File', 'skill_gui_test.skd', 'SKD Files (*.skd)')
        if file_path:
            with open(file_path, 'w') as file:
                # json.dump(data, file, indent=4)
                file.write(data)
                print(f'JSON data saved to {file_path}')

    def open_json(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Open SKD File', '', 'SKD Files (*.sdk)')
        if file_path:
            with open(file_path, 'r') as file:
                data = json.load(file)
                print(f'JSON data loaded from {file_path}: {data}')

                self.skill_gui.skFCWidget.decode_json(json.dumps(data))

    def load_json_file(self):
        file_path = 'skill_gui_test.skd'
        with open(file_path, 'r') as f:
            data = json.load(f)

            print(f'SKD data loaded from {file_path}: {data}')

            self.skill_gui.skFCWidget.decode_json(json.dumps(data))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SkillWindow()
    # window.show()
    sys.exit(app.exec())
