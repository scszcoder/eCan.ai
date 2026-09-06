"""Single source of truth for LLM token pricing (USD per 1K tokens).

Consolidates the pricing tables that used to live in three places and drift:
  * token_tracker._calculate_cost  (authoritative ingest cost)
  * llm_token_usage_handler        (DEFAULT_PRICING + the billing split ratio)
  * the frontend TokenUsageDisplay (a hardcoded fallback — now removed; the
    frontend displays the backend value and never recomputes cost)

Cost is computed AT INGEST (token_tracker) and stored as cost_usd on each
token_usage row. This table drives that ingest calc and the billing
input/output split ratio. Update prices HERE only.

Prices are per 1K tokens (input, output). Anthropic first-party list rates as
of 2026-06 (per-1M ÷ 1000); OpenAI/DeepSeek/Google carried over from the prior
token_tracker table. Keys are matched as SUBSTRINGS of the model id
(case-insensitive), most-specific FIRST — so a dated snapshot like
'claude-opus-4-8-20260401' still resolves to the 'claude-opus-4-8' entry.
"""

from typing import Dict, Tuple

# vendor -> ordered {model_key: (input_per_1k, output_per_1k)} ; specific first
MODEL_PRICING: Dict[str, object] = {
    'openai': {
        'gpt-5': (0.005, 0.015),
        'gpt-4.1-mini': (0.0004, 0.0016),
        'gpt-4.1-nano': (0.0001, 0.0004),
        'gpt-4.1': (0.002, 0.008),
        'gpt-4o-mini': (0.00015, 0.0006),
        'gpt-4o': (0.005, 0.015),
        'gpt-4-turbo': (0.01, 0.03),
        'gpt-4': (0.03, 0.06),
        'gpt-3.5-turbo': (0.0005, 0.0015),
        'o4-mini': (0.0011, 0.0044),
        'o3-mini': (0.0011, 0.0044),
        'o3': (0.002, 0.008),
        'o1-preview': (0.015, 0.06),
        'o1-mini': (0.003, 0.012),
        'text-embedding-3-small': (0.00002, 0.0),
        'text-embedding-3-large': (0.00013, 0.0),
    },
    'anthropic': {
        # current (Anthropic first-party per-1M ÷ 1000)
        'claude-fable-5-1': (0.010, 0.050),
        'claude-fable-5': (0.010, 0.050),
        'claude-mythos-5-1': (0.010, 0.050),
        'claude-opus-5': (0.005, 0.025),
        'claude-opus-4-8': (0.005, 0.025),
        'claude-opus-4-7': (0.005, 0.025),
        'claude-opus-4-6': (0.005, 0.025),
        'claude-sonnet-5': (0.002, 0.010),
        'claude-sonnet-4-6': (0.003, 0.015),
        'claude-haiku-4-5': (0.001, 0.005),
        # legacy
        'claude-3-opus': (0.015, 0.075),
        'claude-3-5-sonnet': (0.003, 0.015),
        'claude-3-sonnet': (0.003, 0.015),
        'claude-3-5-haiku': (0.0008, 0.004),
        'claude-3-haiku': (0.00025, 0.00125),
    },
    'deepseek': {
        'deepseek-chat': (0.00014, 0.00028),
        'deepseek-coder': (0.00014, 0.00028),
    },
    'google': {
        'gemini-1.5-pro': (0.00125, 0.005),
        'gemini-pro': (0.00025, 0.0005),
    },
    'default': (0.01, 0.02),
}

DEFAULT_PRICE: Tuple[float, float] = MODEL_PRICING['default']  # type: ignore[assignment]


def get_model_price(vendor: str, model: str) -> Tuple[float, float]:
    """(input_per_1k, output_per_1k) for a vendor+model, falling back to the
    default. Matches a price key as a case-insensitive substring of the model
    id; most-specific keys are listed first so they win."""
    vmap = MODEL_PRICING.get((vendor or '').lower())
    if isinstance(vmap, dict):
        ml = (model or '').lower()
        for key, price in vmap.items():
            if key in ml:
                return price
    return DEFAULT_PRICE


def calc_cost(vendor: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in USD for the given token counts."""
    pin, pout = get_model_price(vendor, model)
    return (input_tokens / 1000.0) * pin + (output_tokens / 1000.0) * pout
