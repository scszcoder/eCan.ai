"""
EC Task Management Module

Modular architecture for task management:
- models: Data models (ManagedTask, TaskSchedule, Enums)
- scheduler: Schedule calculation
- serializer: JSON serialization
- executor: Task execution
- message_sender: GUI messaging
- dev_runner: Debug support
- runner: TaskRunner
- resume: Event normalization, checkpoint, resume payload
- timer_service: Timeout timer management
- pending_events: Async operation registration and routing

Usage:
    from agent.ec_tasks import ManagedTask, TaskRunner, TaskExecutor
"""

from .models import (
    ManagedTask,
    TaskSchedule,
    PriorityType,
    RepeatType,
    WeekDayType,
    MonthType,
)

from .scheduler import (
    get_next_runtime,
    get_runtime_bounds,
    get_repeat_interval_seconds,
    find_tasks_ready_to_run,
    add_months,
    add_years,
)

from .serializer import TaskSerializer

from .executor import (
    TaskExecutor,
    execute_task_stream,
    execute_task_astream,
    execute_task_hybrid,
)

from .message_sender import ChatMessageSender, MessageType

from .dev_runner import DevRunner

from .runner import TaskRunner, TaskRunnerRegistry

from .resume import (
    normalize_event,
    select_checkpoint,
    inject_attributes_into_checkpoint,
    build_resume_from_mapping,
    build_node_transfer_patch,
    build_general_resume_payload,
    load_mapping_for_task,
    get_current_state,
    DEFAULT_MAPPINGS,
)

from .timer_service import (
    TimerService,
    TimerHandle,
    get_timer_service,
    set_timer_service,
)

from .pending_events import (
    register_async_operation,
    resolve_async_operation,
    cancel_task_async_operations,
    generate_correlation_id,
    parse_correlation_id,
    build_callback_event,
    route_callback_to_task,
)

from .models import (
    PendingEvent,
    PendingEventStatus,
)

__all__ = [
    # Models
    "ManagedTask",
    "TaskSchedule",
    "PriorityType",
    "RepeatType",
    "WeekDayType",
    "MonthType",
    # Scheduler
    "get_next_runtime",
    "get_runtime_bounds",
    "get_repeat_interval_seconds",
    "find_tasks_ready_to_run",
    "add_months",
    "add_years",
    # Serializer
    "TaskSerializer",
    # Executor
    "TaskExecutor",
    "execute_task_stream",
    "execute_task_astream",
    "execute_task_hybrid",
    # Message Sender
    "ChatMessageSender",
    "MessageType",
    # Dev Runner
    "DevRunner",
    # Runner
    "TaskRunner",
    "TaskRunnerRegistry",
    # Resume
    "normalize_event",
    "select_checkpoint",
    "inject_attributes_into_checkpoint",
    "build_resume_from_mapping",
    "build_node_transfer_patch",
    "build_general_resume_payload",
    "load_mapping_for_task",
    "get_current_state",
    "DEFAULT_MAPPINGS",
    # Timer Service
    "TimerService",
    "TimerHandle",
    "get_timer_service",
    "set_timer_service",
    # Pending Events
    "PendingEvent",
    "PendingEventStatus",
    "register_async_operation",
    "resolve_async_operation",
    "cancel_task_async_operations",
    "generate_correlation_id",
    "parse_correlation_id",
    "build_callback_event",
    "route_callback_to_task",
]
