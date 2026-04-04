"""
Timer Service - Manages timeout timers for pending async operations.

This module provides a thread-safe timer service for:
- Starting timers that fire timeout events into task queues
- Cancelling timers when callbacks arrive
- Bulk cancellation for task cleanup
- Unified asyncio loop for all repeating timers (prevents thread explosion)
"""

import asyncio
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from .models import ManagedTask


# Shared asyncio loop for ALL repeating timers - prevents thread explosion
# instead of 1 thread per timer, we use 1 thread for ALL timers
_timer_loop_runner: Optional["_RepeatingTimerLoop"] = None
_timer_loop_lock = threading.Lock()

# ============================================================================
# Global Thread Registry — tracks all threads for memory leak diagnosis
# ============================================================================
_thread_registry: Dict[str, list] = {}  # category -> list of thread names
_thread_registry_lock = threading.Lock()

def _register_thread(category: str, name: str) -> None:
    """Register a thread with the global registry (call right after Thread.start())."""
    with _thread_registry_lock:
        if category not in _thread_registry:
            _thread_registry[category] = []
        if name not in _thread_registry[category]:
            _thread_registry[category].append(name)
            logger.debug(f"[THREAD_REGISTRY] +{category}: {name} (total={len(_thread_registry[category])})")

def _unregister_thread(category: str, name: str) -> None:
    """Unregister a thread (call when thread finishes)."""
    with _thread_registry_lock:
        if category in _thread_registry and name in _thread_registry[category]:
            _thread_registry[category].remove(name)
            logger.debug(f"[THREAD_REGISTRY] -{category}: {name} (remaining={len(_thread_registry[category])})")

def _dump_thread_registry() -> Dict[str, int]:
    """Return thread count by category for diagnostics."""
    with _thread_registry_lock:
        return {cat: len(names) for cat, names in _thread_registry.items()}


