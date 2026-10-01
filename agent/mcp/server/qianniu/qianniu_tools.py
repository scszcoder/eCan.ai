"""千牛 (AliWorkbench) MCP tools — reply delivery + transcript read.

Native-desktop RPA, cloned from the wechat tools: window-focus + OCR + clipboard
+ pyautogui. The send path is the feasibility study's proven primitive
(foreground fix → clipboard → Ctrl+V → Enter), gated by the OCR chat-header
verify (``qianniu_ocr.verify_header_name``) so a reply can only go to the buyer
whose name is actually on screen — fail-closed, never mis-deliver (study §5).

Tools:
  qianniu_send    — verify the open conversation is the intended buyer, then send text
  qianniu_receive — OCR the open conversation's transcript and return visible lines

Co-pilot scope (Phase 1): these act on the ALREADY-OPEN conversation. Auto
conversation-switching (OCR sidebar click + search-by-name) lands in Phase 2;
until then the human/observer opens the chat and the header-verify guards it.
"""
import json
import os
import random
import time
import traceback

import pyautogui
from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger
from agent.mcp.server.wechat.platform_utils import (
    find_windows_by_title,
    bring_window_to_front,
    clipboard_set_text,
    paste_hotkey,
)
from agent.mcp.server.qianniu.qianniu_ocr import (
    ocr_qianniu_window,
    verify_header_name,
    header_band_texts,
)

_QIANNIU_WIN_TITLES = ["千牛", "AliWorkbench", "阿里旺旺"]
_POST_ACTION_DELAY = 0.6
_POST_TYPE_DELAY = 0.5
_SETTLE_AFTER_OPEN = 1.4

# OCR anchors for locating the conversation search box. Calibrate against a live
# client (plan §6): the search box sits in the sidebar, near the top-left.
_SEARCH_ANCHORS = ("搜索", "search", "请输入")


def _humanize(base: float) -> None:
    """Sleep *base* plus a small random jitter (study Phase 3: humanized pacing,
    no superhuman burst rates). Disable with ECAN_QIANNIU_NO_JITTER=1."""
    if os.environ.get("ECAN_QIANNIU_NO_JITTER", "") == "1":
        time.sleep(base)
        return
    time.sleep(base + random.uniform(0.1, 0.5))


def _find_window():
    wins = find_windows_by_title(_QIANNIU_WIN_TITLES)
    return wins[0] if wins else None


def _foreground() -> bool:
    """Bring 千牛 to the foreground. False if the window isn't found."""
    win = _find_window()
    if not win:
        logger.warning("[qianniu] window not found; is 千牛 running?")
        return False
    bring_window_to_front(win)
    _humanize(_POST_ACTION_DELAY)
    return True


def _looks_like_qianniu(ocr_data: list) -> bool:
    """Layout-drift guard: the window must show at least one expected anchor
    before we click anything. Fail-closed on an unrecognised layout."""
    if not ocr_data:
        return False
    blob = " ".join(str(it.get("text") or "") for it in ocr_data).lower()
    return any(a in blob for a in ("搜索", "发送", "send", "阿里", "千牛", "宝贝"))


def _click(x: int, y: int) -> None:
    pyautogui.moveTo(x, y)
    time.sleep(0.15)
    pyautogui.click(x, y)


def _find_search_box(ocr_data: list):
    """Click point for the conversation search box, or None. Picks the
    search-anchor line nearest the top-left (the sidebar search field)."""
    cands = []
    for it in ocr_data:
        t = str(it.get("text") or "").strip().lower()
        loc = it.get("loc")
        if not loc or not any(a in t for a in _SEARCH_ANCHORS):
            continue
        y1, x1, y2, x2 = loc
        cands.append((x1 + y1, (int((x1 + x2) / 2), int((y1 + y2) / 2))))  # rank by x+y
    if not cands:
        return None
    cands.sort(key=lambda c: c[0])
    return cands[0][1]


def _type_and_send(text: str) -> None:
    """Clipboard → Ctrl+V → Enter (study §4.4: Enter sends, not the button)."""
    clipboard_set_text(text)
    paste_hotkey()
    _humanize(_POST_TYPE_DELAY)
    pyautogui.press("enter")
    _humanize(_POST_ACTION_DELAY)


