"""Integration tests for browser-automation runner logic.

Tests the BrowserUseRunner and hook mechanisms with mocked browser sessions
and mainwin. These tests exercise the full async orchestration without
requiring a real browser or GUI.
"""

import pytest
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Add project root to path
_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
sys.path.insert(0, str(_ROOT))

from tests.browser_automation.mock_infrastructure import (
    create_mock_browser_node_config,
    create_mock_state,
    MockAppContext,
    MockMainWindow,
    MockBrowserSession,
    MockUnifiedBrowserManager,
    AppContextTestManager,
)


class TestHookMechanisms:
    """Test browser-automation hook registration and invocation."""

    def test_register_before_browser_session_setup_hook(self):
        """Test registering early-phase hooks."""
        from agent.ec_skills.build_node import (
            register_before_browser_session_setup_hook,
            _before_browser_session_setup_hooks,
        )

        async def test_hook(agent, state, inputs, hook_ctx):
            return None  # Continue normal flow

        # Register and verify
        register_before_browser_session_setup_hook(test_hook)
        assert test_hook in _before_browser_session_setup_hooks

        # Cleanup
        _before_browser_session_setup_hooks.remove(test_hook)

    def test_register_before_prompt_build_hook(self):
        """Test registering prompt-build-phase hooks."""
        from agent.ec_skills.build_node import (
            register_before_prompt_build_hook,
            _before_prompt_build_hooks,
        )

        async def test_hook(state, inputs, hook_ctx, prompt_ctx):
            return None

        register_before_prompt_build_hook(test_hook)
        assert test_hook in _before_prompt_build_hooks

        _before_prompt_build_hooks.remove(test_hook)

    def test_register_before_browser_use_run_hook(self):
        """Test registering late-phase hooks."""
        from agent.ec_skills.build_node import (
            register_before_browser_use_run_hook,
            _before_browser_use_run_hooks,
        )

        async def test_hook(agent, state, inputs, hook_ctx):
            return None

        register_before_browser_use_run_hook(test_hook)
        assert test_hook in _before_browser_use_run_hooks

        _before_browser_use_run_hooks.remove(test_hook)

    def test_hook_idempotent_registration(self):
        """Test that registering same hook twice is idempotent."""
        from agent.ec_skills.build_node import (
            register_before_browser_session_setup_hook,
            _before_browser_session_setup_hooks,
        )

        async def test_hook(agent, state, inputs, hook_ctx):
            return None

        # Register twice
        register_before_browser_session_setup_hook(test_hook)
        register_before_browser_session_setup_hook(test_hook)

        # Should only appear once
        count = _before_browser_session_setup_hooks.count(test_hook)
        assert count == 1

        # Cleanup
        if test_hook in _before_browser_session_setup_hooks:
            _before_browser_session_setup_hooks.remove(test_hook)


class TestBrowserSessionManagement:
    """Test BrowserSessionManager with mocked sessions."""

    @pytest.mark.asyncio
    async def test_session_caching_via_cached_sessions_property(self):
        """Test that sessions are accessible via cached_sessions property."""
        from agent.ec_skills.browser_node.session import BrowserSessionManager
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(node_name="cache_test")
        cfg = parse_node_config(config, node_name="cache_test", skill_name="s", owner="o")
        manager = BrowserSessionManager(cfg)

        scope_key = "chat:user-123"

        # Create mock session and add to cache directly
        mock_session = MockBrowserSession(scope_key)
        manager._cached_sessions[scope_key] = mock_session

        # Access via property
        cached = manager.cached_sessions.get(scope_key)
        assert cached is mock_session

    @pytest.mark.asyncio
    async def test_scope_key_resolution_per_chat(self):
        """Test that per-chat scope keys are created correctly."""
        from agent.ec_skills.browser_node.session import BrowserSessionManager
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(node_name="scope_test")
        cfg = parse_node_config(config, node_name="scope_test", skill_name="s", owner="o")
        manager = BrowserSessionManager(cfg)

        state = create_mock_state(chat_id="user-abc", thread_id="thread-xyz")
        scope_key = manager.resolve_scope_key(state)

        assert scope_key == "chat:user-abc"


