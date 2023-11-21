import os
from qtpy.QtWidgets import QApplication

from qtpyeditor.codeedit import PMPythonCodeEdit
from qtpyeditor import PMGPythonEditor

if __name__ == '__main__':
    app = QApplication([])
    e = PMGPythonEditor()
    e.resize(800, 600)
    e.show()
    e.load_file(os.path.join(os.path.dirname(__file__), '', 'pyeditor_test_file.py'))
    app.exec()
