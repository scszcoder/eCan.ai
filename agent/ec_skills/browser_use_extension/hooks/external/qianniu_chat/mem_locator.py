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
# The SDK keeps the message JSON as BOTH UTF-8 and UTF-16LE; a hidden/closed
# conversation often has only the UTF-16LE copy, so BOTH must be scanned (a
# UTF-8-only scan was the "detected nothing from memory" bug).
_SENDER_STR = '"sender"'
_SENDER_ANCHOR = _SENDER_STR.encode("utf-8")
_SENDER_ANCHOR_U16 = _SENDER_STR.encode("utf-16-le")
_ANCHORS = ('"sender"', '"Sender"')
_CTX = 16384
_DECODER = json.JSONDecoder()


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
    """Cheap predicate for ``win_process_memory.scan_strings`` — does this slice
    contain a sender-anchored object in EITHER encoding?"""
    return _SENDER_ANCHOR in data or _SENDER_ANCHOR_U16 in data


@dataclass
class MsgCandidate:
    uid: str = ""                                  # sender's targetId (the actual sender)
    sender_ids: set = field(default_factory=set)   # {uid} — kept for back-compat
    text: str = ""
    msg_id: str = ""
    send_time: Optional[int] = None
    has_ccode: bool = False                        # outgoing marker (cid.ccode/sendStatus)
    raw: dict = field(default_factory=dict)


def _objs_in_window(decoded: str, anchor_char: int) -> Iterable[dict]:
    """Yield the SMALLEST complete JSON dict enclosing the anchor (proven
    raw_decode-nearest-'{' method). Smallest span = least chance of borrowing
    fields across adjacent messages."""
    starts = [i for i, ch in enumerate(decoded[:anchor_char + 1]) if ch == '{'][-64:]
    best = None
    seen = set()
    for start in reversed(starts):
        try:
            obj, end = _DECODER.raw_decode(decoded, start)
        except (ValueError, RecursionError):
            continue
        if not (start <= anchor_char < end) or not isinstance(obj, dict):
            continue
        if (start, end) in seen:
            continue
        seen.add((start, end))
        if best is None or (end - start) < best[0]:
            best = (end - start, obj)
    if best is not None:
        yield best[1]


def _iter_json_objects_around(data: bytes) -> Iterable[dict]:
    """Yield message objects around every ``"sender"`` anchor, in BOTH UTF-8 and
    UTF-16LE. For each hit, decode a window in that encoding and recover the
    smallest enclosing JSON object."""
    for encoding in ("utf-8", "utf-16-le"):
        for anchor in _ANCHORS:
            needle = anchor.encode(encoding)
            cursor = 0
            while True:
                i = data.find(needle, cursor)
                if i < 0:
                    break
                cursor = i + len(needle)
                lo = max(0, i - _CTX // 2)
                if encoding == "utf-16-le" and (i - lo) % 2:
                    lo += 1
                hi = min(len(data), i + _CTX)
                raw = data[lo:hi]
                try:
                    decoded = raw.decode(encoding, "replace")
                    anchor_char = len(raw[:i - lo].decode(encoding, "replace"))
                except Exception:
                    continue
                for obj in _objs_in_window(decoded, anchor_char):
                    yield obj


def _sender_uid(sender: object) -> str:
    """The sender's id = the VALUE of ``sender.targetId`` (live-confirmed), NOT
    the dict keys (collecting keys yields the literal 'targetId'/'targetType' —
    the original bug). Falls back to a digit-valued key for alternate shapes."""
    if isinstance(sender, dict):
        uid = str(sender.get("targetId") or "")
        if uid:
            return uid
        for k in sender:
            if str(k).isdigit():
                return str(k)
        return ""
    if isinstance(sender, (str, int)):
        return str(sender)
    return ""


def _best_text_field(obj: dict) -> str:
    """Body = the ``content`` field (live-confirmed); fall back to the longest
    chat-like string only if ``content`` is absent."""
    c = obj.get("content")
    if isinstance(c, str) and looks_like_text(c):
        return c
    best = ""
    for v in obj.values():
        if isinstance(v, str) and looks_like_text(v) and len(v) > len(best):
            best = v
    return best


def extract_candidates(data: bytes) -> list:
    """Carve 千牛 message objects out of a memory slice (UTF-8 + UTF-16LE).

    Direction is decided by :func:`is_incoming` (ccode/sendStatus), not by
    cross-candidate intersection — each live message carries only its own
    sender's id."""
    out: list = []
    for obj in _iter_json_objects_around(data):
        sender = obj.get("sender")
        if sender is None:
            continue
        # Drop UI-card objects wholesale (study §4.1): markers are object KEYS.
        if any(m in k for k in obj.keys() for m in _CARD_MARKERS):
            continue
        uid = _sender_uid(sender)
        if not uid:
            continue
        text = _best_text_field(obj)
        if not text or not looks_like_text(text):
            continue
        code = obj.get("code") if isinstance(obj.get("code"), dict) else {}
        cid = obj.get("cid") if isinstance(obj.get("cid"), dict) else {}
        st = obj.get("sendTime")
        out.append(MsgCandidate(
            uid=uid,
            sender_ids={uid},
            text=text,
            msg_id=str((code or {}).get("messageId") or obj.get("messageId") or ""),
            send_time=st if isinstance(st, int) else None,
            has_ccode=bool((cid or {}).get("ccode") or obj.get("ccode")
                           or "sendStatus" in obj or "progress" in obj),
            raw=obj,
        ))
    return out


def is_incoming(cand: "MsgCandidate", self_id: Optional[str] = "") -> bool:
    """True if this is a BUYER message to answer. Structural direction (proven
    v10–v14): an OUTGOING seller message carries a conversation code (ccode) +
    sendStatus; an INCOMING buyer message carries a sender object and no ccode.
    A known store id (``self_id``) marks its own messages outgoing too."""
    if cand.has_ccode:
        return False
    if self_id:
        return bool(cand.uid) and cand.uid != self_id
    return True


def seller_id_of(candidates: list) -> Optional[str]:
    """The sender id present on *every* candidate = the seller/store. With the
    live schema (one sender id per message) this only resolves when every
    candidate happens to share a single id; prefer a configured store id and
    :func:`is_incoming` for direction."""
    if not candidates:
        return None
    common = set(candidates[0].sender_ids)
    for c in candidates[1:]:
        common &= c.sender_ids
    return next(iter(common)) if len(common) == 1 else None
