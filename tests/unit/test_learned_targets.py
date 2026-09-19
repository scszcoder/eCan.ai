"""L3: confidence is earned repeatedly, and only semantics are learned.

Two properties matter more than the rest.

**A selector is never learned.** It would be easy to cache whatever L2 resolved
as a CSS expression, and we would be rebuilding the thing that has broken four
times this year — only now generated automatically and at scale. A learned
selector is a faster way to acquire the same debt.

**One hit is not evidence.** A descriptor that worked once may have worked by
luck. Promotion needs repetition, and a descriptor that stops working has to be
able to lose its place, or the store becomes a cache of yesterday's page.
"""

import json

import pytest

from agent.ec_skills.browser_use_extension import learned_targets as lt
from agent.ec_skills.browser_use_extension.element_targeting import TargetDescriptor


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(lt._STORE, "_path", lambda: tmp_path / "learned.json")
    lt.reset()
    yield
    lt.reset()


NAME = TargetDescriptor(target_text="customer name",
                        container_hint="conversation list")


# ── what may be learned ────────────────────────────────────────────────────

def test_a_selector_only_descriptor_is_never_learned():
    """The point of the whole design: we do not learn brittle things."""
    selector_only = TargetDescriptor(selector_fallbacks=("div.x > span:nth-child(2)",))
    for _ in range(10):
        lt.record_success("s", "row_name", selector_only)
    assert lt.report() == {}


def test_an_empty_descriptor_is_never_learned():
    for _ in range(10):
        lt.record_success("s", "row_name", TargetDescriptor())
    assert lt.report() == {}


# ── earning trust ──────────────────────────────────────────────────────────

def test_one_hit_is_not_enough_to_be_served():
    lt.record_success("s", "row_name", NAME)
    assert lt.best_for("s", "row_name") is None


def test_it_is_served_once_it_has_repeated():
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success("s", "row_name", NAME)
    best = lt.best_for("s", "row_name")
    assert best is not None
    assert best.target_text == "customer name"


def test_a_descriptor_that_stops_working_is_retired():
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success("s", "row_name", NAME)
    assert lt.best_for("s", "row_name") is not None

    for _ in range(lt.RETIRE_AFTER_MISSES):
        lt.record_failure("s", "row_name", NAME)
    assert lt.best_for("s", "row_name") is None, (
        "a stale descriptor must lose its place, or the store becomes a cache "
        "of a page that no longer exists"
    )


def test_a_single_miss_does_not_unseat_a_proven_descriptor():
    """Pages flicker. One failure is noise, not evidence."""
    for _ in range(10):
        lt.record_success("s", "row_name", NAME)
    lt.record_failure("s", "row_name", NAME)
    assert lt.best_for("s", "row_name") is None      # consecutive_misses == 1
    lt.record_success("s", "row_name", NAME)          # recovers immediately
    assert lt.best_for("s", "row_name") is not None


def test_a_failure_for_something_never_learned_does_not_create_it():
    lt.record_failure("s", "row_name", NAME)
    assert lt.report() == {}


# ── choosing between several ───────────────────────────────────────────────

def test_the_better_performer_wins():
    good = TargetDescriptor(target_text="good")
    poor = TargetDescriptor(target_text="poor")
    for _ in range(10):
        lt.record_success("s", "row_name", good)
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success("s", "row_name", poor)
    for _ in range(2):
        lt.record_failure("s", "row_name", poor)
        lt.record_success("s", "row_name", poor)     # keep it un-retired
    assert lt.best_for("s", "row_name").target_text == "good"


def test_a_lucky_one_of_one_does_not_outrank_a_long_record():
    """Score is damped so 1/1 does not beat 40/42."""
    long_record = lt.LearnedTarget(target_text="long", hits=40, misses=2)
    lucky = lt.LearnedTarget(target_text="lucky", hits=1, misses=0)
    assert long_record.score() > lucky.score()


def test_the_store_does_not_grow_without_bound():
    for i in range(lt.MAX_PER_ELEMENT + 20):
        d = TargetDescriptor(target_text=f"variant {i}")
        for _ in range(lt.PROMOTE_AFTER_HITS):
            lt.record_success("s", "row_name", d)
    assert len(lt.report()["s"]["row_name"]) <= lt.MAX_PER_ELEMENT


# ── persistence ────────────────────────────────────────────────────────────

def test_what_was_learned_survives_a_restart(tmp_path, monkeypatch):
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success("s", "row_name", NAME)
    lt.flush()

    lt.reset()
    lt._STORE._loaded = False                 # simulate a fresh process
    assert lt.best_for("s", "row_name").target_text == "customer name"


def test_a_corrupt_store_does_not_stop_a_run(tmp_path, monkeypatch):
    (tmp_path / "learned.json").write_text("{ not json", encoding="utf-8")
    lt.reset()
    lt._STORE._loaded = False
    assert lt.best_for("s", "row_name") is None      # empty, not an exception


def test_rows_whose_shape_drifted_are_skipped_not_fatal(tmp_path):
    (tmp_path / "learned.json").write_text(json.dumps({
        "s": {"row_name": [
            {"target_text": "ok", "hits": 5, "consecutive_misses": 0},
            {"unexpected_field": "from a future version"},
        ]}
    }), encoding="utf-8")
    lt.reset()
    lt._STORE._loaded = False
    assert lt.best_for("s", "row_name").target_text == "ok"


def test_writing_is_atomic(tmp_path):
    """A half-written store on a crash would be read back as corrupt."""
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success("s", "row_name", NAME)
    lt.flush()
    assert (tmp_path / "learned.json").exists()
    assert not (tmp_path / "learned.tmp").exists(), "temp file must be renamed"


def test_nothing_is_written_until_flush(tmp_path):
    lt.record_success("s", "row_name", NAME)
    assert not (tmp_path / "learned.json").exists(), (
        "writing per hit would be pointless churn on a hot path"
    )


# ── it must not break a run ────────────────────────────────────────────────

def test_recording_never_raises(monkeypatch):
    monkeypatch.setattr(lt._STORE, "load",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    lt.record_success("s", "row_name", NAME)      # must not raise
    lt.record_failure("s", "row_name", NAME)


def test_the_learning_module_names_no_business():
    import pathlib
    src = pathlib.Path(lt.__file__).read_text(encoding="utf-8").lower()
    for term in ("feige", "douyin", "jinritemai", "etsy", "ebay"):
        assert term not in src
