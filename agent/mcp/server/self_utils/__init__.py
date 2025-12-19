"""
Self Utils Module - Tools for agent self-introspection and task management.

This module provides MCP tools for:
- describe_self: Get structured agent description (skills, tasks)
- start_task_using_skill: Start a task using a specific skill
- stop_task_using_skill: Stop a running task
- schedule_task: Schedule a task to run at specified times
"""

from .self_tools import (
    describe_self,
    start_task_using_skill,
    stop_task_using_skill,
    schedule_task,
    add_describe_self_tool_schema,
    add_start_task_using_skill_tool_schema,
    add_stop_task_using_skill_tool_schema,
    add_schedule_task_tool_schema,
    async_schedule_task,
)

__all__ = [
    "describe_self",
    "start_task_using_skill",
    "stop_task_using_skill",
    "schedule_task",
    "add_describe_self_tool_schema",
    "add_start_task_using_skill_tool_schema",
    "add_stop_task_using_skill_tool_schema",
    "add_schedule_task_tool_schema",
    "async_schedule_task",
]
