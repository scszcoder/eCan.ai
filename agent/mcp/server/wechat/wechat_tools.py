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
    clipboard_get_text,
    clipboard_set_file,
    paste_hotkey,
    WindowInfo,
    PLATFORM,
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
_MSG_VERTICAL_GAP = 30         # px — OCR items closer than this vertically are same message
_MAX_SCROLL_ATTEMPTS = 15      # max scroll-up attempts to find last_sent_msg
_FILE_EXT_RE = re.compile(
    r"\.\w{1,5}$"              # line ending with .ext (1-5 char extension)
)
_FILE_SIZE_RE = re.compile(
    r"^\d+(\.\d+)?\s*[KMGkmg][Bb]?$"  # e.g. "3.2MB", "128K", "1.5 GB"
)
_AUDIO_DURATION_RE = re.compile(
    r"^\d{1,3}'\d{2}\"$|^\d{1,3}\"$"  # audio: mm'ss" or ss"  e.g. 1'23" or 5"
)
_VIDEO_DURATION_RE = re.compile(
    r"^\d{1,3}:\d{2}$"                  # video: mm:ss  e.g. 1:23 or 0:05
)


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


def _ocr_item_coords(item):
    """Extract (cx, cy, x1, y1, x2, y2) from an OCR item dict.
    Tries txt_struct box first, then paragraph-level loc.
    Returns None if no coordinates found.
    """
    for ts in item.get("txt_struct", []):
        if not isinstance(ts, dict):
            continue
        box = ts.get("box")  # [x1, y1, x2, y2]
        if box and len(box) == 4:
            cx = (box[0] + box[2]) // 2
            cy = (box[1] + box[3]) // 2
            return cx, cy, box[0], box[1], box[2], box[3]
    loc = item.get("loc")  # [y1, x1, y2, x2]
    if loc and len(loc) == 4:
        cx = (loc[1] + loc[3]) // 2
        cy = (loc[0] + loc[2]) // 2
        return cx, cy, loc[1], loc[0], loc[3], loc[2]
    return None


def _is_system_text(text):
    """Return True if text looks like a WeChat system/UI element rather than a chat message."""
    t = text.strip().lower()
    # WeChat UI labels
    ui_labels = {"search", "搜索", "send(s)", "发送(s)", "send", "发送",
                 "file transfer", "文件传输助手", "mini programs", "小程序",
                 "contacts", "通讯录", "discover", "发现", "me", "我",
                 "chats", "聊天", "weixin", "wechat"}
    if t in ui_labels:
        return True
    # Date headers like "Yesterday", "Monday", "2025-03-01" etc.
    if re.match(r"^(yesterday|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                r"昨天|今天|星期[一二三四五六日]|周[一二三四五六日]|\d{4}[-/]\d{1,2}[-/]\d{1,2})$", t):
        return True
    return False


