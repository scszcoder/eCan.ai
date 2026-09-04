"""Feige front-desk hooks (Phases 5A + 5B, 2026-04-24).

Background
----------

The eCan.ai agentic app supports arbitrary browser-automation business
cases.  Feige customer chat is one such case; to meet its real-time
requirement it uses a **front-desk agent + Q&A worker team** pattern
where a single 'front-desk' browser_automation node watches the Feige
sidebar, fans out each new customer message to a pool of worker agents,
and never invokes its own LLM on the fan-out path.

Prior to Phase 5, both the PreDispatch fan-out wrapper AND the inline
HOT-PATH-B reply-typing block lived directly inside
`build_node._run_browser_use`, coupling the generic node factory to
this one business case.  Phase 5 relocates both to this module,
registered with `build_node` via its lifecycle-hook interface.

What this module owns
---------------------

* **Early hook — HOT-PATH-B** (`before_session_setup_hook`): when
  a `chat_message` event arrives carrying a pre-computed
  `{response_text, customer_name}` payload, type the reply directly
  into Feige via `feige_open_session` + `feige_send_message` and
  short-circuit the LLM.  Runs BEFORE the (expensive) browser-use
  agent is constructed so the latency win is real.

* **Late hook — PreDispatch** (`before_run_hook`): when a
  `browser_event` arrives indicating a new customer message, scrape
  the latest customer bubble and fan out to available Q&A workers via
  the generic `node_runtime.frontdesk_dispatch` skeleton.  Runs
  AFTER the browser-use agent is constructed so it can reuse the
  agent's browser session for DOM reads.

What this module does **not** own
---------------------------------

* The Feige DOM selectors + JS snippets (`dom_assets`), the typing
  lock state (`typing_lock`), the action-sequence executor
  (`hot_path.execute`), the per-item enrichment plugin
  (`pre_dispatch_enrich`), or the generic fan-out skeleton
  (`node_runtime.frontdesk_dispatch`) — see those modules.

* The shared state dicts used by HOT-PATH-B + PreDispatch
  (`_dispatch_state_by_agent`, `_auto_dispatch_last_agent_reply`,
  etc.) — still owned by `build_node` module scope and injected
  via `BrowserUseHookContext`.  Deferred to a later phase.
"""

from __future__ import annotations

import asyncio
import json
import dataclasses
import logging
import os
import time
from typing import Any

from agent.ec_skills.node_runtime.frontdesk_dispatch import (
    DispatchConfig,
    DispatchContext,
    run as _run_frontdesk_dispatch,
)
from . import dispatch_state as _ds
from . import typing_lock as _typing_lock
from .sidebar_preview_js import ROW_PREVIEW_FALLBACK_JS as _ROW_PREVIEW_FALLBACK_JS

# CN builds name the app logger "eCan.cn" (propagate=False) — a bare
# getLogger("eCan") record never reaches its handlers, silencing this
# module's entire log output in packaged CN apps (v0.9.95u incident:
# the WS reader looked dead because none of its lines could land).
from utils.logger_helper import logger_helper as logger

__all__ = ["before_run_hook", "before_session_setup_hook", "register", "route_inbound_customer_ws"]

# ws023: registry of the most-recent front-desk dispatch context, so the WS
# detector can route a customer message DIRECTLY through run() (the full
# coordination: inflight/dedup/RR/placeholder/source-msg-id) WITHOUT going through
# the serial front-desk task queue (the 1-to-6 throughput cliff). The node
# populates this on every before_run_hook; route_inbound_customer_ws reuses it with
# a per-item state. One front-desk agent per process => single "slot".
_FEIGE_FD_DISPATCH_REG: dict[str, Any] = {}


def _is_pre_dispatch_busy(res: Any) -> bool:
    """ws084: True if run() short-circuited as ``pre_dispatch_busy`` — it could NOT acquire
    the per-scope dispatch lock within its 15s wait (a concurrent invocation held it past the
    deadline), so the turn was NOT dispatched. The caller must recover it, not discard it."""
    if not isinstance(res, dict):
        return False
    if str(res.get("history") or "").endswith(":busy"):
        return True
    try:
        return json.loads(res.get("final") or "{}").get("hot_path_type") == "pre_dispatch_busy"
    except Exception:
        return False


async def route_inbound_customer_ws(item: dict, fallback) -> None:
    """ws023: route ONE WS-detected customer message straight through the front-desk
    dispatch coordination (run()), bypassing the serial front-desk task. Reuses the
    DispatchContext the node registered (dataclasses.replace with a per-item state
    carrying the WS browser_event, so ws021/ws022 read THIS item). Runs per-frame in
    the WS observer loop => customers no longer serialize through one task. On
    registry-miss or ANY error it invokes `fallback` (the legacy browser_event
    dispatch) so a message is never lost. Gated by the caller on
    ECAN_FEIGE_WS_DIRECT_QA=1.
    """
    reg = _FEIGE_FD_DISPATCH_REG.get("slot")
    if not reg or not isinstance(item, dict):
        fallback()
        return
    cfg, ctx_template, agent = reg
    try:
        fresh_state = {
            "attributes": {
                "browser_event": {
                    "type": "browser_event",
                    "source": "ws_frontier",
                    "body": {"items": [dict(item)]},
                }
            }
        }
        new_ctx = dataclasses.replace(ctx_template, state=fresh_state)
        _res = await _run_frontdesk_dispatch(cfg, new_ctx, agent)
        # ws084 (#1): a `pre_dispatch_busy` short-circuit means run() could NOT acquire the
        # per-scope dispatch lock within its 15s wait (a concurrent invocation held it past
        # the deadline — e.g. a ~10s thread-scrape) and returned WITHOUT dispatching. The
        # result was previously DISCARDED here (route is ``-> None``) -> the turn was silently
        # lost (一对六 2026-06-18: 瓦哒嘻哇's two 00:59 msgs busy-dropped at 00:59:36/00:59:48,
        # customer saw nothing for ~3 min then re-sent). Recover via the legacy queue so a
        # busy turn is re-dispatched, never lost. Gated ECAN_FEIGE_WS_BUSY_FALLBACK=1 (default ON).
        if (os.environ.get("ECAN_FEIGE_WS_BUSY_FALLBACK", "1") != "0"
                and _is_pre_dispatch_busy(_res)):
            logger.info(
                f"[WS-DIRECT-QA] pre_dispatch_busy cust={item.get('customer_name')!r} — lock "
                f"contention starved the WS hot path; re-dispatching via legacy queue "
                f"(turn would otherwise be silently dropped)")
            try:
                fallback()
            except Exception:
                pass
    except Exception as _e:
        logger.warning(
            f"[WS-DIRECT-QA] route_inbound_customer_ws failed -> legacy dispatch: {_e}",
            exc_info=True,
        )
        try:
            fallback()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────
# ws103: cold-start OVERDUE recovery via the MAIN-tab sidebar.
#
# Why ws095's detection-tab path could not fix this: the DOM monitor runs on the
# DEDICATED detection tab — a SEPARATE tab that does NOT render the conversation
# sidebar (live logs: status=page_mismatch, items=0), so it sees ZERO rows. And
# even the main DOM diff baselines pre-existing rows on its first scrape
# (keys_initialized), so an overdue row already on screen at startup is never
# "added" → never dispatched. ws089 (the last working version) only succeeded
# because its first scrape hit an empty sidebar (rows appeared AFTER baseline);
# the dedicated-detection-tab change (post-089 realtime work) regressed it.
#
# Fix: scan the MAIN tab's sidebar directly (the tab that DOES have the rows),
# find rows that look unanswered (unread badge / needReply), and route each to QA
# via route_inbound_customer_ws — bypassing the diff entirely. enrich_item's own
# guards (mt030 agent_already_replied, msg-id dedup, system-row filter) prevent
# re-answering, so the scan can be liberal. One shot per customer name per
# process. Gated on the existing ECAN_FEIGE_COLDSTART_RECOVERY_SCRAPE=1.
_COLDSTART_RECOVERED_NAMES: set[str] = set()

# ws108: the recovery scan is now a CONTINUOUS missed-message backstop (not just a
# startup window), so it also catches a NEW conversation's first message that the
# WS/detection path jams on. Cold-start first-message root cause: ws096 recognizes the
# "小店为你服务" connect banner and ws086 is supposed to thread-scrape the real first
# message — but ws086 runs in the DOM-monitor path, which is PAUSED while WS owns
# dispatch (ECAN_FEIGE_WS_PAUSE_DOM_MONITOR=1), so recovery never fires and the first
# message hangs until a 2nd message arrives. This main-tab scan runs independent of the
# pause, routes connect-banner rows (-> enrich thread-scrapes the real question), and
# uses a per-(name,preview) dedup + staleness gate so it NEVER races the WS path (WS
# answers fresh msgs within seconds; the backstop only fires for what's still unanswered).
_BACKSTOP_FIRST_SEEN: dict = {}   # (name, preview) -> first-seen monotonic ts
_BACKSTOP_ROUTED: set = set()     # (name, preview) already routed once
_CONNECT_BANNER_PATTERNS = (
    "store_assignment_notice", "store_auto_greeting", "smart_cs_auto_greeting",
)

# ws168 (1): typing-lock deferral retry. enrich_item defers a routed row while the
# GLOBAL typing lock is held (skip_reason="typing_lock_active") and registers it in
# pre_dispatch_enrich's deferred set expecting event_monitor's tick to re-fire it —
# but that tick is PAUSED while WS owns dispatch, so the deferral never retried and
# the row stayed in _BACKSTOP_ROUTED forever (live 2026-07-11 11:20:48 'packet':
# deferred once behind a card delivery, silent until the customer re-asked 56s
# later). THIS scan runs regardless of the pause, so it serves the retry itself:
# when the typing lock is free and a deferred entry matches a row's name, drop the
# key from _BACKSTOP_ROUTED (rate-limited) so the normal gate re-routes it.
_BACKSTOP_DEFERRED_LAST_RETRY: dict = {}  # (name, preview) -> last forced-retry monotonic ts

# ws168 (3): reopen re-scrape. A reopened conversation's sidebar preview STAYS the
# connect banner when the customer's next message arrives, so the (name, preview)
# GC never re-tracks the row — and a partially-painted thread can make the reopen
# enrich scrape the PRE-close bubble, leaving the fresh message masked until some
# unrelated event re-triggers enrich (live 2026-07-11 09:59 'packet': 你好 sat 10
# min). After routing a CONNECT-BANNER row, schedule bounded re-routes so enrich
# re-scrapes the settled thread; msg-id dedup + mt030 no-op when nothing new.
_BACKSTOP_REOPEN_RESCRAPE: dict = {}      # (name, preview) -> list of due monotonic ts

# ws168 (2): startup system-row recovery. A question dispatched just before app
# shutdown dies with the process; after restart the row's preview is a PLATFORM
# notice (长时间未回复 / 无效会话…) that this scan skipped as system_other on every
# tick — permanently (live 2026-07-11: 肽斯特+packet asked 10:30, app exited
# 10:31:33 mid-LLM, restarted 10:39, rows skipped 20+ min, never answered). For a
# window after process start, route non-close system rows once so enrich
# thread-scrapes the real thread; mt030/msg-id dedup decide what's unanswered.
_BACKSTOP_PROCESS_START: float = time.monotonic()

