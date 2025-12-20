
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
    """Metaclass for AppContext, supports class-level attribute access"""

    def __getattr__(cls, name):
        """Support direct attribute access via AppContext.xxx"""
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
        # Global important instances
        self.app: Optional[QApplication] = None           # QApplication instance
        self.main_window: Optional[MainWindow] = None   # Main window instance
        self.web_gui: Optional[WebGUI] = None       # Web GUI instance
        self.logger: Optional[Logger] = None        # Logger instance
        self.config: Optional[AppSettings] = None        # Config object
        self.thread_pool: Optional[QThreadPool] = None   # Thread pool
        self.app_info: Optional[AppInfo] = None      # Application info
        self.main_loop: Optional[AbstractEventLoop] = None     # Main loop instance
        self.login: Optional[Login] = None  # Login instance
        self.playwright_browsers_path: Optional[str] = None    # Playwright browsers path
        # ... Other global objects

    @classmethod
    def get_instance(cls):
        """Get singleton instance"""
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __getattr__(self, name):
        """Instance-level attribute access"""
        if name.startswith('_'):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        # If attribute doesn't exist, return None (avoid raising exception)
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
        """Get Playwright browsers path (unified interface)"""
        # Prefer getting from environment variable (real-time status)
        from agent.playwright.core.setup import get_playwright_browsers_path
        return get_playwright_browsers_path()

    def set_url_scheme_handler(self, handler):
        """Set URL scheme handler"""
        self.url_scheme_handler = handler

    # Class method support - can directly use AppContext.get_xxx() to access
    @classmethod
    def get_app(cls):
        """Get QApplication instance"""
        return cls.get_instance().app

    @classmethod
    def get_logger(cls):
        """Get logger instance"""
        return cls.get_instance().logger

    @classmethod
    def get_config(cls):
        """Get config instance"""
        return cls.get_instance().config

    @classmethod
    def get_main_window(cls):
        """Get main window instance"""
        return cls.get_instance().main_window

    @classmethod
    def get_web_gui(cls):
        """Get Web GUI instance"""
        return cls.get_instance().web_gui

    @classmethod
    def get_app_info(cls):
        """Get application info instance"""
        return cls.get_instance().app_info

    @classmethod
    def get_main_loop(cls):
        """Get main loop instance"""
        return cls.get_instance().main_loop

    @classmethod
    def get_login(cls):
        """Get login instance"""
        return cls.get_instance().login

    @classmethod
    def get_thread_pool(cls):
        """Get thread pool instance"""
        return cls.get_instance().thread_pool
    
    @classmethod
    def get_auth_manager(cls):
        """Get authentication manager instance"""
        login = cls.get_login()
        if login and hasattr(login, 'auth_manager'):
            return login.auth_manager
        return None

    def cleanup(self):
        """Clean up all references in AppContext"""
        try:
            # Clean up various instance references
            self.main_window = None
            
            # Note: Don't clean up app, logger, thread_pool, login, as they may still be needed before application fully exits
            
            return True
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error during AppContext cleanup: {e}")
            return False

    @classmethod
    def cleanup_instance(cls):
        """Class method: Clean up AppContext instance"""
        instance = cls.get_instance()
        return instance.cleanup()

    @classmethod
    def safe_get_login(cls):
        """Safely get login object, raise meaningful exception if None"""
        login = cls.get_login()
        if login is None:
            raise RuntimeError("Login object is not available - user may have logged out or system not initialized")
        return login

    @classmethod
    def safe_get_main_window(cls):
        """Safely get main_window object, raise meaningful exception if None"""
        main_window = cls.get_main_window()
        if main_window is None:
            raise RuntimeError("MainWindow is not available - user may have logged out or system not initialized")
        return main_window

    @classmethod
    def safe_get_web_gui(cls):
        """Safely get web_gui object, raise meaningful exception if None"""
        web_gui = cls.get_web_gui()
        if web_gui is None:
            raise RuntimeError("WebGUI is not available - user may have logged out or system not initialized")
        return web_gui

    # You can continue to add more set/get methods

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