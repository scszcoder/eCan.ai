"""
LLM Token Usage IPC Handlers
Handles fetching monthly LLM token usage statistics
"""
from typing import Any, Optional, Dict
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger
from datetime import datetime, timedelta
from pathlib import Path
import json


# Display currency (2026-08-30): costs are STORED in USD (token_tracker's
# pricing table); CN builds display RMB. Conversion happens here at the API
# boundary so every usage endpoint reports the same currency and the frontend
# just renders what it gets.
_USD_TO_CNY = 7.25


def _display_currency_fields(cost_usd: float) -> Dict[str, Any]:
    """{'cost', 'currency'} in the app variant's display currency."""
    try:
        from utils.app_env import is_cn
        if is_cn():
            return {'cost': round(float(cost_usd or 0.0) * _USD_TO_CNY, 4), 'currency': 'CNY'}
    except Exception:
        pass
    return {'cost': round(float(cost_usd or 0.0), 4), 'currency': 'USD'}


# Placeholder pricing (per 1K tokens)
DEFAULT_PRICING = {
    'gpt-4': {'input': 0.03, 'output': 0.06},
    'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
    'gpt-3.5-turbo': {'input': 0.0005, 'output': 0.0015},
    'claude-3-opus': {'input': 0.015, 'output': 0.075},
    'claude-3-sonnet': {'input': 0.003, 'output': 0.015},
    'default': {'input': 0.01, 'output': 0.02}  # Fallback pricing
}


def calculate_cost(input_tokens: int, output_tokens: int, model: str = 'default') -> float:
    """Calculate cost in USD based on token counts and model pricing"""
    pricing = DEFAULT_PRICING.get(model, DEFAULT_PRICING['default'])
    input_cost = (input_tokens / 1000) * pricing['input']
    output_cost = (output_tokens / 1000) * pricing['output']
    return input_cost + output_cost


