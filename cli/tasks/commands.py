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


# Canonical repeat-type tokens accepted by agent/agent_converter.py:_parse_schedule_from_dict
REPEAT_TYPES = ['none', 'seconds', 'minutes', 'hours', 'days', 'weeks', 'months', 'years']
TRIGGER_TYPES = {'schedule', 'message', 'auto', 'manual'}


def _validate_datetime(out, value, label):
    """Validate a schedule datetime string; exit with an error if unparseable."""
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S:%f"):
        try:
            datetime.strptime(value, fmt)
            return value
        except ValueError:
            pass
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except ValueError:
        out.error(f"Invalid {label} datetime: '{value}' (expected 'YYYY-MM-DD HH:MM:SS' or ISO format)")
        raise SystemExit(1)


def _validate_trigger(out, trigger):
    """Validate a comma-separated trigger string; exit with an error on unknown types."""
    tokens = [t.strip() for t in trigger.split(',') if t.strip()]
    invalid = [t for t in tokens if t not in TRIGGER_TYPES]
    if invalid:
        out.error(f"Invalid trigger type(s): {', '.join(invalid)} (valid: {', '.join(sorted(TRIGGER_TYPES))})")
        raise SystemExit(1)
    return ','.join(tokens)


def _build_schedule(out, repeat_type, repeat_number, start, end, timeout):
    """Build the schedule dict stored in the DB, or None if no schedule options were given."""
    if all(v is None for v in (repeat_type, repeat_number, start, end, timeout)):
        return None
    if repeat_type is None:
        out.error("--repeat-type is required when other schedule options are given")
        raise SystemExit(1)
    schedule = {
        'repeat_type': repeat_type,
        'repeat_unit': repeat_type,
        'repeat_number': repeat_number if repeat_number is not None else 1,
        'time_out': timeout if timeout is not None else 120,
    }
    if start is not None:
        schedule['start_date_time'] = _validate_datetime(out, start, 'start')
    if end is not None:
        schedule['end_date_time'] = _validate_datetime(out, end, 'end')
    return schedule


def _parse_vars(out, var_options):
    """Parse repeated --var k=v options into a dict; exit on malformed input."""
    task_vars = {}
    for raw in var_options:
        key, sep, value = raw.partition('=')
        key = key.strip()
        if not sep or not key:
            out.error(f"Invalid --var '{raw}' (expected name=value)")
            raise SystemExit(1)
        task_vars[key] = value
    return task_vars


# CLI aliases -> canonical browser_identity keys (see
# agent/ec_skills/prep_skills_run.py apply_task_vars)
BROWSER_IDENTITY_KEYS = {
    'profile': 'browser_profile',
    'browser_profile': 'browser_profile',
    'cdp_port': 'cdp_port',
    'slot': 'browser_slot_id',
    'browser_slot_id': 'browser_slot_id',
    'user_data_dir': 'user_data_dir',
    'headless': 'headless',
}


def _parse_browser_identity(out, browser_options):
    """Parse repeated --browser k=v options into a canonical dict."""
    identity = {}
    for raw in browser_options:
        key, sep, value = raw.partition('=')
        key = key.strip().lower()
        if not sep or key not in BROWSER_IDENTITY_KEYS:
            out.error(
                f"Invalid --browser '{raw}' (expected key=value with key one of: "
                f"{', '.join(sorted(set(BROWSER_IDENTITY_KEYS)))})"
            )
            raise SystemExit(1)
        identity[BROWSER_IDENTITY_KEYS[key]] = value
    return identity


def _resolve_skill(ctx, out, identifier):
    """Resolve an id-or-name to a concrete skill id, or exit with an error."""
    from ..base.resolve import resolve_entity_id
    try:
        resolved = resolve_entity_id(ctx.db.skill_service, identifier, 'skill')
    except ValueError as e:
        out.error(str(e))
        raise SystemExit(1)
    if not resolved:
        out.error(f"No skill found matching '{identifier}'")
        raise SystemExit(1)
    return resolved


def _schedule_options(f):
    """Shared schedule/trigger options for add and update."""
    options = [
        click.option('--trigger', '-t',
                     help='Trigger source(s), comma-separated: schedule, message, auto, manual'),
        click.option('--repeat-type', type=click.Choice(REPEAT_TYPES),
                     help='Schedule repeat type (e.g. days for daily)'),
        click.option('--repeat-number', type=int,
                     help='Repeat every N units of --repeat-type (default: 1)'),
        click.option('--start',
                     help='Schedule start datetime, e.g. "2026-08-24 09:00:00"'),
        click.option('--end',
                     help='Schedule end datetime (default: 10 years from start)'),
        click.option('--timeout', type=int,
                     help='Per-run timeout in seconds (default: 120)'),
    ]
    for option in reversed(options):
        f = option(f)
    return f


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
@click.option('--skill', 'skill',
              help='Skill (id or name) this task runs — bound via the task-skill relationship')
