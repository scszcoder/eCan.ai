# Pending Events System

A fire-and-forget async operation tracking mechanism for long-running tool calls.

## Overview

When a tool makes an async API call (e.g., a cloud job that takes minutes), the workflow can continue without blocking. The pending events system:

1. **Registers** the async operation with a correlation ID
2. **Starts a timeout timer** as a guardrail
3. **Routes callbacks** (webhooks/SSE) back to the correct task
4. **Gates completion** - workflow waits for all pending events before marking complete

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         ManagedTask                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  pending_events: Dict[correlation_id, PendingEvent]     │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  queue: Queue (receives callbacks & timeouts)           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       TimerService                              │
│  - Manages timeout timers per correlation_id                    │
│  - Fires timeout events into task queue when timer expires      │
│  - Cancels timers when callbacks arrive                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       TaskExecutor                              │
│  - Completion gate: waits for all pending events                │
│  - Processes callback/timeout events from queue                 │
│  - Resolves pending events before marking task complete         │
└─────────────────────────────────────────────────────────────────┘
```

## Correlation ID Format

Correlation IDs are self-routing:

```
{task_id}:{uuid}
```

Example: `task-abc123:7f3d2e1a`

This allows callbacks to be routed directly to the correct task without a centralized registry.

## Key Components

### PendingEvent Model

```python
from agent.ec_tasks import PendingEvent, PendingEventStatus

# Status values
PendingEventStatus.PENDING      # Waiting for callback
PendingEventStatus.COMPLETED    # Callback received with result
PendingEventStatus.TIMED_OUT    # Timer fired before callback
PendingEventStatus.CANCELLED    # Task was cancelled
```

### TimerService

Thread-safe timer management:

```python
from agent.ec_tasks import get_timer_service, TimerService

timer_service = get_timer_service()

# Start a timer
handle = timer_service.start_timer(
    correlation_id="task-123:abc",
    task_id="task-123",
    delay_seconds=60.0,
    callback=lambda: print("Timeout!"),
)

# Cancel a timer
timer_service.cancel_timer("task-123:abc")

