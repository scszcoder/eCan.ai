"""
Callable function management
Manage callable functions and their operations
"""

from typing import List, Optional, Dict, Any, Tuple
from utils.logger_helper import logger_helper as logger
from .types import CallableFunction, CallableFilter
from .storage import CallableStorage
import uuid


class CallableManager:
    """Callable function management class"""
    
    def __init__(self):
        self.storage = CallableStorage()
        # logger.debug("Initializing CallableManager")
    
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
            return self.storage.get_callables(params)
        except Exception as e:
            logger.error("Manager Error getting callables: %s", str(e))
            return []
    
    def add_custom_callable(self, callable: CallableFunction) -> bool:
        """Add custom function

        Args:
            callable: Callable function definition

        Returns:
            bool: Whether addition was successful
        """
        return self.storage.add_custom_callable(callable)

    def remove_custom_callable(self, name: str) -> bool:
        """Remove custom function

        Args:
            name: Function name

        Returns:
            bool: Whether removal was successful
        """
        return self.storage.remove_custom_callable(name)
    
    def get_callable(self, name: str) -> Optional[CallableFunction]:
        """Get function by name
        
        Args:
            name: Function name
            
        Returns:
            Optional[CallableFunction]: Function definition, returns None if it doesn't exist
        """
        return self.storage.get_callable(name)

    def add_callable(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new callable function
        
        Args:
            data: Function data to add
            
        Returns:
            Optional[Dict[str, Any]]: Added function data if successful, None otherwise
        """
        try:
            # Generate new function ID
            id = str(uuid.uuid4())
            data['id'] = id
            logger.debug("Generated new function ID: %s", id)
            
            # Create CallableFunction instance
            function = CallableFunction.from_dict(data)
            
            # Add to storage
            self.storage.add_callable(function.to_dict())
            logger.info("Added new callable function: %s", function.name)
            
            # Return added function data with ID
            return function.to_dict()
            
        except Exception as e:
            logger.error("Error adding callable: %s", str(e))
            return None
        
    def update_callable(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing callable function.
        
        Args:
            data: Dict containing:
                - name: Function name
                - desc: Function description
                - params: Function parameters
                - returns: Function return values
                - type: Function type
                - code: Function code
                
        Returns:
            Updated function data if successful, None if failed
            
        Raises:
            ValueError: If function not found or update fails
        """
        try:
            # Get existing function
            id = data.get('id')
            callables = self.storage.get_callables({'id': id})
            if not callables:
                raise ValueError(f"Function not found: {id}")
            existing = callables[0]

            # Update function data
            updated_data = {
                'id': id,
                'name': data.get('name', existing['name']),
                'desc': data.get('desc', existing['desc']),
                'params': data.get('params', existing['params']),
                'returns': data.get('returns', existing['returns']),
                'type': data.get('type', existing['type']),
                'code': data.get('code', existing['code'])  # Ensure code field exists
            }

            # Create new function object
            updated_function = CallableFunction(**updated_data)

            # Update storage
            self.storage.update_callable(id, updated_function.to_dict())

            # Return updated data
            return updated_function.to_dict()
            
        except Exception as e:
            logger.error(f"Error updating callable: {str(e)}")
            raise ValueError(f"Failed to update function: {str(e)}")
        
    def delete_callable(self, id: str) -> None:
        """Delete callable function

        Args:
            id: Function ID
        """
        try:
            self.storage.delete_callable(id)
            logger.info(f"Deleted callable function: {id}")
        except Exception as e:
            logger.error(f"Error deleting callable function: {e}")
            raise

    def manage_callable(self, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        """Unified entry for managing callable functions.
        
        Args:
            params: Dict containing:
                - action: Action to perform ('add', 'update', 'delete')
                - data: Function data including:
                    - id: Function ID (required for update/delete)
                    - name: Function name
                    - desc: Function description
                    - params: Function parameters
                    - returns: Function return values
                    - type: Function type
                    - code: Function code
                
        Returns:
            Tuple[Optional[Dict[str, Any]], str]: (result, message)
                - result: Function data if successful, None for delete
                - message: Success/error message
                
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        # Parameter validation
        if not params or 'action' not in params or 'data' not in params:
            raise ValueError("Missing required parameters: action and data")

        action = params['action']
        data = params['data']

        # Validate action
        if action not in ['add', 'update', 'delete']:
            raise ValueError(f"Invalid action: {action}")

        # Validate id
        if action in ['update', 'delete'] and 'id' not in data:
            raise ValueError(f"Missing id in data for {action} action")
            
        try:
            if action == 'add':
                result = self.add_callable(data)
                if result:
                    return result, "Function added successfully"
                else:
                    raise ValueError("Failed to add function")
            elif action == 'update':
                result = self.update_callable(data)
                if result:
                    return result, "Function updated successfully"
                else:
                    raise ValueError("Failed to update function")
            elif action == 'delete':
                self.delete_callable(data['id'])
                return None, "Function deleted successfully"
        except Exception as e:
            logger.error(f"Error in manage_callable: {str(e)}")
            raise ValueError(str(e))

# Create global instance
callable_manager = CallableManager() 