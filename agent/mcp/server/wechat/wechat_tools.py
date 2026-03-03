"""
WeChat automation tools — higher-level RPA primitives that wrap
screen-capture + OCR + mouse/keyboard into single tool calls.

Tools:
  wechat_send   — open a chat by name and send a text message (+ optional attachments)
  wechat_receive — open a chat by name and read new messages since a known last-sent message
"""

import asyncio
import json
import re
import time
import os

import pyautogui
import mcp.types as types
from mcp.types import CallToolResult, TextContent

from utils.logger_helper import logger_helper as logger
from agent.mcp.server.wechat.platform_utils import (
    find_windows_by_title,
    bring_window_to_front,
    clipboard_set_text,
    clipboard_set_file,
    paste_hotkey,
    WindowInfo,
)
from agent.mcp.server.wechat.scroll_calibration import calibrate_scroll

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_WECHAT_WIN_TITLES = ["WeChat", "微信", "Weixin"]
_WECHAT_WIN_KW = "Weixin"  # actual Windows title is Pinyin "Weixin"
_MAX_OCR_RETRIES = 2
_SCROLL_UNITS = 3
_POST_ACTION_DELAY = 0.6
_POST_CLICK_DELAY = 0.8
_POST_TYPE_DELAY = 0.5
_POST_SCROLL_DELAY = 0.8


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_wechat_window():
    """Return the best WeChat WindowInfo or None (cross-platform)."""
    logger.debug(f"[wechat] Searching for WeChat window with titles: {_WECHAT_WIN_TITLES}")
    wins = find_windows_by_title(_WECHAT_WIN_TITLES)
    if wins:
        w = wins[0]
        logger.debug(f"[wechat] Found WeChat window: title='{w.title}', pos=({w.left},{w.top}), size={w.width}x{w.height}")
        return w
    logger.debug("[wechat] No WeChat window found")
    return None


def _bring_to_front(win):
    """Bring a WindowInfo to the foreground (cross-platform)."""
    logger.debug(f"[wechat] Bringing to front: '{win.title}'")
    bring_window_to_front(win)


async def _do_ocr(mainwin, use_local=True):
    """Run OCR on the WeChat window. Returns OCR data list (absolute coords).

    Args:
        mainwin: main window reference (needed for remote OCR session/token)
        use_local: if True (default), use local RapidOCR; if False, use remote server
    """
    if use_local:
        return await _do_ocr_local()

    # --- Remote OCR (fallback) ---
    from agent.mcp.server.server import _screen_read, _ocr_semaphore
    logger.debug(f"[wechat] Starting OCR on window keyword='{_WECHAT_WIN_KW}'")
    async with _ocr_semaphore:
        result = await _screen_read(mainwin, _WECHAT_WIN_KW)
    item_count = len(result) if isinstance(result, list) else 0
    logger.debug(f"[wechat] OCR complete: {item_count} items returned")
    _log_ocr_result(result)
    return result


_OCR_MAX_LONG_SIDE = 1500  # resize screenshots to this max dimension before OCR


async def _do_ocr_local():
    """Run local OCR on the WeChat window using RapidOCR (ONNX Runtime).
    Returns OCR data list (absolute screen coords) in remote-server format.
    """
    import tempfile
    from agent.ec_skills.ocr.image_prep import captureScreen, _apply_window_offset
    from agent.mcp.server.local_ocr.paddle_ocr import run_ocr_on_image, scale_ocr_coordinates

    logger.debug(f"[wechat] Starting LOCAL OCR on window keyword='{_WECHAT_WIN_KW}'")

    screen_img, image_bytes, window_rect = captureScreen(_WECHAT_WIN_KW)
    orig_w, orig_h = screen_img.size
    logger.debug(f"[wechat] Screenshot captured: size=({orig_w},{orig_h}), window_rect={window_rect}")

    # Resize to speed up OCR — scale coordinates back afterwards
    scale_x, scale_y = 1.0, 1.0
    long_side = max(orig_w, orig_h)
    if long_side > _OCR_MAX_LONG_SIDE:
        ratio = _OCR_MAX_LONG_SIDE / long_side
        new_w = int(orig_w * ratio)
        new_h = int(orig_h * ratio)
        screen_img = screen_img.resize((new_w, new_h))
        scale_x = orig_w / new_w
        scale_y = orig_h / new_h
        logger.debug(f"[wechat] Resized for OCR: ({orig_w},{orig_h}) -> ({new_w},{new_h}), "
                     f"scale=({scale_x:.3f},{scale_y:.3f})")

    tmp_file = os.path.join(tempfile.gettempdir(), "wechat_ocr_tmp.png")
    screen_img.save(tmp_file)

    ocr_result = run_ocr_on_image(tmp_file)
    if ocr_result.get("status") != "success":
        logger.error(f"[wechat] Local OCR failed: {ocr_result.get('error')}")
        return []

    result = ocr_result.get("ocr_data", [])

    # Scale coordinates from resized image back to original resolution
    if scale_x != 1.0 or scale_y != 1.0:
        result = scale_ocr_coordinates(result, scale_x, scale_y)

    result = _apply_window_offset(result, window_rect)

    item_count = len(result) if isinstance(result, list) else 0
    logger.debug(f"[wechat] Local OCR complete: {item_count} items returned")
    _log_ocr_result(result)
    return result


