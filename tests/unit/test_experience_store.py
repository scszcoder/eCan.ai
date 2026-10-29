"""Explore-and-learn store: the check scores recipes, two failures in a row of one
part trigger one exploration (capped), and a recipe reaches the prompt with the
run's data filled in."""
import json

import pytest

from agent.ec_skills.experience import ExperienceStore, explore_prompt, parse_recipe
from agent.ec_skills.experience import store as store_mod

SCRIPT = "(async(DATA)=>{ return JSON.stringify({n: DATA.skus.length}) })(__DATA__)"


@pytest.fixture
def st(tmp_path, monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(store_mod, "_now", lambda: clock[0])
    s = ExperienceStore(str(tmp_path))
    s.clock = clock
    return s


def test_two_failures_in_a_row_trigger_one_exploration(st):
    st.grade({"规格编码": False, "标题": True})
    assert st.explore_target({"规格编码": False, "标题": True}) is None
    st.grade({"规格编码": False, "标题": True})
    assert st.explore_target({"规格编码": False, "标题": True}) == "规格编码"
    st.grade({"规格编码": False})
    assert st.explore_target({"规格编码": False}) is None          # cooldown


def test_a_pass_resets_the_count(st):
    st.grade({"规格编码": False})
    st.grade({"规格编码": True})
    st.grade({"规格编码": False})
    assert st.explore_target({"规格编码": False}) is None


def test_daily_cap(st):
    for part in ("a", "b", "c"):
        st.grade({part: False}); st.grade({part: False})
        st.explore_target({part: False})
    explored = [p for p in st.parts().values() if p.get("explored")]
    assert len(explored) == store_mod.EXPLORES_PER_DAY


def test_a_candidate_is_verified_by_a_pass_and_retired_by_a_failure(st):
    st.add_recipe({"part": "规格编码", "when": "填完价格后", "script": SCRIPT})
    st.grade({"规格编码": True})
    assert st.recipes()[0]["status"] == "verified"
    st.add_recipe({"part": "价格", "when": "x", "script": SCRIPT})
    st.grade({"价格": False})
    assert {r["part"]: r["status"] for r in st.recipes()}["价格"] == "failed"


def test_render_fills_the_data_and_skips_failed(st):
    st.add_recipe({"part": "规格编码", "when": "填完价格后", "script": SCRIPT})
    st.add_recipe({"part": "价格", "when": "x", "script": SCRIPT})
    st.grade({"价格": False})
    text = st.render({"skus": [1, 2]})
    assert "- 规格编码" in text and "- 价格" not in text
    assert '{"skus": [1, 2]}' in text and "__DATA__" not in text


def test_parse_recipe_needs_a_data_slot_and_drops_template_braces():
    final = "done: " + json.dumps({"part": "规格编码", "when": "w", "script": "(async(DATA)=>{{x}})(__DATA__)"})
    r = parse_recipe(final, "规格编码")
    assert r and "{{" not in r["script"] and "}}" not in r["script"]
    assert parse_recipe(json.dumps({"part": "p", "script": "alert(1)"}), "p") is None
    assert parse_recipe("no json", "p") is None


def test_explore_prompt_names_the_part_and_forbids_saving():
    p = explore_prompt("规格编码", ["页面上没有规格编码 X"], "notes", "https://example/create", "listing.json")
    assert "规格编码" in p and "绝不点“发布”" in p and "(async(DATA)=>{ ... })(__DATA__)" in p


def test_the_part_with_the_most_mismatches_is_explored_first(st):
    for _ in range(2):
        st.grade({"标题": False, "规格编码": False})
    assert st.explore_target({"标题": False, "规格编码": False}, {"标题": 1, "规格编码": 12}) == "规格编码"


def test_a_recipe_is_filed_under_the_explored_part():
    final = json.dumps({"part": "别的", "script": "(async(DATA)=>{ })(__DATA__)"})
    assert parse_recipe(final, "规格编码")["part"] == "规格编码"
