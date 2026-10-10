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
import asyncio
import contextlib
import json
import os
import random
import time
import traceback

import pyautogui
from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger
from agent.mcp.server.wechat.platform_utils import (
    bring_window_to_front,
    clipboard_set_text,
    paste_hotkey,
)
from agent.mcp.server.qianniu.qianniu_ocr import (
    ocr_qianniu_window,
    verify_header_name,
    header_band_texts,
    transcript_contains,
    is_reception_tab,
    find_reception_tab_point,
    find_conversation_row,
    conversation_rows,
    last_turn,
    qianniu_chat_window,
    ocr_dump,
    save_failure_shot,
    _norm,
)

# A message this short ("在吗", "你好") is too common to identify a buyer by
# body text alone: two buyers may both have sent it. Without a header-name
# match, a send keyed on such a text is refused (fail-closed).
_MIN_BODY_ID_CHARS = 4
_LOCK_WAIT_S = 45.0   # a send waits this long for the desktop (cold-start sweep) before failing

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
    # The 接待中心 chat window first (not the 千牛工作台 home) -- shared with the OCR
    # capture so the window we focus is the window we read.
    from agent.mcp.server.qianniu.qianniu_ocr import qianniu_chat_window
    return qianniu_chat_window()


def _is_front(win) -> bool:
    """True if *win* (the 千牛 chat window) is the foreground window. Unknown
    (no hwnd / not Windows) counts as front -- nothing better to check."""
    hwnd = getattr(win, "hwnd", None)
    if not hwnd:
        return True
    try:
        import ctypes
        user32 = ctypes.windll.user32
        fg = user32.GetForegroundWindow()
        return bool(fg) and (fg == hwnd or user32.GetAncestor(fg, 3) == hwnd)   # 3 = GA_ROOTOWNER
    except Exception:
        return True


def _ensure_front(what: str) -> None:
    """Make sure 千牛 is in front right before *what* (a click / paste / Enter).
    飞鸽 and 拼多多 raise Chrome (Page.bringToFront) at any moment on the same
    desktop (alpha 2026-10-08: a 千牛 screen read caught the 抖店 window). Re-
    foreground once; if 千牛 is still not in front, raise -- never type or click
    into another app."""
    win = _find_window()
    if _is_front(win):
        return
    logger.warning(f"[qianniu] another window is in front before {what}; bringing 千牛 back")
    if win is not None:
        bring_window_to_front(win)
        time.sleep(0.3)
    if not _is_front(_find_window()):
        raise RuntimeError(f"千牛 is not the foreground window before {what}; not acting")


def _foreground() -> bool:
    """Bring 千牛 to the foreground. False if the window isn't found."""
    win = _find_window()
    if not win:
        from agent.mcp.server.qianniu.qianniu_ocr import QIANNIU_WIN_TITLES
        logger.warning(f"[qianniu] window not found (titles {list(QIANNIU_WIN_TITLES)}); is 千牛 running?")
        return False
    bring_window_to_front(win)
    _humanize(_POST_ACTION_DELAY)
    logger.info(f"[qianniu] foregrounded window {getattr(win, 'title', win)!r}")
    return True


def _looks_like_qianniu(ocr_data: list) -> bool:
    """Layout-drift guard: the window must show at least one expected anchor
    before we click anything. Fail-closed on an unrecognised layout."""
    if not ocr_data:
        return False
    blob = " ".join(str(it.get("text") or "") for it in ocr_data).lower()
    return any(a in blob for a in _QIANNIU_MARKS)


# Text only 千牛's chat window shows. "发送"/"搜索" are not enough: 抖店's Chrome
# page has them too, and a read that caught Chrome over 千牛 passed as 千牛.
_QIANNIU_MARKS = ("正在接待", "接待中心", "千牛", "阿里旺旺")