def _validate_wechat_ocr(ocr_data):
    """Validate that OCR data looks like a WeChat window.

    Requires at least one of:
      - 'Search' or '搜索' text detected
      - 'Send(S)' or '发送(S)' text detected
      - 3+ vertically aligned timestamps (hh:mm pattern)

    Returns (valid: bool, reason: str).
    """
    if not ocr_data or not isinstance(ocr_data, list):
        return False, "OCR returned no data"

    all_texts = []
    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        t = (item.get("text") or "").strip().lower()
        if t:
            all_texts.append(t)
        for ts in item.get("txt_struct", []):
            if isinstance(ts, dict):
                tst = (ts.get("text") or "").strip().lower()
                if tst:
                    all_texts.append(tst)

    # Check for Search
    for t in all_texts:
        if "search" in t or "搜索" in t:
            logger.debug("[wechat] _validate_wechat_ocr: PASS — found Search")
            return True, "found Search"

    # Check for Send button
    for t in all_texts:
        if "send(s)" in t or "发送(s)" in t or t == "send" or t == "发送":
            logger.debug("[wechat] _validate_wechat_ocr: PASS — found Send")
            return True, "found Send"

    # Check for vertically aligned timestamps
    timestamps = _find_timestamps_in_ocr(ocr_data)
    if len(timestamps) >= 3:
        # Verify roughly vertically aligned (x coords within 60px of each other)
        xs = [ts[1] for ts in timestamps]  # center_x values
        x_spread = max(xs) - min(xs)
        if x_spread < 60:
            logger.debug(f"[wechat] _validate_wechat_ocr: PASS — found {len(timestamps)} aligned timestamps")
            return True, f"found {len(timestamps)} aligned timestamps"

    logger.warning(f"[wechat] _validate_wechat_ocr: FAIL — no WeChat landmarks in {len(all_texts)} text items")
    return False, "OCR data does not contain WeChat landmarks (Search, Send, or timestamps)"


def _log_ocr_result(result):
    """Log OCR result summary for debugging."""
    if not isinstance(result, list):
        return
    for idx, item in enumerate(result):
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        loc = item.get("loc")
        ts_summary = []
        for ts in item.get("txt_struct", []):
            ts_text = (ts.get("text") or "").strip()
            ts_box = ts.get("box")
            ts_summary.append(f"  ts='{ts_text[:30]}' box={ts_box}")
        loc_str = f"loc={loc}" if loc else "loc=None"
        logger.debug(f"[wechat] OCR[{idx}]: '{text[:50]}' {loc_str}")
        for ts_line in ts_summary:
            logger.debug(f"[wechat] OCR[{idx}]{ts_line}")


def _find_text_in_ocr(ocr_data, target_text):
    """Search OCR result for a text entry containing target_text.
    Returns (center_x, center_y) of the best match or None.
    Tries word-level boxes first for precision, then paragraph-level loc.
    """
    logger.debug(f"[wechat] _find_text_in_ocr: searching for '{target_text}'")
    if not ocr_data or not isinstance(ocr_data, list):
        logger.debug("[wechat] _find_text_in_ocr: ocr_data is empty or not a list")
        return None

    target_lower = target_text.strip().lower()

    # Pass 1: word-level boxes in txt_struct
    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        for ts in item.get("txt_struct", []):
            if not isinstance(ts, dict):
                continue
            ts_text = (ts.get("text") or "").strip().lower()
            if target_lower in ts_text:
                box = ts.get("box")  # [x1, y1, x2, y2]
                if box and len(box) == 4:
                    cx = (box[0] + box[2]) // 2
                    cy = (box[1] + box[3]) // 2
                    logger.debug(f"[wechat] _find_text_in_ocr: MATCH (txt_struct) '{ts_text}' -> ({cx},{cy})")
                    return (cx, cy)
            for word in ts.get("words", []):
                if not isinstance(word, dict):
                    continue
                wt = (word.get("text") or "").strip().lower()
                if target_lower == wt or target_lower in wt:
                    wbox = word.get("box")
                    if wbox and len(wbox) == 4:
                        cx = (wbox[0] + wbox[2]) // 2
                        cy = (wbox[1] + wbox[3]) // 2
                        logger.debug(f"[wechat] _find_text_in_ocr: MATCH (word) '{wt}' -> ({cx},{cy})")
                        return (cx, cy)

    # Pass 2: paragraph-level text field + loc [y1, x1, y2, x2]
    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip().lower()
        if target_lower in text:
            loc = item.get("loc")
            if loc and len(loc) == 4:
                # loc is [y1, x1, y2, x2]
                cx = (loc[1] + loc[3]) // 2
                cy = (loc[0] + loc[2]) // 2
                logger.debug(f"[wechat] _find_text_in_ocr: MATCH (paragraph) '{text[:40]}' -> ({cx},{cy})")
                return (cx, cy)

    logger.debug(f"[wechat] _find_text_in_ocr: NO MATCH for '{target_text}'")
    return None


