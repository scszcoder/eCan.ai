import logging
import colorlog
from logging.handlers import RotatingFileHandler
import os
from app_context import AppContext
from config.constants import APP_NAME
from config.app_info import app_info
import traceback

# ====== 集成 TRACE 日志等级 ======
TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")

def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)
logging.Logger.trace = trace
# ====== END ======

login = None
top_web_gui = None
class LoggerHelper:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LoggerHelper, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        print("init logger helper object")
        appdata_path = app_info.appdata_path
        runlogs_dir = appdata_path + "/runlogs"
        if not os.path.isdir(runlogs_dir):
            os.mkdir(runlogs_dir)
            print("create runlogs directory ", runlogs_dir)
        else:
            print(f"runlogs {runlogs_dir} directory is existed")

        self.setup(APP_NAME, appdata_path + "/runlogs/" + APP_NAME + ".log", logging.DEBUG)

    def setup(self, log_name, log_file, level):
        self.logger = logging.getLogger(log_name)
        self.logger.setLevel(level)
        self.logger.propagate = False

        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            console_formatter = colorlog.ColoredFormatter(
                "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "bold_red",
                    "TRACE": "white",
                },
                reset=True,
                secondary_log_colors={},
                style="%"
            )
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

        if not any(isinstance(h, RotatingFileHandler) for h in self.logger.handlers):
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 10, backupCount=5)
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

    def _join_message_args(self, message, *args):
        def safe_str(x):
            try:
                return str(x)
            except Exception:
                return f"<Unprintable {type(x).__name__}>"
        # 如果 message 是字符串且 args 只有一个且包含 %，则用原生格式化
        if isinstance(message, str) and args and "%" in message:
            try:
                return message % args
            except Exception:
                pass  # 格式化失败则退回拼接
        return " ".join(safe_str(x) for x in (message,) + args)

    def trace(self, message, *args, **kwargs):
        if hasattr(self, 'logger'):
            msg = self._join_message_args(message, *args)
            self.logger.trace(msg, **kwargs)

    def debug(self, message, *args, **kwargs):
        if hasattr(self, 'logger'):
            msg = self._join_message_args(message, *args)
            self.logger.debug(msg, **kwargs)

    def info(self, message, *args, **kwargs):
        if hasattr(self, 'logger'):
            msg = self._join_message_args(message, *args)
            self.logger.info(msg, **kwargs)

    def warning(self, message, *args, **kwargs):
        if hasattr(self, 'logger'):
            msg = self._join_message_args(message, *args)
            self.logger.warning(msg, **kwargs)

    def error(self, message, *args, **kwargs):
        if hasattr(self, 'logger'):
            msg = self._join_message_args(message, *args)
            self.logger.error(msg, **kwargs)

    def critical(self, message, *args, **kwargs):
        if hasattr(self, 'logger'):
            msg = self._join_message_args(message, *args)
            self.logger.critical(msg, **kwargs)


logger_helper = LoggerHelper()

def get_top_web_gui():
    global top_web_gui
    return top_web_gui

def set_top_web_gui(web_gui):
    global top_web_gui
    top_web_gui = web_gui

def get_agent_by_id(agent_id):
    # global top_web_gui
    from gui.MainGUI import MainWindow
    app_ctx = AppContext()
    main_window: MainWindow = app_ctx.main_window
    agent = next((ag for ag in main_window.agents if ag.card.id == agent_id), None)
    # print("by id found agent: ", agent_id, agent.card)
    return agent

def get_traceback(e, eType="Error"):
    traceback_info = traceback.extract_tb(e.__traceback__)
    # Extract the file name and line number from the last entry in the traceback
    if traceback_info:
        ex_stat = f"{eType}:" + traceback.format_exc() + " " + str(e)
    else:
        ex_stat = f"{eType}: traceback information not available:" + str(e)
    return ex_stat