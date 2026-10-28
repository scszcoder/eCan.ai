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
        'owner': ctx.username,
        'status': 'active',
    }
    agent_data.pop('id', None)
    # Agents have no type column: keep a non-default type in extra_data.
    agent_data.pop('agent_type', None)
    if agent_type and agent_type != 'custom':
        extra = agent_data.get('extra_data')
        if isinstance(extra, str):
            try:
                extra = json_module.loads(extra) if extra.strip() else {}
            except ValueError:
                extra = {}
        extra = dict(extra) if isinstance(extra, dict) else {}
        extra['agent_type'] = agent_type
        agent_data['extra_data'] = json_module.dumps(extra, ensure_ascii=False)

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
@click.option('--vehicle',
              help='Assign agent to a vehicle (host) id; "this" = this machine, "none" = clear')
def update(agent_id, name, description, status, config, vehicle):
    """
    Update an existing agent.

    OPERATION command - modifies agent properties.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan agents update abc123 --name "New Name"
      ecan agents update abc123 --status inactive
      ecan agents update abc123 -n "Updated" -d "New description" -c update.json
      ecan agents update abc123 --vehicle this     # pin agent to this machine
      ecan agents update abc123 --vehicle none     # run on every host
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
    if vehicle is not None:
        v = vehicle.strip()
        if v.lower() == 'none':
            fields['vehicle_id'] = None
        elif v.lower() == 'this':
            from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
            local_id = resolve_local_vehicle_id(username=ctx.username or '')
            if not local_id:
                out.error("Could not resolve this machine's vehicle id "
                          "(try the explicit id from 'ecan vehicles list')")
                raise SystemExit(1)
            fields['vehicle_id'] = local_id
        else:
            fields['vehicle_id'] = v

    if not fields:
        out.warning("No fields to update")
        return

    from ..base.app_client import call_or_exit, edits_via_app
    if edits_via_app(ctx.username):
        # The app saves it and restarts the agent if it is running.
        call_or_exit(out, 'save_agent', {'username': ctx.username, 'agent': [{'id': agent_id, **fields}]}, timeout=120)
        out.success("Agent updated in the running app")
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

    from ..base.app_client import call_or_exit, edits_via_app
    if edits_via_app(ctx.username):
        call_or_exit(out, 'delete_agent', {'username': ctx.username, 'agent_id': agent_id}, timeout=120)
        out.success("Agent deleted in the running app (it has stopped)")
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


# ---- live commands: talk to the running app (cli/base/app_client.py) ----

def _status_rows(agents_list):
    return [[a.get('agent_id', '')[-12:], a.get('agent_name', ''), a.get('runtime_status', ''),
             'yes' if a.get('enabled') else 'no', str(a.get('active_task_count', 0))] for a in agents_list]


@agents.command()
@requires_auth
@click.argument('agent_id')
@click.option('--task', '-t', required=True,
              help='What to ask the agent (sent as a chat message)')
def run(agent_id, task):
    """
    Ask an agent to do something: sends it a chat message.

    CONTROL command - needs the running app. The reply shows up in the app's
    chat with the agent.

    Examples:
      ecan agents run abc123 -t "Summarize today's orders"
    """
    import time
    import uuid
    from ..base.app_client import call_or_exit
    ctx = get_context()
    out = get_output()
    agent_id = _resolve_agent(ctx, out, agent_id)
    try:
        found = (ctx.db.agent_service.query_agents(id=agent_id) or {}).get('data') or []
        agent_name = (found[0] if found else {}).get('name') or agent_id
    except Exception:
        agent_name = agent_id
    now_ms = int(time.time() * 1000)
    # A new chat is named after the agent (send_chat creates it on first use).
    result = call_or_exit(out, 'send_chat', {
        'chatId': f'cli-{agent_id}', 'id': uuid.uuid4().hex, 'role': 'user', 'content': task,
        'senderId': ctx.username or 'cli', 'senderName': ctx.username or 'cli',
        'receiverId': agent_id, 'receiverName': agent_name,
        'status': 'sent', 'createAt': now_ms, 'time': now_ms,
    }, timeout=60)
    out.success("Sent. The reply appears in the app's chat with this agent.")
    if isinstance(result, dict) and result.get('realChatId'):
        out.print(f"Chat: {result['realChatId']}")


def _resolve_agent_in_app(out, identifier):
    """Resolve an id-or-name against the running app's agents (its signed-in
    user's), for when the CLI itself is not logged in."""
    from ..base.app_client import call_or_exit
    rows = (call_or_exit(out, 'get_all_agents_runtime_status') or {}).get('agents') or []
    target = str(identifier).strip().lower()
    hits = [a for a in rows if a.get('agent_id') == identifier] or \
           [a for a in rows if str(a.get('agent_name') or '').strip().lower() == target]
    if len(hits) == 1:
        return hits[0]['agent_id']
    if hits:
        out.error(f"'{identifier}' matches {len(hits)} agents: "
                  f"{', '.join(a['agent_id'] for a in hits[:10])}. Use the id.")
    else:
        out.error(f"No agent found matching '{identifier}' in the running app")
    raise SystemExit(1)


