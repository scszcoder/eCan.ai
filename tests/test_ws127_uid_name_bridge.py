"""ws127: name_for_talk uid-bridge — a name-less product card whose OWN talk never
received a named frame resolves to the real customer via the stable per-customer uid
(security_sender_id), so its reply raw-routes off the DOM typing lock instead of
failing `Session not found`.

Safety: the bridge must ONLY resolve to a name actually observed for that exact uid,
must never override a direct talk->name hit, and must be killable via env.
"""
import pytest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import ws_session


@pytest.fixture(autouse=True)
def _clean_maps(monkeypatch):
    # Isolate module state per test.
    monkeypatch.setattr(ws_session, "_talk_to_name", {}, raising=True)
    monkeypatch.setattr(ws_session, "_uid_by_talk", {}, raising=True)
    monkeypatch.setattr(ws_session, "_name_by_uid", {}, raising=True)
    monkeypatch.delenv("ECAN_FEIGE_UID_NAME_BRIDGE", raising=False)
    yield


def test_card_talk_resolves_via_uid():
    # Card talk has no direct name, but carries the customer's uid, and a NAMED frame
    # for that uid was seen on a different talk.
    ws_session._uid_by_talk["7658551169551271177"] = "uidWV5UQCyK"
    ws_session._name_by_uid["uidWV5UQCyK"] = "陆地飞鱼"

    assert ws_session.name_for_talk("7658551169551271177") == "陆地飞鱼"


def test_no_uid_mapping_returns_empty():
    # uid captured but no named frame ever seen for it -> must NOT invent a name.
    ws_session._uid_by_talk["7658551169551271177"] = "uidUnknown"

    assert ws_session.name_for_talk("7658551169551271177") == ""


def test_direct_name_takes_precedence_over_uid():
    ws_session._talk_to_name["talkA"] = "肽斯特"
    ws_session._uid_by_talk["talkA"] = "uidX"
    ws_session._name_by_uid["uidX"] = "WRONG_NAME"

    # Direct talk->name must win; uid bridge only fills a MISS.
    assert ws_session.name_for_talk("talkA") == "肽斯特"


def test_bridge_never_returns_a_card_identity():
    ws_session._uid_by_talk["talkB"] = "uidY"
    ws_session._name_by_uid["uidY"] = "card:should_not_leak"

    assert ws_session.name_for_talk("talkB") == ""


def test_kill_switch_disables_bridge(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_UID_NAME_BRIDGE", "0")
    ws_session._uid_by_talk["talkC"] = "uidZ"
    ws_session._name_by_uid["uidZ"] = "陆地飞鱼"

    assert ws_session.name_for_talk("talkC") == ""
