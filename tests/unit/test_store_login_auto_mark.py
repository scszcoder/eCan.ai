"""A store page that demonstrably works marks its profile signed in (2026-10-23:
KEN's 抖店 profile had answered chats for weeks but still read "needs login",
so Fast Deploy asked the customer to sign in for nothing)."""
import types

import pytest

from agent.ec_skills.browser_use_extension import store_page
from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg


@pytest.fixture
def profiles(monkeypatch):
    states = {"douyin-55b2a7fb-login": reg.LOGIN_NEEDED, "pdd_main": reg.LOGIN_OK}
    calls = []
    monkeypatch.setattr(reg, "login_state", lambda pid: {"state": states.get(pid, reg.LOGIN_UNKNOWN)})
    monkeypatch.setattr(reg, "set_login_state", lambda pid, st, detail="": calls.append((pid, st)) or True)
    import agent.ec_skills.browser_use_extension.fingerprint.fingerprint_browser as fb
    monkeypatch.setattr(fb, "running_profiles", lambda: {
        "douyin-55b2a7fb-login": types.SimpleNamespace(debug_port=50674),
        "pdd_main": types.SimpleNamespace(debug_port=54913)})
    monkeypatch.setattr(store_page, "_marked", set())
    return calls


def test_a_working_chat_socket_marks_its_profile_signed_in_once(profiles):
    for _ in range(3):
        store_page.note_signed_in(cdp_url="http://127.0.0.1:50674", proof="飞鸽 chat socket")
    assert profiles == [("douyin-55b2a7fb-login", reg.LOGIN_OK)]


def test_an_already_signed_in_or_unknown_browser_is_left_alone(profiles):
    store_page.note_signed_in(profile_id="pdd_main", proof="拼多多 goods list")
    store_page.note_signed_in(cdp_url="http://127.0.0.1:9999")
    store_page.note_signed_in()
    assert profiles == []