# Cancel all timers for a task
timer_service.cancel_all_for_task("task-123")
```

### Registration Utilities

```python
from agent.ec_tasks import (
    register_async_operation,
    resolve_async_operation,
    cancel_task_async_operations,
    generate_correlation_id,
    parse_correlation_id,
)
```

## Integration with build_node.py

The pending events system is integrated into multiple node builders in `ec_skills/build_node.py`:

| Node Type | Config Option | Default Timeout | Use Case |
|-----------|---------------|-----------------|----------|
| MCP Tool | `async_mode=True` | 60s | Fire-and-forget API calls with webhook callback |
| LLM | `enable_guardrail_timer=True` | 150s | Long-running LLM inference |
| Browser Automation | `enable_guardrail_timer=True` | 300s | Multi-step browser tasks |

### Async Mode vs Guardrail Timer

- **Async Mode** (MCP tools): Fire-and-forget pattern. Tool returns immediately, workflow continues, completion tracked via webhook callback.
- **Guardrail Timer** (LLM/Browser): Blocking operation with timeout tracking. If operation exceeds timeout, a timeout event is queued but operation continues.

### Event Processing Before Each Node

Events from the task queue (callbacks, timeouts) are processed **before each node runs** in the workflow. This is implemented in `node_builder` (`ec_skill.py`):

```
┌─────────────────────────────────────────────────────────┐
│                    Node Execution                        │
├─────────────────────────────────────────────────────────┤
│  1. Breakpoint checks                                   │
│  2. Step-once checks                                    │
│  3. ★ Process async events from queue ★                │
│     - async_callback → resolve pending event            │
│     - async_timeout → mark timed out                    │
│  4. Notify "running" status                             │
│  5. Execute node function                               │
│  6. Notify "completed" status                           │
└─────────────────────────────────────────────────────────┘
```

This ensures callbacks/timeouts are processed ASAP without waiting for the workflow to complete.

### Hybrid Timeout Configuration

Timeouts can be configured at **design-time** (node config) or overridden at **run-time** (state/tool input).

**Precedence (highest to lowest):**
1. `tool_input["_timeout"]` - per-call override (MCP tools only)
2. `state["_timeout_overrides"][node_name]` - per-node runtime override
3. `state["_timeout_overrides"]["*"]` - global runtime override
4. `config.timeout_seconds` - design-time config
5. Default (60s MCP, 150s LLM, 300s Browser)

#### Option A: State-based Override

Set timeouts dynamically before nodes run:

```python
# In a previous node or workflow setup:
state["_timeout_overrides"] = {
    "owner:skill:my_browser_node": 600,  # 10 min for specific node
    "owner:skill:my_llm_node": 300,      # 5 min for LLM
    "*": 120,                             # Global fallback
}
```

#### Option B: Tool Input Override (MCP tools)

Pass timeout directly in tool input:

```python
# In tool_input for MCP tool:
{
    "file_path": "/large/file.csv",
    "_timeout": 300  # Override for this specific call
}
```

### Enabling Guardrail Timer on LLM Nodes

```python
# In config_metadata for LLM node:
{
    "enable_guardrail_timer": True,   # Enable timeout tracking
    "timeout_seconds": 180,           # Design-time default (can be overridden at runtime)
}
```

### Enabling Guardrail Timer on Browser Automation Nodes

```python
# In config_metadata for browser automation node:
{
    "enable_guardrail_timer": True,   # Enable timeout tracking
    "timeout_seconds": 600,           # Design-time default (can be overridden at runtime)
}
```

### Enabling Async Mode on MCP Tool Nodes

Configure an MCP tool node with async mode in the skill editor:

```python
# In config_metadata for the node:
{
    "tool_name": "my_long_running_tool",
    "async_mode": True,           # Enable fire-and-forget
    "async_timeout": 120.0,       # Timeout in seconds (default 60)
}
```

Or via `inputsValues`:

```python
{
    "inputsValues": {
        "tool_name": {"content": "my_long_running_tool"},
        "async_mode": {"content": "true"},
        "async_timeout": {"content": "120"},
    }
}
```

### What Happens in Async Mode

When `async_mode=True`:

1. **Registration**: A pending event is registered with a correlation ID
2. **Injection**: The `_correlation_id` is injected into the tool input
3. **Fire**: The tool call is made (initial response captured)
4. **Forget**: Workflow continues immediately without waiting
5. **Track**: The operation is tracked in `state["_pending_async_operations"]`
6. **Gate**: At workflow end, completion gate waits for callback/timeout

```python
# State after async tool call:
{
    "tool_result": {"status": "job_started", "job_id": "123"},
    "_pending_async_operations": [
        {
            "correlation_id": "task-abc:xyz123",
            "tool_name": "my_long_running_tool",
            "node_name": "owner:skill:node",
            "initial_result": {"status": "job_started", "job_id": "123"}
        }
    ]
}
```

### MCP Tool Implementation for Async Mode

Your MCP tool should:

1. Accept `_correlation_id` in input
2. Start the async operation
3. Return immediately with job ID
4. Call webhook with `correlation_id` when done

```python
# Example MCP tool server implementation
@server.call_tool()
async def my_long_running_tool(input: dict) -> dict:
    correlation_id = input.get("_correlation_id")
    
    # Start async job
    job_id = await start_background_job(
        params=input,
        webhook_url=f"https://myserver.com/webhook?correlation_id={correlation_id}"
    )
    
    # Return immediately
    return {
        "status": "job_started",
        "job_id": job_id,
        "correlation_id": correlation_id
    }
```

## Usage Examples

### Example 1: Basic Async Tool

```python
from agent.ec_tasks import register_async_operation

async def my_cloud_job_tool(task, job_params):
    """
    Tool that starts a long-running cloud job.
    Returns immediately after job is queued.
    """
    # Register pending event and get correlation ID
    correlation_id = register_async_operation(
        task=task,
        source_node="my_cloud_job_tool",
        timeout_seconds=300  # 5 minute timeout
    )
    
    # Start the cloud job, passing correlation_id for webhook callback
    response = await cloud_api.start_job(
        params=job_params,
        webhook_url=f"https://myserver.com/webhook?correlation_id={correlation_id}"
    )
    
    # Return immediately - workflow continues
    return {
        "status": "job_started",
        "job_id": response.job_id,
        "correlation_id": correlation_id
    }
```

### Example 2: Webhook Handler

```python
from fastapi import FastAPI, Request
from agent.ec_tasks import TaskRunner

app = FastAPI()

@app.post("/webhook")
async def handle_webhook(request: Request):
    """
    Webhook endpoint that receives job completion callbacks.
    """
    data = await request.json()
    correlation_id = request.query_params.get("correlation_id")
    
    # Route callback to correct task
    task_runner: TaskRunner = get_task_runner()
    success = task_runner.route_webhook_callback(
        correlation_id=correlation_id,
        result=data.get("result"),
        error=data.get("error")
    )
    
    return {"routed": success}
```

### Example 3: SSE Event Handler

```python
from agent.ec_tasks import route_callback_to_task

async def handle_sse_event(event_data: dict, task_lookup: dict):
    """
    Handle SSE event from external service.
    """
    correlation_id = event_data.get("correlation_id")
    
    route_callback_to_task(
        correlation_id=correlation_id,
        result=event_data.get("payload"),
        error=event_data.get("error"),
        task_lookup=task_lookup
    )
