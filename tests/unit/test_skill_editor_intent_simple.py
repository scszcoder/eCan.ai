"""The rule-based intent shortcut keeps load/save for short commands only
(agent/skill_editor/skill_editor_agent.py; 2026-11-18: a skill spec containing
"upload" and "skill" was answered "which skill to load?")."""
import json

from agent.skill_editor.schemas import IntentType
from agent.skill_editor.skill_editor_agent import SkillEditorAgent

SPEC = ('create a "order_demo" skill that handles custom orders. 1) read the customer message with the '
        'attached image. 2) go to the supplier site, click 上传图片 to upload the image, then 保存 the '
        'preview as a png. 3) upload: open the order page, click import and upload the excel file.')


def _classify(msg):
    agent = object.__new__(SkillEditorAgent)
    agent._log_analysis_context = None
    return agent._classify_intent_simple(msg)


def test_a_long_skill_spec_mentioning_upload_is_a_create_request():
    assert _classify(SPEC) == IntentType.CREATE_FLOWGRAM


def test_short_load_and_save_commands_still_work():
    assert _classify("load ebay000 skill") == IntentType.LOAD_SKILL
    assert _classify("加载技能 ebay000") == IntentType.LOAD_SKILL
    assert _classify("save the skill") == IntentType.SAVE_SKILL


def test_upload_alone_is_not_load():
    assert _classify("upload the skill icon") != IntentType.LOAD_SKILL


SPEC_WITH_LOGIN = ('create a "order_demo" skill: go to https://supplier.example.com/alpha/#/orders, use the '
                   'browser stored login name and password to log in, then upload the order file.')


def test_login_and_a_url_do_not_make_a_skill_spec_a_log_analysis():
    assert _classify(SPEC_WITH_LOGIN) == IntentType.CREATE_FLOWGRAM


def test_log_analysis_requests_still_work():
    assert _classify(r"analyze the run log C:\work\runlogs\app.log") == IntentType.ANALYZE_LOG
    assert _classify("please check the errors in app.log") == IntentType.ANALYZE_LOG


def test_a_skill_with_chinese_text_is_saved_whole(tmp_path):
    # 2026-11-18: written in the Windows default encoding, the Chinese prompt failed
    # half-way and left an empty skill file that was then reported as saved.
    import json
    agent = object.__new__(SkillEditorAgent)
    skill = {"skillName": "demo", "workFlow": {"nodes": [{"id": "n1", "data": {"prompt": "选择材质、手机型号、颜色"}}], "edges": []}}
    path = tmp_path / "demo_skill.json"
    agent._write_skill_and_bundle(skill, {"mainSheetId": "main", "sheets": []}, path)
    assert json.loads(path.read_text(encoding="utf-8"))["workFlow"]["nodes"][0]["data"]["prompt"] == "选择材质、手机型号、颜色"


def test_a_generated_code_node_keeps_its_code_in_the_skill():
    # Code nodes were banned from the generator (llm + mcp instead) and a node without
    # code got a default that did not parse; a code node's source must reach data.script.
    from agent.skill_editor.code_agent import CodeAgent
    src = "def main(state, *, runtime=None, store=None, **kwargs):\n    state['attributes']['n'] = 1\n    return state\n"
    parser = object.__new__(CodeAgent)
    for data in ({"title": "Load", "code": src}, {"title": "Load", "script": {"language": "python", "content": src}}):
        node = parser._parse_node({"id": "code_load_status", "type": "code", "data": data}, 0)
        out = object.__new__(SkillEditorAgent)._node_to_json(node)
        assert out["data"]["script"]["content"] == src


def test_the_generator_is_told_to_use_code_nodes_and_where_browser_results_are():
    from agent.skill_editor import code_agent
    assert "FORBIDDEN" not in code_agent.CODE_GENERATION_PROMPT
    assert 'state["tool_result"]["<node id>"]["final"]' in code_agent.CODE_GENERATION_PROMPT
    compile(code_agent.CODE_NODE_DEFAULT_TEMPLATE, "default", "exec")


