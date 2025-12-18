"""
Pending Events - Registration utilities for async operations.

This module provides helper functions for tools to register pending async
operations and for the system to route callback events back to tasks.
"""

import uuid
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from utils.logger_helper import logger_helper as logger

from .timer_service import get_timer_service, TimerService
from .models import PendingEvent

if TYPE_CHECKING:
    from .models import ManagedTask


def generate_correlation_id(task_id: str) -> str:
    """
    Generate a self-routing correlation ID.
    
    Format: "{task_id}:{uuid}"
    This allows routing callbacks directly to the correct task.
    
    Args:
        task_id: The task ID to embed in the correlation ID
        
    Returns:
        A unique correlation ID
    """
    return f"{task_id}:{uuid.uuid4().hex}"


def parse_correlation_id(correlation_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a correlation ID to extract task_id and unique part.
    
    Args:
        correlation_id: The correlation ID to parse
        
    Returns:
        Tuple of (task_id, unique_part), or (None, None) if invalid
    """
    if not correlation_id or ":" not in correlation_id:
        return None, None
    
    parts = correlation_id.split(":", 1)
    if len(parts) != 2:
        return None, None
    
    return parts[0], parts[1]


def register_async_operation(
    task: "ManagedTask",
    source_node: str,
    timeout_seconds: float = 60.0,
    timer_service: Optional[TimerService] = None
) -> str:
    """
    Register a pending async operation for a task.
    
    This is the main entry point for tools that make async API calls.
    It:
    1. Generates a self-routing correlation ID
    2. Registers the pending event on the task
    3. Starts a timeout timer
    
    Args:
        task: The ManagedTask making the async call
        source_node: Name of the node/tool registering this
        timeout_seconds: How long to wait before timing out
        timer_service: Optional timer service (uses global if not provided)
        
    Returns:
        The correlation ID to include in the async API call
        
    Usage:
        # In a tool that makes an async API call:
        correlation_id = register_async_operation(task, "my_tool", timeout_seconds=120)
        response = await external_api.start_job(callback_id=correlation_id)
        return {"status": "accepted", "correlation_id": correlation_id}
    """
    if timer_service is None:
        timer_service = get_timer_service()
    
    # Generate correlation ID
    correlation_id = generate_correlation_id(task.id)
    
    # Register on task
    task.register_pending_event(
        correlation_id=correlation_id,
        source_node=source_node,
        timeout_seconds=timeout_seconds
    )
    
    # Start timeout timer
    def on_timeout():
        """Called when timer fires - put timeout event in task queue."""
        try:
            if task.queue:
                task.queue.put({
                    "type": "async_timeout",
                    "correlation_id": correlation_id,
                    "source_node": source_node,
                })
                logger.debug(f"[PENDING] Timeout event queued for {correlation_id}")
        except Exception as e:
            logger.error(f"[PENDING] Failed to queue timeout event: {e}")
    
    timer_service.start_timer(
        correlation_id=correlation_id,
        task_id=task.id,
        delay_seconds=timeout_seconds,
        callback=on_timeout
    )
    
    logger.info(f"[PENDING] Registered async operation {correlation_id} from {source_node} (timeout={timeout_seconds}s)")
    
    return correlation_id


def resolve_async_operation(
    task: "ManagedTask",
    correlation_id: str,
    result: Any = None,
    error: Optional[str] = None,
    timer_service: Optional[TimerService] = None
) -> Optional[PendingEvent]:
    """
    Resolve a pending async operation.
    
    Called when a callback/webhook arrives or timeout fires.
    
    Args:
        task: The ManagedTask that owns this operation
        correlation_id: The operation's correlation ID
        result: Success result (if any)
        error: Error message (if failed/timed out)
        timer_service: Optional timer service (uses global if not provided)
        
    Returns:
        The resolved PendingEvent, or None if not found
    """
    if timer_service is None:
        timer_service = get_timer_service()
    
    # Cancel the timer (if callback arrived before timeout)
    timer_service.cancel_timer(correlation_id)
    
    # Resolve on task
    event = task.resolve_pending_event(
        correlation_id=correlation_id,
        result=result,
        error=error
    )
    
    if event:
        status = "error" if error else "completed"
        logger.info(f"[PENDING] Resolved {correlation_id} with status={status}")
    else:
        logger.warning(f"[PENDING] Could not find pending event {correlation_id}")
    
    return event


def cancel_task_async_operations(
    task: "ManagedTask",
    timer_service: Optional[TimerService] = None
) -> int:
    """
    Cancel all pending async operations for a task.
    
    Called when a task is cancelled.
    
    Args:
        task: The ManagedTask to cancel operations for
        timer_service: Optional timer service (uses global if not provided)
        
    Returns:
        Number of operations cancelled
    """
    if timer_service is None:
        timer_service = get_timer_service()
    
    # Cancel all timers for this task
    timer_count = timer_service.cancel_all_for_task(task.id)
    
    # Mark all pending events as cancelled
    cancelled = task.cancel_all_pending_events()
    
    if cancelled:
        logger.info(f"[PENDING] Cancelled {len(cancelled)} pending events for task {task.id}")
    
    return len(cancelled)


def build_callback_event(
    correlation_id: str,
    result: Any = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build a callback event payload for routing.
    
    This is the format expected by the event routing system.
    
    Args:
        correlation_id: The operation's correlation ID
        result: Success result (if any)
        error: Error message (if failed)
        metadata: Additional metadata
        
    Returns:
        Event payload dict
    """
    event = {
        "type": "async_callback",
        "correlation_id": correlation_id,
        "result": result,
        "error": error,
    }
    
    if metadata:
        event["metadata"] = metadata
    
    return event


def route_callback_to_task(
    correlation_id: str,
    result: Any = None,
    error: Optional[str] = None,
    task_lookup: Optional[Dict[str, "ManagedTask"]] = None
) -> bool:
    """
    Route a callback event to the correct task queue.
    
    Parses the correlation ID to find the task and queues the event.
    
    Args:
        correlation_id: The operation's correlation ID
        result: Success result (if any)
        error: Error message (if failed)
        task_lookup: Dict of task_id -> ManagedTask for lookup
        
    Returns:
        True if event was routed successfully, False otherwise
    """
    task_id, _ = parse_correlation_id(correlation_id)
    if not task_id:
        logger.error(f"[PENDING] Invalid correlation_id format: {correlation_id}")
        return False
    
    if not task_lookup:
        logger.error(f"[PENDING] No task_lookup provided for routing")
        return False
    
    task = task_lookup.get(task_id)
    if not task:
        logger.error(f"[PENDING] Task not found: {task_id}")
        return False
    
    if not task.queue:
        logger.error(f"[PENDING] Task has no queue: {task_id}")
        return False
    
    # Build and queue the event
    event = build_callback_event(correlation_id, result, error)
    task.queue.put(event)
    
    logger.debug(f"[PENDING] Routed callback to task {task_id}")
    return True
