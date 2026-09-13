"""Per-turn LLM/MCP usage accounting, for reporting what one turn cost.

``turn_done`` carries ``cost_usd`` / ``input_tokens`` / ``output_tokens``, so a
serving pod has to answer "what did this turn cost?" at the moment it finishes.
``TokenTracker`` already computes exactly those numbers per call — but it
persists them through ``token_usage_service``, which a pod does not have (no
``ec_db_mgr``), and it returns early when that service is missing. So the
numbers exist and are then dropped.

This keeps them, **scoped to the turn that spent them**. A pod runs several
turns at once (``cn_serve.Capacity``), so a global counter read before and after
a turn charges it for whatever its neighbours spent in the same window — with
two overlapping turns of 1000 and 10 tokens, both get billed 1010. Cost
attribution that is quietly wrong is worse than none, so the window is a
``ContextVar``: each turn opens its own, and a sample lands in whichever window
is current.

``contextvars`` is the right primitive because the boundaries a turn actually
crosses preserve it: an ``asyncio.Task`` copies the context at creation (so
turns started by ``serve`` are isolated from each other), and
``asyncio.to_thread`` copies it too (so the execution core, which runs off the
loop, still reports into its own turn's window).

**Known gap:** a raw ``ThreadPoolExecutor`` / ``threading.Thread`` started deep
in a skill does *not* inherit the context, so samples from such a thread land in
the process-wide total and are missing from the turn's figure. That direction is
an undercount for one turn, never a cross-charge to another — the safe way round.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Optional

_lock = threading.Lock()


@dataclass(frozen=True)
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def __sub__(self, other: "UsageTotals") -> "UsageTotals":
        return UsageTotals(
            input_tokens=self.input_tokens - other.input_tokens,
            output_tokens=self.output_tokens - other.output_tokens,
            cost_usd=round(self.cost_usd - other.cost_usd, 10),
            calls=self.calls - other.calls,
        )

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "calls": self.calls,
        }


class UsageWindow:
    """One turn's tally. Read it after the turn; it is its own lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._totals = UsageTotals()

    def add(self, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        with self._lock:
            self._totals = UsageTotals(
                input_tokens=self._totals.input_tokens + int(input_tokens or 0),
                output_tokens=self._totals.output_tokens + int(output_tokens or 0),
                cost_usd=self._totals.cost_usd + float(cost_usd or 0.0),
                calls=self._totals.calls + 1,
            )

    @property
    def totals(self) -> UsageTotals:
        with self._lock:
            return self._totals


_current: ContextVar[Optional[UsageWindow]] = ContextVar("ecan_usage_window", default=None)

# Process-wide total. Still kept: it is where samples from a context that has no
# window land, and it is what a caller measuring by snapshot delta reads.
_totals = UsageTotals()


@contextmanager
def turn_usage() -> Iterator[UsageWindow]:
    """Open a usage window for the work done inside this block.

    Isolated per task and per ``to_thread`` call, so concurrent turns each get
    their own tally instead of sharing one moving total.
    """
    window = UsageWindow()
    token = _current.set(window)
    try:
        yield window
    finally:
        _current.reset(token)


def record_usage_sample(input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    """Add one call's usage. Never raises — accounting must not break a run."""
    global _totals
    try:
        window = _current.get()
        if window is not None:
            window.add(input_tokens, output_tokens, cost_usd)
        with _lock:
            _totals = UsageTotals(
                input_tokens=_totals.input_tokens + int(input_tokens or 0),
                output_tokens=_totals.output_tokens + int(output_tokens or 0),
                cost_usd=_totals.cost_usd + float(cost_usd or 0.0),
                calls=_totals.calls + 1,
            )
    except Exception:
        pass


def snapshot() -> UsageTotals:
    """Process-wide usage so far. Subtract two snapshots to measure a window.

    Correct only when nothing else is running concurrently — prefer
    ``turn_usage()`` for anything per-turn.
    """
    with _lock:
        return _totals


def reset() -> None:
    """Test helper — drop the counters."""
    global _totals
    with _lock:
        _totals = UsageTotals()
