"""Mock infrastructure for browser-automation testing.

Provides mock implementations of:
- MockAppContext: Simulates the AppContext singleton
- MockMainWindow: Simulates MainWindow with browser/llm capabilities
- MockBrowserSession: Simulates Playwright BrowserSession
- MockUnifiedBrowserManager: Simulates UnifiedBrowserManager
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional
from unittest.mock import MagicMock, AsyncMock


class MockBrowserSession:
    """Mock Playwright BrowserSession for testing."""

    def __init__(self, session_id: str = "test-session"):
        self.session_id = session_id
        self._is_alive = True
        self._ecan_fast_attach_ready = True
        self.cdp_client_root = MagicMock()
        self.session_manager = MagicMock()
        self.event_bus = MagicMock()
        self._navigated_urls: list[str] = []
        self._actions: list[dict] = []

    @property
    def is_alive(self) -> bool:
        return self._is_alive

    async def start(self, *args, **kwargs):
        self._is_alive = True
        return self

    async def stop(self, *args, **kwargs):
        self._is_alive = False

    async def navigate(self, url: str, *args, **kwargs):
        self._navigated_urls.append(url)
        return {"url": url, "success": True}

    async def execute_action(self, action: dict):
        self._actions.append(action)
        return {"action": action, "success": True}

    def get_navigated_urls(self) -> list[str]:
        return self._navigated_urls.copy()

    def get_actions(self) -> list[dict]:
        return self._actions.copy()


class MockUnifiedBrowserManager:
    """Mock UnifiedBrowserManager for testing."""

    def __init__(self):
        self._sessions: dict[str, MockBrowserSession] = {}
        self._current_session: Optional[MockBrowserSession] = None
        self._llm_configured = False
        self._llm = MagicMock()

    def set_llm_configured(self, configured: bool):
        self._llm_configured = configured

    def set_llm(self, llm: Any):
        self._llm = llm
        self._llm_configured = True

    @property
    def is_llm_configured(self) -> bool:
        return self._llm_configured

    @property
    def current_session(self) -> Optional[MockBrowserSession]:
        return self._current_session

    async def get_or_create_session(
        self,
        scope_key: str,
        browser_type: str = "new chromium",
        *args,
        **kwargs
    ) -> MockBrowserSession:
        if scope_key not in self._sessions:
            self._sessions[scope_key] = MockBrowserSession(session_id=scope_key)
            await self._sessions[scope_key].start()
        self._current_session = self._sessions[scope_key]
        return self._current_session

    async def close_session(self, scope_key: str):
        if scope_key in self._sessions:
            await self._sessions[scope_key].stop()
            del self._sessions[scope_key]

    def get_session(self, scope_key: str) -> Optional[MockBrowserSession]:
        return self._sessions.get(scope_key)

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())


class MockMainWindow:
    """Mock MainWindow for testing without GUI."""

    def __init__(self):
        self.unified_browser_manager = MockUnifiedBrowserManager()
        self.browser_use_llm = MagicMock()
        self._llm_configured = False

        # Mock agents and skills
        self.agents: list = []
        self.agent_skills: list = []
        self.agent_tasks: list = []

        # Mock MCP tools
        self.mcp_tools_schemas: dict = {}

        # Mock settings
        self.settings = MockSettings()

    @property
    def is_llm_configured(self) -> bool:
        return self.unified_browser_manager.is_llm_configured

    def configure_llm(self, provider: str, model: str, api_key: str = "test-key"):
        """Configure LLM for browser-use."""
        mock_llm = MagicMock()
        mock_llm._provider = provider
        mock_llm._model = model
        self.unified_browser_manager.set_llm(mock_llm)
        self.browser_use_llm = mock_llm
        self._llm_configured = True


class MockSettings:
    """Mock AppSettings for testing."""

    def __init__(self):
        self.llm_provider = "openai"
        self.llm_model = "gpt-4o"
        self.llm_api_key = "sk-test"
        self.dashscope_api_key = "sk-test"
        self.playwright_browsers_path = "/tmp/test-browsers"


class MockAppContext:
    """Mock AppContext singleton for testing."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # Mock all required attributes
        self.app = MagicMock()
        self.main_window: Optional[MockMainWindow] = None
        self.web_gui = MagicMock()
        self.logger = MagicMock()
        self.config = MockSettings()
        self.thread_pool = MagicMock()
        self.app_info = MagicMock()
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None
        self.login = MagicMock()
        self.playwright_browsers_path = "/tmp/test-browsers"

        # Track if properly initialized
        self._properly_initialized = False

    def set_main_window(self, win: Any):
        self.main_window = win

    @classmethod
    def get_instance(cls) -> "MockAppContext":
        return cls()

    @classmethod
    def get_main_window(cls) -> Optional[MockMainWindow]:
        instance = cls.get_instance()
        return instance.main_window

    @classmethod
    def reset(cls):
        """Reset singleton for fresh test."""
        cls._instance = None
        cls._initialized = False

    @classmethod
    def setup_for_test(cls, mainwin: Optional[MockMainWindow] = None) -> "MockAppContext":
        """Setup AppContext with mock or provided mainwin."""
        cls.reset()
        ctx = cls.get_instance()
        ctx.main_window = mainwin or MockMainWindow()
        ctx._properly_initialized = True
        return ctx


