"""Pod sizes and what they cost — shown at the point of decision.

A pod is a recurring charge, and `always_on` means it is charged whether or not
anybody talks to the agent. The UI must say so *before* the toggle flips, which
means the client needs a price without a round-trip.

The rates below reproduce the one figure the fleet design states outright —
2 vCPU / 4 GiB always-on is about ¥321/month::

    (2 * 0.12 + 4 * 0.05) * 730 = ¥321.2

so they are the TKE Serverless per-core-hour and per-GiB-hour rates that figure
was computed from. They are a **client-side estimate for a form**, not billing:
real cost is what the server charges, and per-turn spend is already recorded on
`turns.cost_usd`. If the two ever disagree, the server is right.

TypeScript twin: ``gui_v2/src/types/domain/pod.ts``.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# CNY, TKE Serverless. See the derivation above before changing either.
CPU_CORE_HOUR_CNY = 0.12
MEMORY_GIB_HOUR_CNY = 0.05
HOURS_PER_MONTH = 730

LIFECYCLE_VALUES = ("always_on", "on_demand")
DEFAULT_LIFECYCLE = "always_on"
DEFAULT_IDLE_SHUTDOWN_MINUTES = 15

# Sizes the customer picks from. Concurrency is the pod's advertised
# max_concurrent_tasks: turns are LLM-latency-bound, so this is I/O concurrency
# rather than cores, but a bigger pod still holds more of them before it starts
# swapping context.
POD_SIZES: List[Dict] = [
    {"id": "small", "cpu": 1, "memory_gb": 2, "concurrency": 8},
    {"id": "standard", "cpu": 2, "memory_gb": 4, "concurrency": 16},
    {"id": "large", "cpu": 4, "memory_gb": 8, "concurrency": 32},
    {"id": "xlarge", "cpu": 8, "memory_gb": 16, "concurrency": 64},
]


def monthly_cost_cny(cpu: float, memory_gb: float) -> float:
    """What one always-on replica of this size costs per month."""
    hourly = (float(cpu or 0) * CPU_CORE_HOUR_CNY
              + float(memory_gb or 0) * MEMORY_GIB_HOUR_CNY)
    return round(hourly * HOURS_PER_MONTH, 2)


def hourly_cost_cny(cpu: float, memory_gb: float) -> float:
    """What one replica costs per hour — the on-demand unit."""
    return round(float(cpu or 0) * CPU_CORE_HOUR_CNY
                 + float(memory_gb or 0) * MEMORY_GIB_HOUR_CNY, 4)


def size_by_id(size_id: str) -> Optional[Dict]:
    for size in POD_SIZES:
        if size["id"] == size_id:
            return dict(size)
    return None


def normalize_lifecycle(value) -> str:
    text = str(value or "").strip().lower()
    return text if text in LIFECYCLE_VALUES else DEFAULT_LIFECYCLE


def estimate_pod_cost(
    cpu: float,
    memory_gb: float,
    *,
    lifecycle: str = DEFAULT_LIFECYCLE,
    replicas: int = 1,
) -> Dict:
    """Cost of a pod configuration, with the honesty the form needs.

    An ``on_demand`` pod has no predictable monthly figure — that is the point
    of it — so the monthly number is reported as the ceiling it would reach if
    it never went idle, flagged as a maximum rather than an estimate.
    """
    replicas = max(1, int(replicas or 1))
    lifecycle = normalize_lifecycle(lifecycle)
    hourly = hourly_cost_cny(cpu, memory_gb) * replicas
    monthly = monthly_cost_cny(cpu, memory_gb) * replicas
    return {
        "lifecycle": lifecycle,
        "replicas": replicas,
        "hourly_cny": round(hourly, 4),
        "monthly_cny": round(monthly, 2),
        "monthly_is_ceiling": lifecycle == "on_demand",
        "currency": "CNY",
    }
