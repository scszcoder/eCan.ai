"""Unit tests for MCP server tools (self_utils, code_utils).

These tests use the standalone implementations from tests/test_mcp_server_tools.py
which are self-contained and do not require external dependencies.
"""

import platform
import pytest

pytestmark = pytest.mark.unit


# ============================================================================
# CodeExecutionResult
# ============================================================================

class TestCodeExecutionResult:
    """Tests for CodeExecutionResult data structure."""

    def test_result_structure(self):
        """CodeExecutionResult has correct default attributes."""
        from tests.test_mcp_server_tools import CodeExecutionResult

        result = CodeExecutionResult()
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.return_value is None
        assert result.error is None  # not "" when unset
        assert result.success is False
        assert result.execution_time_ms == 0


# ============================================================================
# Code Execution
# ============================================================================

class TestCodeExecution:
    """Tests for code execution functionality."""

    def test_run_code_simple_python(self):
        """Simple Python code executes and returns output."""
        from tests.test_mcp_server_tools import run_code

        config = {
            "code": "print('hello world')\nresult = 2 + 2\nprint(f'Result: {result}')",
        }
        result = run_code(None, config)

        assert "hello world" in result["stdout"]
        assert "Result: 4" in result["stdout"]
        assert result["success"] is True

    def test_run_code_syntax_error(self):
        """Syntax errors are caught and reported."""
        from tests.test_mcp_server_tools import run_code

        config = {"code": "print("}  # missing quote
        result = run_code(None, config)

        assert result["success"] is False
        assert result["error"] != ""

    def test_run_code_with_args(self):
        """Code can use pre-defined args injected into locals."""
        from tests.test_mcp_server_tools import run_code

        config = {
            "code": "print(f'User: {user_name}')",
            "args": {"user_name": "Alice"},
        }
        result = run_code(None, config)

        assert "Alice" in result["stdout"]
        assert result["success"] is True

    def test_run_code_arithmetic(self):
        """Code can perform arithmetic and return results."""
        from tests.test_mcp_server_tools import run_code

        config = {"code": "x = 10\ny = 20\nprint(f'Sum: {x + y}')"}
        result = run_code(None, config)

        assert result["success"] is True
        assert "Sum: 30" in result["stdout"]

    def test_run_shell_script_echo(self):
        """Shell script execution works on supported platforms."""
        from tests.test_mcp_server_tools import run_shell_script

        if platform.system() == "Windows":
            pytest.skip("Shell scripts not supported on Windows")

        config = {"script": 'echo "test output"'}
        result = run_shell_script(None, config)

        assert result["success"] is True
        assert "test output" in result["stdout"]


# ============================================================================
# Self Utils
# ============================================================================

class TestSelfUtils:
    """Tests for self-describing utilities."""

    def test_describe_self_returns_dict(self):
        """describe_self_standalone returns a dict (may contain error if no agent)."""
        from tests.test_mcp_server_tools import describe_self_standalone

        config = {}
        info = describe_self_standalone(None, config)

        # Returns a dict with timestamp and either data or error
        assert isinstance(info, dict)
        assert "timestamp" in info
        # Either has content or error
        assert "tools" in info or "error" in info

    def test_text_content_class(self):
        """TextContent wrapper works correctly."""
        from tests.test_mcp_server_tools import MockTextContent

        content = MockTextContent(type="text", text="Hello, World!")
        assert content.type == "text"
        assert content.text == "Hello, World!"
        assert content.meta is None
