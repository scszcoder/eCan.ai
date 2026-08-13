#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill Management Commands - CRUD operations and queries for AI skills.
"""

import click

from ..base.context import get_context
from ..base.output import get_output
from ..base.config import get_config
from ..base.decorators import requires_auth


def _resolve_skill(ctx, out, identifier):
    """Resolve an id-or-name to a concrete skill id, or exit with an error."""
    from types import SimpleNamespace
    from ..base.resolve import resolve_entity_id
    # resolve_entity_id dispatches non-'agent' kinds to service.query_tasks;
    # skill_service exposes the same query shape under query_skills.
    svc = SimpleNamespace(query_tasks=ctx.db.skill_service.query_skills)
    try:
        resolved = resolve_entity_id(svc, identifier, 'skill')
    except ValueError as e:
        out.error(str(e))
        raise SystemExit(1)
    if not resolved:
        out.error(f"No skill found matching '{identifier}'")
        raise SystemExit(1)
    return resolved


@click.group()
def skills():
    """
    Skill management commands.

    OPERATION commands for creating, updating, and deleting skills.
    QUERY commands for listing and retrieving skill information.

    Note: Design-time operations (creating/editing skills visually)
    should be done via the GUI, not the CLI.

    Examples:
      ecan skills list
      ecan skills add -n "My Skill"
      ecan skills update abc123 --name "New Name"
    """
    pass


@skills.command('list')
@click.option('--name', '-n',
              help='Filter skills by name (case-insensitive partial match)')
@click.option('--type', '-t',
              help='Filter skills by type (e.g., browser, data, custom)')
@click.option('--limit', '-l', default=50, type=int,
              help='Maximum number of results (default: 50)')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'simple']),
              default='table',
              help='Output format (default: table)')
def list_skills(name, type, limit, format):
    """
    List all skills.

    QUERY command - retrieves and displays skills from the database.

    Examples:
      ecan skills list
      ecan skills list --limit 100
      ecan skills list --type browser
      ecan skills list --format json
    """
    ctx = get_context()
    out = get_output()

    if limit < 1:
        out.error("--limit must be >= 1")
        raise SystemExit(1)
    limit = min(limit, get_config().get('max_limit', 1000))

    try:
        result = ctx.db.skill_service.query_skills(name=name)
        skills_data = result.get('data', [])

        if type:
            skills_data = [s for s in skills_data if s.get('skill_type') == type]
        skills_data = skills_data[:limit]

        if format == 'json':
            out.json({'skills': skills_data, 'count': len(skills_data)})
        elif format == 'simple':
            for skill in skills_data:
                out.print(f"{(skill.get('id') or '')}\t{skill.get('name', '')}\t{skill.get('status', '')}")
        else:
            rows = [
                [
                    (skill.get('id') or '')[:12] + '...' if len(skill.get('id') or '') > 12 else (skill.get('id') or ''),
                    skill.get('name', ''),
                    skill.get('status', ''),
                ]
                for skill in skills_data
            ]
            out.table("Skills", ["ID", "Name", "Status"], rows)
    except Exception as e:
        out.error(f"Failed to list skills: {e}")
        raise SystemExit(1)


@skills.command()
@click.argument('skill_id')
def get(skill_id):
    """
    Get skill details by ID.

    QUERY command - retrieves full details for a specific skill.

    Examples:
      ecan skills get abc123
    """
    ctx = get_context()
    out = get_output()

    skill_id = _resolve_skill(ctx, out, skill_id)

    try:
        result = ctx.db.skill_service.get_skill_by_id(skill_id)
        if result.get('success'):
            out.json(result['data'])
        else:
            out.error(f"Skill not found: {skill_id}")
            raise SystemExit(1)
    except Exception as e:
        out.error(f"Failed to get skill: {e}")
        raise SystemExit(1)


@skills.command()
@requires_auth
@click.option('--name', '-n', required=True,
              help='Skill name (required)')
@click.option('--description', '-d', default='',
              help='Skill description')
@click.option('--type', '-t', 'skill_type', default='custom',
              help='Skill type (default: custom)')
@click.option('--config', '-c', type=click.Path(exists=True),
              help='Configuration file (JSON or YAML format)')
def add(name, description, skill_type, config):
    """
    Create a new skill.

    OPERATION command - creates a new skill in the database.

    Requires authentication. Use 'ecan auth login' first.

    Note: For visual skill editing, use the GUI Skill Editor.

    Examples:
      ecan skills add -n "Web Scraper" -d "Scrapes web pages"
      ecan skills add -n "Data Processor" -t data -c config.json
    """
    ctx = get_context()
    out = get_output()

    extra_config = {}
    if config:
        import json as json_module
        try:
            with open(config) as f:
                if config.endswith('.yaml') or config.endswith('.yml'):
                    import yaml
                    extra_config = yaml.safe_load(f) or {}
                else:
                    extra_config = json_module.load(f)
        except Exception as e:
            out.error(f"Failed to parse config file: {e}")
            raise SystemExit(1)
        if not isinstance(extra_config, dict):
            out.error("Config file must contain a JSON/YAML object (mapping).")
            raise SystemExit(1)

    # Server-controlled fields always win over user-supplied --config.
    skill_data = {
        'description': description,
        **extra_config,
        'name': name,
        'skill_type': skill_type,
        'owner': ctx.username,
        'status': 'active',
    }
    skill_data.pop('id', None)

    try:
        result = ctx.db.skill_service.add_skill(skill_data)
    except Exception as e:
        out.error(f"Failed to create skill: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    out.success("Skill created!")
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    cloud_sync(DataType.SKILL, result.get('data') or {**skill_data, 'id': result.get('id')}, Operation.ADD)


@skills.command()
@requires_auth
@click.argument('skill_id')
@click.option('--name', '-n',
              help='New skill name')
@click.option('--description', '-d',
              help='New skill description')
@click.option('--status', '-s',
              help='New skill status (e.g., active, inactive)')
def update(skill_id, name, description, status):
    """
    Update an existing skill.

    OPERATION command - modifies skill properties.

    Requires authentication. Use 'ecan auth login' first.

    Note: For visual skill editing, use the GUI Skill Editor.

    Examples:
      ecan skills update abc123 --name "New Name"
      ecan skills update abc123 --status inactive
    """
    ctx = get_context()
    out = get_output()

    skill_id = _resolve_skill(ctx, out, skill_id)

    fields = {}
    if name:
        fields['name'] = name
    if description:
        fields['description'] = description
    if status:
        fields['status'] = status

    if not fields:
        out.warning("No fields to update")
        return

    try:
        result = ctx.db.skill_service.update_skill(skill_id, fields)
    except Exception as e:
        out.error(f"Failed to update skill: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    out.success("Skill updated!")
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    cloud_sync(DataType.SKILL, result.get('data') or {'id': skill_id, **fields}, Operation.UPDATE)


@skills.command()
@requires_auth
@click.argument('skill_id')
@click.option('--force', '-f', is_flag=True,
              help='Skip confirmation prompt')
def remove(skill_id, force):
    """
    Delete a skill.

    OPERATION command - permanently removes a skill.

    Requires authentication. Use 'ecan auth login' first.
    This action cannot be undone.

    Examples:
      ecan skills remove abc123      # With confirmation
      ecan skills remove abc123 -f   # Skip confirmation
    """
    ctx = get_context()
    out = get_output()

    skill_id = _resolve_skill(ctx, out, skill_id)

    if not force and not out.confirm(f"Delete skill {skill_id}?"):
        return

    try:
        result = ctx.db.skill_service.delete_skill(skill_id)
    except Exception as e:
        out.error(f"Failed to delete skill: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    out.success("Skill deleted!")
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    cloud_sync(DataType.SKILL, {'id': skill_id}, Operation.DELETE)
