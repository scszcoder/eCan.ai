"""Flash mode (the node's 闪电模式) reaches browser-use, and stuck detection
still works without the model's evaluation: the node setting used to be read and
logged but never passed on, and StuckWatch read only evaluation_previous_goal,
which flash mode drops."""
from types import SimpleNamespace

from agent.ec_skills.browser_node.runner import RunContext, StuckWatch, step_verdict
from agent.ec_skills.browser_use_extension.agent_config import get_agent_kwargs_with_compaction


def _agent(*errors):
    return SimpleNamespace(state=SimpleNamespace(last_result=[SimpleNamespace(error=e) for e in errors]))


FLASH = SimpleNamespace(memory="filling the SKU table", action=[])


def test_the_evaluation_is_the_verdict_when_there_is_one():
    out = SimpleNamespace(evaluation_previous_goal="Typed the title. Verdict: Success")
    assert step_verdict(out, _agent("ignored")) == "Typed the title. Verdict: Success"


def test_flash_mode_judges_the_previous_step_by_its_action_errors():
    assert step_verdict(FLASH, _agent(None, None)) == "Verdict: Success"
    assert step_verdict(FLASH, _agent(None, "Element 812 not found")).startswith("Verdict: Failure Element 812")
    assert step_verdict(FLASH, _agent()) == ""          # first step: nothing to judge yet
    assert step_verdict(FLASH, None) == ""


def test_repeated_action_errors_in_flash_mode_nudge():
    w = StuckWatch()
    same = [step_verdict(FLASH, _agent(f"Element {i} not found")) for i in range(3)]
    assert [w.step(v) for v in same] == ["", "", "nudge"]
    w = StuckWatch()
    varied = [step_verdict(FLASH, _agent(e)) for e in ("Element 4 not found", "Timeout waiting for page",
                                                          "Input rejected: field is read-only",
                                                          "Dropdown option 均码 missing", "Upload failed: no chooser")]
    assert [w.step(v) for v in varied] == ["", "", "", "", "nudge"]


def test_the_node_setting_reaches_the_agent_kwargs():
    assert RunContext.__dataclass_fields__["node_flash_mode"].default is False
    kw = get_agent_kwargs_with_compaction(use_vision=False, context_length=128000, flash_mode=True)
    assert kw["flash_mode"] is True
