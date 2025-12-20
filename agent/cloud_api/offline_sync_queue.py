"""
Offline Sync Queue - Offline Synchronization Queue

Provides offline caching and auto-sync functionality:
1. When network is poor, cache sync requests locally
2. When network recovers, auto-sync cached requests
3. On startup, sync local cache first, then load from cloud
"""

import json
import os
import time
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from utils.logger_helper import logger_helper as logger


class OfflineSyncQueue:
    """Offline Sync Queue - Manages offline caching and auto-sync"""
    
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
        
        # Sync lock
        self._lock = threading.Lock()
        
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
    
    def _save_queue(self):
        """Save queue to file"""
        try:
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(self.pending_queue, f, indent=2, ensure_ascii=False)
            
            with open(self.failed_file, 'w', encoding='utf-8') as f:
                json.dump(self.failed_queue, f, indent=2, ensure_ascii=False)
                
            logger.debug(f"[OfflineSyncQueue] Saved {len(self.pending_queue)} pending, {len(self.failed_queue)} failed")
        except Exception as e:
            logger.error(f"[OfflineSyncQueue] Failed to save queue: {e}")
    
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
            task_id = f"{data_type}_{operation}_{int(time.time() * 1000)}"
            
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
            self.pending_queue = [task for task in self.pending_queue if task['id'] != task_id]
            self._save_queue()
            logger.info(f"[OfflineSyncQueue] Task succeeded: {task_id}")
    
    def mark_failed(self, task_id: str, error: str, max_retries: int = 3):
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
                    
                    if task['retry_count'] >= max_retries:
                        # Exceeded max retries, move to failed queue
                        task['status'] = 'failed'
                        self.failed_queue.append(task)
                        self.pending_queue.remove(task)
                        logger.warning(f"[OfflineSyncQueue] Task failed after {max_retries} retries: {task_id}")
                    else:
                        logger.warning(f"[OfflineSyncQueue] Task retry {task['retry_count']}/{max_retries}: {task_id}")
                    
                    self._save_queue()
                    break
    
    def clear_pending(self):
        """Clear pending queue"""
        with self._lock:
            self.pending_queue = []
            self._save_queue()
            logger.info("[OfflineSyncQueue] Cleared pending queue")
    
    def clear_failed(self):
        """Clear failed queue"""
        with self._lock:
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
