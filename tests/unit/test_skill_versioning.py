"""Save-timestamp skill versioning + read-only gate (2026-08-26).

Skills carry ``version`` = UTC save timestamp ``yymmddHHMMSSmmm`` (15
digits). Comparison is plain string order; legacy semver placeholders
("1.0.0") sort older than any timestamp. Non-owned (subscribed) skills
are READ ONLY — the save handler rejects them; subscribers get newer
versions via the store's Update button (re-subscribe refresh).
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from utils.skill_version import (
    CLOUD_NEWER,
    LOCAL_NEWER,
    SAME,
    UNKNOWN,
    compare_skill_versions,
    is_timestamp_version,
    new_skill_version,
)
import gui.ipc.w2p_handlers.skill_handler as sh


AUTHOR = "wechat_b603a407904569a4ea88f9ac"
CUSTOMER = "1050588178@qq.com"


class TestNewSkillVersion:
    def test_format_is_15_digits(self):
        v = new_skill_version()
        assert re.fullmatch(r"\d{15}", v)
        assert is_timestamp_version(v)

    def test_monotonic_same_millisecond(self):
        a = new_skill_version()
        b = new_skill_version(a)
        assert b > a

    def test_monotonic_against_future_prev(self):
        # Clock went backwards (prev stamped by a fast clock): still advances.
        future = "991231235959999"
        assert new_skill_version(future) == "991231235960000"

    def test_legacy_prev_ignored(self):
        v = new_skill_version("1.0.0")
        assert is_timestamp_version(v)


class TestCompareSkillVersions:
    def test_timestamp_pair(self):
        assert compare_skill_versions("260826010101000", "260826010101001") == CLOUD_NEWER
        assert compare_skill_versions("260826010101002", "260826010101001") == LOCAL_NEWER
        assert compare_skill_versions("260826010101001", "260826010101001") == SAME

    def test_timestamp_beats_legacy(self):
        assert compare_skill_versions("1.0.0", "260826010101000") == CLOUD_NEWER
        assert compare_skill_versions("260826010101000", "1.0.0") == LOCAL_NEWER

    def test_legacy_pair(self):
        assert compare_skill_versions("1.0.0", "1.0.0") == SAME
        assert compare_skill_versions("1.0.0", "2.0.0") == UNKNOWN
        assert compare_skill_versions("", None) == SAME


class TestStampDiagramVersion:
    def test_dict_diagram(self):
        info = {"diagram": {"skillName": "x", "version": "1.0"}}
        sh._stamp_diagram_version(info, "260826010101000")
        assert info["diagram"]["version"] == "260826010101000"

    def test_json_string_diagram(self):
        import json
        info = {"diagram": '{"skillName": "x", "version": "1.0"}'}
        sh._stamp_diagram_version(info, "260826010101000")
        assert json.loads(info["diagram"])["version"] == "260826010101000"

    def test_garbage_diagram_no_raise(self):
        info = {"diagram": "not json"}
        sh._stamp_diagram_version(info, "260826010101000")  # must not raise


class TestSaveReadOnlyGate:
    """save_agent_skill rejects skills owned by another author."""

    def _call_save(self, row_owner, saver_user=CUSTOMER):
        service = MagicMock()
        service.get_skill_by_id.return_value = {
            "success": True,
            "data": {"id": "skill_x", "name": "n", "owner": row_owner, "version": "1.0.0"},
        }
        captured = {}
        with patch.object(sh, "resolve_username", return_value=saver_user), \
             patch.object(sh, "_get_skill_service", return_value=service), \
             patch.object(sh, "get_handler_context", return_value=None), \
             patch.object(sh, "create_error_response",
                          side_effect=lambda req, code, msg: {"error": code, "message": msg}), \
             patch.object(sh, "create_success_response",
                          side_effect=lambda req, data: {"success": True, **data}):
            resp = sh.handle_save_agent_skill(
                MagicMock(), {"username": saver_user,
                              "skill_info": {"id": "skill_x", "name": "n", "public": True}}
            )
        return resp, service

    def test_non_owned_skill_rejected(self):
        resp, service = self._call_save(row_owner=AUTHOR)
        assert resp["error"] == "SKILL_READ_ONLY"
        service.update_skill.assert_not_called()
        service.add_skill.assert_not_called()

    def test_owner_case_insensitive(self):
        resp, _ = self._call_save(row_owner=CUSTOMER.upper())
        assert "error" not in resp or resp.get("error") != "SKILL_READ_ONLY"

    def test_own_skill_saved_with_stamped_version(self):
        resp, service = self._call_save(row_owner=CUSTOMER)
        assert service.update_skill.called
        saved = service.update_skill.call_args.args[1]
        assert is_timestamp_version(saved["version"])

    def test_ownerless_row_still_saves(self):
        # Legacy ownerless rows are treated as the saver's own (repair path).
        resp, service = self._call_save(row_owner="")
        assert service.update_skill.called


class TestStoreAnnotation:
    def _annotate(self, local_version, cloud_version):
        service = MagicMock()
        service.query_skills.return_value = {
            "success": True,
            "data": [{"id": "skill_a", "askid": "0", "owner": AUTHOR, "version": local_version}],
        }
        rows = [{"id": "skill_a", "owner": AUTHOR, "version": cloud_version}]
        with patch.object(sh, "_get_skill_service", return_value=service):
            sh._annotate_store_rows_with_local_versions(rows)
        return rows[0]

    def test_cloud_newer_marks_update_available(self):
        row = self._annotate("260826010101000", "260826020202000")
        assert row["update_available"] is True
        assert row["local_version"] == "260826010101000"

    def test_same_version_no_flag(self):
        row = self._annotate("260826010101000", "260826010101000")
        assert "update_available" not in row

    def test_legacy_local_timestamp_cloud_is_update(self):
        # Author republished with the new scheme; subscriber still on "1.0.0".
        row = self._annotate("1.0.0", "260826010101000")
        assert row["update_available"] is True

    def test_row_without_local_copy_untouched(self):
        service = MagicMock()
        service.query_skills.return_value = {"success": True, "data": []}
        rows = [{"id": "skill_b", "version": "260826010101000"}]
        with patch.object(sh, "_get_skill_service", return_value=service):
            sh._annotate_store_rows_with_local_versions(rows)
        assert "update_available" not in rows[0] and "local_version" not in rows[0]
