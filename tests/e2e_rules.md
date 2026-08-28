# E2E Test Generation Rules

## Overview

This file defines the standards and patterns for generating E2E test scripts for the eCan.ai application. These rules ensure consistent, maintainable, and reliable automated tests.

---

## Rule 1: Test File Structure

### Location
- E2E tests: `tests/e2e/`
- Test fixtures: `tests/e2e/fixtures/`
- Test utilities: `tests/e2e/utils/`

### Naming Convention
```
test_<feature>_<scenario>.py
  ↑        ↑          ↑
  prefix   feature    description
```

**Examples:**
- `test_auth_login.py`
- `test_tasks_create_and_delete.py`
- `test_skills_workflow_execution.py`

### Test Class Structure

```python
"""Test <Feature> <Scenario>.

Test Description:
1. Preconditions: <what must be true before test>
2. Actions: <steps to perform>
3. Expected: <what should happen>

Run: pytest tests/e2e/<this_file>.py -v
"""

import pytest
from tests.e2e_framework import E2ETestContext


class TestFeatureScenario:
    """Test class for <feature> <scenario>."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Setup test context."""
        async with E2ETestContext(
            base_url="http://localhost:3000",
            cdp_port=9222,
            headless=True,
        ) as ctx:
            self.ctx = ctx
            yield ctx

    # Test methods...
```

---

## Rule 2: Test Naming Conventions

### Function Names
- Start with `test_`
- Use snake_case
- Describe the expected behavior

**Good:**
```python
def test_login_with_valid_credentials_succeeds():
def test_task_creation_requires_title():
def test_skill_editor_saves_workflow():
```

**Bad:**
```python
def test_login():  # Too vague
def test_create():  # Missing context
def test_1():  # Not descriptive
```

### Descriptive Pattern
```
test_<subject>_<action>_<expected_result>
```

---

## Rule 3: Test Design Principles

### 3.1 Single Responsibility
Each test should verify ONE specific behavior.

**Good:**
```python
def test_login_displays_error_for_invalid_password():
    """Login form shows error message when password is wrong."""

def test_login_redirects_to_dashboard_on_success():
    """Successful login redirects user to dashboard."""
```

**Bad:**
```python
def test_login():
    """Test login with various credentials and check everything."""
    # This tests too many things!
```

### 3.2 Test Independence
- Tests must NOT depend on other tests
- Each test sets up its own prerequisites
- Use fixtures for common setup

### 3.3 Deterministic Tests
- Tests must produce the same result every run
- Avoid time-based assertions when possible
- Mock external dependencies if needed

### 3.4 Clear Assertions
- Use descriptive assertion messages
- Assert specific values, not just truthiness

**Good:**
```python
assert response.status_code == 200, "Login endpoint should return 200"
assert "Welcome" in page.content, "Dashboard should show welcome message"
```

**Bad:**
```python
assert response.ok
assert page.content
```

---

## Rule 4: Page Object Model (POM)

Use Page Object pattern for UI interactions.

### Structure

```python
# tests/e2e/pages/login_page.py
class LoginPage:
    """Page Object for Login page."""

    def __init__(self, page):
        self.page = page

    @property
    def username_input(self):
        return self.page.locator('input[name="username"]')

    @property
    def password_input(self):
        return self.page.locator('input[name="password"]')

    @property
    def submit_button(self):
        return self.page.locator('button[type="submit"]')

    @property
    def error_message(self):
        return self.page.locator('.error-message')

    async def login(self, username: str, password: str):
        """Perform login action."""
        await self.username_input.fill(username)
        await self.password_input.fill(password)
        await self.submit_button.click()

    async def get_error(self) -> str:
        """Get error message text."""
        return await self.error_message.text_content()
```

### Usage in Tests

```python
from tests.e2e.pages.login_page import LoginPage

@pytest.mark.asyncio
async def test_login_success(self, setup):
    page = LoginPage(self.ctx.pw_page)
    await page.login("admin", "password123")

    # Verify redirect to dashboard
    assert "/dashboard" in self.ctx.pw_page.url
```