def test_a_fix_pass_does_not_cut_prompts_and_code_short():
    from agent.skill_editor.code_agent import CodeAgent
    from agent.skill_editor.schemas import Flowgram, FlowgramNode
    long_code = "def main(state, *, runtime=None, store=None, **kwargs):\n" + "    x = 1\n" * 60 + "    return state\n"
    long_prompt = "Step 1. " * 80
    original = Flowgram(nodes=[FlowgramNode(id="code_a", type="code", config={"code": long_code}),
                               FlowgramNode(id="browser_automation_b", type="browser_automation", config={"prompt": long_prompt})], edges=[])
    fixed = Flowgram(nodes=[FlowgramNode(id="code_a", type="code", config={"code": long_code[:200] + "…[truncated]"}),
                            FlowgramNode(id="browser_automation_b", type="browser_automation", config={"prompt": long_prompt[:200]})], edges=[])
    CodeAgent._restore_truncated_fields(original, fixed)
    assert fixed.nodes[0].config["code"] == long_code
    assert fixed.nodes[1].config["prompt"] == long_prompt


def test_a_missing_estimated_node_type_is_only_a_warning():
    from agent.skill_editor.code_agent import CodeAgent
    from agent.skill_editor.schemas import Flowgram, FlowgramNode, FlowgramEdge, ImplementationPlan
    fg = Flowgram(nodes=[FlowgramNode(id="start", type="start"), FlowgramNode(id="end", type="end")],
                  edges=[FlowgramEdge(source="start", target="end")])
    plan = ImplementationPlan(summary="s", steps=[], estimated_nodes=["start", "loop", "end"])
    v = object.__new__(CodeAgent).validate_flowgram(fg, plan)
    assert not [e for e in v.errors if "loop" in e.message]


def test_browser_nodes_get_the_named_profile_and_a_realistic_timeout():
    # Generated browser nodes had no profile (no store login), a 120 s timeout and a fixed OpenAI model.
    from agent.skill_editor import code_agent
    config = {"browserProfileId": "shop_0"}
    object.__new__(code_agent.CodeAgent)._apply_config_defaults("browser_automation", config)
    assert config["browser"] == "fingerprint" and config["timeout_seconds"] >= 1500
    assert "SAFETY RULES" in code_agent.CODE_GENERATION_PROMPT and "save_element_screenshot" in code_agent.EDIT_FLOWGRAM_PROMPT
    assert "gpt-5.5" not in code_agent.CODE_GENERATION_PROMPT
    for p in (code_agent.CODE_GENERATION_PROMPT, code_agent.EDIT_FLOWGRAM_PROMPT):
        assert "One row per unit" in p and "Write a file only after" in p and "send_email_to_cloud" in p


def test_local_files_named_in_a_request_are_described(tmp_path):
    # The generator guessed a template's name and layout; the desktop now describes the real files.
    import openpyxl
    from agent.skill_editor.local_files import describe_local_files
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["*平台", "订单号", "*收件人姓名", "商品信息"])
    ws.append([None, None, None, "*自定义sku"])
    ws.append(["其他平台", 3892, "Jane Roe", "A-B-C"])
    wb.save(tmp_path / "template7.xlsx")
    (tmp_path / "site.txt").write_text("login: secret-value", encoding="utf-8")
    text = describe_local_files([f"put the work in {tmp_path.as_posix()}/（已有模板）", "C:/no/such/place"])
    assert "template7.xlsx" in text and "*自定义sku" in text and "3892" in text
    assert "Jane Roe" not in text and "secret-value" not in text and "no/such" not in text


def test_a_dated_json_report_is_described_by_its_layout_not_its_values(tmp_path):
    # The coder looped over photo_order as a list; it is {"main": ..., "gallery": [...]}.
    from agent.skill_editor.local_files import describe_local_files
    day = tmp_path / "2026-01-02"
    day.mkdir()
    (day / "report.json").write_text(json.dumps(
        {"proposals": [{"model": "M1", "photo_order": {"main": "a.jpg", "gallery": ["b.jpg"]}}]}), encoding="utf-8")
    text = describe_local_files([f"read {tmp_path.as_posix()}/<date>/report.json"])
    assert '"photo_order": {"main": str, "gallery": [str, ...]}' in text
    assert "M1" not in text and "a.jpg" not in text


