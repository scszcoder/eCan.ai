"""Billing drill-down handlers: local-timezone bucketing and the input/output
cost split that always sums back to the authoritative stored cost_usd."""

from datetime import datetime

import gui.ipc.w2p_handlers.llm_token_usage_handler as h
from gui.ipc.types import create_request


class _FakeSvc:
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def get_usage_rows(self, start_utc, end_utc, user_email=None):
        self.calls.append((start_utc, end_utc))
        return [r for r in self._rows if start_utc <= r['usage_timestamp'] < end_utc]


def _row(ts, vendor, model, itok, otok, cost):
    return {'usage_timestamp': ts, 'vendor': vendor, 'model': model,
            'input_tokens': itok, 'output_tokens': otok,
            'total_tokens': itok + otok, 'cost_usd': cost}


# ── cost split ───────────────────────────────────────────────────────────────

def test_split_cost_sums_to_total():
    for vendor, model in [('openai', 'gpt-4o'), ('anthropic', 'claude-3-opus'),
                          ('unknown', 'mystery-model')]:
        ic, oc = h._split_cost(1.23456, 1000, 500, vendor, model)
        assert abs((ic + oc) - 1.23456) < 1e-9, (vendor, model, ic, oc)
        assert ic >= 0 and oc >= 0


def test_split_cost_zero_tokens_no_crash():
    ic, oc = h._split_cost(0.0, 0, 0, 'openai', 'gpt-4o')
    assert ic == 0 and oc == 0


def test_split_price_falls_back_to_default():
    from agent.ec_skills.llm_pricing import get_model_price, DEFAULT_PRICE
    assert get_model_price('nobody', 'nothing') == DEFAULT_PRICE


# ── daily bucketing with a timezone offset ───────────────────────────────────

def test_daily_buckets_by_local_timezone(monkeypatch):
    # A row at 23:30 UTC on the 1st is 07:30 on the 2nd at +480 (China).
    rows = [
        _row(datetime(2026, 9, 1, 23, 30), 'openai', 'gpt-4o', 100, 50, 0.10),
        _row(datetime(2026, 9, 2, 1, 0), 'openai', 'gpt-4o', 200, 100, 0.20),
    ]
    monkeypatch.setattr(h, '_billing_token_service', lambda: _FakeSvc(rows))
    monkeypatch.setattr(h, '_display_currency_fields', lambda c: {'cost': round(c, 4), 'currency': 'USD'})

    req = create_request('llm.getBillingDaily')
    resp = h.handle_get_billing_daily(req, {'year': 2026, 'month': 9, 'tz_offset_minutes': 480})
    days = {d['date']: d for d in resp['result']['days']}
    # Both rows land on 2026-09-02 in local +480 time.
    assert '2026-09-02' in days
    assert days['2026-09-02']['input_tokens'] == 300
    assert abs(days['2026-09-02']['cost_usd'] - 0.30) < 1e-9
    assert '2026-09-01' not in days


def test_daily_utc_offset_zero(monkeypatch):
    rows = [_row(datetime(2026, 9, 1, 23, 30), 'openai', 'gpt-4o', 100, 50, 0.10)]
    monkeypatch.setattr(h, '_billing_token_service', lambda: _FakeSvc(rows))
    monkeypatch.setattr(h, '_display_currency_fields', lambda c: {'cost': round(c, 4), 'currency': 'USD'})
    resp = h.handle_get_billing_daily(create_request('x'), {'year': 2026, 'month': 9, 'tz_offset_minutes': 0})
    days = {d['date']: d for d in resp['result']['days']}
    assert '2026-09-01' in days  # stays on the 1st at UTC


# ── hourly + per-model ───────────────────────────────────────────────────────

def test_hour_models_split_sums_and_currency(monkeypatch):
    rows = [
        _row(datetime(2026, 9, 2, 3, 15), 'openai', 'gpt-4o', 1000, 500, 0.40),
        _row(datetime(2026, 9, 2, 3, 45), 'openai', 'gpt-4o', 1000, 500, 0.40),
        _row(datetime(2026, 9, 2, 3, 50), 'anthropic', 'claude-3-opus', 200, 100, 0.30),
    ]
    monkeypatch.setattr(h, '_billing_token_service', lambda: _FakeSvc(rows))
    # CN currency conversion x2 to prove display currency is applied.
    monkeypatch.setattr(h, '_display_currency_fields', lambda c: {'cost': round(c * 2, 4), 'currency': 'CNY'})

    resp = h.handle_get_billing_hour_models(
        create_request('x'), {'date': '2026-09-02', 'hour': 3, 'tz_offset_minutes': 0})
    result = resp['result']
    assert result['currency'] == 'CNY'
    by_model = {r['model']: r for r in result['rows']}
    gpt = by_model['gpt-4o']
    assert gpt['input_tokens'] == 2000 and gpt['output_tokens'] == 1000
    # input_cost + output_cost == total_cost (in display currency).
    assert abs((gpt['input_cost'] + gpt['output_cost']) - gpt['total_cost']) < 1e-6
    # total = (0.40+0.40) usd * 2 = 1.60 CNY
    assert abs(gpt['total_cost'] - 1.60) < 1e-6
    # sorted by total_cost desc: gpt-4o (1.60) before claude (0.60)
    assert result['rows'][0]['model'] == 'gpt-4o'


def test_hourly_only_hours_with_usage(monkeypatch):
    rows = [_row(datetime(2026, 9, 2, 5, 0), 'openai', 'gpt-4o', 10, 5, 0.01)]
    monkeypatch.setattr(h, '_billing_token_service', lambda: _FakeSvc(rows))
    monkeypatch.setattr(h, '_display_currency_fields', lambda c: {'cost': round(c, 4), 'currency': 'USD'})
    resp = h.handle_get_billing_hourly(create_request('x'), {'date': '2026-09-02', 'tz_offset_minutes': 0})
    hours = resp['result']['hours']
    assert len(hours) == 1 and hours[0]['hour'] == 5


def test_no_service_returns_empty(monkeypatch):
    monkeypatch.setattr(h, '_billing_token_service', lambda: None)
    monkeypatch.setattr(h, '_display_currency_fields', lambda c: {'cost': 0.0, 'currency': 'USD'})
    resp = h.handle_get_billing_daily(create_request('x'), {'year': 2026, 'month': 9, 'tz_offset_minutes': 0})
    assert resp['result']['days'] == []
