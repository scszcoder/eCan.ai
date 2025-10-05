
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Any, Dict

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


class AppContextMeta(type):
    """AppContext 的元类，支持类级别的属性访问"""

    def __getattr__(cls, name):
        """支持 AppContext.xxx 直接访问属性"""
        if name.startswith('_'):
            raise AttributeError(f"'{cls.__name__}' object has no attribute '{name}'")

        instance = cls.get_instance()
        if hasattr(instance, name):
            return getattr(instance, name)
        return None


class AppContext(metaclass=AppContextMeta):
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

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __getattr__(self, name):
        """实例级别的属性访问"""
        if name.startswith('_'):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        # 如果属性不存在，返回 None（避免抛出异常）
        return None

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

    def set_url_scheme_handler(self, handler):
        """Set URL scheme handler"""
        self.url_scheme_handler = handler

    # 类方法支持 - 可以直接使用 AppContext.get_xxx() 访问
    @classmethod
    def get_app(cls):
        """获取 QApplication 实例"""
        return cls.get_instance().app

    @classmethod
    def get_logger(cls):
        """获取日志器实例"""
        return cls.get_instance().logger

    @classmethod
    def get_config(cls):
        """获取配置实例"""
        return cls.get_instance().config

    @classmethod
    def get_main_window(cls):
        """获取主窗口实例"""
        return cls.get_instance().main_window

    @classmethod
    def get_web_gui(cls):
        """获取 Web GUI 实例"""
        return cls.get_instance().web_gui

    @classmethod
    def get_app_info(cls):
        """获取应用信息实例"""
        return cls.get_instance().app_info

    @classmethod
    def get_main_loop(cls):
        """获取主循环实例"""
        return cls.get_instance().main_loop

    @classmethod
    def get_login(cls):
        """获取登录实例"""
        return cls.get_instance().login

    @classmethod
    def get_thread_pool(cls):
        """获取线程池实例"""
        return cls.get_instance().thread_pool

    def cleanup(self):
        """清理 AppContext 中的所有引用"""
        try:
            # 清理各种实例引用
            self.main_window = None
            
            # 注意：不清理 app, logger, thread_pool, login，因为它们可能在应用完全退出前还需要使用
            
            return True
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error during AppContext cleanup: {e}")
            return False

    @classmethod
    def cleanup_instance(cls):
        """类方法：清理 AppContext 实例"""
        instance = cls.get_instance()
        return instance.cleanup()

    @classmethod
    def safe_get_login(cls):
        """安全获取 login 对象，如果为 None 则抛出有意义的异常"""
        login = cls.get_login()
        if login is None:
            raise RuntimeError("Login object is not available - user may have logged out or system not initialized")
        return login

    @classmethod
    def safe_get_main_window(cls):
        """安全获取 main_window 对象，如果为 None 则抛出有意义的异常"""
        main_window = cls.get_main_window()
        if main_window is None:
            raise RuntimeError("MainWindow is not available - user may have logged out or system not initialized")
        return main_window

    @classmethod
    def safe_get_web_gui(cls):
        """安全获取 web_gui 对象，如果为 None 则抛出有意义的异常"""
        web_gui = cls.get_web_gui()
        if web_gui is None:
            raise RuntimeError("WebGUI is not available - user may have logged out or system not initialized")
        return web_gui

    # 你可以继续添加更多 set/get 方法

    @classmethod
    def get_useful_context(cls) -> "RunContext":
        """Return a lazy, namespaced context for external skills.

        Skills should call namespaces on demand, e.g.:
            core = run_context.core()
            graph = run_context.graph()
            llm = run_context.llm()
            mcp = run_context.mcp()
            log = run_context.log()

        This avoids heavy imports at module import time and limits the exposed surface.
        """
        inst = cls.get_instance()
        try:
            playwright_path = inst.get_playwright_browsers_path()
        except Exception:
            playwright_path = None

        return RunContext(
            app=inst.app,
            main_window=inst.main_window,
            web_gui=inst.web_gui,
            logger=inst.logger,
            config=inst.config,
            thread_pool=inst.thread_pool,
            app_info=inst.app_info,
            main_loop=inst.main_loop,
            login=inst.login,
            playwright_browsers_path=playwright_path,
            mcp_client=(inst.main_window.mcp_client if getattr(inst.main_window, "mcp_client", None) is not None else None) if inst.main_window else None,
        )


