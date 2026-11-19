"""The rule-based intent shortcut keeps load/save for short commands only
(agent/skill_editor/skill_editor_agent.py; 2026-11-18: a skill spec containing
"upload" and "skill" was answered "which skill to load?")."""
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
