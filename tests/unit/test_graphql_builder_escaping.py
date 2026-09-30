"""GraphQL literals from graphql_builder must survive quotes, newlines and
nested lists/dicts (2026-09-30: every task.add failed GRAPHQL_PARSE_FAILED --
a task carried its full `skills` list, formatted as a Python repr)."""

import json

from agent.cloud_api.constants import DataType, Operation
from agent.cloud_api.graphql_builder import GraphQLBuilder, build_mutation


def test_string_literal_round_trips():
    fmt = GraphQLBuilder()._format_graphql_value
    for s in ['plain', 'a "quoted" word', 'back\\slash', 'line1\nline2\ttab', '中文 "引号"']:
        assert json.loads(fmt(s)) == s
        assert '\n' not in fmt(s)


def test_list_and_dict_go_as_json_strings():
    fmt = GraphQLBuilder()._format_graphql_value
    value = [{'code': 'state.get("result", {}).get("k")'}, "]["]
    assert json.loads(json.loads(fmt(value))) == value


def test_task_add_sends_only_task_input_fields():
    task = {"id": "t1", "name": "拼多多客服前台001", "status": "pending",
            "skills": [{"id": "s1", "diagram": '{"nodes": []}'}], "skill_ids": ["s1"],
            "ext": {"x": 1}, "created_at": "2026-09-30T00:00:00", "updated_at": "2026-09-30T00:00:00",
            "description": 'multi\nline "desc"'}
    m = build_mutation(DataType.TASK, Operation.ADD, [task])
    for field in ("skills:", "skill_ids:", "ext:", "created_at:", "updated_at:"):
        assert field not in m
    assert 'description: "multi\\nline \\"desc\\""' in m
