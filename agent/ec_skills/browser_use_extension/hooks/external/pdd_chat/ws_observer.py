"""Titan WebSocket observer: every Pinduoduo customer message, dispatched as it arrives.

The platform starts it from the DOM-mutation event monitor exactly as it
starts Feige's (``bridge.ws_observer.start_ws_shadow_observer``). It attaches
its own CDP client to the chat tab, decodes titan pushes (``ws_protocol``),
and hands each buyer message that needs a reply to ``dispatch_fn`` in the
item shape the front-desk pipeline reads.

Identity is the buyer **uid**, not the nickname: Pinduoduo masks nicknames
(``S*******n``) and two customers can share one. The masked name travels as
``customer_display_name``.

Gate: ``ECAN_PDD_WS_DISPATCH`` (default on). Off, it returns None and the DOM
monitor dispatches alone.
"""
from __future__ import annotations

import json
import os
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional

from utils.logger_helper import logger_helper as logger

from . import dom, ws_protocol, ws_session

CHAT_URL = "https://mms.pinduoduo.com/chat-merchant/index.html"
_SEEN_MAX = 2000
_HANDLE_ATTR = "_ecan_pdd_ws_state"


def dispatch_enabled() -> bool:
    return os.environ.get("ECAN_PDD_WS_DISPATCH", "1") != "0"


def _render_text(ev: Dict[str, Any]) -> str:
    """What the agent reads as the customer's message."""
    kind = ev.get("kind")
    if kind == ws_protocol.KIND_IMAGE:
        return "[图片]"
    if kind == ws_protocol.KIND_GOODS_CARD:
        g = ev.get("goods") or {}
        price = f" ¥{g['price']}" if g.get("price") not in (None, "") else ""
        return f"[商品卡片] {g.get('name', '')}{price} (商品ID {g.get('goods_id', '')})".strip()
    if kind == ws_protocol.KIND_REMIND:
        return "[消费者催促回复] " + (ev.get("text") or "")
    return ev.get("text") or ""


class _State:
    def __init__(self, dispatch_fn: Callable[[dict], Any], label: str):
        self.dispatch_fn = dispatch_fn
        self.label = label
        self.seen: "OrderedDict[str, float]" = OrderedDict()
        self.product: Dict[str, Dict[str, Any]] = {}     # uid -> last goods the buyer came from
        self.stats = {"frames": 0, "messages": 0, "dispatched": 0}

    def first_time(self, key: str) -> bool:
        if not key or key in self.seen:
            return False
        self.seen[key] = time.time()
        while len(self.seen) > _SEEN_MAX:
            self.seen.popitem(last=False)
        return True

    def item_for(self, ev: Dict[str, Any]) -> Dict[str, Any]:
        uid = ev["conversation_id"]
        text = _render_text(ev)
        item = {
            "customer_name": uid, "name": uid, "session_id": uid, "customer_id": uid,
            "talk_id": uid,
            "customer_display_name": ev.get("customer_name") or "",
            "last_message": text, "latest_message": text,
            "msg_id": ev.get("msg_id") or "", "latest_message_msg_id": ev.get("msg_id") or "",
            "identity_key": f"{uid}|{ev.get('msg_id') or text}",
            "unread_badge": "1",
            "source": "ws_frontier",
            "chat_url": CHAT_URL,
            "message_kind": ev.get("kind") or "",
        }
        if ev.get("kind") == ws_protocol.KIND_IMAGE and ev.get("image_url"):
            item["last_message_attachments"] = [{"kind": "image", "url": ev["image_url"], "alt": "customer image"}]
        goods = ev.get("goods") or self.product.get(uid)
        if goods:
            item["product_context"] = goods
        return item

    def on_event(self, ev: Dict[str, Any]) -> None:
        self.stats["messages"] += 1
        uid = ev.get("conversation_id") or ""
        if ev.get("goods") and ev.get("from_customer"):
            self.product[uid] = ev["goods"]          # context for the next question
        if not ev.get("needs_reply") or not uid:
            return
        if not self.first_time(f"{uid}|{ev.get('msg_id')}"):
            return
        item = self.item_for(ev)
        try:
            self.dispatch_fn(item)
            self.stats["dispatched"] += 1
            logger.info(f"[PDD-WS] dispatched {ev.get('kind')} uid={uid} msg={ev.get('msg_id')} "
                        f"text={item['last_message'][:40]!r}")
        except Exception as exc:
            logger.warning(f"[PDD-WS] dispatch failed uid={uid}: {exc}")

    def on_frame(self, payload: Any) -> None:
        self.stats["frames"] += 1
        push = ws_protocol.decode_frame(payload)
        if not push:
            return
        for ev in ws_protocol.chat_events(push):
            self.on_event(ev)


