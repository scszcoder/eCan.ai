"""Feige-chat front-desk actionable-items pattern (Phase 7, 2026-04-24).

Owns the full orchestration for "DOM monitor spotted new customer
items → filter by authored policy → inject protocol override into
the LLM's task → optionally auto-dispatch to worker agents without
invoking the LLM at all".

Previously this was ~650 lines of front-desk business logic sitting
inline in ``build_node._run_browser_use`` + three module-level helpers
(`_try_auto_dispatch`, `_evaluate_item_filter`, `_get_agent_load`)
+ four module-level state dicts.  All of it is Feige-specific (the
protocol-override text is steeped in front-desk conventions, the
auto-dispatch fans out via ``send_chat`` to a worker-agent pool),
so it moves here as a single cohesive bundle.

Contract with ``build_node``:

* registers a ``before_prompt_build`` hook
* input: :class:`build_node.PromptBuildContext` (compact_items,
  actionable_raw, actionable_field, event_type, event_label)
* output: :class:`build_node.PromptBuildResult` with any of
  (``short_circuit_state``, ``task_hint_append``, ``override_prepend``)

The hook activates only when ``actionable_field`` is set on the node
(so a non-Feige node without the config never triggers this logic).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from agent.ec_skills.build_node import (
    BrowserUseHookContext,
    PromptBuildContext,
    PromptBuildResult,
    _normalize_dispatch_identity_key,
    _resolve_template,
    register_before_prompt_build_hook,
)
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.system_message_filter import (
    first_system_row_match,
)

# CN builds name the app logger "eCan.cn" (propagate=False) — a bare
# getLogger("eCan") record never reaches its handlers, silencing this
# module's entire log output in packaged CN apps (v0.9.95u incident:
# the WS reader looked dead because none of its lines could land).
from utils.logger_helper import logger_helper as logger

__all__ = ["before_prompt_build_hook", "register"]


# ==================== Module-level dispatch state ====================
# All state here is keyed per-node or per-customer and persists across
# invocations of this hook.  Previously lived at build_node module scope.

# Round-robin index per node_name — module-level so it persists across
# invocations (a single node_name → one rotating pointer).
_auto_dispatch_rr_index: dict[str, int] = {}

# Affinity table: customer_id → (agent_id, ts).  Persists across
# invocations so a returning customer is routed to the same agent
# that handled them before.  TTL expires entries after
# ``affinity_ttl_s`` (default 1800s, authored in autoDispatch config).
_auto_dispatch_affinity: dict[str, tuple[str, float]] = {}

# ── Identity-key dispatch dedup ───────────────────────────────────
# Tracks identity_key → dispatched_at.  identity_key is the DOM's own
# stable key (e.g. ``"sc|有绿色款吗？"`` = ``<customer>|<message preview>``).
# When the customer sends a new message the key changes; when the
# agent replies, the key disappears from the DOM snapshot and the
# hook prunes it — so a subsequent identical question by the same
# customer re-fires naturally.  The safety TTL below is only
# garbage-collection for stranded entries; it is NOT part of the
# dedup decision.
_dispatched_identity_keys: dict[str, float] = {}
_DISPATCHED_IDENTITY_SAFETY_TTL_S = 3600.0


def clear_dispatched_identity_keys_for_customer(customer_id: str) -> int:
    """Remove every dispatched-identity-key entry whose prefix matches
    *customer_id*.  Used by mt046A: when direct-delivery drops a reply
    via ``stale_reply_source_msg_id``, the original dispatch's
    ``identity_key`` ledger entry was never invalidated — so subsequent
    EventMonitor ticks filter the customer out as ``already_dispatched``
    even though the reply never landed.  Calling this from the
    ``direct_stale_dropped`` branch lets the next tick re-dispatch.

    identity_key format is ``"{customer_name}|{message_text}"`` (set by
    EventMonitor's JS extraction).  We match the leading ``customer_id|``
    so all stamped variants for that customer get cleared in one shot.

    Returns the number of entries removed.
    """
    if not customer_id:
        return 0
    prefix = f"{customer_id}|"
    to_clear = [k for k in _dispatched_identity_keys if k.startswith(prefix)]
    for k in to_clear:
        _dispatched_identity_keys.pop(k, None)
    return len(to_clear)

# Short hard cooldown (seconds) after HOT-PATH-B delivery.
# Suppresses the immediate burst of DOM-echo events right after delivery.
_auto_dispatch_cooldown: dict[str, float] = {}
_AUTO_DISPATCH_COOLDOWN_S = 10.0


# 2026-05-27 mt050E — per-customer ring buffer of recent message
# previews.  Injected into every auto-dispatch payload as
# ``customer_recent_messages`` so any Q&A worker that picks up the
# turn (even one that didn't see the prior turn due to a sticky-routing
# race) can still see the customer's burst context.
#
# Live trace 2026-05-27 12:25:08-12: customer 肽斯特 sent a product
# card at 12:25:08, then text "绿色有货吗" at 12:25:10.  Two
# dom_observed events → two separate dispatches:
#   - card → agent_105be2342fd34cf3
#   - "绿色有货吗" → agent_62de75873cb84d2f  (different agent!)
# Second agent had no idea about the card, replied "可以发下具体是
# 哪款产品吗？" asking the customer for a link they had just sent.
#
# Sticky-affinity SHOULD have routed both to the same agent but lost
# the race (affinity stamp from event A hadn't propagated by the time
# event B's _pick_agent ran).  Rather than fix the race (hard), we
# carry the prior 2 customer message previews along on every payload
# so the receiving agent has cross-turn context regardless of routing.
_customer_recent_messages: dict[str, list[tuple[float, str]]] = {}
_RECENT_MESSAGES_MAX = 5       # ws047: last N customer messages to forward
                               # (3→5: live 1v5 bursts ran 4-5 rapid follow-ups
                               # like "这件呢"/"适合夏天吗" that reference earlier
                               # turns; this field is the cross-turn fallback for
                               # sticky-routing races, so it should cover a whole
                               # burst. Each msg is ≤200 chars, so the prompt bump
                               # is ~1KB — well clear of the MCP-result/task_text
                               # bloat that caused the earlier token blowup.)
_RECENT_MESSAGES_TTL_S = 600   # 10 min — drop stale entries on GC
_CARD_PREFIX = "[商品"          # product-card latest_message marker ("[商品卡片] …")
# ws094: a shared product card sets the conversation's product context for a while, but the
# ring buffer caps at _RECENT_MESSAGES_MAX and TTLs at 600s — so after a handful of follow-ups
# (or ~10min) the card ages out and a later "就这款"/"这件…" reaches the LLM with NO product
# (2026-06-19: sc's 女童套装 card aged out by BOTH the cap AND the 600s TTL at 663s → the LLM
# replied "麻烦发下这款的商品链接或图片"). Pin the LAST card per identity with a longer TTL so it
# stays a durable product anchor. Gated ECAN_FEIGE_CARD_RESHARE (=0 disables).
_pinned_card: dict[str, tuple[float, str]] = {}
_PINNED_CARD_TTL_S = 1800      # 30 min — product context outlives the 600s message TTL


def _append_recent_message(customer_id: str, text: str) -> None:
    """Append a customer message preview to the ring buffer.  Caps at
    ``_RECENT_MESSAGES_MAX``.  Truncates each text to 200 chars to
    keep the payload size bounded (cards can be 100+ chars on their own)."""
    if not customer_id:
        return
    txt = str(text or "").strip()
    if not txt:
        return
    if len(txt) > 200:
        txt = txt[:200] + "…"
    now = time.time()
    buf = _customer_recent_messages.setdefault(customer_id, [])
    # Avoid storing exact duplicates back-to-back — the same dom_observed
    # event sometimes fires twice within ms during DOM reshuffles.
    if buf and buf[-1][1] == txt:
        buf[-1] = (now, txt)
    else:
        buf.append((now, txt))
    # Trim to last N.
    if len(buf) > _RECENT_MESSAGES_MAX:
        del buf[: len(buf) - _RECENT_MESSAGES_MAX]
    # ws094: pin the most-recent product card so it survives the cap + the short TTL.
    # ws105: but do NOT clobber a richer pin (one carrying 价格/券/发货, set by
    # pin_card_detail) with a bare card title — the bare WS card text would erase the
    # ws101-enriched detail and break the coupon follow-up answer.
    if txt.startswith(_CARD_PREFIX):
        _existing = _pinned_card.get(customer_id)
        if not (_existing and _card_text_has_detail(_existing[1]) and not _card_text_has_detail(txt)):
            _pinned_card[customer_id] = (now, txt)


# ws187: parallel ring buffer of OUR OWN recent replies per customer. The Q&A
# LLM's history is wiped every inbound turn (anti-crosstalk, build_node
# _reset_qa_history_on_customer_change) and customer_recent_messages carries
# only the CUSTOMER side — so the model never knew what it already answered
# and could not stay consistent across turns ("你刚说的那个券怎么领"). Fed from
# dispatch_state.remember_agent_reply (the single chokepoint every real reply
# passes, placeholders excluded), injected into the dispatch payload as
# ``recent_agent_replies`` by mt050J. Per-customer-scoped in the payload, so it
# cannot revive the 2026-04-27 shared-history cross-talk. Kill:
# ECAN_FEIGE_AGENT_REPLY_CONTEXT=0.
_agent_recent_replies: dict[str, list[tuple[float, str]]] = {}
_AGENT_REPLIES_MAX = 3
_AGENT_REPLY_TRUNC = 300       # replies run longer than customer messages
_AGENT_REPLIES_TTL_S = 600     # match the customer-buffer window


def note_agent_reply(customer_id: str, text: str) -> None:
    """ws187: record one of our delivered/typed replies for *customer_id*."""
    if os.environ.get("ECAN_FEIGE_AGENT_REPLY_CONTEXT", "1") == "0":
        return
    cid = str(customer_id or "").strip()
    txt = str(text or "").strip()
    if not cid or not txt:
        return
    if len(txt) > _AGENT_REPLY_TRUNC:
        txt = txt[:_AGENT_REPLY_TRUNC] + "…"
    now = time.time()
    buf = _agent_recent_replies.setdefault(cid, [])
    if buf and buf[-1][1] == txt:
        buf[-1] = (now, txt)
    else:
        buf.append((now, txt))
    if len(buf) > _AGENT_REPLIES_MAX:
        del buf[: len(buf) - _AGENT_REPLIES_MAX]


def get_recent_agent_replies(customer_id: str) -> list[str]:
    """ws187: TTL-fresh recent replies for *customer_id*, oldest first."""
    if os.environ.get("ECAN_FEIGE_AGENT_REPLY_CONTEXT", "1") == "0":
        return []
    cid = str(customer_id or "").strip()
    buf = _agent_recent_replies.get(cid)
    if not buf:
        return []
    cutoff = time.time() - _AGENT_REPLIES_TTL_S
    fresh = [(ts, txt) for (ts, txt) in buf if ts >= cutoff]
    if len(fresh) != len(buf):
        if fresh:
            _agent_recent_replies[cid] = fresh
        else:
            _agent_recent_replies.pop(cid, None)
    return [txt for (_ts, txt) in fresh]


_CARD_DETAIL_MARKERS = ("￥", "¥", "券", "发货")


def _card_text_has_detail(text: str) -> bool:
    return any(m in (text or "") for m in _CARD_DETAIL_MARKERS)


def pin_card_detail(identity_keys: list[str], rich_text: str) -> None:
    """ws105: pin the ENRICHED product-card text (carrying 价格/券/发货) under each
    given identity so a later TEXT follow-up — which never goes through the card
    enrichment path — still carries the product detail via ``_get_recent_messages``.
    Authoritative: overwrites any existing (possibly bare) pin for these keys."""
    txt = str(rich_text or "").strip()
    if not txt:
        return
    now = time.time()
    for k in identity_keys:
        k = str(k or "").strip()
        if k:
            _pinned_card[k] = (now, txt)


def _prune_buffer(customer_id: str) -> list[tuple[float, str]]:
    """Return the TTL-fresh ``(ts, txt)`` entries for *customer_id*, pruning
    stale ones in place.  Empty list when none."""
    buf = _customer_recent_messages.get(customer_id)
    if not buf:
        return []
    cutoff = time.time() - _RECENT_MESSAGES_TTL_S
    fresh = [(ts, txt) for (ts, txt) in buf if ts >= cutoff]
    if len(fresh) != len(buf):
        if fresh:
            _customer_recent_messages[customer_id] = fresh
        else:
            _customer_recent_messages.pop(customer_id, None)
    return fresh


def _get_recent_messages(customer_id: str) -> list[str]:
    """Return the recent message texts for *customer_id*, oldest first.

    ws046: also bridges in the customer's PRODUCT CARD context.  A name-less
    product card is dispatched under the synthetic ``card:<talk_id>`` identity
    (cards carry no nickname), so its text lands in a SEPARATE ring buffer from
    the customer's named text questions.  Without this merge, a follow-up like
    "这件适合夏天穿吗" reaches the Q&A worker with the card title absent → the LLM
    answers a 秋冬加厚 jacket as summer-appropriate (live 2026-06-11, cust 'packet').
    We resolve the customer's talk_id via ws_session and fold the ``card:<talk_id>``
    buffer in (oldest-first, card before text since it arrived first).  Pure
    in-memory dict reads — no CDP/LLM/DOM, no hot-path timing impact.

    Lazily prunes entries older than ``_RECENT_MESSAGES_TTL_S``."""
    if not customer_id:
        return []
    merged: list[tuple[float, str]] = list(_prune_buffer(customer_id))
    # Bridge the synthetic card buffer for this customer's conversation, unless
    # we ARE the card identity (avoid self-merge / recursion).
    _talk = ""
    if not str(customer_id).startswith("card:"):
        try:
            from . import ws_session as _ws_session
            _talk = _ws_session.talk_for_name(str(customer_id))
        except Exception:
            _talk = ""
        if _talk:
            card_buf = _prune_buffer(f"card:{_talk}")
            if card_buf:
                _seen = {txt for (_ts, txt) in merged}
                merged.extend(
                    (ts, txt) for (ts, txt) in card_buf if txt not in _seen
                )
    # ws094: fold in the PINNED last card (survives the ring cap + the 600s TTL) so a later
    # follow-up like "就这款" always carries product context. Check this identity AND the
    # bridged card:<talk> identity. Gated ECAN_FEIGE_CARD_RESHARE (=0 disables).
    if os.environ.get("ECAN_FEIGE_CARD_RESHARE", "1") != "0":
        _pin_now = time.time()
        _pin_seen = {txt for (_ts, txt) in merged}
        for _pk in ([str(customer_id)] + ([f"card:{_talk}"] if _talk else [])):
            _pc = _pinned_card.get(_pk)
            if _pc and (_pin_now - _pc[0]) < _PINNED_CARD_TTL_S and _pc[1] not in _pin_seen:
                merged.append(_pc)
                _pin_seen.add(_pc[1])
    if not merged:
        return []
    # ws047: bound the merged size. A flat "keep last N" would drop the CARD —
    # it's the OLDEST entry — defeating the bridge above. So keep the most-recent
    # card as the durable product anchor + the most-recent N text messages.
    if len(merged) > _RECENT_MESSAGES_MAX:
        merged.sort(key=lambda e: e[0])
        _cards = [e for e in merged if str(e[1]).startswith(_CARD_PREFIX)]
        _texts = [e for e in merged if not str(e[1]).startswith(_CARD_PREFIX)]
        merged = _cards[-1:] + _texts[-_RECENT_MESSAGES_MAX:]
    merged.sort(key=lambda e: e[0])  # oldest-first; card precedes later text
    return [txt for (_ts, txt) in merged]


# ==================== Helpers ====================

def _truthy_config_value(value: Any) -> bool:
    """Return True for common bool-ish config values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return False


def _read_jsonish_input(inputs: dict, key: str, parser=None) -> Any:
    """Read a Flowgram-style JSON input using the runtime parser when available."""
    if callable(parser):
        try:
            parsed = parser(inputs, key)
            if parsed is not None:
                if not (
                    isinstance(parsed, dict)
                    and set(parsed.keys()) == {"content"}
                ):
                    return parsed
                raw = parsed.get("content")
                if raw in (None, ""):
                    return None
                if isinstance(raw, (dict, list)):
                    return raw
                if isinstance(raw, str):
                    try:
                        return json.loads(raw.strip())
                    except Exception:
                        return None
                return None
        except Exception:
            pass
    raw = (inputs.get(key) or {}).get("content") if isinstance(inputs, dict) else None
    if raw in (None, ""):
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw.strip())
        except Exception:
            return None
    return None


