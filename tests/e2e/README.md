# E2E Testing Framework

A self-contained E2E testing framework for the eCan.ai application with browser automation support.

## Features

- **Browser Launcher**: Auto-launch Chrome/Firefox/Edge with CDP debugging
- **CDP Connector**: Direct Chrome DevTools Protocol access for fine-grained control
- **Playwright Integration**: High-level browser automation via Playwright
- **Page Object Model**: Clean separation of test code and page structure
- **pytest Integration**: Native pytest fixtures and markers

---

## Quick Start

### 1. Installation

```bash
# Install dependencies
pip install pytest pytest-asyncio playwright websockets

# Install Playwright browsers
playwright install chromium
```

### 2. Start the Application

```bash
# Start the web application
cd gui_v2
npm run dev  # Runs on http://localhost:3000

# Or in another terminal:
python main.py
```

### 3. Run Tests

```bash
# Start the main web application
cd gui_v2
npm run dev  # Runs on http://localhost:3000

# In another terminal, start the IM workbench target when running IM tests
cd tests/targets/im-workbench
npm run dev  # Runs on http://localhost:4173

# Run all E2E tests
pytest tests/e2e/ -v

# Run IM workbench tests only
pytest tests/e2e/test_chat_simulator.py -v

# Run with visible browser (headless=False)
E2E_HEADLESS=false pytest tests/e2e/ -v

# Run with CDP port 9223
E2E_CDP_PORT=9223 pytest tests/e2e/ -v
```

---

## Architecture

```
tests/
├── e2e_framework/          # Core framework
│   └── __init__.py         # BrowserLauncher, CDPConnector, E2ETestContext
├── e2e_rules.md           # Test generation rules
├── conftest.py            # pytest fixtures
├── base.py                # Base classes (PageObject, E2ETestMixin)
├── pages.py               # Page Object implementations
├── test_sample_tasks.py   # Example: Tasks module tests
├── test_sample_skills.py  # Example: Skills module tests
└── README.md             # This file
```

---

## Usage

### Option 1: Using E2ETestContext (Recommended)

The `E2ETestContext` provides both Playwright and CDP access:

```python
import pytest
from tests.e2e_framework import E2ETestContext

@pytest.mark.asyncio
async def test_example():
    async with E2ETestContext(
        base_url="http://localhost:3000",
        cdp_port=9222,
        headless=True,
    ) as ctx:
        # High-level Playwright API
        await ctx.pw_page.goto(f"{ctx.base_url}/tasks")
        await ctx.pw_page.fill('input[name="title"]', "My Task")
        await ctx.pw_page.click('button[type="submit"]')

        # Low-level CDP API (for advanced control)
        await ctx.page.enable()
        await ctx.page.navigate(f"{ctx.base_url}/tasks")
```

### Option 2: Direct Browser Launch

```python
from tests.e2e_framework import BrowserLauncher, CDPConnector, CDPPage

# Launch browser
proc = BrowserLauncher.launch(
    browser_type=BrowserType.CHROME,
    headless=False,
    cdp_port=9222,
)

# Get CDP WebSocket URL
ws_url = BrowserLauncher.get_cdp_ws_url(9222)

# Connect via CDP
async with CDPConnector(ws_url) as cdp:
    page = CDPPage(cdp)
    await page.enable()
    await page.navigate("http://localhost:3000/tasks")
```

### Option 3: Connect to Existing Browser

If you already have a browser running with remote debugging:

```python
# Chrome started with: chrome --remote-debugging-port=9222
from tests.e2e_framework import BrowserLauncher

ws_url = BrowserLauncher.get_cdp_ws_url(9222)
# ws://127.0.0.1:9222/devtools/browser/...

# Use ws_url with Playwright or CDPConnector
```

---

## Writing Tests

### Basic Test Structure

