"""千牛 OCR primitives — capture the AliWorkbench window and read text.

Clones the proven wechat local-OCR recipe (``wechat_tools._do_ocr_local``)
for the 千牛 window, and adds the **select-verify** primitive the feasibility
study (§5) requires: OCR the chat-header buyer-name band and compare it to the
intended recipient before any send. Read-only — this module never sends input.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

from utils.logger_helper import logger_helper as logger

# The Windows title alias for 千牛 is registered in
# agent/ec_skills/ocr/image_prep.py::get_top_visible_window (_WIN_ALIASES).
_QIANNIU_WIN_KW = "千牛"
_OCR_MAX_LONG_SIDE = 1500            # match wechat_tools; resize before OCR
_HEADER_BAND_FRAC = 0.12             # top 12% of the window holds the buyer-name header
_TMP_SHOT = os.path.join(tempfile.gettempdir(), "qianniu_ocr_tmp.png")
_SHOTS_KEEP = 20


def ocr_dump(ocr_data: list, limit: int = 80) -> str:
    """Every OCR line as ``text@(x,y)`` (centre, absolute coords), top to bottom.
    Logged on any failed check: it is what OCR-geometry calibration needs."""
    rows = []
    for it in ocr_data or []:
        lc = it.get("loc")
        t = str(it.get("text") or "").strip()
        if not lc or not t:
            continue
        rows.append(((lc[0] + lc[2]) / 2, (lc[1] + lc[3]) / 2, t))
    rows.sort()
    out = [f"{t}@({int(x)},{int(y)})" for y, x, t in rows[:limit]]
    more = f" …+{len(rows) - limit}" if len(rows) > limit else ""
    return f"{len(rows)} lines: " + " | ".join(out) + more


def save_failure_shot(reason: str) -> str:
    """Keep the last OCR'd screenshot as <runlogs>/qianniu_ocr/<time>_<reason>.png
    (the newest ``_SHOTS_KEEP``) so a failed check can be seen, not guessed.
    Local only; ECAN_QIANNIU_SAVE_SHOTS=0 turns it off. Returns the path or ""."""
    if os.environ.get("ECAN_QIANNIU_SAVE_SHOTS", "1") == "0" or not os.path.exists(_TMP_SHOT):
        return ""
    try:
        from config.app_info import app_info
        folder = os.path.join(app_info.appdata_path, "runlogs", "qianniu_ocr")
        os.makedirs(folder, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)[:40]
        path = os.path.join(folder, f"{time.strftime('%Y%m%d_%H%M%S')}_{safe}.png")
        shutil.copyfile(_TMP_SHOT, path)
        shots = sorted(f for f in os.listdir(folder) if f.endswith(".png"))
        for old in shots[:-_SHOTS_KEEP]:
            os.remove(os.path.join(folder, old))
        logger.info(f"[qianniu] screenshot kept for '{reason}': {path}")
        return path
    except Exception as exc:
        logger.warning(f"[qianniu] could not keep screenshot ({exc})")
        return ""


# 千牛 windows by title. The CHAT window (接待中心) is a separate top-level window
# from the 千牛工作台 home; chats, the 正在接待 list and the composer live only in
# the former. The standalone bot (qianniu_cs_bot v0.15) prefers 接待 then the
# largest; the app used "the first 千牛 window", which on the 0.9.99yd alpha was
# 倪好数码:小柒-千牛工作台 -- the workbench home, so every check saw a promo page.
QIANNIU_WIN_TITLES = ("接待", "千牛", "AliWorkbench", "阿里旺旺")
_CHAT_WIN_MARK = "接待"
_last_window_set = [None]


def qianniu_chat_window():
    """The 千牛 window to act on (WindowInfo with .title), or None: a 接待 (chat)
    window first, then the largest. Logs the candidates when they change and
    warns when no chat window is open."""
    from agent.mcp.server.wechat.platform_utils import find_windows_by_title
    seen, wins = set(), []
    for w in find_windows_by_title(list(QIANNIU_WIN_TITLES)):
        key = getattr(w, "hwnd", None) or w.title
        if key not in seen:
            seen.add(key)
            wins.append(w)
    wins.sort(key=lambda w: (_CHAT_WIN_MARK in (w.title or ""),
                             max(getattr(w, "width", 0) or 0, 1) * max(getattr(w, "height", 0) or 0, 1)),
              reverse=True)
    titles = tuple(w.title for w in wins)
    if titles != _last_window_set[0]:
        _last_window_set[0] = titles
        logger.info(f"[qianniu] 千牛 windows: {list(titles)}; using {titles[0] if titles else None!r}")
        if titles and not any(_CHAT_WIN_MARK in t for t in titles):
            logger.warning("[qianniu] no 接待中心 (chat) window is open -- the 正在接待 list and the "
                           "chat composer are only there; open 接待中心 in 千牛")
    return wins[0] if wins else None


# ── Faster reads: skip the right customer panel ──────────────────────────────
# A read cost 6-7 s on the alpha customer's PC (alpha 2026-10-07): recognition
# time grows with the number of text lines, and the right customer panel below
# its name/badge strip (store identity, orders, a product grid with prices) is
# the densest text on screen -- and nothing reads it. It is painted white before
# OCR, so every coordinate stays where it was. Its left edge is calibrated from
# a FULL read (the panel's own labels); no calibration -> no blanking, and a
# full read recalibrates every _FULL_READ_EVERY reads or when the window size
# changes.
_PANEL_LABELS = ("店铺身份", "店铺消费", "邀请关注", "添加备注", "邀请入会", "足迹", "商品ID")
_PANEL_KEEP_TOP_FRAC = 0.25      # the buyer name + rating badge sit above this
_FULL_READ_EVERY = 20
_panel_cal: dict = {}            # (window w, h) -> panel left x, window-relative px
_reads = [0]


def _panel_left(ocr_rel: list, win_w: int):
    """Window-relative x where the right customer panel starts, or None. Uses
    the panel's own labels; must leave the left 55% (list + chat) alone."""
    xs = [it["loc"][1] for it in ocr_rel or []
          if it.get("loc") and any(lb in str(it.get("text") or "") for lb in _PANEL_LABELS)]
    if not xs:
        return None
    left = min(xs) - 12
    return left if left > 0.55 * win_w else None


