"""Some descriptors are wrong before they ever fail.

`position_hint="item 2 of 3"` works until that customer has a fourth
conversation, and then it silently points at the wrong row. Locally every cycle
looks like a success — heal, break, heal, break — so nothing ever flags it.
The only way out is to refuse to learn that shape in the first place, however
well it is currently working.

The second half is memory: a retired descriptor leaves the serving bucket
immediately, but how long it lasted is the only evidence we get about which
*kinds* hold up. That outlives the descriptor.
"""

import pathlib

import pytest

from agent.ec_skills.browser_use_extension import learned_targets as lt
from agent.ec_skills.browser_use_extension.element_targeting import (
    TargetDescriptor,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(lt._STORE, "_path", lambda: tmp_path / "learned.json")
    monkeypatch.setenv("ECAN_RESOLVER_GUARD_DIR", str(tmp_path / "guard"))
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    from agent.ec_skills.browser_use_extension import resolver_guard
    resolver_guard.reset()
    lt.reset()
    yield
    resolver_guard.reset()
    lt.reset()


# ── what counts as fragile ─────────────────────────────────────────────────

@pytest.mark.parametrize("descriptor,fragile", [
    (TargetDescriptor(target_text="Send"), False),
    (TargetDescriptor(container_hint="conversation list"), False),
    (TargetDescriptor(target_text="Send", position_hint="item 2 of 3"), False),
    (TargetDescriptor(position_hint="item 2 of 3"), True),
    (TargetDescriptor(position_hint="first"), True),
    (TargetDescriptor(role="button"), True),
])
def test_fragility_is_about_form_not_track_record(descriptor, fragile):
    assert descriptor.is_fragile()[0] is fragile


def test_a_position_only_descriptor_explains_itself():
    fragile, why = TargetDescriptor(position_hint="item 2 of 3").is_fragile()
    assert fragile and "collection" in why


def test_text_plus_position_is_fine():
    """Position is a useful DISAMBIGUATOR next to a name. It is only fragile as
    the sole anchor, because then nothing says what the element is."""
    assert not TargetDescriptor(target_text="Edit",
                                position_hint="item 2 of 3").is_fragile()[0]


# ── refusing to learn it ───────────────────────────────────────────────────

def test_a_fragile_descriptor_is_never_learned():
    for _ in range(lt.PROMOTE_AFTER_HITS + 5):
        lt.record_success("s", "e", TargetDescriptor(position_hint="item 2 of 3"))
    assert lt.best_for("s", "e") is None
    assert lt.report() == {}


def test_a_fragile_descriptor_is_refused_out_loud(monkeypatch):
    """Silently dropping it would look identical to learning it."""
    lines = []
    monkeypatch.setattr(lt.logger, "info", lambda m: lines.append(m))
    lt.record_success("s", "e", TargetDescriptor(position_hint="first"))
    assert any("refusing to learn" in l for l in lines)


def test_a_sound_descriptor_is_still_learned():
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success("s", "e", TargetDescriptor(target_text="Alice",
                                                     container_hint="list"))
    assert lt.best_for("s", "e") is not None


def test_refusal_does_not_block_a_fragile_descriptor_from_FAILING():
    """A descriptor learned before this rule existed must still be able to
    retire — refusing only new learning, not the exit path."""
    lt.record_failure("s", "e", TargetDescriptor(position_hint="first"))  # no raise


# ── kinds ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("target,expected", [
    (lt.LearnedTarget(target_text="a"), "text"),
    (lt.LearnedTarget(container_hint="c"), "container"),
    (lt.LearnedTarget(target_text="a", container_hint="c"), "text+container"),
    (lt.LearnedTarget(target_text="a", position_hint="p"), "text+position"),
    (lt.LearnedTarget(), "none"),
])
def test_the_kind_is_which_semantic_fields_carry_it(target, expected):
    assert target.kind() == expected


# ── lifetimes ──────────────────────────────────────────────────────────────

def _promote_then_kill(site, element, descriptor):
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success(site, element, descriptor)
    for _ in range(lt.RETIRE_AFTER_MISSES):
        lt.record_failure(site, element, descriptor)


def test_a_retired_descriptor_leaves_its_lifetime_behind():
    """It goes from the serving bucket at once — keeping it would cost a wasted
    attempt every resolution — but what it taught us stays."""
    _promote_then_kill("s", "e", TargetDescriptor(target_text="Alice"))
    assert lt.best_for("s", "e") is None, "a retired descriptor must not be served"
    lifetimes = lt.kind_lifetimes()
    assert lifetimes["text"]["retired"] == 1


def test_promotion_is_timestamped():
    d = TargetDescriptor(target_text="Alice")
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success("s", "e", d)
    row = lt.report()["s"]["e"][0]
    assert row.get("promoted_at", 0) > 0


