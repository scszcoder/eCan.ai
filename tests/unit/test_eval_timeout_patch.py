"""A model-written page script that loops froze the tab for the rest of the run
(抖店 run 68, KEN 2026-10-31); every evaluate now carries a time limit."""
import asyncio

import pytest
from cdp_use.cdp.runtime.library import RuntimeClient

from agent.ec_skills.browser_use_extension import eval_timeout_patch as p


class _Client:
    def __init__(self, fail_after=0.0):
        self.sent, self.fail_after = [], fail_after

    async def send_raw(self, method, params, session_id=None):
        self.sent.append(params)
        if self.fail_after:
            await asyncio.sleep(self.fail_after)
            raise RuntimeError({"code": -32603, "message": "Internal error"})
        return {"result": {"value": 2}}


def test_a_limit_is_added_and_an_own_limit_kept():
    assert p.install()
    c = _Client()
    asyncio.run(RuntimeClient(c).evaluate({"expression": "1+1"}))
    asyncio.run(RuntimeClient(c).evaluate({"expression": "1+1", "timeout": 500}))
    assert c.sent[0]["timeout"] == p.SCRIPT_TIMEOUT_MS and c.sent[1]["timeout"] == 500


def test_a_stopped_script_is_reported_plainly(monkeypatch):
    assert p.install()
    monkeypatch.setattr(p, "SCRIPT_TIMEOUT_MS", 1500)
    with pytest.raises(p.ScriptTimeout, match="was stopped"):
        asyncio.run(RuntimeClient(_Client(fail_after=1.6)).evaluate({"expression": "while(true){}"}))


def test_other_errors_pass_through_unchanged():
    assert p.install()
    with pytest.raises(RuntimeError) as e:
        asyncio.run(RuntimeClient(_Client(fail_after=0.01)).evaluate({"expression": "x"}))
    assert not isinstance(e.value, p.ScriptTimeout)
