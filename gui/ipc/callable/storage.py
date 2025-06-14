"""
Callable storage management
Manage storage of callable functions
"""

from typing import List, Dict, Optional
from .types import CallableFunction
from utils.logger_helper import logger_helper

logger = logger_helper.logger

class CallableStorage:
    """Callable function storage management class"""
    
    def __init__(self):
        self._system_callables: Dict[str, CallableFunction] = {}
        self._custom_callables: Dict[str, CallableFunction] = {}
        logger.debug("Initializing CallableStorage")
        self._initialize_system_callables()
        self._initialize_custom_callables()
        logger.debug(f"Initialized with {len(self._system_callables)} system callables and {len(self._custom_callables)} custom callables")
    
    def _initialize_system_callables(self):
        """Initialize system functions"""
        logger.debug("Initializing system callables")
        self._system_callables = {
            'send_message': {
                'name': 'send_message',
                'desc': 'Send message to specified target',
                'params': {
                    'type': 'object',
                    'properties': {
                        'target': {
                            'type': 'string',
                            'description': 'Message recipient'
                        },
                        'content': {
                            'type': 'string',
                            'description': 'Message content'
                        }
                    },
                    'required': ['target', 'content']
                },
                'returns': {
                    'type': 'object',
                    'properties': {
                        'success': {
                            'type': 'boolean',
                            'description': 'Whether the message was sent successfully'
                        },
                        'message': {
                            'type': 'string',
                            'description': 'Description of the sending result'
                        }
                    }
                },
                'type': 'system',
                'sysId': 'sys_001',
                'code': '''
async def send_message(target: str, content: str) -> dict:
    """
    Send message to specified target
    
    Args:
        target: Message recipient
        content: Message content
        
    Returns:
        dict: Dictionary containing the sending result
    """
    try:
        # Implement message sending logic
        # TODO: Implement actual message sending
        return {
            'success': True,
            'message': f'Message sent to {target}'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Failed to send message: {str(e)}'
        }
'''
            },
            'get_weather': {
                'name': 'get_weather',
                'desc': 'Get weather information for specified city',
                'params': {
                    'type': 'object',
                    'properties': {
                        'city': {
                            'type': 'string',
                            'description': 'City name'
                        },
                        'date': {
                            'type': 'string',
                            'description': 'Date (optional, defaults to today)',
                            'format': 'YYYY-MM-DD'
                        }
                    },
                    'required': ['city']
                },
                'returns': {
                    'type': 'object',
                    'properties': {
                        'temperature': {
                            'type': 'number',
                            'description': 'Temperature in Celsius'
                        },
                        'weather': {
                            'type': 'string',
                            'description': 'Weather condition'
                        },
                        'humidity': {
                            'type': 'number',
                            'description': 'Humidity percentage'
                        }
                    }
                },
                'type': 'system',
                'sysId': 'sys_002',
                'code': '''
async def get_weather(city: str, date: str = None) -> dict:
    """
    Get weather information for specified city
    
    Args:
        city: City name
        date: Date (optional, defaults to today)
        
    Returns:
        dict: Dictionary containing weather information
    """
    try:
        # Implement weather query logic
        # TODO: Implement actual weather query
        return {
            'temperature': 25.5,
            'weather': 'Sunny',
            'humidity': 65
        }
    except Exception as e:
        raise Exception(f'Failed to get weather: {str(e)}')
'''
            },
            'process_data': {
                'name': 'process_data',
                'desc': 'Process input data and return results',
                'params': {
                    'type': 'object',
                    'properties': {
                        'data': {
                            'type': 'array',
                            'description': 'Data array to process',
                            'items': {
                                'type': 'number'
                            }
                        },
                        'operation': {
                            'type': 'string',
                            'description': 'Processing operation type',
                            'enum': ['sum', 'average', 'max', 'min']
                        }
                    },
                    'required': ['data', 'operation']
                },
                'returns': {
                    'type': 'object',
                    'properties': {
                        'result': {
                            'type': 'number',
                            'description': 'Processing result'
                        },
                        'processed_count': {
                            'type': 'integer',
                            'description': 'Number of processed data items'
                        }
                    }
                },
                'type': 'system',
                'sysId': 'sys_003',
                'code': '''
async def process_data(data: list, operation: str) -> dict:
    """
    Process input data and return results
    
    Args:
        data: Data array to process
        operation: Processing operation type
        
    Returns:
        dict: Dictionary containing processing results
    """
    try:
        if not data:
            raise ValueError('Data array cannot be empty')
            
        if operation == 'sum':
            result = sum(data)
        elif operation == 'average':
            result = sum(data) / len(data)
        elif operation == 'max':
            result = max(data)
        elif operation == 'min':
            result = min(data)
        else:
            raise ValueError(f'Invalid operation: {operation}')
            
        return {
            'result': result,
            'processed_count': len(data)
        }
    except Exception as e:
        raise Exception(f'Failed to process data: {str(e)}')
'''
            },
            'search_database': {
                'name': 'search_database',
                'desc': 'Search records in database',
                'params': {
                    'type': 'object',
                    'properties': {
                        'query': {
                            'type': 'string',
                            'description': 'Search query string'
                        },
                        'filters': {
                            'type': 'object',
                            'description': 'Search filter conditions',
                            'properties': {
                                'date_range': {
                                    'type': 'object',
                                    'properties': {
                                        'start': {
                                            'type': 'string',
                                            'format': 'YYYY-MM-DD'
                                        },
                                        'end': {
                                            'type': 'string',
                                            'format': 'YYYY-MM-DD'
                                        }
                                    }
                                },
                                'category': {
                                    'type': 'string'
                                }
                            }
                        },
                        'limit': {
                            'type': 'integer',
                            'description': 'Maximum number of results to return',
                            'minimum': 1,
                            'maximum': 100
                        }
                    },
                    'required': ['query']
                },
                'returns': {
                    'type': 'object',
                    'properties': {
                        'results': {
                            'type': 'array',
                            'description': 'Array of search results',
                            'items': {
                                'type': 'object'
                            }
                        },
                        'total': {
                            'type': 'integer',
                            'description': 'Total number of matching records'
                        }
                    }
                },
                'type': 'system',
                'sysId': 'sys_004',
                'code': '''
async def search_database(query: str, filters: dict = None, limit: int = 10) -> dict:
    """
    Search records in database
    
    Args:
        query: Search query string
        filters: Search filter conditions
        limit: Maximum number of results to return
        
    Returns:
        dict: Dictionary containing search results
    """
    try:
        # Implement database search logic
        # TODO: Implement actual database search
        return {
            'results': [
                {
                    'id': 1,
                    'title': 'Sample Result',
                    'content': 'This is a sample search result'
                }
            ],
            'total': 1
        }
    except Exception as e:
        raise Exception(f'Failed to search database: {str(e)}')
'''
            }
        }
    
    def _initialize_custom_callables(self):
        """Initialize custom functions"""
        custom_callables = [
            {
                "name": "custom_processor",
                "desc": "Custom data processing function",
                "params": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "string",
                            "description": "Input data"
                        },
                        "transform": {
                            "type": "string",
                            "enum": ["uppercase", "lowercase", "capitalize"],
                            "description": "Transformation method"
                        }
                    },
                    "required": ["data", "transform"]
                },
                "returns": {
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "string",
                            "description": "Processing result"
                        },
                        "original": {
                            "type": "string",
                            "description": "Original data"
                        }
                    }
                },
                "type": "custom",
                "code": """
function process(data, transform) {
    let result = data;
    switch(transform) {
        case 'uppercase':
            result = data.toUpperCase();
            break;
        case 'lowercase':
            result = data.toLowerCase();
            break;
        case 'capitalize':
            result = data.charAt(0).toUpperCase() + data.slice(1);
            break;
    }
    return {
        result: result,
        original: data
    };
}
"""
            },
            {
                "name": "data_validator",
                "desc": "Data validation function",
                "params": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "object",
                            "description": "Data to validate"
                        },
                        "rules": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string"},
                                    "type": {"type": "string"},
                                    "required": {"type": "boolean"},
                                    "min": {"type": "number"},
                                    "max": {"type": "number"}
                                }
                            },
                            "description": "Validation rules"
                        }
                    },
                    "required": ["data", "rules"]
                },
                "returns": {
                    "type": "object",
                    "properties": {
                        "valid": {
                            "type": "boolean",
                            "description": "Whether validation passed"
                        },
                        "errors": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string"},
                                    "message": {"type": "string"}
                                }
                            },
                            "description": "Error information"
                        }
                    }
                },
                "type": "custom",
                "code": """
function validate(data, rules) {
    const errors = [];
    for (const rule of rules) {
        const value = data[rule.field];
        
        // Check required
        if (rule.required && (value === undefined || value === null || value === '')) {
            errors.push({
                field: rule.field,
                message: `${rule.field} is required`
            });
            continue;
        }
        
        // Check type
        if (value !== undefined && value !== null) {
            if (rule.type === 'number' && typeof value !== 'number') {
                errors.push({
                    field: rule.field,
                    message: `${rule.field} must be a number`
                });
            }
            
            // Check range
            if (rule.type === 'number') {
                if (rule.min !== undefined && value < rule.min) {
                    errors.push({
                        field: rule.field,
                        message: `${rule.field} must be greater than ${rule.min}`
                    });
                }
                if (rule.max !== undefined && value > rule.max) {
                    errors.push({
                        field: rule.field,
                        message: `${rule.field} must be less than ${rule.max}`
                    });
                }
            }
        }
    }
    
    return {
        valid: errors.length === 0,
        errors: errors
    };
}
"""
            },
            {
                "name": "data_transformer",
                "desc": "Data transformation function",
                "params": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "object",
                            "description": "Input data"
                        },
                        "mapping": {
                            "type": "object",
                            "description": "Field mapping rules"
                        },
                        "options": {
                            "type": "object",
                            "properties": {
                                "removeNull": {"type": "boolean"},
                                "defaultValue": {"type": "any"}
                            }
                        }
                    },
                    "required": ["data", "mapping"]
                },
                "returns": {
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "object",
                            "description": "Transformed data"
                        },
                        "mapping": {
                            "type": "object",
                            "description": "Used mapping rules"
                        }
                    }
                },
                "type": "custom",
                "code": """
function transform(data, mapping, options = {}) {
    const result = {};
    const { removeNull = false, defaultValue = null } = options;
    
    for (const [targetField, sourceField] of Object.entries(mapping)) {
        let value = data[sourceField];
        
        if (value === undefined || value === null) {
            value = defaultValue;
        }
        
        if (!(removeNull && value === null)) {
            result[targetField] = value;
        }
    }
    
    return {
        result: result,
        mapping: mapping
    };
}
"""
            }
        ]
        
        for callable in custom_callables:
            self._custom_callables[callable['name']] = callable
    
    def get_all_callables(self) -> List[CallableFunction]:
        """Get all callable functions list
        
        Returns:
            List[CallableFunction]: List of all callable functions
        """
        # Merge system functions and custom functions
        all_callables = list(self._system_callables.values()) + list(self._custom_callables.values())
        return all_callables
    
    def get_system_callables(self) -> List[CallableFunction]:
        """Get system functions"""
        return list(self._system_callables.values())
    
    def get_custom_callables(self) -> List[CallableFunction]:
        """Get custom functions"""
        return list(self._custom_callables.values())
    
    def add_custom_callable(self, callable: CallableFunction) -> bool:
        """Add custom function
        
        Args:
            callable: Callable function definition
            
        Returns:
            bool: Whether the function was added successfully
        """
        if callable['name'] in self._system_callables:
            return False
        
        self._custom_callables[callable['name']] = callable
        return True
    
    def remove_custom_callable(self, name: str) -> bool:
        """Remove custom function
        
        Args:
            name: Function name
            
        Returns:
            bool: Whether the function was removed successfully
        """
        if name in self._custom_callables:
            del self._custom_callables[name]
            return True
        return False
    
    def get_callable(self, name: str) -> Optional[CallableFunction]:
        """Get function by name
        
        Args:
            name: Function name
            
        Returns:
            Optional[CallableFunction]: Function definition, returns None if it doesn't exist
        """
        return self._system_callables.get(name) or self._custom_callables.get(name) 