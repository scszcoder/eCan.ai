"""Dialogs covering 千牛 (alpha 2026-10-20, yay: the 服务态度提醒 dialog refused a
stock-greeting reply and stayed on top, so every later read and send failed
through it). Known ones close by rule; unknown ones go to the LLM
(agent/ec_skills/ui_obstacles.py), which never presses a forbidden button."""
import json
import os
from unittest.mock import patch

import pytest

from agent.ec_skills import ui_obstacles
from agent.mcp.server.qianniu import qianniu_ocr, qianniu_tools

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _screen(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return [{"text": l["text"], "loc": l["loc"]} for l in json.load(f)["lines"]]


POPUP = _screen("qianniu_ocr_service_attitude_popup.json")
CLEAN = [it for it in POPUP if not any(k in it["text"] for k in ("服务态度提醒", "返回修改", "请勿重复"))]


@pytest.fixture(autouse=True)
def _rules_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_obstacles, "_rules_path", lambda: str(tmp_path / "rules.json"))
    monkeypatch.setattr(ui_obstacles.time, "sleep", lambda s: None)
    monkeypatch.setattr(qianniu_tools, "_obstacle_quiet_until", 0.0)


def _act():
    done = []
    return done, {"click": lambda x, y: done.append((x, y)), "esc": lambda: done.append("esc"),
                  "clear_reply_box": lambda: done.append("clear")}


def test_the_known_dialog_is_closed_without_a_model_call():
    done, act = _act()
    with patch.object(ui_obstacles, "_ask") as ask:
        out = ui_obstacles.resolve("qianniu", POPUP, "", "x", act, lambda: CLEAN,
                                   builtin=qianniu_tools._BUILTIN_OBSTACLES, use_model=False)
    ask.assert_not_called()
    assert out["resolved"] and out["via"] == "rule"
    assert done == [(1154, 714), "clear"]                # 返回修改's centre, then the reply box


def test_every_screen_read_closes_a_known_dialog_and_reads_again():
    reads = iter([POPUP, CLEAN, CLEAN])                  # read, check after closing, read again
    with patch.object(qianniu_tools, "ocr_qianniu_window", side_effect=lambda: next(reads)),             patch.object(qianniu_tools, "_looks_like_qianniu", return_value=True),             patch.object(qianniu_tools, "save_failure_shot", return_value=""),             patch.object(qianniu_tools, "_click"),             patch.object(qianniu_tools, "_clear_reply_box"),             patch.object(ui_obstacles, "_ask") as ask:
        assert qianniu_tools._read_qianniu() is CLEAN
    ask.assert_not_called()


def test_a_plain_screen_read_never_asks_a_model():
    with patch.object(qianniu_tools, "ocr_qianniu_window", return_value=CLEAN),             patch.object(qianniu_tools, "_looks_like_qianniu", return_value=True),             patch.object(ui_obstacles, "_ask") as ask:
        assert qianniu_tools._read_qianniu() is CLEAN
    ask.assert_not_called()


REWORDED = [dict(it, text=it["text"].replace("服务态度提醒", "服务提醒").replace("返回修改", "我知道了"))
            for it in POPUP]
LLM_SAYS = {"blocking": True, "kind": "reply_refused", "summary": "服务提醒", "action": "click",
            "button": "我知道了", "clear_reply_box": True, "refused_reason": "像开场白",
            "match": ["服务提醒", "我知道了"], "need_vision": False}


def test_an_unknown_dialog_goes_to_the_text_model_and_is_learned():
    done, act = _act()
    after = [it for it in REWORDED if not any(k in it["text"] for k in ("服务提醒", "我知道了"))]
    with patch.object(ui_obstacles, "_ask", return_value=dict(LLM_SAYS)) as ask:
        out = ui_obstacles.resolve("qianniu", REWORDED, "shot.png", "x", act, lambda: after)
    assert ask.call_count == 1 and ask.call_args[0][0] == ui_obstacles.TEXT_MODEL
    assert out["resolved"] and out["refused_reason"] == "像开场白"
    assert done[-1] == "clear" and isinstance(done[0], tuple)
    # next time: the learned rule, no model call
    done2, act2 = _act()
    with patch.object(ui_obstacles, "_ask") as ask:
        assert ui_obstacles.resolve("qianniu", REWORDED, "", "x", act2, lambda: after)["via"] == "rule"
    ask.assert_not_called()


def test_vision_only_when_the_text_model_asks_for_it(tmp_path):
    shot = tmp_path / "s.png"
    shot.write_bytes(b"png")
    _, act = _act()
    answers = iter([dict(LLM_SAYS, need_vision=True), dict(LLM_SAYS)])
    with patch.object(ui_obstacles, "_ask", side_effect=lambda m, p, img="": next(answers)) as ask:
        out = ui_obstacles.resolve("qianniu", REWORDED, str(shot), "x", act, lambda: CLEAN)
    assert [c[0][0] for c in ask.call_args_list] == [ui_obstacles.TEXT_MODEL, ui_obstacles.VISION_MODEL]
    assert out["via"] == "vision"


