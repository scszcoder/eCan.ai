from PySide6 import QtWidgets
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog
from PySide6.QtTest import QTest
import sys
from gui.skfc.skfc_widget import *
from gui.skcode.codeeditor.pythoneditor import PMGPythonEditor
from config.app_settings import app_settings


class GraphEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Graph Editor")
        self.resize(1000, 800)

        self.skFCWidget = SkFCWidget()
        self.skCodeWidget = PMGPythonEditor()

        self.skvtabs = QtWidgets.QTabWidget()
        self.skvtabs.addTab(self.skFCWidget, "Flow Chart")
        self.skvtabs.addTab(self.skCodeWidget, "Code")

        layout = QVBoxLayout()
        layout.addWidget(self.skvtabs)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.create_menu()

    def create_menu(self):
        # 创建菜单栏
        menubar = self.menuBar()

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
        data = self.skFCWidget.encode_json(indent=4)
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save JSON File', 'diagram_ui.json', 'JSON Files (*.json)')
        if file_path:
            with open(file_path, 'w') as file:
                # json.dump(data, file, indent=4)
                file.write(data)
                print(f'JSON data saved to {file_path}')

    def open_json(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Open JSON File', '', 'JSON Files (*.json)')
        if file_path:
            with open(file_path, 'r') as file:
                data = json.load(file)
                print(f'JSON data loaded from {file_path}: {data}')

                self.skFCWidget.decode_json(json.dumps(data))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GraphEditorWindow()
    window.show()
    sys.exit(app.exec())
