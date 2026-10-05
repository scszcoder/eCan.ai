"""Saving a new skill as a WeChat user created TWO rows: one under the file's id
and the local owner (wechat_<openid>), one under a fresh DB id whose owner later
became the bare cloud openid. The bare-owner row also tripped the save handler's
read-only gate (owner != current user). 2026-10-04.

1. sync_skill_from_file (runs when write_skill_file writes the file, just before
   save_agent_skill) must insert under the file's skillId, so the editor's save
   updates that same row.
2. The cloud->local repair must store the LOCAL owner form, never copy the
   cloud's bare form into the row.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

import gui.ipc.w2p_handlers.skill_handler as sh

LOCAL = "wechat_o3YBk2dxaRe3LKqJXCf5z3PfvD5M"
CLOUD = "o3YBk2dxaRe3LKqJXCf5z3PfvD5M"


@pytest.fixture
def services():
    skill_service = MagicMock()
    skill_service.update_skill.return_value = {"success": True}
    with patch.object(sh, "_get_skill_service", return_value=skill_service), \
         patch.object(sh, "_update_skill_in_memory", return_value=True):
        yield skill_service


class TestOwnerRepairKeepsLocalForm:
    def test_empty_owner_gets_the_local_form_not_the_cloud_form(self, services):
        local = {"id": "skill_a", "name": "n", "owner": ""}
        cloud = {"id": "skill_a", "name": "n", "owner": CLOUD}
        assert sh._repair_local_skill_from_cloud(local, cloud, local_owner=LOCAL) is True
        assert local["owner"] == LOCAL
        assert services.update_skill.call_args.args[1]["owner"] == LOCAL

    def test_row_already_holding_the_cloud_form_is_healed(self, services):
        local = {"id": "skill_a", "name": "n", "owner": CLOUD}
        cloud = {"id": "skill_a", "name": "n", "owner": CLOUD}
        assert sh._repair_local_skill_from_cloud(local, cloud, local_owner=LOCAL) is True
        assert local["owner"] == LOCAL

    def test_correct_local_owner_untouched(self, services):
        local = {"id": "skill_a", "name": "n", "owner": LOCAL}
        cloud = {"id": "skill_a", "name": "n", "owner": CLOUD}
        assert sh._repair_local_skill_from_cloud(local, cloud, local_owner=LOCAL) is False
        services.update_skill.assert_not_called()


def test_first_file_sync_inserts_under_the_files_own_id(tmp_path, services):
    f = tmp_path / "x_skill.json"
    f.write_text(json.dumps({"skillId": "skill_03c970b03841b51c", "skillName": "x",
                             "workFlow": {"nodes": [], "edges": []}}), encoding="utf-8")
    services.get_skill_by_path.return_value = {"success": True, "data": None}
    services.get_skill_by_id.return_value = {"success": True, "data": None}
    services.add_skill.return_value = {"success": True, "id": "skill_03c970b03841b51c"}
    ctx = MagicMock()
    ctx.get_username.return_value = ""
    with patch.object(sh, "get_handler_context", return_value=ctx), \
         patch.object(sh, "is_code_skill", return_value=False), \
         patch.object(sh, "_trigger_cloud_sync"):
        out = sh.sync_skill_from_file(str(f))
    assert out.get("success"), out
    assert services.add_skill.call_args.args[0]["id"] == "skill_03c970b03841b51c"
