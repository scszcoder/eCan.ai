import json
import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog

from SkillGUI import SkillGUI
from config.app_settings import app_settings
from skfc.skfc_skd import SkFCSkd


class SkillWindow(QMainWindow):
    def __init__(self):
        super().__init__()
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

        # 创建保存动作
        gen_psk_action = QAction('Gen Psk', self)
        gen_psk_action.triggered.connect(self.gen_psk_file)
        file_menu.addAction(gen_psk_action)

        # 创建打开动作
        open_action = QAction('Open', self)
        open_action.triggered.connect(self.open_json)
        file_menu.addAction(open_action)

        # 创建Run动作
        run_action = QAction('Run', self)
        run_action.triggered.connect(self.run_psk)
        file_menu.addAction(run_action)

        # 直接生成psk文件
        run_action = QAction('Direct Gen Psk', self)
        run_action.triggered.connect(self.dir_gen_psk_file)
        file_menu.addAction(run_action)

    def save_json(self):
        data = self.skill_gui.skFCWidget.encode_json(indent=4)
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save JSON File', 'skill_gui_test.skd', 'SKD Files (*.skd)')
        if file_path:
            with open(file_path, 'w') as file:
                # json.dump(data, file, indent=4)
                file.write(data)
                print(f'JSON data saved to {file_path}')

    def gen_psk_file(self):
        worksettings = {}
        psk_words = self.skill_gui.skFCWidget.skfc_scene.gen_psk_words(worksettings)
        psk_file_path = "skill_gui_test.psk"
        if psk_file_path:
            with open(psk_file_path, 'w') as file:
                file.write(psk_words)
                print(f'save psk file to {psk_file_path}')

    def open_json(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Open SKD File', '', 'SKD Files (*.skd)')
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

    def run_psk(self):
        self.skill_gui.skFCWidget.skfc_scene.gen_psk_words(None)

    def dir_gen_psk_file(self):
        # skd_file = "/Users/liuqiang02/Desktop/workspace/ecbot/resource/skills/my/win_chrome_amz_home/tests/scripts/tests.skd"
        skd_file = 'skill_gui_test.skd'
        psk_file_dir = "/Users/liuqiang02/Desktop/workspace/ecbot/resource/skills/my/win_chrome_amz_home/tests/scripts"

        SkFCSkd().gen_psk_file(skd_file, psk_file_dir)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SkillWindow()
    # window.show()
    sys.exit(app.exec())
