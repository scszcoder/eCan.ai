"""千牛 send routing: which conversation a reply may go to.

Alpha 2026-10-07: 大作战panda's chat was open while buyer sctisz sent
有樱桃味牙线吗 (a hidden conversation). The body check used to match ANY line on
screen, so sctisz's message showing as a 正在接待 list PREVIEW "confirmed"
panda's open chat -- sctisz's reply could have gone to panda. These tests pin
the body-only check and the bot's open-by-preview route.

Fake OCR layout (window 1000x800): list column x 120-340, chat header band
y 68-176 right of the list, chat body below y 112 right of the list.
"""
import asyncio
import json
from unittest.mock import patch

from agent.mcp.server.qianniu import qianniu_ocr, qianniu_tools


def _line(text, x, y):
    return {"text": text, "loc": [y - 8, x - 30, y + 8, x + 30]}


FRAME = [_line("千牛", 10, 5), _line("搜索", 200, 60), _line("发送", 990, 795)]   # window extent


def screen(open_buyer, body_lines, previews):
    """An OCR frame: the open chat's header + body, and list rows (name, preview)."""
    rows = list(FRAME) + [_line(open_buyer, 600, 120)]
    rows += [_line(t, 600, 300 + 40 * i) for i, t in enumerate(body_lines)]
    for i, (name, preview) in enumerate(previews):
        rows += [_line(name, 230, 300 + 80 * i), _line(preview, 230, 330 + 80 * i)]
    return rows


PANDA_OPEN = screen("大作战panda", ["有花生味牙线吗"],
                    [("sctisz", "有樱桃味牙线吗"), ("大作战panda", "有花生味牙线吗")])
SCTISZ_OPEN = screen("sctisz", ["有樱桃味牙线吗"],
                     [("sctisz", "有樱桃味牙线吗"), ("大作战panda", "有花生味牙线吗")])


def test_the_chat_window_is_chosen_over_the_bigger_workbench_window():
    # 0.9.99yd alpha: the app focused + OCR'd 倪好数码:小柒-千牛工作台 (the home page)
    # instead of the 接待中心 chat window. Bot rule: 接待 first, then largest.
    from types import SimpleNamespace
    from unittest.mock import patch as _patch
    workbench = SimpleNamespace(title="倪好数码:小柒-千牛工作台", hwnd=1, width=1600, height=850)
    chat = SimpleNamespace(title="倪好数码:小柒-接待中心", hwnd=2, width=1200, height=700)
    with _patch("agent.mcp.server.wechat.platform_utils.find_windows_by_title",
                return_value=[workbench, chat, workbench]):
        assert qianniu_ocr.qianniu_chat_window() is chat
    qianniu_ocr._last_window_set[0] = None
    with _patch("agent.mcp.server.wechat.platform_utils.find_windows_by_title",
                return_value=[workbench]), _patch.object(qianniu_ocr.logger, "warning") as warn:
        assert qianniu_ocr.qianniu_chat_window() is workbench
    assert warn.called and "接待中心" in warn.call_args[0][0]


def test_a_list_preview_is_not_the_open_chat_body():
    assert qianniu_ocr.transcript_contains(PANDA_OPEN, "有花生味牙线吗") is True
    assert qianniu_ocr.transcript_contains(PANDA_OPEN, "有樱桃味牙线吗") is False   # only in the list


def test_find_conversation_row_finds_the_hidden_buyer_by_preview():
    pt, name = qianniu_ocr.find_conversation_row(PANDA_OPEN, "有樱桃味牙线吗")
    assert pt == (230, 330) and name == "sctisz"
    assert qianniu_ocr.find_conversation_row(PANDA_OPEN, "没有这条") == (None, "")


def _send(frames, **inp):
    clicks, typed = [], []
    seq = iter(frames)
    with patch.object(qianniu_tools, "ocr_qianniu_window", side_effect=lambda: next(seq)), \
            patch.object(qianniu_tools, "_foreground", return_value=True), \
            patch.object(qianniu_tools, "_click", side_effect=lambda x, y: clicks.append((x, y))), \
            patch.object(qianniu_tools, "_humanize"), \
            patch.object(qianniu_tools, "_type_and_send", side_effect=typed.append), \
            patch.object(qianniu_tools, "save_failure_shot"):
        out = asyncio.run(qianniu_tools.qianniu_send(None, {"input": inp}))
    return json.loads(out[0].text), clicks, typed


def test_reply_to_a_hidden_buyer_opens_their_row_then_sends():
    # open chat = panda; the reply is for sctisz (name unknown to the agent).
    res, clicks, typed = _send([PANDA_OPEN, PANDA_OPEN, SCTISZ_OPEN, SCTISZ_OPEN],
                               buyer_display_name="", chat_msg="有的，樱桃味有货",
                               expect_message_text="有樱桃味牙线吗")
    assert res["chat_sent"] is True and typed == ["有的，樱桃味有货"]
    assert clicks == [(230, 330)]                     # sctisz's row, never panda's chat