# ws178: rate-limit for the nameless-row DOM dump (see the scan JS debug block).
_NAMELESS_DUMP_AT: dict = {}

_COLDSTART_SIDEBAR_SCAN_JS = r"""(function(){""" + _ROW_PREVIEW_FALLBACK_JS + r"""
  function readName(row){
    var nick=row.querySelector('[data-qa-id="qa-conversation-nickname"]');
    if(nick){var nv=(nick.textContent||'').trim(); if(nv) return nv;}
    var line=row.querySelector('[class*="nameLine"]');
    if(line){var lt=(line.getAttribute('title')||'').trim(); if(lt) return lt;
      var nc=line.querySelector('[class*="NameContent"]'); if(nc){var ncv=(nc.textContent||'').trim(); if(ncv) return ncv;}}
    var nc2=row.querySelector('[class*="NameContent"]'); if(nc2){var v=(nc2.textContent||'').trim(); if(v) return v;}
    // ws110: broader fallbacks for DOM/selector drift (ws109 run: 27 rows, readName ''
    // for ALL -> rows=0). Any data-qa-id mentioning nickname/name, or a short title=
    // attribute that isn't a numeric preview/time.
    var alt=row.querySelector('[data-qa-id*="nickname" i],[data-qa-id*="name" i]');
    if(alt){var av=(alt.getAttribute('title')||alt.textContent||'').trim(); if(av&&av.length<=24) return av;}
    // ws183: iterate ALL titled descendants, not just the first — the 重复来访
    // revisit-row variant has qa=[] and its FIRST [title] is the unread badge
    // ('1', numeric → rejected), while the SECOND is the actual name (live
    // 2026-07-26 15:36 'packet': titles=['1','packet'], rows=0 total=1 for the
    // whole session → backstop never routed). Skip badge counts and time-ago
    // strings (45分钟/2小时…).
    var titledAll=row.querySelectorAll('[title]');
    for(var t=0;t<titledAll.length&&t<6;t++){
      var tv=(titledAll[t].getAttribute('title')||'').trim();
      if(tv&&tv.length<=24&&!/^[\d:\s]+$/.test(tv)&&!/^\d+\s*(分钟|小时|秒|天)/.test(tv)) return tv;
    }
    return '';
  }
  function readPreview(row, nm){
    var p=row.querySelector('[class*="msgContent"], .lF_M7QiFB0ukHWpMfQde span');
    var v=p?(p.textContent||'').trim():'';
    if(v) return v;
    // ws189: selector drift on the rebuilt frame (live 2026-09-04: every row
    // empty_preview, cold-start customer never answered) — structural fallback.
    return __ecanRowPreviewFallback(row, nm);
  }
  function rowIsCurrent(row){
    var btm=row&&row.getAttribute?String(row.getAttribute('data-btm-id')||''):'';
    if(btm.endsWith('.current')) return true;
    if(btm.endsWith('.recent')||btm.endsWith('.systemConv')) return false;
    if(row&&row.closest&&row.closest('.pigeonChatNotScrollBox')) return true;
    if(row&&row.closest&&row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  function hasUnread(row){
    if(/needReply/i.test(String(row.className||''))) return true;
    var b=row.querySelector('[class*="badge"],[class*="Badge"],[class*="unread"],[class*="Unread"],[class*="redDot"],[class*="RedDot"]');
    if(b){var t=(b.textContent||'').trim(); if(/^\d+$/.test(t)&&t!=='0') return true;
      if(b.offsetParent!==null&&/dot|badge|unread|red/i.test(String(b.className||''))) return true;}
    return false;
  }
  // ws107: scan ALL conversation rows (NOT just the .current sub-tab) — a residue
  // from a prior session usually sits in 最近联系 (.recent), which the current-only
  // filter excluded (ws104 run logged rows=0 with a residue present). Tag each row
  // with `current` so Python can prefer current but still recover recent ones.
  var all=Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
  var out=[];
  for(var i=0;i<all.length;i++){
    var nm=readName(all[i]); if(!nm) continue;
    out.push({name:nm, preview:readPreview(all[i], nm), unread:hasUnread(all[i]),
              needReply:/needReply/i.test(String(all[i].className||'')),
              current:rowIsCurrent(all[i])});
  }
  // ws110: when rows match the selector (total>0) but NONE yield a name, dump the
  // structure of the first few rows so we can fix readName precisely instead of
  // guessing — class, data-btm-id, all descendant data-qa-ids, and a textContent
  // sample (reveals whether the name is present-but-under-a-new-selector vs the row
  // is an empty virtualized shell).
  var debug=[];
  // ws178: dump ANY nameless row, not only the all-nameless case. Live
  // 2026-07-15 19:56:11->19:57:14: 肽斯特's row was RENDERED within ~3s of the
  // message (total=3) but readName returned '' for ~75s (rows=2), so the scan
  // skipped it as noname and the customer waited — while the ws110 dump (gated
  // on out.length===0) stayed silent because the OTHER two rows had names.
  // Dump the nameless rows' structure (with outerHTML head) so readName can be
  // extended from evidence.
  if(out.length<all.length){
    for(var d=0; d<all.length && debug.length<3; d++){
      var r=all[d];
      if(readName(r)) continue;   // only the nameless ones
      debug.push({
        cls:String(r.className||'').slice(0,60),
        btm:String((r.getAttribute&&r.getAttribute('data-btm-id'))||''),
        qa:Array.from(r.querySelectorAll('[data-qa-id]')).slice(0,10).map(function(e){return e.getAttribute('data-qa-id');}),
        titles:Array.from(r.querySelectorAll('[title]')).slice(0,4).map(function(e){return String(e.getAttribute('title')||'').slice(0,20);}),
        txt:String(r.textContent||'').replace(/\s+/g,' ').trim().slice(0,60),
        html:String(r.outerHTML||'').slice(0,500)
      });
    }
  }
  // ws189: when rows have names but NONE yields a preview even after the
  // structural fallback, dump the first named row's leaf-text inventory +
  // outerHTML so the preview selector can be pinned from evidence next rev.
  var pdebug=null;
  if(out.length>0 && out.every(function(o){return !o.preview;})){
    for(var e=0;e<all.length;e++){
      if(!readName(all[e])) continue;
      var leaves=[]; var le=all[e].querySelectorAll('*');
      for(var l=0;l<le.length&&leaves.length<14;l++){
        if(le[l].children&&le[l].children.length) continue;
        var lt=String(le[l].textContent||'').replace(/\s+/g,' ').trim();
        if(!lt) continue;
        leaves.push({tag:String(le[l].tagName||'').toLowerCase(), cls:String(le[l].className||'').slice(0,40), txt:lt.slice(0,30)});
      }
      pdebug={name:readName(all[e]), leaves:leaves, html:String(all[e].outerHTML||'').slice(0,1500)};
      break;
    }
  }
  return JSON.stringify({rows:out, total:all.length, url:String(location.href||'').slice(-60), debug:debug, pdebug:pdebug});
})()"""


