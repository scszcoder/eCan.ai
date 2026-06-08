import pytest

from tests.e2e.pages import ChatSimulatorPage
from tests.e2e_framework import BrowserLauncher, BrowserType, CDPConnector, CDPPage


class TestIMWorkbenchTarget:
    """E2E tests for the Independent IM Workbench Target.

    These tests target the standalone app at http://localhost:4173.
    Run the target app first:
        cd tests/targets/im-workbench && npm run dev
    """

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context, ensure_im_workbench_ready):
        self.ctx = e2e_context
        self.page = e2e_context.pw_page

    @pytest.mark.asyncio
    async def test_im_workbench_page_loads(self):
        """Verify the IM workbench page loads with all major sections."""
        page = ChatSimulatorPage(self.page)
        await self.page.goto("http://localhost:4173")
        await self.page.wait_for_load_state("networkidle")

        assert await page.root.count() > 0, "IM Workbench root element not found"
        assert await page.control_bar.count() > 0, "Control bar not found"
        assert await page.session_pool.count() > 0, "Session pool not found"
        assert await page.message_column.count() > 0, "Message column not found"

    @pytest.mark.asyncio
    async def test_im_workbench_session_switch(self):
        """Verify session switching works."""
        page = ChatSimulatorPage(self.page)
        await self.page.goto("http://localhost:4173")
        await self.page.wait_for_load_state("networkidle")

        session_count = await page.session_items.count()
        assert session_count > 1, "Need at least 2 sessions to test switching"

        second_session = page.session_items.nth(1)
        await second_session.click()
        await self.page.wait_for_timeout(300)

        active = page.active_session
        assert await active.count() > 0, "Active session should be highlighted"

    @pytest.mark.asyncio
    async def test_im_workbench_manual_reply(self):
        """Verify manual reply submission works."""
        page = ChatSimulatorPage(self.page)
        await self.page.goto("http://localhost:4173")
        await self.page.wait_for_load_state("networkidle")

        await page.reply_input.fill("Automated smoke test reply")
        await page.send_button.click()
        await self.page.wait_for_timeout(500)

        content = await self.page.content()
        assert "Automated smoke test reply" in content, "Manual reply should appear in DOM"

    @pytest.mark.asyncio
    async def test_im_workbench_scenario_switch(self):
        """Verify scenario switching changes state."""
        page = ChatSimulatorPage(self.page)
        await self.page.goto("http://localhost:4173")
        await self.page.wait_for_load_state("networkidle")

        await page.scenario_option("burst").click()
        await self.page.wait_for_timeout(500)

        assert await page.knowledge_card.count() > 0
        assert await page.timeline.count() > 0


class TestIMWorkbenchCDP:
    """CDP-level tests for the IM Workbench Target using direct DevTools Protocol."""

    @pytest.mark.asyncio
    async def test_cdp_evaluate_im_workbench(self, base_url, cdp_port, ensure_im_workbench_ready):
        """Use CDP to evaluate the IM workbench DOM state and inject concurrent messages."""
        try:
            BrowserLauncher.launch(
                browser_type=BrowserType.CHROME,
                headless=True,
                cdp_port=cdp_port,
                wait_ready=True,
                timeout=20,
            )
        except Exception:
            pass

        ws_url = BrowserLauncher.get_cdp_ws_url(cdp_port)
        cdp = CDPConnector(ws_url)
        await cdp.connect()
        page = CDPPage(cdp)
        await page.enable()
        await page.navigate("http://localhost:4173")
        await page.wait_for_load()

        result = await page.evaluate("""
            (() => {
                const root = document.querySelector('[data-testid="im-workbench-page"]');
                const sessions = document.querySelectorAll('[data-testid^="session-item-"]');
                const burstBtn = document.querySelector('[data-testid="scenario-option-burst"]');
                if (burstBtn) burstBtn.click();
                return {
                    hasRoot: Boolean(root),
                    sessionCount: sessions.length,
                    replyInputCount: document.querySelectorAll('[data-testid="reply-input"]').length,
                    knowledgeHitCount: document.querySelectorAll('[data-testid^="knowledge-hit-"]').length,
                    timestamp: Date.now(),
                };
            })()
        """)

        assert result is not None
        assert result.get('hasRoot') is True, "IM Workbench root element not found"
        assert result.get('sessionCount', 0) > 0, "Session items should exist"
        assert result.get('replyInputCount', 0) > 0, "Reply input should exist"
        assert result.get('knowledgeHitCount', 0) > 0, "Knowledge hits should exist"

        await cdp.close()

    @pytest.mark.asyncio
    async def test_cdp_concurrent_session_injection(self, base_url, cdp_port):
        """CDP test: inject messages into multiple sessions concurrently."""
        try:
            BrowserLauncher.launch(
                browser_type=BrowserType.CHROME,
                headless=True,
                cdp_port=cdp_port,
                wait_ready=True,
                timeout=20,
            )
        except Exception:
            pass

        ws_url = BrowserLauncher.get_cdp_ws_url(cdp_port)
        cdp = CDPConnector(ws_url)
        await cdp.connect()
        page = CDPPage(cdp)
        await page.enable()
        await page.navigate("http://localhost:4173")
        await page.wait_for_load()

        result = await page.evaluate("""
            (() => {
                // Switch to burst mode for fast injection
                const burstBtn = document.querySelector('[data-testid="scenario-option-burst"]');
                if (burstBtn) burstBtn.click();

                // Wait a bit for messages to inject
                const start = Date.now();
                while (Date.now() - start < 3000) {}

                const sessions = document.querySelectorAll('[data-testid^="session-item-"]');
                const messageCount = document.querySelectorAll('[data-testid^="message-bubble-"]').length;
                const urgentCount = document.querySelectorAll('[data-testid="session-tab-urgent"]').length;

                return {
                    totalSessions: sessions.length,
                    totalMessages: messageCount,
                    urgentTabBadge: urgentCount,
                    timestamp: Date.now(),
                };
            })()
        """)

        assert result is not None
        assert result.get('totalSessions', 0) > 0, "Sessions should exist"
        assert result.get('totalMessages', 0) > 0, "Messages should be injected in burst mode"

        await cdp.close()