def _read_qianniu() -> list:
    """A screen read of 千牛 -- re-taken once after bringing 千牛 back to the
    front when the first read does not look like 千牛 (another app on top)."""
    ocr_data = ocr_qianniu_window()
    if _looks_like_qianniu(ocr_data):
        return ocr_data
    logger.warning(f"[qianniu] the screen read is not 千牛 (another window on top?); "
                   f"bringing 千牛 to the front and reading again: {ocr_dump(ocr_data, limit=12)}")
    _foreground()
    return ocr_qianniu_window()


@contextlib.contextmanager
def _no_corner_failsafe():
    """PyAutoGUI aborts any action while the mouse rests in a screen corner
    (its "fail-safe"). On an unattended 千牛 desk that only means someone left
    the mouse there -- alpha 2026-10-07: a reply was lost to
    FailSafeException mid-send. Off while our own desktop actions run."""
    prev = pyautogui.FAILSAFE
    pyautogui.FAILSAFE = False
    try:
        yield
    finally:
        pyautogui.FAILSAFE = prev


def _click(x: int, y: int) -> None:
    _ensure_front(f"click at ({x}, {y})")
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
    _ensure_front("pasting the reply")
    paste_hotkey()
    _humanize(_POST_TYPE_DELAY)
    _ensure_front("pressing Enter to send")
    pyautogui.press("enter")
    _humanize(_POST_ACTION_DELAY)


def _open_conversation_by_name(name: str) -> tuple:
    """Search-by-name to open buyer *name*'s conversation, then OCR-verify the
    header. Returns (opened_and_verified: bool, header_text: str, error: str).

    千牛 has no stable conversation id we can address, so the display name is
    the only durable key (study §5). Assumes 千牛 is already foregrounded.
    """
    ocr_data = _read_qianniu()
    if not _looks_like_qianniu(ocr_data):
        logger.warning(f"[qianniu] open {name!r}: layout not recognised; screen {ocr_dump(ocr_data)}")
        save_failure_shot("open_layout_unrecognised")
        return False, "", "layout not recognised as 千牛 (OCR drift); aborting"
    box = _find_search_box(ocr_data)
    if not box:
        logger.warning(f"[qianniu] open {name!r}: no search box (anchors {_SEARCH_ANCHORS}); "
                       f"screen {ocr_dump(ocr_data)}")
        save_failure_shot("open_no_search_box")
        return False, "", "search box not found via OCR; cannot open by name"
    logger.info(f"[qianniu] open {name!r}: clicking search box at {box}, typing the name + Enter")
    _click(box[0], box[1])
    _humanize(_POST_TYPE_DELAY)
    clipboard_set_text(name)
    paste_hotkey()
    _humanize(_POST_TYPE_DELAY)
    pyautogui.press("enter")
    _humanize(_SETTLE_AFTER_OPEN)
    v = verify_header_name(name)
    if v.matched:
        logger.info(f"[qianniu] open {name!r}: opened, header {v.header_text!r}")
        return True, v.header_text, ""
    return False, v.header_text, (f"opened by search but header {v.header_text!r} "
                                  f"does not match {name!r}")


