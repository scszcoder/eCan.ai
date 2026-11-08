"""store_page.backoffice_tabs: a 天猫 store's chores read its 千牛 back office in the
store's own browser, started when nothing keeps it open (its 客服 is the desktop app)."""
from types import SimpleNamespace
from unittest.mock import patch

from agent.ec_skills.browser_use_extension import store_page


class _Resp:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self.body


def test_a_closed_store_browser_is_started_and_any_page_used():
    pages = b'[{"type": "page", "url": "about:blank", "webSocketDebuggerUrl": "ws://127.0.0.1:61000/devtools/page/A"}]'
    with patch.object(store_page, "store_tabs", return_value=[]), \
         patch("agent.ec_skills.explorer.page.browser_port", return_value=0), \
         patch("agent.ec_skills.explorer.page.store_profiles", return_value=[{"id": "tmall-x-login"}]), \
         patch("agent.ec_skills.browser_use_extension.fingerprint.fingerprint_browser.launch_profile",
               return_value=SimpleNamespace(debug_port=61000)) as launch, \
         patch("urllib.request.urlopen", return_value=_Resp(pages)):
        tabs = store_page.backoffice_tabs("tmall", "tmall-小店三号")
    launch.assert_called_once_with("tmall-x-login")
    assert tabs == [{"profile": "tmall-x-login", "store_id": "tmall-小店三号", "ws": "ws://127.0.0.1:61000/devtools/page/A"}]


def test_an_open_back_office_tab_is_used_as_is():
    tab = {"profile": "p", "store_id": "s", "ws": "ws://x"}
    with patch.object(store_page, "store_tabs", return_value=[tab]), \
         patch("agent.ec_skills.browser_use_extension.fingerprint.fingerprint_browser.launch_profile") as launch:
        assert store_page.backoffice_tabs("tmall", "s") == [tab]
    launch.assert_not_called()
