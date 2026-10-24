"""The unattended supervisor must stay out of the app's log files.

``eCan --watchdog`` is the *same binary* as the app, so importing
``utils.app_watchdog`` reaches ``utils.exit_intent`` -> ``utils.logger_helper``,
whose module-level ``LoggerHelper`` singleton opens ``eCan.log`` (10 MB x 5)
and ``eCan.wscap.log`` (20 MB x 5) in whatever process imports it first. The
supervisor never writes a byte to either file. On Windows that extra handle is
a correctness bug rather than waste: the app's own ``doRollover()`` cannot
rename a file another process holds open, so ``eCan.log`` stops rotating and
grows without a bound for as long as unattended mode runs (the fallback in
``WindowsSafeRotatingFileHandler.doRollover`` keeps appending to the oversized
file and retries 30 s later, forever).

``main.py`` therefore sets ``ECAN_NO_FILE_LOGGING=1`` before any app import
when it sees ``--watchdog``, and ``LoggerHelper.setup()`` honours it.

These tests assert on the child's *open file handles*, not on configured
paths: ``open_files()`` is the thing Windows actually enforces, and it stays
honest even in a dev checkout, where appdata resolves to the repository root
and two runs share one directory.
"""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from utils import app_watchdog as wd

REPO_ROOT = Path(__file__).resolve().parents[2]


def _watchdog_import_report(env_extra):
    """Import the watchdog the way ``main.py --watchdog`` does; report handles.

    ``ECAN_NO_FILE_LOGGING`` is stripped from the inherited environment first,
    so a developer who exported it cannot make the control-group test pass (or
    the isolation test fail) by accident.
    """
    env = {k: v for k, v in os.environ.items() if k != "ECAN_NO_FILE_LOGGING"}
    env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, "-c", _SNIPPET],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True, text=True, timeout=180,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("REPORT"):
            return json.loads(line[len("REPORT"):])
    raise AssertionError(
        "the watchdog child printed no report\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")


_SNIPPET = """
import json
import psutil
import utils.logger_helper as lh
import utils.app_watchdog as wd

report = {
    "log_file_path": lh.logger_helper._log_file_path,
    "build_tag": getattr(lh.logger_helper, "_build_tag", None),
    "handlers": [type(h).__name__ for h in wd._log.handlers],
    "open_files": [f.path for f in psutil.Process().open_files()],
}
print("REPORT" + json.dumps(report))
"""


def test_the_watchdog_process_does_not_open_the_app_logs():
    report = _watchdog_import_report({"ECAN_NO_FILE_LOGGING": "1"})
    assert report["log_file_path"] is None
    assert report["build_tag"] == "console-only"
    opened = {os.path.basename(p) for p in report["open_files"]}
    assert "eCan.log" not in opened, opened
    assert "eCan.wscap.log" not in opened, opened


def test_without_the_flag_the_app_logs_are_what_normal_startup_opens():
    """Control group: the gate must be *added*, not the logging deleted.

    Without this test, dropping the ``ECAN_NO_FILE_LOGGING`` branch (or
    inverting it) would leave the isolation test above green for the wrong
    reason.
    """
    report = _watchdog_import_report({})
    assert report["log_file_path"], report
    assert report["log_file_path"].endswith("eCan.log")
    opened = {os.path.basename(p) for p in report["open_files"]}
    assert "eCan.log" in opened, sorted(opened)


def test_run_starts_only_one_log_handler(monkeypatch, tmp_path):
    """``run()`` is entered many times in one process by the suite, once in production.

    A second ``RotatingFileHandler`` would print every line twice *and* hold a
    second handle on ``watchdog.log``, so neither handler could roll it over.
    Handlers left behind by earlier ``run()`` calls in this process are parked
    for the duration, so the count below measures what *this* test added.
    """
    borrowed = [h for h in wd._log.handlers if getattr(h, "_ecan_watchdog_sink", False)]
    for handler in borrowed:
        wd._log.removeHandler(handler)
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    monkeypatch.setattr(wd, "_acquire_singleton", lambda lock: False)
    try:
        assert wd.run() == 0          # exits at the singleton check, not a real loop
        assert wd.run() == 0
        sinks = [h for h in wd._log.handlers if getattr(h, "_ecan_watchdog_sink", False)]
        assert len(sinks) == 1, sinks
        assert Path(sinks[0].baseFilename).parent == tmp_path
        assert wd._log.level == logging.INFO
        text = (tmp_path / "watchdog.log").read_text(encoding="utf-8")
        assert text.count("another watchdog is running") == 2
    finally:
        for handler in [h for h in wd._log.handlers
                        if getattr(h, "_ecan_watchdog_sink", False)]:
            wd._log.removeHandler(handler)
            handler.close()
        for handler in borrowed:
            wd._log.addHandler(handler)
