"""A profile keeps its sign-in across a full close, as an anti-detect browser's
does. Sites like eBay keep it in session-only cookies, which Chromium keeps only
when it restores the last session AND is closed through CDP Browser.close."""
from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser as fb


def test_every_launch_restores_the_last_session():
    assert "--restore-last-session" in fb._BASE_FLAGS


def test_close_goes_through_browser_close_not_the_tabs(monkeypatch):
    br = fb.LaunchedBrowser(profile_id="p", user_data_dir="x", debug_port=9, cdp_url="http://127.0.0.1:9")
    monkeypatch.setattr(fb, "_RUNNING", {"p": br})
    asked = []
    monkeypatch.setattr(fb, "_browser_close", lambda url: asked.append(url) or True)
    monkeypatch.setattr(fb, "_cdp_version", lambda port, timeout=1.0: None)    # exited
    monkeypatch.setattr(fb, "_clear_port_file", lambda udd: None)
    opened = []
    monkeypatch.setattr(fb.urllib.request, "urlopen", lambda *a, **k: opened.append(a[0]))

    assert fb.close_profile("p") is True
    assert asked == ["http://127.0.0.1:9"]
    assert opened == [], "tabs closed one by one would drop the session cookies"


def test_close_falls_back_to_the_tabs_when_browser_close_cannot_be_sent(monkeypatch):
    br = fb.LaunchedBrowser(profile_id="p", user_data_dir="x", debug_port=9, cdp_url="http://127.0.0.1:9")
    monkeypatch.setattr(fb, "_RUNNING", {"p": br})
    monkeypatch.setattr(fb, "_browser_close", lambda url: False)
    monkeypatch.setattr(fb, "_cdp_version", lambda port, timeout=1.0: None)
    monkeypatch.setattr(fb, "_clear_port_file", lambda udd: None)
    opened = []
    monkeypatch.setattr(fb.urllib.request, "urlopen", lambda *a, **k: opened.append(a[0]) or (_ for _ in ()).throw(OSError()))

    fb.close_profile("p")
    assert opened == ["http://127.0.0.1:9/json/list"]
