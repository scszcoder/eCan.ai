"""E2E Page Objects - Page Object Model implementations for eCan.ai.

This module contains Page Object classes for common pages in the application.
"""

from typing import Optional

from tests.e2e.base import PageObject


# ============================================================================
# Authentication Pages
# ============================================================================

class LoginPage(PageObject):
    """Page Object for Login page.

    Usage:
        login = LoginPage(page)
        await login.navigate()
        await login.login("user", "pass")
    """

    @property
    def url(self) -> str:
        return "/login"

    # Locators
    @property
    def username_input(self):
        return self.page.locator('input[name="username"], input[type="text"]')

    @property
    def email_input(self):
        return self.page.locator('input[type="email"], input[name="email"]')

    @property
    def password_input(self):
        return self.page.locator('input[type="password"]')

    @property
    def submit_button(self):
        return self.page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign in")')

    @property
    def error_message(self):
        return self.page.locator('.error, .alert-error, [role="alert"], .text-red-500')

    @property
    def forgot_password_link(self):
        return self.page.locator('a:has-text("Forgot"), a:has-text("Reset")')

    # Actions
    async def login(self, username: str, password: str, use_email: bool = False) -> None:
        """Perform login action.

        Args:
            username: Username or email
            password: Password
            use_email: Use email field instead of username
        """
        if use_email:
            await self.email_input.fill(username)
        else:
            await self.username_input.fill(username)

        await self.password_input.fill(password)
        await self.submit_button.click()

    async def get_error(self) -> Optional[str]:
        """Get error message text if visible."""
        if await self.error_message.is_visible():
            return await self.error_message.text_content()
        return None


class LogoutPage(PageObject):
    """Page Object for logout functionality."""

    @property
    def url(self) -> str:
        return "/"  # Usually triggered from any page

    @property
    def user_menu(self):
        return self.page.locator('[class*="user"], [class*="avatar"], button:has-text("User")')

    @property
    def logout_button(self):
        return self.page.locator('button:has-text("Logout"), button:has-text("Sign out"), a:has-text("Logout")')

    async def logout(self) -> None:
        """Perform logout action."""
        await self.user_menu.click()
        await self.logout_button.click()


# ============================================================================
# Tasks Pages
# ============================================================================

class TaskListPage(PageObject):
    """Page Object for Tasks list page.

    Usage:
        task_list = TaskListPage(page)
        await task_list.navigate()
        tasks = await task_list.get_tasks()
    """

    @property
    def url(self) -> str:
        return "/tasks"

    # Locators
    @property
    def task_table(self):
        return self.page.locator('table, [role="grid"], .task-list')

    @property
    def task_rows(self):
        return self.page.locator('tbody tr, .task-item')

    @property
    def create_button(self):
        return self.page.locator('button:has-text("New"), button:has-text("Create"), a:has-text("New Task")')

    @property
    def filter_input(self):
        return self.page.locator('input[type="search"], input[placeholder*="Filter"], input[placeholder*="Search"]')

    @property
    def empty_state(self):
        return self.page.locator('.empty, .no-data, text=No tasks')

    # Actions
    async def get_tasks(self) -> list:
        """Get list of tasks from table."""
        rows = self.task_rows
        count = await rows.count()
        tasks = []

        for i in range(count):
            row = rows.nth(i)
            tasks.append({
                "element": row,
                "title": await row.locator('td:first-child, .task-title').text_content(),
            })

        return tasks

    async def click_task(self, title: str) -> None:
        """Click on a task by title."""
        await self.page.locator(f'text={title}').click()

    async def create_task(self) -> None:
        """Click create new task button."""
        await self.create_button.click()

    async def filter_tasks(self, query: str) -> None:
        """Filter tasks by search query."""
        await self.filter_input.fill(query)


class TaskDetailPage(PageObject):
    """Page Object for Task detail/edit page.

    Usage:
        task_detail = TaskDetailPage(page)
        await task_detail.navigate(task_id="123")
        await task_detail.update_title("New Title")
    """

    def __init__(self, page, task_id: str = None):
        super().__init__(page, base_path="/tasks")
        self._task_id = task_id

    @property
    def url(self) -> str:
        if self._task_id:
            return f"/tasks/{self._task_id}"
        return "/tasks/new"

    # Locators
    @property
    def title_input(self):
        return self.page.locator('input[name="title"], input[placeholder*="Title"]')

    @property
    def description_input(self):
        return self.page.locator('textarea[name="description"], textarea[placeholder*="Description"]')

    @property
    def priority_select(self):
        return self.page.locator('select[name="priority"], [class*="priority"]')

    @property
    def save_button(self):
        return self.page.locator('button:has-text("Save"), button[type="submit"]')

    @property
    def delete_button(self):
        return self.page.locator('button:has-text("Delete"), button:has-text("Remove")')

    @property
    def back_button(self):
        return self.page.locator('a:has-text("Back"), button:has-text("Back")')

    # Actions
    async def fill_title(self, title: str) -> None:
        await self.title_input.fill(title)

    async def fill_description(self, description: str) -> None:
        await self.description_input.fill(description)

    async def select_priority(self, priority: str) -> None:
        """Select priority: low, medium, high, urgent."""
        await self.priority_select.select_option(priority)

    async def save(self) -> None:
        await self.save_button.click()

    async def delete(self) -> None:
        await self.delete_button.click()
        # Handle confirmation dialog
        self.page.on("dialog", lambda dialog: dialog.accept())


