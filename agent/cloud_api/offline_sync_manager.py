"""
Offline Sync Manager - Offline Synchronization Manager

Manages the complete lifecycle of cloud synchronization with offline support:
1. Try to sync directly to cloud
2. Cache to local queue on failure
3. Periodically retry queued tasks
4. Auto-sync cached data on startup
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Union
from utils.logger_helper import logger_helper as logger
from agent.cloud_api.cloud_api_service import get_cloud_service
from agent.cloud_api.offline_sync_queue import get_offline_sync_queue
from agent.cloud_api.constants import DataType, Operation


class OfflineSyncManager:
    """Offline Sync Manager - Handles online/offline synchronization"""
    
    # Configuration variable for offline sync control
    OFFLINE_SYNC_ENABLED = True  # 启用/禁用离线同步功能
    
    def __init__(self):
        """Initialize offline sync manager"""
        self.sync_queue = get_offline_sync_queue()
        self._retry_thread = None
        self._stop_retry = False
        
        # Thread pool for async sync (max 5 concurrent)
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='CloudSync')
        
        logger.info("[OfflineSyncManager] Initialized with thread pool (max_workers=5)")
        logger.info(f"[OfflineSyncManager] OFFLINE_SYNC_ENABLED={self.OFFLINE_SYNC_ENABLED}")

    @staticmethod
    def _is_duplicate_error(errors: List[Any]) -> bool:
        """Check whether the error list indicates an idempotent duplicate-key failure."""
        error_str = ' '.join(str(e) for e in errors)
        return '1062' in error_str or 'Duplicate entry' in error_str

    @staticmethod
    def _is_non_retryable_error(errors: List[Any]) -> bool:
        """Check whether the error list indicates a permanent authorization/configuration failure."""
        error_str = ' '.join(str(e) for e in errors).lower()
        non_retryable_markers = (
            'forbidden',
            'not the owner',
            'not authorized to perform',
            'no identity-based policy allows',
            'accessdenied',
            'access denied',
            'unauthorized',
            'scheduler:deleteschedule',
        )
        return any(marker in error_str for marker in non_retryable_markers)
    
    def sync_to_cloud(self, data_type: Union[DataType, str], data: Dict[str, Any], 
                     operation: Union[Operation, str] = Operation.ADD, timeout: float = None) -> Dict[str, Any]:
        """
        Sync data to cloud (synchronous execution with offline caching)
        
        Args:
            data_type: Data type (DataType enum or string)
            data: Data content
            operation: Operation type (Operation enum or string)
            timeout: Request timeout in seconds, None uses default
        
        Returns:
            Dict: Sync result
        """
        try:
            # Log sync start
            data_name = data.get('name', data.get('id', 'unknown'))
            timeout_info = f" (timeout: {timeout}s)" if timeout else ""
            logger.info(f"[OfflineSyncManager] 🔄 Starting sync: {data_type}.{operation} - {data_name}{timeout_info}")
            
            # Try direct sync
            service = get_cloud_service(data_type)
            result = service.sync_to_cloud([data], operation=operation, timeout=timeout)
            
            # Log detailed result
            logger.debug(f"[OfflineSyncManager] Sync result: {result}")
            
            if result['success']:
                response = result.get('response') if isinstance(result, dict) else None
                logger.info(f"[OfflineSyncManager] ✅ Synced to cloud: {data_type}.{operation} - {data_name}")
                if response is not None:
                    logger.debug(f"[OfflineSyncManager] Cloud response: {response}")
                return {
                    'success': True,
                    'synced': True,
                    'cached': False,
                    'message': 'Synced to cloud successfully',
                    'response': response
                }
            else:
                # Sync failed, check if we should add to queue
                errors = result.get('errors', [])

                # Check for duplicate key errors (record already exists in cloud)
                # Error code 1062 = Duplicate entry - treat as success, no need to retry
                if self._is_duplicate_error(errors):
                    logger.info(f"[OfflineSyncManager] ✅ Record already exists in cloud (duplicate key), treating as success: {data_type}.{operation} - {data_name}")
                    return {
                        'success': True,
                        'synced': True,
                        'cached': False,
                        'message': 'Record already exists in cloud',
                        'errors': errors
                    }

                # Permanent cloud-side authorization/configuration failures should not
                # be treated as offline sync issues, otherwise they will be retried forever.
                if self._is_non_retryable_error(errors):
                    logger.error(f"[OfflineSyncManager] ❌ Non-retryable cloud sync failure: {data_type}.{operation} - {data_name}")
                    logger.error(f"[OfflineSyncManager] Non-retryable errors: {errors}")
                    return {
                        'success': True,
                        'synced': False,
                        'cached': False,
                        'message': 'Cloud sync failed with non-retryable authorization/configuration error',
                        'errors': errors
                    }
                
                # Check if offline sync is disabled
                if not self.OFFLINE_SYNC_ENABLED:
                    logger.info(f"[OfflineSyncManager] ⚠️ Sync failed but offline sync is disabled: {data_type}.{operation} - {data_name}")
                    logger.warning(f"[OfflineSyncManager] Errors: {errors}")
                    return {
                        'success': False,
                        'synced': False,
                        'cached': False,
                        'message': 'Sync failed and offline sync is disabled',
                        'errors': errors
                    }
                
                # Add to queue
                task_id = self.sync_queue.add(data_type, data, operation)
                logger.warning(f"[OfflineSyncManager] ⚠️ Sync failed, cached to queue: {task_id}")
                logger.warning(f"[OfflineSyncManager] Errors: {errors}")
                return {
                    'success': True,  # Local operation succeeded
                    'synced': False,
                    'cached': True,
                    'task_id': task_id,
                    'message': 'Cached for later sync',
                    'errors': errors
                }
                
        except Exception as e:
            # Network error or other exception, check if we should add to queue
            
            # Check if offline sync is disabled
            if not self.OFFLINE_SYNC_ENABLED:
                logger.error(f"[OfflineSyncManager] ❌ Sync error but offline sync is disabled: {e}")
                return {
                    'success': False,
                    'synced': False,
                    'cached': False,
                    'message': 'Sync error and offline sync is disabled',
                    'error': str(e)
                }
            
            # Add to queue
            task_id = self.sync_queue.add(data_type, data, operation)
            logger.error(f"[OfflineSyncManager] ❌ Sync error, cached to queue: {task_id} - {e}")
            return {
                'success': True,  # Local operation succeeded
                'synced': False,
                'cached': True,
                'task_id': task_id,
                'message': 'Cached due to network error',
                'error': str(e)
            }
    
    def sync_to_cloud_async(self, data_type: Union[DataType, str], data: Dict[str, Any], 
                           operation: Union[Operation, str] = Operation.ADD,
                           callback: Optional[callable] = None) -> None:
        """
        Async sync data to cloud (background execution, non-blocking)
        
        Uses thread pool for sync, doesn't block current thread. Suitable for UI scenarios.
        
        Args:
            data_type: Data type (DataType enum or string)
            data: Data content
            operation: Operation type (Operation enum or string)
            callback: Optional callback function to receive sync result
        """
        def _sync_task():
            """Background sync task"""
            try:
                result = self.sync_to_cloud(data_type, data, operation)
                
                # Log result
                if result['synced']:
                    logger.info(f"[OfflineSyncManager] ✅ Async sync completed: {data_type} - {operation}")
                elif result['cached']:
                    logger.info(f"[OfflineSyncManager] 💾 Async sync cached: {data_type} - {operation}")
                
                # Call callback function
                if callback:
                    callback(result)
                    
            except Exception as e:
                logger.error(f"[OfflineSyncManager] ❌ Async sync error: {data_type} - {e}")
                if callback:
                    callback({
                        'success': False,
                        'synced': False,
                        'cached': False,
                        'error': str(e)
                    })
        
        # Submit to thread pool for execution
        self._executor.submit(_sync_task)
    
    # Dependency order for sync: entities must be synced before their relationships
    # Level 0: Core entities (must exist first)
    # Level 1: First-level relationships (depend on Level 0)
    # Level 2: Second-level relationships (depend on Level 1)
    SYNC_DEPENDENCY_ORDER = {
        # Level 0: Core entities
        DataType.AGENT: 0,
        DataType.SKILL: 0,
        DataType.TASK: 0,
        DataType.TOOL: 0,
        DataType.KNOWLEDGE: 0,
        DataType.AGENT_ORG: 0,
        # Level 1: First-level relationships (depend on Level 0 entities)
        DataType.AGENT_SKILL: 1,  # depends on AGENT
        DataType.AGENT_TASK: 1,   # depends on AGENT
        DataType.AGENT_TOOL: 1,  # depends on AGENT
        # Level 2: Second-level relationships (depend on Level 1)
        DataType.SKILL_TOOL: 2,
        DataType.SKILL_KNOWLEDGE: 2,
        DataType.TASK_SKILL: 2,
    }

    def _sort_tasks_by_dependency(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort tasks by dependency order to avoid foreign key constraint errors.

        Entities must be synced before their relationships. For example:
        - agent_skill_add depends on agent_add (agent must exist first)
        - agent_task_add depends on agent_add (agent must exist first)

        Args:
            tasks: List of task dictionaries with 'data_type' and 'operation' keys

        Returns:
            Sorted list of tasks
        """
        def get_sort_key(task: Dict[str, Any]) -> tuple:
            data_type = task.get('data_type')
            operation = task.get('operation', '')

            # Get base priority
            if isinstance(data_type, str):
                try:
                    data_type = DataType(data_type)
                except ValueError:
                    pass

            if isinstance(data_type, DataType):
                priority = self.SYNC_DEPENDENCY_ORDER.get(data_type, 99)
            else:
                priority = 99

            # ADD operations have higher priority within the same level
            # (sync parent records before child records of the same level)
            is_add = operation == Operation.ADD.value
            operation_priority = 0 if is_add else 1

            return (priority, operation_priority)

        return sorted(tasks, key=get_sort_key)

    def _check_foreign_key_error(self, errors: List[Any], data_type: DataType) -> Optional[Dict[str, Any]]:
        """
        Check if error is a foreign key constraint error and extract dependency info.

        Args:
            errors: List of error messages
            data_type: Current data type being synced

        Returns:
            Dict with 'dependency_type' and 'dependency_operation' if it's a FK error,
            None otherwise
        """
        error_str = ' '.join(str(e) for e in errors).lower()

        if 'foreign key constraint fails' not in error_str:
            return None

        # Parse foreign key constraint error to determine which parent is missing
        # Example: CONSTRAINT `fk_asr_agent` FOREIGN KEY (`agent_id`) REFERENCES `agents` (`id`)
        if data_type == DataType.AGENT_SKILL:
            return {
                'dependency_type': DataType.AGENT,
                'dependency_operation': Operation.ADD,
                'message': 'Agent not found in cloud, retry after agent sync'
            }
        elif data_type == DataType.AGENT_TASK:
            return {
                'dependency_type': DataType.AGENT,
                'dependency_operation': Operation.ADD,
                'message': 'Agent not found in cloud, retry after agent sync'
            }
        elif data_type == DataType.AGENT_TOOL:
            return {
                'dependency_type': DataType.AGENT,
                'dependency_operation': Operation.ADD,
                'message': 'Agent not found in cloud, retry after agent sync'
            }
        elif data_type == DataType.SKILL_TOOL:
            return {
                'dependency_type': DataType.SKILL,
                'dependency_operation': Operation.ADD,
                'message': 'Skill not found in cloud, retry after skill sync'
            }

        return None

    def sync_pending_queue(self, max_tasks: int = None, timeout_per_task: float = 10.0, include_failed: bool = True) -> Dict[str, Any]:
        """
        Sync pending tasks in queue
        
        Args:
            max_tasks: Maximum number of tasks to sync (None = all)
            timeout_per_task: Timeout per task (seconds)
            include_failed: Whether to include failed tasks (default True)
        
        Returns:
            Dict: Sync result statistics
        """
        # Get pending tasks
        pending_tasks = self.sync_queue.get_pending_tasks()
        
        # If needed, also get failed tasks and retry
        if include_failed:
            failed_tasks = self.sync_queue.get_failed_tasks()
            if failed_tasks:
                logger.info(f"[OfflineSyncManager] Found {len(failed_tasks)} failed tasks, will retry them")
                # Move failed tasks back to pending queue
                for task in failed_tasks:
                    self.sync_queue.retry_failed_task(task['id'])
                # Re-get pending tasks (now includes failed tasks)
                pending_tasks = self.sync_queue.get_pending_tasks()
        
        if not pending_tasks:
            logger.info("[OfflineSyncManager] No pending tasks to sync")
            return {
                'success': True,
                'total': 0,
                'synced': 0,
                'failed': 0
            }

        # Sort tasks by dependency order to avoid foreign key constraint errors
        # Entities (AGENT, SKILL, TASK, etc.) must be synced before relationships
        pending_tasks = self._sort_tasks_by_dependency(pending_tasks)
        logger.info(f"[OfflineSyncManager] Tasks sorted by dependency order: {[t['data_type'] for t in pending_tasks]}")

        # Limit number of tasks (avoid processing too many tasks at startup)
        if max_tasks and len(pending_tasks) > max_tasks:
            logger.info(f"[OfflineSyncManager] Limiting sync to {max_tasks} tasks (total: {len(pending_tasks)})")
            pending_tasks = pending_tasks[:max_tasks]
        
        logger.info(f"[OfflineSyncManager] Syncing {len(pending_tasks)} pending tasks (timeout: {timeout_per_task}s per task)...")
        
        synced_count = 0
        failed_count = 0
        import time
        
        for task in pending_tasks:
            try:
                data_type = task['data_type']
                operation = task['operation']
                data = task['data']
                task_id = task['id']
                
                # Try sync (with specified timeout)
                service = get_cloud_service(data_type)
                result = service.sync_to_cloud([data], operation=operation, timeout=timeout_per_task)
                
                if result['success']:
                    # Sync succeeded, remove from queue
                    self.sync_queue.mark_success(task_id)
                    synced_count += 1
                    logger.info(f"[OfflineSyncManager] ✅ Queue task synced: {task_id}")
                else:
                    # Check for duplicate key errors - record already exists, treat as success
                    errors = result.get('errors', [])
                    error_str = ', '.join(str(e) for e in errors)
                    if self._is_duplicate_error(errors):
                        self.sync_queue.mark_success(task_id)
                        synced_count += 1
                        logger.info(f"[OfflineSyncManager] ✅ Queue task: record already exists in cloud (duplicate key), marking as success: {task_id}")
                    elif self._is_non_retryable_error(errors):
                        self.sync_queue.mark_failed(
                            task_id,
                            error_str or 'Non-retryable authorization/configuration error',
                            max_retries=1,
                            non_retryable=True,
                        )
                        failed_count += 1
                        logger.error(f"[OfflineSyncManager] ❌ Queue task hit non-retryable cloud error, stopping retries: {task_id}")
                    elif 'NOT_FOUND' in error_str and operation == 'update':
                        # UPDATE failed because resource doesn't exist in cloud.
                        # Retry with ADD to register it first.
                        logger.info(f"[OfflineSyncManager] 🔄 Queue task NOT_FOUND on UPDATE, retrying with ADD: {task_id}")

                        # For agents, the queued update payload may be a partial diff
                        # (e.g. only {id, status} from _sync_agent_status_to_cloud).
                        # addAgents requires `name` which would be missing, causing a
                        # GraphQL validation error. Fetch the full record from local DB
                        # so the ADD has all required fields.
                        add_data = data
                        if data_type == DataType.AGENT:
                            agent_id = data.get('id') if isinstance(data, dict) else None
                            if agent_id:
                                try:
                                    from app_context import AppContext
                                    ec_db_mgr = AppContext.get_ec_db_mgr()
                                    if ec_db_mgr and ec_db_mgr.agent_service:
                                        db_result = ec_db_mgr.agent_service.query_agents(id=agent_id)
                                        full_agent = (db_result.get('data') or [None])[0] if db_result.get('success') else None
                                        if full_agent and full_agent.get('name'):
                                            add_data = full_agent
                                            logger.info(f"[OfflineSyncManager] 📋 ADD fallback: enriched agent payload with full DB record (name='{full_agent.get('name')}')")
                                        else:
                                            logger.warning(f"[OfflineSyncManager] ⚠️ ADD fallback: could not fetch full agent {agent_id} from local DB, using partial payload")
                                except Exception as _db_err:
                                    logger.warning(f"[OfflineSyncManager] ⚠️ ADD fallback: DB lookup failed for agent {agent_id}: {_db_err}, using original payload")

                        add_result = service.sync_to_cloud([add_data], operation=Operation.ADD, timeout=timeout_per_task)
                        if add_result['success']:
                            self.sync_queue.mark_success(task_id)
                            synced_count += 1
                            logger.info(f"[OfflineSyncManager] ✅ Queue task synced via ADD fallback: {task_id}")
                        else:
                            add_errors = add_result.get('errors', [])
                            add_error_str = ', '.join(str(e) for e in add_errors)
                            self.sync_queue.mark_failed(task_id, add_error_str or error_str or 'ADD fallback failed')
                            failed_count += 1
                            logger.warning(f"[OfflineSyncManager] ⚠️ Queue task ADD fallback also failed: {task_id}")
                    elif 'foreign key constraint' in error_str.lower():
                        # Foreign key constraint error - parent record doesn't exist in cloud
                        # This should be handled by dependency sorting, but if it still occurs,
                        # it means the dependency sync failed or the parent record is missing.
                        fk_info = self._check_foreign_key_error(errors, data_type)
                        if fk_info:
                            logger.warning(f"[OfflineSyncManager] ⚠️ FK constraint error for {task_id}: {fk_info['message']}")
                            # Mark as failed but keep it retryable - the parent should be synced first
                            # In a properly sorted queue, this shouldn't happen, but handle it gracefully
                            self.sync_queue.mark_failed(
                                task_id,
                                f"FK constraint: {fk_info['message']}",
                                max_retries=3,  # Allow retries after parent syncs
                                non_retryable=False,
                            )
                            failed_count += 1
                        else:
                            self.sync_queue.mark_failed(task_id, error_str or 'Foreign key constraint error')
                            failed_count += 1
                    elif 'type mismatch' in error_str.lower() and 'expected type list' in error_str.lower():
                        # GraphQL type mismatch error - server expects LIST but received different type
                        # This is a server-side schema issue, mark as non-retryable
                        logger.error(f"[OfflineSyncManager] ❌ GraphQL type mismatch for {task_id}: {error_str}")
                        logger.error(f"[OfflineSyncManager] This indicates a backend schema mismatch. Task will be marked as non-retryable.")
                        self.sync_queue.mark_failed(
                            task_id,
                            f"GraphQL schema error: {error_str}",
                            max_retries=1,
                            non_retryable=True,
                        )
                        failed_count += 1
                    elif 'only available to paid subscribers' in error_str.lower():
                        # Cloud service requires paid subscription
                        logger.warning(f"[OfflineSyncManager] ⚠️ Paid subscription required for {task_id}")
                        self.sync_queue.mark_failed(
                            task_id,
                            'Cloud service requires paid subscription',
                            max_retries=1,
                            non_retryable=True,
                        )
                        failed_count += 1
                    else:
                        # Sync failed, mark as failed
                        self.sync_queue.mark_failed(task_id, error_str or 'Unknown error')
                        failed_count += 1
                        logger.warning(f"[OfflineSyncManager] ⚠️ Queue task failed: {task_id}")
                    
            except Exception as e:
                # Exception, mark as failed
                self.sync_queue.mark_failed(task['id'], str(e))
                failed_count += 1
                logger.error(f"[OfflineSyncManager] ❌ Queue task error: {task['id']} - {e}")
        
        logger.info(f"[OfflineSyncManager] Queue sync completed: {synced_count} synced, {failed_count} failed")
        
        return {
            'success': True,
            'total': len(pending_tasks),
            'synced': synced_count,
            'failed': failed_count
        }
    
    # def load_from_cloud(self, username: str, data_types: Optional[List[str]] = None) -> Dict[str, Any]:
    #     """
    #     从云端加载数据
        
    #     Args:
    #         username: 用户名
    #         data_types: 要加载的数据类型列表，默认为所有类型
        
    #     Returns:
    #         Dict: 加载结果
    #     """
    #     if data_types is None:
    #         data_types = ['skill', 'task', 'agent', 'tool']
        
    #     logger.info(f"[OfflineSyncManager] Loading data from cloud for user: {username}")
        
    #     results = {}
        
    #     for data_type in data_types:
    #         try:
    #             service = get_cloud_service(data_type)
    #             result = service.load_from_cloud(username)
                
    #             if result['success']:
    #                 results[data_type] = {
    #                     'success': True,
    #                     'count': result['count'],
    #                     'items': result['items']
    #                 }
    #                 logger.info(f"[OfflineSyncManager] ✅ Loaded {result['count']} {data_type}(s)")
    #             else:
    #                 results[data_type] = {
    #                     'success': False,
    #                     'error': result.get('error', 'Unknown error')
    #                 }
    #                 logger.error(f"[OfflineSyncManager] ❌ Failed to load {data_type}s")
                    
    #         except Exception as e:
    #             results[data_type] = {
    #                 'success': False,
    #                 'error': str(e)
    #             }
    #             logger.error(f"[OfflineSyncManager] ❌ Error loading {data_type}s: {e}")
        
    #     return results
    
    # def startup_sync(self, username: str) -> Dict[str, Any]:
    #     """
    #     启动时同步流程
        
    #     1. 先同步本地缓存的数据到云端
    #     2. 再从云端加载最新数据
        
    #     Args:
    #         username: 用户名
        
    #     Returns:
    #         Dict: 同步结果
    #     """
    #     logger.info(f"[OfflineSyncManager] 🚀 Starting startup sync for user: {username}")
        
    #     # 步骤 1: 同步本地缓存到云端
    #     logger.info("[OfflineSyncManager] Step 1: Syncing pending queue to cloud...")
    #     queue_result = self.sync_pending_queue()
        
    #     # 步骤 2: 从云端加载数据
    #     logger.info("[OfflineSyncManager] Step 2: Loading data from cloud...")
    #     load_result = self.load_from_cloud(username)
        
    #     # 统计结果
    #     total_loaded = sum(
    #         r.get('count', 0) for r in load_result.values() if r.get('success')
    #     )
        
    #     logger.info(f"[OfflineSyncManager] ✅ Startup sync completed: "
    #                f"{queue_result['synced']} queued synced, "
    #                f"{total_loaded} items loaded")
        
    #     return {
    #         'success': True,
    #         'queue_sync': queue_result,
    #         'cloud_load': load_result,
    #         'total_loaded': total_loaded
    #     }
    
    def start_auto_retry(self, interval: int = 300):
        """
        Start auto-retry thread
        
        Args:
            interval: Retry interval (seconds), default 5 minutes
        """
        if self._retry_thread and self._retry_thread.is_alive():
            logger.warning("[OfflineSyncManager] Auto retry already running")
            return
        
        self._stop_retry = False
        self._retry_thread = threading.Thread(
            target=self._auto_retry_loop,
            args=(interval,),
            daemon=True
        )
        self._retry_thread.start()
        logger.info(f"[OfflineSyncManager] Auto retry started (interval: {interval}s)")
    
    def stop_auto_retry(self):
        """Stop auto-retry thread and thread pool"""
        # Stop auto-retry thread
        self._stop_retry = True
        if self._retry_thread:
            self._retry_thread.join(timeout=5)
        
        # Shutdown thread pool
        self._executor.shutdown(wait=False)
        
        logger.info("[OfflineSyncManager] Auto retry stopped and thread pool shutdown")
    
    def _auto_retry_loop(self, interval: int):
        """Auto-retry loop"""
        while not self._stop_retry:
            try:
                # Wait for interval
                for _ in range(interval):
                    if self._stop_retry:
                        break
                    time.sleep(1)
                
                if self._stop_retry:
                    break
                
                # Check if there are pending tasks
                stats = self.sync_queue.get_stats()
                if stats['pending_count'] > 0:
                    logger.info(f"[OfflineSyncManager] Auto retry: {stats['pending_count']} pending tasks")
                    self.sync_pending_queue()
                    
            except Exception as e:
                logger.error(f"[OfflineSyncManager] Auto retry error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get sync statistics"""
        return self.sync_queue.get_stats()


# Global singleton
_offline_sync_manager: Optional[OfflineSyncManager] = None


def get_sync_manager() -> OfflineSyncManager:
    """Get global offline sync manager instance (legacy name for compatibility)"""
    global _offline_sync_manager
    if _offline_sync_manager is None:
        _offline_sync_manager = OfflineSyncManager()
    return _offline_sync_manager


def get_offline_sync_manager() -> OfflineSyncManager:
    """Get global offline sync manager instance"""
    return get_sync_manager()
