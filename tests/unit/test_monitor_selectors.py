"""Which selectors is the DOM monitor actually depending on right now?

Nothing could answer this before, and that is how the live skill ended up
depending on `.lF_M7QiFB0ukHWpMfQde` for months after the JS readers had
abandoned it as dead. The selectors live in skill config a user can edit in the
skill editor, so any hand-written watch list elsewhere is stale the moment
someone changes one.

`selectors_in_use()` exposes them so the fingerprint can watch what the system
actually depends on rather than what somebody remembered to type.
"""

import pathlib

import pytest

from agent.ec_skills.browser_use_extension import event_monitor as em


@pytest.fixture(autouse=True)
def no_real_monitors(monkeypatch):
    monkeypatch.setattr(em, "_active_monitor_sets", {})
    yield


class _FakeSet:
    def __init__(self, configs):
        self.configs = configs
        self.monitor_set_id = "fake"


def _install(extractor, monkeypatch):
    """One running monitor whose config resolves to *extractor*."""
    monkeypatch.setattr(em, "_active_monitor_sets", {"fake": _FakeSet(["cfg"])})
    monkeypatch.setattr(em, "_resolve_dom_extractor_config", lambda cfg: extractor)


REAL_SHAPE = {
    "roots": ["#chantListScrollArea"],
    "items": [{
        "selector": "[data-qa-id='qa-conversation-chat-item']",
        "fields": {
            "name": {"selector": ".MP1bk3ccfHC9V2SnPCGD", "attr": "title",
                     "fallback": [{"selector": ".MP1bk3ccfHC9V2SnPCGD"},
                                  {"selector": ".Jv6FtqUv5VoYARd2pp4y"}]},
            "last_message": {"selector": ".lF_M7QiFB0ukHWpMfQde span"},
            "unread_badge": {"selector": ".auxo-badge-count"},
        },
    }],
}


def test_nothing_running_means_nothing_claimed():
    assert em.selectors_in_use() == {}


def test_it_reports_the_root_the_item_and_every_field(monkeypatch):
    _install(REAL_SHAPE, monkeypatch)
    found = em.selectors_in_use()
    assert found["root"] == "#chantListScrollArea"
    assert found["item"] == "[data-qa-id='qa-conversation-chat-item']"
    assert found["field:name"] == ".MP1bk3ccfHC9V2SnPCGD"
    assert found["field:last_message"] == ".lF_M7QiFB0ukHWpMfQde span"
    assert found["field:unread_badge"] == ".auxo-badge-count"


def test_fallback_selectors_are_reported_too(monkeypatch):
    """A fallback is a dependency: if the primary AND the fallbacks all die,
    the field dies. Watching only the primary would miss that."""
    _install(REAL_SHAPE, monkeypatch)
    found = em.selectors_in_use()
    assert ".Jv6FtqUv5VoYARd2pp4y" in found.values()


def test_a_body_root_is_not_reported(monkeypatch):
    """`body` is the default when nothing is configured — it is not a
    dependency and watching it says nothing."""
    _install({"roots": ["body"], "items": []}, monkeypatch)
    assert em.selectors_in_use() == {}


def test_the_field_with_no_fallback_is_visible_as_such(monkeypatch):
    """The point of exposing this: last_message has ONE selector and name has
    three. That asymmetry is what made the ws189 breakage asymmetric too."""
    _install(REAL_SHAPE, monkeypatch)
    found = em.selectors_in_use()
    name_keys = [k for k in found if k.startswith("field:name")]
    msg_keys = [k for k in found if k.startswith("field:last_message")]
    assert len(name_keys) > len(msg_keys)


@pytest.mark.parametrize("junk", [None, {}, {"roots": None, "items": None},
                                  {"items": [None, "x", {}]},
                                  {"roots": [None, 1, ""]},
                                  {"items": [{"fields": {"a": "not a dict"}}]}])
def test_a_malformed_config_is_survivable(junk, monkeypatch):
    _install(junk, monkeypatch)
    assert isinstance(em.selectors_in_use(), dict)


def test_a_resolver_that_throws_is_survivable(monkeypatch):
    monkeypatch.setattr(em, "_active_monitor_sets", {"fake": _FakeSet(["cfg"])})
    monkeypatch.setattr(em, "_resolve_dom_extractor_config",
                        lambda cfg: (_ for _ in ()).throw(RuntimeError("boom")))
    assert em.selectors_in_use() == {}


def test_it_is_site_agnostic():
    """It walks the extractor config's own shape and never interprets a
    selector — so it works for the next site without changes."""
    import inspect
    src = inspect.getsource(em.selectors_in_use)
    for term in ("feige", "douyin", "jinritemai", "qa-conversation", "chant"):
        assert term not in src.lower(), (
            f"selectors_in_use() mentions {term!r}; it must stay generic"
        )