def _pre_dispatch_enabled_for_browser_event(inputs: dict, parser, evt_type: str) -> bool:
    if evt_type != "browser_event":
        return False
    cfg = _read_jsonish_input(inputs, "preDispatch", parser)
    return isinstance(cfg, dict) and _truthy_config_value(cfg.get("enabled"))


def _auto_dispatch_allows_pre_dispatch(auto_dispatch_cfg: dict | None) -> bool:
    """Explicit escape hatch for legacy configs that still want both paths."""
    if not isinstance(auto_dispatch_cfg, dict):
        return False
    for key in ("allow_with_preDispatch", "allow_with_pre_dispatch", "allowWithPreDispatch"):
        if _truthy_config_value(auto_dispatch_cfg.get(key)):
            return True
    dispatch_cfg = auto_dispatch_cfg.get("dispatch")
    if isinstance(dispatch_cfg, dict):
        for key in ("allow_with_preDispatch", "allow_with_pre_dispatch", "allowWithPreDispatch"):
            if _truthy_config_value(dispatch_cfg.get(key)):
                return True
    return False


def _build_pre_dispatch_guard_state(item_count: int) -> dict:
    return {
        "result": {
            "llm_result": {
                "all_done": True,
                "work_done": False,
                "hot_path": True,
                "hot_path_type": "predispatch_guard",
                "message": (
                    "preDispatch is enabled; suppressing autoDispatch/LLM "
                    f"fallback for browser_event ({item_count} actionable item(s))."
                ),
            }
        }
    }


