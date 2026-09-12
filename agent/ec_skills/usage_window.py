"""Process-wide LLM/MCP usage counters, for reporting what one turn cost.

``turn_done`` carries ``cost_usd`` / ``input_tokens`` / ``output_tokens``, so a
serving pod has to answer "what did this turn cost?" at the moment it finishes.
``TokenTracker`` already computes exactly those numbers per call — but it
persists them through ``token_usage_service``, which a pod does not have (no
``ec_db_mgr``), and it returns early when that service is missing. So the
numbers exist and are then dropped.

This is the smallest thing that keeps them: a cumulative counter updated where
the cost is computed, plus a snapshot/delta pair so a caller can measure a
window without owning the tracker.

Deliberately global and cumulative rather than scoped: ``cn_serve`` runs one
work item at a time, so a delta across a turn is that turn's usage. **If a pod
ever runs turns concurrently, this must become contextvar-scoped first** — a
delta would otherwise charge one turn for another turn's tokens, and cost
attribution that is quietly wrong is worse than none.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

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


_totals = UsageTotals()


def record_usage_sample(input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    """Add one call's usage. Never raises — accounting must not break a run."""
    global _totals
    try:
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
    """Cumulative usage so far. Subtract two snapshots to measure a window."""
    with _lock:
        return _totals


def reset() -> None:
    """Test helper — drop the counters."""
    global _totals
    with _lock:
        _totals = UsageTotals()