@click.option('--var', 'var', multiple=True,
              help='Per-task prompt variable name=value (repeatable); fills {{name}} in the skill\'s prompts')
@click.option('--browser', 'browser', multiple=True,
              help='Per-task browser identity key=value (repeatable): profile, cdp_port, user_data_dir, headless, slot')
@_schedule_options
def add(name, description, priority, skill, var, browser, trigger, repeat_type, repeat_number, start, end, timeout):
    """
    Create a new task.

    OPERATION command - creates a new task in the database.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan tasks add -n "Daily Report" -d "Generate daily report"
      ecan tasks add -n "Weekly Cleanup" -p high --trigger schedule --repeat-type weeks --start "2026-08-24 09:00:00"
      ecan tasks add -n "Shop A QA" --skill "rt_chat_bot" --var shop_name="Shop A" --var tone=friendly
    """
    ctx = get_context()
    out = get_output()

    skill_id = _resolve_skill(ctx, out, skill) if skill else None
    task_vars = _parse_vars(out, var) if var else {}
    browser_identity = _parse_browser_identity(out, browser) if browser else {}

    task_data = {
        'name': name,
        'description': description,
        'priority': priority,
        'owner': ctx.username,
        'status': 'pending'
    }

    settings = {}
    if task_vars:
        settings['task_vars'] = task_vars
    if browser_identity:
        settings['browser_identity'] = browser_identity
    if settings:
        task_data['settings'] = settings

    if trigger is not None:
        task_data['trigger'] = _validate_trigger(out, trigger)

    schedule = _build_schedule(out, repeat_type, repeat_number, start, end, timeout)
    if schedule is not None:
        task_data['schedule'] = schedule

    try:
        result = ctx.db.task_service.add_task(task_data)
    except Exception as e:
        out.error(f"Failed to create task: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    if skill_id:
        task_id = result.get('id') or (result.get('data') or {}).get('id')
        if task_id:
            try:
                rel = ctx.db.task_service.add_skill_to_task(task_id, skill_id)
                if not (isinstance(rel, dict) and rel.get('success')):
                    out.warning(f"Task created, but skill binding failed: {(rel or {}).get('error')}")
            except Exception as e:
                out.warning(f"Task created, but skill binding failed: {e}")

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
@click.option('--var', 'var', multiple=True,
              help='Set a per-task prompt variable name=value (repeatable); merges into existing vars')
@click.option('--browser', 'browser', multiple=True,
              help='Set a per-task browser identity key=value (repeatable): profile, cdp_port, user_data_dir, headless, slot')
@_schedule_options
def update(task_id, name, description, status, priority, var, browser, trigger, repeat_type, repeat_number, start, end, timeout):
    """
    Update an existing task.

    OPERATION command - modifies task properties.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan tasks update abc123 --name "New Name"
      ecan tasks update abc123 --status completed
      ecan tasks update abc123 --var shop_name="Shop B"
      ecan tasks update abc123 --repeat-type days --repeat-number 2
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
    if trigger is not None:
        fields['trigger'] = _validate_trigger(out, trigger)

    if var or browser:
        # Merge into the task's existing settings so a partial update doesn't
        # wipe other variables, identity keys, or unrelated settings keys.
        settings = {}
        try:
            result = ctx.db.task_service.get_task_by_id(task_id)
            if result.get('success'):
                existing = (result.get('data') or {}).get('metadata')
                if isinstance(existing, dict):
                    settings = dict(existing)
        except Exception:
            pass
        if var:
            merged_vars = dict(settings.get('task_vars') or {})
            merged_vars.update(_parse_vars(out, var))
            settings['task_vars'] = merged_vars
        if browser:
            merged_identity = dict(settings.get('browser_identity') or {})
            merged_identity.update(_parse_browser_identity(out, browser))
            settings['browser_identity'] = merged_identity
        fields['settings'] = settings

    if any(v is not None for v in (repeat_type, repeat_number, start, end, timeout)):
        # Merge schedule changes into the task's existing schedule so a partial
        # update (e.g. only --repeat-number) doesn't wipe the other fields.
        existing = {}
        try:
            result = ctx.db.task_service.get_task_by_id(task_id)
            if result.get('success') and isinstance((result.get('data') or {}).get('schedule'), dict):
                existing = dict(result['data']['schedule'])
        except Exception:
            pass
        changes = {}
        if repeat_type is not None:
            changes['repeat_type'] = repeat_type
            changes['repeat_unit'] = repeat_type
        if repeat_number is not None:
            changes['repeat_number'] = repeat_number
        if start is not None:
            changes['start_date_time'] = _validate_datetime(out, start, 'start')
        if end is not None:
            changes['end_date_time'] = _validate_datetime(out, end, 'end')
        if timeout is not None:
            changes['time_out'] = timeout
        merged = {**existing, **changes}
        if not merged.get('repeat_type'):
            out.error("--repeat-type is required (task has no existing schedule to merge into)")
            raise SystemExit(1)
        fields['schedule'] = merged

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
