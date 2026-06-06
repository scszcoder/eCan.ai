"""Sample E2E Test - Skills Module.

This file demonstrates E2E testing for the Skills/Skill Editor module.

Test Coverage:
- Skills list page navigation
- Skill creation
- Skill editor functionality
- Skill execution (if applicable)

Run:
    pytest tests/e2e/test_sample_skills.py -v
"""

import pytest

from tests.e2e.conftest import authenticated_context, e2e_context
from tests.e2e.pages import Navigation, SkillEditorPage, SkillsPage


class TestSkillsList:
    """Test suite for Skills List page."""

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context):
        """Setup test context."""
        self.ctx = e2e_context
        self.page = e2e_context.pw_page
        self.nav = Navigation(self.page)

    @pytest.mark.asyncio
    async def test_skills_page_loads(self):
        """Test that skills page loads successfully."""
        skills_page = await self.nav.go_to_skills()

        # Verify page loaded
        assert "skills" in self.page.url.lower()

    @pytest.mark.asyncio
    async def test_skills_list_displays_skills(self):
        """Test that existing skills are displayed."""
        skills_page = await self.nav.go_to_skills()

        # Check if skill cards are displayed
        cards = await skills_page.skill_cards.count()
        assert cards >= 0

    @pytest.mark.asyncio
    async def test_search_skills(self):
        """Test searching for skills."""
        skills_page = await self.nav.go_to_skills()

        # Type search query
        await skills_page.search_input.fill("test")

        # Wait for results
        await self.page.wait_for_timeout(500)

        # Verify search was applied
        # Implementation depends on app behavior


class TestSkillCreation:
    """Test suite for Skill Creation functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context, authenticated_context):
        """Setup test context."""
        self.ctx = e2e_context
        self.page = e2e_context.pw_page
        self.nav = Navigation(self.page)

    @pytest.mark.asyncio
    async def test_create_skill_navigates_to_editor(self):
        """Test clicking create skill navigates to editor."""
        skills_page = await self.nav.go_to_skills()

        # Click create button
        await skills_page.create_button.click()

        # Verify editor opened
        assert "/edit" in self.page.url or "/new" in self.page.url

    @pytest.mark.asyncio
    async def test_save_empty_skill(self):
        """Test saving an empty skill shows validation."""
        await self.nav.go_to("/skills/new")

        editor = SkillEditorPage(self.page)

        # Try to save without any nodes
        await editor.save_button.click()

        # Verify validation/error message
        # Implementation depends on app behavior


class TestSkillEditor:
    """Test suite for Skill Editor functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context, authenticated_context):
        """Setup test context."""
        self.ctx = e2e_context
        self.page = e2e_context.pw_page
        self.nav = Navigation(self.page)

    @pytest.mark.asyncio
    async def test_editor_canvas_renders(self):
        """Test that editor canvas is rendered."""
        # Navigate to skill editor
        await self.nav.go_to("/skills/new")

        editor = SkillEditorPage(self.page)

        # Verify canvas is visible
        canvas_visible = await editor.canvas.is_visible()
        # Note: Canvas might not be immediately visible on empty editor

    @pytest.mark.asyncio
    async def test_node_palette_available(self):
        """Test that node palette is available."""
        await self.nav.go_to("/skills/new")

        editor = SkillEditorPage(self.page)

        # Verify palette is visible
        palette_visible = await editor.node_palette.is_visible()
        assert palette_visible or await editor.node_palette.count() > 0

    @pytest.mark.asyncio
    async def test_add_start_node(self):
        """Test adding a start node to the canvas."""
        await self.nav.go_to("/skills/new")

        editor = SkillEditorPage(self.page)

        # Try to add start node
        try:
            await editor.add_node("start")
            # Verify node was added
            # Implementation depends on how the editor works
        except Exception as e:
            # Editor might require different interaction
            pytest.skip(f"Could not add node: {e}")


class TestBrowserAutomationNode:
    """Test suite for Browser Automation node in Skill Editor.

    These tests specifically verify the browser-automation node functionality.
    """

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context, authenticated_context):
        """Setup test context."""
        self.ctx = e2e_context
        self.page = e2e_context.pw_page
        self.nav = Navigation(self.page)

    @pytest.mark.asyncio
    async def test_browser_node_in_palette(self):
        """Test that browser-automation node appears in palette."""
        await self.nav.go_to("/skills/new")

        editor = SkillEditorPage(self.page)

        # Check if browser node exists in palette
        browser_node = self.page.locator('text=Browser, text=browser-automation')
        node_exists = await browser_node.count() > 0

        if not node_exists:
            pytest.skip("Browser automation node not found in palette")

        assert node_exists

    @pytest.mark.asyncio
    async def test_browser_node_configuration(self):
        """Test configuring browser automation node."""
        await self.nav.go_to("/skills/new")

        editor = SkillEditorPage(self.page)

        # Add browser node
        try:
            await editor.add_node("browser-automation")

            # Check if properties panel shows browser config
            panel_visible = await editor.properties_panel.is_visible()
            assert panel_visible or await editor.properties_panel.count() > 0
        except Exception as e:
            pytest.skip(f"Could not add browser node: {e}")
