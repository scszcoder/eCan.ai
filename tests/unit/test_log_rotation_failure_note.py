"""A failed eCan.log rotation must say so in the log itself.

2026-11-18: rotation kept failing on a customer PC; the only message went to
stderr (nowhere in the packaged GUI) and eCan.log grew to 341 MB, past what a
bug report uploads.
"""
import logging
import sys

import pytest

from utils import logger_helper as lh


@pytest.mark.skipif(sys.platform != "win32", reason="the retry/fallback path is Windows-only")
def test_failed_rotation_is_noted_in_the_log_once(tmp_path, monkeypatch):
    path = tmp_path / "eCan.log"
    h = lh.WindowsSafeRotatingFileHandler(str(path), maxBytes=50, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(message)s"))

    def locked(*a, **k):
        raise PermissionError(32, "being used by another process")
    monkeypatch.setattr(lh.RotatingFileHandler, "doRollover", locked)
    monkeypatch.setattr(h, "rotate", locked)
    monkeypatch.setattr(lh.time, "sleep", lambda s: None)

    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "x" * 60, None, None)
    for _ in range(3):
        h.emit(rec)
        h._rollover_retry_after = 0          # retry on every record
    h.close()
    text = path.read_text(encoding="utf-8")
    assert text.count("log rotation failed (PermissionError") == 1
    assert text.count("x" * 60) == 3          # records still written