def _find_send_button(ocr_data):
    """Find the Send button / 发送 / Send(S) in OCR data.
    Returns (center_x, center_y, box_width, box_height) or None."""
    send_keywords = ["send(s)", "发送(s)", "send", "发送"]
    logger.debug(f"[wechat] _find_send_button: searching for send button keywords={send_keywords}")
    if not ocr_data:
        logger.debug("[wechat] _find_send_button: no OCR data")
        return None
    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        for ts in item.get("txt_struct", []):
            if not isinstance(ts, dict):
                continue
            ts_text = (ts.get("text") or "").strip().lower()
            for kw in send_keywords:
                if kw in ts_text:
                    box = ts.get("box")  # [x1, y1, x2, y2]
                    if box and len(box) == 4:
                        bw = box[2] - box[0]
                        bh = box[3] - box[1]
                        cx = (box[0] + box[2]) // 2
                        cy = (box[1] + box[3]) // 2
                        logger.debug(f"[wechat] _find_send_button: FOUND (txt_struct) at ({cx},{cy}), size={bw}x{bh}")
                        return (cx, cy, bw, bh)
        # paragraph level
        text = (item.get("text") or "").strip().lower()
        for kw in send_keywords:
            if kw in text:
                loc = item.get("loc")
                if loc and len(loc) == 4:
                    bw = loc[3] - loc[1]
                    bh = loc[2] - loc[0]
                    cx = (loc[1] + loc[3]) // 2
                    cy = (loc[0] + loc[2]) // 2
                    logger.debug(f"[wechat] _find_send_button: FOUND (paragraph) at ({cx},{cy}), size={bw}x{bh}")
                    return (cx, cy, bw, bh)
    logger.debug("[wechat] _find_send_button: NOT FOUND")
    return None


def _find_search_box(ocr_data):
    """Find the Search / 搜索 text in the WeChat window.
    Returns (center_x, center_y) or None."""
    search_keywords = ["search", "搜索"]
    logger.debug(f"[wechat] _find_search_box: searching for search box keywords={search_keywords}")
    if not ocr_data:
        logger.debug("[wechat] _find_search_box: no OCR data")
        return None
    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        for ts in item.get("txt_struct", []):
            if not isinstance(ts, dict):
                continue
            ts_text = (ts.get("text") or "").strip().lower()
            for kw in search_keywords:
                if kw in ts_text:
                    box = ts.get("box")
                    if box and len(box) == 4:
                        cx = (box[0] + box[2]) // 2
                        cy = (box[1] + box[3]) // 2
                        logger.debug(f"[wechat] _find_search_box: FOUND at ({cx},{cy})")
                        return (cx, cy)
        text = (item.get("text") or "").strip().lower()
        for kw in search_keywords:
            if kw in text:
                loc = item.get("loc")
                if loc and len(loc) == 4:
                    cx = (loc[1] + loc[3]) // 2
                    cy = (loc[0] + loc[2]) // 2
                    logger.debug(f"[wechat] _find_search_box: FOUND (paragraph) at ({cx},{cy})")
                    return (cx, cy)
    logger.debug("[wechat] _find_search_box: NOT FOUND")
    return None


def _find_icon_in_ocr(ocr_data, icon_keywords):
    """Find an icon/emoji element in OCR data by matching icon description keywords.
    Icons in OCR often appear as short text items or special characters.
    Returns (center_x, center_y, box) or None.
    box is [x1, y1, x2, y2] if from txt_struct, or derived from loc.
    """
    if not ocr_data:
        return None
    for kw in icon_keywords:
        kw_lower = kw.strip().lower()
        for item in ocr_data:
            if not isinstance(item, dict):
                continue
            for ts in item.get("txt_struct", []):
                if not isinstance(ts, dict):
                    continue
                ts_text = (ts.get("text") or "").strip().lower()
                if kw_lower in ts_text or ts_text in kw_lower:
                    box = ts.get("box")
                    if box and len(box) == 4:
                        cx = (box[0] + box[2]) // 2
                        cy = (box[1] + box[3]) // 2
                        logger.debug(f"[wechat] _find_icon_in_ocr: MATCH '{ts_text}' for kw='{kw}' -> ({cx},{cy}) box={box}")
                        return (cx, cy, box)
            text = (item.get("text") or "").strip().lower()
            if kw_lower in text or text in kw_lower:
                loc = item.get("loc")
                if loc and len(loc) == 4:
                    cx = (loc[1] + loc[3]) // 2
                    cy = (loc[0] + loc[2]) // 2
                    box = [loc[1], loc[0], loc[3], loc[2]]  # convert loc to [x1,y1,x2,y2]
                    logger.debug(f"[wechat] _find_icon_in_ocr: MATCH '{text}' for kw='{kw}' -> ({cx},{cy}) box={box}")
                    return (cx, cy, box)
    logger.debug(f"[wechat] _find_icon_in_ocr: NOT FOUND for keywords={icon_keywords}")
    return None


