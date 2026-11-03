"""Fill flows as data: the engine's steps and guards, the version store, the
explorer's edits (agent/ec_skills/fill)."""
import asyncio

import pytest

from agent.ec_skills.fill.engine import run_flow
from agent.ec_skills.fill.explore import edit, finish
from agent.ec_skills.fill.store import FillStore, validate


class FakePage:
    """Answers a page script by the first keyword of *answers* it contains."""

    def __init__(self, answers):
        self.answers, self.clicks, self.typed, self.keys, self.scripts = answers, [], [], [], []
        self.network, self.client = [], None

    async def evaluate(self, expr, timeout=30):
        self.scripts.append(expr)
        for key, val in self.answers.items():
            if key in expr:
                return val(expr) if callable(val) else val
        return None

    async def mouse_click(self, x, y):
        self.clicks.append((x, y))

    async def insert_text(self, text):
        self.typed.append(text)

    async def press(self, key):
        self.keys.append(key)

    async def send(self, method, params=None, timeout=30):
        return {}


def flow(*steps, **kw):
    return dict({"steps": list(steps), "snippets": {}}, **kw)


SUBMIT = {"id": "submit", "op": "submit", "target": "SUBMIT_BTN", "until": "SUBMITTED"}
GUARDS = {"forbid_click": "发布|提交|保存"}


def run(page, f, mode="publish", listing=None):
    return asyncio.run(run_flow(page, f, GUARDS, listing or {"title": "t"}, {}, {}, mode))


def test_dry_run_stops_at_submit_with_the_report():
    page = FakePage({"READ_FORM": {"title": "t"}, "STEP1": True})
    out = run(page, flow({"id": "a", "js": "STEP1"}, SUBMIT, {"id": "after", "js": "NEVER"}, report="READ_FORM"), "dry_run")
    assert out["ok"] and out["report"] == {"title": "t"}
    assert not any("NEVER" in s for s in page.scripts) and not page.clicks


def test_a_failing_step_names_itself_and_the_page():
    page = FakePage({"BAD": {"error": "no box"}})
    out = run(page, flow({"id": "a", "stage": "标题", "js": "BAD", "error": "title box"}, SUBMIT))
    assert not out["ok"] and out["step"] == "a" and out["stage"] == "标题"
    assert "title box" in out["error"] and "no box" in out["error"] and "diag" in out


def test_optional_failure_is_a_problem_not_the_end():
    page = FakePage({"BAD": None, "READ": {}})
    out = run(page, flow({"id": "a", "js": "BAD", "optional": True, "error": "详情图没有放上"}, SUBMIT, report="READ"), "dry_run")
    assert out["ok"] and out["vars"]["problems"] == ["详情图没有放上"]


def test_click_on_a_publish_button_outside_submit_is_refused():
    page = FakePage({"label:": {"x": 1, "y": 2, "label": "提交宝贝信息"}})
    out = run(page, flow({"id": "c", "op": "click", "target": "BTN"}, SUBMIT))
    assert not out["ok"] and "refused" in out["error"] and not page.clicks


def test_submit_step_may_press_it_in_publish_mode():
    page = FakePage({"label:": {"x": 1, "y": 2, "label": "提交宝贝信息"}, "SUBMITTED": True})
    out = run(page, flow(SUBMIT))
    assert out["ok"] and page.clicks == [(1, 2)]


def test_foreach_runs_its_steps_per_item_and_skips_by_if():
    seen = []
    page = FakePage({"ITEMS": ["a", "b", "c"], "SKIP_B": lambda e: '"item": "b"' not in e,
                     "TOUCH": lambda e: seen.append(e) or True, "READ": {}})
    out = run(page, flow({"id": "each", "op": "foreach", "items": "ITEMS",
                          "steps": [{"id": "t", "if": "SKIP_B", "js": "TOUCH"}]}, SUBMIT, report="READ"), "dry_run")
    assert out["ok"] and len(seen) == 2


