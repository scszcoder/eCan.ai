"""Feige Frontier WebSocket reader — PROTOTYPE (feige_ws branch, 2026-06-05).

Turns raw Feige WS frames (captured passively via CDP Network.webSocketFrame*)
into structured customer-message events, with NO DOM scraping. This is the read
half of the API bypass — it replaces the scrape-based 新消息 detection that
saturates the renderer.

Schema reverse-engineered from real captured frames (customer_logs/eCan_feigecap.jsonl):
  frame .8.6.<evt>.5  = a message struct, where:
     .5.8           = message text
     .5.3           = server msg id
     .5.6           = msg type enum (1000 = chat text)
     .5.10          = timestamp (ms)
     .5.9 (repeated)= kv-map {field1=key, field2=value}; keys we use:
        sender_role : '1'=customer(Buyer), '2'=agent(CurrentServer)  <-- direction
        nickname / uname : customer display name
        talk_id          : conversation id
        pigeon_cid       : pigeon conversation id
        type             : 'text' / ...
System events arrive as JSON at frame .8 (e.g. "用户已等待超30秒").

Self-contained (no app deps) so it can be unit-tested offline:
  python ws_reader.py customer_logs/eCan_feigecap.jsonl
"""
from __future__ import annotations
import json, base64, sys
from dataclasses import dataclass, field as _dc_field
from typing import Any

# ---------------------------------------------------------------- protobuf wire
def _varint(b: bytes, p: int):
    shift = val = 0
    while p < len(b):
        c = b[p]; p += 1
        val |= (c & 0x7f) << shift
        if not (c & 0x80):
            return val, p
        shift += 7
        if shift > 63:
            return None, p
    return None, p

def _printable(s: str) -> bool:
    return bool(s) and sum(ch.isprintable() or ch in "\n\t" for ch in s) / len(s) > 0.85

def decode(b: bytes, depth: int = 0):
    """Return list[(field, wiretype, value)] or None if not a clean message.
    Length-delimited values become ('str',s) / ('msg',[...]) / ('bytes',hex)."""
    out = []; p = 0
    while p < len(b):
        tag, p = _varint(b, p)
        if tag is None:
            return None
        f, wt = tag >> 3, tag & 7
        if f == 0:
            return None
        if wt == 0:
            v, p = _varint(b, p)
            if v is None:
                return None
            out.append((f, 0, v))
        elif wt == 1:
            if p + 8 > len(b):
                return None
            out.append((f, 1, b[p:p+8])); p += 8
        elif wt == 2:
            ln, p = _varint(b, p)
            if ln is None or p + ln > len(b):
                return None
            chunk = b[p:p+ln]; p += ln
            out.append((f, 2, _ld(chunk, depth)))
        elif wt == 5:
            if p + 4 > len(b):
                return None
            out.append((f, 5, b[p:p+4])); p += 4
        else:
            return None
    return out

def _ld(chunk: bytes, depth: int):
    try:
        s = chunk.decode("utf-8")
        if _printable(s):
            return ("str", s)
    except Exception:
        pass
    if depth < 10 and len(chunk) > 1:
        sub = decode(chunk, depth + 1)
        if sub is not None:
            return ("msg", sub)
    return ("bytes", chunk)

# ------------------------------------------------------------- struct navigation
def _all(dec, num):
    """All values of field `num` in a decoded message (handles repeated)."""
    return [v for (f, wt, v) in (dec or []) if f == num]

def _sub(val):
    """Unwrap a length-delimited value into a sub-message ([...]) or None."""
    if isinstance(val, tuple) and val[0] == "msg":
        return val[1]
    return None

def _str(val):
    return val[1] if isinstance(val, tuple) and val[0] == "str" else None

def _kvmap(msg5) -> dict:
    """Field .9 is a repeated {1=key, 2=value} map."""
    out = {}
    for entry in _all(msg5, 9):
        sub = _sub(entry)
        if not sub:
            # decoder may have left it as a raw 'str' like '\n<key>\x12<value>'
            s = _str(entry)
            if s:
                d2 = decode(s.encode("utf-8", "surrogatepass"))
                sub = d2
        if not sub:
            continue
        k = _str((_all(sub, 1) or [None])[0])
        v = _all(sub, 2)
        vv = _str(v[0]) if v else None
        if k is not None:
            out[k] = vv if vv is not None else (v[0] if v else None)
    return out

# ---------------------------------------------------------------- message model
@dataclass
class CustomerMessage:
    customer_name: str
    conversation_id: str   # talk_id (UI conversation id)
    text: str
    msg_id: str
    ts_ms: int
    sender_role: str
    msg_type: str
    pigeon_cid: str = ""   # routing id that matches a SENT frame's .8.9 (for off-DOM send)
    client_msg_id: str = ""  # s:client_message_id — on an echo of OUR send, equals the cid we set
    read_cursor: str = ""  # .5 server-snowflake — the "read up to" id a read-ack (.8.8.604.2) needs

