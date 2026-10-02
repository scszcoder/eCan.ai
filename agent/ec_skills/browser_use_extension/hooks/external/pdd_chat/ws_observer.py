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

import asyncio
import base64
import json
import os
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

from . import dom, ws_protocol, ws_session

CHAT_URL = "https://mms.pinduoduo.com/chat-merchant/index.html"
_SEEN_MAX = 2000
_HANDLE_ATTR = "_ecan_pdd_ws_state"


RESCAN_DELAY_S = 1.5   # let the page render a push before reading its list
LIST_CHECK_S = 10.0    # safety-net read of the conversation list
RECLAIM_COOLDOWN_S = 120.0  # at most one reload to win the session back per this long
RECLAIM_WAIT_S = 20.0      # how long a reload may take before the list is read again
RECENT_DISPATCH_S = 60.0   # the list check leaves a conversation alone this long after a dispatch

# Our own replies as the server pushes them back (role mall_cs): uid -> [(text, at)].
# The surest delivery proof there is -- the probe's 20-reply run had exactly one
# echo per reply, including two the thread check wrongly called missing.
_ECHOES: Dict[str, List[Tuple[str, float]]] = {}
_ECHO_KEEP_S = 300.0


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def record_echo(uid: str, text: str) -> None:
    now = time.time()
    kept = [(t, at) for t, at in _ECHOES.get(uid, []) if now - at < _ECHO_KEEP_S]
    kept.append((_norm(text), now))
    _ECHOES[uid] = kept[-20:]


def echoed_since(uid: str, text: str, since: float) -> bool:
    """Whether the server pushed back *text* to *uid* at or after *since*."""
    want = _norm(text)
    return any(t == want and at >= since for t, at in _ECHOES.get(uid, []))


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
        self.stats = {"frames": 0, "pushes": 0, "undecodable": 0, "messages": 0, "dispatched": 0}
        self._stats_at = time.time()
        self.last_text: Dict[str, str] = {}              # uid -> last text dispatched for it
        self.last_dispatch_at: Dict[str, float] = {}     # uid -> when it was last dispatched
        self.rescan: Optional[Callable[[], Any]] = None   # DOM re-scan, set once attached
        self._rescan_task: Optional[asyncio.Task] = None
        self.last_frame_at = 0.0
        self.watch_task: Optional[asyncio.Task] = None
        self.kicked_since = 0.0
        self.last_reclaim_at = 0.0

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
        """Every chat message is logged with what became of it, so a customer
        message that gets no reply can be traced to the step that dropped it."""
        self.stats["messages"] += 1
        uid = ev.get("conversation_id") or ""
        if ev.get("goods") and ev.get("from_customer"):
            self.product[uid] = ev["goods"]          # context for the next question
        seen = (f"[PDD-WS] msg uid={uid} msg={ev.get('msg_id')} role={ev.get('sender_role') or '-'} "
                f"type={ev.get('msg_type')} tpl={ev.get('template') or '-'} kind={ev.get('kind')} "
                f"text={(_render_text(ev) or '')[:40]!r}")
        if not uid:
            logger.info(f"{seen} -> skip: no conversation id")
            return
        if not ev.get("from_customer") and ev.get("sender_role") == "mall_cs" and ev.get("text"):
            record_echo(uid, ev["text"])
        if not ev.get("needs_reply"):
            reason = ("not from the customer" if not ev.get("from_customer")
                      else f"kind {ev.get('kind')} needs no reply")
            logger.info(f"{seen} -> skip: {reason}")
            return
        if not self.first_time(f"{uid}|{ev.get('msg_id')}"):
            logger.info(f"{seen} -> skip: already dispatched")
            return
        item = self.item_for(ev)
        try:
            self.dispatch_fn(item)
            self.stats["dispatched"] += 1
            self.last_text[uid] = item["last_message"]
            self.last_dispatch_at[uid] = time.time()
            logger.info(f"[PDD-WS] dispatched {ev.get('kind')} uid={uid} msg={ev.get('msg_id')} "
                        f"text={item['last_message'][:40]!r}")
        except Exception as exc:
            logger.warning(f"[PDD-WS] dispatch failed uid={uid}: {exc}")

    def on_frame(self, payload: Any) -> None:
        self.stats["frames"] += 1
        self.last_frame_at = time.time()
        pushes = ws_protocol.decode_frames(payload)
        if not pushes:
            raw = ws_protocol._as_bytes(payload)
            if ws_protocol.GZIP_MAGIC in raw:
                # A compressed push we could not read may hold customer messages.
                self.stats["undecodable"] += 1
                logger.warning(f"[PDD-WS] undecodable gzip frame len={len(raw)} "
                               f"b64={base64.b64encode(raw[:2048]).decode()}")
                self.request_rescan()
            self._log_stats()
            return
        for push in pushes:
            self.stats["pushes"] += 1
            events = list(ws_protocol.chat_events(push))
            if not events:
                logger.info(f"[PDD-WS] push without chat items: push_type={push.get('push_type')} "
                            f"response={push.get('response')} keys={sorted(push)[:8]}")
            for ev in events:
                self.on_event(ev)
        self._log_stats()

    def request_rescan(self) -> None:
        """A push we could not read may be a customer message (2026-10-01 14:54:25:
        "具体打几折？" arrived in an undecodable frame and was never answered). Read the
        conversation list instead, once the page has rendered the push."""
        if self.rescan is None or (self._rescan_task and not self._rescan_task.done()):
            return
        try:
            self._rescan_task = asyncio.get_running_loop().create_task(self._rescan_soon())
        except RuntimeError:
            pass

    async def _rescan_soon(self) -> None:
        await asyncio.sleep(RESCAN_DELAY_S)
        await self.rescan()

    def _log_stats(self) -> None:
        if time.time() - self._stats_at >= 60:
            self._stats_at = time.time()
            logger.info(f"[PDD-WS] stats {self.stats}")


