import os
from qtpy.QtWidgets import QApplication

from skcode.codeedit import PMPythonCodeEdit
from skcode import PMGPythonEditor
from config.app_settings import app_settings


if __name__ == '__main__':
    app = QApplication([])
    e = PMGPythonEditor()
    e.resize(800, 600)
    e.show()
    e.load_file(os.path.join(os.path.dirname(__file__), '', 'skcode_test_file.py'))
    app.exec()
