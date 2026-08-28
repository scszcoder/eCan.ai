"""Tests for provider_limits_validator MAX_GLEANING / MAX_ASYNC_LLM defaults.

These two settings control LightRAG processing speed at the chunk level:

- MAX_GLEANING: extra LLM pass per chunk for "second-pass entity refinement".
  Set to 0 to skip this pass entirely (~50% speedup, may miss 5-10% entities).
- MAX_ASYNC_LLM: LightRAG 1.5.6's primary env var for chunk-level LLM concurrency.
  Unified default of 2 (cloud and local) — chosen to cap stop latency when a
  chunk LLM hangs; throughput trade-off is acceptable.

User-set values must NOT be overwritten — these tests cover only the
"not set" path.
"""

from knowledge.provider_limits_validator import ProviderLimitsValidator


def _validate(provider_name: str, config: dict):
    validator = ProviderLimitsValidator()
    return validator.validate_and_adjust_config(provider_name, config)


def test_max_gleaning_defaults_to_zero_when_unset_cloud() -> None:
    adjusted, warnings = _validate("openai", {})
    assert adjusted["MAX_GLEANING"] == 0
    # WARNING must be emitted so operators see why this changed.
    assert any("MAX_GLEANING" in w for w in warnings)


def test_max_gleaning_defaults_to_zero_when_unset_local() -> None:
    adjusted, warnings = _validate("ollama", {})
    assert adjusted["MAX_GLEANING"] == 0
    assert any("MAX_GLEANING" in w for w in warnings)


def test_max_gleaning_respects_user_value() -> None:
    # When the user explicitly sets MAX_GLEANING=1 (quality over speed),
    # the validator must NOT overwrite it. The value passes through as-is
    # (LightRAG reads it via get_env_value(..., int) which coerces).
    adjusted, warnings = _validate("openai", {"MAX_GLEANING": "1"})
    assert str(adjusted["MAX_GLEANING"]) == "1"
    assert not any("MAX_GLEANING" in w for w in warnings)


def test_max_async_llm_defaults_to_two_when_unset_cloud() -> None:
    adjusted, warnings = _validate("openai", {})
    assert adjusted["MAX_ASYNC_LLM"] == 2
    assert any("MAX_ASYNC_LLM" in w for w in warnings)


def test_max_async_llm_defaults_to_two_when_unset_local() -> None:
    adjusted, warnings = _validate("ollama", {})
    assert adjusted["MAX_ASYNC_LLM"] == 2
    assert any("MAX_ASYNC_LLM" in w for w in warnings)


def test_max_async_llm_respects_user_value() -> None:
    adjusted, warnings = _validate("openai", {"MAX_ASYNC_LLM": "12"})
    assert str(adjusted["MAX_ASYNC_LLM"]) == "12"
    assert not any("MAX_ASYNC_LLM" in w for w in warnings)


def test_max_async_llm_ryoais_is_treated_as_local() -> None:
    # RyoAIS is the other local provider; must use the conservative default.
    adjusted, warnings = _validate("ryoais", {})
    assert adjusted["MAX_ASYNC_LLM"] == 2


def test_recommended_config_includes_new_keys() -> None:
    validator = ProviderLimitsValidator()
    cloud = validator.get_recommended_config("openai")
    local = validator.get_recommended_config("ollama")
    assert cloud["MAX_GLEANING"] == 0
    assert cloud["MAX_ASYNC_LLM"] == 2
    assert local["MAX_GLEANING"] == 0
    assert local["MAX_ASYNC_LLM"] == 2
