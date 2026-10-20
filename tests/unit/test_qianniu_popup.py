"""千牛's 服务态度提醒 dialog (alpha 2026-10-20, yay): it refused a stock-greeting
reply and stayed on top, so every later read and send failed through it."""
import json
import os
from unittest.mock import patch

from agent.mcp.server.qianniu import qianniu_tools

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _screen(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return [{"text": l["text"], "loc": l["loc"]} for l in json.load(f)["lines"]]


POPUP = _screen("qianniu_ocr_service_attitude_popup.json")
CLEAN = [it for it in POPUP if not any(k in it["text"] for k in ("服务态度提醒", "返回修改", "请勿重复"))]


def test_the_dialog_is_closed_and_the_refused_text_cleared():
    clicks, keys = [], []
    with patch.object(qianniu_tools, "_click", side_effect=lambda x, y: clicks.append((x, y))), \
            patch.object(qianniu_tools, "_click_composer", side_effect=lambda: clicks.append("composer")), \
            patch.object(qianniu_tools.pyautogui, "hotkey", side_effect=lambda *k: keys.append(k)), \
            patch.object(qianniu_tools.pyautogui, "press", side_effect=lambda k: keys.append(k)), \
            patch.object(qianniu_tools, "save_failure_shot"), \
            patch.object(qianniu_tools.time, "sleep"):
        assert qianniu_tools._dismiss_popup(POPUP) is True
    assert clicks == [(1154, 714), "composer"]          # 返回修改's centre, then the reply box
    assert keys == [("ctrl", "a"), "delete"]


def test_a_screen_without_the_dialog_is_left_alone():
    with patch.object(qianniu_tools, "_click") as click:
        assert qianniu_tools._dismiss_popup(CLEAN) is False
    click.assert_not_called()


def test_every_screen_read_reads_again_after_closing_it():
    reads = iter([POPUP, CLEAN])
    with patch.object(qianniu_tools, "ocr_qianniu_window", side_effect=lambda: next(reads)), \
            patch.object(qianniu_tools, "_looks_like_qianniu", return_value=True), \
            patch.object(qianniu_tools, "_dismiss_popup", side_effect=lambda d: d is POPUP):
        assert qianniu_tools._read_qianniu() is CLEAN
