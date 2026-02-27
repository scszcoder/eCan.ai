#!/usr/bin/env python3
"""
eCan.ai Command Line Interface

A comprehensive CLI for managing eCan.ai in headless/server mode.

Usage:
    python -m cli.main [COMMAND] [OPTIONS]
    python ecan_cli.py [COMMAND] [OPTIONS]
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

# Set ECAN_MODE before importing eCan modules
os.environ.setdefault('ECAN_MODE', 'web')

# Rich console for pretty output
console = Console()

# Global state
_db_service = None


# ============================================================================
# Utility Functions
# ============================================================================

def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def init_database():
    """Initialize database connection."""
    global _db_service
    if _db_service is None:
        try:
            from agent.db.services.singleton import get_db_service
            _db_service = get_db_service()
        except Exception as e:
            console.print(f"[red]Error initializing database: {e}[/red]")
            sys.exit(1)
    return _db_service


def load_session() -> Optional[dict]:
    """Load saved session from file."""
    session_file = get_project_root() / ".ecan_session.json"
    if session_file.exists():
        try:
            with open(session_file) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_session(session_data: dict):
    """Save session to file."""
    session_file = get_project_root() / ".ecan_session.json"
    with open(session_file, 'w') as f:
        json.dump(session_data, f, indent=2)


def clear_session():
    """Clear saved session."""
    session_file = get_project_root() / ".ecan_session.json"
    if session_file.exists():
        session_file.unlink()


def require_auth():
    """Check authentication and return session."""
    session = load_session()
    if not session or not session.get('username'):
        console.print("[yellow]Please login first: ecan auth login[/yellow]")
        sys.exit(1)
    return session


def print_table(title: str, columns: list, rows: list):
    """Print a formatted table."""
    table = Table(title=title, show_header=True, header_style="bold cyan")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    console.print(table)


def print_json(data: dict, title: str = None):
    """Print formatted JSON."""
    if title:
        console.print(f"\n[bold]{title}[/bold]")
    json_str = json.dumps(data, indent=2, default=str)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
    console.print(syntax)


# ============================================================================
# Main CLI Group
# ============================================================================

@click.group()
@click.version_option(version="0.1.0", prog_name="ecan")
def cli():
    """eCan.ai Command Line Interface - Manage agents, skills, tasks, and more."""
    pass


# ============================================================================
# Version & Status Commands
# ============================================================================

@cli.command()
def version():
    """Show eCan.ai version."""
    try:
        version_file = get_project_root() / "VERSION"
        ver = version_file.read_text().strip() if version_file.exists() else "unknown"
    except Exception:
        ver = "unknown"
    
    console.print(Panel(
        f"[bold cyan]eCan.ai[/bold cyan] version [green]{ver}[/green]\n"
        f"CLI version [green]0.1.0[/green]",
        title="Version Info"
    ))


@cli.command()
def status():
    """Show system status."""
    console.print("\n[bold cyan]eCan.ai System Status[/bold cyan]\n")
    
    # Check database
    try:
        db = init_database()
        console.print("  [green]✓[/green] Database: Connected")
    except Exception as e:
        console.print(f"  [red]✗[/red] Database: {e}")
    
    # Check auth session
    session = load_session()
    if session and session.get('username'):
        console.print(f"  [green]✓[/green] Logged in as: {session['username']}")
    else:
        console.print("  [yellow]○[/yellow] Not logged in")
    
    # Check server status
    pid_file = get_project_root() / ".ecan-web.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if sys.platform == 'win32':
                import subprocess
                result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                       capture_output=True, text=True)
                if str(pid) in result.stdout:
                    console.print(f"  [green]✓[/green] Server: Running (PID {pid})")
                else:
                    console.print("  [yellow]○[/yellow] Server: Not running (stale PID)")
            else:
                os.kill(pid, 0)
                console.print(f"  [green]✓[/green] Server: Running (PID {pid})")
        except (ProcessLookupError, ValueError):
            console.print("  [yellow]○[/yellow] Server: Not running")
    else:
        console.print("  [yellow]○[/yellow] Server: Not running")
    
    console.print()


# ============================================================================
# Agents Commands
# ============================================================================

@cli.group()
def agents():
    """Manage agents (list, add, update, remove, run, stop)."""
    pass


@agents.command("list")
@click.option("--name", "-n", help="Filter by name")
@click.option("--status", "-s", help="Filter by status")
@click.option("--limit", "-l", default=50, help="Maximum results")
@click.option("--output", "-o", default="table", type=click.Choice(["table", "json"]))
def agents_list(name, status, limit, output):
    """List all agents."""
    db = init_database()
    
    try:
        result = db.agent_service.query_agents(name=name)
        agents_data = result.get('data', [])
        
        if status:
            agents_data = [a for a in agents_data if a.get('status') == status]
        agents_data = agents_data[:limit]
        
        if output == "json":
            print_json({"agents": agents_data, "count": len(agents_data)})
        else:
            if not agents_data:
                console.print("[yellow]No agents found.[/yellow]")
                return
            
            rows = []
            for agent in agents_data:
                aid = agent.get('id', '')
                rows.append([
                    aid[:12] + '...' if len(aid) > 12 else aid,
                    agent.get('name', ''),
                    agent.get('status', 'unknown'),
                    agent.get('owner', ''),
                ])
            print_table("Agents", ["ID", "Name", "Status", "Owner"], rows)
            console.print(f"\n[dim]Total: {len(agents_data)} agents[/dim]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@agents.command("get")
@click.argument("agent_id")
def agents_get(agent_id):
    """Get agent details by ID."""
    db = init_database()
    try:
        result = db.agent_service.get_agent_by_id(agent_id)
        if result.get('success'):
            print_json(result['data'], f"Agent: {agent_id}")
        else:
            console.print(f"[red]Agent not found: {agent_id}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@agents.command("add")
@click.option("--name", "-n", required=True, help="Agent name")
@click.option("--description", "-d", default="", help="Agent description")
@click.option("--owner", help="Owner username")
def agents_add(name, description, owner):
    """Add a new agent."""
    session = require_auth()
    db = init_database()
    
    owner = owner or session.get('username')
    agent_data = {'name': name, 'description': description, 'owner': owner, 'status': 'active'}
    
    try:
        result = db.agent_service.add_agent(agent_data)
        if result.get('success'):
            console.print(f"[green]✓ Agent created![/green]")
            print_json(result['data'], "New Agent")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@agents.command("update")
@click.argument("agent_id")
@click.option("--name", "-n", help="New name")
@click.option("--description", "-d", help="New description")
@click.option("--status", "-s", help="New status")
def agents_update(agent_id, name, description, status):
    """Update an agent."""
    require_auth()
    db = init_database()
    
    fields = {}
    if name: fields['name'] = name
    if description: fields['description'] = description
    if status: fields['status'] = status
    
    if not fields:
        console.print("[yellow]No fields to update.[/yellow]")
        return
    
    try:
        result = db.agent_service.update_agent(agent_id, fields)
        if result.get('success'):
            console.print(f"[green]✓ Agent updated![/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@agents.command("remove")
@click.argument("agent_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def agents_remove(agent_id, force):
    """Remove an agent."""
    require_auth()
    db = init_database()
    
    if not force and not click.confirm(f"Delete agent {agent_id}?"):
        return
    
    try:
        result = db.agent_service.delete_agent(agent_id)
        if result.get('success'):
            console.print(f"[green]✓ Agent deleted![/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@agents.command("run")
@click.argument("agent_id")
@click.option("--task", "-t", required=True, help="Task description")
def agents_run(agent_id, task):
    """Run an agent with a task."""
    # TODO(cli-task-execution): When implementing this, integrate:
    #   1. SleepInhibitor — acquire() on task start, release() on completion
    #      (already works headless, import from utils.sleep_inhibitor)
    #   2. PowerMonitor — needs a NativePowerBackend (no Qt available in CLI)
    #      See TODO in utils/power_monitor.py for backend design
    #   3. WakeRecoveryManager — needs a lightweight CLIContext instead of MainWindow
    #      See TODO in utils/wake_recovery.py for CLIContext design
    #   4. For scheduled tasks, also wire up the scheduler nudge on wake
    require_auth()
    console.print(f"[cyan]Starting agent {agent_id}...[/cyan]")
    console.print(f"[dim]Task: {task}[/dim]")
    console.print("[yellow]Agent execution via CLI not yet implemented.[/yellow]")


@agents.command("stop")
@click.argument("agent_id")
def agents_stop(agent_id):
    """Stop a running agent."""
    require_auth()
    console.print(f"[cyan]Stopping agent {agent_id}...[/cyan]")
    console.print("[yellow]Agent stop via CLI not yet implemented.[/yellow]")


@agents.command("monitor")
@click.argument("agent_id", required=False)
def agents_monitor(agent_id):
    """Monitor agent status."""
    console.print("[yellow]Agent monitoring via CLI not yet implemented.[/yellow]")


# ============================================================================
# Skills Commands
# ============================================================================

@cli.group()
def skills():
    """Manage skills (list, add, update, remove)."""
    pass


@skills.command("list")
@click.option("--name", "-n", help="Filter by name")
@click.option("--limit", "-l", default=50)
@click.option("--output", "-o", default="table", type=click.Choice(["table", "json"]))
def skills_list(name, limit, output):
    """List all skills."""
    db = init_database()
    try:
        result = db.skill_service.query_skills(name=name)
        skills_data = result.get('data', [])[:limit]
        
        if output == "json":
            print_json({"skills": skills_data, "count": len(skills_data)})
        else:
            if not skills_data:
                console.print("[yellow]No skills found.[/yellow]")
                return
            rows = [[s.get('id','')[:12], s.get('name',''), s.get('skill_type',''), s.get('owner','')] for s in skills_data]
            print_table("Skills", ["ID", "Name", "Type", "Owner"], rows)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@skills.command("get")
@click.argument("skill_id")
def skills_get(skill_id):
    """Get skill details."""
    db = init_database()
    try:
        result = db.skill_service.get_skill_by_id(skill_id)
        if result.get('success'):
            print_json(result['data'], f"Skill: {skill_id}")
        else:
            console.print(f"[red]Skill not found[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@skills.command("add")
@click.option("--name", "-n", required=True)
@click.option("--description", "-d", default="")
@click.option("--type", "-t", "skill_type", default="custom")
def skills_add(name, description, skill_type):
    """Add a new skill."""
    session = require_auth()
    db = init_database()
    skill_data = {'name': name, 'description': description, 'skill_type': skill_type, 
                  'owner': session.get('username'), 'status': 'active'}
    try:
        result = db.skill_service.add_skill(skill_data)
        if result.get('success'):
            console.print(f"[green]✓ Skill created![/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@skills.command("remove")
@click.argument("skill_id")
@click.option("--force", "-f", is_flag=True)
def skills_remove(skill_id, force):
    """Remove a skill."""
    require_auth()
    db = init_database()
    if not force and not click.confirm(f"Delete skill {skill_id}?"):
        return
    try:
        result = db.skill_service.delete_skill(skill_id)
        if result.get('success'):
            console.print(f"[green]✓ Skill deleted![/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ============================================================================
# Tasks Commands
# ============================================================================

@cli.group()
def tasks():
    """Manage tasks (list, add, update, remove)."""
    pass


@tasks.command("list")
@click.option("--name", "-n", help="Filter by name")
@click.option("--limit", "-l", default=50)
@click.option("--output", "-o", default="table", type=click.Choice(["table", "json"]))
def tasks_list(name, limit, output):
    """List all tasks."""
    db = init_database()
    try:
        result = db.task_service.query_tasks(name=name)
        tasks_data = result.get('data', [])[:limit]
        
        if output == "json":
            print_json({"tasks": tasks_data, "count": len(tasks_data)})
        else:
            if not tasks_data:
                console.print("[yellow]No tasks found.[/yellow]")
                return
            rows = [[t.get('id','')[:12], t.get('name',''), t.get('task_type',''), t.get('status','')] for t in tasks_data]
            print_table("Tasks", ["ID", "Name", "Type", "Status"], rows)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@tasks.command("get")
@click.argument("task_id")
def tasks_get(task_id):
    """Get task details."""
    db = init_database()
    try:
        result = db.task_service.get_task_by_id(task_id)
        if result.get('success'):
            print_json(result['data'], f"Task: {task_id}")
        else:
            console.print(f"[red]Task not found[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@tasks.command("add")
@click.option("--name", "-n", required=True)
@click.option("--description", "-d", default="")
@click.option("--type", "-t", "task_type", default="general")
def tasks_add(name, description, task_type):
    """Add a new task."""
    session = require_auth()
    db = init_database()
    task_data = {'name': name, 'description': description, 'task_type': task_type,
                 'owner': session.get('username'), 'status': 'pending'}
    try:
        result = db.task_service.add_task(task_data)
        if result.get('success'):
            console.print(f"[green]✓ Task created![/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@tasks.command("remove")
@click.argument("task_id")
@click.option("--force", "-f", is_flag=True)
def tasks_remove(task_id, force):
    """Remove a task."""
    require_auth()
    db = init_database()
    if not force and not click.confirm(f"Delete task {task_id}?"):
        return
    try:
        result = db.task_service.delete_task(task_id)
        if result.get('success'):
            console.print(f"[green]✓ Task deleted![/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ============================================================================
# Vehicles Commands
# ============================================================================

@cli.group()
def vehicles():
    """Manage vehicles (list, add, update, remove)."""
    pass


@vehicles.command("list")
@click.option("--name", "-n", help="Filter by name")
@click.option("--limit", "-l", default=50)
@click.option("--output", "-o", default="table", type=click.Choice(["table", "json"]))
def vehicles_list(name, limit, output):
    """List all vehicles."""
    db = init_database()
    try:
        result = db.vehicle_service.query_vehicles(name=name)
        vehicles_data = result.get('data', [])[:limit]
        
        if output == "json":
            print_json({"vehicles": vehicles_data, "count": len(vehicles_data)})
        else:
            if not vehicles_data:
                console.print("[yellow]No vehicles found.[/yellow]")
                return
            rows = [[v.get('id','')[:12], v.get('name',''), v.get('vehicle_type',''), v.get('status','')] for v in vehicles_data]
            print_table("Vehicles", ["ID", "Name", "Type", "Status"], rows)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@vehicles.command("get")
@click.argument("vehicle_id")
def vehicles_get(vehicle_id):
    """Get vehicle details."""
    db = init_database()
    try:
        result = db.vehicle_service.get_vehicle_by_id(vehicle_id)
        if result.get('success'):
            print_json(result['data'], f"Vehicle: {vehicle_id}")
        else:
            console.print(f"[red]Vehicle not found[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@vehicles.command("add")
@click.option("--name", "-n", required=True)
@click.option("--description", "-d", default="")
@click.option("--type", "-t", "vehicle_type", default="computer")
def vehicles_add(name, description, vehicle_type):
    """Add a new vehicle."""
    session = require_auth()
    db = init_database()
    vehicle_data = {'name': name, 'description': description, 'vehicle_type': vehicle_type,
                    'owner': session.get('username'), 'status': 'active'}
    try:
        result = db.vehicle_service.add_vehicle(vehicle_data)
        if result.get('success'):
            console.print(f"[green]✓ Vehicle created![/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@vehicles.command("remove")
@click.argument("vehicle_id")
@click.option("--force", "-f", is_flag=True)
def vehicles_remove(vehicle_id, force):
    """Remove a vehicle."""
    require_auth()
    db = init_database()
    if not force and not click.confirm(f"Delete vehicle {vehicle_id}?"):
        return
    try:
        result = db.vehicle_service.delete_vehicle(vehicle_id)
        if result.get('success'):
            console.print(f"[green]✓ Vehicle deleted![/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ============================================================================
# Tools Commands
# ============================================================================

@cli.group()
def tools():
    """Manage tools (list, get)."""
    pass


@tools.command("list")
@click.option("--limit", "-l", default=50)
def tools_list(limit):
    """List all tools."""
    console.print("[yellow]Tool listing not yet implemented.[/yellow]")


@tools.command("get")
@click.argument("tool_id")
def tools_get(tool_id):
    """Get tool details."""
    console.print("[yellow]Tool details not yet implemented.[/yellow]")


# ============================================================================
# Knowledge Commands
# ============================================================================

@cli.group()
def knowledge():
    """Manage knowledge bases (list, get)."""
    pass


@knowledge.command("list")
@click.option("--limit", "-l", default=50)
def knowledge_list(limit):
    """List all knowledge bases."""
    console.print("[yellow]Knowledge listing not yet implemented.[/yellow]")


@knowledge.command("get")
@click.argument("knowledge_id")
def knowledge_get(knowledge_id):
    """Get knowledge base details."""
    console.print("[yellow]Knowledge details not yet implemented.[/yellow]")


# ============================================================================
# Prompts Commands
# ============================================================================

@cli.group()
def prompts():
    """Manage prompts (list, get, add, remove)."""
    pass


@prompts.command("list")
@click.option("--name", "-n", help="Filter by name")
def prompts_list(name):
    """List all prompts."""
    prompts_dir = get_project_root() / "prompts"
    prompts_data = []
    
    if prompts_dir.exists():
        for ext in ['*.txt', '*.md']:
            for f in prompts_dir.glob(ext):
                if not name or name.lower() in f.stem.lower():
                    prompts_data.append({'name': f.stem, 'path': str(f), 'size': f.stat().st_size})
    
    if not prompts_data:
        console.print("[yellow]No prompts found.[/yellow]")
        return
    
    rows = [[p['name'], p['path'], f"{p['size']} bytes"] for p in prompts_data]
    print_table("Prompts", ["Name", "Path", "Size"], rows)


@prompts.command("get")
@click.argument("name")
def prompts_get(name):
    """Get prompt content."""
    prompts_dir = get_project_root() / "prompts"
    for ext in ['.txt', '.md', '']:
        prompt_file = prompts_dir / f"{name}{ext}"
        if prompt_file.exists():
            content = prompt_file.read_text()
            console.print(Panel(content, title=f"Prompt: {name}"))
            return
    console.print(f"[red]Prompt not found: {name}[/red]")


@prompts.command("add")
@click.option("--name", "-n", required=True)
@click.option("--content", "-c", help="Prompt content")
@click.option("--file", "-f", "file_path", type=click.Path(exists=True), help="Read from file")
def prompts_add(name, content, file_path):
    """Add a new prompt."""
    prompts_dir = get_project_root() / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    
    if file_path:
        content = Path(file_path).read_text()
    if not content:
        console.print("[red]Provide content via --content or --file[/red]")
        return
    
    prompt_file = prompts_dir / f"{name}.txt"
    prompt_file.write_text(content)
    console.print(f"[green]✓ Prompt '{name}' created![/green]")


@prompts.command("remove")
@click.argument("name")
@click.option("--force", "-f", is_flag=True)
def prompts_remove(name, force):
    """Remove a prompt."""
    prompts_dir = get_project_root() / "prompts"
    for ext in ['.txt', '.md', '']:
        prompt_file = prompts_dir / f"{name}{ext}"
        if prompt_file.exists():
            if not force and not click.confirm(f"Delete prompt {name}?"):
                return
            prompt_file.unlink()
            console.print(f"[green]✓ Prompt '{name}' deleted![/green]")
            return
    console.print(f"[red]Prompt not found: {name}[/red]")


# ============================================================================
# Auth Commands
# ============================================================================

@cli.group()
def auth():
    """Authentication (login, logout, signup, status)."""
    pass


@auth.command("login")
@click.option("--username", "-u", prompt=True)
@click.option("--password", "-p", prompt=True, hide_input=True)
def auth_login(username, password):
    """Login to eCan.ai."""
    console.print(f"[cyan]Logging in as {username}...[/cyan]")
    
    try:
        from auth.auth_manager import AuthManager
        auth_mgr = AuthManager()
        result = auth_mgr.login(username, password)
        
        if result.get('success'):
            save_session({'username': username, 'token': result.get('token'),
                         'logged_in_at': datetime.now().isoformat()})
            console.print(f"[green]✓ Logged in as {username}![/green]")
        else:
            console.print(f"[red]Login failed: {result.get('error', 'Unknown error')}[/red]")
    except Exception as e:
        console.print(f"[yellow]Auth service unavailable, creating local session.[/yellow]")
        save_session({'username': username, 'logged_in_at': datetime.now().isoformat()})
        console.print(f"[green]✓ Local session created for {username}![/green]")


@auth.command("logout")
def auth_logout():
    """Logout from eCan.ai."""
    session = load_session()
    if session:
        username = session.get('username', 'unknown')
        clear_session()
        console.print(f"[green]✓ Logged out from {username}![/green]")
    else:
        console.print("[yellow]Not logged in.[/yellow]")


@auth.command("status")
def auth_status():
    """Show authentication status."""
    session = load_session()
    if session and session.get('username'):
        console.print(Panel(
            f"[green]Logged in[/green]\n"
            f"Username: [cyan]{session['username']}[/cyan]\n"
            f"Since: {session.get('logged_in_at', 'unknown')}",
            title="Auth Status"
        ))
    else:
        console.print(Panel("[yellow]Not logged in[/yellow]\nUse: ecan auth login", title="Auth Status"))


@auth.command("signup")
@click.option("--username", "-u", prompt=True)
@click.option("--email", "-e", prompt=True)
@click.option("--password", "-p", prompt=True, hide_input=True)
def auth_signup(username, email, password):
    """Sign up for a new account."""
    console.print(f"[cyan]Creating account for {username}...[/cyan]")
    console.print("[yellow]Signup requires the auth service to be running.[/yellow]")


# ============================================================================
# Settings Commands
# ============================================================================

@cli.group()
def settings():
    """Manage settings (show, set, reset)."""
    pass


@settings.command("show")
@click.argument("key", required=False)
def settings_show(key):
    """Show current settings."""
    env_file = get_project_root() / ".env.web"
    settings_data = {}
    
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                settings_data[k.strip()] = v.strip()
    
    for k in ['ECAN_MODE', 'ECAN_WS_HOST', 'ECAN_WS_PORT', 'ECAN_LOG_LEVEL']:
        if k in os.environ:
            settings_data[k] = os.environ[k]
    
    if key:
        if key in settings_data:
            console.print(f"{key}={settings_data[key]}")
        else:
            console.print(f"[yellow]Setting not found: {key}[/yellow]")
    else:
        rows = [[k, v] for k, v in sorted(settings_data.items())]
        print_table("Settings", ["Key", "Value"], rows)


@settings.command("set")
@click.argument("key")
@click.argument("value")
def settings_set(key, value):
    """Set a configuration value."""
    env_file = get_project_root() / ".env.web"
    settings_data = {}
    
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                settings_data[k.strip()] = v.strip()
    
    settings_data[key] = value
    
    with open(env_file, 'w') as f:
        for k, v in sorted(settings_data.items()):
            f.write(f"{k}={v}\n")
    
    console.print(f"[green]✓ Set {key}={value}[/green]")


@settings.command("reset")
@click.option("--force", "-f", is_flag=True)
def settings_reset(force):
    """Reset settings to defaults."""
    if not force and not click.confirm("Reset all settings to defaults?"):
        return
    
    env_file = get_project_root() / ".env.web"
    default_settings = """# eCan.ai Web Server Configuration