def test_a_new_skill_does_not_replace_an_existing_one(tmp_path, monkeypatch):
    from agent.skill_editor import skill_editor_agent as sea
    from agent.skill_editor.schemas import Flowgram
    def make(name):
        (tmp_path / name / "diagram_dir").mkdir(parents=True)
        (tmp_path / name / "diagram_dir" / f"{name}.json").write_text("{}", encoding="utf-8")
    make("order_demo_skill")
    make("order_demo_2_skill")
    monkeypatch.setattr(sea, "user_skills_root", lambda: tmp_path)
    monkeypatch.setattr(sea, "_is_lambda_runtime", lambda: False)
    agent = object.__new__(SkillEditorAgent)
    agent._last_saved_skill_name = None
    fg = Flowgram(nodes=[], edges=[], metadata={"skillName": "order_demo"})
    agent._keep_existing_skill(fg)
    assert fg.metadata["skillName"] == "order_demo_3"
    agent._last_saved_skill_name = "order_demo_3"     # regenerating in the same session saves over it
    make("order_demo_3_skill")
    agent._keep_existing_skill(fg)
    assert fg.metadata["skillName"] == "order_demo_3"


def test_the_generator_is_told_to_fill_templates_read_last_values_and_really_cancel():
    from agent.skill_editor import code_agent
    for prompt in (code_agent.CODE_GENERATION_PROMPT, code_agent.EDIT_FLOWGRAM_PROMPT):
        assert "fill EVERY required column" in prompt
        assert "a hard-coded starting value is wrong" in prompt
        assert "a message alone does not cancel anything" in prompt


def test_missing_details_are_guessed_and_emailed_not_a_stop():
    # A listing skill stopped at an unpublished draft for want of photos and specifics; the
    # generator must have it guess, publish, and email the owner a to-do list instead.
    from agent.skill_editor import code_agent, planner_agent
    for prompt in (code_agent.CODE_GENERATION_PROMPT, code_agent.EDIT_FLOWGRAM_PROMPT):
        assert "Missing details never block the main result" in prompt
        assert "owner_todo.json" in prompt
        assert "Store(DEFAULT_TENANT).kb_get(" in prompt
    assert "Missing details never block the main result" in open(planner_agent.__file__, encoding="utf-8").read()


def test_a_browser_profile_the_user_did_not_name_gets_the_named_one():
    from agent.skill_editor.code_agent import CodeAgent
    from agent.skill_editor.schemas import Flowgram, FlowgramNode
    fg = Flowgram(nodes=[
        FlowgramNode(id="browser_automation_a", type="browser_automation", config={"browserProfileId": "shop_0", "prompt": "x"}),
        FlowgramNode(id="loop_b", type="loop", blocks=[FlowgramNode(
            id="browser_automation_c", type="browser_automation", config={"browserProfileId": "supplier_0", "prompt": "profile supplier_0"})])],
        edges=[])
    object.__new__(CodeAgent)._fix_browser_profiles(fg, "use profile shop_0 for both sites")
    inner = fg.nodes[1].blocks[0]
    assert inner.config["browserProfileId"] == "shop_0" and inner.config["prompt"] == "profile shop_0"


