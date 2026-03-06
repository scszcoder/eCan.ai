"""Shared constants for ec_tasks serialization."""

# Fields to exclude when serializing ManagedTask objects to JSON.
# These fields contain non-serializable objects (Event, Future, Queue, etc.).
TASK_SERIALIZATION_EXCLUDE = {
    "skill",                 # StateGraph object (complex, handled separately)
    "task",                  # asyncio.Task
    "pause_event",           # asyncio.Event
    "cancellation_event",    # threading.Event
    "queue",                 # Queue object
    "future",                # concurrent.futures.Future
    "executor",              # ThreadPoolExecutor
    "loop",                  # asyncio event loop
    "thread",                # threading.Thread
    "process",               # multiprocessing.Process
    "pending_events",        # Dict with complex objects
    "checkpoint_nodes",      # May contain non-serializable objects
    "_force_stop_callbacks", # Private attr with Callable objects
}