def ocr_qianniu_window() -> list:
    """Capture the 千牛 chat window and run local OCR. Returns ocr_data in remote
    format with **absolute screen coords** (``loc=[y1,x1,y2,x2]``), or []."""
    from PIL import ImageDraw
    from agent.ec_skills.ocr.image_prep import captureScreen, _apply_window_offset
    from agent.mcp.server.local_ocr.paddle_ocr import (
        _get_ocr, normalize_to_remote_format, scale_ocr_coordinates,
    )

    t0 = time.monotonic()
    win = qianniu_chat_window()
    keyword = win.title if win and win.title else _QIANNIU_WIN_KW   # exact title of the chosen window
    try:
        screen_img, _image_bytes, window_rect = captureScreen(keyword)
    except Exception as exc:
        logger.warning(f"[qianniu] capture of the 千牛 window failed: {exc}")
        raise
    orig_w, orig_h = screen_img.size

    scale_x, scale_y = 1.0, 1.0
    long_side = max(orig_w, orig_h)
    if long_side > _OCR_MAX_LONG_SIDE:
        ratio = _OCR_MAX_LONG_SIDE / long_side
        new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
        screen_img = screen_img.resize((new_w, new_h))
        scale_x, scale_y = orig_w / new_w, orig_h / new_h

    _reads[0] += 1
    panel_x = _panel_cal.get((orig_w, orig_h))
    blank = panel_x is not None and _reads[0] % _FULL_READ_EVERY != 0
    if blank:
        ImageDraw.Draw(screen_img).rectangle(
            [int(panel_x / scale_x), int(orig_h * _PANEL_KEEP_TOP_FRAC / scale_y),
             screen_img.width, screen_img.height], fill="white")
    screen_img.save(_TMP_SHOT)

    try:
        # use_cls=False: 千牛 text is never rotated. A per-call option -- the
        # shared engine's settings (WeChat OCR) are not changed.
        raw, elapsed = _get_ocr()(_TMP_SHOT, use_cls=False)
    except Exception as exc:
        logger.error(f"[qianniu] local OCR failed: {exc}")
        return []
    result = normalize_to_remote_format(raw)
    if scale_x != 1.0 or scale_y != 1.0:
        result = scale_ocr_coordinates(result, scale_x, scale_y)
    if not blank:    # a full read: (re)calibrate the panel edge for this window size
        left = _panel_left(result, orig_w)
        if left != _panel_cal.get((orig_w, orig_h)):
            logger.info(f"[qianniu] customer panel edge for window {orig_w}x{orig_h}: x={left} "
                        f"({'blanked below the name strip from now on' if left else 'not found; full reads'})")
        if left:
            _panel_cal[(orig_w, orig_h)] = left
        else:
            _panel_cal.pop((orig_w, orig_h), None)
    result = _apply_window_offset(result, window_rect)
    split = "/".join(f"{x:.1f}" for x in (elapsed or [])) if isinstance(elapsed, (list, tuple)) else "?"
    logger.info(f"[qianniu] OCR window={keyword!r} rect={window_rect} img={orig_w}x{orig_h} "
                f"lines={len(result)} {'panel-blanked' if blank else 'full'} det/cls/rec={split}s "
                f"in {int((time.monotonic() - t0) * 1000)}ms")
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


