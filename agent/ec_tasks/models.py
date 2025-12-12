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
from typing import Any, ClassVar, Dict, List, Optional

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