def _pre_dispatch_suppresses_prompt_auto_dispatch(
    *,
    inputs: dict,
    parser,
    evt_type: str,
    auto_dispatch_cfg: dict | None,
) -> bool:
    """Whether prompt-build autoDispatch should defer to late PreDispatch.

    The before-prompt hook runs before the browser session is fully prepared
    and before the late ``front_desk`` PreDispatch hook.  Returning a
    short-circuit guard here prevents PreDispatch from ever running, which
    can swallow live-site browser events.  Treat this as an autoDispatch-only
    suppression flag instead: late PreDispatch gets first shot, and if it
    returns ``None`` the injected actionable-items prompt remains as fallback.
    """
    return (
        _pre_dispatch_enabled_for_browser_event(inputs, parser, evt_type)
        and not _auto_dispatch_allows_pre_dispatch(auto_dispatch_cfg)
    )


def _get_agent_load(agent_id: str, mainwin) -> int:
    """Return the number of non-done tasks queued for *agent_id*.

    This lets load-aware strategies favour agents with shorter queues.
    Returns 0 if the agent's runner is not accessible (safe default).
    """
    try:
        for agent in (mainwin.agents or []):
            card = getattr(agent, "card", None)
            if card and getattr(card, "id", "") == agent_id:
                runner = getattr(agent, "runner", None)
                if runner:
                    return sum(
                        1 for st in runner._task_states.values()
                        if not st.get("_done", False)
                    )
                return 0
        return 0
    except Exception:
        return 0


# ─── ws055: stuck-conversation recovery ──────────────────────────────────
# A sidebar row showing Feige's platform stall banner ("当前会话已长时间未回复…",
# system_message_filter reason ``platform_long_no_reply``) with NO unread_badge is a
# conversation the bot orphaned — e.g. it arrived while the app was restarting (live
# 2026-06-13: the 12:32 product card landed in the ws052→ws054 restart gap, was never
# detected, and stuck forever with an empty badge). The actionable gate normally drops
# every system-message row, so these never reach PreDispatch's thread-scrape recovery.
#
# When enabled, we instead stamp a synthetic unread_badge on such a row so it looks
# "pending" and flows into the EXISTING PreDispatch recovery (scrape_latest_customer_bubble
# rebuilds the real customer bubble; the downstream strict msg-id dedup prevents a
# double-answer if it was already handled). Rate-limited per customer so a genuinely
# answered-but-still-bannered row doesn't re-scrape every cycle. Gated, default OFF.
_STUCK_RECOVERY_TTL_S = float(os.environ.get("ECAN_FEIGE_STUCK_RECOVERY_TTL", "120") or 120)
_stuck_recovery_last: dict[str, float] = {}


