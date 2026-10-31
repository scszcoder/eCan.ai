"""A proxied profile must not leak the real IP through WebRTC. Chrome ignores the
command-line switch, so the launch writes the profile's ``webrtc`` preference."""
import json

from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser as fb


def test_webrtc_is_kept_on_the_proxy_and_the_rest_of_the_prefs_survive(tmp_path):
    prefs = tmp_path / "Default" / "Preferences"
    prefs.parent.mkdir()
    prefs.write_text(json.dumps({"profile": {"name": "Seller"}, "webrtc": {"other": 1}}), encoding="utf-8")
    fb._keep_webrtc_on_proxy(tmp_path)
    saved = json.loads(prefs.read_text(encoding="utf-8"))
    assert saved["profile"] == {"name": "Seller"}
    assert saved["webrtc"] == {"other": 1, "ip_handling_policy": "disable_non_proxied_udp",
                               "multiple_routes_enabled": False, "nonproxied_udp_enabled": False}


def test_a_new_profile_gets_the_preference_before_its_first_launch(tmp_path):
    fb._keep_webrtc_on_proxy(tmp_path)
    saved = json.loads((tmp_path / "Default" / "Preferences").read_text(encoding="utf-8"))
    assert saved["webrtc"]["ip_handling_policy"] == "disable_non_proxied_udp"


def test_a_profile_without_a_proxy_gets_no_proxy_flags():
    assert fb._proxy_flags({"proxy": {}}) == ([], None, 0)


def test_the_relay_comes_back_on_the_port_the_browser_points_at(monkeypatch):
    """After an app restart the browser still says --proxy-server=127.0.0.1:<port>."""
    import socket
    monkeypatch.setattr(fb.registry, "get_proxy_password", lambda p: "pw")
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    profile = {"proxy": {"scheme": "socks5", "host": "p.example", "port": 1080, "username": "u"}}
    stop = fb._revive_relay(profile, port)
    try:
        assert stop is not None and fb._port_open(port)
    finally:
        stop and stop()
