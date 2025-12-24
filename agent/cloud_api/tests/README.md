# Cloud API Tests

Unit tests for the Cloud API module that handles interactions with AWS AppSync and DynamoDB.

## Test Structure

```
tests/
├── __init__.py                 # Package init
├── conftest.py                 # Pytest fixtures and configuration
├── README.md                   # This file
├── test_agent_api.py           # Agent entity tests
├── test_skill_api.py           # Skill entity and Agent-Skill relation tests
├── test_task_api.py            # Task entity and Task-Skill relation tests
├── test_tool_api.py            # Tool entity and Skill-Tool relation tests
├── test_knowledge_api.py       # Knowledge entity and Skill-Knowledge relation tests
├── test_avatar_api.py          # Avatar Resource entity tests
├── test_vehicle_api.py         # Vehicle entity tests
├── test_organization_api.py    # Organization entity tests
├── test_graphql_builder.py     # GraphQL mutation builder tests
├── test_cloud_api_service.py   # CloudAPIService and Factory tests
└── test_constants.py           # DataType, Operation, and decorator tests
```

## Running Tests

### Run all tests
```bash
cd C:\Users\songc\PycharmProjects\eCan.ai
pytest agent/cloud_api/tests/ -v
```

### Run specific test file
```bash
pytest agent/cloud_api/tests/test_agent_api.py -v
```

### Run specific test class
```bash
pytest agent/cloud_api/tests/test_agent_api.py::TestAgentAPI -v
```

### Run specific test
```bash
pytest agent/cloud_api/tests/test_agent_api.py::TestAgentAPI::test_gen_add_agents_string -v
```

### Run with coverage
```bash
pytest agent/cloud_api/tests/ --cov=agent/cloud_api --cov-report=html -v
```

## Test Categories

### Unit Tests (Mocked)
Most tests use mocking to avoid actual cloud API calls:
- `@patch('agent.cloud_api.cloud_api.appsync_http_request')` - Mocks HTTP requests
- Fixtures in `conftest.py` provide sample data

### Integration Tests (Skipped by default)
Tests marked with `@pytest.mark.skip(reason="Integration test - requires real AWS credentials")` require actual AWS credentials and are skipped by default.

To run integration tests:
```bash
pytest agent/cloud_api/tests/ -v --run-integration
```

## Fixtures

Common fixtures defined in `conftest.py`:

| Fixture | Description |
|---------|-------------|
| `mock_session` | Mock requests.Session |
| `mock_token` | Mock auth token |
| `mock_endpoint` | Mock AppSync endpoint |
| `sample_agent` | Sample agent data |
| `sample_skill` | Sample skill data |
| `sample_task` | Sample task data |
| `sample_tool` | Sample tool data |
| `sample_knowledge` | Sample knowledge data |
| `sample_avatar_resource` | Sample avatar resource data |
| `sample_vehicle` | Sample vehicle data |
| `sample_organization` | Sample organization data |
| `sample_agent_skill_relation` | Sample agent-skill relation |
| `sample_agent_task_relation` | Sample agent-task relation |
| `sample_agent_tool_relation` | Sample agent-tool relation |
| `sample_skill_tool_relation` | Sample skill-tool relation |
| `sample_skill_knowledge_relation` | Sample skill-knowledge relation |
| `sample_task_skill_relation` | Sample task-skill relation |

## Test Coverage

Tests cover the following operations for each entity:

| Entity | ADD | UPDATE | DELETE | QUERY |
|--------|-----|--------|--------|-------|
| Agent | ✅ | ✅ | ✅ | ✅ |
| Skill | ✅ | ✅ | ✅ | ✅ |
| Task | ✅ | ✅ | ✅ | ✅ |
| Tool | ✅ | ✅ | ✅ | ✅ |
| Knowledge | ✅ | ✅ | ✅ | ✅ |
| Avatar Resource | ✅ | ✅ | ✅ | ✅ |
| Vehicle | ✅ | ✅ | - | - |
| Organization | - | - | - | ✅ |

### Relationship Tests

| Relation | ADD | UPDATE | DELETE | QUERY |
|----------|-----|--------|--------|-------|
| Agent-Skill | ✅ | ✅ | ✅ | ✅ |
| Agent-Task | ✅ | ✅ | ✅ | ✅ |
| Agent-Tool | ✅ | ✅ | ✅ | ✅ |
| Skill-Tool | ✅ | ✅ | ✅ | ✅ |
| Skill-Knowledge | ✅ | ✅ | ✅ | ✅ |
| Task-Skill | ✅ | ✅ | ✅ | ✅ |

## Adding New Tests

1. Create sample data fixture in `conftest.py`
2. Create test file `test_<entity>_api.py`
3. Add test class with test methods
4. Use `@patch` decorator to mock HTTP requests
5. Assert expected behavior

Example:
```python
@patch('agent.cloud_api.cloud_api.appsync_http_request')
def test_send_add_entity_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_entity):
    from agent.cloud_api.cloud_api import send_add_entity_to_cloud
    
    mock_request.return_value = {
        "data": {
            "addEntities": '{"success": true, "count": 1}'
        }
    }
    
    result = send_add_entity_to_cloud(mock_session, [sample_entity], mock_token, mock_endpoint)
    
    mock_request.assert_called_once()
    assert result is not None
```
