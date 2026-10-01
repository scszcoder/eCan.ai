"""Pinduoduo chat actions on the shared browser-use controller.

``pdd_list_sessions`` / ``pdd_open_session`` / ``pdd_get_chat_thread`` /
``pdd_send_message``. ``customer_name`` is the buyer **uid** throughout (the
id the titan socket and the conversation rows carry); masked nicknames are
display-only. Sending types into the reply box and clicks Send -- the HTTP
send needs a token only the page can mint -- then waits to see the reply in
the thread before reporting success.
"""
# No ``from __future__ import annotations`` here: browser-use matches the
# injected ``browser_session: BrowserSession`` parameter by its real type, and a
# string annotation makes it reject the action at registration.
import asyncio
import json

from pydantic import BaseModel, Field

from browser_use import BrowserSession
from browser_use.agent.views import ActionResult

from utils.logger_helper import logger_helper as logger
from agent.ec_skills.browser_use_extension.extension_tools_service import (
    _evaluate_live_chat_js,
    custom_controller,
)

from . import dom, hot_path_v2
from .typing_lock import get_lock

SEND_CONFIRM_S = 5.0


class PddListSessionsAction(BaseModel):
    waiting_only: bool = Field(False, description="Only conversations whose customer is waiting for a reply")


class PddOpenSessionAction(BaseModel):
    customer_name: str = Field(..., description="The customer's uid (conversation id)")


class PddGetChatThreadAction(BaseModel):
    customer_name: str = Field("", description="Open this customer's conversation first (uid); empty = the open one")
    max_messages: int = Field(20, ge=1, le=100)


class PddSendMessageAction(BaseModel):
    customer_name: str = Field(..., description="The customer's uid (conversation id)")
    text: str = Field(..., description="The reply to send")
    source_customer_msg_id: str = Field("", description="The customer message this answers")
    source_latest_message: str = Field("", description="Its text, for tracing")


def _evaluator(browser_session: BrowserSession, label: str, customer_key: str = "", read_only: bool = True):
    async def evaluate(js: str):
        return await _evaluate_live_chat_js(browser_session, js, trace_label=label,
                                            read_only=read_only, customer_key=customer_key)
    return evaluate


async def _cdp_sender(browser_session: BrowserSession):
    """Send CDP commands (real input) to the chat tab, on the CDP client's own
    loop (direct delivery calls in from another loop). None: no chat tab."""
    from agent.ec_skills.browser_use_extension.extension_tools_service import _safe_handler_loop
    tid = await dom.resolve_tab_target_id(browser_session)
    if not tid or not hasattr(browser_session, "get_or_create_cdp_session"):
        return None
    cdp_session = await browser_session.get_or_create_cdp_session(target_id=tid, focus=False)
    client, sid = cdp_session.cdp_client, cdp_session.session_id

    async def send(method: str, params: dict):
        domain, name = method.split(".", 1)
        fn = getattr(getattr(client.send, domain), name)
        owner = _safe_handler_loop(client)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if owner is not None and running is not owner:
            return await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(fn(params=params, session_id=sid), owner))
        return await fn(params=params, session_id=sid)
    return send


async def _open(browser_session: BrowserSession, ev, uid: str) -> dict:
    """Open *uid*'s conversation with a real click (synthetic as a last resort)."""
    cdp = await _cdp_sender(browser_session)
    if cdp is not None:
        return await dom.open_conversation(ev, uid, cdp, settle=lambda: asyncio.sleep(0.3))
    logger.warning("[PDD] no CDP sender for the chat tab; trying a synthetic click")
    opened = await dom.open_session(ev, uid)
    if not opened.get("ok"):
        return opened
    for _ in range(10):
        await asyncio.sleep(0.3)
        if (await dom.get_thread(ev)).get("uid") == uid:
            return {"ok": True}
    return {"ok": False, "error": f"conversation {uid} did not open"}


def _ok(data: dict) -> ActionResult:
    return ActionResult(extracted_content=json.dumps(data, ensure_ascii=False), include_in_memory=True)


@custom_controller.action("List customer conversations in the Pinduoduo (拼多多) chat page.",
                          param_model=PddListSessionsAction)
async def pdd_list_sessions(params: PddListSessionsAction, browser_session: BrowserSession) -> ActionResult:
    try:
        rows = await dom.list_sessions(_evaluator(browser_session, "pdd_list_sessions"))
        if params.waiting_only:
            rows = [r for r in rows if r.get("waiting") or r.get("group") == "unTimeout"]
        return _ok({"sessions": rows, "total": len(rows)})
    except Exception as exc:
        return ActionResult(error=f"pdd_list_sessions failed: {exc}")


