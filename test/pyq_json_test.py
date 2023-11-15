import json
import unittest
from PySide6.QtCore import (Signal, QLineF, QPointF, QRect, QRectF, QSize, QSizeF, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QIcon, QIntValidator, QPainter, QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QButtonGroup, QComboBox, \
                    QFontComboBox, QGraphicsItem, QGraphicsLineItem, QGraphicsPolygonItem, \
                            QGraphicsScene, QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsView, QGridLayout, \
                            QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QSizePolicy, \
                            QVBoxLayout, QToolBox, QToolButton, QWidget
from PySide6.QtTest import QTest
import sys
from gui.codeeditor import *
from gui.diagram.pyq_diagram import *

class GraphEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Graph Editor")
        self.resize(800, 600)

        self.skvtabs = QtWidgets.QTabWidget()

        self.skFCWidget = QtWidgets.QScrollArea()
        self.skFCWidget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.skFCWidget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)

        self.skCodeWidget = QtWidgets.QScrollArea()
        self.skCodeWidget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.skCodeWidget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)

        self.skFCDiagram = PyQDiagram()
        self.skFCWidget.setWidget(self.skFCDiagram)

        self.skcodeeditor = SimpleCodeEditor()
        self.skCodeWidget.setWidget(self.skcodeeditor)

        self.skvtabs.addTab(self.skFCDiagram.widget, "Flow Chart")
        self.skvtabs.addTab(self.skCodeWidget, "Code")

        layout = QVBoxLayout()
        layout.addWidget(self.skvtabs)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.load_json()

    def load_json(self):
        with open('diagram_ui.json') as f:
            data: dict = json.load(f)

            self.skFCDiagram.decode_json(json.dumps(data))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GraphEditorWindow()
    window.show()
    sys.exit(app.exec())

