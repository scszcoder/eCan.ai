"""ws170: parking lot for undeliverable card-identity replies.

A cold-start conversation whose FIRST message is a name-less product card is
dispatched under the synthetic ``card:<talk_id>`` identity. When the WS raw
lane can't route it (no per-talk template; first-contact is a proven dead end,
ws131) AND the DOM lane can't find a row by that literal name, the generated
reply is undeliverable **right now** — but the conversation usually gains a
real name minutes later (the customer's first TEXT frame carries the
nickname; live 2026-07-12: card 16:59:40 undeliverable, named frame 17:05:30).

Instead of dropping the reply at the retry-chain dead-ends (runner ws169
ABANDONED, ws127 card-SNF failfast, HOT-PATH-B action_failed), park it here
keyed by talk_id. The front-desk backstop scan (runs every ~5s regardless of
who owns dispatch) drives :func:`resolve_and_flush`: once
``ws_session.name_for_talk(talk)`` yields a real name, the reply is typed via
the standard feige tools under that name — the same de-synth the ws050
placeholder path uses.

Gated ECAN_FEIGE_UNDELIVERABLE_PARK=1 (default on). Entries expire after
ECAN_FEIGE_PARK_TTL_S (900s); each entry gets at most
ECAN_FEIGE_PARK_FLUSH_ATTEMPTS (3) delivery attempts.
Markers: [WS170-PARK] / [WS170-FLUSH].
"""

from __future__ import annotations

import asyncio
import inspect
import os
import threading
import time
from typing import Any

from utils.logger_helper import logger_helper as logger

_LOCK = threading.RLock()
# talk_id -> {customer_key, talk, text, source_msg_id, parked_at, flush_attempts, reason}
_PARKED: dict[str, dict] = {}

_FLUSH_CDP_TIMEOUT_S = 12.0


def _ttl_s() -> float:
    try:
        return float(os.environ.get("ECAN_FEIGE_PARK_TTL_S", "900") or 900)
    except (TypeError, ValueError):
        return 900.0


def _max_attempts() -> int:
    try:
        return int(os.environ.get("ECAN_FEIGE_PARK_FLUSH_ATTEMPTS", "3") or 3)
    except (TypeError, ValueError):
        return 3


def park(customer_key: str, response_text: str, source_msg_id: str = "",
         reason: str = "") -> bool:
    """Park an undeliverable reply for a ``card:<talk>`` identity.

    Returns True when parked. No-op (False) for real-name identities — those
    already have working recovery paths (PreDispatch re-dispatch).
    """
    if os.environ.get("ECAN_FEIGE_UNDELIVERABLE_PARK", "1") == "0":
        return False
    ck = str(customer_key or "")
    if not ck.startswith("card:"):
        return False
    talk = ck[len("card:"):].strip()
    text = str(response_text or "").strip()
    if not talk or not text:
        return False
    with _LOCK:
        _PARKED[talk] = {
            "customer_key": ck,
            "talk": talk,
            "text": text,
            "source_msg_id": str(source_msg_id or ""),
            "parked_at": time.time(),
            "flush_attempts": 0,
            "reason": str(reason or ""),
        }
    logger.warning(
        f"[WS170-PARK] undeliverable reply parked cust={ck!r} len={len(text)} "
        f"reason={reason!r} — will flush when talk->name resolves"
    )
    return True


def _prune_locked(now: float) -> None:
    ttl = _ttl_s()
    for t in [t for t, e in _PARKED.items() if now - e["parked_at"] > ttl]:
        e = _PARKED.pop(t)
        logger.error(
            f"[WS170-PARK] parked reply EXPIRED unflushed cust={e['customer_key']!r} "
            f"age={now - e['parked_at']:.0f}s — talk never resolved to a name; "
            f"reply NOT delivered"
        )


def pending() -> int:
    """Number of live parked entries (prunes expired ones)."""
    with _LOCK:
        _prune_locked(time.time())
        return len(_PARKED)


async def _invoke(action: Any, params: Any, browser_session: Any) -> Any:
    """Mirror the RegisteredAction call pattern used by the placeholder path."""
    sig = inspect.signature(action.function)
    if "browser_session" in sig.parameters:
        raw = action.function(params=params, browser_session=browser_session)
    else:
        raw = action.function(params=params)
    if hasattr(raw, "__await__"):
        return await asyncio.wait_for(raw, timeout=_FLUSH_CDP_TIMEOUT_S)
    return raw


