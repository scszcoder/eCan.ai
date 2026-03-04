"""
Scroll calibration utility for RPA automation.

When pixel_per_scroll is unknown (0), this module runs a two-step calibration:
  1. OCR the scrollable area, pick a unique anchor text near the vertical
     middle of the region, record its Y coordinate.
  2. Scroll a small known amount (e.g. 3 units), OCR again, find the same
     anchor text, measure the Y delta.
  3. pixel_per_scroll = abs(delta_y) / scroll_units

The calibrated value is returned so the caller (and the LLM) can reuse it
for precise scrolling in subsequent calls.
"""

import time

from utils.logger_helper import logger_helper as logger

# Small scroll amount used for calibration measurement
_CALIBRATION_SCROLL_UNITS = 3
_POST_SCROLL_DELAY = 0.8


def _find_anchor_text(ocr_data, bounds):
    """Pick a unique OCR text item near the vertical middle of *bounds*.

    Args:
        ocr_data: list of OCR items (dicts with text, loc, txt_struct …)
        bounds: dict with keys top, bottom, left, right (pixel coords)

    Returns:
        (anchor_text: str, anchor_cy: int) or (None, None)
        anchor_text is the full paragraph text, anchor_cy is its centre Y.
    """
    if not ocr_data or not isinstance(ocr_data, list):
        return None, None

    mid_y = (bounds["top"] + bounds["bottom"]) // 2
    # Collect candidates: OCR items whose centre is inside bounds
    candidates = []
    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text or len(text) < 2:
            continue

        # Determine centre Y from loc [y1, x1, y2, x2] or txt_struct box
        cy, cx = None, None
        loc = item.get("loc")
        if loc and len(loc) == 4:
            cy = (loc[0] + loc[2]) // 2
            cx = (loc[1] + loc[3]) // 2
        else:
            for ts in item.get("txt_struct", []):
                box = ts.get("box")  # [x1, y1, x2, y2]
                if box and len(box) == 4:
                    cy = (box[1] + box[3]) // 2
                    cx = (box[0] + box[2]) // 2
                    break

        if cy is None or cx is None:
            continue

        # Must be inside the bounding region
        if not (bounds["top"] <= cy <= bounds["bottom"] and
                bounds["left"] <= cx <= bounds["right"]):
            continue

        dist = abs(cy - mid_y)
        candidates.append((dist, text, cy))

    if not candidates:
        logger.debug("[scroll_cal] No anchor candidates found inside bounds")
        return None, None

    # Sort by distance to vertical middle (prefer closest to centre)
    candidates.sort(key=lambda t: t[0])

    # Pick the first candidate that appears exactly once in ocr texts
    # (uniqueness helps re-identification after scroll)
    all_texts = [
        (item.get("text") or "").strip().lower()
        for item in ocr_data if isinstance(item, dict)
    ]
    for _dist, text, cy in candidates:
        count = sum(1 for t in all_texts if text.strip().lower() in t or t in text.strip().lower())
        if count == 1:
            logger.debug(f"[scroll_cal] Selected anchor: '{text[:40]}' at cy={cy} (dist_from_mid={_dist})")
            return text, cy

    # Fallback: just use the closest to middle even if not unique
    _, text, cy = candidates[0]
    logger.debug(f"[scroll_cal] Fallback anchor (not unique): '{text[:40]}' at cy={cy}")
    return text, cy


def _find_text_cy(ocr_data, target_text):
    """Find the centre Y of a specific text in OCR data.
    Returns cy (int) or None.
    """
    if not ocr_data or not target_text:
        return None
    target_lower = target_text.strip().lower()

    for item in ocr_data:
        if not isinstance(item, dict):
            continue
        # txt_struct level
        for ts in item.get("txt_struct", []):
            ts_text = (ts.get("text") or "").strip().lower()
            if target_lower in ts_text or ts_text in target_lower:
                box = ts.get("box")
                if box and len(box) == 4:
                    return (box[1] + box[3]) // 2
        # paragraph level
        text = (item.get("text") or "").strip().lower()
        if target_lower in text or text in target_lower:
            loc = item.get("loc")
            if loc and len(loc) == 4:
                return (loc[0] + loc[2]) // 2
    return None


async def calibrate_scroll(do_ocr_fn, bounds, scroll_position_xy=None):
    """Run scroll calibration and return pixel_per_scroll (int).

    Args:
        do_ocr_fn:  async callable() -> ocr_data list
                    (caller wraps their OCR call)
        bounds:     dict(top, bottom, left, right) — pixel region of
                    the scrollable area (absolute screen coords)
        scroll_position_xy: (x, y) tuple — where to place the mouse
                    before scrolling.  If None, uses centre of bounds.

    Returns:
        (pixel_per_scroll: int, ocr_data_after: list)
        pixel_per_scroll is 0 if calibration failed.
    """
    import pyautogui

    logger.info(f"[scroll_cal] Starting calibration in bounds {bounds}")

    # Step 1: OCR before scroll
    ocr_before = await do_ocr_fn()
    anchor_text, anchor_cy_before = _find_anchor_text(ocr_before, bounds)
    if anchor_text is None:
        logger.warning("[scroll_cal] Could not find suitable anchor text — calibration failed")
        return 0, ocr_before

    logger.debug(f"[scroll_cal] Anchor before scroll: '{anchor_text[:40]}' cy={anchor_cy_before}")

    # Step 2: Position mouse and scroll a small amount
    if scroll_position_xy:
        sx, sy = scroll_position_xy
    else:
        sx = (bounds["left"] + bounds["right"]) // 2
        sy = (bounds["top"] + bounds["bottom"]) // 2

    logger.debug(f"[scroll_cal] Moving mouse to ({sx},{sy}), scrolling {_CALIBRATION_SCROLL_UNITS} units down")
    pyautogui.moveTo(sx, sy)
    time.sleep(0.2)

    from pynput.mouse import Controller as _MouseCtrl
    _MouseCtrl().scroll(0, -_CALIBRATION_SCROLL_UNITS)
    time.sleep(_POST_SCROLL_DELAY)

    # Step 3: OCR after scroll, find same anchor
    ocr_after = await do_ocr_fn()
    anchor_cy_after = _find_text_cy(ocr_after, anchor_text)

    if anchor_cy_after is None:
        logger.warning(f"[scroll_cal] Anchor '{anchor_text[:40]}' not found after scroll — calibration failed")
        return 0, ocr_after

    delta_y = abs(anchor_cy_after - anchor_cy_before)
    if delta_y == 0:
        logger.warning("[scroll_cal] Delta Y is 0 — scroll had no effect, calibration failed")
        return 0, ocr_after

    pps = delta_y / _CALIBRATION_SCROLL_UNITS
    # Round to int
    pps = max(1, round(pps))
    logger.info(f"[scroll_cal] Calibration result: anchor moved {delta_y}px over "
                f"{_CALIBRATION_SCROLL_UNITS} units → pixel_per_scroll={pps}")
    return pps, ocr_after
