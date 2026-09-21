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


# ── a monitor on its page finding nothing ───────────────────────────────────
#
# `dom_items=0` with `site_tab=found` was already computed and already
# reported; its only consumer was a UI dot. "The selector died" and "nobody
# wrote in" are indistinguishable from the count alone, and the first is
# invisible until a customer complains.

from agent.ec_skills.browser_use_extension import degraded_state as ds


@pytest.fixture(autouse=True)
def clean_degraded():
    ds.reset()
    yield
    ds.reset()


def test_one_empty_poll_is_not_a_failure():
    """A frame mid-rebuild or a list still painting yields zero for a tick."""
    state = {}
    em._note_item_yield("sidebar", "http://x", 0, state)
    assert ds.active() == {}


def test_a_sustained_zero_is_recorded():
    state = {}
    for _ in range(em._NO_ITEMS_STREAK_FOR_DEGRADED):
        em._note_item_yield("sidebar", "http://x", 0, state)
    assert "monitor_no_items:sidebar" in ds.active()


def test_it_says_so_loudly_exactly_once(monkeypatch):
    """A per-poll warning would drown the log; silence would hide it."""
    lines = []
    monkeypatch.setattr(em.logger, "warning", lambda m: lines.append(m))
    state = {}
    for _ in range(em._NO_ITEMS_STREAK_FOR_DEGRADED * 3):
        em._note_item_yield("sidebar", "http://x", 0, state)
    hits = [l for l in lines if "ZERO items" in l]
    assert len(hits) == 1
    assert "item selector no longer matches" in hits[0]


def test_finding_items_again_clears_it():
    state = {}
    for _ in range(em._NO_ITEMS_STREAK_FOR_DEGRADED):
        em._note_item_yield("sidebar", "http://x", 0, state)
    em._note_item_yield("sidebar", "http://x", 3, state)
    assert ds.active() == {}
    assert state["_no_items_streak"] == 0


def test_the_streak_restarts_after_a_recovery():
    state = {}
    for _ in range(em._NO_ITEMS_STREAK_FOR_DEGRADED):
        em._note_item_yield("sidebar", "http://x", 0, state)
    em._note_item_yield("sidebar", "http://x", 1, state)
    em._note_item_yield("sidebar", "http://x", 0, state)
    assert ds.active() == {}, "one empty poll after recovery is not a failure"


def test_monitors_are_tracked_separately():
    a, b = {}, {}
    for _ in range(em._NO_ITEMS_STREAK_FOR_DEGRADED):
        em._note_item_yield("sidebar", "http://x", 0, a)
        em._note_item_yield("thread", "http://x", 5, b)
    active = ds.active()
    assert "monitor_no_items:sidebar" in active
    assert "monitor_no_items:thread" not in active


def test_it_never_raises(monkeypatch):
    monkeypatch.setattr(ds, "mark_degraded",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    state = {}
    for _ in range(em._NO_ITEMS_STREAK_FOR_DEGRADED + 1):
        em._note_item_yield("sidebar", "http://x", 0, state)   # must not raise


def test_the_threshold_is_a_count_not_a_duration():
    """The poll interval is configurable per skill, so a time-based threshold
    would mean different sensitivity per skill."""
    import inspect
    src = inspect.getsource(em._note_item_yield)
    assert "streak" in src
    assert "time.time" not in src


def test_it_is_called_where_the_pair_is_reported():
    import inspect
    src = inspect.getsource(em)
    assert "_note_item_yield(str(getattr(cfg" in src, (
        "the liveness check is not wired to the place that already computes "
        "site_tab and dom_items"
    )


def test_this_liveness_check_stays_site_agnostic():
    import inspect
    src = inspect.getsource(em._note_item_yield)
    for term in ("feige", "douyin", "jinritemai", "qa-conversation"):
        assert term not in src.lower()