@custom_controller.action("Open one customer's conversation in the Pinduoduo chat page (by uid).",
                          param_model=PddOpenSessionAction)
async def pdd_open_session(params: PddOpenSessionAction, browser_session: BrowserSession) -> ActionResult:
    try:
        ev = _evaluator(browser_session, "pdd_open_session", params.customer_name, read_only=False)
        opened = await _open(browser_session, ev, params.customer_name)
        if not opened.get("ok"):
            return ActionResult(error=opened.get("error") or "could not open the conversation")
        return _ok({"opened": params.customer_name})
    except Exception as exc:
        return ActionResult(error=f"pdd_open_session failed: {exc}")


@custom_controller.action("Read the messages of a Pinduoduo conversation (the open one, or by uid).",
                          param_model=PddGetChatThreadAction)
async def pdd_get_chat_thread(params: PddGetChatThreadAction, browser_session: BrowserSession) -> ActionResult:
    try:
        ev = _evaluator(browser_session, "pdd_get_chat_thread", params.customer_name,
                        read_only=not params.customer_name)
        if params.customer_name and (await dom.get_thread(ev)).get("uid") != params.customer_name:
            opened = await _open(browser_session, ev, params.customer_name)
            if not opened.get("ok"):
                return ActionResult(error=opened.get("error") or "could not open the conversation")
        thread = await dom.get_thread(ev)
        thread["messages"] = (thread.get("messages") or [])[-params.max_messages:]
        return _ok(thread)
    except Exception as exc:
        return ActionResult(error=f"pdd_get_chat_thread failed: {exc}")


async def _confirm_sent(evaluate, uid: str, text: str) -> bool:
    want = " ".join(text.split())
    deadline = asyncio.get_event_loop().time() + SEND_CONFIRM_S
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.4)
        thread = await dom.get_thread(evaluate)
        if thread.get("uid") != uid:
            return False
        for m in reversed(thread.get("messages") or []):
            if m.get("who") == "agent":
                if " ".join((m.get("text") or "").split()) == want:
                    return True
                break
    return False


@custom_controller.action("Send a reply to a Pinduoduo customer (by uid): types it and clicks Send.",
                          param_model=PddSendMessageAction)
async def pdd_send_message(params: PddSendMessageAction, browser_session: BrowserSession) -> ActionResult:
    uid, text = params.customer_name.strip(), params.text.strip()
    if not uid or not text:
        return ActionResult(error="customer_name (uid) and text are required")
    lock = get_lock()
    # this store's reply box (its own browser); direct delivery may already hold it
    own_lock = lock.holder(browser_session) != uid
    if own_lock and not await hot_path_v2._acquire_typing_lock(
            lock, uid, "pdd_send_message", session_key=browser_session):
        return ActionResult(error=f"typing_lock_busy (holder={lock.holder(browser_session)!r})")
    try:
        ev = _evaluator(browser_session, "pdd_send_message", uid, read_only=False)

        async def settle():
            await asyncio.sleep(0.3)

        cdp = await _cdp_sender(browser_session)
        if cdp is None:
            logger.warning(f"[PDD] no CDP sender for the chat tab; synthetic send to {uid} (known to be ignored)")
        out = await dom.send_text(ev, uid, text, settle=settle, cdp=cdp)
        logger.info(f"[PDD] send to {uid}: typed={out.get('ok')} cleared={out.get('cleared')} "
                    f"error={out.get('error')!r} len={len(text)}")
        if not out.get("ok"):
            return ActionResult(error=f"pdd_send_not_typed: {out.get('error')}")
        if not await _confirm_sent(ev, uid, text):
            # Clicked, but the bubble did not show up: report it rather than retype
            # (a retry that re-types would duplicate a reply that did land).
            logger.warning(f"[PDD] send to {uid} not confirmed in the thread within {SEND_CONFIRM_S:.0f}s")
            return ActionResult(error="pdd_send_unverified:no_bubble -- reply not seen in the thread")
        return _ok({"sent": True, "customer": uid, "source_msg_id": params.source_customer_msg_id})
    except Exception as exc:
        return ActionResult(error=f"pdd_send_message failed: {exc}")
    finally:
        if own_lock:
            lock.release(uid, browser_session)