def _open_conversation_by_preview(text: str, ocr_data: list = None, frame_out: list = None) -> tuple:
    """Open the 正在接待 conversation whose list PREVIEW shows *text*, then
    confirm *text* is in the chat BODY (the standalone bot's proven hidden-
    conversation route: no buyer name or search needed). Returns
    (opened_and_verified, buyer_name_from_list, error). Assumes 千牛 is
    foregrounded and the caller holds the desktop lock. *ocr_data*: the
    caller's fresh frame (each OCR costs ~6 s on the customer PC);
    *frame_out* receives the post-click frame, so the caller need not re-read."""
    if not ocr_data:
        ocr_data = _read_qianniu()
    if not _looks_like_qianniu(ocr_data):
        logger.warning(f"[qianniu] open by preview {text[:16]!r}: layout not recognised; "
                       f"screen {ocr_dump(ocr_data)}")
        save_failure_shot("preview_layout_unrecognised")
        return False, "", "layout not recognised as 千牛 (OCR drift)"
    _on_tab, ocr_data = _ensure_reception_tab(ocr_data)
    pt, name = find_conversation_row(ocr_data, text)
    if not pt:
        logger.warning(f"[qianniu] open by preview {text[:16]!r}: no 正在接待 row shows it; "
                       f"screen {ocr_dump(ocr_data)}")
        save_failure_shot("preview_no_row")
        return False, "", "no 正在接待 row previews this message"
    logger.info(f"[qianniu] open by preview {text[:16]!r}: clicking row at {pt} (list name {name!r})")
    _click(pt[0], pt[1])
    _humanize(_SETTLE_AFTER_OPEN)
    ocr_data = _read_qianniu()
    if frame_out is not None:
        frame_out.append(ocr_data)
    if transcript_contains(ocr_data, text):
        logger.info(f"[qianniu] open by preview {text[:16]!r}: opened, message is in the chat body")
        return True, name, ""
    logger.warning(f"[qianniu] open by preview {text[:16]!r}: clicked but the message is not in "
                   f"the chat body; screen {ocr_dump(ocr_data)}")
    save_failure_shot("preview_open_not_in_body")
    return False, name, "clicked the row but the message is not in the chat body"


def _send_result(sent: bool, verified: bool, error: str, header: str = "") -> list:
    return [TextContent(type="text", text=json.dumps({
        "chat_sent": sent, "verified": verified, "error": error,
        "header_name": header,
    }, ensure_ascii=False, default=str))]


def _lock():
    from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat.typing_lock import get_lock
    return get_lock()


async def qianniu_send(mainwin, args):
    """Send a text reply to one buyer in 千牛 — fail-closed, never to the wrong buyer.

    Which conversation is "the buyer's" is decided by one of two identities:

    * ``expect_message_text`` given (the buyer's own latest message — the
      normal case): the open chat's BODY must show it (strict prefix, chat body
      only; the 正在接待 list does not count). If it does not and ``auto_open``
      is set, the conversation whose 正在接待 PREVIEW shows it is opened (works
      with no buyer name — the hidden-conversation route the standalone bot
      proved), else, with a name, the buyer is searched by name. A text shorter
      than ``_MIN_BODY_ID_CHARS`` ("在吗") is too common to identify a buyer, so
      it also needs the header to name ``buyer_display_name``.
    * no expect text: the header must name ``buyer_display_name`` (search by
      name to open it).

    Input:
        buyer_display_name: str  — the buyer (may be "" when expect_message_text is given)
        chat_msg: str            — the reply text
        auto_open: bool          — open the buyer's conversation if it is not the open one (default true)
        expect_message_text: str — the buyer's message this reply answers

    Output (JSON): chat_sent, verified, header_name, error.
    """
    lock = _lock()
    holder = f"send:{id(args)}"
    try:
        inp = args.get("input", args)
        buyer = (inp.get("buyer_display_name") or "").strip()
        msg = inp.get("chat_msg") or ""
        auto_open = inp.get("auto_open", True)
        expect_text = (inp.get("expect_message_text") or "").strip()
        logger.info(f"[qianniu_send] start buyer={buyer!r} auto_open={auto_open} "
                    f"expect={expect_text[:24]!r} msg_len={len(msg)}: {msg[:40]!r}")
        if not msg:
            logger.warning(f"[qianniu_send] refused: empty chat_msg for {buyer!r}")
            return _send_result(False, False, "chat_msg is required")
        if not buyer and not expect_text:
            logger.warning("[qianniu_send] refused: neither buyer_display_name nor expect_message_text")
            return _send_result(False, False,
                                "buyer_display_name or expect_message_text is required")

        # Serialize all desktop action so two sends never interleave on the one
        # shared window (study Phase 3). Wait for it (the startup cold-start
        # sweep holds it one chat at a time) rather than lose the reply.
        waited = 0.0
        while not lock.try_acquire(holder) and waited < _LOCK_WAIT_S:
            await asyncio.sleep(0.5)
            waited += 0.5
        if lock.holder() != holder:
            logger.warning(f"[qianniu_send] busy: desktop lock held by {lock.holder()!r}; "
                           f"not sent to {buyer or expect_text[:16]!r}")
            return _send_result(False, False, f"another send is in progress (holder {lock.holder()!r})")

        with _no_corner_failsafe():
            return _send_locked(buyer, msg, auto_open, expect_text)
    except Exception as e:
        logger.error(f"[qianniu_send] {traceback.format_exc()}")
        return _send_result(False, False, str(e))
    finally:
        lock.release(holder)


