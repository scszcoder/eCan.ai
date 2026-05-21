"""Feige multi-tab pool (Phase 1 — scaffolding only).

Background
----------
Up through 2026-05-19 every Feige operation (sidebar scrape, typing,
customer switch) shared a single Chrome tab + a single process-global
typing-lock.  Under a 20-customer flood that serializes ~10s of typing
per customer → tail latency 200-280s, well past Feige's 30-second
red-flag deadline.

The multi-tab refactor splits work across a pool of Chrome tabs:

* **Monitor tab** (1, dedicated) — EventMonitor polling + PreDispatch's
  sidebar/thread scrape.  Never types, so its CDP eval pipe is always
  free for read-only work.
* **Typing tabs** (N, pool) — each pinned to a specific customer while
  delivering that customer's reply, then released back to the pool.
  Each tab has its own typing-lock; multiple tabs type in parallel.

This module is the **registry**.  It holds the singleton pool, exposes
allocate/release/lookup helpers, and is consulted by:

* ``dom_assets.resolve_feige_tab_target_id`` — routes a customer-keyed
  request to that customer's assigned typing tab (or to the monitor
  tab as fallback when no typing tab is assigned).
* ``extension_tools_service._evaluate_feige_js`` — accepts an optional
  ``customer_key`` and asks the pool which target_id to evaluate against.
* ``runner._do_guarded_direct_delivery`` — allocates a typing tab from
  the pool before invoking ``feige_send_message`` (Phase 3 work).

Phase 1 contract
----------------
The pool starts EMPTY: ``monitor_tab_id`` is unset until
``ensure_feige_tab_focused`` discovers the Feige tab and calls
``designate_monitor()``.  ``typing_tabs`` stays empty until Phase 2
opens them.  Allocation always returns ``None`` (no typing tabs to
allocate), so every caller falls back to the monitor tab — which is
exactly today's single-tab behaviour.

Result: Phase 1 ships with **zero functional change**.  We only add the
plumbing.  Phase 2 will populate ``typing_tabs``; Phase 3 will route
typing through them.

Thread / loop safety
--------------------
Reads (``get_monitor``, ``get_typing_tab_for_customer``) are
lock-protected so callers from any thread / loop see a consistent
snapshot.  Writes (``designate_monitor``, ``register_typing_tab``,
``allocate_for_typing``, ``release``) hold the same ``threading.Lock``
because the pool is accessed from the runner background thread, the
GUI thread, and the agent event loop interchangeably.

A separate ``asyncio.Lock`` is intentionally *not* used here because
the pool is consulted from sync and async contexts; the operations
are O(1) dict lookups and don't ``await`` anything.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


# ── data ──────────────────────────────────────────────────────────────


@dataclass
class TypingTabState:
    """Per-tab state for one typing-pool entry.

    The ``in_use`` flag is the per-tab exclusion mechanism in Phase 3:
    while ``in_use=True`` no other ``allocate_for_typing`` call can pick
    this tab.  Pool methods are atomic under the singleton's lock so
    concurrent allocators can't race on this flag.

    ``created_by_pool`` tells the shutdown cleanup path which tabs we
    opened (and may close) vs. user-opened tabs (leave alone).

    Phase 5 (2026-05-21): ``cdp_client`` + ``cdp_session_id`` hold this
    tab's DEDICATED CDP WebSocket.  When typing operations are routed
    to a pool tab, they bypass the shared ``browser_session._cdp_client_root``
    (which serializes ALL CDP messages through one WebSocket → the
    bottleneck that defeated parallelism at TAB_COUNT=6) and use this
    dedicated client instead — N tabs = N WebSockets = true parallelism.
    """

    target_id: str
    focused_customer: Optional[str] = None
    in_use: bool = False
    last_used_ts: float = 0.0
    health_ok: bool = True
    last_health_check_ts: float = 0.0
    # Phase 2: True for tabs eCan opened via Target.createTarget; False
    # for tabs the user/operator already had open at startup (which we
    # discovered as monitor candidates but happened to also be Feige).
    created_by_pool: bool = False
    # Phase 5: dedicated CDP client + attached session.  None when the
    # lifecycle hasn't wired them up yet (e.g., a tab registered manually
    # without going through ``tab_lifecycle.open_typing_tab``).  When
    # both are present, ``extension_tools_service._evaluate_js`` uses
    # them directly instead of routing through the shared CDP transport.
    cdp_client: Optional[Any] = None
    cdp_session_id: Optional[str] = None
    # Phase 5 Option A (2026-05-21): the dedicated thread + asyncio loop
    # hosting this tab's CDP client.  Created in
    # ``tab_lifecycle._spawn_dedicated_cdp_runtime`` so the client's
    # message-handler task lives on a loop that's NOT contending with
    # eCan's agent loop (which is busy with LangGraph + MCP + model
    # APIs + browser-use's own CDP).  Without this isolation, only 1 of
    # N dedicated clients actually received responses; with this, all N
    # respond in parallel as expected.
    cdp_thread: Optional[Any] = None
    cdp_loop: Optional[Any] = None


class FeigeTabPool:
    """Process-wide singleton.  Owns the monitor tab + typing-tab pool."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._monitor_tab_id: str = ""
        self._typing_tabs: dict[str, TypingTabState] = {}
        # Soft sticky: which typing tab last handled customer X.  Used by
        # ``get_typing_tab_for_customer`` to prefer reuse before falling
        # back to LRU pick.
        self._customer_to_tab: dict[str, str] = {}
        # Phase 2: dispatch-once flag for background pool initialization.
        # ``try_dispatch_initial_population`` returns True only once per
        # process — the caller schedules ``tab_lifecycle.initialize_typing_pool``
        # only when it gets True.  Subsequent calls are no-ops.
        self._initial_population_dispatched: bool = False

    # ── monitor tab ──

    def designate_monitor(self, target_id: str) -> None:
        """Mark a tab as THE monitor.  Idempotent; safe to call repeatedly.

        ``ensure_feige_tab_focused`` calls this whenever it resolves the
        Feige tab.  Phase 1: the monitor stays the same tab forever.
        Phase 4 (polish) will handle promotion when the monitor crashes.
        """
        if not target_id:
            return
        target_id = str(target_id)
        with self._lock:
            if self._monitor_tab_id != target_id:
                self._monitor_tab_id = target_id

    def get_monitor(self) -> str:
        """Return the monitor tab's ``target_id`` or empty string if unset."""
        with self._lock:
            return self._monitor_tab_id

    # ── typing tabs ──

    def register_typing_tab(
        self,
        target_id: str,
        *,
        created_by_pool: bool = False,
        cdp_client: Optional[Any] = None,
        cdp_session_id: Optional[str] = None,
        cdp_thread: Optional[Any] = None,
        cdp_loop: Optional[Any] = None,
    ) -> None:
        """Add a tab to the typing pool (Phase 2 entry point).

        ``created_by_pool`` is True when ``tab_lifecycle.open_typing_tab``
        opened this tab — the shutdown cleanup path closes only these.

        Phase 5: ``cdp_client`` + ``cdp_session_id`` carry this tab's
        dedicated WebSocket and attached session.  Provided by
        ``tab_lifecycle.open_typing_tab`` when it creates the tab; left
        as ``None`` for tabs registered without going through that path
        (which then fall through to the shared CDP at typing time).
        """
        if not target_id:
            return
        target_id = str(target_id)
        with self._lock:
            if target_id == self._monitor_tab_id:
                return  # monitor and typing pool are disjoint
            if target_id not in self._typing_tabs:
                self._typing_tabs[target_id] = TypingTabState(
                    target_id=target_id,
                    created_by_pool=bool(created_by_pool),
                    cdp_client=cdp_client,
                    cdp_session_id=cdp_session_id,
                    cdp_thread=cdp_thread,
                    cdp_loop=cdp_loop,
                )

    def get_typing_tab_state(self, target_id: str) -> Optional[TypingTabState]:
        """Return the ``TypingTabState`` for ``target_id``, or None.

        Phase 5: consulted by ``extension_tools_service._evaluate_js``
        to route CDP calls through a pool tab's dedicated client when
        ``target_id`` matches a registered pool tab.
        """
        if not target_id:
            return None
        with self._lock:
            return self._typing_tabs.get(str(target_id))

    def get_typing_tab_count(self) -> int:
        """Return the current number of typing tabs registered."""
        with self._lock:
            return len(self._typing_tabs)

    def list_pool_created_target_ids(self) -> list[str]:
        """Return target_ids of typing tabs we opened (for shutdown cleanup)."""
        with self._lock:
            return [tid for tid, s in self._typing_tabs.items() if s.created_by_pool]

    def try_dispatch_initial_population(self) -> bool:
        """One-shot dispatch flag.  Returns True only the first time.

        ``dom_assets.ensure_feige_tab_focused`` (and the resolver fallback)
        call this after designating the monitor tab.  Only the first caller
        gets True and schedules ``tab_lifecycle.initialize_typing_pool``;
        every subsequent caller gets False and skips.
        """
        with self._lock:
            if self._initial_population_dispatched:
                return False
            self._initial_population_dispatched = True
            return True

    def mark_tab_health(self, target_id: str, *, ok: bool) -> None:
        """Record a health-check result for ``target_id``."""
        if not target_id:
            return
        with self._lock:
            tab = self._typing_tabs.get(str(target_id))
            if tab is None:
                return
            tab.health_ok = bool(ok)
            tab.last_health_check_ts = time.time()

    def unregister_typing_tab(self, target_id: str) -> None:
        """Remove a tab from the typing pool (Phase 2/4 entry point)."""
        if not target_id:
            return
        target_id = str(target_id)
        with self._lock:
            self._typing_tabs.pop(target_id, None)
            # Clear any sticky references to this tab
            for cust, tid in list(self._customer_to_tab.items()):
                if tid == target_id:
                    del self._customer_to_tab[cust]

    def get_typing_tab_for_customer(self, customer_key: str) -> Optional[str]:
        """Return the typing-tab ``target_id`` currently routing ``customer_key``.

        Phase 1: pool is empty, always returns ``None``.  Phase 3 wires
        the real allocation logic below.
        """
        if not customer_key:
            return None
        with self._lock:
            tid = self._customer_to_tab.get(customer_key)
            if tid and tid in self._typing_tabs:
                return tid
            return None

    def allocate_for_typing(self, customer_key: str) -> Optional[TypingTabState]:
        """Pick (and mark in_use) a typing tab for ``customer_key``.

        Phase 1: pool is empty → always returns ``None`` (caller falls
        back to monitor tab, which is today's behaviour).

        Phase 3 algorithm (when pool has entries):
          1. If ``customer_to_tab[customer_key]`` points to a free tab,
             reuse it (sticky — skip ``feige_open_session`` cost).
          2. Else pick any free tab — LRU first, prefer one already
             focused on this customer (rare).
          3. Else return ``None`` (caller decides: fall back to monitor,
             or queue and wait).
        """
        if not customer_key:
            return None
        with self._lock:
            if not self._typing_tabs:
                return None
            # Sticky: if customer's previous tab is free AND healthy, reuse it
            # — skips the feige_open_session sidebar-click cost.
            preferred_tid = self._customer_to_tab.get(customer_key)
            if preferred_tid:
                tab = self._typing_tabs.get(preferred_tid)
                if tab is not None and not tab.in_use and tab.health_ok:
                    tab.in_use = True
                    tab.last_used_ts = time.time()
                    return tab
            # LRU free pick — skip unhealthy tabs entirely.  Health is set
            # by ``mark_tab_health`` (called from ``tab_lifecycle``'s
            # health-check sweep + on send failures).
            free = [t for t in self._typing_tabs.values() if not t.in_use and t.health_ok]
            if not free:
                return None
            free.sort(key=lambda t: t.last_used_ts)
            chosen = free[0]
            chosen.in_use = True
            chosen.last_used_ts = time.time()
            self._customer_to_tab[customer_key] = chosen.target_id
            chosen.focused_customer = customer_key
            return chosen

    def release(
        self,
        target_id: str,
        *,
        succeeded: bool = True,
        customer_key: str = "",
    ) -> None:
        """Return a typing tab to the pool.

        ``succeeded`` controls the sticky-assignment retention: a
        successful delivery keeps the customer→tab mapping (subsequent
        replies skip the open_session cost), a failed delivery clears
        it so the next attempt can pick a fresh tab.
        """
        if not target_id:
            return
        target_id = str(target_id)
        with self._lock:
            tab = self._typing_tabs.get(target_id)
            if tab is None:
                return
            tab.in_use = False
            tab.last_used_ts = time.time()
            if not succeeded and customer_key:
                # Drop sticky mapping so retry tries a different tab
                if self._customer_to_tab.get(customer_key) == target_id:
                    del self._customer_to_tab[customer_key]

    # ── diagnostics ──

    def snapshot(self) -> dict:
        """Return a JSON-safe snapshot of the pool for logging / IPC."""
        with self._lock:
            return {
                "monitor_tab_id": self._monitor_tab_id,
                "typing_tab_count": len(self._typing_tabs),
                "typing_tabs": {
                    tid: {
                        "focused_customer": s.focused_customer,
                        "in_use": s.in_use,
                        "last_used_ts": s.last_used_ts,
                        "has_dedicated_cdp": s.cdp_client is not None
                        and bool(s.cdp_session_id),
                    }
                    for tid, s in self._typing_tabs.items()
                },
                "customer_to_tab": dict(self._customer_to_tab),
            }


# ── singleton access ──────────────────────────────────────────────────


_POOL_SINGLETON: Optional[FeigeTabPool] = None
_POOL_INIT_LOCK = threading.Lock()


def get_pool() -> FeigeTabPool:
    """Return the process-wide ``FeigeTabPool`` singleton (creating it lazily)."""
    global _POOL_SINGLETON
    if _POOL_SINGLETON is None:
        with _POOL_INIT_LOCK:
            if _POOL_SINGLETON is None:
                _POOL_SINGLETON = FeigeTabPool()
    return _POOL_SINGLETON


__all__ = [
    "TypingTabState",
    "FeigeTabPool",
    "get_pool",
]
