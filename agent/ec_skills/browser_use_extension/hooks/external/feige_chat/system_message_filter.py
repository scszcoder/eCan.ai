"""System / platform message text-based denylist for Feige.

Why this module exists
----------------------
The Feige sidebar (and occasionally the chat-thread bubble extractor)
exposes **non-customer-authored** content as if it were the customer's
latest message:

* **Platform notices** the IM platform itself injects, e.g.
  "当前会话已长时间未回复，若后续仍未回复，平台可能主动介入处理。"

* **Auto-replies from the built-in 智能客服 (smart customer service)**
  before a human-handover happens, e.g. "亲亲，在哒~很高兴为您服务".

* **Operational system messages** when a chat is handed over to a real
  agent or marked read, e.g.
  "您好，现在是人工客服为您服务。为了更高效地帮您解决问题..." and
  "客服XXX的小店接入".

* **DOM noise** like the literal label "已读" (read receipt) or the
  transfer-to-human button text "转人工".

When any of these end up in ``item["last_message"]`` (or in a scraped
bubble's ``text``) the front-desk dispatches them to the Q&A worker as
``latest_message`` — and the LLM dutifully *answers them*, leading to
embarrassing outputs like "您好，这条提示像是系统状态提醒..." (replying
to the platform warning) or generic stalls in response to handover
events.

This module owns the **ground truth** of what counts as a non-customer
message.  Both the V1 and V2 dispatch paths import
``is_platform_or_system_message`` and short-circuit BEFORE marking
inflight or calling ``send_chat``.

Design
------
We use a **regex-pattern denylist**, not an allowlist, because:

* The DOM-class filter in ``dom_assets.FEIGE_LATEST_CUSTOMER_BUBBLE_JS``
  already ATTEMPTS structural classification (row direction etc.); this
  module is a defence-in-depth net for cases where the DOM is
  ambiguous or where the sidebar preview is the only source.
* Patterns have far lower false-positive risk than DOM-class heuristics
  for site-specific platform copy that doesn't change often.
* Any miss (a system message we didn't catch) falls back to current
  behaviour (dispatch + reply); any over-match (filtering a real
  customer message) is recoverable on the customer's next turn.  The
  patterns below are intentionally narrow.

To extend: append to ``_PLATFORM_PATTERNS``.  Keep patterns anchored
(use ``^`` / contain a verbatim site-specific phrase) to avoid
matching customer text that incidentally contains a common substring.
"""

from __future__ import annotations

import re
from typing import Iterable

__all__ = [
    "is_platform_or_system_message",
    "is_platform_or_system_customer",
    "first_matching_pattern",
    "first_system_row_match",
]


_SYSTEM_CUSTOMER_NAMES = {
    "\u667a\u80fd\u5ba2\u670d",  # 智能客服
    "\u7cfb\u7edf\u901a\u77e5",  # 系统通知
}


