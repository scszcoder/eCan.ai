import sys
import asyncio
import os

from PySide6.QtCore import QObject, QEvent, Signal, Qt, QByteArray
from PySide6.QtGui import QMovie, QShortcut, QKeySequence
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QLabel, QSizePolicy, QVBoxLayout
from config.app_info import app_info


ecbhomepath = app_info.app_home_path

class KeyPressFilter(QObject):

    def eventFilter(self, widget, event):
        if event.type() == QEvent.KeyPress:
            text = event.text()
            if event.modifiers():
                text = event.keyCombination().key().name.decode(encoding="utf-8")
            widget.label1.setText(text)
        return False

class WaitWindow(QMainWindow):
    udp_message_received = Signal()

    def __init__(self):
        super().__init__()
        self.mainWidget = QWidget()
        self.setWindowFlags(Qt.FramelessWindowHint)
        # Create a QLabel to display the animated GIF
        self.setGeometry(300, 300, 16, 16)
        self.setWindowTitle(QApplication.translate("QWidget", "QMovie to show animated gif"))

        self.label = QLabel(self)
        self.label.setSizePolicy(QSizePolicy.Expanding,
                                        QSizePolicy.Expanding)
        self.label.setAlignment(Qt.AlignCenter)
        self.noteLabel = QLabel(QApplication.translate("QLabel", "Waiting for Commander Connection....."), alignment=Qt.AlignCenter)

        self.btn_start = QPushButton(QApplication.translate("QPushButton", "Start Animation"))
        self.btn_start.clicked.connect(self.start)

        self.btn_stop = QPushButton(QApplication.translate("QPushButton", "Stop Animation"))
        self.btn_stop.clicked.connect(self.stop)

        # positin the widgets
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.label)
        main_layout.addWidget(self.noteLabel)
        # main_layout.addWidget(self.btn_start)
        # main_layout.addWidget(self.btn_stop)

        # Load the animated GIF
        gif_path = ecbhomepath + "/resource/images/icons/waiting3_spinner.gif"  # Replace with the path to your GIF file
        print("GIF PATH:", gif_path)
        self.movie = QMovie(gif_path, QByteArray(), self)
        self.movie.setCacheMode(QMovie.CacheAll)
        self.movie.setSpeed(120)
        self.label.setMovie(self.movie)
        self.movie.start()

        # self.eventFilter = KeyPressFilter(parent=self)
        # self.installEventFilter(self.eventFilter)

        self.moveStopSc = QShortcut(QKeySequence('Ctrl+e'), self)
        self.moveStopSc.activated.connect(lambda: self.movie.stop())

        self.moveStartSc = QShortcut(QKeySequence('Ctrl+s'), self)
        self.moveStartSc.activated.connect(lambda: self.movie.start())

        self.hideSc = QShortcut(QKeySequence('Ctrl+h'), self)
        self.hideSc.activated.connect(lambda: self.hide())

        # Start the animation
        # self.movie.start()

        self.mainWidget.setLayout(main_layout)
        self.setCentralWidget(self.mainWidget)


    def start(self):
        """start animnation"""
        print("start animation")
        self.movie.start()

    def stop(self):
        """stop the animation"""
        print("stopp animation")
        self.movie.stop()


        # Create a QTimer to periodically check for UDP messages
    #     self.timer = QTimer(self)
    #     self.timer.timeout.connect(self.check_udp_message)
    #     self.timer.start(1000)  # Adjust the interval as needed
    #
    # def check_udp_message(self):
    #     # Implement your UDP message checking logic here
    #     # You can use asyncio to run this in the background
    #     async def udp_receiver():
    #         while True:
    #             # Receive UDP messages here
    #             # You can use asyncio's await to make this non-blocking
    #             await asyncio.sleep(1)  # Simulated UDP message check
    #             print("Checking for UDP messages...")
    #             if self.is_udp_message_matched():  # Replace with your condition
    #                 self.udp_message_received.emit()
    #                 return
    #
    #     asyncio.ensure_future(udp_receiver())
    #
    # def is_udp_message_matched(self):
    #     # Replace this with your actual logic to check for the UDP message match
    #     # Return True when the desired UDP message is received
    #     return False  # Placeholder condition