def test_validate_refuses_broken_flows():
    assert "submit" in validate(flow({"id": "a", "js": "x"}))
    assert "twice" in validate(flow({"id": "a"}, {"id": "a"}, SUBMIT))
    assert "unknown op" in validate(flow({"id": "a", "op": "eval_python"}, SUBMIT))
    assert validate(flow({"id": "a"}, SUBMIT)) == ""


def seed():
    return dict(flow({"id": "a", "js": "x"}, SUBMIT), guards={"dry_block": ["*draft*"], "forbid_click": "提交"})


def test_seed_versions_and_guards_come_only_from_the_seed(tmp_path):
    st = FillStore(str(tmp_path))
    st.seed(seed(), "notes")
    f, g, v = st.current()
    assert v == 1 and g["dry_block"] == ["*draft*"] and "guards" not in f
    w = st.working()
    w["guards"] = {"dry_block": []}            # an edit cannot reach the guards
    assert st.save_working(w) == ""
    assert "guards" not in st.working() and st.guards()["dry_block"] == ["*draft*"]
    st.seed(seed())                            # same seed: nothing new
    assert st.current()[2] == 1


def test_propose_needs_a_passing_dry_run_of_that_exact_copy(tmp_path):
    st = FillStore(str(tmp_path))
    st.seed(seed())
    assert "nothing was edited" in st.propose("x")[1]
    assert edit(st, {"set_snippet": "x", "code": "1 + 1"}).startswith("片段 x")
    assert "dry run" in st.propose("x")[1]
    st.note_dry_run(st.working(), {"ok": True, "check": {"ok": False}})
    assert "did not pass" in st.propose("x")[1]
    st.note_dry_run(st.working(), {"ok": True, "check": {"ok": True}})
    edit(st, {"set_snippet": "y", "code": "2"})          # changed after the dry run
    assert "changed after" in st.propose("x")[1]
    st.note_dry_run(st.working(), {"ok": True, "check": {"ok": True}})
    n, why = st.propose("fixed the title box")
    assert n == 2 and why == "" and st.current()[2] == 2


def test_a_candidate_that_fails_its_real_check_is_rolled_back(tmp_path):
    st = FillStore(str(tmp_path))
    st.seed(seed())
    edit(st, {"set_snippet": "x", "code": "2"})
    st.note_dry_run(st.working(), {"ok": True, "check": {"ok": True}})
    n, _ = st.propose("try")
    st.grade(n, ok=False)
    assert st.current()[2] == 1
    assert [v["status"] for v in st.meta()["versions"]] == ["seed", "failed"]


def test_edits_insert_replace_delete_and_refuse_bad_shapes(tmp_path):
    st = FillStore(str(tmp_path))
    st.seed(seed())
    assert "插入" in edit(st, {"insert_after": "a", "step": {"id": "b", "js": "y"}})
    assert [s["id"] for s in st.working()["steps"]] == ["a", "b", "submit"]
    assert "替换" in edit(st, {"set_step": "b", "step": {"id": "b", "op": "wait", "js": "z"}})
    assert "拒绝" in edit(st, {"delete_step": "submit"})      # a flow must keep its submit
    assert "删除" in edit(st, {"delete_step": "b"})
    assert "没有步骤" in edit(st, {"set_step": "zz", "step": {"id": "zz"}})


def test_finish_proposes_only_a_fixed_and_passed_copy(tmp_path):
    st = FillStore(str(tmp_path))
    st.seed(seed())
    assert finish(str(tmp_path), '{"fill_fixed": false, "root_cause": "login page"}')[0] == 0
    edit(st, {"set_snippet": "x", "code": "3"})
    st.note_dry_run(st.working(), {"ok": True, "check": {"ok": True}})
    n, why = finish(str(tmp_path), '{"fill_fixed": true, "change": "x", "findings": "the box moved"}')
    assert n == 2 and why == "" and "the box moved" in st.notes()


# ── the skill's fill node: run, repair once, run again ─────────────────
import json as _json

from agent.ec_skills.fill import node as fill_node