# ============================================================================
# Skills Pages
# ============================================================================

class SkillsPage(PageObject):
    """Page Object for Skills list page."""

    @property
    def url(self) -> str:
        return "/skills"

    @property
    def skill_cards(self):
        return self.page.locator('.skill-card, [class*="skill"], .card')

    @property
    def create_button(self):
        return self.page.locator('button:has-text("New"), a:has-text("New Skill")')

    @property
    def search_input(self):
        return self.page.locator('input[type="search"], input[placeholder*="Search"]')


class SkillEditorPage(PageObject):
    """Page Object for Skill editor page.

    Usage:
        editor = SkillEditorPage(page)
        await editor.navigate(skill_id="123")
        await editor.add_node("start")
        await editor.connect_nodes("start", "end")
    """

    def __init__(self, page, skill_id: str = None):
        super().__init__(page, base_path="/skills")
        self._skill_id = skill_id

    @property
    def url(self) -> str:
        if self._skill_id:
            return f"/skills/{self._skill_id}/edit"
        return "/skills/new"

    # Locators
    @property
    def canvas(self):
        return self.page.locator('[class*="canvas"], [class*="graph"], svg[class*="sigma"]')

    @property
    def node_palette(self):
        return self.page.locator('[class*="palette"], [class*="nodes"]')

    @property
    def save_button(self):
        return self.page.locator('button:has-text("Save")')

    @property
    def run_button(self):
        return self.page.locator('button:has-text("Run"), button:has-text("Execute")')

    @property
    def properties_panel(self):
        return self.page.locator('[class*="properties"], [class*="config"]')

    # Node operations
    async def add_node(self, node_type: str) -> None:
        """Add a node of specified type to the canvas."""
        # Drag from palette to canvas or click to add
        node_item = self.node_palette.locator(f'text={node_type}')
        if await node_item.count() > 0:
            await node_item.drag_to(self.canvas)
        else:
            # Click on canvas to add
            await self.canvas.click(position={"x": 200, "y": 200})

    async def connect_nodes(self, source_id: str, target_id: str) -> None:
        """Connect two nodes with an edge."""
        # This is canvas-specific, implementation depends on editor
        pass

    async def select_node(self, node_id: str) -> None:
        """Select a node by ID."""
        await self.canvas.locator(f'[data-node-id="{node_id}"]').click()


# ============================================================================
# Settings Pages
# ============================================================================

class SettingsPage(PageObject):
    """Page Object for Settings page."""

    @property
    def url(self) -> str:
        return "/settings"

    @property
    def api_key_input(self):
        return self.page.locator('input[name="apiKey"], input[placeholder*="API Key"]')

    @property
    def save_settings_button(self):
        return self.page.locator('button:has-text("Save")')

    async def set_api_key(self, api_key: str) -> None:
        await self.api_key_input.fill(api_key)
        await self.save_settings_button.click()


# ============================================================================
# Navigation
# ============================================================================

class Navigation:
    """Navigation helper for accessing different pages.

    Usage:
        nav = Navigation(page)
        await nav.go_to_tasks()
        await nav.go_to_settings()
    """

    def __init__(self, page):
        self._page = page

    @property
    def page(self):
        return self._page

    async def go_to(self, path: str) -> None:
        await self._page.goto(path)
        await self._page.wait_for_load_state("networkidle")

    async def go_to_tasks(self) -> TaskListPage:
        await self.go_to("/tasks")
        return TaskListPage(self._page)

    async def go_to_skills(self) -> SkillsPage:
        await self.go_to("/skills")
        return SkillsPage(self._page)

    async def go_to_settings(self) -> SettingsPage:
        await self.go_to("/settings")
        return SettingsPage(self._page)

    async def go_to_login(self) -> LoginPage:
        await self.go_to("/login")
        return LoginPage(self._page)

    @property
    async def current_page(self) -> str:
        return self._page.url
