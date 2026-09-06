#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan.ai Command Line Interface

A comprehensive, modular CLI for managing eCan.ai platform.

Usage:
    python -m cli.main [COMMAND] [OPTIONS]
    python ecan_cli.py [COMMAND] [OPTIONS]

Command Categories:
    - Query: List, get, search, show (read-only operations)
    - Control: Start, stop, login, logout (process/session management)
    - Operation: Add, update, remove (create, modify, delete resources)
"""

import os
import sys
import click

os.environ.setdefault('PYTHONUTF8', '1')
os.environ.setdefault('ECAN_MODE', 'web')

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@click.group(
    context_settings=dict(
        help_option_names=['-h', '--help'],
        token_normalize_func=lambda x: x.lower(),
    )
)
@click.version_option(
    version="1.0.0",
    prog_name="ecan",
    message="%(prog)s version %(version)s"
)
@click.option('--json', '-j', 'output_json', is_flag=True,
              help='Output results as JSON format')
@click.option('--quiet', '-q', is_flag=True,
              help='Suppress non-error output (quiet mode)')
@click.option('--verbose', '-V', is_flag=True,
              help='Enable verbose/debug output')
@click.option('--no-color', is_flag=True,
              help='Disable colored output')
@click.pass_context
def cli(ctx, output_json, quiet, verbose, no_color):
    """
    eCan.ai Command Line Interface

    A comprehensive CLI for managing AI agents, skills, tasks, and more.

    Command Categories:
      QUERY     Read-only operations (list, get, search, show)
      CONTROL   Process/session management (start, stop, login, logout)
      OPERATION Create, modify, delete resources (add, update, remove)

    Examples:
      ecan status                    # QUERY: Show system status
      ecan agents list               # QUERY: List all agents
      ecan server start              # CONTROL: Start the web server
      ecan agents add -n "My Agent"  # OPERATION: Create a new agent
    """
    ctx.ensure_object(dict)
    ctx.obj['output_json'] = output_json
    ctx.obj['quiet'] = quiet
    ctx.obj['verbose'] = verbose
    ctx.obj['no_color'] = no_color

    from cli.base.output import get_output, OutputLevel
    level = OutputLevel.QUIET if quiet else OutputLevel.NORMAL
    if verbose:
        level = OutputLevel.VERBOSE

    get_output(
        level=level,
        no_color=no_color or not sys.stdout.isatty()
    )


@cli.command()
def version():
    """
    Show version information.

    QUERY command - displays version details without modifying state.

    Examples:
      ecan version
      ecan --version
    """
    from cli.base.context import get_context
    from cli.base.output import get_output

    ctx = get_context()
    out = get_output()

    ver = ctx.get_version()

    out.title("eCan.ai")
    out.key_value({
        "Version": ver,
        "CLI Version": "1.0.0",
        "Python": sys.version.split()[0],
    })


@cli.command()
def status():
    """
    Show system status.

    QUERY command - displays current system state including:
    - Database connection status
    - Authentication status
    - Server running status

    Examples:
      ecan status
    """
    from cli.base.context import get_context
    from cli.base.output import get_output

    ctx = get_context()
    out = get_output()

    out.title("System Status")

    try:
        _ = ctx.db
        out.success("Database: Connected")
    except Exception as e:
        out.error(f"Database: {e}")

    if ctx.is_authenticated:
        out.success(f"Logged in as: {ctx.username}")
    else:
        out.warning("Not logged in")

    pid_file = ctx.project_root / ".ecan-web.pid"
    if pid_file.exists():
        try:
            import subprocess
            pid = int(pid_file.read_text().strip())
            if sys.platform == 'win32':
                try:
                    result = subprocess.run(
                        ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                        capture_output=True, text=True
                    )
                    running = f'"{pid}"' in result.stdout
                except FileNotFoundError:
                    running = False
                if running:
                    out.success(f"Server: Running (PID {pid})")
                else:
                    out.warning("Server: Not running (stale PID)")
            else:
                os.kill(pid, 0)
                out.success(f"Server: Running (PID {pid})")
        except PermissionError:
            # POSIX: process owned by another user -> exists, so it IS running.
            out.success(f"Server: Running (PID {pid})")
        except (ProcessLookupError, ValueError):
            out.warning("Server: Not running")
    else:
        out.warning("Server: Not running")


@cli.command()
def doctor():
    """
    Run system diagnostics.

    QUERY command - performs comprehensive system checks:
    - Python version compatibility
    - Required directories existence
    - Configuration file presence
    - Required packages installation

    Examples:
      ecan doctor
    """
    from cli.base.output import get_output
    from cli.base.context import get_context

    out = get_output()
    ctx = get_context()

    out.title("System Diagnostics")

    if sys.version_info >= (3, 9):
        out.success(f"Python: {sys.version.split()[0]}")
    else:
        out.error(f"Python {sys.version.split()[0]} (requires 3.9+)")

    required_dirs = ['cli', 'agent', 'auth', 'web_server.py']
    for d in required_dirs:
        path = ctx.project_root / d
        if path.exists():
            out.success(f"Directory: {d}")
        else:
            out.error(f"Directory: {d} (not found)")

    env_file = ctx.project_root / ".env.web"
    if env_file.exists():
        out.success("Configuration: .env.web exists")
    else:
        out.warning("Configuration: .env.web not found")

    required_packages = ['click', 'rich']
    for pkg in required_packages:
        try:
            __import__(pkg)
            out.success(f"Package: {pkg}")
        except ImportError:
            out.error(f"Package: {pkg} (not installed)")


def _import_subcommands():
    """Import and register all command modules."""
    from cli.auth.commands import auth
    from cli.server.commands import server
    from cli.agents.commands import agents
    from cli.skills.commands import skills
    from cli.tasks.commands import tasks
    from cli.vehicles.commands import vehicles
    from cli.tools.commands import tools
    from cli.knowledge.commands import knowledge
    from cli.prompts.commands import prompts
    from cli.dev.commands import dev
    from cli.data.commands import data
    from cli.config.commands import config
    from cli.deploy.commands import deploy
    from cli.apikey.commands import apikey
    from cli.organizations.commands import org
    from cli.avatars.commands import avatar

    return {
        'auth': auth,
        'server': server,
        'agents': agents,
        'skills': skills,
        'tasks': tasks,
        'vehicles': vehicles,
        'tools': tools,
        'knowledge': knowledge,
        'prompts': prompts,
        'dev': dev,
        'data': data,
        'config': config,
        'deploy': deploy,
        'apikey': apikey,
        'org': org,
        'avatar': avatar,
    }


_subcommands = _import_subcommands()

for name, cmd in _subcommands.items():
    cli.add_command(cmd, name=name)


@cli.command('completion')
@click.argument('shell', type=click.Choice(['bash', 'zsh', 'fish', 'powershell']))
def completion(shell):
    """
    Generate shell completion script.

    QUERY command - generates and displays shell completion code.

    Examples:
      eval "$(ecan completion bash)"
      eval "$(ecan completion zsh)"
    """
    import os

    if shell == 'bash':
        script = f"""
# ecan completion for bash
eval "$(_ECAN_COMPLETE=bash ecan)"
"""
    elif shell == 'zsh':
        script = f"""
# ecan completion for zsh
eval "$(_ECAN_COMPLETE=zsh ecan)"
"""
    elif shell == 'fish':
        script = f"""
# ecan completion for fish
eval (env _ECAN_COMPLETE=fish_source ecan)
"""
    else:
        script = f"""
# ecan completion for powershell
Invoke-Expression "$(_ECAN_COMPLETE=powershell ecan)"
"""

    click.echo(script)


def main():
    """Main entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        from cli.base.output import get_output
        out = get_output()
        out.error(f"Fatal error: {e}")
        if '--verbose' in sys.argv or '-V' in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
