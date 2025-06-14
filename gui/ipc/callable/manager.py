"""
Callable function management
Manage callable functions and their operations
"""

from typing import List, Optional
from utils.logger_helper import logger_helper
from .types import CallableFunction, CallableFilter
from .storage import CallableStorage

logger = logger_helper.logger

class CallableManager:
    """Callable function management class"""
    
    def __init__(self):
        self._storage = CallableStorage()
        logger.debug("Initializing CallableManager")
    
    def get_callables(self, filter: Optional[CallableFilter] = None) -> List[CallableFunction]:
        """Get filtered callable functions
        
        Args:
            filter: Filter conditions, optional including:
                - text: Text filter for function name, description and parameters
                - type: Type filter ('system' or 'custom')
                
        Returns:
            List[CallableFunction]: Filtered callable functions list
        """
        logger.debug(f"Getting callables with filter: {filter}")
        
        # Get all callables
        all_callables = self._storage.get_all_callables()
        logger.debug(f"Total callables before filtering: {len(all_callables)}")
        
        if not filter:
            logger.debug("No filter applied, returning all callables")
            return all_callables
            
        filtered_callables = []
        text_filter = filter.get('text', '').lower() if filter.get('text') else ''
        type_filter = filter.get('type')
        
        for callable in all_callables:
            # Apply type filter
            if type_filter and callable['type'] != type_filter:
                continue
                
            # If no text filter, add the callable
            if not text_filter:
                filtered_callables.append(callable)
                continue
                
            # Apply text filter
            if text_filter in callable['name'].lower():
                filtered_callables.append(callable)
                continue
                
            if text_filter in callable['desc'].lower():
                filtered_callables.append(callable)
                continue
                
            # Check parameters
            if callable['params'].get('properties'):
                for param_name in callable['params']['properties']:
                    if text_filter in param_name.lower():
                        filtered_callables.append(callable)
                        break
                        
            # Check return type
            if callable['returns'].get('type') and text_filter in callable['returns']['type'].lower():
                filtered_callables.append(callable)
                continue
                
        logger.debug(f"Filtered callables count: {len(filtered_callables)}")
        return filtered_callables
    
    def add_custom_callable(self, callable: CallableFunction) -> bool:
        """添加自定义函数
        
        Args:
            callable: 可调用函数定义
            
        Returns:
            bool: 是否添加成功
        """
        return self._storage.add_custom_callable(callable)
    
    def remove_custom_callable(self, name: str) -> bool:
        """删除自定义函数
        
        Args:
            name: 函数名称
            
        Returns:
            bool: 是否删除成功
        """
        return self._storage.remove_custom_callable(name)
    
    def get_callable(self, name: str) -> Optional[CallableFunction]:
        """Get function by name
        
        Args:
            name: Function name
            
        Returns:
            Optional[CallableFunction]: Function definition, returns None if it doesn't exist
        """
        return self._storage.get_callable(name)

# Create global instance
callable_manager = CallableManager() 