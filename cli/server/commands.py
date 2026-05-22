#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Server Management Commands - Start, stop, and monitor the web server.
"""

import os
import sys
import time
import signal
import subprocess
import click

from ..base.context import get_context
from ..base.output import get_output


@click.group()
def server():
    """
    Server lifecycle management commands.

    CONTROL commands for managing the eCan.ai web server.

    Examples:
      ecan server start
      ecan server stop
      ecan server status
      ecan server logs
    """
    pass


def _get_pid_file():
    """Get server PID file path."""
    ctx = get_context()
    return ctx.project_root / ".ecan-web.pid"


def _is_server_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        if sys.platform == 'win32':
            result = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}'],
                capture_output=True, text=True
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, ValueError):
        return False


def _get_server_pid() -> int:
    """Get server PID from file."""
    pid_file = _get_pid_file()
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except (ValueError, FileNotFoundError):
            pass
    return None


@server.command()
@click.option('--host', '-h', default='0.0.0.0',
              help='Host address to bind to (default: 0.0.0.0)')
@click.option('--port', '-p', default=8765, type=int,
              help='Port number to bind to (default: 8765)')
@click.option('--foreground', '-f', is_flag=True,
              help='Run server in foreground (no daemon)')
@click.option('--reload', '-r', is_flag=True,
              help='Enable auto-reload for development')
def start(host, port, foreground, reload):
    """
    Start the eCan.ai web server.

    CONTROL command - launches the web server in background or foreground.

    Examples:
      ecan server start                     # Start on default port 8765
      ecan server start -h 127.0.0.1 -p 9000  # Custom host and port
      ecan server start -f                 # Run in foreground
      ecan server start -r                 # Start with auto-reload

    Server endpoints:
      WebSocket: ws://{host}:{port}
      Health:    http://{host}:{port}/health
      API:       http://{host}:{port}/api
    """
    ctx = get_context()
    out = get_output()
    project_root = ctx.project_root
    pid_file = _get_pid_file()

    existing_pid = _get_server_pid()
    if existing_pid and _is_server_running(existing_pid):
        out.warning(f"Server already running (PID {existing_pid})")
        return

    out.info(f"Starting eCan.ai server on {host}:{port}...")

    env = os.environ.copy()
    env['ECAN_MODE'] = 'web'
    env['ECAN_WS_HOST'] = host
    env['ECAN_WS_PORT'] = str(port)

    if foreground or reload:
        import uvicorn
        os.chdir(str(project_root))
        uvicorn.run(
            "web_server:app",
            host=host,
            port=port,
            reload=reload
        )
    else:
        if sys.platform == 'win32':
            cmd = [sys.executable, '-m', 'uvicorn', 'web_server:app',
                   '--host', host, '--port', str(port)]
            process = subprocess.Popen(
                cmd,
                cwd=str(project_root),
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            pid_file.write_text(str(process.pid))
            out.success(f"Server started (PID {process.pid})")
        else:
            log_file = project_root / "runlogs" / "web_server.log"
            log_file.parent.mkdir(exist_ok=True)

            cmd = f"nohup {sys.executable} -m uvicorn web_server:app --host {host} --port {port} >> {log_file} 2>&1 &"
            subprocess.Popen(cmd, shell=True, cwd=str(project_root), env=env)

            time.sleep(2)
            result = subprocess.run(
                ['pgrep', '-f', 'uvicorn web_server:app'],
                capture_output=True, text=True
            )
            if result.stdout.strip():
                pid = result.stdout.strip().split('\n')[0]
                pid_file.write_text(pid)
                out.success(f"Server started (PID {pid})")

    out.print()
    out.key_value({
        "WebSocket": f"ws://{host}:{port}",
        "Health": f"http://{host}:{port}/health",
        "API": f"http://{host}:{port}/api",
    })


@server.command()
@click.option('--force', '-f', is_flag=True,
              help='Force kill the server (SIGKILL instead of SIGTERM)')
def stop(force):
    """
    Stop the eCan.ai web server.

    CONTROL command - terminates the running server process.

    Examples:
      ecan server stop      # Graceful shutdown (SIGTERM)
      ecan server stop -f   # Force kill (SIGKILL)
    """
    out = get_output()
    pid_file = _get_pid_file()

    if not pid_file.exists():
        out.warning("Server not running")
        return

    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, FileNotFoundError):
        pid_file.unlink()
        out.warning("Server not running")
        return

    if not _is_server_running(pid):
        pid_file.unlink()
        out.warning("Server not running (stale PID)")
        return

    try:
        if sys.platform == 'win32':
            subprocess.run(
                ['taskkill', '/F' if force else '', '/PID', str(pid)],
                capture_output=True
            )
        else:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)

        pid_file.unlink()
        out.success(f"Server stopped (PID {pid})")
    except ProcessLookupError:
        pid_file.unlink()
        out.warning("Server was not running")
    except Exception as e:
        out.error(f"Failed to stop server: {e}")
        raise SystemExit(1)


@server.command()
def status():
    """
    Check if the server is running.

    QUERY command - displays server status and endpoint information.

    Examples:
      ecan server status
    """
    out = get_output()

    pid = _get_server_pid()
    if pid and _is_server_running(pid):
        out.success(f"Server running (PID {pid})")

        ctx = get_context()
        config = ctx.config
        host = config.get('ECAN_WS_HOST', '0.0.0.0')
        port = config.get('ECAN_WS_PORT', '8765')

        out.key_value({
            "PID": str(pid),
            "WebSocket": f"ws://{host}:{port}",
            "Status": "Running",
        })
    else:
        out.warning("Server not running")


@server.command()
@click.option('--follow', '-f', is_flag=True,
              help='Follow log output (tail -f style)')
@click.option('--lines', '-n', default=50, type=int,
              help='Number of lines to show (default: 50)')
def logs(follow, lines):
    """
    View server logs.

    QUERY command - displays recent log entries from the server log file.

    Examples:
      ecan server logs                # Show last 50 lines
      ecan server logs -n 100        # Show last 100 lines
      ecan server logs -f            # Follow log output
    """
    out = get_output()
    ctx = get_context()
    log_file = ctx.project_root / "runlogs" / "web_server.log"

    if not log_file.exists():
        out.warning("No log file found")
        return

    if follow:
        if sys.platform == 'win32':
            subprocess.run(['powershell', '-Command',
                           f'Get-Content -Path "{log_file}" -Wait -Tail {lines}'])
        else:
            subprocess.run(['tail', '-f', '-n', str(lines), str(log_file)])
    else:
        with open(log_file) as f:
            all_lines = f.readlines()
            for line in all_lines[-lines:]:
                out.print(line.rstrip())


@server.command()
def restart():
    """
    Restart the server.

    CONTROL command - stops and starts the server.

    Preserves the previous configuration (host, port) when restarting.

    Examples:
      ecan server restart
    """
    out = get_output()
    out.info("Restarting server...")

    try:
        pid_file = _get_pid_file()

        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/PID', str(pid)],
                             capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)

            time.sleep(1)
    except Exception:
        pass

    ctx = get_context()
    config = ctx.config
    start.callback(
        host=config.get('ECAN_WS_HOST', '0.0.0.0'),
        port=int(config.get('ECAN_WS_PORT', 8765)),
        foreground=False,
        reload=False
    )
