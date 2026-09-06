"""Feige pre-dispatch ground-truth enrichment plugin.

Relocation target for the Feige-specific block that used to sit inside
``build_node.py``'s ``_maybe_run_frontdesk_dispatch_fastpath`` per-item
loop (original lines 9924-10061, ~135 lines).  The generic
``node_runtime.frontdesk_dispatch.run`` orchestrator calls
:func:`enrich_item` once per actionable item via the plugin-loader
when ``preDispatch.site_plugin`` is ``"feige_chat"``.

What this module owns
---------------------

For each item the front-desk fast-path is about to dispatch:

1. **Chat-thread scrape (ground truth)** — click the customer's
   sidebar row and scrape the most recent customer bubble from the
   thread DOM.  Overrides the sidebar preview ``last_message`` with
   the scraped text (the sidebar preview is notoriously polluted by
   bot auto-replies / system spans / human-agent messages — observed
   21:48:40 on 客户A: sidebar showed "亲亲，在哒~..." auto-reply while
   the customer had just asked "能不能便宜点？").

2. **Msg-id dedup guard** — compare the scraped bubble's ``data-id``
   against the last dispatched msg-id for this customer.  If
   identical, the customer hasn't said anything new and we skip
   regardless of whatever the sidebar preview currently echoes.
   Replaces the older text-based dom-echo guard that suppressed
   follow-ups whenever the sidebar re-echoed our reply (observed
   21:49:14 skipping Q4 "有绿色吗？").

3. **Scrape-failure fallback** — when the scrape didn't return a
   usable msg-id (Feige tab not focusable, selector drift, etc.) we
   fall back to two defences against the runaway loop observed
   22:42-22:43 on 2026-04-22, where the sidebar preview echoed the
   bot's own reply and PreDispatch re-dispatched the same text 8
   times to QA workers:

   - **text-based dom-echo**: skip if the sidebar ``last_message``
     (whitespace-normalised, prefix-limited) matches the reply that
     HOT-PATH-B pre-recorded just before it typed.
   - **assigned_sessions text match**: skip only if this
     ``session_id`` already has an active assignment record for the
     same sidebar/customer text.  A newer sidebar preview must
     supersede the prior assignment even when thread scraping is
     temporarily unavailable.

Contract
--------

The sole public entry-point is :func:`enrich_item`, whose signature
matches the plugin protocol that
``node_runtime.frontdesk_dispatch._load_enrich_plugin`` expects.  See
that module for the calling site.

Each item is mutated in place (``item["last_message"]`` may be
overwritten) and an :class:`EnrichResult` is returned describing
whether the item should be skipped and with what reason.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .dom_assets import scrape_latest_customer_bubble
from .sidebar_preview_js import ROW_PREVIEW_FALLBACK_JS as _ROW_PREVIEW_FALLBACK_JS

# CN builds name the app logger "eCan.cn" (propagate=False) — a bare
# getLogger("eCan") record never reaches its handlers, silencing this
# module's entire log output in packaged CN apps (v0.9.95u incident:
# the WS reader looked dead because none of its lines could land).
from utils.logger_helper import logger_helper as logger

# ── B1 fix (2026-05-14): re-fire deferred system-greeting customers ──
#
# When the chat-thread scrape fails because the typing lock is held by
# another customer's delivery, we defer dispatch and return
# ``skip=True reason="typing_lock_active"``. The DOM monitor only emits
# new ``browser_event`` payloads on *added* sidebar entries — once a
# customer's sidebar row is visible (still showing Feige's auto-greeting,
# without a real customer bubble scraped), nothing causes the monitor
# to re-emit for them, so the dispatch path is never tried again.
#
# This module-level set records the (session_id, customer_key) of every
# deferral. ``event_monitor.py`` checks it on each polling tick and
# forces an emit when the set is non-empty (even with zero ``added``),
# giving the front-desk another shot once the typing lock is released.
# Entries are dropped when the same enrich_item call later succeeds
# (i.e. produces a non-skip EnrichResult) or when ``clear_deferred``
# is called from the typing-lock release hook on the canonical
# ``feige_send_message`` post-action.

_DEFERRED_LOCK = threading.RLock()
# Maps (session_id, customer_key) -> deferral epoch ms (latest defer).
_DEFERRED_FOR_TYPING_LOCK: dict[tuple[str, str], float] = {}
# Stale entries older than this are auto-cleared; we don't want a
# deferred ghost outlasting a session that got closed.
_DEFERRED_TTL_S = 120.0


def _record_deferred(session_id: str, customer_key: str) -> None:
    if not session_id and not customer_key:
        return
    with _DEFERRED_LOCK:
        _DEFERRED_FOR_TYPING_LOCK[(str(session_id), str(customer_key))] = time.time()


def clear_deferred(session_id: str = "", customer_key: str = "") -> int:
    """Drop deferred-tracking entries. Returns number cleared.

    With both args empty, clears every entry (used as a coarse reset on
    shutdown / page reload).  With one or both set, clears only matching
    entries.
    """
    if not session_id and not customer_key:
        with _DEFERRED_LOCK:
            n = len(_DEFERRED_FOR_TYPING_LOCK)
            _DEFERRED_FOR_TYPING_LOCK.clear()
            return n
    s = str(session_id or "")
    c = str(customer_key or "")
    with _DEFERRED_LOCK:
        to_pop = [
            k for k in _DEFERRED_FOR_TYPING_LOCK
            if (not s or k[0] == s) and (not c or k[1] == c)
        ]
        for k in to_pop:
            _DEFERRED_FOR_TYPING_LOCK.pop(k, None)
        return len(to_pop)


def snapshot_deferred() -> list[tuple[str, str]]:
    """Return a snapshot of currently-deferred (session_id, customer_key)
    pairs after pruning anything older than ``_DEFERRED_TTL_S``.
    """
    now = time.time()
    with _DEFERRED_LOCK:
        stale = [k for k, ts in _DEFERRED_FOR_TYPING_LOCK.items() if now - ts > _DEFERRED_TTL_S]
        for k in stale:
            _DEFERRED_FOR_TYPING_LOCK.pop(k, None)
        return list(_DEFERRED_FOR_TYPING_LOCK.keys())


def has_deferred() -> bool:
    """Return True if any non-stale deferral is recorded."""
    return bool(snapshot_deferred())


__all__ = [
    "EnrichResult",
    "enrich_item",
    "snapshot_deferred",
    "has_deferred",
    "clear_deferred",
]


# 2026-05-24 mt038B: Feige sidebar previews like "[商品]" / "[图片]" are
# opaque attachment markers — the underlying customer bubble carries the
# real text (e.g. "透气吗？") but it's reachable only via a chat-thread
# scrape, which requires focusing the customer's tab.  Under flood the
# focus can fail; mt038B treats that case as "defer to next tick"
# rather than dispatching the marker as if it were customer text.
_ATTACHMENT_MARKER_PREVIEWS: frozenset[str] = frozenset({
    "[商品]",
    "[图片]",
    "[视频]",
    "[文件]",
    "[语音]",
    "[链接]",
    "[表情]",
    "[卡券]",
    "[红包]",
    "[位置]",
    "[名片]",
    "[订单]",
})


# ws101: stabilise product-card detail (price / 券 / 发货) against the
# non-deterministic DOM render. scrape_latest_customer_bubble returns the rich
# _cardToText only intermittently — full one turn ("…￥79.90 (券:立减10元)…"),
# title-only or bare "[商品卡片]" the next — which is exactly the flip-flop the
# customer reported (前脚说有优惠，后脚又说没有 / 七天无理由 / 包邮). Keep the
# richest detail we've ever scraped per goods_id and reuse it whenever a later
# scrape comes back thin, so the answer is STABLE once the detail has been seen.
_CARD_DETAIL_CACHE: dict[str, str] = {}
# ws186: goods_ids whose _CARD_DETAIL_CACHE entry came from the captured card
# JSON (product_detail_store) — those entries outrank the DOM span scrape.
_WS186_JSON_GIDS: set = set()
_CARD_DETAIL_MARKERS = ("￥", "¥", "券", "发货")

# ws106: the enriched card text per CONVERSATION (talk_id). The fragile bit was always
# getting the card detail to a TEXT follow-up ("有没有优惠券" / "七天无理由" / "运费险"),
# which never goes through the card path — ws094's pinned-card/recent-messages relied on
# identity matching (card:<talk> vs real name) and kept failing (ws103 run: the coupon
# follow-up reached the LLM with NO card -> "麻烦发下商品卡片"). Keyed by the authoritative
# talk_id and injected directly into the follow-up's last_message — no identity guessing.
_CONV_CARD_TEXT: dict[str, str] = {}


def _card_goods_id(text: str) -> str:
    m = re.search(r"商品ID[:：]\s*(\d+)", text or "")
    return m.group(1) if m else ""


def _card_has_detail(text: str) -> bool:
    return any(m in (text or "") for m in _CARD_DETAIL_MARKERS)


@dataclass
class EnrichResult:
    """Outcome of :func:`enrich_item` for a single dispatch candidate.

    Attributes
    ----------
    skip:
        ``True`` if the orchestrator should ``continue`` past this item
        (customer hasn't said anything new, or we detected our own
        DOM-echo).
    skip_reason:
        Short grep-able tag for the caller's log line.  Values:
        ``""`` (no skip), ``"msg_id_dedup"``, ``"dom_echo"``,
        ``"assigned_sessions_legacy"``.
    scraped_msg_id:
        The ``data-id`` of the customer's most-recent bubble if the
        scrape succeeded, ``""`` otherwise.  The caller stores this in
        its ``customer_last_dispatched_msg_id`` cache on successful
        dispatch so the next cycle can dedup by identity.
    should_clear_stale_assignment:
        Set when the scrape confirmed a genuinely new customer bubble
        AND the legacy ``assigned_sessions`` dict still has a stale
        entry for this session.  Caller pops the entry so the new
        turn can dispatch cleanly.
    """

    skip: bool = False
    skip_reason: str = ""
    scraped_msg_id: str = ""
    should_clear_stale_assignment: bool = False
    extras: dict = field(default_factory=dict)


async def _resolve_card_customer_name(browser_session, log_tag: str) -> str:
    """ws040d: return the REAL customer name of the UNIQUE sidebar conversation
    that is a product card needing reply (preview starts '[商品' AND className has
    'needReply'), or '' when zero/multiple match (don't guess). One light read-only
    sidebar eval — used ONLY to de-synthesize a name-less card so the whole pipeline
    keys on the real name instead of the synthetic 'card:<conv>'."""
    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            _evaluate_js,
        )
        from .dom_assets import (
            ensure_feige_tab_reachable,
            _SESSION_FOCUSED_FEIGE_TID_ATTR,
        )
    except Exception:
        return ""
    # ws045: PIN the eval to the Feige MAIN tab (the one with the sidebar).
    # Without target_id, _evaluate_js defaults to whatever target the session
    # last touched — live trace showed it landing on a THIRD tab (session
    # ...F2D453D1) that has ZERO conversation rows (card_rows=0 total_rows=0),
    # so the matcher could never see the '[商品' row and every card stayed
    # synthetic -> turn-2 amnesia. The bubble-scrape path (which DOES find the
    # sidebar) resolves the main tab exactly this way (dom_assets.py:2598/2612).
    _card_target_id = None
    try:
        if await ensure_feige_tab_reachable(browser_session):
            _card_target_id = getattr(
                browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, None
            )
    except Exception:
        _card_target_id = None
    js = '''(function(){''' + _ROW_PREVIEW_FALLBACK_JS + '''
  function rn(r){
    var n=r.querySelector('[class*="nameLine"], .MP1bk3ccfHC9V2SnPCGD');
    if(n){var t=(n.getAttribute('title')||n.textContent||'').trim();if(t)return t;}
    var s=r.querySelector('[class*="NameContent"], .Jv6FtqUv5VoYARd2pp4y');
    return s?(s.textContent||'').trim():'';
  }
  function rp(r){
    var p=r.querySelector('[class*="msgContent"], .lF_M7QiFB0ukHWpMfQde span');
    var v=p?(p.textContent||'').trim():'';
    if(v) return v;
    return __ecanRowPreviewFallback(r, rn(r));  // ws189: selector drift fallback
  }
  var rows=Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
  var cards=[];
  for(var i=0;i<rows.length;i++){
    var pv=rp(rows[i]);
    if(pv&&pv.indexOf('[商品')===0){
      cards.push({name:rn(rows[i]), needReply:/needReply/.test(String(rows[i].className||''))});
    }
  }
  // ws165: a connect-banner row means a cold-start reopen is in progress — the
  // REAL card sender's row previews the banner (not '[商品'), so a lone '[商品'
  // row may be ANOTHER customer's stale card preview (live 2026-07-10 19:58:10:
  // sc sent the card but sc's row showed '接入'; the only '[商品' row was
  // packet's needReply=false leftover -> sc's answer delivered into packet's
  // conversation). With a banner present, trust the unique match only when it
  // actually needs reply.
  var banner=false;
  for(var b=0;b<rows.length;b++){
    var bv=rp(rows[b]);
    if(bv && /小店(接入|为你服务)/.test(bv)){banner=true;break;}
  }
  // ws044: prefer the UNIQUE '[商品' row (the card conv is often the ACTIVE row,
  // where needReply may NOT be set — requiring needReply was why ws040e silently
  // returned ''); only fall back to needReply to disambiguate when >1 card row.
  var name='';
  if(cards.length===1){
    if(!banner || cards[0].needReply){ name=cards[0].name; }
  }
  else if(cards.length>1){
    var nr=cards.filter(function(c){return c.needReply;});
    if(nr.length===1){ name=nr[0].name; }
  }
  return JSON.stringify({name:name, banner:banner, card_count:cards.length, total_rows:rows.length, cards:cards.slice(0,8)});
})()'''

    async def _try_once():
        r = await _evaluate_js(
            browser_session, js,
            target_id=str(_card_target_id) if _card_target_id else None,
            focus=False, read_only=True, lock_free=True,
            trace_label="feige_resolve_card_name",
        )
        if isinstance(r, str):
            r = json.loads(r)
        return r or {}

    try:
        info = await _try_once()
        name = str(info.get("name") or "").strip()
        if not name:
            # ws044: the sidebar can lag the WS card frame at enrich time (live: card
            # at :56, enrich at :57 -> row not yet matchable). Retry once after a short
            # settle before giving up to the synthetic name.
            await asyncio.sleep(0.6)
            info = await _try_once()
            name = str(info.get("name") or "").strip()
        # ALWAYS log what the sidebar looked like — a no-match here is exactly why a
        # card stays synthetic and splits from the customer's later named messages
        # (the turn-2 amnesia). This was invisible before (silent '' return).
        logger.info(
            f"[BrowserAutomation] {log_tag} ws044 resolve-card-name -> {name!r} "
            f"(card_rows={info.get('card_count')} total_rows={info.get('total_rows')} "
            f"banner={info.get('banner')} cards={info.get('cards')})")
        return name
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] {log_tag} ws044 resolve-card-name failed: {exc}")
        return ""


# ws054: 转人工 handover acknowledgement on the WS-DIRECT-QA path. ws050 only
# wired the emoji-ack into the LEGACY front-desk dispatch (first_system_row_match);
# live traffic routes through THIS enrich path, whose system-message filter SKIPs
# the "转人工" row (reason system_message:last_message:transfer_to_human_label)
# before the front-desk hook ever runs — so a 转人工 (esp. with no platform
# auto-greeting) got no ack at all (live 2026-06-13 04:40:39 cust='sc', 0 acks).
# Detect a handover-family skip here and arm the ack; the placeholder sweeper
# drains it and sends the ":)". Deduped per customer in placeholder_timer.
_WS_HANDOVER_ACK_PATTERNS = (
    "transfer_to_human_label",
    "store_assignment_notice",
    "human_handover_notice",
    "store_auto_greeting",
    "smart_cs_auto_greeting",
)


def _maybe_arm_handover_ack(customer_key: str, hit: object, log_tag: str) -> None:
    """If a skipped system-message row is a 转人工 / handover, arm the emoji-ack."""
    try:
        _h = str(hit or "")
        if not _h or not customer_key or str(customer_key).startswith("card:"):
            return
        if not any(p in _h for p in _WS_HANDOVER_ACK_PATTERNS):
            return
        from .placeholder_timer import note_handover_ack_needed as _note_ho
        _note_ho(str(customer_key))
        logger.info(
            f"[BrowserAutomation] {log_tag} ws054 handover-ack armed for "
            f"cust={customer_key!r} (handover row skipped, hit={_h!r})")
    except Exception:
        pass


async def _scrape_and_override_last_message(
    browser_session,
    item: dict,
    customer_key: str,
    log_tag: str,
    typing_holder_getter: Callable[[], str] | None = None,
    customer_last_dispatched_msg_id: dict | None = None,
) -> str:
    """Scrape the thread for the most recent customer bubble and, if
    successful, overwrite ``item['last_message']``.

    Returns the scraped ``msg_id`` (``""`` on scrape failure).  Mutates
    *item* in place when the scraped text differs from the sidebar
    preview.  *typing_holder_getter*, when provided, is forwarded to
    :func:`scrape_latest_customer_bubble` so its active-session race
    guard fires if HOT-PATH-B is mid-reply to a different customer.

    2026-05-25 mt041B: ``customer_last_dispatched_msg_id`` (mapping
    customer_key → most-recently-dispatched msg_id) is forwarded as the
    burst-rebuild's prior-turn cutoff list.  When the burst walks back
    to a bubble that matches this id, the rebuild stops — that bubble
    belongs to a prior turn even though no agent reply landed between
    it and the current bubble (failed dispatch / mt017 drop / etc.).
    """
    # ws027: a WS-detected product card ([商品卡片] …, ws025) already carries the
    # authoritative product text from the WS frame. ws_text_scrape returns None
    # for cards, so this function falls to the DOM thread scrape — which can't
    # see a 商品卡片 as a customer text bubble (and lags the WS frame), so it
    # refuses (skip_dispatch) / fails the scrape, or mt030 marks it "already
    # answered" (agent_idx > cust_idx). The card then NEVER reaches the QA agent
    # (live 肽斯特 13:40:37 → no LLM turn ever saw it). Trust the WS card: skip
    # the DOM scrape + ALL its skip paths and dispatch with the card text. The
    # dispatch_state recent-reply ledger still blocks genuine duplicates.
    # Kill-switch: ECAN_FEIGE_WS_CARD_TRUST=0.
    _card_preview = str(item.get("last_message") or "").strip()
    if (
        _card_preview.startswith("[商品卡片]")
        and os.environ.get("ECAN_FEIGE_WS_CARD_TRUST", "1") != "0"
    ):
        _card_msg_id = str(
            item.get("latest_message_msg_id") or item.get("msg_id") or ""
        ).strip()
        logger.info(
            f"[BrowserAutomation] {log_tag} ws027: WS product-card for "
            f"cust={customer_key!r} — trusting WS text, skipping DOM "
            f"thread-scrape + mt030 (confirmed new customer message) "
            f"msg_id=...{_card_msg_id[-8:] if _card_msg_id else ''}"
        )
        # ws040d: a name-less card was dispatched under the synthetic 'card:<conv>'
        # identity (the WS frame carries no nickname). That SPLIT identity is why a
        # reply delivered as card:<conv> fails to suppress the placeholder keyed on
        # the real DOM name (sc) — the placeholder pops up AFTER the answer. Resolve
        # the real name from the sidebar NOW (one light read, name-less cards ONLY)
        # and rewrite the item so the WHOLE pipeline — QA, placeholder, reply,
        # suppression, session — keys on the real name. Unique-row gated; on 0/>1
        # matches we keep the synthetic name (delivery's ws040 card-row match still
        # delivers, so this can never regress the now-working card answer).
        if customer_key.startswith("card:"):
            _real_name = ""
            # ws040e: prefer the WS-side name. If ANY named frame arrived on this
            # conversation (e.g. a follow-up text after the card), name_for_talk
            # knows the real name regardless of the transient sidebar preview — far
            # more robust than the DOM '[商品]'-preview matcher, which breaks the
            # moment the customer types after the card (live 肽斯特 14:41: preview
            # became '白色款120码…' → no '[商品]' row → card-row match → stuck).
            _talk = str(item.get("talk_id") or item.get("conversation_id") or "").strip()
            # ws192 (2026-09-06): use the talk-match-GUARDED resolver. The old
            # name_for_talk PRIMARY path was not cross-checked (only the DOM
            # fallback was, ws165), so a stale/wrong _talk_to_name or uid-bridge
            # entry made name_for_talk(<card talk>) return a DIFFERENT customer's
            # name (live 96z: card talk …808602 '钛斯特' → '陆地飞鱼' / talk
            # …179238 → answer mis-delivered under 陆地飞鱼 AND dedup keys split
            # → duplicate answer). name_for_talk_verified rejects a name whose
            # own talk isn't this card's talk.
            if _talk:
                try:
                    from . import ws_session as _wss_name
                    _real_name = str(_wss_name.name_for_talk_verified(_talk) or "").strip()
                except Exception:
                    _real_name = ""
            # Fall back to the DOM card-row matcher only for a true card-ONLY conv
            # (no named frame ever arrived → name_for_talk empty).
            if not _real_name:
                _real_name = await _resolve_card_customer_name(browser_session, log_tag)
                # ws165+ws192: talk-match cross-check the DOM candidate too — if
                # the bridge knows its talk and it is NOT this card's conversation,
                # the row-preview match picked the WRONG customer (live 2026-07-10:
                # sc's card resolved to 'packet' via a stale '[商品' preview). Keep
                # the synthetic card:<talk>; ws060 talk-keyed delivery still reaches
                # the right conv.
                if _real_name and _talk:
                    try:
                        from . import ws_session as _wss_xchk
                        _known_talk = str(_wss_xchk.talk_for_name(_real_name) or "").strip()
                    except Exception:
                        _known_talk = ""
                    if _known_talk and _known_talk != _talk:
                        logger.info(
                            f"[BrowserAutomation] {log_tag} ws192 REJECT DOM card-name "
                            f"candidate {_real_name!r}: their talk is {_known_talk[-8:]}"
                            f"..., card conv is {_talk[-8:]}... — keeping synthetic "
                            f"identity (prevents cross-customer mis-delivery)"
                        )
                        _real_name = ""
            if _real_name and not _real_name.startswith("card:"):
                for _idf in ("customer_name", "name", "customer_id", "session_id"):
                    item[_idf] = _real_name
                item["identity_key"] = f"{_real_name}|{item.get('last_message') or ''}"
                logger.info(
                    f"[BrowserAutomation] {log_tag} ws040e: de-synthesized name-less "
                    f"card {customer_key!r} -> real customer {_real_name!r} "
                    f"(whole pipeline now keys on the real name)")
        # ws098: enrich the card text with the FULL rendered detail (price / 券 / 发货) from
        # the DOM. The WS card frame carries only goods_id + title (_card_text), so questions
        # like "这款有优惠吗 / 多少钱 / 什么时候发货" reach the LLM with no answer (2026-06-20:
        # NASA card -> "暂未查到优惠信息"). The DOM card bubble (.chatd-card) IS rendered with
        # everything, and scrape_latest_customer_bubble already returns the rich _cardToText
        # ("[商品卡片] <title> <price> (券:<coupons>) <发货>"). One targeted scrape per card,
        # only when it's RICHER than the WS title (carries ￥/券/发货). Gated
        # ECAN_FEIGE_WS_CARD_DOM_DETAIL=1 (default off — it is one renderer eval per card).
        if os.environ.get("ECAN_FEIGE_WS_CARD_DOM_DETAIL", "") == "1":
            try:
                _gid = _card_goods_id(_card_preview) or str(
                    item.get("talk_id") or item.get("conversation_id") or ""
                )
                _cust = str(item.get("customer_name") or customer_key or "")
                # ws186: consult the captured card-JSON store FIRST — authoritative
                # 价格/券/发货 parsed from getTemplateCardDataV2 etc., available the
                # moment the card arrives, no paint dependency. Seeding the goods_id
                # cache makes the retry loop below break on its first check and the
                # selection logic prefer it over a thin scrape.
                try:
                    from . import product_detail_store as _pds
                    if _gid and _gid not in _WS186_JSON_GIDS:
                        _json_detail = _pds.detail_for(
                            _gid, _card_preview[len("[商品卡片]"):].split("商品ID")[0].strip())
                        if _json_detail:
                            _CARD_DETAIL_CACHE[_gid] = _json_detail
                            _WS186_JSON_GIDS.add(_gid)
                            logger.info(
                                f"[BrowserAutomation] {log_tag} ws186 card-JSON detail "
                                f"seeded goods={_gid} (skips DOM detail scrape retries)")
                except Exception:
                    pass
                # ws105: the .chatd-card detail spans (价格/券/发货) render a beat AFTER
                # the bubble appears, so a single scrape on the card turn often misses
                # them — in the ws103 run ws101 fired for only 1 of 2 cards, so the
                # 男童篮球服 coupon (UI: 券立减10元) was never captured and every later
                # "这款有没有优惠" got "暂未查到优惠信息". RETRY until the detail renders
                # (≤4 tries, ~1.8s total) or the goods_id cache already has it.
                _rich = ""
                for _try in range(4):
                    _cd = await scrape_latest_customer_bubble(
                        browser_session, _cust, typing_holder_getter=typing_holder_getter,
                    )
                    _rich = str((_cd or {}).get("text") or "").strip()
                    if _card_has_detail(_rich) or (_gid and _CARD_DETAIL_CACHE.get(_gid)):
                        break
                    await asyncio.sleep(0.45)
                # Cache real detail keyed by goods_id; fall back to the cache when
                # the scrape is thin so a later turn never reverts to "no coupon".
                # ws186: a JSON-sourced entry (原价/已售/状态 included) always beats
                # the DOM span scrape — never let the scrape overwrite it.
                _detail, _src = "", ""
                _ws186_json = bool(_gid and _gid in _WS186_JSON_GIDS
                                   and _CARD_DETAIL_CACHE.get(_gid))
                if _ws186_json:
                    _detail, _src = _CARD_DETAIL_CACHE[_gid], "card_json"
                elif _rich.startswith("[商品卡片]") and _card_has_detail(_rich):
                    _detail = _rich[len("[商品卡片]"):].strip()
                    _src = "scrape"
                    if _gid:
                        _CARD_DETAIL_CACHE[_gid] = _detail
                elif _gid and _CARD_DETAIL_CACHE.get(_gid):
                    _detail, _src = _CARD_DETAIL_CACHE[_gid], "cache"
                if _detail:
                    # Merge: keep the WS title + 商品ID (authoritative identity) and
                    # append the rendered detail so the LLM can answer 优惠/价格/发货.
                    _merged = (
                        _card_preview if _detail in _card_preview
                        else f"{_card_preview} | {_detail}"
                    )
                    item["last_message"] = _merged
                    item["latest_message"] = _merged
                    # ws106: store the enriched card text per conversation (talk_id) so a
                    # later TEXT follow-up injects it directly (no identity guessing).
                    _talk_conv = str(
                        item.get("talk_id") or item.get("conversation_id") or ""
                    ).strip()
                    if _talk_conv:
                        _CONV_CARD_TEXT[_talk_conv] = _merged
                    # ws105: PIN the rich text per conversation so TEXT follow-ups
                    # ("这款有没有优惠" — which never hit this card path) carry the
                    # 券/价格/发货 via ws094's recent-messages injection. Pin under the
                    # talk-scoped card identity AND the real name; pin_card_detail
                    # won't let a later bare card append clobber this richer text.
                    try:
                        from . import actionable_items as _ai
                        _talk_pin = str(
                            item.get("talk_id") or item.get("conversation_id") or ""
                        ).strip()
                        _pin_keys = []
                        if _talk_pin:
                            _pin_keys.append(f"card:{_talk_pin}")
                        if _cust and not _cust.startswith("card:"):
                            _pin_keys.append(_cust)
                        if _pin_keys:
                            _ai.pin_card_detail(_pin_keys, _merged)
                    except Exception:
                        pass
                    logger.info(
                        f"[BrowserAutomation] {log_tag} ws101: card detail "
                        f"cust={customer_key!r} gid={_gid or '?'} src={_src} "
                        f"-> {_merged[:90]!r}"
                    )
            except Exception as _ws098_e:
                logger.debug(
                    f"[BrowserAutomation] {log_tag} ws101 card-detail scrape failed: {_ws098_e}"
                )
        # ws160: a customer frequently bundles a TEXT question with the card
        # (live 2026-07-10 肽斯特 '你们衣服可以包邮吗\n[商品卡片]'). ws027 above
        # TRUSTS the WS card frame and returns WITHOUT scraping, so the QA agent
        # sees only '[商品卡片] …' and replies with a card-ack greeting ("您好，已
        # 收到这款商品卡片，请问您想咨询价格、尺码还是发货呢？") — the real
        # question ('包邮吗') is never answered. Do ONE targeted scrape now (the
        # real DOM name is resolved by the ws040e block above): if the newest
        # customer bubble carries genuine text alongside the card, fold that
        # question INTO latest_message so the QA agent answers it. Card-ONLY
        # bubbles (scrape fails / text == card synth) fall through unchanged, so
        # the already-working card path never regresses. Kill-switch:
        # ECAN_FEIGE_CARD_BUNDLED_TEXT=0.
        if os.environ.get("ECAN_FEIGE_CARD_BUNDLED_TEXT", "1") != "0":
            _bt_name = str(item.get("customer_name") or customer_key or "")
            if _bt_name and not _bt_name.startswith("card:"):
                try:
                    _bt = await scrape_latest_customer_bubble(
                        browser_session, _bt_name,
                        typing_holder_getter=typing_holder_getter,
                    )
                    _bt_text = str((_bt or {}).get("text") or "").strip()
                    if (_bt or {}).get("scrape_ok") and _bt_text:
                        # drop the card-synth line(s) ("[商品卡片] …"); the remainder
                        # is the customer's genuine typed question.
                        _bt_q = "\n".join(
                            _ln for _ln in _bt_text.split("\n")
                            if _ln.strip() and not _ln.strip().startswith("[商品卡片]")
                        ).strip()
                        if _bt_q and _bt_q not in _card_preview:
                            _bt_lm = f"{_bt_q}\n{_card_preview}"
                            item["last_message"] = _bt_lm
                            item["latest_message"] = _bt_lm
                            logger.info(
                                f"[BrowserAutomation] {log_tag} ws160 bundled text "
                                f"question folded into card dispatch for "
                                f"cust={customer_key!r}: {_bt_q[:40]!r}"
                            )
                except Exception as _ws160_e:
                    logger.debug(
                        f"[BrowserAutomation] {log_tag} ws160 bundled-text scrape "
                        f"failed (non-fatal, keeping WS card): {_ws160_e}"
                    )
        return _card_msg_id
    # mt041B: build the prior-turn cutoff list for the burst-rebuild.
    _prev_ids_for_scrape: list[str] = []
    if customer_last_dispatched_msg_id and customer_key:
        _prev = customer_last_dispatched_msg_id.get(customer_key)
        if _prev:
            _prev_ids_for_scrape.append(str(_prev))
    # ws008 stage2: WS text fast-path. For a plain-TEXT message we can take the customer
    # bubble straight from the WS frame stream (ws_session.ws_text_scrape) and skip the
    # DOM scrape entirely — no renderer contention, instant, and msg_id is the
    # client_message_id so downstream dedup/stale-guard keys stay consistent with DOM.
    # Card/image/unknown or no fresh WS data → ws_text_scrape returns None → DOM scrape.
    # Gated (ECAN_FEIGE_WS_SCRAPE=1, or the master ECAN_FEIGE_WS=1); default OFF.
    scraped = None
    # ws169: NEVER take the ws008 fast-path on a backstop/reopen route. The WS stream
    # is by definition BLIND for a dormant/reopened conversation (that's why the
    # backstop routed it), so ws_text_scrape's cache holds the PRE-close message —
    # live 2026-07-12 09:46 '陆地飞鱼': all 3 reopen enrich passes (incl. both ws168
    # re-scrapes) served the 09:23 pre-close bubble and msg-id-dedup-skipped, while
    # the customer's fresh 不满意能退吗 sat unanswered. A reopen enrich must DOM-scrape.
    if (item.get("_ecan_coldstart_recovery")
            and os.environ.get("ECAN_FEIGE_WS_SCRAPE_SKIP_ON_REOPEN", "1") != "0"):
        pass
    elif (os.environ.get("ECAN_FEIGE_WS_SCRAPE", "") == "1"
            or os.environ.get("ECAN_FEIGE_WS", "") == "1"):
        try:
            from . import ws_session as _wss_scrape
            _ws_hit = _wss_scrape.ws_text_scrape(
                str(item.get("customer_name") or customer_key or ""))
        except Exception:
            _ws_hit = None
        if _ws_hit and _ws_hit.get("text"):
            scraped = _ws_hit
            logger.info(
                f"[BrowserAutomation] {log_tag} ws008 WS text-scrape (off-DOM) "
                f"cust={customer_key!r} msg_id=...{str(_ws_hit.get('msg_id') or '')[-8:]} "
                f"len={len(str(_ws_hit.get('text') or ''))}"
            )
    if scraped is None:
        scraped = await scrape_latest_customer_bubble(
            browser_session,
            str(item.get("customer_name") or ""),
            typing_holder_getter=typing_holder_getter,
            previously_dispatched_msg_ids=_prev_ids_for_scrape or None,
        )
    if scraped.get("skip_dispatch"):
        skip_reason = str(scraped.get("skip_reason") or "scrape_not_safe")
        item["_ecan_pre_dispatch_skip_reason"] = skip_reason
        logger.warning(
            f"[BrowserAutomation] {log_tag} thread-scrape refused "
            f"dispatch for cust={customer_key!r}: reason={skip_reason!r}, "
            f"detail={scraped.get('verify_reason')!r}"
        )
        return ""
    if not scraped.get("scrape_ok"):
        # 2026-05-24 mt038B: defer dispatch when scrape failed AND the
        # sidebar preview is an opaque attachment marker like "[商品]".
        #
        # Under flood (5 concurrent customers, all typing tabs busy)
        # scrape_latest_customer_bubble logs "no Feige tab focusable"
        # and returns scrape_ok=False.  For a normal text preview the
        # fallback ("dispatch with sidebar text, no source_msg_id") is
        # acceptable — the bot at least answers something useful, and
        # mt038A's re-scrape rescue picks up the real msg_id on
        # stale_reply retry.  For attachment markers the fallback is
        # actively harmful: "[商品]" carries zero semantic content so
        # the bot produces a useless generic ask AND burns the LLM
        # call AND occupies the inflight slot.
        #
        # Live customer trace 2026-05-24 17:10:50 J14N9:
        #   17:10:33 sidebar dom_observed "[商品]"
        #   17:10:50 scrape failed (no tab focusable under load)
        #   17:10:50 send_chat_called latest_preview="[商品]" src=""
        #   17:11:06 source-guard fail-stale, reply dropped
        #   17:25    session auto-closed, customer stranded
        #
        # Deferring instead lets the next PreDispatch tick (~250 ms)
        # retry the scrape; once any typing tab releases, focus
        # succeeds and a real (text, msg_id) pair is dispatched.  No
        # risk of infinite deferral: typing tabs always release after
        # the active send completes.
        _orig_preview = str(item.get("last_message") or "").strip()
        if _orig_preview in _ATTACHMENT_MARKER_PREVIEWS:
            item["_ecan_pre_dispatch_skip_reason"] = "scrape_failed_attachment_marker"
            logger.info(
                f"[BrowserAutomation] {log_tag} mt038B defer dispatch "
                f"for cust={customer_key!r}: scrape failed AND sidebar "
                f"preview={_orig_preview!r} is opaque attachment marker; "
                f"next tick will re-scrape once a tab frees up"
            )
            return ""
        # mt056A (2026-05-31) — defer dispatch when scrape failed AND the
        # sidebar preview is OUR OWN PLACEHOLDER text.  This is the
        # perpetual stuck-at-placeholder loop: customer asks → we type
        # placeholder → sidebar now shows placeholder → next scrape fails
        # (CDP eval hangs under load) → fallback uses sidebar preview →
        # LLM gets latest_message="人工服务正在回复中..." → response has
        # wrong source_msg_id → stale-rejected → mt046A clears, mt050H
        # re-emits → loop forever.  Customer sees "人工服务正在回复中..."
        # piling up but never gets a real answer.
        #
        # Live customer trace 2026-05-31 15:25:21 陆地飞鱼 "会不会扎皮肤":
        #   +18.6s scrape attempts begin
        #   +19.3s placeholder #1 fires; sidebar now shows placeholder
        #   +31.8s CDP Runtime.evaluate TIMED OUT after 12.0s
        #   +32.5s LLM dispatched with latest_message="人工服务正在回复中..."
        #   ... stuck forever, no real reply ever lands
        #
        # The fix: when (scrape failed AND sidebar IS our placeholder),
        # defer dispatch.  The next PreDispatch tick will re-scrape; if
        # CDP frees up, we get the real customer bubble.  If the loop
        # continues, the placeholder timer keeps firing (mt055C
        # watchdog) so the customer at least sees acknowledgment.
        # Better one customer waiting than the LLM generating garbage.
        try:
            from . import placeholder_timer as _mt056a_ph_timer
            _mt056a_ph_texts = set(_mt056a_ph_timer._get_placeholder_texts())
            _mt056a_recent_count = _mt056a_ph_timer.count_recent_placeholders(
                str(customer_key or "")
            )
        except Exception:
            _mt056a_ph_texts = set()
            _mt056a_recent_count = 0
        if (
            _orig_preview
            and _orig_preview in _mt056a_ph_texts
            and _mt056a_recent_count > 0
        ):
            item["_ecan_pre_dispatch_skip_reason"] = "scrape_failed_sidebar_is_our_placeholder"
            logger.info(
                f"[BrowserAutomation] {log_tag} mt056A defer dispatch "
                f"for cust={customer_key!r}: scrape failed AND sidebar "
                f"preview={_orig_preview!r} is OUR OWN PLACEHOLDER "
                f"(recent_placeholders_typed={_mt056a_recent_count}); "
                f"refusing to send placeholder text as latest_message "
                f"to the LLM (would loop on stale_reply_source_msg_id)"
            )
            return ""
        logger.debug(
            f"[BrowserAutomation] {log_tag} thread-scrape returned no "
            f"customer bubble for cust={customer_key!r}; falling back "
            f"to sidebar preview"
        )
        return ""

    # ── mt017: human-intervention detection ──────────────────────────
    # The thread scrape now includes the latest AGENT bubble.  If its
    # text isn't in our recent-agent-reply ledger, a human MIGHT have
    # typed it directly into Feige — but the bubble could also be a
    # pre-existing reply from a previous app session (ledger is module-
    # level and resets on restart) or one that aged out of the 90-second
    # ledger TTL.
    #
    # 2026-05-21 baseline fix: on the FIRST scrape per customer per
    # process lifetime, BASELINE whatever agent bubble is in the DOM
    # without firing mark_handled.  Only fire when a genuinely NEW
    # msg_id appears that isn't in our ledger.  The flood-test run
    # 14:28 showed mt017 mis-firing for all 20 customers (stale agent
    # bubbles from prior sessions), dropping every Q&A reply.
    # 2026-05-24 mt038F (F.2): cross-check flag for mt030 below.
    # mt030 fires on agent_idx > customer_idx, but the "agent bubble"
    # may actually be a smart_cs greeting / prior-session leftover
    # that mt017 baselines as "not our reply, treat as pre-existing".
    # Without this flag, mt030 mistakes the greeter for our answer and
    # skips dispatching the customer's NEW question.  Live trace
    # 2026-05-24 14:49:41 客户13: "亲亲，在哒~" greeting at idx 104
    # landed after the new customer Q at idx 103 due to a 2.3s scrape-
    # lock wait; mt030 fired → customer stranded.
    #
    # Flag stays False when mt017 sees the bubble as ours (recent-
    # reply ledger match, typed-msg-id, or typed-text) — in that case
    # mt030's existing skip-our-own-reply behaviour is correct.  Flag
    # flips True only in mt017's "pre-existing baseline" branches.
    _agent_bubble_is_pre_existing_baseline = False
    lab = scraped.get("latest_agent_bubble")
    if isinstance(lab, dict):
        _lab_text = str(lab.get("text") or "").strip()
        _lab_msg_id = str(lab.get("msg_id") or "").strip()
        # ws008 stage3: DEFINITIVE is_ours. Set only by the WS source, and only when the
        # agent echo carried a client_message_id WE generated — so it is unambiguously our
        # reply, not a human agent's. Trust True directly (it doesn't age out like the 90s
        # text ledger and never mis-fires on our own bubble after a quiet period). A
        # False/absent value falls through to the ledger inference below, which also
        # catches DOM-sent replies (not tracked in _our_cmids).
        _ws_is_ours = (lab.get("is_ours") is True)
        if _lab_text:
            try:
                from .dispatch_state import (
                    matches_recent_agent_reply as _hi_match,
                )
            except Exception:
                _hi_match = None
            _is_ours = (
                _ws_is_ours
                or (
                    _hi_match is not None
                    and bool(_hi_match(customer_key, _lab_text))
                )
            )
            # 2026-05-22 mt024: also recognise the bubble as ours when
            # its msg_id is in our typed-msg-id set (no TTL, populated
            # from the JS verify path).  Without this, the recent-reply
            # text ledger ages out after 90 s and mt017 starts firing
            # on our own bubbles after any quiet period > 90 s — the
            # exact failure that dropped 肽斯特 / packet replies on
            # the 2026-05-22 08:19 trace.
            if not _is_ours and _lab_msg_id:
                from . import human_intervention as _hi_check
                if _hi_check.is_known_typed_msg_id(customer_key, _lab_msg_id):
                    _is_ours = True
            # 2026-05-23 mt029: also recognise via the typed-text set.
            # Catches the case where placeholder send was cancelled
            # mid-flight (supersede) — JS typed the bubble in DOM but
            # Python coroutine raised CancelledError before reaching
            # record_typed_msg_id.  The text was pre-registered before
            # the await (mt029 in runner.py), so this back-stop check
            # recognises the bubble as ours by text.  Live trace
            # 2026-05-22 15:38:33 客户13 stuck because mt017 mis-fired
            # on a cancelled-placeholder bubble.
            if not _is_ours and _lab_text:
                from . import human_intervention as _hi_check
                if _hi_check.is_known_typed_text(customer_key, _lab_text):
                    _is_ours = True
            if not _is_ours:
                from . import human_intervention as _hi
                from . import placeholder_timer as _hi_ph
                # Baseline check: have we seen any agent bubble for this
                # customer before?  If not, just remember its msg_id and
                # treat it as pre-existing (could be from prior session).
                baseline = _hi.get_baseline_msg_id(customer_key)
                if not baseline:
                    _hi.set_baseline_msg_id(customer_key, _lab_msg_id)
                    # 2026-05-23 mt028: also baseline the TEXT so the
                    # front-desk's text-based dom-echo guards can
                    # recognise pre-existing bubbles after a process
                    # restart.  Without this, the 2026-05-22 13:46
                    # flood test re-dispatched yesterday's bot reply
                    # text as today's customer question (客户16/18/19
                    # got 3-5 wasted dispatches, 0 answers).
                    _hi.set_baseline_text(customer_key, _lab_text)
                    logger.info(
                        f"[BrowserAutomation] mt017 baselined latest agent "
                        f"bubble for cust={customer_key!r} "
                        f"msg_id=...{_lab_msg_id[-8:]} "
                        f"text={_lab_text[:30]!r} — treating as pre-existing"
                    )
                    # mt052N (2026-05-29): only suppress mt030 when the
                    # baseline bubble is genuinely NOT a real reply —
                    # smart_cs greeting / human-handover notice / placeholder
                    # echo.  Pre-mt052N the suppression was unconditional,
                    # so every fresh-process start with carryover state in
                    # the chat re-dispatched every customer's previously-
                    # answered question (run 2026-05-29 13:50 flood test:
                    # 20 customers, ~17 produced near-duplicate bot
                    # replies because the prior-session real reply was
                    # carried over in the DOM and mt038F's suppression let
                    # dispatch proceed regardless of mt030's index check).
                    _is_system_bubble_mt052n = False
                    try:
                        from .system_message_filter import (
                            first_matching_pattern as _mt052n_sys_match,
                        )
                        if _mt052n_sys_match(_lab_text):
                            _is_system_bubble_mt052n = True
                    except Exception:
                        pass
                    _is_placeholder_mt052n = False
                    if not _is_system_bubble_mt052n:
                        try:
                            from .dispatch_state import (
                                is_placeholder_text as _mt052n_is_ph_text,
                            )
                            if _mt052n_is_ph_text(_lab_text):
                                _is_placeholder_mt052n = True
                        except Exception:
                            pass
                    # ws150: a bare agent greeting ("你好" / "在的" / 智能客服 bot auto-hello)
                    # is NOT a substantive answer, so it must not let mt030 mask a fresh customer
                    # question (live 2026-07-07: '你好' baseline masked '第二件半价吗' → never
                    # dispatched → closed). Treat it like a system/placeholder baseline.
                    _is_greeting_mt052n = False
                    if (
                        not _is_system_bubble_mt052n
                        and not _is_placeholder_mt052n
                        and os.environ.get("ECAN_FEIGE_MT052N_GREETING_NOMASK", "1") != "0"
                    ):
                        try:
                            from .system_message_filter import (
                                is_trivial_greeting as _mt052n_is_greeting,
                            )
                            if _mt052n_is_greeting(_lab_text):
                                _is_greeting_mt052n = True
                        except Exception:
                            pass
                    if _is_system_bubble_mt052n or _is_placeholder_mt052n or _is_greeting_mt052n:
                        # 2026-05-24 mt038F (F.2): tell mt030 below this
                        # bubble doesn't count as "we already replied".
                        _agent_bubble_is_pre_existing_baseline = True
                        _mt052n_kind = (
                            "system" if _is_system_bubble_mt052n
                            else "placeholder" if _is_placeholder_mt052n
                            else "greeting"
                        )
                        logger.info(
                            f"[BrowserAutomation] mt052N keeping mt038F "
                            f"suppression for cust={customer_key!r} — baseline "
                            f"bubble is "
                            f"{_mt052n_kind} "
                            f"({_lab_text[:30]!r})"
                        )
                    else:
                        logger.info(
                            f"[BrowserAutomation] mt052N letting mt030 fire "
                            f"for cust={customer_key!r} — baseline bubble looks "
                            f"like a real prior-session reply "
                            f"({_lab_text[:30]!r}); will skip dispatch when "
                            f"agent_idx > cust_idx"
                        )
                elif _lab_msg_id and _lab_msg_id == baseline:
                    # 2026-05-24 mt038F (F.2): same — still a pre-
                    # existing bubble, mt030 must not treat it as a
                    # real reply.
                    # mt052N: only honour the suppression when the
                    # baselined bubble was a system/placeholder text; a
                    # repeat sighting of a real prior-session reply must
                    # still let mt030 fire.
                    _baseline_text_for_mt052n = _hi.get_baseline_text(customer_key) or ""
                    _is_system_or_placeholder_mt052n = False
                    try:
                        from .system_message_filter import (
                            first_matching_pattern as _mt052n_sys_match,
                        )
                        if _mt052n_sys_match(_baseline_text_for_mt052n):
                            _is_system_or_placeholder_mt052n = True
                    except Exception:
                        pass
                    if not _is_system_or_placeholder_mt052n:
                        try:
                            from .dispatch_state import (
                                is_placeholder_text as _mt052n_is_ph_text,
                            )
                            if _mt052n_is_ph_text(_baseline_text_for_mt052n):
                                _is_system_or_placeholder_mt052n = True
                        except Exception:
                            pass
                    if _is_system_or_placeholder_mt052n:
                        _agent_bubble_is_pre_existing_baseline = True
                else:
                    # 2026-05-25 mt041A: classify platform-system bubbles
                    # BEFORE treating as human intervention.  smart_cs
                    # auto-greetings, human-handover notices, store
                    # assignment messages, etc. are emitted by the
                    # platform itself (NOT by a human staff member) and
                    # bypass eCan's send path, so they're not in any of
                    # the three "is_ours" ledgers.  Pre-mt041A: mt017
                    # mis-classified the platform's smart_cs greeting
                    # "亲亲，在哒~..." as human intervention and silenced
                    # the bot for 120s, dropping the customer's actual
                    # reply.  Live trace 2026-05-24 23:30:32 客户15
                    # (emulator); production-relevant since real Feige
                    # emits the same smart_cs greetings the bot didn't
                    # type.  When matched, treat as pre-existing baseline
                    # (sets the F.2 flag for mt030) and DON'T mark_handled.
                    try:
                        from .system_message_filter import (
                            first_matching_pattern as _hi_sys_match,
                        )
                        _sys_pat = _hi_sys_match(_lab_text)
                    except Exception:
                        _sys_pat = None
                    if _sys_pat:
                        _hi.set_baseline_msg_id(customer_key, _lab_msg_id)
                        _hi.set_baseline_text(customer_key, _lab_text)
                        _agent_bubble_is_pre_existing_baseline = True
                        logger.info(
                            f"[BrowserAutomation] mt041A treat as pre-existing "
                            f"system bubble for cust={customer_key!r} "
                            f"pattern={_sys_pat!r} msg_id=...{_lab_msg_id[-8:]} "
                            f"text={_lab_text[:30]!r} — skipping mark_handled"
                        )
                        # mt041A path: baseline + flag set above; skip the
                        # human-intervention block.
                    last_seen_human = (
                        "" if _sys_pat else _hi.get_handled_msg_id(customer_key)
                    )
                    if _sys_pat:
                        pass  # mt041A handled it above
                    elif _lab_msg_id and last_seen_human == _lab_msg_id:
                        pass  # already-known human bubble, skip
                    else:
                        # 2026-05-24 mt036A: scope the mark to the
                        # CUSTOMER question the human appears to have
                        # answered (= the latest customer bubble msg_id
                        # in the same scrape, ``scraped["msg_id"]``).
                        # The bot's reply to a NEWER question won't be
                        # suppressed; only its reply to THIS question
                        # will.  Pre-mt036A the mark blanketed the
                        # whole customer for 120 s, dropping legitimate
                        # bot replies for unrelated questions (live
                        # trace 2026-05-24 11:34:21 packet —
                        # un-related agent bubble msg_id 673c40e5
                        # triggered the mark, then packet's good
                        # 能不能包邮 reply at 11:34:41 was dropped via
                        # blanket suppression).
                        _question_msg_id_for_mark = str(
                            scraped.get("msg_id") or ""
                        ).strip()
                        _hi.mark_handled(
                            customer_key,
                            _lab_msg_id,
                            source="thread_scrape",
                            question_msg_id=_question_msg_id_for_mark,
                            # 2026-05-26 mt048B: capture human text so the
                            # LLM relevance judge can later decide drop vs proceed.
                            bubble_text=_lab_text,
                        )
                        _hi.set_baseline_msg_id(customer_key, _lab_msg_id)
                        try:
                            _hi_ph.cancel_any_for_customer(customer_key)
                        except Exception:
                            pass

    msg_id = str(scraped.get("msg_id", "") or "")

    # 2026-05-23 mt030: skip dispatch when the chat thread shows the
    # latest agent bubble is MORE RECENT than the latest customer
    # bubble (i.e. we / a prior session already replied to this
    # customer's latest question).  Catches the stale-bubble case
    # from the 2026-05-22 16:06:37 trace where 客户18's
    # yesterday-question + yesterday-reply were both still in the
    # DOM at fresh-process start — we wrongly re-dispatched the
    # question and the bot's irrelevant reply landed at the same
    # moment the customer typed a NEW unrelated question.
    #
    # The rule is symmetric and stateless: it doesn't matter whether
    # the agent reply was typed yesterday, an hour ago, or 5 seconds
    # ago.  If the agent bubble is more recent than the customer
    # bubble, the customer's last question is answered, full stop.
    #
    # If the customer types a NEW question after our reply, the
    # customer bubble's index moves past the agent bubble → dispatch
    # fires legitimately.
    try:
        _scraped_cust_index = int(
            scraped.get("index") if scraped.get("index") is not None else -1
        )
        _agent_bubble = scraped.get("latest_agent_bubble") or {}
        _agent_index = int(
            _agent_bubble.get("index")
            if isinstance(_agent_bubble, dict)
            and _agent_bubble.get("index") is not None
            else -1
        )
        # mt052M (2026-05-29): the mt030 check fires when the latest agent
        # bubble's DOM index is greater than the latest customer bubble's,
        # i.e. "we already replied".  But the agent bubble may be one of our
        # placeholder echoes ("人工服务正在回复中..."), in which case the
        # underlying customer question is still unanswered.  客户01/04/15
        # trace 2026-05-29 13:38:44→13:38:56: placeholder typed at 13:38:44,
        # PreDispatch enrich at 13:38:56 saw it as agent_index > cust_index
        # and skipped dispatch with reason=agent_already_replied → the real
        # question stayed silent the entire run.  Check the bubble text
        # against the placeholder ledger and fall through when matched, so
        # the customer's real question can finally reach the QA agent.
        _agent_bubble_text = ""
        if isinstance(_agent_bubble, dict):
            _agent_bubble_text = str(_agent_bubble.get("text") or "").strip()
        try:
            from .dispatch_state import is_placeholder_text as _is_ph_text_mt052m
            _agent_bubble_is_placeholder = bool(_agent_bubble_text) and _is_ph_text_mt052m(
                _agent_bubble_text
            )
        except Exception:
            _agent_bubble_is_placeholder = False
        # ws158: on a connect-banner REOPEN (customer re-engaged a closed conversation via the
        # ws108 backstop), the baseline agent bubble is a PRE-REOPEN answer and must not mask the
        # customer's re-ask. ws151's in-thread close-floor is unreliable — the 关闭会话 /
        # 以上为历史消息 marker is often NOT rendered in the scraped thread DOM (live 2026-07-10
        # packet 支持七天: mt030 masked by pre-close '支持七天无理由，具体…', and 关闭会话/以上为历史
        # appeared 0× in the whole log). The connect-banner routing flag (source=
        # connect_banner_backstop, front_desk.py:471) is the RELIABLE reopen signal. Answering a
        # re-asked question beats silence; true duplicates are caught by the recent-reply/msg-id
        # dedup. Reversible: ECAN_FEIGE_MT030_REOPEN_NOMASK=0.
        # Signal: the row was KEPT as a system-looking connect-banner (store_assignment_notice) —
        # set on the item at frontdesk_dispatch.py:1316 (item['_ecan_system_row_kept']=system_reason)
        # and read here / at line ~1160. (NOT item['source'] — that is stripped to '' before enrich.)
        # ws162: ws158's reopen signal (_ecan_system_row_kept) is stamped ONLY on the
        # frontdesk_dispatch actionable path — but EVERY real cold-start reopen routes
        # through the ws108 connect-banner backstop (front_desk.py:470), which stamps
        # _ecan_coldstart_recovery instead and never sets _ecan_system_row_kept. So ws158
        # NEVER fired for real cold-starts, and mt030 kept masking the re-asked question with
        # a pre-reopen agent bubble → dead silence (live 2026-07-10 'sc' '有人吗？': cust_idx=11
        # < agent_idx=13 '您…' → mt030 skip; identical failure for text/card/转人工 because the
        # sidebar preview is ALWAYS the '客服…小店接入' banner). Recognise the backstop reopen
        # too: the coldstart flag on the item, OR the incoming last_message still classifying as
        # store_assignment_notice (mt030 runs BEFORE the line-1260 scrape merge, so last_message
        # is still the banner here). Same reversal switch as ws158.
        _ws162_reopen = False
        if os.environ.get("ECAN_FEIGE_MT030_REOPEN_NOMASK", "1") != "0":
            if bool(item.get("_ecan_coldstart_recovery")):
                _ws162_reopen = True
            else:
                try:
                    from .system_message_filter import (
                        first_system_row_match as _ws162_fsr,
                    )
                    if "store_assignment_notice" in str(_ws162_fsr(item) or ""):
                        _ws162_reopen = True
                except Exception:
                    _ws162_reopen = False
        _mt030_is_reopen = (
            os.environ.get("ECAN_FEIGE_MT030_REOPEN_NOMASK", "1") != "0"
            and (
                "store_assignment_notice" in str(item.get("_ecan_system_row_kept") or "")
                or _ws162_reopen
            )
        )
        if _mt030_is_reopen:
            # ws173: durable in-pass reopen marker. _ecan_coldstart_recovery has
            # proven unreliable on some dispatch paths (2026-07-12 run: two
            # coldstart dedup-skips, ZERO [WS170-CARD-DOM-DUMP] lines — the flag
            # was absent at Stage 2), and the banner classification is destroyed
            # by the mt057 last_message override before Stage 2 runs. Stamp the
            # reopen fact HERE (where it is reliably detected) so downstream
            # consumers in the same pass (the ws170 dump gate) can see it.
            item["_ecan_ws162_reopen"] = True
        if _mt030_is_reopen and _agent_index > _scraped_cust_index >= 0:
            logger.info(
                f"[BrowserAutomation] ws158 mt030 REOPEN-nomask for cust={customer_key!r} "
                f"(connect-banner reopen; pre-reopen baseline won't mask the re-ask) "
                f"cust_idx={_scraped_cust_index} agent_idx={_agent_index}"
            )
            # ws172: settle-hold — dispatch the RIGHT message, not the first one
            # scraped. See _WS172_REOPEN_HOLD for the full write-up. Held once
            # per (customer, bubble); the revisit dispatches whatever is latest.
            # Reversible: ECAN_FEIGE_REOPEN_SETTLE_HOLD=0.
            if os.environ.get("ECAN_FEIGE_REOPEN_SETTLE_HOLD", "1") != "0":
                _hold_mid = str(scraped.get("msg_id") or "")
                _hold_key = (customer_key, _hold_mid)
                _hold_now = time.time()
                for _hk in [
                    k for k, ts in _WS172_REOPEN_HOLD.items()
                    if _hold_now - ts > _WS172_HOLD_TTL_S
                ]:
                    _WS172_REOPEN_HOLD.pop(_hk, None)
                if _hold_mid and _hold_key not in _WS172_REOPEN_HOLD:
                    _WS172_REOPEN_HOLD[_hold_key] = _hold_now
                    # Register for the ws168 deferred-retry channel so the scan
                    # re-routes this row (~5-15s); the ws168 re-scrape schedule
                    # provides a second revisit path when the lock is busy.
                    _record_deferred(customer_key, customer_key)
                    logger.info(
                        f"[BrowserAutomation] {log_tag} ws172 reopen settle-hold "
                        f"cust={customer_key!r} msg_id=...{_hold_mid[-8:]} — scraped "
                        f"bubble is agent-answered on the reopen's first look; the "
                        f"fresh message may not have painted yet. Holding one cycle "
                        f"(revisit dispatches the latest bubble)."
                    )
                    item["_ecan_pre_dispatch_skip_reason"] = "reopen_settle_hold"
                    return ""
        if (
            _agent_index >= 0
            and _scraped_cust_index >= 0
            and _agent_index > _scraped_cust_index
            and not _agent_bubble_is_pre_existing_baseline
            and not _agent_bubble_is_placeholder
            and not _mt030_is_reopen
        ):
            # ws134+ws135: on a 手动关闭 manual-reopen cold-start, Feige RE-EMITS the conversation's
            # HISTORICAL product card; eCan card-acks it ("已收到商品卡片") and that card-ack becomes
            # the agent bubble that trips agent_idx > cust_idx over the customer's REAL new message
            # in the same thread — wrongly suppressing 人工/text (陆地飞鱼 waited 2min+; text='的人工'
            # was found by the scrape then skipped here). A card-ack CANNOT answer a non-card message.
            _mt030_cust_text = str(scraped.get("text", "") or "")
            _mt030_agent_text = str(_agent_bubble_text or "")
            _mt030_cust_is_card = _mt030_cust_text.strip().startswith("[商品")
            _mt030_agent_is_card_ack = "商品卡片" in _mt030_agent_text
            _mt030_cust_is_handover = False
            try:
                from . import human_mode as _mt030_hm
                # STRICT is_human_handover_request (ws117 short-standalone): '的人工'=True,
                # long '人工智能课程'=False (no false positive).
                _mt030_cust_is_handover = (
                    bool(_mt030_cust_text)
                    and _mt030_hm.is_human_handover_request(_mt030_cust_text)
                )
            except Exception:
                _mt030_cust_is_handover = False

            # (a) ws134: latest customer bubble is a 人工 request → arm the [微笑] ack (that IS the
            #     response) and skip the QA dispatch. Reversible: ECAN_FEIGE_MT030_HANDOVER_OVERRIDE=0.
            if (_mt030_cust_is_handover
                    and os.environ.get("ECAN_FEIGE_MT030_HANDOVER_OVERRIDE", "1") != "0"):
                try:
                    from .placeholder_timer import note_handover_ack_needed as _mt030_ho
                    _mt030_ho(customer_key)
                    logger.info(
                        f"[BrowserAutomation] ws134 mt030 handover-override: 人工 request "
                        f"({_mt030_cust_text[:16]!r}) — armed [微笑] ack despite agent-already-"
                        f"replied (card-ack != 人工) cust={customer_key!r}")
                except Exception as _mt030_ho_err:
                    logger.debug(
                        f"[BrowserAutomation] ws134 handover-override failed: {_mt030_ho_err}")
                item["_ecan_pre_dispatch_skip_reason"] = "agent_already_replied"
                return ""

            # (b) ws135: the "more recent" agent bubble is a card-ack but the customer's latest
            #     message is NOT a card → the card-ack cannot be its answer. Do NOT skip; dispatch
            #     the real (text) message. Reversible: ECAN_FEIGE_MT030_CARD_ACK_NOMASK=0.
            if (os.environ.get("ECAN_FEIGE_MT030_CARD_ACK_NOMASK", "1") != "0"
                    and not _mt030_cust_is_card and _mt030_agent_is_card_ack):
                logger.info(
                    f"[BrowserAutomation] ws135 mt030 card-ack-nomask: agent bubble is a card-ack "
                    f"but customer's latest message is NOT a card ({_mt030_cust_text[:24]!r}) — a "
                    f"card-ack cannot answer it; allowing dispatch cust={customer_key!r}")
                # fall through — do NOT skip; dispatch the real message
            else:
                item["_ecan_pre_dispatch_skip_reason"] = "agent_already_replied"
                logger.info(
                    f"[BrowserAutomation] mt030 skip dispatch for "
                    f"cust={customer_key!r} cust_idx={_scraped_cust_index} "
                    f"agent_idx={_agent_index} msg_id=...{msg_id[-8:]} "
                    f"text={_mt030_cust_text[:40]!r} — "
                    f"agent bubble is more recent (already answered)"
                )
                return ""
        if (
            _agent_index >= 0
            and _scraped_cust_index >= 0
            and _agent_index > _scraped_cust_index
            and _agent_bubble_is_placeholder
        ):
            logger.info(
                f"[BrowserAutomation] mt052M mt030 override for "
                f"cust={customer_key!r} cust_idx={_scraped_cust_index} "
                f"agent_idx={_agent_index} — agent bubble is a PLACEHOLDER "
                f"({_agent_bubble_text[:40]!r}), not a real reply; "
                f"allowing dispatch to continue"
            )
        # 2026-05-24 mt038F (F.2): log when mt030 would have fired but
        # was suppressed because the "agent" bubble is actually a
        # pre-existing baseline (smart_cs greeting, prior-session
        # leftover, etc.).  Operator-grep-able so we can monitor that
        # the suppression isn't masking legitimate skips in production.
        if (
            _agent_index >= 0
            and _scraped_cust_index >= 0
            and _agent_index > _scraped_cust_index
            and _agent_bubble_is_pre_existing_baseline
        ):
            logger.info(
                f"[BrowserAutomation] mt038F-F2 mt030 would fire but "
                f"agent bubble is pre-existing baseline — dispatch "
                f"continues for cust={customer_key!r} "
                f"cust_idx={_scraped_cust_index} agent_idx={_agent_index}"
            )
    except Exception as _mt030_err:
        logger.debug(
            f"[BrowserAutomation] {log_tag} mt030 agent-after-customer "
            f"check failed (non-fatal): {_mt030_err}"
        )

    # 2026-05-25 mt040A: defer dispatch when the trigger row was a
    # system message (greeting, transfer-to-human label, etc.) kept
    # for thread enrichment by frontdesk_dispatch.  The system row
    # signals "Feige surfaced an unread event" but the unread event
    # is NOT a new customer message — it's a platform-side bubble
    # (store auto-greeting, "用户正在查看商品" marker, etc.).  Any
    # customer bubble the thread scrape finds is PRE-EXISTING content
    # (the customer may have pasted a product card earlier or have
    # leftover bubbles from a prior browsing session) — dispatching
    # on it makes the LLM hallucinate questions the customer never
    # asked.
    #
    # Live customer trace 2026-05-25 12:34:06 J14N9:
    #   12:34:06  dom_observed: 'Hi, 欢迎光临' (store_auto_greeting)
    #   12:34:08  thread scrape: latest customer bubble = pre-existing
    #             product card (msg_id ...B5065260)
    #   12:34:09  send_chat with the card as context
    #   12:34:31  LLM hallucinated answer about "透气" (cotton/breath-
    #             ability) — customer never asked
    #   12:34:40  hallucinated reply typed into chat
    #   12:35:33  mt017 mis-classified our own reply as human-intervention
    #             (mt037C verified_msg_id capture is broken in prod);
    #             bot silenced for 120 s
    #   12:35:48  customer's actual question 夏天能不能便宜点 arrives
    #   12:36:15  bot's price-answer dropped (cause 3: stale_reply on
    #             card+text wrapper)
    #   12:43:58  customer rephrased
    #   ~7+ min   customer effectively ignored
    #
    # mt040A: defer this dispatch.  mt017 baseline still set in the
    # block above (so future scrapes recognise the agent bubble as
    # pre-existing); the customer's next real text message will fire
    # a non-system dom_observed and dispatch normally.
    if item.get("_ecan_system_row_kept"):
        _system_reason = str(item.get("_ecan_system_row_kept") or "")
        item["_ecan_pre_dispatch_skip_reason"] = "mt040A_system_row_only"
        logger.info(
            f"[BrowserAutomation] {log_tag} mt040A defer dispatch for "
            f"cust={customer_key!r}: trigger row was system message "
            f"({_system_reason!r}); thread scrape returned customer "
            f"msg_id=...{(msg_id or '')[-8:]} text="
            f"{str(scraped.get('text', '') or '')[:40]!r} but that's "
            f"pre-existing content, not a fresh customer question.  "
            f"Waiting for the customer's actual message before dispatching."
        )
        return ""

    orig_last = str(item.get("last_message") or "")
    new_last = str(scraped.get("text", "") or "")
    if new_last and new_last != orig_last:
        try:
            from .system_message_filter import first_matching_pattern

            new_hit = first_matching_pattern(new_last)
            orig_hit = first_matching_pattern(orig_last)
            if (
                new_hit
                in {
                    "transfer_to_human_label",
                    "smart_cs_auto_greeting",
                    "human_handover_notice",
                    "store_assignment_notice",
                }
                and orig_last
                and not orig_hit
            ):
                logger.info(
                    f"[BrowserAutomation] {log_tag} thread-scrape ignored "
                    f"system-looking latest bubble for cust={customer_key!r}: "
                    f"sidebar={orig_last[:40]!r} thread={new_last[:40]!r} "
                    f"pattern={new_hit!r}; dispatching sidebar text"
                )
                return ""
        except Exception as exc:
            logger.debug(
                f"[BrowserAutomation] {log_tag} system-looking scrape guard "
                f"failed for cust={customer_key!r}: {exc}"
            )
        # mt052A (2026-05-29): MERGE sidebar + scraped-bubble text instead
        # of overriding (the prior behaviour silently dropped the older
        # question).  Live trace: 陆地飞鱼 typed "夏天穿会不会热" at 10:50:06;
        # eCan saw it at 10:50:15 but the front-desk queue was busy for
        # ~6 s.  Before front-desk could finish, the customer typed "透气
        # 吗" at 10:50:25.  When PreDispatch's thread-scrape ran, the
        # latest bubble was "透气吗" — the OLD code replaced the sidebar's
        # "夏天穿会不会热" with "透气吗", and the older question never
        # reached the LLM.  Merging both into one ``last_message`` lets
        # the LLM address BOTH in a single reply; ``source_msg_id`` stays
        # the newer one (so the JS source-guard still validates against
        # the latest visible bubble).
        #
        # Skip the merge when the new bubble already contains the old
        # text (e.g., when Feige's sidebar preview is just a truncation
        # of the same bubble) so we don't duplicate the question in the
        # prompt.
        #
        # mt057 (2026-05-31): also skip the merge when the SIDEBAR is a
        # system-message (e.g., "当前会话已长时间未回复，若后续仍未回复，
        # 平台可能主动介入处理。") but the SCRAPED bubble is a real
        # customer question.  Otherwise the merged "warning\nQuestion"
        # text trips the system_message filter downstream (line ~1431)
        # which matches ``platform_long_no_reply`` on the prefix and
        # SKIPs the dispatch entirely — customer's actual question is
        # never sent to the LLM.  Under load this becomes a permanent
        # trap: slow scrape → 1 min silence → Feige inserts warning →
        # filter drops dispatch → still no reply → warning stays in
        # sidebar → next retry also dropped → loop forever.  Live
        # trace 2026-05-31 21:09 陆地飞鱼 "会不会扎皮肤": dispatched
        # zero times across 130 seconds, customer waiting on a
        # placeholder that never converted into an answer.
        _mt057_sidebar_is_system = False
        if orig_last:
            try:
                from .system_message_filter import (
                    first_matching_pattern as _mt057_first_pat,
                )
                _mt057_sidebar_is_system = (
                    _mt057_first_pat(orig_last) is not None
                )
            except Exception:
                _mt057_sidebar_is_system = False
        if orig_last and orig_last not in new_last and not _mt057_sidebar_is_system:
            merged = f"{orig_last}\n{new_last}"
            logger.info(
                f"[BrowserAutomation] {log_tag} thread-scrape merged "
                f"sidebar + bubble for cust={customer_key!r}: "
                f"sidebar={orig_last[:40]!r} + "
                f"customer_bubble={new_last[:40]!r} "
                f"(msg_id=...{msg_id[-8:] if msg_id else ''})"
            )
            item["last_message"] = merged
        elif _mt057_sidebar_is_system:
            logger.info(
                f"[BrowserAutomation] {log_tag} mt057 thread-scrape "
                f"OVERRODE last_message (skipped merge — sidebar is "
                f"system-message) for cust={customer_key!r}: "
                f"sidebar={orig_last[:40]!r} -> "
                f"customer_bubble={new_last[:40]!r} "
                f"(msg_id=...{msg_id[-8:] if msg_id else ''})"
            )
            item["last_message"] = new_last
        else:
            logger.info(
                f"[BrowserAutomation] {log_tag} thread-scrape overrode "
                f"last_message for cust={customer_key!r}: "
                f"sidebar={orig_last[:40]!r} -> "
                f"customer_bubble={new_last[:40]!r} "
                f"(msg_id=...{msg_id[-8:] if msg_id else ''})"
            )
            item["last_message"] = new_last

    # Multimodal: forward any image attachments scraped from the
    # customer bubble.  Eager fetch + base64-encode so signed CDN URLs
    # (carrying ``x-expires=...``) don't expire en route to the worker.
    # Failure is non-fatal — fall back to raw URL passthrough.  See
    # ``pre_dispatch_v2._dispatch_one_item`` for the symmetric v2 path.
    raw_atts = scraped.get("attachments") or []
    if raw_atts:
        try:
            from .image_fetch import fetch_attachments  # local import
            enriched = await fetch_attachments(raw_atts)
            if enriched:
                item["last_message_attachments"] = enriched
        except Exception as fetch_exc:
            logger.warning(
                f"[BrowserAutomation] {log_tag} fetch_attachments failed "
                f"for cust={customer_key!r}: {type(fetch_exc).__name__}: "
                f"{fetch_exc!r}; forwarding raw URLs"
            )
            item["last_message_attachments"] = list(raw_atts)
    # ws106: a TEXT follow-up ("有没有优惠券" / "七天无理由" / "运费险" / "包邮") carries no
    # product context, so the LLM answered "暂未查到…" or "麻烦发下商品卡片". If we've enriched
    # a card for THIS conversation (talk_id), prepend its detail (价格/券/发货/服务) to the
    # question so the bot answers from the card. Only when the message isn't itself a card.
    if os.environ.get("ECAN_FEIGE_WS_CARD_DOM_DETAIL", "") == "1":
        try:
            _talk_fu = str(item.get("talk_id") or item.get("conversation_id") or "").strip()
            _card_ctx = _CONV_CARD_TEXT.get(_talk_fu) if _talk_fu else ""
            _cur = str(item.get("last_message") or "")
            if _card_ctx and "[商品卡片]" not in _cur:
                item["last_message"] = f"{_card_ctx}\n{_cur}"
                item["latest_message"] = item["last_message"]
                logger.info(
                    f"[BrowserAutomation] {log_tag} ws106: injected card context into "
                    f"text follow-up cust={customer_key!r} talk=...{_talk_fu[-8:]} "
                    f"q={_cur[:30]!r}"
                )
        except Exception:
            pass
    return msg_id


# ws172: reopen settle-hold ledger — (customer_key, scraped_msg_id) -> hold ts.
# On a connect-banner reopen the FIRST enrich pass often runs BEFORE the
# customer's fresh message has painted in the seller thread (live 2026-07-12
# 19:51:06 'packet': the 11s-scrape saw the PRE-close 你好, the fresh
# 现在拍可以发货吗 painted by ~15-20s). ws158/ws162's REOPEN-nomask then forces a
# dispatch of that stale agent-answered bubble — wasting an LLM turn, holding
# the typing lock, getting stale-guard dropped, and blocking the window in
# which the fresh message becomes scrapeable. The settle-hold defers the
# FORCED (nomask) dispatch exactly once per (customer, bubble): the revisit
# (ws168 deferred-retry / re-scrape, ~5-15s later) dispatches whatever is
# latest — the fresh message when painted, else the same stale bubble (the
# ws162 answer-beats-silence trade preserved, just one cycle later). Genuine
# re-asks (customer bubble newest, cust_idx > agent_idx) never enter the
# nomask branch and are NOT delayed.
_WS172_REOPEN_HOLD: dict = {}
_WS172_HOLD_TTL_S = 120.0

# ws170: card-DOM diagnostic dump. The 2026-07-12 failing cold start ended with
# the named-row enrich scraping packet's real thread and reporting
# product_cards=0 — while the customer's 电商小助手 recommendation card sat right
# there in the thread. Either that card bubble isn't classified customer-
# authored or it isn't in the scraped wrap set at all; we can't fix the
# classifier blind (the ws110 lesson: dump the real DOM, don't guess). When a
# coldstart-recovery enrich ends in a msg-id dedup skip ("nothing new" on a
# just-reopened conversation — exactly the suspicious outcome), dump the tail
# of the thread's message wrappers: classes, qa-ids, card-ish flags, text, and
# an outerHTML head for card-looking wraps. Rate-limited per customer; gated
# ECAN_FEIGE_CARD_DOM_DUMP=1 (default on). Marker: [WS170-CARD-DOM-DUMP].
_WS170_DUMP_AT: dict = {}   # customer_key -> monotonic ts of last dump
_WS170_DUMP_MIN_INTERVAL_S = 600.0
_WS170_CARD_DOM_DUMP_JS = r"""(function(){
  var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
  var start = Math.max(0, wrappers.length - 8);
  var out = [];
  for (var i = start; i < wrappers.length; i++) {
    var w = wrappers[i];
    var text = (w.textContent || '').replace(/\s+/g, ' ').trim();
    var qa = Array.from(w.querySelectorAll('[data-qa-id]')).slice(0, 6)
      .map(function(n){ return n.getAttribute('data-qa-id'); });
    var idNode = w.querySelector('[data-id]');
    var cardLike = !!w.querySelector('[class*="card" i]');
    var rec = {
      idx: i,
      cls: String(w.className || '').slice(0, 120),
      qa_ids: qa,
      data_id_tail: idNode ? String(idNode.getAttribute('data-id') || '').slice(-12) : '',
      has_chatd_card: !!w.querySelector('.chatd-card'),
      card_like: cardLike,
      text: text.slice(0, 90)
    };
    if ((cardLike || /商品|推荐/.test(text)) && !rec.has_chatd_card) {
      rec.html_head = String(w.outerHTML || '').slice(0, 500);
    }
    out.push(rec);
  }
  return JSON.stringify({total: wrappers.length, tail: out});
})()"""


async def _maybe_dump_card_dom(browser_session, customer_key: str, item: dict,
                               log_tag: str) -> None:
    """One-shot thread-DOM dump on a suspicious coldstart dedup skip (ws170)."""
    if os.environ.get("ECAN_FEIGE_CARD_DOM_DUMP", "1") == "0":
        return
    # ws173: accept EITHER the backstop's coldstart flag (unreliable on some
    # dispatch paths) OR the in-pass reopen marker stamped at the mt030
    # nomask site (reliable — same item, same pass).
    if not (item.get("_ecan_coldstart_recovery") or item.get("_ecan_ws162_reopen")):
        return
    now = time.time()
    last = _WS170_DUMP_AT.get(customer_key, 0.0)
    if now - last < _WS170_DUMP_MIN_INTERVAL_S:
        return
    _WS170_DUMP_AT[customer_key] = now
    # ws171: log the attempt BEFORE the eval and any failure at WARNING — the
    # 2026-07-12 19:51 run showed zero dump lines on three coldstart dedup
    # skips and the silent (debug-level) failure path left no way to tell
    # whether the gate, the eval, or the flag was the reason.
    logger.info(
        f"[WS170-CARD-DOM-DUMP] attempting for cust={customer_key!r}"
    )
    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            _evaluate_js,
        )
        res = await _evaluate_js(
            browser_session, _WS170_CARD_DOM_DUMP_JS,
            focus=False, read_only=True, lock_free=True,
            timeout_s=6.0,
            trace_label="ws170_card_dom_dump",
        )
        logger.info(
            f"[WS170-CARD-DOM-DUMP] cust={customer_key!r} (coldstart enrich ended "
            f"in dedup-skip; thread tail follows): {str(res)[:4000]}"
        )
    except Exception as exc:
        logger.warning(
            f"[WS170-CARD-DOM-DUMP] dump failed for cust={customer_key!r} "
            f"(non-fatal): {type(exc).__name__}: {exc}"
        )


# ws177: card-join rescue. A card-ONLY cold start has no name-resolution path:
# the WS frame is nameless, the sidebar row shows only the connect banner (no
# conv id in row attributes, ws038), the thread scrape can't classify the card
# (it renders as pigeon-dynamic-card-system-container-new with NO .chatd-card —
# the 2026-07-13 20:51:59 dump), and ws171's preview-bridge needs a TEXT frame.
# So the reply parks and, with no follow-up text, EXPIRES — the customer sees
# nothing (陆地飞鱼 20:51:46 卡死). BUT the dump also revealed the join key: the
# card wrap's data-id (``2_<uuid>_template``) IS the WS frame's
# s:client_message_id. When a coldstart enrich ends in a dedup-skip on a NAMED
# row, harvest the thread's card wraps' data-ids and bind any matching unnamed
# WS conversation to this row's name — deterministic (globally unique cmid),
# mis-delivery-proof. The ws170 flush then delivers the parked ack within one
# scan tick. Gate ECAN_FEIGE_CARD_CMID_JOIN=1 (default on). Marker [ws177].
_WS177_CARD_JOIN_JS = r"""(function(){
  var wraps = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
  var out = [];
  for (var i = wraps.length - 1; i >= 0 && out.length < 3; i--) {
    var w = wraps[i];
    var idn = w.querySelector('[data-id]');
    var did = idn ? String(idn.getAttribute('data-id') || '') : '';
    // ws177b: match by the '_template' data-id suffix, NOT the container class.
    // The 2026-07-14 17:37:12 dump showed the DIRECT product card renders as
    // .chatd-card (no pigeon-dynamic container) while the assistant-
    // recommendation card (2026-07-13 dump) is pigeon-dynamic with NO
    // .chatd-card — the original class filter missed today's variant. The
    // '_template' suffix is shared by both card frames' client_message_ids and
    // by neither system-notice family (…_CsAssign_, close_non_process_…,
    // poor_response_notification…).
    if (!did || did.slice(-9) !== '_template') continue;
    out.push(did);
  }
  return JSON.stringify(out);
})()"""


async def _maybe_card_cmid_join(browser_session, customer_key: str, item: dict,
                                log_tag: str) -> None:
    """Bind unnamed card conversations to this named row via cmid join (ws177)."""
    if os.environ.get("ECAN_FEIGE_CARD_CMID_JOIN", "1") == "0":
        return
    if not customer_key or customer_key.startswith("card:"):
        return
    if not (item.get("_ecan_coldstart_recovery") or item.get("_ecan_ws162_reopen")):
        return
    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            _evaluate_js,
        )
        res = await _evaluate_js(
            browser_session, _WS177_CARD_JOIN_JS,
            focus=False, read_only=True, lock_free=True,
            timeout_s=6.0,
            trace_label="ws177_card_cmid_join",
        )
        if isinstance(res, str):
            cmids = json.loads(res)
        else:
            cmids = res or []
        if not isinstance(cmids, list):
            return
        from . import ws_session as _wss177
        for cmid in cmids[:3]:
            talk = _wss177.talk_for_cmid(str(cmid))
            if not talk:
                continue
            if _wss177.bind_talk_name(talk, customer_key, source="ws177_cmid_join"):
                logger.info(
                    f"[BrowserAutomation] {log_tag} ws177 card cmid-join: thread "
                    f"card data-id matched WS conv {talk} -> bound to "
                    f"cust={customer_key!r}; parked replies flush next tick"
                )
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] {log_tag} ws177 card cmid-join failed "
            f"(non-fatal): {type(exc).__name__}: {exc}"
        )


def _check_msg_id_dedup(
    customer_key: str,
    scraped_msg_id: str,
    last_dispatched_cache: dict,
    session_id: str,
    log_tag: str,
) -> bool:
    """Return True iff the scraped msg-id matches the one we already
    dispatched for this customer (i.e. customer hasn't said anything
    new).  Safe no-op when *scraped_msg_id* is empty.
    """
    if not scraped_msg_id:
        return False
    prev_msg_id = last_dispatched_cache.get(customer_key, "")
    if not prev_msg_id or prev_msg_id != scraped_msg_id:
        return False
    logger.info(
        f"[BrowserAutomation] {log_tag} msg-id dedup skip "
        f"session={session_id!r} cust={customer_key!r} "
        f"(last customer bubble msg_id=...{scraped_msg_id[-8:]} "
        f"already dispatched)"
    )
    return True


def _check_dom_echo_fallback(
    item: dict,
    customer_key: str,
    session_id: str,
    assigned_sessions: dict,
    last_agent_reply_cache: dict,
    normalize_reply_text: Callable[[str], str],
    log_tag: str,
) -> tuple[bool, str]:
    """Two secondary defences used only when the chat-thread scrape
    failed to return a usable msg-id.

    Returns ``(skip, reason)``.  Reasons: ``"dom_echo"`` (text match
    against our pre-recorded reply) or
    ``"assigned_sessions_same_message"``.
    """
    item_last_raw = str(
        item.get("last_message")
        or item.get("latest_message")
        or item.get("message")
        or ""
    )
    item_last_norm = ""
    try:
        from .dispatch_state import reply_echo_matches as _reply_echo_matches
    except Exception:
        _reply_echo_matches = None
    # (a) text-based dom-echo.
    try:
        last_agent_reply = last_agent_reply_cache.get(customer_key, "")
        item_last_norm = normalize_reply_text(item_last_raw)
        if (
            last_agent_reply
            and item_last_norm
            and (
                item_last_norm == last_agent_reply
                or (
                    _reply_echo_matches is not None
                    and _reply_echo_matches(item_last_raw, last_agent_reply)
                )
            )
        ):
            # 2026-05-27 mt050K-(b) — when the matched sidebar text is
            # a PLACEHOLDER (e.g. "人工服务正在回复中..."), the customer's
            # real question is still unanswered.  Suppressing here would
            # strand the customer for the full RECENT_REPLY_TTL_S
            # (~90 s).  Live trace 2026-05-27 15:41-15:51: customer
            # 肽斯特 waited 10 min after a stale-drop because the
            # sidebar showed the placeholder echo and PreDispatch
            # dom-echo-skipped every retry.  Skip the suppression when
            # the match was a placeholder; the caller will fall through
            # to thread-scrape which sees the actual customer bubble.
            try:
                from .dispatch_state import is_placeholder_text as _is_ph_text
                _matched_is_placeholder = _is_ph_text(item_last_raw)
            except Exception:
                _matched_is_placeholder = False
            if _matched_is_placeholder:
                logger.info(
                    f"[BrowserAutomation] {log_tag} mt050K dom-echo "
                    f"override session={session_id!r} cust={customer_key!r} "
                    f"— sidebar matches a placeholder echo, NOT a real "
                    f"reply; allowing re-dispatch of underlying question"
                )
                # Fall through to the normal pre-dispatch path; don't return skip.
            else:
                if assigned_sessions.pop(session_id, None) is not None:
                    logger.info(
                        f"[BrowserAutomation] {log_tag} dom-echo evicted "
                        f"assigned_sessions[{session_id!r}] because the agent "
                        f"reply is now visible in the sidebar"
                    )
                logger.info(
                    f"[BrowserAutomation] {log_tag} dom-echo skip "
                    f"session={session_id!r} cust={customer_key!r} "
                    f"(thread-scrape unavailable; sidebar last_message "
                    f"matches our pre-recorded reply — refusing to "
                    f"re-dispatch our own text)"
                )
                return True, "dom_echo"
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] {log_tag} dom-echo fallback "
            f"failed: {exc}"
        )

    # (b) assigned_sessions text-match heuristic.
    #
    # Older code skipped on *any* prior assignment when thread scraping
    # failed.  That is unsafe under CDP contention: a customer can send
    # a newer sidebar-visible message while the stale assignment remains
    # present, and the front desk will silently suppress the new turn.
    # Only dedup when the prior assignment recorded the same message
    # text; otherwise the newer sidebar preview supersedes the pending
    # assignment.
    assigned = assigned_sessions.get(session_id)
    if assigned:
        prior_text = ""
        if isinstance(assigned, dict):
            prior_text = str(
                assigned.get("latest_message")
                or assigned.get("last_message")
                or assigned.get("source_latest_message")
                or ""
            )
        prior_norm = normalize_reply_text(prior_text) if prior_text else ""
        if prior_norm and item_last_norm and prior_norm == item_last_norm:
            logger.info(
                f"[BrowserAutomation] {log_tag} assigned-sessions skip "
                f"session={session_id!r} cust={customer_key!r} "
                f"(thread-scrape unavailable; same message already "
                f"assigned; prior assignment={assigned})"
            )
            return True, "assigned_sessions_same_message"
        # 2026-05-19 Fix A: bot-reply DOM-echo guard for the supersede
        # path.  When the sidebar last_message has flipped to OUR most
        # recent reply text for this customer (Feige rendered the bot's
        # outbound message on the customer's bubble side), the text
        # legitimately differs from the prior assignment's customer
        # question — but it is NOT a new customer turn, it is just the
        # DOM-echo of our own outgoing reply.  Without this guard,
        # supersede fires and triggers a fresh duplicate dispatch.
        # Observed in the 2026-05-19 21:11 customer-log trace where
        # packet "这件穿了会不会过敏" was dispatched 5 times because the
        # bot's earlier reply renders kept tripping this supersede.
        last_reply_norm = ""
        if last_agent_reply_cache:
            last_reply_raw = str(
                last_agent_reply_cache.get(customer_key, "") or ""
            )
            if last_reply_raw:
                try:
                    last_reply_norm = normalize_reply_text(last_reply_raw)
                except Exception:
                    last_reply_norm = ""
        if last_reply_norm and item_last_norm and last_reply_norm == item_last_norm:
            logger.info(
                f"[BrowserAutomation] {log_tag} bot-reply-echo skip "
                f"session={session_id!r} cust={customer_key!r} "
                f"(thread-scrape unavailable; sidebar text matches our "
                f"last reply for this customer — DOM-echo, not a new "
                f"turn.  prior assignment={prior_text[:80]!r}, "
                f"echo={item_last_raw[:80]!r})"
            )
            return True, "bot_reply_echo_supersede_blocked"
        # Multi-slot ledger: catch echoes from placeholder texts that
        # were typed in addition to the single-slot last reply.  The
        # single-slot check above only remembers ONE text, so when a
        # real reply is followed by a placeholder (or vice versa) the
        # sidebar can echo the *other* one and slip past.
        try:
            from .dispatch_state import (
                matches_recent_agent_reply as _matches_recent_reply,
            )
        except Exception:
            _matches_recent_reply = None
        if _matches_recent_reply is not None and item_last_raw:
            _recent_echo = _matches_recent_reply(customer_key, item_last_raw)
            if _recent_echo:
                logger.info(
                    f"[BrowserAutomation] {log_tag} recent-echo skip "
                    f"session={session_id!r} cust={customer_key!r} "
                    f"(thread-scrape unavailable; sidebar text matches "
                    f"one of our recent typed messages — DOM-echo of "
                    f"real reply or placeholder, not a new turn.  "
                    f"prior assignment={prior_text[:80]!r}, "
                    f"echo={item_last_raw[:80]!r}, "
                    f"match={_recent_echo[:80]!r})"
                )
                return True, "recent_echo_supersede_blocked"
        logger.info(
            f"[BrowserAutomation] {log_tag} assigned-sessions supersede "
            f"session={session_id!r} cust={customer_key!r} "
            f"(thread-scrape unavailable; current sidebar text differs "
            f"from prior assignment, allowing dispatch; "
            f"current={item_last_raw[:80]!r}, prior={prior_text[:80]!r}, "
            f"prior assignment={assigned})"
        )
    return False, ""


async def enrich_item(
    *,
    item: dict,
    browser_session,
    customer_key: str,
    session_id: str,
    log_tag: str,
    assigned_sessions: dict,
    customer_last_dispatched_msg_id: dict,
    auto_dispatch_last_agent_reply: dict,
    normalize_reply_text: Callable[[str], str],
    typing_holder_getter: Callable[[], str] | None = None,
) -> EnrichResult:
    """Plugin entry-point: enrich one dispatch candidate with Feige
    ground-truth data and apply all Feige-specific skip guards.

    See module docstring for the three-stage pipeline.  When
    *typing_holder_getter* returns a non-empty key, enrichment skips
    the thread scrape and uses the sidebar preview so dispatch can
    continue without stealing focus from a concurrent HOT-PATH-B reply.
    """
    # mt017 Stage -1: human-intervention skip.  Pre-mt036A this used
    # the blanket :func:`is_handled_recent` check which dropped
    # dispatches for the full 120 s TTL after ANY mark fired — even
    # legitimate dispatches for newer questions the human did NOT
    # answer.
    #
    # Post-mt036A: REMOVED at this stage.  Dispatch proceeds; the
    # Q&A bot generates a reply; the direct-delivery hot path
    # (runner.py) applies the SCOPED :func:`is_question_handled`
    # check at type-time and drops only when the bot's reply targets
    # the SAME customer question the human answered.  Cost: a wasted
    # LLM round (~5 s) in the rare case the bot answers a handled
    # question.  Benefit: replies for unrelated newer questions stop
    # being silently lost.
    #
    # The check is intentionally left here as a no-op comment block
    # rather than deleted, so the failure mode is grep-discoverable
    # if we ever need to re-enable the blanket guard (e.g. for an
    # operator preference: "really stop everything when I take over").
    pass
    try:
        # Sentinel imports retained so future tooling can flag a missing
        # human_intervention module at this site rather than at the
        # delivery hot path.
        from . import human_intervention as _hi_skip  # noqa: F401
        _ = _hi_skip  # silence linters about unused import
    except Exception as _hi_exc:
        logger.debug(
            f"[BrowserAutomation] {log_tag} human-intervention check "
            f"failed (non-fatal): {_hi_exc}"
        )
    # Stage 0: Pre-scrape dom-echo fast-path (added 2026-04-30 20:30).
    # When the sidebar last_message text already equals our last
    # recorded agent reply for this customer, we already answered them
    # and no thread-scrape is required.  This avoids the 6s CDP
    # Runtime.evaluate timeout that PreDispatch was hitting on every
    # already-answered customer in the sidebar (observed 2026-04-30
    # 20:24-20:25 where 5 sequential 6s timeouts produced two 60s
    # front-desk stalls).  Safe because the sidebar shows the LATEST
    # entry only -- if the customer had sent a newer message it would
    # supersede our reply text in last_message.
    try:
        _early_last_raw = str(
            item.get("last_message")
            or item.get("latest_message")
            or item.get("message")
            or ""
        )
        # 转人工 handover ack — EARLY arm, before ANY skip (dom-echo / typing-lock /
        # self-block / system-message filter) can defer this row and bypass the
        # later _maybe_arm_handover_ack (which only fires on the system-filter skip
        # at the bottom of the pipeline). A customer who types 转人工 is a customer
        # message that must get a response within Feige's 40s window — we ack it with
        # the [微笑] (same as the WS path in ws_observer), and the bot keeps assisting
        # on later turns. Delivery still gated by handover_ack_enabled (default on).
        try:
            from . import human_mode as _hm_early
            # ws117: is_human_handover_request (SHORT standalone), NOT is_human_trigger —
            # _early_last_raw is the sidebar last_message, which is frequently OUR own
            # reply/placeholder containing 人工; substring-matching it flooded false acks.
            if _early_last_raw and _hm_early.is_human_handover_request(_early_last_raw):
                from .placeholder_timer import note_handover_ack_needed as _note_ho_early
                _note_ho_early(customer_key)
                logger.info(
                    f"[BrowserAutomation] {log_tag} 转人工 handover trigger (early-arm) "
                    f"cust={customer_key!r} text={_early_last_raw[:40]!r} -> [微笑] ack armed")
        except Exception:
            pass
        # mt052I (2026-05-29): when the matched sidebar text is one of our
        # placeholder echoes ("人工服务正在回复中..."), the customer's real
        # question is still unanswered — same logic as mt050K-(b) at the
        # post-scrape dom-echo guard but applied at the pre-scrape fast-
        # path here too.  Without this, 客户06 trace 2026-05-29 12:00:00
        # showed dom_echo_pre_scrape skipping the HOT-PATH-B retry payload
        # because last_agent_reply was the placeholder text the front-desk
        # had typed earlier — reply was lost.  We compute the flag once and
        # consult it at each of the four pre-scrape skip sites below.
        try:
            from .dispatch_state import is_placeholder_text as _is_ph_text
            _early_sidebar_is_placeholder = (
                bool(_early_last_raw) and _is_ph_text(_early_last_raw)
            )
        except Exception:
            _early_sidebar_is_placeholder = False
        _early_prev_reply = auto_dispatch_last_agent_reply.get(customer_key, "")
        if _early_last_raw and _early_prev_reply:
            _early_norm = normalize_reply_text(_early_last_raw)
            try:
                from .dispatch_state import reply_echo_matches as _reply_echo_matches
            except Exception:
                _reply_echo_matches = None
            if _early_norm and (
                _early_norm == _early_prev_reply
                or (
                    _reply_echo_matches is not None
                    and _reply_echo_matches(_early_last_raw, _early_prev_reply)
                )
            ):
                if _early_sidebar_is_placeholder:
                    logger.info(
                        f"[BrowserAutomation] {log_tag} mt052I pre-scrape "
                        f"dom-echo override session={session_id!r} "
                        f"cust={customer_key!r} — sidebar matches our recorded "
                        f"reply but it's a PLACEHOLDER, not a real answer; "
                        f"allowing dispatch to continue"
                    )
                    # Fall through to subsequent checks / thread-scrape so
                    # the underlying customer question can be re-dispatched.
                else:
                    if assigned_sessions.pop(session_id, None) is not None:
                        logger.info(
                            f"[BrowserAutomation] {log_tag} pre-scrape "
                            f"dom-echo evicted assigned_sessions[{session_id!r}] "
                            f"because the agent reply is now visible in the sidebar"
                        )
                    logger.info(
                        f"[BrowserAutomation] {log_tag} pre-scrape dom-echo "
                        f"skip session={session_id!r} cust={customer_key!r} "
                        f"(sidebar last_message already matches our recorded "
                        f"reply -- skipping 6s thread scrape)"
                    )
                    return EnrichResult(
                        skip=True, skip_reason="dom_echo_pre_scrape", scraped_msg_id=""
                    )
        # Multi-slot check: even when single-slot last reply differs (e.g.
        # the most recent recorded text is the real reply but the sidebar
        # currently echoes a placeholder), suppress dispatch if the sidebar
        # matches ANY of our recent typed messages for this customer.
        if _early_last_raw:
            try:
                from .dispatch_state import (
                    matches_recent_agent_reply as _matches_recent_reply,
                )
            except Exception:
                _matches_recent_reply = None
            if _matches_recent_reply is not None:
                _recent_echo = _matches_recent_reply(customer_key, _early_last_raw)
                if _recent_echo:
                    if _early_sidebar_is_placeholder:
                        logger.info(
                            f"[BrowserAutomation] {log_tag} mt052I pre-scrape "
                            f"recent-echo override session={session_id!r} "
                            f"cust={customer_key!r} — sidebar matches a recent "
                            f"typed message but it's a PLACEHOLDER; allowing "
                            f"dispatch to continue (match={_recent_echo[:80]!r})"
                        )
                        # Fall through to subsequent checks.
                    else:
                        if assigned_sessions.pop(session_id, None) is not None:
                            logger.info(
                                f"[BrowserAutomation] {log_tag} pre-scrape "
                                f"recent-echo evicted assigned_sessions[{session_id!r}]"
                            )
                        logger.info(
                            f"[BrowserAutomation] {log_tag} pre-scrape recent-echo "
                            f"skip session={session_id!r} cust={customer_key!r} "
                            f"(sidebar text matches a recent typed message — DOM-echo "
                            f"of real reply or placeholder.  match={_recent_echo[:80]!r})"
                        )
                        return EnrichResult(
                            skip=True, skip_reason="recent_echo_pre_scrape", scraped_msg_id=""
                        )
            # 2026-05-23 mt028: back-stop with the no-TTL typed-text
            # set and the per-process baseline text.  Catches the
            # cases the TTL'd recent_agent_replies multi-slot ledger
            # misses (fresh process + yesterday's bubble in DOM).
            try:
                from . import human_intervention as _hi_pre
                _baseline_txt = _hi_pre.get_baseline_text(customer_key)
                if (
                    _baseline_txt
                    and _early_last_raw.strip() == _baseline_txt.strip()
                ):
                    if _early_sidebar_is_placeholder:
                        logger.info(
                            f"[BrowserAutomation] {log_tag} mt052I pre-scrape "
                            f"baseline-text override session={session_id!r} "
                            f"cust={customer_key!r} — baseline match is a "
                            f"PLACEHOLDER; allowing dispatch to continue"
                        )
                        # Fall through.
                    else:
                        if assigned_sessions.pop(session_id, None) is not None:
                            logger.info(
                                f"[BrowserAutomation] {log_tag} pre-scrape "
                                f"baseline-text evicted assigned_sessions[{session_id!r}]"
                            )
                        logger.info(
                            f"[BrowserAutomation] {log_tag} pre-scrape baseline-text "
                            f"skip session={session_id!r} cust={customer_key!r} "
                            f"(sidebar matches mt028 pre-existing baseline; "
                            f"echo={_early_last_raw[:80]!r})"
                        )
                        return EnrichResult(
                            skip=True, skip_reason="baseline_text_pre_scrape", scraped_msg_id=""
                        )
                if _hi_pre.is_known_typed_text(customer_key, _early_last_raw):
                    if _early_sidebar_is_placeholder:
                        logger.info(
                            f"[BrowserAutomation] {log_tag} mt052I pre-scrape "
                            f"typed-text override session={session_id!r} "
                            f"cust={customer_key!r} — known typed text is a "
                            f"PLACEHOLDER; allowing dispatch to continue "
                            f"(echo={_early_last_raw[:80]!r})"
                        )
                        # Fall through.
                    else:
                        if assigned_sessions.pop(session_id, None) is not None:
                            logger.info(
                                f"[BrowserAutomation] {log_tag} pre-scrape "
                                f"typed-text evicted assigned_sessions[{session_id!r}]"
                            )
                        logger.info(
                            f"[BrowserAutomation] {log_tag} pre-scrape typed-text "
                            f"skip session={session_id!r} cust={customer_key!r} "
                            f"(sidebar matches a bubble WE typed earlier; "
                            f"echo={_early_last_raw[:80]!r})"
                        )
                        return EnrichResult(
                            skip=True, skip_reason="typed_text_pre_scrape", scraped_msg_id=""
                        )
            except Exception:
                pass
    except Exception as _early_exc:
        logger.debug(
            f"[BrowserAutomation] {log_tag} pre-scrape dom-echo "
            f"check failed (non-fatal): {_early_exc}"
        )

    typing_lock_sidebar_only = False
    sidebar_only_reason = ""
    if typing_holder_getter is not None:
        try:
            _holder = str(typing_holder_getter() or "").strip()
        except Exception as _holder_exc:
            logger.debug(
                f"[BrowserAutomation] {log_tag} typing-lock check failed "
                f"(non-fatal): {_holder_exc}"
            )
            _holder = ""
        # ws112 Fix A: self-block detection. A name-less product card is
        # dispatched under the synthetic ``card:<talk_id>`` identity and grabs
        # the typing lock; the SAME conversation's real-name text row (e.g. the
        # customer's "这款有包邮吗") then matches the system/connect-banner guard
        # below and is DEFERRED behind the typing lock its OWN card identity is
        # holding — the conversation blocks itself (live 2026-06-24: 陆地飞鱼
        # stranded ~34s until the ws108 backstop forced the scrape). When the
        # holder resolves to the same talk_id as this row, the scrape is safe
        # (same conversation → no cross-customer mis-delivery; the ws108 backstop
        # already proves it) so we DON'T go sidebar-only. A different customer
        # holding the lock still defers (genuine browser contention). Env-disable:
        # ECAN_FEIGE_SELFBLOCK_SCRAPE=0.
        _self_block_same_conv = False
        if (_holder and _holder.startswith("card:")
                and os.environ.get("ECAN_FEIGE_SELFBLOCK_SCRAPE", "1") == "1"):
            try:
                _holder_talk = _holder.split(":", 1)[1].strip()
                _row_talk = str(
                    item.get("talk_id") or item.get("conversation_id") or ""
                ).strip()
                if not _row_talk:
                    from . import ws_session as _ws_sess_sb
                    _row_talk = str(_ws_sess_sb.talk_for_name(customer_key) or "").strip()
                if _holder_talk and _row_talk and _holder_talk == _row_talk:
                    _self_block_same_conv = True
                    logger.info(
                        f"[BrowserAutomation] {log_tag} ws112 self-block: typing-lock "
                        f"holder={_holder!r} is the SAME conversation (talk={_holder_talk}) "
                        f"as cust={customer_key!r} — allowing thread scrape instead of "
                        f"deferring (conv was blocking its own real message)"
                    )
            except Exception as _sb_err:
                logger.debug(
                    f"[BrowserAutomation] {log_tag} ws112 self-block check "
                    f"failed (non-fatal): {_sb_err}"
                )
        if _holder and not _self_block_same_conv:
            logger.info(
                f"[BrowserAutomation] {log_tag} typing-lock sidebar-only "
                f"session={session_id!r} cust={customer_key!r} "
                f"holder={_holder!r} (not scraping/clicking while Feige "
                "reply delivery owns the browser)"
            )
            typing_lock_sidebar_only = True
            sidebar_only_reason = "typing_lock"

            # 2026-05-23 mt031: in sidebar-only mode the thread scrape
            # is skipped, so mt019 customer-bubble-msg-id dedup and
            # mt030 agent-vs-customer-index check can't fire.  Without
            # those, a stale-but-currently-shown sidebar text can be
            # dispatched as new — observed live 2026-05-22 17:00:13 for
            # 客户16: same question "你们默认走什么快递？" dispatched
            # twice (13 s apart) because the typing-lock was held by
            # 客户19 during the second cycle.
            #
            # Mirror the actionable_items.py text-based identity_key
            # dedup here for the sidebar-only path.  The identity_key
            # is what actionable_items already stamps after a
            # successful dispatch, so this check is symmetric with the
            # HOT-PATH-B filter that drops 客户16(already_dispatched).
            try:
                from .actionable_items import _dispatched_identity_keys as _ai_keys
                import time as _ai_time
                _ident = str(item.get("identity_key") or "").strip()
                if _ident and _ident in _ai_keys:
                    _age = _ai_time.time() - _ai_keys[_ident]
                    item["_ecan_pre_dispatch_skip_reason"] = "identity_key_dedup_sidebar_only"
                    logger.info(
                        f"[BrowserAutomation] {log_tag} mt031 sidebar-only "
                        f"identity_key dedup skip session={session_id!r} "
                        f"cust={customer_key!r} ident={_ident!r} age={_age:.1f}s "
                        f"(this identity_key was dispatched already; skipping "
                        f"duplicate dispatch on the typing-lock fallback path)"
                    )
                    # ws007 (2026-06-06): MUST return an EnrichResult, not "".
                    # Returning a bare string made the caller's `if enrich.skip:`
                    # (frontdesk_dispatch.py) raise AttributeError: 'str' object has
                    # no attribute 'skip' — which crashed the whole item dispatch and
                    # stranded the customer's turn for ~90s until a watchdog recovered
                    # it (live 2026-06-06: fired 4x for 肽斯特/瓦哒嘻哇/陆地飞鱼, the
                    # "stuck for 1.5 min" turns). This is a dedup SKIP, so signal it.
                    return EnrichResult(
                        skip=True,
                        skip_reason="identity_key_dedup_sidebar_only",
                        scraped_msg_id="",
                    )
            except Exception as _mt031_err:
                logger.debug(
                    f"[BrowserAutomation] {log_tag} mt031 identity_key "
                    f"dedup check failed (non-fatal): {_mt031_err}"
                )

    # NOTE: the prior "live-monitor sidebar-only" fast path (2026-05-11) used
    # to bypass the thread scrape whenever a pending-marker was present on
    # the sidebar row.  That was an over-aggressive optimization: the thread
    # scrape is also where we extract customer-bubble image attachments
    # (see ``dom_assets.FEIGE_LATEST_CUSTOMER_BUBBLE_JS._collectAttachments``
    # and ``_scrape_and_override_last_message``'s ``fetch_attachments`` call).
    # Skipping the scrape therefore silently dropped every image a customer
    # sent — reproduced live 2026-05-11 10:48 where 14/20 pending customers
    # went sidebar-only and only 客户14 (forced through scrape via the
    # system-y sidebar guard) actually received its image through the Q&A
    # pipeline ([data-uri-mitigation] image_ref_stored / image_ref_resolved /
    # [multimodal] prep: built 1 image part(s)).  We now always fall through
    # to the thread scrape below for non-typing-lock items so multimodal
    # content reaches the LLM.  The typing-lock sidebar-only path above is
    # structurally required — we cannot scrape while the send path owns
    # the browser — and is preserved.

    scraped_msg_id = ""
    if not typing_lock_sidebar_only:
        scraped_msg_id = await _scrape_and_override_last_message(
            browser_session,
            item,
            customer_key,
            log_tag,
            typing_holder_getter,
            customer_last_dispatched_msg_id=customer_last_dispatched_msg_id,
        )
        predispatch_skip_reason = str(
            item.pop("_ecan_pre_dispatch_skip_reason", "") or ""
        )
        if predispatch_skip_reason:
            return EnrichResult(
                skip=True,
                skip_reason=predispatch_skip_reason,
                scraped_msg_id="",
            )

    # Stage 1.5: System / platform message guard.
    #
    # The Feige sidebar's ``last_message`` preview AND occasionally the
    # chat-thread bubble extractor can surface non-customer-authored
    # text — platform stall warnings ("当前会话已长时间未回复"),
    # human-handover system messages ("您好，现在是人工客服为您服务"),
    # built-in 智能客服 auto-replies ("亲亲，在哒~"), etc.  When these
    # reach the Q&A worker as ``latest_message`` the LLM dutifully
    # *answers them* — observed live 2026-04-27 10:35:01 where the bot
    # replied to a platform warning with "您好，这条提示像是系统状态
    # 提醒...".  Filter HERE, BEFORE the dedup cache is touched, so a
    # genuine subsequent customer message isn't suppressed by msg-id
    # dedup against a system-noise turn we accidentally remembered.
    try:
        from .system_message_filter import (
            first_system_row_match as _first_row_match,
            first_matching_pattern as _first_pat,
        )
        _row_hit = _first_row_match(item)
        _stage15_pending_marker = any(
            str(item.get(k) or "").strip()
            for k in (
                "pending_timer",
                "unread_badge",
                "unread",
                "needs_action",
            )
        )
        if _row_hit:
            _pending_marker = _stage15_pending_marker
            if sidebar_only_reason == "typing_lock" and _pending_marker:
                # Register for re-fire: when the typing-lock releases and
                # the next DOM monitor tick runs, event_monitor will see
                # this entry and force an emit even though no row was
                # added — see the B1 block at the top of this module and
                # event_monitor.py:_should_emit_for_deferred(...).
                _record_deferred(session_id, customer_key)
                logger.info(
                    f"[BrowserAutomation] {log_tag} system-looking pending "
                    f"row deferred while typing lock is active for "
                    f"cust={customer_key!r} reason={_row_hit!r}"
                )
                return EnrichResult(
                    skip=True,
                    skip_reason="typing_lock_active",
                    scraped_msg_id="",
                )
            if _pending_marker and not scraped_msg_id:
                logger.info(
                    f"[BrowserAutomation] {log_tag} system-looking pending "
                    f"row deferred for cust={customer_key!r} "
                    f"reason={_row_hit!r} (sidebar polluted by auto-reply/"
                    "system text; thread scrape did not recover a real "
                    "customer bubble -- will retry next cycle)"
                )
                return EnrichResult(
                    skip=True,
                    skip_reason="sidebar_polluted_pending_retry",
                    scraped_msg_id="",
                )
            logger.info(
                f"[BrowserAutomation] {log_tag} system-message filter "
                f"SKIP for cust={customer_key!r} reason={_row_hit!r}"
            )
            _maybe_arm_handover_ack(customer_key, _row_hit, log_tag)
            return EnrichResult(
                skip=True,
                skip_reason=_row_hit,
                scraped_msg_id=scraped_msg_id,
            )
        _candidate_text = str(item.get("last_message") or "")
        _smf_hit = _first_pat(_candidate_text)
        if _smf_hit:
            if _stage15_pending_marker and not scraped_msg_id:
                logger.info(
                    f"[BrowserAutomation] {log_tag} system-looking pending "
                    f"preview deferred for cust={customer_key!r} "
                    f"pattern={_smf_hit!r} (thread scrape did not recover "
                    "a real customer bubble -- will retry next cycle)"
                )
                return EnrichResult(
                    skip=True,
                    skip_reason="sidebar_polluted_pending_retry",
                    scraped_msg_id="",
                )
            logger.info(
                f"[BrowserAutomation] {log_tag} system-message filter "
                f"SKIP for cust={customer_key!r} pattern={_smf_hit!r} "
                f"text={_candidate_text[:80]!r}"
            )
            _maybe_arm_handover_ack(customer_key, _smf_hit, log_tag)
            return EnrichResult(
                skip=True,
                skip_reason=f"system_message:{_smf_hit}",
                scraped_msg_id=scraped_msg_id,
            )
    except Exception as _smf_exc:
        # Defence-in-depth: a filter failure must not abort dispatch.
        logger.debug(
            f"[BrowserAutomation] {log_tag} system-message filter "
            f"raised (non-fatal): {type(_smf_exc).__name__}: {_smf_exc}"
        )

    # Stage 2: strict msg-id dedup (only meaningful when scrape gave us an id).
    try:
        if _check_msg_id_dedup(
            customer_key,
            scraped_msg_id,
            customer_last_dispatched_msg_id,
            session_id,
            log_tag,
        ):
            # ws177: FIRST try the cmid join — if the thread shows a card whose
            # data-id matches an unnamed WS conversation, bind it to this row's
            # name (the parked card-ack then flushes via ws170 within a tick).
            await _maybe_card_cmid_join(
                browser_session, customer_key, item, log_tag
            )
            # ws170: "nothing new" on a just-reopened conversation is the
            # signature of the invisible-card failure — dump the thread tail
            # so the card bubble's real DOM can be captured (rate-limited).
            await _maybe_dump_card_dom(
                browser_session, customer_key, item, log_tag
            )
            return EnrichResult(
                skip=True,
                skip_reason="msg_id_dedup",
                scraped_msg_id=scraped_msg_id,
            )
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] {log_tag} msg-id guard failed: {exc}"
        )

    # Stage 3a: scrape-failure fallback guards.
    if not scraped_msg_id:
        skip, reason = _check_dom_echo_fallback(
            item,
            customer_key,
            session_id,
            assigned_sessions,
            auto_dispatch_last_agent_reply,
            normalize_reply_text,
            log_tag,
        )
        if skip:
            return EnrichResult(skip=True, skip_reason=reason, scraped_msg_id="")

    # Stage 3b: if scrape succeeded AND there's a stale assigned_sessions
    # entry, signal the caller to clear it — the msg-id guard above
    # already confirmed this is a genuinely new customer turn.
    should_clear_stale = bool(
        scraped_msg_id and assigned_sessions.get(session_id)
    )
    if should_clear_stale:
        logger.info(
            f"[BrowserAutomation] {log_tag} clearing stale "
            f"assigned_sessions entry for session={session_id!r} "
            f"(new customer bubble detected, "
            f"msg_id=...{scraped_msg_id[-8:]})"
        )

    # B1: this customer successfully cleared the system-greeting filter
    # (we have a real scraped msg_id), so drop any prior typing-lock
    # deferral record. The recurring re-emit in event_monitor stops as
    # soon as the deferred set is empty.
    clear_deferred(session_id, customer_key)

    # 2026-05-26 mt048C: detect customer-pasted URLs and surface them as
    # structured fields on the dispatch item so downstream consumers (the
    # Q&A LLM via the JSON payload, and the future mt048D browser-fetch
    # router) can react.  Default behaviour unchanged — this is detection
    # + foundation only, not routing.  Routing change tracked in mt048D.
    try:
        from . import url_detector as _ud
        # By this point _scrape_and_override_last_message has populated
        # item["last_message"] with the customer's most recent bubble
        # text (when scrape succeeded), so it's the authoritative source.
        _customer_text_for_url = str(
            item.get("last_message")
            or item.get("latest_message")
            or ""
        )
        _urls = _ud.find_all_urls(_customer_text_for_url)
        if _urls:
            _primary_url = _urls[0]
            _is_product = _ud.is_jinritemai_product_url(_primary_url)
            _product_id = _ud.extract_product_id(_primary_url) if _is_product else ""
            # Item flags so downstream (mt048D) can route.  Stored under
            # _ecan_* so they survive the JSON round-trip without
            # polluting the Q&A LLM's user-visible payload.
            item["_ecan_url_detected"] = _primary_url
            item["_ecan_url_all"] = list(_urls)
            item["_ecan_url_is_jinritemai_product"] = bool(_is_product)
            if _product_id:
                item["_ecan_url_product_id"] = _product_id
            logger.info(
                f"[BrowserAutomation] {log_tag} mt048C URL detected for "
                f"cust={customer_key!r}: url={_primary_url!r} "
                f"is_product={_is_product} product_id={_product_id!r} "
                f"url_count={len(_urls)}"
            )
    except Exception as _url_err:
        logger.debug(
            f"[BrowserAutomation] {log_tag} mt048C URL detection failed "
            f"(non-fatal): {_url_err}"
        )

    return EnrichResult(
        skip=False,
        skip_reason="",
        scraped_msg_id=scraped_msg_id,
        should_clear_stale_assignment=should_clear_stale,
    )