# Lines that span the 正在接待 list column: the tab bar and the search box.
_LIST_ANCHORS = ("正在接待全部", "全部买家", "联系人、订单号", "订单号、聊天记录")


def _list_column(ocr_data: list):
    """(left, right) x of the conversation-list column. Read from the tab bar /
    search box when on screen: the fixed fractions assumed no left nav strip,
    and on a window with one (alpha 2026-10-07) the cut landed at x~620 while
    buyer bubbles sat at x~580 -- the body check rejected the buyer's message
    and "open by preview" clicked a chat bubble instead of the list row."""
    anchors = [it["loc"] for it in ocr_data or []
               if it.get("loc") and any(a in str(it.get("text") or "") for a in _LIST_ANCHORS)]
    if anchors:
        return min(lc[1] for lc in anchors) - 10, max(lc[3] for lc in anchors) + 10
    x0, _y0, x1, _y1 = _extent(ocr_data or [])
    w = (x1 - x0) or 1
    return x0 + 0.12 * w, x0 + _LIST_X_FRAC * w


def header_band_items(ocr_data: list) -> list:
    """[(text, (cx, cy))] in the chat-pane header band (see header_band_texts)."""
    locs = [it for it in ocr_data or [] if it.get("loc")]
    if not locs:
        return []
    x0, y0, x1, y1 = _extent(locs)
    h = (y1 - y0) or 1
    list_cut = _list_column(locs)[1]
    top, bot = y0 + _HEADER_Y[0] * h, y0 + _HEADER_Y[1] * h
    out = []
    for it in locs:
        lc = it["loc"]
        cx, cy = (lc[1] + lc[3]) / 2, (lc[0] + lc[2]) / 2
        t = str(it.get("text") or "").strip()
        if t and cx > list_cut and top <= cy <= bot:
            out.append((t, (int(cx), int(cy))))
    return out


def header_band_texts(ocr_data: list) -> list:
    """Text lines in the CHAT-PANE header (right of the conversation list, below
    the global toolbar/store-stats bar), where the open conversation's buyer
    name sits.

    NOTE: the old version took the top 12% of the WHOLE window, which captured
    the store-stats bar (``今日接待 … 展开``) rather than the buyer name. This
    restricts to the chat pane and the header y-band instead.
    """
    return [t for t, _xy in header_band_items(ocr_data)]


def is_reception_tab(ocr_data: list) -> bool:
    """True if the left panel shows the 正在接待 conversation list (not the
    联系人/contacts panel and not the 工作台/workbench home)."""
    joined = " ".join(str(it.get("text") or "") for it in ocr_data)
    # The list's own tab bar ("正在接待全部买家其他消息") is shown only on that
    # list. Checked first: the 接待中心 window's left nav always shows "工作台",
    # so every send "left" the tab, clicked it and re-OCR'd (~7 s; alpha
    # 2026-10-07, "after clicking 正在接待: on_tab=False" every time).
    if any("正在接待" in str(it.get("text") or "") and "全部买家" in str(it.get("text") or "")
           for it in ocr_data):
        return True
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
    from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat.name_map import (
        looks_like_buyer_name,
    )
    data = ocr_data if ocr_data is not None else ocr_qianniu_window()
    items = header_band_items(data)
    names = [(t, xy) for t, xy in items if looks_like_buyer_name(t)]   # not banners / UI labels
    if not names:
        return ""
    # The open chat's buyer name sits just left of its rating badge
    # ("sctisz  好评100.00%企超级"); other names can share the band.
    badges = [xy for t, xy in items if "好评" in t or "%" in t]
    if badges:
        bx, by = badges[0]
        row = [(bx - xy[0], t) for t, xy in names if abs(xy[1] - by) <= 15 and xy[0] < bx]
        if row:
            return min(row)[1]
    return max((t for t, _xy in names), key=len)


# Chat BODY = right of the conversation list, below the chat header. Values from
# the standalone bot (live-tuned on the customer client, qianniu_cs_bot v0.15).
_BODY_TOP_FRAC = 0.14
_BODY_PROBE_CHARS = 6


