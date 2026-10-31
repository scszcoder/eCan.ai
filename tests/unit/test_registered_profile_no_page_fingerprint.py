"""A registered (signed-in) browser profile runs as launched: no page-level
fingerprint. The seller signs in to it unfaked, so faking another device only
while a skill drives it shows the site two machines behind one set of cookies;
eBay answered with a CAPTCHA and a forced password reset (2026-10-30)."""
from types import SimpleNamespace

from agent.ec_skills.browser_node import runner
from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg


def _browser_profile():
    return SimpleNamespace(user_agent=None, viewport=None, device_scale_factor=None, args=[], proxy=None)


def test_a_registered_profile_gets_no_fingerprint_even_with_the_stealth_box_ticked(monkeypatch):
    monkeypatch.setattr(reg, "get_profile", lambda pid: {"id": pid, "fingerprint_profile": "win_chrome_02"})
    bp = _browser_profile()
    fp = runner.apply_stealth_fingerprint(bp, {"enableStealth": True}, calling_agent_id="a",
                                          node_name="n", browser_profile_id="ebay_0")
    assert fp is None
    assert bp.user_agent is None and bp.viewport is None and bp.args == []


def test_an_unregistered_node_keeps_its_stealth_box(monkeypatch):
    monkeypatch.setattr(reg, "get_profile", lambda pid: None)
    fp = runner.apply_stealth_fingerprint(_browser_profile(), {"enableStealth": False},
                                          calling_agent_id="a", node_name="n", browser_profile_id="nope")
    assert fp is None
    assert runner._is_registered_profile("nope") is False
