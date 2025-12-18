"""
Timer Service - Manages timeout timers for pending async operations.

This module provides a thread-safe timer service for:
- Starting timers that fire timeout events into task queues
- Cancelling timers when callbacks arrive
- Bulk cancellation for task cleanup
"""

import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from .models import ManagedTask


class TimerHandle:
    """
    Handle for a registered timer.
    
    Allows checking status and cancelling the timer.
    """
    
    def __init__(
        self,
        timer_id: str,
        correlation_id: str,
        task_id: str,
        timer: threading.Timer,
        timeout_seconds: float,
        created_at: float
    ):
        self.timer_id = timer_id
        self.correlation_id = correlation_id
        self.task_id = task_id
        self.timer = timer
        self.timeout_seconds = timeout_seconds
        self.created_at = created_at
        self.cancelled = False
        self.fired = False
    
    def cancel(self):
        """Cancel this timer."""
        if not self.cancelled and not self.fired:
            self.timer.cancel()
            self.cancelled = True
    
    def is_active(self) -> bool:
        """Check if timer is still active (not cancelled or fired)."""
        return not self.cancelled and not self.fired


class TimerService:
    """
    Thread-safe service for managing timeout timers.
    
    Timers are associated with correlation IDs and task IDs,
    allowing bulk cancellation when tasks complete or are cancelled.
    """
    
    def __init__(self):
        self._timers: Dict[str, TimerHandle] = {}
        self._lock = threading.Lock()
    
    def start_timer(
        self,
        correlation_id: str,
        task_id: str,
        delay_seconds: float,
        callback: Callable[[], None],
        on_fire: Optional[Callable[[str], None]] = None
    ) -> TimerHandle:
        """
        Start a timer that calls callback after delay.
        
        Args:
            correlation_id: Unique ID for this timer (matches pending event)
            task_id: ID of the task this timer belongs to
            delay_seconds: Seconds until timer fires
            callback: Function to call when timer fires
            on_fire: Optional callback with correlation_id when timer fires
            
        Returns:
            TimerHandle for managing this timer
        """
        timer_id = f"{correlation_id}:{uuid.uuid4().hex[:8]}"
        
        def _on_timeout():
            with self._lock:
                handle = self._timers.get(correlation_id)
                if handle and not handle.cancelled:
                    handle.fired = True
                    # Remove from active timers
                    self._timers.pop(correlation_id, None)
            
            # Call the callback outside the lock
            try:
                callback()
                if on_fire:
                    on_fire(correlation_id)
            except Exception as e:
                logger.error(f"[TIMER] Callback error for {correlation_id}: {e}")
        
        timer = threading.Timer(delay_seconds, _on_timeout)
        timer.daemon = True  # Don't block process exit
        
        handle = TimerHandle(
            timer_id=timer_id,
            correlation_id=correlation_id,
            task_id=task_id,
            timer=timer,
            timeout_seconds=delay_seconds,
            created_at=time.time()
        )
        
        with self._lock:
            # Cancel any existing timer for this correlation_id
            existing = self._timers.get(correlation_id)
            if existing:
                existing.cancel()
            
            self._timers[correlation_id] = handle
        
        timer.start()
        logger.debug(f"[TIMER] Started timer {correlation_id} ({delay_seconds}s)")
        
        return handle
    
    def cancel_timer(self, correlation_id: str) -> bool:
        """
        Cancel a timer by its correlation ID.
        
        Args:
            correlation_id: The timer's correlation ID
            
        Returns:
            True if timer was found and cancelled, False otherwise
        """
        with self._lock:
            handle = self._timers.pop(correlation_id, None)
            if handle:
                handle.cancel()
                logger.debug(f"[TIMER] Cancelled timer {correlation_id}")
                return True
        return False
    
    def cancel_all_for_task(self, task_id: str) -> int:
        """
        Cancel all timers for a specific task.
        
        Args:
            task_id: The task ID to cancel timers for
            
        Returns:
            Number of timers cancelled
        """
        cancelled_count = 0
        with self._lock:
            to_remove = []
            for corr_id, handle in self._timers.items():
                if handle.task_id == task_id:
                    handle.cancel()
                    to_remove.append(corr_id)
                    cancelled_count += 1
            
            for corr_id in to_remove:
                self._timers.pop(corr_id, None)
        
        if cancelled_count > 0:
            logger.debug(f"[TIMER] Cancelled {cancelled_count} timers for task {task_id}")
        
        return cancelled_count
    
    def get_active_timers(self) -> Dict[str, TimerHandle]:
        """
        Get all active timers.
        
        Returns:
            Dict of correlation_id -> TimerHandle for active timers
        """
        with self._lock:
            return {
                corr_id: handle
                for corr_id, handle in self._timers.items()
                if handle.is_active()
            }
    
    def get_timer(self, correlation_id: str) -> Optional[TimerHandle]:
        """
        Get a timer by correlation ID.
        
        Args:
            correlation_id: The timer's correlation ID
            
        Returns:
            TimerHandle if found, None otherwise
        """
        with self._lock:
            return self._timers.get(correlation_id)
    
    def clear_all(self):
        """Cancel and remove all timers."""
        with self._lock:
            for handle in self._timers.values():
                handle.cancel()
            count = len(self._timers)
            self._timers.clear()
        
        if count > 0:
            logger.debug(f"[TIMER] Cleared all {count} timers")


# Global timer service instance (can be overridden for testing)
_timer_service: Optional[TimerService] = None


def get_timer_service() -> TimerService:
    """Get the global timer service instance."""
    global _timer_service
    if _timer_service is None:
        _timer_service = TimerService()
    return _timer_service


def set_timer_service(service: TimerService):
    """Set the global timer service instance (for testing)."""
    global _timer_service
    _timer_service = service
