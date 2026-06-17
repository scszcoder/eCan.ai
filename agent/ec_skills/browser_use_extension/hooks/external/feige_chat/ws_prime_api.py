"""ws076A: prime-on-attach via PASSIVE capture of the SPA's own history/conversation HTTP responses.

The Feige SPA already fetches the active-conversation list (``getCSReceptionInServiceAssist``)
and per-conversation history (``pigeon_im/.../get_by_conversation``, ``.../get_user_message``,
``.../get_message_by_index*``) when a conversation opens. Those requests carry a per-request
``pigeon_sign`` (anti-bot) so we CANNOT replay them — but we can READ the RESPONSES off the
observer's CDP, exactly the way we passively read WS frames. No replay, no signing, off-renderer.

Goal for this first cut: seed ``ws_session.prime_name`` (talk_id -> real customer name) so a
name-less card resolves to the real customer from turn 1 (milestone gap #2). History seeding
(gap #1) is logged but deferred until the response shape is confirmed.

Response shapes are NOT in our request captures, so on the FIRST response per endpoint this logs
a raw sample + top-level keys, and meanwhile does a best-effort recursive scan for
(conversation_id, nickname) pairs. Refine ``_scan_pairs`` once a real sample is in hand.

Gated by the caller on ``ECAN_FEIGE_WS_PRIME_API=1``.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging

from . import ws_session

logger = logging.getLogger("eCan")

# pigeon_im / reception endpoints that carry conversation identity + history
_ENDPOINTS = (
    "getCSReceptionInServiceAssist",   # active-conversation list (names + ids)
    "get_by_conversation",             # per-conversation message history
    "get_user_message",                # user message fetch
    "get_message_by_index",            # ranged history
)

_tracked: dict = {}     # requestId -> (endpoint, session_id)
_sampled: set = set()   # endpoints we've already logged a raw sample for
_seeded_total = [0]


def _match_endpoint(url: str) -> str:
    u = str(url or "")
    for e in _ENDPOINTS:
        if e in u:
            return e
    return ""


# name keys / id keys seen across pigeon responses (best-effort; widen as samples arrive)
_ID_KEYS = ("conversation_id", "conversation_short_id", "conv_id", "talk_id", "cid", "short_id")
_NAME_KEYS = ("nickname", "nick_name", "user_name", "uname", "name", "customer_name", "buyer_name")
# ws078: the ws076A run armed but seeded 0 with a flat-key scan — the nickname is almost
# certainly nested under a user-ish sub-object, so also look one level down under these keys.
_USER_SUBOBJS = ("user", "user_info", "userinfo", "sender", "buyer", "customer", "base_info",
                 "contact", "peer", "user_detail", "profile")


def _find_name(d: dict):
    """ws078: a name directly on the dict, else nested one level under a user-ish sub-object."""
    for k in _NAME_KEYS:
        if d.get(k):
            return str(d[k])
    for sk in _USER_SUBOBJS:
        sub = d.get(sk)
        if isinstance(sub, dict):
            for k in _NAME_KEYS:
                if sub.get(k):
                    return str(sub[k])
    return None


def _scan_pairs(obj, out: dict) -> None:
    """Recursively pull {conversation_id -> nickname} pairs from a decoded JSON body."""
    if isinstance(obj, dict):
        _cid = next((obj[k] for k in _ID_KEYS if obj.get(k)), None)
        _nm = _find_name(obj)
        if _cid and _nm and not str(_nm).startswith("card:"):
            out[str(_cid)] = str(_nm)
        for v in obj.values():
            _scan_pairs(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _scan_pairs(v, out)


def _describe(d, _depth=0):
    """ws078: one-line shape of a JSON node so the FIRST-response sample reveals WHERE the
    conversation list + its id/name fields live (ws076A logged only the wrapper). Surfaces the
    keys of the first dict in any nested list so we can finalize _ID_KEYS/_NAME_KEYS in one look."""
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return f"dict{list(d.keys())} .{k}[0]={list(v[0].keys())}"
        if _depth == 0:
            sub = {k: _describe(v, 1) for k, v in d.items() if isinstance(v, (dict, list))}
            return f"dict{list(d.keys())} sub={sub}"
        return f"dict{list(d.keys())}"
    if isinstance(d, list) and d and isinstance(d[0], dict):
        return f"list[0]={list(d[0].keys())}"
    return f"<{type(d).__name__}>"


async def _read_and_seed(client, request_id, endpoint, session_id) -> None:
    try:
        res = await client.send_raw(
            "Network.getResponseBody", {"requestId": request_id}, session_id=session_id)
        body = res.get("body") or ""
        if res.get("base64Encoded"):
            body = base64.b64decode(body).decode("utf-8", "ignore")
        data = json.loads(body)
    except Exception as e:
        logger.debug(f"[WS-PRIME-API] body read/parse failed ({endpoint}): {e}")
        return
    if endpoint not in _sampled:
        _sampled.add(endpoint)
        # ws078: log the SHAPE (where the conv list + id/name fields live) + a longer raw head,
        # so the next run finalizes the extractor in one look (ws076A's 400-char sample cut off
        # before `data`). data_shape descends into `data` specifically.
        _inner = data.get("data") if isinstance(data, dict) else None
        logger.info(
            f"[WS-PRIME-API] {endpoint} first response — shape={_describe(data)} "
            f"data_shape={_describe(_inner)} raw_head={str(body)[:1800]!r}")
    pairs: dict = {}
    _scan_pairs(data, pairs)
    seeded = sum(1 for cid, nm in pairs.items() if ws_session.prime_name(cid, nm))
    if seeded:
        _seeded_total[0] += seeded
        logger.info(
            f"[WS-PRIME-API] {endpoint}: seeded {seeded} talk->name "
            f"(prime total={_seeded_total[0]})")


def register(client) -> None:
    """Arm the passive history/conversation response capture on the observer's CDP client.
    Network is already enabled per-tab by the observer, so these events flow for free."""
    def _on_response(params, session_id=None):
        try:
            url = ((params.get("response") or {}).get("url")) or ""
            ep = _match_endpoint(url)
            if ep:
                _tracked[params.get("requestId")] = (ep, session_id)
        except Exception:
            pass

    def _on_finished(params, session_id=None):
        try:
            rid = params.get("requestId")
            if rid in _tracked:
                ep, sid = _tracked.pop(rid)
                asyncio.get_running_loop().create_task(_read_and_seed(client, rid, ep, sid))
        except Exception:
            pass

    client._event_registry.register("Network.responseReceived", _on_response)
    client._event_registry.register("Network.loadingFinished", _on_finished)
    logger.info(
        "[WS-PRIME-API] passive history/conversation capture armed "
        f"(endpoints={','.join(_ENDPOINTS)})")
