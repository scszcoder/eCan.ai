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
        opened = await dom.open_session(ev, params.customer_name)
        if not opened.get("ok"):
            return ActionResult(error=opened.get("error") or "could not open the conversation")
        for _ in range(10):
            await asyncio.sleep(0.3)
            if (await dom.get_thread(ev)).get("uid") == params.customer_name:
                return _ok({"opened": params.customer_name})
        return ActionResult(error=f"conversation {params.customer_name} did not open")
    except Exception as exc:
        return ActionResult(error=f"pdd_open_session failed: {exc}")


@custom_controller.action("Read the messages of a Pinduoduo conversation (the open one, or by uid).",
                          param_model=PddGetChatThreadAction)
async def pdd_get_chat_thread(params: PddGetChatThreadAction, browser_session: BrowserSession) -> ActionResult:
    try:
        ev = _evaluator(browser_session, "pdd_get_chat_thread", params.customer_name,
                        read_only=not params.customer_name)
        if params.customer_name and (await dom.get_thread(ev)).get("uid") != params.customer_name:
            opened = await dom.open_session(ev, params.customer_name)
            if not opened.get("ok"):
                return ActionResult(error=opened.get("error") or "could not open the conversation")
            await asyncio.sleep(0.6)
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
    own_lock = lock.holder() != uid       # direct delivery already holds it for this customer
    if own_lock and not await hot_path_v2._acquire_typing_lock(lock, uid, "pdd_send_message"):
        return ActionResult(error=f"typing_lock_busy (holder={lock.holder()!r})")
    try:
        ev = _evaluator(browser_session, "pdd_send_message", uid, read_only=False)

        async def settle():
            await asyncio.sleep(0.3)

        out = await dom.send_text(ev, uid, text, settle=settle)
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
            lock.release(uid)
