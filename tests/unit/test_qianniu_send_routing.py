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
