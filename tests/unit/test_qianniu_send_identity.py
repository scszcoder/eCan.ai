"""千牛 send identity + the OCR history (alpha 2026-10-20: a reply for one buyer
went into the chat that happened to be open, and nothing showed why)."""
import json
import os
import time
from unittest.mock import patch

from PIL import Image

from agent.mcp.server.qianniu import qianniu_ocr, qianniu_tools


def test_a_one_character_header_fragment_is_not_the_buyer():
    assert not qianniu_ocr._header_names("8", "tb398427493806")
    assert qianniu_ocr._header_names("tb398427493806", "tb398427493806")
    assert qianniu_ocr._header_names("tb3984274", "tb398427493806")          # truncated, half or more
    assert not qianniu_ocr._header_names("tb39", "tb398427493806")            # too small a part
    assert qianniu_ocr._header_names("大作战panda 的会话", "大作战panda")


def _send(header_ok, body_ok, expect="确认好了吗，耐不耐洗啊"):
    """_send_locked with the screen faked: returns (sent?, opened the buyer's row?)."""
    opened = []
    hdr = qianniu_ocr.HeaderVerifyResult(header_ok, "tb398427493806" if header_ok else "8", "tb398427493806", [])
    with patch.object(qianniu_tools, "_foreground", return_value=True), \
            patch.object(qianniu_tools, "_read_qianniu", return_value=[{"text": "x", "loc": [0, 0, 1, 1]}]), \
            patch.object(qianniu_tools, "verify_header_name", return_value=hdr), \
            patch.object(qianniu_tools, "transcript_contains", return_value=body_ok), \
            patch.object(qianniu_tools, "_open_conversation_by_preview",
                         side_effect=lambda *a: (opened.append(1) or True, "tb398427493806", "")), \
            patch.object(qianniu_tools, "_type_and_send") as typed, \
            patch.object(qianniu_tools, "save_failure_shot"):
        qianniu_tools._send_locked("tb398427493806", "这边帮您核实一下", True, expect)
    return typed.called, bool(opened)


def test_the_open_chat_is_used_only_when_text_and_header_agree():
    assert _send(header_ok=True, body_ok=True) == (True, False)      # already open, verified twice


def test_a_text_hit_alone_opens_the_buyers_own_row_first():
    # 10:55 alpha: body matched, header was a lone '8' -> it typed into the open chat
    sent, opened = _send(header_ok=False, body_ok=True)
    assert opened                                                   # clicked the buyer's row first


def test_every_ocr_image_is_kept_with_what_was_read_for_12_hours(tmp_path):
    with patch.object(qianniu_ocr, "_history_dir", return_value=str(tmp_path)):
        old = tmp_path / "20261019_000000_000.jpg"
        old.write_bytes(b"x")
        os.utime(old, (time.time() - 13 * 3600,) * 2)
        qianniu_ocr._history_pruned[0] = 0
        name = qianniu_ocr.keep_history_shot(Image.new("RGB", (40, 20), "white"))
        qianniu_ocr.keep_history_text(name, [{"text": "确认好了吗，耐不耐洗啊", "loc": [1, 2, 3, 4]}], "remote/url:aihub")
    assert name.endswith(".jpg") and (tmp_path / name).exists()
    assert not old.exists()                                         # older than 12 h: gone
    read = json.loads((tmp_path / (name[:-4] + ".json")).read_text(encoding="utf-8"))
    assert read["lines"][0]["text"] == "确认好了吗，耐不耐洗啊" and read["engine"] == "remote/url:aihub"
