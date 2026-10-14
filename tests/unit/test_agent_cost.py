"""[agent-cost] lines: memory and thread deltas around an agent's build/start/stop."""
import logging
import threading
import time

from utils import agent_cost


class _Grab(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def test_delta_names_the_new_threads():
    grab = _Grab()
    log = logging.getLogger("memory_monitor")
    log.addHandler(grab)
    log.setLevel(logging.INFO)
    try:
        before = agent_cost.snapshot()
        stop = threading.Event()
        t = threading.Thread(target=stop.wait, name="SkillExec_0", daemon=True)
        t.start()
        agent_cost.log_delta("start", "客服小晴", before)
        stop.set()
        t.join()
    finally:
        log.removeHandler(grab)
    line = grab.lines[-1]
    assert line.startswith("[agent-cost] start '客服小晴': ") and "+1 threads" in line and "SkillExec" in line


def test_log_later_does_not_count_its_own_thread():
    grab = _Grab()
    log = logging.getLogger("memory_monitor")
    log.addHandler(grab)
    log.setLevel(logging.INFO)
    try:
        agent_cost.log_later("stop", "a", agent_cost.snapshot(), 0.05)
        for _ in range(50):
            if grab.lines:
                break
            time.sleep(0.05)
    finally:
        log.removeHandler(grab)
    assert "stop (after 0.05 s, gc)" in grab.lines[-1] and "+0 threads" in grab.lines[-1]