async def coldstart_overdue_recovery_scan(legacy_dispatcher=None) -> int:
    """ws103: scan the MAIN-tab sidebar for unanswered overdue rows and route each
    to QA, bypassing the (blind detection-tab + baseline-diff) detection path.

    Returns the number of rows dispatched. One shot per customer name per process.
    Gated ECAN_FEIGE_COLDSTART_RECOVERY_SCRAPE=1.

    ws166: *legacy_dispatcher* (optional, a sync ``fn(item) -> None``) lets the
    scan run BEFORE the front-desk dispatch slot exists. The slot registers only
    in before_run_hook — i.e. on the FIRST browser_event — so an app started
    against a QUIET sidebar (nothing pending) never fires an event, never
    registers the slot, and this scan silently returned 0 every 5s while the WS
    monitor (which paused the DOM path on its first frame) dropped the cold-start
    message: TOTAL blindness (live 2026-07-10 21:38:35 'sc' 转人工 — zero
    ws108/scan lines the whole run; earlier runs worked only because they
    START with unread rows → startup event → slot). Routing a found row through
    the legacy browser_event dispatcher invokes the node → before_run_hook →
    registers the slot → self-healing.
    """
    if os.environ.get("ECAN_FEIGE_COLDSTART_RECOVERY_SCRAPE", "") != "1":
        return 0
    _slot_missing = not _FEIGE_FD_DISPATCH_REG.get("slot")
    if _slot_missing and legacy_dispatcher is None:
        return 0  # front-desk dispatch context not registered yet (pre-ws166 behavior)
    if _slot_missing:
        logger.info(
            "[BrowserAutomation] ws166 backstop scanning WITHOUT dispatch slot "
            "(no browser_event yet this process) — found rows will route via the "
            "legacy event dispatcher to bootstrap the slot"
        )
    try:
        from agent.ec_skills.browser_node.build_helpers import cached_browser_sessions
        from agent.ec_skills.browser_use_extension.extension_tools_service import _evaluate_js
        from .dom_assets import (
            ensure_feige_tab_reachable,
            _SESSION_FOCUSED_FEIGE_TID_ATTR,
        )
    except Exception:
        return 0
    browser_session = None
    for sess in list((cached_browser_sessions or {}).values()):
        if sess is not None:
            browser_session = sess
            break
    if browser_session is None:
        return 0
    _tid = None
    try:
        if await ensure_feige_tab_reachable(browser_session):
            _tid = getattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, None)
    except Exception:
        _tid = None
    # ws170: flush parked undeliverable card replies whose talk has since
    # resolved to a real name (see undeliverable.py). This scan runs every
    # ~5s regardless of who owns dispatch, so it's the natural driver.
    try:
        from . import undeliverable as _undlv
        if _undlv.pending():
            await _undlv.resolve_and_flush(browser_session)
    except Exception as _undlv_e:
        logger.debug(f"[BrowserAutomation] ws170 flush tick failed (non-fatal): {_undlv_e}")
    # ws182: dormant-conversation read-probe tick (phase-1 experiment; internally
    # throttled + capped, total no-op unless ECAN_FEIGE_DORMANT_POLL=1).
    try:
        from . import dormant_probe as _dprobe
        await _dprobe.maybe_probe(browser_session)
    except Exception as _dp_e:
        logger.debug(f"[BrowserAutomation] ws182 dormant probe tick failed (non-fatal): {_dp_e}")
    try:
        r = await _evaluate_js(
            browser_session, _COLDSTART_SIDEBAR_SCAN_JS,
            target_id=str(_tid) if _tid else None,
            focus=False, read_only=True, lock_free=True,
            trace_label="feige_coldstart_recovery_scan",
        )
        if isinstance(r, str):
            r = json.loads(r)
        rows = (r or {}).get("rows") or []
        _scan_total = (r or {}).get("total")
        _scan_url = (r or {}).get("url") or ""
        _scan_debug = (r or {}).get("debug") or []
        if _scan_debug:
            # ws110/ws178: some rows yield no name — show the real row DOM so we can fix
            # readName instead of guessing (the wall behind every prior residue/first-msg fix).
            # Rate-limited: while a row stays nameless (partial paint) the scan would
            # otherwise dump every 5s tick.
            _now_dump = time.monotonic()
            if _now_dump - _NAMELESS_DUMP_AT.get("ts", 0.0) >= 120.0:
                _NAMELESS_DUMP_AT["ts"] = _now_dump
                logger.info(f"[BrowserAutomation] ws178 backstop scan NAMELESS-ROW DUMP: {_scan_debug}")
        _scan_pdebug = (r or {}).get("pdebug")
        if _scan_pdebug:
            # ws189: every named row read back preview-empty (selector drift AND the
            # structural fallback missed) — show the real row so readPreview can be
            # pinned from evidence. Rate-limited like the nameless dump.
            _now_pd = time.monotonic()
            if _now_pd - _NAMELESS_DUMP_AT.get("pd_ts", 0.0) >= 120.0:
                _NAMELESS_DUMP_AT["pd_ts"] = _now_pd
                logger.info(f"[BrowserAutomation] ws189 backstop scan EMPTY-PREVIEW DUMP: {_scan_pdebug}")
    except Exception as _e:
        logger.debug(f"[BrowserAutomation] ws103 coldstart recovery scan failed: {_e}")
        return 0
    try:
        from .system_message_filter import first_matching_pattern as _sys_match
    except Exception:
        _sys_match = None
    try:
        from .dispatch_state import matches_recent_agent_reply as _recent_reply
    except Exception:
        _recent_reply = None
    # ws126 (1): bridge for backstop<->WS in-flight dedup. ``talk_for_name`` (ws046
    # forward map) turns the sidebar row's NAME into the conversation's talk_id so we
    # can ask whether the WS hot path is already dispatching it under the synthetic
    # ``card:<talk_id>`` identity (30s TTL).
    try:
        from .ws_session import talk_for_name as _talk_for_name
    except Exception:
        _talk_for_name = None
    # ws167: per-conversation live/dormant map — the cold-start algorithm's core
    # (docs/FEIGE_COLDSTART_DETECTION.md). dormant = no WS frame for this conv since
    # process start / its last 关闭会话. A dormant customer's row change routes FAST
    # (WS will NOT deliver it); a live customer's row keeps the "give WS first crack"
    # stale gate. Gated ECAN_FEIGE_DORMANT_FASTROUTE=1 (default on).
    try:
        from .ws_session import (
            is_conv_live as _is_conv_live,
            mark_conv_dormant as _mark_conv_dormant,
        )
    except Exception:
        _is_conv_live = None
        _mark_conv_dormant = None
    try:
        from agent.ec_skills.build_node import _is_dispatch_inflight
    except Exception:
        _is_dispatch_inflight = None
    # ws104: ALWAYS log what the scan found (rows + names), even when 0 are routed —
    # the ws103 run dispatched 0 with NO clue why; the gap was: a residue row from a
    # prior session has NO unread badge (same as ws055/ws086 platform-stall rows), so
    # the old `unread || needReply` gate dropped exactly the row we needed.
    _now = time.monotonic()
    try:
        _stale_s = float(os.environ.get("ECAN_FEIGE_BACKSTOP_STALE_S", "15") or 15)
    except (TypeError, ValueError):
        _stale_s = 15.0
    _names = [str((r or {}).get("name") or "") for r in rows if isinstance(r, dict)]
    # ws171: preview-correlation bridge — bind still-unnamed WS conversations to
    # sidebar names via exact preview==text match (see ws_session for the safety
    # rules). Runs BEFORE the row loop so this tick's dedup/delivery/flush all
    # see the fresh mapping; the ws170 parking lot flushes on the next tick.
    try:
        from .ws_session import bind_unnamed_conv_by_preview as _bind_by_preview
        _bind_by_preview([
            (str((r or {}).get("name") or ""), str((r or {}).get("preview") or ""))
            for r in rows if isinstance(r, dict)
        ])
    except Exception as _bind_e:
        logger.debug(f"[BrowserAutomation] ws171 preview-bridge failed (non-fatal): {_bind_e}")
    # ws168 (1): customers whose enrich deferred on the typing lock. The event_monitor
    # re-fire that normally serves these is paused while WS owns dispatch, so this
    # scan retries them once the lock frees (see _BACKSTOP_DEFERRED_LAST_RETRY).
    _deferred_names: set = set()
    if os.environ.get("ECAN_FEIGE_BACKSTOP_DEFERRED_RETRY", "1") != "0":
        try:
            from .pre_dispatch_enrich import snapshot_deferred as _snap_deferred
            _deferred_names = {c for (_s, c) in _snap_deferred()}
        except Exception:
            _deferred_names = set()
    try:
        _deferred_retry_min_s = float(
            os.environ.get("ECAN_FEIGE_DEFERRED_RETRY_MIN_S", "10") or 10
        )
    except (TypeError, ValueError):
        _deferred_retry_min_s = 10.0
    _n = 0
    _skipped: dict = {}
    _live_keys: set = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        _name = str(row.get("name") or "").strip()
        if not _name:
            _skipped["noname"] = _skipped.get("noname", 0) + 1
            continue
        _prev = str(row.get("preview") or "").strip()
        if not _prev:
            _skipped["empty_preview"] = _skipped.get("empty_preview", 0) + 1
            continue
        # ws116: a sidebar row whose preview is a 转人工/人工 handover request must get
        # the [微笑] ack even when the WS observer missed the frame AND the DOM monitor
        # is paused (live 2026-06-25: packet typed 人工 — the WS reader never decoded a
        # 人工 text frame, the DOM monitor was paused under WS-owns-dispatch, and bare
        # 人工 matches NO system filter -> it fell through every crack: no dispatch, no
        # ack). This backstop scans the sidebar continuously regardless of who owns
        # dispatch, so arm the ack here. Arming only (no routing change); idempotent +
        # rate-limited (600s) in placeholder_timer. The WS path (ws_observer:561) and
        # the enrich path (ws115 early-arm) still cover the cases they see.
        try:
            from . import human_mode as _bs_hm
            # ws117: is_human_handover_request (SHORT standalone), NOT is_human_trigger
            # (substring) — the preview is often OUR placeholder/reply ("人工服务正在
            # 回复中…", "正在为您转接人工客服") or a platform notice ("现在是人工客服为您
            # 服务"), all of which contain 人工 and would flood false [微笑] acks.
            if _bs_hm.is_human_handover_request(_prev):
                from .placeholder_timer import note_handover_ack_needed as _bs_note_ho
                _bs_note_ho(_name)
                logger.info(
                    f"[BrowserAutomation] ws116 backstop handover trigger cust={_name!r} "
                    f"preview={_prev[:40]!r} -> [微笑] ack armed")
        except Exception:
            pass
        _key = (_name, _prev)
        _live_keys.add(_key)
        # Classify the preview. A CONNECT banner ("小店接入"/"小店为你服务", ws096) means
        # a NEW conversation whose real first message lives in the thread — route it so
        # enrich_item thread-scrapes the question (the ws086 path, but pause-independent).
        # Any OTHER system message (platform-stall / transfer) we leave alone. Our own
        # recent reply as the preview => already answered.
        _sys = None
        if _sys_match is not None:
            try:
                _sys = _sys_match(_prev)
            except Exception:
                _sys = None
        _is_connect = _sys in _CONNECT_BANNER_PATTERNS
        _is_sysrow_recovery = False
        if _sys and not _is_connect:
            # ws167: a 关闭会话 close marker re-enters DORMANT for this conversation —
            # the server stops pushing its frames after a close, so this customer's
            # NEXT message is a cold start that the DOM watcher must own.
            if _sys == "session_close_notice" and _mark_conv_dormant is not None:
                try:
                    _mark_conv_dormant(_name)
                    logger.info(
                        f"[BrowserAutomation] ws167 close marker -> conversation "
                        f"DORMANT cust={_name!r} (next msg = cold start, DOM owns it)"
                    )
                except Exception:
                    pass
            # ws168 (2): within the startup window a platform-notice preview usually
            # hides a question whose dispatch died with the previous process (app
            # shutdown mid-turn). Route it ONCE through the normal gates below so
            # enrich thread-scrapes the real thread; outside the window keep the
            # old skip (these rows are just closed/idle conversations). A 关闭会话
            # close-notice row stays excluded — the platform closed it, nothing is
            # pending. Reversible: ECAN_FEIGE_STARTUP_SYSROW_RECOVERY=0.
            try:
                _sysrow_window = float(
                    os.environ.get("ECAN_FEIGE_STARTUP_SYSROW_WINDOW_S", "900") or 900
                )
            except (TypeError, ValueError):
                _sysrow_window = 900.0
            if (
                _sys != "session_close_notice"
                and os.environ.get("ECAN_FEIGE_STARTUP_SYSROW_RECOVERY", "1") != "0"
                and (_now - _BACKSTOP_PROCESS_START) <= _sysrow_window
            ):
                _is_sysrow_recovery = True
            else:
                _skipped["system_other"] = _skipped.get("system_other", 0) + 1
                continue
        if not _sys and _recent_reply is not None:
            try:
                if _recent_reply(_name, _prev):
                    _skipped["our_recent_reply"] = _skipped.get("our_recent_reply", 0) + 1
                    continue
            except Exception:
                pass
        # ws126 (1): dedup against an IN-FLIGHT WS card-identity dispatch. The WS hot
        # path owns a conversation under the synthetic ``card:<talk_id>`` identity (a
        # name-less product card) while THIS backstop scans the sidebar by NAME — the
        # identities mismatch, so without this check the same customer is dispatched
        # TWICE (once real-time by WS under card:<talk>, once here by name). That is the
        # 陆地飞鱼 double-dispatch: doubled main-tab work + the card-id self-block the
        # post-ws095 recovery machinery re-introduced. Bridge name -> talk_id and skip
        # while the WS path is actively dispatching this conversation (30s inflight TTL).
        # The 15s staleness gate below only gives the WS path "first crack"; a SLOW WS
        # turn (>15s LLM) still needs this to avoid a duplicate. Reversible:
        # ECAN_FEIGE_BACKSTOP_WS_DEDUP=0.
        if (
            os.environ.get("ECAN_FEIGE_BACKSTOP_WS_DEDUP", "1") != "0"
            and _talk_for_name is not None
            and _is_dispatch_inflight is not None
        ):
            try:
                _talk = str(_talk_for_name(_name) or "").strip()
            except Exception:
                _talk = ""
            _ws_busy = 0.0
            _probe_keys = ((f"card:{_talk}", _talk) if _talk else ()) + (_name,)
            for _idk in _probe_keys:
                try:
                    _age = float(_is_dispatch_inflight(_idk) or 0.0)
                except Exception:
                    _age = 0.0
                if _age > 0.0:
                    _ws_busy = _age
                    break
            if _ws_busy > 0.0:
                _skipped["ws_inflight"] = _skipped.get("ws_inflight", 0) + 1
                logger.info(
                    f"[BrowserAutomation] ws126 backstop dedup: WS hot path already "
                    f"dispatching cust={_name!r} talk={_talk or '?'} "
                    f"inflight_age={_ws_busy:.1f}s — skipping duplicate main-tab route"
                )
                continue
        # Per-(name,preview) dedup + staleness: give the WS/normal path first crack;
        # only route what's STILL unanswered after _stale_s. enrich_item's mt030 +
        # msg-id dedup + inflight guard are the final safety net against double-answer.
        if _key in _BACKSTOP_ROUTED:
            # ws168 (1): the routed row's enrich deferred on the typing lock and was
            # never retried (event_monitor's re-fire is paused under WS ownership).
            # Once the lock is free, un-route the key so the gates below route it
            # again; enrich re-defers (refreshing the deferral) if the lock got
            # re-taken, and clears the deferral on success.
            _retried = False
            if _name in _deferred_names:
                try:
                    _lock_holder = str(_typing_lock.holder() or "")
                except Exception:
                    _lock_holder = ""
                _last_retry = _BACKSTOP_DEFERRED_LAST_RETRY.get(_key, 0.0)
                if not _lock_holder and (_now - _last_retry) >= _deferred_retry_min_s:
                    _BACKSTOP_DEFERRED_LAST_RETRY[_key] = _now
                    _BACKSTOP_ROUTED.discard(_key)
                    _retried = True
                    logger.info(
                        f"[BrowserAutomation] ws168 deferred-row retry cust={_name!r} "
                        f"(enrich deferred on the typing lock; lock now free -> re-route)"
                    )
            # ws168 (3): a routed CONNECT-BANNER row keeps its banner preview when the
            # customer's next message arrives, so the GC never re-tracks it. Re-route
            # at the scheduled re-scrape times so enrich re-scrapes the settled thread
            # (partial paint on reopen can hide the fresh bubble from the first pass).
            if not _retried:
                # An exhausted schedule stays as [] so a re-route can't re-arm it
                # (the GC drops the key when the row leaves the screen).
                _due = _BACKSTOP_REOPEN_RESCRAPE.get(_key)
                if _due and _now >= _due[0]:
                    _due.pop(0)
                    _BACKSTOP_ROUTED.discard(_key)
                    _retried = True
                    logger.info(
                        f"[BrowserAutomation] ws168 reopen re-scrape cust={_name!r} "
                        f"preview={_prev[:30]!r} (re-route so enrich re-scrapes the "
                        f"thread; msg-id dedup/mt030 no-op when nothing new)"
                    )
            if not _retried:
                _skipped["already_routed"] = _skipped.get("already_routed", 0) + 1
                continue
        _fs = _BACKSTOP_FIRST_SEEN.setdefault(_key, _now)
        # ws144: a CONNECT-BANNER row is a cold-start conversation whose real customer
        # message the WS path is NOT dispatching (WS delivered the card, not the text; the
        # preview here is a SYSTEM banner, not a customer bubble). So the 15s "give WS first
        # crack" wait is pure wasted latency — live 1-vs-2 cold-start: 陆地飞鱼's 买两件有优惠吗
        # arrived 18:19:18 but only routed at 18:20:05 (age=24s), ~47s end-to-end. The ws126
        # inflight-dedup + mt030 + msg-id dedup already prevent a double-answer if WS DOES
        # catch it, so route connect-banner rows fast. Regular (missed-msg) rows keep the full
        # gate. Reversible: ECAN_FEIGE_BACKSTOP_CONNECT_STALE_S (default 4).
        _stale_eff = _stale_s
        if _is_connect:
            _stale_eff = float(
                os.environ.get("ECAN_FEIGE_BACKSTOP_CONNECT_STALE_S", "4") or 4
            )
        # ws167: a DORMANT conversation's row change is a cold start BY DEFINITION —
        # WS will not deliver this message (no frames since process start / last
        # 关闭会话), so the 15s "give WS first crack" wait is pure lost latency.
        # Route on the fast (connect) gate. Live conversations keep the full gate
        # (WS is delivering for them; this scan is only their late safety net).
        elif (
            _is_conv_live is not None
            and os.environ.get("ECAN_FEIGE_DORMANT_FASTROUTE", "1") != "0"
        ):
            try:
                if not _is_conv_live(_name):
                    _stale_eff = float(
                        os.environ.get("ECAN_FEIGE_BACKSTOP_CONNECT_STALE_S", "4") or 4
                    )
                    logger.info(
                        f"[BrowserAutomation] ws167 dormant fast-route "
                        f"cust={_name!r} preview={_prev[:30]!r} (no WS frames for "
                        f"this conv -> cold start, gate {_stale_eff:.0f}s)"
                    )
            except Exception:
                pass
        if (_now - _fs) < _stale_eff:
            _skipped["not_stale_yet"] = _skipped.get("not_stale_yet", 0) + 1
            continue
        _BACKSTOP_ROUTED.add(_key)
        # ws168 (3): schedule bounded re-routes for a CONNECT-BANNER (reopen) row —
        # its preview never changes when the customer's next message arrives, and a
        # partially-painted thread can hide that message from the first enrich pass.
        if (
            _is_connect
            and os.environ.get("ECAN_FEIGE_REOPEN_RESCRAPE", "1") != "0"
            and _key not in _BACKSTOP_REOPEN_RESCRAPE  # arm once; re-routes must not re-arm
        ):
            try:
                _rs_raw = os.environ.get("ECAN_FEIGE_REOPEN_RESCRAPE_S", "12,30") or "12,30"
                _rs_delays = [float(x) for x in _rs_raw.split(",") if x.strip()]
            except (TypeError, ValueError):
                _rs_delays = [12.0, 30.0]
            if _rs_delays:
                _BACKSTOP_REOPEN_RESCRAPE[_key] = [_now + _d for _d in _rs_delays]
        if _is_sysrow_recovery:
            _source = "startup_sysrow_backstop"
            _row_kind = "STARTUP-SYSROW"
        elif _is_connect:
            _source = "connect_banner_backstop"
            _row_kind = "CONNECT-BANNER"
        else:
            _source = "missed_msg_backstop"
            _row_kind = "stale"
        _item = {
            "customer_name": _name,
            "name": _name,
            "customer_id": _name,
            "last_message": _prev,
            "latest_message": _prev,
            "unread_badge": "1",
            "_ecan_coldstart_recovery": True,
            "source": _source,
        }
        logger.info(
            f"[BrowserAutomation] ws108 missed-msg backstop: routing "
            f"{_row_kind} row cust={_name!r} "
            f"preview={_prev[:40]!r} age={_now - _fs:.0f}s (enrich thread-scrapes the "
            f"real message; mt030/dedup decide)"
        )
        try:
            if _FEIGE_FD_DISPATCH_REG.get("slot"):
                await route_inbound_customer_ws(_item, lambda: None)
            elif legacy_dispatcher is not None:
                # ws166: no slot yet — legacy browser_event dispatch. The runner
                # invokes the node, before_run_hook registers the slot, and THIS
                # item is processed by the full PreDispatch pipeline.
                logger.info(
                    f"[BrowserAutomation] ws166 backstop -> legacy event dispatch "
                    f"cust={_name!r} (bootstrapping dispatch slot)"
                )
                legacy_dispatcher(_item)
            else:
                continue
            _n += 1
        except Exception as _de:
            logger.warning(
                f"[BrowserAutomation] ws108 backstop dispatch failed cust={_name!r}: {_de}"
            )
    # GC: a key that's no longer on screen (preview changed = answered or superseded)
    # is dropped, so a NEW message for the same customer gets tracked + routed fresh.
    for _k in list(_BACKSTOP_FIRST_SEEN):
        if _k not in _live_keys:
            _BACKSTOP_FIRST_SEEN.pop(_k, None)
            _BACKSTOP_ROUTED.discard(_k)
            _BACKSTOP_REOPEN_RESCRAPE.pop(_k, None)
            _BACKSTOP_DEFERRED_LAST_RETRY.pop(_k, None)
    logger.info(
        f"[BrowserAutomation] ws108 backstop scan: rows={len(rows)} total={_scan_total} "
        f"url=...{_scan_url} names={_names[:8]} routed={_n} skipped={_skipped}"
    )
    return _n


