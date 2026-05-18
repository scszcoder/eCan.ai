# Browser Automation Tests

This directory contains tests for the browser-automation node functionality in eCan.ai.

## Directory Structure

```
tests/
├── browser_automation/                    # Browser automation tests
│   ├── README.md                        # This file
│   ├── conftest.py                      # Shared pytest fixtures
│   ├── mock_infrastructure.py           # Mock classes for testing
│   ├── test_config.py                  # Configuration parsing tests (unit)
│   ├── test_runner_integration.py      # Runner integration tests
│   ├── test_e2e.py                     # End-to-end tests (requires GUI)
│   ├── __init__.py
│   └── tests/                           # Integration tests
│       ├── __init__.py
│       ├── test_file_reader.py         # File/folder reading tests
│       ├── test_browser_real.py       # Real browser-use tests
│       └── test_skill_e2e.py          # Skill framework e2e tests
│
├── test_data/                          # Test data
│   └── product_listing/                # Product listing test data
│       ├── product_info.txt            # Plain text product info
│       ├── product_info.json           # JSON format product info
│       └── product_info.md             # Markdown format product info
```

## Test Categories

### 1. Unit Tests (test_config.py)
Tests the pure parsing logic without any GUI or browser dependencies.

```bash
pytest tests/browser_automation/test_config.py -v
```

### 2. Integration Tests (test_runner_integration.py)
Tests the BrowserUseRunner and hook mechanisms with mocked browser sessions.

```bash
pytest tests/browser_automation/test_runner_integration.py -v
```

### 3. File Reader Tests (tests/test_file_reader.py)
Tests file/folder detection and reading logic.

```bash
pytest tests/browser_automation/tests/test_file_reader.py -v
```

### 4. Real Browser Tests (tests/test_browser_real.py)
Tests using real browser-use library.

```bash
# Run non-browser tests only
pytest tests/browser_automation/tests/test_browser_real.py -v -m "not browser"

# Run with real browser (manual testing)
pytest tests/browser_automation/tests/test_browser_real.py -v -m browser
```

### 5. Skill E2E Tests (tests/test_skill_e2e.py)
Tests for the skill framework with product listing workflow.

```bash
# Run TEXT input tests
pytest tests/browser_automation/tests/test_skill_e2e.py -v -k "Text"

# Run file tests
pytest tests/browser_automation/tests/test_skill_e2e.py -v -k "File"
```

## Test Data

Test data files are located in `tests/test_data/product_listing/`:

- `product_info.txt` - Plain text product info (iPhone 15 Pro Max)
- `product_info.json` - JSON format product info (AirPods Pro 2代)
- `product_info.md` - Markdown format product info (索尼 A7M4)

## Running All Tests

```bash
# Run all browser automation tests
pytest tests/browser_automation/ -v

# Skip slow tests
pytest tests/browser_automation/ -v -m "not browser"

# Quick smoke test
pytest tests/browser_automation/tests/test_file_reader.py tests/browser_automation/tests/test_browser_real.py::TestFileReading -v
```

## Markers

- `@pytest.mark.browser` - Tests that require real browser (skipped by default)
- `@pytest.mark.gui` - Tests that require GUI environment
- `@pytest.mark.integration` - Tests with mocked external dependencies
- `@pytest.mark.unit` - Pure unit tests without dependencies

## Test Results Summary

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_config.py` | 22 | Configuration parsing |
| `test_runner_integration.py` | 17 | Runner integration |
| `test_file_reader.py` | 9 | File/folder detection |
| `test_browser_real.py` | 9 | Browser module tests |
| `test_skill_e2e.py` | 13 | Skill framework tests |

**Total: 70 tests (63 passed, 7 skipped)**
