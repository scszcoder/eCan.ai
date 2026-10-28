"""千牛 fixes from the alpha PC run of 2026-10-22: a hung 千牛登录 window froze
the backstop, the 消息提醒 popup was read as the chat, a refused send counted
as a success, and a closed 接待中心 was never opened. user32 is faked
throughout -- no real window, key or mouse is touched."""
import ctypes
import json
import os
import types

import pytest

from agent.mcp.server.qianniu import qianniu_ocr, qianniu_tools

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
# The conftest guard stubs these for every test; captured here, at import, so
# they can be tested -- with user32 faked, nothing real is touched.
_force_front = qianniu_tools._force_front
_open_reception = qianniu_tools._open_reception


class FakeUser32:
    def __init__(self, fg=200, hung=False, pids=None):
        self.fg, self.hung, self.pids = fg, hung, pids or {}
        self.calls = []

    def __getattr__(self, name):            # anything not modelled: record, return 0
        def f(*a):
            self.calls.append((name, a))
            return 0
        return f

    def GetForegroundWindow(self):
        return self.fg

    def IsHungAppWindow(self, h):
        return self.hung

    def GetWindowThreadProcessId(self, h, ref):
        if ref is not None:
            ref._obj.value = self.pids.get(h, 0)
        return 7                             # the window's thread id

    def AttachThreadInput(self, *a):
        self.calls.append(("AttachThreadInput", a))
        return 1


@pytest.fixture
def user32(monkeypatch):
    def make(**kw):
        u = FakeUser32(**kw)
        k = types.SimpleNamespace(GetCurrentThreadId=lambda: 1)
        monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=u, kernel32=k), raising=False)
        return u
    return make


def _names(u):
    return [c[0] for c in u.calls]


def test_a_hung_front_window_is_never_attached_to(user32):
    u = user32(fg=200, hung=True, pids={200: 5, 100: 9})       # someone else's hung window
    _force_front(types.SimpleNamespace(hwnd=100))
    assert "AttachThreadInput" not in _names(u)
    assert "ShowWindowAsync" not in _names(u)                 # not 千牛's: left alone
    assert "SetForegroundWindow" in _names(u)


def test_qiannius_own_hung_login_window_is_minimized(user32):
    u = user32(fg=200, hung=True, pids={200: 9, 100: 9})       # same process as the chat window
    _force_front(types.SimpleNamespace(hwnd=100))
    assert ("ShowWindowAsync", (200, 6)) in u.calls
    assert "AttachThreadInput" not in _names(u)


def test_a_responding_front_window_is_attached_as_before(user32):
    u = user32(fg=200, hung=False, pids={200: 5, 100: 9})
    _force_front(types.SimpleNamespace(hwnd=100))
    assert "AttachThreadInput" in _names(u)


@pytest.fixture
def reception(monkeypatch, user32):
    monkeypatch.setattr(qianniu_tools, "_humanize", lambda s: None)
    monkeypatch.setattr(qianniu_tools, "_last_reception_hotkey", [-1e9])
    monkeypatch.delenv("ECAN_QIANNIU_RECEPTION_HOTKEY", raising=False)
    return user32()


def test_ctrl_alt_x_opens_a_closed_reception_window_once(monkeypatch, reception):
    chat = types.SimpleNamespace(title="shopA71-接待中心", hwnd=100)
    monkeypatch.setattr(qianniu_tools, "_find_window", lambda: chat)
    assert _open_reception() is chat
    keys = [c[1][:2] + (c[1][2],) for c in reception.calls if c[0] == "keybd_event"]
    assert keys == [(0x11, 0, 0), (0x12, 0, 0), (0x58, 0, 0), (0x58, 0, 2), (0x12, 0, 2), (0x11, 0, 2)]
    reception.calls.clear()
    assert _open_reception() is None              # not again within 30 s
    assert "keybd_event" not in _names(reception)


def test_no_hotkey_when_the_chat_window_is_already_shown(monkeypatch, reception):
    chat = types.SimpleNamespace(title="shopA71-接待中心", hwnd=100)
    monkeypatch.setattr(qianniu_tools, "_find_window", lambda: chat)
    monkeypatch.setattr(qianniu_tools, "bring_window_to_front", lambda w: None)
    assert qianniu_tools._foreground()
    assert "keybd_event" not in _names(reception)


def test_hotkey_can_be_turned_off(monkeypatch, reception):
    monkeypatch.setenv("ECAN_QIANNIU_RECEPTION_HOTKEY", "0")
    assert _open_reception() is None
    assert "keybd_event" not in _names(reception)


def test_the_reminder_popup_is_not_read_as_the_chat():
    with open(os.path.join(FIX, "qianniu_ocr_reminder_popup.json"), encoding="utf-8") as f:
        screen = [{"text": l["text"], "loc": l["loc"]} for l in json.load(f)["lines"]]
    # Was ('buyer', '关闭124s人工服务'): the popup's card for the same buyer, with
    # the 关闭 button and its 124s timer, sat lower than the chat's own label.
    assert qianniu_ocr.last_turn(screen, "买家阿青", "shopA71") == ("buyer", "人工服务")


def test_a_refused_send_reports_failure_to_the_skill_runtime():
    out = json.loads(qianniu_tools._send_result(False, False, "could not open the buyer's chat")[0].text)
    assert out["success"] is False and out["chat_sent"] is False
    assert json.loads(qianniu_tools._send_result(True, True, "")[0].text)["success"] is True
