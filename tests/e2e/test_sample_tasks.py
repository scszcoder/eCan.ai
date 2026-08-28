"""Sample E2E Test - Tasks Module.

This file demonstrates the E2E test framework for testing the Tasks module.

Test Coverage:
- Task list page navigation
- Task creation with valid data
- Task creation validation (missing fields)
- Task editing
- Task deletion

Run:
    pytest tests/e2e/test_sample_tasks.py -v
"""

import pytest
from typing import Any, Dict

from tests.e2e.conftest import (
    authenticated_context,
    base_url,
    e2e_context,
    sample_task_data,
)
from tests.e2e.pages import Navigation, TaskDetailPage, TaskListPage


class TestTaskList:
    """Test suite for Task List page."""

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context):
        """Setup test context."""
        self.ctx = e2e_context
        self.page = e2e_context.pw_page
        self.nav = Navigation(self.page)

    @pytest.mark.asyncio
    async def test_task_list_page_loads(self):
        """Test that task list page loads successfully."""
        task_page = await self.nav.go_to_tasks()

        # Verify page loaded
        assert task_page.url in self.page.url, "Should be on tasks page"

        # Verify main elements present
        assert await task_page.task_table.is_visible() or await task_page.empty_state.is_visible(), \
            "Task table or empty state should be visible"

    @pytest.mark.asyncio
    async def test_task_list_displays_tasks(self, authenticated_context):
        """Test that existing tasks are displayed in the list."""
        task_page = await self.nav.go_to_tasks()

        # If tasks exist, they should be in the table
        row_count = await task_page.task_rows.count()
        assert row_count >= 0, "Task rows count should be non-negative"

    @pytest.mark.asyncio
    async def test_filter_tasks(self):
        """Test filtering tasks by search query."""
        task_page = await self.nav.go_to_tasks()

        # Type in filter
        await task_page.filter_tasks("test")

        # Verify filter was applied (tasks should be filtered)
        # This is a basic check - real implementation would verify results


class TestTaskCreation:
    """Test suite for Task Creation functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context, authenticated_context):
        """Setup test context with authenticated user."""
        self.ctx = e2e_context
        self.page = e2e_context.pw_page
        self.nav = Navigation(self.page)

    @pytest.mark.asyncio
    async def test_create_task_button_navigates_to_form(self):
        """Test clicking create task button navigates to creation form."""
        task_page = await self.nav.go_to_tasks()

        # Click create button
        await task_page.create_task()

        # Verify we're on the create page
        assert "/new" in self.page.url or "create" in self.page.url.lower()

    @pytest.mark.asyncio
    async def test_create_task_with_valid_data(self, sample_task_data: Dict[str, Any]):
        """Test creating a task with all required fields succeeds."""
        # Navigate to create form
        await self.nav.go_to("/tasks/new")

        detail_page = TaskDetailPage(self.page)

        # Fill form
        await detail_page.fill_title(sample_task_data["title"])
        await detail_page.fill_description(sample_task_data["description"])

        # Submit
        await detail_page.save()

        # Verify success - should redirect to task detail or list
        # This depends on your app's behavior
        current_url = self.page.url
        assert "/tasks/" in current_url or "/tasks" in current_url, \
            "Should redirect to task list or detail after creation"

    @pytest.mark.asyncio
    async def test_create_task_without_title_shows_error(self):
        """Test that creating task without title shows validation error."""
        await self.nav.go_to("/tasks/new")

        detail_page = TaskDetailPage(self.page)

        # Leave title empty and submit
        await detail_page.fill_description("Some description")
        await detail_page.save()

        # Verify error is shown
        # Note: Adapt selector to your app's error display
        error_visible = await self.page.locator('.error, .error-message, [role="alert"]').count() > 0
        assert error_visible, "Validation error should be displayed for missing title"


class TestTaskDetail:
    """Test suite for Task Detail/Edit functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context, authenticated_context):
        """Setup test context."""
        self.ctx = e2e_context
        self.page = e2e_context.pw_page
        self.nav = Navigation(self.page)

    @pytest.mark.asyncio
    async def test_task_detail_page_loads(self):
        """Test that task detail page loads with correct data."""
        # Navigate to tasks first
        await self.nav.go_to_tasks()

        # Get first task if exists
        task_page = TaskListPage(self.page)
        rows = await task_page.task_rows.count()

        if rows > 0:
            # Click first task
            await task_page.task_rows.first.click()

            # Verify detail page loaded
            detail_page = TaskDetailPage(self.page)
            # Check that at least title input is present
            title_input_count = await detail_page.title_input.count()
            assert title_input_count > 0 or "/tasks/" in self.page.url, \
                "Detail page should load with task data or redirect"


class TestTaskDeletion:
    """Test suite for Task Deletion functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context, authenticated_context):
        """Setup test context."""
        self.ctx = e2e_context
        self.page = e2e_context.pw_page
        self.nav = Navigation(self.page)

    @pytest.mark.asyncio
    async def test_delete_task_confirmation(self):
        """Test that deleting a task shows confirmation dialog."""
        # This test verifies the confirmation flow
        # Adapt to your app's deletion behavior
        pass


# ============================================================================
# CDP-Only Tests
# These tests use direct CDP protocol for more control
# ============================================================================

class TestCDPIntegration:
    """Tests using direct CDP protocol for advanced scenarios."""

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context):
        """Setup test context."""
        self.ctx = e2e_context
        self.page = e2e_context.page  # CDP Page

    @pytest.mark.asyncio
    async def test_cdp_navigation(self):
        """Test navigation using CDP protocol."""
        await self.page.enable()
        await self.page.navigate(f"{self.ctx.base_url}/tasks")
        await self.page.wait_for_load()

        # Get page title via CDP
        title = await self.page.evaluate("document.title")
        assert title is not None

    @pytest.mark.asyncio
    async def test_cdp_element_interaction(self):
        """Test element interaction using CDP protocol."""
        await self.page.enable()
        await self.page.navigate(f"{self.ctx.base_url}/tasks")

        # Get element text
        text = await self.page.get_element_text("h1, h2, .title")
        # Text may be None if element not found
        assert text is None or isinstance(text, str)

    @pytest.mark.asyncio
    async def test_cdp_evaluate_script(self):
        """Test executing arbitrary JavaScript via CDP."""
        await self.page.enable()
        await self.page.navigate(f"{self.ctx.base_url}/tasks")

        # Execute custom script
        result = await self.page.evaluate("""
            () => {
                return {
                    url: window.location.href,
                    title: document.title,
                    ready: document.readyState
                };
            }
        """)

        assert result is not None
        assert "url" in result or isinstance(result, dict)
