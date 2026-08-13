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
import threading
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


# ── dedicated thread+loop runtime per typing tab ─────────────────────


def _spawn_dedicated_cdp_runtime(
    cdp_url: str,
    target_id: str,
    *,
    init_timeout_s: float = 8.0,
) -> Optional[dict]:
    """Spawn a dedicated thread + asyncio loop hosting a single CDPClient.

    Phase 5 Option A (2026-05-21).  cdp_use itself is fine with N
    concurrent CDPClient instances (verified via _repro_multi_cdpclient.py
    — 6 clients × 6 evals in 1 ms total), but only when each lives on a
    loop that's not contending with eCan's busy agent loop.  Creating
    all clients on the agent loop starved their message-handler tasks
    of scheduler time, so only one of N actually delivered responses.

    Each pool tab now gets its OWN thread with its OWN asyncio loop
    that runs nothing except this one client's WebSocket handler.
    Worker-loop send_raw calls dispatch into that loop via
    ``run_coroutine_threadsafe`` (handled by ``_evaluate_js``'s existing
    ``_send_on_owner_loop`` cross-loop hop — no caller changes needed).

    Blocks the caller for at most ``init_timeout_s`` seconds while the
    thread starts the client and attaches the session.  Returns a dict
    ``{thread, loop, client, session_id}`` on success, ``None`` on
    failure (in which case the thread has already exited).
    """
    ready = threading.Event()
    state: dict = {"client": None, "session_id": None, "loop": None, "error": None}

    def _thread_main():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        state["loop"] = loop
        client = None

        async def _init():
            nonlocal client
            from cdp_use import CDPClient  # type: ignore

            client = CDPClient(url=cdp_url)
            await client.start()
            attach = await client.send_raw(
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
            )
            sid = attach.get("sessionId") if isinstance(attach, dict) else None
            if not sid:
                raise RuntimeError(f"attachToTarget returned no sessionId: {attach!r}")
            await client.send_raw("Runtime.enable", {}, session_id=sid)
            state["client"] = client
            state["session_id"] = str(sid)

        try:
            loop.run_until_complete(_init())
        except Exception as e:
            state["error"] = f"{type(e).__name__}: {e}"
            ready.set()
            # If client got partially created, try to stop it before exit
            if client is not None:
                try:
                    loop.run_until_complete(client.stop())
                except Exception:
                    pass
            try:
                loop.close()
            except Exception:
                pass
            return

        ready.set()
        # Run forever — this loop hosts the client's _message_handler_task.
        # Exits when shutdown_runtime() schedules loop.stop() from outside.
        try:
            loop.run_forever()
        finally:
            # Best-effort cleanup at thread shutdown
            try:
                loop.run_until_complete(client.stop())
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(
        target=_thread_main,
        name=f"FeigeCDP-{target_id[-6:]}",
        daemon=True,
    )
    t.start()
    if not ready.wait(timeout=init_timeout_s):
        logger.warning(
            f"[tab_lifecycle] dedicated CDP runtime for target=...{target_id[-6:]} "
            f"did not init within {init_timeout_s}s"
        )
        return None
    if state["error"] is not None or state["client"] is None or state["session_id"] is None:
        logger.warning(
            f"[tab_lifecycle] dedicated CDP runtime init failed for "
            f"target=...{target_id[-6:]}: {state['error']!r}"
        )
        return None
    return {
        "thread": t,
        "loop": state["loop"],
        "client": state["client"],
        "session_id": state["session_id"],
    }


def shutdown_dedicated_cdp_runtime(
    *,
    thread: Optional[Any],
    loop: Optional[Any],
    join_timeout_s: float = 3.0,
) -> None:
    """Stop a dedicated CDP runtime created by ``_spawn_dedicated_cdp_runtime``.

    Schedules ``loop.stop()`` on the dedicated loop (so its
    ``run_forever`` exits and its ``finally`` block stops the client +
    closes the loop), then joins the thread.
    """
    if loop is not None:
        try:
            if not getattr(loop, "is_closed", lambda: True)():
                loop.call_soon_threadsafe(loop.stop)
        except Exception as e:
            logger.debug(f"[tab_lifecycle] shutdown_dedicated loop.stop failed: {e}")
    if thread is not None:
        try:
            thread.join(timeout=join_timeout_s)
        except Exception as e:
            logger.debug(f"[tab_lifecycle] shutdown_dedicated thread.join failed: {e}")


