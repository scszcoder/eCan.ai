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


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return None


def resolve_bool(name: str, default: bool, state: dict | None = None) -> bool:
    """Resolve a bool tunable: per-node → env → hardcoded default.

    Empty string in the per-node override is treated as "not set" so the
    UI's blank checkbox falls through to env / default.
    """
    override = _node_override(name, state)
    if override is not None and override != "":
        coerced = _coerce_bool(override)
        if coerced is not None:
            return coerced
        logger.debug(f"[tunables] invalid node override {name}={override!r}, falling back")
    env_val = os.getenv("ECAN_" + name)
    if env_val is not None and env_val != "":
        coerced = _coerce_bool(env_val)
        if coerced is not None:
            return coerced
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

# ── 2026-05-19 Fix C: PreDispatch firing-rate controls (v0.9.79 parity) ──
# v0.9.79 didn't have either of the load-shedding mechanisms below.
# Commits 9299db8eb ("fix flood test", REARM) and 5d4486717 ("fix rt
# chat timing", B1 force-emit) added them in v0.9.91 to chase deferred
# customers; under 8+ customer flood the combined effect multiplies
# PreDispatch invocation rate and amplifies the duplicate-dispatch
# cascade.  Defaults below restore v0.9.79 behaviour.

# B1 force-emit: when ON, EventMonitor force-emits on every poll while
# the deferred-set (typing-lock-blocked customers) is non-empty.
# v0.9.79: OFF (only emit on real DOM diffs).
DEFAULT_EVENT_MONITOR_B1_FORCE_EMIT: bool = False

# REARM: when ON, _maybe_schedule_self_rearm schedules a detached async
# task to poll typing-lock-stably-clear and re-run PreDispatch (up to
# 12 chained levels) for deferred rows.  v0.9.79 didn't have this code
# path, but turning it OFF together with B1 force-emit stranded
# customers who were deferred during their initial PreDispatch wave
# (no retry trigger anywhere): the 2026-05-19 12:59 local-emulation
# flood test saw 6/20 customers replied to, the remaining 14 deferred
# with reason 'system_message:smart_cs_auto_greeting' (sidebar showed
# greeting, real question only in chat thread) — no DOM diff ever
# fired again because the emulator sidebar text didn't change after
# the initial wave.  REARM is the right safety valve for this: it
# fires ONCE per typing-lock-drain cycle (not per poll like B1), so
# it doesn't inflate PreDispatch invocation rate beyond what's
# actually useful.
#
# 2026-05-19 (revised): DEFAULT switched back to True.  The runaway
# PreDispatch firing rate we attributed to REARM in the earlier
# customer-log analysis was actually driven by B1 force-emit + the
# supersede-on-bot-reply race (now fixed by Fix A).  REARM by itself
# is bounded.
DEFAULT_FRONTDESK_REARM_ENABLED: bool = True

# Direct-delivery bypass on backpressure: when ON (v0.9.79 default),
# `_submit_loop_direct_delivery` returns False once queue depth exceeds
# `_DIRECT_LIVE_CHAT_MAX_ASYNC_QUEUE_DEPTH`, letting the reply fall through
# to target_task.queue.put_nowait (the per-task queue + HOT-PATH-B
# path).  Commit 1d18e4714 "fix stuck." (2026-05-11) removed the
# `return False` and forced every reply into the single direct-delivery
# queue, leading to unbounded backpressure under flood.
#
# 2026-05-19: tried flipping default to False (Option C) to make bypass
# replies queue at direct-delivery instead of falling through to the
# broken per-task-queue path.  Caused CATASTROPHIC regression — 9/20
# customers never dispatched.  Root cause: with bypass=False, the
# direct-delivery worker queue stays non-empty under flood, the typing
# lock is held continuously, PreDispatch's sidebar-only scrape window
# (which requires typing-lock-clear) never opens, and customers whose
# real question is buried in chat-thread (not sidebar preview) get
# starved.  Reverting to True; the bypass drops are the lesser evil
# vs. dispatch-side starvation.
# NOTE: this tunable is currently consulted via the env path only,
# because the direct-delivery worker runs in a thread without the
# LangGraph state in scope.  Wiring it as a true per-node override
# would require routing state into runner.py — left for follow-up.
# Use ECAN_DIRECT_LIVE_CHAT_BYPASS_ON_BACKPRESSURE=0/1 to override.
DEFAULT_DIRECT_LIVE_CHAT_BYPASS_ON_BACKPRESSURE: bool = True