---

## Rule 5: Browser & CDP Configuration

### 5.1 Browser Selection

```python
from tests.e2e_framework import BrowserType, BrowserLauncher

# For most tests: Use headless Chrome
proc = BrowserLauncher.launch(
    browser_type=BrowserType.CHROME,
    headless=True,
    cdp_port=9222,
)

# For debugging: Use visible browser
proc = BrowserLauncher.launch(
    browser_type=BrowserType.CHROME,
    headless=False,
    cdp_port=9222,
)

# For cross-browser testing
BROWSERS = [
    BrowserType.CHROME,
    BrowserType.FIREFOX,
    BrowserType.EDGE,
]
```

### 5.2 CDP Connection Options

```python
# Option 1: Use E2ETestContext (recommended)
async with E2ETestContext(base_url="http://localhost:3000") as ctx:
    # ctx.pw_page - Playwright page object
    # ctx.page - CDP page object
    pass

# Option 2: Direct CDP connection
from tests.e2e_framework import BrowserLauncher, CDPConnector

ws_url = BrowserLauncher.get_cdp_ws_url(9222)
cdp = CDPConnector(ws_url)
await cdp.connect()

# Option 3: Connect to existing browser
EXISTING_BROWSER_WS = "ws://localhost:9222/devtools/page/..."
cdp = CDPConnector(EXISTING_BROWSER_WS)
```

### 5.3 Test Markers

```python
import pytest

@pytest.mark.e2e           # General E2E tests
@pytest.mark.slow          # Tests taking > 10s
@pytest.mark.browser       # Tests requiring real browser
@pytest.mark.requires_auth # Tests requiring logged-in user
```

---

## Rule 6: Test Data Management

### 6.1 Fixtures for Test Data

```python
# tests/e2e/fixtures/test_data.py
import pytest

@pytest.fixture
def test_user():
    """Return test user credentials."""
    return {
        "username": "test_user_001",
        "email": "test@example.com",
        "password": "TestPass123!",
    }

@pytest.fixture
def sample_task():
    """Return sample task data."""
    return {
        "title": "E2E Test Task",
        "description": "Created by automated test",
        "priority": "high",
    }
```

### 6.2 Cleanup

```python
@pytest.fixture
async def cleanup_test_tasks(self):
    """Cleanup created tasks after test."""
    created_ids = []

    yield created_ids.append

    # Cleanup
    for task_id in created_ids:
        await delete_task(task_id)
```

---

## Rule 7: Common Test Scenarios

### 7.1 Navigation Tests

```python
@pytest.mark.asyncio
async def test_navigation_to_tasks_page(self, setup):
    """Verify navigation to Tasks page."""
    await self.ctx.pw_page.goto(f"{self.ctx.base_url}/tasks")
    await self.ctx.pw_page.wait_for_load_state("networkidle")

    # Verify page loaded
    assert "Tasks" in await self.ctx.pw_page.title()

    # Verify key elements present
    assert await self.ctx.pw_page.locator("table").count() > 0
```

### 7.2 Form Submission Tests

```python
@pytest.mark.asyncio
async def test_create_task_with_valid_data(self, setup):
    """Test creating a task with all required fields."""
    # Navigate to create form
    await self.ctx.pw_page.goto(f"{self.ctx.base_url}/tasks/new")

    # Fill form
    await self.ctx.pw_page.fill('input[name="title"]', "New Task")
    await self.ctx.pw_page.fill('textarea[name="description"]', "Task description")

    # Submit
    await self.ctx.pw_page.click('button[type="submit"]')

    # Verify success
    await self.ctx.pw_page.wait_for_url("**/tasks/**")
    assert "New Task" in await self.ctx.pw_page.content()
```

### 7.3 Validation Tests

```python
@pytest.mark.asyncio
async def test_create_task_without_title_shows_error(self, setup):
    """Test that creating task without title shows validation error."""
    await self.ctx.pw_page.goto(f"{self.ctx.base_url}/tasks/new")

    # Leave title empty and submit
    await self.ctx.pw_page.click('button[type="submit"]')

    # Verify error message
    error = self.ctx.pw_page.locator(".error-title")
    assert await error.is_visible()
    assert "required" in (await error.text_content()).lower()
```