@pytest.mark.parametrize("button", ["发送", "同意退款", "不在屏幕上的按钮"])
def test_a_forbidden_or_unseen_button_is_never_clicked(button):
    done, act = _act()
    with patch.object(ui_obstacles, "_ask", return_value=dict(LLM_SAYS, button=button)):
        ui_obstacles.resolve("qianniu", REWORDED + [{"text": "发送", "loc": [870, 860, 890, 900]},
                                                    {"text": "同意退款", "loc": [500, 900, 520, 960]}],
                             "", "x", act, lambda: CLEAN)
    assert "esc" in done and not any(isinstance(d, tuple) for d in done)


def test_model_down_means_esc_and_carry_on():
    done, act = _act()
    with patch.object(ui_obstacles, "_ask", side_effect=RuntimeError("proxy 503")):
        out = ui_obstacles.resolve("qianniu", REWORDED, "", "x", act, lambda: REWORDED)
    assert done == ["esc"] and out["via"] == "none"


def test_open_by_name_never_types_into_another_app():
    """2026-10-20: the buyer's name + Enter landed in the user's own chat window
    (sent as a message) -- the paste and Enter had no foreground check."""
    order = []
    with patch.object(qianniu_tools, "find_conversation_row_by_name", return_value=(None, "")), \
            patch.object(qianniu_tools, "_find_search_box", return_value=(10, 20)), \
            patch.object(qianniu_tools, "_click", side_effect=lambda x, y: order.append("click")), \
            patch.object(qianniu_tools, "_humanize"), \
            patch.object(qianniu_tools, "clipboard_set_text"), \
            patch.object(qianniu_tools, "paste_hotkey", side_effect=lambda: order.append("paste")), \
            patch.object(qianniu_tools.pyautogui, "press", side_effect=lambda k: order.append(k)), \
            patch.object(qianniu_tools, "_ensure_front", side_effect=lambda what: order.append("front?")), \
            patch.object(qianniu_tools, "verify_header_name",
                         return_value=qianniu_ocr.HeaderVerifyResult(True, "x", "x", [])), \
            patch.object(qianniu_tools, "_read_qianniu", return_value=[]), \
            patch.object(qianniu_tools, "_looks_like_qianniu", return_value=True):
        qianniu_tools._open_conversation_by_name("买家熊猫")
    assert order.index("front?", order.index("click")) < order.index("paste")
    assert order.index("front?", order.index("paste")) < order.index("enter")


# --- a reply 千牛 refuses is rewritten once -------------------------------------------

def _send_with(after_send_screens, rewrite="您说的是耐洗程度吧？这款可机洗，建议30度以下冷水。"):
    """Already-open chat (the expected text is in the body, header shows the buyer);
    after each Enter, the next screen of *after_send_screens* is what 千牛 shows."""
    open_chat = [{"text": "买家熊猫", "loc": [120, 400, 150, 520]},
                 {"text": "确认好了吗，耐不耐洗啊", "loc": [400, 400, 430, 700]},
                 {"text": "接待中心", "loc": [10, 10, 30, 90]}]
    after = iter(after_send_screens)
    typed = []
    with patch.object(qianniu_tools, "ocr_qianniu_window",
                      side_effect=lambda: next(after) if typed else open_chat), \
            patch.object(qianniu_tools, "_read_qianniu", return_value=open_chat), \
            patch.object(qianniu_tools, "transcript_contains", return_value=True), \
            patch.object(qianniu_tools, "verify_header_name",
                         return_value=qianniu_ocr.HeaderVerifyResult(True, "买家熊猫", "买家熊猫", [])), \
            patch.object(qianniu_tools, "_foreground", return_value=True), \
            patch.object(qianniu_tools, "_humanize"), \
            patch.object(qianniu_tools, "_click"), \
            patch.object(qianniu_tools, "_clear_reply_box"), \
            patch.object(qianniu_tools, "_type_and_send", side_effect=typed.append), \
            patch.object(qianniu_tools, "save_failure_shot", return_value=""), \
            patch.object(ui_obstacles, "rewrite_refused", return_value=rewrite) as rw, \
            patch.object(ui_obstacles, "_ask") as ask:
        out = qianniu_tools._send_locked("买家熊猫", "您好，在的，请问有什么可以帮您？", False, "确认好了吗，耐不耐洗啊")
    return json.loads(out[0].text), typed, rw, ask


