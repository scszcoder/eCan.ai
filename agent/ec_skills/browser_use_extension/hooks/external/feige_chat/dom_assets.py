"""Feige-site DOM assets and helpers.

This module owns the Feige-specific DOM plumbing that used to live inline
in ``agent/ec_skills/build_node.py`` (Phase 1+2 of the
site-code-out-of-core-node cleanup).  The generic ``browser_automation``
node re-exports the symbols from here under their legacy underscore-
prefixed names so the remaining HOT-PATH-B call sites keep working
verbatim during the migration.

Contents
--------

* ``FEIGE_ACTIVE_CUSTOMER_JS``
    JS snippet reading two independent signals (sidebar + header) that
    identify the currently-focused chat.

* ``FEIGE_LATEST_CUSTOMER_BUBBLE_JS``
    JS snippet walking the chat-thread DOM backwards to find the most
    recent customer bubble (skipping agent replies / system spans).

* ``FEIGE_CLICK_SIDEBAR_ROW_JS``
    JS snippet clicking the sidebar row whose name matches a target
    customer name.  Consumers must ``.replace("CUSTOMER_NAME", ...)`` on
    the string before eval-ing.

* ``verify_customer_match(verify_result, expected_name)``
    Zero-risk verification policy — returns ``(ok, reason)`` given the
    dict produced by ``FEIGE_ACTIVE_CUSTOMER_JS``.

* ``ensure_feige_tab_focused(browser_session)``
    Async — switches the session to a Feige tab (by ``im.jinritemai.com``
    URL match) and keeps the sidebar on ``当前会话``.

* ``scrape_latest_customer_bubble(browser_session, customer_name, *, typing_holder_getter=None)``
    Async — focuses the given customer's chat pane and extracts the
    most recent customer bubble.  ``typing_holder_getter`` is an
    optional zero-arg callable returning the current "who is typing"
    holder key (Phase 3 — migrating to hook state-store).

The module has **no dependency on build_node.py** so future moves of
HOT-PATH-B orchestration into hook bundles can import from here
directly.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Callable

logger = logging.getLogger("eCan")

# ---------------------------------------------------------------------------
# Focus-target tuning constants.
#
# Stress tests showed concurrent HOT-PATH-B / PreDispatch focus calls
# against the same Chrome CDP session. Two controls keep this bounded:
#
#   1. A short 3s focus budget. If focus is contended, fail fast and let
#      the guarded open/send path continue instead of tying up the worker.
#
#   2. A per-session cross-loop async lock (see ``_session_focus_lock``) so concurrent
#      callers serialize at the application level rather than racing inside
#      the CDP transport.  A plain asyncio.Lock cannot be shared across the
#      runner loops; it fails with "bound to a different event loop" under
#      direct-delivery flood.
# ---------------------------------------------------------------------------
_FOCUS_TARGET_TIMEOUT_S: float = 3.0
_SESSION_FOCUS_LOCK_ATTR: str = "_ecan_feige_focus_lock"
_SESSION_CDP_OPERATION_LOCK_ATTR: str = "_ecan_feige_cdp_operation_lock"
_SESSION_FOCUSED_FEIGE_TID_ATTR: str = "_ecan_feige_focused_tid"
_FOCUS_LOCK_POLL_S: float = 0.02
_CDP_OPERATION_PROBE_TIMEOUT_S: float = 2.0


class _CrossLoopAsyncLock:
    """Async context manager backed by a process-local ``threading.Lock``.

    ``asyncio.Lock`` binds to the loop that first waits on it. The Feige
    browser session is shared by the front-desk monitor, fallback queue, and
    direct-delivery worker, which can run on different loops. Polling a
    non-blocking ``threading.Lock`` keeps the event loop responsive while
    still serializing CDP focus calls across loops.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    async def __aenter__(self):
        import asyncio as _lock_asyncio

        while True:
            if self._lock.acquire(blocking=False):
                return self
            await _lock_asyncio.sleep(_FOCUS_LOCK_POLL_S)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._lock.release()


def _session_focus_lock(browser_session) -> "object":
    """Return the per-session cross-loop async lock.

    Falls back to a module-level registry keyed by ``id(session)`` if the
    session object disallows attribute assignment.

    Why per-session: each BrowserSession owns one CDP transport.  Two
    concurrent ``get_or_create_cdp_session(target_id=..., focus=True)``
    calls on that transport contend for the same chrome focus, which
    is what produced ``CDP session contended`` timeouts in the
    2026-04-30 stress test.  Different sessions (different chrome
    connections) are independent and must not share a lock.
    """
    lock = getattr(browser_session, _SESSION_FOCUS_LOCK_ATTR, None)
    if isinstance(lock, _CrossLoopAsyncLock):
        return lock

    # Some BrowserSession variants (frozen pydantic models) disallow
    # attribute assignment. Fall back to a process-global registry.
    lock = _CrossLoopAsyncLock()
    try:
        setattr(browser_session, _SESSION_FOCUS_LOCK_ATTR, lock)
        return lock
    except Exception:
        _global_key = id(browser_session)
        lock = _GLOBAL_FOCUS_LOCKS.get(_global_key)
        if lock is None:
            lock = _CrossLoopAsyncLock()
            _GLOBAL_FOCUS_LOCKS[_global_key] = lock
        return lock


_GLOBAL_FOCUS_LOCKS: dict[int, _CrossLoopAsyncLock] = {}
_GLOBAL_CDP_OPERATION_LOCKS: dict[int, _CrossLoopAsyncLock] = {}


def session_cdp_operation_lock(browser_session) -> "object":
    """Return the per-session lock for Feige CDP renderer operations.

    The focus lock only protects tab switching. Under flood, direct sends,
    monitor polls, and pre-dispatch scrapes can still overlap at
    ``Runtime.evaluate`` on the same Feige renderer. This lock serializes that
    broader operation class across event loops while still allowing unrelated
    browser sessions to proceed independently.
    """
    lock = getattr(browser_session, _SESSION_CDP_OPERATION_LOCK_ATTR, None)
    if isinstance(lock, _CrossLoopAsyncLock):
        return lock

    lock = _CrossLoopAsyncLock()
    try:
        setattr(browser_session, _SESSION_CDP_OPERATION_LOCK_ATTR, lock)
        return lock
    except Exception:
        _global_key = id(browser_session)
        lock = _GLOBAL_CDP_OPERATION_LOCKS.get(_global_key)
        if lock is None:
            lock = _CrossLoopAsyncLock()
            _GLOBAL_CDP_OPERATION_LOCKS[_global_key] = lock
        return lock


def clear_feige_tab_focus_cache(browser_session, reason: str = "") -> None:
    """Clear the cached Feige target id on a shared browser session."""
    try:
        setattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, None)
        if reason:
            logger.debug(
                f"[BrowserAutomation] ensure-feige-tab: cleared cached "
                f"Feige target ({reason})"
            )
    except Exception:
        pass


def _feige_path_depth(url: str) -> int:
    m = re.search(r"im\.jinritemai\.com(/[^?#]*)?", str(url or ""))
    if not m:
        return 999
    path = (m.group(1) or "/").strip("/")
    return 0 if not path else path.count("/") + 1


