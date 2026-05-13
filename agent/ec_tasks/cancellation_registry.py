"""
Global cancellation registry for cooperative task cancellation.

Simple thread-safe dictionary mapping task_id -> threading.Event.
Avoids passing objects through LangGraph state (serialization issues).

Usage:
    from agent.ec_tasks import cancellation_registry

    # Register a task for cancellation
    event = threading.Event()
    cancellation_registry.register("task-123", event)

    # Check if task should be cancelled
    if cancellation_registry.get("task-123")?.is_set():
        # Task was cancelled

    # List all registered tasks
    tasks = cancellation_registry.list_registered_tasks()

    # Unregister when done
    cancellation_registry.unregister("task-123")

    # Cancel task by ID (external API)
    cancellation_registry.cancel_task("task-123")

    # Check and cancel (atomic operation)
    cancellation_registry.cancel_if_registered("task-123")

    # Create and register cancellation event atomically
    was_registered = cancellation_registry.create_and_register("task-123")
"""
import os
import threading
import time
import json
from typing import Optional, List

from utils.logger_helper import logger_helper as logger

_registry: dict[str, threading.Event] = {}
_lock = threading.Lock()

# File-based cancellation for cross-process/CLI usage
_CANCEL_REQUEST_FILE = os.environ.get("ECAN_TASK_CANCEL_FILE", "/tmp/ecan_task_cancel_request.json")


def register(task_id: str, event: threading.Event) -> None:
    """Register a task for cancellation tracking."""
    with _lock:
        _registry[task_id] = event


def unregister(task_id: str) -> None:
    """Unregister a task from cancellation tracking."""
    with _lock:
        _registry.pop(task_id, None)


def get(task_id: str) -> Optional[threading.Event]:
    """Get the cancellation event for a task."""
    return _registry.get(task_id)


def list_registered_tasks() -> List[str]:
    """
    List all task IDs currently registered for cancellation.

    Returns:
        List of task IDs
    """
    with _lock:
        return list(_registry.keys())


# ==================== External API Methods ====================
# These methods provide a higher-level API for task management,
# replacing the need for standalone cancel_task_script.py

def cancel_task(task_id: str, reason: str = "external_request") -> bool:
    """
    Cancel a task by ID. Sets the cancellation event if registered.

    This is the main external API for canceling tasks from:
    - MCP tools
    - CLI scripts
    - GUI actions

    Args:
        task_id: The task ID to cancel
        reason: Optional reason for cancellation

    Returns:
        True if cancellation was triggered, False if task not found
    """
    with _lock:
        event = _registry.get(task_id)

    if event is None:
        logger.debug(f"[cancellation_registry] Task '{task_id}' not registered for cancellation")
        return False

    event.set()
    logger.info(f"[cancellation_registry] Cancellation triggered for task '{task_id}' (reason: {reason})")
    return True


def cancel_if_registered(task_id: str, reason: str = "external_request") -> bool:
    """
    Atomic check-and-cancel operation.

    Returns True if task was registered and cancellation was triggered.
    Returns False if task was not registered.

    Args:
        task_id: The task ID to cancel
        reason: Optional reason for cancellation

    Returns:
        True if task was cancelled, False if not found
    """
    with _lock:
        event = _registry.get(task_id)
        if event is None:
            return False
        event.set()
        return True


def create_and_register(task_id: str) -> threading.Event:
    """
    Create and register a new cancellation event atomically.

    If a task is already registered, returns the existing event.

    Args:
        task_id: The task ID to register

    Returns:
        The cancellation event (new or existing)
    """
    with _lock:
        existing = _registry.get(task_id)
        if existing is not None:
            return existing
        event = threading.Event()
        _registry[task_id] = event
        return event


def is_registered(task_id: str) -> bool:
    """Check if a task is registered for cancellation."""
    with _lock:
        return task_id in _registry


def is_cancelled(task_id: str) -> bool:
    """Check if a task's cancellation event has been set."""
    with _lock:
        event = _registry.get(task_id)
    if event is None:
        return False
    return event.is_set()


# ==================== File-Based Cancellation ====================
# For CLI/cross-process cancellation

def request_cancel_from_file(task_id: str, timeout: float = 30.0) -> dict:
    """
    Write a cancellation request to a file and wait for acknowledgment.

    This allows external processes (CLI scripts) to request cancellation
    without needing direct Python import.

    Args:
        task_id: The task ID to cancel
        timeout: Maximum seconds to wait for acknowledgment

    Returns:
        Dict with status: "cancelled", "not_found", "timeout", or "error"
    """
    cancel_request = {
        "action": "cancel_task",
        "task_id": task_id,
        "timestamp": time.time(),
    }

    try:
        with open(_CANCEL_REQUEST_FILE, "w") as f:
            json.dump(cancel_request, f, indent=2)

        logger.info(f"[cancellation_registry] Cancel request written to {_CANCEL_REQUEST_FILE}")

        # Wait for acknowledgment
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with open(_CANCEL_REQUEST_FILE, "r") as f:
                    status = json.load(f)
                status_str = status.get("status", "")
                if status_str in ("cancelled", "not_found"):
                    logger.info(f"[cancellation_registry] Cancel request acknowledged: {status_str}")
                    return status
            except (json.JSONDecodeError, FileNotFoundError):
                pass
            time.sleep(0.5)

        logger.warning(f"[cancellation_registry] Cancel request timeout for task '{task_id}'")
        return {"status": "timeout", "task_id": task_id}

    except Exception as e:
        logger.error(f"[cancellation_registry] Failed to write cancel request: {e}")
        return {"status": "error", "error": str(e)}


def process_cancel_request_file() -> Optional[str]:
    """
    Check and process any pending cancellation request from file.

    Call this periodically from the main event loop.

    Returns:
        task_id if a cancellation was processed, None otherwise
    """
    try:
        if not os.path.exists(_CANCEL_REQUEST_FILE):
            return None

        with open(_CANCEL_REQUEST_FILE, "r") as f:
            request = json.load(f)

        action = request.get("action", "")
        if action != "cancel_task":
            return None

        task_id = request.get("task_id", "")
        if not task_id:
            return None

        # Try to cancel via in-memory registry
        cancelled = cancel_task(task_id, reason="file_request")

        # Write acknowledgment
        response = {
            "status": "cancelled" if cancelled else "not_found",
            "task_id": task_id,
            "processed_at": time.time(),
        }
        with open(_CANCEL_REQUEST_FILE, "w") as f:
            json.dump(response, f, indent=2)

        return task_id

    except Exception as e:
        logger.debug(f"[cancellation_registry] No pending cancel request: {e}")
        return None


# ==================== Utility ====================

def get_registry_size() -> int:
    """Get the number of registered tasks."""
    with _lock:
        return len(_registry)


def clear_all() -> int:
    """
    Clear all registered tasks. Use with caution.

    Returns:
        Number of tasks cleared
    """
    with _lock:
        count = len(_registry)
        _registry.clear()
        return count