def test_a_descriptor_that_never_earned_trust_is_counted_separately():
    """A kind that keeps failing to earn promotion is as informative as one
    that earns it and then dies."""
    d = TargetDescriptor(target_text="Alice")
    lt.record_success("s", "e", d)                    # one hit, never promoted
    for _ in range(lt.RETIRE_AFTER_MISSES):
        lt.record_failure("s", "e", d)
    assert lt.kind_lifetimes()["text"]["never_promoted"] == 1


def test_lifetimes_survive_a_reload():
    _promote_then_kill("s", "e", TargetDescriptor(target_text="Alice"))
    lt.flush()
    lt._STORE._loaded = False
    lt._STORE._data.clear()
    lt._STORE._lifetimes.clear()
    assert lt.kind_lifetimes()["text"]["retired"] == 1


def test_the_lifetime_ledger_is_bounded():
    for i in range(lt.MAX_LIFETIMES + 30):
        _promote_then_kill("s", f"e{i}", TargetDescriptor(target_text=f"n{i}"))
    assert len(lt._STORE._lifetimes) <= lt.MAX_LIFETIMES


def test_an_old_store_without_lifetimes_still_loads(tmp_path, monkeypatch):
    """Backward compatibility: files written before this existed have no
    `_lifetimes` key."""
    import json
    path = tmp_path / "old.json"
    path.write_text(json.dumps({
        "s": {"e": [{"target_text": "Alice", "hits": 5}]}
    }), encoding="utf-8")
    monkeypatch.setattr(lt._STORE, "_path", lambda: path)
    lt._STORE._loaded = False
    lt._STORE._data.clear()
    lt._STORE._lifetimes.clear()
    assert lt.report()["s"]["e"], "an old store failed to load"
    assert lt.kind_lifetimes() == {}


# ── using what was learned ─────────────────────────────────────────────────

def test_score_still_beats_kind_history():
    """A kind that once lasted a long time must not outrank a descriptor that
    is working right now."""
    lt._STORE._lifetimes.append(
        {"kind": "container", "promoted": True, "survived_s": 999999})
    good = TargetDescriptor(target_text="Alice")
    weak = TargetDescriptor(container_hint="the list")
    for _ in range(10):
        lt.record_success("s", "e", good)
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success("s", "e", weak)
    lt.record_failure("s", "e", weak)
    lt.record_success("s", "e", weak)
    assert lt.best_for("s", "e").target_text == "Alice"


def test_kind_history_separates_equally_good_descriptors():
    lt._STORE._lifetimes.append(
        {"kind": "text+container", "promoted": True, "survived_s": 90000})
    lt._STORE._lifetimes.append(
        {"kind": "container", "promoted": True, "survived_s": 10})
    durable = TargetDescriptor(target_text="Alice", container_hint="list")
    flimsy = TargetDescriptor(container_hint="list")
    for _ in range(lt.PROMOTE_AFTER_HITS):
        lt.record_success("s", "e", durable)
        lt.record_success("s", "e", flimsy)
    best = lt.best_for("s", "e")
    assert best.target_text == "Alice"


def test_an_unknown_kind_ranks_neutral_not_worst():
    """A kind with no history has not failed — it has not been tried. Burying
    it would stop us ever learning about it."""
    lifetimes = {"container": {"median_survived_s": 500.0}}
    assert lt._kind_rank("text", lifetimes) == 0.0
    assert lt._kind_rank("container", lifetimes) == 500.0


def test_the_kind_report_is_quiet_before_anything_retires(monkeypatch):
    lines = []
    monkeypatch.setattr(lt.logger, "info", lambda m: lines.append(m))
    lt.log_kind_report()
    assert not any("kind lifetimes" in l for l in lines)


def test_the_kind_report_names_the_durable_kind_first(monkeypatch):
    lt._STORE._lifetimes.extend([
        {"kind": "container", "promoted": True, "survived_s": 10},
        {"kind": "text", "promoted": True, "survived_s": 90000},
    ])
    lines = []
    monkeypatch.setattr(lt.logger, "info", lambda m: lines.append(m))
    lt.log_kind_report()
    body = [l for l in lines if "median after promotion" in l]
    assert body and "text:" in body[0]


def test_the_run_end_reports_kind_lifetimes():
    import inspect
    from agent.ec_tasks import runner
    src = inspect.getsource(runner)
    assert "log_kind_report" in src


# ── the standing directive ─────────────────────────────────────────────────

def test_the_platform_modules_name_no_business():
    for mod in (lt, __import__(
            "agent.ec_skills.browser_use_extension.element_targeting",
            fromlist=["x"])):
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8").lower()
        for term in ("feige", "douyin", "jinritemai", "飞鸽", "etsy", "ebay"):
            assert term not in src, f"{mod.__name__} mentions {term}"