# Each entry is a ``re.compile(... , re.IGNORECASE)`` pattern.  Order
# matters only for diagnostic ``first_matching_pattern`` (returned name
# is the FIRST match) — the boolean check short-circuits.
#
# IMPORTANT: keep these patterns site-anchored.  A pattern that matches
# legitimate Chinese customer text (e.g. just "您好") would silence
# real customers.  Each entry below contains a verbatim platform/system
# phrase that customers do not naturally type.
_PLATFORM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "winback_template_config",
        re.compile(r"\u633d\u5355\u65b9\u6848\u914d\u7f6e|\u50ac\u53d1\u8d27\u8bdd\u672f\u914d\u7f6e", re.IGNORECASE),
    ),
    # ── IM platform-injected stall warning ───────────────────────────
    # Observed verbatim:
    #   "当前会话已长时间未回复，若后续仍未回复，平台可能主动介入处理。"
    # The "平台可能主动介入处理" tail is unique enough on its own.
    (
        "platform_long_no_reply",
        re.compile(r"当前会话已长时间未回复|平台可能主动介入处理", re.IGNORECASE),
    ),
    # ── Built-in 智能客服 auto-reply ─────────────────────────────────
    # Common pre-handover bot greeting.  Customers don't usually open
    # with "亲亲在哒" — that's a brand voice tic of platform bots.
    (
        "smart_cs_auto_greeting",
        re.compile(r"亲亲，?在哒|很高兴为您服务，请问有什么可以帮您", re.IGNORECASE),
    ),
    # ── Human-handover system message ────────────────────────────────
    # Verbatim: "您好，现在是人工客服为您服务。为了更高效地帮您解决问题..."
    (
        "human_handover_notice",
        re.compile(r"现在是人工客服为您服务|为了更高效地帮您解决问题", re.IGNORECASE),
    ),
    # ── Store/agent assignment system message ────────────────────────
    # Verbatim: "客服XXX的小店接入" — XXX is variable agent name.
    (
        "store_assignment_notice",
        re.compile(r"客服\S{1,30}的小店接入|小店接入", re.IGNORECASE),
    ),
    # ── DOM read-receipt label ───────────────────────────────────────
    # Pure label "已读" sometimes leaks into the sidebar preview when
    # the last actual message is invisible to the scraper.  Match it
    # ONLY as a standalone token (whole-string) to avoid false-positive
    # on a customer who happens to write "已读" inside a longer message.
    (
        "read_receipt_label",
        re.compile(r"^\s*已读\s*$"),
    ),
    # ── Transfer-to-human button text ────────────────────────────────
    # Pure label "转人工".  Same standalone-only guard.
    (
        "transfer_to_human_label",
        re.compile(r"^\s*转人工\s*$"),
    ),
    # ── Order/shipment platform alerts ───────────────────────────────
    # Generic platform notices about delivery/refund deadlines that
    # appear inline in the chat thread.  These have very specific
    # phrasings that customers don't reproduce.
    (
        "platform_delivery_notice",
        re.compile(r"系统消息|系统提醒|平台已介入|平台介入处理", re.IGNORECASE),
    ),
]


def first_matching_pattern(text: str) -> str | None:
    """Return the *name* of the first denylist pattern that matches
    ``text``, or ``None`` if no pattern matches.

    Useful for diagnostics: the dispatch path logs WHICH pattern caused
    the skip so future bug reports can confirm the filter fired for
    the right reason.
    """
    if not text or not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None
    for name, pat in _PLATFORM_PATTERNS:
        try:
            if pat.search(stripped):
                return name
        except Exception:
            # A malformed regex would be a bug here, but defence-in-depth:
            # never let pattern evaluation raise into the dispatch path.
            continue
    return None


def is_platform_or_system_message(text: str) -> bool:
    """Return ``True`` if ``text`` matches any platform/system message
    pattern and should NOT be dispatched to the Q&A worker.

    Empty / whitespace-only / non-string input returns ``False``
    (treat as "no signal" — let the caller's existing empty-text guard
    handle it; we don't want to hide a separate "empty message" bug
    inside this filter).
    """
    return first_matching_pattern(text) is not None


def is_platform_or_system_customer(name: str) -> bool:
    """Return True for Feige pseudo-conversations, not real shoppers."""
    if not name or not isinstance(name, str):
        return False
    return name.strip() in _SYSTEM_CUSTOMER_NAMES


def first_system_row_match(item: dict, resolved: dict | None = None) -> str | None:
    """Return a diagnostic reason if a monitor/action row is platform noise."""
    if not isinstance(item, dict):
        return None
    resolved = resolved if isinstance(resolved, dict) else {}

    for field in ("customer_name", "customer_id", "name"):
        val = str(resolved.get(field) or item.get(field) or "").strip()
        if val and is_platform_or_system_customer(val):
            return f"system_customer:{field}"

    for field in ("last_message", "latest_message", "message", "source_latest_message"):
        val = str(resolved.get(field) or item.get(field) or "").strip()
        if not val:
            continue
        pattern = first_matching_pattern(val)
        if pattern:
            return f"system_message:{field}:{pattern}"

    return None


def is_platform_or_system_message_strict(
    text: str, extra_patterns: Iterable[re.Pattern[str]] | None = None
) -> bool:
    """Like :func:`is_platform_or_system_message` but accepts caller-
    supplied additional patterns (e.g. site-specific overrides loaded
    from a config file).

    This is exposed for the V2 dispatch path which may want to layer
    in customer-tenant-specific platform phrases without modifying
    this module.
    """
    if is_platform_or_system_message(text):
        return True
    if not extra_patterns:
        return False
    if not text or not isinstance(text, str):
        return False
    stripped = text.strip()
    for pat in extra_patterns:
        try:
            if pat.search(stripped):
                return True
        except Exception:
            continue
    return False
