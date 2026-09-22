"""Standalone verification test for the OTA launcher BAT fix.

Verifies the two bugs we just fixed in
``ota/resources/ecan_ota_launcher_template.bat``:

  1. ``set "FILTER=/FI \"...\""`` -- cmd.exe's ``set`` does NOT
     process ``\"`` as an escape, so FILTER ended up with literal
     backslashes and tasklist failed with
     ``Invalid parameter/option - 'eq'``.

  2. ``2^>nul`` -- the caret escapes the ``>`` into a literal, so
     tasklist received the literal string ``2>nul`` as an argument
     instead of stderr redirection. Same ``Invalid parameter/
     option - '2>nul'`` failure mode.

Both bugs combined to make the launcher wait-loop a no-op in
production: tasklist always failed, ERRORLEVEL was always non-zero,
the BAT skipped straight to ``WAIT_DONE``, and Inno Setup was
launched while the host process still held file locks -- the
"Created temporary directory" hang we've been chasing.

To avoid a deadlock (where the BAT waits for the very cmd.exe that
runs it), scenarios that need an alive target use a child
``ping.exe`` whose lifetime we control.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, '.')
from ota.core.installer import InstallationManager


PASS_MARK = 'PASS'
FAIL_MARK = 'FAIL'
results = []


def check(cond: bool, msg: str) -> None:
    results.append(bool(cond))
    print(f'  [{PASS_MARK if cond else FAIL_MARK}] {msg}')


def run_bat(bat_path: Path, timeout: int = 130) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['cmd.exe', '/c', str(bat_path)],
        capture_output=True, text=True, timeout=timeout,
    )


def wait_count_from(r: subprocess.CompletedProcess) -> int:
    m = re.search(r'waited (\d+) seconds', r.stdout)
    return int(m.group(1)) if m else -1


def main() -> int:
    print('=' * 60)
    print('OTA launcher BAT fix verification')
    print('=' * 60)
    m = InstallationManager()

    # ----- Scenario 1: name mode, target NOT running -----
    print('\n[Scenario 1] name mode, target NOT running -> immediate exit')
    bat = m._write_inno_launcher_bat(
        wait_mode='name',
        wait_target='nonexistent_target_xyz_12345.exe',
        extra_wait_seconds=1,
        inno_cmd=['setup.exe', '/SILENT'],
    )
    r = run_bat(bat, timeout=20)
    wc = wait_count_from(r)
    print(f'  exit={r.returncode}, WAIT_COUNT={wc}')
    check(wc == 0, 'WAIT_COUNT=0 (immediate exit, no false-positive wait)')
    check('Starting Inno Setup' in r.stdout, 'BAT proceeds to start Inno Setup')
    check('eq' not in r.stderr.lower(), 'no tasklist "eq" error in stderr')
    check('2>nul' not in r.stderr.lower(), 'no tasklist "2>nul" error in stderr')

    # ----- Scenario 2: name mode, target alive briefly, then exits -----
    print('\n[Scenario 2] name mode, target alive 3s then exits -> loop until exit')
    # Spawn a ping child that lives ~3 seconds. The BAT waits for ping.exe.
    ping = subprocess.Popen(
        ['ping', '127.0.0.1', '-n', '5'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=0x00000008,  # DETACHED_PROCESS
    )
    try:
        time.sleep(0.5)  # let ping register in tasklist
        bat = m._write_inno_launcher_bat(
            wait_mode='name',
            wait_target='ping.exe',
            extra_wait_seconds=1,
            inno_cmd=['setup.exe', '/SILENT'],
        )
        start = time.time()
        r = run_bat(bat, timeout=20)
        elapsed = time.time() - start
    finally:
        try:
            ping.kill()
        except Exception:
            pass
    wc = wait_count_from(r)
    print(f'  exit={r.returncode}, WAIT_COUNT={wc}, elapsed={elapsed:.1f}s')
    check(wc >= 2, f'WAIT_COUNT >= 2 (BAT actually looped), got {wc}')
    check('eq' not in r.stderr.lower(), 'no tasklist "eq" error in stderr')
    check('2>nul' not in r.stderr.lower(), 'no tasklist "2>nul" error in stderr')

    # ----- Scenario 3: pid mode, target NOT running -----
    print('\n[Scenario 3] pid mode, target PID NOT running -> immediate exit')
    bat = m._write_inno_launcher_bat(
        wait_mode='pid',
        wait_target='99999',
        extra_wait_seconds=1,
        inno_cmd=['setup.exe', '/SILENT'],
    )
    r = run_bat(bat, timeout=20)
    wc = wait_count_from(r)
    print(f'  exit={r.returncode}, WAIT_COUNT={wc}')
    check(wc == 0, 'pid mode with nonexistent PID exits immediately')
    check('eq' not in r.stderr.lower(), 'no tasklist "eq" error in stderr')

    # ----- Scenario 4: pid mode, target PID alive -----
    print('\n[Scenario 4] pid mode, target PID alive -> loop until exit')
    ping = subprocess.Popen(
        ['ping', '127.0.0.1', '-n', '5'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=0x00000008,
    )
    try:
        time.sleep(0.5)
        bat = m._write_inno_launcher_bat(
            wait_mode='pid',
            wait_target=str(ping.pid),
            extra_wait_seconds=1,
            inno_cmd=['setup.exe', '/SILENT'],
        )
        start = time.time()
        r = run_bat(bat, timeout=20)
        elapsed = time.time() - start
    finally:
        try:
            ping.kill()
        except Exception:
            pass
    wc = wait_count_from(r)
    print(f'  exit={r.returncode}, WAIT_COUNT={wc}, elapsed={elapsed:.1f}s')
    check(wc >= 2, f'pid mode WAIT_COUNT >= 2 (BAT looped on real PID), got {wc}')
    check('eq' not in r.stderr.lower(), 'no tasklist "eq" error in stderr')

    # ----- Summary -----
    passed = sum(results)
    total = len(results)
    print()
    print('=' * 60)
    print(f'Summary: {passed}/{total} checks passed')
    print('=' * 60)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