@agents.command()
@click.argument('agent_id')
def stop(agent_id):
    """
    Disable an agent: it stops now (a turn in progress is cut off) and stays
    off, also after a restart, until it is enabled again in the app.

    CONTROL command - needs the running app. Without a CLI login, the agent is
    looked up among the running app's agents (the app's signed-in user).

    Examples:
      ecan agents stop abc123
      ecan agents stop "ChipCrawler1"
    """
    from ..base.app_client import call_or_exit
    ctx = get_context()
    out = get_output()
    if ctx.is_authenticated:
        agent_id = _resolve_agent(ctx, out, agent_id)
    else:
        agent_id = _resolve_agent_in_app(out, agent_id)
    result = call_or_exit(out, 'set_agent_enabled', {'agent_id': agent_id, 'enabled': False}) or {}
    out.success(f"Agent stopped and disabled ({result.get('runtime_status', 'stopped')})")


@agents.command()
@click.argument('agent_id', required=False)
@click.option('--watch', '-w', is_flag=True,
              help='Refresh every few seconds until Ctrl+C')
@click.option('--interval', default=5, type=int, help='Seconds between refreshes with --watch (default: 5)')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table',
              help='Output format (default: table)')
def monitor(agent_id, watch, interval, format):
    """
    Show what the running app's agents are doing.

    QUERY command - needs the running app.

    Examples:
      ecan agents monitor
      ecan agents monitor abc123
      ecan agents monitor --watch
    """
    import time
    from ..base.app_client import call_or_exit
    ctx = get_context()
    out = get_output()
    if agent_id:
        agent_id = _resolve_agent(ctx, out, agent_id)
    while True:
        if agent_id:
            one = dict(call_or_exit(out, 'get_agent_runtime_status', {'agent_id': agent_id}) or {})
            if not one.get('agent_name'):
                try:
                    rows_ = (ctx.db.agent_service.query_agents(id=agent_id) or {}).get('data') or []
                    one['agent_name'] = (rows_[0] if rows_ else {}).get('name') or ''
                except Exception:
                    pass
            rows = [one]
        else:
            rows = (call_or_exit(out, 'get_all_agents_runtime_status') or {}).get('agents') or []
        if format == 'json':
            out.json({'agents': rows})
        else:
            out.table("Agents", ["ID", "Name", "Status", "Enabled", "Running tasks"], _status_rows(rows))
        if not watch:
            return
        try:
            time.sleep(max(1, interval))
        except KeyboardInterrupt:
            return


@agents.command()
@click.argument('agent_id', required=False)
@click.option('--pin', type=int, help='Keep exactly this many Q&A agents answering, now (no auto-scaling)')
@click.option('--unpin', is_flag=True, help='Back to automatic sizing')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table',
              help='Output format (default: table)')
def pool(agent_id, pin, unpin, format):
    """
    A front desk's Q&A pool: who is answering, who is parked, waits.

    QUERY / CONTROL command - needs the running app. --pin lasts until
    --unpin or an app restart; for a lasting size use
    'ecan tasks update <front desk task> --pool-min N --pool-max N'.

    Examples:
      ecan agents pool                  # every pool
      ecan agents pool frontdesk-1
      ecan agents pool frontdesk-1 --pin 4
      ecan agents pool frontdesk-1 --unpin
    """
    from ..base.app_client import call_or_exit
    ctx = get_context()
    out = get_output()
    if (pin is not None or unpin) and not agent_id:
        out.error("Name the front desk agent to pin or unpin")
        raise SystemExit(1)
    if pin is not None and unpin:
        out.error("Use --pin or --unpin, not both")
        raise SystemExit(1)
    if pin is not None and pin < 1:
        out.error("--pin must be 1 or more")
        raise SystemExit(1)
    if agent_id:
        agent_id = _resolve_agent(ctx, out, agent_id)
        if pin is not None or unpin:
            ctx.require_auth()
            view = (call_or_exit(out, 'set_agent_pool_pin', {'agent_id': agent_id, 'size': None if unpin else pin})
                    or {}).get('pool')
            out.success("Pool unpinned (automatic)" if unpin else f"Pool pinned to {pin}")
        else:
            view = (call_or_exit(out, 'get_agent_pool', {'agent_id': agent_id}) or {}).get('pool')
            if not view:
                out.info("This agent has no Q&A pool (not a running front desk)")
                return
        views = {agent_id: view} if view else {}
    else:
        views = (call_or_exit(out, 'get_agent_pools') or {}).get('pools') or {}
    if format == 'json':
        out.json({'pools': views})
        return
    if not views:
        out.info("No front desk pools running")
        return
    for fd, v in views.items():
        st = v.get('settings') or {}
        size = f"pinned to {v['pinned']}" if v.get('pinned') else f"min {st.get('min')} / max {st.get('max')}"
        out.print(f"Front desk {fd}: {v.get('active_count')} answering ({size}, park after "
                  f"{st.get('idle_minutes')} idle min); wait p50 {v.get('wait_p50_s') or 0:.1f}s, "
                  f"p90 {v.get('wait_p90_s') or 0:.1f}s; {v.get('turns_last_hour', 0)} turns last hour"
                  + ("" if v.get('scaling', True) else " [scaling off]"))
        out.table("Members", ["ID", "Name", "Answering", "Running", "Load"],
                  [[m.get('id', '')[-12:], m.get('name', ''), 'yes' if m.get('active') else 'parked',
                    'yes' if m.get('running') else 'no', str(m.get('load', 0))] for m in v.get('members') or []])