# ── 2026-05-20 Phase 2-4 multi-tab tunables ──────────────────────────
# Size of the Feige typing-tab pool (excludes the dedicated monitor tab).
#
#   0  = single-tab mode (today's behaviour — all typing on monitor)
#   1+ = open this many additional Feige tabs at startup; direct-delivery
#        routes customer replies to them in parallel
#
# Practical sizing:
#   * 2-3 tabs ≈ 2-3x throughput on a 20-customer flood, fits well within
#     Chrome's per-tab memory budget (~80-150 MB each)
#   * 6-8 tabs ≈ near-linear parallelism but heavier on RAM; recommended
#     only on dev machines with 16+ GB
#
# PROD-VERIFY: confirm Feige's server doesn't rate-limit per-session
# parallel sends.  If it does, raising this beyond N=2 won't help
# (the bottleneck moves from CDP to server).  Run the "Test Feige Tabs
# (Concurrent Send)" diagnostic to check.
#
# Ships at 0 so Phase 2-4 code lands with NO behaviour change.  Flip
# via env (``ECAN_FEIGE_TYPING_TAB_COUNT=4``) or per-node override.
DEFAULT_FEIGE_TYPING_TAB_COUNT: int = 0

# Background health-check sweep interval (seconds).
#   0 = disabled (no periodic sweep — failed tabs detected on next use)
#   30 = balanced default for production
#
# Disabled by default in Phase 2 to keep the change footprint minimal.
DEFAULT_FEIGE_TYPING_TAB_HEALTH_SWEEP_S: float = 0.0

# ── 2026-05-21 Phase 3.5 — placeholder-timer guardrail ───────────────
# Feige (and similar chat platforms) raise a "未回复" red flag against
# the store's performance score when a customer message goes unanswered
# beyond a deadline (Feige: 30 seconds).  Under heavy flood the tail
# customers can wait 60-200+ seconds for the first real Q&A reply.
#
# Guardrail: after PreDispatch dispatches a customer's question to the
# Q&A bot, arm a timer.  If the real reply hasn't been typed within
# ``FEIGE_PLACEHOLDER_TIMEOUT_S`` seconds, type a brief stand-by message
# like "您好，稍等一下哦~" so the red-flag clock resets.  Re-arm up to
# ``FEIGE_PLACEHOLDER_MAX`` times if the real reply is still delayed.
#
# Defaults: disabled (timeout=0) — operator opts in by setting
#   ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S=10
#
# Sizing for the 30s Feige red-flag deadline:
#   wall-clock from customer-message-arrival to placeholder-typed =
#     PreDispatch_latency (3-15s under flood) + timeout_s (configured)
#     + sweep_interval_s (≤2s) + claim_to_type_latency (~2-4s)
#
#   To stay under 30s consistently, timeout_s should be 8-12.
#   Earlier 20s default (and user env=20) frequently overshot the
#   deadline under load (observed 2026-05-20 22:52 trace: placeholders
#   for 客户02/06/20 etc. would have fired well past 30s).  Recommend
#   ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S=10 in env.
#
# Placeholders go through the SAME direct-delivery worker queue as
# real replies, so they get pool-tab routing automatically (won't
# fight for typing-lock).  Each placeholder uses a different
# pre-canned phrase to avoid the dedup cache suppressing the
# second/third attempt as a near-duplicate.
DEFAULT_FEIGE_PLACEHOLDER_TIMEOUT_S: float = 0.0  # 0 = disabled
# Max placeholders typed during a single in-flight turn (one customer
# question → Q&A bot still processing).  After this count is reached
# the timer entry is removed and no further "稍等"/"再稍等" messages
# fire for that turn.  Default 2 (was 3 pre-mt016) on customer request:
# 3 was perceived as too noisy when the bot took 60-90s.  Two
# placeholders ("您好，稍等一下哦~" then "再稍等一下，马上回复") refresh
# Feige's 30s red-flag clock TWICE before going quiet again.
# Tune via ECAN_FEIGE_MAX_PLACEHOLDERS_PER_INFLIGHT.
DEFAULT_FEIGE_MAX_PLACEHOLDERS_PER_INFLIGHT: int = 2
# Legacy alias — kept for backward compat with code that still imports
# DEFAULT_FEIGE_PLACEHOLDER_MAX.  New code should reference
# DEFAULT_FEIGE_MAX_PLACEHOLDERS_PER_INFLIGHT.  The env var
# ECAN_FEIGE_PLACEHOLDER_MAX is also still honoured but the new
# ECAN_FEIGE_MAX_PLACEHOLDERS_PER_INFLIGHT takes precedence when both
# are set (see dom_assets.py sweeper-start).
DEFAULT_FEIGE_PLACEHOLDER_MAX: int = DEFAULT_FEIGE_MAX_PLACEHOLDERS_PER_INFLIGHT
# Rearm interval — how long between placeholder #N and the deadline
# for #N+1.  Reduced from 20→15 on 2026-05-20 so even if customer
# misses the first placeholder window, the second arrives well within
# Feige's red-flag refresh cycle.
DEFAULT_FEIGE_PLACEHOLDER_REARM_S: float = 15.0
# How often the background sweeper checks for expired timers.  Reduced
# from 2.0→1.0 on 2026-05-20 so the placeholder fires within at most
# 1s of its scheduled deadline (was up to 2s of slop).
DEFAULT_FEIGE_PLACEHOLDER_SWEEP_INTERVAL_S: float = 1.0

