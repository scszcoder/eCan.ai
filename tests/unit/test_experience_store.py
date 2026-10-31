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


def test_daily_cap(st, monkeypatch):
    monkeypatch.setattr(store_mod, "EXPLORES_PER_DAY", 2)
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


def _asker(names):
    return lambda prompt: json.dumps({"parts": names}, ensure_ascii=False)


def test_parts_are_named_by_the_model_and_store_limits_dropped():
    from agent.ec_skills.experience import part_results, STORE_LIMIT
    failed = ["尺码表-无法填写尺码信息", "店铺为个人店，无法开通该类目"]
    passed = ["标题"]
    results, weights, named = part_results(failed, passed, ["标题"], _asker(["尺码表", STORE_LIMIT, "标题"]))
    assert results == {"尺码表": False, "标题": True}
    assert weights == {"尺码表": 1} and named == {"尺码表": ["尺码表-无法填写尺码信息"]}


def test_a_failed_and_passed_item_of_one_part_is_a_failure():
    from agent.ec_skills.experience import part_results
    results, _, _ = part_results(["ECC-12 的价格不对"], ["ECC-11"], (), _asker(["价格", "价格"]))
    assert results == {"价格": False}


def test_an_unusable_answer_names_nothing():
    from agent.ec_skills.experience import name_parts
    assert name_parts(["a", "b"], (), _asker(["只一个"])) == []
    assert name_parts(["a"], (), lambda p: "not json") == []
    assert name_parts([], (), _asker([])) == []


def test_the_explore_task_carries_the_toolbox():
    p = explore_prompt("尺码表", ["x"], "notes", "https://example/create", "data")
    assert "probe_page_data" in p and "write_form_field" in p and "revert_form_field" in p


def test_the_cooldown_holds_for_the_same_explorer_but_not_a_changed_one(st):
    for _ in range(2):
        st.grade({"尺码表": False})
    assert st.explore_target({"尺码表": False}, signature="A") == "尺码表"
    st.grade({"尺码表": False})
    assert st.explore_target({"尺码表": False}, signature="A") is None      # same explorer: wait
    assert st.explore_target({"尺码表": False}, signature="B") == "尺码表"  # toolbox/model changed


def test_a_known_failing_part_is_explored_before_the_next_run(st):
    for _ in range(2):
        st.grade({"尺码表": False}, {"尺码表": ["缺少身高、体重"]})
    assert st.parts()["尺码表"]["last_failures"] == ["缺少身高、体重"]
    assert st.pending_explore("A") == "尺码表"
    assert st.pending_explore("A") is None                                    # cooldown
    st.add_recipe({"part": "尺码表", "when": "w", "script": SCRIPT})
    assert st.pending_explore("B") is None                                    # it has a recipe to try


def test_the_signature_names_the_explorer():
    from agent.ec_skills.experience import explore_signature
    assert explore_signature("qwen3.7-flash", "qwen3.8-max") != explore_signature("qwen3.8-max")
    assert explore_signature("m") == explore_signature("m")


def test_the_toolbox_carries_a_probe_the_prompt_renderer_leaves_alone():
    from agent.ec_skills.experience.store import EXPLORE_TOOLBOX
    assert "probe_page_data(text)" in EXPLORE_TOOLBOX and "read_form_field(key)" in EXPLORE_TOOLBOX
    assert "{{" not in EXPLORE_TOOLBOX and "}}" not in EXPLORE_TOOLBOX


def test_the_toolbox_says_how_to_write_and_read_safely():
    from agent.ec_skills.experience.store import EXPLORE_TOOLBOX
    assert "write_form_field(key, value)" in EXPLORE_TOOLBOX and "不要自己写遍历组件的脚本" in EXPLORE_TOOLBOX


def test_a_key_build_recipe_becomes_a_runnable_script():
    final = json.dumps({"part": "尺码表", "key": "size_chart_form/configTable",
                        "build": "return DATA.rows.map(r => ({ size: r.s }))"})
    r = parse_recipe(final, "尺码表")
    assert r and "__DATA__" in r["script"] and "locate(key)" in r["script"]
    assert "{{" not in r["script"] and "}}" not in r["script"]


def test_namer_is_told_not_to_force_a_known_name():
    # KEN 2026-10-30: "属性 风格：…" was named 规格值, the nearest known part,
    # and the explorer spent 37 steps on spec values.
    from agent.ec_skills.experience import name_parts
    seen = []
    name_parts(["属性 风格：页面「运动活力」，资料「运动风」"], ["规格值", "尺码表"],
               lambda p: seen.append(p) or '{"parts": ["属性"]}')
    assert "不要硬套" in seen[0] and "开头已经写明" in seen[0]


def test_a_try_that_never_ran_is_given_back(tmp_path):
    from agent.ec_skills.experience import ExperienceStore
    xs = ExperienceStore(str(tmp_path))
    xs.grade({"尺码": False}); xs.grade({"尺码": False})
    assert xs.explore_target({"尺码": False}) == "尺码"
    assert xs.explore_target({"尺码": False}) is None      # cooling down
    xs.unmark_explored("尺码")
    assert xs.explore_target({"尺码": False}) == "尺码"
