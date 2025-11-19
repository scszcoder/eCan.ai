#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Browser Resource Manager
Resolves resource conflicts between crawl4ai, browser_use, and Playwright
"""

from typing import Optional, Any, Dict, TYPE_CHECKING
import sys
import os
import asyncio
from threading import Lock

from agent.playwright import get_playwright_manager
from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger
from agent.ec_skills.llm_utils.llm_utils import run_async_in_worker_thread
from agent.agent_service import get_agent_by_id

if TYPE_CHECKING:
    from crawl4ai import AsyncWebCrawler
    from browser_use.browser import BrowserSession
    from browser_use.controller.service import Controller
    from browser_use.filesystem.file_system import FileSystem
    from browser_use.agent.service import Agent


class UnifiedBrowserManager:
    """Unified browser resource manager"""

    def __init__(self):
        self._lock = Lock()
        self._initialized = False
        self._initialization_error = None

        # Playwright manager
        self._playwright_manager = None

        # Component instances
        self._async_crawler = None
        self._browser_session = None
        self._browser_use_controller = None
        self._browser_use_file_system = None

        # Configuration
        self._crawler_config = None
        self._file_system_path = None
        self._browser_agent = None

        
    def initialize(self, crawler_config: Optional[Dict] = None, file_system_path: Optional[str] = None) -> bool:
        """Initialize unified browser manager"""
        with self._lock:
            if self._initialized:
                return True

            if self._initialization_error:
                logger.warning(f"Previous initialization failed: {self._initialization_error}")

            try:
                logger.info("🔧 Starting unified browser manager initialization...")

                if not self._init_playwright_manager():
                    raise RuntimeError("Playwright manager initialization failed")

                # Set environment variables immediately to ensure subsequent components can find browsers
                self._setup_crawler_environment()

                self._setup_crawler_config(crawler_config)
                self._file_system_path = file_system_path
                logger.info("crawler initialized.............")
                self._initialized = True
                self._initialization_error = None
                logger.info("✅ Unified browser manager initialized successfully")

                # Defer crawl4ai initialization; creating it here may bind to the GUI/qasync loop.
                return True

            except Exception as e:
                self._initialization_error = str(e)
                logger.error(f"❌ Unified browser manager initialization failed: {e}")
                return False
    
    def _init_playwright_manager(self) -> bool:
        """Initialize Playwright manager"""
        try:
            self._playwright_manager = get_playwright_manager()

            if not self._playwright_manager.is_initialized():
                logger.info("🔧 Initializing Playwright environment...")
                if not self._playwright_manager.lazy_init():
                    raise RuntimeError("Playwright environment initialization failed")

            logger.info("✅ Playwright manager ready")
            return True

        except Exception as e:
            logger.error(f"Playwright manager initialization failed: {e}")
            return False


    
    def _setup_crawler_config(self, crawler_config: Optional[Dict]):
        """Setup crawler configuration"""
        default_config = {
            'headless': False,
            'verbose': True,
            'viewport_width': 1920,
            'viewport_height': 1080
        }

        if crawler_config:
            default_config.update(crawler_config)

        self._crawler_config = default_config

    def _setup_crawler_environment(self):
        """Setup crawler runtime environment"""
        from pathlib import Path
        from agent.playwright.core.utils import core_utils

        # Ensure Playwright environment variables are set correctly so crawl4ai can find browsers
        if self._playwright_manager and self._playwright_manager.is_initialized():
            browsers_path = self._playwright_manager.get_browsers_path()
            if browsers_path:
                # Use unified environment variable setting function
                core_utils.set_environment_variables(Path(browsers_path))
                logger.debug(f"Set crawler environment variables using core_utils: {browsers_path}")
            else:
                logger.warning("Playwright manager is initialized but browser path is empty")
        else:
            logger.warning("Playwright manager is not initialized or not ready")






    
    def get_async_crawler(self) -> Optional["AsyncWebCrawler"]:
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get AsyncWebCrawler")
            return None

        # Do not create AsyncWebCrawler on GUI/qasync thread to avoid Playwright subprocess errors.
        # Create and use it within a worker thread when needed.
        logger.debug("get_async_crawler called: returning None to avoid creating AsyncWebCrawler on GUI thread")
        return None
    
    def get_browser_session(self) -> Optional['BrowserSession']:
        """Get BrowserSession instance (lazy creation)"""
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserSession")
            return None

        if self._browser_session is None:
            try:
                from browser_use.browser import BrowserSession as _BrowserSession
                # Note: BrowserSession needs to be created after AsyncWebCrawler is started
                # This is just preparation, actual creation should be done when needed
                logger.debug("BrowserSession will be created when needed")
                return None

            except Exception as e:
                logger.error(f"Failed to prepare BrowserSession: {e}")
                return None

        return self._browser_session

    def _create_bu_agent(self, mainwin=None):
        try:
            if not mainwin:
                raise ValueError("mainwin is required. Must use mainwin.llm from MainWindow. Please configure LLM provider API key in Settings.")
            
            logger.debug("create bu agent....")
            from browser_use import Agent
            from browser_use.browser import BrowserProfile, BrowserSession
            logger.debug("done import browser use....")
            
            # Use mainwin's LLM configuration (no fallback)
            from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm
            llm = create_browser_use_llm(mainwin=mainwin, skip_playwright_check=True)
            if not llm:
                raise ValueError("Failed to create browser_use LLM from mainwin. Please configure LLM provider API key in Settings.")
            
            BasicConfig = {
                "chrome_path": "",
                "target_user":  "",# Twitter handle without @
                "message":  "",
                "reply_url":  "",
                "headless": True,
                "model": 'gpt-4o',
                "base_url": 'https://www.amazon.com/',
                "product_phrase": "resistance loop band"
            }
            config = BasicConfig
            logger.debug("done config....")
            full_message = f'@{config["target_user"]} {config["message"]}'
            logger.debug("done full message....")
            basic_task = f"""Navigate to Amazon and search a product.
    
                Here are the specific steps:
    
                1. Go to https://www.amazon.com/ See the search text input field at the top of the page"
                2. Look for the text input field at the top of the page that says "What's happening?"
                3. Click the input field and type exactly this product name: '"{config["product_phrase"]}'
                4. Hit <Enter> key
    
                Important:
                - Wait for each element to load before interacting
                - Make sure the search phrase is typed exactly as shown
                """
            logger.debug("done basic task....", basic_task)
            logger.debug("llm set....")
            browser_profile = BrowserProfile(
                headless=config["headless"],
                executable_path=config["chrome_path"],
                minimum_wait_page_load_time=1,  # 3 on prod
                maximum_wait_page_load_time=10,  # 20 on prod
                viewport={'width': 1280, 'height': 1100},
                viewport_expansion=-1,
                highlight_elements=False,
                user_data_dir='~/.config/browseruse/profiles/default',
                # trace_path='./tmp/web_voyager_agent',
            )
            logger.debug("browser profile set....", browser_profile)
            browser_session = BrowserSession(browser_profile=browser_profile)
            logger.debug("browser session set....", browser_session)
            # Construct the full message with tag
            # Create the agent with detailed instructions
            # Auto-detect model vision support and set use_vision accordingly to avoid warnings
            from agent.ec_skills.llm_utils.llm_utils import get_use_vision_from_llm
            agent_kwargs = {
                'task': basic_task,
                'llm': llm,
                'browser_session': browser_session,
                'validate_output': True,
                'enable_memory': False,
                'use_vision': get_use_vision_from_llm(llm, context="UnifiedBrowserManager")
            }
            agent = Agent(**agent_kwargs)
            logger.debug("browser agent set....", browser_session)
            return agent

        except Exception as e:
            errMsg = get_traceback(e, "ErrorCreateBUAgent")
            logger.debug(errMsg)
            return None



    def get_browser_user(self) -> Optional['Agent']:
        """Get BrowserSession instance (lazy creation)"""
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserSession")
            return None

        # Do not create Browser Use Agent on GUI/qasync thread to avoid Playwright subprocess errors.
        # Agent will be created and run within run_basic_agent_task() on a worker thread.
        logger.debug("get_browser_user called: returning None to avoid creating Agent on GUI thread")
        return None

    def run_basic_agent_task(self, product_phrase: Optional[str] = None, mainwin=None):
        """Build and run a simple Browser Use agent inside a worker thread with its own Selector loop.

        This avoids running Playwright on the GUI/qasync loop (which lacks subprocess support on Windows).
        
        Args:
            product_phrase: Optional product phrase to search for
            mainwin: MainWindow instance (required, no fallback)
        """
        if not mainwin:
            raise ValueError("mainwin is required. Must use mainwin.llm from MainWindow. Please configure LLM provider API key in Settings.")
        
        async def _do():
            try:
                loop = asyncio.get_running_loop()
                logger.info(f"[UnifiedBrowserManager._do] loop={type(loop).__name__}")
            except Exception:
                pass
            from browser_use import Agent
            from browser_use.browser import BrowserProfile, BrowserSession

            cfg_phrase = product_phrase or "resistance loop band"
            task_text = f"""Navigate to Amazon and search a product.
                1. Go to https://www.amazon.com/
                2. Focus the top search input
                3. Type exactly: '{cfg_phrase}'
                4. Press Enter and wait for results
            """

            # Use mainwin's LLM configuration (no fallback)
            from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm
            llm = create_browser_use_llm(mainwin=mainwin, skip_playwright_check=True)
            if not llm:
                raise ValueError("Failed to create browser_use LLM from mainwin. Please configure LLM provider API key in Settings.")
            browser_profile = BrowserProfile(
                headless=False,
                executable_path='',
                minimum_wait_page_load_time=1,
                maximum_wait_page_load_time=12,
                viewport={'width': 1280, 'height': 1100},
                viewport_expansion=-1,
                highlight_elements=False,
                user_data_dir='~/.config/browseruse/profiles/default',
                keep_alive=True,
            )
            browser_session = BrowserSession(browser_profile=browser_profile)

            # Auto-detect model vision support and set use_vision accordingly to avoid warnings
            from agent.ec_skills.llm_utils.llm_utils import get_use_vision_from_llm
            agent_kwargs = {
                'task': task_text,
                'llm': llm,
                'browser_session': browser_session,
                'validate_output': True,
                'enable_memory': False,
                'use_vision': get_use_vision_from_llm(llm, context="UnifiedBrowserManager._do")
            }
            agent = Agent(**agent_kwargs)

            history = await agent.run()
            return history

        try:
            return run_async_in_worker_thread(lambda: _do())
        except Exception as e:
            logger.error(f"Failed to run Browser Use agent task: {e}")
            logger.debug(get_traceback(e, "ErrorRunBasicAgentTask"))
            return None


    def get_browser_use_controller(self) -> Optional['Controller']:
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserUseController")
            return None

        if self._browser_use_controller is None:
            from browser_use.controller.service import Controller as BrowserUseController
            try:
                logger.debug("Creating BrowserUseController instance...")
                display_files_in_done_text = True
                self._browser_use_controller = BrowserUseController(
                    display_files_in_done_text=display_files_in_done_text
                )
                logger.debug("✅ BrowserUseController created successfully")

            except Exception as e:
                logger.error(f"Failed to create BrowserUseController: {e}")
                return None

        return self._browser_use_controller
    
    def get_browser_use_file_system(self) -> Optional['FileSystem']:
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserUse FileSystem")
            return None

        if self._browser_use_file_system is None:
            from browser_use.filesystem.file_system import FileSystem
            try:
                if self._file_system_path:
                    self._browser_use_file_system = FileSystem(self._file_system_path)
                    logger.debug(f"✅ BrowserUse FileSystem created successfully, path: {self._file_system_path}")
                else:
                    self._browser_use_file_system = FileSystem()
                    logger.debug("✅ BrowserUse FileSystem created successfully (default path)")
            except Exception as e:
                logger.error(f"Failed to create BrowserUse FileSystem: {e}")
                return None

        return self._browser_use_file_system

    def run_browser_use_coro(self, coro_factory):
        """
        Run an arbitrary Browser Use async coroutine in the dedicated worker thread.

        Args:
            coro_factory: A zero-arg callable that returns an async coroutine.
                The coroutine MUST import and create any Browser Use / Playwright objects
                inside itself so they bind to the worker thread's Proactor event loop.

        Returns:
            The coroutine's return value (synchronously), or None on failure.

        Notes:
            - This ensures we do NOT touch the GUI/qasync loop and avoid subprocess errors on Windows.
            - Internally uses run_async_in_worker_thread with WindowsProactorEventLoopPolicy.
        """
        try:
            # Ensure manager is initialized for environment setup
            if not self._initialized:
                logger.warning("Manager not initialized; initializing with defaults before running coroutine")
                if not self.initialize():
                    logger.error("Failed to initialize UnifiedBrowserManager")
                    return None

            return run_async_in_worker_thread(lambda: coro_factory())
        except Exception as e:
            logger.error(f"Failed to run Browser Use coroutine in worker thread: {e}")
            logger.debug(get_traceback(e, "ErrorRunBrowserUseCoro"))
            return None
    
    def cleanup(self):
        """Clean up all resources"""
        with self._lock:
            try:
                # Clean up component instances
                self._async_crawler = None
                self._browser_session = None
                self._browser_use_controller = None
                self._browser_use_file_system = None

                self._initialized = False
                self._initialization_error = None
                logger.debug("Unified browser manager resources cleaned up")
            except Exception as e:
                logger.warning(f"Error during resource cleanup: {e}")

    def is_ready(self) -> bool:
        """Check if manager is ready to provide services"""
        return self._initialized and self._initialization_error is None

    def get_status(self) -> Dict[str, Any]:
        """Get manager status"""
        return {
            'initialized': self._initialized,
            'ready': self.is_ready(),
            'initialization_error': self._initialization_error,
            'async_crawler_ready': self._async_crawler is not None,
            'browser_session_ready': self._browser_session is not None,
            'browser_use_controller_ready': self._browser_use_controller is not None,
            'browser_use_file_system_ready': self._browser_use_file_system is not None,
            'playwright_manager_status': self._playwright_manager.get_status() if self._playwright_manager else None
        }

    def switch_profile(self, new_profile):
        # close old
        try:
            if self._browser_session and hasattr(self._browser_session, "close"):
                self._browser_session.close()
            elif self._browser_session and hasattr(self._browser_session, "shutdown"):
                self._browser_session.shutdown()
        except Exception:
            pass

        # create new
        self._browser_session = BrowserSession(browser_profile=new_profile)

        # rebuild agent if needed (safer than mutating in place)
        if self._browser_agent is not None:
            # self._browser_agent = Agent(task=..., llm=..., browser_session=self._browser_session)
            pass

        return self._browser_session



# Global manager instance
_unified_manager_instance: Optional[UnifiedBrowserManager] = None
_unified_manager_lock = Lock()


def get_unified_browser_manager() -> UnifiedBrowserManager:
    """
    Get global unified browser manager instance (singleton pattern)

    Returns:
        UnifiedBrowserManager: Manager instance
    """
    global _unified_manager_instance

    if _unified_manager_instance is None:
        with _unified_manager_lock:
            if _unified_manager_instance is None:
                _unified_manager_instance = UnifiedBrowserManager()

    return _unified_manager_instance
