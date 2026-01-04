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
from ecan_ai import get_db_service

# Get database service
db = get_db_service()

# List agents
agents = db.agent_service.query_agents()
print(agents)
```

## Features

- **Agent Management**: Create, configure, and run AI agents
- **Skill System**: Modular skills that agents can use
- **Task Execution**: Run tasks with monitoring and control
- **Vehicle Support**: Deploy agents on different platforms
- **Knowledge Base**: Store and retrieve agent knowledge

## Documentation

See the [full documentation](https://docs.ecan.ai) for more details.

## License

MIT License
