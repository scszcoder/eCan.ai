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

import json
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
        name="conversation_missed",
        kind="invariant",
        severity="incident",
        means=("the site closed a conversation for non-reply AND we have a "
               "record of seeing that customer's message — this one is ours"),
        example="",      # not a phrase: raised by matching a notice to the ledger
    ),
    SiteSignal(
        name="closure_for_unseen_conversation",
        kind="invariant",
        severity="warning",
        means=("the site closed a conversation we have no record of seeing — "
               "it may predate this process, or we may have been blind to it"),
        example="",
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


def notice_customer_uid(text: str) -> str:
    """The customer identifier carried by a notice, or "".

    Measured against a real capture: the plaintext ``biz_conversation_id`` /
    ``customer_id`` / ``customer_name`` fields are empty, and the populated
    ``security_customer_id`` is exactly the ``security_pigeon_uid`` that rides
    messages. That is the only join available between a notice and a
    conversation.
    """
    try:
        if "{" not in text:
            return ""
        obj = json.loads(text[text.find("{"):text.rfind("}") + 1])
        data = obj.get("data") if isinstance(obj, dict) else None
        if not isinstance(data, dict):
            return ""
        return str(data.get("security_customer_id")
                   or data.get("security_biz_conversation_id") or "")
    except Exception:
        return ""


def report_system_event(text: str, *, talk_id: str = "") -> str:
    """Match a system-event string and trip its signal. Returns the name.

    A closure notice gets one extra step: it is matched against the
    conversation ledger, so "the site closed a conversation" becomes either
    "and it was ours to answer" or "and we never saw it". The first is a
    definitive miss -- no inference, the site and our own records agree.

    Never raises: this runs off the frame decoder, and a message from a
    backend we do not control must not be able to break decoding.
    """
    try:
        name = match_system_event(text)
        if not name:
            return ""
        from agent.ec_skills.browser_use_extension import site_signals
        register()

        evidence = {"talk_id": talk_id} if talk_id else {}

        if name == "conversation_closed_unanswered":
            from . import conversation_ledger
            uid = notice_customer_uid(text)
            outcome, why = conversation_ledger.verdict(uid=uid, talk_id=talk_id)
            evidence["verdict"] = outcome
            if outcome == "missed":
                site_signals.trip(SITE, "conversation_missed",
                                  detail=why, evidence=evidence)
            elif outcome == "unknown":
                site_signals.trip(SITE, "closure_for_unseen_conversation",
                                  detail=why, evidence=evidence)
            # "served" still trips the plain closure signal below: the site
            # closed it for non-reply although we dispatched one, which is a
            # delivery failure rather than a miss.

        site_signals.trip(
            SITE, name,
            detail=f"talk={talk_id}" if talk_id else "",
            # Only signal names, a verdict and the opaque talk id. The notice
            # arrives wrapped in JSON that also carries customer fields, so
            # none of that travels.
            evidence=evidence or None,
        )
        return name
    except Exception:
        return ""
