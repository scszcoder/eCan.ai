
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication
    from gui.MainGUI import MainWindow
    from gui.WebGUI import WebGUI
    from logging import Logger
    from config.app_settings import AppSettings
    from PySide6.QtCore import QThreadPool
    from config.app_info import AppInfo
    from asyncio import AbstractEventLoop
    from gui.LoginoutGUI import Login



class AppContext:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(AppContext, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # 全局重要实例
        self.app: Optional[QApplication] = None           # QApplication 实例
        self.main_window: Optional[MainWindow] = None   # 主窗口实例
        self.web_gui: Optional[WebGUI] = None       # web gui实例
        self.logger: Optional[Logger] = None        # 日志实例
        self.config: Optional[AppSettings] = None        # 配置对象
        self.thread_pool: Optional[QThreadPool] = None   # 线程池
        self.app_info: Optional[AppInfo] = None      # 应用信息
        self.main_loop: Optional[AbstractEventLoop] = None     # 主循环实例
        self.login: Optional[Login] = None  # 登录实例
        self.playwright_browsers_path: Optional[str] = None    # Playwright 浏览器路径
        # ... 其他全局对象

    def set_app(self, app: QApplication):
        self.app = app

    def set_main_window(self, win: MainWindow):
        self.main_window = win

    def set_logger(self, logger: Logger):
        self.logger = logger

    def set_config(self, config: AppSettings):
        self.config = config

    def set_thread_pool(self, pool: QThreadPool):
        self.thread_pool = pool

    def set_app_info(self, info: AppInfo):
        self.app_info = info

    def set_web_gui(self, gui: WebGUI):
        self.web_gui = gui

    def set_main_loop(self, loop: AbstractEventLoop):
        self.main_loop = loop

    def set_login(self, login: Login):
        self.login = login

    def set_playwright_browsers_path(self, path: str):
        self.playwright_browsers_path = path

    def get_playwright_browsers_path(self) -> Optional[str]:
        """获取 Playwright 浏览器路径（统一接口）"""
        # 优先从环境变量获取（实时状态）
        from agent.playwright.core.setup import get_playwright_browsers_path
        return get_playwright_browsers_path()

    # 你可以继续添加更多 set/get 方法 