def _send_locked(buyer: str, msg: str, auto_open, expect_text: str) -> list:
    """qianniu_send's desktop part; the caller holds the desktop lock."""
    if not _foreground():
        return _send_result(False, False, "千牛 window not found. Is it running?")

    short = bool(expect_text) and len(_norm(expect_text)) < _MIN_BODY_ID_CHARS

    def identify(ocr_data):
        """(is the buyer's chat, body_ok, header result or None)."""
        hdr = verify_header_name(buyer, ocr_data, quiet=bool(expect_text)) if buyer else None
        if expect_text:
            body = transcript_contains(ocr_data, expect_text)
            return body and (not short or bool(hdr and hdr.matched)), body, hdr
        return bool(hdr and hdr.matched), False, hdr

    ocr_data = _read_qianniu()
    ok, body_ok, hdr = identify(ocr_data)
    route = "already open"
    if not ok and auto_open:
        opened, err, frames = False, "", []
        if expect_text:
            opened, list_name, err = _open_conversation_by_preview(expect_text, ocr_data, frames)
            route = f"opened by preview (list name {list_name!r})"
        if not opened and buyer:
            frames = []
            opened, _header, err = _open_conversation_by_name(buyer)
            route = "opened by name search"
        if not opened:
            logger.warning(f"[qianniu_send] ABORT: could not open the buyer's chat "
                           f"(buyer={buyer!r} expect={expect_text[:16]!r}): {err}")
            return _send_result(False, False, f"could not open the buyer's chat: {err}")
        # Re-verify after the switch -- on the frame the preview route just read
        # (a fresh read costs ~6 s), else a new one.
        ocr_data = frames[-1] if frames else _read_qianniu()
        ok, body_ok, hdr = identify(ocr_data)
    header_text = hdr.header_text if hdr else ""
    if not ok:
        if expect_text and body_ok and short:
            why = (f"{expect_text!r} is too short to identify the buyer by text alone and the "
                   f"header does not show {buyer!r}")
        elif expect_text:
            why = f"{expect_text[:24]!r} is not in the open chat body"
        else:
            why = f"open chat header {header_text!r} does not match {buyer!r}"
        logger.warning(f"[qianniu_send] ABORT: {why} — refusing to send; screen {ocr_dump(ocr_data)}")
        save_failure_shot("send_not_identified")
        return _send_result(False, False, f"{why} — refusing to send", header_text)

    _type_and_send(msg)
    logger.info(f"[qianniu_send] sent ({route}; body={body_ok} header={header_text!r}) "
                f"buyer={buyer!r}: {msg[:40]!r}")
    try:   # our reply reappears in 千牛 memory looking incoming; mark it as ours
        from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat.observer import record_sent
        record_sent(msg)
    except Exception as rec_err:
        logger.warning(f"[qianniu_send] could not record the sent text: {rec_err}")
    return _send_result(True, True, "", header_text)


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
        message_text = (inp.get("message_text") or "").strip()
        logger.info(f"[qianniu_open_session] start buyer={buyer!r} message_text={message_text[:16]!r}")
        if not buyer and not message_text:
            logger.warning("[qianniu_open_session] refused: neither buyer_display_name nor message_text")
            return [TextContent(type="text", text=json.dumps(
                {"opened": False, "header_name": "",
                 "error": "buyer_display_name or message_text is required"},
                ensure_ascii=False))]
        if not lock.try_acquire(holder):
            logger.warning(f"[qianniu_open_session] busy: desktop lock held by {lock.holder()!r}")
            return [TextContent(type="text", text=json.dumps(
                {"opened": False, "header_name": "", "error": f"busy (holder {lock.holder()!r})"},
                ensure_ascii=False))]
        if not _foreground():
            return [TextContent(type="text", text=json.dumps(
                {"opened": False, "header_name": "", "error": "千牛 window not found"},
                ensure_ascii=False))]
        opened, header, err = False, "", ""
        if message_text:     # the buyer's message in the 正在接待 list: no name needed
            opened, header, err = _open_conversation_by_preview(message_text)
        if not opened and buyer:
            opened, header, err = _open_conversation_by_name(buyer)
        logger.info(f"[qianniu_open_session] buyer={buyer!r} opened={opened} header={header!r} "
                    f"error={err!r}")
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
        ocr_data = _read_qianniu()
        lines = [{"text": str(it.get("text") or ""), "loc": it.get("loc")}
                 for it in ocr_data if str(it.get("text") or "").strip()]
        logger.info(f"[qianniu_receive] {len(lines)} line(s); screen {ocr_dump(ocr_data, limit=40)}")
        return [TextContent(type="text", text=json.dumps(
            {"lines": lines, "error": ""}, ensure_ascii=False, default=str))]
    except Exception as e:
        logger.error(f"[qianniu_receive] {traceback.format_exc()}")
        return [TextContent(type="text", text=json.dumps(
            {"lines": [], "error": str(e)}, ensure_ascii=False))]


