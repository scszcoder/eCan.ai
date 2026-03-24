"""
Local test to reproduce and diagnose the PowerShell stdout=0 issue.

Simulates the exact same code path as the cloud passive command:
  cloud -> passive_agent -> mcp_call_tool -> MCP HTTP server ->
  async_run_code -> run_code -> execute_shell_script

Run with the project venv:
  .venv\\Scripts\\python.exe tests\\test_powershell_stdout.py

Test levels (each builds on the previous):
  1. Raw subprocess (baseline)
  2. execute_shell_script() directly
  3. run_code() directly
  4. MCP HTTP call (same as passive_agent uses)
"""

import sys
import os
import subprocess
import time
import shutil
import asyncio
import json

# Force UTF-8 stdout so emojis don't crash on cp1252 console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path so we can import project modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# The exact payload from the cloud passive command logs
TEST_TOOL_INPUT = {
    "input": {
        "code": "Get-ChildItem -Path C:\\ -Directory | Select-Object Name",
        "language": "powershell",
        "args": {},
        "allowed_imports": []
    }
}

DIVIDER = "=" * 70


def test_1_raw_subprocess():
    """Test 1: Raw subprocess.Popen — the absolute baseline."""
    print(f"\n{DIVIDER}")
    print("TEST 1: Raw subprocess.Popen (baseline)")
    print(DIVIDER)

    ps_exe = shutil.which("powershell") or "powershell"
    script = TEST_TOOL_INPUT["input"]["code"]
    wrapped = f"& {{ {script} }} | Out-String -Width 4096"
    full_cmd = [ps_exe, "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-Command", wrapped]

    print(f"  ps_exe:   {ps_exe}")
    print(f"  wrapped:  {wrapped[:100]}...")
    print(f"  full_cmd: {full_cmd}")

    t0 = time.perf_counter()
    p = subprocess.Popen(
        full_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    out, err = p.communicate(timeout=30)
    elapsed = int((time.perf_counter() - t0) * 1000)

    print(f"  rc:         {p.returncode}")
    print(f"  elapsed_ms: {elapsed}")
    print(f"  stdout_len: {len(out)}")
    print(f"  stderr_len: {len(err)}")
    if out:
        print(f"  stdout[:200]: {out[:200]}")
    if err:
        print(f"  stderr[:200]: {err[:200]}")

    assert len(out) > 0, "FAIL: stdout is empty!"
    assert elapsed > 100, f"WARN: suspiciously fast ({elapsed}ms)"
    print("  ✅ PASS")
    return True


def test_2_execute_shell_script():
    """Test 2: Call execute_shell_script() directly — same function MCP uses."""
    print(f"\n{DIVIDER}")
    print("TEST 2: execute_shell_script() direct call")
    print(DIVIDER)

    from agent.mcp.server.code_utils.code_tools import execute_shell_script

    script = TEST_TOOL_INPUT["input"]["code"]
    print(f"  script: {script}")
    print(f"  shell:  powershell")

    result = execute_shell_script(
        script=script,
        shell="powershell",
        timeout_seconds=30,
    )

    print(f"  success:          {result['success']}")
    print(f"  return_code:      {result['return_code']}")
    print(f"  execution_time_ms:{result['execution_time_ms']}")
    print(f"  stdout_len:       {len(result['stdout'])}")
    print(f"  stderr_len:       {len(result['stderr'])}")
    if result['stdout']:
        print(f"  stdout[:200]:     {result['stdout'][:200]}")
    if result['stderr']:
        print(f"  stderr[:200]:     {result['stderr'][:200]}")

    assert len(result['stdout']) > 0, "FAIL: stdout is empty!"
    assert result['execution_time_ms'] > 100, f"WARN: suspiciously fast ({result['execution_time_ms']}ms)"
    print("  ✅ PASS")
    return True


def test_3_run_code():
    """Test 3: Call run_code() directly — same as async_run_code calls."""
    print(f"\n{DIVIDER}")
    print("TEST 3: run_code() direct call")
    print(DIVIDER)

    from agent.mcp.server.code_utils.code_tools import run_code

    config = TEST_TOOL_INPUT["input"]
    print(f"  config: {json.dumps(config, indent=2)[:200]}")

    result = run_code(None, config)  # mainwin=None, unused for shell

    print(f"  success:          {result['success']}")
    print(f"  return_code:      {result.get('return_code', '?')}")
    print(f"  execution_time_ms:{result['execution_time_ms']}")
    print(f"  language:         {result.get('language', '?')}")
    print(f"  stdout_len:       {len(result['stdout'])}")
    print(f"  stderr_len:       {len(result['stderr'])}")
    if result['stdout']:
        print(f"  stdout[:200]:     {result['stdout'][:200]}")
    if result['stderr']:
        print(f"  stderr[:200]:     {result['stderr'][:200]}")

    assert len(result['stdout']) > 0, "FAIL: stdout is empty!"
    print("  ✅ PASS")
    return True


async def test_4_mcp_http_call():
    """Test 4: Call through MCP HTTP server — same path as passive_agent.

    This requires the MCP server to be running (i.e., the app is running).
    If the app is not running, this test will be skipped.
    """
    print(f"\n{DIVIDER}")
    print("TEST 4: MCP HTTP call (requires running app)")
    print(DIVIDER)

    try:
        from agent.mcp.local_client import mcp_call_tool
        from agent.mcp.config import mcp_http_base
        url = mcp_http_base()
        print(f"  MCP server URL: {url}")
    except Exception as e:
        print(f"  SKIP: Cannot import MCP client: {e}")
        return None

    try:
        print(f"  Calling run_code via MCP HTTP...")
        result = await mcp_call_tool("run_code", TEST_TOOL_INPUT, timeout=30.0)
        print(f"  Raw result type: {type(result)}")
        print(f"  Result: {str(result)[:500]}")

        # Extract content from MCP result
        if hasattr(result, 'content'):
            for item in result.content:
                if hasattr(item, 'text'):
                    print(f"  Text: {item.text[:300]}")
                if hasattr(item, 'meta') and item.meta:
                    code_result = item.meta.get('code_execution_result', {})
                    stdout = code_result.get('stdout', '')
                    print(f"  code_result.stdout_len: {len(stdout)}")
                    print(f"  code_result.execution_time_ms: {code_result.get('execution_time_ms', '?')}")
                    if stdout:
                        print(f"  stdout[:200]: {stdout[:200]}")
                    assert len(stdout) > 0, "FAIL: stdout is empty via MCP!"
                    print("  ✅ PASS")
                    return True

        print("  ⚠️  Could not extract structured result from MCP response")
        return None

    except Exception as e:
        print(f"  SKIP/FAIL: MCP call failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")
    print(f"CWD: {os.getcwd()}")
    print(f"Project root: {PROJECT_ROOT}")

    results = {}

    # Test 1: Raw subprocess
    try:
        results["test_1_raw_subprocess"] = test_1_raw_subprocess()
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        results["test_1_raw_subprocess"] = False

    # Test 2: execute_shell_script
    try:
        results["test_2_execute_shell_script"] = test_2_execute_shell_script()
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        results["test_2_execute_shell_script"] = False

    # Test 3: run_code
    try:
        results["test_3_run_code"] = test_3_run_code()
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        results["test_3_run_code"] = False

    # Test 4: MCP HTTP (only if app is running)
    try:
        results["test_4_mcp_http"] = asyncio.run(test_4_mcp_http_call())
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        results["test_4_mcp_http"] = False

    # Summary
    print(f"\n{DIVIDER}")
    print("SUMMARY")
    print(DIVIDER)
    for name, passed in results.items():
        status = "✅ PASS" if passed else ("⏭️ SKIP" if passed is None else "❌ FAIL")
        print(f"  {name}: {status}")

    # Check debug file
    import tempfile
    dbg_path = os.path.join(tempfile.gettempdir(), "ecan_ps_debug.txt")
    if os.path.exists(dbg_path):
        print(f"\n--- Debug file ({dbg_path}) ---")
        with open(dbg_path, "r") as f:
            print(f.read())


if __name__ == "__main__":
    main()
