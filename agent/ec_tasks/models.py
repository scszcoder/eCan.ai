"""
Task Models - Pure data models for task management.

This module contains only data structures with minimal logic.
Execution logic is separated into executor.py.
"""

import asyncio
import threading
import uuid
from datetime import datetime
from enum import Enum
from queue import Queue
import time
from typing import Any, Callable, ClassVar, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.a2a.common.types import Task, TaskState, Message, TextPart


# ==================== Utility Functions ====================

def create_enum_validator(enum_class, invalid_values=None, allow_none=True):
    """
    Create a generic validator for enum fields.
    
    Args:
        enum_class: The Enum class to validate against
        invalid_values: Set of values to treat as invalid (e.g., {'none', ''})
        allow_none: Whether to allow None values (default: True)
    
    Returns:
        A validator function that can be used with @field_validator
    
    Example:
        @field_validator('priority', mode='before')
        @classmethod
        def validate_priority(cls, v):
            return create_enum_validator(PriorityType, {'none', ''})(v)
    """
    if invalid_values is None:
        invalid_values = {'none', ''}
    
    def validator(v):
        # Handle None and empty values
        if v is None or v == '':
            return None if allow_none else v
        
        # Check if value is in invalid set (case-insensitive)
        if isinstance(v, str) and v.lower() in invalid_values:
            return None if allow_none else v
        
        # If already correct enum type, return as is
        if isinstance(v, enum_class):
            return v
        
        # Try to convert string to enum
        if isinstance(v, str):
            try:
                # Try exact match first
                return enum_class(v)
            except ValueError:
                # Try case-insensitive match
                v_lower = v.lower()
                for enum_item in enum_class:
                    if enum_item.value.lower() == v_lower:
                        return enum_item
                # Invalid value
                return None if allow_none else v
        
        # Unknown type
        return None if allow_none else v
    
    return validator


# ==================== Enums ====================

class PriorityType(str, Enum):
    """Task priority levels."""
    LOW = "low"
    MID = "mid"
    HIGH = "High"
    URGENT = "Urgent"
    ASAP = "ASAP"


class RepeatType(str, Enum):
    """Task repeat schedule types."""
    NONE = "none"
    BY_SECONDS = "by seconds"
    BY_MINUTES = "by minutes"
    BY_HOURS = "by hours"
    BY_DAYS = "by days"
    BY_WEEKS = "by weeks"
    BY_MONTHS = "by months"
    BY_YEARS = "by years"


class WeekDayType(str, Enum):
    """Days of the week."""
    M = "M"
    TU = "Tu"
    W = "W"
    TH = "Th"
    F = "F"
    SA = "Sa"
    SU = "Su"


class MonthType(str, Enum):
    """Months of the year."""
    JAN = "Jan"
    FEB = "Feb"
    MAR = "Mar"
    APR = "Apr"
    MAY = "May"
    JUN = "Jun"
    JUL = "Jul"
    AUG = "Aug"
    SEP = "Sep"
    OCT = "Oct"
    NOV = "Nov"
    DEC = "Dec"


# ==================== Pending Event Status ====================

class PendingEventStatus(str, Enum):
    """Status of a pending async event."""
    PENDING = "pending"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


# ==================== Pending Event Model ====================

class PendingEvent(BaseModel):
    """
    Represents a pending async operation that the task is waiting for.
    
    Used for fire-and-forget async tool calls where the workflow continues
    but completion tracking is deferred until the callback/webhook arrives.
    """
    correlation_id: str  # Self-routing: "{task_id}:{uuid}"
    source_node: str  # Node that registered this event
    registered_at: float = Field(default_factory=time.time)
    timeout_at: float  # When to timeout (absolute timestamp)
    timeout_seconds: float  # Original timeout value
    status: PendingEventStatus = PendingEventStatus.PENDING
    result: Optional[Any] = None  # Callback result when completed
    error: Optional[str] = None  # Error message if failed/timed_out
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    def is_pending(self) -> bool:
        """Check if this event is still pending."""
        return self.status == PendingEventStatus.PENDING
    
    def is_expired(self) -> bool:
        """Check if this event has expired based on timeout."""
        return time.time() > self.timeout_at
    
    def mark_completed(self, result: Any = None):
        """Mark this event as completed with optional result."""
        self.status = PendingEventStatus.COMPLETED
        self.result = result
    
    def mark_timed_out(self):
        """Mark this event as timed out."""
        self.status = PendingEventStatus.TIMED_OUT
        self.error = "timeout"
    
    def mark_cancelled(self):
        """Mark this event as cancelled."""
        self.status = PendingEventStatus.CANCELLED
        self.error = "cancelled"


# ==================== Schedule Model ====================

class TaskSchedule(BaseModel):
    """Task scheduling configuration."""
    repeat_type: RepeatType
    repeat_number: int
    repeat_unit: str
    start_date_time: str
    end_date_time: str
    time_out: int  # seconds


