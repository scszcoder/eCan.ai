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
from agent.cloud_api.fk_metadata import build_fk_dependency_config
from agent.cloud_api.sync_rules import is_permanent_sync_error, validate_preflight


class OfflineSyncManager:
    """Offline Sync Manager - Handles online/offline synchronization"""
    
    # FK 依赖配置：从 fk_metadata 模块动态构建
    # 格式：{(data_type, operation, fk_constraint): (dep_field, dep_type, service_name, DataType)}
    # 
    # 添加新的 FK 依赖处理时，只需在 agent/cloud_api/fk_metadata.py 中的 FK_CONSTRAINTS 添加即可
    # 这样可以保持数据库 schema 和代码的一致性
    FK_DEPENDENCY_CONFIG = build_fk_dependency_config()
    
    # 配置变量：启用/禁用离线同步功能
    OFFLINE_SYNC_ENABLED = True

    @staticmethod
    def _is_dependency_missing_error(error: str, constraint_name: str) -> bool:
        err = str(error or "").lower()
        return (
            "foreign key constraint fails" in err
            and constraint_name.lower() in err
            and "error code: 1452" in err
        )

    @staticmethod
    def _is_permanent_error(error: str) -> bool:
        return is_permanent_sync_error(error)

    def _has_pending_dependency_task(self, data_type: DataType, dep_id: str) -> bool:
        try:
            for task in self.sync_queue.get_pending_tasks(data_type.value):
                task_data = task.get("data") or {}
                if task_data.get("id") == dep_id:
                    return True
            return False
        except Exception as e:
            logger.debug(f"[OfflineSyncManager] Failed checking pending dependency {data_type}:{dep_id}: {e}")
            return False

    def _retry_failed_dependency_task(self, data_type: DataType, dep_id: str) -> bool:
        try:
            for task in self.sync_queue.get_failed_tasks(data_type.value):
                task_data = task.get("data") or {}
                if task_data.get("id") == dep_id:
                    self.sync_queue.retry_failed_task(task["id"])
                    logger.info(f"[OfflineSyncManager] Revived failed dependency task for {data_type.value}: {dep_id}")
                    return True
            return False
        except Exception as e:
            logger.debug(f"[OfflineSyncManager] Failed reviving dependency {data_type}:{dep_id}: {e}")
            return False

    def _enqueue_missing_dependency(self, dep_type: str, dep_id: str, service_name: str, data_type: DataType) -> bool:
        """通用依赖补全方法
        
        Args:
            dep_type: 依赖类型名称（用于日志）
            dep_id: 依赖资源 ID
            service_name: DB 服务名称（如 'org_service', 'avatar_service'）
            data_type: 依赖资源的 DataType
        """
        try:
            from app_context import AppContext

            main_window = AppContext.get_main_window()
            if not main_window or not getattr(main_window, "ec_db_mgr", None):
                logger.warning(f"[OfflineSyncManager] Cannot backfill {dep_type} dependency {dep_id}: main window or DB manager unavailable")
                return False

            service = getattr(main_window.ec_db_mgr, service_name, None)
            if not service:
                logger.warning(f"[OfflineSyncManager] Cannot backfill {dep_type} dependency {dep_id}: {service_name} unavailable")
                return False

            get_method_candidates = {
                'agent': ('get_agent_by_id', 'query_agents', 'search_agents'),
                'task': ('get_task_by_id', 'query_tasks', 'search_tasks'),
                'organization': ('get_org_by_id', 'query_organizations', 'search_organizations'),
                'skill': ('get_skill_by_id', 'query_skills', 'search_skills'),
                'tool': ('get_tool_by_id', 'query_tools', 'search_tools'),
                'knowledge': ('get_knowledge_by_id', 'query_knowledges', 'search_knowledges'),
                'vehicle': ('get_vehicle_by_id', 'query_vehicles', 'search_vehicles'),
                'avatar_resource': ('get_avatar_by_id',),
            }
            candidate_names = get_method_candidates.get(dep_type, (f"get_{dep_type.lower()}_by_id",))
            get_method = next((getattr(service, name, None) for name in candidate_names if getattr(service, name, None)), None)
            if not get_method:
                logger.warning(f"[OfflineSyncManager] Cannot backfill {dep_type} dependency {dep_id}: no supported fetch method found")
                return False

            method_name = getattr(get_method, '__name__', '')
            if method_name.startswith('query_') or method_name.startswith('search_'):
                result = get_method(id=dep_id)
            else:
                result = get_method(dep_id)

            dep_data = None
            if isinstance(result, dict):
                dep_data = result.get("data")
                if isinstance(dep_data, list):
                    dep_data = dep_data[0] if dep_data else None
            elif isinstance(result, list):
                dep_data = result[0] if result else None

            if not dep_data and dep_type == 'agent':
                try:
                    from agent.agent_service import get_agent_by_id as get_agent_from_memory
                    mem_agent = get_agent_from_memory(dep_id)
                    if mem_agent and hasattr(mem_agent, 'card'):
                        dep_data = {
                            'id': getattr(mem_agent.card, 'id', None),
                            'name': getattr(mem_agent.card, 'name', None),
                            'description': getattr(mem_agent.card, 'description', None),
                            'url': getattr(mem_agent.card, 'url', None),
                            'version': getattr(mem_agent.card, 'version', None),
                            'avatar_resource_id': getattr(mem_agent.card, 'avatar_id', None),
                        }
                        owner = getattr(mem_agent, 'owner', None) or getattr(mem_agent.card, 'owner', None)
                        if owner:
                            dep_data['owner'] = owner
                except Exception as memory_fetch_e:
                    logger.debug(f"[OfflineSyncManager] Memory fallback failed for agent dependency {dep_id}: {memory_fetch_e}")

            if not dep_data:
                logger.warning(f"[OfflineSyncManager] Cannot backfill {dep_type} dependency {dep_id}: local resource not found")
                return False

            # 检查是否已在队列中
            if self._has_pending_dependency_task(data_type, dep_id):
                logger.info(f"[OfflineSyncManager] {dep_type} dependency already queued: {dep_id}")
                return True

            if self._retry_failed_dependency_task(data_type, dep_id):
                logger.info(f"[OfflineSyncManager] {dep_type} dependency moved from failed queue back to pending: {dep_id}")
                return True

            self.sync_queue.add(data_type, dep_data, Operation.ADD)
            logger.info(f"[OfflineSyncManager] ✅ Queued missing {dep_type} dependency: {dep_id}")
            return True
        except Exception as e:
            logger.warning(f"[OfflineSyncManager] Failed to enqueue {dep_type} dependency {dep_id}: {e}")
            return False
    
    def _retry_update_as_add(self, task_id: str, data_type_str: str, data: dict, service, timeout: float, original_error: str) -> bool:
        """UPDATE NOT_FOUND 时重试 ADD 操作的通用方法
        
        Args:
            task_id: 任务 ID
            data_type_str: 数据类型字符串
            data: 数据内容
            service: 云服务实例
            timeout: 超时时间
            original_error: 原始错误信息
            
        Returns:
            bool: 是否成功
        """
        logger.info(f"[OfflineSyncManager] 🔄 {data_type_str} UPDATE NOT_FOUND, retrying with ADD: {task_id}")
        add_result = service.sync_to_cloud([data], operation=Operation.ADD, timeout=timeout)
        
        if add_result['success']:
            self.sync_queue.mark_success(task_id)
            logger.info(f"[OfflineSyncManager] ✅ {data_type_str} synced via ADD fallback: {task_id}")
            return True
        else:
            add_errors = add_result.get('errors', [])
            add_error_str = ', '.join(str(e) for e in add_errors)
            add_error_lower = add_error_str.lower()
            add_is_duplicate = '1062' in add_error_str or 'duplicate entry' in add_error_lower
            add_is_already_exists = 'already exists' in add_error_lower
            
            if add_is_duplicate or add_is_already_exists:
                self.sync_queue.mark_success(task_id)
                logger.info(f"[OfflineSyncManager] ✅ {data_type_str} ADD fallback hit existing record: {task_id}")
                return True
            else:
                self.sync_queue.mark_failed(task_id, add_error_str or original_error or 'ADD fallback failed')
                logger.warning(f"[OfflineSyncManager] ⚠️ {data_type_str} ADD fallback also failed: {task_id}")
                return False
    
    def __init__(self):
        """Initialize offline sync manager"""
        self.sync_queue = get_offline_sync_queue()
        self._retry_thread = None
        self._stop_retry = False
        
        # Thread pool for async sync (max 5 concurrent)
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='CloudSync')
        
        logger.info("[OfflineSyncManager] Initialized with thread pool (max_workers=5)")
        logger.info(f"[OfflineSyncManager] OFFLINE_SYNC_ENABLED={self.OFFLINE_SYNC_ENABLED}")
        self._cleanup_invalid_pending_tasks()

    def _cleanup_invalid_pending_tasks(self):
        try:
            invalid_task_ids = []
            for task in self.sync_queue.get_pending_tasks():
                data_type = task.get('data_type')
                operation = task.get('operation')
                data = task.get('data') or {}
                try:
                    data_type_enum = DataType(data_type)
                except Exception:
                    continue
                if validate_preflight(data_type_enum, [data], operation):
                    invalid_task_ids.append(task.get('id'))

            for task_id in invalid_task_ids:
                self.sync_queue.mark_failed(task_id, 'Preflight cleanup: invalid sync task', max_retries=1)

            if invalid_task_ids:
                logger.warning(f"[OfflineSyncManager] Cleaned up {len(invalid_task_ids)} invalid pending sync task(s)")
        except Exception as e:
            logger.warning(f"[OfflineSyncManager] Failed to clean invalid pending tasks: {e}")
    
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
                error_str = ' '.join(str(e) for e in errors)
                if self._is_permanent_error(error_str):
                    logger.warning(f"[OfflineSyncManager] ⛔ Permanent sync error, not caching: {data_type}.{operation} - {data_name}")
                    logger.warning(f"[OfflineSyncManager] Errors: {errors}")
                    return {
                        'success': False,
                        'synced': False,
                        'cached': False,
                        'message': 'Permanent sync error',
                        'errors': errors,
                        'response': result.get('response')
                    }
                if '1062' in error_str or 'Duplicate entry' in error_str:
                    logger.info(f"[OfflineSyncManager] ✅ Record already exists in cloud (duplicate key), treating as success: {data_type}.{operation} - {data_name}")
                    return {
                        'success': True,
                        'synced': True,
                        'cached': False,
                        'message': 'Record already exists in cloud',
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
            failed_tasks = [
                task for task in self.sync_queue.get_failed_tasks()
                if not self._is_permanent_error(task.get('last_error', ''))
            ]
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
        deferred_count = 0
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
                    # 错误处理：使用配置驱动的统一处理逻辑
                    errors = result.get('errors', [])
                    error_str = ', '.join(str(e) for e in errors)
                    error_lower = error_str.lower()
                    operation_str = operation.value if hasattr(operation, 'value') else str(operation)
                    data_type_str = data_type.value if hasattr(data_type, 'value') else str(data_type)
                    
                    # 通用错误检测
                    is_duplicate = '1062' in error_str or 'duplicate entry' in error_lower
                    is_already_exists = 'already exists' in error_lower
                    is_not_found = 'not_found' in error_lower or 'not found' in error_lower
                    
                    is_permanent = self._is_permanent_error(error_str)

                    # 1. 处理重复键错误（记录已存在）
                    if is_duplicate or is_already_exists:
                        self.sync_queue.mark_success(task_id)
                        synced_count += 1
                        logger.info(f"[OfflineSyncManager] ✅ Record already exists in cloud: {task_id}")

                    # 2. 处理永久性权限/认证错误（不重试）
                    elif is_permanent:
                        self.sync_queue.mark_failed(task_id, error_str or 'Permanent permission/auth error', max_retries=1)
                        failed_count += 1
                        logger.warning(f"[OfflineSyncManager] ⛔ Permanent sync error, will not retry: {task_id}")

                    # 3. 处理 FK 依赖缺失错误（使用类级别配置）
                    else:
                        fk_handled = False
                        for (dt, op, fk_name), (field, dep_type, service_name, dtype) in self.FK_DEPENDENCY_CONFIG.items():
                            if (data_type_str == dt and operation_str == op and 
                                self._is_dependency_missing_error(error_str, fk_name)):
                                dep_id = (data or {}).get(field)
                                if dep_id and self._has_pending_dependency_task(dtype, dep_id):
                                    self.sync_queue.defer_task(task_id, f'Waiting for queued {dep_type} dependency')
                                    deferred_count += 1
                                    logger.info(f"[OfflineSyncManager] ⏳ Deferred {data_type_str} task until queued {dep_type} sync completes: {task_id}")
                                elif dep_id and self._enqueue_missing_dependency(dep_type, dep_id, service_name, dtype):
                                    self.sync_queue.defer_task(task_id, f'Missing {dep_type} dependency')
                                    deferred_count += 1
                                    logger.info(f"[OfflineSyncManager] ⏳ Deferred {data_type_str} task until {dep_type} exists: {task_id}")
                                else:
                                    self.sync_queue.mark_failed(task_id, f'Missing {dep_type} dependency')
                                    failed_count += 1
                                    logger.warning(f"[OfflineSyncManager] ⚠️ Failed to backfill {dep_type} dependency: {task_id}")
                                fk_handled = True
                                break
                        
                        if not fk_handled:
                            # 4. 处理 UPDATE NOT_FOUND（重试 ADD）
                            if operation_str == 'update' and is_not_found and data_type_str in ('agent', 'skill'):
                                success = self._retry_update_as_add(task_id, data_type_str, data, service, timeout_per_task, error_str)
                                if success:
                                    synced_count += 1
                                else:
                                    failed_count += 1
                            
                            # 5. 处理 DELETE NOT_FOUND（标记成功）
                            elif operation_str == 'delete' and is_not_found:
                                self.sync_queue.mark_success(task_id)
                                synced_count += 1
                                logger.info(f"[OfflineSyncManager] ✅ {data_type_str} already absent in cloud: {task_id}")
                            
                            # 6. 其他错误
                            else:
                                self.sync_queue.mark_failed(task_id, error_str or 'Unknown error')
                                failed_count += 1
                                logger.warning(f"[OfflineSyncManager] ⚠️ Queue task failed: {task_id}")
                    
            except Exception as e:
                # Exception, mark as failed
                self.sync_queue.mark_failed(task['id'], str(e))
                failed_count += 1
                logger.error(f"[OfflineSyncManager] ❌ Queue task error: {task['id']} - {e}")
        
        logger.info(f"[OfflineSyncManager] Queue sync completed: {synced_count} synced, {deferred_count} deferred, {failed_count} failed")
        
        return {
            'success': True,
            'total': len(pending_tasks),
            'synced': synced_count,
            'deferred': deferred_count,
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
