"""Compaction is an LLM call of its own: the browser agent must not compact
after every step (KEN 2026-10-25: a second LLM call per step burned the credit)."""
from agent.ec_skills.browser_use_extension.agent_config import (
    CompressionConfig, get_agent_kwargs_with_compaction)


def test_large_context_model_does_not_compact_every_step():
    kw = get_agent_kwargs_with_compaction(context_length=128000)
    mc = kw["message_compaction"]
    assert mc.compact_every_n_steps > 1
    assert mc.trigger_char_count > 1000


def test_standard_context_model_does_not_compact_every_step():
    kw = get_agent_kwargs_with_compaction(context_length=CompressionConfig.STANDARD_CONTEXT_THRESHOLD)
    assert kw["message_compaction"].compact_every_n_steps > 1