def test_a_refused_reply_is_rewritten_once_and_sent():
    res, typed, rw, ask = _send_with([POPUP, CLEAN, CLEAN, CLEAN])
    assert typed == ["您好，在的，请问有什么可以帮您？", "您说的是耐洗程度吧？这款可机洗，建议30度以下冷水。"]
    assert res["chat_sent"] is True
    assert rw.call_args[0][0] == "确认好了吗，耐不耐洗啊" and "开场白" in rw.call_args[0][2]
    ask.assert_not_called()                                  # the known dialog needs no model


def test_refused_twice_gives_up_without_a_third_try():
    res, typed, _rw, _ask = _send_with([POPUP, CLEAN, POPUP, CLEAN])
    assert len(typed) == 2 and res["chat_sent"] is False


def test_a_normal_send_reads_once_and_asks_no_model():
    res, typed, rw, ask = _send_with([CLEAN])
    assert res["chat_sent"] is True and len(typed) == 1
    rw.assert_not_called()
    ask.assert_not_called()


# --- yba alpha 2026-10-20: a window on top dropped two replies for 30-50 min -----------

def test_qianniu_is_brought_back_patiently_before_acting():
    fronts = iter([False, False, True])
    with patch.object(qianniu_tools, "_find_window", return_value=object()), \
            patch.object(qianniu_tools, "_is_front", side_effect=lambda w: next(fronts)), \
            patch.object(qianniu_tools, "_force_front") as force, \
            patch.object(qianniu_tools.time, "sleep"):
        qianniu_tools._ensure_front("click")                 # no raise
    assert force.call_count == 2


def test_still_covered_after_all_tries_means_not_acting():
    with patch.object(qianniu_tools, "_find_window", return_value=object()), \
            patch.object(qianniu_tools, "_is_front", return_value=False), \
            patch.object(qianniu_tools, "_force_front") as force, \
            patch.object(qianniu_tools.time, "sleep"):
        with pytest.raises(RuntimeError, match="not the foreground window"):
            qianniu_tools._ensure_front("click")
    assert force.call_count == qianniu_tools._FRONT_TRIES


@pytest.mark.parametrize("error,forgotten", [
    ("千牛 is not the foreground window before click at (1, 2); not acting", True),
    ("'是现货吗' is not in the open chat body — refusing to send", False),   # wrong chat: no blind retry
])
def test_a_reply_not_sent_for_a_passing_reason_goes_back_to_the_backstop(error, forgotten):
    held = []
    lock = type("L", (), {"try_acquire": lambda s, h: held.append(h) or True, "release": lambda s, *a: None,
                          "holder": lambda s: held[-1]})()
    res = [type("T", (), {"text": json.dumps({"chat_sent": False, "error": error})})()]
    from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import observer
    with patch.object(qianniu_tools, "_lock", return_value=lock), \
            patch.object(qianniu_tools, "_send_locked", return_value=res), \
            patch.object(observer, "forget_dispatched") as forget:
        qianniu_tools.send_reply("hxxss", "这边帮您核实一下库存情况", "是现货吗")
    assert forget.called is forgotten


def test_forget_dispatched_lets_the_backstop_answer_again():
    from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import observer
    obs = observer._OBSERVER
    saved = list(obs._dispatched_texts)
    try:
        obs._dispatched_texts[:] = [(observer._norm_text("是现货吗"), __import__("time").time())]
        assert obs._already_handled("hxxss", "是现货吗")
        observer.forget_dispatched("是现货吗")
        assert not obs._already_handled("hxxss", "是现货吗")
    finally:
        obs._dispatched_texts[:] = saved


AD = POPUP + [{"text": "【客服差评抵消】开通「不满意挽回」", "loc": [180, 970, 200, 1420]},
              {"text": "关闭", "loc": [1100, 785, 1120, 835]}]     # the reply box's own, at the bottom


@pytest.mark.parametrize("llm", [
    dict(LLM_SAYS, button="关闭", match=["客服差评抵消"]),        # the reply box's 关闭: refused
    dict(LLM_SAYS, action="esc", match=["客服差评抵消"]),         # Esc closes the chat in 千牛
])
def test_qianniu_never_presses_esc(llm):
    done, act = _act()
    with patch.object(ui_obstacles, "_ask", return_value=llm):
        out = ui_obstacles.resolve("qianniu", AD, "", "x", act, lambda: AD, allow_esc=False)
    assert done == [] and not out["resolved"]


def test_model_down_in_qianniu_leaves_the_screen_alone():
    done, act = _act()
    with patch.object(ui_obstacles, "_ask", side_effect=RuntimeError("proxy 503")):
        ui_obstacles.resolve("qianniu", REWORDED, "", "x", act, lambda: REWORDED, allow_esc=False)
    assert done == []