async def _cold_start(client, sid: str, state: _State) -> None:
    """Conversations already waiting when we attached: dispatch each once.

    The socket only reports what happens after we attach, and a live observer
    silences the DOM monitor, so without this a customer waiting at start-up
    is never answered.
    """
    try:
        r = await client.send_raw("Runtime.evaluate", {"expression": dom.LIST_SESSIONS_JS,
                                                       "returnByValue": True}, session_id=sid)
        rows = json.loads((r.get("result") or {}).get("value") or "[]")
    except Exception as exc:
        logger.warning(f"[PDD-WS] cold-start scan failed: {exc}")
        return
    waiting = [row for row in rows if row.get("waiting") or row.get("group") == "unTimeout"]
    for row in waiting:
        state.on_event({
            "conversation_id": row["uid"], "customer_name": row.get("name") or "",
            "from_customer": True, "kind": ws_protocol.KIND_TEXT,
            "text": row.get("last_message") or "", "msg_id": f"cold:{row.get('last_message') or ''}",
            "needs_reply": True,
        })
    if waiting:
        logger.info(f"[PDD-WS] cold start: {len(waiting)} conversation(s) already waiting")


async def start_ws_shadow_observer(session: Any, target_id: str, label: str = "",
                                   dispatch_fn: Optional[Callable[[dict], Any]] = None) -> Any:
    """Attach to the chat tab and dispatch from the titan socket. Returns the handle, or None."""
    if not dispatch_enabled() or dispatch_fn is None:
        return None
    cdp_url = getattr(session, "cdp_url", None) or getattr(getattr(session, "browser_profile", None), "cdp_url", None)
    if not cdp_url:
        logger.warning("[PDD-WS] no cdp_url on the session; observer not started")
        return None
    try:
        from cdp_use import CDPClient
        from agent.ec_skills.browser_use_extension.site_probe import browser_ws_url
        client = CDPClient(url=browser_ws_url(cdp_url))
        await client.start()
        sid = (await client.send_raw("Target.attachToTarget",
                                     {"targetId": target_id, "flatten": True})).get("sessionId")
        if not sid:
            await client.stop()
            return None
        state = _State(dispatch_fn, label)
        setattr(client, _HANDLE_ATTR, state)

        def _on_frame(params, session_id=None):
            if session_id != sid:
                return
            try:
                state.on_frame((params.get("response") or {}).get("payloadData", ""))
            except Exception as exc:
                logger.debug(f"[PDD-WS] frame skipped: {exc}")

        client._event_registry.register("Network.webSocketFrameReceived", _on_frame)
        await client.send_raw("Network.enable", {}, session_id=sid)
        ws_session.set_dispatch_live(True)
        logger.info(f"[PDD-WS] observer live on tab {target_id[-6:]} label={label!r}")
        await _cold_start(client, sid, state)
        return client
    except Exception as exc:
        logger.warning(f"[PDD-WS] observer failed to start: {exc}")
        return None


async def stop_ws_shadow_observer(client: Any) -> None:
    if client is None:
        return
    state = getattr(client, _HANDLE_ATTR, None)
    ws_session.set_dispatch_live(False)
    try:
        await client.stop()
    except Exception:
        pass
    if state is not None:
        logger.info(f"[PDD-WS] observer stopped: {state.stats}")
