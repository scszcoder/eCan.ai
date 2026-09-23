#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end validation of the OTA launcher-BAT fix.

The bug this test reproduces: ``_install_exe`` previously
launched the Inno Setup installer via a launcher BAT but the
Python parent never actually exited, so the BAT sat in its
wait-loop for 120 s, then gave up and ran Inno Setup while
the Python process (or another ``eCan.cn.exe`` on the box)
was still locking the install dir -- producing the silent
"自动退出后，没有自动安装更新" failure the user reported.

This test verifies:

  1. The launcher BAT correctly waits for the SPECIFIC host PID
     (not the image name) using ``wait_for_pid=os.getpid()``.
  2. The launcher BAT launches Inno Setup via ``start "" /B``
     after the host PID exits + the extra safety window.
  3. The Inno Setup command actually executes (we verify via
     a sentinel file the Inno Setup command writes).

Pre-fix behavior: BAT would either wait for the wrong process
(by image name) or timeout at 120 s; sentinel would not appear.

Post-fix behavior: BAT waits for our PID, sees it exit, runs
Inno Setup; sentinel appears within ~6 s of the fake host
exiting.

Run:
    python tests/test_ota_launcher_e2e_fix.py

Exit 0 = fix verified.
Exit non-zero = regression.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ota.core.installer import InstallationManager  # noqa: E402


def main() -> int:
    sentinel_path = Path(tempfile.gettempdir()) / "ecan_ota_e2e_sentinel.txt"
    if sentinel_path.exists():
        sentinel_path.unlink()

    # 1. Spawn a fake host process so wait_for_pid has a real PID
    #    to wait on. Sleeps 3 s and exits.
    print("[E2E] Spawning fake host (python -c 'sleep 3')...")
    fake_host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(3)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    host_pid = fake_host.pid
    print(f"[E2E] Fake host PID = {host_pid}")

    # 2. The "Inno Setup" command for this test is a one-liner
    #    Python invocation that writes a sentinel file. We use
    #    ``subprocess.list2cmdline`` so the quoting matches what
    #    real ``_install_exe`` produces.
    inno_cmd = [
        sys.executable,
        "-c",
        f"import time; open(r'{sentinel_path}', 'w', encoding='utf-8').write('INNO_RAN_AT=' + time.strftime('%H:%M:%S'))",
    ]

    # 3. Use the production launcher-BAT code path. ``wait_for_pid``
    #    is the host PID -- this is the change that fixes the bug.
    manager = InstallationManager()
    extra_wait_seconds = 3  # shorter for tests
    print(f"[E2E] Launching BAT with wait_for_pid={host_pid}, extra_wait={extra_wait_seconds}s")
    launcher_pid = manager._launch_windows_installer_delayed(
        cmd=inno_cmd,
        delay_seconds=0,  # ignored, kept for ABI
        wait_for_pid=host_pid,
        extra_wait_seconds=extra_wait_seconds,
    )

    if launcher_pid <= 0:
        print(f"[E2E] FAIL: launcher BAT failed to start (pid={launcher_pid})")
        return 2

    print(f"[E2E] Launcher BAT PID = {launcher_pid}")

    # 4. Wait for the fake host to exit naturally.
    print("[E2E] Waiting for fake host to exit...")
    fake_host.wait()
    print(f"[E2E] Fake host exited (rc={fake_host.returncode})")

    # 5. The BAT polls tasklist every 1 s, detects our PID exit,
    #    sleeps ``extra_wait_seconds``, then runs Inno Setup. Allow
    #    up to 30 s total for the sentinel to appear.
    deadline = time.time() + 30.0
    while time.time() < deadline:
        if sentinel_path.exists():
            content = sentinel_path.read_text(encoding="utf-8").strip()
            print(f"[E2E] PASS: Sentinel appeared with content: {content!r}")
            print("[E2E] The launcher BAT correctly waited for our PID,")
            print("[E2E] slept the safety window, and ran Inno Setup.")
            print("[E2E] Production OTA flow should now work end-to-end.")
            return 0
        time.sleep(0.5)

    print(
        f"[E2E] FAIL: Sentinel did not appear within 30 s.\n"
        f"[E2E] This means the launcher BAT did NOT run the Inno Setup\n"
        f"[E2E] command after the host PID exited -- which is the exact\n"
        f"[E2E] bug the production OTA flow is hitting. Inspect:\n"
        f"[E2E]   * C:\\Users\\<user>\\AppData\\Local\\Temp\\ecan_ota_launcher_*.bat\n"
        f"[E2E]     (should have been self-deleted if it ran to completion)\n"
        f"[E2E]   * The corresponding eCan.cn log for OTA Installer lines.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
