"""Feige human-mode + competing-answer arbitration (转人工 / 智能客服 / 机器人).

A Feige store chat can be answered by up to three systems besides us:
  1) the store bot (机器人, "1st system") — always on, limited answers
  2) the 抖音电商智能客服 agent ("2nd system") — toggleable on/off
  3) human service (人工) — where OUR agent operates, replacing/helping a human

Run modes (conceptual today):
  A) we run alongside the 1st system  — we answer every new customer message
  B) we run alongside the 2nd system  — ideally we'd answer ONLY in human mode,
     but the entry into human mode is vague (customer types 人工, OR the 2nd
     system silently switches). So for NOW, in BOTH modes we answer every new
     ws_reader message. The ``should_respond`` gate below is the single place to
     later plug in a real human-mode signal so mode B stops spending LLM tokens
     on turns a bot/human is still handling.

This module centralizes three behaviours:
  * should_respond(conv_id)          — the future human-mode gate (always True now)
  * is_human_trigger(text)           — does the customer message request 人工?
  * competing-answer arbitration     — when a bot (智能客服/机器人) answers a turn,
                                        drop our own 过渡句/final reply for that
                                        turn and remember the bot's text.

Config: ``<userdata>/feige_human_mode.json`` (store-owner editable). Schema::

    {
      "mode": "A",
      "human_trigger_keywords": ["人工"],            # regex, matched on the msg
      "human_ack_text": "[微笑]",                     # smiley sent on a 人工 trigger
      "competing_answer_sender_patterns": ["智能客服", "机器人"]  # regex on sender name
    }

Defaults above apply when the file is missing or a field is absent.

Gated by env ``ECAN_FEIGE_HUMAN_MODE=1`` (default OFF). When off, every gate here
is a no-op so the live pipeline behaves exactly as before.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

logger = logging.getLogger("eCan")

_DEFAULTS = {
    "mode": "A",
    "human_trigger_keywords": ["人工"],
    "human_ack_text": "[微笑]",
    "competing_answer_sender_patterns": ["智能客服", "机器人"],
}
_CONFIG_FILENAME = "feige_human_mode.json"

_config_cache: dict | None = None
_config_lock = threading.Lock()
_compiled: dict[str, list] = {}


def enabled() -> bool:
    """Master switch. Default OFF — turn on with ECAN_FEIGE_HUMAN_MODE=1."""
    return os.environ.get("ECAN_FEIGE_HUMAN_MODE", "") == "1"


def _load_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    with _config_lock:
        if _config_cache is not None:
            return _config_cache
        cfg = dict(_DEFAULTS)
        try:
            from utils.path_manager import get_user_data_path
            path = os.path.join(get_user_data_path(), _CONFIG_FILENAME)
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    user_cfg = json.load(f)
                if isinstance(user_cfg, dict):
                    cfg.update({k: v for k, v in user_cfg.items() if v is not None})
                logger.info(
                    f"[HumanMode] config loaded from {path}: mode={cfg.get('mode')} "
                    f"keywords={cfg.get('human_trigger_keywords')} "
                    f"ack={cfg.get('human_ack_text')!r} "
                    f"competing={cfg.get('competing_answer_sender_patterns')}"
                )
            else:
                logger.info(
                    f"[HumanMode] no config at {path}; using defaults "
                    f"(keywords={cfg['human_trigger_keywords']}, ack={cfg['human_ack_text']!r})"
                )
        except Exception as e:
            logger.warning(
                f"[HumanMode] config load failed ({type(e).__name__}: {e}); using defaults"
            )
        _config_cache = cfg
        return cfg


def _compiled_patterns(key: str) -> list:
    if key in _compiled:
        return _compiled[key]
    pats = []
    for raw in (_load_config().get(key) or []):
        try:
            pats.append(re.compile(str(raw)))
        except Exception:
            pats.append(re.compile(re.escape(str(raw))))  # bad regex → literal
    _compiled[key] = pats
    return pats


def human_ack_text() -> str:
    return str(_load_config().get("human_ack_text") or _DEFAULTS["human_ack_text"])


def is_ack_text(text: str) -> bool:
    return (text or "").strip() == human_ack_text().strip()


# ws149: AI mentions ("人工智能"/"人工智慧") contain the 人工 substring but are a topic,
# not a handover request. Stripped before the 人工-keyword match so they never fire [微笑].
_HUMAN_AI_EXCLUDE = re.compile(r"人工智[能慧]")


def is_human_trigger(text: str) -> bool:
    """True when the customer message matches a configured 人工 keyword.

    SUBSTRING match — appropriate ONLY for an actual CUSTOMER message (the WS
    observer path), where any mention of 人工 signals handover intent. NOT safe on
    a sidebar PREVIEW, which is often OUR own reply/placeholder ("人工服务正在回复
    中…", "正在为您转接人工客服") or a platform notice ("现在是人工客服为您服务") —
    all contain 人工 and would false-positive. Use :func:`is_human_handover_request`
    there instead. (ws117: this substring match in the ws116 backstop / ws115 enrich
    early-arm flooded false [微笑] acks → "slow from start".)
    """
    t = (text or "").strip()
    if not t:
        return False
    # ws149: "人工智能"/"人工智慧" (AI) contains the 人工 substring but is a product/topic
    # mention, not a handover request. Strip those tokens before matching so "人工智能课程"
    # doesn't fire the [微笑] ack — while "我要转人工，别用人工智能" still matches on the real
    # 转人工. (Even short — is_human_handover_request's length gate doesn't catch 人工智能.)
    t2 = _HUMAN_AI_EXCLUDE.sub("", t)
    if not t2:
        return False
    return any(p.search(t2) for p in _compiled_patterns("human_trigger_keywords"))


# ws117: a customer 人工/转人工 request is SHORT and standalone; our own
# placeholder/replies and platform notices that merely contain 人工 are long.
# Length-gate the substring match so a sidebar preview that is OUR text (or a
# system notice) is not mistaken for a customer handover request.
_HANDOVER_REQUEST_MAX_LEN = 8


def is_human_handover_request(text: str) -> bool:
    """True only when *text* is a SHORT standalone 人工/转人工 request — safe to
    run on a sidebar preview (excludes our placeholder/replies + platform notices,
    which are longer)."""
    t = (text or "").strip()
    if not t or len(t) > _HANDOVER_REQUEST_MAX_LEN:
        return False
    return is_human_trigger(t)


def is_competing_sender(sender_name: str) -> bool:
    """True when a (server-side, role=2) sender name looks like a competing bot."""
    n = (sender_name or "").strip()
    if not n:
        return False
    return any(p.search(n) for p in _compiled_patterns("competing_answer_sender_patterns"))


# ── human-mode gate (scaffold for later) ─────────────────────────────────
# Per-conversation human-mode state. Today every conversation is treated as
# "we respond". When we learn the exact signal that flips a thread INTO human
# mode, record it via set_human_mode() and make should_respond() honour it.
_human_mode_state: dict[str, str] = {}
_state_lock = threading.Lock()


def set_human_mode(conversation_id: str, mode: str) -> None:
    if not conversation_id:
        return
    with _state_lock:
        _human_mode_state[conversation_id] = mode


def get_human_mode(conversation_id: str) -> str:
    return _human_mode_state.get(conversation_id or "", "unknown")


def should_respond(conversation_id: str) -> bool:
    """Future human-mode gate. Always True today (we answer every new message in
    both run modes).

    The first confirmed human-mode ENTRY signal is the WS ``switch_human`` frame
    (ws057) — ws_observer records it via set_human_mode(talk_id, "human"). We do
    NOT gate on it yet: it has only been observed for keyword=人工 handovers, and
    the silent 智能客服 auto-switch (negative sentiment / no-answer, no keyword)
    has not been captured — it may emit a different event. Gating now would risk
    going silent on a human-mode entry we don't yet recognise. Once the entry
    signals are fully mapped, make mode B return ``get_human_mode(conv) == "human"``
    here — that is the single token-saving lever for mode B."""
    return True


# ── competing-answer arbitration ─────────────────────────────────────────
# Keyed by customer NAME — the key feige_send_message and the dispatch pipeline
# already use (session_id == customer name on the WS path).
_turn_started: dict[str, float] = {}        # last customer-msg ts per customer
_competing_answered: dict[str, float] = {}  # last competing bot-answer ts per customer
_arb_lock = threading.Lock()


def note_customer_turn(customer_key: str, ts_ms: int = 0) -> None:
    """A new customer message arrived → opens a fresh turn we should answer, and
    clears any prior competing-answer suppression for this customer."""
    if not customer_key:
        return
    ts = (ts_ms / 1000.0) if ts_ms else time.time()
    with _arb_lock:
        if ts > _turn_started.get(customer_key, 0.0):
            _turn_started[customer_key] = ts


def note_competing_answer(customer_key: str, sender_name: str, text: str, ts_ms: int = 0) -> None:
    """A competing bot (智能客服/机器人) answered this customer → suppress our own
    reply for the current turn and remember the bot's text in thread context."""
    if not customer_key:
        return
    ts = (ts_ms / 1000.0) if ts_ms else time.time()
    with _arb_lock:
        if ts > _competing_answered.get(customer_key, 0.0):
            _competing_answered[customer_key] = ts
    logger.info(
        f"[HumanMode] competing answer noted cust={customer_key!r} by={sender_name!r} "
        f"text={(text or '')[:60]!r} — will suppress our reply for this turn"
    )
    # Best-effort: add the bot's reply to the per-customer recent-message context
    # so a later turn's LLM knows it was already answered.
    try:
        from .actionable_items import _append_recent_message
        _append_recent_message(customer_key, f"[{sender_name or '客服系统'}] {text}")
    except Exception:
        pass


def is_suppressed(customer_key: str) -> bool:
    """True when a competing bot answered AFTER the customer's latest message —
    i.e. the current turn is already handled, so drop our 过渡句/final reply."""
    if not customer_key:
        return False
    with _arb_lock:
        answered = _competing_answered.get(customer_key, 0.0)
        turn = _turn_started.get(customer_key, 0.0)
    return answered > turn > 0.0