def _extract_chat_messages(ocr_data, bounds=None):
    """Extract structured chat messages from OCR data within the chat panel.

    Args:
        ocr_data: OCR result list
        bounds: dict(top, bottom, left, right) — chat panel region.
                If None, all OCR items are considered.

    Returns:
        list of dicts, top-to-bottom, each with:
            - sender: "me" | "them" | "system"
            - text: str (concatenated if multi-line)
            - cy: int (center Y for positioning)
            - cx: int (center X)
            - type: "text" | "timestamp" | "file" | "audio" | "video"
            - box: [x1, y1, x2, y2] of the first OCR line in the group
    """
    if not ocr_data or not isinstance(ocr_data, list):
        logger.debug("[wechat] _extract_chat_messages: no OCR data")
        return []

    # Step 1: Collect all OCR text items with coordinates, filtered to bounds
    items = []
    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        coords = _ocr_item_coords(item)
        if coords is None:
            continue
        cx, cy, x1, y1, x2, y2 = coords

        # Filter to chat panel bounds if provided
        if bounds:
            if cy < bounds["top"] or cy > bounds["bottom"]:
                continue
            if cx < bounds["left"] or cx > bounds["right"]:
                continue

        # Skip WeChat UI / system labels
        if _is_system_text(text):
            continue

        items.append({
            "text": text, "cx": cx, "cy": cy,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        })

    if not items:
        logger.debug("[wechat] _extract_chat_messages: no items in bounds")
        return []

    # Sort by Y position (top to bottom)
    items.sort(key=lambda it: it["cy"])

    # Step 2: Determine the left/right split for sent vs. received
    # In WeChat, the chat panel has a center line. Messages to the left of
    # center are from the other party; messages to the right are ours.
    if bounds:
        panel_center_x = (bounds["left"] + bounds["right"]) // 2
    else:
        all_cx = [it["cx"] for it in items]
        panel_center_x = (min(all_cx) + max(all_cx)) // 2

    logger.debug(f"[wechat] _extract_chat_messages: {len(items)} items, panel_center_x={panel_center_x}")

    # Step 3: Classify each item and group vertically close items of the same alignment
    messages = []
    prev_cy = None  # track previous OCR item's Y for gap-based heuristics
    for it in items:
        text = it["text"]
        cx = it["cx"]
        cy = it["cy"]

        # Classify type
        # Note: _TIMESTAMP_RE (hh:mm) overlaps with _VIDEO_DURATION_RE (mm:ss).
        # Disambiguation: WeChat timestamps are horizontally centered in the
        # chat panel, while video durations overlay a left/right-aligned thumbnail.
        _center_tolerance = (bounds["right"] - bounds["left"]) // 6 if bounds else 80
        if _TIMESTAMP_RE.match(text) and abs(cx - panel_center_x) < _center_tolerance:
            msg_type = "timestamp"
            sender = "system"
        elif _AUDIO_DURATION_RE.match(text):
            msg_type = "audio"
            sender = "them" if cx < panel_center_x else "me"
        elif _VIDEO_DURATION_RE.match(text):
            msg_type = "video"
            sender = "them" if cx < panel_center_x else "me"
        elif _FILE_SIZE_RE.match(text):
            # Size line — attach to the file message above (handled in grouping)
            msg_type = "file_size"
            sender = "them" if cx < panel_center_x else "me"
        elif _FILE_EXT_RE.search(text):
            msg_type = "file"
            sender = "them" if cx < panel_center_x else "me"
        else:
            msg_type = "text"
            sender = "them" if cx < panel_center_x else "me"

        # Try to merge with the previous message if:
        # - same sender/alignment
        # - vertically close (within _MSG_VERTICAL_GAP)
        # - previous message is not a timestamp
        if (messages
                and messages[-1]["sender"] == sender
                and messages[-1]["type"] not in ("timestamp",)
                and abs(cy - messages[-1]["cy"]) < _MSG_VERTICAL_GAP):
            # Special: if this is a file_size line, mark previous as file
            if msg_type == "file_size" and messages[-1]["type"] in ("text", "file"):
                messages[-1]["type"] = "file"
                messages[-1]["text"] += f" ({text})"
                messages[-1]["cy"] = cy  # update cy to the bottom of the group
            else:
                messages[-1]["text"] += "\n" + text
                messages[-1]["cy"] = cy
        else:
            if msg_type == "file_size":
                # Orphan size line — still a file indicator
                msg_type = "file"
            messages.append({
                "sender": sender,
                "text": text,
                "cy": cy,
                "cx": cx,
                "type": msg_type,
                "box": [it["x1"], it["y1"], it["x2"], it["y2"]],
            })

        prev_cy = cy

    logger.debug(f"[wechat] _extract_chat_messages: grouped into {len(messages)} messages "
                 f"(me={sum(1 for m in messages if m['sender']=='me')}, "
                 f"them={sum(1 for m in messages if m['sender']=='them')}, "
                 f"system={sum(1 for m in messages if m['sender']=='system')})")
    return messages