def test_required_template_columns_are_reviewed_and_fixed():
    import asyncio
    import json as _json
    from agent.skill_editor.code_agent import CodeAgent
    from agent.skill_editor.schemas import Flowgram, FlowgramNode
    text = ("## LOCAL FILES (read on the user's computer):\n  Spreadsheet t1.xlsx:\n    sheet 'a':\n"
            "      row 1: *平台 | 订单号 | *收件人姓名 | *联系电话\n      row 3: X | 1 | *** | ***\n")
    assert CodeAgent._required_columns(text) == ["*平台", "*收件人姓名", "*联系电话"]
    new_code = "def main(state, *, runtime=None, store=None, **kwargs):\n    import openpyxl\n    return state\n"
    agent = object.__new__(CodeAgent)

    async def fake_llm(prompt, *, action=""):
        assert "*联系电话" in prompt
        return _json.dumps({"ok": False, "missing": ["*联系电话"], "fixes": [
            {"node_id": "code_w", "field": "code", "value": new_code},
            {"node_id": "browser_automation_r", "field": "prompt", "value": "also return phone"},
            {"node_id": "code_w", "field": "code", "value": "def broken(:"}]})

    async def no_progress(*a, **k):
        return None
    agent._invoke_llm_async = fake_llm
    agent._emit_progress = no_progress
    fg = Flowgram(nodes=[FlowgramNode(id="code_w", type="code", config={"code": "import openpyxl"}),
                         FlowgramNode(id="browser_automation_r", type="browser_automation", config={"prompt": "read order"})], edges=[])
    asyncio.run(agent._review_required_columns(fg, text))
    assert fg.nodes[0].config["code"] == new_code          # the fix that does not compile is skipped
    assert fg.nodes[1].config["prompt"] == "also return phone"


def test_a_file_writer_is_moved_after_the_step_that_decides_its_values():
    # The import sheet was written before the supplier-site step that picks the option names in it.
    import asyncio
    import json as _json
    from agent.skill_editor.code_agent import CodeAgent
    from agent.skill_editor.schemas import Flowgram, FlowgramNode, FlowgramEdge
    agent = object.__new__(CodeAgent)
    writer = "def main(state, *, runtime=None, store=None, **kwargs):\n    import openpyxl\n    return state\n"

    async def fake_llm(prompt, *, action=""):
        assert "ORDER" in prompt and "LAST NUMBER" in prompt and "ROWS" in prompt
        return _json.dumps({"ok": False, "problems": ["sheet written before design"],
                            "moves": [{"node_id": "code_xlsx", "after": "browser_automation_design"}],
                            "fixes": [{"node_id": "browser_automation_design", "field": "prompt", "value": "design; return names"}]})

    async def no_progress(*a, **k):
        return None
    agent._invoke_llm_async = fake_llm
    agent._emit_progress = no_progress
    body = [FlowgramNode(id="bs", type="block-start"),
            FlowgramNode(id="code_xlsx", type="code", config={"code": writer}, meta={"p": 1}),
            FlowgramNode(id="browser_automation_design", type="browser_automation", config={"prompt": "design"}, meta={"p": 2}),
            FlowgramNode(id="code_after", type="code", config={"code": "x"}),
            FlowgramNode(id="be", type="block-end")]
    chain = ["bs", "code_xlsx", "browser_automation_design", "code_after", "be"]
    loop = FlowgramNode(id="loop", type="loop", blocks=body,
                        edges=[FlowgramEdge(sourceNodeID=a, targetNodeID=b) for a, b in zip(chain, chain[1:])])
    fg = Flowgram(nodes=[FlowgramNode(id="start", type="start"), loop], edges=[FlowgramEdge(sourceNodeID="start", targetNodeID="loop")])
    asyncio.run(agent._review_file_writers(fg, "make the order sheet"))
    nxt = {e.sourceNodeID: e.targetNodeID for e in loop.edges}
    assert nxt == {"bs": "browser_automation_design", "browser_automation_design": "code_xlsx", "code_xlsx": "code_after", "code_after": "be"}
    assert [n.id for n in loop.blocks][1:3] == ["browser_automation_design", "code_xlsx"]
    assert loop.blocks[2].meta == {"p": 2} and loop.blocks[1].config["prompt"] == "design; return names"


def test_text_typed_next_to_a_listed_choice_is_kept():
    # "profile shop_0" typed next to the recommended choice was dropped, so the generator invented profiles.
    import asyncio
    agent = object.__new__(SkillEditorAgent)
    agent._pending_clarification = None
    agent._requirement_answers = {}

    async def stop(*a, **k):
        raise StopIteration
    agent._emit_progress = stop
    agent._generate_workflow_description = stop
    agent._classified_domain = "need_info"
    try:
        asyncio.run(agent._handle_requirement_responses({"q3": ["c1"], "freeform_q3": ["profile shop_0"]}, None, None, None))
    except (StopIteration, RuntimeError, AttributeError):
        pass
    assert "note: profile shop_0" in sum(agent._requirement_answers.values(), [])


