# Token Usage Tracking Implementation Guide

## Overview

This document describes the comprehensive token usage tracking system implemented across eCan.ai to monitor and aggregate LLM token consumption from all sources.

## Architecture

### Database Schema

**Table: `token_usage`**

| Column | Type | Description |
|--------|------|-------------|
| id | String (UUID) | Primary key |
| source_type | String | Source type: `skill_llm_node`, `skill_browser_node`, `mcp_rag`, `mcp_image_gen`, `mcp_video_gen`, `skill_editor` |
| source_id | String | Source identifier (skill_id, task_id, etc.) |
| source_name | String | Human-readable source name |
| user_email | String | User email for attribution |
| session_id | String | Session ID if applicable |
| vendor | String | LLM vendor: `openai`, `anthropic`, `azure`, `deepseek`, `ollama`, etc. |
| model | String | Model name: `gpt-4`, `claude-3-opus`, etc. |
| input_tokens | Integer | Input/prompt tokens |
| output_tokens | Integer | Output/completion tokens |
| total_tokens | Integer | Total tokens (input + output) |
| cost_usd | Float | Calculated cost in USD |
| usage_timestamp | DateTime | When the tokens were used |
| node_type | String | For skills: node type (`llm`, `browser_automation`) |
| operation | String | Operation type: `embedding`, `re-ranking`, `generation`, `chat`, etc. |
| created_at | DateTime | Record creation timestamp |
| updated_at | DateTime | Record update timestamp |

**Indexes:**
- `idx_token_usage_timestamp` on `usage_timestamp`
- `idx_token_usage_user` on `user_email`
- `idx_token_usage_source` on `source_type`, `source_id`
- `idx_token_usage_model` on `vendor`, `model`
- `idx_token_usage_month` on `usage_timestamp` (for monthly aggregation)

### Components

1. **Database Model** (`agent/db/models/token_usage_model.py`)
   - SQLAlchemy model for token_usage table
   - Inherits from BaseModel for common functionality

2. **Database Service** (`agent/db/services/db_token_usage_service.py`)
   - `record_usage()` - Record a single token usage entry
   - `get_monthly_usage()` - Get aggregated usage for a month
   - `get_usage_by_source()` - Get usage grouped by source type
   - `get_usage_by_model()` - Get usage grouped by model
   - `get_recent_usage()` - Get recent usage records

3. **Token Tracker** (`agent/ec_skills/token_tracker.py`)
   - Singleton class for recording token usage
   - `record_llm_usage()` - Record from LangChain responses
   - `record_mcp_usage()` - Record from MCP tool metadata
   - Automatic cost calculation based on vendor/model pricing

4. **IPC Handler** (`gui/ipc/w2p_handlers/llm_token_usage_handler.py`)
   - `llm.getMonthlyTokenUsage` - Frontend API for monthly stats
   - Queries real database data via token_usage_service

## Token Collection Points

### 1. Skills - LLM Nodes

**Location:** `agent/ec_skills/build_node.py`

**Implementation needed:**
```python
from agent.ec_skills.token_tracker import token_tracker

# After LLM call in LLM node execution
response = llm.invoke(messages)

# Record token usage
token_tracker.record_llm_usage(
    response=response,
    source_type="skill_llm_node",
    source_id=skill_id,
    source_name=skill_name,
    user_email=user_email,
    node_type="llm"
)
```

### 2. Skills - Browser Automation Nodes

**Location:** `agent/ec_skills/build_node.py` (browser_automation node)

**Implementation needed:**
```python
from agent.ec_skills.token_tracker import token_tracker

# After browser-use agent execution
result = await agent.run(task)

# Extract token usage from result metadata
if hasattr(result, 'usage_metadata') or hasattr(result, 'response_metadata'):
    token_tracker.record_llm_usage(
        response=result,
        source_type="skill_browser_node",
        source_id=skill_id,
        source_name=skill_name,
        user_email=user_email,
        node_type="browser_automation"
    )
```

### 3. MCP Tools - RAG (Embedding & Re-ranking)

**Location:** `agent/ec_skills/rag/local_rag_mcp.py`

**Implementation needed:**
```python
from agent.ec_skills.token_tracker import token_tracker

# After embedding or re-ranking operation
metadata = {
    "token_usage": {
        "vendor": "openai",
        "model": "text-embedding-3-small",
        "in_tokens": embedding_token_count,
        "out_tokens": 0,
        "cost": calculated_cost
    }
}

token_tracker.record_mcp_usage(
    metadata=metadata,
    source_type="mcp_rag",
    operation="embedding",  # or "re-ranking"
    user_email=user_email
)
```

### 4. MCP Tools - Image/Video Generation

**Location:** MCP tool implementations that call image/video generation APIs

**Implementation needed:**
```python
from agent.ec_skills.token_tracker import token_tracker

# After API call returns with token usage in metadata
response_metadata = {
    "token_usage": {
        "vendor": api_vendor,
        "model": model_name,
        "in_tokens": prompt_tokens,
        "out_tokens": 0,
        "cost": api_cost
    }
}

token_tracker.record_mcp_usage(
    metadata=response_metadata,
    source_type="mcp_image_gen",  # or "mcp_video_gen"
    operation="generation",
    user_email=user_email
)
```

### 5. Skill Editor Agent Usage

**Location:** `agent/skill_editor/` (various agent files)

