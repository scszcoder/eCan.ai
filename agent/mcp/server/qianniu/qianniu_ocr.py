"""千牛 OCR primitives — capture the AliWorkbench window and read text.

Clones the proven wechat local-OCR recipe (``wechat_tools._do_ocr_local``)
for the 千牛 window, and adds the **select-verify** primitive the feasibility
study (§5) requires: OCR the chat-header buyer-name band and compare it to the
intended recipient before any send. Read-only — this module never sends input.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Optional

from utils.logger_helper import logger_helper as logger

# The Windows title alias for 千牛 is registered in
# agent/ec_skills/ocr/image_prep.py::get_top_visible_window (_WIN_ALIASES).
_QIANNIU_WIN_KW = "千牛"
_OCR_MAX_LONG_SIDE = 1500            # match wechat_tools; resize before OCR
_HEADER_BAND_FRAC = 0.12             # top 12% of the window holds the buyer-name header


def ocr_qianniu_window() -> list:
    """Capture the 千牛 window and run local OCR. Returns ocr_data in remote
    format with **absolute screen coords** (``loc=[y1,x1,y2,x2]``), or []."""
    from agent.ec_skills.ocr.image_prep import captureScreen, _apply_window_offset
    from agent.mcp.server.local_ocr.paddle_ocr import (
        run_ocr_on_image, scale_ocr_coordinates,
    )

    screen_img, _image_bytes, window_rect = captureScreen(_QIANNIU_WIN_KW)
    orig_w, orig_h = screen_img.size

    scale_x, scale_y = 1.0, 1.0
    long_side = max(orig_w, orig_h)
    if long_side > _OCR_MAX_LONG_SIDE:
        ratio = _OCR_MAX_LONG_SIDE / long_side
        new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
        screen_img = screen_img.resize((new_w, new_h))
        scale_x, scale_y = orig_w / new_w, orig_h / new_h

    tmp_file = os.path.join(tempfile.gettempdir(), "qianniu_ocr_tmp.png")
    screen_img.save(tmp_file)

    ocr_result = run_ocr_on_image(tmp_file)
    if ocr_result.get("status") != "success":
        logger.error(f"[qianniu] local OCR failed: {ocr_result.get('error')}")
        return []

    result = ocr_result.get("ocr_data", [])
    if scale_x != 1.0 or scale_y != 1.0:
        result = scale_ocr_coordinates(result, scale_x, scale_y)
    result = _apply_window_offset(result, window_rect)
    return result


def _norm(name: str) -> str:
    return "".join((name or "").split()).lower()


@dataclass
class HeaderVerifyResult:
    matched: bool
    header_text: str
    expected: str
    candidates: list        # all texts seen in the header band (for diagnostics)


# Conversation-list / workbench markers used to tell which left-panel tab is up.
_CONTACTS_MARKERS = ("黑名单", "群聊", "团队", "未分组", "新的朋友")
_WORKBENCH_MARKERS = ("待发货", "待付款", "待处理", "待评价", "店铺数据",
                      "数据更新", "支付金额", "交易物流", "工作台")
# Left conversation-list column occupies roughly x in [0.12, 0.34] of the window.
_LIST_X_FRAC = 0.34
# The chat-pane header (buyer name) sits BELOW the global toolbar / store-stats
# bar and ABOVE the transcript — this y-band, right of the list, not the top 12%.
_HEADER_Y = (0.085, 0.22)


def _extent(ocr_data: list):
    """(x0, y0, x1, y1) bounding box of all OCR'd text (absolute coords)."""
    locs = [it["loc"] for it in ocr_data if it.get("loc")]
    xs = [v for lc in locs for v in (lc[1], lc[3])]
    ys = [v for lc in locs for v in (lc[0], lc[2])]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)


