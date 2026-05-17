"""E2E tests for browser-automation in GUI environment.

These tests require:
1. Full GUI application running
2. Real AppContext initialization
3. Playwright browsers installed
4. Network access (for real URL tests)

Run with: pytest tests/browser_automation/test_e2e.py -v --gui

Mark tests with @pytest.mark.gui to skip in CI.
"""

import pytest
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
sys.path.insert(0, str(_ROOT))


@pytest.mark.gui
class TestBrowserAutomationE2E:
    """End-to-end tests requiring full GUI + browser environment."""

    @pytest.fixture(autouse=True)
    def check_gui_available(self):
        """Check if GUI environment is available."""
        pytest.importorskip("PySide6")
        pytest.importorskip("app_context")

        # Skip if AppContext is not properly initialized
        try:
            from app_context import AppContext
            mainwin = AppContext.get_main_window()
            if mainwin is None:
                pytest.skip("MainWindow not available - GUI not fully initialized")
        except Exception as e:
            pytest.skip(f"AppContext not available: {e}")

    @pytest.fixture
    def app_mainwin(self):
        """Get main window from AppContext."""
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            pytest.skip("MainWindow not available")
        return mainwin

    @pytest.fixture
    def browser_manager(self, app_mainwin):
        """Get unified browser manager."""
        return app_mainwin.unified_browser_manager

    @pytest.mark.asyncio
    async def test_browser_manager_available(self, browser_manager):
        """Verify browser manager is available."""
        assert browser_manager is not None

    @pytest.mark.asyncio
    async def test_llm_configured(self, app_mainwin):
        """Verify LLM is configured for browser-use."""
        assert app_mainwin.is_llm_configured, "LLM not configured - set API key in Settings"

    @pytest.mark.asyncio
    async def test_simple_page_navigation(self, browser_manager):
        """Test simple browser page navigation."""
        # This is a placeholder - real implementation would:
        # 1. Get or create a session
        # 2. Navigate to a test URL
        # 3. Verify the page loaded
        # 4. Extract some content

        scope_key = "e2e:test:simple_nav"
        session = await browser_manager.get_or_create_session(scope_key)

        # Navigate to a simple test page
        result = await session.navigate("https://example.com")
        assert result["success"] is True

        # Cleanup
        await browser_manager.close_session(scope_key)


@pytest.mark.gui
class TestBrowserAutomationWithSkill:
    """Test browser-automation as part of a complete Skill workflow."""

    @pytest.fixture(autouse=True)
    def check_gui_available(self):
        """Check if GUI environment is available."""
        pytest.importorskip("PySide6")
        try:
            from app_context import AppContext
            mainwin = AppContext.get_main_window()
            if mainwin is None:
                pytest.skip("MainWindow not available")
        except Exception:
            pytest.skip("AppContext not available")

    def test_load_skill_with_browser_node(self):
        """Test loading a skill that contains browser-automation nodes."""
        from agent.ec_skills.flowgram2langgraph import flowgram2langgraph_v2

        # Example skill with browser-automation node
        skill_data = {
            "name": "test_browser_skill",
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                },
                {
                    "id": "browser_node",
                    "type": "browser-automation",
                    "config": {
                        "task": "Navigate to example.com and extract the title",
                        "provider": "browser-use",
                    },
                },
                {
                    "id": "end",
                    "type": "end",
                },
            ],
            "edges": [
                {"source": "start", "target": "browser_node"},
                {"source": "browser_node", "target": "end"},
            ],
        }

        graph, _ = flowgram2langgraph_v2(
            skill_data,
            bundle_json=skill_data.get("bundle"),
            enable_subgraph=False,
        )

        assert graph is not None, "Failed to build graph with browser-automation node"

    @pytest.mark.asyncio
    async def test_run_browser_node_in_skill(self):
        """Test running a browser-automation node as part of skill execution."""
        # This would execute the full skill graph with browser automation
        # Placeholder for full E2E test
        pytest.skip("Requires complete skill runtime setup")


@pytest.mark.gui
class TestBrowserAutomationEdgeCases:
    """Test edge cases and error handling in browser automation."""

    @pytest.fixture(autouse=True)
    def check_gui_available(self):
        """Check if GUI environment is available."""
        pytest.importorskip("PySide6")
        try:
            from app_context import AppContext
            if AppContext.get_main_window() is None:
                pytest.skip("MainWindow not available")
        except Exception:
            pytest.skip("AppContext not available")

    @pytest.mark.asyncio
    async def test_invalid_url_handling(self):
        """Test handling of invalid URLs."""
        pytest.skip("Requires browser session with error injection")

    @pytest.mark.asyncio
    async def test_network_timeout_handling(self):
        """Test handling of network timeouts."""
        pytest.skip("Requires network condition simulation")

    @pytest.mark.asyncio
    async def test_browser_crash_recovery(self):
        """Test recovery from browser crash."""
        pytest.skip("Requires browser crash simulation")


# Pytest configuration for GUI tests
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "gui: tests that require GUI environment"
    )
