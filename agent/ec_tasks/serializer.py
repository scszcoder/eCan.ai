"""
Task Serializer - Serialization logic for tasks.

This module handles converting tasks and their state to JSON-serializable formats.
"""

import json
from typing import Any, Dict, Optional, TYPE_CHECKING

from pydantic import BaseModel
from langgraph.types import Interrupt

from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from .models import ManagedTask


class TaskSerializer:
    """
    Serializer for ManagedTask objects.
    
    Handles conversion of complex objects to JSON-serializable formats,
    including special handling for:
    - Pydantic models
    - LangChain messages
    - LangGraph interrupts
    - Non-serializable objects
    """
    
    @staticmethod
    def to_dict(task: "ManagedTask") -> Dict[str, Any]:
        """
        Convert a ManagedTask to a JSON-serializable dictionary.
        
        Args:
            task: The task to serialize.
            
        Returns:
            A dictionary representation of the task.
        """
        serializer = TaskSerializer()
        
        # Convert datetime to ISO format string
        last_run_datetime_str = None
        if task.last_run_datetime:
            last_run_datetime_str = task.last_run_datetime.isoformat()
        
        # Convert schedule to dict with proper enum handling
        schedule_dict = None
        if task.schedule:
            schedule_dict = task.schedule.model_dump(mode='json')
        
        # Safely serialize state
        safe_state = serializer.make_serializable(task.state) if task.state else None
        
        # Safely serialize checkpoint_nodes
        safe_checkpoint_nodes = serializer.make_serializable(task.checkpoint_nodes) if task.checkpoint_nodes else None
        
        # Safely serialize metadata
        safe_metadata = serializer.make_serializable(task.metadata) if task.metadata else None
        
        # Safely get skill name
        skill_name = serializer._get_skill_name(task)
        
        return {
            "id": task.id,
            "runId": task.run_id,
            "name": task.name,
            "description": task.description,
            "skill": skill_name,
            "metadata": safe_metadata,
            "state": safe_state,
            "resume_from": task.resume_from,
            "trigger": task.trigger,
            "schedule": schedule_dict,
            "checkpoint_nodes": safe_checkpoint_nodes,
            "priority": task.priority.value if task.priority else None,
            "last_run_datetime": last_run_datetime_str,
            "already_run_flag": task.already_run_flag,
        }
    
    def _get_skill_name(self, task: "ManagedTask") -> Optional[str]:
        """Safely extract skill name from task."""
        if not task.skill:
            return None
        
        skill_name = getattr(task.skill, 'name', None)
        if skill_name:
            return skill_name
        
        # Try string representation
        skill_str = str(task.skill)
        if not skill_str.startswith('<'):
            return skill_str
        
        logger.warning(f"Task {task.name} has skill object without name attribute: {type(task.skill)}")
        return None
    
    def make_serializable(self, obj: Any) -> Any:
        """
        Recursively convert objects to JSON-serializable format.
        
        Filters out non-serializable objects like Interrupt instances
        and langchain Message objects.
        
        Args:
            obj: The object to serialize.
            
        Returns:
            A JSON-serializable representation.
        """
        if obj is None:
            return None
        
        # Handle Pydantic BaseModel objects
        if isinstance(obj, BaseModel):
            return self.make_serializable(obj.model_dump(mode='json'))
        
        # Handle langchain Message objects
        if self._is_langchain_message(obj):
            return self._serialize_langchain_message(obj)
        
        # Handle Interrupt objects
        if isinstance(obj, Interrupt):
            return self._serialize_interrupt(obj)
        
        # Handle custom interrupt objects with checkpoint
        if self._is_interrupt_with_checkpoint(obj):
            return self._serialize_interrupt_with_checkpoint(obj)
        
        # Handle dictionaries
        if isinstance(obj, dict):
            return self._serialize_dict(obj)
        
        # Handle lists and tuples
        if isinstance(obj, (list, tuple)):
            return [self.make_serializable(item) for item in obj]
        
        # Handle basic types
        if isinstance(obj, (str, int, float, bool)):
            return obj
        
        # Try to serialize the object
        return self._try_serialize(obj)
    
    def _is_langchain_message(self, obj: Any) -> bool:
        """Check if object is a langchain message."""
        return (hasattr(obj, '__class__') and 
                obj.__class__.__module__.startswith('langchain_core.messages'))
    
    def _serialize_langchain_message(self, obj: Any) -> Dict[str, Any]:
        """Serialize a langchain message object."""
        try:
            return {
                "type": obj.__class__.__name__,
                "content": str(getattr(obj, 'content', '')),
                "role": getattr(obj, 'type', 'unknown')
            }
        except Exception as e:
            logger.warning(f"Failed to serialize langchain message: {e}")
            return f"<langchain-message: {obj.__class__.__name__}>"
    
    def _serialize_interrupt(self, obj: Interrupt) -> Dict[str, Any]:
        """Serialize an Interrupt object."""
        return {
            "type": "interrupt",
            "value": self.make_serializable(getattr(obj, 'value', None)),
            "id": str(getattr(obj, 'id', 'unknown'))
        }
    
    def _is_interrupt_with_checkpoint(self, obj: Any) -> bool:
        """Check if object is an InterruptWithCheckpoint."""
        return (hasattr(obj, '__class__') and 
                obj.__class__.__name__ == 'InterruptWithCheckpoint')
    
    def _serialize_interrupt_with_checkpoint(self, obj: Any) -> Dict[str, Any]:
        """Serialize an InterruptWithCheckpoint object."""
        return {
            "type": "interrupt_with_checkpoint",
            "value": self.make_serializable(getattr(obj, 'value', None)),
            "id": str(getattr(obj, 'id', 'unknown')),
            "checkpoint_available": True  # Don't serialize the actual checkpoint
        }
    
    def _serialize_dict(self, obj: dict) -> Dict[str, Any]:
        """Serialize a dictionary, handling special keys."""
        result = {}
        for key, value in obj.items():
            try:
                if key == "__interrupt__":
                    # Convert interrupt list to safe format
                    if isinstance(value, list):
                        result[key] = [self.make_serializable(item) for item in value]
                    else:
                        result[key] = self.make_serializable(value)
                else:
                    result[key] = self.make_serializable(value)
            except Exception as e:
                logger.warning(f"Skipping non-serializable key '{key}': {e}")
                result[key] = f"<non-serializable: {type(value).__name__}>"
        return result
    
    def _try_serialize(self, obj: Any) -> Any:
        """Try to serialize an object, returning a placeholder if it fails."""
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return f"<non-serializable: {type(obj).__name__}>"


# Convenience function for direct use
def serialize_task(task: "ManagedTask") -> Dict[str, Any]:
    """Serialize a ManagedTask to a dictionary."""
    return TaskSerializer.to_dict(task)
