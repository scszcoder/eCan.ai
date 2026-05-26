# eCan.ai CLI Framework

## Overview

eCan.ai CLI is a modular, extensible command-line tool framework built on Click. It focuses on **operation**, **control**, and **query** functionalities for managing the eCan.ai platform. Design-time operations (like creating skills/workflows) are handled by the GUI, not the CLI.

## Architecture

```
cli/
├── __init__.py              # Package exports
├── main.py                  # Main entry point and command registration
├── base/                    # Core utilities
│   ├── __init__.py
│   ├── context.py           # CLI context management
│   ├── output.py            # Output formatting
│   ├── decorators.py        # Reusable decorators
│   └── config.py            # Configuration management
├── auth/                    # Authentication commands
├── server/                  # Server control commands
├── agents/                  # Agent operations and queries
├── skills/                  # Skill operations and queries
├── tasks/                   # Task operations and queries
├── vehicles/                # Vehicle operations and queries
├── tools/                   # Tool queries
├── knowledge/               # Knowledge base queries
├── prompts/                 # Prompt operations
├── dev/                     # Development control commands
├── data/                    # Data import/export operations
└── config/                  # Configuration commands
```

## Command Categories

### 1. Query Commands (Read-only)

Query commands retrieve and display information without modifying state.

| Command | Description |
|---------|-------------|
| `ecan status` | Show system status (DB connection, auth, server) |
| `ecan version` | Display version information |
| `ecan auth status` | Check authentication status |
| `ecan server status` | Check if server is running |
| `ecan server logs` | View server logs |
| `ecan agents list` | List all agents |
| `ecan agents get <id>` | Get agent details |
| `ecan skills list` | List all skills |
| `ecan skills get <id>` | Get skill details |
| `ecan tasks list` | List all tasks |
| `ecan tasks get <id>` | Get task details |
| `ecan vehicles list` | List all vehicles |
| `ecan vehicles get <id>` | Get vehicle details |
| `ecan tools list` | List available tools |
| `ecan knowledge list` | List knowledge bases |
| `ecan knowledge search <query>` | Search knowledge base |
| `ecan prompts list` | List prompts |
| `ecan prompts get <name>` | Get prompt content |
| `ecan config show` | Show configuration |
| `ecan config path` | Show config file paths |
| `ecan data backup list` | List available backups |

### 2. Control Commands (State-changing operations)

Control commands start, stop, or manage services/processes.

| Command | Description |
|---------|-------------|
| `ecan server start` | Start the web server |
| `ecan server stop` | Stop the web server |
| `ecan server restart` | Restart the web server |
| `ecan auth login` | Login to eCan.ai |
| `ecan auth logout` | Logout from eCan.ai |
| `ecan dev build run` | Run build process |
| `ecan dev build clean` | Clean build artifacts |
| `ecan dev test run` | Run tests |
| `ecan dev lint run` | Run linters |
| `ecan dev lint format` | Format code |
| `ecan dev db migrate` | Run database migrations |
| `ecan dev db makemigration` | Create migration |
| `ecan dev serve` | Start development server |
| `ecan dev shell` | Start interactive shell |
| `ecan config set <key> <value>` | Set configuration value |
| `ecan config reset` | Reset configuration |

### 3. Operation Commands (CRUD - Create/Update/Delete)

Operation commands create, modify, or delete resources. Most require authentication.

| Command | Description |
|---------|-------------|
| `ecan agents add` | Create a new agent |
| `ecan agents update <id>` | Update an agent |
| `ecan agents remove <id>` | Delete an agent |
| `ecan skills add` | Create a new skill |
| `ecan skills update <id>` | Update a skill |
| `ecan skills remove <id>` | Delete a skill |
| `ecan tasks add` | Create a new task |
| `ecan tasks update <id>` | Update a task |
| `ecan tasks remove <id>` | Delete a task |
| `ecan tasks execute <id>` | Execute a task immediately |
| `ecan vehicles add` | Create a new vehicle |
| `ecan vehicles update <id>` | Update a vehicle |
| `ecan vehicles remove <id>` | Delete a vehicle |
| `ecan prompts add` | Create a new prompt |
| `ecan prompts edit <name>` | Edit a prompt |
| `ecan prompts remove <name>` | Delete a prompt |
| `ecan data export all` | Export all data |
| `ecan data export entity <type>` | Export specific entity type |
| `ecan data import <file>` | Import data from file |
| `ecan data backup create` | Create a backup |
| `ecan data backup restore <file>` | Restore from backup |
| `ecan knowledge add` | Add a knowledge base |
| `ecan auth signup` | Create a new account |

## Global Options

| Option | Description |
|--------|-------------|
| `--json`, `-j` | Output results as JSON |
| `--quiet`, `-q` | Suppress non-error output |
| `--verbose`, `-V` | Enable verbose/debug output |
| `--no-color` | Disable colored output |
| `--version` | Show version information |
| `--help`, `-h` | Show help message |

