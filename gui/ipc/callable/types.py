"""
Callable types definition
Define types for callable functions
"""

from typing import TypedDict, Optional, Dict, Any, List, Union
from dataclasses import dataclass, asdict
import json

class JsonSchema(TypedDict, total=False):
    """JSON Schema type definition"""
    type: str
    properties: Dict[str, 'JsonSchema']
    required: List[str]
    items: 'JsonSchema'
    enum: List[Any]
    description: str

@dataclass
class CallableFunction:
    """Callable function data class

    Attributes:
        id: Function ID
        name: Function name
        desc: Function description
        params: Parameter definition
        returns: Return value definition
        type: Function type ('system' or 'custom')
        code: Function implementation code
        userId: User ID (optional)
    """
    id: str
    name: str
    desc: str
    params: Dict[str, Any]
    returns: Dict[str, Any]
    type: str
    code: str
    userId: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CallableFunction':
        """Create instance from dictionary"""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> 'CallableFunction':
        """Create instance from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)

class CallableFilter(TypedDict, total=False):
    """Callable function filter conditions"""
    text: Optional[str]  # Text search condition
    type: Optional[str]  # Type filter condition 