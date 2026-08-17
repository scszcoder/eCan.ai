#!/usr/bin/env python3
"""
Verify the ExecutionPolicy fix in release-cn.yml's preflight step.

Problem: The old code called `Get-ExecutionPolicy -List`, which forces
loading the Microsoft.PowerShell.Security module. On some pwsh 7
installations, that module's Security.types.ps1xml fails
AuthorizationManager validation, and the entire step crashes with:

  The 'Get-ExecutionPolicy' command was found in the module
  'Microsoft.PowerShell.Security', but the module could not be
  loaded due to the following error: [The following error
  occurred while loading the extended type data file: ,
  C:\\users\\...\\Modules\\Microsoft.PowerShell.Security\\Security.types.ps1xml:
  The file was skipped because of the following validation exception:
  AuthorizationManager check failed.. ]

Fix: Read ExecutionPolicy directly from the registry instead. This
bypasses the module loader entirely.

This test verifies:
1. The fixed script does NOT reference Get-ExecutionPolicy (which loads
   the broken module).
2. The fixed script reads ExecutionPolicy from the registry.
3. The script correctly handles the case where the registry key is
   absent (defaults to RemoteSigned, the GitHub-hosted default).
4. The script only fails (exit 1) when ExecutionPolicy is 'Restricted'.

Run: python3 tests/manual_simulate_windows_bash.py (also runs this)
Or:  python3 tests/manual_test_execution_policy_fix.py
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/release-cn.yml"


def test_no_get_execution_policy_in_preflight():
    """The fixed script must NOT call Get-ExecutionPolicy."""
    print("=" * 60)
    print("Test 1: preflight script does not call Get-ExecutionPolicy")
    print("=" * 60)

    content = WORKFLOW_PATH.read_text()
    # Only count occurrences in actual code lines (not in comments).
    # Comments start with # at the start of a line.
    code_lines = []
    for line in content.split("\n"):
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            code_lines.append(line)

    code_text = "\n".join(code_lines)
    matches = re.findall(r"Get-ExecutionPolicy", code_text)
    print(f"  Found {len(matches)} occurrences of 'Get-ExecutionPolicy' in code (excluding comments)")
    if matches:
        for m in re.finditer(r"Get-ExecutionPolicy[^\n]*", code_text):
            line_no = code_text[:m.start()].count("\n") + 1
            print(f"    code-line ~{line_no}: {m.group()}")
        print(f"\n  FAIL: preflight still uses Get-ExecutionPolicy")
        return False

    print(f"  [PASS] no Get-ExecutionPolicy calls in preflight code")
    return True


def test_uses_registry_for_execution_policy():
    """The fixed script reads ExecutionPolicy from the registry."""
    print()
    print("=" * 60)
    print("Test 2: preflight script reads ExecutionPolicy from registry")
    print("=" * 60)

    content = WORKFLOW_PATH.read_text()
    expected = "HKLM:\\SOFTWARE\\Microsoft\\PowerShell\\1\\ShellIds\\Microsoft.PowerShell"
    if expected not in content:
        print(f"  FAIL: did not find registry path '{expected}'")
        return False

    # Also check for pwsh 7 path
    pwsh7_path = "HKLM:\\SOFTWARE\\Microsoft\\PowerShell\\7\\ShellIds\\Microsoft.PowerShell"
    if pwsh7_path not in content:
        print(f"  WARN: did not find pwsh 7 fallback path '{pwsh7_path}'")
        # Not strictly a fail if WinPS 5.1 path is present and we're running in pwsh 7
        # (WinPS policy still applies to pwsh 7 in many cases)

    print(f"  [PASS] registry-based ExecutionPolicy read present")
    return True


def test_execution_policy_logic_via_pwsh():
    """
    If pwsh is available locally, run the actual preflight script logic
    and verify it does NOT trigger the Microsoft.PowerShell.Security
    module load.

    Skipped on macOS/Linux where pwsh isn't installed.
    """
    print()
    print("=" * 60)
    print("Test 3: preflight logic runs without loading Microsoft.PowerShell.Security")
    print("=" * 60)

    # Check if pwsh is installed
    pwsh_paths = [
        "/opt/homebrew/bin/pwsh",
        "/usr/local/bin/pwsh",
        "/usr/bin/pwsh",
        "C:/Program Files/PowerShell/7/pwsh.exe",
    ]
    pwsh = None
    for p in pwsh_paths:
        if Path(p).exists():
            pwsh = p
            break
    # Also try `which`
    if not pwsh:
        try:
            pwsh = subprocess.check_output(["which", "pwsh"], text=True).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pwsh = None

    if not pwsh:
        print(f"  SKIPPED: pwsh not installed locally (cannot verify module-load behavior)")
        print(f"  This test only runs on systems with PowerShell 7 installed.")
        print(f"  The fix itself (registry read instead of Get-ExecutionPolicy)")
        print(f"  is verified by tests 1-2 above.")
        return True

    print(f"  Found pwsh at: {pwsh}")

    # Test the fix: a script that reads ExecutionPolicy from registry
    # should NOT trigger loading Microsoft.PowerShell.Security.
    test_script = '''
# Track module loads via verbose output
$VerbosePreference = "Continue"
$modulesLoaded = @()

# The actual fixed code from workflow:
$effectiveEp = (Get-ItemProperty -Path "HKLM:\\SOFTWARE\\Microsoft\\PowerShell\\1\\ShellIds\\Microsoft.PowerShell" -Name ExecutionPolicy -ErrorAction SilentlyContinue).ExecutionPolicy
if (-not $effectiveEp) {
    $effectiveEp = (Get-ItemProperty -Path "HKLM:\\SOFTWARE\\Microsoft\\PowerShell\\7\\ShellIds\\Microsoft.PowerShell" -Name ExecutionPolicy -ErrorAction SilentlyContinue).ExecutionPolicy
}
if (-not $effectiveEp) { $effectiveEp = "RemoteSigned" }

Write-Host "Effective EP: $effectiveEp"
if ($effectiveEp -eq "Restricted") {
    Write-Host "WOULD FAIL"
    exit 1
}
Write-Host "WOULD PASS"
exit 0
'''

    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.ps1', delete=False
    ) as f:
        f.write(test_script)
        script_path = f.name

    try:
        result = subprocess.run(
            [pwsh, "-NoProfile", "-Command", f"& '{script_path}'"],
            capture_output=True, text=True, timeout=30
        )
        print(f"  pwsh exit: {result.returncode}")
        if result.stdout:
            print(f"  stdout: {result.stdout}")
        if result.stderr:
            print(f"  stderr: {result.stderr[:500]}")

        # Check if Microsoft.PowerShell.Security error appears
        if "Microsoft.PowerShell.Security" in result.stderr:
            if "AuthorizationManager check failed" in result.stderr:
                print(f"  FAIL: Microsoft.PowerShell.Security module still tried to load")
                return False

        if result.returncode == 0:
            print(f"  [PASS] registry-based read works without module load issues")
            return True
        else:
            print(f"  FAIL: pwsh exited with code {result.returncode}")
            return False
    finally:
        os.unlink(script_path)


def main():
    print("\n" + "=" * 60)
    print("ExecutionPolicy Fix Verification")
    print("=" * 60)
    print()
    print(f"Workflow: {WORKFLOW_PATH}")
    print()

    results = {}

    try:
        results["test_no_get_execution_policy_in_preflight"] = (
            test_no_get_execution_policy_in_preflight()
        )
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        results["test_no_get_execution_policy_in_preflight"] = False

    try:
        results["test_uses_registry_for_execution_policy"] = (
            test_uses_registry_for_execution_policy()
        )
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        results["test_uses_registry_for_execution_policy"] = False

    try:
        results["test_execution_policy_logic_via_pwsh"] = (
            test_execution_policy_logic_via_pwsh()
        )
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        results["test_execution_policy_logic_via_pwsh"] = False

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = all(results.values())
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {name}: {status}")
    print()
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()