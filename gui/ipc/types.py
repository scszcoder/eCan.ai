"""
IPC Communication Type Definitions
"""

from typing import TypedDict, Union, Optional, Dict, Any, Literal
from datetime import datetime
import uuid

# IPC error information
class IPCError(TypedDict):
    code: Union[int, str]  # Error code
    message: str          # Error description
    details: Optional[Any]  # Additional error context

# IPC request
class IPCRequest(TypedDict):
    id: str              # Globally unique request identifier
    type: Literal['request', 'response']  # Request type
    method: str          # Interface name to call
    params: Optional[Any]  # Request parameters
    meta: Optional[Dict[str, Any]]  # Extended metadata
    timestamp: Optional[int]  # Send timestamp in ms

# IPC response
class IPCResponse(TypedDict):
    id: str              # Same ID as request
    method: Optional[str]  # Echo request's method
    status: Literal['success', 'pending', 'error']  # Call result status
    result: Optional[Any]  # Normal return data (required when status=success)
    error: Optional[IPCError]  # Error information (required when status=error)
    meta: Optional[Dict[str, Any]]  # Extended metadata
    timestamp: Optional[int]  # Send timestamp in ms

def create_request(method: str, params: Optional[Any] = None, meta: Optional[Dict[str, Any]] = None) -> IPCRequest:
    """Create IPC request

    Args:
        method: Interface name to call
        params: Request parameters
        meta: Extended metadata

    Returns:
        IPCRequest: Request object
    """
    return {
        'id': str(uuid.uuid4()),
        'type': 'request',
        'method': method,
        'params': params,
        'meta': meta,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }

def create_success_response(request: IPCRequest, result: Any, meta: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Create success response

    Args:
        request: Original request
        result: Return result
        meta: Extended metadata

    Returns:
        IPCResponse: Response object
    """
    return {
        'id': request['id'],
        'type': 'response',
        'method': request['method'],
        'status': 'success',
        'result': result,
        'meta': meta,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }

def create_error_response(request: IPCRequest, code: Union[int, str], message: str, details: Optional[Any] = None, meta: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Create error response

    Args:
        request: Original request
        code: Error code
        message: Error description
        details: Additional error context
        meta: Extended metadata

    Returns:
        IPCResponse: Response object
    """
    return {
        'id': request['id'],
        'type': 'response',
        'method': request['method'],
        'status': 'error',
        'error': {
            'code': code,
            'message': message,
            'details': details
        },
        'meta': meta,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }

def create_pending_response(request: IPCRequest, message: str, details: Any = None, meta: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Create pending response

    Args:
        request: Original request
        message: Description message
        details: Additional information
        meta: Extended metadata
    Returns:
        IPCResponse: Response object
    """
    return {
        'id': request['id'],
        'type': 'response',
        'method': request['method'],
        'status': 'pending',
        'result': {
            'message': message,
            'details': details
        },
        'meta': meta,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }