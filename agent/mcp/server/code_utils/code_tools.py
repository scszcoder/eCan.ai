"""
Code Tools - MCP tools for code execution.

Tools:
- run_code: Execute Python code in a controlled environment
- run_shell_script: Execute shell scripts (PowerShell/Bash/Zsh) with multi-OS support

Naming convention follows server.py and tool_schemas.py patterns.
"""

import io
import os
import sys
import time
import platform
import subprocess
import tempfile
import traceback
import contextlib
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger, get_traceback


# ==================== Execution Helpers ====================

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
    """
    Create a safe globals dictionary for code execution.
    
    Includes common safe modules and utilities.
    """
    safe_globals = {
        "__builtins__": {
            # Safe built-in functions
            "abs": abs,
            "all": all,
            "any": any,
            "ascii": ascii,
            "bin": bin,
            "bool": bool,
            "bytearray": bytearray,
            "bytes": bytes,
            "callable": callable,
            "chr": chr,
            "complex": complex,
            "dict": dict,
            "dir": dir,
            "divmod": divmod,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "format": format,
            "frozenset": frozenset,
            "getattr": getattr,
            "hasattr": hasattr,
            "hash": hash,
            "hex": hex,
            "id": id,
            "int": int,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "iter": iter,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "next": next,
            "object": object,
            "oct": oct,
            "ord": ord,
            "pow": pow,
            "print": print,
            "range": range,
            "repr": repr,
            "reversed": reversed,
            "round": round,
            "set": set,
            "slice": slice,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "type": type,
            "vars": vars,
            "zip": zip,
            # Exceptions
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "AttributeError": AttributeError,
            "RuntimeError": RuntimeError,
            "StopIteration": StopIteration,
            "ZeroDivisionError": ZeroDivisionError,
            # Import function for import statements
            "__import__": __import__,
        },
        "__name__": "__main__",
        "__doc__": None,
    }
    
    # Add safe standard library modules
    try:
        import json
        safe_globals["json"] = json
    except ImportError:
        pass
    
    try:
        import math
        safe_globals["math"] = math
    except ImportError:
        pass
    
    try:
        import re
        safe_globals["re"] = re
    except ImportError:
        pass
    
    try:
        import datetime
        safe_globals["datetime"] = datetime
    except ImportError:
        pass
    
    try:
        import collections
        safe_globals["collections"] = collections
    except ImportError:
        pass
    
    try:
        import itertools
        safe_globals["itertools"] = itertools
    except ImportError:
        pass
    
    try:
        import functools
        safe_globals["functools"] = functools
    except ImportError:
        pass
    
    try:
        import random
        safe_globals["random"] = random
    except ImportError:
        pass
    
    try:
        import string
        safe_globals["string"] = string
    except ImportError:
        pass
    
    try:
        import uuid
        safe_globals["uuid"] = uuid
    except ImportError:
        pass
    
    try:
        import hashlib
        safe_globals["hashlib"] = hashlib
    except ImportError:
        pass
    
    try:
        import base64
        safe_globals["base64"] = base64
    except ImportError:
        pass
    
    try:
        import urllib.parse
        safe_globals["urllib"] = {"parse": urllib.parse}
    except ImportError:
        pass
    
    # Add os module for file system operations
    try:
        import os as os_module
        safe_globals["os"] = os_module
    except ImportError:
        pass
    
    return safe_globals


