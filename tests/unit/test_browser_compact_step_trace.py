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


def test_each_step_records_its_page_url():
    h = _step("Submitted. Verdict: Success", "report the id", [])
    h.state = SimpleNamespace(url="https://mms.pinduoduo.com/goods/goods_add/success?goods_id=1022282270745")
    t = compact_step_trace(SimpleNamespace(history=[h, _step("", "", [])]))
    assert t[0]["url"].endswith("goods_id=1022282270745")
    assert t[1]["url"] == ""


def test_run_finished_only_when_the_agent_called_done():
    from agent.ec_skills.browser_node.runner import run_finished
    assert run_finished(SimpleNamespace(is_done=lambda: True)) is True
    # stopped by the stuck watchdog: final_result() would still be the last evaluate output
    assert run_finished(SimpleNamespace(is_done=lambda: False)) is False
    assert run_finished(None) is False


def test_trace_says_which_action_failed():
    step = SimpleNamespace(
        model_output=SimpleNamespace(evaluation_previous_goal="", next_goal="fill attributes",
                                     action=[_Action({"select_option": {"index": 5, "text": "棉"}}),
                                             _Action({"select_option": {"index": 9, "text": "通用"}})]),
        result=[SimpleNamespace(error=None), SimpleNamespace(error="select_option: no option matches '通用'")])
    t = compact_step_trace(SimpleNamespace(history=[step]))
    assert t[0]["failed"] == [{"action": "select_option", "args": {"index": 9, "text": "通用"},
                               "error": "select_option: no option matches '通用'"}]
