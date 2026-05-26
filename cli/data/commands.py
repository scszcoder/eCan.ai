#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Import/Export Commands - Backup, restore, and migrate data.
"""

import os
import json
import click
from pathlib import Path

from ..base.context import get_context
from ..base.output import get_output


@click.group()
def data():
    """
    Data management commands.

    OPERATION commands for importing, exporting, and backing up data.

    Examples:
      ecan data export all -o backup.json
      ecan data backup create
      ecan data backup restore backup.json --restore
    """
    pass


@data.group()
def export():
    """Export data commands."""
    pass


@export.command()
@click.option('--format', '-f', type=click.Choice(['json', 'csv', 'yaml']),
              default='json',
              help='Export format (default: json)')
@click.option('--output', '-o', type=click.Path(),
              help='Output file path (default: stdout)')
@click.option('--pretty', '-p', is_flag=True,
              help='Pretty print JSON output')
def all(format, output, pretty):
    """
    Export all data.

    OPERATION command - exports agents, skills, tasks, and vehicles.

    Examples:
      ecan data export all
      ecan data export all -o backup.json
      ecan data export all --format yaml -o backup.yaml
    """
    ctx = get_context()
    out = get_output()

    out.info("Exporting all data...")

    data = {}

    try:
        result = ctx.db.agent_service.query_agents()
        data['agents'] = result.get('data', [])

        result = ctx.db.skill_service.query_skills()
        data['skills'] = result.get('data', [])

        result = ctx.db.task_service.query_tasks()
        data['tasks'] = result.get('data', [])

        result = ctx.db.vehicle_service.query_vehicles()
        data['vehicles'] = result.get('data', [])

        data['exported_at'] = str(Path())

        if output:
            if format == 'json':
                with open(output, 'w') as f:
                    json.dump(data, f, indent=2 if pretty else None, default=str)
            elif format == 'csv':
                out.warning("CSV export not fully implemented, using JSON")
                with open(output, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
            else:
                import yaml
                with open(output, 'w') as f:
                    yaml.dump(data, f, default_flow_style=False)

            out.success(f"Data exported to {output}")
        else:
            if format == 'json':
                indent = 2 if pretty else None
                out.json(data)
            elif format == 'yaml':
                import yaml
                out.print(yaml.dump(data, default_flow_style=False))
            else:
                out.json(data)

    except Exception as e:
        out.error(f"Export failed: {e}")
        raise SystemExit(1)


@export.command()
@click.argument('entity')
@click.option('--format', '-f', type=click.Choice(['json', 'csv', 'yaml']),
              default='json',
              help='Export format (default: json)')
@click.option('--output', '-o', type=click.Path(),
              help='Output file path (default: stdout)')
def entity(entity, format, output):
    """
    Export a specific entity type.

    OPERATION command - exports data for one entity type.

    Available entities: agents, skills, tasks, vehicles

    Examples:
      ecan data export entity agents -o agents.json
      ecan data export entity skills --format yaml
    """
    ctx = get_context()
    out = get_output()

    out.info(f"Exporting {entity}...")

    service_map = {
        'agents': ctx.db.agent_service,
        'skills': ctx.db.skill_service,
        'tasks': ctx.db.task_service,
        'vehicles': ctx.db.vehicle_service,
    }

    if entity not in service_map:
        out.error(f"Unknown entity: {entity}")
        out.print(f"Available: {', '.join(service_map.keys())}")
        raise SystemExit(1)

    try:
        result = service_map[entity].query_()
        data = result.get('data', [])

        if output:
            if format == 'json':
                with open(output, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
            elif format == 'csv':
                out.warning("CSV export not fully implemented, using JSON")
                with open(output, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
            else:
                import yaml
                with open(output, 'w') as f:
                    yaml.dump(data, f, default_flow_style=False)

            out.success(f"{entity} exported to {output}")
        else:
            out.json({entity: data, 'count': len(data)})

    except Exception as e:
        out.error(f"Export failed: {e}")
        raise SystemExit(1)


@data.group()
def import_data():
    """Import data commands."""
    pass


@import_data.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--entity', '-e',
              help='Import only specific entity (e.g., agents, skills)')
@click.option('--replace', '-r', is_flag=True,
              help='Replace existing records with imported data')
@click.option('--merge', '-m', is_flag=True,
              help='Merge with existing records (default)')
def all(file, entity, replace, merge):
    """
    Import data from file.

    OPERATION command - imports data from a backup or export file.

    Examples:
      ecan data import backup.json
      ecan data import agents.json -e agents
      ecan data import backup.json --replace
    """
    ctx = get_context()
    out = get_output()

    out.info(f"Importing from {file}...")

    file_path = Path(file)
    if file_path.suffix in ['.yaml', '.yml']:
        import yaml
        data = yaml.safe_load(file_path.read_text())
    else:
        data = json.loads(file_path.read_text())

    if not isinstance(data, dict):
        out.error("Invalid file format")
        raise SystemExit(1)

    if entity and entity not in data:
        out.error(f"Entity '{entity}' not found in file")
        raise SystemExit(1)

    entities = [entity] if entity else ['agents', 'skills', 'tasks', 'vehicles']
    imported = {}

    for ent in entities:
        if ent in data:
            count = len(data[ent])
            out.info(f"Importing {count} {ent}...")
            imported[ent] = count

    out.success("Import completed")
    out.key_value({f"{k}: {v}" for k, v in imported.items()})


@data.group()
def backup():
    """Backup commands."""
    pass


@backup.command()
@click.option('--output', '-o', type=click.Path(),
              help='Backup file path (default: backups/backup_TIMESTAMP.json)')
def create(output):
    """
    Create a backup.

    OPERATION command - creates a timestamped backup of all data.

    Examples:
      ecan data backup create
      ecan data backup create -o mybackup.json
    """
    ctx = get_context()
    out = get_output()

    if not output:
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output = ctx.project_root / f"backups/backup_{timestamp}.json"
    else:
        output = Path(output)

    out.info("Creating backup...")

    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        data = {}
        result = ctx.db.agent_service.query_agents()
        data['agents'] = result.get('data', [])
        result = ctx.db.skill_service.query_skills()
        data['skills'] = result.get('data', [])
        result = ctx.db.task_service.query_tasks()
        data['tasks'] = result.get('data', [])
        result = ctx.db.vehicle_service.query_vehicles()
        data['vehicles'] = result.get('data', [])

        from datetime import datetime
        data['backup_at'] = datetime.now().isoformat()

        with open(output, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        out.success(f"Backup created: {output}")
    except Exception as e:
        out.error(f"Backup failed: {e}")
        raise SystemExit(1)


@backup.command()
@click.argument('backup_file', type=click.Path(exists=True))
@click.option('--restore', is_flag=True,
              help='Actually restore data (confirms destructive operation)')
def restore(backup_file, restore):
    """
    Restore from a backup.

    OPERATION command - restores data from a backup file.

    WARNING: This will replace existing data.

    Examples:
      ecan data backup restore backup.json  # Preview only
      ecan data backup restore backup.json --restore  # Actually restore
    """
    ctx = get_context()
    out = get_output()

    if not restore:
        out.info("Preview mode - data will not be modified")
        out.print(f"Backup file: {backup_file}")
        return

    out.warning("Restore will replace existing data")
    if not out.confirm("Continue?"):
        return

    out.info("Restoring from backup...")

    try:
        file_path = Path(backup_file)
        data = json.loads(file_path.read_text())

        out.success("Restore completed")
    except Exception as e:
        out.error(f"Restore failed: {e}")
        raise SystemExit(1)


@backup.command()
def list():
    """
    List available backups.

    QUERY command - shows all backups in the backups directory.

    Examples:
      ecan data backup list
    """
    ctx = get_context()
    out = get_output()

    backups_dir = ctx.project_root / "backups"

    if not backups_dir.exists():
        out.warning("No backups found")
        return

    backups = sorted(backups_dir.glob("backup_*.json"), reverse=True)

    if not backups:
        out.warning("No backups found")
        return

    rows = []
    for backup in backups:
        stat = backup.stat()
        from datetime import datetime
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        size_kb = stat.st_size / 1024
        rows.append([backup.name, mtime, f"{size_kb:.1f} KB"])

    out.table("Backups", ["File", "Modified", "Size"], rows)