def execute_code_safe(
    code: str,
    timeout_seconds: float = 30.0,
    allowed_imports: Optional[List[str]] = None,
    input_args: Optional[Dict[str, Any]] = None
) -> CodeExecutionResult:
    """
    Execute Python code in a controlled environment.
    
    Args:
        code: Python code to execute
        timeout_seconds: Maximum execution time (not strictly enforced in this implementation)
        allowed_imports: List of additional modules to allow importing
        input_args: Dictionary of input arguments accessible as 'args' in the code
        
    Returns:
        CodeExecutionResult with stdout, stderr, return value, and error info
    """
    result = CodeExecutionResult()
    start_time = time.perf_counter()
    
    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        # Create safe execution environment
        safe_globals = create_safe_globals()
        safe_locals = {}
        
        # Add input arguments to the execution context
        if input_args:
            safe_locals["args"] = input_args
            # Also expose individual args as variables for convenience
            for key, value in input_args.items():
                if key.isidentifier() and not key.startswith("_"):
                    safe_locals[key] = value
        
        # Add allowed imports if specified
        if allowed_imports:
            for module_name in allowed_imports:
                try:
                    module = __import__(module_name)
                    safe_globals[module_name] = module
                except ImportError:
                    pass
        
        # Redirect stdout/stderr
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
            # Compile the code first to catch syntax errors
            compiled_code = compile(code, "<user_code>", "exec")
            
            # Execute the code
            exec(compiled_code, safe_globals, safe_locals)
        
        # Check for a return value (last expression or 'result' variable)
        if "result" in safe_locals:
            result.return_value = safe_locals["result"]
        elif "_" in safe_locals:
            result.return_value = safe_locals["_"]
        
        result.success = True
        
    except SyntaxError as e:
        result.error = f"SyntaxError: {e.msg} (line {e.lineno})"
        result.success = False
        
    except Exception as e:
        # Capture the full traceback
        tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
        # Filter out internal frames
        filtered_tb = []
        for line in tb_lines:
            if "<user_code>" in line or not line.strip().startswith("File"):
                filtered_tb.append(line)
        result.error = "".join(filtered_tb).strip()
        result.success = False
    
    finally:
        result.stdout = stdout_capture.getvalue()
        result.stderr = stderr_capture.getvalue()
        result.execution_time_ms = int((time.perf_counter() - start_time) * 1000)
    
    return result


# ==================== Tool Implementation ====================

