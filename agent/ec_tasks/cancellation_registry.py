"""
Global cancellation registry for cooperative task cancellation.

Simple thread-safe dictionary mapping task_id -> threading.Event.
Avoids passing objects through LangGraph state (serialization issues).
"""
import threading
from typing import Optional

_registry: dict[str, threading.Event] = {}
_lock = threading.Lock()


def register(task_id: str, event: threading.Event) -> None:
    with _lock:
        _registry[task_id] = event


def unregister(task_id: str) -> None:
    with _lock:
        _registry.pop(task_id, None)


def get(task_id: str) -> Optional[threading.Event]:
    return _registry.get(task_id)