def _open_conversation_by_name(name: str) -> tuple:
    """Search-by-name to open buyer *name*'s conversation, then OCR-verify the
    header. Returns (opened_and_verified: bool, header_text: str, error: str).

    千牛 has no stable conversation id we can address, so the display name is
    the only durable key (study §5). Assumes 千牛 is already foregrounded.
    """
    ocr_data = ocr_qianniu_window()
    if not _looks_like_qianniu(ocr_data):
        return False, "", "layout not recognised as 千牛 (OCR drift); aborting"
    box = _find_search_box(ocr_data)
    if not box:
        return False, "", "search box not found via OCR; cannot open by name"
    _click(box[0], box[1])
    _humanize(_POST_TYPE_DELAY)
    clipboard_set_text(name)
    paste_hotkey()
    _humanize(_POST_TYPE_DELAY)
    pyautogui.press("enter")
    _humanize(_SETTLE_AFTER_OPEN)
    v = verify_header_name(name)
    if v.matched:
        return True, v.header_text, ""
    return False, v.header_text, (f"opened by search but header {v.header_text!r} "
                                  f"does not match {name!r}")


def _send_result(sent: bool, verified: bool, error: str, header: str = "") -> list:
    return [TextContent(type="text", text=json.dumps({
        "chat_sent": sent, "verified": verified, "error": error,
        "header_name": header,
    }, ensure_ascii=False, default=str))]


def _lock():
    from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat.typing_lock import get_lock
    return get_lock()


async def qianniu_send(mainwin, args):
    """Send a text reply to buyer *buyer_display_name* in 千牛.

    If the open conversation is not that buyer and ``auto_open`` is set
    (default), searches for the buyer by name and opens their conversation
    first. The reply is sent ONLY after an OCR header verify confirms the open
    chat is the intended buyer — fail-closed, never mis-delivers (study §5).

    Input:
        buyer_display_name: str — the buyer the reply is FOR (header must match)
        chat_msg: str           — the reply text
        auto_open: bool         — open the buyer's conversation if not already open (default true)

    Output (JSON): chat_sent, verified (header matched), header_name, error.
    """
    lock = _lock()
    holder = f"send:{id(args)}"
    try:
        inp = args.get("input", args)
        buyer = (inp.get("buyer_display_name") or "").strip()
        msg = inp.get("chat_msg") or ""
        auto_open = inp.get("auto_open", True)
        if not buyer:
            return _send_result(False, False, "buyer_display_name is required")
        if not msg:
            return _send_result(False, False, "chat_msg is required")

        # Serialize all desktop action so two sends never interleave on the one
        # shared window (study Phase 3).
        if not lock.try_acquire(holder):
            return _send_result(False, False, f"another send is in progress (holder {lock.holder()!r})")

        if not _foreground():
            return _send_result(False, False, "千牛 window not found. Is it running?")

        # Fail-closed guard: the open conversation MUST be this buyer.
        v = verify_header_name(buyer)
        if not v.matched and auto_open:
            logger.info(f"[qianniu_send] open chat is {v.header_text!r}, not {buyer!r}; opening by name")
            opened, header, err = _open_conversation_by_name(buyer)
            if not opened:
                return _send_result(False, False, f"could not open {buyer!r}: {err}", header)
            v = verify_header_name(buyer)   # re-verify after the switch
        if not v.matched:
            logger.warning(f"[qianniu_send] ABORT: header {v.header_text!r} != buyer {buyer!r}; "
                           f"band saw {v.candidates[:6]}")
            return _send_result(False, False,
                                f"header verify failed: open chat header {v.header_text!r} "
                                f"does not match {buyer!r} — refusing to send", v.header_text)

        _type_and_send(msg)
        logger.info(f"[qianniu_send] sent to {buyer!r} (header {v.header_text!r}): {msg[:40]!r}")
        return _send_result(True, True, "", v.header_text)

    except Exception as e:
        logger.error(f"[qianniu_send] {traceback.format_exc()}")
        return _send_result(False, False, str(e))
    finally:
        lock.release(holder)