# mt050O (2026-05-28): per-customer placeholder ceiling, separate from
# DEFAULT_FEIGE_MAX_PLACEHOLDERS_PER_INFLIGHT.  Prior to mt050O the
# claim_expired sweeper reused the per-inflight cap (2) as a hard limit
# on how many placeholders any single customer could see in a rolling
# 90-second window.  Live trace 2026-05-28 08:52-09:21: customer 肽斯特
# hit the cap after the first two placeholders fired, and the next
# 90 s of slow turns had their registry entries silently dropped by
# claim_expired (no log) — 29 of 39 turns >10s saw NO placeholder.
#
# The 2026-05-21 "Fix B" comment that introduced the cap was defending
# against orphan-timer scenarios where a phantom dispatch + the real
# turn both armed timers.  Those scenarios are now closed at the
# source by mt050K (broad-cancel placeholders on supersede) and
# mt050N-#1a (proactive identity-key clear on supersede), so the cap
# can be relaxed safely.
#
# Default 12 = 6 turns × per-inflight cap (2).  Operators can tune
# down with ECAN_FEIGE_PLACEHOLDER_CAP_PER_WINDOW if spam recurs, or
# disable entirely with 0 (= no per-customer-window ceiling).
DEFAULT_FEIGE_PLACEHOLDER_CAP_PER_WINDOW: int = 12


# ── 2026-05-25 mt044 — tab-focus contention tunables ────────────────
# Six knobs covering the typing-path tab-focus failures observed in
# the 2026-05-25 12:36-14:58 live customer trace.  All defaults aim
# to fix the observed failure modes; set to the "off" value to
# revert any individual fix to legacy behaviour.

# mt044A: cache the chosen Feige tab target_id per browser session
# so a flood of dispatches doesn't re-run the multi-candidate row
# probe (which acquires the session CDP lock once per candidate).
#   * 10.0 (default) — 10-second TTL.  Re-probes only when cache
#     is stale (URL drifted, tab closed, etc.).
#   * 0.0 — disabled (always probe; legacy behaviour).
DEFAULT_FEIGE_TAB_RESOLVE_CACHE_TTL_S: float = 10.0

# mt044B: run the multi-candidate row probe in parallel via
# asyncio.gather.  Requires mt044C per-target lock to avoid
# serializing on the session-wide lock.
#   * True (default) — parallel; total time = max(per-probe).
#   * False — sequential (legacy); total time = sum(per-probe).
# Disable if Chrome shows signs of distress under parallel probes
# (very rare; per-target locks should prevent thrash).
DEFAULT_FEIGE_PROBE_PARALLEL: bool = True

