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
    """可调用函数的数据类
    
    Attributes:
        id: 函数ID
        name: 函数名称
        desc: 函数描述
        params: 参数定义
        returns: 返回值定义
        type: 函数类型 ('system' 或 'custom')
        code: 函数实现代码
        userId: 用户ID（可选）
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
        """转换为字典格式"""
        return asdict(self)

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CallableFunction':
        """从字典创建实例"""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> 'CallableFunction':
        """从JSON字符串创建实例"""
        data = json.loads(json_str)
        return cls.from_dict(data)

class CallableFilter(TypedDict, total=False):
    """Callable function filter conditions"""
    text: Optional[str]  # Text search condition
    type: Optional[str]  # Type filter condition 