def _ensure_reception_tab(ocr_data: list) -> tuple:
    """If the left panel is not the 正在接待 list, click its tab and re-OCR.
    Returns (on_reception: bool, ocr_data: list) — the (possibly refreshed) OCR.
    """
    if is_reception_tab(ocr_data):
        return True, ocr_data
    pt = find_reception_tab_point(ocr_data)
    if not pt:
        logger.warning("[qianniu] not on the 正在接待 tab and the tab was not found by OCR")
        return False, ocr_data
    logger.info(f"[qianniu] not on the 正在接待 tab; clicking it at {pt}")
    _foreground()
    _click(pt[0], pt[1])
    _humanize(_POST_ACTION_DELAY)
    ocr_data = _read_qianniu()
    ok = is_reception_tab(ocr_data)
    logger.info(f"[qianniu] after clicking 正在接待: on_tab={ok}")
    return ok, ocr_data


async def qianniu_check_location(mainwin, args):
    """Verify 千牛 is 'in the right place' before a send: on the 正在接待 tab AND
    the intended consumer's chat thread is loaded. Read-mostly (it may click the
    正在接待 tab when ``ensure_reception_tab`` is set, but never sends).

    The thread-identity check is FAIL-CLOSED on BOTH signals: the buyer's last
    message text must appear in the chat BODY *and* the chat-header must name the
    buyer. Either missing → ``thread_ok=False`` and the caller must open/retry.

    Input:
        expect_message_text: str  — the buyer's message (body content-join check)
        buyer_display_name:  str  — the buyer (chat-header name check)
        ensure_reception_tab: bool — click 正在接待 if not already there (default true)

    Output (JSON): on_reception_tab, thread_ok, matched_by ('both'|'body'|'header'|'none'),
                   body_ok, header_ok, header_name, header_candidates, error.
    """
    try:
        inp = args.get("input", args)
        expect_text = (inp.get("expect_message_text") or "").strip()
        buyer = (inp.get("buyer_display_name") or "").strip()
        ensure_tab = inp.get("ensure_reception_tab", True)

        logger.info(f"[qianniu_check_location] start buyer={buyer!r} expect={expect_text[:24]!r} "
                    f"ensure_tab={ensure_tab}")

        def _result(on_tab, body_ok, header_ok, header_name, cands, error="", screen=None):
            matched_by = ("both" if body_ok and header_ok else
                          "body" if body_ok else "header" if header_ok else "none")
            summary = (f"[qianniu_check_location] buyer={buyer!r} on_tab={on_tab} "
                       f"matched_by={matched_by} header_name={header_name!r} "
                       f"header_band={cands[:8]} error={error!r}")
            if body_ok and header_ok:
                logger.info(summary)
            else:
                # Not a fault by itself (the LLM then opens / re-checks), but every
                # miss carries the full screen so OCR geometry can be calibrated.
                logger.warning(summary + (f"; screen {ocr_dump(screen)}" if screen else ""))
                if screen is not None:   # only a capture taken by THIS check
                    save_failure_shot(f"check_{matched_by}")
            return [TextContent(type="text", text=json.dumps({
                "on_reception_tab": on_tab,
                "thread_ok": bool(body_ok and header_ok),
                "matched_by": matched_by,
                "body_ok": body_ok, "header_ok": header_ok,
                "header_name": header_name, "header_candidates": cands[:8],
                "error": error,
            }, ensure_ascii=False, default=str))]

        if not _foreground():
            return _result(False, False, False, "", [], "千牛 window not found. Is it running?")
        ocr_data = _read_qianniu()
        if not _looks_like_qianniu(ocr_data):
            return _result(False, False, False, "", [], "layout not recognised as 千牛 (OCR drift)",
                           screen=ocr_data)

        on_tab = is_reception_tab(ocr_data)
        if not on_tab and ensure_tab:
            on_tab, ocr_data = _ensure_reception_tab(ocr_data)

        body_ok = bool(expect_text) and transcript_contains(ocr_data, expect_text)
        header_ok = False
        header_name = ""
        cands = header_band_texts(ocr_data)
        if buyer:
            v = verify_header_name(buyer, ocr_data)
            header_ok, header_name = v.matched, v.header_text
        return _result(on_tab, body_ok, header_ok, header_name, cands, screen=ocr_data)
    except Exception as e:
        logger.error(f"[qianniu_check_location] {traceback.format_exc()}")
        return [TextContent(type="text", text=json.dumps(
            {"on_reception_tab": False, "thread_ok": False, "matched_by": "none",
             "body_ok": False, "header_ok": False, "header_name": "",
             "header_candidates": [], "error": str(e)}, ensure_ascii=False))]


