import logging
import colorlog
from logging.handlers import RotatingFileHandler

login = None
top_web_gui = None
class LoggerHelper:
    def __init__(self):
        print("init logger helper object")
        pass

    def setup(self, log_name, log_file, level):
        self.logger = logging.getLogger(log_name)
        self.logger.setLevel(level)

        console_formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
            reset=True,
            secondary_log_colors={},
            style="%"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 10, backupCount=5)
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def critical(self, message):
        self.logger.critical(message)


logger_helper = LoggerHelper()

def get_top_web_gui():
    global top_web_gui
    return top_web_gui

def set_top_web_gui(web_gui):
    global top_web_gui
    top_web_gui = web_gui

def get_agent_by_id(agent_id):
    global top_web_gui
    agent = next((ag for ag in top_web_gui.py_login.main_win.agents if ag.card.id == agent_id), None)
    print("by id foundagent: ", agent_id, agent.card)
    return agent