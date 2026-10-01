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
)

_QIANNIU_WIN_TITLES = ["千牛", "AliWorkbench", "阿里旺旺"]
_POST_ACTION_DELAY = 0.6
_POST_TYPE_DELAY = 0.5


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
    time.sleep(_POST_ACTION_DELAY)
    return True


def _type_and_send(text: str) -> None:
    """Clipboard → Ctrl+V → Enter (study §4.4: Enter sends, not the button)."""
    clipboard_set_text(text)
    paste_hotkey()
    time.sleep(_POST_TYPE_DELAY)
    pyautogui.press("enter")
    time.sleep(_POST_ACTION_DELAY)


def _send_result(sent: bool, verified: bool, error: str, header: str = "") -> list:
    return [TextContent(type="text", text=json.dumps({
        "chat_sent": sent, "verified": verified, "error": error,
        "header_name": header,
    }, ensure_ascii=False, default=str))]


async def qianniu_send(mainwin, args):
    """Send a text reply to the currently-open 千牛 conversation, after OCR-
    verifying its chat header names the intended buyer.

    Input:
        buyer_display_name: str — the buyer the reply is FOR (header must match)
        chat_msg: str           — the reply text

    Output (JSON): chat_sent, verified (header matched), header_name, error.
    """
    try:
        inp = args.get("input", args)
        buyer = (inp.get("buyer_display_name") or "").strip()
        msg = inp.get("chat_msg") or ""
        if not buyer:
            return _send_result(False, False, "buyer_display_name is required")
        if not msg:
            return _send_result(False, False, "chat_msg is required")

        if not _foreground():
            return _send_result(False, False, "千牛 window not found. Is it running?")

        # Fail-closed guard: the open conversation MUST be this buyer.
        v = verify_header_name(buyer)
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
                },
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