# --- MCP tool schemas -------------------------------------------------------

def _store_label() -> str:
    """The store's sub-account as it labels our own messages: the 接待中心 window
    title before "-接待中心" (e.g. "倪好数码:小柒")."""
    win = qianniu_chat_window()
    title = str(getattr(win, "title", "") or "")
    return title.split("-")[0].strip() if "-" in title else ""


def cold_start_sweep(dispatch, already_handled, max_rows: int = 8) -> dict:
    """Answer chats that were waiting when eCan started. 千牛's memory holds no
    buyer text for them, so the memory observer never sees them until the buyer
    writes again (alpha 2026-10-08: "冷启动出不来，得再顶一句").

    Opens each 正在接待 row (one chat per desktop-lock hold, so replies are not
    blocked for long) and asks who spoke last; when it is the buyer, calls
    ``dispatch(name, text)`` unless ``already_handled(name, text)``. Every
    decision is logged under [QIANNIU-COLD]. Returns counts."""
    stats = {"rows": 0, "dispatched": 0, "store_last": 0, "unknown": 0, "handled": 0, "skipped": 0}
    store = _store_label()
    lock = _lock()
    holder = "coldstart"
    if not lock.try_acquire(holder):
        logger.info(f"[QIANNIU-COLD] desktop busy ({lock.holder()!r}); cold-start sweep skipped")
        return stats
    try:
        with _no_corner_failsafe():
            if not _foreground():
                return stats
            _on_tab, ocr_data = _ensure_reception_tab(_read_qianniu())
            rows = conversation_rows(ocr_data, limit=max_rows)
    finally:
        lock.release(holder)
    stats["rows"] = len(rows)
    logger.info(f"[QIANNIU-COLD] sweep: store label {store!r}; {len(rows)} 正在接待 row(s): "
                f"{[(n, p[:12]) for n, p, _pt in rows]}")
    for name, preview, pt in rows:
        if not lock.try_acquire(holder):
            stats["skipped"] += 1
            logger.info(f"[QIANNIU-COLD] row {name!r}: desktop busy ({lock.holder()!r}); skipped")
            continue
        try:
            with _no_corner_failsafe():
                _foreground()
                _click(pt[0], pt[1])
                _humanize(_SETTLE_AFTER_OPEN)
                side, text = last_turn(_read_qianniu(), name, store)
        except Exception as exc:
            stats["skipped"] += 1
            logger.warning(f"[QIANNIU-COLD] row {name!r}: open/read failed: {exc}")
            continue
        finally:
            lock.release(holder)
        if side == "store":
            stats["store_last"] += 1
            logger.info(f"[QIANNIU-COLD] row {name!r}: the store spoke last; nothing to answer")
        elif side != "buyer" or not text:
            stats["unknown"] += 1
            logger.info(f"[QIANNIU-COLD] row {name!r} (preview {preview[:16]!r}): last turn not readable; "
                        f"skipped")
        elif already_handled(name, text):
            stats["handled"] += 1
            logger.info(f"[QIANNIU-COLD] row {name!r}: {text[:24]!r} already dispatched live; skipped")
        else:
            stats["dispatched"] += 1
            logger.info(f"[QIANNIU-COLD] row {name!r}: buyer spoke last {text[:30]!r} -> dispatching")
            dispatch(name, text)
    logger.info(f"[QIANNIU-COLD] sweep done: {stats}")
    return stats


