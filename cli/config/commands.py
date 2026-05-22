#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Management Commands - View and modify eCan.ai configuration.
"""

import click
from pathlib import Path

from ..base.context import get_context
from ..base.output import get_output
from ..base.config import get_config


@click.group()
def config():
    """
    Configuration management commands.

    QUERY commands for viewing configuration.
    OPERATION commands for modifying configuration.

    Examples:
      ecan config show
      ecan config set ECAN_LOG_LEVEL DEBUG
      ecan config reset
    """
    pass


@config.command('show')
@click.argument('key', required=False)
def show(key):
    """
    Show current configuration.

    QUERY command - displays configuration values from .env.web.

    Examples:
      ecan config show
      ecan config show ECAN_WS_PORT
    """
    ctx = get_context()
    out = get_output()

    env_file = ctx.project_root / ".env.web"
    settings = {}

    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                settings[k.strip()] = v.strip()

    for k in ['ECAN_MODE', 'ECAN_WS_HOST', 'ECAN_WS_PORT', 'ECAN_LOG_LEVEL']:
        if k in ctx.env:
            settings[k] = ctx.env[k]

    if key:
        if key in settings:
            out.print(f"{key}={settings[key]}")
        else:
            out.warning(f"Setting not found: {key}")
    else:
        out.title("Configuration")
        rows = [[k, v] for k, v in sorted(settings.items())]
        out.table("Settings", ["Key", "Value"], rows)


@config.command('set')
@click.argument('key')
@click.argument('value')
def set_value(key, value):
    """
    Set a configuration value.

    OPERATION command - updates a configuration value in .env.web.

    Examples:
      ecan config set ECAN_LOG_LEVEL DEBUG
      ecan config set ECAN_WS_PORT 9000
    """
    ctx = get_context()
    out = get_output()

    env_file = ctx.project_root / ".env.web"
    settings = {}

    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                settings[k.strip()] = v.strip()

    settings[key] = value

    with open(env_file, 'w') as f:
        for k, v in sorted(settings.items()):
            f.write(f"{k}={v}\n")

    out.success(f"Set {key}={value}")


@config.command()
@click.option('--force', '-f', is_flag=True,
              help='Skip confirmation prompt')
def reset(force):
    """
    Reset configuration to defaults.

    OPERATION command - replaces .env.web with default values.

    WARNING: This will overwrite your current configuration.

    Examples:
      ecan config reset
      ecan config reset --force
    """
    ctx = get_context()
    out = get_output()

    if not force and not out.confirm("Reset all settings to defaults?"):
        return

    env_file = ctx.project_root / ".env.web"

    defaults = """# eCan.ai Web Server Configuration
ECAN_MODE=web
ECAN_WS_HOST=0.0.0.0
ECAN_WS_PORT=8765
ECAN_LOG_LEVEL=INFO
"""

    env_file.write_text(defaults)
    out.success("Configuration reset to defaults")


@config.command()
def path():
    """
    Show configuration file paths.

    QUERY command - displays paths to configuration files.

    Examples:
      ecan config path
    """
    ctx = get_context()
    out = get_output()

    cfg = get_config()

    env_file = ctx.project_root / ".env.web"

    out.title("Configuration Paths")

    paths = {
        "Project .env": str(env_file),
        "CLI Config": str(cfg.config_file),
        "Session": str(ctx.project_root / ".ecan_session.json"),
        "PID File": str(ctx.project_root / ".ecan-web.pid"),
    }

    for name, path in paths.items():
        exists = " (exists)" if Path(path).exists() else ""
        out.print(f"  {name}: {path}{exists}")
