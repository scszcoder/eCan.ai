"""A reused browser-use agent must not carry the last run into the next one.

browser-use turns state.last_model_output / last_result into the first history
item of the next step, so with only the message history wiped a new publish
run started believing it was at "Step 148/150" of the previous one and gave up
within a minute (KEN 2026-10-28, both stores)."""
from types import SimpleNamespace

from agent.ec_skills.browser_node.agent import reset_bu_agent_for_next_round


def _agent():
    mm_state = SimpleNamespace(context_messages=[], agent_history_items=["old step"], compacted_memory="old",
                               read_state_description="old read", read_state_images=[{"x": 1}],
                               compaction_count=3, last_compaction_step=140)
    state = SimpleNamespace(n_steps=149, consecutive_failures=2, stopped=True,
                            last_model_output="Step 148/150 memory", last_result=["done: failed"],
                            plan=["old plan"], current_plan_item_index=4, plan_generation_step=12)
    return SimpleNamespace(task="old", message_manager=SimpleNamespace(task="old", state=mm_state),
                           state=state, history=SimpleNamespace(history=["h"]))


def test_clear_mode_forgets_the_last_run():
    a = _agent()
    reset_bu_agent_for_next_round(a, "clear", "new task")
    st, mm = a.state, a.message_manager.state
    assert (st.last_model_output, st.last_result, st.plan) == (None, None, None)
    assert (st.current_plan_item_index, st.plan_generation_step, st.n_steps) == (0, None, 1)
    assert mm.agent_history_items == [] and mm.compacted_memory is None
    assert (mm.read_state_description, mm.read_state_images, mm.compaction_count) == ("", [], 0)
    assert a.history.history == [] and a.message_manager.task == "new task"


def test_accumulate_mode_keeps_the_last_step():
    a = _agent()
    reset_bu_agent_for_next_round(a, "accumulate", "new task")
    assert a.state.last_model_output == "Step 148/150 memory"
    assert a.message_manager.state.agent_history_items == ["old step"]