async def resolve_feige_tab_target_id(browser_session) -> str:
    """Return the best Feige tab target id without changing browser focus."""
    try:
        sm = getattr(browser_session, "session_manager", None)
        all_targets = sm.get_all_targets() if sm else {}
    except Exception:
        all_targets = {}

    cached_tid = str(
        getattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, "") or ""
    )
    if cached_tid:
        cached = (all_targets or {}).get(cached_tid)
        cached_url = str(getattr(cached, "url", "") or "") if cached else ""
        if cached is not None and "im.jinritemai.com" in cached_url:
            return cached_tid
        clear_feige_tab_focus_cache(browser_session, "cached target stale")

    candidates: list[tuple[str, str]] = []
    for tid, tgt in (all_targets or {}).items():
        if getattr(tgt, "target_type", "") not in ("page", "tab"):
            continue
        url = str(getattr(tgt, "url", "") or "")
        if "im.jinritemai.com" in url:
            candidates.append((str(tid), url))
    if not candidates:
        return ""

    candidates.sort(key=lambda c: _feige_path_depth(c[1]))

    if len(candidates) > 1 and hasattr(browser_session, "get_or_create_cdp_session"):
        row_count_js = (
            "(function(){return document.querySelectorAll("
            "'[data-qa-id=\"qa-conversation-chat-item\"]').length;})()"
        )

        async def _probe_rows(tid: str) -> int:
            try:
                import asyncio as _probe_asyncio

                async def _run_probe():
                    cdp_sess = await browser_session.get_or_create_cdp_session(
                        target_id=tid,
                        focus=False,
                    )
                    if cdp_sess is None:
                        return None
                    cdp_client = getattr(cdp_sess, "cdp_client", None)
                    session_id = getattr(cdp_sess, "session_id", None)
                    if cdp_client is None or session_id is None:
                        return None
                    await cdp_client.send.Runtime.enable(session_id=session_id)
                    return await cdp_client.send.Runtime.evaluate(
                        params={"expression": row_count_js, "returnByValue": True},
                        session_id=session_id,
                    )

                async with session_cdp_operation_lock(browser_session):
                    result = await _probe_asyncio.wait_for(
                        _run_probe(),
                        timeout=_CDP_OPERATION_PROBE_TIMEOUT_S,
                    )
                if result is None:
                    return -1
                val = (result.get("result") or {}).get("value")
                return int(val) if isinstance(val, (int, float)) else -1
            except Exception:
                return -1

        probed: list[tuple[int, int, str, str]] = []
        for tid, url in candidates:
            probed.append((await _probe_rows(tid), _feige_path_depth(url), tid, url))
        probed.sort(key=lambda r: (-(max(r[0], 0)), r[1]))
        candidates = [(tid, url) for _rows, _depth, tid, url in probed]

    target_id = candidates[0][0]
    try:
        setattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, target_id)
    except Exception:
        pass
    return target_id


# ---------------------------------------------------------------------------
# Minimal utilities — duplicated from build_node.py to avoid a core->bundle
# import edge.  Keep bodies byte-identical so future deduplication via a
# shared util module is a trivial delete.
# ---------------------------------------------------------------------------

def _normalize_dispatch_identity_key(raw_id: str) -> str:
    """Strip the message-preview suffix (``"sc|..."``) from a customer id.

    Mirrors ``build_node._normalize_dispatch_identity_key`` exactly.  See that doc
    for the rationale (DOM extractor identity keys carry a mutable
    preview tail that breaks dedup / affinity caches).
    """
    if not raw_id:
        return ""
    s = str(raw_id).strip()
    if "|" in s:
        prefix = s.split("|", 1)[0].strip()
        if prefix:
            return prefix
    return s


def _normalize_reply_text(text: str) -> str:
    """Whitespace-collapse + length-cap for DOM-echo comparisons.

    Mirrors ``build_node._normalize_reply_text`` exactly.
    """
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    return s[:120]


# ---------------------------------------------------------------------------
# JS snippet — active-customer detection (sidebar + header signals).
#
# Reads two independent signals identifying the currently-focused chat in
# Feige's DOM so HOT-PATH-B can verify (post-open, pre-send) that the SPA
# is displaying the intended customer before typing.  Without this guard,
# a race between ``get_or_create_cdp_session(focus=True)`` and the
# emulation's React render commit can cause ``feige_send_message`` to
# type into whichever session the middle pane last committed — which in
# the 2026-04-22 11:51 run put 客户B's answer into 客户C's chat window.
# On the real Feige production site (``im.jinritemai.com/pc_seller_v2/…``),
# the ``.active`` class we relied on didn't exist at all — production uses
# a CSS-in-JS hashed state class (``wmvLQcpt39Hk9PSISrlN`` as of
# 2026-04-23), which broke every reply in the first customer deployment.
#
# Returns JSON:
#   { ok, active,                       // legacy: populated with the best name
#     sidebar_name,  sidebar_method,    // signal 1: which row is visually selected
#     header_name,                      // signal 2: which customer's chat pane is open
#     diagnostics: { item_count, odd_count, sample_items } }
#
# Signal 1 (sidebar) — tries 3 strategies, first hit wins:
#   a. class token ``active``            — emulation + any site that ships it
#   b. known hashed class                — today's real Feige production
#   c. self-adaptive ``odd-one-out``     — exactly one chat-item has a class
#      token unique to itself.  Robust against future Feige hash rotations
#      without code changes.
#
# Signal 2 (header) — authoritative because the textarea that receives
#   keystrokes lives in the same chat pane.  Anchors on the stable
#   ``id="topbar-left-info"`` (real HTML id, not CSS-in-JS hashed) and
#   picks the first leaf text-bearing div that isn't the ``添加备注``
#   (add-remark) placeholder.
#
# Verification policy lives in Python — see ``verify_customer_match``.
# ---------------------------------------------------------------------------
FEIGE_ACTIVE_CUSTOMER_JS: str = r"""
(function() {
  var result = {
    ok: false, active: '',
    sidebar_name: '', sidebar_method: 'none',
    header_name: '',
    diagnostics: {}
  };

  // ───── Signal 2: header (primary, authoritative) ─────
  try {
    var topbar = document.querySelector('#topbar-left-info');
    if (topbar) {
      var cands = topbar.querySelectorAll('div, span');
      for (var hi = 0; hi < cands.length; hi++) {
        var ht = (cands[hi].textContent || '').trim();
        if (!ht || ht === '添加备注' || ht.length > 60) continue;
        if (cands[hi].children.length === 0) { result.header_name = ht; break; }
      }
      if (!result.header_name) {
        var btm = topbar.querySelector('div[data-btm-id]');
        if (btm) result.header_name = (btm.textContent || '').trim();
      }
    }
  } catch (e) { result.diagnostics.header_err = String(e); }

  // ───── Signal 1: sidebar (cross-check) ─────
  function rowIsCurrent(row) {
    var btm = row && row.getAttribute ? String(row.getAttribute('data-btm-id') || '') : '';
    if (btm.endsWith('.current')) return true;
    if (btm.endsWith('.recent') || btm.endsWith('.systemConv')) return false;
    if (row && row.closest && row.closest('.pigeonChatNotScrollBox')) return true;
    if (row && row.closest && row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  var items = Array.from(document.querySelectorAll(
    '[data-qa-id="qa-conversation-chat-item"], .chat-item'
  )).filter(rowIsCurrent);
  result.diagnostics.item_count = items.length;

  function readName(row) {
    var wrap = row.querySelector('.MP1bk3ccfHC9V2SnPCGD');
    if (wrap) {
      var t = wrap.getAttribute('title');
      if (t && t.trim()) return t.trim();
    }
    var span = row.querySelector('.Jv6FtqUv5VoYARd2pp4y');
    if (span) {
      var s = (span.textContent || '').trim();
      if (s) return s;
    }
    var legacy = row.querySelector('[data-qa-id="qa-conversation-nickname"]');
    if (legacy) return (legacy.textContent || '').trim();
    return '';
  }

  var found = null;

  // Strategy (a): class token "active" (emulation)
  for (var i = 0; i < items.length; i++) {
    var cn = (items[i].className || '').toLowerCase();
    if (cn.indexOf('active') >= 0) {
      found = items[i];
      result.sidebar_method = 'class-active';
      break;
    }
  }

  // Strategy (b): known production Feige hashed state class
  if (!found) {
    for (var j = 0; j < items.length; j++) {
      if (items[j].classList.contains('wmvLQcpt39Hk9PSISrlN')) {
        found = items[j];
        result.sidebar_method = 'class-hash-known';
        break;
      }
    }
  }

  // Strategy (c): self-adaptive odd-one-out — exactly one item has a class
  // token unique to itself.  Survives future hash rotations.
  if (!found && items.length >= 2) {
    var tokenCount = {};
    var tokensPerItem = [];
    for (var k = 0; k < items.length; k++) {
      var toks = (items[k].className || '').split(/\s+/).filter(Boolean);
      tokensPerItem.push(toks);
      for (var tc = 0; tc < toks.length; tc++) {
        tokenCount[toks[tc]] = (tokenCount[toks[tc]] || 0) + 1;
      }
    }
    var oddIdx = -1, oddCount = 0;
    for (var m = 0; m < tokensPerItem.length; m++) {
      var hasUnique = false;
      for (var n = 0; n < tokensPerItem[m].length; n++) {
        if (tokenCount[tokensPerItem[m][n]] === 1) { hasUnique = true; break; }
      }
      if (hasUnique) { oddIdx = m; oddCount++; }
    }
    result.diagnostics.odd_count = oddCount;
    if (oddCount === 1 && oddIdx >= 0) {
      found = items[oddIdx];
      result.sidebar_method = 'odd-one-out';
    }
  }

  if (found) {
    result.sidebar_name = readName(found);
  } else {
    result.sidebar_method = result.sidebar_method || 'not-found';
    var hints = [];
    for (var si = 0; si < items.length && hints.length < 5; si++) {
      hints.push({ name: readName(items[si]), classes: (items[si].className || '').slice(0, 220) });
    }
    result.diagnostics.sample_items = hints;
  }

  // Legacy fields: `active` carries the best name we could identify; `ok`
  // is true whenever at least one signal produced a non-empty name.
  result.active = result.sidebar_name || result.header_name;
  result.ok = !!result.active;
  return JSON.stringify(result);
})()
"""