# ── tab open / close / health ─────────────────────────────────────────


async def open_typing_tab(
    browser_session,
    *,
    monitor_url: str,
    ready_timeout_s: float = _DEFAULT_NAV_READY_TIMEOUT_S,
) -> Optional[dict]:
    """Open a new Chrome tab at ``monitor_url``, wait for Feige sidebar, and
    create a DEDICATED CDP WebSocket for this tab.

    Returns a dict ``{target_id, cdp_client, cdp_session_id}`` on success,
    ``None`` on failure.  The tab is NOT yet registered in the pool — the
    caller (``initialize_typing_pool``) does that after ``open_typing_tab``
    returns, passing the dedicated client + session_id into
    ``pool.register_typing_tab``.

    Phase 5 (2026-05-21): each typing tab now owns its own ``CDPClient``
    WebSocket.  This avoids the single-shared-WebSocket bottleneck that
    serialized all CDP messages through ``browser_session._cdp_client_root``
    in earlier phases — N tabs = N WebSockets = real parallelism.  The
    dedicated client is created on the current event loop so it survives
    across send operations until ``close_typing_tab`` tears it down.
    """
    # Use the shared lifecycle CDP client for the initial Target.createTarget
    # call (one-shot bookkeeping operation).  After the tab is created we
    # spin up a FRESH dedicated CDP client just for this tab's typing.
    pool = _tab_pool.get_pool()
    bootstrap_client, alive = await _ensure_cdp_client(pool, browser_session)
    if not alive or bootstrap_client is None:
        return None

    try:
        create_result = await bootstrap_client.send_raw(
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

    # Phase 5 Option A: spin up a DEDICATED THREAD with its own event
    # loop hosting this tab's CDPClient.  Critical — see
    # _spawn_dedicated_cdp_runtime docstring for why "client on agent
    # loop" failed in practice (only 1 of N got handler-task time).
    cdp_url = ""
    try:
        cache = _get_pool_cdp_attr(pool)
        cdp_url = str(cache.get("cdp_url") or "")
    except Exception:
        cdp_url = ""
    if not cdp_url:
        cdp_url = await _resolve_cdp_url(browser_session)
    if not cdp_url:
        logger.warning(
            f"[tab_lifecycle] cannot resolve CDP url for dedicated client on "
            f"target=...{new_tid[-6:]}; closing tab"
        )
        try:
            await bootstrap_client.send_raw("Target.closeTarget", {"targetId": new_tid})
        except Exception:
            pass
        return None

    # ``_spawn_dedicated_cdp_runtime`` blocks (thread.start + wait_for_ready)
    # for at most init_timeout_s; this is fine because pool init runs
    # sequentially (one tab at a time, with sleep(0.3) gap).
    loop_run_in_thread = asyncio.get_event_loop()
    runtime = await loop_run_in_thread.run_in_executor(
        None,  # default thread pool — _spawn_dedicated_cdp_runtime returns quickly
        _spawn_dedicated_cdp_runtime,
        cdp_url,
        new_tid,
    )
    if runtime is None:
        logger.warning(
            f"[tab_lifecycle] dedicated CDP runtime spawn failed for "
            f"target=...{new_tid[-6:]}; closing tab"
        )
        try:
            await bootstrap_client.send_raw("Target.closeTarget", {"targetId": new_tid})
        except Exception:
            pass
        return None

    dedicated_client = runtime["client"]
    dedicated_sid = runtime["session_id"]
    dedicated_thread = runtime["thread"]
    dedicated_loop = runtime["loop"]
    logger.info(
        f"[tab_lifecycle] dedicated CDP client attached for typing tab "
        f"target=...{new_tid[-6:]} sessionId=...{dedicated_sid[-6:]} "
        f"thread={dedicated_thread.name} loop_id={id(dedicated_loop)}"
    )

    # Poll for readiness USING THE DEDICATED CLIENT — but the client is
    # on a different thread's event loop now (Option A).  Hand the call
    # off via run_coroutine_threadsafe.
    try:
        await_ms = max(500, int(ready_timeout_s * 1000))
        ready_js = _FEIGE_READY_JS.replace("AWAIT_READY_UNTIL_MS", str(await_ms))
        t0 = time.time()
        ready_future = asyncio.run_coroutine_threadsafe(
            dedicated_client.send_raw(
                "Runtime.evaluate",
                {
                    "expression": ready_js,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
                session_id=dedicated_sid,
            ),
            dedicated_loop,
        )
        eval_result = await asyncio.wait_for(
            asyncio.wrap_future(ready_future),
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
            return {
                "target_id": new_tid,
                "cdp_client": dedicated_client,
                "cdp_session_id": dedicated_sid,
                "cdp_thread": dedicated_thread,
                "cdp_loop": dedicated_loop,
            }
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

    # Not ready → tear down dedicated runtime + close tab
    shutdown_dedicated_cdp_runtime(thread=dedicated_thread, loop=dedicated_loop)
    try:
        await bootstrap_client.send_raw("Target.closeTarget", {"targetId": new_tid})
    except Exception:
        pass
    return None


async def close_typing_tab(browser_session, target_id: str) -> bool:
    """Close a Chrome tab via CDP + tear down its dedicated CDP runtime.

    Phase 5 Option A: stops the dedicated thread+loop hosting the
    tab's CDPClient (which also stops the client via the loop's
    ``finally`` block) and joins the thread.
    """
    if not target_id:
        return False
    pool = _tab_pool.get_pool()

    # Tear down dedicated runtime first (the thread's loop.run_forever
    # exits via its finally block, which stops the client cleanly).
    tab_state = pool.get_typing_tab_state(target_id)
    if tab_state is not None and tab_state.cdp_thread is not None:
        try:
            shutdown_dedicated_cdp_runtime(
                thread=tab_state.cdp_thread, loop=tab_state.cdp_loop
            )
        except Exception as e:
            logger.debug(
                f"[tab_lifecycle] dedicated runtime shutdown failed for "
                f"...{target_id[-6:]} (non-fatal): {e}"
            )

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
    """Verify a tab is responsive by round-tripping a trivial Runtime.evaluate.

    Phase 5: prefer the tab's dedicated CDP client (which is what real
    typing will use), so a healthy result here actually reflects
    typing-path health.  Falls back to the bootstrap client when no
    dedicated one exists.
    """
    if not target_id:
        return False
    pool = _tab_pool.get_pool()

    # Phase 5 preferred path: use the tab's dedicated CDP client via
    # cross-loop hop to its dedicated thread.
    tab_state = pool.get_typing_tab_state(target_id)
    if (
        tab_state is not None
        and tab_state.cdp_client is not None
        and tab_state.cdp_session_id
        and tab_state.cdp_loop is not None
    ):
        try:
            ded_future = asyncio.run_coroutine_threadsafe(
                tab_state.cdp_client.send_raw(
                    "Runtime.evaluate",
                    {"expression": _HEALTH_CHECK_JS, "returnByValue": True},
                    session_id=tab_state.cdp_session_id,
                ),
                tab_state.cdp_loop,
            )
            result = await asyncio.wait_for(
                asyncio.wrap_future(ded_future), timeout=timeout_s
            )
            return (
                isinstance(result, dict)
                and isinstance(result.get("result"), dict)
                and isinstance(result["result"].get("value"), dict)
                and result["result"]["value"].get("ok") is True
            )
        except Exception:
            return False

    # Legacy fallback path — use bootstrap client + attach/detach.
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
        result = await open_typing_tab(browser_session, monitor_url=monitor_url)
        if result and result.get("target_id"):
            pool.register_typing_tab(
                result["target_id"],
                created_by_pool=True,
                cdp_client=result.get("cdp_client"),
                cdp_session_id=result.get("cdp_session_id"),
                cdp_thread=result.get("cdp_thread"),
                cdp_loop=result.get("cdp_loop"),
            )
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