_TIMESTAMP_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _find_timestamps_in_ocr(ocr_data):
    """Find all OCR items whose text matches the chat timestamp pattern hh:mm.

    Returns a list of (text, center_x, center_y, box) sorted by center_y
    descending (bottommost first).  box is [x1, y1, x2, y2].
    """
    results = []
    if not ocr_data or not isinstance(ocr_data, list):
        return results

    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        # Check txt_struct level
        for ts in item.get("txt_struct", []):
            if not isinstance(ts, dict):
                continue
            ts_text = (ts.get("text") or "").strip()
            if _TIMESTAMP_RE.match(ts_text):
                box = ts.get("box")
                if box and len(box) == 4:
                    cx = (box[0] + box[2]) // 2
                    cy = (box[1] + box[3]) // 2
                    results.append((ts_text, cx, cy, list(box)))
        # Check paragraph level
        text = (item.get("text") or "").strip()
        if _TIMESTAMP_RE.match(text):
            loc = item.get("loc")
            if loc and len(loc) == 4:
                cx = (loc[1] + loc[3]) // 2
                cy = (loc[0] + loc[2]) // 2
                box = [loc[1], loc[0], loc[3], loc[2]]
                # Avoid duplicates from txt_struct pass
                if not any(r[1] == cx and r[2] == cy for r in results):
                    results.append((text, cx, cy, box))

    results.sort(key=lambda r: r[2], reverse=True)  # bottommost first
    if results:
        logger.debug(f"[wechat] _find_timestamps_in_ocr: found {len(results)} timestamps, "
                     f"bottommost='{results[0][0]}' at cy={results[0][2]}")
    else:
        logger.debug("[wechat] _find_timestamps_in_ocr: no timestamps found")
    return results


def _find_chat_panel_bounds(ocr_data, win):
    """Detect the chat thread panel bounds from OCR anchor points.

    Anchors (WeChat chat page):
      - "Search" text → defines top bound of chat panel
      - "Send(S)" / "发送(S)" → defines right bound
      - Smiley / emoji icon (😊 or similar) → defines bottom-left bound

    Fallback (when smiley not detected):
      - Find chat timestamps (hh:mm format) in OCR data.
      - The bottommost timestamp's box right-edge → left bound.
      - All text to the right of that left bound and above Send(S) →
        the lowest such text defines the bottom bound.

    Args:
        ocr_data: OCR result list
        win: WindowInfo for fallback geometry

    Returns:
        dict(top, bottom, left, right) in absolute screen pixels.
    """
    logger.debug("[wechat] _find_chat_panel_bounds: detecting chat panel region")

    # Find "Search" → top boundary
    search_pos = _find_search_box(ocr_data)
    search_y = search_pos[1] if search_pos else None

    # Find "Send(S)" → right boundary
    send_info = _find_send_button(ocr_data)
    send_x = None
    send_y = None
    if send_info:
        send_x = send_info[0] + send_info[2] // 2  # right edge ≈ cx + half width
        send_y = send_info[1]

    # Find smiley icon → bottom-left boundary
    smiley_keywords = ["😊", "☺", "😄", "🙂", "smiley", "emoji", "表情"]
    smiley_info = _find_icon_in_ocr(ocr_data, smiley_keywords)
    smiley_x = smiley_info[0] if smiley_info else None
    smiley_y = smiley_info[1] if smiley_info else None

    # --- Timestamp fallback when smiley is NOT detected ---
    ts_left = None
    ts_bottom = None
    if smiley_info is None:
        logger.debug("[wechat] _find_chat_panel_bounds: smiley not found, trying timestamp fallback")
        timestamps = _find_timestamps_in_ocr(ocr_data)
        if timestamps:
            # Bottommost timestamp → its box right-edge defines left bound
            _ts_text, _ts_cx, _ts_cy, ts_box = timestamps[0]
            ts_left = ts_box[2]  # x2 = right edge of timestamp box
            logger.debug(f"[wechat] _find_chat_panel_bounds: bottommost timestamp "
                         f"'{_ts_text}' box={ts_box} → ts_left={ts_left}")

            # Find the lowest text that is:
            #   (a) to the right of ts_left, AND
            #   (b) above Send(S) (if known)
            send_y_limit = send_y if send_y else 99999
            lowest_cy = None
            for item in ocr_data:
                if not isinstance(item, dict):
                    continue
                for ts in item.get("txt_struct", []):
                    box = ts.get("box")
                    if not box or len(box) != 4:
                        continue
                    item_cx = (box[0] + box[2]) // 2
                    item_cy = (box[1] + box[3]) // 2
                    if item_cx > ts_left and item_cy < send_y_limit:
                        if lowest_cy is None or item_cy > lowest_cy:
                            lowest_cy = item_cy
                # Also check paragraph-level loc
                loc = item.get("loc")
                if loc and len(loc) == 4:
                    item_cx = (loc[1] + loc[3]) // 2
                    item_cy = (loc[0] + loc[2]) // 2
                    if item_cx > ts_left and item_cy < send_y_limit:
                        if lowest_cy is None or item_cy > lowest_cy:
                            lowest_cy = item_cy

            if lowest_cy is not None:
                ts_bottom = lowest_cy + 10  # small padding below the lowest text
                logger.debug(f"[wechat] _find_chat_panel_bounds: timestamp fallback → "
                             f"ts_bottom={ts_bottom} (lowest text cy={lowest_cy})")
            else:
                logger.debug("[wechat] _find_chat_panel_bounds: no text found right of timestamp for bottom")

    # Build bounds from whatever anchors we found, with fallbacks
    if win:
        fallback_top = win.top + 60
        fallback_bottom = win.top + win.height - 150
        fallback_left = win.left + int(win.width * 0.3)
        fallback_right = win.left + win.width - 20
    else:
        fallback_top = 100
        fallback_bottom = 800
        fallback_left = 400
        fallback_right = 1200

    top = (search_y + 20) if search_y else fallback_top

    # Left bound priority: smiley > timestamp fallback > window geometry
    if smiley_x is not None:
        left = smiley_x - 30
    elif ts_left is not None:
        left = ts_left + 5  # slight padding right of the timestamp box
    else:
        left = fallback_left

    # Bottom bound priority: smiley > timestamp fallback > send_y offset > window geometry
    if smiley_y is not None:
        bottom = smiley_y - 10
    elif ts_bottom is not None:
        bottom = ts_bottom
    elif send_y is not None:
        bottom = send_y - 30
    else:
        bottom = fallback_bottom

    right = (send_x + 10) if send_x else fallback_right

    bounds = {"top": top, "bottom": bottom, "left": left, "right": right}
    logger.info(f"[wechat] _find_chat_panel_bounds: "
                f"search_y={search_y}, send_xy=({send_x},{send_y}), "
                f"smiley_xy=({smiley_x},{smiley_y}), ts_left={ts_left}, ts_bottom={ts_bottom} "
                f"→ bounds={bounds}")
    return bounds


