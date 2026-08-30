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
