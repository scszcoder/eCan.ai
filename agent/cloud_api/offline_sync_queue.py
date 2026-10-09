"""
Offline Sync Queue - Offline Synchronization Queue

Provides offline caching and auto-sync functionality:
1. When network is poor, cache sync requests locally
2. When network recovers, auto-sync cached requests
3. On startup, sync local cache first, then load from cloud
"""

import contextlib
import itertools
import json
import os
import time
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from utils.logger_helper import logger_helper as logger

_LOCK_TIMEOUT_S = 5.0
_REMOVED_IDS_MAX = 5000
_ID_SEQ = itertools.count()   # process-wide, so ids from two queue objects never collide


@contextlib.contextmanager
def _interprocess_lock(lock_path: Path):
    """Best-effort exclusive lock on *lock_path* across processes (the app and
    the CLI share one queue file). Gives up after _LOCK_TIMEOUT_S and proceeds
    unlocked rather than block a sync forever."""
    fh = None
    locked = False
    try:
        fh = open(lock_path, 'a+b')
        deadline = time.monotonic() + _LOCK_TIMEOUT_S
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    logger.warning(f"[OfflineSyncQueue] queue file lock busy > {_LOCK_TIMEOUT_S}s; proceeding")
                    break
                time.sleep(0.05)
        yield
    finally:
        if fh is not None:
            try:
                if locked:
                    if os.name == 'nt':
                        import msvcrt
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            finally:
                fh.close()