**Implementation needed:**
```python
from agent.ec_skills.token_tracker import token_tracker

# After each LLM call in skill editor agents
response = llm.invoke(messages)

token_tracker.record_llm_usage(
    response=response,
    source_type="skill_editor",
    source_id=session_id,
    source_name="skill_editor_agent",
    user_email=user_email,
    operation="code_generation"  # or "validation", "planning", etc.
)
```

**API Endpoint:** `get_skill_editor_agent_usage()`
- Should aggregate token usage for skill editor sessions
- Return format matches metadata structure

## Frontend Integration

**Component:** `gui_v2/src/components/TokenUsage/TokenUsageDisplay.tsx`

Already implemented:
- Calls `ipcApi.getMonthlyTokenUsage()` every 5 minutes
- Displays input/output/total tokens
- Toggles between token count and USD cost display
- Green LED-style display with 3-circle token icon

## Cost Calculation

**Pricing Table** (in `agent/ec_skills/token_tracker.py`):

```python
pricing_table = {
    'openai': {
        'gpt-4': {'input': 0.03, 'output': 0.06},
        'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
        'gpt-4o': {'input': 0.005, 'output': 0.015},
        'gpt-3.5-turbo': {'input': 0.0005, 'output': 0.0015},
        'o1-preview': {'input': 0.015, 'output': 0.06},
        'o1-mini': {'input': 0.003, 'output': 0.012},
        'text-embedding-3-small': {'input': 0.00002, 'output': 0},
        'text-embedding-3-large': {'input': 0.00013, 'output': 0},
    },
    'anthropic': {
        'claude-3-opus': {'input': 0.015, 'output': 0.075},
        'claude-3-sonnet': {'input': 0.003, 'output': 0.015},
        'claude-3-haiku': {'input': 0.00025, 'output': 0.00125},
    },
    'deepseek': {
        'deepseek-chat': {'input': 0.00014, 'output': 0.00028},
        'deepseek-coder': {'input': 0.00014, 'output': 0.00028},
    },
    'google': {
        'gemini-pro': {'input': 0.00025, 'output': 0.0005},
        'gemini-1.5-pro': {'input': 0.00125, 'output': 0.005},
    },
    'default': {'input': 0.01, 'output': 0.02}
}
```

## Implementation Checklist

### ✅ Completed
- [x] Database model (`token_usage_model.py`)
- [x] Database service (`db_token_usage_service.py`)
- [x] Token tracker utility (`token_tracker.py`)
- [x] ECDBMgr integration (service initialization)
- [x] IPC handler update (real database queries)
- [x] Frontend display component

### 🔲 TODO - Token Collection Implementation

- [ ] **LLM Nodes** - Add token tracking in `build_node.py` after LLM invocations
- [ ] **Browser Automation Nodes** - Add token tracking after browser-use agent runs
- [ ] **RAG Embedding** - Add token tracking in embedding operations
- [ ] **RAG Re-ranking** - Add token tracking in re-ranking operations
- [ ] **Image Generation** - Add token tracking in image gen API calls
- [ ] **Video Generation** - Add token tracking in video gen API calls
- [ ] **Skill Editor** - Add token tracking in all skill editor agent LLM calls
- [ ] **Skill Editor API** - Implement `get_skill_editor_agent_usage()` endpoint

### 🔲 TODO - Database Migration

- [ ] Create migration script to add `token_usage` table to existing databases
- [ ] Test migration on development database
- [ ] Document migration process

## Testing

### Manual Testing Steps

1. **Database Initialization**
   ```python
   from agent.db import ECDBMgr
   db_mgr = ECDBMgr()
   db_mgr.initialize()
   # Verify token_usage table exists
   ```

2. **Record Test Usage**
   ```python
   from agent.ec_skills.token_tracker import token_tracker
   from langchain_openai import ChatOpenAI
   
   llm = ChatOpenAI(model="gpt-4")
   response = llm.invoke("Hello, world!")
   
   token_tracker.record_llm_usage(
       response=response,
       source_type="test",
       user_email="test@example.com"
   )
   ```

3. **Query Usage**
   ```python
   from app_context import AppContext
   ec_db_mgr = AppContext.get_ec_db_mgr()
   usage = ec_db_mgr.token_usage_service.get_monthly_usage(2026, 3)
   print(usage)
   ```

4. **Frontend Display**
   - Login to application
   - Check token display in header (right side, next to bell icon)
   - Verify numbers update after LLM usage
   - Test toggle between token count and USD display

## Maintenance

### Adding New Models

Update pricing table in `agent/ec_skills/token_tracker.py`:
```python
pricing_table['vendor_name']['model_name'] = {
    'input': price_per_1k_tokens,
    'output': price_per_1k_tokens
}
```

### Monitoring

Query recent usage:
```python
service = ec_db_mgr.token_usage_service
recent = service.get_recent_usage(limit=100)
for usage in recent:
    print(f"{usage.source_type}: {usage.total_tokens} tokens, ${usage.cost_usd}")
```

Query by source:
```python
from datetime import datetime, timedelta
end = datetime.utcnow()
start = end - timedelta(days=30)
by_source = service.get_usage_by_source(start, end)
```

Query by model:
```python
by_model = service.get_usage_by_model(start, end)
```

## Notes

- All timestamps are stored in UTC
- Token counts are integers, costs are floats
- User email is optional but recommended for multi-user tracking
- Source ID/name help trace usage back to specific skills/tasks
- Operation field helps distinguish between different use cases (embedding vs generation)
