"""Phase B — chat and background work on two browsers, one store.

Both browsers hold the SAME seller login, and the platform pushes every
customer message to both (verified on a customer machine 2026-09-22). That
makes two failure modes possible, and they are not symmetric:

  loud   two observers -> every customer gets answered twice (ws190, but
         across browsers, where ws190's per-cdp_url ref-count cannot see it)
  silent the background browser opens the chat workstation page, the platform
         marks those conversations read, and the chat browser's unread-based
         detection goes blind while the customer waits

The silent one is the dangerous one, and it is *built into the current
deploy*: every task gets the same ``store_url`` in task_vars, and on this site
the store URL IS the chat workstation page.
"""

import os
import unittest
from unittest.mock import patch

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import ws_observer


STORE_A = "lands_flying_fish"
STORE_B = "second_shop"
CHAT_CDP = "http://127.0.0.1:9222"
BACKGROUND_CDP = "http://127.0.0.1:9333"


class _Registry:
    """Install a fake _SHARED_OBSERVERS for the duration of a test."""

    def __init__(self, entries):
        self.entries = entries

    def __enter__(self):
        self.saved = ws_observer._SHARED_OBSERVERS
        ws_observer._SHARED_OBSERVERS = dict(self.entries)

    def __exit__(self, *exc):
        ws_observer._SHARED_OBSERVERS = self.saved
        return False


def _entry(store_key, cdp_url, alive=True):
    return {"client": None, "dispatchers": [], "handles": set(),
            "alive": alive, "store_key": store_key, "cdp_url": cdp_url}


def _no_env(*names):
    """Remove env vars so ambient settings cannot change the verdict."""
    saved = {n: os.environ.pop(n, None) for n in names}

    class _Ctx:
        def __enter__(self_inner):
            return None

        def __exit__(self_inner, *exc):
            for n, v in saved.items():
                if v is not None:
                    os.environ[n] = v
            return False

    return _Ctx()


class OneChatBrowserPerStoreTests(unittest.TestCase):
    """The loud failure: a second observer answers every customer twice."""

    def test_first_browser_for_a_store_is_allowed(self):
        with _Registry({}), _no_env("ECAN_FEIGE_ONE_CHAT_BROWSER"):
            self.assertTrue(
                ws_observer._may_run_chat_dispatch(STORE_A, CHAT_CDP, "node")
            )

    def test_second_browser_for_the_same_store_is_refused(self):
        reg = {"k1": _entry(STORE_A, CHAT_CDP)}
        with _Registry(reg), _no_env("ECAN_FEIGE_ONE_CHAT_BROWSER"):
            self.assertFalse(
                ws_observer._may_run_chat_dispatch(STORE_A, BACKGROUND_CDP, "node")
            )

    def test_the_same_browser_is_still_allowed(self):
        # ws190 sharing must keep working: several sessions on ONE Chrome are
        # fine, they subscribe to one observer.
        reg = {"k1": _entry(STORE_A, CHAT_CDP)}
        with _Registry(reg), _no_env("ECAN_FEIGE_ONE_CHAT_BROWSER"):
            self.assertTrue(
                ws_observer._may_run_chat_dispatch(STORE_A, CHAT_CDP, "other-label")
            )

    def test_a_different_store_gets_its_own_browser(self):
        # THE case this must not break: store B's chat browser is not a
        # duplicate of store A's, and refusing it would take store B offline.
        reg = {"k1": _entry(STORE_A, CHAT_CDP)}
        with _Registry(reg), _no_env("ECAN_FEIGE_ONE_CHAT_BROWSER"):
            self.assertTrue(
                ws_observer._may_run_chat_dispatch(STORE_B, BACKGROUND_CDP, "node")
            )

    def test_unidentified_store_is_allowed_through(self):
        # A blank store key collapses every store into one bucket. Refusing
        # would take a legitimate second store offline -- a silent outage,
        # worse than the duplicate reply this guards against.
        reg = {"k1": _entry("", CHAT_CDP)}
        with _Registry(reg), _no_env("ECAN_FEIGE_ONE_CHAT_BROWSER"):
            self.assertTrue(
                ws_observer._may_run_chat_dispatch("", BACKGROUND_CDP, "node")
            )

    def test_a_dead_observer_does_not_block_the_replacement(self):
        # Chrome relaunches with a NEW ephemeral CDP port, so the replacement
        # browser has a different cdp_url. A stale claim would lock the store
        # out permanently.
        reg = {"k1": _entry(STORE_A, CHAT_CDP, alive=False)}
        with _Registry(reg), _no_env("ECAN_FEIGE_ONE_CHAT_BROWSER"):
            self.assertTrue(
                ws_observer._may_run_chat_dispatch(STORE_A, BACKGROUND_CDP, "node")
            )

    def test_kill_switch_allows_the_second_browser(self):
        reg = {"k1": _entry(STORE_A, CHAT_CDP)}
        with _Registry(reg), patch.dict(
            os.environ, {"ECAN_FEIGE_ONE_CHAT_BROWSER": "0"}, clear=False
        ):
            self.assertTrue(
                ws_observer._may_run_chat_dispatch(STORE_A, BACKGROUND_CDP, "node")
            )


