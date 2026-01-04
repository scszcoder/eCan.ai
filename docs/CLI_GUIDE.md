# eCan.ai Command Line Interface (CLI) Guide

The eCan.ai CLI provides a comprehensive command-line interface for managing eCan.ai in headless/server mode. This is ideal for server deployments without a GUI.

## Installation

The CLI is included with eCan.ai. No additional installation is required.

## Quick Start

```bash
# Show help
python ecan_cli.py --help

# Show version
python ecan_cli.py version

# Check system status
python ecan_cli.py status

# Login
python ecan_cli.py auth login -u your_username -p your_password
```

## Command Reference

### Global Commands

| Command | Description |
|---------|-------------|
| `version` | Show eCan.ai and CLI version |
| `status` | Show system status (database, auth, server) |
| `--help` | Show help for any command |
| `--version` | Show version |

### Authentication (`auth`)

```bash
# Login (interactive)
python ecan_cli.py auth login

# Login with credentials
python ecan_cli.py auth login -u username -p password

# Check login status
python ecan_cli.py auth status

# Logout
python ecan_cli.py auth logout

# Sign up for new account
python ecan_cli.py auth signup -u username -e email@example.com -p password
```

### Agents (`agents`)

```bash
# List all agents
python ecan_cli.py agents list

# List with filters
python ecan_cli.py agents list --name "search term" --status active --limit 20

# Output as JSON
python ecan_cli.py agents list --output json

# Get agent details
python ecan_cli.py agents get <agent_id>

# Add new agent
python ecan_cli.py agents add --name "My Agent" --description "Agent description"

# Update agent
python ecan_cli.py agents update <agent_id> --name "New Name" --status inactive

# Remove agent
python ecan_cli.py agents remove <agent_id>
python ecan_cli.py agents remove <agent_id> --force  # Skip confirmation

# Run agent with task
python ecan_cli.py agents run <agent_id> --task "Do something"

# Stop running agent
python ecan_cli.py agents stop <agent_id>

# Monitor agent
python ecan_cli.py agents monitor <agent_id>
```

### Skills (`skills`)

```bash
# List skills
python ecan_cli.py skills list
python ecan_cli.py skills list --name "search" --limit 10 --output json

# Get skill details
python ecan_cli.py skills get <skill_id>

# Add skill
python ecan_cli.py skills add --name "My Skill" --description "Description" --type custom

# Remove skill
python ecan_cli.py skills remove <skill_id> --force
```

### Tasks (`tasks`)

```bash
# List tasks
python ecan_cli.py tasks list
python ecan_cli.py tasks list --name "search" --output json

# Get task details
python ecan_cli.py tasks get <task_id>

# Add task
python ecan_cli.py tasks add --name "My Task" --description "Description" --type general

# Remove task
python ecan_cli.py tasks remove <task_id> --force
```

### Vehicles (`vehicles`)

```bash
# List vehicles
python ecan_cli.py vehicles list
python ecan_cli.py vehicles list --name "search" --output json

# Get vehicle details
python ecan_cli.py vehicles get <vehicle_id>

# Add vehicle
python ecan_cli.py vehicles add --name "My Vehicle" --description "Description" --type computer

# Remove vehicle
python ecan_cli.py vehicles remove <vehicle_id> --force
```

### Tools (`tools`)

```bash
# List tools
python ecan_cli.py tools list

# Get tool details
python ecan_cli.py tools get <tool_id>
```

### Knowledge (`knowledge`)

```bash
# List knowledge bases
python ecan_cli.py knowledge list

# Get knowledge base details
python ecan_cli.py knowledge get <knowledge_id>
```

### Prompts (`prompts`)

```bash
# List prompts
python ecan_cli.py prompts list
python ecan_cli.py prompts list --name "search"

# Get prompt content
python ecan_cli.py prompts get <prompt_name>

# Add prompt from content
python ecan_cli.py prompts add --name "my_prompt" --content "Prompt text here"

# Add prompt from file
python ecan_cli.py prompts add --name "my_prompt" --file /path/to/prompt.txt

# Remove prompt
python ecan_cli.py prompts remove <prompt_name> --force
```

### Settings (`settings`)

```bash
# Show all settings
python ecan_cli.py settings show

# Show specific setting
python ecan_cli.py settings show ECAN_WS_PORT

# Set a value
python ecan_cli.py settings set ECAN_LOG_LEVEL DEBUG

# Reset to defaults
python ecan_cli.py settings reset --force
```

### Server (`server`)

```bash
# Start server (background)
python ecan_cli.py server start

# Start with custom host/port
python ecan_cli.py server start --host 0.0.0.0 --port 8080

# Start in foreground (for debugging)
python ecan_cli.py server start --foreground

# Check server status
python ecan_cli.py server status

# Stop server
python ecan_cli.py server stop
python ecan_cli.py server stop --force  # Force kill

# View logs
python ecan_cli.py server logs
python ecan_cli.py server logs --lines 100
python ecan_cli.py server logs --follow  # Tail logs
```

## Output Formats

Most list commands support different output formats:

- `--output table` (default): Pretty-printed table
- `--output json`: JSON format for scripting

Example:
```bash
python ecan_cli.py agents list --output json | jq '.agents[0].name'
```

## Environment Variables

The CLI respects the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `ECAN_MODE` | Operation mode (`web` for headless) | `web` |
| `ECAN_WS_HOST` | WebSocket server host | `0.0.0.0` |
| `ECAN_WS_PORT` | WebSocket server port | `8765` |
| `ECAN_LOG_LEVEL` | Logging level | `INFO` |

## Session Management

The CLI stores session data in `.ecan_session.json` in the project root. This file contains:
- Username
- Authentication token (if available)
- Login timestamp

To clear the session, use `python ecan_cli.py auth logout`.

## Examples

### Complete Workflow

```bash
# 1. Login
python ecan_cli.py auth login -u admin -p password

# 2. Start server
python ecan_cli.py server start

# 3. Check status
python ecan_cli.py status

# 4. List agents
python ecan_cli.py agents list

# 5. Create a new agent
python ecan_cli.py agents add --name "Web Scraper" --description "Scrapes websites"

# 6. Run the agent
python ecan_cli.py agents run <agent_id> --task "Scrape example.com"

# 7. Monitor
python ecan_cli.py agents monitor <agent_id>

# 8. Stop server when done
python ecan_cli.py server stop

# 9. Logout
python ecan_cli.py auth logout
```

### Scripting Example

```bash
#!/bin/bash
# List all active agents as JSON and process with jq

python ecan_cli.py agents list --status active --output json | \
  jq -r '.agents[] | "\(.id): \(.name)"'
```

## Troubleshooting

### Database Connection Error

If you see "Error initializing database", ensure:
1. The database file exists and is accessible
2. You're running from the project root directory
3. All dependencies are installed

### Server Won't Start

1. Check if port is already in use: `netstat -an | grep 8765`
2. Check logs: `python ecan_cli.py server logs`
3. Try a different port: `python ecan_cli.py server start --port 8080`

### Authentication Issues

1. Check session status: `python ecan_cli.py auth status`
2. Clear and re-login: `python ecan_cli.py auth logout && python ecan_cli.py auth login`

## See Also

- [DEPLOYMENT_UBUNTU.md](DEPLOYMENT_UBUNTU.md) - Ubuntu server deployment guide
- [README.md](../README.md) - Main project documentation
