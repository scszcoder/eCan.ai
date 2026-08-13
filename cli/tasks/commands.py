#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task Management Commands - CRUD operations and queries for tasks.
"""

import click

from ..base.context import get_context
from ..base.output import get_output
from ..base.config import get_config
from ..base.decorators import requires_auth


def _resolve_task(ctx, out, identifier):
    """Resolve an id-or-name to a concrete task id, or exit with an error."""
    from ..base.resolve import resolve_entity_id
    try:
        resolved = resolve_entity_id(ctx.db.task_service, identifier, 'task')
    except ValueError as e:
        out.error(str(e))
        raise SystemExit(1)
    if not resolved:
        out.error(f"No task found matching '{identifier}'")
        raise SystemExit(1)
    return resolved


@click.group()
def tasks():
    """
    Task management commands.

    OPERATION commands for creating, updating, and deleting tasks.
    QUERY commands for listing and retrieving task information.
    CONTROL commands for executing tasks.

    Examples:
      ecan tasks list
      ecan tasks add -n "My Task"
      ecan tasks update abc123 --status completed
    """
    pass


@tasks.command('list')
@click.option('--name', '-n',
              help='Filter tasks by name (case-insensitive partial match)')
@click.option('--status', '-s',
              help='Filter tasks by status (e.g., pending, running, completed)')
@click.option('--limit', '-l', default=50, type=int,
              help='Maximum number of results (default: 50)')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'simple']),
              default='table',
              help='Output format (default: table)')
def list_tasks(name, status, limit, format):
    """
    List all tasks.

    QUERY command - retrieves and displays tasks from the database.

    Examples:
      ecan tasks list
      ecan tasks list --limit 100
      ecan tasks list --status pending
      ecan tasks list --format json
    """
    ctx = get_context()
    out = get_output()

    if limit < 1:
        out.error("--limit must be >= 1")
        raise SystemExit(1)
    limit = min(limit, get_config().get('max_limit', 1000))

    try:
        result = ctx.db.task_service.query_tasks(name=name)
        tasks_data = result.get('data', [])

        if status:
            tasks_data = [t for t in tasks_data if t.get('status') == status]
        tasks_data = tasks_data[:limit]

        if format == 'json':
            out.json({'tasks': tasks_data, 'count': len(tasks_data)})
        elif format == 'simple':
            for task in tasks_data:
                out.print(f"{(task.get('id') or '')}\t{task.get('name', '')}\t{task.get('status', '')}")
        else:
            rows = [
                [
                    (task.get('id') or '')[:12] + '...' if len(task.get('id') or '') > 12 else (task.get('id') or ''),
                    task.get('name', ''),
                    task.get('status', ''),
                ]
                for task in tasks_data
            ]
            out.table("Tasks", ["ID", "Name", "Status"], rows)
    except Exception as e:
        out.error(f"Failed to list tasks: {e}")
        raise SystemExit(1)


@tasks.command()
@click.argument('task_id')
def get(task_id):
    """
    Get task details by ID.

    QUERY command - retrieves full details for a specific task.

    Examples:
      ecan tasks get abc123
    """
    ctx = get_context()
    out = get_output()

    task_id = _resolve_task(ctx, out, task_id)

    try:
        result = ctx.db.task_service.get_task_by_id(task_id)
        if result.get('success'):
            out.json(result['data'])
        else:
            out.error(f"Task not found: {task_id}")
            raise SystemExit(1)
    except Exception as e:
        out.error(f"Failed to get task: {e}")
        raise SystemExit(1)


@tasks.command()
@requires_auth
@click.option('--name', '-n', required=True,
              help='Task name (required)')
@click.option('--description', '-d', default='',
              help='Task description')
@click.option('--priority', '-p', type=click.Choice(['low', 'normal', 'high', 'urgent']),
              default='normal',
              help='Task priority (default: normal)')
@click.option('--schedule',
              help='Schedule in cron expression (e.g., "0 9 * * *" for daily at 9am)')
def add(name, description, priority, schedule):
    """
    Create a new task.

    OPERATION command - creates a new task in the database.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan tasks add -n "Daily Report" -d "Generate daily report"
      ecan tasks add -n "Weekly Cleanup" -p high --schedule "0 9 * * 1"
      ecan tasks add -n "Process Queue" -p urgent
    """
    ctx = get_context()
    out = get_output()

    task_data = {
        'name': name,
        'description': description,
        'priority': priority,
        'owner': ctx.username,
        'status': 'pending'
    }

    if schedule:
        task_data['schedule'] = schedule

    try:
        result = ctx.db.task_service.add_task(task_data)
    except Exception as e:
        out.error(f"Failed to create task: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    out.success("Task created!")
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    cloud_sync(DataType.TASK, result.get('data') or {**task_data, 'id': result.get('id')}, Operation.ADD)


@tasks.command()
@requires_auth
@click.argument('task_id')
@click.option('--name', '-n',
              help='New task name')
@click.option('--description', '-d',
              help='New task description')
@click.option('--status', '-s',
              help='New task status (e.g., pending, running, completed, failed)')
@click.option('--priority', '-p', type=click.Choice(['low', 'normal', 'high', 'urgent']),
              help='New task priority')
def update(task_id, name, description, status, priority):
    """
    Update an existing task.

    OPERATION command - modifies task properties.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan tasks update abc123 --name "New Name"
      ecan tasks update abc123 --status completed
      ecan tasks update abc123 -s running -p high
    """
    ctx = get_context()
    out = get_output()

    task_id = _resolve_task(ctx, out, task_id)

    fields = {}
    if name:
        fields['name'] = name
    if description:
        fields['description'] = description
    if status:
        fields['status'] = status
    if priority:
        fields['priority'] = priority

    if not fields:
        out.warning("No fields to update")
        return

    try:
        result = ctx.db.task_service.update_task(task_id, fields)
    except Exception as e:
        out.error(f"Failed to update task: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    out.success("Task updated!")
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    cloud_sync(DataType.TASK, result.get('data') or {'id': task_id, **fields}, Operation.UPDATE)


@tasks.command()
@requires_auth
@click.argument('task_id')
@click.option('--force', '-f', is_flag=True,
              help='Skip confirmation prompt')
def remove(task_id, force):
    """
    Delete a task.

    OPERATION command - permanently removes a task.

    Requires authentication. Use 'ecan auth login' first.
    This action cannot be undone.

    Examples:
      ecan tasks remove abc123      # With confirmation
      ecan tasks remove abc123 -f   # Skip confirmation
    """
    ctx = get_context()
    out = get_output()

    task_id = _resolve_task(ctx, out, task_id)

    if not force and not out.confirm(f"Delete task {task_id}?"):
        return

    try:
        result = ctx.db.task_service.delete_task(task_id)
    except Exception as e:
        out.error(f"Failed to delete task: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    out.success("Task deleted!")
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    cloud_sync(DataType.TASK, {'id': task_id}, Operation.DELETE)


@tasks.command()
@requires_auth
@click.argument('task_id')
def execute(task_id):
    """
    Execute a task immediately.

    CONTROL command - triggers immediate task execution.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan tasks execute abc123

    Note:
      Task execution is not yet fully implemented.
    """
    out = get_output()
    out.info(f"Executing task {task_id}...")
    out.warning("Task execution not yet implemented")
