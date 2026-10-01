"""browser_watchdog: a monitored run's store Chrome is rebuilt when it dies
(2026-09-30: a closed 拼多多 Chrome left the front desk blind for 30 min)."""

import asyncio
import http.server
import threading
from types import SimpleNamespace

import pytest

from agent.ec_skills.browser_node import browser_watchdog as wd


class _Cdp:
    """A /json/version endpoint that can be taken down, like a dying Chrome."""

    def __init__(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def kill(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setenv("ECAN_BROWSER_WATCHDOG", "1")
    monkeypatch.setattr(wd, "PROBE_INTERVAL_S", 0.05)
    monkeypatch.setattr(wd, "BACKOFF_S", (0.01, 0.01, 0.01))
    monkeypatch.setattr(wd, "_monitors_registered", lambda _id: True)
    reports, dropped = [], []
    monkeypatch.setattr(wd._agent_status, "report", lambda aid=None, **f: reports.append(f))

    async def _drop(w):
        dropped.append(w.scope_key)
    monkeypatch.setattr(wd, "_drop_dead_session", _drop)
    wd._watches.clear()
    return SimpleNamespace(reports=reports, dropped=dropped)


def _mainwin(agent_ids=("a1",)):
    return SimpleNamespace(get_agents=lambda: [SimpleNamespace(card=SimpleNamespace(id=i)) for i in agent_ids])


async def _arm(cdp, rebuild, mainwin=None, scope="s1"):
    wd.arm(scope_key=scope, session=SimpleNamespace(cdp_url=cdp.url), monitor_set_id="m1",
           agent_id="a1", mainwin=mainwin or _mainwin(), rebuild=rebuild)
    return wd._watches[scope]


def test_live_browser_is_left_alone(fast):
    async def _t():
        cdp, calls = _Cdp(), []

        async def rebuild():
            calls.append(1)
            return True
        w = await _arm(cdp, rebuild)
        await asyncio.sleep(0.4)
        assert not calls and not fast.dropped and not w.task.done()
        w.task.cancel()
        cdp.kill()
    asyncio.run(_t())


def test_dead_browser_is_rebuilt_once(fast):
    async def _t():
        cdp, calls = _Cdp(), []

        async def rebuild():
            calls.append(1)
            return True
        w = await _arm(cdp, rebuild)
        cdp.kill()
        await asyncio.wait_for(w.task, 5)
        assert fast.dropped == ["s1"] and calls == [1]
        assert {"chrome": "recovering", "chrome_recover_attempt": 1} in fast.reports
        assert not any(r.get("chrome") == "dead" for r in fast.reports)
    asyncio.run(_t())


def test_gives_up_after_three_attempts(fast):
    async def _t():
        cdp, calls = _Cdp(), []

        async def rebuild():
            calls.append(1)
            raise RuntimeError("launch failed")
        w = await _arm(cdp, rebuild)
        cdp.kill()
        await asyncio.wait_for(w.task, 5)
        assert len(calls) == wd.MAX_ATTEMPTS
        assert fast.reports[-1] == {"chrome": "dead"}
    asyncio.run(_t())


def test_stands_down_when_monitors_stop(fast, monkeypatch):
    async def _t():
        cdp, calls = _Cdp(), []
        monkeypatch.setattr(wd, "_monitors_registered", lambda _id: False)

        async def rebuild():
            calls.append(1)
            return True
        w = await _arm(cdp, rebuild)
        cdp.kill()
        await asyncio.wait_for(w.task, 5)
        assert not calls and not fast.dropped
    asyncio.run(_t())


def test_stopped_agent_is_not_relaunched(fast):
    async def _t():
        cdp, calls = _Cdp(), []

        async def rebuild():
            calls.append(1)
            return True
        w = await _arm(cdp, rebuild, mainwin=_mainwin(agent_ids=()))
        cdp.kill()
        await asyncio.wait_for(w.task, 5)
        assert not calls
    asyncio.run(_t())


def test_rearm_same_session_keeps_the_watch(fast):
    async def _t():
        cdp = _Cdp()

        async def rebuild():
            return True
        session = SimpleNamespace(cdp_url=cdp.url)
        wd.arm(scope_key="s1", session=session, monitor_set_id="m1", agent_id="a1",
               mainwin=_mainwin(), rebuild=rebuild)
        first = wd._watches["s1"].task
        wd.arm(scope_key="s1", session=session, monitor_set_id="m2", agent_id="a1",
               mainwin=_mainwin(), rebuild=rebuild)
        assert wd._watches["s1"].task is first and wd._watches["s1"].monitor_set_id == "m2"
        first.cancel()
        cdp.kill()
    asyncio.run(_t())


def test_rebuild_runs_setup_but_never_dispatches(monkeypatch):
    from agent.ec_skills.browser_node import runner as r
    calls = []
    session = SimpleNamespace()
    agent = SimpleNamespace(browser_session=session)
    rs = r.BrowserRunSession(ctx=SimpleNamespace(node_name="n", skill_name="s"), task="t",
                             mainwin=None, state={}, calling_agent_id="a1")

    async def _asg(**k):
        calls.append("scope")
        return None, "t", SimpleNamespace(browser_scope_key="k", last_known_focus_target_id=None)

    async def _acquire(**k):
        calls.append("acquire")
        return agent, None

    async def _finalize(**k):
        calls.append("finalize")
        return "k", None

    async def _never(**k):
        raise AssertionError("rebuild must not dispatch")

    monkeypatch.setattr(r, "prepare_task_with_runtime_context", lambda task, **k: (task, False))
    monkeypatch.setattr(rs, "_extract_assignment_and_scope", _asg)
    monkeypatch.setattr(rs, "_resolve_agent_class", lambda: type("Agent", (), {}))
    monkeypatch.setattr(rs, "_build_local_llm_and_kwargs", lambda **k: (None, None, {}))
    monkeypatch.setattr(rs, "_build_browser_profile_and_callbacks", lambda **k: (None, {}, True))
    monkeypatch.setattr(rs, "_apply_post_kwargs_extensions", lambda **k: None)
    monkeypatch.setattr(rs, "_acquire_browser_and_agent", _acquire)
    monkeypatch.setattr(rs, "_finalize_agent_setup", _finalize)
    monkeypatch.setattr(rs, "_handle_pre_dispatch", _never)
    monkeypatch.setattr(rs, "_run_agent_dispatch", _never)
    monkeypatch.setattr(r._bh, "is_session_alive", lambda s: s is session)
    from agent.ec_skills.browser_use_extension import event_monitor_capability as emc
    monkeypatch.setattr(emc, "get_event_monitor_capability", lambda s, create=False: SimpleNamespace(
        get_active_monitor_set=lambda: SimpleNamespace(monitors=[object()])))

    assert asyncio.run(rs.rebuild_monitored_browser()) is True
    assert calls == ["scope", "acquire", "finalize"]


def test_off_unless_enabled(monkeypatch):
    monkeypatch.delenv("ECAN_BROWSER_WATCHDOG", raising=False)
    wd._watches.clear()

    async def _t():
        async def rebuild():
            return True
        wd.arm(scope_key="s-off", session=SimpleNamespace(cdp_url="http://127.0.0.1:1"), monitor_set_id="m1",
               agent_id="a1", mainwin=_mainwin(), rebuild=rebuild)
    asyncio.run(_t())
    assert "s-off" not in wd._watches