# ---------------------------------------------------------------------------
# JS snippet — latest customer bubble extractor.
#
# Walks the chat-thread DOM backwards and returns the most recent
# *customer* bubble (skipping agent replies and system / event spans).
# Returns JSON with ``{text, msg_id, timestamp, index}`` — all empty /
# ``-1`` when no customer bubble exists in the currently-focused pane.
# The selectors mirror those in
# ``agent.ec_skills.browser_use_extension.extension_tools_service._FEIGE_GET_THREAD_JS``
# (keep in sync if selectors change).
# ---------------------------------------------------------------------------
FEIGE_LATEST_CUSTOMER_BUBBLE_JS: str = r"""
(function() {
  // Avatar imgs use class "Zq9KgucRnc7bRQfikvzQ" (sidebar/header) or
  // "qwDH4Hnmk4jmYkYLmHGF" (in-thread sender avatar).  Skip those —
  // we only want CONTENT images (alt="图片").  We keep an inclusive
  // alt-attribute filter as the primary signal so future class-name
  // churn doesn't silently drop content images.
  function _customerBubble(wrap) {
    // Customer-side row direction is "row" (agent-side is row-reverse).
    // We rely on the inner row container's flex-direction style — the
    // Feige DOM sets it inline so reading style.flexDirection is
    // reliable across both real Feige and the emulation.
    var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
    if (!row) return null;
    if ((row.style.flexDirection || '').indexOf('reverse') !== -1) {
      return null;  // agent-side bubble
    }
    return row;
  }
  function _collectAttachments(row) {
    if (!row) return [];
    var atts = [];
    var imgs = Array.from(row.querySelectorAll('img'));
    for (var k = 0; k < imgs.length; k++) {
      var im = imgs[k];
      var cls = (im.className || '').toString();
      var alt = (im.getAttribute('alt') || '').trim();
      // Skip avatar imgs by class.
      if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(cls)) continue;
      // Skip avatar imgs by alt (catches future class-name renames).
      if (alt === '头像') continue;
      // Use ``im.src`` (the resolved property) in preference to
      // ``im.getAttribute('src')`` so relative URLs like ``/sample0.png``
      // come out as absolute (``http://host:port/sample0.png``).  The
      // downstream eager-fetch in ``image_fetch.fetch_image_to_data_uri``
      // uses aiohttp which rejects relative URLs with ``InvalidURL``.
      var src = im.src || im.getAttribute('src') || '';
      if (!src) continue;
      // Skip data: avatars (the SVG default-avatar fallback).
      if (src.indexOf('data:image/svg') === 0) continue;
      atts.push({ kind: 'image', url: src, alt: alt });
    }
    return atts;
  }
  function _isTransferMarker(text) {
    var t = String(text || '').replace(/\s+/g, '').trim();
    return t === '转人工' || t === '转人工客服' || t === '人工客服';
  }
  var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
  for (var i = wrappers.length - 1; i >= 0; i--) {
    var wrap = wrappers[i];
    var row = _customerBubble(wrap);
    if (!row) continue;                                  // agent-side or system
    var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1');
    var text = '';
    if (bubble) {
      if (bubble.classList.contains('messageIsMe')) continue;  // double-check
      text = (bubble.querySelector('pre') || bubble).textContent.trim();
    }
    var attachments = _collectAttachments(row);
    // A bubble counts as a customer message if it has either text or
    // a content image.  Image-only bubbles (text === '') were silently
    // dropped before this change.
    if (!text && attachments.length === 0) continue;
    if (text && _isTransferMarker(text)) continue;
    // ── Merge attachments from immediately-prior customer bubbles ──
    // Real-world multimodal chats fire as bursts: e.g. (image, text)
    // or (text, image, text).  When the latest bubble we picked is
    // text, the image lives in a sibling bubble just above it.  Walk
    // backwards collecting customer-side attachments until we hit:
    //   * an agent-side bubble (real reply already happened) → STOP
    //   * a non-customer-non-agent wrapper (system/notice) → SKIP
    //   * the look-back cap (3 bubbles) → STOP
    // We DON'T merge prior bubbles' text (that would conflate two
    // distinct messages); we only merge image attachments so the
    // vision LLM has them available.  Dedup/msg_id stay anchored on
    // the tail bubble so existing dispatch logic is unchanged.
    var lookback = 0, j = i - 1;
    while (j >= 0 && lookback < 3) {
      var prevWrap = wrappers[j];
      // Detect agent-side row (row-reverse flexDirection).
      var prevRowAny = prevWrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
      if (prevRowAny &&
          (prevRowAny.style.flexDirection || '').indexOf('reverse') !== -1) {
        break;  // agent reply already happened — don't reach across
      }
      var prevRow = _customerBubble(prevWrap);
      if (!prevRow) { j--; continue; }  // system/notice — skip, keep walking
      var prevAtts = _collectAttachments(prevRow);
      if (prevAtts.length) {
        // Prepend so visual order is preserved (older bubble first).
        attachments = prevAtts.concat(attachments);
      }
      lookback++;
      j--;
    }
    var tsEl = wrap.querySelector('.O4UWWFoQxgMq4AWHMq25');
    var ts = tsEl ? tsEl.textContent.trim() : '';
    var msgIdEl = wrap.querySelector('[data-id]');
    var msgId = msgIdEl ? msgIdEl.getAttribute('data-id') : '';
    return JSON.stringify({
      text: text,
      msg_id: msgId,
      timestamp: ts,
      index: i,
      attachments: attachments
    });
  }
  return JSON.stringify({ text: '', msg_id: '', timestamp: '', index: -1, attachments: [] });
})()
"""


