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
   - **legacy assigned_sessions heuristic**: skip if this
     ``session_id`` already has an active assignment record.

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
    against our pre-recorded reply) or ``"assigned_sessions_legacy"``
    (legacy per-session dedup).
    """
    # (a) text-based dom-echo.
    try:
        last_agent_reply = last_agent_reply_cache.get(customer_key, "")
        item_last_norm = normalize_reply_text(item.get("last_message") or "")
        if (
            last_agent_reply
            and item_last_norm
            and item_last_norm == last_agent_reply
        ):
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

    # (b) legacy assigned_sessions heuristic.
    if assigned_sessions.get(session_id):
        logger.info(
            f"[BrowserAutomation] {log_tag} assigned-sessions skip "
            f"session={session_id!r} cust={customer_key!r} "
            f"(thread-scrape unavailable, falling back to legacy "
            f"dedup; prior assignment={assigned_sessions.get(session_id)})"
        )
        return True, "assigned_sessions_legacy"
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
    *typing_holder_getter* returns a non-empty key different from
    *customer_key* the thread-scrape yields early to avoid stealing
    the Feige active session from a concurrent HOT-PATH-B reply.
    """
    scraped_msg_id = await _scrape_and_override_last_message(
        browser_session, item, customer_key, log_tag, typing_holder_getter
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