# ==================== Managed Task Model ====================

class ManagedTask(Task):
    """
    A managed task that wraps a skill execution.
    
    This class focuses on data and state management.
    Execution logic is delegated to TaskExecutor.
    """
    # Core identifiers
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # Will be overridden in __init__
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    source: str = "ui"  # "code" for code-based, "ui" for UI-created
    
    # Skill reference (Any to avoid strict validation)
    skill: Any = None
    
    # State management
    state: dict = Field(default_factory=dict)
    resume_from: Optional[str] = None
    trigger: Optional[str] = None
    
    # Async task reference
    task: Optional[asyncio.Task] = None
    
    # Synchronization primitives
    pause_event: asyncio.Event = Field(default_factory=asyncio.Event)
    cancellation_event: threading.Event = Field(default_factory=threading.Event)
    
    # Scheduling
    schedule: Optional[TaskSchedule] = None
    priority: Optional[PriorityType] = None
    last_run_datetime: Optional[datetime] = None
    already_run_flag: bool = False
    
    # Checkpoints for interrupt/resume
    checkpoint_nodes: Optional[List[dict]] = None
    
    # Message queue for this task
    queue: Optional[Queue] = Field(default_factory=Queue)
    
    # Pending async events (fire-and-forget completions)
    pending_events: Dict[str, PendingEvent] = Field(default_factory=dict)
    
    # Guardrail: Max steps limit (like browser-use)
    max_steps: Optional[int] = None  # None = unlimited
    n_steps: int = 0  # Current step counter
    
    # Guardrail: Consecutive failure tracking
    consecutive_failures: int = 0
    max_failures: int = 3  # Stop after this many consecutive failures
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    @field_validator('priority', mode='before')
    @classmethod
    def validate_priority(cls, v):
        """Validate and normalize priority field using generic enum validator."""
        return create_enum_validator(PriorityType, invalid_values={'none', ''})(v)
    
    def __init__(self, **data):
        super().__init__(**data)
        # Ensure pause_event is set by default (not paused)
        if not self.pause_event.is_set():
            self.pause_event.set()
        # Default priority
        if self.priority is None:
            self.priority = PriorityType.LOW
        # Initialize checkpoint_nodes
        if self.checkpoint_nodes is None:
            self.checkpoint_nodes = []
        # Initialize pending_events
        if self.pending_events is None:
            self.pending_events = {}
    
    # ==================== Skill Management ====================
    
    def set_skill(self, skill):
        """Set the skill for this task."""
        self.skill = skill
    
    def set_priority(self, priority: PriorityType):
        """Set task priority."""
        self.priority = priority
    
    # ==================== Checkpoint Management ====================
    
    def add_checkpoint_node(self, checkpoint: dict):
        """Add a checkpoint node for interrupt/resume."""
        if self.checkpoint_nodes is None:
            self.checkpoint_nodes = []
        if checkpoint not in self.checkpoint_nodes:
            self.checkpoint_nodes.append(checkpoint)
    
    def remove_checkpoint_node(self, checkpoint: dict):
        """Remove a checkpoint node."""
        if self.checkpoint_nodes is None:
            self.checkpoint_nodes = []
        if checkpoint in self.checkpoint_nodes:
            self.checkpoint_nodes.remove(checkpoint)
    
    def get_last_checkpoint(self) -> Optional[dict]:
        """Get the most recent checkpoint."""
        if self.checkpoint_nodes:
            return self.checkpoint_nodes[-1]
        return None
    
    def pop_checkpoint_by_tag(self, tag: str) -> Optional[dict]:
        """Find and remove a checkpoint by its tag."""
        if not self.checkpoint_nodes:
            return None
        for i, cp in enumerate(self.checkpoint_nodes):
            if cp.get("tag") == tag:
                return self.checkpoint_nodes.pop(i)
        return None
    
    # ==================== Lifecycle Management ====================
    
    def cancel(self):
        """Signal the task to cancel its execution."""
        self.cancellation_event.set()
    
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self.cancellation_event.is_set()
    
    def pause(self):
        """Pause the task execution."""
        self.pause_event.clear()
    
    def resume(self):
        """Resume the task execution."""
        self.pause_event.set()
    
    def is_paused(self) -> bool:
        """Check if task is paused."""
        return not self.pause_event.is_set()
    
    def exit(self):
        """Stop the task and cancel any running operations."""
        self.cancel()
        if self.task and not self.task.done():
            self.task.cancel()
    
    # ==================== Validation ====================
    
    def validate_skill(self) -> bool:
        """
        Validate that the task has a valid skill with a runnable.
        
        Returns:
            True if valid, False otherwise.
        """
        if self.skill is None:
            return False
        if not hasattr(self.skill, 'runnable') or self.skill.runnable is None:
            return False
        return True
    
    def get_skill_name(self) -> str:
        """Get the skill name safely."""
        if self.skill is None:
            return "UNKNOWN"
        return getattr(self.skill, 'name', 'UNKNOWN')
    
    # ==================== Pending Event Management ====================
    
    def register_pending_event(
        self,
        correlation_id: str,
        source_node: str,
        timeout_seconds: float = 60.0
    ) -> PendingEvent:
        """
        Register a pending async event.
        
        Args:
            correlation_id: Unique ID for this event (format: "{task_id}:{uuid}")
            source_node: Name of the node that registered this event
            timeout_seconds: How long to wait before timing out
            
        Returns:
            The created PendingEvent
        """
        event = PendingEvent(
            correlation_id=correlation_id,
            source_node=source_node,
            registered_at=time.time(),
            timeout_at=time.time() + timeout_seconds,
            timeout_seconds=timeout_seconds,
        )
        self.pending_events[correlation_id] = event
        return event
    
    def resolve_pending_event(
        self,
        correlation_id: str,
        result: Any = None,
        error: Optional[str] = None
    ) -> Optional[PendingEvent]:
        """
        Resolve a pending event with result or error.
        
        Args:
            correlation_id: The event's correlation ID
            result: Success result (if any)
            error: Error message (if failed/timed out)
            
        Returns:
            The resolved PendingEvent, or None if not found
        """
        event = self.pending_events.get(correlation_id)
        if event is None:
            return None
        
        if error:
            if error == "timeout":
                event.mark_timed_out()
            elif error == "cancelled":
                event.mark_cancelled()
            else:
                event.status = PendingEventStatus.COMPLETED
                event.error = error
        else:
            event.mark_completed(result)
        
        return event
    
    def has_pending_events(self) -> bool:
        """
        Check if there are any pending (unresolved) events.
        
        Returns:
            True if any events are still pending
        """
        return any(e.is_pending() for e in self.pending_events.values())
    
    def get_pending_events(self) -> List[PendingEvent]:
        """
        Get all pending (unresolved) events.
        
        Returns:
            List of pending events
        """
        return [e for e in self.pending_events.values() if e.is_pending()]
    
    def get_all_pending_event_results(self) -> Dict[str, Any]:
        """
        Get results from all resolved pending events.
        
        Returns:
            Dict mapping correlation_id to result/error info
        """
        results = {}
        for corr_id, event in self.pending_events.items():
            if not event.is_pending():
                results[corr_id] = {
                    "status": event.status.value,
                    "result": event.result,
                    "error": event.error,
                    "source_node": event.source_node,
                }
        return results
    
    def cleanup_expired_events(self) -> List[str]:
        """
        Mark all expired pending events as timed out.
        
        Returns:
            List of correlation IDs that were marked as timed out
        """
        expired = []
        for corr_id, event in self.pending_events.items():
            if event.is_pending() and event.is_expired():
                event.mark_timed_out()
                expired.append(corr_id)
        return expired
    
    def cancel_all_pending_events(self) -> List[str]:
        """
        Cancel all pending events (used when task is cancelled).
        
        Returns:
            List of correlation IDs that were cancelled
        """
        cancelled = []
        for corr_id, event in self.pending_events.items():
            if event.is_pending():
                event.mark_cancelled()
                cancelled.append(corr_id)
        return cancelled
    
    def clear_pending_events(self):
        """Clear all pending events (for cleanup after task completion)."""
        self.pending_events.clear()
    
    # ==================== Step & Failure Tracking ====================
    
    def increment_step(self) -> int:
        """
        Increment step counter and return new value.
        
        Returns:
            Current step number after increment
        """
        self.n_steps += 1
        return self.n_steps
    
    def is_max_steps_reached(self) -> bool:
        """
        Check if max steps limit has been reached.
        
        Returns:
            True if max_steps is set and n_steps >= max_steps
        """
        if self.max_steps is None:
            return False
        return self.n_steps >= self.max_steps
    
    def record_failure(self) -> int:
        """
        Record a consecutive failure.
        
        Returns:
            Current consecutive failure count
        """
        self.consecutive_failures += 1
        return self.consecutive_failures
    
    def reset_failures(self):
        """Reset consecutive failure counter (called on success)."""
        self.consecutive_failures = 0
    
    def is_max_failures_reached(self) -> bool:
        """
        Check if max consecutive failures has been reached.
        
        Returns:
            True if consecutive_failures >= max_failures
        """
        return self.consecutive_failures >= self.max_failures
    
    def get_guardrail_status(self) -> dict:
        """
        Get current guardrail status for logging/debugging.
        
        Returns:
            Dict with step and failure tracking info
        """
        return {
            "n_steps": self.n_steps,
            "max_steps": self.max_steps,
            "steps_remaining": (self.max_steps - self.n_steps) if self.max_steps else None,
            "consecutive_failures": self.consecutive_failures,
            "max_failures": self.max_failures,
            "failures_remaining": self.max_failures - self.consecutive_failures,
        }
