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
    URL match) and clicks the ``最近联系`` sub-tab if present.

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
from typing import Any, Callable

logger = logging.getLogger("eCan")


# ---------------------------------------------------------------------------
# Minimal utilities — duplicated from build_node.py to avoid a core->bundle
# import edge.  Keep bodies byte-identical so future deduplication via a
# shared util module is a trivial delete.
# ---------------------------------------------------------------------------

def _normalize_customer_id(raw_id: str) -> str:
    """Strip the message-preview suffix (``"sc|..."``) from a customer id.

    Mirrors ``build_node._normalize_customer_id`` exactly.  See that doc
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
  var items = Array.from(document.querySelectorAll(
    '[data-qa-id="qa-conversation-chat-item"], .chat-item'
  ));
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
  var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
  for (var i = wrappers.length - 1; i >= 0; i--) {
    var wrap = wrappers[i];
    var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1');
    if (!bubble) continue;                               // system / event
    if (bubble.classList.contains('messageIsMe')) continue; // agent reply
    var text = (bubble.querySelector('pre') || bubble).textContent.trim();
    var tsEl = wrap.querySelector('.O4UWWFoQxgMq4AWHMq25');
    var ts = tsEl ? tsEl.textContent.trim() : '';
    var msgIdEl = wrap.querySelector('[data-id]');
    var msgId = msgIdEl ? msgIdEl.getAttribute('data-id') : '';
    return JSON.stringify({ text: text, msg_id: msgId, timestamp: ts, index: i });
  }
  return JSON.stringify({ text: '', msg_id: '', timestamp: '', index: -1 });
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
  var items = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
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
    sidebar = _normalize_customer_id(str(verify_result.get("sidebar_name") or "").strip())
    header = _normalize_customer_id(str(verify_result.get("header_name") or "").strip())
    expected = _normalize_customer_id(str(expected_name or "").strip())
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

    Also clicks the ``最近联系`` (recent-contacts) inner sub-tab if one
    is found, because the Feige SPA may be sitting on ``待回复`` /
    ``人工接待`` / some other sub-tab where the sidebar selector
    ``[data-qa-id="qa-conversation-chat-item"]`` returns zero elements.
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
            return True
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
                    cdp_sess = await browser_session.get_or_create_cdp_session(
                        target_id=tid, focus=False
                    )
                    if cdp_sess is None:
                        return -1
                    cdp_client = getattr(cdp_sess, "cdp_client", None)
                    session_id = getattr(cdp_sess, "session_id", None)
                    if cdp_client is None or session_id is None:
                        return -1
                    await cdp_client.send.Runtime.enable(session_id=session_id)
                    result = await cdp_client.send.Runtime.evaluate(
                        params={
                            "expression": _row_count_js,
                            "returnByValue": True,
                        },
                        session_id=session_id,
                    )
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
        try:
            if hasattr(browser_session, "get_or_create_cdp_session"):
                await browser_session.get_or_create_cdp_session(
                    target_id=feige_tid, focus=True
                )
            else:
                # Fallback for legacy BrowserSession API without the
                # method — fire the event and sleep as before.
                from browser_use.browser.events import SwitchTabEvent as _EF_STE
                await browser_session.event_bus.dispatch(_EF_STE(target_id=feige_tid))
                await _ef_asyncio.sleep(0.3)
        except Exception as _focus_err:
            logger.info(
                f"[BrowserAutomation] ensure-feige-tab: focus-target failed "
                f"(target=...{feige_tid[-6:]}): {_focus_err}"
            )
            return False
        logger.info(
            f"[BrowserAutomation] ensure-feige-tab: focused Feige tab "
            f"(target=...{feige_tid[-6:]}, was cur_url={cur_url!r})"
        )
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
    customer key different from *customer_name*, the helper yields
    immediately and returns ``scrape_ok=False`` to avoid stealing the
    active session from the customer currently being typed to.
    """
    import asyncio as _s_asyncio
    empty = {"text": "", "msg_id": "", "timestamp": "", "index": -1, "scrape_ok": False}
    if not browser_session or not customer_name:
        return empty

    # ── Feige active-session race guard ──
    # If another customer is currently being typed to, skip our sidebar
    # click (which would swap the active session and land the reply in
    # the wrong chat).  Caller (PreDispatch) will fall back to the
    # sidebar preview text for this one cycle.
    if typing_holder_getter is not None:
        try:
            _st_holder = typing_holder_getter()
            _st_cust_key = _normalize_customer_id(customer_name)
            if _st_holder and _st_holder != _st_cust_key:
                logger.info(
                    f"[BrowserAutomation] scrape-latest-customer: yield — another "
                    f"customer is currently being typed to ({_st_holder!r}); "
                    f"skipping sidebar click for {customer_name!r} to avoid "
                    f"stealing the active session (caller will use sidebar preview)"
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
        if not text:
            logger.info(
                f"[BrowserAutomation] scrape-latest-customer: thread had no customer "
                f"bubble for {customer_name!r} (index={idx}) — falling back"
            )
            return empty
        logger.info(
            f"[BrowserAutomation] scrape-latest-customer: {customer_name!r} "
            f"latest_bubble msg_id=...{msg_id[-8:] if msg_id else '<none>'} "
            f"text={text[:40]!r}"
        )
        return {
            "text": text,
            "msg_id": msg_id,
            "timestamp": str(data.get("timestamp") or "").strip(),
            "index": idx,
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
    "ensure_feige_tab_focused",
    "scrape_latest_customer_bubble",
]