# mt044D: per-probe Runtime.evaluate timeout (existing constant
# _CDP_OPERATION_PROBE_TIMEOUT_S = 2.0).  Raised to give Chrome
# headroom under load.  Per-probe, not for the whole probe set.
#   * 5.0 (default) — was 2.0
#   * lower for emulator / faster Chrome
DEFAULT_FEIGE_PROBE_TIMEOUT_S: float = 5.0

# mt044D: outer wait_for around _resolve_feige_tab_target_id in
# runner.py.  Was 2.0s — too tight when N candidate probes run
# sequentially or under lock contention.
#   * 8.0 (default) — was 2.0
DEFAULT_FEIGE_TAB_RESOLVE_TIMEOUT_S: float = 8.0

# mt044E: cap concurrent typing CDP operations per browser session
# to keep Chrome's main thread from thrashing.  Each typing op
# consumes the main thread for the Runtime.evaluate window
# (typically 1-3s).  More parallel typing = more main-thread
# contention = focus calls on OTHER tabs time out.
#   * 3 (default) — three customers can type in parallel; the rest
#     queue.  Sized for typical 3-10 concurrent customer chats.
#   * 0 — unlimited (legacy behaviour; risk of Chrome thrashing).
#   * 1 — fully serial typing (slowest but most predictable).
DEFAULT_FEIGE_TYPING_CONCURRENCY: int = 3

# mt044F: per-customer scrape cooldown.  Suppresses
# scrape_latest_customer_bubble for the same customer when called
# again within this window.  Returns the previous scrape's cached
# result instead.  Stops dom_observed bursts (multiple events for
# the same customer within ~1s) from triggering N CDP evals when
# only one is meaningful.
#   * 1.0 (default) — re-scrape at most once per second per customer.
#   * 0.0 — disabled (every call hits CDP; legacy behaviour).
#   * Higher (e.g. 3.0) for low-traffic stores where freshness is
#     less critical than CDP load.
DEFAULT_FEIGE_SCRAPE_COOLDOWN_S: float = 1.0


__all__ = [
    "resolve_int",
    "resolve_float",
    "resolve_bool",
    "DEFAULT_HOT_PATH_DRIFT_RETRY_MAX",
    "DEFAULT_HOT_PATH_TOOL_TIMEOUT_S",
    "DEFAULT_FEIGE_SEND_CDP_EVALUATE_TIMEOUT_S",
    "DEFAULT_BROWSER_AUTO_MAX_RETRIES",
    "DEFAULT_BROWSER_AUTO_RETRY_SLEEP_S",
    "DEFAULT_EVENT_MONITOR_B1_FORCE_EMIT",
    "DEFAULT_FRONTDESK_REARM_ENABLED",
    "DEFAULT_DIRECT_LIVE_CHAT_BYPASS_ON_BACKPRESSURE",
    "DEFAULT_FEIGE_TYPING_TAB_COUNT",
    "DEFAULT_FEIGE_TYPING_TAB_HEALTH_SWEEP_S",
    "DEFAULT_FEIGE_PLACEHOLDER_TIMEOUT_S",
    "DEFAULT_FEIGE_MAX_PLACEHOLDERS_PER_INFLIGHT",
    "DEFAULT_FEIGE_PLACEHOLDER_MAX",
    "DEFAULT_FEIGE_PLACEHOLDER_CAP_PER_WINDOW",
    "DEFAULT_FEIGE_PLACEHOLDER_REARM_S",
    "DEFAULT_FEIGE_PLACEHOLDER_SWEEP_INTERVAL_S",
    # mt044
    "DEFAULT_FEIGE_TAB_RESOLVE_CACHE_TTL_S",
    "DEFAULT_FEIGE_PROBE_PARALLEL",
    "DEFAULT_FEIGE_PROBE_TIMEOUT_S",
    "DEFAULT_FEIGE_TAB_RESOLVE_TIMEOUT_S",
    "DEFAULT_FEIGE_TYPING_CONCURRENCY",
    "DEFAULT_FEIGE_SCRAPE_COOLDOWN_S",
]
