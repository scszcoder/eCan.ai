"""A thread pool that fills once and stays full is not a leak: it warns once, a growing category keeps warning."""
import logging
from types import SimpleNamespace

from utils import memory_monitor
from utils.memory_monitor import MemoryMonitor


def _warnings(counts_per_check, monkeypatch, caplog):
    mon = MemoryMonitor()
    for counts in counts_per_check:
        threads = [SimpleNamespace(name="AsyncPreload") for i in range(counts)]
        monkeypatch.setattr(memory_monitor.threading, "enumerate", lambda t=threads: t)
        mon._log_thread_breakdown(len(threads))
    return [r for r in caplog.records if "thread-leak suspects" in r.getMessage()]


def test_a_pool_that_stays_full_warns_once(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="memory_monitor")
    assert len(_warnings([1, 7] + [7] * 50, monkeypatch, caplog)) == 1


def test_a_growing_category_keeps_warning(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="memory_monitor")
    assert len(_warnings([1, 7, 7, 12, 12, 17], monkeypatch, caplog)) == 3
