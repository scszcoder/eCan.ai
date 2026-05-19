"""Auto-refresh the Feige chat page when WAN connectivity is restored.

Background
----------
Customer's 2026-05-18 30-min network-disconnect test showed that after
the LAN was restored, the Feige chat page in their Chrome tab persists
with the "人工客服目前不在线" (or similar) offline banner — even
though ``wan_a2a_chat`` successfully reconnects all 9 agent WebSocket
channels.  Manual F5 refresh clears the banner; the customer's report:

    关于断网测试，今天还出现一个情况，在长时间断网的情况(30min)，
    如果在这期间有用户发起会话，会提示人工客服目前不在线，此时接
    通网络后，这个发起会话的用户再次发起会话时，仍会提示人工客服
    不在线，需要把浏览器刷新或新用户发起会话，才可以进行处理

This module wires a callback on ``mainwin.wan_connected`` transitions
from ``False`` → ``True`` to:

  1. Detect a live browser session (from
     ``cached_browser_sessions`` registry).
  2. Find the Feige tab via ``resolve_feige_tab_target_id``.
  3. Acquire the per-Feige typing-lock so the refresh doesn't clobber
     a reply mid-type (uses the sentinel holder ``"__page_refresh__"``).
  4. Check the page DOM for an "offline banner" string — only refresh
     if the indicator is actually present (avoids needless reloads).
  5. If present, fire ``location.reload()`` via the existing
     ``_evaluate_js`` CDP path.

Design notes
------------

* **Sync caller, async work**: ``set_wan_connected`` runs on the Qt /
  ec_agent thread; the refresh needs an asyncio loop for the CDP eval.
  We spawn a daemon thread that runs ``asyncio.run(...)`` rather than
  scheduling onto a possibly-not-running existing loop.

* **Idempotent registration**: callable from many places (every
  ``wan_a2a_subscribe`` invocation, the eCan startup path, etc.)
  without creating duplicate handlers.  Guarded by a module-level
  ``_handler_registered`` flag.

* **Cooldown**: a second WAN-flap within 60 s reuses the existing
  in-flight refresh attempt rather than firing a second one (Feige
  reload is ~3-5 s; multiple parallel reloads would race).

* **Disable**: ``ECAN_FEIGE_PAGE_REFRESH=0`` env var to opt out
  entirely.

* **What this does NOT do**: It does NOT reconnect customers'
  conversations, retry undelivered Q&A turns, or replay messages.
  Those happen organically once the page is healthy again — the
  refresh just removes the stale visual indicator.  The point is to
  ensure the operator's app is in a usable state when the next
  customer message arrives, not to back-fill lost work.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger("eCan")


# ── Offline-banner detector JS ───────────────────────────────────────────
# Looks for common Feige offline-indicator strings in the page DOM.
# Multiple patterns covered because Feige's UI rotates wording slightly
# between platform tiers / locale variants.  Returns a small JSON dict
# so we can also log the URL we checked for forensics.
_OFFLINE_BANNER_DETECT_JS: str = r"""
(function() {
  var text = '';
  try { text = document.body ? document.body.innerText : ''; } catch (e) { text = ''; }
  var offlinePatterns = /人工客服[^\n]*不在线|智能客服[^\n]*不在线|客服[^\n]*离线|当前会话[^\n]*不在线|无法连接|网络.*异常|连接[^\n]*失败/;
  return JSON.stringify({
    has_banner: offlinePatterns.test(text),
    url: location.href,
    matched_text_sample: (text.match(offlinePatterns) || [""])[0].slice(0, 80)
  });
})()
"""


_FEIGE_RELOAD_JS: str = "(function(){try{location.reload();return 'reloading';}catch(e){return 'reload-error:'+e.message;}})()"


# ── Module-level registration state ──────────────────────────────────────
_handler_registered: bool = False
_handler_lock = threading.Lock()
# Cooldown — minimum seconds between two refresh attempts.  Protects
# against rapid WAN flap (network goes down then up multiple times in
# quick succession during an unstable connection).
_REFRESH_COOLDOWN_S: float = 60.0


class FeigePageRefreshHandler:
    """Single-instance handler that lives on the mainwin's callback list.

    State:
      ``_refresh_in_progress`` — flag flipped while a refresh thread is
      running, set back to False in the worker's finally block.  Used
      to coalesce multiple rapid WAN-flap transitions into one refresh.

      ``_last_refresh_at`` — monotonic timestamp of the last refresh
      attempt completion (success or failure).  Used by the cooldown
      check.
    """

    def __init__(self, mainwin):
        self.mainwin = mainwin
        self._refresh_in_progress: bool = False
        self._last_refresh_at: float = 0.0

    def on_wan_state_change(self, prev_stat, new_stat) -> None:
        # Only refresh on False → True (network recovery).  All other
        # transitions (True → False, None → True at app start, etc.)
        # do nothing.
        if not (prev_stat is False and new_stat is True):
            return

        # Opt-out env var.
        if str(os.getenv("ECAN_FEIGE_PAGE_REFRESH", "1")).strip().lower() in (
            "0", "false", "no", "off",
        ):
            logger.info(
                "[feige_page_refresh] disabled by ECAN_FEIGE_PAGE_REFRESH; "
                "skipping post-WAN-recovery refresh"
            )
            return

        # Cooldown check — guards against rapid WAN flap.
        now = time.monotonic()
        if now - self._last_refresh_at < _REFRESH_COOLDOWN_S:
            logger.info(
                f"[feige_page_refresh] cooldown active "
                f"({now - self._last_refresh_at:.1f}s of "
                f"{_REFRESH_COOLDOWN_S:.0f}s); skipping refresh"
            )
            return

        if self._refresh_in_progress:
            logger.info(
                "[feige_page_refresh] refresh already in progress; "
                "skipping duplicate trigger"
            )
            return

        logger.info(
            "[feige_page_refresh] WAN recovered (False→True); "
            "scheduling Feige page check + refresh-if-offline-banner"
        )
        self._refresh_in_progress = True
        t = threading.Thread(
            target=self._run_refresh_thread,
            name="FeigePageRefresh",
            daemon=True,
        )
        t.start()

    def _run_refresh_thread(self) -> None:
        try:
            asyncio.run(self._refresh_async())
        except Exception as exc:
            logger.warning(
                f"[feige_page_refresh] refresh thread errored "
                f"(non-fatal): {type(exc).__name__}: {exc}"
            )
        finally:
            self._last_refresh_at = time.monotonic()
            self._refresh_in_progress = False

    async def _refresh_async(self) -> None:
        # 1. Find a live browser session — any session that's open will
        # do since we filter to the Feige tab next.
        try:
            from agent.ec_skills.browser_node.build_helpers import (
                cached_browser_sessions,
            )
        except Exception as imp_err:
            logger.info(
                f"[feige_page_refresh] cached_browser_sessions unavailable "
                f"({imp_err}); skipping"
            )
            return

        if not cached_browser_sessions:
            logger.info(
                "[feige_page_refresh] no browser sessions cached "
                "(no agent has started a browser yet); skipping"
            )
            return

        browser_session: Any | None = None
        for sess in list(cached_browser_sessions.values()):
            if sess is not None:
                browser_session = sess
                break
        if browser_session is None:
            logger.info(
                "[feige_page_refresh] no live browser session found; skipping"
            )
            return

        # 2. Find the Feige tab.  resolve_feige_tab_target_id returns
        # empty string if none of the tabs match im.jinritemai.com.
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets import (
                resolve_feige_tab_target_id,
            )
        except Exception as imp_err:
            logger.info(
                f"[feige_page_refresh] resolve_feige_tab_target_id "
                f"unavailable ({imp_err}); skipping"
            )
            return

        target_id = await resolve_feige_tab_target_id(browser_session)
        if not target_id:
            logger.info(
                "[feige_page_refresh] no Feige tab in browser; "
                "operator may have closed it — skipping"
            )
            return

        # 3. Acquire the typing-lock so we don't refresh mid-type.  A
        # ~3-5 s reload while feige_send_message is actively typing
        # would lose that reply and leave the customer's bubble half-
        # rendered.  Sentinel holder name "__page_refresh__" so the
        # lock-release in finally targets only OUR acquire.
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                typing_lock,
            )
        except Exception as imp_err:
            logger.info(
                f"[feige_page_refresh] typing_lock unavailable "
                f"({imp_err}); proceeding without lock"
            )
            typing_lock = None  # type: ignore

        sentinel_holder = "__page_refresh__"
        lock_acquired = False
        if typing_lock is not None:
            # Poll the lock briefly — a real reply takes <30 s so giving
            # up early is fine; the next WAN-state transition (or the
            # cooldown expiry) will re-trigger us.
            for _attempt in range(10):  # 10 × 0.3 s = 3 s budget
                if typing_lock.try_acquire(sentinel_holder):
                    lock_acquired = True
                    break
                holder = typing_lock.holder()
                logger.debug(
                    f"[feige_page_refresh] typing-lock held by "
                    f"{holder!r}, waiting ({_attempt + 1}/10)"
                )
                await asyncio.sleep(0.3)

            if not lock_acquired:
                holder = typing_lock.holder()
                logger.info(
                    f"[feige_page_refresh] could not acquire typing-lock "
                    f"after 3 s (holder={holder!r}); deferring refresh "
                    f"to the next WAN-state transition"
                )
                return

        try:
            # 4. Check for offline banner.  Only refresh if the page
            # actually shows an offline indicator — if it's already
            # healthy, the reload is pure churn.
            try:
                from agent.ec_skills.browser_use_extension.extension_tools_service import (
                    _evaluate_js,
                )
            except Exception as imp_err:
                logger.info(
                    f"[feige_page_refresh] _evaluate_js unavailable "
                    f"({imp_err}); skipping"
                )
                return

            check_raw = await _evaluate_js(
                browser_session,
                _OFFLINE_BANNER_DETECT_JS,
                target_id=target_id,
                focus=False,
                trace_label="feige_page_refresh_banner_check",
                timeout_s=5.0,
                read_only=True,
            )
            has_banner = False
            matched = ""
            url = ""
            if isinstance(check_raw, str):
                try:
                    import json as _json
                    data = _json.loads(check_raw)
                except Exception:
                    data = {}
                has_banner = bool(data.get("has_banner"))
                matched = str(data.get("matched_text_sample") or "")
                url = str(data.get("url") or "")
            elif isinstance(check_raw, dict):
                has_banner = bool(check_raw.get("has_banner"))
                matched = str(check_raw.get("matched_text_sample") or "")
                url = str(check_raw.get("url") or "")

            if not has_banner:
                logger.info(
                    f"[feige_page_refresh] no offline banner on "
                    f"{url[:80]}; skipping refresh (page already healthy)"
                )
                return

            # 5. Refresh the page.
            logger.warning(
                f"[feige_page_refresh] offline banner detected "
                f"({matched!r}) on {url[:80]}; reloading Feige page"
            )
            try:
                await _evaluate_js(
                    browser_session,
                    _FEIGE_RELOAD_JS,
                    target_id=target_id,
                    focus=False,
                    trace_label="feige_page_refresh_reload",
                    timeout_s=5.0,
                )
                logger.info(
                    "[feige_page_refresh] reload command sent; "
                    "Feige tab will re-init in ~3-5 s"
                )
            except Exception as reload_err:
                logger.warning(
                    f"[feige_page_refresh] reload eval failed "
                    f"(operator may need to F5 manually): "
                    f"{type(reload_err).__name__}: {reload_err}"
                )

        finally:
            if typing_lock is not None and lock_acquired:
                try:
                    typing_lock.release(sentinel_holder)
                except Exception:
                    pass


# ── Idempotent registration ──────────────────────────────────────────────


def register_if_needed(mainwin) -> bool:
    """Register the refresh handler on mainwin's wan-connected callback list.

    Idempotent — calling from multiple places (every
    ``wan_a2a_subscribe`` invocation, app startup, etc.) is safe; only
    the first call wires the callback, subsequent calls return False.

    Returns
    -------
    True
        If this call installed the handler.
    False
        If already registered, or if registration failed (e.g. mainwin
        doesn't expose ``register_wan_connected_callback`` — happens on
        older builds that haven't picked up the 2026-05-18 MainGUI
        change yet).
    """
    global _handler_registered
    with _handler_lock:
        if _handler_registered:
            return False
        if mainwin is None:
            return False
        if not hasattr(mainwin, "register_wan_connected_callback"):
            logger.debug(
                "[feige_page_refresh] mainwin lacks "
                "register_wan_connected_callback (older build?); "
                "skipping registration"
            )
            return False
        try:
            handler = FeigePageRefreshHandler(mainwin)
            mainwin.register_wan_connected_callback(handler.on_wan_state_change)
            _handler_registered = True
            logger.info(
                "[feige_page_refresh] handler registered on mainwin's "
                "wan-connected transition list"
            )
            return True
        except Exception as exc:
            logger.warning(
                f"[feige_page_refresh] failed to register handler: "
                f"{type(exc).__name__}: {exc}"
            )
            return False


__all__ = [
    "FeigePageRefreshHandler",
    "register_if_needed",
]
