"""What one agent costs: memory and threads around its build, start and stop.

Lines go to runlogs/memory.log as ``[agent-cost]``:

    [agent-cost] build '客服小晴': +38.2 MB RSS, +0 threads (812.4 MB, 221 threads)
    [agent-cost] start '客服小晴': +4.1 MB RSS, +3 threads [SkillExec, ThreadPoolExecutor-2, mem0] ...
    [agent-cost] start '客服小晴' (after 10 s, gc): ...
    [agent-cost] stop '客服小晴' (after 3 s, gc): -29.8 MB RSS, -3 threads ...

Deltas are process-wide: other work running at the same moment (startup,
other agents building in parallel) adds noise, so read the median over many
agents, or a build/stop done on its own (lazy wake, a saved agent restarting).
"""
from __future__ import annotations

import gc
import logging
import threading
import time
from typing import Optional, Tuple

_log = logging.getLogger('memory_monitor')   # memory.log (utils/memory_monitor.py)

Snapshot = Tuple[float, frozenset]


def snapshot() -> Optional[Snapshot]:
    try:
        import psutil
        rss = psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return None
    return rss, frozenset((t.ident, t.name) for t in threading.enumerate() if t.name != "AgentCostStop")


def _thread_family(name: str) -> str:
    # 'ThreadPoolExecutor-2_3' -> 'ThreadPoolExecutor-2', 'Thread-12 (run)' -> 'Thread'
    base = name.split('_')[0] if name.startswith('ThreadPoolExecutor') else name
    return base.split('-')[0] if base.startswith('Thread-') else base


def log_delta(event: str, name: str, before: Optional[Snapshot]) -> None:
    after = snapshot()
    if before is None or after is None:
        return
    rss_b, th_b = before
    rss_a, th_a = after
    new = sorted({_thread_family(n) for _, n in th_a - th_b})
    gone = sorted({_thread_family(n) for _, n in th_b - th_a})
    names = (f" new [{', '.join(new)}]" if new else "") + (f" gone [{', '.join(gone)}]" if gone else "")
    _log.info(f"[agent-cost] {event} '{name}': {rss_a - rss_b:+.1f} MB RSS, "
              f"{len(th_a) - len(th_b):+d} threads{names} ({rss_a:.1f} MB, {len(th_a)} threads)")


def log_later(event: str, name: str, before: Optional[Snapshot], delay_s: float) -> None:
    """Threads an agent starts or stops come and go a little after the call
    returns, and freed memory needs a gc pass."""
    def _later():
        time.sleep(delay_s)
        gc.collect()
        log_delta(f"{event} (after {delay_s:g} s, gc)", name, before)
    threading.Thread(target=_later, name="AgentCostStop", daemon=True).start()