async def qianniu_open_session(mainwin, args):
    """Open buyer *buyer_display_name*'s 千牛 conversation (search-by-name) and
    OCR-verify the header. Does not send anything.

    Input: buyer_display_name: str
    Output (JSON): opened, header_name, error.
    """
    lock = _lock()
    holder = f"open:{id(args)}"
    try:
        inp = args.get("input", args)
        buyer = (inp.get("buyer_display_name") or "").strip()
        if not buyer:
            return [TextContent(type="text", text=json.dumps(
                {"opened": False, "header_name": "", "error": "buyer_display_name is required"},
                ensure_ascii=False))]
        if not lock.try_acquire(holder):
            return [TextContent(type="text", text=json.dumps(
                {"opened": False, "header_name": "", "error": f"busy (holder {lock.holder()!r})"},
                ensure_ascii=False))]
        if not _foreground():
            return [TextContent(type="text", text=json.dumps(
                {"opened": False, "header_name": "", "error": "千牛 window not found"},
                ensure_ascii=False))]
        opened, header, err = _open_conversation_by_name(buyer)
        return [TextContent(type="text", text=json.dumps(
            {"opened": opened, "header_name": header, "error": err},
            ensure_ascii=False, default=str))]
    except Exception as e:
        logger.error(f"[qianniu_open_session] {traceback.format_exc()}")
        return [TextContent(type="text", text=json.dumps(
            {"opened": False, "header_name": "", "error": str(e)}, ensure_ascii=False))]
    finally:
        lock.release(holder)


async def qianniu_receive(mainwin, args):
    """OCR the open 千牛 conversation and return visible text lines (newest-last).

    Input: (none required)
    Output (JSON): lines (list of {text, loc}), error.
    """
    try:
        if not _foreground():
            return [TextContent(type="text", text=json.dumps(
                {"lines": [], "error": "千牛 window not found. Is it running?"},
                ensure_ascii=False))]
        ocr_data = ocr_qianniu_window()
        lines = [{"text": str(it.get("text") or ""), "loc": it.get("loc")}
                 for it in ocr_data if str(it.get("text") or "").strip()]
        return [TextContent(type="text", text=json.dumps(
            {"lines": lines, "error": ""}, ensure_ascii=False, default=str))]
    except Exception as e:
        logger.error(f"[qianniu_receive] {traceback.format_exc()}")
        return [TextContent(type="text", text=json.dumps(
            {"lines": [], "error": str(e)}, ensure_ascii=False))]


# --- MCP tool schemas -------------------------------------------------------

def add_qianniu_send_tool_schema(tool_schemas):
    import mcp.types as types
    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="qianniu_send",
        description=(
            "<category>Qianniu</category><sub-category>Messaging</sub-category>"
            "Send a text reply to the currently-open 千牛 (Taobao/Tmall seller) "
            "conversation. Before sending it OCR-verifies that the open chat's "
            "header names buyer_display_name, and refuses to send on any mismatch "
            "(never mis-delivers to the wrong buyer)."
        ),
        inputSchema={
            "type": "object", "required": ["input"],
            "properties": {"input": {
                "type": "object", "required": ["buyer_display_name", "chat_msg"],
                "properties": {
                    "buyer_display_name": {"type": "string",
                        "description": "Display name of the buyer the reply is for; the open chat header must match it"},
                    "chat_msg": {"type": "string", "description": "Reply text to send"},
                    "auto_open": {"type": "boolean", "default": True,
                        "description": "If the buyer's chat is not already open, search for it by name and open it first"},
                },
            }},
        },
    ))


def add_qianniu_open_session_tool_schema(tool_schemas):
    import mcp.types as types
    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="qianniu_open_session",
        description=(
            "<category>Qianniu</category><sub-category>Messaging</sub-category>"
            "Open a 千牛 (Taobao/Tmall) buyer's conversation by searching their "
            "display name, and OCR-verify the chat header. Does not send anything."
        ),
        inputSchema={
            "type": "object", "required": ["input"],
            "properties": {"input": {
                "type": "object", "required": ["buyer_display_name"],
                "properties": {"buyer_display_name": {"type": "string",
                    "description": "Display name of the buyer whose conversation to open"}},
            }},
        },
    ))


def add_qianniu_receive_tool_schema(tool_schemas):
    import mcp.types as types
    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="qianniu_receive",
        description=(
            "<category>Qianniu</category><sub-category>Messaging</sub-category>"
            "OCR the currently-open 千牛 conversation and return the visible text "
            "lines (top to bottom). Read-only."
        ),
        inputSchema={"type": "object", "properties": {
            "input": {"type": "object", "properties": {}}}},
    ))