def test_a_condition_route_needs_one_target_and_a_test_per_branch():
    # A three-way route came out as two untested branches with two targets on one: it could
    # never reach its publish branch, because a status string in state['condition'] is truthy.
    from agent.skill_editor.code_agent import CodeAgent
    from agent.skill_editor.schemas import Flowgram, FlowgramEdge, FlowgramNode
    agent = object.__new__(CodeAgent)
    ids = ["start", "condition_route", "code_a", "code_b", "code_c", "end"]

    def flow(conds, ports):
        nodes = [FlowgramNode(id=i, type=i.split("_")[0], config={"conditions": conds} if i == "condition_route" else {})
                 for i in ids]
        edges = [FlowgramEdge(sourceNodeID="start", targetNodeID="condition_route")]
        edges += [FlowgramEdge(sourceNodeID="condition_route", targetNodeID=t, sourcePortID=p) for t, p in ports]
        return Flowgram(nodes=nodes, edges=edges)

    def errors(fg):
        out = []
        agent._check_compiler_contract(fg, out)
        return [e.message for e in out]

    bad = flow([{"key": "if_branch", "value": {}}, {"key": "else_branch", "value": {}}],
               [("code_a", "if_branch"), ("code_c", "if_branch"), ("code_b", "else_branch")])
    assert any("leads to 2 nodes" in m for m in errors(bad))
    untested = flow([{"key": "if_a", "value": {}}, {"key": "elseif_c", "value": {}}, {"key": "else_b", "value": {}}],
                    [("code_a", "if_a"), ("code_c", "elseif_c"), ("code_b", "else_b")])
    assert any("have no test" in m for m in errors(untested))
    t = lambda v: {"mode": "custom", "expr": f"state.get('attributes', {{}}).get('s') == '{v}'"}
    good = flow([{"key": "if_a", "value": t("A")}, {"key": "elseif_c", "value": t("C")}, {"key": "else_b", "value": {}}],
                [("code_a", "if_a"), ("code_c", "elseif_c"), ("code_b", "else_b")])
    assert errors(good) == []


def test_an_unconnected_branch_target_gets_its_own_elseif():
    # The validator hung a node with no incoming edge on the condition's first, used branch.
    from agent.skill_editor.validator_agent import ValidatorAgent
    v = object.__new__(ValidatorAgent)
    cond = {"id": "condition_route", "type": "condition",
            "data": {"conditions": [{"key": "if_branch", "value": {}}, {"key": "else_branch", "value": {}}]}}
    data = {"nodes": [{"id": "start", "type": "start"}, {"id": "code_x", "type": "code"}, cond,
                      {"id": "code_c", "type": "code"}, {"id": "code_a", "type": "code"},
                      {"id": "code_b", "type": "code"}, {"id": "end", "type": "end"}],
            "edges": [{"sourceNodeID": "start", "targetNodeID": "code_x"},
                      {"sourceNodeID": "code_x", "targetNodeID": "condition_route"},
                      {"sourceNodeID": "condition_route", "targetNodeID": "code_a", "sourcePortID": "if_branch"},
                      {"sourceNodeID": "condition_route", "targetNodeID": "code_b", "sourcePortID": "else_branch"},
                      {"sourceNodeID": "code_a", "targetNodeID": "end"}, {"sourceNodeID": "code_b", "targetNodeID": "end"},
                      {"sourceNodeID": "code_c", "targetNodeID": "end"}]}
    out = v.fix_disconnected_nodes(data)
    ports = {}
    for e in out["edges"]:
        if e["sourceNodeID"] == "condition_route":
            ports.setdefault(e.get("sourcePortID"), set()).add(e["targetNodeID"])
    assert all(len(t) == 1 for t in ports.values()), ports
    assert ports.get("elseif_1") == {"code_c"}
    keys = [c["key"] for c in next(n for n in out["nodes"] if n["id"] == "condition_route")["data"]["conditions"]]
    assert keys == ["if_branch", "elseif_1", "else_branch"]