async def before_session_setup_hook(
    agent: Any,  # Always None at the early phase.
    state: dict,
    inputs: dict,
    hook_ctx: Any,
) -> dict | None:
    """Early-phase hook: HOT-PATH-B chat_message reply bypass.

    Fires when a `chat_message` event arrives with a pre-computed
    `{response_text, customer_name}` payload.  Types the reply
    directly into Feige and returns a completed state dict to
    short-circuit the LLM.  Returns `None` when the event is not a
    chat_message reply or HOT-PATH-B is not configured (lets the
    normal flow proceed).

    *hook_ctx* is a `build_node.BrowserUseHookContext` carrying the
    generic helpers + shared state dicts.  See that class for field
    documentation.  `agent` is unused (always `None` at this
    phase) — HOT-PATH-B acquires a browser session directly via
    `hook_ctx.get_or_create_browser_session`.
    """
    # ── Hot-path: configurable action templates (Option B) ──
    # Allows users to define custom hot-path triggers and action sequences
    # in the node editor.  Currently default-bypassed; enable by setting
    # hotPathActions in the node config.
    # Config format:
    #   hotPathActions: [
    #     {
    #       "trigger": {"event_type": "chat_message", "has_fields": ["response_text"]},
    #       "actions": [
    #         {"tool": "feige_open_session", "args": {"customer_name": "{{customer_name}}"}},
    #         {"tool": "feige_send_message", "args": {"text": "{{response_text}}"}}
    #       ]
    #     }
    #   ]
    _hp_b_claim_active = False
    _hp_b_claim_cust = ""
    _hp_b_claim_reply = ""
    _hp_b_claim_source_msg_id = ""
    try:
        _hp_b_raw = (inputs.get("hotPathActions") or {}).get("content")
        _hp_b_actions_list = None
        if isinstance(_hp_b_raw, str) and _hp_b_raw.strip():
            _hp_b_actions_list = json.loads(_hp_b_raw)
        elif isinstance(_hp_b_raw, list):
            _hp_b_actions_list = _hp_b_raw
        # Determine current event type and payload fields.
        # IMPORTANT (customer cross-talk fix 2026-04-22): We must read the
        # payload from the JUST-RESUMED event for THIS cycle, not from
        # state["input"] (stale) and not from state["events"][-1] alone
        # (which can contain an event from a different customer's cycle
        # when multiple chat_messages are interleaved on the same task's
        # shared graph state).
        #
        # Priority order for sourcing the payload:
        #   1. state["prompt_refs"]["events"] (AUTHORITATIVE — this is
        #      written by pend_event_node for THIS cycle's triggering
        #      event, and matches the "Injected triggering event
        #      context" log emitted just above)
        #   2. state["events"][-1].data.human_text (matches #1 in most
        #      cases; used when prompt_refs is missing)
        #   3. state["input"] (legacy fallback ONLY when the current
        #      event is itself a chat_message)
        #
        # Cross-check: if #1 and #2 disagree on customer_name, trust #1
        # and WARN — that is the cross-customer bleed scenario.
        _hp_b_evt_type = ""
        _hp_b_payload = {}
        _hp_b_payload_src = "none"
        _hp_b_payload_from_events_tail = {}
        if isinstance(state, dict):
            # --- 1. prompt_refs.events (authoritative per-cycle) ---
            _hp_b_pr = state.get("prompt_refs")
            if isinstance(_hp_b_pr, dict):
                _hp_b_evt_str = _hp_b_pr.get("events", "")
                if _hp_b_evt_str and isinstance(_hp_b_evt_str, str):
                    try:
                        _hp_b_evt = json.loads(_hp_b_evt_str)
                        _hp_b_evt_type = _hp_b_evt.get("event_type", "") or _hp_b_evt_type
                        _hp_b_pr_ht = _hp_b_evt.get("human_text")
                        if isinstance(_hp_b_pr_ht, str) and _hp_b_pr_ht.strip():
                            try:
                                _hp_b_parsed = json.loads(_hp_b_pr_ht)
                                if isinstance(_hp_b_parsed, dict):
                                    _hp_b_payload = _hp_b_parsed
                                    _hp_b_payload_src = "prompt_refs.events.human_text"
                            except Exception:
                                pass
                    except Exception:
                        pass
            # --- 2. state.events[-1] — also sample so we can detect
            # disagreement with #1 (cross-customer bleed warning). ---
            _hp_b_events_list = state.get("events") or []
            if isinstance(_hp_b_events_list, list) and _hp_b_events_list:
                _hp_b_last_evt = _hp_b_events_list[-1] if isinstance(_hp_b_events_list[-1], dict) else {}
                _hp_b_tail_type = _hp_b_last_evt.get("event_type", "")
                _hp_b_evt_data = _hp_b_last_evt.get("data") or {}
                _hp_b_raw_ht = _hp_b_evt_data.get("human_text") if isinstance(_hp_b_evt_data, dict) else None
                if isinstance(_hp_b_raw_ht, str) and _hp_b_raw_ht.strip():
                    try:
                        _hp_b_tail_parsed = json.loads(_hp_b_raw_ht)
                        if isinstance(_hp_b_tail_parsed, dict):
                            _hp_b_payload_from_events_tail = _hp_b_tail_parsed
                            # Fill in only if prompt_refs.events was empty.
                            if not _hp_b_payload:
                                _hp_b_payload = _hp_b_tail_parsed
                                _hp_b_payload_src = "events[-1].data.human_text"
                                _hp_b_evt_type = _hp_b_tail_type or _hp_b_evt_type
                    except Exception:
                        pass
            # --- 3. Legacy state.input fallback ---
            # Only trust state.input when the current cycle is itself a
            # chat_message AND we could not source a payload from #1/#2.
            # Otherwise the inherited value is from a previous customer.
            if not _hp_b_payload and _hp_b_evt_type == "chat_message":
                _hp_b_input = state.get("input", "")
                if isinstance(_hp_b_input, str) and _hp_b_input.strip():
                    try:
                        _hp_b_parsed = json.loads(_hp_b_input)
                        if isinstance(_hp_b_parsed, dict):
                            _hp_b_payload = _hp_b_parsed
                            _hp_b_payload_src = "state.input[legacy-fallback]"
                    except Exception:
                        pass
            # --- 4. Response-payload fallback ---
            # Under bursty queues prompt_refs.events can be empty while a
            # stale browser_event remains in state.  If the current input is
            # clearly a Q&A reply, recover it here and force HOT-PATH-B.
            #
            # ws006 (2026-06-06): but NOT when the CURRENT cycle is a fresh
            # browser_event (a new customer message). In that case state.input /
            # messages[4] still holds the PREVIOUS turn's reply; recovering it
            # forces HOT-PATH-B, which then source-verify-drops it as stale —
            # consuming the invocation so the new customer message never reaches
            # PreDispatch. Under WS dispatch the message is then never re-dispatched
            # (observer dedup + DOM suppressed) → permanently stuck (live 2026-06-06:
            # 'sc' 2nd msg). build_helpers.py already suppresses the response payload
            # for browser_event cycles; mirror that here so the browser_event flows
            # to PreDispatch for fresh Q&A. A genuinely-pending reply still has its
            # own a2a_response/chat_message event (and the drift-recovery override
            # below handles a2a_response explicitly).
            if (
                not state.get("_ecan_predispatch_actionable_items")
                and _hp_b_evt_type != "browser_event"
            ):
                _hp_b_candidates = []
                _hp_b_current_values = set()
                _hp_b_current_input = state.get("current_invocation_input")
                if isinstance(_hp_b_current_input, str) and _hp_b_current_input.strip():
                    _hp_b_current_values.add(_hp_b_current_input.strip())
                _hp_b_attrs = state.get("attributes")
                if isinstance(_hp_b_attrs, dict):
                    _hp_b_attr_current_input = _hp_b_attrs.get("current_invocation_input")
                    if isinstance(_hp_b_attr_current_input, str) and _hp_b_attr_current_input.strip():
                        _hp_b_current_values.add(_hp_b_attr_current_input.strip())
                _hp_b_input = state.get("input", "")
                if isinstance(_hp_b_input, str) and _hp_b_input.strip():
                    _hp_b_candidates.append(_hp_b_input)
                _hp_b_messages = state.get("messages")
                if isinstance(_hp_b_messages, list) and len(_hp_b_messages) > 4:
                    _hp_b_msg_input = _hp_b_messages[4]
                    if isinstance(_hp_b_msg_input, str) and _hp_b_msg_input.strip():
                        _hp_b_candidates.append(_hp_b_msg_input)
                for _hp_b_candidate in _hp_b_candidates:
                    try:
                        _hp_b_parsed = json.loads(_hp_b_candidate)
                    except Exception:
                        continue
                    if not isinstance(_hp_b_parsed, dict):
                        continue
                    if (
                        str(_hp_b_parsed.get("response_text") or "").strip()
                        and str(
                            _hp_b_parsed.get("customer_name")
                            or _hp_b_parsed.get("customer_id")
                            or ""
                        ).strip()
                    ):
                        _hp_b_parsed_customer = str(
                            _hp_b_parsed.get("customer_name")
                            or _hp_b_parsed.get("customer_id")
                            or ""
                        ).strip()
                        _hp_b_parsed_response = str(_hp_b_parsed.get("response_text") or "").strip()
                        _hp_b_payload_customer = str(
                            _hp_b_payload.get("customer_name")
                            or _hp_b_payload.get("customer_id")
                            or ""
                        ).strip()
                        _hp_b_payload_response = str(_hp_b_payload.get("response_text") or "").strip()
                        _hp_b_candidate_is_current = _hp_b_candidate.strip() in _hp_b_current_values
                        _hp_b_use_response_payload = not _hp_b_payload
                        if (
                            not _hp_b_use_response_payload
                            and _hp_b_candidate_is_current
                            and (
                                _hp_b_parsed_customer != _hp_b_payload_customer
                                or _hp_b_parsed_response != _hp_b_payload_response
                            )
                        ):
                            _hp_b_use_response_payload = True
                        if _hp_b_use_response_payload:
                            _hp_b_payload = _hp_b_parsed
                            _hp_b_payload_src = "state.input[response-fallback]"
                            _hp_b_evt_type = "chat_message"
                            logger.warning(
                                f"[BrowserAutomation] HOT-PATH-B: recovered "
                                f"chat_message response payload from state input "
                                f"while prompt_refs/events were stale or empty; "
                                f"customer={_hp_b_payload.get('customer_name') or _hp_b_payload.get('customer_id')!r}"
                            )
                            break
        # 2026-05-19 drift-recovery override.  When DIRECT-DELIVERY
        # exhausts drift retries, pend_event preserves the response_text
        # in state.input AND calls mark_drift_recovery_pending(cust) on
        # the module-level signal (see drift_recovery_signal.py).  The
        # subsequent a2a_response event carries that response_text in
        # prompt_refs.events.human_text, so payload extraction (#1
        # above) populates _hp_b_payload correctly but leaves
        # _hp_b_evt_type='a2a_response'.  Without this override
        # HOT-PATH-B's chat_message rule trigger fails to match, the
        # node short-circuits as 'first_invocation_skip', and the
        # preserved reply is silently dropped — reproduced live
        # 2026-05-19 17:42 for 客户05 / 18:18 for 客户20.
        #
        # An earlier attempt routed the signal via
        # state['_ecan_drift_recovery_pending'], but the langgraph
        # state pipeline strips unknown keys between pend_event_node
        # exit and HOT-PATH-B entry (confirmed via PROBE: marker
        # present at pend_event exit, missing at HOT-PATH-B entry,
        # different state_id).  Module-level signal bypasses that.
        #
        # Bounded by drift exhaustion rate (~1-2/flood) AND consumed
        # one-shot per customer AND TTL-evicted after 60s — so this
        # doesn't reintroduce the Option F typing-lock contention storm.
        try:
            if (
                isinstance(state, dict)
                and _hp_b_payload
                and _hp_b_evt_type == "a2a_response"
                and str(_hp_b_payload.get("response_text") or "").strip()
            ):
                _hp_b_drift_cust = (
                    _hp_b_payload.get("customer_name")
                    or _hp_b_payload.get("customer_id")
                    or ""
                )
                if _hp_b_drift_cust:
                    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.drift_recovery_signal import (
                        consume_drift_recovery_pending,
                        mark_recovery_in_flight,
                    )
                    _hp_b_drift_record = consume_drift_recovery_pending(_hp_b_drift_cust)
                    if _hp_b_drift_record:
                        logger.info(
                            f"[BrowserAutomation] HOT-PATH-B: drift-recovery "
                            f"override fired - cust={_hp_b_drift_cust!r}, "
                            f"was evt_type=a2a_response src={_hp_b_payload_src}, "
                            f"forcing chat_message rule match to retry typed delivery"
                        )
                        _hp_b_evt_type = "chat_message"
                        _hp_b_payload_src = (_hp_b_payload_src or "") + "+drift-recovery"
                        # 2026-05-19 Bug 2: also mark recovery-in-flight
                        # so hot_path.py's source-verify drift check
                        # (line 484-495) applies a longer wait + more
                        # attempts before aborting.  Reproduced live
                        # 2026-05-19 19:33 for 客户09: override fired,
                        # rule matched, typing-lock acquired, session
                        # opened — then source-verify drift killed it
                        # with chat thread customer='' and the reply was
                        # lost.  Marking here softens that check.
                        try:
                            mark_recovery_in_flight(_hp_b_drift_cust)
                        except Exception as _rif_err:
                            logger.debug(
                                f"[BrowserAutomation] HOT-PATH-B: "
                                f"mark_recovery_in_flight failed "
                                f"(non-fatal): {_rif_err}"
                            )
        except Exception as _drift_override_err:
            logger.warning(
                f"[BrowserAutomation] HOT-PATH-B: drift-recovery override "
                f"check failed (non-fatal): {_drift_override_err}"
            )
        # Cross-customer bleed detection: if prompt_refs.events (cycle
        # truth) disagrees with state.events[-1] (accumulated tail), WARN
        # loudly and trust prompt_refs. Previously we trusted tail first,
        # which caused HOT-PATH-B to type customer B's reply into customer
        # C's chat when their cycles interleaved on the shared task state.
        try:
            if (
                _hp_b_payload
                and _hp_b_payload_from_events_tail
                and _hp_b_payload is not _hp_b_payload_from_events_tail
            ):
                _cn_cur = (
                    _hp_b_payload.get("customer_name")
                    or _hp_b_payload.get("customer_id")
                    or ""
                )
                _cn_tail = (
                    _hp_b_payload_from_events_tail.get("customer_name")
                    or _hp_b_payload_from_events_tail.get("customer_id")
                    or ""
                )
                if _cn_cur and _cn_tail and _cn_cur != _cn_tail:
                    logger.warning(
                        f"[BrowserAutomation] HOT-PATH-B: cycle/tail customer "
                        f"disagreement — cycle(prompt_refs)={_cn_cur!r} "
                        f"tail(events[-1])={_cn_tail!r}; trusting cycle. "
                        f"This indicates state.events accumulated from a "
                        f"prior customer's resume that is not the current "
                        f"cycle — defence-in-depth for graph-state bleed."
                    )
        except Exception:
            pass
        # Cross-check: detect stale-state bleed. If state.input carries a
        # customer_name different from the per-cycle payload's, log a
        # WARN so we can track residual bleed after this fix.
        try:
            if _hp_b_payload and isinstance(state, dict):
                _hp_b_state_input = state.get("input", "")
                if isinstance(_hp_b_state_input, str) and _hp_b_state_input.strip():
                    try:
                        _hp_b_si = json.loads(_hp_b_state_input)
                        if isinstance(_hp_b_si, dict):
                            _hp_b_cn_cur = (_hp_b_payload.get("customer_name") or _hp_b_payload.get("customer_id") or "")
                            _hp_b_cn_stale = (_hp_b_si.get("customer_name") or _hp_b_si.get("customer_id") or "")
                            if _hp_b_cn_cur and _hp_b_cn_stale and _hp_b_cn_cur != _hp_b_cn_stale:
                                logger.warning(
                                    f"[BrowserAutomation] HOT-PATH-B: detected stale state.input bleed "
                                    f"(cur_cycle_customer='{_hp_b_cn_cur}' src={_hp_b_payload_src} "
                                    f"!= state.input_customer='{_hp_b_cn_stale}'); using cur_cycle payload"
                                )
                    except Exception:
                        pass
        except Exception:
            pass
        # Entry-log so we can see HOT-PATH-B was considered and why it
        # did (not) fire.
        logger.info(
            f"[BrowserAutomation] HOT-PATH-B: entry "
            f"event_type={_hp_b_evt_type or 'none'}, "
            f"payload_keys={list(_hp_b_payload.keys()) if _hp_b_payload else []}, "
            f"payload_src={_hp_b_payload_src}, "
            f"payload_customer={_hp_b_payload.get('customer_name') or _hp_b_payload.get('customer_id') or '-'}, "
            f"rules_configured={len(_hp_b_actions_list) if isinstance(_hp_b_actions_list, list) else 0}, "
            f"node={hook_ctx.node_name}"
        )
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.system_message_filter import (
                first_system_row_match as _hp_b_system_row_match,
            )
            _hp_b_system_reason = _hp_b_system_row_match(_hp_b_payload)
            if _hp_b_system_reason:
                logger.warning(
                    f"[BrowserAutomation] HOT-PATH-B: dropped system/non-customer "
                    f"reply payload reason={_hp_b_system_reason!r}, "
                    f"customer={_hp_b_payload.get('customer_name') or _hp_b_payload.get('customer_id')!r}, "
                    f"node={hook_ctx.node_name}"
                )
                state.setdefault("result", {})["llm_result"] = {
                    "all_done": True,
                    "work_done": False,
                    "hot_path": True,
                    "hot_path_type": "system_reply_drop",
                }
                return state
        except Exception as _hp_b_system_err:
            logger.debug(
                f"[BrowserAutomation] HOT-PATH-B: system-payload filter failed "
                f"(non-fatal): {_hp_b_system_err}"
            )
        if isinstance(_hp_b_actions_list, list) and _hp_b_actions_list:

            for _hp_b_rule in _hp_b_actions_list:
                if not isinstance(_hp_b_rule, dict):
                    continue
                _hp_b_trigger = _hp_b_rule.get("trigger", {})
                # Check trigger conditions
                if _hp_b_trigger.get("event_type") and _hp_b_trigger["event_type"] != _hp_b_evt_type:
                    continue
                _hp_b_required = _hp_b_trigger.get("has_fields", [])
                if not all(f in _hp_b_payload for f in _hp_b_required):
                    continue
                # Trigger matched — execute action sequence
                _hp_b_action_seq = _hp_b_rule.get("actions", [])
                if not _hp_b_action_seq:
                    continue
                logger.info(
                    f"[BrowserAutomation] HOT-PATH-B: trigger matched "
                    f"(event={_hp_b_evt_type}, rule={_hp_b_trigger}), "
                    f"executing {len(_hp_b_action_seq)} actions"
                )
                # ── Replay dedup guard (fixes observed crosstalk loop) ──
                # 2026-04-22 11:51 run: HOT-PATH-B re-entered 8+ times with
                # an IDENTICAL payload ({customer_name:'客户B', response_text:...})
                # because send_response_back's fallback path keeps re-firing
                # the same chat_message after `Chat not found: 客户B` errors.
                # Each replay re-ran feige_open_session + feige_send_message,
                # and due to a brief focus race between cycles, some of those
                # sends landed in the wrong customer's chat pane (客户C got
                # 客户B's XXL answer).  Short-TTL dedup on (cust, reply-hash)
                # breaks the loop without blocking legitimate future replies.
                _hp_b_dedup_cust = (
                    _hp_b_payload.get("customer_name")
                    or _hp_b_payload.get("customer_id")
                    or ""
                )
                _hp_b_dedup_reply = _hp_b_payload.get("response_text") or ""
                _hp_b_source_msg_id = str(
                    _hp_b_payload.get("source_customer_msg_id")
                    or _hp_b_payload.get("latest_message_msg_id")
                    or _hp_b_payload.get("reply_to_msg_id")
                    or ""
                ).strip()
                _hp_b_claim_cust = _hp_b_dedup_cust
                _hp_b_claim_reply = _hp_b_dedup_reply
                _hp_b_claim_source_msg_id = _hp_b_source_msg_id
                _hp_b_dedup_age = _ds.claim_send_for_turn(
                    _hp_b_dedup_cust, _hp_b_dedup_reply, _hp_b_source_msg_id
                )
                if _hp_b_dedup_age > 0:
                    logger.info(
                        f"[BrowserAutomation] HOT-PATH-B: dedup skip "
                        f"cust={_hp_b_dedup_cust!r} reply_len="
                        f"{len(_hp_b_dedup_reply)} (identical reply already "
                        f"sent {_hp_b_dedup_age:.1f}s ago, "
                        f"source_msg_id={_hp_b_source_msg_id!r}), "
                        f"node={hook_ctx.node_name}"
                    )
                    # Release the cross-scope inflight lock so the
                    # *next* genuine customer turn isn't blocked by
                    # the stale inflight record from the loop.
                    try:
                        _hp_b_skip_cust = hook_ctx.normalize_dispatch_identity_key(_hp_b_dedup_cust)
                        if _hp_b_skip_cust:
                            hook_ctx.clear_dispatch_inflight(_hp_b_skip_cust)
                    except Exception:
                        pass
                    if (
                        _hp_b_payload_src == "state.input[response-fallback]"
                        and isinstance(state, dict)
                        and state.get("_ecan_predispatch_actionable_items")
                    ):
                        try:
                            state.pop("input", None)
                            state.pop("current_invocation_input", None)
                            _hp_b_msgs = state.get("messages")
                            if isinstance(_hp_b_msgs, list) and len(_hp_b_msgs) > 4:
                                _hp_b_msgs[4] = ""
                            _hp_b_attrs = state.get("attributes")
                            if isinstance(_hp_b_attrs, dict):
                                _hp_b_attrs.pop("current_invocation_input", None)
                        except Exception:
                            pass
                        logger.info(
                            f"[BrowserAutomation] HOT-PATH-B: deduped "
                            f"response-fallback will not short-circuit "
                            f"pre-dispatch actionable_items, "
                            f"node={hook_ctx.node_name}"
                        )
                        return None
                    state.setdefault("result", {})["llm_result"] = {
                        "all_done": True, "work_done": False,
                        "hot_path": True, "hot_path_type": "dedup_skip",
                    }
                    return state
                _hp_b_claim_active = True
                # ── Pre-record the outgoing reply text BEFORE send ──
                # The equality guard in PreDispatch compares the DOM's
                # sidebar `last_message` against this recorded text to
                # recognise our own DOM-echo events and skip them.  By
                # recording *before* feige_send_message runs, we close
                # the race window entirely: if a DOM diff fires while
                # typing is in flight, the recorded text is already
                # available for comparison.  If the send ultimately
                # fails, the recorded text is harmless — the DOM won't
                # contain it, so the equality guard will never match a
                # genuine event against it.
                try:
                    _hp_b_pre_cust = hook_ctx.normalize_dispatch_identity_key(
                        _hp_b_payload.get("customer_name")
                        or _hp_b_payload.get("customer_id")
                        or ""
                    )
                    _hp_b_pre_reply = _ds.remember_agent_reply(
                        _hp_b_pre_cust,
                        _hp_b_payload.get("response_text") or ""
                    )
                    if _hp_b_pre_cust and _hp_b_pre_reply:
                        logger.info(
                            f"[BrowserAutomation] HOT-PATH-B: pre-recorded "
                            f"last_agent_reply for '{_hp_b_pre_cust}' "
                            f"(len={len(_hp_b_pre_reply)}, before send), "
                            f"node={hook_ctx.node_name}"
                        )
                except Exception as _hp_b_pre_err:
                    logger.warning(
                        f"[BrowserAutomation] HOT-PATH-B: pre-record reply failed: {_hp_b_pre_err}"
                    )
                from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller as _hp_b_ctrl
                _hp_b_actions_reg = _hp_b_ctrl.registry.registry.actions
                _hp_b_session = await hook_ctx.get_or_create_browser_session(
                    hook_ctx.mainwin, state=state, calling_agent_id=hook_ctx.calling_agent_id
                )
                if not _hp_b_session:
                    logger.warning("[BrowserAutomation] HOT-PATH-B: no browser session")
                    if _hp_b_claim_active:
                        try:
                            _ds.unclaim_send_for_turn(
                                _hp_b_claim_cust,
                                _hp_b_claim_reply,
                                _hp_b_claim_source_msg_id,
                            )
                        except Exception:
                            pass
                        _hp_b_claim_active = False
                    break
                # ── Delegate Feige DOM orchestration to the hook bundle ──
                # (Phase 4 B-refined cleanup, 2026-04-23.)  The
                # ~440 lines of pre-action tab focus, typing-lock
                # acquire, action-sequence execution with per-tool
                # verification (post-open active-customer check,
                # pre-send re-verify + re-open recovery), and
                # post-success tab restore now live in
                # ``feige_chat.hot_path.execute``.  Typing-lock
                # release is handled inside the executor's
                # ``finally`` for every exit path (success,
                # abort, exception).
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.hot_path import (
                    execute as _hp_b_feige_execute,
                )
                _hp_b_typing_cust = hook_ctx.normalize_dispatch_identity_key(
                    _hp_b_payload.get("customer_name")
                    or _hp_b_payload.get("customer_id")
                    or ""
                )
                _hp_b_outcome = await _hp_b_feige_execute(
                    browser_session=_hp_b_session,
                    customer_key=_hp_b_typing_cust,
                    action_seq=_hp_b_action_seq,
                    payload=_hp_b_payload,
                    actions_registry=_hp_b_actions_reg,
                    resolve_template=hook_ctx.resolve_template,
                    node_name=hook_ctx.node_name,
                    # Pass langgraph state so hot_path._run_one_action
                    # can resolve per-node tunable overrides from
                    # state.metadata.browser_auto_overrides (Fix 2026-05-18
                    # to let product-listing skills keep their longer
                    # timeouts while chat keeps tight v0.9.79 defaults).
                    state=state,
                )
                _hp_b_all_ok = _hp_b_outcome.ok
                _hp_b_typing_acquired = _hp_b_outcome.typing_acquired
                logger.info(
                    f"[BrowserAutomation] HOT-PATH-B: executor returned "
                    f"ok={_hp_b_all_ok} reason={_hp_b_outcome.reason!r} "
                    f"actions_attempted={_hp_b_outcome.actions_attempted} "
                    f"last_tool_error={_hp_b_outcome.last_tool_error!r}, "
                    f"node={hook_ctx.node_name}"
                )

                # (Feige action-loop body moved to
                # ``feige_chat.hot_path.execute`` — see above.)
                if (
                    not _hp_b_all_ok
                    and _hp_b_outcome.reason == "stale_reply_source_msg_id"
                ):
                    # The reply reached the front desk correctly, but it
                    # answers an older Feige customer bubble.  Treat it as
                    # handled/dropped, leave the recent-send claim in place
                    # briefly to suppress replays, and do not clear a newer
                    # dispatch inflight lock for the same customer.
                    _hp_b_claim_active = False
                    try:
                        _stale_cust = hook_ctx.normalize_dispatch_identity_key(
                            _hp_b_payload.get("customer_name")
                            or _hp_b_payload.get("customer_id")
                            or ""
                        )
                        _expected_msg_id = str(
                            _hp_b_payload.get("source_customer_msg_id")
                            or _hp_b_payload.get("latest_message_msg_id")
                            or _hp_b_payload.get("reply_to_msg_id")
                            or ""
                        ).strip()
                        _current_msg_id = _ds.last_dispatched_msg_id_by_customer.get(
                            _stale_cust, ""
                        )
                        if _stale_cust and (
                            not _current_msg_id or _current_msg_id == _expected_msg_id
                        ):
                            hook_ctx.clear_dispatch_inflight(_stale_cust)
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: cleared "
                                f"dispatch_inflight after stale reply drop "
                                f"for cust={_stale_cust!r}, node={hook_ctx.node_name}"
                            )
                            # ws142: a cold-start card was dispatched under the
                            # 'card:<talk>' identity, so its inflight marker is keyed
                            # there (and on the bare <talk>) — NOT under the resolved
                            # name cleared above. The ws126 backstop dedup probes
                            # card:<talk>/<talk>/<name>, so a surviving card-keyed
                            # inflight BLOCKS the intended re-dispatch of the newer
                            # bubble → the stale-dropped reply never recovers (live 肽斯特
                            # 15:38: answer stale-dropped, then 'WS hot path already
                            # dispatching card:<talk>' for 2min, question answered
                            # nowhere). Clear the talk-keyed variants too. mt030 +
                            # msg-id dedup in enrich_item remain the double-answer guard.
                            # Reversible: ECAN_FEIGE_STALE_CLEAR_CARD_INFLIGHT=0.
                            if os.environ.get(
                                "ECAN_FEIGE_STALE_CLEAR_CARD_INFLIGHT", "1"
                            ) != "0":
                                try:
                                    from .ws_session import talk_for_name as _sd_t4n
                                    _sd_talk = str(_sd_t4n(_stale_cust) or "").strip()
                                except Exception:
                                    _sd_talk = ""
                                if _sd_talk:
                                    for _sd_k in (f"card:{_sd_talk}", _sd_talk):
                                        try:
                                            hook_ctx.clear_dispatch_inflight(_sd_k)
                                        except Exception:
                                            pass
                                    logger.info(
                                        f"[BrowserAutomation] ws142: also cleared "
                                        f"inflight for card:{_sd_talk}/{_sd_talk} after "
                                        f"stale-drop so the backstop re-dispatch isn't "
                                        f"blocked, cust={_stale_cust!r}"
                                    )
                            # mt052L (2026-05-29): also clear the dispatched-
                            # msg_id ledger entry so PreDispatch's msg_id-
                            # based dedup doesn't suppress the next scrape's
                            # legitimate re-dispatch of the newer customer
                            # message.  Without this clear, the customer's
                            # follow-up question stays silently unanswered
                            # — 客户02/06/07 trace 2026-05-29 13:11→13:13
                            # showed each of them getting one QA reply, the
                            # reply being stale-dropped due to a rapidly-
                            # following customer bubble, mt038A rescue retry
                            # failing, and then no further QA dispatch ever
                            # firing because last_dispatched_msg_id still
                            # equalled _expected_msg_id and PreDispatch saw
                            # the customer as "already handled".
                            try:
                                _ds.last_dispatched_msg_id_by_customer.pop(
                                    _stale_cust, None
                                )
                                logger.info(
                                    f"[BrowserAutomation] HOT-PATH-B: mt052L "
                                    f"cleared last_dispatched_msg_id for "
                                    f"cust={_stale_cust!r} after stale-drop "
                                    f"so PreDispatch can re-dispatch the "
                                    f"customer's still-pending newer message"
                                )
                            except Exception as _mt052l_clear_err:
                                logger.debug(
                                    f"[BrowserAutomation] HOT-PATH-B: mt052L "
                                    f"last_dispatched_msg_id clear failed "
                                    f"(non-fatal): {_mt052l_clear_err}"
                                )
                            # ws155: complete the clear via the unified primitive. mt052L above
                            # cleared msg-id and ws142 cleared inflight, but NEITHER cleared the
                            # identity_key dedup — which then blocked re-dispatch for up to ~1h
                            # (identity TTL 3600s), orphaning the customer's newer message.
                            # clear_dispatch_blockers clears ALL blockers (msg-id/identity/inflight)
                            # across all keys (name/card:<talk>/<talk>); it never touches the
                            # suppressor stores, so no double-send risk. Additive + gated.
                            if os.environ.get("ECAN_FEIGE_UNIFIED_BLOCKER_CLEAR", "1") != "0":
                                try:
                                    _u155 = _ds.clear_dispatch_blockers(
                                        _stale_cust, reason="mt052L_stale"
                                    )
                                    logger.info(
                                        f"[BrowserAutomation] ws155 unified blocker-clear "
                                        f"(mt052L) cust={_stale_cust!r}: {_u155}"
                                    )
                                except Exception as _u155_err:
                                    logger.debug(
                                        f"[BrowserAutomation] ws155 unified-clear failed "
                                        f"(non-fatal): {_u155_err}"
                                    )
                        else:
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: kept "
                                f"dispatch_inflight after stale reply drop "
                                f"for cust={_stale_cust!r} because newer "
                                f"msg_id is recorded, node={hook_ctx.node_name}"
                            )
                    except Exception as _hp_b_stale_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: stale-drop "
                            f"inflight handling failed: {_hp_b_stale_err}"
                        )
                    state.setdefault("result", {})["llm_result"] = {
                        "all_done": True,
                        "work_done": False,
                        "hot_path": True,
                        "hot_path_type": "stale_reply_drop",
                    }
                    logger.warning(
                        f"[BrowserAutomation] HOT-PATH-B: dropped stale "
                        f"reply instead of typing it, node={hook_ctx.node_name}"
                    )
                    return state
                if _hp_b_all_ok:
                    # Mark this (cust, reply) as sent so any immediate
                    # replay of the same chat_message (from
                    # send_response_back fallback path) is deduped
                    # by the guard at the top of HOT-PATH-B.
                    try:
                        _ds.mark_sent_for_turn(
                            _hp_b_dedup_cust,
                            _hp_b_dedup_reply,
                            _hp_b_source_msg_id,
                        )
                    except Exception:
                        pass
                    _hp_b_claim_active = False
                    # Reply text was already pre-recorded before send
                    # (see the `Pre-record the outgoing reply text BEFORE
                    # send` block above). No timer-based cooldown is
                    # needed — PreDispatch's equality guard uses the
                    # pre-recorded text directly to recognise DOM echoes.

                    # Release the QA-response pending lock so the next
                    # *genuine* customer turn for this customer can be
                    # dispatched again.  Acquired in
                    # agent.mcp.server.chat_utils.chat_tools.send_chat
                    # on the first response-bearing payload.  Keyed by
                    # (recipient=this typing agent, customer).  Safe
                    # no-op if the lock already expired via TTL.
                    try:
                        from agent.mcp.server.chat_utils.chat_tools import (
                            clear_qa_response_pending as _hp_b_clear_pending,
                        )
                        _hp_b_clr_cust = hook_ctx.normalize_dispatch_identity_key(
                            _hp_b_payload.get("customer_name")
                            or _hp_b_payload.get("customer_id")
                            or ""
                        )
                        if _hp_b_clr_cust and hook_ctx.calling_agent_id:
                            _hp_b_clear_pending(str(hook_ctx.calling_agent_id), _hp_b_clr_cust)
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: cleared "
                                f"qa_response_pending lock for "
                                f"recipient={hook_ctx.calling_agent_id!r} "
                                f"cust={_hp_b_clr_cust!r}, node={hook_ctx.node_name}"
                            )
                    except Exception as _hp_b_clr_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: "
                            f"qa_response_pending clear failed: {_hp_b_clr_err}"
                        )

                    # Release the cross-scope dispatch-inflight
                    # lock so the next customer turn (or a
                    # queued follow-up already visible in the
                    # sidebar) can be dispatched by the first
                    # PreDispatch that notices it.
                    try:
                        if _hp_b_clr_cust:
                            hook_ctx.clear_dispatch_inflight(_hp_b_clr_cust)
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: cleared "
                                f"dispatch_inflight lock for "
                                f"cust={_hp_b_clr_cust!r}, node={hook_ctx.node_name}"
                            )
                    except Exception as _hp_b_cdi_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: "
                            f"dispatch_inflight clear failed: {_hp_b_cdi_err}"
                        )
                    # Evict this customer from assigned_sessions so the next
                    # customer message for them re-dispatches. Without this, the
                    # PreDispatch dedup guard (`if assigned_sessions.get(sid): continue`)
                    # would permanently skip this customer after their first reply.
                    try:
                        # Prefer the shared module-level dispatch_state
                        # (see hook_ctx.dispatch_state_by_agent). Fall back
                        # to the per-session attribute only if for some reason
                        # PreDispatch hasn't run yet.
                        _hp_b_shared_key = (
                            str(hook_ctx.calling_agent_id or ""),
                            str(hook_ctx.node_name or ""),
                            "_ecan_frontdesk_dispatch_state",
                        )
                        _hp_b_ds = hook_ctx.dispatch_state_by_agent.get(_hp_b_shared_key)
                        if not isinstance(_hp_b_ds, dict):
                            _hp_b_ds = getattr(_hp_b_session, "_ecan_frontdesk_dispatch_state", None)
                        if isinstance(_hp_b_ds, dict):
                            _hp_b_as = _hp_b_ds.get("assigned_sessions") or {}
                            _hp_b_raw_sid = (
                                _hp_b_payload.get("session_id")
                                or _hp_b_payload.get("customer_name")
                                or _hp_b_payload.get("customer_id")
                                or ""
                            )
                            if _hp_b_raw_sid and _hp_b_raw_sid in _hp_b_as:
                                _hp_b_as.pop(_hp_b_raw_sid, None)
                                logger.info(
                                    f"[BrowserAutomation] HOT-PATH-B: evicted "
                                    f"assigned_sessions[{_hp_b_raw_sid!r}] so next "
                                    f"customer message will re-dispatch, node={hook_ctx.node_name}"
                                )
                    except Exception as _hp_b_evict_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: assigned_sessions eviction failed: {_hp_b_evict_err}"
                        )
                    # (Tab restore + typing-lock release now
                    # handled inside feige_chat.hot_path.execute.)
                    state.setdefault("result", {})["llm_result"] = {
                        "all_done": True, "work_done": False,
                        "hot_path": True, "hot_path_type": "configurable",
                    }
                    logger.info(f"[BrowserAutomation] HOT-PATH-B: all actions completed, node={hook_ctx.node_name}")
                    return state
                else:
                    if _hp_b_claim_active:
                        try:
                            _ds.unclaim_send_for_turn(
                                _hp_b_claim_cust,
                                _hp_b_claim_reply,
                                _hp_b_claim_source_msg_id,
                            )
                        except Exception:
                            pass
                        _hp_b_claim_active = False
                    # Any action in the sequence failed (e.g.
                    # feige_open_session returning "Session not
                    # found" when Feige's SPA is transiently in a
                    # bad state).  Release the cross-scope
                    # `_dispatch_inflight` lock here —
                    # otherwise PreDispatch keeps skipping the
                    # next message for this customer for the full
                    # 120 s TTL (observed 2026-04-22 11:18:38 —
                    # customer A's question sat unanswered for
                    # `1m 42s` with repeated
                    # `PreDispatch inflight skip ... ttl=120.0s`).
                    # We deliberately do NOT clear
                    # `qa_response_pending` or evict
                    # `assigned_sessions`: the QA worker already
                    # generated a reply and we want the *next*
                    # genuine customer turn to cause a fresh
                    # reply, not for PreDispatch to race with a
                    # half-consumed state.
                    try:
                        _hp_b_fail_cust = hook_ctx.normalize_dispatch_identity_key(
                            _hp_b_payload.get("customer_name")
                            or _hp_b_payload.get("customer_id")
                            or ""
                        )
                        if _hp_b_fail_cust:
                            hook_ctx.clear_dispatch_inflight(_hp_b_fail_cust)
                            # ── Clear last_dispatched_msg_id so PreDispatch
                            # will re-dispatch on the next loop ───────────
                            # Background (incident 2026-05-13 flood test,
                            # 客户11): HOT-PATH-B opened the wrong customer
                            # session ('客户04' instead of '客户11') due to
                            # a CDP-eval race, the crosstalk guard correctly
                            # aborted the send.  But the reply was lost
                            # because PreDispatch's msg-id dedup
                            # (last_dispatched_msg_id_by_customer) still
                            # remembered that 客户11's msg_id had been
                            # dispatched — so PreDispatch refused to
                            # re-dispatch on the next loop and the customer's
                            # question stayed permanently unanswered.
                            # Clearing the record here lets PreDispatch
                            # re-dispatch this customer's still-pending
                            # question on its next scrape pass.  Inflight
                            # was already cleared above.
                            try:
                                _ds.last_dispatched_msg_id_by_customer.pop(
                                    _hp_b_fail_cust, None
                                )
                                logger.info(
                                    f"[BrowserAutomation] HOT-PATH-B: also "
                                    f"cleared last_dispatched_msg_id for "
                                    f"cust={_hp_b_fail_cust!r} so PreDispatch "
                                    f"can re-dispatch the still-pending "
                                    f"customer question; the Q&A bot's "
                                    f"answer was lost but the customer is "
                                    f"still waiting, node={hook_ctx.node_name}"
                                )
                            except Exception as _hp_b_mid_err:
                                logger.debug(
                                    f"[BrowserAutomation] HOT-PATH-B: "
                                    f"last_dispatched_msg_id clear failed "
                                    f"(non-fatal): {_hp_b_mid_err}"
                                )
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: released "
                                f"dispatch_inflight after action-failure "
                                f"for cust={_hp_b_fail_cust!r}, node={hook_ctx.node_name}"
                            )
                    except Exception as _hp_b_fail_cdi_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: inflight clear "
                            f"after failure: {_hp_b_fail_cdi_err}"
                        )
                    # (Typing-lock release now handled inside
                    # feige_chat.hot_path.execute's finally.)
                    # ws170: action_failed is a retry-chain DEAD-END — the
                    # send_response_back short-circuit (correctly) never
                    # propagates it, so a reply that reached HOT-PATH-B via the
                    # runner's fallback dies here silently (live 2026-07-12
                    # 17:00:24 card ack). For a card:<talk> identity the failure
                    # is structural (no row by that name yet): park the reply so
                    # the backstop flushes it once the talk resolves to a real
                    # name. Real-name customers keep the existing recovery
                    # (inflight + last_dispatched cleared above -> PreDispatch
                    # re-dispatches).
                    try:
                        _hp_b_park_cust = str(
                            _hp_b_payload.get("customer_name")
                            or _hp_b_payload.get("customer_id")
                            or ""
                        )
                        if _hp_b_park_cust.startswith("card:"):
                            from . import undeliverable as _hp_b_undlv
                            _hp_b_undlv.park(
                                _hp_b_park_cust,
                                str(_hp_b_payload.get("response_text") or ""),
                                str(_hp_b_payload.get("source_customer_msg_id") or ""),
                                reason="hot_path_action_failed",
                            )
                    except Exception as _hp_b_park_err:
                        logger.debug(
                            f"[BrowserAutomation] ws170 park failed (non-fatal): "
                            f"{_hp_b_park_err}"
                        )
                    state.setdefault("result", {})["llm_result"] = {
                        "all_done": True,
                        "work_done": False,
                        "hot_path": True,
                        "hot_path_type": "action_failed",
                        "hot_path_reason": str(_hp_b_outcome.reason or ""),
                        "last_tool_error": str(_hp_b_outcome.last_tool_error or ""),
                    }
                    logger.warning(
                        f"[BrowserAutomation] HOT-PATH-B: action failed; "
                        f"short-circuiting browser node to avoid full "
                        f"browser-use fallback, reason={_hp_b_outcome.reason!r}, "
                        f"node={hook_ctx.node_name}"
                    )
                    return state
                break  # Only try first matching rule
    except asyncio.CancelledError:
        # ── Diagnostic surface (2026-04-28) ──
        # ``CancelledError`` is ``BaseException`` (not ``Exception``)
        # in Python 3.8+, so the previous bare ``except Exception``
        # below would not log it.  When the parent persistent-worker
        # cycle is cancelled mid-await (e.g., the CDP focus call in
        # ``ensure_feige_tab_focused`` hangs under contention and the
        # supervisor pre-empts), HOT-PATH-B was silently torn down —
        # producing the "ensure-feige-tab: 1 candidate → silence"
        # signature that hid the cejs-reply-never-arrives regression
        # observed 2026-04-28 05:17:27.  Log + re-raise so the cancel
        # still propagates correctly to the runner.
        logger.warning(
            "[BrowserAutomation] HOT-PATH-B: cancelled mid-execute "
            "(parent cycle pre-empted) — typing-lock release handled "
            "by hot_path.execute's finally"
        )
        raise
    except Exception as _hp_b_err:
        if _hp_b_claim_active:
            try:
                _ds.unclaim_send_for_turn(
                    _hp_b_claim_cust,
                    _hp_b_claim_reply,
                    _hp_b_claim_source_msg_id,
                )
            except Exception:
                pass
        logger.warning(
            f"[BrowserAutomation] HOT-PATH-B: check failed (non-fatal): {_hp_b_err}",
            exc_info=True,
        )
        # (Typing-lock release now handled inside
        # feige_chat.hot_path.execute's finally — no defensive
        # release needed here.)