def _extract_chat_messages(ocr_data):
    """Extract visible chat messages from OCR data.
    Returns a list of message strings (order: top to bottom on screen)."""
    if not ocr_data or not isinstance(ocr_data, list):
        logger.debug("[wechat] _extract_chat_messages: no OCR data")
        return []
    messages = []
    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if text:
            messages.append(text)
    logger.debug(f"[wechat] _extract_chat_messages: extracted {len(messages)} messages")
    return messages


def _click(x, y, clicks=1, interval=0.1):
    """Move to (x,y) and click."""
    logger.debug(f"[wechat] _click: ({x},{y}) clicks={clicks}")
    pyautogui.moveTo(x, y)
    time.sleep(0.2)
    pyautogui.click(x, y, clicks=clicks, interval=interval)


def _type_text(text, interval=0.03):
    """Type text via clipboard paste (cross-platform, supports CJK)."""
    logger.debug(f"[wechat] _type_text: '{text[:50]}{'...' if len(text)>50 else ''}'")
    try:
        clipboard_set_text(text)
        paste_hotkey()
    except Exception as e:
        logger.debug(f"[wechat] _type_text: clipboard paste failed ({e}), falling back to pyautogui.write")
        pyautogui.write(text, interval=interval)


def _press_enter():
    pyautogui.hotkey("enter")


def _press_escape():
    pyautogui.hotkey("escape")


# ---------------------------------------------------------------------------
# Core workflow: navigate to a chat by chatter_name
# ---------------------------------------------------------------------------