def transcript_contains(ocr_data: list, text: str) -> bool:
    """True if the first chars of *text* appear in the open conversation's chat
    BODY — the content join that ties a memory message to the open chat.

    Only the body counts. It used to match ANY line on screen, so a hidden
    buyer's message showing as a 正在接待 list PREVIEW "confirmed" whichever
    conversation was open, and their reply could be sent to that other buyer
    (and the learning pass could bind their id to the wrong name). Strict
    contiguous prefix, no fuzzy match: Chinese messages share characters, and a
    false negative (skip a send) is acceptable where a false positive is not."""
    needle = _norm(text)
    if len(needle) < 2:
        return False
    probe = needle[:_BODY_PROBE_CHARS]
    locs = [it for it in ocr_data or [] if it.get("loc")]
    if not locs:
        return False
    x0, y0, x1, y1 = _extent(locs)
    h = (y1 - y0) or 1
    cut, top = _list_column(locs)[1], y0 + _BODY_TOP_FRAC * h
    for it in locs:
        lc = it["loc"]
        cx, cy = (lc[1] + lc[3]) / 2, (lc[0] + lc[2]) / 2
        if cx > cut and cy > top and probe in _norm(str(it.get("text") or "")):
            return True
    return False


# 正在接待 list's non-conversation labels — ported from the bot's
# find_conversation_row (the column itself comes from _list_column).
_LIST_SKIP = ("全部买家", "其他消息", "联系人", "列表分组", "最后一句", "消息",
              "离线", "分组", "正在接待")
_TIMEISH = re.compile(r"^[\d:：]+$|小时|分钟|刚刚|昨天|星期|周|天前|:|^\d+秒$")


def find_conversation_row(ocr_data: list, text: str):
    """(click point, buyer name) of the 正在接待 row whose PREVIEW shows *text*,
    or (None, ""). A new message bumps its conversation up and changes its
    preview, so this finds a hidden buyer with no name and no search; the name
    is the non-time list line just above the preview (≤70 px)."""
    probe = _norm(text)[:4]           # previews are truncated: a short prefix
    locs = [it for it in ocr_data or [] if it.get("loc") and str(it.get("text") or "").strip()]
    if not probe or not locs:
        return None, ""
    left, right = _list_column(locs)
    lines = []
    for it in locs:
        lc = it["loc"]
        cx, cy = (lc[1] + lc[3]) / 2, (lc[0] + lc[2]) / 2
        if left <= cx <= right:
            lines.append((cy, cx, str(it["text"]).strip()))
    cands = sorted((cy, cx) for cy, cx, t in lines
                   if probe in _norm(t) and not any(s in t for s in _LIST_SKIP))
    if not cands:
        return None, ""
    cy, cx = cands[0]                 # topmost: the newest message is at the top
    above = sorted((cy - ly, t) for ly, _lx, t in lines
                   if 0 < cy - ly <= 70 and not any(s in t for s in _LIST_SKIP)
                   and not (_TIMEISH.search(t) and len(t) <= 8) and _norm(t)[:4] != probe)
    return (int(cx), int(cy)), (above[0][1] if above else "")


# ── Cold start (alpha 2026-10-08) ────────────────────────────────────────────
# At startup 千牛's memory holds no buyer text for chats that were already
# waiting, so the memory observer cannot see them ("冷启动出不来，得再顶一句").
# These read the screen instead: the 正在接待 rows, and who spoke last in a chat.
_ROW_PREVIEW_DY = (12, 45)        # a row = name line, preview line this far below
_TIMESTAMP_LINE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}\s*\d{1,2}:\d{2}|^\d{1,2}:\d{2}(:\d{2})?$")
_BODY_NOISE = ("已读", "未读", "当前用户来自", "发送", "按Enter", "请输入")
_WORDY_RE = re.compile(r"[一-鿿A-Za-z0-9]")