async def resolve_and_flush(browser_session: Any) -> int:
    """Try to deliver parked replies whose talk now resolves to a real name.

    Driven by the front-desk backstop scan tick. Returns number delivered.
    """
    now = time.time()
    with _LOCK:
        _prune_locked(now)
        candidates = [dict(e) for e in _PARKED.values()]
    if not candidates:
        return 0
    try:
        from . import ws_session as _wss
        from .dispatch_state import reply_echo_matches as _echo_match
    except Exception:
        return 0
    delivered = 0
    for entry in candidates:
        talk = entry["talk"]
        try:
            name = str(_wss.name_for_talk(talk) or "").strip()
        except Exception:
            name = ""
        if not name or name.startswith("card:"):
            continue  # still unresolvable — keep parked
        # Already delivered by another lane in the meantime? (e.g. a runner
        # retry that finally found the row). The WS agent-frame echo is the
        # authoritative off-DOM check — same lane ws169's card echo-confirm uses.
        try:
            snap = _wss.ws_thread_snapshot(entry["customer_key"]) or {}
            agent_txt = str((snap.get("agent") or {}).get("text") or "")
            if agent_txt and _echo_match(agent_txt, entry["text"]):
                with _LOCK:
                    _PARKED.pop(talk, None)
                logger.info(
                    f"[WS170-FLUSH] parked reply already on the wire for "
                    f"cust={entry['customer_key']!r} — dropping park entry"
                )
                continue
        except Exception:
            pass
        with _LOCK:
            live = _PARKED.get(talk)
            if live is None:
                continue
            live["flush_attempts"] += 1
            attempts = live["flush_attempts"]
        if attempts > _max_attempts():
            with _LOCK:
                _PARKED.pop(talk, None)
            logger.error(
                f"[WS170-FLUSH] giving up after {attempts - 1} flush attempts "
                f"cust={entry['customer_key']!r} -> name={name!r}; reply NOT delivered"
            )
            continue
        try:
            from agent.ec_skills.browser_use_extension.extension_tools_service import (
                custom_controller as _ctrl,
            )
            _actions = _ctrl.registry.registry.actions
            _open_fn = _actions.get("feige_open_session")
            _send_fn = _actions.get("feige_send_message")
            if not _open_fn or not _send_fn:
                logger.warning("[WS170-FLUSH] feige tools not in registry; keeping park entry")
                continue
            logger.info(
                f"[WS170-FLUSH] talk->name resolved: {entry['customer_key']!r} -> "
                f"{name!r}; delivering parked reply (attempt {attempts}/{_max_attempts()})"
            )
            await _invoke(_open_fn, _open_fn.param_model(customer_name=name), browser_session)
            # Empty source ids bypass source-turn-verify: the original source
            # msg id is a WS card id the DOM verifier can't see (same
            # trade-off the placeholder path makes).
            _res = await _invoke(
                _send_fn,
                _send_fn.param_model(
                    text=entry["text"],
                    customer_name=name,
                    source_customer_msg_id="",
                    source_latest_message="",
                ),
                browser_session,
            )
            _err = getattr(_res, "error", None)
            if _err:
                logger.warning(
                    f"[WS170-FLUSH] send reported error for cust={name!r}: "
                    f"{str(_err)[:120]} — keeping park entry for retry"
                )
                continue
            with _LOCK:
                _PARKED.pop(talk, None)
            delivered += 1
            logger.warning(
                f"[WS170-FLUSH] parked reply DELIVERED cust={name!r} "
                f"(was {entry['customer_key']!r}) len={len(entry['text'])} "
                f"parked_for={now - entry['parked_at']:.0f}s"
            )
            # Keep the dedup/echo ledgers consistent under the REAL name so
            # the backstop's our_recent_reply skip and the DOM-echo filter
            # recognise this bubble as ours.
            try:
                from . import dispatch_state as _ds
                _ds.remember_agent_reply(name, entry["text"])
                _ds.mark_reply_delivered(name, entry["text"], entry["source_msg_id"])
            except Exception:
                pass
        except Exception as _e:
            logger.warning(
                f"[WS170-FLUSH] delivery attempt failed for {name!r}: "
                f"{type(_e).__name__}: {str(_e)[:120]} — keeping park entry"
            )
    return delivered


__all__ = ["park", "pending", "resolve_and_flush"]
