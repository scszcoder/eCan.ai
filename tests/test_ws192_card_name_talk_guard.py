"""ws192: name_for_talk_verified rejects a card→name bind when the candidate
name provably belongs to a DIFFERENT talk (the 96z 钛斯特→陆地飞鱼 mis-bind
that mis-delivered and split the dedup keys into a duplicate answer)."""

import importlib

wss = importlib.import_module(
    "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.ws_session"
)


def _reset(monkeypatch, talk_to_name=None, routing=None, uid_by_talk=None, name_by_uid=None):
    monkeypatch.setattr(wss, "_talk_to_name", dict(talk_to_name or {}), raising=False)
    monkeypatch.setattr(wss, "_routing", dict(routing or {}), raising=False)
    monkeypatch.setattr(wss, "_uid_by_talk", dict(uid_by_talk or {}), raising=False)
    monkeypatch.setattr(wss, "_name_by_uid", dict(name_by_uid or {}), raising=False)


def test_rejects_wrong_talk_name(monkeypatch):
    # card talk 808602 (钛斯特) wrongly maps to 陆地飞鱼, whose real talk is 179238.
    _reset(
        monkeypatch,
        talk_to_name={"808602": "陆地飞鱼"},
        routing={"陆地飞鱼": "179238"},
    )
    # name_for_talk returns the (wrong) name...
    assert wss.name_for_talk("808602") == "陆地飞鱼"
    # ...but the guarded resolver rejects it because 陆地飞鱼's talk != 808602.
    assert wss.name_for_talk_verified("808602") == ""


def test_accepts_matching_talk_name(monkeypatch):
    _reset(
        monkeypatch,
        talk_to_name={"808602": "钛斯特"},
        routing={"钛斯特": "808602"},
    )
    assert wss.name_for_talk_verified("808602") == "钛斯特"


def test_accepts_when_candidate_talk_unknown(monkeypatch):
    # name resolved but never routed (talk_for_name empty) → allow (prior behavior).
    _reset(monkeypatch, talk_to_name={"808602": "新客户"}, routing={})
    assert wss.name_for_talk_verified("808602") == "新客户"


def test_empty_when_no_name(monkeypatch):
    _reset(monkeypatch)
    assert wss.name_for_talk_verified("808602") == ""


def test_uid_bridge_wrong_talk_rejected(monkeypatch):
    # name resolves via the uid bridge to a name whose talk differs → reject.
    monkeypatch.setenv("ECAN_FEIGE_UID_NAME_BRIDGE", "1")
    _reset(
        monkeypatch,
        talk_to_name={},
        uid_by_talk={"808602": "uidA"},
        name_by_uid={"uidA": "陆地飞鱼"},
        routing={"陆地飞鱼": "179238"},
    )
    assert wss.name_for_talk("808602") == "陆地飞鱼"
    assert wss.name_for_talk_verified("808602") == ""
