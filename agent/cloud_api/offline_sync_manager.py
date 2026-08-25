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

        # State machine driven by SessionSupervisor events:
        #   "active"      — token is fresh (or being refreshed); pull work.
        #   "expiring"    — session will die soon; pause retries, the
        #                   supervisor will either refresh or fire expired.
        #   "paused"      — no usable token; resume on on_session_refreshed.
        self._session_state = "active"
        self._pause_lock = threading.Condition()
        self._supervisor_wired = False

        self._wire_session_supervisor()

        logger.info("[OfflineSyncManager] Initialized with thread pool (max_workers=5)")
        logger.info(f"[OfflineSyncManager] OFFLINE_SYNC_ENABLED={self.OFFLINE_SYNC_ENABLED}")

    @staticmethod
    def _is_duplicate_error(errors: List[Any]) -> bool:
        """Check whether the error list indicates an idempotent duplicate-key failure."""
        error_str = ' '.join(str(e) for e in errors)
        return ('1062' in error_str or 'Duplicate entry' in error_str
                or 'ID_TAKEN' in error_str)

    @staticmethod
    def _is_non_retryable_error(errors: List[Any]) -> bool:
        """Check whether the error list indicates a permanent authorization/configuration failure.

        Also catches permanent GraphQL schema mismatches (backend SDL does not
        declare a selected field). Retrying those payloads never converges and
        floods the log; treat them as non-retryable so the queue task moves to
        failed immediately and the next sync attempts can decide what to do.

        Order matters: ``_is_token_expired_error`` runs first in the caller
        (sync_pending_queue) so UNAUTHENTICATED / "access token has expired"
        responses get a chance to be refreshed before being labeled permanent.
        """
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
            # GraphQL validation: backend SDL lacks a selected field.
            # Example: client selects `upload_urls` on SkillMutationResult but
            # the active backend (e.g. CN TCB) does not declare it.
            'cannot query field',
            'graphql_validation_failed',
        )
        return any(marker in error_str for marker in non_retryable_markers)

    @staticmethod
    def _is_token_expired_error(errors: List[Any]) -> bool:
        """Detect UNAUTHENTICATED / Invalid-or-expired access token responses.

        These are NOT permanent failures (the session can be refreshed via
        refresh_token or a silent re-auth) and they are NOT ordinary transient
        failures (retrying with the same token just hits the same wall). The
        OfflineSyncManager should leave the task in the pending queue without
        advancing retry_count and stop processing the rest of the batch until
        the SessionSupervisor has had a chance to refresh.
        """
        error_str = ' '.join(str(e) for e in errors).lower()
        token_expired_markers = (
            'unauthenticated',
            'invalid or expired access token',
            'access token has expired',
            'expired access token',
            'token expired',
        )
        return any(marker in error_str for marker in token_expired_markers)

    # ------------------------------------------------------------------
    # Session supervisor wiring
    # ------------------------------------------------------------------
    def _wire_session_supervisor(self) -> None:
        """Subscribe to the global SessionSupervisor, if one is installed.

        Wires up exactly once even if called from multiple code paths. We
        use a flag instead of re-checking for the supervisor so that the
        wiring happens during ``__init__`` regardless of install order.
        """
        if self._supervisor_wired:
            return
        try:
            from auth.session_supervisor import get_session_supervisor
        except Exception as exc:
            logger.debug(
                f"[OfflineSyncManager] SessionSupervisor not available: {exc}"
            )
            return
        supervisor = get_session_supervisor()
        if supervisor is None:
            # Supervisor will be installed later; don't poll. We re-try on
            # the first call to sync_pending_queue instead.
            return
        supervisor.on_session_expiring_soon(self._on_session_expiring)
        supervisor.on_session_refreshed(self._on_session_refreshed)
        supervisor.on_session_expired(self._on_session_expired)
        self._supervisor_wired = True
        logger.info("[OfflineSyncManager] Subscribed to SessionSupervisor events")

    # ------------------------------------------------------------------
    # Token-rejection nudge to SessionSupervisor
    # ------------------------------------------------------------------
    # Throttle so a single dead token doesn't generate one nudge per write
    # attempt. The supervisor's tick is cheap and idempotent, but logging
    # 30 "refresh attempted" lines per dead-token event is noise.
    _last_token_rejection_notify_ts: float = 0.0
    _TOKEN_REJECTION_NOTIFY_THROTTLE_SECONDS = 5.0

    def _notify_supervisor_of_token_rejection(self, source: str) -> None:
        """Tell SessionSupervisor the cloud rejected our access token.

        The supervisor's 30s tick treats an already-expired token as a
        no-op (assuming AuthManager will clean it up on its next
        ensure_valid_tokens() call), but OfflineSyncManager writes go
        straight to the cloud without going through AuthManager.
        Without this nudge, every sync attempt in the next 30s hits the
        same UNAUTHENTICATED wall before the supervisor reacts.
        """
        import time as _time
        now = _time.monotonic()
        if now - self._last_token_rejection_notify_ts < self._TOKEN_REJECTION_NOTIFY_THROTTLE_SECONDS:
            return
        self._last_token_rejection_notify_ts = now
        try:
            from auth.session_supervisor import get_session_supervisor
            supervisor = get_session_supervisor()
            if supervisor is not None:
                supervisor.notify_token_rejected(source=source)
        except Exception as exc:
            logger.debug(
                f"[OfflineSyncManager] notify_token_rejected skipped: {exc}"
            )

    def _on_session_expiring(self, info: Dict[str, Any]) -> None:
        """Token will die in <= EXPIRING_SOON. Pause background retries."""
        with self._pause_lock:
            self._session_state = "expiring"
        logger.info(
            f"[OfflineSyncManager] Session expiring soon (exp={info.get('exp')}); "
            "pausing background retries"
        )

    def _on_session_refreshed(self, info: Dict[str, Any]) -> None:
        """New token installed. Resume background retries.

        Just wake any thread blocked in ``_wait_for_active_session`` — do
        NOT call ``sync_pending_queue`` from here.  Doing so used to look
        like a useful "kick" but turned into a 401 → nudge → refresh →
        notify_token_installed → sync again infinite loop on the WeChat
        session-token path.  The legitimate retry path is:

          - ``sync_pending_queue`` is in progress: ``_wait_for_active_session``
            returns and the SAME call resumes from the failed task. The
            nudge + wait + continue pattern (see line ~810) handles that.
          - background auto-retry: its 5-min tick picks it up next round.

        Removing the inline ``self.sync_pending_queue()`` shuts down the
        storm without changing user-visible behaviour (the queue drains on
        the next tick either way).
        """
        with self._pause_lock:
            self._session_state = "active"
            self._pause_lock.notify_all()
        logger.info("[OfflineSyncManager] Session refreshed; resuming retries")

    def _on_session_expired(self) -> None:
        """Refresh failed; session is dead. Park pending work, wait for re-login."""
        with self._pause_lock:
            self._session_state = "paused"
        logger.warning(
            "[OfflineSyncManager] Session expired (no refresh token or refresh "
            "failed). Background retries paused until user re-logs in."
        )

    # How long after a fresh token install we should treat a server 401
    # as cache lag rather than a real auth failure. Kept in sync with the
    # SessionSupervisor grace in ``auth.session_supervisor.SessionSupervisor
    # .is_fresh_token_rejection``.
    _FRESH_TOKEN_REJECTION_SECONDS = 60

    def _is_fresh_token_rejection(self) -> bool:
        """Decide whether a 401 right now looks like CloudBase cache lag.

        Delegates to the global SessionSupervisor when one is wired.
        Returns False when no supervisor is installed (tests, web mode
        without auth), so non-CloudBase flows keep their old behavior.
        """
        try:
            from auth.session_supervisor import get_session_supervisor
            supervisor = get_session_supervisor()
            if supervisor is None:
                return False
        except Exception:
            return False
        return supervisor.is_fresh_token_rejection()

    def _wait_for_active_session(self, timeout: float = 0.0) -> bool:
        """Block (up to ``timeout`` seconds) until the session is active.

        Returns True if active, False if still paused/expired when the
        timeout expires.  Called from ``sync_pending_queue`` so the
        auto-retry loop doesn't hammer the API while we know the token is
        dead.
        """
        with self._pause_lock:
            if self._session_state == "active":
                return True
            if timeout <= 0:
                return False
            return self._pause_lock.wait_for(
                lambda: self._session_state == "active",
                timeout=timeout,
            )

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

                # Token expired / UNAUTHENTICATED — not a permanent failure and
                # not an ordinary transient failure. Retrying with the same dead
                # token just hits UNAUTHENTICATED again, and adding the task to
                # the queue only spams logs on the next tick (sync_pending_queue
                # already pauses batches on token-expired).  Notify the
                # SessionSupervisor (it may already know, but a direct nudge
                # cuts the lag from up to 30s to a few seconds for the NEXT
                # sync attempt) and return without queuing. The caller can
                # retry later, by which time the supervisor should have rotated
                # the token.
                if self._is_token_expired_error(errors):
                    logger.info(
                        f"[OfflineSyncManager] 🔑 Sync skipped: token "
                        f"expired for {data_type}.{operation} - {data_name}; "
                        f"waiting for supervisor refresh"
                    )
                    self._notify_supervisor_of_token_rejection(f"sync_to_cloud:{data_type}.{operation}")
                    return {
                        'success': True,
                        'synced': False,
                        'cached': False,
                        'message': 'Token expired; awaiting SessionSupervisor refresh',
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
        # The FK reference tells us the parent table
        # Example: CONSTRAINT `fk_asr_skill` FOREIGN KEY (`skill_id`) REFERENCES `agent_skills` (`id`)
        if data_type == DataType.AGENT_SKILL:
            # Check which FK constraint failed based on the REFERENCES clause
            if 'references `agent_skills`' in error_str or 'fk_asr_skill' in error_str:
                # FK: skill_id → agent_skills(id), need SKILL to exist
                # But wait - agent_skill_rels.skill_id should reference agent_skills.id
                # So we need to sync the skill that this agent_skill points to
                return {
                    'dependency_type': DataType.SKILL,
                    'dependency_operation': Operation.ADD,
                    'message': 'Skill not found in cloud (agent_skill references non-existent skill)'
                }
            elif 'references `agents`' in error_str or 'fk_asr_agent' in error_str:
                return {
                    'dependency_type': DataType.AGENT,
                    'dependency_operation': Operation.ADD,
                    'message': 'Agent not found in cloud'
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

    def _extract_parent_data(self, child_data: Dict[str, Any], dependency_type: DataType, child_type: DataType, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract parent record data from child data or local DB for syncing parent first.

        Args:
            child_data: The child record data
            dependency_type: The parent data type (AGENT, SKILL, etc.)
            child_type: The child data type (AGENT_SKILL, AGENT_TASK, etc.)
            task: The original task from the queue

        Returns:
            Parent record data if found, None otherwise
        """
        try:
            # Try to extract parent ID from child data
            parent_id = None
            if dependency_type == DataType.AGENT:
                # Extract agent_id from agent_skill, agent_task, agent_tool
                parent_id = child_data.get('agid') or child_data.get('agent_id')
            elif dependency_type == DataType.SKILL:
                # Extract skill_id from agent_skill, skill_tool, etc.
                parent_id = child_data.get('skid') or child_data.get('skill_id')

            if not parent_id:
                logger.warning(f"[OfflineSyncManager] Could not extract parent_id from child_data: {child_data}")
                return None

            # Try to get full parent record from local DB
            if dependency_type == DataType.AGENT:
                try:
                    from app_context import AppContext
                    ec_db_mgr = AppContext.get_ec_db_mgr()
                    if ec_db_mgr and ec_db_mgr.agent_service:
                        db_result = ec_db_mgr.agent_service.query_agents(id=parent_id)
                        full_agent = (db_result.get('data') or [None])[0] if db_result.get('success') else None
                        if full_agent:
                            logger.info(f"[OfflineSyncManager] 📋 Extracted full agent record from DB: {parent_id} ({full_agent.get('name', 'unknown')})")
                            return full_agent
                except Exception as db_err:
                    logger.warning(f"[OfflineSyncManager] DB lookup for agent {parent_id} failed: {db_err}")

            elif dependency_type == DataType.SKILL:
                try:
                    from app_context import AppContext
                    ec_db_mgr = AppContext.get_ec_db_mgr()
                    if ec_db_mgr and ec_db_mgr.skill_service:
                        db_result = ec_db_mgr.skill_service.query_skills(id=parent_id)
                        full_skill = (db_result.get('data') or [None])[0] if db_result.get('success') else None
                        if full_skill:
                            logger.info(f"[OfflineSyncManager] 📋 Extracted full skill record from DB: {parent_id} ({full_skill.get('name', 'unknown')})")
                            return full_skill
                except Exception as db_err:
                    logger.warning(f"[OfflineSyncManager] DB lookup for skill {parent_id} failed: {db_err}")

            # Fallback: construct minimal parent record from child data
            logger.warning(f"[OfflineSyncManager] ⚠️ Could not fetch full record from DB, using minimal parent data")
            if dependency_type == DataType.AGENT:
                return {
                    'id': parent_id,
                    'owner': child_data.get('owner', 'unknown'),
                    'name': f"Agent_{parent_id[:8]}",
                }
            elif dependency_type == DataType.SKILL:
                return {
                    'id': parent_id,
                    'name': f"Skill_{parent_id[:8]}",
                }

            return None

        except Exception as e:
            logger.error(f"[OfflineSyncManager] Error extracting parent data: {e}")
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
        # If the supervisor already knows the session is dead or about to die,
        # do not hammer the API. Wait briefly for the supervisor to refresh
        # (Cognito refresh-token flow) or to be told the user has to re-login
        # (CloudBase WeChat, no refresh_token). Without this gate, every queued
        # retry returns UNAUTHENTICATED and the log fills with "Task retry N/3"
        # spam even though the supervisor is already on the case.
        if self._session_state == "paused":
            logger.info(
                "[OfflineSyncManager] Sync skipped: session is paused "
                "(no usable token; waiting for user re-login)"
            )
            return {
                'success': True,
                'total': 0,
                'synced': 0,
                'failed': 0,
                'skipped': 'session_paused',
            }
        if self._session_state == "expiring":
            # Brief wait — supervisor is actively trying to refresh. We only
            # block for a short window so the caller's timeout budget isn't
            # blown; if the refresh hasn't completed by then we abort this
            # run and let the next auto-retry tick pick it up.
            if not self._wait_for_active_session(timeout=2.0):
                logger.info(
                    "[OfflineSyncManager] Sync skipped: token refresh did not "
                    "complete within 2s; will retry on next tick"
                )
                return {
                    'success': True,
                    'total': 0,
                    'synced': 0,
                    'failed': 0,
                    'skipped': 'session_expiring',
                }

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

        # Loop over tasks with restart-on-refresh: when a task hits
        # UNAUTHENTICATED we nudge the supervisor, wait for the session
        # to become active again, and resume from the SAME task (not the
        # next one) so a silent WeChat re-auth doesn't leave the rest of
        # the batch stranded until the next 5-min auto-retry tick.
        cursor = 0
        while cursor < len(pending_tasks):
            task = pending_tasks[cursor]
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
                    cursor += 1
                else:
                    # Check for duplicate key errors - record already exists, treat as success
                    errors = result.get('errors', [])
                    error_str = ', '.join(str(e) for e in errors)
                    if self._is_duplicate_error(errors):
                        self.sync_queue.mark_success(task_id)
                        synced_count += 1
                        logger.info(f"[OfflineSyncManager] ✅ Queue task: record already exists in cloud (duplicate key), marking as success: {task_id}")
                        cursor += 1
                    elif self._is_token_expired_error(errors):
                        # Access token is dead/expired. The retry with the same
                        # token will never succeed; only the SessionSupervisor's
                        # next refresh tick can fix this. Nudge the supervisor
                        # (force=True on its end means local TTL is ignored),
                        # wait for the refresh/silent-reauth to land, then
                        # retry THIS task. The remaining tasks in the batch
                        # are processed in the same loop iteration after we
                        # resume.
                        #
                        # This MUST be checked BEFORE _is_non_retryable_error,
                        # because UNAUTHENTICATED responses also contain tokens
                        # like "unauthorized" that we don't want to interpret
                        # as permanent auth failures.
                        #
                        # Fresh-token guard: if the supervisor just installed
                        # a token moments ago, the rejection is overwhelmingly
                        # likely a CloudBase upstream cache lag (the SCF
                        # gateway takes 30-60s to see a freshly minted JWT).
                        # The supervisor itself will suppress ``on_session_expired``
                        # via its grace window, but it has no way to back THIS
                        # loop off — without help, we'd hammer the API every
                        # ~125ms until the cache catches up (observed in
                        # runlog 2026-08-14 10:45:09 where the same task
                        # retried at .263, .387, .553 and so on). Park this
                        # task back on the queue and exit the batch; the next
                        # auto-retry tick will pick it up after the grace has
                        # elapsed and, with high probability, the cache will
                        # have caught up by then.
                        if self._is_fresh_token_rejection():
                            logger.info(
                                f"[OfflineSyncManager] ⏳ Token rejected but "
                                f"supervisor marked it fresh — leaving "
                                f"{task_id} on the queue, exiting batch to "
                                f"back off the cache-lag window."
                            )
                            # Don't mark as failed, don't retry now. Just
                            # stop processing this batch.
                            break
                        logger.warning(
                            f"[OfflineSyncManager] 🔑 Queue task hit UNAUTHENTICATED "
                            f"({task_id}). Nudging supervisor and waiting for "
                            f"refresh before retrying (remaining batch tasks "
                            f"after cursor will run in the same tick)."
                        )
                        self._notify_supervisor_of_token_rejection(
                            f"sync_pending_queue:{task_id}"
                        )
                        # Brief wait for the supervisor to install a new token.
                        # The OAuth round-trip for CloudBase WeChat can take a
                        # few seconds; cap the wait so the caller's overall
                        # budget isn't blown. If we time out, the task stays
                        # on the pending queue for the next auto-retry tick.
                        refreshed = self._wait_for_active_session(timeout=8.0)
                        if not refreshed:
                            logger.warning(
                                f"[OfflineSyncManager] ⚠️ Token refresh did not "
                                f"complete within 8s; leaving {task_id} pending "
                                f"and stopping the batch."
                            )
                            # Mark this task as a soft failure (we DID try), and
                            # stop the batch so the remaining tasks aren't
                            # wasted on the still-dead token.
                            failed_count += 1
                            break
                        # Token refreshed — loop will retry this same task.
                        continue
                    elif self._is_non_retryable_error(errors):
                        self.sync_queue.mark_failed(
                            task_id,
                            error_str or 'Non-retryable authorization/configuration error',
                            max_retries=1,
                            non_retryable=True,
                        )
                        failed_count += 1
                        logger.error(f"[OfflineSyncManager] ❌ Queue task hit non-retryable cloud error, stopping retries: {task_id}")
                        cursor += 1
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
                        cursor += 1
                    elif 'foreign key constraint' in error_str.lower():
                        # Foreign key constraint error - parent record doesn't exist in cloud
                        # Try to sync the parent record first, then retry this task
                        fk_info = self._check_foreign_key_error(errors, data_type)
                        if fk_info:
                            logger.warning(f"[OfflineSyncManager] ⚠️ FK constraint error for {task_id}: {fk_info['message']}")

                            # Try to sync the parent record first
                            dependency_type = fk_info.get('dependency_type')
                            dependency_operation = fk_info.get('dependency_operation')
                            if dependency_type and dependency_operation:
                                parent_data = self._extract_parent_data(data, dependency_type, data_type, task)
                                if parent_data:
                                    logger.info(f"[OfflineSyncManager] 🔄 Attempting to sync parent {dependency_type} first...")
                                    try:
                                        parent_service = get_cloud_service(dependency_type)
                                        parent_result = parent_service.sync_to_cloud([parent_data], operation=dependency_operation, timeout=timeout_per_task)
                                        if parent_result.get('success'):
                                            logger.info(f"[OfflineSyncManager] ✅ Parent {dependency_type} synced successfully, retrying {task_id}")
                                            # Retry the original task immediately
                                            retry_result = service.sync_to_cloud([data], operation=operation, timeout=timeout_per_task)
                                            if retry_result.get('success'):
                                                self.sync_queue.mark_success(task_id)
                                                synced_count += 1
                                                logger.info(f"[OfflineSyncManager] ✅ FK task retried successfully: {task_id}")
                                            else:
                                                retry_errors = retry_result.get('errors', [])
                                                self.sync_queue.mark_failed(task_id, ', '.join(str(e) for e in retry_errors) or 'Retry failed')
                                                failed_count += 1
                                        else:
                                            # Parent sync failed - check if it's ID_TAKEN (record already exists)
                                            parent_errors = parent_result.get('errors', [])
                                            parent_error_str = ', '.join(str(e) for e in parent_errors)
                                            if self._is_duplicate_error(parent_errors):
                                                # Parent already exists in cloud, retry the child task
                                                logger.info(f"[OfflineSyncManager] ✅ Parent {dependency_type} already exists (ID_TAKEN), retrying {task_id}")
                                                retry_result = service.sync_to_cloud([data], operation=operation, timeout=timeout_per_task)
                                                if retry_result.get('success') or self._is_duplicate_error(retry_result.get('errors', [])):
                                                    self.sync_queue.mark_success(task_id)
                                                    synced_count += 1
                                                    logger.info(f"[OfflineSyncManager] ✅ FK task retried successfully after ID_TAKEN: {task_id}")
                                                else:
                                                    child_errors = retry_result.get('errors', [])
                                                    self.sync_queue.mark_failed(task_id, ', '.join(str(e) for e in child_errors) or 'Retry failed after ID_TAKEN')
                                                    failed_count += 1
                                            else:
                                                logger.warning(f"[OfflineSyncManager] ⚠️ Parent sync also failed: {parent_error_str}")
                                                self.sync_queue.mark_failed(task_id, f"FK constraint: {fk_info['message']}", max_retries=3)
                                                failed_count += 1
                                    except Exception as sync_err:
                                        logger.error(f"[OfflineSyncManager] ❌ Error syncing parent: {sync_err}")
                                        self.sync_queue.mark_failed(task_id, f"FK constraint: {fk_info['message']}", max_retries=3)
                                        failed_count += 1
                                else:
                                    logger.warning(f"[OfflineSyncManager] ⚠️ Could not extract parent data for {dependency_type} from task {task_id}")
                                    self.sync_queue.mark_failed(task_id, f"FK constraint: {fk_info['message']}", max_retries=3)
                                    failed_count += 1
                            else:
                                self.sync_queue.mark_failed(task_id, f"FK constraint: {fk_info['message']}", max_retries=3)
                                failed_count += 1
                        else:
                            self.sync_queue.mark_failed(task_id, error_str or 'Foreign key constraint error')
                            failed_count += 1
                        cursor += 1
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
                        cursor += 1
                    elif 'cannot query field' in error_str.lower() and 'graphql_validation_failed' in error_str.lower():
                        # GraphQL validation error - client selected a field that the
                        # backend SDL does not declare (e.g. requesting `upload_urls`
                        # on the CN TCB SkillMutationResult). The shape mismatch is
                        # permanent until either the backend SDL grows the field or
                        # the client stops selecting it; retrying the same payload
                        # burns 3 retries and floods the log without any progress.
                        logger.error(f"[OfflineSyncManager] ❌ GraphQL validation failed for {task_id}: {error_str}")
                        logger.error(f"[OfflineSyncManager] Backend schema does not expose a selected field. Marking non-retryable to stop retry spam.")
                        self.sync_queue.mark_failed(
                            task_id,
                            f"GraphQL validation failed: {error_str}",
                            max_retries=1,
                            non_retryable=True,
                        )
                        failed_count += 1
                        cursor += 1
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
                        cursor += 1
                    else:
                        # Sync failed, mark as failed
                        self.sync_queue.mark_failed(task_id, error_str or 'Unknown error')
                        failed_count += 1
                        logger.warning(f"[OfflineSyncManager] ⚠️ Queue task failed: {task_id}")
                        cursor += 1

            except Exception as e:
                # Exception, mark as failed
                self.sync_queue.mark_failed(task['id'], str(e))
                failed_count += 1
                logger.error(f"[OfflineSyncManager] ❌ Queue task error: {task['id']} - {e}")
                cursor += 1

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

                # If the supervisor told us the session is dead, do not
                # hammer the API.  The supervisor will resume us via
                # on_session_refreshed (after a successful re-login) or
                # re-establish the active state itself.
                if self._session_state != "active":
                    logger.info(
                        f"[OfflineSyncManager] Auto retry skipped: "
                        f"session_state={self._session_state}"
                    )
                    continue

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
