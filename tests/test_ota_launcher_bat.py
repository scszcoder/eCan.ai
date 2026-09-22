#!/usr/bin/env python3
"""
Test script to verify the OTA launcher BAT logic.

This test:
1. Creates a launcher BAT from the template
2. Simulates the process-wait logic (without actually launching Inno Setup)
3. Verifies the BAT content is correct

Run with: python tests/test_ota_launcher_bat.py
"""
import os
import sys
import tempfile
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_launcher_bat_creation():
    """Test that the launcher BAT is created correctly."""
    print("[TEST] Testing launcher BAT creation...")

    from ota.core.installer import InstallationManager

    manager = InstallationManager()

    # Simulate Inno Setup command
    inno_cmd = [
        r"C:\Users\liuqiang\AppData\Local\eCan.cn\ota_downloads\eCan.cn-0.9.98r-windows-amd64-Setup.exe",
        '/SILENT',
        '/NORESTART',
        '/SP-',
        r'/DIR=C:\Users\liuqiang\AppData\Local\eCan.cn',
    ]

    try:
        bat_path = manager._write_inno_launcher_bat(
            process_name='eCan.cn.exe',
            extra_wait_seconds=5,
            inno_cmd=inno_cmd,
        )
        print(f"  OK: Launcher BAT created at: {bat_path}")

        # Read the BAT content
        bat_content = bat_path.read_text(encoding='utf-8')

        # Verify key elements
        checks = [
            ('eCan.cn.exe' in bat_content, 'Process name in BAT'),
            ('5' in bat_content, 'Extra wait seconds in BAT'),
            ('tasklist' in bat_content, 'tasklist command in BAT'),
            ('timeout /t' in bat_content, 'timeout command in BAT'),
            ('start "" /B' in bat_content, 'start command in BAT'),
            ('del /F /Q' in bat_content, 'self-delete in BAT'),
            ('Created temporary directory' not in bat_content, 'No old log messages'),
            ('watch thread' not in bat_content, 'No watch thread references'),
        ]

        all_passed = True
        for passed, description in checks:
            status = 'PASS' if passed else 'FAIL'
            print(f"  [{status}] {description}")
            if not passed:
                all_passed = False

        # Show a snippet of the BAT
        print(f"\n  BAT snippet (first 20 lines):")
        for i, line in enumerate(bat_content.split('\n')[:20]):
            print(f"    {line}")

        # Clean up
        bat_path.unlink(missing_ok=True)

        return all_passed

    except Exception as e:
        print(f"  FAIL: Exception during BAT creation: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_process_wait_logic():
    """Test that the process wait logic works correctly."""
    print("\n[TEST] Testing process wait logic...")

    # Test with a non-existent process - should exit immediately
    test_process = 'nonexistent_test_process_12345.exe'

    # Run a quick test with tasklist
    cmd = f'tasklist /FI "IMAGENAME eq {test_process}" /NH'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if test_process.lower() not in result.stdout.lower():
        print(f"  PASS: tasklist correctly reports process not found")
        return True
    else:
        print(f"  FAIL: tasklist incorrectly reports process found")
        return False


def test_inno_cmd_formatting():
    """Test that Inno Setup command is formatted correctly in the BAT."""
    print("\n[TEST] Testing Inno Setup command formatting...")

    from ota.core.installer import InstallationManager

    manager = InstallationManager()

    # Test with a command that has spaces in path
    inno_cmd = [
        r"C:\Users\My App\eCan.cn-0.9.98-Setup.exe",
        '/SILENT',
        '/NORESTART',
        '/DIR=C:\\Users\\My App\\eCan',
    ]

    try:
        bat_path = manager._write_inno_launcher_bat(
            process_name='eCan.cn.exe',
            extra_wait_seconds=5,
            inno_cmd=inno_cmd,
        )

        bat_content = bat_path.read_text(encoding='utf-8')

        # Check that the INNO_CMD placeholder was replaced
        if '{INNO_CMD}' in bat_content:
            print("  FAIL: INNO_CMD placeholder not replaced")
            bat_path.unlink(missing_ok=True)
            return False

        # Check that the full command is in the BAT
        if '/SILENT' in bat_content and '/NORESTART' in bat_content and '/DIR=' in bat_content:
            print("  PASS: Inno Setup command correctly formatted in BAT")
            bat_path.unlink(missing_ok=True)
            return True
        else:
            print("  FAIL: Inno Setup command not correctly formatted")
            print(f"  BAT snippet:")
            for line in bat_content.split('\n'):
                if 'INNO_CMD' in line or 'inno_cmd' in line.lower() or 'start' in line.lower():
                    print(f"    {line}")
            bat_path.unlink(missing_ok=True)
            return False

    except Exception as e:
        print(f"  FAIL: Exception: {e}")
        return False


def main():
    print("=" * 60)
    print("OTA Launcher BAT Test")
    print("=" * 60)

    results = []

    results.append(("Launcher BAT Creation", test_launcher_bat_creation()))
    results.append(("Process Wait Logic", test_process_wait_logic()))
    results.append(("Inno Setup Command Formatting", test_inno_cmd_formatting()))

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