def _state(tmp_path):
    item = tmp_path / "item"
    item.mkdir()
    (item / "listing.json").write_text(_json.dumps({"title": "t", "files": {"main": ["a.png"]}}), encoding="utf-8")
    (item / "a.png").write_bytes(b"x")
    exp = tmp_path / "exp"
    return {"attributes": {"listing_dir": str(item), "listing_file_map": {"a.png": str(item / "a.png")},
                           "listing_experience_files": {"platform": str(exp / "_platform.md")}},
            "prompt_refs": {"store_id": "s1"}}, str(exp)


def _scripted(monkeypatch, outcomes, repair_to=0):
    calls = {"runs": 0, "repairs": 0}

    def fake_run_sync(fn, timeout):
        calls["runs"] += 1
        return dict(outcomes.pop(0))

    def fake_repair(store, *a, **k):
        calls["repairs"] += 1
        if repair_to:
            edit(store, {"set_snippet": "fixed", "code": "1"})
            store.note_dry_run(store.working(), {"ok": True, "check": {"ok": True}})
            return store.propose("fixed")[0]
        return 0
    monkeypatch.setattr(fill_node, "_run_sync", fake_run_sync)
    monkeypatch.setattr(fill_node, "_port", lambda *a: 1)
    monkeypatch.setattr(fill_node, "_repair", fake_repair)
    return calls


def test_a_page_failure_is_repaired_and_the_listing_filled_again(tmp_path, monkeypatch):
    state, exp = _state(tmp_path)
    calls = _scripted(monkeypatch, [{"ok": False, "stage": "规格", "error": "颜色没有加上"},
                                    {"ok": True, "vars": {"product_id": "123"}}], repair_to=2)
    out = fill_node.run_fill_node(state, seed(), explore_model="m")
    a = out["attributes"]
    assert calls == {"runs": 2, "repairs": 1} and a["fill_ok"] and a["fill_version"] == 2
    assert a["fill_result"]["repaired"] and "123" in out["tool_result"]["browser_publish"]["final"]


def test_login_problems_are_not_sent_to_the_explorer(tmp_path, monkeypatch):
    state, exp = _state(tmp_path)
    calls = _scripted(monkeypatch, [{"ok": False, "stage": "类目", "error": "这个浏览器没有登录淘宝/千牛"}])
    out = fill_node.run_fill_node(state, seed(), explore_model="m")
    assert calls["repairs"] == 0 and not out["attributes"]["fill_ok"]
    assert FillStore(exp)._load("last_failure.json", {})["stage"] == "类目"


def test_repairs_are_capped_per_day(tmp_path, monkeypatch):
    state, exp = _state(tmp_path)
    monkeypatch.setattr(fill_node, "REPAIRS_PER_DAY", 1)
    calls = _scripted(monkeypatch, [{"ok": False, "stage": "规格", "error": "x"}] * 2)
    fill_node.run_fill_node(state, seed(), explore_model="m")
    fill_node.run_fill_node(state, seed(), explore_model="m")
    assert calls["repairs"] == 1


def test_dry_block_can_match_by_method():
    from types import SimpleNamespace
    from agent.ec_skills.fill.engine import FlowRun as Runner
    handlers, sent = [], []
    page = FakePage({})
    page.client = SimpleNamespace(register=SimpleNamespace(Fetch=SimpleNamespace(requestPaused=handlers.append)))

    async def send(method, params=None, timeout=30):
        sent.append((method, params))
    page.send = send

    async def go():
        r = Runner(page, flow(SUBMIT), {"dry_block": ["POST *://h/sell/publish.htm*", "*://h/draft/*"]}, {}, {}, {}, "dry_run")
        await r.arm()
        for i, (m, u) in enumerate([("GET", "https://h/sell/publish.htm?x=1"), ("POST", "https://h/sell/publish.htm"),
                                    ("GET", "https://h/draft/add.json")]):
            handlers[0]({"requestId": str(i), "request": {"method": m, "url": u}})
        await asyncio.sleep(0)
        return r
    r = asyncio.run(go())
    assert [m for m, _ in sent[1:]] == ["Fetch.continueRequest", "Fetch.failRequest", "Fetch.failRequest"]
    assert r.blocked == ["POST https://h/sell/publish.htm", "GET https://h/draft/add.json"]
