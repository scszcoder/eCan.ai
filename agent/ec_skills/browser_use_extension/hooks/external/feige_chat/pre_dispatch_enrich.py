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

import logging
from dataclasses import dataclass, field
from typing import Callable

from .dom_assets import scrape_latest_customer_bubble

logger = logging.getLogger("eCan")

__all__ = ["EnrichResult", "enrich_item"]


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


async def _scrape_and_override_last_message(
    browser_session,
    item: dict,
    customer_key: str,
    log_tag: str,
    typing_holder_getter: Callable[[], str] | None = None,
) -> str:
    """Scrape the thread for the most recent customer bubble and, if
    successful, overwrite ``item['last_message']``.

    Returns the scraped ``msg_id`` (``""`` on scrape failure).  Mutates
    *item* in place when the scraped text differs from the sidebar
    preview.  *typing_holder_getter*, when provided, is forwarded to
    :func:`scrape_latest_customer_bubble` so its active-session race
    guard fires if HOT-PATH-B is mid-reply to a different customer.
    """
    scraped = await scrape_latest_customer_bubble(
        browser_session,
        str(item.get("customer_name") or ""),
        typing_holder_getter=typing_holder_getter,
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
        logger.debug(
            f"[BrowserAutomation] {log_tag} thread-scrape returned no "
            f"customer bubble for cust={customer_key!r}; falling back "
            f"to sidebar preview"
        )
        return ""

    msg_id = str(scraped.get("msg_id", "") or "")
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
    return msg_id


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
        if _holder:
            logger.info(
                f"[BrowserAutomation] {log_tag} typing-lock sidebar-only "
                f"session={session_id!r} cust={customer_key!r} "
                f"holder={_holder!r} (not scraping/clicking while Feige "
                "reply delivery owns the browser)"
            )
            typing_lock_sidebar_only = True
            sidebar_only_reason = "typing_lock"

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
            browser_session, item, customer_key, log_tag, typing_holder_getter
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

    return EnrichResult(
        skip=False,
        skip_reason="",
        scraped_msg_id=scraped_msg_id,
        should_clear_stale_assignment=should_clear_stale,
    )