async def _cold_start(client, sid: str, state: _State, reason: str = "cold start") -> bool:
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
        logger.warning(f"[PDD-WS] {reason} scan failed: {exc}")
        return False
    # A conversation dispatched moments ago is being answered: its sidebar preview
    # can differ from the text the socket gave (a goods card), so skip it by time.
    recent = time.time() - RECENT_DISPATCH_S
    waiting = [row for row in rows if (row.get("waiting") or row.get("group") == "unTimeout")
               and state.last_text.get(row["uid"]) != (row.get("last_message") or "")
               and state.last_dispatch_at.get(row["uid"], 0) < recent]
    for row in waiting:
        state.on_event({
            "conversation_id": row["uid"], "customer_name": row.get("name") or "",
            "from_customer": True, "kind": ws_protocol.KIND_TEXT,
            "text": row.get("last_message") or "", "msg_id": f"cold:{row.get('last_message') or ''}",
            "needs_reply": True,
        })
    if waiting:
        logger.info(f"[PDD-WS] {reason}: {len(waiting)} conversation(s) waiting")
    return True


async def _eval(client, sid: str, js: str) -> Any:
    r = await client.send_raw("Runtime.evaluate", {"expression": js, "returnByValue": True}, session_id=sid)
    return (r.get("result") or {}).get("value")