def test_a_generated_three_way_condition_keeps_its_tests_and_targets():
    # The validator read branches from data only; a generated node keeps them in config, so a
    # three-way route came out as two empty branches and lost its middle target.
    from agent.skill_editor.code_agent import CodeAgent
    agent = object.__new__(CodeAgent)
    ex = lambda v: {"mode": "custom", "expr": f"state.get('attributes', {{}}).get('s') == '{v}'"}
    code = {"code": "def main(state, **k):\n    return state\n"}
    fg = {"nodes": [{"id": "start", "type": "start"}, {"id": "code_parse", "type": "code", "config": code},
                    {"id": "condition_sku", "type": "condition", "config": {"conditions": [
                        {"key": "if_blocked", "value": ex("B")}, {"key": "elseif_live", "value": ex("L")},
                        {"key": "else_publish", "value": {}}]}},
                    {"id": "code_revise", "type": "code", "config": code}, {"id": "code_publish", "type": "code", "config": code},
                    {"id": "code_report", "type": "code", "config": code}, {"id": "end", "type": "end"}],
          "edges": [{"source": "start", "target": "code_parse"}, {"source": "code_parse", "target": "condition_sku"},
                    {"source": "condition_sku", "target": "code_report", "source_handle": "if_blocked"},
                    {"source": "condition_sku", "target": "code_revise", "source_handle": "elseif_live"},
                    {"source": "condition_sku", "target": "code_publish", "source_handle": "else_publish"},
                    {"source": "code_revise", "target": "code_report"}, {"source": "code_publish", "target": "code_report"},
                    {"source": "code_report", "target": "end"}]}
    out = agent._parse_flowgram_from_response(json.dumps({"action": "generate_flowgram", "flowgram": fg}), task_context="x")["flowgram"]
    routes = {e.get("sourcePortID"): e.get("target") or e.get("targetNodeID")
              for e in out["edges"] if (e.get("source") or e.get("sourceNodeID")) == "condition_sku"}
    assert routes == {"if_branch": "code_report", "elseif_1": "code_revise", "else_branch": "code_publish"}
    conds = next(n for n in out["nodes"] if n["id"] == "condition_sku")["config"]["conditions"]
    assert conds[0]["value"] == ex("B") and conds[1]["value"] == ex("L")


def test_a_ui_shape_condition_keeps_its_branches_from_inputs_values():
    # The coder emitted the branches as data.inputsValues.conditions; the validator saw none and
    # replaced them with two empty defaults, leaving the publish step behind the revise step.
    from agent.skill_editor.code_agent import CodeAgent
    agent = object.__new__(CodeAgent)
    ex = lambda v: {"mode": "custom", "expr": f"state.get('attributes', {{}}).get('s') == '{v}'"}
    code = {"title": "c", "code": "def main(state, **k):\n    return state\n"}
    conds = [{"key": "if_blocked", "value": ex("B")}, {"key": "elseif_live", "value": ex("L")},
             {"key": "else_new", "value": {}}]
    fg = {"nodes": [{"id": "start", "type": "start"}, {"id": "code_load", "type": "code", "data": code},
                    {"id": "cond", "type": "condition",
                     "data": {"title": "cond", "inputsValues": {"conditions": {"type": "constant", "content": conds}}}},
                    {"id": "code_stop", "type": "code", "data": code}, {"id": "code_revise", "type": "code", "data": code},
                    {"id": "code_publish", "type": "code", "data": code}, {"id": "end", "type": "end"}],
          "edges": [{"sourceNodeID": "start", "targetNodeID": "code_load"}, {"sourceNodeID": "code_load", "targetNodeID": "cond"},
                    {"sourceNodeID": "cond", "targetNodeID": "code_stop", "sourcePortID": "if_blocked"},
                    {"sourceNodeID": "cond", "targetNodeID": "code_revise", "sourcePortID": "elseif_live"},
                    {"sourceNodeID": "cond", "targetNodeID": "code_publish", "sourcePortID": "else_new"},
                    {"sourceNodeID": "code_stop", "targetNodeID": "end"}, {"sourceNodeID": "code_revise", "targetNodeID": "end"},
                    {"sourceNodeID": "code_publish", "targetNodeID": "end"}]}
    out = agent._parse_flowgram_from_response(json.dumps({"action": "generate_flowgram", "flowgram": fg}), task_context="x")["flowgram"]
    routes = {e.get("sourcePortID"): e.get("targetNodeID") for e in out["edges"] if e.get("sourceNodeID") == "cond"}
    assert routes == {"if_branch": "code_stop", "elseif_1": "code_revise", "else_branch": "code_publish"}
    got = next(n for n in out["nodes"] if n["id"] == "cond")["data"]["conditions"]
    assert got[0]["value"] == ex("B") and got[1]["value"] == ex("L")