def backstop_sweep(dispatch, already_handled, is_ours, checked: set, max_rows: int = 8) -> dict:
    """Periodic safety net for buyer messages the memory observer missed
    (yp alpha 2026-10-09: 大作战panda's 「这个质量怎么样」 never appeared in 千牛's
    memory and stayed unanswered -- the cold sweep runs only at startup).

    One list-only OCR of the 正在接待 list; a row is opened only when its
    preview is a message we neither sent (``is_ours``) nor dispatched
    (``already_handled``) and the (name, preview) pair was not checked before
    (``checked``, kept by the caller) -- so the seller's open chat is not
    switched on every pass. An opened row whose last turn is the buyer's is
    dispatched like a cold-start row. Returns counts."""
    stats = {"rows": 0, "opened": 0, "dispatched": 0, "skipped": 0}
    lock = _lock()
    holder = "backstop"
    if not lock.try_acquire(holder):
        return stats
    try:
        with _no_corner_failsafe():
            if not _foreground():
                return stats
            _on_tab, ocr_data = _ensure_reception_tab(_read_qianniu())
            rows = conversation_rows(ocr_data, limit=max_rows)
    finally:
        lock.release(holder)
    stats["rows"] = len(rows)
    store = _store_label()
    for name, preview, pt in rows:
        key = (name, preview)
        if key in checked:
            continue
        checked.add(key)
        if not preview or is_ours(preview) or already_handled(name, preview):
            continue
        if not lock.try_acquire(holder):
            checked.discard(key)              # look again next pass
            stats["skipped"] += 1
            continue
        try:
            with _no_corner_failsafe():
                _foreground()
                _click(pt[0], pt[1])
                _humanize(_SETTLE_AFTER_OPEN)
                side, text = last_turn(_read_qianniu(), name, store)
        except Exception as exc:
            stats["skipped"] += 1
            logger.warning(f"[QIANNIU-BACKSTOP] row {name!r}: open/read failed: {exc}")
            continue
        finally:
            lock.release(holder)
        stats["opened"] += 1
        if side == "buyer" and text and not already_handled(name, text):
            stats["dispatched"] += 1
            logger.info(f"[QIANNIU-BACKSTOP] row {name!r}: buyer message missed by the memory "
                        f"observer {text[:30]!r} -> dispatching")
            dispatch(name, text)
        else:
            logger.info(f"[QIANNIU-BACKSTOP] row {name!r} (preview {preview[:16]!r}): "
                        f"last turn {side or 'unreadable'}; nothing to answer")
    if stats["opened"] or stats["dispatched"]:
        logger.info(f"[QIANNIU-BACKSTOP] pass done: {stats}")
    return stats


