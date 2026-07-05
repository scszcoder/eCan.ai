"""ws130: seed the FORWARD route (_routing[name]=talk) for a name-less card frame via the
uid bridge, so a card-only customer's reply RAW-routes instead of no_talk_id -> NO-ROUTE -> DOM.

ws129 proved 62/62 NO-ROUTE were `no_talk_id` for card-only customers (e.g. 'packet' never
sent a named frame, so _routing had no entry). This must NOT override an authoritative named
route (mis-delivery safety), but should track the latest card talk for a card-only customer.
"""
import pytest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import ws_session, ws_reader


def _msg(name, talk, uid, role="1", mtype="template_card"):
    return ws_reader.CustomerMessage(
        customer_name=name, conversation_id=talk, text="[商品卡片] x", msg_id="m1",
        ts_ms=1, sender_role=role, msg_type=mtype, pigeon_cid="p", client_msg_id="",
        read_cursor="", sender_uid=uid,
    )


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(ws_session, "_routing", {}, raising=True)
    monkeypatch.setattr(ws_session, "_talk_to_name", {}, raising=True)
    monkeypatch.setattr(ws_session, "_uid_by_talk", {}, raising=True)
    monkeypatch.setattr(ws_session, "_name_by_uid", {}, raising=True)
    monkeypatch.setattr(ws_session, "_card_bridged_names", set(), raising=True)
    monkeypatch.delenv("ECAN_FEIGE_UID_NAME_BRIDGE", raising=False)
    yield


def _feed(monkeypatch, msg):
    monkeypatch.setattr(ws_reader, "extract_messages", lambda _raw: [msg])
    ws_session.note_recv_frame(b"x")


def test_card_only_customer_gets_forward_route(monkeypatch):
    # A named frame for this uid was seen elsewhere -> uid bridge knows the name.
    ws_session._name_by_uid["uidP"] = "packet"
    # Now a NAME-LESS card frame on packet's card talk arrives.
    _feed(monkeypatch, _msg(name="", talk="talkCARD", uid="uidP"))
    assert ws_session.talk_for_name("packet") == "talkCARD"   # forward route seeded


def test_named_frame_route_is_never_overridden(monkeypatch):
    # Authoritative named frame sets the main route.
    _feed(monkeypatch, _msg(name="packet", talk="talkMAIN", uid="uidP", mtype="text"))
    assert ws_session.talk_for_name("packet") == "talkMAIN"
    # A later card on a DIFFERENT talk must NOT hijack the named route.
    _feed(monkeypatch, _msg(name="", talk="talkCARD", uid="uidP"))
    assert ws_session.talk_for_name("packet") == "talkMAIN"


def test_card_bridge_tracks_latest_card_talk(monkeypatch):
    ws_session._name_by_uid["uidP"] = "packet"
    _feed(monkeypatch, _msg(name="", talk="talk1", uid="uidP"))
    assert ws_session.talk_for_name("packet") == "talk1"
    # Same customer shares a new card on a newer talk -> reply should follow to talk2.
    _feed(monkeypatch, _msg(name="", talk="talk2", uid="uidP"))
    assert ws_session.talk_for_name("packet") == "talk2"


def test_kill_switch_disables_route_seed(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_UID_NAME_BRIDGE", "0")
    ws_session._name_by_uid["uidP"] = "packet"
    _feed(monkeypatch, _msg(name="", talk="talkCARD", uid="uidP"))
    assert ws_session.talk_for_name("packet") == ""   # no forward route seeded
