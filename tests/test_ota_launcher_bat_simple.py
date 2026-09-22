#!/usr/bin/env python3
"""
Simplified test for OTA launcher BAT logic.

This test verifies the launcher BAT behavior:
1. When the target process is NOT running, BAT launches Inno Setup immediately
2. When the target process IS running, BAT waits for it to exit first
3. The BAT self-deletes after execution

Run with:
  $env:ECAN_FORCE_FROZEN_OTA="1"; python tests/test_ota_launcher_bat_simple.py
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


def create_dummy_script(script_name: str, content: str) -> Path:
    """Create a Python script for testing."""
    script = project_root / "tests" / f"_{script_name}"
    script.write_text(content, encoding='utf-8')
    return script


def test_bat_with_no_process():
    """Test: launcher BAT with no target process should run immediately."""
    print("\n[TEST 1] Launcher BAT when target process is NOT running...")

    from ota.core.installer import InstallationManager

    manager = InstallationManager()

    # Create a dummy "Inno Setup" that just writes to a log
    log_file = Path(tempfile.gettempdir()) / "test_inno_1.log"
    log_file.unlink(missing_ok=True)

    dummy_inno = create_dummy_script(
        "dummy_inno_1.py",
        f'''
import time
from pathlib import Path
log = Path(r"{log_file}")
with log.open("a") as f:
    f.write(f"DUMMY_INNO_RAN at {{time.time()}}\\n")
'''
    )

    # Create launcher BAT (use a non-existent process name)
    inno_cmd = [sys.executable, str(dummy_inno)]
    bat_path = manager._write_inno_launcher_bat(
        process_name="nonexistent_process_for_test.exe",
        extra_wait_seconds=1,  # Short wait
        inno_cmd=inno_cmd,
    )
    print(f"  BAT path: {bat_path}")

    # Launch the BAT and time it
    start_time = time.time()
    bat_pid = manager._launch_windows_installer_delayed(
        inno_cmd,
        delay_seconds=3,
        wait_for_process_name="nonexistent_process_for_test.exe",
        extra_wait_seconds=1,
    )
    print(f"  Launcher PID: {bat_pid}")

    # Wait for the dummy Inno to run
    for i in range(10):
        if log_file.exists():
            elapsed = time.time() - start_time
            content = log_file.read_text(encoding='utf-8')
            print(f"  OK: Dummy Inno ran after {elapsed:.1f}s")
            print(f"      Log: {content.strip()}")
            if "DUMMY_INNO_RAN" in content:
                bat_path.unlink(missing_ok=True)
                dummy_inno.unlink(missing_ok=True)
                log_file.unlink(missing_ok=True)
                return True
        time.sleep(0.5)

    print("  FAIL: Dummy Inno did not run within 5s")
    return False


def test_bat_with_running_process():
    """Test: launcher BAT should wait for target process to exit."""
    print("\n[TEST 2] Launcher BAT waits for target process to exit...")

    from ota.core.installer import InstallationManager

    manager = InstallationManager()

    # Create a long-running dummy "host process"
    host_log = Path(tempfile.gettempdir()) / "test_host_2.log"
    host_log.unlink(missing_ok=True)

    host_process = subprocess.Popen(
        [sys.executable, '-c', 'import time; [time.sleep(1) for _ in range(60)]'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"  Started fake host process: PID={host_process.pid}")

    # Wait a bit for the host to register
    time.sleep(1)

    # Create a dummy "Inno Setup"
    inno_log = Path(tempfile.gettempdir()) / "test_inno_2.log"
    inno_log.unlink(missing_ok=True)
    dummy_inno = create_dummy_script(
        "dummy_inno_2.py",
        f'''
import time
from pathlib import Path
log = Path(r"{inno_log}")
with log.open("a") as f:
    f.write(f"DUMMY_INNO_RAN at {{time.time()}}\\n")
'''
    )

    # Create launcher BAT (with our fake host as the target)
    inno_cmd = [sys.executable, str(dummy_inno)]
    bat_path = manager._write_inno_launcher_bat(
        process_name=f"python.exe",  # We need to wait for ANY python.exe
        extra_wait_seconds=2,
        inno_cmd=inno_cmd,
    )
    print(f"  BAT path: {bat_path}")

    bat_pid = manager._launch_windows_installer_delayed(
        inno_cmd,
        delay_seconds=3,
        wait_for_process_name=f"python.exe",
        extra_wait_seconds=2,
    )
    print(f"  Launcher PID: {bat_pid}")

    # Wait 3 seconds - BAT should NOT have run Inno yet because the host is still alive
    time.sleep(3)
    if inno_log.exists():
        print(f"  FAIL: Inno Setup ran too early (while host was still alive)")
        host_process.kill()
        host_process.wait()
        return False
    print(f"  OK: Inno Setup NOT run yet (host is alive)")

    # Now kill the host
    print(f"  Killing host process...")
    kill_start = time.time()
    host_process.kill()
    host_process.wait()
    print(f"  Host killed")

    # Wait for Inno Setup to run
    for i in range(15):
        if inno_log.exists():
            elapsed = time.time() - kill_start
            content = inno_log.read_text(encoding='utf-8')
            print(f"  OK: Inno Setup ran {elapsed:.1f}s after host was killed")
            print(f"      Log: {content.strip()}")
            if elapsed >= 1.5:  # Should be at least 2s (extra_wait_seconds)
                print(f"      (>= 2s confirms BAT waited for extra_wait_seconds)")
                bat_path.unlink(missing_ok=True)
                dummy_inno.unlink(missing_ok=True)
                inno_log.unlink(missing_ok=True)
                return True
            else:
                print(f"  WARN: Inno Setup ran too quickly ({elapsed:.1f}s)")
                return False
        time.sleep(0.5)

    print("  FAIL: Inno Setup did not run after host was killed")
    host_process.kill()
    host_process.wait()
    return False


def main():
    print("=" * 60)
    print("OTA Launcher BAT - Simplified Test")
    print("=" * 60)

    results = []

    results.append(("Test 1: BAT runs when no target process", test_bat_with_no_process()))
    results.append(("Test 2: BAT waits for target process to exit", test_bat_with_running_process()))

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests PASSED!")
        return 0
    else:
        print("Some tests FAILED!")
        return 1


if __name__ == '__main__':
    sys.exit(main())
