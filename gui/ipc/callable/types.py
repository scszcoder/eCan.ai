"""
Callable types definition
Define types for callable functions
"""

from typing import TypedDict, Optional, Dict, Any, List, Union

class JsonSchema(TypedDict, total=False):
    """JSON Schema type definition"""
    type: str
    properties: Dict[str, 'JsonSchema']
    required: List[str]
    items: 'JsonSchema'
    enum: List[Any]
    description: str

class CallableFunction(TypedDict, total=False):
    """Callable function type definition"""
    name: str
    desc: str
    params: JsonSchema
    returns: JsonSchema
    type: str  # 'system' or 'custom'
    sysId: Optional[str]  # System function identifier
    code: Optional[str]  # Custom function code

class CallableFilter(TypedDict, total=False):
    """Callable function filter conditions"""
    text: Optional[str]  # Text search condition
    type: Optional[str]  # Type filter condition 