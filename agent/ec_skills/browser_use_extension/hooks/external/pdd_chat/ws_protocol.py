"""Pinduoduo chat push decoding: one titan WebSocket frame in, chat events out.

Pure functions -- no browser, no I/O -- so they are tested against frames built
in the tests and checked offline against real captures (which stay out of the
repo: they hold customer messages).

Inbound chat arrives on ``wss://titan-ws.pinduoduo.com/`` as binary frames:
a small binary header, a protobuf-style envelope, then a gzip block whose
content is that envelope's inner bytes followed by one JSON object. Outbound
goes through the page (the HTTP send needs a page-minted anti-bot token), so
nothing here encodes.
"""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any, Dict, Iterator, List, Optional, Union

GZIP_MAGIC = b"\x1f\x8b"
TITAN_HOST = "titan-ws.pinduoduo.com"

# message.type / template_name -> the kind a skill reasons about
KIND_TEXT = "text"
KIND_IMAGE = "image"
KIND_GOODS_CARD = "goods_card"
KIND_SOURCE = "source"          # "当前用户来自 商品详情页" -- context, needs no reply
KIND_REMIND = "remind"          # the buyer nudged for a reply (消费者催促您)
KIND_OTHER = "other"


def is_titan_url(url: str) -> bool:
    return TITAN_HOST in (url or "")


def _as_bytes(frame: Union[bytes, str]) -> bytes:
    if isinstance(frame, bytes):
        return frame
    try:
        return base64.b64decode(frame, validate=False)
    except Exception:
        return b""


def decode_frame(frame: Union[bytes, str]) -> Optional[Dict[str, Any]]:
    """The JSON object inside one titan frame, or None (heartbeat, ack, protobuf-only)."""
    raw = _as_bytes(frame)
    i = raw.find(GZIP_MAGIC)
    if i < 0:
        return None
    try:
        body = zlib.decompressobj(31).decompress(raw[i:])
    except Exception:
        return None
    start, end = body.find(b"{"), body.rfind(b"}")
    if start < 0 or end <= start:
        return None                 # e.g. the client_ip_info push: protobuf, no JSON
    try:
        obj = json.loads(body[start:end + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _kind(msg: Dict[str, Any]) -> str:
    t = msg.get("type")
    tpl = msg.get("template_name") or ""
    if t == 1:
        return KIND_IMAGE
    if t == 41 or tpl == "user_source":
        return KIND_SOURCE
    if t == 31 or tpl.startswith("remind_customer_service"):
        return KIND_REMIND
    if tpl == "user_goods_card":
        return KIND_GOODS_CARD
    if t == 0 and isinstance(msg.get("info"), dict) and msg["info"].get("goodsName"):
        return KIND_GOODS_CARD     # an older product-link shape: content = goods URL
    if t == 0:
        return KIND_TEXT
    return KIND_OTHER


def _goods(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    info = msg.get("info") or {}
    if not isinstance(info, dict):
        return None
    g = info.get("goods_info") if isinstance(info.get("goods_info"), dict) else None
    if g:
        return {"goods_id": str(g.get("goods_id") or ""), "name": g.get("goods_name") or "",
                "price": (g.get("total_amount") / 100) if isinstance(g.get("total_amount"), (int, float)) else None,
                "thumb": g.get("goods_thumb_url") or "", "url": g.get("mall_link_url") or ""}
    if info.get("goodsName") or info.get("goodsID"):
        price = info.get("goodsPrice")
        try:
            price = float(price) if price not in (None, "") else None
        except (TypeError, ValueError):
            pass
        return {"goods_id": str(info.get("goodsID") or ""), "name": info.get("goodsName") or "",
                "price": price, "thumb": info.get("goodsThumbUrl") or "",
                "url": info.get("linkUrl") or msg.get("content") or ""}
    return None


def normalize_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """One chat message as a site-neutral event."""
    frm, to = msg.get("from") or {}, msg.get("to") or {}
    from_buyer = frm.get("role") == "user"
    uid = str((frm if from_buyer else to).get("uid") or "")
    kind = _kind(msg)
    info = msg.get("info") if isinstance(msg.get("info"), dict) else {}
    event = {
        "platform": "pinduoduo",
        "conversation_id": uid,                 # the buyer uid keys a conversation
        "customer_id": uid,
        "customer_name": msg.get("nickname") or "",
        "from_customer": from_buyer,
        "sender_role": frm.get("role") or "",
        "agent_account": frm.get("csid") or "",
        "kind": kind,
        "text": msg.get("content") if kind in (KIND_TEXT, KIND_REMIND) else "",
        "msg_id": str(msg.get("msg_id") or ""),
        "pre_msg_id": str(msg.get("pre_msg_id") or ""),
        "ts": int(msg.get("ts") or 0) if str(msg.get("ts") or "").isdigit() else 0,
        "needs_reply": from_buyer and kind in (KIND_TEXT, KIND_IMAGE, KIND_GOODS_CARD, KIND_REMIND)
                       and not msg.get("no_unreply_hint"),
    }
    if kind == KIND_IMAGE:
        event["image_url"] = info.get("image_url") or msg.get("content") or ""
    if kind in (KIND_GOODS_CARD, KIND_SOURCE):
        event["goods"] = _goods(msg)
    if kind == KIND_REMIND:
        event["text"] = (msg.get("content") or "").strip()
    return event


def chat_events(push: Optional[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    """Chat messages in one decoded push (a push may carry several)."""
    if not push or push.get("push_type") != 2:
        return
    for item in (push.get("push_data") or {}).get("data") or []:
        msg = (item or {}).get("message")
        if isinstance(msg, dict):
            yield normalize_message(msg)


def system_event(push: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A mall_system_msg as {type, ...}: read receipts (20), cs online (40),
    marketing tip (50, ignore), "awaiting reply" tag (68)."""
    if not push or push.get("response") != "mall_system_msg":
        return None
    msg = push.get("message") or {}
    data = msg.get("data") or {}
    out = {"type": msg.get("type"), "data": data if isinstance(data, dict) else {}}
    uid = (out["data"].get("user_id") or out["data"].get("uid"))
    if uid is not None:
        out["conversation_id"] = str(uid)
    return out


def decode_events(frame: Union[bytes, str]) -> List[Dict[str, Any]]:
    """Every chat event in one frame (empty for system pushes and control frames)."""
    return list(chat_events(decode_frame(frame)))
