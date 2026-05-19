"""Per-node tunables for Feige chat hot-path constants.

Background
----------
Commit ``80d50eb36`` "fix bug of product listing" (Liu Qiang, 2026-05-11)
introduced more aggressive timeout + retry constants to handle transient
CDP disconnects during product-listing scrapes.  The retry logic itself
is correct for that scenario — but the same constants were applied to
*every* browser-automation node, including the latency-sensitive Feige
chat dispatch path.  On sustained 1-on-8 customer load this converted
"fail-fast and let the next dom-tick retry" into "hold the line for
30-100 s and stall every other concurrent customer behind one slow
turn", reproducing the 3-min worst-case latencies the customer reported
on the 2026-05-18 flood test.

Design
------
Each tunable is resolved in this precedence order:

1. **Per-node override** — ``state["metadata"]["browser_auto_overrides"]
   [<name>]``.  Set on the langgraph state by the skill author (in the
   node's params, propagated by ``build_node`` into ``state.metadata``
   at node entry) so a chat skill can keep tight timeouts while a
   product-listing skill loosens them.

2. **Global env var** — ``ECAN_<NAME>``.  Operator escape hatch for
   site-wide tuning without code changes.

3. **Hardcoded default** — restored to the v0.9.79 conservative values
   that empirically worked for the customer's flood-tested chat path.
   Product-listing-style skills should override these per-node.

Suggested per-node overrides for slow / batch operations (e.g. a
product-listing scrape skill that needs longer waits for transient
CDP errors):
    state["metadata"]["browser_auto_overrides"] = {
        "HOT_PATH_TOOL_TIMEOUT_S": 25.0,
        "HOT_PATH_DRIFT_RETRY_MAX": 4,
        "FEIGE_SEND_CDP_EVALUATE_TIMEOUT_S": 22.0,
        "BROWSER_AUTO_MAX_RETRIES": 2,
    }
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("eCan")


def _node_override(name: str, state: dict | None) -> Any | None:
    """Return the per-node override value for ``name`` if present, else ``None``."""
    if not state or not isinstance(state, dict):
        return None
    metadata = state.get("metadata")
    if not isinstance(metadata, dict):
        return None
    overrides = metadata.get("browser_auto_overrides")
    if not isinstance(overrides, dict):
        return None
    if name not in overrides:
        return None
    return overrides[name]


def resolve_int(name: str, default: int, state: dict | None = None) -> int:
    """Resolve an int tunable: per-node → env → hardcoded default."""
    override = _node_override(name, state)
    if override is not None:
        try:
            return int(override)
        except (TypeError, ValueError):
            logger.debug(f"[tunables] invalid node override {name}={override!r}, falling back")
    env_val = os.getenv("ECAN_" + name)
    if env_val:
        try:
            return int(env_val)
        except (TypeError, ValueError):
            logger.debug(f"[tunables] invalid env ECAN_{name}={env_val!r}, falling back")
    return default


def resolve_float(name: str, default: float, state: dict | None = None) -> float:
    """Resolve a float tunable: per-node → env → hardcoded default."""
    override = _node_override(name, state)
    if override is not None:
        try:
            return float(override)
        except (TypeError, ValueError):
            logger.debug(f"[tunables] invalid node override {name}={override!r}, falling back")
    env_val = os.getenv("ECAN_" + name)
    if env_val:
        try:
            return float(env_val)
        except (TypeError, ValueError):
            logger.debug(f"[tunables] invalid env ECAN_{name}={env_val!r}, falling back")
    return default


# ── Canonical defaults (restored to v0.9.79 values, 2026-05-18) ────────────
# These are the module-import-time defaults imported by hot_path.py /
# hot_path_v2.py / extension_tools_service.py.  Call resolve_int/float
# above with the same name to honour per-node overrides at use sites.

# Hot-path drift retry: how many times to ATTEMPT feige_send_message
# (1 = just the initial attempt, 2 = one retry, etc.).  The retry kicks
# in only for drift-shaped errors (sidebar reshuffled, "Active customer
# drifted between typing and click") — non-drift failures still abort
# immediately.  v0.9.79 default was 1.  v0.9.80+ used 4.  Bumped to 2
# on 2026-05-18 after the 18:44 + 18:49 flood waves each left exactly
# one customer unanswered with this drift error on their single dispatch
# attempt (客户18 in wave 1, 客户08 in wave 2); the source-msg-id dedup
# then blocked re-dispatch on subsequent browser-event ticks.  One
# absorbing retry within the same dispatch — before the dedup locks the
# msg_id — closes that gap.  Going higher would help marginally but
# costs latency on the success path.
DEFAULT_HOT_PATH_DRIFT_RETRY_MAX: int = 2

# Hot-path tool timeout: outer asyncio.wait_for around every browser-tool
# call from the front-desk hot path.  v0.9.79: 8 s.  v0.9.80: 25 s.
# v0.9.91: 50 s.
DEFAULT_HOT_PATH_TOOL_TIMEOUT_S: float = 8.0

# Inner CDP eval timeout for feige_send_message.  v0.9.79: 15 s.
# v0.9.80: 22 s.  v0.9.91: 45 s.  Re-raised to 30 s on 2026-05-18 after
# the 16:47-16:49 flood test caught 3 customers with 15-s Runtime.evaluate
# timeouts under 20-customer load (overlapping CDP evals on the same
# page push individual evaluate latency past 15 s).  Each timeout then
# triggers the 4-s shared cooldown which cascaded into 5+ additional
# dropped customers.  30 s absorbs page contention without leaving a
# hung renderer holding the queue for a full minute.
DEFAULT_FEIGE_SEND_CDP_EVALUATE_TIMEOUT_S: float = 30.0

# Browser-automation node retry count (build_node.py _MAX_RETRIES).
# v0.9.79: no retry (effectively 0).  v0.9.80+: 2.  The retry itself
# re-executes the entire browser turn (5-15 s) so 0 is conservative;
# bump for product-listing nodes where CDP flakiness is more common.
DEFAULT_BROWSER_AUTO_MAX_RETRIES: int = 0

# Sleep between browser-automation node retries.  v0.9.80+: 2.0 s
# (originally a synchronous time.sleep blocking the worker thread).
# Reduced to 0.5 s for hot-path safety; bump for product-listing.
DEFAULT_BROWSER_AUTO_RETRY_SLEEP_S: float = 0.5


__all__ = [
    "resolve_int",
    "resolve_float",
    "DEFAULT_HOT_PATH_DRIFT_RETRY_MAX",
    "DEFAULT_HOT_PATH_TOOL_TIMEOUT_S",
    "DEFAULT_FEIGE_SEND_CDP_EVALUATE_TIMEOUT_S",
    "DEFAULT_BROWSER_AUTO_MAX_RETRIES",
    "DEFAULT_BROWSER_AUTO_RETRY_SLEEP_S",
]
