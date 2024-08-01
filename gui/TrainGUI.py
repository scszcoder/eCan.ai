import asyncio
import json
import os
import platform
import queue
import threading
import time
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QLabel, QApplication, QPushButton, QHBoxLayout, QMessageBox, \
    QFileDialog, QDialog, QVBoxLayout
from pynput import keyboard, mouse

import pyautogui
import pyscreenshot as ImageGrab

from gui.SkillGUI import SkillGUI
from utils.logger_helper import logger_helper

counter = 0
record_over = False


class StopRecordDialog(QDialog):
    def __init__(self):
        super(StopRecordDialog, self).__init__()
        # 创建提示标签
        self.prompt_label = QLabel(self.tr("Are you done with showing the process to be automated?"))

        # 创建带有翻译文本的“是”和“否”按钮
        self.yes_button = QPushButton(self.tr("Yes"))
        self.no_button = QPushButton(self.tr("No"))

        # 连接按钮点击信号与槽函数
        self.yes_button.clicked.connect(self.accept)
        self.no_button.clicked.connect(self.reject)

        # 创建一个垂直布局用于对话框
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.prompt_label)
        main_layout.addWidget(self.yes_button)
        main_layout.addWidget(self.no_button)

        self.setLayout(main_layout)

# 使用 QDialog 实现自定义提示弹窗
class CustomDialog(QDialog):
    def __init__(self, parent=None):
        super(CustomDialog, self).__init__(parent)

        self.setWindowTitle(QApplication.translate("QLabel", "Tips"))
        self.setWindowFlags(Qt.WindowStaysOnTopHint)  # 使弹窗始终在最前端

        layout = QVBoxLayout()
        self.label = QLabel(QApplication.translate("QLabel", "Are you done with showing the process to be automated?"))
        layout.addWidget(self.label)

        self.ok_button = QPushButton(QApplication.translate("QPushButton", "Ok"))
        self.ok_button.clicked.connect(self.submitData)
        layout.addWidget(self.ok_button)

        self.setLayout(layout)

    def submitData(self):
        self.close()

class TrainDialogWin(QMainWindow):
    def __init__(self, train_win):
        super(TrainDialogWin, self).__init__(train_win)

        self.mainWidget = QWidget()
        self.reminder_label = QLabel(QApplication.translate("QLabel", "press <Esc> key to end recording"),
                                     alignment=Qt.AlignLeft)

        self.start_button = QPushButton(QApplication.translate("QPushButton", "Start Training"))
        self.cancel_button = QPushButton(QApplication.translate("QPushButton", "Cancel"))

        self.rLayout = QHBoxLayout(self)
        self.rLayout.addWidget(self.reminder_label)
        self.mainWidget.setLayout(self.rLayout)
        self.setCentralWidget(self.mainWidget)


class ReminderWin(QMainWindow):
    def __init__(self, main_win):
        super(ReminderWin, self).__init__(main_win)

        self.mainWidget = QWidget()
        self.reminder_label = QLabel(QApplication.translate("QLabel", "press <Esc> key to end recording"),
                                     alignment=Qt.AlignLeft)
        self.rLayout = QHBoxLayout()
        if platform.system() == 'Darwin':
            self.cancel_button = QPushButton(QApplication.translate("QPushButton", "Cancel"))
            self.cancel_button.clicked.connect(main_win.trainNewSkillWin.stop_record)
            self.rLayout.addWidget(self.cancel_button)
        self.rLayout.addWidget(self.reminder_label)
        self.mainWidget.setLayout(self.rLayout)
        self.setCentralWidget(self.mainWidget)
        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowStaysOnTopHint)