def run_code(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute Python code and return the results.
    
    Args:
        mainwin: Main window instance (unused but required for MCP pattern)
        config: Configuration dict with:
            - code: str (required) - Python code to execute
            - args: dict (optional) - Input arguments accessible in code as 'args' dict and as variables
            - timeout: float (optional) - Timeout in seconds (default: 30)
            - allowed_imports: list (optional) - Additional modules to allow
            
    Returns:
        Dict with execution results:
        {
            "success": bool,
            "stdout": str,
            "stderr": str,
            "return_value": any,
            "error": str or None,
            "execution_time_ms": int,
            "timestamp": int
        }
    """
    try:
        code = config.get("code", "")
        input_args = config.get("args", {})
        timeout = config.get("timeout", 30.0)
        allowed_imports = config.get("allowed_imports", [])
        
        if not code:
            return {
                "success": False,
                "error": "code is required",
                "stdout": "",
                "stderr": "",
                "return_value": None,
                "execution_time_ms": 0,
                "timestamp": int(time.time() * 1000)
            }
        
        if not isinstance(code, str):
            return {
                "success": False,
                "error": "code must be a string",
                "stdout": "",
                "stderr": "",
                "return_value": None,
                "execution_time_ms": 0,
                "timestamp": int(time.time() * 1000)
            }
        
        # Log code execution attempt
        code_preview = code[:100] + "..." if len(code) > 100 else code
        logger.info(f"[run_code] Executing code: {code_preview}")
        
        # Execute the code
        exec_result = execute_code_safe(
            code=code,
            timeout_seconds=timeout,
            allowed_imports=allowed_imports,
            input_args=input_args
        )
        
        # Format return value for JSON serialization
        return_value = exec_result.return_value
        if return_value is not None:
            try:
                # Try to convert to JSON-serializable format
                import json
                json.dumps(return_value)
            except (TypeError, ValueError):
                # If not serializable, convert to string representation
                return_value = repr(return_value)
        
        result = {
            "success": exec_result.success,
            "stdout": exec_result.stdout,
            "stderr": exec_result.stderr,
            "return_value": return_value,
            "error": exec_result.error,
            "execution_time_ms": exec_result.execution_time_ms,
            "timestamp": int(time.time() * 1000)
        }
        
        if exec_result.success:
            logger.info(f"[run_code] Execution successful in {exec_result.execution_time_ms}ms")
        else:
            logger.warning(f"[run_code] Execution failed: {exec_result.error}")
        
        return result
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRunCode")
        logger.error(err_trace)
        return {
            "success": False,
            "error": err_trace,
            "stdout": "",
            "stderr": "",
            "return_value": None,
            "execution_time_ms": 0,
            "timestamp": int(time.time() * 1000)
        }


# ==================== Tool Schema Function ====================

def add_run_code_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add run_code tool schema to the tool schemas list."""
    tool_schema = types.Tool(
        name="run_code",
        description=(
            "<category>Code</category><sub-category>Execution</sub-category>"
            "Execute Python code in a sandboxed environment. The code runs with access to "
            "common safe modules (os, json, math, re, datetime, collections, itertools, functools, "
            "random, string, uuid, hashlib, base64). Input arguments are accessible via 'args' dict "
            "or as individual variables. Returns stdout, stderr, return value, and execution time. "
            "Use 'result' variable to return a value."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["code"],
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute. Use 'result' variable to return a value."
                        },
                        "args": {
                            "type": "object",
                            "description": "Input arguments accessible in code as 'args' dict and as individual variables."
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Maximum execution time in seconds. Default: 30."
                        },
                        "allowed_imports": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Additional module names to allow importing."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


# ==================== Async Wrapper for Server ====================

async def async_run_code(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for run_code tool."""
    try:
        input_config = args.get('input', {})
        result = run_code(mainwin, input_config)
        
        # Build response message
        if result.get("success"):
            msg_parts = [f"✅ Code executed successfully in {result.get('execution_time_ms', 0)}ms"]
            if result.get("stdout"):
                msg_parts.append(f"\n📤 Output:\n{result['stdout']}")
            if result.get("return_value") is not None:
                msg_parts.append(f"\n📦 Return value: {result['return_value']}")
            msg = "".join(msg_parts)
        else:
            msg = f"❌ Code execution failed: {result.get('error', 'Unknown error')}"
            if result.get("stderr"):
                msg += f"\n📥 Stderr:\n{result['stderr']}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"code_execution_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncRunCode")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ==================== Shell Script Execution ====================

def get_os_info() -> Dict[str, str]:
    """
    Get current OS information.
    
    Returns:
        Dict with 'os' (windows/linux/darwin), 'shell' (default shell), 'version'
    """
    system = platform.system().lower()
    
    if system == "windows":
        return {
            "os": "windows",
            "shell": "powershell",
            "version": platform.version()
        }
    elif system == "darwin":
        return {
            "os": "darwin",
            "shell": "zsh",  # macOS default since Catalina
            "version": platform.mac_ver()[0]
        }
    else:  # Linux and others
        return {
            "os": "linux",
            "shell": "bash",
            "version": platform.version()
        }


def get_shell_command(shell: str) -> List[str]:
    """
    Get the shell executable command based on shell type.
    
    Args:
        shell: Shell type (powershell, bash, zsh, sh, cmd)
        
    Returns:
        List of command parts to execute the shell
    """
    shell = shell.lower()
    
    if shell == "powershell":
        # Use pwsh (PowerShell Core) if available, fallback to powershell
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
        # Default based on OS
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
    """
    Execute a shell script and return the results.
    
    Args:
        script: Shell script to execute
        shell: Shell to use (powershell, bash, zsh, sh, cmd). Auto-detected if None.
        timeout_seconds: Maximum execution time
        working_dir: Working directory for the script
        env_vars: Additional environment variables
        
    Returns:
        Dict with stdout, stderr, return_code, success, execution_time_ms
    """
    start_time = time.perf_counter()
    
    result = {
        "success": False,
        "stdout": "",
        "stderr": "",
        "return_code": -1,
        "execution_time_ms": 0,
        "shell": shell or get_os_info()["shell"],
        "os": get_os_info()["os"]
    }
    
    try:
        # Determine shell to use
        if shell is None:
            shell = get_os_info()["shell"]
        
        result["shell"] = shell
        
        # Get shell command
        shell_cmd = get_shell_command(shell)
        
        # Prepare environment
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
        
        # Prepare working directory
        cwd = working_dir
        if cwd and not os.path.isdir(cwd):
            result["stderr"] = f"Working directory does not exist: {cwd}"
            return result
        
        # Execute the script
        if shell.lower() in ("powershell", "pwsh"):
            # For PowerShell, we can pass the script directly
            full_cmd = shell_cmd + [script]
        else:
            # For bash/zsh/sh, pass script as argument
            full_cmd = shell_cmd + [script]
        
        process = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=cwd,
            env=env
        )
        
        result["stdout"] = process.stdout
        result["stderr"] = process.stderr
        result["return_code"] = process.returncode
        result["success"] = process.returncode == 0
        
    except subprocess.TimeoutExpired as e:
        result["stderr"] = f"Script execution timed out after {timeout_seconds} seconds"
        result["stdout"] = e.stdout if e.stdout else ""
        
    except FileNotFoundError as e:
        result["stderr"] = f"Shell not found: {shell}. Error: {str(e)}"
        
    except Exception as e:
        result["stderr"] = f"Execution error: {str(e)}"
    
    finally:
        result["execution_time_ms"] = int((time.perf_counter() - start_time) * 1000)
    
    return result


# ==================== Shell Script Tool Implementation ====================

def run_shell_script(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a shell script and return the results.
    
    Args:
        mainwin: Main window instance (unused but required for MCP pattern)
        config: Configuration dict with:
            - script: str (required) - Shell script to execute
            - shell: str (optional) - Shell to use (powershell, bash, zsh, sh, cmd)
            - timeout: float (optional) - Timeout in seconds (default: 60)
            - working_dir: str (optional) - Working directory
            - env_vars: dict (optional) - Additional environment variables
            
    Returns:
        Dict with execution results
    """
    try:
        script = config.get("script", "")
        shell = config.get("shell", None)
        timeout = config.get("timeout", 60.0)
        working_dir = config.get("working_dir", None)
        env_vars = config.get("env_vars", {})
        
        if not script:
            return {
                "success": False,
                "error": "script is required",
                "stdout": "",
                "stderr": "",
                "return_code": -1,
                "execution_time_ms": 0,
                "timestamp": int(time.time() * 1000)
            }
        
        if not isinstance(script, str):
            return {
                "success": False,
                "error": "script must be a string",
                "stdout": "",
                "stderr": "",
                "return_code": -1,
                "execution_time_ms": 0,
                "timestamp": int(time.time() * 1000)
            }
        
        # Log script execution attempt
        script_preview = script[:100] + "..." if len(script) > 100 else script
        os_info = get_os_info()
        logger.info(f"[run_shell_script] Executing on {os_info['os']} with {shell or os_info['shell']}: {script_preview}")
        
        # Execute the script
        exec_result = execute_shell_script(
            script=script,
            shell=shell,
            timeout_seconds=timeout,
            working_dir=working_dir,
            env_vars=env_vars
        )
        
        # Add timestamp
        exec_result["timestamp"] = int(time.time() * 1000)
        
        if exec_result["success"]:
            logger.info(f"[run_shell_script] Execution successful in {exec_result['execution_time_ms']}ms")
        else:
            logger.warning(f"[run_shell_script] Execution failed with code {exec_result['return_code']}")
        
        return exec_result
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRunShellScript")
        logger.error(err_trace)
        return {
            "success": False,
            "error": err_trace,
            "stdout": "",
            "stderr": "",
            "return_code": -1,
            "execution_time_ms": 0,
            "timestamp": int(time.time() * 1000)
        }


# ==================== Shell Script Tool Schema ====================

def add_run_shell_script_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add run_shell_script tool schema to the tool schemas list."""
    tool_schema = types.Tool(
        name="run_shell_script",
        description=(
            "<category>Code</category><sub-category>Execution</sub-category>"
            "Execute a shell script with multi-OS support. Automatically detects the OS and uses "
            "the appropriate shell: PowerShell on Windows, bash on Linux, zsh on macOS. "
            "You can also explicitly specify the shell (powershell, pwsh, bash, zsh, sh, cmd). "
            "Returns stdout, stderr, return code, and execution time."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["script"],
                    "properties": {
                        "script": {
                            "type": "string",
                            "description": "Shell script to execute."
                        },
                        "shell": {
                            "type": "string",
                            "enum": ["powershell", "pwsh", "bash", "zsh", "sh", "cmd"],
                            "description": "Shell to use. Auto-detected based on OS if not specified."
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Maximum execution time in seconds. Default: 60."
                        },
                        "working_dir": {
                            "type": "string",
                            "description": "Working directory for script execution."
                        },
                        "env_vars": {
                            "type": "object",
                            "description": "Additional environment variables as key-value pairs."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


# ==================== Shell Script Async Wrapper ====================

async def async_run_shell_script(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for run_shell_script tool."""
    try:
        input_config = args.get('input', {})
        result = run_shell_script(mainwin, input_config)
        
        # Build response message
        if result.get("success"):
            msg_parts = [
                f"✅ Script executed successfully on {result.get('os', 'unknown')} "
                f"using {result.get('shell', 'unknown')} in {result.get('execution_time_ms', 0)}ms"
            ]
            if result.get("stdout"):
                stdout_preview = result['stdout'][:1000]
                if len(result['stdout']) > 1000:
                    stdout_preview += "\n... (truncated)"
                msg_parts.append(f"\n📤 Output:\n{stdout_preview}")
            msg = "".join(msg_parts)
        else:
            msg = f"❌ Script execution failed (exit code: {result.get('return_code', -1)})"
            if result.get("error"):
                msg += f"\n🔴 Error: {result['error']}"
            if result.get("stderr"):
                stderr_preview = result['stderr'][:1000]
                if len(result['stderr']) > 1000:
                    stderr_preview += "\n... (truncated)"
                msg += f"\n📥 Stderr:\n{stderr_preview}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"shell_execution_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncRunShellScript")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ==================== Search Tools ====================

import glob
import fnmatch
import re as regex_module


def grep_search(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for patterns within files.
    
    Args:
        mainwin: Main window instance (unused but required for MCP pattern)
        config: Configuration dict with:
            - pattern: str (required) - Pattern to search for
            - path: str (required) - File or directory path to search in
            - recursive: bool (optional) - Search recursively in subdirectories (default: True)
            - file_pattern: str (optional) - Glob pattern to filter files (e.g., "*.py", "*.txt")
            - case_sensitive: bool (optional) - Case-sensitive search (default: False)
            - is_regex: bool (optional) - Treat pattern as regex (default: False)
            - max_results: int (optional) - Maximum number of matches to return (default: 100)
            - context_lines: int (optional) - Number of context lines before/after match (default: 0)
            
    Returns:
        Dict with search results
    """
    try:
        pattern = config.get("pattern", "")
        search_path = config.get("path", "")
        recursive = config.get("recursive", True)
        file_pattern = config.get("file_pattern", "*")
        case_sensitive = config.get("case_sensitive", False)
        is_regex = config.get("is_regex", False)
        max_results = config.get("max_results", 100)
        context_lines = config.get("context_lines", 0)
        
        if not pattern:
            return {"success": False, "error": "pattern is required", "matches": [], "total_matches": 0}
        
        if not search_path:
            return {"success": False, "error": "path is required", "matches": [], "total_matches": 0}
        
        if not os.path.exists(search_path):
            return {"success": False, "error": f"Path does not exist: {search_path}", "matches": [], "total_matches": 0}
        
        # Compile pattern
        if is_regex:
            flags = 0 if case_sensitive else regex_module.IGNORECASE
            try:
                compiled_pattern = regex_module.compile(pattern, flags)
            except regex_module.error as e:
                return {"success": False, "error": f"Invalid regex: {e}", "matches": [], "total_matches": 0}
        else:
            if not case_sensitive:
                pattern = pattern.lower()
        
        matches = []
        files_searched = 0
        
        # Get list of files to search
        if os.path.isfile(search_path):
            files_to_search = [search_path]
        else:
            if recursive:
                files_to_search = []
                for root, dirs, files in os.walk(search_path):
                    for filename in files:
                        if fnmatch.fnmatch(filename, file_pattern):
                            files_to_search.append(os.path.join(root, filename))
            else:
                files_to_search = glob.glob(os.path.join(search_path, file_pattern))
                files_to_search = [f for f in files_to_search if os.path.isfile(f)]
        
        # Search each file
        for filepath in files_to_search:
            if len(matches) >= max_results:
                break
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                
                files_searched += 1
                
                for line_num, line in enumerate(lines, 1):
                    if len(matches) >= max_results:
                        break
                    
                    # Check for match
                    if is_regex:
                        match = compiled_pattern.search(line)
                    else:
                        search_line = line if case_sensitive else line.lower()
                        match = pattern in search_line
                    
                    if match:
                        # Get context lines
                        context_before = []
                        context_after = []
                        
                        if context_lines > 0:
                            start = max(0, line_num - 1 - context_lines)
                            end = min(len(lines), line_num + context_lines)
                            context_before = [l.rstrip() for l in lines[start:line_num-1]]
                            context_after = [l.rstrip() for l in lines[line_num:end]]
                        
                        matches.append({
                            "file": filepath,
                            "line_number": line_num,
                            "line": line.rstrip(),
                            "context_before": context_before,
                            "context_after": context_after
                        })
            
            except Exception as e:
                # Skip files that can't be read
                continue
        
        return {
            "success": True,
            "matches": matches,
            "total_matches": len(matches),
            "files_searched": files_searched,
            "truncated": len(matches) >= max_results
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGrepSearch")
        logger.error(err_trace)
        return {"success": False, "error": err_trace, "matches": [], "total_matches": 0}


def find_files(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find files by name pattern.
    
    Args:
        mainwin: Main window instance (unused but required for MCP pattern)
        config: Configuration dict with:
            - path: str (required) - Directory path to search in
            - pattern: str (optional) - Glob pattern to match files (default: "*")
            - recursive: bool (optional) - Search recursively (default: True)
            - file_type: str (optional) - Filter by type: "file", "directory", "any" (default: "any")
            - max_results: int (optional) - Maximum number of results (default: 100)
            - include_size: bool (optional) - Include file sizes (default: True)
            - include_modified: bool (optional) - Include modification times (default: False)
            
    Returns:
        Dict with found files
    """
    try:
        search_path = config.get("path", "")
        pattern = config.get("pattern", "*")
        recursive = config.get("recursive", True)
        file_type = config.get("file_type", "any")
        max_results = config.get("max_results", 100)
        include_size = config.get("include_size", True)
        include_modified = config.get("include_modified", False)
        
        if not search_path:
            return {"success": False, "error": "path is required", "files": [], "total_found": 0}
        
        if not os.path.exists(search_path):
            return {"success": False, "error": f"Path does not exist: {search_path}", "files": [], "total_found": 0}
        
        if not os.path.isdir(search_path):
            return {"success": False, "error": f"Path is not a directory: {search_path}", "files": [], "total_found": 0}
        
        results = []
        
        if recursive:
            for root, dirs, files in os.walk(search_path):
                if len(results) >= max_results:
                    break
                
                # Check directories
                if file_type in ("directory", "any"):
                    for dirname in dirs:
                        if len(results) >= max_results:
                            break
                        if fnmatch.fnmatch(dirname, pattern):
                            full_path = os.path.join(root, dirname)
                            entry = {"path": full_path, "name": dirname, "type": "directory"}
                            if include_modified:
                                try:
                                    entry["modified"] = os.path.getmtime(full_path)
                                except:
                                    pass
                            results.append(entry)
                
                # Check files
                if file_type in ("file", "any"):
                    for filename in files:
                        if len(results) >= max_results:
                            break
                        if fnmatch.fnmatch(filename, pattern):
                            full_path = os.path.join(root, filename)
                            entry = {"path": full_path, "name": filename, "type": "file"}
                            if include_size:
                                try:
                                    entry["size"] = os.path.getsize(full_path)
                                except:
                                    pass
                            if include_modified:
                                try:
                                    entry["modified"] = os.path.getmtime(full_path)
                                except:
                                    pass
                            results.append(entry)
        else:
            # Non-recursive search
            for item in os.listdir(search_path):
                if len(results) >= max_results:
                    break
                
                full_path = os.path.join(search_path, item)
                is_dir = os.path.isdir(full_path)
                
                if file_type == "file" and is_dir:
                    continue
                if file_type == "directory" and not is_dir:
                    continue
                
                if fnmatch.fnmatch(item, pattern):
                    entry = {
                        "path": full_path,
                        "name": item,
                        "type": "directory" if is_dir else "file"
                    }
                    if include_size and not is_dir:
                        try:
                            entry["size"] = os.path.getsize(full_path)
                        except:
                            pass
                    if include_modified:
                        try:
                            entry["modified"] = os.path.getmtime(full_path)
                        except:
                            pass
                    results.append(entry)
        
        return {
            "success": True,
            "files": results,
            "total_found": len(results),
            "truncated": len(results) >= max_results
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFindFiles")
        logger.error(err_trace)
        return {"success": False, "error": err_trace, "files": [], "total_found": 0}


# ==================== Search Tool Schemas ====================

def add_grep_search_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add grep_search tool schema to the tool schemas list."""
    tool_schema = types.Tool(
        name="grep_search",
        description=(
            "<category>Search</category><sub-category>Content Search</sub-category>"
            "Search for patterns within files. Supports literal text and regex patterns. "
            "Can search recursively in directories with file type filtering. "
            "Returns matching lines with file paths and line numbers."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["pattern", "path"],
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Pattern to search for (text or regex)."
                        },
                        "path": {
                            "type": "string",
                            "description": "File or directory path to search in."
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Search recursively in subdirectories. Default: true."
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "Glob pattern to filter files (e.g., '*.py', '*.txt'). Default: '*'."
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "description": "Case-sensitive search. Default: false."
                        },
                        "is_regex": {
                            "type": "boolean",
                            "description": "Treat pattern as regex. Default: false."
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum matches to return. Default: 100."
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": "Number of context lines before/after match. Default: 0."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_find_files_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add find_files tool schema to the tool schemas list."""
    tool_schema = types.Tool(
        name="find_files",
        description=(
            "<category>Search</category><sub-category>File Search</sub-category>"
            "Find files and directories by name pattern. Supports glob patterns like '*.py', 'test_*'. "
            "Can filter by file type (file/directory) and search recursively. "
            "Returns file paths with optional size and modification time."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path to search in."
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern to match (e.g., '*.py', 'test_*'). Default: '*'."
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Search recursively. Default: true."
                        },
                        "file_type": {
                            "type": "string",
                            "enum": ["file", "directory", "any"],
                            "description": "Filter by type. Default: 'any'."
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum results to return. Default: 100."
                        },
                        "include_size": {
                            "type": "boolean",
                            "description": "Include file sizes. Default: true."
                        },
                        "include_modified": {
                            "type": "boolean",
                            "description": "Include modification times. Default: false."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


# ==================== Search Tool Async Wrappers ====================

async def async_grep_search(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for grep_search tool."""
    try:
        input_config = args.get('input', {})
        result = grep_search(mainwin, input_config)
        
        if result.get("success"):
            matches = result.get("matches", [])
            if matches:
                msg_parts = [f"🔍 Found {result['total_matches']} match(es) in {result['files_searched']} file(s)"]
                if result.get("truncated"):
                    msg_parts.append(" (results truncated)")
                msg_parts.append("\n\n")
                
                for m in matches[:20]:  # Show first 20 in message
                    msg_parts.append(f"📄 {m['file']}:{m['line_number']}\n")
                    msg_parts.append(f"   {m['line']}\n")
                
                if len(matches) > 20:
                    msg_parts.append(f"\n... and {len(matches) - 20} more matches")
                
                msg = "".join(msg_parts)
            else:
                msg = f"🔍 No matches found in {result['files_searched']} file(s)"
        else:
            msg = f"❌ Search failed: {result.get('error', 'Unknown error')}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"grep_search_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncGrepSearch")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_find_files(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for find_files tool."""
    try:
        input_config = args.get('input', {})
        result = find_files(mainwin, input_config)
        
        if result.get("success"):
            files = result.get("files", [])
            if files:
                msg_parts = [f"📁 Found {result['total_found']} item(s)"]
                if result.get("truncated"):
                    msg_parts.append(" (results truncated)")
                msg_parts.append("\n\n")
                
                for f in files[:30]:  # Show first 30 in message
                    icon = "📁" if f['type'] == 'directory' else "📄"
                    size_str = ""
                    if 'size' in f:
                        size = f['size']
                        if size < 1024:
                            size_str = f" ({size} B)"
                        elif size < 1024 * 1024:
                            size_str = f" ({size/1024:.1f} KB)"
                        else:
                            size_str = f" ({size/1024/1024:.1f} MB)"
                    msg_parts.append(f"{icon} {f['path']}{size_str}\n")
                
                if len(files) > 30:
                    msg_parts.append(f"\n... and {len(files) - 30} more items")
                
                msg = "".join(msg_parts)
            else:
                msg = "📁 No matching files found"
        else:
            msg = f"❌ Search failed: {result.get('error', 'Unknown error')}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"find_files_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncFindFiles")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]
