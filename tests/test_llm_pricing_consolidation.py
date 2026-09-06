"""One pricing source of truth: agent/ec_skills/llm_pricing.py. token_tracker
and the billing handler both resolve through it, and current models are priced
(no silent fall-through to the generic default)."""

from agent.ec_skills import llm_pricing


def test_current_models_priced_not_default():
    # Anthropic current family must resolve to real prices, not the fallback.
    for model, expect in [
        ('claude-opus-5', (0.005, 0.025)),
        ('claude-sonnet-5', (0.002, 0.010)),
        ('claude-haiku-4-5', (0.001, 0.005)),
        ('claude-fable-5-1', (0.010, 0.050)),
    ]:
        assert llm_pricing.get_model_price('anthropic', model) == expect, model
        assert llm_pricing.get_model_price('anthropic', model) != llm_pricing.DEFAULT_PRICE


def test_dated_snapshot_resolves_via_substring():
    assert llm_pricing.get_model_price('anthropic', 'claude-opus-4-8-20260401') == (0.005, 0.025)


def test_specific_key_wins_over_generic():
    # 'claude-sonnet-5' must not be captured by 'claude-sonnet-4-6' or vice versa.
    assert llm_pricing.get_model_price('anthropic', 'claude-sonnet-5') == (0.002, 0.010)
    assert llm_pricing.get_model_price('anthropic', 'claude-sonnet-4-6') == (0.003, 0.015)
    # gpt-4.1-mini must not be captured by 'gpt-4' or 'gpt-4.1'.
    assert llm_pricing.get_model_price('openai', 'gpt-4.1-mini') == (0.0004, 0.0016)


def test_unknown_vendor_and_model_default():
    assert llm_pricing.get_model_price('', '') == llm_pricing.DEFAULT_PRICE
    assert llm_pricing.get_model_price('mystery', 'x') == llm_pricing.DEFAULT_PRICE


def test_calc_cost_matches_manual():
    # 1000 in + 500 out on opus-5: 1*0.005 + 0.5*0.025 = 0.0175
    assert abs(llm_pricing.calc_cost('anthropic', 'claude-opus-5', 1000, 500) - 0.0175) < 1e-9


def test_token_tracker_delegates_to_shared_table():
    from agent.ec_skills.token_tracker import token_tracker
    got = token_tracker._calculate_cost('anthropic', 'claude-opus-5', 1000, 500)
    assert abs(got - llm_pricing.calc_cost('anthropic', 'claude-opus-5', 1000, 500)) < 1e-12


def test_handler_split_uses_shared_table():
    import gui.ipc.w2p_handlers.llm_token_usage_handler as h
    # opus-5 output is 5x input price; a 1000/1000 split of a $0.03 total should
    # apportion 1/6 to input, 5/6 to output, and always sum to the total.
    ic, oc = h._split_cost(0.03, 1000, 1000, 'anthropic', 'claude-opus-5')
    assert abs((ic + oc) - 0.03) < 1e-9
    assert oc > ic  # output priced higher
