"""千牛 message-object locator over raw process memory (business-specific).

Pairs with the platform scanner ``utils/win_process_memory.py``: that walks the
AliWorkbench process read-only and hands over readable region bytes; this module
knows the 千牛 schema (feasibility study §4.1–4.3) and carves buyer messages out.

Phase-0 status: the content field name is client-hashed and the exact object
shape must be re-confirmed from a live capture (plan §6). The sender anchor,
the noise filter, and the sender-id attribution below are the proven parts; the
JSON carving is best-effort until calibrated on a real client.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

# --- noise filter (study §4.1): drop UI-card JSON, id tokens, URLs, base64 ---
_CARD_MARKERS = ("h5_url", "qnCardStrategyCode", "eventhandler", "layoutJson",
                 "dinamicx.alibabausercontent.com")
_ID_TOKEN_RE = re.compile(r"^\d+\.PNM$")
_URL_RE = re.compile(r"https?://")
_CJK_RE = re.compile(r"[一-鿿]")
_SENDER_ANCHOR = b'"sender"'


def is_noise(text: str) -> bool:
    """True for strings that are UI cards / id tokens / urls — not chat text."""
    t = (text or "").strip()
    if not t:
        return True
    if any(m in t for m in _CARD_MARKERS):
        return True
    if _ID_TOKEN_RE.match(t) or _URL_RE.search(t):
        return True
    return False


def looks_like_text(text: str) -> bool:
    """Keep CJK / sentence-like bodies (study §4.1: classify text vs card)."""
    t = (text or "").strip()
    return bool(t) and not is_noise(t) and (bool(_CJK_RE.search(t)) or len(t.split()) >= 1)


def region_has_messages(data: bytes) -> bool:
    """Cheap predicate for ``win_process_memory.scan_strings`` — does this region
    contain any sender-anchored object at all?"""
    return _SENDER_ANCHOR in data


@dataclass
class MsgCandidate:
    sender_ids: set = field(default_factory=set)   # all ids under the "sender" object
    text: str = ""
    msg_id: str = ""
    send_time: Optional[int] = None
    raw: dict = field(default_factory=dict)


def _iter_json_objects_around(data: bytes, anchor: bytes) -> Iterable[dict]:
    """Yield decoded JSON objects whose body contains *anchor*.

    Best-effort bracket matching backwards/forwards from each anchor hit to the
    enclosing ``{...}``; objects that don't ``json.loads`` are skipped. Memory
    holds the SDK's deserialized UTF-8 JSON, so this recovers most objects.
    """
    start = 0
    while True:
        hit = data.find(anchor, start)
        if hit < 0:
            return
        start = hit + len(anchor)
        # Walk back to the opening brace of the ENCLOSING object, matching
        # braces so a nested object before the anchor (e.g. "ids":{...}) does
        # not steal the match.
        depth, j, open_at = 0, hit - 1, -1
        while j >= 0 and j > hit - 65536:
            c = data[j]
            if c == 0x7D:      # }
                depth += 1
            elif c == 0x7B:    # {
                if depth == 0:
                    open_at = j
                    break
                depth -= 1
            j -= 1
        if open_at < 0:
            continue
        # Forward brace-match from open_at.
        depth, i, n = 0, open_at, len(data)
        end = -1
        while i < n and i < open_at + 65536:   # cap object size
            c = data[i]
            if c == 0x7B:      # {
                depth += 1
            elif c == 0x7D:    # }
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            i += 1
        if end < 0:
            continue
        try:
            obj = json.loads(data[open_at:end].decode("utf-8", "strict"))
        except Exception:
            continue
        if isinstance(obj, dict):
            yield obj


def _collect_sender_ids(sender: object) -> set:
    """Ids under the ``sender`` object. Per study §4.2 the participant ids are
    the dict KEYS (``{<buyerId>: ..., <sellerId>: ...}``); calibrate if a live
    capture shows a different shape (plan §6)."""
    ids: set = set()
    if isinstance(sender, dict):
        for k in sender.keys():
            if str(k).strip():
                ids.add(str(k))
    elif isinstance(sender, (str, int)):
        ids.add(str(sender))
    return ids


def extract_candidates(data: bytes) -> list:
    """Carve 千牛 message objects out of a memory region.

    Returns ``MsgCandidate`` records that passed the noise filter. Attribution
    (seller vs buyer) is decided across candidates by the observer, not here:
    the seller id is the one present on *every* message (study §4.3).
    """
    out: list = []
    for obj in _iter_json_objects_around(data, _SENDER_ANCHOR):
        sender = obj.get("sender")
        if sender is None:
            continue
        # Drop UI-card objects wholesale (study §4.1): their markers are object
        # KEYS, so a per-string check on the body alone would miss them.
        if any(m in k for k in obj.keys() for m in _CARD_MARKERS):
            continue
        sender_ids = _collect_sender_ids(sender)
        if not sender_ids:
            continue
        text = _best_text_field(obj)
        if not text or not looks_like_text(text):
            continue
        ids = obj.get("ids") if isinstance(obj.get("ids"), dict) else {}
        out.append(MsgCandidate(
            sender_ids=sender_ids,
            text=text,
            msg_id=str((ids or {}).get("messageId") or obj.get("messageId") or ""),
            send_time=obj.get("sendTime") if isinstance(obj.get("sendTime"), int) else None,
            raw=obj,
        ))
    return out


def _best_text_field(obj: dict) -> str:
    """The body field name is client-hashed (study §4.2); pick the longest
    string value that reads like chat text. Calibrate to the real field name
    once a live capture pins it (plan §6)."""
    best = ""
    for v in obj.values():
        if isinstance(v, str) and looks_like_text(v) and len(v) > len(best):
            best = v
    return best


def seller_id_of(candidates: list) -> Optional[str]:
    """The sender id present on *every* candidate = the seller/store (study
    §4.3). None if it can't be determined (fewer than 2 distinct senders)."""
    if not candidates:
        return None
    common = set(candidates[0].sender_ids)
    for c in candidates[1:]:
        common &= c.sender_ids
    return next(iter(common)) if len(common) == 1 else None
