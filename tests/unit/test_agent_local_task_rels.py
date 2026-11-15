"""An agent keeps the tasks given to it on this machine (agent_task_rels) even when
its record lists other tasks: one-offs and chat schedules were dropped at restart."""
from unittest.mock import patch

from agent import agent_converter as C
from agent.ec_agents import lazy_agent


def test_with_local_tasks_adds_only_missing_rows():
    record = [{"id": "t_daily", "name": "t_daily"}]
    local = [{"id": "t_daily", "name": "daily"}, {"id": "t_sched", "name": "ads schedule"}]
    assert C._with_local_tasks(record, local) == [record[0], local[1]]
    assert C._with_local_tasks([], local) == local
    assert C._with_local_tasks(record, []) == record


def test_lazy_task_ids_union_record_and_local():
    agent = {"id": "a1", "extra_data": '{"tasks": ["t_daily"]}'}
    with patch.object(C, "_relation_ids_from_local_db",
                      return_value=([], [{"id": "t_daily"}, {"id": "t_oneoff"}])):
        assert lazy_agent.agent_task_ids(agent, mainwin=None) == ["t_daily", "t_oneoff"]
    with patch.object(C, "_relation_ids_from_local_db", return_value=([], [])):
        assert lazy_agent.agent_task_ids(agent, mainwin=None) == ["t_daily"]
        assert lazy_agent.agent_task_ids({"id": "a2"}, mainwin=None) == []


def test_node_transfer_append_extends_the_state_list():
    """append keeps earlier passes: the patch replaces the list when merged back."""
    from agent.ec_tasks.resume import build_node_transfer_patch
    rules = {"n": {"mappings": [{"from": ["state.tool_result.b.final"], "to": [{"target": "state.prompt_refs.collected"}],
                                 "on_conflict": "append", "transform": "parse_json"}]}}
    state = {"tool_result": {"b": {"final": '{"phase": 2}'}}, "prompt_refs": {"collected": [{"phase": 1}]}}
    assert build_node_transfer_patch("n", state, rules)["prompt_refs"]["collected"] == [{"phase": 1}, {"phase": 2}]
    assert state["prompt_refs"]["collected"] == [{"phase": 1}]          # the state itself is not mutated
    assert build_node_transfer_patch("n", {"tool_result": state["tool_result"]}, rules)["prompt_refs"]["collected"] == [{"phase": 2}]