async def _ensure_single_session(client, sid: str, target_id: str, state: _State) -> None:
    """Exactly one PDD chat page, ours, holding the session.

    Every other chat tab in this browser is closed (a second tab logs the account
    in again and kicks ours out); if ours shows "账户在别处登录" it is reloaded, which
    takes the session back -- at most once per RECLAIM_COOLDOWN_S so two owners
    cannot reload each other forever.
    """
    try:
        infos = (await client.send_raw("Target.getTargets", {})).get("targetInfos") or []
    except Exception as exc:
        logger.debug(f"[PDD-WS] tab survey failed: {exc}")
        infos = []
    for info in infos:
        tid = str(info.get("targetId") or "")
        if info.get("type") == "page" and tid != target_id and dom.is_chat_url(info.get("url") or ""):
            try:
                await client.send_raw("Target.closeTarget", {"targetId": tid})
                logger.warning(f"[PDD-WS] closed extra PDD chat tab ...{tid[-6:]} "
                               f"(one chat session per account; ours is ...{target_id[-6:]})")
            except Exception as exc:
                logger.warning(f"[PDD-WS] could not close extra chat tab ...{tid[-6:]}: {exc}")
    try:
        kicked = dom.is_kicked(await _eval(client, sid, dom.KICKED_JS))
    except Exception:
        return
    if not kicked:
        if state.kicked_since:
            logger.info("[PDD-WS] chat session is ours again")
            _report_status(chat_session="ok")
        state.kicked_since = 0.0
        return
    if not state.kicked_since:
        state.kicked_since = time.time()
        logger.error("[PDD-WS] chat page logged in elsewhere (账户在别处登录): no messages reach "
                     "this store until the session is taken back")
        _report_status(chat_session="logged_in_elsewhere")
    if time.time() - state.last_reclaim_at < RECLAIM_COOLDOWN_S:
        return
    state.last_reclaim_at = time.time()
    logger.warning("[PDD-WS] reloading the chat page to take the session back")
    try:
        await client.send_raw("Page.reload", {"ignoreCache": False}, session_id=sid)
    except Exception as exc:
        logger.warning(f"[PDD-WS] reload failed: {exc}")
        return
    deadline = time.time() + RECLAIM_WAIT_S
    while time.time() < deadline:
        await asyncio.sleep(1.0)
        try:
            rows = json.loads(await _eval(client, sid, dom.LIST_SESSIONS_JS) or "[]")
        except Exception:
            continue
        if rows:
            break


def _report_status(**fields: Any) -> None:
    try:
        from utils import agent_status
        agent_status.report(None, **fields)
    except Exception:
        pass


async def _watch_list(client, sid: str, state: _State, session: Any, target_id: str = "") -> None:
    """Read the conversation list every LIST_CHECK_S, whatever the socket does.

    While the observer is live the page's DOM monitor stands down, so a socket that
    stops carrying pushes left the store blind (2026-10-02 run: attached while the
    page was still loading, never got a frame; a goods card and a follow-up went
    unanswered). A waiting conversation is dispatched from here instead; if the list
    cannot be read, the observer stops claiming dispatch and the DOM monitor resumes.
    """
    last_stats = time.time()
    while True:
        await asyncio.sleep(LIST_CHECK_S)
        if target_id:
            await _ensure_single_session(client, sid, target_id, state)
        if not await _cold_start(client, sid, state, reason="list check"):
            ws_session.set_dispatch_live(False, session)
            logger.warning("[PDD-WS] list check failed; page monitor takes over detection")
            return
        if time.time() - last_stats >= 60:
            last_stats = time.time()
            idle = f"{time.time() - state.last_frame_at:.0f}s" if state.last_frame_at else "never"
            logger.info(f"[PDD-WS] stats {state.stats} last frame {idle} ago")


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
                logger.warning(f"[PDD-WS] frame skipped: {exc}")

        client._event_registry.register("Network.webSocketFrameReceived", _on_frame)

        def _on_socket(event: str):
            def handler(params, session_id=None):
                if session_id == sid:
                    logger.info(f"[PDD-WS] socket {event}: {str(params.get('url') or params.get('requestId'))[:120]}")
            return handler
        client._event_registry.register("Network.webSocketCreated", _on_socket("opened"))
        client._event_registry.register("Network.webSocketClosed", _on_socket("closed"))
        await client.send_raw("Network.enable", {}, session_id=sid)
        state.shop = session
        ws_session.set_dispatch_live(True, session)
        logger.info(f"[PDD-WS] observer live on tab {target_id[-6:]} label={label!r}")
        state.rescan = lambda: _cold_start(client, sid, state, reason="rescan after undecodable push")
        await _ensure_single_session(client, sid, target_id, state)
        await _cold_start(client, sid, state)
        state.watch_task = asyncio.get_running_loop().create_task(
            _watch_list(client, sid, state, session, target_id))
        return client
    except Exception as exc:
        logger.warning(f"[PDD-WS] observer failed to start: {exc}")
        return None


async def stop_ws_shadow_observer(client: Any) -> None:
    if client is None:
        return
    state = getattr(client, _HANDLE_ATTR, None)
    ws_session.set_dispatch_live(False, getattr(state, "shop", None))
    if state is not None and state.watch_task:
        state.watch_task.cancel()
    try:
        await client.stop()
    except Exception:
        pass
    if state is not None:
        logger.info(f"[PDD-WS] observer stopped: {state.stats}")
