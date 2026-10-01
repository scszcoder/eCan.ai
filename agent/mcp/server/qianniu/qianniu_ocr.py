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


def verify_header_name(expected_display_name: str) -> HeaderVerifyResult:
    """OCR the chat-header band and check it names *expected_display_name*.

    The feasibility study's fail-closed guard: a send proceeds only when the
    open conversation's header matches the intended buyer. Mismatch / nothing
    read → ``matched=False`` and the caller MUST abort the send.
    """
    expected = _norm(expected_display_name)
    if not expected:
        return HeaderVerifyResult(False, "", expected_display_name, [])

    ocr_data = ocr_qianniu_window()
    if not ocr_data:
        return HeaderVerifyResult(False, "", expected_display_name, [])

    # Header band: the top _HEADER_BAND_FRAC of the window in absolute coords.
    ys = [min(it["loc"][0], it["loc"][2]) for it in ocr_data if it.get("loc")]
    if not ys:
        return HeaderVerifyResult(False, "", expected_display_name, [])
    top = min(ys)
    bottom = max(max(it["loc"][0], it["loc"][2]) for it in ocr_data if it.get("loc"))
    band_cut = top + (bottom - top) * _HEADER_BAND_FRAC

    band = [it for it in ocr_data
            if it.get("loc") and min(it["loc"][0], it["loc"][2]) <= band_cut]
    texts = [str(it.get("text") or "").strip() for it in band]
    texts = [t for t in texts if t]

    matched = any(expected in _norm(t) or _norm(t) in expected for t in texts)
    best = next((t for t in texts if expected in _norm(t) or _norm(t) in expected),
                texts[0] if texts else "")
    if not matched:
        logger.warning(f"[qianniu] header verify MISMATCH: expected "
                       f"{expected_display_name!r}, header band saw {texts[:6]}")
    return HeaderVerifyResult(matched, best, expected_display_name, texts)
