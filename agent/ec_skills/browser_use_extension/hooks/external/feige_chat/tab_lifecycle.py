"""Lifecycle helpers for Feige typing tabs (Phase 2 + 4 work).

Responsibilities
----------------
* **Open** new Chrome tabs via CDP ``Target.createTarget`` and navigate
  them to the monitor tab's Feige URL.
* **Wait** for the new tab's DOM to be ready enough to type into
  (sidebar present, customer rows loaded).
* **Register** the new tab in the singleton ``FeigeTabPool``.
* **Health-check** existing typing tabs and mark stale/dead ones.
* **Close** pool-created tabs on shutdown.

Design notes
------------
We deliberately use the same ``cdp_use.CDPClient`` connection that
``event_monitor.py:_get_monitor_cdp`` uses, NOT browser-use's
``BrowserSession`` machinery.  Reasons:

* Independent of browser-use's task lifecycle — the pool's tabs live
  beyond any single agent task.
* Lower-level control: ``Target.createTarget`` returns the new
  targetId directly; we don't need to fight browser-use's "active tab"
  abstraction.
* Multi-tab BrowserSession support in browser-use is patchy.  Keeping
  our own CDP connection avoids stepping on its state.

The CDP URL is discovered from the same source EventMonitor uses
(``session.cdp_url`` or ``session.browser_profile.cdp_url``).  We
cache the client on the pool so subsequent operations reuse it.

Confirmed-stable Feige selectors (2026-05-21 live diagnostic)
-------------------------------------------------------------
These are the selectors we'll rely on across the multi-tab refactor.
Counts shown in parentheses are typical occurrences per active chat
tab.  All confirmed present on the customer's real Feige install.

* ``#topbar-left-info`` — stable HTML id, holds the focused customer's
  display name as visible text.  Authoritative signal for "which
  customer is this tab currently showing".  Survives Feige's CSS-in-JS
  hash rotations (it's a real HTML id, not a hashed class).
* ``#chantListScrollArea`` — sidebar scroll root.  Present on the chat
  view even when there are zero conversations.
* ``[data-qa-id="qa-conversation-chat-item"]`` (1 per row) — sidebar
  customer rows.  Use ``data-btm-id`` ending (``.current`` / ``.recent``
  / ``.systemConv``) to filter by sub-tab.
* ``[data-qa-id="qa-send-message-textarea"]`` (1) — typing input.
* ``[data-qa-id="qa-send-message-button"]`` (1) — send button.
* ``[data-qa-id="qa-active-chat-tab"]`` (1) — "当前会话" sub-tab button.
* ``[data-qa-id="qa-last-chat-tab"]`` (1) — "最近联系" sub-tab button.
* ``.MP1bk3ccfHC9V2SnPCGD`` — CSS-in-JS hashed class on the customer-name
  span inside a sidebar row; also has a ``title`` attribute matching the
  full name.  This hash MAY rotate on Feige's next deploy; the
  ``.Jv6FtqUv5VoYARd2pp4y`` and ``[title]`` fallbacks (already in
  production) cover that case.

Adapting to other customer platforms
------------------------------------
This module is currently Feige-specific in two places:

* ``DEFAULT_FEIGE_URL_FRAGMENT`` — substring used to confirm a target
  is a Feige page after navigation.  For a different chat platform,
  replace with that platform's URL fragment.
* ``_FEIGE_READY_JS`` — JS that resolves when the page is hydrated
  enough to type.  Each platform has its own DOM-ready signals; replace
  with the equivalent for your platform.

When we generalize this for the next customer case (see
``MULTITAB_DESIGN.md``), both of these will become configuration on an
"external hook bundle" descriptor object rather than module-level
constants.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
from typing import Any, Optional

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    tab_pool as _tab_pool,
)

logger = logging.getLogger("eCan")


# PROD-VERIFIED 2026-05-21: Live diagnostic against customer's real
# Feige showed all open tabs at https://im.jinritemai.com/pc_seller_v2/
# main/workspace — substring match works.  If a future customer site
# uses a different domain, this becomes a per-bundle config.
DEFAULT_FEIGE_URL_FRAGMENT = "im.jinritemai.com"

# Default per-tab wait budget for navigation + sidebar readiness.
# PROD-VERIFIED 2026-05-21: real Feige loads in ~3-5s (full SPA boot
# including auth + initial websocket connect).  Emulator loads in
# ~200ms.  8s default covers both with margin.
_DEFAULT_NAV_READY_TIMEOUT_S = 8.0

# How often (seconds) the background health-check sweep should run.
# 0 = disabled (Phase 2 ship state — no background task spawned).
_DEFAULT_HEALTH_CHECK_INTERVAL_S = 30.0

# JS that resolves once a new Feige tab is hydrated enough to interact with.
# We accept ANY of these signals (whichever shows up first):
#   1. The chat-list scroll root ``#chantListScrollArea`` (always present
#      on the IM SPA's chat view even when no conversations are listed).
#   2. The header anchor ``#topbar-left-info`` (present when seller has
#      a chat focused).
#   3. Sidebar rows ``[data-qa-id="qa-conversation-chat-item"]`` (present
#      when there are active conversations).
#   4. ``document.readyState === 'complete'`` — last-ditch fallback so
#      tabs that load onto views without conversations still progress.
#
# This is more permissive than the earlier draft (which required
# sidebar rows).  Live data 2026-05-21 showed real Feige's seller
# workspace can be 'complete' with 0 sidebar rows for long stretches
# — that's a legitimate ready state, not a failure.
#
# PROD-VERIFIED 2026-05-21: live diagnostic on customer machine
# confirmed #chantListScrollArea + #topbar-left-info + qa-conversation-
# chat-item are all present on real Feige's seller workspace.  The
# document.readyState fallback handles the workspace-dashboard view
# (no chat anchors but page is loaded — legitimate ready state).
_FEIGE_READY_JS = r"""
(function() {
  return new Promise(function(resolve) {
    var deadline = Date.now() + AWAIT_READY_UNTIL_MS;
    function tick() {
      try {
        var sidebar_root = document.querySelector('#chantListScrollArea');
        var header = document.querySelector('#topbar-left-info');
        var rows = document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"], .chat-item');
        if (sidebar_root || header || (rows && rows.length > 0)) {
          resolve({
            ok: true,
            rows: rows ? rows.length : 0,
            has_sidebar_root: !!sidebar_root,
            has_header: !!header,
            ts: Date.now()
          });
          return;
        }
        if (document.readyState === 'complete') {
          // No chat-specific anchors found but the page is fully loaded.
          // Accept as ready — the tab probably landed on a workspace
          // dashboard, not the chat panel.  Routing logic upstream
          // will navigate it to chat when needed.
          resolve({
            ok: true,
            rows: 0,
            has_sidebar_root: false,
            has_header: false,
            ts: Date.now(),
            note: 'document_complete_no_chat_anchors'
          });
          return;
        }
      } catch (e) { /* ignore */ }
      if (Date.now() >= deadline) {
        resolve({ ok: false, rows: 0, ts: Date.now(), reason: 'timeout' });
        return;
      }
      setTimeout(tick, 100);
    }
    tick();
  });
})();
"""

# Trivial health-check JS — round-trip a constant to detect a frozen page.
_HEALTH_CHECK_JS = "(function(){return {ok:true, ts:Date.now()};})()"


# ── CDP client cache on the pool ──────────────────────────────────────


def _get_pool_cdp_attr(pool: _tab_pool.FeigeTabPool) -> dict:
    """Return a mutable dict attached to the pool for caching CDP state."""
    attr = getattr(pool, "_lifecycle_cdp_cache", None)
    if attr is None:
        attr = {}
        setattr(pool, "_lifecycle_cdp_cache", attr)
    return attr


async def _resolve_cdp_url(browser_session) -> str:
    """Resolve Chrome's CDP debugging WebSocket URL.

    Tries (in order):
      1. ``browser_session.cdp_url`` — set by browser-use when it
         attaches.
      2. ``browser_session.browser_profile.cdp_url`` — fallback used by
         EventMonitor (see ``event_monitor.py:94-101``).
      3. ``http://127.0.0.1:9228/json/version`` — last-resort discovery.
         PROD-VERIFIED 2026-05-21: real customer install uses port 9228
         (the eCan default).  Custom installs that override this port
         should always be reachable via the BrowserSession's cdp_url
         attribute (paths 1 or 2 above), so this fallback only matters
         when both BrowserSession lookups fail.
    """
    try:
        url = getattr(browser_session, "cdp_url", None)
        if url:
            return str(url)
    except Exception:
        pass
    try:
        bp = getattr(browser_session, "browser_profile", None)
        url = getattr(bp, "cdp_url", None) if bp else None
        if url:
            return str(url)
    except Exception:
        pass
    # Last-resort port probe
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:9228/json/version", timeout=2.0
        ) as resp:
            info = json.loads(resp.read().decode("utf-8"))
        url = info.get("webSocketDebuggerUrl", "")
        if url:
            return str(url)
    except Exception as e:
        logger.debug(f"[tab_lifecycle] CDP url probe via :9228 failed: {e}")
    return ""


async def _ensure_cdp_client(pool: _tab_pool.FeigeTabPool, browser_session):
    """Return a (cdp_client, alive_flag) pair, opening a fresh client if needed.

    The client lives on ``pool._lifecycle_cdp_cache`` so multiple
    open/close/healthcheck operations share one WebSocket.
    """
    cache = _get_pool_cdp_attr(pool)
    cached = cache.get("client")
    if cached is not None:
        # Lightweight liveness check via internal WS state when possible
        try:
            ws = getattr(cached, "ws", None)
            if ws is not None and hasattr(ws, "state"):
                # cdp_use's WebSocket state — same as event_monitor.py:80
                from websockets.protocol import State as _WsState  # type: ignore

                if ws.state is _WsState.OPEN:
                    return cached, True
        except Exception:
            pass
        # Treat as dead
        try:
            await cached.stop()
        except Exception:
            pass
        cache.pop("client", None)

    cdp_url = await _resolve_cdp_url(browser_session)
    if not cdp_url:
        logger.warning("[tab_lifecycle] unable to resolve CDP url — skipping open")
        return None, False
    try:
        from cdp_use import CDPClient  # type: ignore

        client = CDPClient(url=cdp_url)
        await client.start()
        cache["client"] = client
        cache["cdp_url"] = cdp_url
        return client, True
    except Exception as e:
        logger.warning(f"[tab_lifecycle] CDP client open failed: {e}")
        return None, False


# ── tab open / close / health ─────────────────────────────────────────


async def open_typing_tab(
    browser_session,
    *,
    monitor_url: str,
    ready_timeout_s: float = _DEFAULT_NAV_READY_TIMEOUT_S,
) -> Optional[str]:
    """Open a new Chrome tab at ``monitor_url`` and wait for Feige sidebar to load.

    Returns the new tab's ``target_id`` on success, ``None`` on failure.
    The tab is NOT yet registered in the pool — the caller (typically
    ``initialize_typing_pool``) does that after ``open_typing_tab``
    returns to avoid race windows where the tab is registered but not
    ready.
    """
    pool = _tab_pool.get_pool()
    client, alive = await _ensure_cdp_client(pool, browser_session)
    if not alive or client is None:
        return None

    # 1. Create a new tab via CDP Target.createTarget.
    #    PROD-VERIFIED 2026-05-21: Real customer Chrome at port 9228
    #    responded to Target.getTargets + Target.attachToTarget +
    #    Runtime.evaluate against real Feige pages — same wire protocol
    #    Target.createTarget uses.  No special permissions needed.
    try:
        create_result = await client.send_raw(
            "Target.createTarget",
            {"url": monitor_url, "newWindow": False, "background": False},
        )
    except Exception as e:
        logger.warning(f"[tab_lifecycle] Target.createTarget failed: {e}")
        return None
    new_tid = ""
    if isinstance(create_result, dict):
        new_tid = str(create_result.get("targetId") or "")
    if not new_tid:
        logger.warning(f"[tab_lifecycle] createTarget returned no targetId: {create_result!r}")
        return None

    logger.info(f"[tab_lifecycle] opened new typing tab target=...{new_tid[-6:]} at {monitor_url}")

    # 2. Attach a CDP session to the new tab so we can poll for readiness.
    sid = None
    try:
        attach = await client.send_raw(
            "Target.attachToTarget", {"targetId": new_tid, "flatten": True}
        )
        sid = attach.get("sessionId") if isinstance(attach, dict) else None
    except Exception as e:
        logger.warning(f"[tab_lifecycle] attachToTarget failed for ...{new_tid[-6:]}: {e}")
        return None
    if not sid:
        logger.warning(f"[tab_lifecycle] attachToTarget returned no sessionId for ...{new_tid[-6:]}")
        return None

    try:
        await client.send_raw("Runtime.enable", {}, session_id=sid)
        # 3. Poll until sidebar rows appear OR timeout.
        await_ms = max(500, int(ready_timeout_s * 1000))
        ready_js = _FEIGE_READY_JS.replace("AWAIT_READY_UNTIL_MS", str(await_ms))
        t0 = time.time()
        eval_result = await asyncio.wait_for(
            client.send_raw(
                "Runtime.evaluate",
                {
                    "expression": ready_js,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
                session_id=sid,
            ),
            timeout=ready_timeout_s + 2.0,
        )
        elapsed_ms = (time.time() - t0) * 1000
        result = (eval_result or {}).get("result", {}) if isinstance(eval_result, dict) else {}
        ready_data = result.get("value") if isinstance(result, dict) else None
        if isinstance(ready_data, dict) and ready_data.get("ok"):
            logger.info(
                f"[tab_lifecycle] tab ...{new_tid[-6:]} ready: "
                f"sidebar_rows={ready_data.get('rows')} after {elapsed_ms:.0f}ms"
            )
            return new_tid
        logger.warning(
            f"[tab_lifecycle] tab ...{new_tid[-6:]} did not become ready within "
            f"{ready_timeout_s:.1f}s (ready_data={ready_data!r}); closing"
        )
    except asyncio.TimeoutError:
        logger.warning(
            f"[tab_lifecycle] tab ...{new_tid[-6:]} ready-poll timed out after "
            f"{ready_timeout_s:.1f}s; closing"
        )
    except Exception as e:
        logger.warning(f"[tab_lifecycle] tab ...{new_tid[-6:]} ready-check failed: {e}; closing")
    finally:
        if sid:
            try:
                await client.send_raw("Target.detachFromTarget", {"sessionId": sid})
            except Exception:
                pass

    # Tab failed to become ready → close it before returning failure
    try:
        await client.send_raw("Target.closeTarget", {"targetId": new_tid})
    except Exception:
        pass
    return None


async def close_typing_tab(browser_session, target_id: str) -> bool:
    """Close a Chrome tab via CDP.  Returns True on success."""
    if not target_id:
        return False
    pool = _tab_pool.get_pool()
    client, alive = await _ensure_cdp_client(pool, browser_session)
    if not alive or client is None:
        return False
    try:
        await client.send_raw("Target.closeTarget", {"targetId": target_id})
        return True
    except Exception as e:
        logger.debug(f"[tab_lifecycle] closeTarget failed for ...{target_id[-6:]}: {e}")
        return False


async def health_check_target(
    browser_session, target_id: str, *, timeout_s: float = 3.0
) -> bool:
    """Verify a tab is responsive by round-tripping a trivial Runtime.evaluate."""
    if not target_id:
        return False
    pool = _tab_pool.get_pool()
    client, alive = await _ensure_cdp_client(pool, browser_session)
    if not alive or client is None:
        return False
    sid = None
    try:
        attach = await client.send_raw(
            "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )
        sid = attach.get("sessionId") if isinstance(attach, dict) else None
        if not sid:
            return False
        await client.send_raw("Runtime.enable", {}, session_id=sid)
        result = await asyncio.wait_for(
            client.send_raw(
                "Runtime.evaluate",
                {"expression": _HEALTH_CHECK_JS, "returnByValue": True},
                session_id=sid,
            ),
            timeout=timeout_s,
        )
        ok = (
            isinstance(result, dict)
            and isinstance(result.get("result"), dict)
            and isinstance(result["result"].get("value"), dict)
            and result["result"]["value"].get("ok") is True
        )
        return ok
    except Exception:
        return False
    finally:
        if sid:
            try:
                await client.send_raw("Target.detachFromTarget", {"sessionId": sid})
            except Exception:
                pass


# ── pool initialization / shutdown ────────────────────────────────────


async def initialize_typing_pool(
    browser_session,
    *,
    target_size: int,
    monitor_url: str,
) -> None:
    """Open ``target_size`` typing tabs and register them with the pool.

    Fire-and-forget — failures log a warning and degrade gracefully.
    Called once at startup via ``pool.try_dispatch_initial_population``.
    """
    pool = _tab_pool.get_pool()
    if target_size <= 0:
        logger.info("[tab_lifecycle] FEIGE_TYPING_TAB_COUNT=0 — pool stays empty (single-tab mode)")
        return
    current = pool.get_typing_tab_count()
    needed = max(0, target_size - current)
    if needed == 0:
        return
    logger.info(
        f"[tab_lifecycle] initializing typing pool: target={target_size} "
        f"existing={current} need_to_open={needed} url={monitor_url!r}"
    )
    opened = 0
    for i in range(needed):
        new_tid = await open_typing_tab(browser_session, monitor_url=monitor_url)
        if new_tid:
            pool.register_typing_tab(new_tid, created_by_pool=True)
            opened += 1
        else:
            logger.warning(
                f"[tab_lifecycle] failed to open typing tab #{i + 1} of {needed}; "
                f"pool will run with {opened} of {target_size} tabs"
            )
            # Don't keep trying if creation fails consistently — give up after one failure
            break
        # Small gap between opens to avoid hammering Chrome with simultaneous
        # navigation events (each tab does its own initial load).
        await asyncio.sleep(0.3)
    logger.info(
        f"[tab_lifecycle] typing pool initialized: {opened}/{needed} new tabs opened, "
        f"pool size now={pool.get_typing_tab_count()}"
    )


async def cleanup_pool_tabs(browser_session) -> int:
    """Close all pool-opened typing tabs.  Returns count closed.

    Called from app shutdown.  Only closes tabs we opened
    (``created_by_pool=True``); user-opened tabs stay alone.
    """
    pool = _tab_pool.get_pool()
    targets_to_close = pool.list_pool_created_target_ids()
    closed = 0
    for tid in targets_to_close:
        ok = await close_typing_tab(browser_session, tid)
        if ok:
            pool.unregister_typing_tab(tid)
            closed += 1
    if closed:
        logger.info(f"[tab_lifecycle] cleanup: closed {closed}/{len(targets_to_close)} typing tabs")
    return closed


# ── background health sweep (Phase 4 — disabled by default) ───────────


async def health_check_sweep_loop(
    browser_session, *, interval_s: float = _DEFAULT_HEALTH_CHECK_INTERVAL_S
) -> None:
    """Run periodic health checks on all typing tabs.

    Phase 4 polish.  Not yet wired by default (tunable
    FEIGE_TYPING_TAB_HEALTH_SWEEP_S defaults to 0 = disabled).  To
    enable, set ECAN_FEIGE_TYPING_TAB_HEALTH_SWEEP_S=30 (or similar).
    """
    pool = _tab_pool.get_pool()
    if interval_s <= 0:
        return
    logger.info(f"[tab_lifecycle] health-sweep started: interval={interval_s}s")
    while True:
        try:
            await asyncio.sleep(interval_s)
            snap = pool.snapshot()
            for tid in list(snap.get("typing_tabs", {}).keys()):
                ok = await health_check_target(browser_session, tid)
                pool.mark_tab_health(tid, ok=ok)
                if not ok:
                    logger.warning(
                        f"[tab_lifecycle] health-sweep: tab ...{tid[-6:]} unresponsive; "
                        f"will be skipped by allocator until next sweep"
                    )
        except asyncio.CancelledError:
            logger.info("[tab_lifecycle] health-sweep cancelled")
            return
        except Exception as e:
            logger.warning(f"[tab_lifecycle] health-sweep tick failed: {e}")


__all__ = [
    "DEFAULT_FEIGE_URL_FRAGMENT",
    "open_typing_tab",
    "close_typing_tab",
    "health_check_target",
    "initialize_typing_pool",
    "cleanup_pool_tabs",
    "health_check_sweep_loop",
]