class RunContext:
    """Lazy, namespaced context exposed to external skills.

    Namespaces (methods): core(), graph(), llm(), mcp(), log()
    Metadata and common instances are available as attributes.
    """

    def __init__(
        self,
        *,
        app: Any = None,
        main_window: Any = None,
        web_gui: Any = None,
        logger: Any = None,
        config: Any = None,
        thread_pool: Any = None,
        app_info: Any = None,
        main_loop: Any = None,
        login: Any = None,
        playwright_browsers_path: Optional[str] = None,
        mcp_client: Any = None,
    ) -> None:
        self.app = app
        self.main_window = main_window
        self.web_gui = web_gui
        self.logger = logger
        self.config = config
        self.thread_pool = thread_pool
        self.app_info = app_info
        self.main_loop = main_loop
        self.login = login
        self.playwright_browsers_path = playwright_browsers_path
        self.mcp_client = mcp_client
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._api_version = "ecan_context_v1"

    # Dict-like helpers for convenience (optional)
    def __getitem__(self, key: str) -> Any:
        # Allow run_context["core"] to return the core namespace
        if key == "core":
            return self.core()
        if key == "graph":
            return self.graph()
        if key == "llm":
            return self.llm()
        if key == "mcp":
            return self.mcp()
        if key == "log":
            return self.log()
        # Allow access to attributes like app, logger, etc.
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self.__getitem__(key)
        except Exception:
            return default

    @property
    def api_version(self) -> str:
        return self._api_version

    # Namespaces
    def core(self) -> Dict[str, Any]:
        if "core" not in self._cache:
            from agent.ec_skill import EC_Skill, WorkFlowContext, NodeState, node_builder, node_wrapper
            try:
                from agent.ec_skills.dev_defs import BreakpointManager
            except Exception:
                # Fallback if not available
                class BreakpointManager:  # type: ignore
                    pass
            self._cache["core"] = {
                "EC_Skill": EC_Skill,
                "WorkFlowContext": WorkFlowContext,
                "NodeState": NodeState,
                "node_builder": node_builder,
                "node_wrapper": node_wrapper,
                "BreakpointManager": BreakpointManager,
                "api_version": self._api_version,
            }
        return self._cache["core"]

    def graph(self) -> Dict[str, Any]:
        if "graph" not in self._cache:
            from langgraph.graph import StateGraph
            from langgraph.constants import END
            from langgraph.runtime import Runtime
            from langgraph.store.base import BaseStore
            from langgraph.errors import GraphInterrupt
            from langgraph.types import interrupt
            self._cache["graph"] = {
                "StateGraph": StateGraph,
                "END": END,
                "Runtime": Runtime,
                "BaseStore": BaseStore,
                "GraphInterrupt": GraphInterrupt,
                "interrupt": interrupt,
            }
        return self._cache["graph"]

    def llm(self) -> Dict[str, Any]:
        if "llm" not in self._cache:
            from agent.ec_skills.llm_hooks.llm_hooks import llm_node_with_raw_files
            from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync, try_parse_json
            self._cache["llm"] = {
                "llm_node_with_raw_files": llm_node_with_raw_files,
                "run_async_in_sync": run_async_in_sync,
                "try_parse_json": try_parse_json,
            }
        return self._cache["llm"]

    def mcp(self) -> Dict[str, Any]:
        if "mcp" not in self._cache:
            from agent.mcp.local_client import mcp_call_tool
            self._cache["mcp"] = {
                "mcp_call_tool": mcp_call_tool,
            }
        return self._cache["mcp"]

    def log(self) -> Dict[str, Any]:
        if "log" not in self._cache:
            from utils.logger_helper import logger_helper as logger, get_traceback
            self._cache["log"] = {
                "logger": logger,
                "get_traceback": get_traceback,
            }
        return self._cache["log"]