```python
"""Test <Feature> <Scenario>.

Run: pytest tests/e2e/<this_file>.py -v
"""

import pytest
from tests.e2e.conftest import e2e_context

class TestFeatureScenario:
    """Test class for feature scenarios."""

    @pytest.fixture(autouse=True)
    async def setup(self, e2e_context):
        """Setup test context."""
        self.ctx = e2e_context
        self.page = e2e_context.pw_page
        yield
        # Cleanup if needed

    @pytest.mark.asyncio
    async def test_something(self):
        """Test description."""
        await self.page.goto(f"{self.ctx.base_url}/path")
        # assertions...
```

### Using Page Objects

```python
from tests.e2e.pages import TaskListPage, Navigation

@pytest.mark.asyncio
async def test_with_page_object(self, e2e_context):
    page = e2e_context.pw_page

    # Using Navigation helper
    nav = Navigation(page)
    task_page = await nav.go_to_tasks()

    # Using Page Objects
    tasks = await task_page.get_tasks()
    assert len(tasks) >= 0
```

### CDP-Only Tests

```python
@pytest.mark.asyncio
async def test_with_cdp(self, e2e_context):
    cdp_page = e2e_context.page  # CDP Page object

    await cdp_page.enable()
    await cdp_page.navigate("https://example.com")
    await cdp_page.wait_for_load()

    # Execute JavaScript
    result = await cdp_page.evaluate("document.title")

    # Get element text
    text = await cdp_page.get_element_text("h1")

    # Screenshot
    img = await cdp_page.screenshot()
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_BASE_URL` | `http://localhost:3000` | Application base URL |
| `E2E_CDP_PORT` | `9222` | CDP debugging port |
| `E2E_HEADLESS` | `true` | Run browser headless |
| `E2E_BROWSER` | `chrome` | Browser type: chrome/firefox/edge |
| `E2E_TIMEOUT` | `30000` | Default timeout (ms) |

### pytest Configuration

In `pytest.ini`:

```ini
[pytest]
testpaths = tests/e2e
python_files = test_*.py
asyncio_mode = auto
markers =
    e2e: End-to-end tests
    slow: Tests taking > 10s
    browser: Tests requiring browser
```

---

## Test Generation Rules

See [tests/e2e_rules.md](tests/e2e_rules.md) for detailed rules on:

- File naming conventions
- Test structure and organization
- Page Object Model patterns
- Browser/CDP configuration
- Error handling and reporting

---

## CLI Usage

### Launch Browser Manually

```bash
python -m tests.e2e_framework
```

This will:
1. Launch Chrome with remote debugging on port 9222
2. Print available browser targets
3. Print CDP WebSocket URL
4. Wait for Enter to close

### Connect to Existing Browser

```python
from tests.e2e_framework import CDPConnector, CDPPage

# Get the WebSocket URL from browser
# Chrome: Navigate to http://localhost:9222/json
ws_url = "ws://localhost:9222/devtools/page/..."

async with CDPConnector(ws_url) as cdp:
    page = CDPPage(cdp)
    await page.enable()
    await page.navigate("https://example.com")
```

---

## Troubleshooting

### Browser Won't Launch

```bash
# Check if Chrome is installed
which google-chrome

# Or install Chrome/Chromium
brew install --cask google-chrome  # macOS
apt install chromium-browser       # Linux
```

### CDP Connection Failed

```bash
# Ensure no other browser is using the port
lsof -i :9222

# Try a different port
E2E_CDP_PORT=9223 pytest tests/e2e/ -v
```

### Playwright Not Installed

```bash
pip install playwright
playwright install chromium
```

### Tests Timeout

Increase timeout in configuration:
```bash
E2E_TIMEOUT=60000 pytest tests/e2e/ -v
```

---

## Examples

See the `tests/e2e/` directory for complete examples:

- `test_sample_tasks.py` - Tasks module tests
- `test_sample_skills.py` - Skills module tests

---

## License

Internal use only.
