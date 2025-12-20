"""
Callable function storage module
Provides storage and management for callable functions
"""

import json
import os
from typing import Dict, List, Optional, Any
from .types import CallableFunction, CallableFilter
from utils.logger_helper import logger_helper as logger

class CallableStorage:
    """Callable function storage class"""
    
    # System function definitions
    SYSTEM_FUNCTIONS = {
        'send_message': CallableFunction(
            id='send_message',
            name='send_message',
            desc='Send message to specified channel',
            params={
                'type': 'object',
                'properties': {
                    'channel_id': {
                        'type': 'string',
                        'description': 'Channel ID to send message to'
                    },
                    'content': {
                        'type': 'string',
                        'description': 'Message content to send'
                    }
                },
                'required': ['channel_id', 'content']
            },
            returns={
                'type': 'object',
                'properties': {
                    'success': {
                        'type': 'boolean',
                        'description': 'Whether the message was sent successfully'
                    },
                    'message_id': {
                        'type': 'string',
                        'description': 'ID of the sent message'
                    }
                }
            },
            type='system',
            code='''def send_message(params):
    """
    Send message to specified channel
    
    Args:
        params (dict): A dictionary containing:
            - channel_id (str): Channel ID to send message to
            - content (str): Message content to send
    
    Returns:
        dict: A dictionary containing:
            - success (bool): Whether the message was sent successfully
            - message_id (str): ID of the sent message
    """
    try:
        channel_id = params.get('channel_id')
        content = params.get('content')
        
        if not channel_id or not content:
            return {
                'success': False,
                'message_id': None
            }
            
        # TODO: Implement actual message sending logic
        
        return {
            'success': True,
            'message_id': 'msg_123'  # Example message ID
        }
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return {
            'success': False,
            'message_id': None
        }'''
        ),
        
        'get_weather': CallableFunction(
            id='get_weather',
            name='get_weather',
            desc='Get weather information for a location',
            params={
                'type': 'object',
                'properties': {
                    'location': {
                        'type': 'string',
                        'description': 'Location to get weather for'
                    },
                    'unit': {
                        'type': 'string',
                        'description': 'Temperature unit (celsius/fahrenheit)',
                        'enum': ['celsius', 'fahrenheit']
                    }
                },
                'required': ['location']
            },
            returns={
                'type': 'object',
                'properties': {
                    'temperature': {
                        'type': 'number',
                        'description': 'Current temperature'
                    },
                    'condition': {
                        'type': 'string',
                        'description': 'Weather condition'
                    },
                    'humidity': {
                        'type': 'number',
                        'description': 'Humidity percentage'
                    }
                }
            },
            type='system',
            code='''def get_weather(params):
    """
    Get weather information for a location
    
    Args:
        params (dict): A dictionary containing:
            - location (str): Location to get weather for
            - unit (str, optional): Temperature unit (celsius/fahrenheit)
    
    Returns:
        dict: A dictionary containing:
            - temperature (float): Current temperature
            - condition (str): Weather condition
            - humidity (float): Humidity percentage
    """
    try:
        location = params.get('location')
        unit = params.get('unit', 'celsius')
        
        if not location:
            raise ValueError("Location is required")
            
        # TODO: Implement actual weather API call
        
        return {
            'temperature': 25.5,
            'condition': 'Sunny',
            'humidity': 65.0
        }
        
    except Exception as e:
        logger.error(f"Error getting weather: {e}")
        raise'''
        ),
        
        'search_web': CallableFunction(
            id='search_web',
            name='search_web',
            desc='Search the web for information',
            params={
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Search query'
                    },
                    'limit': {
                        'type': 'integer',
                        'description': 'Maximum number of results to return',
                        'minimum': 1,
                        'maximum': 10
                    }
                },
                'required': ['query']
            },
            returns={
                'type': 'object',
                'properties': {
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'title': {
                                    'type': 'string',
                                    'description': 'Result title'
                                },
                                'url': {
                                    'type': 'string',
                                    'description': 'Result URL'
                                },
                                'snippet': {
                                    'type': 'string',
                                    'description': 'Result snippet'
                                }
                            }
                        }
                    },
                    'total': {
                        'type': 'integer',
                        'description': 'Total number of results found'
                    }
                }
            },
            type='system',
            code='''def search_web(params):
    """
    Search the web for information
    
    Args:
        params (dict): A dictionary containing:
            - query (str): Search query
            - limit (int, optional): Maximum number of results to return
    
    Returns:
        dict: A dictionary containing:
            - results (list): List of search results
            - total (int): Total number of results found
    """
    try:
        query = params.get('query')
        limit = params.get('limit', 5)
        
        if not query:
            raise ValueError("Query is required")
            
        # TODO: Implement actual web search
        
        return {
            'results': [
                {
                    'title': 'Example Result 1',
                    'url': 'https://example.com/1',
                    'snippet': 'This is an example search result...'
                }
            ],
            'total': 1
        }
        
    except Exception as e:
        logger.error(f"Error searching web: {e}")
        raise'''
        )
    }
    
    def __init__(self):
        """Initialize storage"""
        self._callables: Dict[str, CallableFunction] = {}
        self._init_system_callables()
        self._init_custom_callables()
        # logger.info(f"Initialized {len(self._callables)} callable functions")
        
    def _init_system_callables(self):
        """Initialize system functions"""
        for func in self.SYSTEM_FUNCTIONS.values():
            self._callables[func.id] = func
            # logger.debug(f"Initialized system function: {func.name}")
            
    def _init_custom_callables(self):
        """Initialize custom functions"""
        # Add example custom functions
        custom_functions = [
            CallableFunction(
                id="data_processor",
                name="data_processor",
                desc="Process and transform data according to specified rules",
                params={
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "array",
                            "description": "Input data array to process",
                            "items": {
                                "type": "number"
                            }
                        },
                        "operation": {
                            "type": "string",
                            "description": "Processing operation type",
                            "enum": ["sum", "average", "max", "min", "filter"]
                        },
                        "filter_condition": {
                            "type": "object",
                            "description": "Filter condition for filter operation",
                            "properties": {
                                "operator": {
                                    "type": "string",
                                    "enum": [">", "<", ">=", "<=", "==", "!="]
                                },
                                "value": {
                                    "type": "number"
                                }
                            }
                        }
                    }
                },
                returns={
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "number",
                            "description": "Processing result"
                        },
                        "processed_count": {
                            "type": "integer",
                            "description": "Number of processed items"
                        },
                        "filtered_data": {
                            "type": "array",
                            "description": "Filtered data array (for filter operation)",
                            "items": {
                                "type": "number"
                            }
                        }
                    }
                },
                type="custom",
                code="""def data_processor(params):
    \"\"\"
    Process and transform data according to specified rules
    
    Args:
        params (dict): Dictionary containing:
            - data (list): Input data array to process
            - operation (str): Processing operation type
            - filter_condition (dict, optional): Filter condition for filter operation
    
    Returns:
        dict: Dictionary containing:
            - result (float): Processing result
            - processed_count (int): Number of processed items
            - filtered_data (list, optional): Filtered data array
    \"\"\"
    try:
        data = params.get('data', [])
        operation = params.get('operation')
        
        if not data:
            return {
                'result': 0,
                'processed_count': 0
            }
            
        if operation == 'sum':
            result = sum(data)
        elif operation == 'average':
            result = sum(data) / len(data)
        elif operation == 'max':
            result = max(data)
        elif operation == 'min':
            result = min(data)
        elif operation == 'filter':
            filter_condition = params.get('filter_condition', {})
            operator = filter_condition.get('operator')
            value = filter_condition.get('value')
            
            if not operator or value is None:
                raise ValueError("Filter condition must include operator and value")
                
            filtered_data = []
            for item in data:
                if operator == '>' and item > value:
                    filtered_data.append(item)
                elif operator == '<' and item < value:
                    filtered_data.append(item)
                elif operator == '>=' and item >= value:
                    filtered_data.append(item)
                elif operator == '<=' and item <= value:
                    filtered_data.append(item)
                elif operator == '==' and item == value:
                    filtered_data.append(item)
                elif operator == '!=' and item != value:
                    filtered_data.append(item)
                    
            return {
                'result': len(filtered_data),
                'processed_count': len(data),
                'filtered_data': filtered_data
            }
        else:
            raise ValueError(f"Invalid operation: {operation}")
            
        return {
            'result': result,
            'processed_count': len(data)
        }
    except Exception as e:
        logger.error(f"Error processing data: {e}")
        raise"""
            ),
            CallableFunction(
                id="text_transformer",
                name="text_transformer",
                desc="Transform text according to specified rules",
                params={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Input text to transform"
                        },
                        "transform_type": {
                            "type": "string",
                            "description": "Type of transformation to apply",
                            "enum": ["uppercase", "lowercase", "capitalize", "reverse", "strip"]
                        },
                        "options": {
                            "type": "object",
                            "description": "Additional transformation options",
                            "properties": {
                                "remove_spaces": {
                                    "type": "boolean",
                                    "description": "Whether to remove spaces"
                                },
                                "remove_special_chars": {
                                    "type": "boolean",
                                    "description": "Whether to remove special characters"
                                }
                            }
                        }
                    }
                },
                returns={
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "string",
                            "description": "Transformed text"
                        },
                        "original_length": {
                            "type": "integer",
                            "description": "Length of original text"
                        },
                        "transformed_length": {
                            "type": "integer",
                            "description": "Length of transformed text"
                        }
                    }
                },
                type="custom",
                code="""def text_transformer(params):
    \"\"\"
    Transform text according to specified rules
    
    Args:
        params (dict): Dictionary containing:
            - text (str): Input text to transform
            - transform_type (str): Type of transformation to apply
            - options (dict, optional): Additional transformation options
    
    Returns:
        dict: Dictionary containing:
            - result (str): Transformed text
            - original_length (int): Length of original text
            - transformed_length (int): Length of transformed text
    \"\"\"
    try:
        text = params.get('text', '')
        transform_type = params.get('transform_type')
        options = params.get('options', {})
        
        if not text:
            return {
                'result': '',
                'original_length': 0,
                'transformed_length': 0
            }
            
        result = text
        
        # Apply transformation
        if transform_type == 'uppercase':
            result = result.upper()
        elif transform_type == 'lowercase':
            result = result.lower()
        elif transform_type == 'capitalize':
            result = result.capitalize()
        elif transform_type == 'reverse':
            result = result[::-1]
        elif transform_type == 'strip':
            result = result.strip()
        else:
            raise ValueError(f"Invalid transform type: {transform_type}")
            
        # Apply options
        if options.get('remove_spaces'):
            result = result.replace(' ', '')
            
        if options.get('remove_special_chars'):
            import re
            result = re.sub(r'[^a-zA-Z0-9\\s]', '', result)
            
        return {
            'result': result,
            'original_length': len(text),
            'transformed_length': len(result)
        }
    except Exception as e:
        logger.error(f"Error transforming text: {e}")
        raise"""
            )
        ]
        
        for func in custom_functions:
            self._callables[func.id] = func
            logger.debug(f"Initialized custom function: {func.name}")
            
        logger.info(f"Initialized {len(self._callables) - len(self.SYSTEM_FUNCTIONS)} custom callables")
        
    def get_callables(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get list of callable functions
        
        Args:
            params: Optional filter parameters
                - text: Text to search for in name, description and parameters
                - type: Function type to filter by ('system' or 'custom')
                
        Returns:
            List[Dict[str, Any]]: List of callable functions as dictionaries
        """
        try:
            # Get all functions
            functions = list(self._callables.values())
            
            # Apply filters if provided
            if params is not None:
                # Ensure params is dict type
                if not isinstance(params, dict):
                    logger.warning(f"Invalid params type: {type(params)}, expected dict")
                    return [func.to_dict() for func in functions]

                # Safely get and convert search text
                search_text = str(params.get('text', '')).lower()
                func_type = params.get('type')
                
                if search_text:
                    functions = [
                        func for func in functions
                        if search_text in str(func.name).lower() or
                           search_text in str(func.desc).lower() or
                           (isinstance(func.params, dict) and 
                            any(search_text in str(param.get('name', '')).lower() or
                                search_text in str(param.get('desc', '')).lower()
                                for param in func.params.get('properties', {}).values())) or
                           (isinstance(func.params, list) and
                            any(search_text in str(param.get('name', '')).lower() or
                                search_text in str(param.get('desc', '')).lower()
                                for param in func.params))
                    ]
                
                if func_type:
                    functions = [func for func in functions if func.type == func_type]
            
            # Convert to dictionaries
            return [func.to_dict() for func in functions]
            
        except Exception as e:
            import traceback
            stack_trace = traceback.format_exc()
            logger.error("Storage Error getting callables: %s\nStack trace:\n%s", str(e), stack_trace)
            return []
        
    def add_callable(self, data: Dict[str, Any]) -> None:
        """Add a new callable function
        
        Args:
            data: Function data to add
            
        Raises:
            ValueError: If function with same name already exists
        """
        try:
            # Create CallableFunction instance
            function = CallableFunction.from_dict(data)
            
            # Check if function with same name exists
            for existing_func in self._callables.values():
                if existing_func.name == function.name:
                    raise ValueError(f"Function with name '{function.name}' already exists")
            
            # Add to storage
            self._callables[function.id] = function
            logger.info("Added new callable function: %s", function.name)
            
        except Exception as e:
            import traceback
            stack_trace = traceback.format_exc()
            logger.error("Storage Error adding callable: %s\nStack trace:\n%s", str(e), stack_trace)
            raise
        
    def update_callable(self, id: str, data: Dict[str, Any]) -> None:
        """Update a callable function
        
        Args:
            id: ID of the function to update
            data: Updated function data
            
        Raises:
            ValueError: If function not found
        """
        try:
            if id not in self._callables:
                raise ValueError(f"Function not found: {id}")
                
            # Create CallableFunction instance
            function = CallableFunction.from_dict(data)
            
            # Update storage
            self._callables[id] = function
            logger.info("Updated callable function: %s, %s", function.id,  function.name)
            
        except Exception as e:
            import traceback
            stack_trace = traceback.format_exc()
            logger.error("Storage Error updating callable: %s\nStack trace:\n%s", str(e), stack_trace)
            raise
        
    def delete_callable(self, id: str) -> None:
        """Delete a callable function
        
        Args:
            id: Function ID
        """
        if id not in self._callables:
            raise ValueError(f"Function not found: {id}")
            
        function = self._callables[id]
        if function.type == 'system':
            raise ValueError("Cannot delete system function")
            
        del self._callables[id]
        logger.info(f"Deleted callable function: {function.name}") 