### 7.4 CRUD Tests

```python
@pytest.mark.asyncio
async def test_full_task_crud_workflow(self, setup):
    """Test complete Create-Read-Update-Delete workflow."""

    # CREATE
    task_id = await create_task({"title": "CRUD Test Task"})
    assert task_id is not None

    # READ
    task = await get_task(task_id)
    assert task["title"] == "CRUD Test Task"

    # UPDATE
    updated = await update_task(task_id, {"title": "Updated Task"})
    assert updated["title"] == "Updated Task"

    # DELETE
    await delete_task(task_id)
    assert await get_task(task_id) is None
```

---

## Rule 8: Error Handling & Reporting

### 8.1 Screenshot on Failure

```python
import pytest
from pathlib import Path

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_makereport(item, call):
    """Take screenshot on test failure."""
    if call.when == "call" and call.excinfo is not None:
        # Get the driver from test
        if hasattr(item, "funcargs") and "setup" in item.funcargs:
            ctx = item.funcargs["setup"]
            if hasattr(ctx, "pw_page"):
                screenshot_dir = Path("tests/e2e/screenshots")
                screenshot_dir.mkdir(parents=True, exist_ok=True)

                filename = f"{item.name}_{int(time.time())}.png"
                asyncio.get_event_loop().run_until_complete(
                    ctx.pw_page.screenshot(path=str(screenshot_dir / filename))
                )
                print(f"\nScreenshot saved: {screenshot_dir / filename}")
```

### 8.2 Console Logging

```python
import logging

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_something(self, setup):
    """Test with logging."""
    logger.info("Starting test_something")
    try:
        # Test steps with logging
        logger.debug("Navigating to page...")
        await self.ctx.pw_page.goto(url)

        logger.debug("Filling form...")
        await self.ctx.pw_page.fill("input", "value")

        logger.info("Test completed successfully")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
```

---

## Rule 9: Performance & Best Practices

### 9.1 Timeouts

```python
# Use appropriate timeouts
await page.wait_for_selector(".element", timeout=5000)  # 5s for fast elements
await page.wait_for_load_state("networkidle", timeout=30000)  # 30s for page load
```

### 9.2 Waits over Sleeps

**Good:**
```python
await page.wait_for_selector(".loading", state="hidden")
await expect(page.locator(".result")).to_be_visible()
```

**Bad:**
```python
time.sleep(2)  # Arbitrary sleep - don't use!
```

### 9.3 Parallel Execution

```python
# pytest.ini
[pytest]
addopts = -n auto  # Run tests in parallel with pytest-xdist
```

---

## Rule 10: CI/CD Integration

### 10.1 Environment Variables

```bash
# .env.test
E2E_BASE_URL=http://localhost:3000
E2E_CDP_PORT=9222
E2E_HEADLESS=true
E2E_BROWSER=chrome
```

### 10.2 CI Pipeline

```yaml
# .github/workflows/e2e.yml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install pytest pytest-asyncio playwright
          playwright install chromium

      - name: Start application
        run: python main.py &
        env:
          E2E_MODE: true

      - name: Run E2E tests
        run: pytest tests/e2e/ -v --tb=short
        env:
          E2E_BASE_URL: http://localhost:3000
          E2E_HEADLESS: true
```

---

## Summary Checklist

Before submitting E2E tests, verify:

- [ ] Test file follows naming convention (`test_<feature>_<scenario>.py`)
- [ ] Test function names are descriptive (`test_<subject>_<action>_<result>`)
- [ ] Each test has ONE clear assertion/verification
- [ ] Tests are independent (don't depend on execution order)
- [ ] Page Objects used for UI interactions
- [ ] Appropriate timeouts configured
- [ ] Error handling with screenshots on failure
- [ ] Documentation comment explaining test purpose
- [ ] Run: `pytest tests/e2e/<file>.py -v` passes