def header_band_texts(ocr_data: list) -> list:
    """Text lines in the CHAT-PANE header (right of the conversation list, below
    the global toolbar/store-stats bar), where the open conversation's buyer
    name sits.

    NOTE: the old version took the top 12% of the WHOLE window, which captured
    the store-stats bar (``今日接待 … 展开``) rather than the buyer name. This
    restricts to the chat pane and the header y-band instead.
    """
    locs = [it for it in ocr_data if it.get("loc")]
    if not locs:
        return []
    x0, y0, x1, y1 = _extent(ocr_data)
    w, h = (x1 - x0) or 1, (y1 - y0) or 1
    list_cut = x0 + _LIST_X_FRAC * w
    top, bot = y0 + _HEADER_Y[0] * h, y0 + _HEADER_Y[1] * h
    out = []
    for it in locs:
        lc = it["loc"]
        cx, cy = (lc[1] + lc[3]) / 2, (lc[0] + lc[2]) / 2
        if cx > list_cut and top <= cy <= bot:
            t = str(it.get("text") or "").strip()
            if t:
                out.append(t)
    return out


def is_reception_tab(ocr_data: list) -> bool:
    """True if the left panel shows the 正在接待 conversation list (not the
    联系人/contacts panel and not the 工作台/workbench home)."""
    joined = " ".join(str(it.get("text") or "") for it in ocr_data)
    if any(m in joined for m in _CONTACTS_MARKERS):
        return False
    if any(m in joined for m in _WORKBENCH_MARKERS):
        return False
    return "正在接待" in joined


def find_reception_tab_point(ocr_data: list):
    """Click-point (x, y) of the 正在接待 TAB, or None. 千牛 merges the tab bar
    into one OCR line (``正在接待全部买家其他消息…``) where 正在接待 is the first
    4 chars, so aim at the centre of that substring (char-proportional)."""
    cands = [it for it in ocr_data if "正在接待" in str(it.get("text") or "") and it.get("loc")]
    if not cands:
        return None
    cands.sort(key=lambda it: min(it["loc"][0], it["loc"][2]))   # topmost = tab bar
    it = cands[0]
    lc, txt = it["loc"], str(it.get("text") or "")
    x1, x2 = lc[1], lc[3]
    n = max(len(txt), 1)
    return (int(x1 + (x2 - x1) * (2.0 / n)), int((lc[0] + lc[2]) / 2))


def read_header_name(ocr_data: Optional[list] = None) -> str:
    """Best-guess buyer display name from the chat-header band ("" if none).

    The longest header-band line that is not an obvious UI control — used by
    the observer's learning pass to join a memory sender id to a screen name.
    """
    data = ocr_data if ocr_data is not None else ocr_qianniu_window()
    texts = header_band_texts(data)
    texts = [t for t in texts if len(t) <= 40]  # names are short; drop long UI strings
    return max(texts, key=len) if texts else ""


def transcript_contains(ocr_data: list, text: str) -> bool:
    """True if *text* (or a solid prefix of it) appears anywhere on screen —
    the content join that ties a memory message to the visible conversation."""
    needle = _norm(text)
    if len(needle) < 2:
        return False
    probe = needle[:16]
    return any(probe in _norm(str(it.get("text") or "")) for it in ocr_data)


def verify_header_name(expected_display_name: str,
                       ocr_data: Optional[list] = None) -> HeaderVerifyResult:
    """OCR the chat-header band and check it names *expected_display_name*.

    The feasibility study's fail-closed guard: a send proceeds only when the
    open conversation's header matches the intended buyer. Mismatch / nothing
    read → ``matched=False`` and the caller MUST abort the send.
    """
    expected = _norm(expected_display_name)
    if not expected:
        return HeaderVerifyResult(False, "", expected_display_name, [])

    data = ocr_data if ocr_data is not None else ocr_qianniu_window()
    if not data:
        return HeaderVerifyResult(False, "", expected_display_name, [])

    texts = header_band_texts(data)
    matched = any(expected in _norm(t) or _norm(t) in expected for t in texts)
    best = next((t for t in texts if expected in _norm(t) or _norm(t) in expected),
                texts[0] if texts else "")
    if not matched:
        logger.warning(f"[qianniu] header verify MISMATCH: expected "
                       f"{expected_display_name!r}, header band saw {texts[:6]}")
    return HeaderVerifyResult(matched, best, expected_display_name, texts)