def test_a_store_record_named_in_a_request_is_described_by_its_layout(monkeypatch):
    # The coder read owner settings from a file path it made up and guessed the email key name.
    from agent.ec_skills.ecom import store as store_mod
    from agent.skill_editor.local_files import describe_local_files

    class FakeStore:
        def __init__(self, tenant):
            pass

        def kb_get(self, collection, key, version):
            return {"collection": collection, "key": key, "value": {"list_price": 59.99, "report_email": "a@b.c"}}
    monkeypatch.setattr(store_mod, "Store", FakeStore)
    text = describe_local_files(['ec_kb {"op":"get","collection":"owner_settings","key":"shop_0"}'])
    assert 'ec_kb owner_settings/shop_0' in text and '"report_email": str' in text and '"list_price": float' in text
    assert "a@b.c" not in text and "59.99" not in text


def test_browser_steps_wait_for_loading_pages_and_emails_report_the_result():
    # A lister quit on an editor still showing placeholders, then emailed "published".
    from agent.skill_editor.code_agent import CODE_GENERATION_PROMPT, EDIT_FLOWGRAM_PROMPT
    for prompt in (CODE_GENERATION_PROMPT, EDIT_FLOWGRAM_PROMPT):
        assert "A page still loading" in prompt and "never while there is still work" in prompt
        assert "never what the run set out to do" in prompt
        assert "still shows empty after two tries" in prompt and "flat shipping" in prompt
        assert "click_text(\"<its words>\")" in prompt and "never scroll down step after step" in prompt
        assert "never from a guess: an invented address" in prompt and "ship_from_zip" in prompt
        assert "item quantities, not listings" in prompt and "set quantity 1 on the owner's other" in prompt


def test_a_step_that_uploads_files_allows_them_first():
    # The lister named the right photo but upload_file refused it: no upload_files in prompt_refs.
    from agent.skill_editor.code_agent import CODE_GENERATION_PROMPT, EDIT_FLOWGRAM_PROMPT
    for prompt in (CODE_GENERATION_PROMPT, EDIT_FLOWGRAM_PROMPT):
        assert 'state.setdefault("prompt_refs", {})["upload_files"]' in prompt.format_map(__import__("collections").defaultdict(str))


def test_an_mcp_node_for_owner_settings_or_email_fails_generation():
    # Twice the coder read owner settings and sent the owner email by llm + mcp; the email
    # step then sent nothing because the llm found no recipient.
    from agent.skill_editor.code_agent import CodeAgent
    from agent.skill_editor.schemas import Flowgram
    agent = object.__new__(CodeAgent)
    nodes = [agent._parse_node(n, i) for i, n in enumerate([
        {"id": "mcp_get_owner_settings", "type": "mcp", "data": {"title": "mcp_get_owner_settings"}},
        {"id": "mcp_send_publish_email", "type": "mcp", "data": {"title": "mcp_send_publish_email"}},
        {"id": "mcp_web_search", "type": "mcp", "data": {"title": "mcp_web_search"}}])]
    errors = []
    agent._check_compiler_contract(Flowgram(nodes=nodes, edges=[], metadata={}), errors)
    flagged = {e.node_id for e in errors if "mcp node" in e.message}
    assert flagged == {"mcp_get_owner_settings", "mcp_send_publish_email"}
