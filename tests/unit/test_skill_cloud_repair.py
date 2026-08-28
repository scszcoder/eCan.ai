"""Tests for the cloud→local skill field repair (out-of-sync fix 2026-08-23).

Local skill rows were observed OWNERLESS (owner='' + public/rentable=0)
while the cloud row carried the correct owner and store flags; the
get_agent_skills merge skipped already-local ids entirely, so the rows
never healed and stayed invisible in the GUI (My Skills filters
owner === username). `_repair_local_skill_from_cloud` backfills the
missing fields without ever overwriting real local values.
"""

from unittest.mock import MagicMock, patch

import pytest

import gui.ipc.w2p_handlers.skill_handler as sh


@pytest.fixture
def services():
    skill_service = MagicMock()
    skill_service.update_skill.return_value = {"success": True}
    with patch.object(sh, "_get_skill_service", return_value=skill_service), \
         patch.object(sh, "_update_skill_in_memory", return_value=True) as mem:
        yield skill_service, mem


class TestRepairLocalSkillFromCloud:
    def test_ownerless_local_row_repaired(self, services):
        """The observed incident: local owner='' public=0 rentable=0, cloud
        carries owner + flags (public/rentable/¥0 store skill)."""
        skill_service, mem = services
        local = {"id": "skill_71209937ed7449bf", "name": "飞鸽客服前台00",
                 "owner": "", "public": 0, "rentable": 0}
        cloud = {"id": "skill_71209937ed7449bf", "name": "飞鸽客服前台00",
                 "owner": "wechat_b603a407904569a4ea88f9ac",
                 "public": True, "rentable": True, "price": 0}

        assert sh._repair_local_skill_from_cloud(local, cloud) is True
        assert local["owner"] == "wechat_b603a407904569a4ea88f9ac"
        assert local["public"] is True and local["rentable"] is True

        db_fields = skill_service.update_skill.call_args.args[1]
        assert db_fields == {"owner": "wechat_b603a407904569a4ea88f9ac",
                             "public": True, "rentable": True}
        mem.assert_called_once()

    def test_stale_owner_corrected_from_own_cloud_row(self, services):
        """The second observed incident: the skill file twin carried the
        owner of a PREVIOUS login account (intl email) after migrating to a
        CN WeChat identity — non-empty but wrong, so the GUI still hid the
        skill. The caller only reaches the helper for the current user's
        own cloud rows, so the cloud owner is authoritative."""
        skill_service, _ = services
        local = {"id": "skill_71209937ed7449bf", "name": "飞鸽客服前台00",
                 "owner": "songc@yahoo.com"}
        cloud = {"id": "skill_71209937ed7449bf", "name": "飞鸽客服前台00",
                 "owner": "wechat_b603a407904569a4ea88f9ac"}

        assert sh._repair_local_skill_from_cloud(local, cloud) is True
        assert local["owner"] == "wechat_b603a407904569a4ea88f9ac"

    def test_matching_owner_and_flags_untouched(self, services):
        """Same owner (case-insensitive) and real flag values → no repair;
        a cloud public=False never downgrades a local public=True."""
        skill_service, _ = services
        local = {"id": "s1", "name": "n", "owner": "Me@X", "public": True, "rentable": False}
        cloud = {"id": "s1", "name": "n", "owner": "me@x", "public": False, "rentable": False}

        assert sh._repair_local_skill_from_cloud(local, cloud) is False
        assert local["owner"] == "Me@X" and local["public"] is True
        skill_service.update_skill.assert_not_called()

    def test_no_repair_when_cloud_also_empty(self, services):
        skill_service, _ = services
        local = {"id": "s1", "name": "n", "owner": "", "public": 0}
        cloud = {"id": "s1", "name": "n", "owner": "", "public": None}

        assert sh._repair_local_skill_from_cloud(local, cloud) is False
        skill_service.update_skill.assert_not_called()

    def test_db_failure_still_patches_response_dict(self, services):
        """A DB write failure must not lose the repair for THIS response —
        the GUI list should still show the healed owner."""
        skill_service, _ = services
        skill_service.update_skill.return_value = {"success": False, "error": "locked"}
        local = {"id": "s1", "name": "n", "owner": ""}
        cloud = {"id": "s1", "name": "n", "owner": "me@x"}

        assert sh._repair_local_skill_from_cloud(local, cloud) is True
        assert local["owner"] == "me@x"

    def test_price_zero_cloud_not_treated_as_value(self, services):
        """price=0 on the cloud row is falsy — must not trigger a pointless
        repair write on its own."""
        skill_service, _ = services
        local = {"id": "s1", "name": "n", "owner": "me@x", "price": 0}
        cloud = {"id": "s1", "name": "n", "owner": "me@x", "price": 0}

        assert sh._repair_local_skill_from_cloud(local, cloud) is False
        skill_service.update_skill.assert_not_called()