async def _navigate_to_chat(mainwin, chatter_name: str, pixel_per_scroll: int = 0):
    """Open the specified chat in WeChat.
    Returns (success: bool, ocr_data: list, error: str, pixel_per_scroll: int).
    """
    pps = pixel_per_scroll  # track calibrated value through the call

    # Step 1: Bring WeChat to front
    logger.debug(f"[wechat] _navigate_to_chat: Step 1 — find/activate WeChat for chat '{chatter_name}'")
    win = _find_wechat_window()
    if not win:
        logger.info("[wechat] _navigate_to_chat: WeChat not found, attempting os_open_app")
        from agent.mcp.server.server import os_open_app
        await os_open_app(mainwin, {"input": {"app_name": "WeChat"}})
        time.sleep(2)
        win = _find_wechat_window()
        if not win:
            logger.warning("[wechat] _navigate_to_chat: WeChat still not found after open attempt")
            return False, [], "WeChat window not found. Is WeChat running?", pps
    _bring_to_front(win)
    time.sleep(_POST_ACTION_DELAY)

    # Step 2: OCR the screen and validate it looks like WeChat
    logger.debug(f"[wechat] _navigate_to_chat: Step 2 — OCR and validate WeChat window")
    ocr_data = await _do_ocr(mainwin)

    # Guardrail: abort if OCR doesn't look like a WeChat window
    valid, reason = _validate_wechat_ocr(ocr_data)
    if not valid:
        logger.error(f"[wechat] _navigate_to_chat: OCR guardrail FAILED — {reason}")
        return False, ocr_data, f"OCR guardrail: {reason}. Aborting to prevent misclicks.", pps

    # Step 3: Use Search to navigate (always — clicking chat list toggles view in WeChat)
    # Search + Enter auto-opens the chat and activates the input box.
    logger.info(f"[wechat] _navigate_to_chat: Step 3 — using Search to open '{chatter_name}'")
    search_pos = _find_search_box(ocr_data)
    if not search_pos:
        logger.warning("[wechat] _navigate_to_chat: Search box not found via OCR, aborting (no fallback)")
        return False, ocr_data, "Cannot find Search box in WeChat via OCR. Aborting to prevent misclicks.", pps

    _click(search_pos[0], search_pos[1])
    time.sleep(_POST_CLICK_DELAY)

    # Step 4: Type chatter_name and press Enter
    # WeChat search auto-opens the first match and activates the text input box.
    logger.debug(f"[wechat] _navigate_to_chat: Step 4 — typing '{chatter_name}' into search")
    _type_text(chatter_name)
    time.sleep(_POST_TYPE_DELAY)
    _press_enter()
    time.sleep(1.5)  # wait for chat to open

    # Step 5: Verify the chat opened by checking for Send(S) button
    logger.debug(f"[wechat] _navigate_to_chat: Step 5 — verifying chat opened (looking for Send button)")
    ocr_data = await _do_ocr(mainwin)

    send_info = _find_send_button(ocr_data)
    if send_info:
        logger.info(f"[wechat] Chat opened successfully (Send button at {send_info[:2]}). Input box is active.")
        return True, ocr_data, "", pps

    # Send button not found — chat may not have opened
    logger.warning(f"[wechat] _navigate_to_chat: Send button not found after search — "
                   f"chat '{chatter_name}' may not exist or search failed")
    _press_escape()
    time.sleep(0.3)
    return False, ocr_data, f"Could not verify chat '{chatter_name}' opened (Send button not found)", pps


