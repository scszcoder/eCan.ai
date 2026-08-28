#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vehicle Management Commands - CRUD operations and queries for vehicles.

Vehicles are host computers that run agents. Each vehicle can run
multiple agents in parallel.
"""

import click

from ..base.context import get_context
from ..base.output import get_output
from ..base.decorators import requires_auth


@click.group()
def vehicles():
    """
    Vehicle management commands.

    OPERATION commands for registering, updating, and removing vehicles.
    QUERY commands for listing and retrieving vehicle information.

    Vehicles are host computers that run agents. Each vehicle can
    run multiple agents and connect to a commander server.

    Examples:
      ecan vehicles list
      ecan vehicles add -n "My PC" --host 192.168.1.100
      ecan vehicles update abc123 --status offline
    """
    pass


@vehicles.command('list')
@click.option('--name', '-n',
              help='Filter vehicles by name (case-insensitive partial match)')
@click.option('--status', '-s',
              help='Filter vehicles by status (e.g., online, offline)')
@click.option('--limit', '-l', default=50, type=int,
              help='Maximum number of results (default: 50)')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'simple']),
              default='table',
              help='Output format (default: table)')
def list_vehicles(name, status, limit, format):
    """
    List all vehicles.

    QUERY command - retrieves and displays vehicles from the database.

    Examples:
      ecan vehicles list
      ecan vehicles list --status online
      ecan vehicles list --format json
    """
    ctx = get_context()
    out = get_output()

    try:
        result = ctx.db.vehicle_service.query_vehicles(name=name)
        vehicles_data = result.get('data', [])

        if status:
            vehicles_data = [v for v in vehicles_data if v.get('status') == status]
        vehicles_data = vehicles_data[:limit]

        if format == 'json':
            out.json({'vehicles': vehicles_data, 'count': len(vehicles_data)})
        elif format == 'simple':
            for vehicle in vehicles_data:
                out.print(f"{(vehicle.get('id') or '')[:12]}\t{vehicle.get('name', '')}\t{vehicle.get('status', '')}")
        else:
            rows = [
                [
                    (vehicle.get('id') or '')[:12] + '...' if len(vehicle.get('id') or '') > 12 else (vehicle.get('id') or ''),
                    vehicle.get('name', ''),
                    vehicle.get('status', 'unknown'),
                ]
                for vehicle in vehicles_data
            ]
            out.table("Vehicles", ["ID", "Name", "Status"], rows)
    except Exception as e:
        out.error(f"Failed to list vehicles: {e}")
        raise SystemExit(1)


@vehicles.command()
@click.argument('vehicle_id')
@click.option('--format', '-f', type=click.Choice(['json', 'yaml', 'simple']),
              default='json',
              help='Output format (default: json)')
def get(vehicle_id, format):
    """
    Get vehicle details by ID.

    QUERY command - retrieves full details for a specific vehicle.

    Examples:
      ecan vehicles get abc123
      ecan vehicles get abc123 --format simple
    """
    ctx = get_context()
    out = get_output()

    try:
        result = ctx.db.vehicle_service.get_vehicle_by_id(vehicle_id)
        if result.get('success'):
            if format == 'json':
                out.json(result['data'])
            else:
                out.key_value(result['data'], title=f"Vehicle: {vehicle_id}")
        else:
            out.error(f"Vehicle not found: {vehicle_id}")
            raise SystemExit(1)
    except Exception as e:
        out.error(f"Failed to get vehicle: {e}")
        raise SystemExit(1)


@vehicles.command()
@requires_auth
@click.option('--name', '-n', required=True,
              help='Vehicle name (required)')
@click.option('--host', '-h', default='',
              help='Vehicle host address (IP or hostname)')
@click.option('--description', '-d', default='',
              help='Vehicle description')
@click.option('--config', '-c', type=click.Path(exists=True),
              help='Configuration file (JSON or YAML format)')
def add(name, host, description, config):
    """
    Register a new vehicle.

    OPERATION command - registers a vehicle with the system.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan vehicles add -n "My Desktop" -h 192.168.1.100
      ecan vehicles add -n "Office Server" -h server.local -d "Main server"
    """
    ctx = get_context()
    out = get_output()

    import json as json_module
    extra_config = {}

    if config:
        with open(config) as f:
            if config.endswith('.yaml') or config.endswith('.yml'):
                import yaml
                extra_config = yaml.safe_load(f) or {}
            else:
                extra_config = json_module.load(f)

    # Server-controlled fields always win over user-supplied --config.
    vehicle_data = {
        'host': host,
        'description': description,
        **extra_config,
        'name': name,
        'owner': ctx.username,
        'status': 'offline',
    }
    vehicle_data.pop('id', None)

    try:
        result = ctx.db.vehicle_service.add_vehicle(vehicle_data)
        if result.get('success'):
            out.success("Vehicle registered!")
        else:
            out.error(f"Failed: {result.get('error')}")
            raise SystemExit(1)
    except Exception as e:
        out.error(f"Failed to register vehicle: {e}")
        raise SystemExit(1)


@vehicles.command()
@requires_auth
@click.argument('vehicle_id')
@click.option('--name', '-n',
              help='New vehicle name')
@click.option('--host', '-h',
              help='New vehicle host address')
@click.option('--description', '-d',
              help='New vehicle description')
@click.option('--status', '-s',
              help='New vehicle status (e.g., online, offline, maintenance)')
def update(vehicle_id, name, host, description, status):
    """
    Update a vehicle.

    OPERATION command - modifies vehicle properties.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan vehicles update abc123 --name "New Name"
      ecan vehicles update abc123 --status maintenance
      ecan vehicles update abc123 -n "Office PC" -h 192.168.1.200
    """
    ctx = get_context()
    out = get_output()

    fields = {}
    if name:
        fields['name'] = name
    if host:
        fields['host'] = host
    if description:
        fields['description'] = description
    if status:
        fields['status'] = status

    if not fields:
        out.warning("No fields to update")
        return

    try:
        result = ctx.db.vehicle_service.update_vehicle(vehicle_id, fields)
        if result.get('success'):
            out.success("Vehicle updated!")
        else:
            out.error(f"Failed: {result.get('error')}")
            raise SystemExit(1)
    except Exception as e:
        out.error(f"Failed to update vehicle: {e}")
        raise SystemExit(1)


@vehicles.command()
@requires_auth
@click.argument('vehicle_id')
@click.option('--force', '-f', is_flag=True,
              help='Skip confirmation prompt')
def remove(vehicle_id, force):
    """
    Unregister a vehicle.

    OPERATION command - removes a vehicle from the system.

    Requires authentication. Use 'ecan auth login' first.
    This action cannot be undone.

    Examples:
      ecan vehicles remove abc123      # With confirmation
      ecan vehicles remove abc123 -f   # Skip confirmation
    """
    ctx = get_context()
    out = get_output()

    if not force and not out.confirm(f"Unregister vehicle {vehicle_id}?"):
        return

    try:
        result = ctx.db.vehicle_service.delete_vehicle(vehicle_id)
        if result.get('success'):
            out.success("Vehicle unregistered!")
        else:
            out.error(f"Failed: {result.get('error')}")
            raise SystemExit(1)
    except Exception as e:
        out.error(f"Failed to unregister vehicle: {e}")
        raise SystemExit(1)


@vehicles.command()
@click.argument('vehicle_id')
def ping(vehicle_id):
    """
    Ping a vehicle to check connectivity.

    CONTROL command - sends a ping request to verify vehicle is reachable.

    Examples:
      ecan vehicles ping abc123

    Note:
      Vehicle ping is not yet fully implemented.
    """
    out = get_output()
    out.info(f"Pinging vehicle {vehicle_id}...")
    out.warning("Vehicle ping not yet implemented")


@vehicles.command()
@click.argument('vehicle_id')
def status(vehicle_id):
    """
    Get detailed vehicle status.

    QUERY command - retrieves current status and metrics from a vehicle.

    Examples:
      ecan vehicles status abc123

    Note:
      Vehicle status is not yet fully implemented.
    """
    out = get_output()
    out.info(f"Getting status for vehicle {vehicle_id}...")
    out.warning("Vehicle status not yet fully implemented")