# ---------------------------------------------------------------------------
# JS snippet — click the sidebar row whose name matches ``customer_name``.
#
# Used by PreDispatch before scraping to guarantee the chat pane is
# focused on the customer we're about to dispatch for — in Feige the
# chat pane is a single-focus region, so scraping without clicking first
# would pick up whatever other customer happened to be displayed.
# Returns JSON with ``{ok, name, already_active}``.
#
# **Caller contract**: replace the literal token ``CUSTOMER_NAME`` with
# ``json.dumps(name, ensure_ascii=False)`` before evaluating.
# ---------------------------------------------------------------------------
FEIGE_CLICK_SIDEBAR_ROW_JS: str = r"""
(function(customerName) {
  // Extract the customer display name from a chat-list row.  Real Feige
  // (and the emulation that mirrors it) renders the name in two
  // redundant places:
  //   • <div class="MP1bk3ccfHC9V2SnPCGD" title="客户C">…</div>
  //     — wrapper carrying the exact name in its `title` attribute
  //   • <span class="Jv6FtqUv5VoYARd2pp4y">客户C</span>
  //     — inner span with the name as its textContent
  // The row also contains tags, a timestamp, the last-message preview
  // and an unread badge — so comparing against `row.textContent` as a
  // last-ditch fallback is meaningless (`"客户C重复来访2分钟质量怎么样？1"`
  // never equals `"客户C"`).  We therefore only accept a name from one
  // of the precise name nodes and leave an explicit diagnostic when no
  // node matches, to make future selector drift obvious in logs.
  function readName(row) {
    var wrap = row.querySelector('.MP1bk3ccfHC9V2SnPCGD');
    if (wrap) {
      var t = wrap.getAttribute('title');
      if (t && t.trim()) return t.trim();
    }
    var span = row.querySelector('.Jv6FtqUv5VoYARd2pp4y');
    if (span) {
      var s = (span.textContent || '').trim();
      if (s) return s;
    }
    // Legacy selector kept as a last resort in case real Feige ever
    // ships it; the emulation and current production DOM do not.
    var legacy = row.querySelector('[data-qa-id="qa-conversation-nickname"]');
    if (legacy) {
      var l = (legacy.textContent || '').trim();
      if (l) return l;
    }
    return '';
  }
  function rowIsCurrent(row) {
    var btm = row && row.getAttribute ? String(row.getAttribute('data-btm-id') || '') : '';
    if (btm.endsWith('.current')) return true;
    if (btm.endsWith('.recent') || btm.endsWith('.systemConv')) return false;
    if (row && row.closest && row.closest('.pigeonChatNotScrollBox')) return true;
    if (row && row.closest && row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  var items = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
    .filter(rowIsCurrent);
  var target = null;
  var seenNames = [];
  for (var i = 0; i < items.length; i++) {
    var nm = readName(items[i]);
    if (nm) seenNames.push(nm);
    if (nm === customerName) { target = items[i]; break; }
  }
  if (!target) {
    return JSON.stringify({
      ok: false,
      name: customerName,
      already_active: false,
      diagnostics: { item_count: items.length, seen_names: seenNames.slice(0, 20) }
    });
  }
  var alreadyActive = target.classList.contains('active') ||
                      (target.className || '').toLowerCase().indexOf('active') >= 0;
  if (!alreadyActive) target.click();
  return JSON.stringify({ ok: true, name: customerName, already_active: alreadyActive });
})(CUSTOMER_NAME)
"""


# ---------------------------------------------------------------------------
# Verification policy — strict dual-signal match.
# ---------------------------------------------------------------------------
def verify_customer_match(verify_result: dict, expected_name: str) -> tuple[bool, str]:
    """Zero-risk verification policy for HOT-PATH-B.

    Given the JSON dict returned by ``FEIGE_ACTIVE_CUSTOMER_JS`` and the
    expected customer name, decide whether it is safe to send a reply.

    Returns ``(ok: bool, reason: str)`` where *reason* is a human-readable
    summary suitable for logging.

    Policy (strict — customer service is mission-critical):
      PASS iff  (sidebar_name == expected OR sidebar_name == "")
            AND (header_name  == expected OR header_name  == "")
            AND (sidebar_name == expected OR header_name  == expected)
    i.e. *at least one* signal must affirmatively identify the expected
    customer, and *neither* signal may name a different customer.
    """
    if not isinstance(verify_result, dict):
        return False, f"verify-result-not-dict: {type(verify_result).__name__}"
    sidebar = _normalize_dispatch_identity_key(str(verify_result.get("sidebar_name") or "").strip())
    header = _normalize_dispatch_identity_key(str(verify_result.get("header_name") or "").strip())
    expected = _normalize_dispatch_identity_key(str(expected_name or "").strip())
    method = str(verify_result.get("sidebar_method") or "unknown")
    if not expected:
        return False, "expected-empty"

    sidebar_ok = (sidebar == expected)
    header_ok = (header == expected)
    sidebar_conflicts = (sidebar != "" and not sidebar_ok)
    header_conflicts = (header != "" and not header_ok)

    if sidebar_conflicts or header_conflicts:
        return False, (
            f"conflict expected={expected!r} "
            f"sidebar={sidebar!r}({method}) header={header!r}"
        )
    if not (sidebar_ok or header_ok):
        return False, (
            f"no-affirmative-signal expected={expected!r} "
            f"sidebar={sidebar!r}({method}) header={header!r}"
        )
    return True, (
        f"ok expected={expected!r} sidebar={sidebar!r}({method}) header={header!r}"
    )


_FEIGE_SELECT_CURRENT_TAB_JS: str = r"""
(function() {
  function rowIsCurrent(row) {
    var btm = row && row.getAttribute ? String(row.getAttribute('data-btm-id') || '') : '';
    if (btm.endsWith('.current')) return true;
    if (btm.endsWith('.recent') || btm.endsWith('.systemConv')) return false;
    if (row && row.closest && row.closest('.pigeonChatNotScrollBox')) return true;
    if (row && row.closest && row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  function countCurrentRows() {
    return Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
      .filter(rowIsCurrent).length;
  }
  var current = document.querySelector('[data-qa-id="qa-active-chat-tab"]');
  if (!current) {
    return JSON.stringify({ ok: false, reason: 'current_tab_not_found', current_rows: countCurrentRows() });
  }
  var tabBtn = current.closest('[role="tab"]');
  var tabWrap = current.closest('.auxo-tabs-tab, .tab');
  var selected =
    (tabBtn && tabBtn.getAttribute('aria-selected') === 'true') ||
    (tabWrap && /\b(auxo-tabs-tab-active|active)\b/.test(String(tabWrap.className || '')));
  if (!selected) current.click();
  return JSON.stringify({ ok: true, clicked: !selected, current_rows: countCurrentRows() });
})()
"""


async def _ensure_feige_current_subtab(browser_session) -> None:
    """Best-effort keep Feige on the live Current Conversations sidebar."""
    import asyncio as _ct_asyncio
    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            _evaluate_js as _ct_eval_js,
        )
    except Exception as _imp_err:
        logger.debug(
            f"[BrowserAutomation] ensure-feige-current-tab: _evaluate_js import failed: {_imp_err}"
        )
        return

    try:
        raw = await _ct_eval_js(browser_session, _FEIGE_SELECT_CURRENT_TAB_JS)
        data = raw
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
        if isinstance(data, dict) and data.get("clicked"):
            await _ct_asyncio.sleep(0.2)
            logger.info(
                f"[BrowserAutomation] ensure-feige-current-tab: clicked current tab "
                f"(current_rows_before={data.get('current_rows')})"
            )
        elif isinstance(data, dict) and data.get("ok"):
            logger.debug(
                f"[BrowserAutomation] ensure-feige-current-tab: already on current tab "
                f"(current_rows={data.get('current_rows')})"
            )
        else:
            logger.debug(
                f"[BrowserAutomation] ensure-feige-current-tab: no current tab "
                f"(result={data!r})"
            )
    except Exception as _err:
        logger.debug(f"[BrowserAutomation] ensure-feige-current-tab failed: {_err}")