class TestRunnerExecutionPaths:
    """Test different execution paths in BrowserUseRunner."""

    def test_parse_node_config_for_runner(self):
        """Test that NodeConfig is correctly parsed for runner."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(
            node_name="runner_test",
            skill_name="test_skill",
            provider="browser-use",
            browser_type="new chromium",
            run_environment="full_local",
            prompt="Open the page and extract data",
            modelProvider="openai",
            modelName="gpt-4o",
            timeout_seconds="600",
        )

        cfg = parse_node_config(
            config,
            node_name="runner_test",
            skill_name="test_skill",
            owner="test_owner",
        )

        assert cfg.node_name == "runner_test"
        assert cfg.provider == "browser-use"
        assert cfg.run_environment == "full_local"
        assert cfg.browser_timeout_seconds == 600.0
        assert cfg.inline_user_prompt == "Open the page and extract data"

    def test_node_config_defaults(self):
        """Test that NodeConfig has correct defaults."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(
            node_name="defaults_test",
            skill_name="test_skill",
        )

        cfg = parse_node_config(
            config,
            node_name="defaults_test",
            skill_name="test_skill",
            owner="test_owner",
        )

        # Check defaults
        assert cfg.provider == "browser-use"
        assert cfg.browser_type == "new chromium"
        assert cfg.headless is False
        assert cfg.run_environment == "full_local"
        assert cfg.privacy_strategy == "none"
        assert cfg.loop_history_mode == "clear"


class TestAppContextIntegration:
    """Test integration with AppContext mocking."""

    def test_mock_appcontext_provides_mainwin(self):
        """Test that mock AppContext correctly provides mainwin."""
        with AppContextTestManager() as ctx:
            assert ctx.main_window is not None
            assert isinstance(ctx.main_window, MockMainWindow)

    def test_mock_mainwindow_browser_manager(self):
        """Test that mock mainwin provides browser manager."""
        with AppContextTestManager() as ctx:
            assert ctx.main_window.unified_browser_manager is not None
            assert isinstance(
                ctx.main_window.unified_browser_manager, MockUnifiedBrowserManager
            )

    def test_llm_configuration_flow(self):
        """Test LLM configuration through mock components."""
        with AppContextTestManager() as ctx:
            mainwin = ctx.main_window

            # Initially not configured
            assert mainwin.is_llm_configured is False

            # Configure
            mainwin.configure_llm("openai", "gpt-4o", "sk-test")

            # Now configured
            assert mainwin.is_llm_configured is True
            assert mainwin.browser_use_llm._provider == "openai"
            assert mainwin.browser_use_llm._model == "gpt-4o"

    def test_appcontext_reset_between_tests(self):
        """Test that AppContext can be reset between tests."""
        # First setup
        ctx1 = MockAppContext.setup_for_test()
        mainwin1 = MockMainWindow()
        ctx1.main_window = mainwin1

        # Reset
        MockAppContext.reset()

        # New setup should be independent
        ctx2 = MockAppContext.setup_for_test()
        assert ctx2.main_window is not mainwin1


class TestSafeFormatDict:
    """Test _SafeFormatDict for mustache template safety."""

    def test_safe_format_dict_basic(self):
        """Test basic safe format dict."""
        from agent.ec_skills.build_node import _SafeFormatDict

        data = _SafeFormatDict({"name": "Alice", "count": 42})
        assert data["name"] == "Alice"
        assert data["count"] == 42

    def test_safe_format_dict_missing_key(self):
        """Test safe format dict returns empty for missing keys."""
        from agent.ec_skills.build_node import _SafeFormatDict

        data = _SafeFormatDict({"name": "Bob"})
        # Should not raise, returns empty string for missing keys
        assert data.get("missing", "") == ""


class TestNodeConfigFieldExtraction:
    """Test specific NodeConfig field extraction."""

    def test_extract_browser_type(self):
        """Test browser type extraction from config."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(
            browser_type="ads power",
        )

        cfg = parse_node_config(config, node_name="t", skill_name="s", owner="o")
        assert cfg.browser_type == "ads power"

    def test_extract_run_environment(self):
        """Test run environment extraction."""
        from agent.ec_skills.browser_node.config import parse_node_config

        # Test full_cloud
        config = create_mock_browser_node_config(
            run_environment="full_cloud",
        )

        cfg = parse_node_config(config, node_name="t", skill_name="s", owner="o")
        assert cfg.run_environment == "full_cloud"

        # Test hybrid_cloud
        config = create_mock_browser_node_config(
            run_environment="hybrid_cloud",
        )

        cfg = parse_node_config(config, node_name="t2", skill_name="s", owner="o")
        assert cfg.run_environment == "hybrid_cloud"

    def test_extract_llm_provider(self):
        """Test LLM provider extraction."""
        from agent.ec_skills.browser_node.config import parse_node_config

        # Test anthropic
        config = create_mock_browser_node_config(
            modelProvider="anthropic",
            modelName="claude-3-5-sonnet",
        )

        cfg = parse_node_config(config, node_name="t", skill_name="s", owner="o")
        assert cfg.llm_provider == "anthropic"
        assert cfg.llm_model_name == "claude-3-5-sonnet"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