ECAN_MODE=web
ECAN_WS_HOST=0.0.0.0
ECAN_WS_PORT=8765
ECAN_LOG_LEVEL=INFO
"""
    env_file.write_text(default_settings)
    console.print("[green]✓ Settings reset to defaults![/green]")


# ============================================================================
# Server Commands
# ============================================================================

@cli.group()
def server():
    """Server management (start, stop, status, logs)."""
    pass


@server.command("start")
@click.option("--host", "-h", default="0.0.0.0")
@click.option("--port", "-p", default=8765, type=int)
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground")
def server_start(host, port, foreground):
    """Start the eCan.ai web server."""
    console.print(f"[cyan]Starting eCan.ai server on {host}:{port}...[/cyan]")
    
    project_root = get_project_root()
    pid_file = project_root / ".ecan-web.pid"
    
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if sys.platform == 'win32':
                import subprocess
                result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
                if str(pid) in result.stdout:
                    console.print(f"[yellow]Server already running (PID {pid})[/yellow]")
                    return
            else:
                os.kill(pid, 0)
                console.print(f"[yellow]Server already running (PID {pid})[/yellow]")
                return
        except (ProcessLookupError, ValueError):
            pid_file.unlink()
    
    if foreground:
        import uvicorn
        os.environ['ECAN_MODE'] = 'web'
        os.environ['ECAN_WS_HOST'] = host
        os.environ['ECAN_WS_PORT'] = str(port)
        os.chdir(str(project_root))
        uvicorn.run("web_server:app", host=host, port=port, reload=False)
    else:
        import subprocess
        env = os.environ.copy()
        env['ECAN_MODE'] = 'web'
        env['ECAN_WS_HOST'] = host
        env['ECAN_WS_PORT'] = str(port)
        
        if sys.platform == 'win32':
            cmd = [sys.executable, '-m', 'uvicorn', 'web_server:app', '--host', host, '--port', str(port)]
            process = subprocess.Popen(cmd, cwd=str(project_root), env=env,
                                      creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pid_file.write_text(str(process.pid))
            console.print(f"[green]✓ Server started (PID {process.pid})[/green]")
        else:
            log_file = project_root / "runlogs" / "web_server.log"
            log_file.parent.mkdir(exist_ok=True)
            cmd = f"nohup {sys.executable} -m uvicorn web_server:app --host {host} --port {port} >> {log_file} 2>&1 &"
            subprocess.Popen(cmd, shell=True, cwd=str(project_root), env=env)
            import time
            time.sleep(2)
            result = subprocess.run(['pgrep', '-f', 'uvicorn web_server:app'], capture_output=True, text=True)
            if result.stdout.strip():
                pid = result.stdout.strip().split('\n')[0]
                pid_file.write_text(pid)
                console.print(f"[green]✓ Server started (PID {pid})[/green]")
        
        console.print(f"[dim]WebSocket: ws://{host}:{port}[/dim]")
        console.print(f"[dim]Health: http://{host}:{port}/health[/dim]")


@server.command("stop")
@click.option("--force", "-f", is_flag=True)
def server_stop(force):
    """Stop the eCan.ai web server."""
    pid_file = get_project_root() / ".ecan-web.pid"
    
    if not pid_file.exists():
        console.print("[yellow]Server not running[/yellow]")
        return
    
    try:
        pid = int(pid_file.read_text().strip())
        if sys.platform == 'win32':
            import subprocess
            subprocess.run(['taskkill', '/F' if force else '', '/PID', str(pid)], capture_output=True)
        else:
            import signal
            os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        pid_file.unlink()
        console.print(f"[green]✓ Server stopped (PID {pid})[/green]")
    except ProcessLookupError:
        pid_file.unlink()
        console.print("[yellow]Server was not running[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@server.command("status")
def server_status():
    """Check server status."""
    pid_file = get_project_root() / ".ecan-web.pid"
    
    if not pid_file.exists():
        console.print("[yellow]Server: Not running[/yellow]")
        return
    
    try:
        pid = int(pid_file.read_text().strip())
        if sys.platform == 'win32':
            import subprocess
            result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
            if str(pid) in result.stdout:
                console.print(f"[green]Server: Running (PID {pid})[/green]")
            else:
                console.print("[yellow]Server: Not running (stale PID)[/yellow]")
                pid_file.unlink()
        else:
            os.kill(pid, 0)
            console.print(f"[green]Server: Running (PID {pid})[/green]")
    except ProcessLookupError:
        console.print("[yellow]Server: Not running (stale PID)[/yellow]")
        pid_file.unlink()


@server.command("logs")
@click.option("--follow", "-f", is_flag=True)
@click.option("--lines", "-n", default=50)
def server_logs(follow, lines):
    """View server logs."""
    log_file = get_project_root() / "runlogs" / "web_server.log"
    
    if not log_file.exists():
        console.print("[yellow]No log file found.[/yellow]")
        return
    
    if follow:
        import subprocess
        if sys.platform == 'win32':
            subprocess.run(['powershell', '-Command', f'Get-Content -Path "{log_file}" -Wait -Tail {lines}'])
        else:
            subprocess.run(['tail', '-f', '-n', str(lines), str(log_file)])
    else:
        with open(log_file) as f:
            all_lines = f.readlines()
            for line in all_lines[-lines:]:
                console.print(line.rstrip())


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
