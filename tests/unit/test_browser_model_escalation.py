"""A browser agent stuck on the same failure moves up to stronger models
(flash -> max -> Opus as the capped last resort) and back once it moves on."""
from types import SimpleNamespace

from agent.ec_skills.browser_node.runner import ModelEscalator, escalation_tiers


def _agent(model="qwen3.8-flash"):
    reg = []
    return SimpleNamespace(llm=SimpleNamespace(model=model), _fallback_llm=None,
                           token_cost_service=SimpleNamespace(register_llm=reg.append))


def _esc(**kw):
    return ModelEscalator(["qwen3.8-max", "claude-opus-5-5"], lambda m: SimpleNamespace(model=m), **kw)


def test_tiers_start_above_the_base_model(monkeypatch):
    monkeypatch.delenv("ECAN_BROWSER_ESCALATION", raising=False)
    assert escalation_tiers("qwen3.8-flash") == ["qwen3.8-max", "claude-opus-5-5"]
    assert escalation_tiers("qwen3.8-max") == ["claude-opus-5-5"]
    assert escalation_tiers("claude-opus-5-5") == []
    monkeypatch.setenv("ECAN_BROWSER_ESCALATION", "")
    assert escalation_tiers("qwen3.8-flash") == []


def test_first_nudge_keeps_the_model_later_ones_climb():
    a, e = _agent(), _esc()
    base = a.llm
    assert e.on_nudge(a, 1) == "" and a.llm is base
    assert e.on_nudge(a, 2) == "qwen3.8-max" and a._fallback_llm is base
    assert e.on_nudge(a, 3) == "claude-opus-5-5" and a.llm.model == "claude-opus-5-5"
    assert e.on_nudge(a, 4) == ""


def test_back_to_the_base_model_after_three_good_steps():
    a, e = _agent(), _esc()
    base = a.llm
    e.on_nudge(a, 2)
    assert [e.on_step(a, True) for _ in range(3)] == ["", "", "moving again"]
    assert a.llm is base


def test_last_resort_is_capped_per_run():
    a, e = _agent(), _esc(last_cap=20)
    base = a.llm
    e.on_nudge(a, 2)
    e.on_nudge(a, 3)
    out = [e.on_step(a, False) for _ in range(20)]
    assert out[-1] == "last-resort budget used" and out.count("") == 19 and a.llm is base
    assert e.on_nudge(a, 4) == "qwen3.8-max"          # max is not capped
    assert e.on_nudge(a, 5) == ""                     # Opus budget is spent


def test_a_model_that_cannot_be_built_changes_nothing():
    a = _agent()
    e = ModelEscalator(["claude-opus-5-5"], lambda m: None)
    assert e.on_nudge(a, 2) == "" and a.llm.model == "qwen3.8-flash"


def test_a_node_can_set_its_own_chain():
    # explore-and-learn: baseline qwen3.7-flash, a stuck agent goes to qwen3.8-max only
    assert escalation_tiers("qwen3.7-flash", ["qwen3.8-max"]) == ["qwen3.8-max"]
    assert escalation_tiers("qwen3.8-max", ["qwen3.8-max"]) == []
    assert escalation_tiers("qwen3.7-flash", []) == []       # "none"