def _extract_chat_messages_flat(ocr_data, bounds=None):
    """Legacy wrapper — returns flat list of message strings (backward compatible)."""
    structured = _extract_chat_messages(ocr_data, bounds)
    return [m["text"] for m in structured]


# ---------------------------------------------------------------------------
# Double-click + copy: read full message text via clipboard
# ---------------------------------------------------------------------------

def _read_full_message_via_clipboard(msg):
    """Double-click a message bubble to select it, then Ctrl+C to get the full text.

    This handles long messages that may be truncated in OCR.
    Args:
        msg: structured message dict with 'cx', 'cy', 'box'
    Returns:
        str — the full message text, or '' if it failed
    """
    cx, cy = msg["cx"], msg["cy"]
    # Use the center of the first line's box for targeting
    box = msg.get("box")
    if box and len(box) == 4:
        target_x = (box[0] + box[2]) // 2
        target_y = (box[1] + box[3]) // 2
    else:
        target_x, target_y = cx, cy

    logger.debug(f"[wechat] _read_full_message_via_clipboard: double-clicking ({target_x},{target_y})")

    # Double-click to select (in WeChat, double-clicking a text message opens selection)
    pyautogui.moveTo(target_x, target_y)
    time.sleep(0.2)
    pyautogui.doubleClick(target_x, target_y)
    time.sleep(0.5)

    # Select all text in the selection popup (Ctrl+A) then copy (Ctrl+C)
    if PLATFORM == "darwin":
        pyautogui.hotkey("command", "a")
        time.sleep(0.2)
        pyautogui.hotkey("command", "c")
    else:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "c")
    time.sleep(0.3)

    # Read clipboard
    full_text = clipboard_get_text().strip()

    # Dismiss the selection popup
    pyautogui.press("escape")
    time.sleep(0.3)

    if full_text:
        logger.debug(f"[wechat] _read_full_message_via_clipboard: got {len(full_text)} chars")
    else:
        logger.warning("[wechat] _read_full_message_via_clipboard: clipboard was empty")
    return full_text


# ---------------------------------------------------------------------------
# Right-click probe: identify content type from context menu
# ---------------------------------------------------------------------------

async def _probe_content_type_via_rightclick(mainwin, msg):
    """Right-click a message bubble and OCR the context menu to determine content type.

    Known WeChat context menu signatures:
        - "Silent Play" / "静音播放"   → forwarded video
        - "Save As" / "另存为"         → file attachment
        - "Speech to Text" / "转文字"  → audio message

    Args:
        mainwin: main window reference for OCR
        msg: structured message dict with 'cx', 'cy', 'box'
    Returns:
        str — detected type: "video", "file", "audio", or "unknown"
    """
    box = msg.get("box")
    if box and len(box) == 4:
        target_x = (box[0] + box[2]) // 2
        target_y = (box[1] + box[3]) // 2
    else:
        target_x, target_y = msg["cx"], msg["cy"]

    logger.debug(f"[wechat] _probe_content_type: right-clicking ({target_x},{target_y})")

    pyautogui.moveTo(target_x, target_y)
    time.sleep(0.2)
    pyautogui.rightClick(target_x, target_y)
    time.sleep(_POST_CLICK_DELAY)

    ocr_data = await _do_ocr(mainwin)

    # Check menu items for type signatures
    menu_signatures = {
        "video": ["silent play", "静音播放"],
        "file":  ["save as", "另存为"],
        "audio": ["speech to text", "转文字"],
    }
    detected = "unknown"
    for content_type, keywords in menu_signatures.items():
        for kw in keywords:
            if _find_text_in_ocr(ocr_data, kw):
                detected = content_type
                break
        if detected != "unknown":
            break

    # Dismiss context menu
    pyautogui.press("escape")
    time.sleep(0.3)

    logger.debug(f"[wechat] _probe_content_type: detected '{detected}'")
    return detected