# Global context manager for tests
class AppContextTestManager:
    """Context manager for test AppContext setup/teardown."""

    def __init__(self, mainwin: Optional[MockMainWindow] = None):
        self.ctx: Optional[MockAppContext] = None
        self.mainwin = mainwin
        self._original_instance = None

    def __enter__(self) -> MockAppContext:
        # Store original state
        self._original_instance = MockAppContext._instance

        # Setup fresh mock context
        self.ctx = MockAppContext.setup_for_test(self.mainwin)
        return self.ctx

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original state
        MockAppContext._instance = self._original_instance
        MockAppContext._initialized = False
        return False


# Fixture factories
def create_mock_browser_node_config(
    node_name: str = "test_browser_node",
    skill_name: str = "test_skill",
    provider: str = "browser-use",
    browser_type: str = "new chromium",
    run_environment: str = "full_local",
    headless: str = "false",
    timeout_seconds: str = "300",
    modelProvider: str = "openai",
    modelName: str = "gpt-4o",
    loopHistoryMode: str = "clear",
    actionableField: str = "",
    promptSelection: str = "inline",
    prompt: str = "Test prompt",
    systemPrompt: str = "",
    useThinking: str = "false",
    useVision: str = "false",
    **kwargs  # Additional inputsValues keys with {"content": value} format
) -> dict:
    """Create a mock browser-automation node config for testing.

    Args:
        node_name: Node identifier
        skill_name: Skill name
        provider: Browser provider (browser-use, crawl4ai, browsebase)
        browser_type: Browser type (new chromium, existing chrome, etc.)
        run_environment: Run environment (full_local, hybrid_cloud, full_cloud)
        headless: Headless mode setting
        timeout_seconds: Timeout in seconds
        modelProvider: LLM provider
        modelName: LLM model name
        loopHistoryMode: Loop history mode (clear, trim:N)
        actionableField: CSS selector for actionable elements
        promptSelection: Prompt selection mode (inline, pool)
        prompt: User prompt content
        systemPrompt: System prompt content
        useThinking: Enable thinking mode
        useVision: Enable vision
        **kwargs: Additional inputsValues keys (will be wrapped in {"content": ...})

    Returns:
        Mock config_metadata dict matching the node editor format
    """
    # Build inputsValues, wrapping simple kwargs in {"content": value}
    inputs_extra = {}
    for key, value in kwargs.items():
        if isinstance(value, dict):
            inputs_extra[key] = value
        else:
            inputs_extra[key] = {"content": str(value)}

    return {
        "nodeName": node_name,
        "skillName": skill_name,
        "provider": provider,
        "action": "open_page",
        "params": {},
        "wait_for_done": False,
        "inputsValues": {
            "tool": {"content": provider},
            "browser": {"content": browser_type},
            "browserDriver": {"content": "native"},
            "cdpPort": {"content": ""},
            "runEnvironment": {"content": run_environment},
            "privacyStrategy": {"content": "none"},
            "prompt": {"content": prompt},
            "systemPrompt": {"content": systemPrompt},
            "modelProvider": {"content": modelProvider},
            "modelName": {"content": modelName},
            "headless": {"content": headless},
            "timeout_seconds": {"content": timeout_seconds},
            "promptSelection": {"content": promptSelection},
            "loopHistoryMode": {"content": loopHistoryMode},
            "actionableField": {"content": actionableField},
            "useThinking": {"content": useThinking},
            "useVision": {"content": useVision},
            **inputs_extra
        },
        **kwargs
    }


def create_mock_state(
    chat_id: str = "test-chat-123",
    thread_id: str = "test-thread-456",
    input_text: str = "Test input",
    **kwargs
) -> dict:
    """Create a mock state dict for browser-automation node testing.

    Args:
        chat_id: Chat identifier
        thread_id: Thread identifier
        input_text: Input text for the node
        **kwargs: Additional state overrides

    Returns:
        Mock state dict matching the LangGraph state format
    """
    import time
    return {
        "input": input_text,
        "messages": [],
        "result": {},
        "tool_result": {},
        "attributes": {
            "__llm_timings__": [],
            "__node_timings__": [],
            "agent_id": "test_agent",
            "chat_id": chat_id,
            "human": {"id": "user1", "name": "测试用户"},
            "thread_id": thread_id or f"test_{int(time.time())}",
        },
        "prompts": [],
        "history": [],
        "threads": [],
        "events": [],
        "attachments": [],
        "error": "",
        "retries": 0,
        "condition": False,
        "condition_vars": {},
        "loop_end_vars": {},
        "case": "",
        "goals": [],
        "breakpoint": False,
        "max_steps": 100,
        "n_steps": 0,
        "metadata": {},
        "http_response": {},
        "cli_input": {},
        "cli_results": {},
        **kwargs
    }