class OfflineSyncQueue:
    """Offline Sync Queue - Manages offline caching and auto-sync"""
    
    # Limits to prevent unbounded memory growth
    MAX_PENDING_TASKS = 1000
    MAX_FAILED_TASKS = 500
    MAX_TASK_AGE_SECONDS = 7 * 24 * 3600  # 7 days TTL
    CLEANUP_INTERVAL_SECONDS = 3600  # Run cleanup at most once per hour
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize offline sync queue
        
        Args:
            cache_dir: Cache directory path, defaults to app_info.appdata_path/offline_sync_queue
        """
        if cache_dir is None:
            # Use appdata directory from app_info
            from config.app_info import app_info
            cache_dir = Path(app_info.appdata_path) / 'offline_sync_queue'
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Queue file paths
        self.queue_file = self.cache_dir / 'pending_sync.json'
        self.failed_file = self.cache_dir / 'failed_sync.json'
        self._lock_file = self.cache_dir / 'queue.lock'

        # Sync lock (threads in this process). Other processes (the CLI next to the
        # running app) share the files: every save merges what they added
        # (_merge_from_disk) under an inter-process lock, and ids this process
        # removed on purpose are remembered so a merge does not resurrect them.
        # (2026-10-08: the app rewrote the file from memory and dropped 8 agent/
        # task items the CLI had just queued.)
        self._lock = threading.Lock()
        self._removed_ids: Dict[str, None] = {}
        
        # Track last cleanup time to avoid excessive cleanup
        self._last_cleanup_time = 0.0
        
        # Initialize queue
        self._load_queue()
        
        logger.info(f"[OfflineSyncQueue] Initialized with cache dir: {self.cache_dir}")
    
    def _load_queue(self):
        """Load queue from file"""
        try:
            if self.queue_file.exists():
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    self.pending_queue = json.load(f)
            else:
                self.pending_queue = []
            
            if self.failed_file.exists():
                with open(self.failed_file, 'r', encoding='utf-8') as f:
                    self.failed_queue = json.load(f)
            else:
                self.failed_queue = []
                
            logger.info(f"[OfflineSyncQueue] Loaded {len(self.pending_queue)} pending, {len(self.failed_queue)} failed")
        except Exception as e:
            logger.error(f"[OfflineSyncQueue] Failed to load queue: {e}")
            self.pending_queue = []
            self.failed_queue = []
    
    @staticmethod
    def _read_json_list(path: Path) -> list:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding='utf-8') or '[]')
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"[OfflineSyncQueue] could not read {path.name}: {e}")
        return []

    def _forget(self, task_ids) -> None:
        """Remember ids removed on purpose so a merge from disk keeps them gone."""
        for tid in task_ids:
            self._removed_ids[tid] = None
        while len(self._removed_ids) > _REMOVED_IDS_MAX:
            self._removed_ids.pop(next(iter(self._removed_ids)))

    def _merge_from_disk(self) -> int:
        """Add tasks another process wrote to the files since we last looked.
        This process's own copy of a task wins; removed ids stay removed.
        Returns how many tasks were picked up."""
        known = {t.get('id') for t in self.pending_queue} | {t.get('id') for t in self.failed_queue}
        picked = 0
        for path, queue in ((self.queue_file, self.pending_queue), (self.failed_file, self.failed_queue)):
            for task in self._read_json_list(path):
                tid = task.get('id') if isinstance(task, dict) else None
                if tid and tid not in known and tid not in self._removed_ids:
                    queue.append(task)
                    known.add(tid)
                    picked += 1
        if picked:
            logger.info(f"[OfflineSyncQueue] picked up {picked} task(s) queued by another process")
        return picked

    @staticmethod
    def _write_atomic(path: Path, data: list) -> None:
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, path)

    def _save_queue(self):
        """Save queue to file -- merged with what other processes queued meanwhile."""
        try:
            with _interprocess_lock(self._lock_file):
                self._merge_from_disk()
                self._write_atomic(self.queue_file, self.pending_queue)
                self._write_atomic(self.failed_file, self.failed_queue)

            logger.debug(f"[OfflineSyncQueue] Saved {len(self.pending_queue)} pending, {len(self.failed_queue)} failed")
        except Exception as e:
            logger.error(f"[OfflineSyncQueue] Failed to save queue: {e}")

    def refresh_from_disk(self) -> int:
        """Pick up tasks other processes queued (e.g. the CLI while the app runs)."""
        with self._lock:
            with _interprocess_lock(self._lock_file):
                return self._merge_from_disk()
    
    def _enforce_limits(self) -> None:
        """
        Enforce queue size limits and TTL to prevent unbounded memory growth.
        Called automatically when adding tasks, but can also be called manually.
        """
        now = time.time()
        
        # Throttle cleanup: only run once per CLEANUP_INTERVAL_SECONDS
        if now - self._last_cleanup_time < self.CLEANUP_INTERVAL_SECONDS:
            return
        
        self._last_cleanup_time = now
        removed = 0
        
        # Remove tasks older than MAX_TASK_AGE_SECONDS
        cutoff = now - self.MAX_TASK_AGE_SECONDS
        for queue in (self.pending_queue, self.failed_queue):
            before = len(queue)
            self._forget(t.get('id') for t in queue
                         if datetime.fromisoformat(t['created_at']).timestamp() <= cutoff)
            queue[:] = [
                t for t in queue
                if datetime.fromisoformat(t['created_at']).timestamp() > cutoff
            ]
            removed += before - len(queue)

        # Enforce MAX_PENDING_TASKS: drop oldest entries
        while len(self.pending_queue) > self.MAX_PENDING_TASKS:
            self._forget([self.pending_queue.pop(0).get('id')])
            removed += 1

        # Enforce MAX_FAILED_TASKS: drop oldest entries
        while len(self.failed_queue) > self.MAX_FAILED_TASKS:
            self._forget([self.failed_queue.pop(0).get('id')])
            removed += 1
        
        if removed > 0:
            logger.warning(f"[OfflineSyncQueue] Cleanup removed {removed} stale/overflow tasks "
                           f"(pending={len(self.pending_queue)}, failed={len(self.failed_queue)})")
            self._save_queue()
    
    def add(self, data_type: str, data: Dict[str, Any], operation: str = 'add') -> str:
        """
        Add sync task to queue
        
        Args:
            data_type: Data type ('skill', 'task', 'agent', 'tool')
            data: Data content
            operation: Operation type ('add', 'update', 'delete')
        
        Returns:
            str: Task ID
        """
        with self._lock:
            # pid + counter: two processes (or two adds in one millisecond) must
            # never produce the same id -- ids are the merge key.
            task_id = f"{data_type}_{operation}_{int(time.time() * 1000)}_{os.getpid()}_{next(_ID_SEQ)}"
            
            task = {
                'id': task_id,
                'data_type': data_type,
                'operation': operation,
                'data': data,
                'created_at': datetime.now().isoformat(),
                'retry_count': 0,
                'status': 'pending'
            }
            
            self.pending_queue.append(task)
            self._enforce_limits()
            self._save_queue()
            
            logger.info(f"[OfflineSyncQueue] Added task: {task_id}")
            return task_id
    
    def get_pending_tasks(self, data_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get pending sync tasks
        
        Args:
            data_type: Optional, only get tasks of specified type
        
        Returns:
            List[Dict]: Pending task list
        """
        with self._lock:
            # Include what another process queued (the CLI while the app runs).
            try:
                with _interprocess_lock(self._lock_file):
                    self._merge_from_disk()
            except Exception as e:
                logger.debug(f"[OfflineSyncQueue] merge before read skipped: {e}")
            if data_type:
                return [task for task in self.pending_queue if task['data_type'] == data_type]
            return self.pending_queue.copy()
    
    def get_failed_tasks(self, data_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get failed tasks
        
        Args:
            data_type: Optional, only get tasks of specified type
        
        Returns:
            List[Dict]: Failed task list
        """
        with self._lock:
            if data_type:
                return [task for task in self.failed_queue if task['data_type'] == data_type]
            return self.failed_queue.copy()
    
    def retry_failed_task(self, task_id: str):
        """
        Move failed task back to pending queue

        Args:
            task_id: Task ID
        """
        with self._lock:
            for task in self.failed_queue:
                if task['id'] == task_id:
                    # Never retry permanent failures (auth/ownership/configuration, etc.)
                    if bool(task.get('non_retryable')):
                        logger.info(f"[OfflineSyncQueue] Skip retry non-retryable task: {task_id}")
                        break
                    # Reset status
                    task['status'] = 'pending'
                    task['retry_count'] = 0
                    task['last_error'] = None
                    # Move back to pending queue
                    self.pending_queue.append(task)
                    self.failed_queue.remove(task)
                    self._save_queue()
                    logger.info(f"[OfflineSyncQueue] Retry failed task: {task_id}")
                    break

    def get_pending(self) -> List[Dict[str, Any]]:
        """
        Get all pending tasks (alias for get_pending_tasks)
        
        Returns:
            List[Dict]: Pending task list
        """
        return self.get_pending_tasks()
    
    def mark_completed(self, task_id: str):
        """
        Mark task as completed (alias for mark_success)
        
        Args:
            task_id: Task ID
        """
        self.mark_success(task_id)
    
    def mark_success(self, task_id: str):
        """
        Mark task as successful (remove from queue)
        
        Args:
            task_id: Task ID
        """
        with self._lock:
            self._forget([task_id])
            self.pending_queue = [task for task in self.pending_queue if task['id'] != task_id]
            self._save_queue()
            logger.info(f"[OfflineSyncQueue] Task succeeded: {task_id}")
    
    def mark_failed(self, task_id: str, error: str, max_retries: int = 3, non_retryable: bool = False):
        """
        Mark task as failed
        
        Args:
            task_id: Task ID
            error: Error message
            max_retries: Maximum retry count
        """
        with self._lock:
            for task in self.pending_queue:
                if task['id'] == task_id:
                    task['retry_count'] += 1
                    task['last_error'] = error
                    task['last_retry_at'] = datetime.now().isoformat()
                    if non_retryable:
                        task['non_retryable'] = True
                    
                    if non_retryable or task['retry_count'] >= max_retries:
                        # Exceeded max retries, move to failed queue
                        task['status'] = 'failed_non_retryable' if non_retryable else 'failed'
                        self.failed_queue.append(task)
                        self.pending_queue.remove(task)
                        if non_retryable:
                            logger.warning(f"[OfflineSyncQueue] Task marked non-retryable and moved to failed queue: {task_id}")
                        else:
                            logger.warning(f"[OfflineSyncQueue] Task failed after {max_retries} retries: {task_id}")
                    else:
                        logger.warning(f"[OfflineSyncQueue] Task retry {task['retry_count']}/{max_retries}: {task_id}")
                    
                    self._save_queue()
                    break
    
    def clear_pending(self):
        """Clear pending queue"""
        with self._lock:
            self._forget(t.get('id') for t in self.pending_queue)
            self.pending_queue = []
            self._save_queue()
            logger.info("[OfflineSyncQueue] Cleared pending queue")
    
    def clear_failed(self):
        """Clear failed queue"""
        with self._lock:
            self._forget(t.get('id') for t in self.failed_queue)
            self.failed_queue = []
            self._save_queue()
            logger.info("[OfflineSyncQueue] Cleared failed queue")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics
        
        Returns:
            Dict: Statistics
        """
        with self._lock:
            return {
                'pending_count': len(self.pending_queue),
                'failed_count': len(self.failed_queue),
                'pending_by_type': self._count_by_type(self.pending_queue),
                'failed_by_type': self._count_by_type(self.failed_queue)
            }
    
    def _count_by_type(self, queue: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count tasks by type"""
        counts = {}
        for task in queue:
            data_type = task['data_type']
            counts[data_type] = counts.get(data_type, 0) + 1
        return counts
    
    def remove_tasks_by_resource(self, data_type: str, resource_id: str, operation: Optional[str] = None) -> int:
        """
        Remove tasks related to a specific resource from both pending and failed queues
        
        Args:
            data_type: Data type ('skill', 'task', 'agent', 'tool', etc.)
            resource_id: Resource ID to match
            operation: Optional, only remove tasks with specific operation ('add', 'update', 'delete')
        
        Returns:
            int: Number of tasks removed
        """
        with self._lock:
            removed_count = 0
            self._forget(
                task.get('id') for task in self.pending_queue + self.failed_queue
                if task['data_type'] == data_type and task.get('data', {}).get('id') == resource_id
                and (operation is None or task.get('operation') == operation))

            # Remove from pending queue
            original_pending = len(self.pending_queue)
            self.pending_queue = [
                task for task in self.pending_queue
                if not (
                    task['data_type'] == data_type and
                    task.get('data', {}).get('id') == resource_id and
                    (operation is None or task.get('operation') == operation)
                )
            ]
            removed_from_pending = original_pending - len(self.pending_queue)
            
            # Remove from failed queue
            original_failed = len(self.failed_queue)
            self.failed_queue = [
                task for task in self.failed_queue
                if not (
                    task['data_type'] == data_type and
                    task.get('data', {}).get('id') == resource_id and
                    (operation is None or task.get('operation') == operation)
                )
            ]
            removed_from_failed = original_failed - len(self.failed_queue)
            
            removed_count = removed_from_pending + removed_from_failed
            
            if removed_count > 0:
                self._save_queue()
                logger.info(f"[OfflineSyncQueue] Removed {removed_count} tasks for {data_type}:{resource_id} (operation={operation})")
            
            return removed_count


# Global singleton
_offline_sync_queue: Optional[OfflineSyncQueue] = None


def get_sync_queue() -> OfflineSyncQueue:
    """Get global offline sync queue instance (legacy name for compatibility)"""
    global _offline_sync_queue
    if _offline_sync_queue is None:
        _offline_sync_queue = OfflineSyncQueue()
    return _offline_sync_queue


def get_offline_sync_queue() -> OfflineSyncQueue:
    """Get global offline sync queue instance"""
    return get_sync_queue()
