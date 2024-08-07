import asyncio
import json
import os
import platform
import queue
import threading
import time
from asyncio import Event
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QLabel, QApplication, QPushButton, QHBoxLayout, QMessageBox, \
    QFileDialog, QDialog, QVBoxLayout
from pynput import keyboard, mouse

import pyautogui

from gui.SkillGUI import SkillGUI
from utils.logger_helper import logger_helper

counter = 0
record_over = False


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
        self.loop = None
        self.thread = None
        self.stop_event = threading.Event()
        self.last_screenshot_time = time.time()
        self.frame_count = 0
        self.listeners_running = False
        # 创建一个队列来存储事件
        self.event_queue = queue.Queue()

        self.listener_list = []

    def mousePressEvent(self, event):
        self.oldPos = event.globalPos()

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
        """
        todo 单独线程 需要修改
        """
        while not self.record_over:
            # 从队列中获取事件
            event_type, x, y, dx, dy, button = self.event_queue.get()
            if event_type is not None:
                await self.screenshot(event_type, x, y, dx, dy, button)
            # 处理完事件后通知队列
            self.event_queue.task_done()
            await asyncio.sleep(0.01)

    async def save_screenshot(self):
        """
        todo 单独线程 需要修改
        """
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
        self.listeners_running = False
        msgBox = QMessageBox()
        msgBox.setText(QApplication.translate("QMessageBox", "Are you done with showing the process to be automated?"))
        msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        ret = msgBox.exec()

        if ret == QMessageBox.Yes:
            print("done with demo...")
            self.saveRecordFile()
        self.main_win.show()
        self.show()
        self.stop_thread_listeners()

    async def _start_listener(self, listener_class, callback_dict):
        """通用监听器启动函数"""

        async def run_listener():
            with listener_class(**callback_dict) as listener:
                await asyncio.sleep(0)  # 确保异步上下文切换
                listener.join()

        return asyncio.create_task(run_listener())

    async def start_listeners(self):
        """启动鼠标和键盘监听器"""
        if self.listeners_running:
            print("Listeners are already running.")
            return
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.listeners_running = True
        # 启动鼠标监听器
        mouse_listener = await self._start_listener(mouse.Listener, {
            'on_move': self.on_move,
            'on_click': self.on_click,
            'on_scroll': self.on_scroll,
        })

        # 如果不是 macOS，则启动键盘监听器
        if platform.system() != 'Darwin':
            keyboard_listener = await self._start_listener(keyboard.Listener, {
                'on_press': self.on_press,
                'on_release': self.on_release,
            })
            self.listener_list.append(keyboard_listener)
        self.listener_list.append(mouse_listener)
        process_events = self.process_events()
        self.listener_list.append(process_events)
        save_screenshot = self.save_screenshot()
        self.listener_list.append(save_screenshot)
        await asyncio.gather(*self.listener_list)

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
            self.start_thread_listeners()
        except Exception as e:
            logger_helper.error(f"Failed to start listeners: {e}")

    def stop_thread_listeners(self):
        self.stop_event.set()  # 设置停止标志
        if self.thread and self.thread.is_alive():
            # 等待线程结束，或者你可以尝试加入超时机制
            self.thread.join()

    def start_thread_listeners(self):
        self.stop_event.clear()  # 清除停止标志
        self.thread = threading.Thread(target=self.run_listeners)
        self.thread.start()

    def run_listeners(self):
        asyncio.run(self.start_listeners())

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