def conversation_rows(ocr_data: list, limit: int = 8) -> list:
    """[(name, preview, (x, y))] for the 正在接待 list, top to bottom."""
    left, right = _list_column(ocr_data)
    # Rows sit below the list's tab bar; above it are the account/status lines.
    tab_y = max(((it["loc"][0] + it["loc"][2]) / 2 for it in ocr_data or []
                 if it.get("loc") and any(a in str(it.get("text") or "") for a in _LIST_ANCHORS)),
                default=0)
    lines = []
    for it in ocr_data or []:
        lc, t = it.get("loc"), str(it.get("text") or "").strip()
        if not lc or not t:
            continue
        cx, cy = (lc[1] + lc[3]) / 2, (lc[0] + lc[2]) / 2
        # A red unread dot / badge OCRs as "." or a digit: not a row line
        # (yn alpha: row name '.', its "message" 「个关闭」 was dispatched).
        if len(_WORDY_RE.findall(t)) < 2:
            continue
        if cy > tab_y + 5 and left <= cx <= right and not any(s in t for s in _LIST_SKIP) \
                and not (_TIMEISH.search(t) and len(t) <= 8):
            lines.append((cy, cx, t))
    lines.sort()
    rows, i = [], 0
    while i < len(lines) - 1 and len(rows) < limit:
        (y1, x1, t1), (y2, _x2, t2) = lines[i], lines[i + 1]
        if _ROW_PREVIEW_DY[0] <= y2 - y1 <= _ROW_PREVIEW_DY[1]:
            rows.append((t1, t2, (int(x1), int(y1))))
            i += 2
        else:
            i += 1
    return rows


def _colon_norm(s: str) -> str:
    return _norm(s).replace("：", ":")


def last_turn(ocr_data: list, buyer_name: str, store_label: str) -> tuple:
    """Who spoke last in the open chat: ("buyer", text) / ("store", "") /
    ("unknown", ""). Each message has a label line -- the buyer's name, or the
    store account (``store_label``, from the window title) -- and the lowest
    label is the last turn. *text* = the message lines under the buyer's label."""
    _left, list_right = _list_column(ocr_data)
    _x0, y0, _x1, y1 = _extent(ocr_data or [])
    top = y0 + _HEADER_Y[1] * ((y1 - y0) or 1)
    body = []
    for it in ocr_data or []:
        lc, t = it.get("loc"), str(it.get("text") or "").strip()
        if not lc or not t:
            continue
        cx, cy = (lc[1] + lc[3]) / 2, (lc[0] + lc[2]) / 2
        if cx > list_right and cy > top:
            body.append((cy, cx, t))
    body.sort()
    bn, sl = _norm(buyer_name), _colon_norm(store_label)
    labels = [(cy, "buyer") for cy, _cx, t in body if bn and _norm(t).startswith(bn)] + \
             [(cy, "store") for cy, _cx, t in body if sl and sl in _colon_norm(t)]
    if not labels:
        return "unknown", ""
    hy, side = max(labels)
    if side != "buyer":
        return side, ""
    text = [t for cy, _cx, t in body
            if hy < cy <= hy + 150 and not _norm(t).startswith(bn) and not _TIMESTAMP_LINE.search(t)
            and not any(n in t for n in _BODY_NOISE) and len(_WORDY_RE.findall(t)) >= 2]   # not "..0"
    joined = "".join(text[:3])
    return ("buyer", joined) if len(_WORDY_RE.findall(joined)) >= 2 else ("unknown", "")


def verify_header_name(expected_display_name: str,
                       ocr_data: Optional[list] = None,
                       quiet: bool = False) -> HeaderVerifyResult:
    """OCR the chat-header band and check it names *expected_display_name*.

    The feasibility study's fail-closed guard: a send proceeds only when the
    open conversation's header matches the intended buyer. Mismatch / nothing
    read → ``matched=False`` and the caller MUST abort the send.
    """
    expected = _norm(expected_display_name)
    if not expected:
        logger.info("[qianniu] header verify skipped: no expected buyer name")
        return HeaderVerifyResult(False, "", expected_display_name, [])

    data = ocr_data if ocr_data is not None else ocr_qianniu_window()
    if not data:
        logger.warning(f"[qianniu] header verify for {expected_display_name!r}: OCR read nothing")
        return HeaderVerifyResult(False, "", expected_display_name, [])

    texts = header_band_texts(data)
    matched = any(expected in _norm(t) or _norm(t) in expected for t in texts)
    best = next((t for t in texts if expected in _norm(t) or _norm(t) in expected),
                texts[0] if texts else "")
    if matched:
        logger.info(f"[qianniu] header verify OK: {expected_display_name!r} ~ {best!r}")
    elif quiet:   # informational only (the caller's gate is something else)
        logger.info(f"[qianniu] header does not show {expected_display_name!r} "
                    f"(band {texts[:8]}); not the gate here")
    else:
        logger.warning(f"[qianniu] header verify MISMATCH: expected "
                       f"{expected_display_name!r}, header band saw {texts[:12]}; "
                       f"screen {ocr_dump(data)}")
        save_failure_shot("header_mismatch")
    return HeaderVerifyResult(matched, best, expected_display_name, texts)
