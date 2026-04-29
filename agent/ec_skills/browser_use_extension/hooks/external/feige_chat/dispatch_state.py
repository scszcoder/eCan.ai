"""Feige-chat dispatch state (Phase 6, 2026-04-24).

State dicts + helpers that used to live in ``build_node.py`` module scope
but are purely Feige-customer-chat concerns:

* **HOT-PATH-B recent-send dedup** — suppresses replay loops when
  ``send_response_back``'s fallback path re-fires the same
  ``chat_message`` after a transient ``Chat not found`` error.

* **Last-typed reply per customer** — used by PreDispatch as a DOM-echo
  guard: when Feige's sidebar preview still echoes our outgoing text
  because the customer's freshest bubble hasn't refreshed the preview
  row yet, we compare and skip to wait for the real diff.

* **Last-dispatched msg_id per customer** — replaces the text-based
  dom-echo guard with a strict identity check on Feige's own
  ``data-id`` attribute.

* **Reply-text normaliser** — whitespace-collapsed, 120-char-prefix
  comparison because Feige's sidebar preview trims/collapses
  whitespace and may truncate long replies with an ellipsis.

All state is module-level; the Feige hooks and the Feige enrichment
plugin acquire it via sibling import (the same pattern we use for
``typing_lock``).  ``build_node`` no longer knows about any of this.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time

# ── HOT-PATH-B recent-send dedup cache ───────────────────────────────
# Keyed by (normalised customer_id, sha1(response_text)) → timestamp.
# Prevents replay loops when the same (customer, reply) pair re-enters
# HOT-PATH-B due to a stale pend_event_node resume.  TTL keeps the
# cache bounded; after TTL expires a genuinely identical new reply can
# be re-sent.
_recent_sends: dict[tuple[str, str], float] = {}
_recent_sends_lock = threading.Lock()
DEDUP_TTL_S = 15.0

# ── Last reply HOT-PATH-B typed for each customer ────────────────────
# Keyed by normalised customer id.  Read by PreDispatch to recognise
# its own DOM-echo and wait for a genuinely new customer bubble.
last_agent_reply_by_customer: dict[str, str] = {}

# ── Per-customer record of the LAST customer bubble msg_id that
# PreDispatch successfully dispatched. ────────────────────────────────
# Strict identity check on Feige's own ``data-id`` attribute.
last_dispatched_msg_id_by_customer: dict[str, str] = {}


def normalize_reply_text(text: str) -> str:
    """Normalise a reply for DOM-echo comparison against Feige's sidebar.

    The sidebar preview trims + collapses whitespace and truncates
    long replies with an ellipsis, so we compare whitespace-collapsed,
    stripped, 120-char-prefix versions.
    """
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    return s[:120]


def _fingerprint(customer: str, reply_text: str) -> tuple[str, str]:
    """Build a stable (customer, reply-hash) key for dedup."""
    # Imported lazily to avoid a startup-time circular dep with
    # build_node (which imports this bundle to trigger registration).
    from agent.ec_skills.build_node import _normalize_dispatch_identity_key
    cust = _normalize_dispatch_identity_key(customer or "")
    rtxt = normalize_reply_text(reply_text or "")
    h = hashlib.sha1(rtxt.encode("utf-8", errors="ignore")).hexdigest()[:16] if rtxt else ""
    return (cust, h)


def was_recently_sent(customer: str, reply_text: str) -> float:
    """Return age (s) of a recent identical send, or 0.0 if none/expired."""
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return 0.0
    now = time.time()
    with _recent_sends_lock:
        ts = _recent_sends.get(key)
        if ts is None:
            return 0.0
        age = now - ts
        if age > DEDUP_TTL_S:
            _recent_sends.pop(key, None)
            return 0.0
        return age if age > 0.0 else 0.000001


def claim_send(customer: str, reply_text: str) -> float:
    """Atomically reserve a (customer, reply) pair before typing it.

    Returns 0.0 when this caller acquired the claim.  Returns the age of
    an existing unexpired claim/send when another concurrent hot-path
    cycle already owns the same pair.
    """
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return 0.0
    now = time.time()
    with _recent_sends_lock:
        ts = _recent_sends.get(key)
        if ts is not None:
            age = now - ts
            if age <= DEDUP_TTL_S:
                return age if age > 0.0 else 0.000001
            _recent_sends.pop(key, None)
        _recent_sends[key] = now
        _gc_recent_sends_locked(now)
        return 0.0


def unclaim_send(customer: str, reply_text: str) -> None:
    """Release a pre-send claim after the DOM action failed.

    This lets a later retry deliver the same reply instead of suppressing
    it for the full dedup TTL.
    """
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return
    with _recent_sends_lock:
        _recent_sends.pop(key, None)


def mark_sent(customer: str, reply_text: str) -> None:
    """Record that *reply_text* was just typed into Feige for *customer*."""
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return
    now = time.time()
    with _recent_sends_lock:
        _recent_sends[key] = now
        _gc_recent_sends_locked(now)


def _gc_recent_sends_locked(now: float) -> None:
    """Opportunistically keep the recent-send cache bounded.

    Caller must hold ``_recent_sends_lock``.
    """
    if len(_recent_sends) <= 256:
        return
    for k in list(_recent_sends.keys()):
        if now - _recent_sends[k] > DEDUP_TTL_S:
            _recent_sends.pop(k, None)
