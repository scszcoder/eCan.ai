"""The compiler contract, as tests.

Each case is a defect the compiler accepts in silence and then does not run —
which is how 339 dead nodes reached the skill corpus without anyone noticing.
The two negative cases matter as much as the positive ones: the agent's internal
node names must NOT trip the gate, because they are translated on the way out.
"""

import pytest

from agent.skill_editor.code_agent import CodeAgent
from agent.skill_editor.schemas import Flowgram, FlowgramNode, to_compiler_type


def findings(*nodes):
    gate = CodeAgent.__new__(CodeAgent)  # no LLM needed for a pure check
    errors = []
    gate._check_compiler_contract(Flowgram(nodes=list(nodes), edges=[]), errors)
    return errors


def fields(errors):
    return {e.field for e in errors}


def test_unknown_node_type_is_an_error():
    errors = findings(FlowgramNode(id="x_1", type="screenshot"))
    assert "type" in fields(errors)
    assert "executes nothing" in errors[0].message


@pytest.mark.parametrize("internal,emitted", [
    ("browser_automation", "browser-automation"),
    ("pend_event", "pend_event_node"),
    ("mcp_tool", "mcp"),
])
def test_internal_names_translate_and_do_not_trip_the_gate(internal, emitted):
    assert to_compiler_type(internal) == emitted
    assert findings(FlowgramNode(id=f"{internal}_a", type=internal)) == []


def test_loop_subscripting_state_is_an_error():
    errors = findings(FlowgramNode(
        id="loop_1", type="loop",
        config={"loopWhileExpr": 'not state["result"]["llm_result"]["all_done"]'},
        blocks=[FlowgramNode(id="block_start_1", type="block-start"),
                FlowgramNode(id="block_end_1", type="block-end")]))
    assert "loopWhileExpr" in fields(errors)
    assert "KeyError" in errors[0].message


def test_loop_with_get_defaults_is_accepted():
    assert findings(FlowgramNode(
        id="loop_2", type="loop",
        config={"loopWhileExpr": 'not state.get("result", {}).get("llm_result", {}).get("all_done", False)'},
        blocks=[FlowgramNode(id="block_start_2", type="block-start"),
                FlowgramNode(id="block_end_2", type="block-end")])) == []


def test_loop_body_needs_block_start_and_end():
    errors = findings(FlowgramNode(
        id="loop_3", type="loop", config={},
        blocks=[FlowgramNode(id="llm_x", type="llm")]))
    assert "blocks" in fields(errors)


def test_llm_must_not_pin_openai_or_carry_a_key():
    errors = findings(FlowgramNode(
        id="llm_1", type="llm",
        config={"apiHost": "https://api.openai.com/v1", "apiKey": "sk-live-abc123"}))
    assert {"apiHost", "apiKey"} <= fields(errors)


def test_the_walk_reaches_nodes_inside_a_loop_body():
    # The dead node types all lived inside loops; a top-level-only check walked
    # straight past them.
    errors = findings(FlowgramNode(
        id="loop_4", type="loop", config={},
        blocks=[FlowgramNode(id="block_start_4", type="block-start"),
                FlowgramNode(id="bogus_1", type="screen_scrape"),
                FlowgramNode(id="block_end_4", type="block-end")]))
    assert "type" in fields(errors)
    assert any("bogus_1" == e.node_id for e in errors)
