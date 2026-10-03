"""A site whose chat lives on one page (拼多多) must never get a tab opened per
conversation: each extra chat tab logs the account in again and freezes the
store's page ("账户在别处登录")."""

import asyncio
import types
import unittest
from unittest import mock

from agent.ec_skills.node_runtime import frontdesk_dispatch as fd


class SingleChatPageTests(unittest.TestCase):
    def test_single_chat_page_site_reuses_its_tab(self):
        async def resolve(session):
            return "CHATTAB"
        bridge = types.SimpleNamespace(single_chat_page=True, resolve_tab_target_id=resolve)

        async def never(*a, **k):
            raise AssertionError("must not open a tab")
        with mock.patch.object(fd, "_live_chat_bridge", lambda: bridge), \
                mock.patch.object(fd, "_open_tab_for_session", never):
            tab = asyncio.run(fd._tab_for_item(object(), "https://mms/chat?r=1", "U1", {}, "PreDispatch"))
        self.assertEqual(tab, "CHATTAB")

    def test_other_sites_keep_per_conversation_tabs(self):
        async def opened(session, chat_url, session_id, opened_tabs, log_tag):
            return "NEWTAB"
        with mock.patch.object(fd, "_live_chat_bridge", lambda: types.SimpleNamespace()), \
                mock.patch.object(fd, "_open_tab_for_session", opened):
            tab = asyncio.run(fd._tab_for_item(object(), "u", "U1", {}, "PreDispatch"))
        self.assertEqual(tab, "NEWTAB")


if __name__ == "__main__":
    unittest.main()