def _card_text(kv: dict) -> str:
    """ws025: readable text for a CUSTOMER-shared product card (template_card).

    Title = ``generic_search_keywords.content``; ``goods_id`` = the sku/link
    target.  Returns '' when no product title is present (e.g. the role=4
    shop-pushed recommendation cards, which carry goods_id/card_header but no
    ``generic_search_keywords``) so those are left untouched.
    """
    raw = kv.get("generic_search_keywords")
    title = ""
    if isinstance(raw, str) and raw:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                title = str(obj.get("content") or "").strip()
        except Exception:
            title = ""
    if not title:
        return ""
    goods_id = str(kv.get("goods_id") or "").strip()
    return "[商品卡片] " + title + (f" 商品ID:{goods_id}" if goods_id else "")


def extract_messages(frame_bytes: bytes) -> list[CustomerMessage]:
    """Decode one WS frame -> list of CUSTOMER (sender_role=='1') text messages."""
    dec = decode(frame_bytes)
    if not dec:
        return []
    out: list[CustomerMessage] = []
    for f8 in _all(dec, 8):
        body = _sub(f8)
        if not body:
            continue  # .8 may be a JSON system-event string; skip here
        for f6 in _all(body, 6):
            evt = _sub(f6)
            if not evt:
                continue
            # message structs live at <evt>.<NNN>.5 ; iterate every sub-field's .5
            for (fld, wt, val) in evt:
                struct = _sub(val)
                if not struct:
                    continue
                for m5 in _all(struct, 5):
                    msg = _sub(m5)
                    if not msg:
                        continue
                    text = _str((_all(msg, 8) or [None])[0])
                    kv = _kvmap(msg)
                    msg_type = str(kv.get("type") or "")
                    # ws025: a product card the CUSTOMER shares carries only the
                    # literal '[商品]' placeholder (or nothing) in field 8 and no
                    # nickname/uname — the product they're asking about lives in
                    # the kv-map (generic_search_keywords.content = title,
                    # goods_id = sku). Surface it as the message text so the LLM
                    # can ground a "这件…?" follow-up instead of replying
                    # "请发下商品链接". (Compute kv BEFORE the empty-text gate so
                    # cards whose field 8 is absent aren't dropped here.)
                    if msg_type == "template_card" or (text or "") == "[商品]":
                        _ct = _card_text(kv)
                        if _ct:
                            text = _ct
                    if not text:
                        continue
                    role = str(kv.get("sender_role") or "")
                    out.append(CustomerMessage(
                        customer_name=str(kv.get("nickname") or kv.get("uname") or ""),
                        conversation_id=str(kv.get("talk_id") or kv.get("pigeon_cid") or ""),
                        text=text,
                        msg_id=str((_all(msg, 3) or [""])[0]),
                        ts_ms=int((_all(msg, 10) or [0])[0] or 0),
                        sender_role=role,
                        msg_type=msg_type,
                        pigeon_cid=str(kv.get("pigeon_cid") or ""),
                        client_msg_id=str(kv.get("s:client_message_id")
                                          or kv.get("client_message_id") or ""),
                        read_cursor=str((_all(msg, 5) or [""])[0] or ""),
                    ))
    return out

def customer_messages(frame_bytes: bytes) -> list[CustomerMessage]:
    """Only inbound customer messages (sender_role == '1')."""
    return [m for m in extract_messages(frame_bytes) if m.sender_role == "1"]

# ------------------------------------------------------------------------- CLI
if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "customer_logs/eCan_feigecap.jsonl"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    n_frames = n_cust = n_agent = 0
    seen = set()
    for line in open(src, encoding="utf-8", errors="replace"):
        if '"dir": "recv"' not in line or '"opcode": 2' not in line:
            continue
        try:
            d = json.loads(line)
            raw = base64.b64decode(d["payload_b64"], validate=False)
        except Exception:
            continue
        n_frames += 1
        for m in extract_messages(raw):
            if m.sender_role == "1":
                n_cust += 1
                key = (m.msg_id, m.text)
                if key in seen:
                    continue
                seen.add(key)
                print(f"  [CUSTOMER] {m.customer_name!r} conv={m.conversation_id} "
                      f"msg_id={m.msg_id} ts={m.ts_ms}\n             text={m.text!r}")
            elif m.sender_role == "2":
                n_agent += 1
    print(f"\nframes={n_frames}  customer_msgs={n_cust}  agent_msgs(filtered out)={n_agent}")
    print("If distinct customer messages print above with names -> passive READER works.")