class _RepeatingTimerLoop:
    """
    Shared asyncio loop runner for all repeating timers.
    All RepeatingTimerHandles share this ONE thread instead of each creating their own.
    """

    def __init__(self):
        self._timers: Dict[str, "RepeatingTimerHandle"] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def register(self, handle: "RepeatingTimerHandle"):
        with self._lock:
            self._timers[handle.timer_id] = handle

    def unregister(self, timer_id: str):
        with self._lock:
            self._timers.pop(timer_id, None)

    def start(self):
        if self._started:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="RepeatingTimerLoop",
            daemon=True,
        )
        self._thread.start()
        self._started = True
        logger.debug(f"[_RepeatingTimerLoop] Started shared timer loop")

    def _run_loop(self):
        """Run the shared asyncio loop for all repeating timers."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_timers())
        except Exception as e:
            logger.error(f"[_RepeatingTimerLoop] Loop error: {e}")
        finally:
            self._loop.close()

    async def _run_timers(self):
        """Async loop: schedule all timers and run until stopped."""
        while not self._stop_event.is_set():
            with self._lock:
                timer_ids = list(self._timers.keys())

            for timer_id in timer_ids:
                if self._stop_event.is_set():
                    break
                with self._lock:
                    handle = self._timers.get(timer_id)
                if handle and handle.is_active():
                    try:
                        handle._fire_in_loop(self._loop)
                    except Exception as e:
                        logger.error(f"[_RepeatingTimerLoop] Fire error for {timer_id}: {e}")

            await asyncio.sleep(0.5)  # Check every 500ms

    def stop(self):
        self._stop_event.set()
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)


def _get_timer_loop() -> _RepeatingTimerLoop:
    """Get or create the shared timer loop."""
    global _timer_loop_runner
    with _timer_loop_lock:
        if _timer_loop_runner is None:
            _timer_loop_runner = _RepeatingTimerLoop()
            _timer_loop_runner.start()
        return _timer_loop_runner


class RepeatingTimerHandle:
    """
    Handle for a named repeating interval timer.

    Fires periodically at a fixed interval, invoking a callback each time.
    Supports finite repeat counts or continuous (-1) operation.

    Uses a shared asyncio timer loop (_RepeatingTimerLoop) to avoid thread explosion.
    """

    def __init__(
        self,
        timer_id: str,
        timer_name: str,
        agent_id: str,
        period_ms: int,
        repeat_count: int,
        callback: Callable[["RepeatingTimerHandle"], None],
        created_at: float,
    ):
        self.timer_id = timer_id
        self.timer_name = timer_name
        self.agent_id = agent_id
        self.period_ms = period_ms
        self.repeat_count = repeat_count  # -1 = continuous, 0 = stopped, N = N remaining
        self.callback = callback
        self.created_at = created_at
        self.fire_count: int = 0
        self.cancelled = False
        self._paused = False
        self._handle: Optional[asyncio.TimerHandle] = None  # asyncio scheduled handle

    def start(self):
        """Register this timer with the shared loop (no new thread created)."""
        if self.cancelled:
            return
        if self._paused:
            return  # use resume() instead
        _get_timer_loop().register(self)
        self._schedule_next(0)

    def _schedule_next(self, delay_sec: float):
        """Schedule the next fire using asyncio (called from shared loop thread)."""
        loop = _get_timer_loop()._loop
        if loop and not loop.is_closed():
            self._handle = loop.call_later(
                delay_sec,
                self._fire_in_loop,
                loop,
            )

    def _fire_in_loop(self, loop: asyncio.AbstractEventLoop):
        """Fire callback and schedule next iteration. Called from the shared timer loop."""
        if self.cancelled or self._paused:
            return

        # Check repeat count
        if self.repeat_count == 0:
            self.cancelled = True
            _get_timer_loop().unregister(self.timer_id)
            logger.debug(f"[REPEATING_TIMER] Timer '{self.timer_name}' stopped (repeat_count=0)")
            return

        self.fire_count += 1

        # Decrement finite repeat count
        if self.repeat_count > 0:
            self.repeat_count -= 1

        # Fire callback (synchronous call into user code)
        try:
            self.callback(self)
        except Exception as e:
            logger.error(f"[REPEATING_TIMER] Callback error for '{self.timer_name}': {e}")

        # If repeat_count reached 0 after decrement, stop
        if self.repeat_count == 0:
            self.cancelled = True
            _get_timer_loop().unregister(self.timer_id)
            logger.debug(f"[REPEATING_TIMER] Timer '{self.timer_name}' completed ({self.fire_count} fires)")
            return

        # Schedule next fire
        self._schedule_next(self.period_ms / 1000.0)

    def cancel(self):
        """Stop the repeating timer permanently."""
        if self.cancelled:
            return
        self.cancelled = True
        self._paused = False
        # Cancel any pending scheduled call
        if self._handle:
            self._handle.cancel()
            self._handle = None
        _get_timer_loop().unregister(self.timer_id)

    def pause(self):
        """Pause the repeating timer. Can be resumed later with resume()."""
        if self.cancelled or self._paused:
            return
        self._paused = True
        if self._handle:
            self._handle.cancel()
            self._handle = None
        logger.info(f"[REPEATING_TIMER] Paused timer '{self.timer_name}' (id={self.timer_id})")

    def resume(self):
        """Resume a paused timer. Continues from where it left off."""
        if self.cancelled or not self._paused:
            return
        self._paused = False
        _get_timer_loop().register(self)
        self._schedule_next(self.period_ms / 1000.0)
        logger.info(f"[REPEATING_TIMER] Resumed timer '{self.timer_name}' (id={self.timer_id})")

    @property
    def is_paused(self) -> bool:
        """Check if timer is currently paused."""
        return self._paused and not self.cancelled

    def is_active(self) -> bool:
        """Check if timer is still running (not cancelled, not paused, has repeats left)."""
        return not self.cancelled and not self._paused and (self.repeat_count != 0)

    def to_dict(self) -> dict:
        """Serialize to dict for listing/API responses."""
        return {
            "timer_id": self.timer_id,
            "timer_name": self.timer_name,
            "agent_id": self.agent_id,
            "period_ms": self.period_ms,
            "repeat_count": self.repeat_count,
            "fire_count": self.fire_count,
            "active": self.is_active(),
            "paused": self.is_paused,
            "created_at": self.created_at,
        }


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
    Thread-safe service for managing timeout timers and repeating interval timers.
    
    Timeout timers are associated with correlation IDs and task IDs,
    allowing bulk cancellation when tasks complete or are cancelled.
    
    Repeating timers are named, per-agent interval timers that fire
    periodically and dispatch timer events through event routing.
    """
    
    def __init__(self):
        self._timers: Dict[str, TimerHandle] = {}
        self._repeating_timers: Dict[str, RepeatingTimerHandle] = {}  # keyed by timer_id
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
        """Cancel and remove all timers (both one-shot and repeating)."""
        with self._lock:
            for handle in self._timers.values():
                handle.cancel()
            count = len(self._timers)
            self._timers.clear()
            
            for handle in self._repeating_timers.values():
                handle.cancel()
            rep_count = len(self._repeating_timers)
            self._repeating_timers.clear()
        
        total = count + rep_count
        if total > 0:
            logger.debug(f"[TIMER] Cleared all {count} one-shot + {rep_count} repeating timers")
    
    # ==================== Repeating Timer Methods ====================
    
    def add_repeating_timer(
        self,
        timer_name: str,
        agent_id: str,
        period_ms: int,
        repeat_count: int,
        callback: Callable[[RepeatingTimerHandle], None],
        timer_id: Optional[str] = None,
    ) -> RepeatingTimerHandle:
        """
        Create and start a named repeating interval timer.
        
        Args:
            timer_name: Human-readable name (e.g. 'check_orders')
            agent_id: ID of the agent that owns this timer
            period_ms: Interval between fires in milliseconds
            repeat_count: Number of times to fire (-1 = continuous, 0 = stopped/paused)
            callback: Called each time the timer fires, receives the handle
            timer_id: Optional explicit ID; auto-generated if not provided
            
        Returns:
            RepeatingTimerHandle for managing this timer
        """
        if timer_id is None:
            timer_id = f"tmr_{uuid.uuid4().hex[:12]}"
        
        handle = RepeatingTimerHandle(
            timer_id=timer_id,
            timer_name=timer_name,
            agent_id=agent_id,
            period_ms=period_ms,
            repeat_count=repeat_count,
            callback=callback,
            created_at=time.time(),
        )
        
        with self._lock:
            # Cancel existing timer with same ID
            existing = self._repeating_timers.get(timer_id)
            if existing:
                existing.cancel()
            self._repeating_timers[timer_id] = handle
        
        if repeat_count != 0:
            handle.start()
        
        logger.info(
            f"[REPEATING_TIMER] Added timer '{timer_name}' (id={timer_id}, "
            f"period={period_ms}ms, repeat={repeat_count}, agent={agent_id})"
        )
        return handle
    
    def remove_repeating_timer(self, timer_id: str) -> bool:
        """
        Remove and cancel a repeating timer by its ID.
        
        Returns:
            True if found and removed, False otherwise
        """
        with self._lock:
            handle = self._repeating_timers.pop(timer_id, None)
            if handle:
                handle.cancel()
                logger.info(f"[REPEATING_TIMER] Removed timer '{handle.timer_name}' (id={timer_id})")
                return True
        return False
    
    def update_repeating_timer(
        self,
        timer_id: str,
        period_ms: Optional[int] = None,
        repeat_count: Optional[int] = None,
    ) -> Optional[RepeatingTimerHandle]:
        """
        Update a repeating timer's period and/or repeat count.
        
        Stops the current loop and restarts with new parameters.
        
        Args:
            timer_id: ID of the timer to update
            period_ms: New period in milliseconds (None = keep current)
            repeat_count: New repeat count (None = keep current)
            
        Returns:
            Updated handle, or None if not found
        """
        with self._lock:
            handle = self._repeating_timers.get(timer_id)
            if not handle:
                return None
            
            # Stop the current loop gracefully (don't use cancel() which
            # permanently marks the timer as cancelled)
            handle._stop_event.set()
            old_thread = handle._thread
            
            # Apply updates
            if period_ms is not None:
                handle.period_ms = period_ms
            if repeat_count is not None:
                handle.repeat_count = repeat_count
            
            # Reset state for restart
            handle.cancelled = False
            handle._paused = False

        # Wait for old thread to finish OUTSIDE the lock to avoid deadlocks
        if old_thread and old_thread.is_alive():
            old_thread.join(timeout=2.0)
        
        # Now start fresh
        with self._lock:
            handle._stop_event.clear()
            handle._thread = None  # force start() to create a new thread
            if handle.repeat_count != 0:
                handle.start()
            
            logger.info(
                f"[REPEATING_TIMER] Updated timer '{handle.timer_name}' (id={timer_id}, "
                f"period={handle.period_ms}ms, repeat={handle.repeat_count})"
            )
            return handle
    
    def get_repeating_timer(self, timer_id: str) -> Optional[RepeatingTimerHandle]:
        """Get a repeating timer by ID."""
        with self._lock:
            return self._repeating_timers.get(timer_id)
    
    def find_repeating_timer_by_name(self, timer_name: str, agent_id: str) -> Optional[RepeatingTimerHandle]:
        """Find a repeating timer by name within an agent."""
        with self._lock:
            for handle in self._repeating_timers.values():
                if handle.timer_name == timer_name and handle.agent_id == agent_id:
                    return handle
        return None
    
    def list_repeating_timers(self, agent_id: Optional[str] = None) -> List[RepeatingTimerHandle]:
        """
        List repeating timers, optionally filtered by agent.
        
        Args:
            agent_id: If provided, only return timers for this agent
            
        Returns:
            List of RepeatingTimerHandle objects
        """
        with self._lock:
            if agent_id:
                return [h for h in self._repeating_timers.values() if h.agent_id == agent_id]
            return list(self._repeating_timers.values())
    
    def pause_repeating_timer(self, timer_id: str) -> Optional[RepeatingTimerHandle]:
        """Pause a repeating timer by ID. Returns the handle if found."""
        with self._lock:
            handle = self._repeating_timers.get(timer_id)
            if handle:
                handle.pause()
                return handle
        return None

    def resume_repeating_timer(self, timer_id: str) -> Optional[RepeatingTimerHandle]:
        """Resume a paused repeating timer by ID. Returns the handle if found."""
        with self._lock:
            handle = self._repeating_timers.get(timer_id)
            if handle:
                handle.resume()
                return handle
        return None

    def resume_all_paused_for_agent(self, agent_id: str) -> int:
        """
        Resume all paused repeating timers for a specific agent.
        Used as a safety net (e.g., auto-resume at pend_event node).

        Returns:
            Number of timers resumed
        """
        resumed = 0
        with self._lock:
            for handle in self._repeating_timers.values():
                if handle.agent_id == agent_id and handle.is_paused:
                    handle.resume()
                    resumed += 1
        if resumed:
            logger.info(f"[REPEATING_TIMER] Auto-resumed {resumed} paused timer(s) for agent {agent_id}")
        return resumed

    def cancel_all_repeating_for_agent(self, agent_id: str) -> int:
        """
        Cancel all repeating timers for a specific agent.
        
        Returns:
            Number of timers cancelled
        """
        cancelled_count = 0
        with self._lock:
            to_remove = []
            for tid, handle in self._repeating_timers.items():
                if handle.agent_id == agent_id:
                    handle.cancel()
                    to_remove.append(tid)
                    cancelled_count += 1
            for tid in to_remove:
                self._repeating_timers.pop(tid, None)
        
        if cancelled_count > 0:
            logger.info(f"[REPEATING_TIMER] Cancelled {cancelled_count} timers for agent {agent_id})")
        return cancelled_count


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
