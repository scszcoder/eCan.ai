
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
        self.app = None           # QApplication 实例
        self.main_window = None   # 主窗口实例
        self.web_gui = None       # web gui实例
        self.logger = None        # 日志实例
        self.config = None        # 配置对象
        self.thread_pool = None   # 线程池
        self.app_info = None      # 应用信息
        self.main_loop = None     # 主循环实例
        self.login = None  # 登录实例
        # ... 其他全局对象

    def set_app(self, app):
        self.app = app

    def set_main_window(self, win):
        self.main_window = win

    def set_logger(self, logger):
        self.logger = logger

    def set_config(self, config):
        self.config = config

    def set_thread_pool(self, pool):
        self.thread_pool = pool

    def set_app_info(self, info):
        self.app_info = info

    def set_web_gui(self, gui):
        self.web_gui = gui

    def set_main_loop(self, loop):
        self.main_loop = loop

    def set_login(self, login):
        self.login = login

    # 你可以继续添加更多 set/get 方法 