def _stuck_recovery_enabled() -> bool:
    return os.environ.get("ECAN_FEIGE_STUCK_RECOVERY", "") == "1"


def _row_has_unread_badge(item: dict) -> bool:
    try:
        return int(str(item.get("unread_badge", "") or "0").strip() or "0") >= 1
    except Exception:
        return False


def _stuck_recovery_due(cust: str, now: float | None) -> bool:
    """Rate-limit recovery attempts per customer to the TTL window."""
    if not cust:
        return False
    n = now if now is not None else time.time()
    if n - _stuck_recovery_last.get(cust, 0.0) < _STUCK_RECOVERY_TTL_S:
        return False
    _stuck_recovery_last[cust] = n
    return True


def _evaluate_item_filter(
    item: dict,
    filter_cfg: dict | None,
    *,
    resolved: dict | None = None,
    customer_id: str | None = None,
    inflight_check=None,
    now: float | None = None,
) -> tuple[bool, str]:
    """Check an actionable item against a data-driven filter config.

    Returns ``(keep, reason)``. ``reason`` is "" when keeping, otherwise a
    short tag like ``"required_field_missing:customer_name"`` or
    ``"exclude:customer_name:equals:您好"``.

    Config schema (all keys optional)::

        {
          "required_fields": ["customer_name", ...],
          "exclude_patterns": [
            {"field": "customer_name", "equals": "您好"},
            {"field": "customer_name", "contains": "通知"},
            {"field": "customer_name", "prefix": "系统"},
            {"field": "customer_name", "regex": "^店铺"}
          ],
          "exclude_self_echo": {"enabled": true},
          "inflight": {
            "enabled": true,
            "allow_new_message": true,
            "message_fields": ["last_message", "latest_message"]
          },
          "cooldown": {"enabled": true, "window_s": 10}
        }

    The three stateful checks (self_echo, inflight, cooldown) each require
    different item data. ``exclude_self_echo`` reads the DOM's
    ``identity_key`` and checks :data:`_dispatched_identity_keys` — no TTL.
    ``cooldown`` reads :data:`_auto_dispatch_cooldown` by customer_id.
    ``inflight`` is evaluated via a caller-supplied
    ``inflight_check(customer_id) -> age`` callback so this helper stays
    free of browser-extension imports.
    """
    import re as _re
    if now is None:
        now = time.time()
    cfg = filter_cfg or {}
    resolved = resolved or {}

    system_reason = first_system_row_match(item, resolved)
    if system_reason:
        # ws055/ws152: don't just DROP a badge-less system-looking row that is actually a
        # cold-start REOPEN signal — recover it so the 250ms EventMonitor catches it NOW instead
        # of waiting ~5s for the ws108 backstop (the eCan-side half of the ~35s cold-start
        # detection lag; live 2026-07-07 22:45: the reopen's 客服…接入 row was dropped here every
        # 250ms cycle and only the 5s backstop picked it up). The real customer message lives in
        # the THREAD, not the sidebar preview (which shows the system line), so a synthetic badge
        # routes the row into the EXISTING PreDispatch scrape-recovery (scrape_latest_customer_bubble
        # rebuilds the real bubble; strict msg-id dedup downstream prevents a double-answer).
        # Rate-limited per customer (TTL). Signals:
        #   platform_long_no_reply  = 长时间未回复 stall banner (ws055, gate ECAN_FEIGE_STUCK_RECOVERY)
        #   store_assignment_notice = 客服…接入 / 小店为你服务 connect banner (ws152, reopen/new conv)
        #   session_close_notice    = 关闭会话 close notice               (ws152, close→reopen)
        if not _row_has_unread_badge(item):
            _reopen_recover = (
                os.environ.get("ECAN_FEIGE_REOPEN_RECOVERY", "1") != "0"
                and (
                    "store_assignment_notice" in system_reason
                    or "session_close_notice" in system_reason
                )
            )
            _stall_recover = (
                _stuck_recovery_enabled()
                and "platform_long_no_reply" in system_reason
            )
            if _reopen_recover or _stall_recover:
                _cust = customer_id or str(
                    item.get("customer_name") or item.get("customer_id") or ""
                ).strip()
                if _stuck_recovery_due(_cust, now):
                    item["unread_badge"] = "1"  # synthetic pending marker → PreDispatch scrape recovery
                    _tag = "ws152 reopen" if _reopen_recover else "ws055 stall"
                    logger.info(
                        f"[actionable] {_tag}-recovery: re-activating badge-less "
                        f"{system_reason} row cust={_cust!r} → thread-scrape recovery "
                        f"(catches the reopen on the 250ms monitor, not the 5s backstop)"
                    )
                    return True, ("reopen_recovery" if _reopen_recover else "stuck_recovery")
        return False, system_reason

    # 1. Required fields — must resolve to non-empty in resolved or item.
    for rf in (cfg.get("required_fields") or []):
        v = resolved.get(rf) or str(item.get(rf, "") or "").strip()
        if not v:
            return False, f"required_field_missing:{rf}"

    # 2. Exclude patterns — drop on first match.
    for pat in (cfg.get("exclude_patterns") or []):
        if not isinstance(pat, dict):
            continue
        field = pat.get("field")
        if not field:
            continue
        val = str(resolved.get(field) or item.get(field, "") or "").strip()
        if not val:
            continue
        for op in ("equals", "contains", "prefix", "regex"):
            if op not in pat:
                continue
            literal = str(pat[op])
            try:
                if op == "equals":
                    matched = (val == literal)
                elif op == "contains":
                    matched = (literal in val)
                elif op == "prefix":
                    matched = val.startswith(literal)
                else:  # regex
                    matched = bool(_re.search(literal, val))
            except Exception:
                matched = False
            if matched:
                return False, f"exclude:{field}:{op}:{literal[:30]}"

    se_cfg = cfg.get("exclude_self_echo") or {}
    il_cfg = cfg.get("inflight") or {}
    cd_cfg = cfg.get("cooldown") or {}
    # msg_text powers inflight's allow_new_message gate.
    msg_fields = il_cfg.get("message_fields") or ["last_message", "latest_message"]
    msg_text = ""
    for mf in msg_fields:
        v = resolved.get(mf) or item.get(mf) or ""
        if isinstance(v, str) and v.strip():
            msg_text = v.strip()[:80]
            break

    cust_id = customer_id or ""

    # 3. Identity-key dedup — skip items whose DOM identity_key has already
    #    been dispatched.  When the customer sends a new message, identity_key
    #    changes; when the agent replies, the old identity_key disappears
    #    from the DOM snapshot and the caller prunes our record of it.  So an
    #    identical repeat question by the same customer re-fires naturally.
    if se_cfg.get("enabled"):
        ident = str(item.get("identity_key") or "").strip()
        if ident and ident in _dispatched_identity_keys:
            logger.info(
                f"[filter] identity_key dedup: cust={cust_id!r}, "
                f"identity_key={ident!r}, "
                f"age={now - _dispatched_identity_keys[ident]:.1f}s"
            )
            return False, "already_dispatched"

    # 4. In-flight — suppress items whose customer already has a dispatch
    #    in flight, unless allow_new_message is set and there is new text.
    if il_cfg.get("enabled") and cust_id and inflight_check:
        try:
            age = float(inflight_check(cust_id) or 0.0)
        except Exception:
            age = 0.0
        if age > 0.0:
            if il_cfg.get("allow_new_message", True) and msg_text:
                pass  # new user message; let it through
            else:
                return False, f"inflight:{age:.0f}s"

    # 5. Cooldown — short hard window after HOT-PATH-B delivery.
    if cd_cfg.get("enabled") and cust_id:
        window = float(cd_cfg.get("window_s") or _AUTO_DISPATCH_COOLDOWN_S)
        cd_ts = _auto_dispatch_cooldown.get(cust_id, 0.0)
        if cd_ts and (now - cd_ts) < window:
            return False, f"cooldown:{now - cd_ts:.0f}s"

    return True, ""


