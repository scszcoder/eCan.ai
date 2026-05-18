"""Unit tests for browser-automation node configuration parsing.

Tests the pure parsing logic in browser_node/config.py without any
GUI or browser dependencies.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
sys.path.insert(0, str(_ROOT))

from tests.browser_automation.mock_infrastructure import (
    create_mock_browser_node_config,
    MockAppContext,
    AppContextTestManager,
)


class TestNodeConfigParsing:
    """Test NodeConfig parsing from config_metadata."""

    def test_parse_minimal_config(self):
        """Test parsing with minimal config."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(
            node_name="test_node",
            skill_name="test_skill",
        )

        result = parse_node_config(
            config,
            node_name="test_node",
            skill_name="test_skill",
            owner="test_owner",
        )

        assert result.node_name == "test_node"
        assert result.skill_name == "test_skill"
        assert result.owner == "test_owner"
        assert result.provider == "browser-use"
        assert result.browser_type == "new chromium"

    def test_parse_full_config(self):
        """Test parsing with full browser settings."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(
            node_name="full_config_node",
            skill_name="full_skill",
            provider="browser-use",
            browser_type="existing chrome",
            run_environment="hybrid_cloud",
            headless="true",
            timeout_seconds="600",
        )

        result = parse_node_config(
            config,
            node_name="full_config_node",
            skill_name="full_skill",
            owner="owner",
        )

        assert result.provider == "browser-use"
        assert result.browser_type == "existing chrome"
        assert result.run_environment == "hybrid_cloud"
        assert result.headless is True
        assert result.browser_timeout_seconds == 600.0

    def test_parse_llm_settings(self):
        """Test parsing LLM configuration."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(
            node_name="llm_test",
            skill_name="llm_skill",
            modelProvider="openai",
            modelName="gpt-4o",
            useThinking="true",
            useVision="true",
        )

        result = parse_node_config(
            config,
            node_name="llm_test",
            skill_name="llm_skill",
            owner="owner",
        )

        assert result.llm_provider == "openai"
        assert result.llm_model_name == "gpt-4o"
        assert result.use_thinking is True
        assert result.use_vision is True

    def test_parse_loop_settings(self):
        """Test parsing loop/history settings."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(
            node_name="loop_test",
            skill_name="loop_skill",
            loopHistoryMode="trim:20",
            actionableField=".action-button",
        )

        result = parse_node_config(
            config,
            node_name="loop_test",
            skill_name="loop_skill",
            owner="owner",
        )

        assert result.loop_history_mode == "trim:20"
        assert result.actionable_field == ".action-button"

    def test_parse_prompt_selection_inline(self):
        """Test parsing inline prompt selection."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(
            node_name="prompt_test",
            skill_name="prompt_skill",
            promptSelection="inline",
            prompt="Navigate to the page and extract product info",
            systemPrompt="You are a helpful assistant",
        )

        result = parse_node_config(
            config,
            node_name="prompt_test",
            skill_name="prompt_skill",
            owner="owner",
        )

        assert result.prompt_selection == "inline"
        assert result.inline_user_prompt == "Navigate to the page and extract product info"
        assert result.inline_system_prompt == "You are a helpful assistant"

    def test_timeout_floor_enforcement(self):
        """Test that timeout below minimum is raised to floor."""
        from agent.ec_skills.browser_node.config import (
            parse_node_config,
            BROWSER_MIN_TIMEOUT_SEC,
        )

        # Use nodeTimeoutSeconds key (not timeout_seconds)
        config = create_mock_browser_node_config(
            node_name="timeout_test",
            skill_name="timeout_skill",
            nodeTimeoutSeconds=60,  # Below minimum 300
        )

        result = parse_node_config(
            config,
            node_name="timeout_test",
            skill_name="timeout_skill",
            owner="owner",
        )

        assert result.node_timeout_seconds == BROWSER_MIN_TIMEOUT_SEC

    def test_provider_normalization(self):
        """Test provider name normalization."""
        from agent.ec_skills.browser_node.config import parse_node_config

        # Test browser-use
        config = create_mock_browser_node_config(provider="browser-use")
        result = parse_node_config(config, node_name="n", skill_name="s", owner="o")
        assert result.provider == "browser-use"

        # Test crawl4ai
        config = create_mock_browser_node_config(provider="crawl4ai")
        result = parse_node_config(config, node_name="n", skill_name="s", owner="o")
        assert result.provider == "crawl4ai"

    def test_browser_type_normalization(self):
        """Test browser type normalization to lowercase."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(browser_type="NEW CHROMIUM")
        result = parse_node_config(config, node_name="n", skill_name="s", owner="o")
        assert result.browser_type == "new chromium"

        config = create_mock_browser_node_config(browser_type="Existing Chrome")
        result = parse_node_config(config, node_name="n", skill_name="s", owner="o")
        assert result.browser_type == "existing chrome"


class TestNodeConfigHelpers:
    """Test helper functions for content extraction."""

    def test_str_content_with_default(self):
        """Test _str_content helper with default."""
        from agent.ec_skills.browser_node.config import _str_content

        inputs = {"name": {"content": "  test value  "}}
        result = _str_content(inputs, "name")
        assert result == "test value"

    def test_str_content_missing_key(self):
        """Test _str_content helper with missing key."""
        from agent.ec_skills.browser_node.config import _str_content

        inputs = {}
        result = _str_content(inputs, "missing", default="default_value")
        assert result == "default_value"

    def test_bool_content_true_values(self):
        """Test _bool_content with various true values."""
        from agent.ec_skills.browser_node.config import _bool_content

        for val in ["true", "True", "TRUE", "1", "yes", "on"]:
            inputs = {"flag": {"content": val}}
            assert _bool_content(inputs, "flag") is True, f"Failed for {val}"

    def test_bool_content_false_values(self):
        """Test _bool_content with false values."""
        from agent.ec_skills.browser_node.config import _bool_content

        for val in ["false", "False", "0", "no", "off", ""]:
            inputs = {"flag": {"content": val}}
            assert _bool_content(inputs, "flag") is False, f"Failed for {val}"

    def test_int_content(self):
        """Test _int_content helper."""
        from agent.ec_skills.browser_node.config import _int_content

        inputs = {"count": {"content": "42"}}
        assert _int_content(inputs, "count") == 42

        inputs = {"count": {"content": "invalid"}}
        assert _int_content(inputs, "count", default=10) == 10

    def test_float_content(self):
        """Test _float_content helper."""
        from agent.ec_skills.browser_node.config import _float_content

        inputs = {"rate": {"content": "3.14"}}
        assert _float_content(inputs, "rate") == 3.14

        inputs = {"rate": {"content": ""}}
        assert _float_content(inputs, "rate") is None


class TestNodeConfigProperties:
    """Test NodeConfig derived properties."""

    def test_is_browser_use(self):
        """Test is_browser_use property."""
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(provider="browser-use")
        result = parse_node_config(config, node_name="n", skill_name="s", owner="o")
        assert result.is_browser_use is True

        config = create_mock_browser_node_config(provider="crawl4ai")
        result = parse_node_config(config, node_name="n", skill_name="s", owner="o")
        assert result.is_browser_use is False


class TestScopeKeyResolution:
    """Test browser session scope key resolution."""

    def test_resolve_scope_key_with_chat_id(self):
        """Test scope key resolution with chat_id."""
        from agent.ec_skills.browser_node.session import BrowserSessionManager
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(node_name="scope_test")
        cfg = parse_node_config(config, node_name="scope_test", skill_name="s", owner="o")
        manager = BrowserSessionManager(cfg)

        state = {"attributes": {"chat_id": "chat-123"}}
        scope_key = manager.resolve_scope_key(state)
        assert scope_key == "chat:chat-123"

    def test_resolve_scope_key_with_nested_chat_id(self):
        """Test scope key resolution with nested chat_id."""
        from agent.ec_skills.browser_node.session import BrowserSessionManager
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(node_name="scope_test")
        cfg = parse_node_config(config, node_name="scope_test", skill_name="s", owner="o")
        manager = BrowserSessionManager(cfg)

        state = {
            "attributes": {
                "params": {
                    "metadata": {
                        "params": {"chatId": "nested-chat-456"}
                    }
                }
            }
        }
        scope_key = manager.resolve_scope_key(state)
        assert scope_key == "chat:nested-chat-456"

    def test_resolve_scope_key_fallback_to_node(self):
        """Test scope key falls back to node name when no chat_id."""
        from agent.ec_skills.browser_node.session import BrowserSessionManager
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(node_name="my_browser_node")
        cfg = parse_node_config(config, node_name="my_browser_node", skill_name="s", owner="o")
        manager = BrowserSessionManager(cfg)

        state = {"attributes": {}}
        scope_key = manager.resolve_scope_key(state)
        assert scope_key == "node:my_browser_node"

    def test_resolve_scope_key_no_state(self):
        """Test scope key resolution with no state."""
        from agent.ec_skills.browser_node.session import BrowserSessionManager
        from agent.ec_skills.browser_node.config import parse_node_config

        config = create_mock_browser_node_config(node_name="empty_test")
        cfg = parse_node_config(config, node_name="empty_test", skill_name="s", owner="o")
        manager = BrowserSessionManager(cfg)

        scope_key = manager.resolve_scope_key(None)
        assert scope_key == "node:empty_test"


class TestExtractRuntimeInput:
    """Test runtime invocation input extraction."""

    def test_extract_from_json_string(self):
        """Test extracting runtime input from JSON string."""
        from agent.ec_skills.browser_node.session import BrowserSessionManager

        payload = {"url": "https://example.com", "action": "scrape"}
        import json
        runtime_input = json.dumps(payload)

        result = BrowserSessionManager.extract_assignment_scope(runtime_input)
        assert result["url"] == "https://example.com"
        assert result["action"] == "scrape"

    def test_extract_from_empty_string(self):
        """Test extracting from empty string."""
        from agent.ec_skills.browser_node.session import BrowserSessionManager

        result = BrowserSessionManager.extract_assignment_scope("")
        assert result == {}

    def test_extract_from_invalid_json(self):
        """Test extracting from invalid JSON."""
        from agent.ec_skills.browser_node.session import BrowserSessionManager

        result = BrowserSessionManager.extract_assignment_scope("not valid json")
        assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
