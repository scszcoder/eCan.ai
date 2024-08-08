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

from gui.SkillGUI import SkillGUI
from utils.logger_helper import logger_helper

counter = 0
listeners_running = False


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

        self.temp_dir = None
        self.skillGUI = None
        self.rLayout = None
        self.bLayout = None
        self.cancel_button = None
        self.start_skill_button = None
        self.start_demo_button = None
        self.start_tutor_button = None

        self.root_temp_dir = main_win.homepath + "/resource/skills/temp/"
        self.main_win = main_win
        self.mainWidget = QWidget()
        self.trainDialog = TrainDialogWin(self)
        self.session = None
        self.cog = None
        self.screen_image_stream = []
        self.steps = 0
        self.actionRecord = []
        self.executor = ThreadPoolExecutor()
        self.loop_listener = None
        self.loop_screenshot = None
        self.thread_listener = None
        self.thread_screenshot = None
        self.stop_event = threading.Event()
        self.last_screenshot_time = time.time()
        self.listeners_running = False
        # 创建一个队列来存储事件
        self.event_queue = queue.Queue()
        self.listener_list = []
        self.screenshot_list = []
        self.init_gui()

    def init_gui(self):
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

    async def _start_listener(self, listener_class, callback_dict):
        def run_listener():
            with listener_class(**callback_dict) as listener:
                listener.join()

        self.loop_listener.run_in_executor(self.executor, run_listener)

    def on_move(self, x, y):
        if not self.listeners_running:
            return False
        else:
            current_time = time.time()
            time_since_last_screenshot = current_time - self.last_screenshot_time
            if time_since_last_screenshot > 0.3:
                print('Pointer moved to {0}'.format((x, y)))
                self.event_queue.put(('move', x, y, None, None, None))
                self.last_screenshot_time = current_time

    async def process_events(self):
        while self.listeners_running:
            # 从队列中获取事件
            try:
                if not self.event_queue.empty():
                    event_type, x, y, dx, dy, button = self.event_queue.get()
                    self.screenshot(event_type, x, y, dx, dy, button)
                    # 处理完事件后通知队列
                    self.event_queue.task_done()
            except queue.Empty:
                pass
            finally:
                await asyncio.sleep(0.01)

    async def save_screenshot(self):
        while self.listeners_running:
            try:
                if len(self.screen_image_stream) >= 5:
                    for stream in self.screen_image_stream:
                        stream['stream'].save(stream['file_name'])
            finally:
                await asyncio.sleep(1)

        if not self.listeners_running:
            if len(self.screen_image_stream) > 0:
                for stream in self.screen_image_stream:
                    if not self.loop_screenshot.is_closed():
                        stream['stream'].save(stream['file_name'])

    def screenshot(self, option: str, x: int = None, y: int = None, dx: any = None, dy: any = None,
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
        if not self.listeners_running:
            return False
        print('{0} at {1}'.format('Pressed' if pressed else 'Released', (x, y)))
        if pressed:
            self.event_queue.put(('click', x, y, None, None, button))

    def on_scroll(self, x, y, dx, dy):
        if not self.listeners_running:
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
        if not self.listeners_running:
            return False
        try:
            print('alphanumeric key {0} pressed'.format(key.char))
        except AttributeError:
            print('special key {0} pressed'.format(key))

    def on_release(self, key):
        if not self.listeners_running:
            return False
        print('{0} released'.format(key))
        if key == keyboard.Key.esc:
            # Stop listener
            self.stop_record()
            return False

    def stop_record(self):
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

    async def start_screenshot(self):
        save_screenshot = asyncio.create_task(self.save_screenshot())
        self.screenshot_list.append(save_screenshot)
        await asyncio.gather(*self.screenshot_list)

    async def start_listeners(self):
        self.listeners_running = True
        process_events = asyncio.create_task(self.process_events())
        self.listener_list.append(process_events)
        mouse_listener = self._start_listener(mouse.Listener, {
            'on_move': self.on_move,
            'on_click': self.on_click,
            'on_scroll': self.on_scroll,
        })
        if platform.system() != 'Darwin':
            keyboard_listener = self._start_listener(keyboard.Listener, {
                'on_press': self.on_press,
                'on_release': self.on_release,
            })
            self.listener_list.append(asyncio.create_task(keyboard_listener))
        self.listener_list.append(asyncio.create_task(mouse_listener))
        await asyncio.gather(*self.listener_list)

    def start_listening(self):
        try:
            self.main_win.reminderWin.show()
            self.main_win.reminderWin.setGeometry(800, 0, 100, 50)
            print("Starting input event listeners...")
            self.temp_dir = self.root_temp_dir + time.strftime("%Y%m%d-%H%M%S") + "/"
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir)
            # 创建任务
            self.hide()
            self.main_win.hide()
            self.start_thread_listeners()
        except Exception as e:
            logger_helper.error(f"Failed to start listeners: {e}")

    def stop_thread_listeners(self):
        for task in self.screenshot_list:
            task.cancel()
        try:
            if not self.loop_screenshot.is_closed():
                self.loop_screenshot.run_until_complete(asyncio.gather(*self.screenshot_list))
        except Exception as e:
            print(f"Error during task cancellation: {e}")
        # 取消所有异步任务
        for task in self.listener_list:
            task.cancel()
        try:
            if not self.loop_listener.is_closed():
                self.loop_listener.run_until_complete(asyncio.gather(*self.listener_list))
        except Exception as e:
            print(f"Error during task cancellation: {e}")
        self.steps = 0
        self.listener_list.clear()
        self.stop_event.set()  # 设置停止标志
        if self.thread_listener and self.thread_listener.is_alive():
            self.thread_listener.join()
        if self.thread_screenshot and self.thread_screenshot.is_alive():
            self.thread_screenshot.join()

    def start_thread_listeners(self):
        self.thread_listener = threading.Thread(target=self.run_listeners)
        self.thread_listener.start()
        self.thread_screenshot = threading.Thread(target=self.run_screenshot)
        self.thread_screenshot.start()

    def run_screenshot(self):
        if self.loop_screenshot is None or self.loop_screenshot.is_closed():
            self.loop_screenshot = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop_screenshot)
        try:
            self.loop_screenshot.run_until_complete(self.start_screenshot())
        finally:
            self.loop_screenshot.close()

    def run_listeners(self):
        if self.loop_listener is None or self.loop_listener.is_closed():
            self.loop_listener = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop_listener)
        try:
            self.loop_listener.run_until_complete(self.start_listeners())
        finally:
            self.loop_listener.close()

    def cancel_recording(self):
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