async def _try_auto_dispatch(
    config: dict,
    actionable: list,
    all_agents: list,
    caller_id: str,
    mainwin: object,
    node_name: str,
    evt_type: str,
) -> dict | None:
    """Attempt configurable auto-dispatch of actionable items to agents.

    Returns a ``state`` dict (with ``hot_path_type: "auto_dispatch"``) if at
    least one item was dispatched, otherwise ``None`` so the caller falls
    through to the LLM.

    *config* schema::

        {
          "trigger": {"event_type": "browser_event", "require_actionable": true},
          "agent_selection": {
            "strategy": "round_robin",
            "filter_by_tasks": ["客户应答"],
            "affinity_ttl_s": 1800
          },
          "payload_template": {"key": "{{field || fallback}}"},
          "item_filter": {"required_fields": ["field1", "field2"]},
          "dispatch": {"tool": "send_chat", "dedup": true, "per_item": true}
        }

    Agent selection strategies
    --------------------------
    ``first_available``
        Pick the candidate with the fewest pending tasks (load-aware).
        Ties broken by list order.

    ``round_robin``
        Rotate through candidates.  With ``per_item: true`` each actionable
        item advances the index, spreading items across agents evenly.

    Affinity / sticky routing
    -------------------------
    Before any strategy runs, the dispatcher checks whether the customer
    (derived from the resolved ``customer_id`` or ``customer_name``) was
    previously assigned to one of the current candidates.  If so — and the
    assignment is fresher than ``affinity_ttl_s`` (default 30 min) — the
    same agent is reused.  This keeps an ongoing conversation on one agent.
    """
    # ── 1. Trigger check ──
    trigger = config.get("trigger") or {}
    required_evt = trigger.get("event_type", "")
    if required_evt and required_evt != evt_type:
        return None
    if trigger.get("require_actionable", True) and not actionable:
        return None

    # ── 2. Build candidate pool ──
    sel = config.get("agent_selection") or {}
    strategy = sel.get("strategy", "first_available")
    filter_tasks = sel.get("filter_by_tasks") or []
    affinity_ttl = float(sel.get("affinity_ttl_s", 1800))

    # Exclude disabled agents — they never launch tasks.
    candidates = [
        a for a in all_agents
        if a.get("status", "active") != "disabled"
    ]
    if filter_tasks:
        _filter_patterns = [str(p) for p in filter_tasks if str(p).strip()]

        def _agent_task_matches(agent_entry: dict) -> bool:
            _tasks = [str(t) for t in (agent_entry.get("tasks") or [])]
            for _pat in _filter_patterns:
                for _t in _tasks:
                    if _pat in _t:
                        return True
            return False

        candidates = [a for a in candidates if _agent_task_matches(a)]
    if not candidates:
        logger.info(
            f"[AUTO-DISPATCH] No candidate agents after filter "
            f"(filter_by_tasks={filter_tasks}, all_agent_tasks="
            f"{[a.get('tasks', []) for a in all_agents]}), node={node_name}"
        )
        return None

    candidate_ids = {a["id"] for a in candidates}

    # ── 3. Payload template & item filter ──
    payload_tpl = config.get("payload_template") or {}
    if not payload_tpl:
        # Default: emit a canonical {customer_id, customer_name, latest_message}
        # payload so downstream responders always have usable data even when
        # the author didn't specify a template.  Field fallbacks cover the
        # common DOM-extractor shapes (customer_name + last_message).
        payload_tpl = {
            "customer_id": "{{customer_id || identity_key || customer_name}}",
            "customer_name": "{{customer_name || name}}",
            "latest_message": "{{latest_message || last_message || message}}",
        }
    # Hot-path-A hardcodes self-echo + cooldown because they guard the
    # HOT-PATH-B delivery burst; callers can still override message_fields
    # / ttl / window via the authored item_filter.
    _user_filter = dict(config.get("item_filter") or {})
    _user_filter.setdefault("exclude_self_echo", {"enabled": True})
    _user_filter.setdefault("cooldown", {
        "enabled": True,
        "window_s": _AUTO_DISPATCH_COOLDOWN_S,
    })
    item_filter_cfg = _user_filter
    dispatch_cfg = config.get("dispatch") or {}
    use_dedup = dispatch_cfg.get("dedup", True)

    from agent.mcp.server.chat_utils.chat_tools import send_chat as _auto_send_chat

    # ── 4. Agent-picker with affinity → strategy fallback ──
    _rr_idx = _auto_dispatch_rr_index.get(node_name, 0)
    now = time.time()

    # Lazy-load per-agent load counts (computed once per dispatch batch).
    _load_cache: dict[str, int] = {}

    def _agent_load(aid: str) -> int:
        if aid not in _load_cache:
            _load_cache[aid] = _get_agent_load(aid, mainwin)
        return _load_cache[aid]

    def _pick_agent(customer_id: str) -> dict:
        nonlocal _rr_idx

        # ── Affinity check: reuse previous agent if still valid ──
        if customer_id:
            entry = _auto_dispatch_affinity.get(customer_id)
            if entry:
                prev_agent_id, ts = entry
                if (now - ts) < affinity_ttl and prev_agent_id in candidate_ids:
                    for c in candidates:
                        if c["id"] == prev_agent_id:
                            return c

        # ── Strategy fallback ──
        if strategy == "round_robin":
            agent = candidates[_rr_idx % len(candidates)]
            _rr_idx += 1
            return agent

        # first_available: pick candidate with lowest pending-task count
        return min(candidates, key=lambda c: _agent_load(c["id"]))

    dispatched = 0
    for item in actionable:
        # Resolve template fields
        resolved = {}
        for key, tpl in payload_tpl.items():
            resolved[key] = _resolve_template(tpl, item)

        cust_id = _normalize_dispatch_identity_key(
            resolved.get("customer_id")
            or resolved.get("customer_name")
            or ""
        )

        # 2026-05-26 mt048D: skip auto-dispatch when the customer's
        # message contains a URL.  PreDispatch (mt048C) sets
        # ``_ecan_url_detected`` on items where ``find_first_url``
        # matched.  Those items must reach the front-desk LLM (which
        # runs the new "Path C — URL handling" instructions) instead of
        # being routed to a Q&A worker that has no way to fetch the
        # URL.  Without this skip, ``_ecan_frontdesk_dispatched_all``
        # would be set and ``abort_when_pre_dispatched`` would kill the
        # LangGraph run before Path C could fire.
        if str(item.get("_ecan_url_detected") or "").strip():
            logger.info(
                f"[AUTO-DISPATCH] mt048D skip URL item '{cust_id or '?'}' "
                f"url=...{str(item.get('_ecan_url_detected') or '')[-40:]} "
                f"is_product={bool(item.get('_ecan_url_is_jinritemai_product'))} "
                f"— letting front-desk LLM (Path C) handle, node={node_name}"
            )
            continue

        keep, reason = _evaluate_item_filter(
            item,
            item_filter_cfg,
            resolved=resolved,
            customer_id=cust_id,
            now=now,
        )
        if not keep:
            logger.info(
                f"[AUTO-DISPATCH] filter drop '{cust_id or '?'}' "
                f"reason={reason}, node={node_name}"
            )
            continue

        target_agent = _pick_agent(cust_id)
        target_agent_id = target_agent.get("id", "")
        target_agent_name = target_agent.get("name", target_agent_id)

        # 2026-05-27 mt050E — inject prior-message context so the
        # receiving Q&A agent has cross-turn awareness even if a
        # sticky-routing race sends bursts to different agents.  Read
        # BEFORE appending the current message so the LLM sees prior
        # context separately from latest_message (no duplication).
        _mt050e_prior = _get_recent_messages(cust_id)
        if _mt050e_prior:
            resolved["customer_recent_messages"] = _mt050e_prior

        message_str = json.dumps(resolved, ensure_ascii=False)
        send_config = {
            "sender_agent_id": caller_id,
            "recipient_agent_id": target_agent_id,
            "message": message_str,
        }

        result = _auto_send_chat(mainwin, send_config)
        if result.get("success"):
            dispatched += 1

            # mt050E — record this message in the per-customer ring
            # buffer so the NEXT burst from the same customer carries
            # this turn's preview along, regardless of which agent
            # picks up the next dispatch.
            _mt050e_text = str(
                resolved.get("latest_message")
                or resolved.get("last_message")
                or ""
            ).strip()
            if cust_id and _mt050e_text:
                _append_recent_message(cust_id, _mt050e_text)

            # Update affinity: this customer → this agent.
            if cust_id:
                _auto_dispatch_affinity[cust_id] = (target_agent_id, now)

            # Record identity_key so repeat dispatch attempts while the same
            # customer message is still in the DOM are suppressed.  The
            # caller prunes this entry when the key disappears from the
            # snapshot (customer sent a new message or agent replied), so a
            # legitimate repeat of the same question re-fires naturally.
            _ident = str(item.get("identity_key") or "").strip()
            if _ident:
                _dispatched_identity_keys[_ident] = now

            # ws191: record the talk-level claim so a later parked card:<talk>
            # dispatch for the SAME conversation is dropped instead of producing
            # a second answer. Resolve talk from the (possibly synthetic) cust_id.
            try:
                from . import dispatch_state as _ds191c, ws_session as _wss191
                _talk191 = ""
                if cust_id.startswith("card:"):
                    _talk191 = cust_id[len("card:"):]
                else:
                    _talk191 = str(_wss191.talk_for_name(cust_id) or "")
                if _talk191:
                    _ds191c.note_talk_dispatched(
                        _talk191, str(item.get("msg_id") or ""))
            except Exception:
                pass

            # Record in Fix A caches
            if use_dedup:
                try:
                    from agent.ec_skills.browser_use_extension.extension_tools_service import (
                        _send_chat_customer_last,
                        _send_chat_dedup_cache,
                    )
                    if cust_id:
                        _send_chat_customer_last[cust_id] = now
                        dedup_key = f"{target_agent_id}|{cust_id}"
                        _send_chat_dedup_cache[dedup_key] = now
                except Exception:
                    pass

            logger.info(
                f"[AUTO-DISPATCH] sent '{resolved.get('customer_name', '?')}' "
                f"→ {target_agent_name} (load={_agent_load(target_agent_id)}) "
                f"msg='{message_str[:80]}', node={node_name}"
            )
        else:
            logger.warning(
                f"[AUTO-DISPATCH] failed for item: {result.get('error', '?')}, "
                f"node={node_name}"
            )

    # Persist round-robin index across calls
    _auto_dispatch_rr_index[node_name] = _rr_idx

    # Prune stale affinity entries (older than 2× TTL)
    _stale = [k for k, (_, ts) in _auto_dispatch_affinity.items() if now - ts > affinity_ttl * 2]
    for k in _stale:
        _auto_dispatch_affinity.pop(k, None)

    # Prune stale cooldown entries
    _stale_cd = [k for k, ts in _auto_dispatch_cooldown.items() if now - ts > _AUTO_DISPATCH_COOLDOWN_S * 2]
    for k in _stale_cd:
        _auto_dispatch_cooldown.pop(k, None)
    # Safety gc for identity-key records (DOM-diff pruning is the primary path)
    _stale_ident = [k for k, ts in _dispatched_identity_keys.items() if now - ts > _DISPATCHED_IDENTITY_SAFETY_TTL_S]
    for k in _stale_ident:
        _dispatched_identity_keys.pop(k, None)

    if dispatched > 0:
        logger.info(
            f"[AUTO-DISPATCH] {dispatched}/{len(actionable)} items dispatched, "
            f"skipping LLM Phase 1, node={node_name}"
        )
        return {
            "result": {
                "llm_result": {
                    "all_done": False,
                    "work_done": False,
                    "hot_path": True,
                    "hot_path_type": "auto_dispatch",
                }
            }
        }
    return None


