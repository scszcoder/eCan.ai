"""Same-machine A2A dispatch must survive a LAN IP change.

2026-09-07 (customer AllOne-PC): all agents pinned to one host, but their
advertised A2A endpoints were frozen at the IP the box had at agent-creation
(192.168.10.100). A router/modem power-cycle moved the box to 192.168.10.102,
so every front-desk->QA send hit the dead .100 address and limped onto the
flaky WAN relay -> QA answers never returned -> customers saw only placeholders.

Fix: co-located recipients are reached at 127.0.0.1:<port> (port is stable, only
the host IP drifts) — both in the legacy ec_agent dispatch (localize_a2a_url)
and the discovery router (same-machine fast-path).
"""

import agent.ec_agents.vehicle_affinity as va
from agent.ec_agents.vehicle_affinity import localize_a2a_url, agent_on_this_machine


class _FakeAgent:
    def __init__(self, vehicle_id):
        self.vehicle_id = vehicle_id
        self.mainwin = None


def _pin_local(monkeypatch, local_id="MID-LOCAL"):
    monkeypatch.setattr(va, "resolve_local_vehicle_id", lambda mw=None, username="": local_id)
    monkeypatch.setattr(va, "_local_legacy_vehicle_id", lambda mw=None, username="": "")
    monkeypatch.setattr(va, "_vehicle_row_is_local", lambda mw, vid: False)


def test_localize_rewrites_host_for_same_machine(monkeypatch):
    _pin_local(monkeypatch)
    # stale LAN IP -> localhost, port preserved.
    assert localize_a2a_url("http://192.168.10.100:3604", _FakeAgent("MID-LOCAL")) == \
        "http://127.0.0.1:3604"
    # with an /a2a/ path preserved.
    assert localize_a2a_url("http://192.168.10.100:3604/a2a/", _FakeAgent("MID-LOCAL")) == \
        "http://127.0.0.1:3604/a2a/"


def test_localize_noop_for_remote_and_unknown(monkeypatch):
    _pin_local(monkeypatch)
    # a different vehicle (real other host) is left untouched.
    assert localize_a2a_url("http://192.168.10.100:3604", _FakeAgent("MID-OTHER")) == \
        "http://192.168.10.100:3604"
    # empty vehicle_id is NOT assumed local (conservative).
    assert localize_a2a_url("http://192.168.10.100:3604", _FakeAgent("")) == \
        "http://192.168.10.100:3604"


def test_localize_noop_when_already_local_or_killswitch(monkeypatch):
    _pin_local(monkeypatch)
    assert localize_a2a_url("http://127.0.0.1:3604", _FakeAgent("MID-LOCAL")) == \
        "http://127.0.0.1:3604"
    assert localize_a2a_url("http://localhost:3604", _FakeAgent("MID-LOCAL")) == \
        "http://localhost:3604"
    monkeypatch.setenv("ECAN_A2A_NO_LOCALHOST_REWRITE", "1")
    assert localize_a2a_url("http://192.168.10.100:3604", _FakeAgent("MID-LOCAL")) == \
        "http://192.168.10.100:3604"


def test_agent_on_this_machine(monkeypatch):
    _pin_local(monkeypatch)
    assert agent_on_this_machine(_FakeAgent("MID-LOCAL")) is True
    assert agent_on_this_machine(_FakeAgent("MID-OTHER")) is False
    assert agent_on_this_machine(_FakeAgent("")) is False


async def test_router_same_machine_uses_localhost(monkeypatch):
    """The discovery router routes a same-machine agent to 127.0.0.1, not its
    (possibly stale) advertised lan_host."""
    import agent.a2a.discovery.router as router

    class _EP:
        machine_id = "MID-LOCAL"
        lan_port = 3604
        lan_path = "/a2a/"
        lan_url = "http://192.168.10.100:3604/a2a/"

    class _Dir:
        def lookup(self, agent_id):
            return _EP()

        def get_self_machine_id(self):
            return "MID-LOCAL"

    posted = {}

    async def _fake_post(url, payload, timeout):
        posted["url"] = url
        return {"ok": True}

    monkeypatch.setattr(router, "_post_lan", _fake_post)
    out = await router.send_to_agent("agent_x", {"hi": 1}, directory=_Dir())
    assert out.success is True
    assert posted["url"] == "http://127.0.0.1:3604/a2a/"
