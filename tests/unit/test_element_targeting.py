"""Phase 1 of docs/SELF_HEALING_ROADMAP.md: measure before changing anything.

Two things are under test, and the second matters more than the first.

1. The platform bookkeeping itself — vocabulary, counters, bounds, and the
   guarantee that instrumentation can never raise into the path it measures.

2. That the platform module stays **business-free**. The standing directive is
   that platform code must not know about any site; a docstring mentioning one
   already slipped through once while writing this. A test is cheaper than
   remembering.
"""

import pathlib

import pytest

from agent.ec_skills.browser_use_extension import element_targeting as et


@pytest.fixture(autouse=True)
def clean():
    et.reset()
    yield
    et.reset()


# ── the vocabulary ─────────────────────────────────────────────────────────

def test_a_descriptor_that_names_visible_text_is_semantic():
    d = et.TargetDescriptor(target_text="Send", container_hint="reply box")
    assert d.is_semantic()
    assert "Send" in d.describe()


def test_a_descriptor_holding_only_selectors_is_not_semantic():
    """The whole point: a CSS expression is not a name, it is a bet."""
    d = et.TargetDescriptor(selector_fallbacks=("div.x > button:nth-child(2)",))
    assert not d.is_semantic()
    assert d.describe() == "(no semantic descriptor)"


def test_descriptors_are_hashable_so_they_can_key_learned_state():
    """Phase 3 stores what was resolved, keyed by descriptor."""
    a = et.TargetDescriptor(target_text="Send")
    b = et.TargetDescriptor(target_text="Send")
    assert {a, b} == {a}


# ── counting ───────────────────────────────────────────────────────────────

def test_it_records_which_strategy_won():
    et.record_resolution("site_a", "row_name", "semantic_text", ok=True)
    et.record_resolution("site_a", "row_name", "semantic_text", ok=True)
    et.record_resolution("site_a", "row_name", "legacy_class", ok=True)

    report = et.resolution_report()
    assert report["site_a"]["row_name"]["semantic_text"]["ok"] == 2
    assert report["site_a"]["row_name"]["legacy_class"]["ok"] == 1


def test_a_strategy_that_was_tried_and_failed_is_distinguishable():
    """'tried and missed' is the interesting signal, not just 'won'."""
    et.record_resolution("site_a", "row_name", "semantic_text", ok=False)
    counts = et.resolution_report()["site_a"]["row_name"]["semantic_text"]
    assert counts == {"ok": 0, "miss": 1}


def test_sites_and_elements_are_counted_separately():
    et.record_resolution("site_a", "row_name", "s1")
    et.record_resolution("site_b", "row_name", "s1")
    et.record_resolution("site_a", "send_button", "s1")

    report = et.resolution_report()
    assert set(report) == {"site_a", "site_b"}
    assert set(report["site_a"]) == {"row_name", "send_button"}


# ── the in-page tally ──────────────────────────────────────────────────────

def test_a_js_tally_is_recorded_in_one_go():
    """A scan resolves many elements per pass; it tallies in-page and hands
    over a map rather than calling back per element."""
    n = et.record_from_js_tally("site_a", "row_name",
                                {"semantic_text": 18, "legacy_class": 2})
    assert n == 20
    counts = et.resolution_report()["site_a"]["row_name"]
    assert counts["semantic_text"]["ok"] == 18
    assert counts["legacy_class"]["ok"] == 2


@pytest.mark.parametrize("junk", [None, "not a dict", 42, [], {"s": "NaN"},
                                  {"s": -3}, {"s": None}])
def test_a_malformed_tally_from_an_untrusted_page_is_survivable(junk):
    """The tally crosses from a page we do not control. It must never raise."""
    assert et.record_from_js_tally("site_a", "row_name", junk) == 0


# ── instrumentation must not be able to break the thing it measures ────────

def test_recording_never_raises_even_when_logging_explodes(monkeypatch):
    class _Boom:
        def info(self, *a, **k):
            raise RuntimeError("log sink died")

    monkeypatch.setattr(et, "logger", _Boom())
    monkeypatch.setattr(et, "_ROLLUP_INTERVAL_S", 0.0)   # force the log path
    et.record_resolution("site_a", "row_name", "s1")     # must not raise
    et.record_from_js_tally("site_a", "row_name", {"s1": 1})


def test_weird_labels_do_not_blow_up():
    et.record_resolution(None, None, None)               # type: ignore[arg-type]
    assert et.resolution_report()["?"]["?"]["unknown"]["ok"] == 1


def test_tracked_keys_are_bounded():
    """Per-element counters on a long-lived session must not grow forever."""
    for i in range(et._MAX_TRACKED_KEYS + 50):
        et.record_resolution(f"site_{i}", "row_name", "s1")
    assert len(et._BUCKETS) <= et._MAX_TRACKED_KEYS


def test_a_full_table_still_counts_elements_it_already_knows():
    """Dropping NEW keys must not stop counting the ones already tracked."""
    for i in range(et._MAX_TRACKED_KEYS):
        et.record_resolution(f"site_{i}", "row_name", "s1")
    et.record_resolution("site_0", "row_name", "s1")
    assert et.resolution_report()["site_0"]["row_name"]["s1"]["ok"] == 2


def test_it_is_safe_from_several_threads():
    import threading
    def work():
        for _ in range(200):
            et.record_resolution("site_a", "row_name", "s1")

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert et.resolution_report()["site_a"]["row_name"]["s1"]["ok"] == 800


# ── the standing directive ─────────────────────────────────────────────────

def test_the_platform_module_names_no_business(  ):
    """Platform code must stay site-independent. One slipped into a docstring
    while this module was being written; this is the cheap guard."""
    src = pathlib.Path(et.__file__).read_text(encoding="utf-8").lower()
    for term in ("feige", "douyin", "jinritemai", "飞鸽", "etsy", "ebay"):
        assert term not in src, (
            f"platform module element_targeting.py mentions '{term}'; "
            f"business specifics belong in hooks/external/<site>/"
        )
