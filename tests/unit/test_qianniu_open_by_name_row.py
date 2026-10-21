# -*- coding: utf-8 -*-
"""Switch to a specific buyer by clicking their list row, not a search box.

With two buyers active, qianniu_send's open-by-name used to require a search box
and ABORT ("cannot open by name") when OCR couldn't find one — dropping the
reply (customer 2026-10-15, 淘宝 一对二). Every active buyer's NAME is visible in
the 正在接待 list, so find_conversation_row_by_name returns the row to click.

conversation_rows' own OCR geometry is covered by its own tests; here we stub it
and exercise this function's name-matching + the row it returns.
"""
import pytest

from agent.mcp.server.qianniu import qianniu_ocr as qo

# [(name, preview, (x, y))], as conversation_rows yields (grouping headers
# already filtered out by conversation_rows itself).
ROWS = [
    ("大作战panda", "这个牙线盒耐用吗", (495, 475)),
    ("tb398427493806", "现在拍能不能发货", (512, 647)),
]


@pytest.fixture(autouse=True)
def _stub_rows(monkeypatch):
    monkeypatch.setattr(qo, "conversation_rows", lambda ocr_data, limit=8: list(ROWS))


def test_finds_the_named_buyers_row():
    assert qo.find_conversation_row_by_name([], "大作战panda") == ((495, 475), "大作战panda")


def test_finds_the_other_buyer():
    assert qo.find_conversation_row_by_name([], "tb398427493806") == ((512, 647), "tb398427493806")


def test_clipped_long_name_still_matches_by_containment():
    # OCR sometimes clips a long id; containment (len>=4) still resolves it.
    pt, matched = qo.find_conversation_row_by_name([], "tb398427493806615")
    assert pt == (512, 647) and matched == "tb398427493806"


def test_unknown_name_returns_none():
    assert qo.find_conversation_row_by_name([], "someone_else") == (None, "")


def test_empty_name_returns_none():
    assert qo.find_conversation_row_by_name([], "") == (None, "")


def test_short_name_requires_exact_match_not_substring():
    # A 1-3 char name must not loosely match a longer row (avoid mis-switching).
    monkey_rows = [("abc", "hi", (10, 20)), ("abcdefg", "yo", (10, 40))]
    import agent.mcp.server.qianniu.qianniu_ocr as m
    orig = m.conversation_rows
    m.conversation_rows = lambda ocr_data, limit=8: list(monkey_rows)
    try:
        # "ab" (len 2) must NOT match "abc"/"abcdefg" by containment.
        assert qo.find_conversation_row_by_name([], "ab") == (None, "")
        # exact short name is fine.
        assert qo.find_conversation_row_by_name([], "abc")[1] == "abc"
    finally:
        m.conversation_rows = orig