```

### Example 4: Multiple Async Operations

```python
from agent.ec_tasks import register_async_operation

async def parallel_jobs_tool(task, job_list):
    """
    Tool that starts multiple parallel async jobs.
    """
    correlation_ids = []
    
    for job in job_list:
        corr_id = register_async_operation(
            task=task,
            source_node="parallel_jobs_tool",
            timeout_seconds=600
        )
        correlation_ids.append(corr_id)
        
        await cloud_api.start_job(
            params=job,
            callback_id=corr_id
        )
    
    # All jobs started - workflow continues
    # Completion gate will wait for all to finish
    return {
        "status": "all_jobs_started",
        "count": len(correlation_ids),
        "correlation_ids": correlation_ids
    }
```

### Example 5: Manual Resolution (Testing)

```python
from agent.ec_tasks import resolve_async_operation

# Manually resolve a pending event (useful for testing)
event = resolve_async_operation(
    task=task,
    correlation_id="task-123:abc",
    result={"data": "test_result"}
)

# Or resolve with error
event = resolve_async_operation(
    task=task,
    correlation_id="task-123:abc",
    error="external_service_error"
)
```

### Example 6: Checking Pending Events

```python
# Check if task has pending events
if task.has_pending_events():
    pending = task.get_pending_events()
    print(f"Waiting for {len(pending)} events")
    
    for event in pending:
        print(f"  - {event.correlation_id} from {event.source_node}")

# Get all event results (after completion)
results = task.get_all_pending_event_results()
for corr_id, result in results.items():
    print(f"{corr_id}: {result}")
```

## Completion Gate

The `TaskExecutor.finalize_run()` method includes a completion gate that:

1. Checks if task has pending events
2. Enters a wait loop polling the task queue
3. Processes `async_callback` and `async_timeout` events
4. Resolves pending events as they arrive
5. Exits when all events resolved or overall timeout reached

```python
# In executor.py
def finalize_run(self, success, step, current_checkpoint, effective_config):
    # ...
    
    # Wait for pending async events before marking complete
    if success and self.task.has_pending_events():
        self._wait_for_pending_events(timeout=300)  # 5 min max
    
    # Include results in run output
    if self.task.pending_events:
        run_result["pending_event_results"] = task.get_all_pending_event_results()
    
    # ...
```

## Cleanup on Cancellation

When a task is cancelled, all pending events and timers are cleaned up:

```python
from agent.ec_tasks import cancel_task_async_operations

# Called automatically by TaskRunner.cancel_task()
cancel_task_async_operations(task)

# This:
# 1. Cancels all timers for the task
# 2. Marks all pending events as CANCELLED
```

## Event Types

Events in the task queue:

```python
# Callback event (from webhook/SSE)
{
    "type": "async_callback",
    "correlation_id": "task-123:abc",
    "result": {...},  # Success result
    "error": None     # Or error string
}

# Timeout event (from timer)
{
    "type": "async_timeout",
    "correlation_id": "task-123:abc",
    "source_node": "my_tool"
}
```

## Testing

Run the test suite:

```bash
python -m pytest tests/test_pending_events.py -v
```

Test categories:
- `TestPendingEventModel` - PendingEvent creation and status transitions
- `TestManagedTaskPendingEvents` - Task-level pending event management
- `TestTimerService` - Timer start/cancel/fire behavior
- `TestCorrelationId` - Correlation ID generation and parsing
- `TestRegisterAsyncOperation` - Full registration flow
- `TestResolveAsyncOperation` - Resolution and timer cancellation
- `TestRouteCallbackToTask` - Callback routing
- `TestCancelTaskAsyncOperations` - Cleanup on cancellation

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_PENDING_EVENTS_TIMEOUT` | 300 | Max seconds to wait in completion gate |

## API Reference

### Registration

| Function | Description |
|----------|-------------|
| `register_async_operation(task, source_node, timeout_seconds)` | Register pending event and start timer |
| `resolve_async_operation(task, correlation_id, result, error)` | Resolve event and cancel timer |
| `cancel_task_async_operations(task)` | Cancel all pending events for task |

### Correlation IDs

| Function | Description |
|----------|-------------|
| `generate_correlation_id(task_id)` | Generate self-routing correlation ID |
| `parse_correlation_id(correlation_id)` | Extract task_id and unique part |

### Routing

| Function | Description |
|----------|-------------|
| `route_callback_to_task(correlation_id, result, error, task_lookup)` | Route callback to task queue |
| `build_callback_event(correlation_id, result, error)` | Build callback event dict |

### TaskRunner Methods

