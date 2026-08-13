#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Management Commands - CRUD operations and queries for AI agents.
"""

import click

from ..base.context import get_context
from ..base.output import get_output
from ..base.config import get_config
from ..base.decorators import requires_auth


def _resolve_agent(ctx, out, identifier):
    """Resolve an id-or-name to a concrete agent id, or exit with an error."""
    from ..base.resolve import resolve_entity_id
    try:
        resolved = resolve_entity_id(ctx.db.agent_service, identifier, 'agent')
    except ValueError as e:
        out.error(str(e))
        raise SystemExit(1)
    if not resolved:
        out.error(f"No agent found matching '{identifier}'")
        raise SystemExit(1)
    return resolved


@click.group()
def agents():
    """
    Agent management commands.

    OPERATION commands for creating, updating, and deleting agents.
    QUERY commands for listing and retrieving agent information.

    Examples:
      ecan agents list
      ecan agents add -n "My Agent"
      ecan agents update abc123 --name "New Name"
    """
    pass


@agents.command('list')
@click.option('--name', '-n',
              help='Filter agents by name (case-insensitive partial match)')
@click.option('--status', '-s',
              help='Filter agents by status (e.g., active, inactive)')
@click.option('--limit', '-l', default=50, type=int,
              help='Maximum number of results to return (default: 50)')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'simple']),
              default='table',
              help='Output format (default: table)')
def list_agents(name, status, limit, format):
    """
    List all agents.

    QUERY command - retrieves and displays agents from the database.

    Examples:
      ecan agents list
      ecan agents list --limit 100
      ecan agents list --status active
      ecan agents list --format json
    """
    ctx = get_context()
    out = get_output()

    if limit < 1:
        out.error("--limit must be >= 1")
        raise SystemExit(1)
    limit = min(limit, get_config().get('max_limit', 1000))

    try:
        result = ctx.db.agent_service.query_agents(name=name)
        agents_data = result.get('data', [])

        if status:
            agents_data = [a for a in agents_data if a.get('status') == status]
        agents_data = agents_data[:limit]

        if format == 'json':
            out.json({'agents': agents_data, 'count': len(agents_data)})
        elif format == 'simple':
            for agent in agents_data:
                out.print(f"{(agent.get('id') or '')}\t{agent.get('name', '')}\t{agent.get('status', '')}")
        else:
            rows = [
                [
                    (agent.get('id') or '')[:12] + '...' if len(agent.get('id') or '') > 12 else (agent.get('id') or ''),
                    agent.get('name', ''),
                    agent.get('status', 'unknown'),
                ]
                for agent in agents_data
            ]
            out.table("Agents", ["ID", "Name", "Status"], rows)
    except Exception as e:
        out.error(f"Failed to list agents: {e}")
        raise SystemExit(1)


@agents.command()
@click.argument('agent_id')
@click.option('--format', '-f', type=click.Choice(['json', 'yaml', 'simple']),
              default='json',
              help='Output format (default: json)')
def get(agent_id, format):
    """
    Get agent details by ID.

    QUERY command - retrieves full details for a specific agent.

    Examples:
      ecan agents get abc123
      ecan agents get abc123 --format simple
    """
    ctx = get_context()
    out = get_output()

    agent_id = _resolve_agent(ctx, out, agent_id)

    try:
        result = ctx.db.agent_service.get_agent_by_id(agent_id)
        if result.get('success'):
            if format == 'json':
                out.json(result['data'])
            elif format == 'yaml':
                import yaml
                out.print(yaml.safe_dump(result['data'], allow_unicode=True, sort_keys=False))
            else:
                out.key_value(result['data'], title=f"Agent: {agent_id}")
        else:
            out.error(f"Agent not found: {agent_id}")
            raise SystemExit(1)
    except Exception as e:
        out.error(f"Failed to get agent: {e}")
        raise SystemExit(1)


@agents.command()
@requires_auth
@click.option('--name', '-n', required=True,
              help='Agent name (required)')
@click.option('--description', '-d', default='',
              help='Agent description')
@click.option('--type', '-t', 'agent_type', default='custom',
              help='Agent type (default: custom)')
@click.option('--config', '-c', type=click.Path(exists=True),
              help='Configuration file (JSON or YAML format)')
def add(name, description, agent_type, config):
    """
    Create a new agent.

    OPERATION command - creates a new agent in the database.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan agents add -n "Web Scraper" -d "Scrapes web pages"
      ecan agents add -n "Data Processor" -t "data" -c config.json

    File format example (config.json):
      {
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 2000
      }
    """
    ctx = get_context()
    out = get_output()

    import json as json_module
    extra_config = {}

    if config:
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
    agent_data = {
        'description': description,
        **extra_config,
        'name': name,
        'agent_type': agent_type,
        'owner': ctx.username,
        'status': 'active',
    }
    agent_data.pop('id', None)

    try:
        result = ctx.db.agent_service.add_agent(agent_data)
    except Exception as e:
        out.error(f"Failed to create agent: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    out.success("Agent created!")
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    cloud_sync(DataType.AGENT, result.get('data') or {**agent_data, 'id': result.get('id')}, Operation.ADD)
    if get_config().get('output_format') == 'json':
        out.json(result['data'])


@agents.command()
@requires_auth
@click.argument('agent_id')
@click.option('--name', '-n',
              help='New agent name')
@click.option('--description', '-d',
              help='New agent description')
@click.option('--status', '-s',
              help='New agent status (e.g., active, inactive)')
@click.option('--config', '-c', type=click.Path(exists=True),
              help='Update configuration from file (JSON or YAML)')
def update(agent_id, name, description, status, config):
    """
    Update an existing agent.

    OPERATION command - modifies agent properties.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan agents update abc123 --name "New Name"
      ecan agents update abc123 --status inactive
      ecan agents update abc123 -n "Updated" -d "New description" -c update.json
    """
    ctx = get_context()
    out = get_output()

    agent_id = _resolve_agent(ctx, out, agent_id)

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

    # Apply --config first, then let server-controlled / CLI fields win.
    fields = dict(extra_config)
    fields.pop('id', None)
    fields.pop('owner', None)
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
        result = ctx.db.agent_service.update_agent(agent_id, fields)
    except Exception as e:
        out.error(f"Failed to update agent: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    out.success("Agent updated!")
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    cloud_sync(DataType.AGENT, result.get('data') or {'id': agent_id, **fields}, Operation.UPDATE)


@agents.command()
@requires_auth
@click.argument('agent_id')
@click.option('--force', '-f', is_flag=True,
              help='Skip confirmation prompt')
def remove(agent_id, force):
    """
    Delete an agent.

    OPERATION command - permanently removes an agent.

    Requires authentication. Use 'ecan auth login' first.
    This action cannot be undone.

    Examples:
      ecan agents remove abc123      # With confirmation
      ecan agents remove abc123 -f   # Skip confirmation
    """
    ctx = get_context()
    out = get_output()

    agent_id = _resolve_agent(ctx, out, agent_id)

    if not force and not out.confirm(f"Delete agent {agent_id}?"):
        return

    try:
        result = ctx.db.agent_service.delete_agent(agent_id)
    except Exception as e:
        out.error(f"Failed to delete agent: {e}")
        raise SystemExit(1)

    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)

    out.success("Agent deleted!")
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    cloud_sync(DataType.AGENT, {'id': agent_id}, Operation.DELETE)


@agents.command()
@requires_auth
@click.argument('agent_id')
@click.option('--task', '-t', required=True,
              help='Task description for the agent to execute')
@click.option('--async', 'async_mode', is_flag=True,
              help='Run agent asynchronously (non-blocking)')
def run(agent_id, task, async_mode):
    """
    Execute an agent with a task.

    CONTROL command - starts agent execution.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan agents run abc123 -t "Process this data"
      ecan agents run abc123 --task "Scrape prices" --async

    Note:
      Agent execution is not yet fully implemented.
    """
    ctx = get_context()
    out = get_output()

    out.info(f"Starting agent {agent_id}...")
    out.print(f"Task: {task}")

    if async_mode:
        out.info("Running in async mode...")
        out.warning("Agent execution not yet implemented")
    else:
        out.warning("Agent execution not yet implemented")
        out.print("See TODO in cli/main.py:agents_run for implementation details")


@agents.command()
@requires_auth
@click.argument('agent_id')
def stop(agent_id):
    """
    Stop a running agent.

    CONTROL command - terminates an executing agent.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan agents stop abc123

    Note:
      Agent stop is not yet fully implemented.
    """
    out = get_output()
    out.info(f"Stopping agent {agent_id}...")
    out.warning("Agent stop not yet implemented")


@agents.command()
@click.argument('agent_id', required=False)
@click.option('--watch', '-w', is_flag=True,
              help='Watch for status changes continuously')
def monitor(agent_id, watch):
    """
    Monitor agent status.

    QUERY command - displays agent status and metrics.

    Examples:
      ecan agents monitor abc123
      ecan agents monitor

    Note:
      Agent monitoring is not yet fully implemented.
    """
    out = get_output()

    if agent_id:
        out.info(f"Monitoring agent {agent_id}...")
    else:
        out.info("Monitoring all agents...")

    out.warning("Agent monitoring not yet implemented")
