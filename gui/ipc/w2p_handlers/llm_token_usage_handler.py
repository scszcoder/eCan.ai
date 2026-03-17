"""
LLM Token Usage IPC Handlers
Handles fetching monthly LLM token usage statistics
"""
from typing import Any, Optional, Dict
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger
from datetime import datetime


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
        
        logger.info(f"[llm_token_usage] Monthly usage for {year}-{month:02d}: "
                   f"{usage_data['total_tokens']:,} tokens (${usage_data['cost_usd']:.2f})")
        
        return create_success_response(request, usage_data)
        
    except Exception as e:
        logger.error(f"[llm_token_usage] Error getting monthly token usage: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_USAGE_ERROR', str(e))