# ---------------------------------------------------------------------------
# Tab-focus helper — ensure the session is on a Feige tab before running
# any DOM query.  Without this the JS below silently returns empty and
# the caller falls back to the (often stale) sidebar preview text.
# ---------------------------------------------------------------------------
async def ensure_feige_tab_focused(browser_session) -> bool:
    """Switch *browser_session* to its Feige (``im.jinritemai.com``) tab if
    it isn't already focused there.  Returns ``True`` when the active
    page contains ``im.jinritemai.com`` in its URL after the call,
    ``False`` otherwise (e.g. no Feige tab open).

    Also clicks the current-conversation inner sub-tab when present.  Recent
    Contacts uses the same row selectors for historical/system rows, so it is
    not a safe source for real-time dispatch.
    """
    import asyncio as _ef_asyncio
    try:
        page = await browser_session.get_current_page()
        cur_url = ""
        try:
            cur_url = page.url if page else ""
        except Exception:
            cur_url = ""
        if "im.jinritemai.com" in (cur_url or ""):
            await _ensure_feige_current_subtab(browser_session)
            return True

        # Fast-path: cached Feige target_id (added 2026-04-30 19:00,
        # corrected 2026-04-30 23:45).
        # page.url is empty under this browser_use version so the URL
        # guard above never fires.  We can skip the expensive target scan
        # when the cached target is still alive, but we must still refocus
        # the CDP session.  Returning True here without a synchronous
        # ``get_or_create_cdp_session(target_id=..., focus=True)`` leaves
        # later Runtime.evaluate calls pointed at a stale tab; under flood
        # that made active-customer checks read ``active=''`` and jam direct
        # delivery behind repeated 24s timeouts.
        _cached_tid = getattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, None)
        if _cached_tid:
            try:
                _sm_fast = getattr(browser_session, "session_manager", None)
                _all_fast = _sm_fast.get_all_targets() if _sm_fast else {}
            except Exception:
                _all_fast = {}
            _cached_tgt = (_all_fast or {}).get(_cached_tid)
            if _cached_tgt is not None:
                _cached_url = str(getattr(_cached_tgt, "url", "") or "")
                if "im.jinritemai.com" in _cached_url:
                    try:
                        async with _session_focus_lock(browser_session):
                            async with session_cdp_operation_lock(browser_session):
                                if hasattr(browser_session, "get_or_create_cdp_session"):
                                    await _ef_asyncio.wait_for(
                                        browser_session.get_or_create_cdp_session(
                                            target_id=_cached_tid, focus=True
                                        ),
                                        timeout=_FOCUS_TARGET_TIMEOUT_S,
                                    )
                                else:
                                    from browser_use.browser.events import SwitchTabEvent as _EF_STE
                                    await browser_session.event_bus.dispatch(
                                        _EF_STE(target_id=_cached_tid)
                                    )
                                    await _ef_asyncio.sleep(0.3)
                        logger.debug(
                            f"[BrowserAutomation] ensure-feige-tab: refocused "
                            f"cached Feige tab (target=...{str(_cached_tid)[-6:]})"
                        )
                        await _ensure_feige_current_subtab(browser_session)
                        return True
                    except _ef_asyncio.TimeoutError:
                        logger.warning(
                            f"[BrowserAutomation] ensure-feige-tab: cached "
                            f"focus-target TIMEOUT after {_FOCUS_TARGET_TIMEOUT_S:.0f}s "
                            f"(target=...{str(_cached_tid)[-6:]})"
                        )
                        clear_feige_tab_focus_cache(
                            browser_session,
                            "cached focus-target timeout",
                        )
                        return False
                    except Exception as _cached_focus_err:
                        logger.info(
                            f"[BrowserAutomation] ensure-feige-tab: cached "
                            f"focus-target failed (target=...{str(_cached_tid)[-6:]}): "
                            f"{_cached_focus_err}"
                        )
                        try:
                            setattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, None)
                        except Exception:
                            pass
                        return False
            try:
                setattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, None)
            except Exception:
                pass

        sm = getattr(browser_session, "session_manager", None)
        all_targets = sm.get_all_targets() if sm else {}
        feige_candidates: list[tuple[str, str]] = []
        _scan_count = 0
        for tid, tgt in (all_targets or {}).items():
            if getattr(tgt, "target_type", "") not in ("page", "tab"):
                continue
            _scan_count += 1
            turl = str(getattr(tgt, "url", "") or "")
            if "im.jinritemai.com" in turl:
                feige_candidates.append((str(tid), turl))
        if not feige_candidates:
            logger.info(
                f"[BrowserAutomation] ensure-feige-tab: no Feige tab among "
                f"{_scan_count} page/tab targets (cur_url={cur_url!r})"
            )
            clear_feige_tab_focus_cache(browser_session, "focus-target timeout")
            return False
        # ── Prefer the main sidebar-carrying tab over per-session tabs ──
        # PreDispatch opens a new tab per customer session via
        # ``NavigateToUrlEvent(chat_url, new_tab=True)`` where
        # ``chat_url`` contains ``im.jinritemai.com`` plus a session
        # path.  The first-match loop (pre-2026-04-23) sometimes picked
        # those per-session tabs, which have no
        # ``[data-qa-id="qa-conversation-chat-item"]`` sidebar — making
        # the downstream ``feige_open_session`` fail with
        # ``Session not found`` and freezing every HOT-PATH-B reply.
        #
        # Heuristic: rank candidates by the number of non-empty path
        # segments that follow ``im.jinritemai.com``.  The main tab has
        # the shortest path (bare ``/`` or a short app root like
        # ``/pc/chat``); per-session URLs carry extra session-id
        # segments and therefore score higher (worse).  Ties fall back
        # to insertion order (the main tab is usually opened first).
        import re as _ef_re
        def _path_depth(url: str) -> int:
            m = _ef_re.search(r"im\.jinritemai\.com(/[^?#]*)?", url)
            if not m:
                return 999
            path = (m.group(1) or "/").strip("/")
            return 0 if not path else path.count("/") + 1
        feige_candidates.sort(key=lambda c: _path_depth(c[1]))
        logger.info(
            f"[BrowserAutomation] ensure-feige-tab: {len(feige_candidates)} "
            f"Feige candidate(s) of {_scan_count} page/tab targets: "
            + ", ".join(
                f"...{tid[-6:]}(d={_path_depth(url)}, url={url!r})"
                for tid, url in feige_candidates
            )
        )
        # ── Multi-candidate disambiguation (added 2026-04-23) ──
        # When multiple Feige tabs exist at the same path depth (e.g.
        # two tabs both at ``http://.../im.jinritemai.com/`` — a
        # scenario observed tonight that caused the monitor to lock
        # onto an empty duplicate tab), the shortest-path sort falls
        # back to insertion order which is unreliable.  Probe each
        # candidate's sidebar row count via CDP (without moving agent
        # focus) and prefer the populated tab.  Ties broken by path
        # depth.
        if len(feige_candidates) > 1 and hasattr(
            browser_session, "get_or_create_cdp_session"
        ):
            _row_count_js = (
                "(function(){return document.querySelectorAll("
                "'[data-qa-id=\"qa-conversation-chat-item\"]').length;})()"
            )

            async def _probe_rows(tid: str) -> int:
                """Return row count on *tid* without touching agent focus.
                Returns -1 when the probe fails (e.g. target gone,
                CDP session unavailable) so the caller can treat it
                as "unknown" rather than "zero".
                """
                try:
                    import asyncio as _probe_asyncio

                    async def _run_probe():
                        cdp_sess = await browser_session.get_or_create_cdp_session(
                            target_id=tid, focus=False
                        )
                        if cdp_sess is None:
                            return None
                        cdp_client = getattr(cdp_sess, "cdp_client", None)
                        session_id = getattr(cdp_sess, "session_id", None)
                        if cdp_client is None or session_id is None:
                            return None
                        await cdp_client.send.Runtime.enable(session_id=session_id)
                        return await cdp_client.send.Runtime.evaluate(
                            params={
                                "expression": _row_count_js,
                                "returnByValue": True,
                            },
                            session_id=session_id,
                        )

                    async with session_cdp_operation_lock(browser_session):
                        result = await _probe_asyncio.wait_for(
                            _run_probe(),
                            timeout=_CDP_OPERATION_PROBE_TIMEOUT_S,
                        )
                    if result is None:
                        return -1
                    val = (result.get("result") or {}).get("value")
                    return int(val) if isinstance(val, (int, float)) else -1
                except Exception as _probe_exc:
                    logger.debug(
                        f"[BrowserAutomation] ensure-feige-tab: row-probe "
                        f"failed for target=...{tid[-6:]}: {_probe_exc}"
                    )
                    return -1

            # (rows, depth, tid, url)
            _probed: list[tuple[int, int, str, str]] = []
            for _tid, _url in feige_candidates:
                _rows = await _probe_rows(_tid)
                _probed.append((_rows, _path_depth(_url), _tid, _url))
            # Rank: highest rows first (unknown = -1 treated as 0 so it
            # loses to any positive count); ties broken by path depth.
            _probed.sort(key=lambda r: (-(max(r[0], 0)), r[1]))
            logger.info(
                "[BrowserAutomation] ensure-feige-tab: multi-candidate "
                "row-probe: "
                + ", ".join(
                    f"...{tid[-6:]}(rows={rows}, d={depth})"
                    for rows, depth, tid, _u in _probed
                )
            )
            feige_candidates = [(tid, url) for _r, _d, tid, url in _probed]

        feige_tid, _feige_url = feige_candidates[0]
        # Directly acquire a CDP session for the Feige target and update
        # agent focus synchronously.  Previously this used
        # ``SwitchTabEvent`` via the event bus, but that runs
        # asynchronously while ``_evaluate_js`` calls
        # ``get_or_create_cdp_session()`` with no target_id — which falls
        # back to ``agent_focus_target_id``.  The race meant JS ran
        # against the front-desk's stale focused tab, not Feige,
        # producing persistent ``selector_not_found`` for every Feige
        # selector.  ``get_or_create_cdp_session(target_id=..., focus=True)``
        # is awaited and guarantees ``agent_focus_target_id`` points at
        # the Feige tab before returning.
        # ── Hang-bound (2026-04-28): same deadlock class as the
        # ``get_browser_state_summary`` call in
        # ``browser_node/runner.py:4376-4395`` — under target detach /
        # high CDP concurrency this await has been observed to block
        # for 3+ s while the parent persistent-worker run is racing
        # post-preflight on the same target.  When the parent is then
        # cancelled mid-await, the ``CancelledError`` propagates past
        # every ``except Exception`` block in HOT-PATH-B (CancelledError
        # is BaseException, not Exception in Python 3.8+), which
        # silently kills the typing into the customer's tab — the
        # "cejs reply never arrives" regression observed
        # 2026-04-28 05:17:27 (eCan.log.2 lines 1218-1462).  Bound the
        # focus call with a 3 s budget; on timeout treat as focus-failure
        # and let the caller continue through the guarded open/send path.
        # Per-session asyncio.Lock serializes contending callers so each
        # focus request gets a clean CDP turn instead of racing.
        try:
            async with _session_focus_lock(browser_session):
                async with session_cdp_operation_lock(browser_session):
                    if hasattr(browser_session, "get_or_create_cdp_session"):
                        await _ef_asyncio.wait_for(
                            browser_session.get_or_create_cdp_session(
                                target_id=feige_tid, focus=True
                            ),
                            timeout=_FOCUS_TARGET_TIMEOUT_S,
                        )
                    else:
                    # Fallback for legacy BrowserSession API without the
                    # method — fire the event and sleep as before.
                        from browser_use.browser.events import SwitchTabEvent as _EF_STE
                        await browser_session.event_bus.dispatch(_EF_STE(target_id=feige_tid))
                        await _ef_asyncio.sleep(0.3)
        except _ef_asyncio.TimeoutError:
            logger.warning(
                f"[BrowserAutomation] ensure-feige-tab: focus-target TIMEOUT "
                f"after {_FOCUS_TARGET_TIMEOUT_S:.0f}s (target=...{feige_tid[-6:]}) — CDP session "
                f"contended; HOT-PATH-B will proceed to the guarded "
                f"open/send path"
            )
            clear_feige_tab_focus_cache(browser_session, "focus-target timeout")
            return False
        except Exception as _focus_err:
            logger.info(
                f"[BrowserAutomation] ensure-feige-tab: focus-target failed "
                f"(target=...{feige_tid[-6:]}): {_focus_err}"
            )
            clear_feige_tab_focus_cache(browser_session, "focus-target failed")
            return False
        logger.info(
            f"[BrowserAutomation] ensure-feige-tab: focused Feige tab "
            f"(target=...{feige_tid[-6:]}, was cur_url={cur_url!r})"
        )
        try:
            setattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, feige_tid)
        except Exception:
            pass
        await _ensure_feige_current_subtab(browser_session)
        return True
        # ── Sub-tab resolution (rewritten 2026-04-23) ──
        # The sidebar row selector ``[data-qa-id="qa-conversation-chat-item"]``
        # only returns rows on specific sub-tabs.  The emulator has two:
        # ``当前会话`` (``data-tab="current"``) holds customers with
        # active unread messages; ``最近联系`` (``data-tab="recent"``)
        # holds recent-contacts history and is usually empty.  Real
        # Feige uses ``[data-qa-id="qa-last-chat-tab"]`` as its primary
        # list.
        #
        # The previous logic blindly clicked ``最近联系`` regardless of
        # current state.  When the emulator landed on a populated
        # ``当前会话`` (the common case after human-takeover of a
        # customer), that click switched away to the empty
        # recent-contacts view and produced ``items=0``; downstream
        # ``feige_open_session`` then failed with ``Session not found``
        # — the stuck-message regression observed 20:57-21:12 on
        # 2026-04-23.
        #
        # New strategy: if the current sub-tab already has chat-item
        # rows, do nothing (common case).  Otherwise try candidate
        # selectors in priority order, clicking each and polling for
        # up to ~450 ms for rows to appear; settle on the first
        # populated one.  If all candidates produce an empty sidebar,
        # log WARN with DOM diagnostics and return True anyway (the
        # caller may still navigate by ``customer_name`` as a last
        # resort).
        try:
            from agent.ec_skills.browser_use_extension.extension_tools_service import (
                _evaluate_js as _ef_eval_js,
            )
            _count_rows_js = (
                "(function(){return JSON.stringify({count:"
                "document.querySelectorAll("
                "'[data-qa-id=\"qa-conversation-chat-item\"]').length});})()"
            )

            async def _row_count() -> int:
                try:
                    r = await _ef_eval_js(browser_session, _count_rows_js)
                    if isinstance(r, str):
                        r = json.loads(r)
                    return int((r or {}).get("count") or 0)
                except Exception:
                    return 0

            pre_count = await _row_count()
            if pre_count > 0:
                logger.debug(
                    f"[BrowserAutomation] ensure-feige-tab: sub-tab "
                    f"already populated ({pre_count} rows); no click needed"
                )
                return True

            # Priority-ordered (selector, short-name).  Order favours
            # "active/current" sessions over "recent" history so we
            # land on whichever sub-tab holds the live customer list
            # first.  Selectors covering both emulator and real Feige.
            _candidates = [
                ('.tab[data-tab="current"]',             'tab=current'),
                ('[data-qa-id="qa-last-chat-tab"]',      'qa-last-chat-tab'),
                ('.tab[data-tab="recent"]',              'tab=recent'),
                ('[data-tab="current"]',                 'loose-current'),
                ('[data-tab="recent"]',                  'loose-recent'),
            ]
            # Also cover plain-text fallbacks for both labels.
            _text_fallbacks = [
                ('当前会话',   'text:当前会话'),
                ('最近联系',   'text:最近联系'),
                ('最近联系人', 'text:最近联系人'),
            ]
            _click_tab_js = r"""
(function(sel) {
  var el = document.querySelector(sel);
  if (!el) return JSON.stringify({ok:false, reason:'not_found'});
  var cls = (el.className || '').toLowerCase();
  var alreadyActive = cls.indexOf('active') >= 0 ||
                      (el.classList && el.classList.contains('active'));
  if (!alreadyActive) el.click();
  return JSON.stringify({ok:true, already_active:alreadyActive});
})(SELECTOR)
"""
            _click_text_js = r"""
(function(label) {
  var nodes = document.querySelectorAll(
    'button, div[role="button"], [class*="tab"], a, span'
  );
  for (var j = 0; j < nodes.length; j++) {
    var t = (nodes[j].textContent || '').trim();
    if (t === label) {
      var el = nodes[j];
      var cls = (el.className || '').toLowerCase();
      var alreadyActive = cls.indexOf('active') >= 0 ||
                          (el.classList && el.classList.contains('active'));
      if (!alreadyActive) el.click();
      return JSON.stringify({ok:true, already_active:alreadyActive});
    }
  }
  return JSON.stringify({ok:false, reason:'text_not_found'});
})(LABEL)
"""

            async def _try_click(js_src: str, placeholder: str, value: str):
                """Click helper: substitute *value* (JSON-quoted) into
                ``js_src`` at ``placeholder`` and evaluate.  Returns
                the decoded dict or ``{}``.
                """
                try:
                    script = js_src.replace(placeholder, json.dumps(value))
                    r = await _ef_eval_js(browser_session, script)
                    if isinstance(r, str):
                        r = json.loads(r)
                    return r if isinstance(r, dict) else {}
                except Exception as _exc:
                    logger.debug(
                        f"[BrowserAutomation] ensure-feige-tab: click "
                        f"eval error for {value!r}: {_exc}"
                    )
                    return {}

            settled_on = ""
            tried: list[str] = []
            # Phase 1: selector-based candidates.
            for sel, name in _candidates:
                tried.append(name)
                cres = await _try_click(_click_tab_js, "SELECTOR", sel)
                if not cres.get("ok"):
                    continue
                if not cres.get("already_active"):
                    await _ef_asyncio.sleep(0.15)
                count_after = 0
                for _ in range(6):
                    count_after = await _row_count()
                    if count_after > 0:
                        break
                    await _ef_asyncio.sleep(0.075)
                if count_after > 0:
                    settled_on = name
                    logger.info(
                        f"[BrowserAutomation] ensure-feige-tab: settled "
                        f"on sub-tab={name!r} with {count_after} rows "
                        f"(already_active={cres.get('already_active')})"
                    )
                    break

            # Phase 2: text-content fallbacks, only if no selector worked.
            if not settled_on:
                for label, name in _text_fallbacks:
                    tried.append(name)
                    cres = await _try_click(_click_text_js, "LABEL", label)
                    if not cres.get("ok"):
                        continue
                    if not cres.get("already_active"):
                        await _ef_asyncio.sleep(0.15)
                    count_after = 0
                    for _ in range(6):
                        count_after = await _row_count()
                        if count_after > 0:
                            break
                        await _ef_asyncio.sleep(0.075)
                    if count_after > 0:
                        settled_on = name
                        logger.info(
                            f"[BrowserAutomation] ensure-feige-tab: settled "
                            f"on text-tab={name!r} with {count_after} rows "
                            f"(already_active={cres.get('already_active')})"
                        )
                        break

            if not settled_on:
                _diag_js = r"""
(function() {
  var qaIds = [];
  var qaNodes = document.querySelectorAll('[data-qa-id]');
  for (var k = 0; k < qaNodes.length && qaIds.length < 40; k++) {
    var v = qaNodes[k].getAttribute('data-qa-id') || '';
    if (v && qaIds.indexOf(v) < 0) qaIds.push(v);
  }
  var tabBar = document.querySelector(
    '#tabBar, .tab-bar, [class*="tabBar"], [class*="TabBar"]'
  );
  return JSON.stringify({
    url: (location && location.href) || '',
    data_qa_ids: qaIds,
    tab_bar_html: tabBar ? (tabBar.outerHTML || '').slice(0, 800) : '',
    chat_item_count: document.querySelectorAll(
      '[data-qa-id="qa-conversation-chat-item"]'
    ).length
  });
})()
"""
                try:
                    diag = await _ef_eval_js(browser_session, _diag_js)
                    if isinstance(diag, str):
                        diag = json.loads(diag)
                    diag = diag if isinstance(diag, dict) else {}
                except Exception:
                    diag = {}
                logger.warning(
                    f"[BrowserAutomation] ensure-feige-tab: all "
                    f"{len(tried)} sub-tab candidates produced empty "
                    f"sidebar (tried={tried}); proceeding anyway "
                    f"(url={diag.get('url')!r}, "
                    f"chat_items={diag.get('chat_item_count')}, "
                    f"data_qa_ids={diag.get('data_qa_ids')}, "
                    f"tab_bar={(diag.get('tab_bar_html') or '')[:400]!r})"
                )
        except Exception as _tab_err:
            logger.info(
                f"[BrowserAutomation] ensure-feige-tab: sub-tab "
                f"resolution failed: {_tab_err}"
            )
        return True
    except Exception as _err:
        logger.info(f"[BrowserAutomation] ensure-feige-tab: exception: {_err}")
        return False