| Method | Description |
|--------|-------------|
| `route_webhook_callback(correlation_id, result, error)` | Public API for webhook handlers |

### ManagedTask Methods

| Method | Description |
|--------|-------------|
| `register_pending_event(correlation_id, source_node, timeout_seconds)` | Register event |
| `resolve_pending_event(correlation_id, result, error)` | Resolve event |
| `has_pending_events()` | Check if any pending |
| `get_pending_events()` | Get list of pending events |
| `get_all_pending_event_results()` | Get all results dict |
| `cleanup_expired_events()` | Mark expired events as timed out |
| `cancel_all_pending_events()` | Cancel all pending events |
| `clear_pending_events()` | Remove all events |
| `increment_step()` | Increment step counter, return new value |
| `is_max_steps_reached()` | Check if max_steps limit reached |
| `record_failure()` | Record consecutive failure, return count |
| `reset_failures()` | Reset consecutive failure counter |
| `is_max_failures_reached()` | Check if max_failures threshold reached |
| `get_guardrail_status()` | Get dict with step/failure tracking info |

---

## Workflow Guardrails (browser-use inspired)

These features are inspired by `browser-use`'s guardrail mechanisms for multi-step workflows.

### Max Steps Limit

Limit the number of steps a workflow can execute to prevent runaway loops.

```python
# Set max_steps when creating a task
task = ManagedTask(
    name="my_task",
    max_steps=100,  # Stop after 100 steps (default: None = unlimited)
)

# Or set it dynamically
task.max_steps = 50

# Check status
if task.is_max_steps_reached():
    print(f"Reached limit at step {task.n_steps}")
```

**Behavior:**
- Each workflow step increments `task.n_steps`
- When `n_steps >= max_steps`, workflow stops with `TaskState.COMPLETED`
- Status message indicates the limit was reached

### Hard Timeout (Cancel on Timeout)

Unlike soft guardrail timers that only track timeouts, hard timeouts actually cancel the operation.

```python
# In config_metadata for LLM node:
{
    "enable_guardrail_timer": True,  # Not needed for hard timeout
    "timeout_seconds": 60,
    "hard_timeout": True,  # Cancel operation on timeout
}

# In config_metadata for browser automation node:
{
    "timeout_seconds": 300,
    "hard_timeout": True,
}
```

**Runtime Override:**
```python
# Via state (applies to all nodes or specific node)
state["_hard_timeout_overrides"] = {
    "owner:skill:my_llm_node": True,   # Enable for specific node
    "*": False,                         # Default for all others
}

# Via tool_input (MCP tools only)
{
    "file_path": "/large/file.csv",
    "_timeout": 300,
    "_hard_timeout": True,
}
```

**Behavior:**
- Uses `asyncio.wait_for()` to enforce timeout
- Raises `TimeoutError` if operation exceeds timeout
- Records failure via `task.record_failure()`
- Soft timeout (guardrail timer) is disabled when hard timeout is enabled

### Consecutive Failure Tracking

Track consecutive failures and stop execution if threshold is reached.

```python
# Set max_failures when creating a task
task = ManagedTask(
    name="my_task",
    max_failures=3,  # Stop after 3 consecutive failures (default: 3)
)

# Check status
status = task.get_guardrail_status()
# {
#     "n_steps": 5,
#     "max_steps": None,
#     "steps_remaining": None,
#     "consecutive_failures": 1,
#     "max_failures": 3,
#     "failures_remaining": 2,
# }
```

**Behavior:**
- `task.record_failure()` is called when a node fails after exhausting retries
- `task.reset_failures()` is called when a node completes successfully
- When `consecutive_failures >= max_failures`, workflow stops with `TaskState.FAILED`
- Hard timeouts also record failures

### Comparison: Soft vs Hard Timeout

| Feature | Soft Timeout (Guardrail) | Hard Timeout |
|---------|--------------------------|--------------|
| Operation continues | Yes | No (cancelled) |
| Timer event queued | Yes | No |
| Exception raised | No | Yes (`TimeoutError`) |
| Failure recorded | No | Yes |
| Use case | Monitoring, alerts | Strict time limits |

### Configuration Summary

| Node Type | Config Key | Default | Description |
|-----------|------------|---------|-------------|
| LLM | `timeout_seconds` | 150s | Max time for LLM call |
| LLM | `hard_timeout` | false | Cancel on timeout |
| Browser | `timeout_seconds` | 300s | Max time for automation |
| Browser | `hard_timeout` | false | Cancel on timeout |
| MCP Tool | `async_timeout` | 60s | Timeout for async mode |
| Task | `max_steps` | None | Max workflow steps |
| Task | `max_failures` | 3 | Max consecutive failures |