# ---------------------------------------------------------------------------
# File attachment: right-click → Save As
# ---------------------------------------------------------------------------

async def _save_file_attachment(mainwin, msg, save_dir=None):
    """Right-click a file attachment and select 'Save As...' to save it.

    Args:
        mainwin: main window reference for OCR
        msg: structured message dict (type="file") with 'cx', 'cy', 'box'
        save_dir: directory to save to. If None, uses Downloads folder.
    Returns:
        dict with 'saved': bool, 'path': str, 'error': str
    """
    cx, cy = msg["cx"], msg["cy"]
    box = msg.get("box")
    if box and len(box) == 4:
        target_x = (box[0] + box[2]) // 2
        target_y = (box[1] + box[3]) // 2
    else:
        target_x, target_y = cx, cy

    logger.info(f"[wechat] _save_file_attachment: right-clicking ({target_x},{target_y})")

    # Right-click to open context menu
    pyautogui.moveTo(target_x, target_y)
    time.sleep(0.2)
    pyautogui.rightClick(target_x, target_y)
    time.sleep(_POST_CLICK_DELAY)

    # OCR the context menu to find "Save As..." / "另存为..."
    ocr_data = await _do_ocr(mainwin)
    save_as_keywords = ["save as", "另存为"]
    save_pos = None
    for kw in save_as_keywords:
        pos = _find_text_in_ocr(ocr_data, kw)
        if pos:
            save_pos = pos
            break

    if not save_pos:
        logger.warning("[wechat] _save_file_attachment: 'Save As' not found in context menu — "
                       "this may not be a file attachment")
        pyautogui.press("escape")
        time.sleep(0.3)
        return {"saved": False, "path": "", "error": "Save As not found in context menu"}

    # Click "Save As..."
    _click(save_pos[0], save_pos[1])
    time.sleep(1.0)

    # The Save dialog should now be open.
    # Type the save directory if specified.
    if save_dir:
        # In Windows Save dialog, the address bar can be activated with Alt+D
        # then type the path and press Enter
        if PLATFORM == "win32":
            pyautogui.hotkey("alt", "d")
            time.sleep(0.3)
            _type_text(save_dir)
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(0.5)

    # Press Enter / click Save to confirm
    pyautogui.press("enter")
    time.sleep(1.0)

    # Check for overwrite confirmation dialog (just press Enter again)
    pyautogui.press("enter")
    time.sleep(0.5)

    logger.info(f"[wechat] _save_file_attachment: save dialog confirmed, dir={save_dir or 'default'}")
    return {"saved": True, "path": save_dir or "(default downloads)", "error": ""}


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


