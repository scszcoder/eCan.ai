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

from .executor import TaskExecutor

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
]
