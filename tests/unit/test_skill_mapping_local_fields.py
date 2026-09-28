"""need_inputs / objectives are local copies lifted out of config (skill_model.to_dict);
the cloud's SkillUpdateInput has no such fields, so sending them failed every skill
update with GRAPHQL_VALIDATION_FAILED (2026-09-28). They must stay inside config only."""

from agent.cloud_api.constants import DataType
from agent.cloud_api.schema_registry import get_schema_registry


def test_lifted_fields_ride_in_config_only():
    schema = get_schema_registry().get_schema(DataType.SKILL)
    local = {"id": "skill_x", "name": "t",
             "config": {"need_inputs": [{"name": "p"}], "objectives": ["o"]},
             "need_inputs": [{"name": "p"}], "objectives": ["o"]}
    for op in ("add", "update"):
        out = schema.to_cloud(dict(local), operation=op)
        assert "need_inputs" not in out and "objectives" not in out
        assert "need_inputs" in str(out["config"]) and "objectives" in str(out["config"])
