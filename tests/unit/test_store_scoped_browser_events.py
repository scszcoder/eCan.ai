"""Gated store-scoping of browser_event dispatch (ECAN_STORE_SCOPED_BROWSER_EVENTS).

When ON, a detection event is stamped with the detecting session's
browser_profile_id (a store's login) so a front desk only resumes for its OWN
store's `新消息` — stops one 抖店 store's detection from waking the other store's
desk and swallowing the turn. Default OFF (needs a live two-store Feige run).
"""

import os
from unittest import mock

from agent.ec_skills.browser_use_extension import event_monitor as em
from agent.ec_skills.browser_use_extension.fingerprint.profile_registry import login_profile_id


def _off():
    return {k: v for k, v in os.environ.items() if k != "ECAN_STORE_SCOPED_BROWSER_EVENTS"}


def test_flag_defaults_off():
    with mock.patch.dict(os.environ, _off(), clear=True):
        assert em._store_scoped_browser_events_enabled() is False


def test_flag_truthy_values():
    for v in ("1", "true", "yes", "on", "TRUE"):
        with mock.patch.dict(os.environ, {"ECAN_STORE_SCOPED_BROWSER_EVENTS": v}):
            assert em._store_scoped_browser_events_enabled() is True


def test_qualifier_is_identical_on_both_ends():
    """The event side stamps the session's browser_profile_id (the scope-key
    value); the match side computes login_profile_id(store_id). They MUST be
    equal or the filter drops every event. login_profile_id is canonical for
    both, so this pins that they agree for the customer's two stores."""
    assert login_profile_id("douyin-抖音二号") == "douyin-6a4b2c53-login"
    assert login_profile_id("douyin-抖音三号") == "douyin-167bb80f-login"
    # deterministic
    assert login_profile_id("douyin-抖音二号") == login_profile_id("douyin-抖音二号")


def _capture_event(flag_on: bool):
    captured = {}

    def _fake_dispatch(sub_type, event, target_agent_id=""):
        captured["event"] = event

    env = {"ECAN_STORE_SCOPED_BROWSER_EVENTS": "1"} if flag_on else _off()
    with mock.patch.dict(os.environ, env, clear=not flag_on), \
         mock.patch.object(em, "_dispatch_to_runners", side_effect=_fake_dispatch):
        bridge = em._build_bridge_callback(
            "新消息", "mset1", "agentX", session=None,
            browser_profile_id="douyin-6a4b2c53-login")
        bridge("http://x", "GET", 200, "plain non-json body", "新消息")
    return captured.get("event")


def test_event_stamped_when_flag_on():
    event = _capture_event(flag_on=True)
    assert event is not None
    assert event.get("browser_profile_id") == "douyin-6a4b2c53-login"


def test_event_not_stamped_when_flag_off():
    event = _capture_event(flag_on=False)
    assert event is not None
    assert "browser_profile_id" not in event