def add_qianniu_send_tool_schema(tool_schemas):
    import mcp.types as types
    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="qianniu_send",
        description=(
            "<category>Qianniu</category><sub-category>Messaging</sub-category>"
            "Send a text reply to one 千牛 (Taobao/Tmall seller) buyer, fail-closed. "
            "With expect_message_text (the buyer's own message) the open chat's BODY "
            "must show it; if it does not, the conversation whose 正在接待 list preview "
            "shows it is opened first (no buyer name needed). Without it, the chat "
            "header must name buyer_display_name. Refuses on any mismatch (never "
            "mis-delivers to the wrong buyer)."
        ),
        inputSchema={
            "type": "object", "required": ["input"],
            "properties": {"input": {
                "type": "object", "required": ["chat_msg"],
                "properties": {
                    "buyer_display_name": {"type": "string",
                        "description": "Display name of the buyer, if known (may be empty when expect_message_text is given)"},
                    "chat_msg": {"type": "string", "description": "Reply text to send"},
                    "auto_open": {"type": "boolean", "default": True,
                        "description": "Open the buyer's conversation first if it is not the open one"},
                    "expect_message_text": {"type": "string",
                        "description": "The buyer's message this reply answers; identifies the buyer's conversation by its text"},
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
            "Open a 千牛 (Taobao/Tmall) buyer's conversation: by the 正在接待 row whose "
            "preview shows message_text (no name needed), else by searching "
            "buyer_display_name. OCR-verifies the result. Does not send anything."
        ),
        inputSchema={
            "type": "object", "required": ["input"],
            "properties": {"input": {
                "type": "object",
                "properties": {"message_text": {"type": "string",
                    "description": "The buyer's latest message (matched against the 正在接待 list previews)"},
                               "buyer_display_name": {"type": "string",
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


def add_qianniu_check_location_tool_schema(tool_schemas):
    import mcp.types as types
    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="qianniu_check_location",
        description=(
            "<category>Qianniu</category><sub-category>Messaging</sub-category>"
            "Verify 千牛 is in the right place before replying: on the 正在接待 tab "
            "AND the intended buyer's chat thread is loaded. Fail-closed on BOTH "
            "signals — the buyer's message must be in the chat body AND the header "
            "must name the buyer. May click the 正在接待 tab but never sends. Call "
            "this before qianniu_send; if thread_ok is false, qianniu_open_session "
            "then re-check."
        ),
        inputSchema={
            "type": "object", "required": ["input"],
            "properties": {"input": {
                "type": "object",
                "properties": {
                    "expect_message_text": {"type": "string",
                        "description": "The buyer's message text to confirm in the chat body"},
                    "buyer_display_name": {"type": "string",
                        "description": "The buyer whose name the chat header must show"},
                    "ensure_reception_tab": {"type": "boolean",
                        "description": "Click the 正在接待 tab if not already there (default true)"},
                },
            }},
        },
    ))
