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
    OFFLINE_SYNC_ENABLED = False  # 启用/禁用离线同步功能
    
    def __init__(self):
        """Initialize offline sync manager"""
        self.sync_queue = get_offline_sync_queue()
        self._retry_thread = None
        self._stop_retry = False
        
        # Thread pool for async sync (max 5 concurrent)
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='CloudSync')
        
        logger.info("[OfflineSyncManager] Initialized with thread pool (max_workers=5)")
        logger.info(f"[OfflineSyncManager] OFFLINE_SYNC_ENABLED={self.OFFLINE_SYNC_ENABLED}")
    
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
                logger.info(f"[OfflineSyncManager] ✅ Synced to cloud: {data_type}.{operation} - {data_name}")
                if 'response' in result:
                    logger.debug(f"[OfflineSyncManager] Cloud response: {result['response']}")
                return {
                    'success': True,
                    'synced': True,
                    'cached': False,
                    'message': 'Synced to cloud successfully',
                    'response': result.get('response')
                }
            else:
                # Sync failed, check if we should add to queue
                errors = result.get('errors', [])
                
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
                    # Sync failed, mark as failed
                    error = ', '.join(result.get('errors', ['Unknown error']))
                    self.sync_queue.mark_failed(task_id, error)
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