class TrainNewWin(QMainWindow):
    def __init__(self, main_win):
        super(TrainNewWin, self).__init__(main_win)
        self.mouse_listener = None
        self.keyboard_listener = None

        self.record_over = False
        self.oldPos = None
        # self.temp_dir = None
        self.root_temp_dir = main_win.homepath + "/resource/skills/temp/"
        self.temp_dir = ''
        self.newSkill = None
        self.main_win = main_win
        self.mainWidget = QWidget()
        self.trainDialog = TrainDialogWin(self)
        self.session = None
        self.cog = None

        self.start_tutor_button = QPushButton(QApplication.translate("QPushButton", "Tutorial"))
        self.start_demo_button = QPushButton(QApplication.translate("QPushButton", "Start Demo"))
        self.start_skill_button = QPushButton(QApplication.translate("QPushButton", "Define Skill"))
        self.cancel_button = QPushButton(QApplication.translate("QPushButton", "Cancel"))

        self.bLayout = QHBoxLayout(self)
        self.rLayout = QHBoxLayout(self)

        # self.label = QLabel()
        self.bLayout.addWidget(self.start_tutor_button)
        self.bLayout.addWidget(self.start_demo_button)
        self.bLayout.addWidget(self.start_skill_button)
        self.bLayout.addWidget(self.cancel_button)

        self.start_tutor_button.clicked.connect(self.skill_tutorial)
        self.start_demo_button.clicked.connect(self.start_listening)
        self.start_skill_button.clicked.connect(self.start_skill)
        self.cancel_button.clicked.connect(self.cancel_recording)

        self.mainWidget.setLayout(self.bLayout)
        self.setCentralWidget(self.mainWidget)

        self.skillGUI = SkillGUI(self)

        self.screen_image_stream = []
        self.record = []
        self.steps = 0
        self.actionRecord = []
        self.executor = ThreadPoolExecutor()
        self.loop = asyncio.get_event_loop()
        self.last_screenshot_time = time.time()
        self.frame_count = 0
        self.listeners_running = False
        # 创建一个队列来存储事件
        self.event_queue = queue.Queue()

    def mousePressEvent(self, event):
        self.oldPos = event.globalPos()

    def mouseMoveEvent(self, event):
        delta = QPoint(event.globalPos() - self.oldPos)
        # self.move(self.x() + delta.x(), self.y() + delta.y())
        # self.oldPos = event.globalPos()
        # Update the origin for next time.
        # self.last_x = event.x()
        # self.last_y = event.y()

    def mouseReleaseEvent(self, e):
        delta = QPoint(e.globalPos() - self.oldPos)
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
        if event.key() == Qt.Key_Escape:
            self.showMinimized()

    def on_move(self, x, y):
        print("监听到的坐标： ", x, y)
        if self.record_over:
            self.record_over = False
            return False
        else:
            current_time = time.time()
            time_since_last_screenshot = current_time - self.last_screenshot_time
            if time_since_last_screenshot > 0.3:
                print('Pointer moved to {0}'.format((x, y)))
                self.event_queue.put(('move', x, y, None, None, None))
                self.last_screenshot_time = current_time

    async def process_events(self):
        while not self.record_over:
            # 从队列中获取事件
            event_type, x, y, dx, dy, button = self.event_queue.get()
            if event_type is not None:
                await self.screenshot(event_type, x, y, dx, dy, button)
            # 处理完事件后通知队列
            self.event_queue.task_done()
            await asyncio.sleep(0.01)

    async def save_screenshot(self):
        while not self.record_over:
            if len(self.screen_image_stream) >= 5:
                for stream in self.screen_image_stream:
                    stream['stream'].save(stream['file_name'])
            await asyncio.sleep(1)

        if self.record_over:
            if len(self.screen_image_stream) > 0:
                for stream in self.screen_image_stream:
                    stream['stream'].save(stream['file_name'])

    async def screenshot(self, option: str, x: int = None, y: int = None, dx: any = None, dy: any = None,
                         button: any = None):
        self.steps += 1
        now = datetime.now()
        fname = self.temp_dir + option + "_step" + str(self.steps) + '_' + str(now.timestamp()) + ".png"
        print("目前的操作：", option, x, y, dx, dy, button, self.steps, fname)
        im = pyautogui.screenshot(fname)
        self.screen_image_stream.append({'file_name': fname, 'stream': im})
        button_name = None
        if button is not None:
            button_name = button.name
        action = {
            'step': self.steps,
            'file_name': fname,
            'type': option,
            'time': now.timestamp(),
            'x': x,
            'y': y,
            'dx': dx,
            'dy': dy,
            'button': button_name
        }
        self.actionRecord.append(action)


    def on_click(self, x, y, button, pressed):

        if self.record_over:
            return False
        print('{0} at {1}'.format('Pressed' if pressed else 'Released', (x, y)))
        if self.record_over:
            return False
        else:
            #  当按键松了后才进行记录事件
            if not pressed:
                self.event_queue.put(('click', x, y, None, None, button))

    def on_scroll(self, x, y, dx, dy):
        print("scroll:", x, y, dx, dy)
        if self.record_over:
            return False
        else:
            current_time = time.time()
            time_since_last_screenshot = current_time - self.last_screenshot_time
            if time_since_last_screenshot > 0.5:
                print('Scrolled {0} at {1} at {2}'.format(
                    'down' if dy < 0 else 'up',
                    (x, y), (dx, dy)))
                self.event_queue.put(('scroll', x, y, dx, dy, None))
                self.last_screenshot_time = current_time

    def on_press(self, key):
        try:
            print('alphanumeric key {0} pressed'.format(key.char))
        except AttributeError:
            print('special key {0} pressed'.format(key))

    def on_release(self, key):
        print('{0} released'.format(key))
        if key == keyboard.Key.esc:
            # Stop listener
            self.stop_record()
            return False

    def stop_record(self):
        self.record_over = True
        self.main_win.reminderWin.hide()
        # dialog = CustomDialog(self)
        # dialog.exec()
        msgBox = QMessageBox()
        msgBox.setText(QApplication.translate("QMessageBox", "Are you done with showing the process to be automated?"))
        msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        ret = msgBox.exec()
        if ret == QMessageBox.Yes:
            print("done with demo...")
            self.saveRecordFile()

    async def _start_listener(self, listener_class, callback_dict):
        """通用监听器启动函数"""

        def run_listener():
            with listener_class(**callback_dict) as listener:
                listener.join()

        self.loop.run_in_executor(self.executor, run_listener)

    async def start_listeners(self):
        """启动鼠标和键盘监听器"""
        if self.listeners_running:
            print("Listeners are already running.")
            return
        listener_list = []
        self.listeners_running = True

        mouse_listener = self._start_listener(mouse.Listener, {
            'on_move': self.on_move,
            'on_click': self.on_click,
            'on_scroll': self.on_scroll,
        })
        listener_list.append(mouse_listener)
        if platform.system() != 'Darwin':
            keyboard_listener = self._start_listener(keyboard.Listener, {
                'on_press': self.on_press,
                'on_release': self.on_release,
            })
            listener_list.append(keyboard_listener)
        process_events = self.process_events()
        listener_list.append(process_events)
        save_screenshot = self.save_screenshot()
        listener_list.append(save_screenshot)
        await asyncio.gather(*listener_list)

    def start_listening(self):
        try:
            self.record_over = False
            self.main_win.reminderWin.show()
            self.main_win.reminderWin.setGeometry(800, 0, 100, 50)
            print("Starting input event listeners...")
            self.temp_dir = self.root_temp_dir + time.strftime("%Y%m%d-%H%M%S") + "/"
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir)
            # 创建任务
            self.main_win.hide()
            self.hide()
            self.loop.create_task(self.start_listeners())
        except Exception as e:
            logger_helper.error(f"Failed to start listeners: {e}")

    def cancel_recording(self):
        self.record_over = True
        # self.showMinimized()
        self.hide()

    def saveRecordFile(self):
        filename, _ = QFileDialog.getSaveFileName(
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
                QMessageBox.information(self, "Unable to open file: %s" % filename)

    def skill_tutorial(self):
        print("start tutorial....")
        # direct directly to the github web site.

    def start_skill(self):
        self.skillGUI.set_cloud(self.session, self.cog)
        self.skillGUI.set_edit_mode("new")
        self.skillGUI.show()
        # self.skillGUI.skFCDiagram.show()

    def set_cloud(self, session, cog):
        self.session = session
        self.cog = cog
