"""A node that raises max_actions_per_step gets a system-prompt rule to batch.

browser-use's own prompt pushes one goal per step and a wait after typing into
a combobox; the 拼多多 publish took one action in 61% of 101 steps (KEN
2026-10-27).
"""
from agent.ec_skills.browser_use_extension.agent_config import get_agent_kwargs_with_compaction


def test_raised_action_cap_adds_the_batching_policy():
    kw = get_agent_kwargs_with_compaction(context_length=128000, max_actions_per_step=10)
    assert kw["max_actions_per_step"] == 10
    msg = kw["extend_system_message"]
    assert "<batching_policy>" in msg and "up to 10 actions" in msg


def test_default_or_lower_cap_leaves_the_system_prompt_alone():
    for cap in (None, 1, 5):
        kw = get_agent_kwargs_with_compaction(context_length=128000, max_actions_per_step=cap)
        assert "extend_system_message" not in kw
