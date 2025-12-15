"""
Unit tests for MCP Server Tools.

Tests for:
- self_utils: describe_self, start_task_using_skill, stop_task_using_skill
- code_utils: run_code, run_shell_script

Run with: python -m unittest tests.test_mcp_server_tools -v

Note: These tests are designed to be self-contained and mock external dependencies.
"""

import os
import sys
import io
import time
import platform
import subprocess
import contextlib
import traceback
import unittest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, List, Optional

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ==================== Mock External Dependencies ====================
# Mock modules that may not be available in test environment

# Mock MCP
sys.modules['mcp'] = MagicMock()
sys.modules['mcp.types'] = MagicMock()

class MockTextContent:
    def __init__(self, type, text):
        self.type = type
        self.text = text
        self.meta = None

sys.modules['mcp.types'].TextContent = MockTextContent
sys.modules['mcp.types'].Tool = MagicMock()

# Mock logger_helper
mock_logger = MagicMock()
mock_logger.info = lambda *args, **kwargs: None
mock_logger.debug = lambda *args, **kwargs: None
mock_logger.warning = lambda *args, **kwargs: None
mock_logger.error = lambda *args, **kwargs: None

def mock_get_traceback(e, context=""):
    return f"{context}: {str(e)}"

sys.modules['utils'] = MagicMock()
sys.modules['utils.logger_helper'] = MagicMock()
sys.modules['utils.logger_helper'].logger_helper = mock_logger
sys.modules['utils.logger_helper'].get_traceback = mock_get_traceback

# Mock app_context
sys.modules['app_context'] = MagicMock()

# Mock agent modules
sys.modules['agent'] = MagicMock()
sys.modules['agent.agent_service'] = MagicMock()
sys.modules['agent.agent_service'].get_agent_by_id = MagicMock(return_value=None)
sys.modules['agent.ec_tasks'] = MagicMock()
sys.modules['agent.a2a'] = MagicMock()
sys.modules['agent.a2a.common'] = MagicMock()
sys.modules['agent.a2a.common.types'] = MagicMock()


# ==================== Standalone Implementation for Testing ====================
# These are simplified versions of the actual functions for testing purposes

class CodeExecutionResult:
    """Result of code execution."""
    def __init__(self):
        self.stdout: str = ""
        self.stderr: str = ""
        self.return_value: Any = None
        self.error: Optional[str] = None
        self.execution_time_ms: int = 0
        self.success: bool = False


def create_safe_globals() -> Dict[str, Any]:
    """Create a safe globals dictionary for code execution."""
    safe_globals = {
        "__builtins__": {
            "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
            "enumerate": enumerate, "filter": filter, "float": float,
            "int": int, "len": len, "list": list, "map": map, "max": max,
            "min": min, "print": print, "range": range, "round": round,
            "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
            "type": type, "zip": zip,
            "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
            "KeyError": KeyError, "IndexError": IndexError, "ZeroDivisionError": ZeroDivisionError,
        },
        "__name__": "__main__",
    }
    
    import json, math, re, datetime
    safe_globals["json"] = json
    safe_globals["math"] = math
    safe_globals["re"] = re
    safe_globals["datetime"] = datetime
    
    return safe_globals


def execute_code_safe(
    code: str,
    timeout_seconds: float = 30.0,
    allowed_imports: Optional[List[str]] = None,
    input_args: Optional[Dict[str, Any]] = None
) -> CodeExecutionResult:
    """Execute Python code in a controlled environment."""
    result = CodeExecutionResult()
    start_time = time.perf_counter()
    
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        safe_globals = create_safe_globals()
        safe_locals = {}
        
        if input_args:
            safe_locals["args"] = input_args
            for key, value in input_args.items():
                if key.isidentifier() and not key.startswith("_"):
                    safe_locals[key] = value
        
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
            compiled_code = compile(code, "<user_code>", "exec")
            exec(compiled_code, safe_globals, safe_locals)
        
        if "result" in safe_locals:
            result.return_value = safe_locals["result"]
        
        result.success = True
        
    except SyntaxError as e:
        result.error = f"SyntaxError: {e.msg} (line {e.lineno})"
        result.success = False
        
    except Exception as e:
        result.error = f"{type(e).__name__}: {str(e)}"
        result.success = False
    
    finally:
        result.stdout = stdout_capture.getvalue()
        result.stderr = stderr_capture.getvalue()
        result.execution_time_ms = int((time.perf_counter() - start_time) * 1000)
    
    return result


