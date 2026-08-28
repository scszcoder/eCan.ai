"""Startup skill pool must include SUBSCRIBED skills (v0.9.95s incident).

Subscribed rows keep the AUTHOR as owner, so the old owner-scoped startup
query (get_skills_by_owner) returned 0 rows on a customer machine —
问答00 never entered the compiled pool, agents/tasks converted against
stubs (runnable=False, "WILL FAIL"), and 8 Q&A tasks were dead until the
Skills page happened to backfill. The DB is per-user, so ALL its rows
belong in the pool.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import agent.ec_tasks  # noqa: F401  (import-order guard)
import agent.ec_skills.build_agent_skills as bas


AUTHOR = "wechat_b603a407904569a4ea88f9ac"
CUSTOMER = "1050588178@qq.com"


class TestStartupLoadsSubscribedRows:
    def _load(self, rows):
        service = MagicMock()
        service.query_skills.return_value = {"success": True, "data": rows}
        mainwin = MagicMock()
        with patch.object(bas, "_get_username", return_value=CUSTOMER), \
             patch.object(bas, "_get_skill_service", return_value=service):
            return asyncio.get_event_loop().run_until_complete(
                bas._load_skills_from_database_async(mainwin)), service

    def test_subscribed_rows_included(self):
        rows = [
            {"id": "skill_own", "name": "mine", "owner": CUSTOMER},
            {"id": "skill_4f24592c81894ae7", "name": "飞鸽客服问答00", "owner": AUTHOR,
             "source": "subscribed"},
        ]
        loaded, service = self._load(rows)
        assert len(loaded) == 2  # subscribed row NOT dropped
        service.query_skills.assert_called_once()  # all-rows query
        service.get_skills_by_owner.assert_not_called()  # owner-scoped query gone