def test_the_panda_case_never_sends_into_the_wrong_chat():
    # The row click does not switch (stays on panda): refuse, do not type.
    res, _clicks, typed = _send([PANDA_OPEN, PANDA_OPEN, PANDA_OPEN],
                                buyer_display_name="大作战panda", chat_msg="有的，樱桃味有货",
                                expect_message_text="有樱桃味牙线吗", auto_open=True)
    assert res["chat_sent"] is False and typed == []


def test_a_short_greeting_needs_the_header_too():
    hi_open = screen("大作战panda", ["在吗"], [("sctisz", "在吗")])
    res, _c, typed = _send([hi_open], buyer_display_name="", chat_msg="在的",
                           expect_message_text="在吗", auto_open=False)
    assert res["chat_sent"] is False and typed == [] and "too short" in res["error"]
    res, _c, typed = _send([hi_open], buyer_display_name="大作战panda", chat_msg="在的",
                           expect_message_text="在吗", auto_open=False)
    assert res["chat_sent"] is True and typed == ["在的"]


def test_without_message_text_the_header_is_the_gate():
    res, _c, typed = _send([PANDA_OPEN], buyer_display_name="大作战panda", chat_msg="您好",
                           auto_open=False)
    assert res["chat_sent"] is True and typed == ["您好"]
    res, _c, typed = _send([PANDA_OPEN], buyer_display_name="sctisz", chat_msg="您好",
                           auto_open=False)
    assert res["chat_sent"] is False and typed == []


# The customer's real 接待中心 screen, alpha 2026-10-07 (0.9.99yi): (text, cx, cy)
# from the failure dump. A left nav strip (工作台/消息/进店 at x~96) shifts the
# list to x~200-390 and the buyer's bubbles to x~580 -- the fixed 34% cut sat at
# x~620, so the body check rejected "有黑人牙膏吗" and "open by preview" clicked
# a chat bubble.
def _real(text, cx, cy):
    half = max(len(text), 1) * 7
    return {"text": text, "loc": [cy - 8, cx - half, cy + 8, cx + half]}


REAL_SCREEN = [_real(t, x, y) for t, x, y in [
    ("×", 1662, 24), ("小柒", 213, 68), ("在线停止辅助离线", 291, 96), ("今日接待", 493, 98),
    ("联系人、订单号、聊天记录", 271, 152), ("智能客服全新升级，助力客服高效接待！", 1289, 165),
    ("操作指南", 1465, 165), ("工作台", 96, 203), ("好评100.00%企超级", 1280, 213),
    ("sctisz", 1152, 214), ("正在接待全部买家其他消息", 252, 229), ("有蓝色牙线吗？", 586, 240),
    ("消息", 97, 292), ("倪好数码：小柒", 959, 302), ("正在接待1", 202, 316),
    ("这边帮您核实一下，稍后回复您。", 867, 349), ("sctisz", 231, 361), ("3秒", 391, 362),
    ("进店", 97, 382), ("节日有打折吗", 254, 387), ("sctisz", 538, 443), ("有粉色牙线吗？", 586, 490),
    ("sctisz", 538, 552), ("有黑人牙膏吗", 580, 599), ("这边帮您核实一下，稍后回复您。", 867, 708),
    ("发送", 1600, 1100),
]]


def test_on_the_real_screen_the_buyers_bubble_is_chat_body():
    assert qianniu_ocr.transcript_contains(REAL_SCREEN, "有黑人牙膏吗")
    assert not qianniu_ocr.transcript_contains(REAL_SCREEN, "节日有打折吗")   # list preview only


def test_on_the_real_screen_open_by_preview_clicks_the_list_row_not_a_bubble():
    point, name = qianniu_ocr.find_conversation_row(REAL_SCREEN, "节日有打折吗")
    assert point == (254, 387) and name == "sctisz"
    assert qianniu_ocr.find_conversation_row(REAL_SCREEN, "有黑人牙膏吗") == (None, "")


def test_on_the_real_screen_the_rating_badge_is_not_the_buyer_name():
    assert qianniu_ocr.read_header_name(REAL_SCREEN) == "sctisz"


def test_the_buyer_name_is_the_one_beside_the_rating_badge_not_another_name_in_the_band():
    # Alpha 2026-10-07 (yj multi-buyer): a new buyer was learned as 'sctisz'
    # (another buyer); another as the timestamp '2026-10-714:51:37'.
    base = [it for it in REAL_SCREEN if it["text"] not in ("sctisz", "好评100.00%企超级")]
    band = [_real("sctisz", 521, 149), _real("2026-10-714:51:37", 700, 180),
            _real("t_8812", 1152, 214), _real("好评100.00%企超级", 1280, 213)]
    assert qianniu_ocr.read_header_name(base + band) == "t_8812"