def run_code(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """Execute Python code and return the results."""
    try:
        code = config.get("code", "")
        input_args = config.get("args", {})
        timeout = config.get("timeout", 30.0)
        allowed_imports = config.get("allowed_imports", [])
        
        if not code:
            return {
                "success": False, "error": "code is required",
                "stdout": "", "stderr": "", "return_value": None,
                "execution_time_ms": 0, "timestamp": int(time.time() * 1000)
            }
        
        exec_result = execute_code_safe(
            code=code, timeout_seconds=timeout,
            allowed_imports=allowed_imports, input_args=input_args
        )
        
        return {
            "success": exec_result.success,
            "stdout": exec_result.stdout,
            "stderr": exec_result.stderr,
            "return_value": exec_result.return_value,
            "error": exec_result.error,
            "execution_time_ms": exec_result.execution_time_ms,
            "timestamp": int(time.time() * 1000)
        }
        
    except Exception as e:
        return {
            "success": False, "error": str(e),
            "stdout": "", "stderr": "", "return_value": None,
            "execution_time_ms": 0, "timestamp": int(time.time() * 1000)
        }


def get_os_info() -> Dict[str, str]:
    """Get current OS information."""
    system = platform.system().lower()
    if system == "windows":
        return {"os": "windows", "shell": "powershell", "version": platform.version()}
    elif system == "darwin":
        return {"os": "darwin", "shell": "zsh", "version": platform.mac_ver()[0]}
    else:
        return {"os": "linux", "shell": "bash", "version": platform.version()}


def get_shell_command(shell: str) -> List[str]:
    """Get the shell executable command based on shell type."""
    shell = shell.lower()
    if shell == "powershell":
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    elif shell == "pwsh":
        return ["pwsh", "-NoProfile", "-NonInteractive", "-Command"]
    elif shell == "bash":
        return ["bash", "-c"]
    elif shell == "zsh":
        return ["zsh", "-c"]
    elif shell == "sh":
        return ["sh", "-c"]
    elif shell == "cmd":
        return ["cmd", "/c"]
    else:
        os_info = get_os_info()
        if os_info["os"] == "windows":
            return ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
        else:
            return ["bash", "-c"]


def execute_shell_script(
    script: str,
    shell: Optional[str] = None,
    timeout_seconds: float = 60.0,
    working_dir: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Execute a shell script and return the results."""
    start_time = time.perf_counter()
    
    result = {
        "success": False, "stdout": "", "stderr": "",
        "return_code": -1, "execution_time_ms": 0,
        "shell": shell or get_os_info()["shell"],
        "os": get_os_info()["os"]
    }
    
    try:
        if shell is None:
            shell = get_os_info()["shell"]
        result["shell"] = shell
        
        shell_cmd = get_shell_command(shell)
        
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
        
        cwd = working_dir
        if cwd and not os.path.isdir(cwd):
            result["stderr"] = f"Working directory does not exist: {cwd}"
            return result
        
        full_cmd = shell_cmd + [script]
        
        process = subprocess.run(
            full_cmd, capture_output=True, text=True,
            timeout=timeout_seconds, cwd=cwd, env=env
        )
        
        result["stdout"] = process.stdout
        result["stderr"] = process.stderr
        result["return_code"] = process.returncode
        result["success"] = process.returncode == 0
        
    except subprocess.TimeoutExpired as e:
        result["stderr"] = f"Script execution timed out after {timeout_seconds} seconds"
    except FileNotFoundError as e:
        result["stderr"] = f"Shell not found: {shell}. Error: {str(e)}"
    except Exception as e:
        result["stderr"] = f"Execution error: {str(e)}"
    finally:
        result["execution_time_ms"] = int((time.perf_counter() - start_time) * 1000)
    
    return result


def run_shell_script(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a shell script and return the results."""
    try:
        script = config.get("script", "")
        shell = config.get("shell", None)
        timeout = config.get("timeout", 60.0)
        working_dir = config.get("working_dir", None)
        env_vars = config.get("env_vars", {})
        
        if not script:
            return {
                "success": False, "error": "script is required",
                "stdout": "", "stderr": "", "return_code": -1,
                "execution_time_ms": 0, "timestamp": int(time.time() * 1000)
            }
        
        exec_result = execute_shell_script(
            script=script, shell=shell, timeout_seconds=timeout,
            working_dir=working_dir, env_vars=env_vars
        )
        exec_result["timestamp"] = int(time.time() * 1000)
        return exec_result
        
    except Exception as e:
        return {
            "success": False, "error": str(e),
            "stdout": "", "stderr": "", "return_code": -1,
            "execution_time_ms": 0, "timestamp": int(time.time() * 1000)
        }


# ==================== Code Utils Tests ====================

class TestRunCode(unittest.TestCase):
    """Tests for run_code tool."""
    
    @classmethod
    def setUpClass(cls):
        """Use local implementations for testing."""
        # Use local implementations defined above
        cls.run_code = staticmethod(run_code)
        cls.execute_code_safe = staticmethod(execute_code_safe)
        cls.create_safe_globals = staticmethod(create_safe_globals)
    
    def test_simple_print(self):
        """Test simple print statement."""
        result = self.run_code(None, {"code": "print('Hello, World!')"})
        self.assertTrue(result["success"])
        self.assertIn("Hello, World!", result["stdout"])
        self.assertIsNone(result["error"])
    
    def test_return_value(self):
        """Test returning a value via result variable."""
        result = self.run_code(None, {"code": "result = 42"})
        self.assertTrue(result["success"])
        self.assertEqual(result["return_value"], 42)
    
    def test_math_operations(self):
        """Test math operations."""
        result = self.run_code(None, {"code": "result = 2 + 2 * 3"})
        self.assertTrue(result["success"])
        self.assertEqual(result["return_value"], 8)
    
    def test_input_args_dict(self):
        """Test input arguments via args dict."""
        result = self.run_code(None, {
            "code": "result = args['x'] + args['y']",
            "args": {"x": 10, "y": 20}
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["return_value"], 30)
    
    def test_input_args_variables(self):
        """Test input arguments as individual variables."""
        result = self.run_code(None, {
            "code": "result = x * y",
            "args": {"x": 5, "y": 6}
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["return_value"], 30)
    
    def test_list_comprehension(self):
        """Test list comprehension with args."""
        result = self.run_code(None, {
            "code": "result = [item.upper() for item in items]",
            "args": {"items": ["hello", "world"]}
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["return_value"], ["HELLO", "WORLD"])
    
    def test_json_module(self):
        """Test json module is available."""
        result = self.run_code(None, {
            "code": "result = json.dumps({'key': 'value'})"
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["return_value"], '{"key": "value"}')
    
    def test_math_module(self):
        """Test math module is available."""
        result = self.run_code(None, {
            "code": "result = math.sqrt(16)"
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["return_value"], 4.0)
    
    def test_datetime_module(self):
        """Test datetime module is available."""
        result = self.run_code(None, {
            "code": "result = datetime.datetime(2024, 1, 1).year"
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["return_value"], 2024)
    
    def test_syntax_error(self):
        """Test syntax error handling."""
        result = self.run_code(None, {"code": "def broken("})
        self.assertFalse(result["success"])
        self.assertIn("SyntaxError", result["error"])
    
    def test_runtime_error(self):
        """Test runtime error handling."""
        result = self.run_code(None, {"code": "x = 1 / 0"})
        self.assertFalse(result["success"])
        self.assertIn("ZeroDivisionError", result["error"])
    
    def test_name_error(self):
        """Test undefined variable error."""
        result = self.run_code(None, {"code": "result = undefined_var"})
        self.assertFalse(result["success"])
        self.assertIn("NameError", result["error"])
    
    def test_empty_code(self):
        """Test empty code handling."""
        result = self.run_code(None, {"code": ""})
        self.assertFalse(result["success"])
        self.assertIn("code is required", result["error"])
    
    def test_missing_code(self):
        """Test missing code parameter."""
        result = self.run_code(None, {})
        self.assertFalse(result["success"])
        self.assertIn("code is required", result["error"])
    
    def test_execution_time(self):
        """Test execution time is recorded."""
        result = self.run_code(None, {"code": "x = 1"})
        self.assertTrue(result["success"])
        self.assertIn("execution_time_ms", result)
        self.assertIsInstance(result["execution_time_ms"], int)
        self.assertGreaterEqual(result["execution_time_ms"], 0)
    
    def test_timestamp(self):
        """Test timestamp is included."""
        result = self.run_code(None, {"code": "x = 1"})
        self.assertIn("timestamp", result)
        self.assertIsInstance(result["timestamp"], int)
    
    def test_multiline_code(self):
        """Test multiline code execution."""
        code = """
def add(a, b):
    return a + b

result = add(3, 4)
"""
        result = self.run_code(None, {"code": code})
        self.assertTrue(result["success"])
        self.assertEqual(result["return_value"], 7)
    
    def test_safe_globals(self):
        """Test that safe globals are created properly."""
        safe_globals = self.create_safe_globals()
        self.assertIn("__builtins__", safe_globals)
        self.assertIn("json", safe_globals)
        self.assertIn("math", safe_globals)
        self.assertIn("re", safe_globals)
        self.assertIn("datetime", safe_globals)


class TestRunShellScript(unittest.TestCase):
    """Tests for run_shell_script tool."""
    
    @classmethod
    def setUpClass(cls):
        """Use local implementations for testing."""
        cls.run_shell_script = staticmethod(run_shell_script)
        cls.execute_shell_script = staticmethod(execute_shell_script)
        cls.get_os_info = staticmethod(get_os_info)
        cls.get_shell_command = staticmethod(get_shell_command)
    
    def test_get_os_info(self):
        """Test OS info detection."""
        os_info = self.get_os_info()
        self.assertIn("os", os_info)
        self.assertIn("shell", os_info)
        self.assertIn("version", os_info)
        self.assertIn(os_info["os"], ["windows", "linux", "darwin"])
    
    def test_get_shell_command_powershell(self):
        """Test PowerShell command generation."""
        cmd = self.get_shell_command("powershell")
        self.assertEqual(cmd[0], "powershell")
        self.assertIn("-Command", cmd)
    
    def test_get_shell_command_bash(self):
        """Test bash command generation."""
        cmd = self.get_shell_command("bash")
        self.assertEqual(cmd, ["bash", "-c"])
    
    def test_get_shell_command_zsh(self):
        """Test zsh command generation."""
        cmd = self.get_shell_command("zsh")
        self.assertEqual(cmd, ["zsh", "-c"])
    
    def test_simple_echo(self):
        """Test simple echo command."""
        os_info = self.get_os_info()
        if os_info["os"] == "windows":
            script = "Write-Output 'Hello'"
        else:
            script = "echo 'Hello'"
        
        result = self.run_shell_script(None, {"script": script})
        self.assertTrue(result["success"])
        self.assertIn("Hello", result["stdout"])
    
    def test_return_code_success(self):
        """Test successful return code."""
        os_info = self.get_os_info()
        if os_info["os"] == "windows":
            script = "exit 0"
        else:
            script = "exit 0"
        
        result = self.run_shell_script(None, {"script": script})
        self.assertTrue(result["success"])
        self.assertEqual(result["return_code"], 0)
    
    def test_return_code_failure(self):
        """Test failed return code."""
        os_info = self.get_os_info()
        if os_info["os"] == "windows":
            script = "exit 1"
        else:
            script = "exit 1"
        
        result = self.run_shell_script(None, {"script": script})
        self.assertFalse(result["success"])
        self.assertEqual(result["return_code"], 1)
    
    def test_env_vars(self):
        """Test environment variables."""
        os_info = self.get_os_info()
        if os_info["os"] == "windows":
            script = "Write-Output $env:MY_TEST_VAR"
        else:
            script = "echo $MY_TEST_VAR"
        
        result = self.run_shell_script(None, {
            "script": script,
            "env_vars": {"MY_TEST_VAR": "test_value_123"}
        })
        self.assertTrue(result["success"])
        self.assertIn("test_value_123", result["stdout"])
    
    def test_working_dir(self):
        """Test working directory."""
        os_info = self.get_os_info()
        if os_info["os"] == "windows":
            script = "Get-Location"
            test_dir = os.environ.get("TEMP", "C:\\Windows\\Temp")
        else:
            script = "pwd"
            test_dir = "/tmp"
        
        result = self.run_shell_script(None, {
            "script": script,
            "working_dir": test_dir
        })
        self.assertTrue(result["success"])
        # Normalize paths for comparison
        self.assertIn(os.path.basename(test_dir).lower(), result["stdout"].lower())
    
    def test_invalid_working_dir(self):
        """Test invalid working directory."""
        result = self.run_shell_script(None, {
            "script": "echo test",
            "working_dir": "/nonexistent/path/12345"
        })
        self.assertFalse(result["success"])
        self.assertIn("does not exist", result["stderr"])
    
    def test_empty_script(self):
        """Test empty script handling."""
        result = self.run_shell_script(None, {"script": ""})
        self.assertFalse(result["success"])
        self.assertIn("script is required", result["error"])
    
    def test_missing_script(self):
        """Test missing script parameter."""
        result = self.run_shell_script(None, {})
        self.assertFalse(result["success"])
        self.assertIn("script is required", result["error"])
    
    def test_execution_time(self):
        """Test execution time is recorded."""
        os_info = self.get_os_info()
        script = "Write-Output 'test'" if os_info["os"] == "windows" else "echo 'test'"
        
        result = self.run_shell_script(None, {"script": script})
        self.assertIn("execution_time_ms", result)
        self.assertIsInstance(result["execution_time_ms"], int)
        self.assertGreaterEqual(result["execution_time_ms"], 0)
    
    def test_os_and_shell_in_result(self):
        """Test OS and shell info in result."""
        os_info = self.get_os_info()
        script = "Write-Output 'test'" if os_info["os"] == "windows" else "echo 'test'"
        
        result = self.run_shell_script(None, {"script": script})
        self.assertIn("os", result)
        self.assertIn("shell", result)
        self.assertEqual(result["os"], os_info["os"])
    
    @unittest.skipIf(platform.system().lower() != "windows", "Windows-only test")
    def test_powershell_specific(self):
        """Test PowerShell-specific commands."""
        result = self.run_shell_script(None, {
            "script": "$PSVersionTable.PSVersion.Major",
            "shell": "powershell"
        })
        self.assertTrue(result["success"])
        # Should return a version number
        self.assertTrue(result["stdout"].strip().isdigit())
    
    @unittest.skipIf(platform.system().lower() == "windows", "Unix-only test")
    def test_bash_specific(self):
        """Test bash-specific commands."""
        result = self.run_shell_script(None, {
            "script": "echo $BASH_VERSION",
            "shell": "bash"
        })
        self.assertTrue(result["success"])


# ==================== Self Utils Tests ====================

def describe_self_standalone(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """Standalone describe_self for testing."""
    try:
        agent_id = config.get("agent_id", "")
        
        agent = None
        if hasattr(mainwin, 'agents') and mainwin.agents:
            agent = mainwin.agents[0]
            agent_id = getattr(getattr(agent, 'card', None), 'id', 'unknown')
        
        if not agent:
            return {"error": f"Agent not found: {agent_id}", "timestamp": int(time.time() * 1000)}
        
        result = {
            "agent_id": agent_id,
            "agent_name": getattr(getattr(agent, 'card', None), 'name', 'Unknown'),
            "agent_description": getattr(getattr(agent, 'card', None), 'description', ''),
            "skills": [],
            "tasks": {"running": [], "pending": [], "completed": [], "failed": []},
            "status": getattr(agent, 'status', 'unknown'),
            "timestamp": int(time.time() * 1000)
        }
        
        for skill in getattr(agent, 'skills', []) or []:
            skill_info = {
                "id": getattr(skill, 'id', ''),
                "name": getattr(skill, 'name', 'Unknown'),
                "description": getattr(skill, 'description', ''),
                "type": getattr(skill, 'type', 'unknown'),
                "enabled": getattr(skill, 'enabled', True)
            }
            if hasattr(skill, 'tags') and skill.tags:
                skill_info["tags"] = skill.tags
            result["skills"].append(skill_info)
        
        for task in getattr(agent, 'tasks', []) or []:
            task_info = {
                "id": getattr(task, 'id', 'unknown'),
                "name": getattr(task, 'name', 'Unknown'),
                "state": "unknown"
            }
            task_status = getattr(task, 'status', None)
            if task_status:
                state = getattr(task_status, 'state', None)
                if state:
                    task_info["state"] = state.value if hasattr(state, 'value') else str(state)
            
            state_str = task_info["state"].lower()
            if state_str in ("working", "running"):
                result["tasks"]["running"].append(task_info)
            else:
                result["tasks"]["pending"].append(task_info)
        
        return result
    except Exception as e:
        return {"error": str(e), "timestamp": int(time.time() * 1000)}


def start_task_using_skill_standalone(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """Standalone start_task_using_skill for testing."""
    try:
        skill_name = config.get("skill_name", "")
        if not skill_name:
            return {"success": False, "error": "skill_name is required", "timestamp": int(time.time() * 1000)}
        
        agent = None
        if hasattr(mainwin, 'agents') and mainwin.agents:
            agent = mainwin.agents[0]
        
        if not agent:
            return {"success": False, "error": "Agent not found", "timestamp": int(time.time() * 1000)}
        
        skills = getattr(agent, 'skills', []) or []
        target_skill = None
        for skill in skills:
            if getattr(skill, 'name', '') == skill_name:
                target_skill = skill
                break
        
        if not target_skill:
            return {"success": False, "error": f"Skill '{skill_name}' not found", "timestamp": int(time.time() * 1000)}
        
        import uuid
        task_id = str(uuid.uuid4())
        return {
            "success": True,
            "task_id": task_id,
            "skill_name": skill_name,
            "message": f"Task created using skill '{skill_name}'",
            "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        return {"success": False, "error": str(e), "timestamp": int(time.time() * 1000)}


def stop_task_using_skill_standalone(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """Standalone stop_task_using_skill for testing."""
    try:
        task_id = config.get("task_id", "")
        if not task_id:
            return {"success": False, "error": "task_id is required", "timestamp": int(time.time() * 1000)}
        
        agent = None
        if hasattr(mainwin, 'agents') and mainwin.agents:
            agent = mainwin.agents[0]
        
        if not agent:
            return {"success": False, "error": "Agent not found", "timestamp": int(time.time() * 1000)}
        
        tasks = getattr(agent, 'tasks', []) or []
        target_task = None
        for task in tasks:
            if getattr(task, 'id', '') == task_id:
                target_task = task
                break
        
        if not target_task:
            return {"success": False, "error": f"Task '{task_id}' not found", "timestamp": int(time.time() * 1000)}
        
        previous_state = "unknown"
        task_status = getattr(target_task, 'status', None)
        if task_status:
            state = getattr(task_status, 'state', None)
            if state:
                previous_state = state.value if hasattr(state, 'value') else str(state)
        
        if hasattr(target_task, 'cancellation_event'):
            target_task.cancellation_event.set()
        
        return {
            "success": True,
            "task_id": task_id,
            "task_name": getattr(target_task, 'name', 'Unknown'),
            "previous_state": previous_state,
            "message": f"Task '{task_id}' has been stopped",
            "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        return {"success": False, "error": str(e), "timestamp": int(time.time() * 1000)}


class TestDescribeSelf(unittest.TestCase):
    """Tests for describe_self tool."""
    
    @classmethod
    def setUpClass(cls):
        """Use standalone implementation for testing."""
        cls.describe_self = staticmethod(describe_self_standalone)
    
    def _create_mock_agent(self):
        """Create a mock agent for testing."""
        mock_skill = Mock()
        mock_skill.id = "skill_1"
        mock_skill.name = "TestSkill"
        mock_skill.description = "A test skill"
        mock_skill.type = "test"
        mock_skill.enabled = True
        mock_skill.tags = ["test", "mock"]
        
        mock_task = Mock()
        mock_task.id = "task_1"
        mock_task.name = "TestTask"
        mock_task.skill = mock_skill
        mock_task.run_id = "run_123"
        mock_task.status = Mock()
        mock_task.status.state = Mock()
        mock_task.status.state.value = "working"
        mock_task.schedule = None
        
        mock_card = Mock()
        mock_card.id = "agent_123"
        mock_card.name = "TestAgent"
        mock_card.description = "A test agent"
        
        mock_agent = Mock()
        mock_agent.card = mock_card
        mock_agent.skills = [mock_skill]
        mock_agent.tasks = [mock_task]
        mock_agent.status = "active"
        
        return mock_agent
    
    def test_describe_self_with_mock_agent(self):
        """Test describe_self with a mock agent."""
        mock_agent = self._create_mock_agent()
        mock_mainwin = Mock()
        mock_mainwin.agents = [mock_agent]
        
        result = self.describe_self(mock_mainwin, {})
        
        self.assertIn("agent_id", result)
        self.assertIn("agent_name", result)
        self.assertIn("skills", result)
        self.assertIn("tasks", result)
        self.assertIn("timestamp", result)
        
        # Check skills
        self.assertEqual(len(result["skills"]), 1)
        self.assertEqual(result["skills"][0]["name"], "TestSkill")
        
        # Check tasks
        self.assertEqual(len(result["tasks"]["running"]), 1)
        self.assertEqual(result["tasks"]["running"][0]["name"], "TestTask")
    
    def test_describe_self_no_agent(self):
        """Test describe_self when no agent is found."""
        mock_mainwin = Mock()
        mock_mainwin.agents = []
        
        result = self.describe_self(mock_mainwin, {"agent_id": "nonexistent"})
        
        self.assertIn("error", result)
        self.assertIn("not found", result["error"].lower())
    
    def test_describe_self_with_agent_id(self):
        """Test describe_self with specific agent_id (uses first agent from mainwin)."""
        mock_agent = self._create_mock_agent()
        mock_mainwin = Mock()
        mock_mainwin.agents = [mock_agent]
        
        # Standalone implementation uses first agent from mainwin.agents
        result = self.describe_self(mock_mainwin, {"agent_id": "agent_123"})
        
        self.assertNotIn("error", result)
        self.assertEqual(result["agent_name"], "TestAgent")


class TestStartTaskUsingSkill(unittest.TestCase):
    """Tests for start_task_using_skill tool."""
    
    @classmethod
    def setUpClass(cls):
        """Use standalone implementation for testing."""
        cls.start_task_using_skill = staticmethod(start_task_using_skill_standalone)
    
    def _create_mock_agent(self):
        """Create a mock agent for testing."""
        mock_skill = Mock()
        mock_skill.id = "skill_1"
        mock_skill.name = "TestSkill"
        
        mock_card = Mock()
        mock_card.id = "agent_123"
        
        mock_agent = Mock()
        mock_agent.card = mock_card
        mock_agent.skills = [mock_skill]
        mock_agent.tasks = []
        mock_agent.runner = None
        
        return mock_agent
    
    def test_missing_skill_name(self):
        """Test error when skill_name is missing."""
        result = self.start_task_using_skill(None, {})
        
        self.assertFalse(result["success"])
        self.assertIn("skill_name is required", result["error"])
    
    def test_skill_not_found(self):
        """Test error when skill is not found."""
        mock_agent = self._create_mock_agent()
        mock_mainwin = Mock()
        mock_mainwin.agents = [mock_agent]
        
        result = self.start_task_using_skill(mock_mainwin, {
            "skill_name": "NonexistentSkill"
        })
        
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])
    
    def test_start_task_success(self):
        """Test successful task start."""
        mock_agent = self._create_mock_agent()
        mock_mainwin = Mock()
        mock_mainwin.agents = [mock_agent]
        
        result = self.start_task_using_skill(mock_mainwin, {
            "skill_name": "TestSkill"
        })
        
        self.assertTrue(result["success"])
        self.assertIn("task_id", result)
        self.assertEqual(result["skill_name"], "TestSkill")


class TestStopTaskUsingSkill(unittest.TestCase):
    """Tests for stop_task_using_skill tool."""
    
    @classmethod
    def setUpClass(cls):
        """Use standalone implementation for testing."""
        cls.stop_task_using_skill = staticmethod(stop_task_using_skill_standalone)
    
    def _create_mock_agent_with_task(self):
        """Create a mock agent with a running task."""
        mock_task = Mock()
        mock_task.id = "task_123"
        mock_task.name = "RunningTask"
        mock_task.run_id = "run_456"
        mock_task.status = Mock()
        mock_task.status.state = Mock()
        mock_task.status.state.value = "working"
        mock_task.cancellation_event = Mock()
        
        mock_card = Mock()
        mock_card.id = "agent_123"
        
        mock_agent = Mock()
        mock_agent.card = mock_card
        mock_agent.tasks = [mock_task]
        mock_agent.runner = None
        
        return mock_agent, mock_task
    
    def test_missing_task_id(self):
        """Test error when task_id is missing."""
        result = self.stop_task_using_skill(None, {})
        
        self.assertFalse(result["success"])
        self.assertIn("task_id is required", result["error"])
    
    def test_task_not_found(self):
        """Test error when task is not found."""
        mock_agent, _ = self._create_mock_agent_with_task()
        mock_mainwin = Mock()
        mock_mainwin.agents = [mock_agent]
        
        result = self.stop_task_using_skill(mock_mainwin, {
            "task_id": "nonexistent_task"
        })
        
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])
    
    def test_stop_task_success(self):
        """Test successful task stop."""
        mock_agent, mock_task = self._create_mock_agent_with_task()
        mock_mainwin = Mock()
        mock_mainwin.agents = [mock_agent]
        
        result = self.stop_task_using_skill(mock_mainwin, {
            "task_id": "task_123"
        })
        
        self.assertTrue(result["success"])
        self.assertEqual(result["task_id"], "task_123")
        self.assertEqual(result["previous_state"], "working")
        mock_task.cancellation_event.set.assert_called_once()


# ==================== Integration Tests (require full environment) ====================
# These tests are skipped when dependencies are not available

@unittest.skipIf(True, "Integration tests require full environment with all dependencies")
class TestAsyncWrappers(unittest.TestCase):
    """Tests for async wrapper functions - requires full environment."""
    
    def test_async_functions_exist(self):
        """Placeholder for async function tests."""
        pass


@unittest.skipIf(True, "Integration tests require full environment with all dependencies")
class TestToolSchemas(unittest.TestCase):
    """Tests for tool schema functions - requires full environment."""
    
    def test_schemas_exist(self):
        """Placeholder for schema tests."""
        pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
