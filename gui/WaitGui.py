import sys
import asyncio
import os
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton

class KeyPressFilter(QtCore.QObject):

    def eventFilter(self, widget, event):
        if event.type() == QtCore.QEvent.KeyPress:
            text = event.text()
            if event.modifiers():
                text = event.keyCombination().key().name.decode(encoding="utf-8")
            widget.label1.setText(text)
        return False

class WaitWindow(QtWidgets.QMainWindow):
    udp_message_received = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.mainWidget = QtWidgets.QWidget()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        # Create a QLabel to display the animated GIF
        self.setGeometry(300, 300, 16, 16)
        self.setWindowTitle("QMovie to show animated gif")

        self.label = QtWidgets.QLabel(self)
        self.label.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                        QtWidgets.QSizePolicy.Expanding)
        self.label.setAlignment(QtCore.Qt.AlignCenter)

        self.noteLabel = QtWidgets.QLabel("Waiing for Commander Connection.....", alignment=QtCore.Qt.AlignCenter)

        self.btn_start = QPushButton("Start Animation")
        self.btn_start.clicked.connect(self.start)

        self.btn_stop = QPushButton("Stop Animation")
        self.btn_stop.clicked.connect(self.stop)

        # positin the widgets
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(self.label)
        main_layout.addWidget(self.noteLabel)
        # main_layout.addWidget(self.btn_start)
        # main_layout.addWidget(self.btn_stop)

        # Load the animated GIF
        gif_path = "C:/Users/songc/PycharmProjects/ecbot/resource/images/icons/waiting3_spinner.gif"  # Replace with the path to your GIF file
        self.movie = QtGui.QMovie(gif_path, QtCore.QByteArray(), self)
        self.movie.setCacheMode(QtGui.QMovie.CacheAll)
        self.movie.setSpeed(120)
        self.label.setMovie(self.movie)
        self.movie.start()

        # self.eventFilter = KeyPressFilter(parent=self)
        # self.installEventFilter(self.eventFilter)

        self.moveStopSc = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+e'), self)
        self.moveStopSc.activated.connect(lambda: self.movie.stop())

        self.moveStartSc = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+s'), self)
        self.moveStartSc.activated.connect(lambda: self.movie.start())

        self.hideSc = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+h'), self)
        self.hideSc.activated.connect(lambda: self.hide())

        # Start the animation
        # self.movie.start()

        self.mainWidget.setLayout(main_layout)
        self.setCentralWidget(self.mainWidget)


    def start(self):
        """sart animnation"""
        print("start animation")
        self.movie.start()

    def stop(self):
        """stop the animation"""
        print("stopp animation")
        self.movie.stop()


        # Create a QTimer to periodically check for UDP messages
    #     self.timer = QtCore.QTimer(self)
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