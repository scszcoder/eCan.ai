"""
Cloud API Service - Cloud API Data Sync Service

Supports cloud sync for all data types:
- Skills, Tasks, Agents, Organizations, Tools, Knowledges, etc.

Features:
1. Unified API interface
2. Automatic field mapping
3. Batch operation support
4. Async non-blocking
"""

import asyncio
import requests
from typing import Dict, Any, List, Optional, Callable, Union
from utils.logger_helper import logger_helper as logger
from agent.cloud_api.constants import DataType, Operation, get_cloud_api_function
from agent.cloud_api.schema_registry import get_schema_registry

# Import cloud_api module to trigger decorator registration
import agent.cloud_api.cloud_api  # noqa: F401


class CloudAPIService:
    """Cloud API Sync Service (auto-registered using decorators)"""

    @staticmethod
    def _is_duplicate_entry_error(error: Any) -> bool:
        """Check whether an error message indicates a DB duplicate-key insert."""
        err = str(error or "").lower()
        return (
            "duplicate entry" in err
            or "error code: 1062" in err
            or "sqlstate: 23000" in err
        )

    def _is_idempotent_error(self, operation: str, error: Any) -> bool:
        """Treat known idempotent errors as success based on operation type."""
        err = str(error or "")

        # DELETE on non-existent resource is idempotent: the desired end state is achieved
        if operation == Operation.DELETE.value and 'NOT_FOUND' in err:
            return True

        # Duplicate insert errors on TASK_SKILL.add are idempotent
        if operation == Operation.ADD.value and self.data_type == DataType.TASK_SKILL:
            return self._is_duplicate_entry_error(error)

        return False
    
    def __init__(self, data_type: Union[DataType, str]):
        """
        Initialize cloud service
        
        Args:
            data_type: Data type (DataType enum or string)
        """
        # Support both string and enum
        if isinstance(data_type, str):
            self.data_type = DataType(data_type)
        else:
            self.data_type = data_type
        
        # Use Schema directly instead of Adapter (simplified architecture)
        self.schema_registry = get_schema_registry()
        self.schema = self.schema_registry.get_schema(self.data_type)
    
    def _get_auth_token(self) -> Optional[str]:
        """Get authentication token from MainWindow.get_auth_token()"""
        try:
            from app_context import AppContext
            
            # Get token from MainWindow.get_auth_token()
            main_window = AppContext.get_main_window()
            if main_window and hasattr(main_window, 'get_auth_token'):
                token = main_window.get_auth_token()
                if token:
                    return token
            
            logger.warning("[CloudAPIService] No auth token available from MainWindow")
            return None
            
        except Exception as e:
            logger.error(f"[CloudAPIService] Failed to get auth token: {e}")
            return None
    
    def _get_api_endpoint(self) -> str:
        """Get API endpoint URL (using Cloud.py's common method)"""
        from agent.cloud_api.cloud_api import get_appsync_endpoint
        return get_appsync_endpoint()
    
    def _get_cloud_api_function(self, operation: Union[Operation, str]) -> Optional[Callable]:
        """
        Get cloud API function from decorator registry
        
        Args:
            operation: Operation type (Operation enum or string)
            
        Returns:
            Cloud API function
        """
        # Support both string and enum
        if isinstance(operation, str):
            operation = Operation(operation)
        
        # Get function from decorator registry
        api_func = get_cloud_api_function(self.data_type, operation)
        
        if not api_func:
            logger.error(f"[CloudAPIService] No API function for {self.data_type}.{operation}")
            return None
        
        return api_func
    
    def sync_to_cloud(self, local_items: List[Dict[str, Any]], operation: Union[Operation, str] = Operation.ADD, timeout: float = None) -> Dict[str, Any]:
        """
        Sync data to cloud
        
        Args:
            local_items: List of local data items
            operation: Operation type ('add', 'update', 'delete')
            timeout: Request timeout in seconds, None uses default
            
        Returns:
            Sync result {'success': bool, 'synced': int, 'failed': int, 'errors': []}
        """
        token = self._get_auth_token()
        if not token:
            return {
                'success': False,
                'synced': 0,
                'failed': len(local_items),
                'errors': ['No auth token available']
            }
        
        # Use Schema to convert data format (simplified: removed Adapter layer)
        # Pass operation type to schema for operation-specific transformations
        logger.debug(f"[CloudAPIService] Sample local item BEFORE conversion: {local_items[0] if local_items else 'N/A'}")
        operation_str = operation.value if hasattr(operation, 'value') else str(operation)
        cloud_items = [self.schema.to_cloud(item, operation=operation_str) for item in local_items]
        logger.debug(f"[CloudAPIService] Sample cloud item AFTER conversion: {cloud_items[0] if cloud_items else 'N/A'}")
        
        try:
            # Get cloud API function
            api_func = self._get_cloud_api_function(operation)
            if not api_func:
                return {
                    'success': False,
                    'synced': 0,
                    'failed': len(local_items),
                    'errors': [f'No cloud API function for {self.data_type}.{operation}']
                }
            
            # Create session with proper timeout configuration
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            session = requests.Session()
            
            # Configure HTTPAdapter with proper timeout handling
            # This ensures the session respects the timeout parameter
            retry_strategy = Retry(
                total=0,  # No automatic retries (we handle retries at a higher level)
                backoff_factor=0
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            
            endpoint = self._get_api_endpoint()
            
            # Handle delete operation (requires special format)
            if operation == 'delete':
                cloud_items = self._prepare_delete_items(cloud_items)
            
            # Call cloud API
            timeout_info = f" (timeout: {timeout}s)" if timeout else ""
            logger.info(f"[CloudAPIService] 🚀 Calling cloud API: {self.data_type}.{operation} with {len(cloud_items)} item(s){timeout_info}")
            logger.debug(f"[CloudAPIService] API endpoint: {endpoint}")
            
            # Call API function with timeout parameter
            # Note: api_func signature may be (session, items, token, endpoint) or (session, items, token, endpoint, timeout)
            # We need to check function signature
            import inspect
            sig = inspect.signature(api_func)
            
            if 'timeout' in sig.parameters and timeout is not None:
                # Function supports timeout parameter
                result = api_func(session, cloud_items, token, endpoint, timeout=timeout)
            else:
                # Function doesn't support timeout parameter, use default
                result = api_func(session, cloud_items, token, endpoint)
            
            # Log detailed response information
            logger.debug(f"[CloudAPIService] Cloud API response type: {type(result)}")
            if isinstance(result, dict):
                logger.debug(f"[CloudAPIService] Cloud API response keys: {result.keys()}")
                logger.debug(f"[CloudAPIService] Cloud API response: {result}")

            # Schema mismatch: server doesn't support this operation.
            # Some legacy relation syncs are now represented directly on the entity
            # (e.g. agent.org_id), so they can be treated as a successful no-op.
            if isinstance(result, dict) and result.get('skipped'):
                reason = result.get('reason', 'unknown reason')
                op_name = result.get('operation', f"{self.data_type}.{operation}")
                if self.data_type == 'agent_org':
                    logger.info(
                        f"[CloudAPIService] ⏭️ Skipping deprecated cloud operation: {op_name} | endpoint={endpoint} | reason={reason}"
                    )
                    return {
                        'success': True,
                        'synced': len(local_items),
                        'failed': 0,
                        'errors': [],
                        'response': result
                    }
                logger.error(
                    f"[CloudAPIService] ❌ Cloud operation not supported by server schema: {op_name} | endpoint={endpoint} | reason={reason}"
                )
                logger.error(
                    f"[CloudAPIService] ❌ Action required: deploy/upgrade AppSync GraphQL schema for this endpoint to include the missing mutation(s)."
                )
                return {
                    'success': False,
                    'synced': 0,
                    'failed': len(local_items),
                    'errors': [f"{op_name} not supported by server schema: {reason}"],
                    'response': result
                }
            
            # Check result
            if isinstance(result, dict) and 'errorType' in result:
                error_msg = result.get('message', 'Unknown error')
                logger.error(f"[CloudAPIService] ❌ Cloud API error: {error_msg}")
                logger.error(f"[CloudAPIService] Full error response: {result}")
                return {
                    'success': False,
                    'synced': 0,
                    'failed': len(local_items),
                    'errors': [error_msg],
                    'response': result
                }

            # Explicit failure shape from some cloud handlers
            if isinstance(result, dict) and result.get('success') is False:
                error_msg = result.get('error') or result.get('message') or 'Cloud API returned success=false'

                # Idempotent behavior for duplicate inserts on TASK_SKILL.add
                if self._is_idempotent_error(operation_str, error_msg):
                    logger.info(
                        f"[CloudAPIService] ✅ Duplicate TASK_SKILL relation already exists in cloud, treating as idempotent success ({operation_str})"
                    )
                    return {
                        'success': True,
                        'synced': len(local_items),
                        'failed': 0,
                        'errors': [],
                        'response': result
                    }

                logger.error(f"[CloudAPIService] ❌ Cloud API failure: {error_msg}")
                logger.error(f"[CloudAPIService] Full failure response: {result}")
                return {
                    'success': False,
                    'synced': 0,
                    'failed': len(local_items),
                    'errors': [error_msg],
                    'response': result
                }
            
            # Check if response is successful (may not have explicit success flag)
            if result is None:
                # None response means the cloud API returned null (rejected the request)
                error_msg = f"Cloud API returned null for {self.data_type}.{operation}"
                logger.error(f"[CloudAPIService] ❌ {error_msg}")
                return {
                    'success': False,
                    'synced': 0,
                    'failed': len(local_items),
                    'errors': [error_msg]
                }
            
            # List responses are valid for batch operations (e.g., removeAgentSkills returns list of results)
            if isinstance(result, list):
                logger.debug(f"[CloudAPIService] Cloud API returned list response with {len(result)} item(s)")
                # Some APIs return per-item results like {success: false, error: ...}
                duplicate_errors = []
                item_errors = []
                for item in result:
                    if not isinstance(item, dict):
                        continue
                    if item.get('success') is False or item.get('errorType') or item.get('error'):
                        item_error = item.get('error') or item.get('message') or str(item)
                        if self._is_idempotent_error(operation_str, item_error):
                            duplicate_errors.append(item_error)
                        else:
                            item_errors.append(item_error)

                if duplicate_errors:
                    logger.info(
                        f"[CloudAPIService] ℹ️ Ignoring {len(duplicate_errors)} duplicate TASK_SKILL relation error(s) as idempotent ({operation_str})"
                    )

                if item_errors:
                    logger.error(
                        f"[CloudAPIService] ❌ Cloud API returned {len(item_errors)} failed item(s) out of {len(result)}"
                    )
                    logger.error(f"[CloudAPIService] Item-level errors: {item_errors}")
                    failed_count = max(len(item_errors), len(local_items) - (len(result) - len(item_errors)))
                    return {
                        'success': False,
                        'synced': max(0, len(local_items) - failed_count),
                        'failed': failed_count,
                        'errors': item_errors,
                        'response': result
                    }
            elif not isinstance(result, dict):
                # Only warn for truly unexpected types (not list or dict)
                logger.warning(f"[CloudAPIService] Unexpected response type: {type(result)}, treating as success")
            
            # Success response
            logger.info(f"[CloudAPIService] ✅ Successfully synced {len(local_items)} {self.data_type}(s) to cloud ({operation})")
            logger.debug(f"[CloudAPIService] Cloud API success response: {result}")
            return {
                'success': True,
                'synced': len(local_items),
                'failed': 0,
                'errors': [],
                'response': result
            }
            
        except Exception as e:
            error_msg = str(e)
            
            # This is a real exception, log with traceback
            import traceback
            logger.warning(f"[CloudAPIService] Exception during sync {self.data_type}(s): {error_msg}")
            logger.debug(f"[CloudAPIService] Traceback: {traceback.format_exc()}")
            
            return {
                'success': False,
                'synced': 0,
                'failed': len(local_items),
                'errors': [error_msg]
            }
    
    def _prepare_delete_items(self, cloud_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare data format for delete operation
        
        Args:
            cloud_items: Cloud format data (already converted by schema)
            
        Returns:
            Delete operation format data
        """
        # Different data types have different ID field names in cloud format.
        # For skills, delete schema currently keeps `id` and excludes `skid`.
        id_field_mapping = {
            DataType.SKILL: 'id',
            DataType.TASK: 'id',
            DataType.AGENT: 'agid',  # ✅ Fixed: Agent uses 'agid' in cloud format
            DataType.TOOL: 'id',
        }
        
        id_field = id_field_mapping.get(self.data_type, 'id')
        delete_items = []
        for item in cloud_items:
            oid = item.get(id_field, item.get('id', item.get('agid')))
            delete_item = {
                'oid': oid,
                'reason': f'User deleted {self.data_type.value}'
            }
            owner = item.get('owner')
            if owner not in (None, ''):
                delete_item['owner'] = owner
            delete_items.append(delete_item)
        return delete_items
    
    def load_from_cloud(self, username: str, query_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Load data from cloud
        
        Args:
            username: Username
            query_params: Query parameters (optional)
            
        Returns:
            Load result {'success': bool, 'items': [], 'count': int}
        """
        token = self._get_auth_token()
        if not token:
            return {
                'success': False,
                'items': [],
                'count': 0,
                'error': 'No auth token available'
            }
        
        try:
            # Get query API function
            api_func = self._get_cloud_api_function('query')
            if not api_func:
                return {
                    'success': False,
                    'items': [],
                    'count': 0,
                    'error': f'No query API function for {self.data_type}'
                }
            
            # Create session with proper timeout configuration
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            session = requests.Session()
            
            # Configure HTTPAdapter with proper timeout handling
            retry_strategy = Retry(
                total=0,  # No automatic retries (we handle retries at a higher level)
                backoff_factor=0
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            
            endpoint = self._get_api_endpoint()
            q_settings = query_params or {'byowneruser': True}
            
            result = api_func(session, token, q_settings, endpoint)
            
            # Check for errors
            if isinstance(result, dict) and 'errorType' in result:
                logger.warning(f"[CloudAPIService] Cloud query error: {result.get('message')}")
                return {
                    'success': False,
                    'items': [],
                    'count': 0,
                    'error': result.get('message', 'Unknown error')
                }
            
            # Parse cloud data
            if isinstance(result, list):
                cloud_items = result
            elif isinstance(result, dict):
                cloud_items = result.get('items', result.get(f'{self.data_type}s', []))
            else:
                cloud_items = []
            
            # Use Schema to convert to local format (simplified: removed Adapter layer)
            local_items = [self.schema.from_cloud(item) for item in cloud_items]
            
            logger.info(f"[CloudAPIService] ✅ Loaded {len(local_items)} {self.data_type}(s) from cloud")
            return {
                'success': True,
                'items': local_items,
                'count': len(local_items)
            }
            
        except Exception as e:
            logger.error(f"[CloudAPIService] Failed to load {self.data_type}(s) from cloud: {e}")
            return {
                'success': False,
                'items': [],
                'count': 0,
                'error': str(e)
            }
    
    async def async_sync_to_cloud(self, local_items: List[Dict[str, Any]], operation: str = 'add') -> Dict[str, Any]:
        """Async sync to cloud (non-blocking)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.sync_to_cloud, local_items, operation)
    
    async def async_load_from_cloud(self, username: str, query_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Async load from cloud (non-blocking)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.load_from_cloud, username, query_params)
    
    def reload_field_mapping(self) -> bool:
        """
        Reload field mapping configuration
        
        Returns:
            Whether reload was successful
        """
        logger.info(f"[CloudAPIService] Reloading field mapping for {self.data_type}...")
        success = self.adapter.reload_config()
        if success:
            logger.info(f"[CloudAPIService] ✅ Field mapping reloaded for {self.data_type}")
        else:
            logger.warning(f"[CloudAPIService] ⚠️ Failed to reload field mapping for {self.data_type}")
        return success


class CloudAPIServiceFactory:
    """Cloud API Service Factory - Manages service instances for all data types"""
    
    _services: Dict[str, CloudAPIService] = {}
    
    @classmethod
    def get_service(cls, data_type: str) -> CloudAPIService:
        """
        Get cloud service instance for specified data type (singleton)
        
        Args:
            data_type: Data type
            
        Returns:
            Service instance
        """
        if data_type not in cls._services:
            cls._services[data_type] = CloudAPIService(data_type)
        return cls._services[data_type]
    
    @classmethod
    def reload_service(cls, data_type: str) -> bool:
        """Reload service configuration for specified data type"""
        if data_type in cls._services:
            return cls._services[data_type].reload_field_mapping()
        return False
    
    @classmethod
    def reload_all_services(cls) -> Dict[str, bool]:
        """Reload all service configurations"""
        results = {}
        for data_type, service in cls._services.items():
            results[data_type] = service.reload_field_mapping()
        return results
    
    @classmethod
    def reset(cls) -> None:
        """Reset all services (for testing)"""
        cls._services.clear()


# Convenience functions
def get_cloud_service(data_type: str) -> CloudAPIService:
    """Get cloud service for specified data type"""
    return CloudAPIServiceFactory.get_service(data_type)


def reload_cloud_service(data_type: str) -> bool:
    """Reload service configuration for specified data type"""
    return CloudAPIServiceFactory.reload_service(data_type)


def reload_all_cloud_services() -> Dict[str, bool]:
    """Reload all service configurations"""
    return CloudAPIServiceFactory.reload_all_services()
