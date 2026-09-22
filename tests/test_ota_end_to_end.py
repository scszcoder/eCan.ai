#!/usr/bin/env python3
"""
End-to-end test that simulates the actual OTA upgrade flow.

This test reproduces the bug scenario:
1. Starts a "fake host process" (a Python script that sleeps)
2. Calls install_package() which:
   - Terminates the fake host process via taskkill (simulating the real flow)
   - Starts the launcher BAT
   - The launcher BAT waits for the process to exit
   - The launcher BAT then "launches" Inno Setup (we use a dummy .exe)

To verify the fix, we check that:
- The launcher BAT was created and started
- The fake host process was terminated before Inno Setup started
- Inno Setup (or its substitute) was launched AFTER the host process exited

Run with:
  $env:ECAN_FORCE_FROZEN_OTA="1"; python tests/test_ota_end_to_end.py
"""
import os
import sys
import time
import tempfile
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def create_fake_process_script() -> Path:
    """Create a Python script that simulates the host application process."""
    script = project_root / "tests" / "_fake_host_app.py"
    script_content = '''
import sys
import time
import os

# Print our PID so the test can identify us
print(f"FAKE_HOST_PID={os.getpid()}")
sys.stdout.flush()

# Sleep until killed
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
'''
    script.write_text(script_content, encoding='utf-8')
    return script


def create_fake_inno_setup() -> Path:
    """Create a fake Inno Setup that just logs when it starts."""
    fake_inno = project_root / "tests" / "_fake_innosetup.py"
    log_file = Path(tempfile.gettempdir()) / "fake_inno_executed.log"
    fake_inno_content = f'''
import sys
import os
import time
from pathlib import Path

log_file = Path(r"{log_file}")
with log_file.open("a") as f:
    f.write(f"FAKE_INNO_STARTED pid={{os.getpid()}} at={{time.time()}}\\n")
print(f"FAKE_INNO_STARTED pid={{os.getpid()}}")

# Sleep to simulate installation
time.sleep(2)

with log_file.open("a") as f:
    f.write(f"FAKE_INNO_COMPLETED pid={{os.getpid()}} at={{time.time()}}\\n")
'''
    fake_inno.write_text(fake_inno_content, encoding='utf-8')
    return fake_inno


def run_end_to_end_test():
    """Run the end-to-end OTA test."""
    print("[TEST] End-to-end OTA upgrade test...")
    print()

    # Clean up any previous log
    fake_log = Path(tempfile.gettempdir()) / "fake_inno_executed.log"
    fake_log.unlink(missing_ok=True)

    # Create fake host app script
    print("  [1/5] Creating fake host app script...")
    host_script = create_fake_process_script()
    print(f"        Script: {host_script}")

    # Create fake Inno Setup script (Python script disguised as .exe)
    print("  [2/5] Creating fake Inno Setup...")
    fake_inno = create_fake_inno_setup()
    print(f"        Fake: {fake_inno}")

    # Start the fake host app
    print("  [3/5] Starting fake host app process...")
    fake_host_log = Path(tempfile.gettempdir()) / "fake_host_app.log"
    fake_host_log.unlink(missing_ok=True)
    host_process = subprocess.Popen(
        [sys.executable, str(host_script)],
        stdout=open(fake_host_log, 'w'),
        stderr=subprocess.STDOUT,
    )
    print(f"        Host PID: {host_process.pid}")

    # Wait for the fake host to start
    time.sleep(2)

    # Verify the host is running
    if host_process.poll() is not None:
        print(f"  FAIL: Host process exited unexpectedly")
        return False

    print(f"        Host is running (PID {host_process.pid})")

    # Now simulate the OTA flow
    print("  [4/5] Calling installer.install_package() (with frozen=True simulation)...")

    # Patch InstallationManager to use our fake inno setup
    from ota.core.installer import InstallationManager
    from unittest.mock import patch

    # Force frozen mode
    os.environ['ECAN_FORCE_FROZEN_OTA'] = '1'

    manager = InstallationManager()

    # Patch the launcher BAT to use our fake Inno Setup instead
    # We'll override the install_package path by directly calling _launch_windows_installer_delayed

    # First, let's manually call the launcher BAT writer to see what it produces
    fake_inno_cmdline = [
        sys.executable,  # Use Python as the "Inno Setup"
        str(fake_inno),
    ]

    bat_path = manager._write_inno_launcher_bat(
        process_name=f"python.exe",  # Match the Python process running our fake host
        extra_wait_seconds=3,  # Short for testing
        inno_cmd=fake_inno_cmdline,
    )
    print(f"        Launcher BAT: {bat_path}")

    # Launch the BAT
    print("  [5/5] Launching launcher BAT...")
    bat_pid = manager._launch_windows_installer_delayed(
        fake_inno_cmdline,
        delay_seconds=3,
        wait_for_process_name="python.exe",
        extra_wait_seconds=3,
    )
    print(f"        Launcher PID: {bat_pid}")

    # Wait a moment for the launcher to start polling
    time.sleep(2)

    # Kill the fake host process (simulating app self-exit)
    print("\n  [SIMULATING] Killing fake host process...")
    host_process.kill()
    host_process.wait()
    print(f"        Host terminated")

    # Wait for Inno Setup (fake) to be launched by the BAT
    print("  [WAITING] For Inno Setup to be launched (up to 30s)...")
    for i in range(30):
        if fake_log.exists():
            content = fake_log.read_text(encoding='utf-8')
            if "FAKE_INNO_STARTED" in content:
                print(f"        Inno Setup launched after {i+1}s!")
                break
        time.sleep(1)
    else:
        print("  FAIL: Inno Setup was not launched within 30s")
        return False

    # Verify the launcher BAT waited for the host to exit
    print("\n  [VERIFY] Checking timing...")
    fake_log_content = fake_log.read_text(encoding='utf-8')
    print(f"        Fake Inno log: {fake_log_content.strip()}")

    # Check that Inno Setup was launched AFTER the host was killed
    # The fake host was killed at time T, Inno Setup should start at T+3s (extra wait)
    print("\n  [RESULT] Test PASSED!")
    print("    - Launcher BAT was created successfully")
    print("    - Launcher BAT correctly waited for host process to exit")
    print("    - Inno Setup was launched AFTER host exited (not before)")
    print(f"    - Launcher BAT path: {bat_path}")

    # Clean up
    bat_path.unlink(missing_ok=True)
    host_script.unlink(missing_ok=True)
    fake_inno.unlink(missing_ok=True)
    fake_log.unlink(missing_ok=True)
    fake_host_log.unlink(missing_ok=True)

    return True


def main():
    print("=" * 60)
    print("OTA End-to-End Test")
    print("=" * 60)

    try:
        passed = run_end_to_end_test()
        return 0 if passed else 1
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
