"""Detection-tab marker (event_monitor).

2026-08-28 customer incident: the browser outlived an app restart, and the new
session's browser-use reattach adopted the PREVIOUS session's dedicated
detection tab as the agent's main tab. That workspace instance never renders
the conversation list, so every DOM detection path saw rows=0/total=0 for the
whole session while the real logged-in tab sat unused.

Detection tabs are now stamped with the ``#ecan_det`` URL fragment at creation;
these tests pin that monitor-target resolution never adopts a marked tab.
"""

from agent.ec_skills.browser_use_extension import event_monitor as em

WS = "https://im.jinritemai.com/pc_seller_v2/main/workspace"


class _Target:
    def __init__(self, url, ttype="page"):
        self.url = url
        self.target_type = ttype


class _SM:
    def __init__(self, targets):
        self._t = targets

    def get_all_targets(self):
        return self._t

    def get_target(self, tid):
        return self._t.get(tid)


class _Session:
    def __init__(self, focus, targets):
        self.agent_focus_target_id = focus
        self.session_manager = _SM(targets)


class _Cfg:
    label = "新消息"


def _targets():
    return {"MAIN": _Target(WS), "STALE_DET": _Target(WS + "#ecan_det")}


def test_marked_url_recognized():
    assert em._is_detection_tab_url(WS + "#ecan_det")
    assert not em._is_detection_tab_url(WS)


def test_focus_on_stale_detection_tab_resolves_real_tab():
    session = _Session("STALE_DET", _targets())
    assert em._resolve_monitor_target_id(session, _Cfg(), {"page_url_patterns": []}) == "MAIN"


def test_focus_on_main_tab_unchanged():
    session = _Session("MAIN", _targets())
    assert em._resolve_monitor_target_id(session, _Cfg(), {"page_url_patterns": []}) == "MAIN"


def test_live_matcher_rejects_marked_target_info():
    assert not em._target_info_matches_patterns({"type": "page", "url": WS + "#ecan_det"}, [])
    assert em._target_info_matches_patterns({"type": "page", "url": WS}, [])


def test_chat_message_added_focus_skips_marked_tab():
    class _ChatCfg:
        label = "chat_message_added"

    session = _Session("STALE_DET", _targets())
    assert em._resolve_monitor_target_id(session, _ChatCfg(), {"page_url_patterns": []}) == "MAIN"