## Help System

Each command provides detailed help via `-h` or `--help`:

```bash
# Global help
ecan -h

# Command group help
ecan agents -h

# Subcommand help
ecan agents add -h

# Example help output:
ecan agents add -h
Usage: ecan agents add [OPTIONS]

  Create a new agent.

  Requires authentication. Use 'ecan auth login' first.

Options:
  -n, --name TEXT     Agent name (required) [required]
  -d, --description TEXT
                      Agent description
  -t, --type TEXT     Agent type (default: custom)
  -c, --config FILE  Configuration file (JSON or YAML)
  -h, --help         Show this message and exit
```

## Base Module API

### CLIContext

Global context object providing:
- `project_root`: Project root directory
- `session`: Current session data
- `is_authenticated`: Authentication status
- `username`: Current username
- `db`: Database service (lazy-loaded)
- `config`: Configuration dictionary

```python
from cli.base.context import get_context

ctx = get_context()
if ctx.is_authenticated:
    print(ctx.username)
```

### CLIOutput

Unified output handler supporting:
- Colored ANSI output
- Table formatting
- JSON output
- Confirmation prompts

```python
from cli.base.output import get_output

out = get_output()
out.success("Operation completed")
out.table("Users", ["ID", "Name"], rows)
out.json(data)
```

### Decorators

```python
from cli.base.decorators import requires_auth, requires_db

@requires_auth
def protected_command():
    """Requires login before execution"""
    pass
```

## Usage Examples

### Query Examples

```bash
# System status
ecan status
ecan version

# List resources
ecan agents list --limit 20
ecan skills list --type custom
ecan tasks list --status pending
ecan vehicles list

# Get details
ecan agents get abc123
ecan skills get def456
ecan server logs --lines 100

# Search
ecan knowledge search "shipping policy" --limit 10
```

### Control Examples

```bash
# Server lifecycle
ecan server start --port 8765
ecan server stop
ecan server restart

# Authentication
ecan auth login -u username -p password
ecan auth logout

# Development
ecan dev build run --mode prod
ecan dev test run --coverage
ecan dev lint run --fix
ecan dev db migrate
ecan dev serve --reload
```

### Operation Examples

```bash
# Create resources
ecan agents add -n "My Agent" -d "Description"
ecan skills add -n "Web Scraper" -t "browser"
ecan tasks add -n "Daily Report" -p high --schedule "0 9 * * *"

# Update resources
ecan agents update abc123 --name "New Name"
ecan tasks update def456 --status completed

# Delete resources (with confirmation)
ecan agents remove abc123
ecan agents remove abc123 --force  # Skip confirmation

# Data management
ecan data export all -o backup.json --format json
ecan data backup create
ecan data backup restore backups/backup_20240101.json --restore
```

## Adding New Commands

### Step 1: Create Module Directory

```bash
mkdir -p cli/newmodule
```

### Step 2: Create `__init__.py`

```python
from .commands import newmodule
__all__ = ['newmodule']
```

### Step 3: Create `commands.py`

Follow the command category pattern:
- **Query** commands: Use `list`, `get` for reading data
- **Control** commands: Use `start`, `stop`, `run` for process management
- **Operation** commands: Use `add`, `update`, `remove` for CRUD

```python
import click
from ..base.context import get_context
from ..base.output import get_output

@click.group()
def newmodule():
    """New module description."""
    pass

@newmodule.command('list')
@click.option('--limit', '-l', default=50, help='Maximum number of results')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'simple']),
              default='table', help='Output format')
def list_(limit, format):
    """List all items in the new module.

    Query command - retrieves and displays information without modifying state.

    Examples:
        ecan newmodule list
        ecan newmodule list --limit 100
        ecan newmodule list --format json
    """
    pass
```

### Step 4: Register in `cli/main.py`

```python
# In _import_subcommands()
from cli.newmodule.commands import newmodule

# In return dict
'newmodule': newmodule,
```

## Best Practices

1. **Categorize correctly**: Use Query for read-only, Control for process management, Operation for CRUD
2. **Provide detailed help**: Every command and option needs a helpful description
3. **Use context managers**: Always use `get_context()` and `get_output()`
4. **Handle errors gracefully**: Use try/except with user-friendly messages
5. **Support multiple formats**: Offer `--format table|json|simple`
6. **Require auth when needed**: Use `@requires_auth` decorator for operations
7. **Confirm destructive actions**: Always prompt before delete operations
8. **Support --quiet mode**: Respect global quiet flag
9. **Exit codes**: Use `SystemExit(0)` for success, `SystemExit(1)` for errors

## Command Naming Convention

| Category | Verbs | Examples |
|----------|-------|----------|
| Query | list, get, search, show, status | `agents list`, `server status` |
| Control | start, stop, restart, run, login, logout | `server start`, `auth login` |
| Operation | add, create, update, remove, delete, import, export | `agents add`, `data export` |