async def _smart_scroll_chat(mainwin, ocr_data, win, pixel_per_scroll,
                             scroll_units=None, direction="down"):
    """Scroll the chat thread panel, calibrating first if pixel_per_scroll == 0.

    Args:
        direction: "down" (scroll toward newer messages) or "up" (toward older)

    Returns (ocr_data_after, pixel_per_scroll).
    """
    pps = pixel_per_scroll
    sign = -1 if direction == "down" else 1  # pynput: negative = scroll down

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
            _MouseCtrl().scroll(0, sign * _SCROLL_UNITS)
            time.sleep(_POST_SCROLL_DELAY)
            ocr_data = await _do_ocr(mainwin)
            return ocr_data, 0
        # calibrate_scroll already scrolled once, so ocr_data is post-scroll
        logger.info(f"[wechat] _smart_scroll_chat: calibrated pixel_per_scroll={pps}")
        return ocr_data, pps

    # Known pps — scroll precisely
    units = scroll_units if scroll_units else _SCROLL_UNITS
    logger.debug(f"[wechat] _smart_scroll_chat: scrolling {direction} {units} units (pps={pps}, "
                 f"expected ~{units * pps}px)")
    scroll_xy = ((bounds["left"] + bounds["right"]) // 2,
                 (bounds["top"] + bounds["bottom"]) // 2)
    pyautogui.moveTo(scroll_xy[0], scroll_xy[1])
    time.sleep(0.2)
    from pynput.mouse import Controller as _MouseCtrl
    _MouseCtrl().scroll(0, sign * units)
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

def _find_msg_in_structured(messages, target_text):
    """Find a structured message whose text contains target_text (case-insensitive).
    Searches from the bottom (newest) upward.
    Returns the index or -1.
    """
    target_lower = target_text.strip().lower()
    # Search bottom-up to find the most recent match
    for i in range(len(messages) - 1, -1, -1):
        if target_lower in messages[i]["text"].lower():
            return i
    return -1


async def _scroll_up_to_find(mainwin, ocr_data, win, pps, target_text):
    """Scroll the chat UP repeatedly until we find target_text in the visible messages.

    Strategy:
      - On each scroll, extract structured messages and search for the target.
      - Stop when found, or after _MAX_SCROLL_ATTEMPTS.

    Returns (found_idx, messages, ocr_data, pps, bounds).
    found_idx is -1 if not found after exhausting attempts.
    """
    bounds = _find_chat_panel_bounds(ocr_data, win)
    messages = _extract_chat_messages(ocr_data, bounds)
    found_idx = _find_msg_in_structured(messages, target_text)
    if found_idx >= 0:
        return found_idx, messages, ocr_data, pps, bounds

    for attempt in range(1, _MAX_SCROLL_ATTEMPTS + 1):
        logger.info(f"[wechat_receive] Scroll UP attempt {attempt}/{_MAX_SCROLL_ATTEMPTS} "
                    f"to find: '{target_text[:30]}...'")
        ocr_data, pps = await _smart_scroll_chat(mainwin, ocr_data, win, pps, direction="up")
        bounds = _find_chat_panel_bounds(ocr_data, win)
        messages = _extract_chat_messages(ocr_data, bounds)
        found_idx = _find_msg_in_structured(messages, target_text)
        if found_idx >= 0:
            logger.info(f"[wechat_receive] Found target at index {found_idx} after {attempt} scroll(s)")
            return found_idx, messages, ocr_data, pps, bounds

    logger.warning(f"[wechat_receive] Target not found after {_MAX_SCROLL_ATTEMPTS} scrolls")
    return -1, messages, ocr_data, pps, bounds


async def _scroll_down_collect(mainwin, ocr_data, win, pps, collected,
                                last_cy_seen, bounds):
    """Scroll DOWN to collect all new messages below what's currently visible.

    Keeps scrolling until no new messages appear (we've reached the bottom).

    Args:
        collected: list of structured messages accumulated so far
        last_cy_seen: the cy of the bottom-most message we already captured
        bounds: chat panel bounds

    Returns (collected, ocr_data, pps).
    """
    prev_bottom_text = None
    stale_count = 0

    for attempt in range(1, _MAX_SCROLL_ATTEMPTS + 1):
        logger.debug(f"[wechat_receive] Scroll DOWN attempt {attempt} to collect more messages")
        ocr_data, pps = await _smart_scroll_chat(mainwin, ocr_data, win, pps, direction="down")
        bounds = _find_chat_panel_bounds(ocr_data, win)
        messages = _extract_chat_messages(ocr_data, bounds)

        if not messages:
            logger.debug("[wechat_receive] No messages after scroll-down, likely at bottom")
            break

        # Collect messages we haven't seen (avoid duplication by checking text+sender)
        seen_keys = {(m["sender"], m["text"]) for m in collected}
        new_count = 0
        for m in messages:
            key = (m["sender"], m["text"])
            if key not in seen_keys:
                collected.append(m)
                seen_keys.add(key)
                new_count += 1

        logger.debug(f"[wechat_receive] Scroll-down: {new_count} new messages collected")

        # Detect if we've hit the bottom (same bottom message as last scroll)
        bottom_text = messages[-1]["text"] if messages else None
        if bottom_text == prev_bottom_text:
            stale_count += 1
            if stale_count >= 2:
                logger.debug("[wechat_receive] Bottom reached (same content 2x), stopping")
                break
        else:
            stale_count = 0
            prev_bottom_text = bottom_text

    return collected, ocr_data, pps


def _format_structured_messages(messages, include_types=None):
    """Format structured messages into a readable list for the LLM.

    Args:
        messages: list of structured message dicts
        include_types: set of types to include, or None for all except timestamps

    Returns:
        list of dicts with keys: sender, text, type
    """
    result = []
    for m in messages:
        if m["type"] == "timestamp":
            continue  # skip timestamp dividers
        if include_types and m["type"] not in include_types:
            continue
        result.append({
            "sender": m["sender"],
            "text": m["text"],
            "type": m["type"],
        })
    return result


async def wechat_receive(mainwin, args):
    """Read new messages from a WeChat contact since a known last-sent message.

    Strategy:
      1. Navigate to the chat (Search + Enter).
      2. OCR the visible chat panel and extract structured messages
         (sender="me"/"them", type="text"/"file"/"audio").
      3. If last_sent_msg is provided:
         a. Search visible messages for it.
         b. If not found, scroll UP repeatedly (up to 15 attempts) to find it.
         c. Once found, collect everything AFTER it on this screen.
         d. Scroll DOWN to collect any additional new messages below.
      4. If last_sent_msg is empty: return all visible messages.
      5. For each text message from "them": double-click → Ctrl+A → Ctrl+C
         to capture the full text (handles long messages truncated by OCR).
      6. For file attachments: include metadata (filename, size) in output.

    Input:
        chatter_name: str   — display name of the contact/group
        last_sent_msg: str  — your last sent message text (anchor to find new msgs after it).
                              Leave empty to return all visible messages.
        save_files_to: str  — directory to save file attachments to (optional).
                              If provided, file attachments will be right-click → Save As'd.
        pixel_per_scroll: int — pixels per scroll unit (0 = auto-calibrate)

    Output (JSON):
        new_msgs: list of {sender, text, type}
        pixel_per_scroll: int
        error: str
        last_ocr_raw_result: dict/list
    """
    try:
        inp = args.get("input", args)
        chatter_name = inp.get("chatter_name", "")
        last_sent_msg = inp.get("last_sent_msg", "").strip()
        save_files_to = inp.get("save_files_to", "").strip()
        pps = int(inp.get("pixel_per_scroll", 0))

        if not chatter_name:
            return _recv_result([], "chatter_name is required", [], pps)

        logger.info(f"[wechat_receive] Reading from '{chatter_name}', "
                     f"last_sent='{last_sent_msg[:40]}', pixel_per_scroll={pps}")

        # Step 1: Navigate to the chat
        success, ocr_data, error, pps = await _navigate_to_chat(mainwin, chatter_name, pps)
        if not success:
            logger.warning(f"[wechat_receive] Navigation failed: {error}")
            return _recv_result([], error, ocr_data, pps)

        win = _find_wechat_window()
        bounds = _find_chat_panel_bounds(ocr_data, win)

        # Step 2: Extract structured messages from current view
        all_messages = _extract_chat_messages(ocr_data, bounds)
        logger.info(f"[wechat_receive] Visible: {len(all_messages)} messages "
                    f"(me={sum(1 for m in all_messages if m['sender']=='me')}, "
                    f"them={sum(1 for m in all_messages if m['sender']=='them')})")

        new_msgs_structured = []

        if last_sent_msg:
            # Step 3a: Find last_sent_msg in visible messages
            found_idx = _find_msg_in_structured(all_messages, last_sent_msg)

            if found_idx < 0:
                # Step 3b: Scroll UP to find it
                found_idx, all_messages, ocr_data, pps, bounds = await _scroll_up_to_find(
                    mainwin, ocr_data, win, pps, last_sent_msg
                )

            if found_idx >= 0:
                # Step 3c: Collect everything after the anchor on this screen
                new_msgs_structured = [m for m in all_messages[found_idx + 1:]
                                       if m["type"] != "timestamp"]
                logger.info(f"[wechat_receive] Found anchor at idx={found_idx}, "
                            f"{len(new_msgs_structured)} new msgs on screen")

                # Step 3d: Scroll DOWN to collect any more new messages
                if new_msgs_structured:
                    last_cy = new_msgs_structured[-1]["cy"]
                else:
                    last_cy = all_messages[found_idx]["cy"]

                new_msgs_structured, ocr_data, pps = await _scroll_down_collect(
                    mainwin, ocr_data, win, pps, new_msgs_structured, last_cy, bounds
                )
                logger.info(f"[wechat_receive] After scroll-down collect: "
                            f"{len(new_msgs_structured)} total new messages")
            else:
                # Anchor not found at all — return everything visible as fallback
                logger.warning("[wechat_receive] last_sent_msg not found after scrolling, "
                               "returning all visible messages")
                new_msgs_structured = [m for m in all_messages if m["type"] != "timestamp"]
        else:
            # No anchor — return all visible messages
            new_msgs_structured = [m for m in all_messages if m["type"] != "timestamp"]
            logger.info(f"[wechat_receive] No anchor, returning {len(new_msgs_structured)} visible msgs")

        # Step 5: For text messages from "them", use double-click+copy to get full text
        for msg in new_msgs_structured:
            if msg["type"] == "text" and msg["sender"] == "them":
                full_text = _read_full_message_via_clipboard(msg)
                if full_text and len(full_text) > len(msg["text"]):
                    logger.debug(f"[wechat_receive] Clipboard expanded msg from "
                                 f"{len(msg['text'])} to {len(full_text)} chars")
                    msg["text"] = full_text

        # Step 6: Handle file attachments
        file_msgs = [m for m in new_msgs_structured if m["type"] == "file"]
        if file_msgs and save_files_to:
            for fm in file_msgs:
                logger.info(f"[wechat_receive] Saving file attachment: '{fm['text']}'")
                save_result = await _save_file_attachment(mainwin, fm, save_files_to)
                fm["file_saved"] = save_result.get("saved", False)
                fm["file_save_path"] = save_result.get("path", "")
                if save_result.get("error"):
                    fm["file_save_error"] = save_result["error"]

        # Format output
        output_msgs = _format_structured_messages(new_msgs_structured)

        result_payload = {
            "new_msgs": output_msgs,
            "msg_count": len(output_msgs),
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
            "Opens WeChat, navigates to the specified chat, and extracts structured messages "
            "with sender identification (me/them) and type detection (text/file/audio). "
            "If last_sent_msg is provided, scrolls UP to find it as an anchor, then collects "
            "everything after it (scrolling DOWN as needed). Long text messages are read via "
            "double-click + clipboard copy for full accuracy. "
            "File attachments are detected by extension + size pattern and can optionally be "
            "saved via right-click → Save As. "
            "Returns new_msgs as [{sender, text, type}, ...]. "
            "Returns pixel_per_scroll in output — pass it back on subsequent calls."
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
                            "description": "Your last sent message text — used as an anchor. "
                                           "The tool scrolls up to find this message, then returns everything after it. "
                                           "Leave empty to return all visible messages.",
                        },
                        "save_files_to": {
                            "type": "string",
                            "description": "Optional directory path to save incoming file attachments to. "
                                           "If provided, detected file attachments will be right-click → Save As'd "
                                           "to this directory. Leave empty to skip file saving.",
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