async def _smart_scroll_chat(mainwin, ocr_data, win, pixel_per_scroll, scroll_units=None):
    """Scroll the chat thread panel, calibrating first if pixel_per_scroll == 0.

    Returns (ocr_data_after, pixel_per_scroll).
    """
    pps = pixel_per_scroll

    # Detect chat panel bounds for scroll targeting
    bounds = _find_chat_panel_bounds(ocr_data, win)

    # Calibrate if unknown
    if pps == 0:
        logger.info("[wechat] _smart_scroll_chat: pixel_per_scroll=0, running calibration")
        scroll_xy = ((bounds["left"] + bounds["right"]) // 2,
                     (bounds["top"] + bounds["bottom"]) // 2)
        pps, ocr_data = await calibrate_scroll(
            do_ocr_fn=lambda: _do_ocr(mainwin),
            bounds=bounds,
            scroll_position_xy=scroll_xy,
        )
        if pps == 0:
            logger.warning("[wechat] _smart_scroll_chat: calibration failed, using default scroll")
            # Fall back to simple scroll
            from pynput.mouse import Controller as _MouseCtrl
            pyautogui.moveTo(scroll_xy[0], scroll_xy[1])
            time.sleep(0.2)
            _MouseCtrl().scroll(0, -_SCROLL_UNITS)
            time.sleep(_POST_SCROLL_DELAY)
            ocr_data = await _do_ocr(mainwin)
            return ocr_data, 0
        # calibrate_scroll already scrolled once, so ocr_data is post-scroll
        logger.info(f"[wechat] _smart_scroll_chat: calibrated pixel_per_scroll={pps}")
        return ocr_data, pps

    # Known pps — scroll precisely
    units = scroll_units if scroll_units else _SCROLL_UNITS
    logger.debug(f"[wechat] _smart_scroll_chat: scrolling {units} units (pps={pps}, "
                 f"expected ~{units * pps}px)")
    scroll_xy = ((bounds["left"] + bounds["right"]) // 2,
                 (bounds["top"] + bounds["bottom"]) // 2)
    pyautogui.moveTo(scroll_xy[0], scroll_xy[1])
    time.sleep(0.2)
    from pynput.mouse import Controller as _MouseCtrl
    _MouseCtrl().scroll(0, -units)
    time.sleep(_POST_SCROLL_DELAY)
    ocr_data = await _do_ocr(mainwin)
    return ocr_data, pps


# ---------------------------------------------------------------------------
# wechat_send
# ---------------------------------------------------------------------------

async def wechat_send(mainwin, args):
    """Send a message (and optional attachments) to a WeChat contact.

    Input:
        chatter_name: str   — display name of the contact/group
        chat_msg: str       — text message to send
        attachments: list   — list of file full paths to send (optional)
        pixel_per_scroll: int — pixels per scroll unit (0 = unknown, will calibrate)

    Output (JSON):
        chat_sent: bool
        verified: bool
        pixel_per_scroll: int
        error: str
        last_ocr_raw_result: dict/list
    """
    try:
        inp = args.get("input", args)
        chatter_name = inp.get("chatter_name", "")
        chat_msg = inp.get("chat_msg", "")
        attachments = inp.get("attachments", [])
        pps = int(inp.get("pixel_per_scroll", 0))

        if not chatter_name:
            return _result(False, 0, "chatter_name is required", [], pps)

        logger.info(f"[wechat_send] Sending to '{chatter_name}': msg='{chat_msg[:50]}...', "
                     f"attachments={len(attachments)}, pixel_per_scroll={pps}")

        # Navigate to the chat
        logger.debug(f"[wechat_send] Navigating to chat '{chatter_name}'")
        success, ocr_data, error, pps = await _navigate_to_chat(mainwin, chatter_name, pps)
        if not success:
            logger.warning(f"[wechat_send] Navigation failed: {error}")
            return _result(False, 0, error, ocr_data, pps)
        # Input box is already active after search navigation — type directly.
        logger.debug("[wechat_send] Navigation succeeded, input box should be active")

        # Send attachments first (drag-drop or clipboard)
        for attachment_path in attachments:
            if not os.path.exists(attachment_path):
                logger.warning(f"[wechat_send] Attachment not found: {attachment_path}")
                continue
            try:
                # Copy file to clipboard and paste (cross-platform)
                clipboard_set_file(attachment_path)
                paste_hotkey()
                time.sleep(1.0)
                _press_enter()
                time.sleep(1.0)
                logger.info(f"[wechat_send] Sent attachment: {attachment_path}")
            except Exception as e:
                logger.warning(f"[wechat_send] Failed to send attachment {attachment_path}: {e}")

        # Type the message
        if chat_msg:
            logger.debug(f"[wechat_send] Typing message ({len(chat_msg)} chars)")
            _type_text(chat_msg)
            time.sleep(_POST_TYPE_DELAY)
            logger.debug("[wechat_send] Pressing Enter to send")
            _press_enter()
            time.sleep(_POST_ACTION_DELAY)
        else:
            logger.debug("[wechat_send] No text message to send (attachments only)")

        # Verify — do a final OCR to check the message appears
        logger.debug("[wechat_send] Running verification OCR")
        ocr_data = await _do_ocr(mainwin)
        verified = False
        if chat_msg:
            pos = _find_text_in_ocr(ocr_data, chat_msg[:20])  # check first 20 chars
            verified = pos is not None
            logger.info(f"[wechat_send] Verification: {'PASS' if verified else 'FAIL'} (searched first 20 chars)")

        result_payload = {
            "chat_sent": True,
            "verified": verified,
            "pixel_per_scroll": pps,
            "error": "",
            "last_ocr_raw_result": ocr_data,
        }
        return [TextContent(type="text", text=json.dumps(result_payload, ensure_ascii=False, default=str))]

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        logger.error(f"[wechat_send] {err}")
        return _result(False, 0, str(e), [], 0)


# ---------------------------------------------------------------------------
# wechat_receive
# ---------------------------------------------------------------------------

async def wechat_receive(mainwin, args):
    """Read new messages from a WeChat contact since a known last-sent message.

    Input:
        chatter_name: str   — display name of the contact/group
        last_sent_msg: str  — your last sent message (to identify new messages after it)
        pixel_per_scroll: int — pixels per scroll unit (0 = unknown, will calibrate on first scroll)

    Output (JSON):
        new_msgs: [str]
        pixel_per_scroll: int
        error: str
        last_ocr_raw_result: dict/list
    """
    try:
        inp = args.get("input", args)
        chatter_name = inp.get("chatter_name", "")
        last_sent_msg = inp.get("last_sent_msg", "")
        pps = int(inp.get("pixel_per_scroll", 0))

        if not chatter_name:
            return _recv_result([], "chatter_name is required", [], pps)

        logger.info(f"[wechat_receive] Reading from '{chatter_name}', "
                     f"last_sent='{last_sent_msg[:30]}...', pixel_per_scroll={pps}")

        # Navigate to the chat
        logger.debug(f"[wechat_receive] Navigating to chat '{chatter_name}'")
        success, ocr_data, error, pps = await _navigate_to_chat(mainwin, chatter_name, pps)
        if not success:
            logger.warning(f"[wechat_receive] Navigation failed: {error}")
            return _recv_result([], error, ocr_data, pps)
        logger.debug("[wechat_receive] Navigation succeeded, extracting messages")

        # Extract all visible messages
        all_messages = _extract_chat_messages(ocr_data)
        logger.debug(f"[wechat_receive] Total visible messages: {len(all_messages)}")

        # If we have a last_sent_msg, find it and return everything after it
        new_msgs = []
        if last_sent_msg:
            last_sent_lower = last_sent_msg.strip().lower()
            found_idx = -1
            for i, msg in enumerate(all_messages):
                if last_sent_lower in msg.lower():
                    found_idx = i
            if found_idx >= 0:
                new_msgs = all_messages[found_idx + 1:]
                logger.debug(f"[wechat_receive] last_sent_msg matched at index {found_idx}, returning {len(new_msgs)} new msgs")
            else:
                # last_sent_msg not visible — try scrolling up in chat to find it
                logger.info("[wechat_receive] last_sent_msg not visible, scrolling chat panel to find it")
                win = _find_wechat_window()
                ocr_data, pps = await _smart_scroll_chat(mainwin, ocr_data, win, pps)
                all_messages_after_scroll = _extract_chat_messages(ocr_data)
                # Re-check for last_sent_msg
                found_idx = -1
                for i, msg in enumerate(all_messages_after_scroll):
                    if last_sent_lower in msg.lower():
                        found_idx = i
                if found_idx >= 0:
                    new_msgs = all_messages_after_scroll[found_idx + 1:]
                    logger.debug(f"[wechat_receive] After scroll: last_sent_msg at index {found_idx}, {len(new_msgs)} new msgs")
                else:
                    new_msgs = all_messages_after_scroll
                    logger.debug(f"[wechat_receive] After scroll: last_sent_msg still NOT found, returning all {len(new_msgs)} msgs")
        else:
            new_msgs = all_messages
            logger.debug(f"[wechat_receive] No last_sent_msg filter, returning all {len(new_msgs)} msgs")

        result_payload = {
            "new_msgs": new_msgs,
            "pixel_per_scroll": pps,
            "error": "",
            "last_ocr_raw_result": ocr_data,
        }
        return [TextContent(type="text", text=json.dumps(result_payload, ensure_ascii=False, default=str))]

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        logger.error(f"[wechat_receive] {err}")
        return _recv_result([], str(e), [], 0)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

def _result(chat_sent, scroll_resolution, error, ocr_data, pixel_per_scroll=0):
    payload = {
        "chat_sent": chat_sent,
        "pixel_per_scroll": pixel_per_scroll,
        "error": error,
        "last_ocr_raw_result": ocr_data,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _recv_result(new_msgs, error, ocr_data, pixel_per_scroll=0):
    payload = {
        "new_msgs": new_msgs,
        "pixel_per_scroll": pixel_per_scroll,
        "error": error,
        "last_ocr_raw_result": ocr_data,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


# ---------------------------------------------------------------------------
# Tool schema registration helpers
# ---------------------------------------------------------------------------

def add_wechat_send_tool_schema(tool_schemas):
    """Add schema for wechat_send tool."""
    schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="wechat_send",
        description=(
            "<category>WeChat</category><sub-category>Messaging</sub-category>"
            "Send a text message and/or file attachments to a WeChat contact or group. "
            "Handles opening WeChat, finding the chat, navigating to it, typing the message, "
            "and pressing Send — all in one tool call. "
            "Returns pixel_per_scroll (calibrated scroll resolution) in output — pass it back "
            "on subsequent calls for precise scrolling."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["chatter_name", "chat_msg"],
                    "properties": {
                        "chatter_name": {
                            "type": "string",
                            "description": "Display name of the WeChat contact or group to message",
                        },
                        "chat_msg": {
                            "type": "string",
                            "description": "Text message to send (can be empty if only sending attachments)",
                        },
                        "attachments": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of full file paths to send as attachments",
                        },
                        "pixel_per_scroll": {
                            "type": "integer",
                            "description": "Pixels moved per scroll unit. 0 means unknown — the tool will "
                                           "auto-calibrate on first scroll and return the measured value. "
                                           "Pass the returned value back on subsequent calls for precise scrolling.",
                            "default": 0,
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(schema)


def add_wechat_receive_tool_schema(tool_schemas):
    """Add schema for wechat_receive tool."""
    schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="wechat_receive",
        description=(
            "<category>WeChat</category><sub-category>Messaging</sub-category>"
            "Read new messages from a WeChat contact or group. "
            "Opens WeChat, navigates to the specified chat, runs OCR, and returns "
            "messages that appeared after your last_sent_msg. "
            "If last_sent_msg is not visible, scrolls the chat panel (calibrating scroll "
            "resolution if pixel_per_scroll is 0). Returns pixel_per_scroll in output."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["chatter_name"],
                    "properties": {
                        "chatter_name": {
                            "type": "string",
                            "description": "Display name of the WeChat contact or group",
                        },
                        "last_sent_msg": {
                            "type": "string",
                            "description": "Your last sent message text — new messages after this will be returned. "
                                           "Leave empty to return all visible messages.",
                        },
                        "pixel_per_scroll": {
                            "type": "integer",
                            "description": "Pixels moved per scroll unit. 0 means unknown — the tool will "
                                           "auto-calibrate on first scroll and return the measured value. "
                                           "Pass the returned value back on subsequent calls for precise scrolling.",
                            "default": 0,
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(schema)