@IPCHandlerRegistry.handler('llm.getMonthlyTokenUsage')
def handle_get_monthly_token_usage(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get monthly LLM token usage statistics
    
    Args:
        request: IPC request
        params: {
            'month': int (optional) - Month (1-12), defaults to current month
            'year': int (optional) - Year, defaults to current year
        }
    
    Returns:
        IPCResponse with token usage data:
        {
            'input_tokens': int,
            'output_tokens': int,
            'total_tokens': int,
            'cost_usd': float,
            'month': int,
            'year': int
        }
    """
    try:
        from app_context import AppContext
        
        now = datetime.now()
        month = params.get('month', now.month) if params else now.month
        year = params.get('year', now.year) if params else now.year
        
        # Get token usage service from database manager
        ec_db_mgr = AppContext.get_ec_db_mgr()
        if not ec_db_mgr or not hasattr(ec_db_mgr, 'token_usage_service'):
            logger.warning("[llm_token_usage] Token usage service not available, returning zeros")
            return create_success_response(request, {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'cost_usd': 0.0,
                'month': month,
                'year': year
            })
        
        # Query database for monthly usage
        token_service = ec_db_mgr.token_usage_service
        usage_data = token_service.get_monthly_usage(year, month)
        usage_data.update(_display_currency_fields(usage_data.get('cost_usd', 0.0)))

        logger.info(f"[llm_token_usage] Monthly usage for {year}-{month:02d}: "
                   f"{usage_data['total_tokens']:,} tokens "
                   f"({usage_data['cost']:.2f} {usage_data['currency']})")

        return create_success_response(request, usage_data)
        
    except Exception as e:
        logger.error(f"[llm_token_usage] Error getting monthly token usage: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_USAGE_ERROR', str(e))


# Token alarm config file path
TOKEN_ALARM_CONFIG_PATH = Path(__file__).resolve().parents[3] / 'config' / 'token_alarm_config.json'

DEFAULT_ALARM_LEVELS = {
    'daily_token_limit': 500000,
    'monthly_token_limit': 10000000
}


def _load_alarm_config() -> Dict[str, int]:
    """Load token alarm configuration from JSON file, or return defaults."""
    try:
        if TOKEN_ALARM_CONFIG_PATH.exists():
            with open(TOKEN_ALARM_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"[llm_token_usage] Failed to load alarm config: {e}")
    return DEFAULT_ALARM_LEVELS.copy()


def _save_alarm_config(config: Dict[str, int]) -> None:
    """Save token alarm configuration to JSON file."""
    TOKEN_ALARM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_ALARM_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


@IPCHandlerRegistry.handler('llm.getTokenUsageTimeSeries')
def handle_get_token_usage_time_series(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get token usage time series for bar chart display.

    Params:
        period: str - '24h', '3d', '1w', '1m', '12m', '36m'

    Returns: {
        'series': [{period, input_tokens, output_tokens, total_tokens, cost_usd, invocation_count}],
        'granularity': str  ('hour', 'day', 'month')
    }
    """
    try:
        from app_context import AppContext

        period_map = {
            '24h': (timedelta(hours=24), 'hour'),
            '3d': (timedelta(days=3), 'hour'),
            '1w': (timedelta(weeks=1), 'day'),
            '1m': (timedelta(days=30), 'day'),
            '12m': (timedelta(days=365), 'month'),
            '36m': (timedelta(days=1095), 'month'),
        }

        period = params.get('period', '1m') if params else '1m'
        if period not in period_map:
            period = '1m'

        delta, granularity = period_map[period]
        now = datetime.now()
        start = now - delta
        end = now

        ec_db_mgr = AppContext.get_ec_db_mgr()
        if not ec_db_mgr or not hasattr(ec_db_mgr, 'token_usage_service'):
            logger.warning("[llm_token_usage] Token usage service not available, returning empty series")
            return create_success_response(request, {
                'series': [],
                'granularity': granularity
            })

        token_service = ec_db_mgr.token_usage_service
        series = token_service.get_time_series_usage(start, end, granularity)
        for point in series:
            point.update(_display_currency_fields(point.get('cost_usd', 0.0)))

        logger.info(f"[llm_token_usage] Time series for period={period}, granularity={granularity}: "
                    f"{len(series)} data points")

        return create_success_response(request, {
            'series': series,
            'granularity': granularity,
            'currency': _display_currency_fields(0.0)['currency'],
        })

    except Exception as e:
        logger.error(f"[llm_token_usage] Error getting token usage time series: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_USAGE_ERROR', str(e))


@IPCHandlerRegistry.handler('llm.getTokenUsageBreakdown')
def handle_get_token_usage_breakdown(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get token usage breakdown by model and skill for a specific period.

    Params:
        start: str - ISO datetime string for period start
        end: str - ISO datetime string for period end
        (If not provided, defaults to last 24 hours)

    Returns: {
        'by_model': [{vendor, model, total_tokens, cost_usd, count}],
        'by_skill': [{skill_name, total_tokens, cost_usd, count}],
        'total_invocations': int
    }
    """
    try:
        from app_context import AppContext

        now = datetime.now()

        if params and params.get('start') and params.get('end'):
            start = datetime.fromisoformat(params['start'])
            end = datetime.fromisoformat(params['end'])
        else:
            start = now - timedelta(hours=24)
            end = now

        ec_db_mgr = AppContext.get_ec_db_mgr()
        if not ec_db_mgr or not hasattr(ec_db_mgr, 'token_usage_service'):
            logger.warning("[llm_token_usage] Token usage service not available, returning empty breakdown")
            return create_success_response(request, {
                'by_model': [],
                'by_skill': [],
                'total_invocations': 0
            })

        token_service = ec_db_mgr.token_usage_service
        breakdown = token_service.get_breakdown_for_period(start, end)
        for row in breakdown.get('by_model', []) + breakdown.get('by_skill', []):
            row.update(_display_currency_fields(row.get('cost_usd', 0.0)))
        breakdown['currency'] = _display_currency_fields(0.0)['currency']

        logger.info(f"[llm_token_usage] Breakdown for {start.isoformat()} to {end.isoformat()}: "
                    f"{breakdown.get('total_invocations', 0)} invocations")

        return create_success_response(request, breakdown)

    except Exception as e:
        logger.error(f"[llm_token_usage] Error getting token usage breakdown: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_USAGE_ERROR', str(e))


@IPCHandlerRegistry.handler('llm.getTokenUsageAlarms')
def handle_get_token_usage_alarms(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get current daily and monthly usage with alarm levels.

    Returns: {
        'daily': {input_tokens, output_tokens, total_tokens, cost_usd},
        'monthly': {input_tokens, output_tokens, total_tokens, cost_usd, month, year},
        'alarm_levels': {daily_token_limit, monthly_token_limit}
    }
    """
    try:
        from app_context import AppContext

        now = datetime.now()

        ec_db_mgr = AppContext.get_ec_db_mgr()
        if not ec_db_mgr or not hasattr(ec_db_mgr, 'token_usage_service'):
            logger.warning("[llm_token_usage] Token usage service not available, returning zeros")
            return create_success_response(request, {
                'daily': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost_usd': 0.0},
                'monthly': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost_usd': 0.0,
                            'month': now.month, 'year': now.year},
                'alarm_levels': _load_alarm_config()
            })

        token_service = ec_db_mgr.token_usage_service
        daily = token_service.get_daily_usage()
        monthly = token_service.get_monthly_usage(now.year, now.month)
        daily.update(_display_currency_fields(daily.get('cost_usd', 0.0)))
        monthly.update(_display_currency_fields(monthly.get('cost_usd', 0.0)))
        alarm_levels = _load_alarm_config()

        logger.info(f"[llm_token_usage] Alarms - daily: {daily.get('total_tokens', 0):,} tokens, "
                    f"monthly: {monthly.get('total_tokens', 0):,} tokens")

        return create_success_response(request, {
            'daily': daily,
            'monthly': monthly,
            'alarm_levels': alarm_levels
        })

    except Exception as e:
        logger.error(f"[llm_token_usage] Error getting token usage alarms: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_USAGE_ERROR', str(e))


@IPCHandlerRegistry.handler('llm.setTokenAlarmLevels')
def handle_set_token_alarm_levels(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Set alarm levels for token usage.

    Params:
        daily_token_limit: int
        monthly_token_limit: int
    """
    try:
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Parameters required: daily_token_limit, monthly_token_limit')

        daily_limit = params.get('daily_token_limit')
        monthly_limit = params.get('monthly_token_limit')

        if daily_limit is None or monthly_limit is None:
            return create_error_response(request, 'INVALID_PARAMS',
                                         'Both daily_token_limit and monthly_token_limit are required')

        config = {
            'daily_token_limit': int(daily_limit),
            'monthly_token_limit': int(monthly_limit)
        }

        _save_alarm_config(config)

        logger.info(f"[llm_token_usage] Alarm levels updated: daily={config['daily_token_limit']:,}, "
                    f"monthly={config['monthly_token_limit']:,}")

        return create_success_response(request, config)

    except Exception as e:
        logger.error(f"[llm_token_usage] Error setting token alarm levels: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_USAGE_ERROR', str(e))


# ─── Billing drill-down (2026-09-06): daily → hourly → per-model ──────────────
# Reads the local token_usage DB. Buckets by the CLIENT's local timezone (the
# rows store UTC in usage_timestamp), and splits each (vendor, model) group's
# authoritative stored cost_usd into an input/output share. The split RATIO
# uses a compact price map — even if a price is stale the group TOTAL is always
# the stored cost_usd, so only the apportionment shifts, never the billed total.
# Top-ups are server-side (cloud getBillingHistory); the frontend merges those
# into the day rows. See docs/BILLING_TOPUP_API_CONTRACT.md.

# Ratio-only per-1K USD prices (input, output). Total cost is authoritative from
# the DB; this table only decides how a group's total is split in/out.
_SPLIT_PRICING = {
    'openai': {
        'gpt-5': (0.005, 0.015), 'gpt-4.1': (0.002, 0.008), 'gpt-4o': (0.005, 0.015),
        'gpt-4o-mini': (0.00015, 0.0006), 'gpt-4-turbo': (0.01, 0.03),
        'gpt-4': (0.03, 0.06), 'gpt-3.5-turbo': (0.0005, 0.0015),
        'o4-mini': (0.0011, 0.0044), 'o3': (0.002, 0.008),
        'text-embedding-3-small': (0.00002, 0.0), 'text-embedding-3-large': (0.00013, 0.0),
    },
    'anthropic': {
        'claude-3-opus': (0.015, 0.075), 'claude-3-sonnet': (0.003, 0.015),
        'claude-3-haiku': (0.00025, 0.00125),
    },
    'deepseek': {'deepseek-chat': (0.00014, 0.00028), 'deepseek-coder': (0.00014, 0.00028)},
    'google': {'gemini-pro': (0.00025, 0.0005), 'gemini-1.5-pro': (0.00125, 0.005)},
    'default': (0.01, 0.02),
}


def _split_price(vendor, model):
    """(input_price, output_price) per 1K tokens for the split ratio only."""
    vmap = _SPLIT_PRICING.get((vendor or '').lower())
    if isinstance(vmap, dict):
        ml = (model or '').lower()
        for key, price in vmap.items():
            if key in ml:
                return price
    return _SPLIT_PRICING['default']


def _split_cost(cost_usd, in_tokens, out_tokens, vendor, model):
    """Apportion an authoritative *cost_usd* into (input_cost, output_cost) so
    the two always sum back to cost_usd."""
    pin, pout = _split_price(vendor, model)
    w_in = (in_tokens / 1000.0) * pin
    w_out = (out_tokens / 1000.0) * pout
    denom = w_in + w_out
    if denom <= 0:
        tt = (in_tokens + out_tokens) or 1
        frac_in = in_tokens / tt
    else:
        frac_in = w_in / denom
    in_cost = round(cost_usd * frac_in, 6)
    out_cost = round(cost_usd - in_cost, 6)
    return in_cost, out_cost


def _tz_window(local_dt, offset_min):
    """UTC datetime for a local naive datetime given the client's tz offset
    (minutes east of UTC, i.e. JS -getTimezoneOffset())."""
    return local_dt - timedelta(minutes=int(offset_min or 0))


def _local(ts, offset_min):
    """Shift a stored UTC timestamp into the client's local wall clock."""
    return ts + timedelta(minutes=int(offset_min or 0))


def _cost_display(cost_usd):
    """Cost in the app variant's display currency (RMB on CN, else USD)."""
    return _display_currency_fields(cost_usd).get('cost', round(cost_usd, 4))


def _billing_token_service():
    from app_context import AppContext
    ec_db_mgr = AppContext.get_ec_db_mgr()
    if not ec_db_mgr or not hasattr(ec_db_mgr, 'token_usage_service'):
        return None
    return ec_db_mgr.token_usage_service


@IPCHandlerRegistry.handler('llm.getBillingDaily')
def handle_get_billing_daily(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Per-day usage totals for a local month.

    Params: { year:int, month:int, tz_offset_minutes:int }
    Returns: { currency, days:[{date, input_tokens, output_tokens, total_tokens, cost, cost_usd}] }
    """
    try:
        p = params or {}
        now = datetime.utcnow()
        year = int(p.get('year') or now.year)
        month = int(p.get('month') or now.month)
        off = int(p.get('tz_offset_minutes') or 0)

        svc = _billing_token_service()
        if not svc:
            return create_success_response(request, {'currency': _display_currency_fields(0.0)['currency'], 'days': []})

        local_start = datetime(year, month, 1)
        local_end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
        rows = svc.get_usage_rows(_tz_window(local_start, off), _tz_window(local_end, off))

        by_day = {}
        for r in rows:
            d = _local(r['usage_timestamp'], off).strftime('%Y-%m-%d')
            b = by_day.setdefault(d, {'date': d, 'input_tokens': 0, 'output_tokens': 0,
                                      'total_tokens': 0, 'cost_usd': 0.0})
            b['input_tokens'] += r['input_tokens']
            b['output_tokens'] += r['output_tokens']
            b['total_tokens'] += r['total_tokens']
            b['cost_usd'] += r['cost_usd']

        days = []
        for d in sorted(by_day):
            b = by_day[d]
            b['cost_usd'] = round(b['cost_usd'], 6)
            b['cost'] = _cost_display(b['cost_usd'])
            days.append(b)
        return create_success_response(request, {
            'currency': _display_currency_fields(0.0)['currency'],
            'year': year, 'month': month, 'days': days,
        })
    except Exception as e:
        logger.error(f"[llm_token_usage] getBillingDaily error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_USAGE_ERROR', str(e))


@IPCHandlerRegistry.handler('llm.getBillingHourly')
def handle_get_billing_hourly(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """24 hourly usage totals for a local day (only hours with usage).

    Params: { date:"YYYY-MM-DD", tz_offset_minutes:int }
    Returns: { currency, date, hours:[{hour, input_tokens, output_tokens, total_tokens, cost, cost_usd}] }
    """
    try:
        p = params or {}
        off = int(p.get('tz_offset_minutes') or 0)
        date_str = str(p.get('date') or datetime.utcnow().strftime('%Y-%m-%d'))
        local_start = datetime.strptime(date_str, '%Y-%m-%d')
        local_end = local_start + timedelta(days=1)

        svc = _billing_token_service()
        if not svc:
            return create_success_response(request, {'currency': _display_currency_fields(0.0)['currency'], 'date': date_str, 'hours': []})

        rows = svc.get_usage_rows(_tz_window(local_start, off), _tz_window(local_end, off))
        by_hour = {}
        for r in rows:
            h = _local(r['usage_timestamp'], off).hour
            b = by_hour.setdefault(h, {'hour': h, 'input_tokens': 0, 'output_tokens': 0,
                                       'total_tokens': 0, 'cost_usd': 0.0})
            b['input_tokens'] += r['input_tokens']
            b['output_tokens'] += r['output_tokens']
            b['total_tokens'] += r['total_tokens']
            b['cost_usd'] += r['cost_usd']

        hours = []
        for h in sorted(by_hour):
            b = by_hour[h]
            b['cost_usd'] = round(b['cost_usd'], 6)
            b['cost'] = _cost_display(b['cost_usd'])
            hours.append(b)
        return create_success_response(request, {
            'currency': _display_currency_fields(0.0)['currency'],
            'date': date_str, 'hours': hours,
        })
    except Exception as e:
        logger.error(f"[llm_token_usage] getBillingHourly error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_USAGE_ERROR', str(e))


@IPCHandlerRegistry.handler('llm.getBillingHourModels')
def handle_get_billing_hour_models(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Per-(vendor, model) rows for one local hour of one local day.

    Params: { date:"YYYY-MM-DD", hour:0..23, tz_offset_minutes:int }
    Returns: { currency, rows:[{vendor, model, input_tokens, output_tokens,
                                input_cost, output_cost, total_cost}] }
    (input_cost/output_cost are the display currency; they sum to total_cost.)
    """
    try:
        p = params or {}
        off = int(p.get('tz_offset_minutes') or 0)
        date_str = str(p.get('date') or datetime.utcnow().strftime('%Y-%m-%d'))
        hour = int(p.get('hour'))
        local_start = datetime.strptime(date_str, '%Y-%m-%d') + timedelta(hours=hour)
        local_end = local_start + timedelta(hours=1)

        svc = _billing_token_service()
        if not svc:
            return create_success_response(request, {'currency': _display_currency_fields(0.0)['currency'], 'rows': []})

        rows = svc.get_usage_rows(_tz_window(local_start, off), _tz_window(local_end, off))
        by_model = {}
        for r in rows:
            key = (r['vendor'], r['model'])
            b = by_model.setdefault(key, {'vendor': r['vendor'], 'model': r['model'],
                                          'input_tokens': 0, 'output_tokens': 0, 'cost_usd': 0.0})
            b['input_tokens'] += r['input_tokens']
            b['output_tokens'] += r['output_tokens']
            b['cost_usd'] += r['cost_usd']

        out_rows = []
        for b in by_model.values():
            in_cost_usd, out_cost_usd = _split_cost(
                b['cost_usd'], b['input_tokens'], b['output_tokens'], b['vendor'], b['model'])
            out_rows.append({
                'vendor': b['vendor'], 'model': b['model'],
                'input_tokens': b['input_tokens'], 'output_tokens': b['output_tokens'],
                'input_cost': _cost_display(in_cost_usd),
                'output_cost': _cost_display(out_cost_usd),
                'total_cost': _cost_display(round(b['cost_usd'], 6)),
            })
        out_rows.sort(key=lambda x: x['total_cost'], reverse=True)
        return create_success_response(request, {
            'currency': _display_currency_fields(0.0)['currency'],
            'date': date_str, 'hour': hour, 'rows': out_rows,
        })
    except Exception as e:
        logger.error(f"[llm_token_usage] getBillingHourModels error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_USAGE_ERROR', str(e))
