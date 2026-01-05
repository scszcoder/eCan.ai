# eCan.ai

AI Agent Framework for Automation - Build and run intelligent agents.

## Installation

```bash
pip install ecan-ai
```

For full functionality with LLM support:

```bash
pip install ecan-ai[full]
```

## Quick Start

```python
from ecan_ai import EcanAI

# Initialize
ecan = EcanAI(db_path="path/to/data")

# List agents
agents = ecan.agents.list()
print(f"Found {len(agents)} agents")

# Create an agent
agent = ecan.agents.create(
    name="WebScraper",
    description="Scrapes websites for data"
)
print(f"Created agent: {agent['name']}")

# Get agent by ID
agent = ecan.agents.get(agent['id'])

# Update agent
ecan.agents.update(agent['id'], description="Updated description")

# Delete agent
ecan.agents.delete(agent['id'])
```

## API Reference

### EcanAI

The main entry point for the library.

```python
from ecan_ai import EcanAI

ecan = EcanAI(db_path="path/to/data", auto_migrate=True)
```

### Agents

```python
# List all agents
agents = ecan.agents.list()
agents = ecan.agents.list(name="search", owner="user1", limit=10)

# Get agent by ID
agent = ecan.agents.get("agent_id")

# Create agent
agent = ecan.agents.create(name="MyAgent", description="...", owner="user1")

# Update agent
ecan.agents.update("agent_id", name="NewName", status="inactive")

# Delete agent
ecan.agents.delete("agent_id")
```

### Skills

```python
skills = ecan.skills.list()
skill = ecan.skills.get("skill_id")
skill = ecan.skills.create(name="MySkill", skill_type="custom")
ecan.skills.delete("skill_id")
```

### Tasks

```python
tasks = ecan.tasks.list()
task = ecan.tasks.get("task_id")
task = ecan.tasks.create(name="MyTask", task_type="general")
ecan.tasks.delete("task_id")
```

### Vehicles

```python
vehicles = ecan.vehicles.list()
vehicle = ecan.vehicles.get("vehicle_id")
vehicle = ecan.vehicles.create(name="MyVehicle", vehicle_type="computer")
ecan.vehicles.delete("vehicle_id")
```

## Advanced Usage

For advanced usage, you can access the underlying database services directly:

```python
from ecan_ai import DBAgentService, DBSkillService

# Or access via EcanAI
ecan = EcanAI(db_path="path/to/data")
db_manager = ecan.db_manager  # Access ECDBMgr directly
```

## Features

- **Agent Management**: Create, configure, and manage AI agents
- **Skill System**: Modular skills that agents can use
- **Task Execution**: Define and track tasks
- **Vehicle Support**: Deploy agents on different platforms
- **Knowledge Base**: Store and retrieve agent knowledge
- **Database Migrations**: Automatic schema migrations

## License

MIT License
