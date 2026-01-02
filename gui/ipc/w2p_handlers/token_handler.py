"""
Token Management IPC Handlers
Handles token refresh and extension operations
"""
from typing import Any, Optional, Dict
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from gui.ipc.token_manager import token_manager
from utils.logger_helper import logger_helper as logger


@IPCHandlerRegistry.handler('auth.refreshToken')
def handle_refresh_token(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Refresh user token - generate new token with extended validity
    
    Args:
        request: IPC request
        params: {
            'token': str  # Current token to refresh
        }
    
    Returns:
        IPCResponse with new token or error
    """
    try:
        if not params or 'token' not in params:
            return create_error_response(request, 'MISSING_TOKEN', 'Token is required')
        
        current_token = params['token']
        
        # Refresh token
        new_token = token_manager.refresh_token(current_token)
        
        if not new_token:
            return create_error_response(
                request, 
                'REFRESH_FAILED', 
                'Failed to refresh token. Token may be invalid or expired.'
            )
        
        # Get user info with new token
        user_info = token_manager.get_user_info(new_token)
        
        logger.info(f"[token_handler] Token refreshed for user: {user_info['username']}")
        
        return create_success_response(request, {
            'token': new_token,
            'username': user_info['username'],
            'role': user_info['role'],
            'message': 'Token refreshed successfully'
        })
        
    except Exception as e:
        logger.error(f"[token_handler] Error refreshing token: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'REFRESH_ERROR', str(e))


@IPCHandlerRegistry.handler('auth.extendToken')
def handle_extend_token(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Extend current token validity period
    
    Args:
        request: IPC request
        params: {
            'token': str,  # Token to extend
            'seconds': int (optional)  # Seconds to extend (default: 24 hours)
        }
    
    Returns:
        IPCResponse with success status
    """
    try:
        if not params or 'token' not in params:
            return create_error_response(request, 'MISSING_TOKEN', 'Token is required')
        
        current_token = params['token']
        additional_seconds = params.get('seconds')
        
        # Extend token
        success = token_manager.extend_token(current_token, additional_seconds)
        
        if not success:
            return create_error_response(
                request, 
                'EXTEND_FAILED', 
                'Failed to extend token. Token may be invalid.'
            )
        
        # Get updated token info
        token_info = token_manager.validate_token(current_token, auto_extend=False)
        
        if token_info:
            import time
            time_remaining = token_info['expires_at'] - time.time()
            hours_remaining = time_remaining / 3600
            
            logger.info(f"[token_handler] Token extended for user: {token_info['username']}, remaining: {hours_remaining:.1f}h")
            
            return create_success_response(request, {
                'message': 'Token extended successfully',
                'expires_at': token_info['expires_at'],
                'time_remaining_seconds': int(time_remaining),
                'time_remaining_hours': round(hours_remaining, 1)
            })
        else:
            return create_error_response(request, 'EXTEND_FAILED', 'Token validation failed after extension')
        
    except Exception as e:
        logger.error(f"[token_handler] Error extending token: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'EXTEND_ERROR', str(e))


@IPCHandlerRegistry.handler('auth.getTokenInfo')
def handle_get_token_info(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get current token information including expiration time
    
    Args:
        request: IPC request
        params: {
            'token': str  # Token to query
        }
    
    Returns:
        IPCResponse with token info
    """
    try:
        if not params or 'token' not in params:
            return create_error_response(request, 'MISSING_TOKEN', 'Token is required')
        
        current_token = params['token']
        
        # Get token info without auto-extend
        token_info = token_manager.validate_token(current_token, auto_extend=False)
        
        if not token_info:
            return create_error_response(
                request, 
                'INVALID_TOKEN', 
                'Token is invalid or expired'
            )
        
        import time
        current_time = time.time()
        time_remaining = token_info['expires_at'] - current_time
        hours_remaining = time_remaining / 3600
        
        return create_success_response(request, {
            'username': token_info['username'],
            'role': token_info['role'],
            'created_at': token_info['created_at'],
            'expires_at': token_info['expires_at'],
            'last_used': token_info['last_used'],
            'time_remaining_seconds': int(time_remaining),
            'time_remaining_hours': round(hours_remaining, 1),
            'is_expiring_soon': time_remaining < 3600  # Less than 1 hour
        })
        
    except Exception as e:
        logger.error(f"[token_handler] Error getting token info: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TOKEN_INFO_ERROR', str(e))