class ChatBrowserLookupTests(unittest.TestCase):
    def test_reports_the_owning_endpoint(self):
        with _Registry({"k1": _entry(STORE_A, CHAT_CDP)}):
            self.assertEqual(ws_observer.chat_browser_cdp_url(STORE_A), CHAT_CDP)

    def test_no_opinion_for_an_unobserved_store(self):
        with _Registry({"k1": _entry(STORE_A, CHAT_CDP)}):
            self.assertEqual(ws_observer.chat_browser_cdp_url(STORE_B), "")

    def test_no_opinion_when_nothing_is_observing(self):
        with _Registry({}):
            self.assertEqual(ws_observer.chat_browser_cdp_url(STORE_A), "")

    def test_a_dead_entry_owns_nothing(self):
        with _Registry({"k1": _entry(STORE_A, CHAT_CDP, alive=False)}):
            self.assertEqual(ws_observer.chat_browser_cdp_url(STORE_A), "")


class _Session:
    def __init__(self, cdp_url):
        self.cdp_url = cdp_url


class _Bridge:
    def __init__(self, owner):
        self._owner = owner

    def chat_browser_cdp_url(self, store_key=""):
        return self._owner


class BackgroundChatPageGuardTests(unittest.TestCase):
    """The silent failure: the wrong browser opens the chat workstation page."""

    def setUp(self):
        from agent.ec_skills.browser_node import runner
        self.runner = runner
        # Every deployed task carries the same store_url, which on this site is
        # the chat workstation page -- that is exactly why the guard is needed.
        self.state = {
            "prompt_refs": {
                "store_id": STORE_A,
                "store_url": "https://im.jinritemai.com/pc_seller_v2/main/workspace",
            }
        }

    def _ask(self, session, owner):
        with patch(
            "agent.ec_skills.live_chat_dispatch.runner_bridge",
            return_value=_Bridge(owner),
        ):
            return self.runner._another_browser_owns_live_chat(session, self.state)

    def test_background_browser_sees_the_chat_owner(self):
        self.assertEqual(
            self._ask(_Session(BACKGROUND_CDP), CHAT_CDP), CHAT_CDP
        )

    def test_the_chat_browser_itself_is_not_blocked(self):
        self.assertEqual(self._ask(_Session(CHAT_CDP), CHAT_CDP), "")

    def test_no_owner_means_no_opinion(self):
        self.assertEqual(self._ask(_Session(BACKGROUND_CDP), ""), "")

    def test_a_session_without_a_known_endpoint_is_not_blocked(self):
        # Better to allow a session we cannot identify than to strand it.
        self.assertEqual(self._ask(_Session(""), CHAT_CDP), "")

    def test_no_bridge_loaded_means_no_opinion(self):
        # Any non-chat scenario: no site bundle, so nothing to protect.
        with patch(
            "agent.ec_skills.live_chat_dispatch.runner_bridge", return_value=None
        ):
            self.assertEqual(
                self.runner._another_browser_owns_live_chat(
                    _Session(BACKGROUND_CDP), self.state
                ),
                "",
            )

    def test_a_bridge_without_the_capability_means_no_opinion(self):
        # An older or unrelated site bundle must not break navigation.
        class _Bare:
            pass

        with patch(
            "agent.ec_skills.live_chat_dispatch.runner_bridge", return_value=_Bare()
        ):
            self.assertEqual(
                self.runner._another_browser_owns_live_chat(
                    _Session(BACKGROUND_CDP), self.state
                ),
                "",
            )

    def test_a_raising_bridge_never_breaks_navigation(self):
        class _Boom:
            def chat_browser_cdp_url(self, store_key=""):
                raise RuntimeError("bundle exploded")

        with patch(
            "agent.ec_skills.live_chat_dispatch.runner_bridge", return_value=_Boom()
        ):
            self.assertEqual(
                self.runner._another_browser_owns_live_chat(
                    _Session(BACKGROUND_CDP), self.state
                ),
                "",
            )


class PlatformPurityTests(unittest.TestCase):
    def test_the_runner_guard_names_no_site(self):
        from pathlib import Path
        src = Path("agent/ec_skills/browser_node/runner.py").read_text(encoding="utf-8")
        self.assertNotIn("feige", src.lower())
        # And it asks the bridge rather than importing the bundle.
        self.assertIn("chat_browser_cdp_url", src)

    def test_the_guard_is_applied_before_pre_navigation(self):
        from pathlib import Path
        src = Path("agent/ec_skills/browser_node/runner.py").read_text(encoding="utf-8")
        guard = src.index("_another_browser_owns_live_chat(browser_session, state)")
        nav = src.index("NavigateToUrlEvent(url=store_url, new_tab=False)")
        self.assertLess(guard, nav)


if __name__ == "__main__":
    unittest.main()