async def before_run_hook(
    agent: Any,
    state: dict,
    inputs: dict,
    hook_ctx: Any,
) -> dict | None:
    """Late-phase hook: PreDispatch customer-message fan-out.

    Fires when a `browser_event` arrives indicating a new customer
    message.  Reads the sidebar preview, scrapes the freshest customer
    bubble, applies msg-id dedup + DOM-echo guards, and fans out to
    available Q&A workers via the generic fan-out skeleton.  Returns a
    completed state dict when PreDispatch handled the event (skips the
    LLM); returns `None` to let the LLM proceed.
    """
    # ── Parse preDispatch config ──
    # Back-compat default: the pre-refactor monolithic wrapper always
    # invoked the Feige-specific enrichment (customer-bubble scrape,
    # msg-id dedup, dom-echo fallback).  The generic skeleton made
    # this opt-in via `preDispatch.site_plugin`, which silently broke
    # existing skill configs (2026-04-23 regression).  Default to
    # `feige_chat` when the raw config omits the field; explicit
    # empty string `""` still opts out.
    _pd_raw = hook_ctx.parse_json_input(inputs, "preDispatch") or {}
    if "site_plugin" not in _pd_raw:
        _pd_raw["site_plugin"] = "feige_chat"
    _pd_config = DispatchConfig.from_raw(_pd_raw)
    logger.info(
        f"[BrowserAutomation] PreDispatch config: enabled={_pd_config.enabled}, "
        f"source_monitor_label={_pd_config.source_monitor_label!r}, "
        f"site_plugin={_pd_config.site_plugin!r}, node={hook_ctx.node_name}"
    )
    if not _pd_config.enabled:
        return None

    # ── Build DispatchContext from hook_ctx ──
    _pd_ctx = DispatchContext(
        state=state,
        calling_agent_id=str(hook_ctx.calling_agent_id or ""),
        node_name=str(hook_ctx.node_name or ""),
        mainwin=hook_ctx.mainwin,
        scope_key=hook_ctx.resolve_scope_key(state),
        cached_browser_sessions=hook_ctx.cached_browser_sessions,
        dispatch_state_by_agent=hook_ctx.dispatch_state_by_agent,
        customer_last_dispatched_msg_id=_ds.last_dispatched_msg_id_by_customer,
        auto_dispatch_last_agent_reply=_ds.last_agent_reply_by_customer,
        is_dispatch_inflight=hook_ctx.is_dispatch_inflight,
        mark_dispatch_inflight=hook_ctx.mark_dispatch_inflight,
        clear_dispatch_inflight=hook_ctx.clear_dispatch_inflight,
        inflight_ttl_s=hook_ctx.inflight_ttl_s,
        normalize_dispatch_identity_key=hook_ctx.normalize_dispatch_identity_key,
        normalize_reply_text=_ds.normalize_reply_text,
        safe_format_dict=hook_ctx.safe_format_dict,
        typing_holder_getter=_typing_lock.holder,
    )
    # ws023: register this context so the WS detector can route messages directly
    # through run() (bypassing the serial front-desk task) when ECAN_FEIGE_WS_DIRECT_QA=1.
    _FEIGE_FD_DISPATCH_REG["slot"] = (_pd_config, _pd_ctx, agent)
    return await _run_frontdesk_dispatch(_pd_config, _pd_ctx, agent)


def register() -> None:
    """Register this bundle's hooks with `build_node`.

    Called automatically when the `feige_chat` package is imported
    (see `__init__.py`).  Idempotent: re-importing the package does
    not double-register.
    """
    from agent.ec_skills.build_node import (
        register_before_browser_session_setup_hook,
        register_before_browser_use_run_hook,
    )
    # Order matters for readability only — each hook is invoked at
    # its own distinct phase, so registration order within a phase is
    # the only thing the hook registry sees.
    register_before_browser_session_setup_hook(before_session_setup_hook)
    register_before_browser_use_run_hook(before_run_hook)