# ---------------------------------------------------------------------------
# Scrape latest customer bubble — focuses the chat pane on *customer_name*
# and extracts the most recent customer bubble.  The typing-lock guard
# (Phase 3 migration target) is injected via ``typing_holder_getter``.
# ---------------------------------------------------------------------------
async def scrape_latest_customer_bubble(
    browser_session,
    customer_name: str,
    *,
    typing_holder_getter: Callable[[], str] | None = None,
) -> dict:
    """Focus the chat pane on *customer_name* and return the most recent
    customer bubble.

    Returns a dict ``{text, msg_id, timestamp, index, scrape_ok}``.
    ``scrape_ok`` is ``False`` when the sidebar row could not be clicked
    or the thread DOM contained no customer bubbles — callers should
    fall back to the sidebar preview in that case.

    When *typing_holder_getter* is provided and returns a non-empty
    customer key, the helper yields immediately and returns
    ``scrape_ok=False``. Even the same customer is unsafe here: the
    send path may be between open-session and send-message, and a
    concurrent scrape can still contend on CDP or disturb focus.
    """
    import asyncio as _s_asyncio
    empty = {
        "text": "",
        "msg_id": "",
        "timestamp": "",
        "index": -1,
        "attachments": [],
        "scrape_ok": False,
        "skip_dispatch": False,
        "skip_reason": "",
    }
    if not browser_session or not customer_name:
        return empty

    # ── Feige active-session race guard ──
    # If a reply is currently being typed, skip our sidebar click. The
    # caller should retry later instead of consuming stale sidebar
    # previews while the write path owns the browser.
    if typing_holder_getter is not None:
        try:
            _st_holder = typing_holder_getter()
            if _st_holder:
                logger.info(
                    f"[BrowserAutomation] scrape-latest-customer: yield - "
                    f"Feige typing lock held by {_st_holder!r}; skipping "
                    f"sidebar click for {customer_name!r} (caller should retry)"
                )
                return empty
        except Exception as _st_err:
            logger.debug(
                f"[BrowserAutomation] scrape-latest-customer: typing-lock check "
                f"failed (non-fatal): {_st_err}"
            )

    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            _evaluate_js as _s_eval_js,
        )
    except Exception as _imp_err:
        logger.info(
            f"[BrowserAutomation] scrape-latest-customer: _evaluate_js import "
            f"failed for {customer_name!r}: {_imp_err}"
        )
        return empty

    # Ensure we are on Feige before running any JS — otherwise queries
    # return empty and we silently fall back to the (often stale)
    # sidebar preview.
    if not await ensure_feige_tab_focused(browser_session):
        logger.info(
            f"[BrowserAutomation] scrape-latest-customer: no Feige tab focusable "
            f"for {customer_name!r} — falling back to sidebar preview"
        )
        return empty

    # Re-check after focusing and immediately before any sidebar click.
    # Direct delivery can claim the lock between the initial guard above
    # and this point; without this second check the scraper can still
    # steal focus from a send that is about to type.
    if typing_holder_getter is not None:
        try:
            _st_holder = typing_holder_getter()
            if _st_holder:
                logger.info(
                    f"[BrowserAutomation] scrape-latest-customer: yield - "
                    f"Feige typing lock held by {_st_holder!r}; skipping "
                    f"pre-click scrape for {customer_name!r}"
                )
                return empty
        except Exception as _st_err:
            logger.debug(
                f"[BrowserAutomation] scrape-latest-customer: pre-click "
                f"typing-lock check failed (non-fatal): {_st_err}"
            )

    try:
        _click_js = FEIGE_CLICK_SIDEBAR_ROW_JS.replace(
            "CUSTOMER_NAME", json.dumps(customer_name, ensure_ascii=False)
        )
        click_raw = await _s_eval_js(browser_session, _click_js)
        if isinstance(click_raw, str):
            try:
                click_data = json.loads(click_raw)
            except Exception:
                click_data = {}
        else:
            click_data = click_raw if isinstance(click_raw, dict) else {}
        if not click_data.get("ok"):
            _diag = click_data.get("diagnostics") or {}
            logger.info(
                f"[BrowserAutomation] scrape-latest-customer: sidebar row not found "
                f"for {customer_name!r} — falling back to sidebar preview "
                f"(item_count={_diag.get('item_count')!r}, "
                f"seen_names={_diag.get('seen_names')!r})"
            )
            return empty
        # Brief settle so the chat pane repaints after clicking a row.
        if not click_data.get("already_active"):
            await _s_asyncio.sleep(0.35)
        verify_ok = False
        verify_reason = ""
        verify_data = {}
        for _attempt in range(2):
            verify_raw = await _s_eval_js(browser_session, FEIGE_ACTIVE_CUSTOMER_JS)
            if isinstance(verify_raw, str):
                try:
                    verify_data = json.loads(verify_raw)
                except Exception:
                    verify_data = {}
            else:
                verify_data = verify_raw if isinstance(verify_raw, dict) else {}
            verify_ok, verify_reason = verify_customer_match(
                verify_data, customer_name
            )
            if verify_ok:
                break
            if _attempt == 0:
                await _s_asyncio.sleep(0.25)
        if not verify_ok:
            logger.info(
                f"[BrowserAutomation] scrape-latest-customer: active-customer "
                f"verification mismatch after sidebar click for {customer_name!r}; "
                "retrying click once"
            )
            retry_raw = await _s_eval_js(browser_session, _click_js)
            if isinstance(retry_raw, str):
                try:
                    retry_data = json.loads(retry_raw)
                except Exception:
                    retry_data = {}
            else:
                retry_data = retry_raw if isinstance(retry_raw, dict) else {}
            if retry_data.get("ok"):
                if not retry_data.get("already_active"):
                    await _s_asyncio.sleep(0.5)
                for _attempt in range(3):
                    verify_raw = await _s_eval_js(
                        browser_session, FEIGE_ACTIVE_CUSTOMER_JS
                    )
                    if isinstance(verify_raw, str):
                        try:
                            verify_data = json.loads(verify_raw)
                        except Exception:
                            verify_data = {}
                    else:
                        verify_data = verify_raw if isinstance(verify_raw, dict) else {}
                    verify_ok, verify_reason = verify_customer_match(
                        verify_data, customer_name
                    )
                    if verify_ok:
                        break
                    if _attempt < 2:
                        await _s_asyncio.sleep(0.25)
        if not verify_ok:
            logger.warning(
                f"[BrowserAutomation] scrape-latest-customer: active-customer "
                f"verification failed after sidebar click for {customer_name!r}; "
                f"refusing thread scrape and dispatch "
                f"(reason={verify_reason}, verify={verify_data!r})"
            )
            blocked = dict(empty)
            blocked["skip_dispatch"] = True
            blocked["skip_reason"] = "active_customer_mismatch"
            blocked["verify_reason"] = verify_reason
            return blocked
        scrape_raw = await _s_eval_js(browser_session, FEIGE_LATEST_CUSTOMER_BUBBLE_JS)
        if isinstance(scrape_raw, str):
            try:
                data = json.loads(scrape_raw)
            except Exception:
                data = {}
        else:
            data = scrape_raw if isinstance(scrape_raw, dict) else {}
        text = str(data.get("text") or "").strip()
        msg_id = str(data.get("msg_id") or "").strip()
        idx = int(data.get("index", -1) or -1)
        # Attachments — list of {kind, url, alt}.  Defensive coercion:
        # the JS may, on selector drift, return missing key or non-list.
        raw_atts = data.get("attachments") or []
        attachments: list[dict] = []
        if isinstance(raw_atts, list):
            for a in raw_atts:
                if not isinstance(a, dict):
                    continue
                url = str(a.get("url") or "").strip()
                if not url:
                    continue
                attachments.append({
                    "kind": str(a.get("kind") or "image"),
                    "url": url,
                    "alt": str(a.get("alt") or ""),
                })
        # Bubble counts as a customer message if it has text or attachments.
        # Image-only bubbles (text == '') were silently dropped before this.
        if not text and not attachments:
            logger.info(
                f"[BrowserAutomation] scrape-latest-customer: thread had no customer "
                f"bubble for {customer_name!r} (index={idx}) — falling back"
            )
            return empty
        logger.info(
            f"[BrowserAutomation] scrape-latest-customer: {customer_name!r} "
            f"latest_bubble msg_id=...{msg_id[-8:] if msg_id else '<none>'} "
            f"text={text[:40]!r} attachments={len(attachments)}"
        )
        return {
            "text": text,
            "msg_id": msg_id,
            "timestamp": str(data.get("timestamp") or "").strip(),
            "index": idx,
            "attachments": attachments,
            "scrape_ok": True,
        }
    except Exception as _err:
        logger.info(
            f"[BrowserAutomation] scrape-latest-customer: JS eval failed for "
            f"{customer_name!r}: {_err}"
        )
        return empty


__all__ = [
    "FEIGE_ACTIVE_CUSTOMER_JS",
    "FEIGE_LATEST_CUSTOMER_BUBBLE_JS",
    "FEIGE_CLICK_SIDEBAR_ROW_JS",
    "verify_customer_match",
    "clear_feige_tab_focus_cache",
    "resolve_feige_tab_target_id",
    "session_cdp_operation_lock",
    "ensure_feige_tab_focused",
    "scrape_latest_customer_bubble",
]