# ==================== Prompt-build hook ====================

async def before_prompt_build_hook(
    state: dict,
    inputs: dict,
    hook_ctx: BrowserUseHookContext,
    prompt_ctx: PromptBuildContext,
) -> PromptBuildResult | None:
    """Feige front-desk actionable-items handler.

    Activates only when the node has an ``actionable_field`` configured
    (i.e. the node author has opted into the front-desk pattern).

    Flow:

    1. Apply data-driven item filter (inflight + self_echo + cooldown
       defaults, plus any user-authored patterns) to ``actionable_raw``.
    2. Build the task-hint block (``actionable_items`` JSON + hard
       rule) and the protocol-override block (10 binding rules that
       win against conflicting system-prompt guidance).
    3. Inject pre-resolved ``agent_list`` so the LLM can skip the
       ``bu_select_agents`` tool call.
    4. If ``autoDispatch`` is authored on the node, attempt
       deterministic dispatch via :func:`_try_auto_dispatch` — if it
       dispatched all actionable items, short-circuit the LLM entirely.
    """
    actionable_field = prompt_ctx.actionable_field
    if not actionable_field:
        # Not our round — node doesn't opt into the front-desk pattern.
        return None

    compact_items = prompt_ctx.compact_items
    actionable_raw = list(prompt_ctx.actionable_raw)
    if not compact_items:
        return None

    node_name = hook_ctx.node_name
    calling_agent_id = hook_ctx.calling_agent_id
    mainwin = hook_ctx.mainwin
    evt_type = prompt_ctx.event_type

    # ── Inflight-check helper (lives in extension_tools_service) ──
    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            customer_recently_dispatched as _cust_recent,
        )
    except Exception:
        _cust_recent = lambda _c: 0.0  # noqa: E731
    _now = time.time()

    # ── Resolve user-authored filter (tolerant to missing blob) ──
    _user_filter: dict = {}
    try:
        _fa_raw = (inputs.get("autoDispatch") or {}).get("content")
        if isinstance(_fa_raw, str) and _fa_raw.strip():
            _fa_parsed = json.loads(_fa_raw)
            if isinstance(_fa_parsed, dict):
                _fif = _fa_parsed.get("item_filter")
                if isinstance(_fif, dict):
                    _user_filter = dict(_fif)
        elif isinstance(_fa_raw, dict):
            _fif = _fa_raw.get("item_filter")
            if isinstance(_fif, dict):
                _user_filter = dict(_fif)
    except Exception as _fa_err:
        logger.debug(
            f"[BrowserAutomation] actionable_items: could not parse "
            f"autoDispatch.item_filter ({_fa_err}); using defaults"
        )

    _user_filter.setdefault("inflight", {
        "enabled": True,
        "allow_new_message": True,
        "message_fields": ["last_message", "latest_message"],
    })
    _user_filter.setdefault("exclude_self_echo", {"enabled": True})
    _user_filter.setdefault("cooldown", {
        "enabled": True,
        "window_s": _AUTO_DISPATCH_COOLDOWN_S,
    })

    # ── Prune identity_key records for entries no longer in the
    #    DOM snapshot — the customer either sent a new message
    #    (key changed) or the agent replied (key disappeared).
    #    Keeps the dedup set aligned with live state so an identical
    #    earlier question is not silently suppressed forever.
    _live_ident_keys = {
        str(_it.get("identity_key") or "").strip()
        for _it in compact_items
        if _it.get("identity_key")
    }
    _stale_live = [
        _k for _k in _dispatched_identity_keys
        if _k and _k not in _live_ident_keys
    ]
    for _k in _stale_live:
        _dispatched_identity_keys.pop(_k, None)

    # ── Apply filter to actionable_raw ──
    _actionable = []
    _filtered_out: list[tuple[str, str]] = []
    for _it in actionable_raw:
        _cust_id = _normalize_dispatch_identity_key(
            _it.get("customer_id")
            or _it.get("customer_name")
            or _it.get("name")
            or ""
        )
        _keep, _reason = _evaluate_item_filter(
            _it,
            _user_filter,
            customer_id=_cust_id,
            inflight_check=_cust_recent,
            now=_now,
        )
        if _keep:
            _actionable.append(_it)
        else:
            _filtered_out.append((_cust_id or "?", _reason))
    if _filtered_out:
        logger.info(
            f"[BrowserAutomation] actionable_items: filtered "
            f"{len(_filtered_out)} entry/entries "
            f"(kept {len(_actionable)} of {len(actionable_raw)}): "
            + ", ".join(f"{c}({r})" for c, r in _filtered_out)
            + f" node={node_name}"
        )

    _auto_dispatch_guard_cfg = _read_jsonish_input(
        inputs,
        "autoDispatch",
        getattr(hook_ctx, "parse_json_input", None),
    )
    _pre_dispatch_blocks_prompt_auto = _pre_dispatch_suppresses_prompt_auto_dispatch(
        inputs=inputs,
        parser=getattr(hook_ctx, "parse_json_input", None),
        evt_type=evt_type,
        auto_dispatch_cfg=_auto_dispatch_guard_cfg,
    )
    if _pre_dispatch_blocks_prompt_auto:
        try:
            state["_ecan_predispatch_actionable_items"] = [
                dict(_it) for _it in _actionable if isinstance(_it, dict)
            ]
            state["_ecan_predispatch_actionable_items_ts"] = time.time()
        except Exception:
            pass
        logger.info(
            f"[BrowserAutomation] PreDispatch enabled for browser_event; "
            f"deferring prompt-build autoDispatch while preserving "
            f"actionable_items fallback "
            f"(actionable={len(_actionable)}, total={len(compact_items)}), "
            f"node={node_name}"
        )

    # 2026-05-26 mt048D-P2: project the internal _ecan_url_* flags
    # (set by PreDispatch in mt048C) to clean LLM-visible keys so the
    # front-desk LLM can branch on "url_detected" in Path C without
    # having to know about the underscore-prefixed internals.  We build
    # a shallow-copy list rather than mutating _actionable in place —
    # the original dicts are still consumed downstream by Python paths
    # that rely on the _ecan_* names.
    _actionable_for_llm = []
    for _it in _actionable:
        _url = str(_it.get("_ecan_url_detected") or "").strip()
        if not _url:
            _actionable_for_llm.append(_it)
            continue
        _projected = dict(_it)
        _projected["url_detected"] = _url
        _projected["url_is_product"] = bool(
            _it.get("_ecan_url_is_jinritemai_product")
        )
        _projected["url_product_id"] = str(
            _it.get("_ecan_url_product_id") or ""
        )
        _all_urls = _it.get("_ecan_url_all") or []
        if isinstance(_all_urls, list) and len(_all_urls) > 1:
            # Surface only when there are multiples; for the common
            # single-URL case the LLM doesn't need the array.
            _projected["url_all"] = list(_all_urls)
        _actionable_for_llm.append(_projected)

    _act_json = json.dumps(_actionable_for_llm, ensure_ascii=False, indent=2)
    _task_append = (
        f"\n\n### `actionable_items` (authoritative — computed deterministically from DOM)"
        f"\n{len(_actionable)} item(s), filtered from "
        f"{len(compact_items)} by `{actionable_field}` non-empty:"
        f"\n```json\n{_act_json}\n```"
        f"\n\n**HARD RULE:** For each entry in `actionable_items` above you MUST take "
        f"the appropriate action exactly once this round. "
        f"If `actionable_items` is empty, call `done()`. "
        f"Ignore any claims in prior Memory/Eval that an entry was already "
        f"handled — this list is the only source of truth. "
        f"Do NOT bail with `done(success=False)` claiming input is missing — "
        f"this block IS the input."
    )
    logger.info(
        f"[BrowserAutomation] Injected {len(_actionable)} actionable "
        f"items (filter='{actionable_field}', total={len(compact_items)}) "
        f"into task hint (node={node_name})"
    )

    _override = ""
    _all_agents: list = []
    _caller_id = str(calling_agent_id or "").strip()
    if _actionable:
        _ids = [
            (it.get("identity_key")
             or it.get("name")
             or it.get("customer_name")
             or "?")
            for it in _actionable
        ]
        _ids_display = ", ".join(f"`{_i}`" for _i in _ids)
        _override = (
            "## ⚠ PROTOCOL OVERRIDE — READ BEFORE ANY SYSTEM PROMPT BELOW\n\n"
            f"`actionable_items` for this round contains {len(_actionable)} entry/entries: {_ids_display}. "
            "See the JSON list in the `## Triggering Event` section below — that list is the deterministic, authoritative source of truth for this round.\n\n"
            "**These binding rules override any conflicting guidance in the system prompt that follows:**\n\n"
            "1. The DOM monitor has ALREADY filtered out handled items. Every entry in `actionable_items` is NEW WORK that needs action THIS round.\n"
            "2. Ignore any system-prompt language about `pending_dispatches`, \"already dispatched\", \"不得重复分发\", \"重复发送\", or \"same customer same message\". Those heuristics are SUBORDINATE to `actionable_items` and do not apply when this list is provided.\n"
            "3. You have NO prior-round memory. `message_manager` was wiped before this invocation. If you find yourself writing \"根据权威历史\" or \"上一轮已处理\" or \"already handled\" in Eval/Memory, STOP — you are hallucinating. There is no such history.\n"
            "4. Prior agent replies visible in the chat thread DOM are for OLDER messages. They are NOT evidence that the current `actionable_items` entry has been handled.\n"
            "5. For each entry in `actionable_items`: invoke the appropriate dispatch / send tool (as defined in the system prompt for this node's path) **exactly once** per entry, then call `done(success=True)`.\n"
            "6. **DEDUP / duplicate-dispatch signals count as successful completion.** If a dispatch tool (e.g. `bu_send_chat`) returns a message like `DEDUP: skipping duplicate dispatch`, `already sent`, `last_sent=Ns ago`, or any \"already in flight\" indicator, treat that entry as DONE for this round. Call `done(success=True)` immediately — do NOT retry.\n"
            "7. **Do NOT rotate to a different recipient agent to bypass DEDUP.** DEDUP is a correct signal that work for this customer is already in flight with the originally-assigned respondent. Rotating to another agent (客服小王, 客服小张, etc.) to \"satisfy must-dispatch\" creates duplicate customer replies and is FORBIDDEN.\n"
            "8. Calling `done(success=True)` while `actionable_items` is non-empty and neither a real dispatch NOR a DEDUP/already-sent response has occurred this round is a PROTOCOL VIOLATION.\n"
            "9. If `actionable_items` is empty, call `done(success=True)` immediately — no work to do.\n"
            "10. **Never use placeholder or template strings as real tool arguments.** "
            "Do NOT pass `agent_id_1`, `agent_id_2`, `<分配的代理ID>`, `<example_agent_id>`, or any other placeholder/template string as `recipient_agent_id` — those are illustrations in the system prompt, not real values. Use ONLY the real agent IDs from the Pre-resolved agent_list above. A dispatch with a fake ID silently fails and the customer gets no reply.\n\n"
        )
        # ── Inject pre-resolved agent list ──
        # Look up service/responder agents and inject them directly
        # so the LLM skips the bu_select_agents tool call (~8-10s).
        try:
            from agent.mcp.server.chat_utils.chat_tools import (
                list_chat_agents as _list_agents_fn,
                _mark_discovery,
            )
            if _caller_id and mainwin:
                _agents_result = _list_agents_fn(mainwin, {"exclude_self": _caller_id})
                _all_agents = [
                    a for a in _agents_result.get("agents", [])
                    if a.get("status", "active") != "disabled"
                ]
                if _all_agents:
                    _agent_lines = []
                    for _ag in _all_agents:
                        _tasks_str = ", ".join(_ag.get("tasks", [])) or "none"
                        _agent_lines.append(
                            f"- {_ag['name']} (ID: {_ag['id']}, tasks: {_tasks_str})"
                        )
                    _override += (
                        "### Pre-resolved `agent_list` (skip `bu_select_agents`)\n\n"
                        "The following agents are available for dispatch. "
                        "Use these IDs directly — do NOT call `bu_select_agents`, it is unnecessary.\n\n"
                        + "\n".join(_agent_lines)
                        + "\n\n---\n\n"
                    )
                    # Also mark discovery so send_chat dispatch gate passes.
                    _mark_discovery(_caller_id, _all_agents)
                    logger.info(
                        f"[BrowserAutomation] Injected pre-resolved agent_list "
                        f"({len(_all_agents)} agents) into override block, "
                        f"node={node_name}"
                    )
        except Exception as _agent_inject_err:
            logger.debug(
                f"[BrowserAutomation] Failed to inject agent_list "
                f"(non-fatal): {_agent_inject_err}"
            )
        _override += "---\n\n"

        # ── Configurable auto-dispatch short-circuit ──
        # If the node has an autoDispatch config, try to dispatch
        # actionable items directly to agents without invoking the
        # browser-use LLM at all.
        try:
            _ad_raw = (inputs.get("autoDispatch") or {}).get("content")
            _ad_cfg = None
            if isinstance(_ad_raw, str) and _ad_raw.strip():
                _ad_cfg = json.loads(_ad_raw)
            elif isinstance(_ad_raw, dict):
                _ad_cfg = _ad_raw
            if (
                _ad_cfg
                and not _pre_dispatch_blocks_prompt_auto
                and _all_agents
                and _caller_id
                and mainwin
            ):
                _ad_state = await _try_auto_dispatch(
                    config=_ad_cfg,
                    actionable=_actionable,
                    all_agents=_all_agents,
                    caller_id=_caller_id,
                    mainwin=mainwin,
                    node_name=node_name,
                    evt_type=evt_type,
                )
                if _ad_state is not None:
                    return PromptBuildResult(short_circuit_state=_ad_state)
        except Exception as _ad_err:
            logger.debug(
                f"[AUTO-DISPATCH] config-driven dispatch failed "
                f"(non-fatal, falling back to LLM): {_ad_err}"
            )

    return PromptBuildResult(
        task_hint_append=_task_append,
        override_prepend=_override,
    )


def register() -> None:
    """Register this module's hook with ``build_node``.

    Called automatically when ``feige_chat`` is imported (the package's
    ``__init__.py`` imports this module and then invokes ``register``
    on each submodule that exposes one).  Registration is idempotent.
    """
    register_before_prompt_build_hook(before_prompt_build_hook)
