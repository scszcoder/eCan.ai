"""The browser node hands a compact per-step trace to the next node, so a skill
can learn from what its agent judged, aimed at, did and got wrong (str(history)
has no verdicts or goals)."""
from types import SimpleNamespace

from agent.ec_skills.browser_node.runner import compact_step_trace


class _Action:
    def __init__(self, d):
        self.d = d

    def model_dump(self, **_):
        return self.d


def _step(ev, goal, actions, errors=()):
    return SimpleNamespace(
        model_output=SimpleNamespace(evaluation_previous_goal=ev, next_goal=goal,
                                     action=[_Action(a) for a in actions]),
        result=[SimpleNamespace(error=e) for e in errors] or [SimpleNamespace(error=None)])


def test_trace_keeps_verdict_goal_actions_and_errors():
    history = SimpleNamespace(history=[
        _step("", "add sizes", [{"input": {"index": 7, "text": "M"}}, {"input": {"index": 7, "text": "L"}}]),
        _step("Failure - L replaced M", "tick the standard sizes", [{"click": {"index": 9}}], ["element 9 not found"]),
        SimpleNamespace(model_output=None, result=[]),
    ])
    t = compact_step_trace(history)
    assert [s["step"] for s in t] == [1, 2, 3]
    assert t[0]["actions"] == [{"input": {"index": 7, "text": "M"}}, {"input": {"index": 7, "text": "L"}}]
    assert t[1]["eval"].startswith("Failure") and t[1]["goal"] == "tick the standard sizes"
    assert t[1]["errors"] == ["element 9 not found"]
    assert t[2]["actions"] == [] and t[2]["errors"] == []


def test_no_history_is_an_empty_trace():
    assert compact_step_trace(None) == []
