"""A browser step that ends early with the work undone is sent back to work (2026-11-19)."""
import asyncio
from types import SimpleNamespace

from browser_use.agent.views import ActionResult

from agent.ec_skills.browser_node.runner import _install_early_done_guard


class Action:
    def __init__(self, **body):
        self.body = body

    def model_dump(self, exclude_unset=False):
        return self.body


class FakeAgent:
    def __init__(self, step):
        self.state = SimpleNamespace(n_steps=step)
        self.ran = []

    async def multi_act(self, actions):
        self.ran.append(actions)
        return [ActionResult(is_done=True, extracted_content="done")]


def _done(agent, **params):
    return asyncio.run(agent.multi_act([Action(done=params)]))[0]


def test_an_early_done_on_a_loading_page_is_refused_three_times_then_taken():
    agent = FakeAgent(3)
    _install_early_done_guard(agent, 100)
    report = '{"success": false, "summary": "the listing rows have not yet loaded"}'
    assert _done(agent, text=report, success=True).error
    assert _done(agent, text=report, success=True).error
    agent.state.n_steps = 53   # half way: the form was still half filled (2026-11-19)
    assert _done(agent, text=report, success=True).error and not agent.ran
    assert _done(agent, text=report, success=True).is_done and len(agent.ran) == 1


def test_a_finished_late_or_other_action_is_taken():
    agent = FakeAgent(3)
    _install_early_done_guard(agent, 100)
    assert _done(agent, text='{"published": true, "notes": "uploading 4 photos went fine"}').is_done
    assert asyncio.run(agent.multi_act([Action(wait={"seconds": 3})]))[0].is_done
    late = FakeAgent(80)
    _install_early_done_guard(late, 100)
    assert _done(late, text="page still loading", success=False).is_done
