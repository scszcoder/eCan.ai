"""What Feige tells us about our own failures, and what we depend on it for.

This is the site half of the declared-signal contract (see the platform module
``site_signals``): the phrases and thresholds, hand-written by whoever knows
this site. Platform owns the vocabulary and the recording; nothing here is
general.

The discovery that prompted this
--------------------------------
Feige emits explicit failure notices over the websocket we already read, and
``ws_reader`` discarded the entire channel::

    continue  # .8 may be a JSON system-event string; skip here

Probing one ordinary captured session (535 decoded received frames) found:

===================================  =====  ==========================
phrase                               count  meaning
===================================  =====  ==========================
用户已等待超N秒，请尽快回复            8     we are late
客服超时未回复用户，系统关闭会话        4     the site CLOSED it: lost
转人工                                2     customer wants a human
===================================  =====  ==========================

Four conversations were closed because we never replied. The site said so, and
we threw the message away.

This matters beyond the immediate fix: it is the only source of **labelled
failures** available in production. Every other detector infers that something
changed; this one is the site stating outright that we lost a customer. That
is the ground truth the self-healing work otherwise has no way to obtain.

A note on where these live in the frame
---------------------------------------
``ws_reader``'s docstring says system events arrive "as JSON at frame .8". In
the real capture they were only found by walking **every** string field
recursively -- matching on ``.8`` alone finds nothing. Anything added here
should be probed against a capture before being trusted, not derived from the
documented layout.
"""

from __future__ import annotations

import re
from typing import List

from agent.ec_skills.browser_use_extension.site_signals import SiteSignal

SITE = "feige_chat"

# ── the declared set ───────────────────────────────────────────────────────
#
# Ordered most severe first; `match_system_event` returns the first hit, so a
# closure notice is never merely reported as "customer waiting".

SIGNALS: List[SiteSignal] = [
    SiteSignal(
        name="conversation_closed_unanswered",
        kind="distress",
        severity="incident",
        means=("the site CLOSED a conversation because we never replied — "
               "this customer is lost, not merely waiting"),
        example="客服超时未回复用户，系统关闭会话",
    ),
    SiteSignal(
        name="customer_waiting",
        kind="distress",
        severity="warning",
        means="the site says a customer has been waiting for a reply",
        example="用户已等待超30秒，请尽快回复",
    ),
    SiteSignal(
        name="handover_requested",
        kind="distress",
        severity="info",
        means="the customer asked for a human agent",
        example="转人工",
    ),
]

# Deliberately loose on the variable parts (the wait threshold changes: 30秒,
# 5分钟, ...) and anchored on the words the site does not vary.
_PATTERNS = [
    ("conversation_closed_unanswered",
     re.compile(r"超时未回复.{0,6}系统关闭会话|系统关闭会话")),
    ("customer_waiting",
     re.compile(r"(用户|客户).{0,4}等待超|等待超\d+\s*(秒|分钟|小时)")),
    ("handover_requested",
     re.compile(r"转人工")),
]


def match_system_event(text: str) -> str:
    """Which declared signal this system-event string is, or ``""``.

    First match wins, and :data:`_PATTERNS` is ordered most severe first: a
    closure notice also contains wait-like wording, and reporting it as merely
    "waiting" would lose the fact that the customer is already gone.
    """
    if not text:
        return ""
    body = str(text)
    for name, pattern in _PATTERNS:
        if pattern.search(body):
            return name
    return ""


def register() -> None:
    """Declare this bundle's signals with the platform. Safe to call twice."""
    from agent.ec_skills.browser_use_extension import site_signals
    site_signals.register(SITE, SIGNALS)


def report_system_event(text: str, *, talk_id: str = "") -> str:
    """Match a system-event string and trip its signal. Returns the name.

    Never raises: this runs off the frame decoder, and a message from a
    backend we do not control must not be able to break decoding.
    """
    try:
        name = match_system_event(text)
        if not name:
            return ""
        from agent.ec_skills.browser_use_extension import site_signals
        register()
        site_signals.trip(
            SITE, name,
            detail=f"talk={talk_id}" if talk_id else "",
            # Only the signal name and the opaque talk id. The notice itself is
            # site boilerplate, but it arrives wrapped in JSON that also carries
            # customer fields, so none of it travels.
            evidence={"talk_id": talk_id} if talk_id else None,
        )
        return name
    except Exception:
        return ""
