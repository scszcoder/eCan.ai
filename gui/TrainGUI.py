import sys
import random
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from locale import getdefaultlocale

import ctypes as ct
from ctypes import wintypes as wt
import time
import json

from pynput import mouse
from pynput import keyboard
import threading

import pyautogui
from Cloud import *
from SkillGUI import *


counter = 0
record_over = False
temp_dir = "C:/Users/Teco/PycharmProjects/ecbot/resource/skills/temp/"

class STEP:
    def __init__(self, parent):
        super(ReminderWin, self).__init__(parent)

        self.order = 0
        self.img = None
        self.location = (0, 0, 0, 0)
        self.action = ""


class TrainDialogWin(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(TrainDialogWin, self).__init__(parent)

        self.mainWidget = QtWidgets.QWidget()
        self.reminder_label = QtWidgets.QLabel("press <Esc> key to end recording", alignment=QtCore.Qt.AlignLeft)

        self.start_button = QtWidgets.QPushButton("Start Training")
        self.cancel_button = QtWidgets.QPushButton("Cancel")

        self.rLayout = QtWidgets.QHBoxLayout(self)
        self.rLayout.addWidget(self.reminder_label)
        self.mainWidget.setLayout(self.rLayout)
        self.setCentralWidget(self.mainWidget)


class ReminderWin(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(ReminderWin, self).__init__(parent)

        self.mainWidget = QtWidgets.QWidget()
        self.reminder_label = QtWidgets.QLabel("press <Esc> key to end recording", alignment=QtCore.Qt.AlignLeft)
        self.rLayout = QtWidgets.QHBoxLayout(self)
        self.rLayout.addWidget(self.reminder_label)
        self.mainWidget.setLayout(self.rLayout)
        self.setCentralWidget(self.mainWidget)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowStaysOnTopHint)


class TrainNewWin(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(TrainNewWin, self).__init__(parent)

    # def __init__(self):
    #     super().__init__()
        self.newSkill = None
        self.parent = parent
        self.mainWidget = QtWidgets.QWidget()
        self.trainDialog = TrainDialogWin(self)
        self.session = None
        self.cog = None

        self.start_tutor_button = QtWidgets.QPushButton("Tutorial")
        self.start_demo_button = QtWidgets.QPushButton("Start Demo")
        self.start_skill_button = QtWidgets.QPushButton("Define Skill")
        self.cancel_button = QtWidgets.QPushButton("Cancel")

        self.bLayout = QtWidgets.QHBoxLayout(self)
        self.rLayout = QtWidgets.QHBoxLayout(self)

        #self.label = QtWidgets.QLabel()
        self.bLayout.addWidget(self.start_tutor_button)
        self.bLayout.addWidget(self.start_demo_button)
        self.bLayout.addWidget(self.start_skill_button)
        self.bLayout.addWidget(self.cancel_button)

        self.start_tutor_button.clicked.connect(self.skill_tutorial)
        self.start_demo_button.clicked.connect(self.start_recording)
        self.start_skill_button.clicked.connect(self.start_skill)
        self.cancel_button.clicked.connect(self.cancel_recording)

        self.mainWidget.setLayout(self.bLayout)
        self.setCentralWidget(self.mainWidget)

        self.skillGUI = SkillGUI(self)

        self.imq = []
        self.record = []
        self.steps = 0
        self.actionRecord = [{"step": 0}]

    def mousePressEvent(self, event):
        self.oldPos = event.globalPos()


    def mouseMoveEvent(self, event):
        delta = QtCore.QPoint(event.globalPos() - self.oldPos)
        #self.move(self.x() + delta.x(), self.y() + delta.y())
        #self.oldPos = event.globalPos()
        # Update the origin for next time.
        #self.last_x = event.x()
        #self.last_y = event.y()

    def mouseReleaseEvent(self, e):
        delta = QtCore.QPoint(e.globalPos() - self.oldPos)
        print("box[", self.oldPos.x(), ", ", self.oldPos.y(), ", ", e.globalPos().x(), ", ", e.globalPos().y(), "]")
        # color code design: text: yellow, image: purple, selected text: orange, selected image, dark purple.
        # anchored text: red, anchored image: Blue. info-box: blue, seletected info-box: cyan
        # selected anchor text: dark red, selected anchor image: midnight blue
        #
        # now for the enclosed rectangles, re-draw them red, if already red, redraw the dark red,
        # then allow right mouse click to bring out
        # select "Set anchor" or "Unset anchor", "Set Info", "Unselect Info"
        # double click on anchor will bring out view and edit anchor subwindow.
        # double click on

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.showMinimized()


    def on_move(self, x, y):
        global record_over
        if record_over == True:
            record_over = False
            return False
        else:
            print('Pointer moved to {0}'.format((x, y)))
            im = pyautogui.screenshot()
            self.imq.append(im)
            if len(self.imq) > 5:
                self.imq.pop(0)


    def on_click(self, x, y, button, pressed):
        global record_over
        print('{0} at {1}'.format('Pressed' if pressed else 'Released', (x, y)))
        if record_over:
            return False
        else:

            self.steps = self.steps + 1
            fname = temp_dir + "step" + str(self.steps) + ".png"
            im = pyautogui.screenshot(fname)
            #self.record.append(im)
            self.steps = self.steps + 1

            self.record.append(self.imq.pop(0))
            im = pyautogui.screenshot()
            self.imq.append(im)
            # if not pressed:
            #     # Stop listener
            #     return False

    def on_scroll(self, x, y, dx, dy):
        global record_over
        if record_over:
            return False
        else:
            print('Scrolled {0} at {1}'.format(
                'down' if dy < 0 else 'up',
                (x, y)))
            fname = temp_dir + "step" + str(self.steps) + ".png"
            im = pyautogui.screenshot(fname)
            #self.record.append(im)
            self.steps = self.steps + 1

    def on_press(self, key):
        try:
            print('alphanumeric key {0} pressed'.format(
                key.char))
        except AttributeError:
            print('special key {0} pressed'.format(
                key))

    def on_release(self, key):
        print('{0} released'.format(
            key))
        if key == keyboard.Key.esc:
            # Stop listener
            global record_over
            record_over = True
            self.parent.reminderWin.hide()

            msgBox = QtWidgets.QMessageBox()
            msgBox.setText("Are you done with showing the process to be automated?")
            # msgBox.setInformativeText("Do you want to save your changes?")
            msgBox.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            # msgBox.setDefaultButton(QMessageBox.Save)
            ret = msgBox.exec()

            if ret == QtWidgets.QMessageBox.Yes:
                print("done with demo...")
                self.saveRecordFile()

            return False

    def start_recording(self):
        # Collect events until released
        global record_over
        record_over = False
        self.hide()
        #reminder = ReminderWin(self)
        #self.move(800, 0)
        #reminder.setGeometry(800, 0, 100, 50)
        #self.setCentralWidget(self.reminder)
        self.parent.reminderWin.show()
        self.parent.reminderWin.setGeometry(800, 0, 100, 50)
        #time.sleep(1)
        self.mouse_listener = mouse.Listener(
                on_move=self.on_move,
                on_click=self.on_click,
                on_scroll=self.on_scroll)
        #time.sleep(1)
        self.mouse_listener.start()
        #
        self.kb_listener = keyboard.Listener(
                on_press=self.on_press,
                on_release=self.on_release)
        self.kb_listener.start()
        #time.sleep(1)
        #self.mouse_listener.join()
        #self.kb_listener.join()

    def cancel_recording(self):
        global record_over
        record_over = True
        #self.showMinimized()
        self.hide()

    def saveRecordFile(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            'Save File',
            '',
            "Process Record Files (*.prf)"
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.actionRecord, f)
                # self.rebuildHTML()
            except IOError:
                QtGui.QMessageBox.information(
                    self,
                    "Unable to open file: %s" % filename
                )

    def skill_tutorial(self):
        print("start tutorial....")
        # direct directly to the github web site.

    def start_skill(self):
        self.skillGUI.set_cloud(self.session, self.cog)
        self.skillGUI.show()
        # self.skillGUI.skFCDiagram.show()

    def set_cloud(self, session, cog):
        self.session = session
        self.cog = cog

