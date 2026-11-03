"""A browser session whose tab list went blank is refilled over its own
connection: the throwaway-client rediscovery left a 抖店 listing run with 5 tabs
in Chrome and none in the session (KEN 2026-10-29), so every run failed its
focus preflight until eCan restarted."""
import asyncio
from types import SimpleNamespace

from agent.ec_skills.browser_node.runner import reattach_session_targets, run_cdp_focus_preflight

PAGE = SimpleNamespace(target_type="page", url="https://fxg.jinritemai.com/ffa/g/create")


class _Manager:
    def __init__(self, refill=None, fail=False):
        self.targets, self.refill, self.fail = {}, refill or {}, fail

    def get_all_targets(self):
        return self.targets

    async def _initialize_existing_targets(self):
        if self.fail:
            raise ConnectionError("root websocket closed")
        self.targets = dict(self.refill)


class _Session:
    cdp_url = None
    agent_focus_target_id = None

    def __init__(self, manager, after_connect=None):
        self.session_manager, self.after_connect, self.connected = manager, after_connect, 0
        self.switched = []
        self.event_bus = SimpleNamespace(dispatch=self._dispatch)

    async def _dispatch(self, event):
        self.switched.append(event.target_id)

    async def get_browser_state_summary(self, **_):
        return None

    async def connect(self):
        self.connected += 1
        self.session_manager = self.after_connect


def test_tabs_come_back_over_the_sessions_own_connection():
    s = _Session(_Manager(refill={"T1": PAGE}))
    assert asyncio.run(reattach_session_targets(s)) is True and s.connected == 0


def test_a_dead_connection_is_reconnected():
    fresh = _Manager(); fresh.targets = {"T1": PAGE}
    s = _Session(_Manager(fail=True), after_connect=fresh)
    assert asyncio.run(reattach_session_targets(s)) is True and s.connected == 1


def test_no_tabs_anywhere_stays_false():
    assert asyncio.run(reattach_session_targets(_Session(_Manager()))) is False


def test_preflight_recovers_instead_of_failing():
    s = _Session(_Manager(refill={"T1": PAGE}))
    focus = asyncio.run(run_cdp_focus_preflight(s, last_known_focus_target_id=None, assignment_tab_id="",
                                            assignment_chat_url="", skill_name="抖店商品上架", node_name="browser_publish",
                                            any_page_ok=True))[0]
    assert focus == "T1" and s.switched == ["T1"]
