# Mapping DSL (Domain-Specific Language) for Node State and Resume Payload

This document describes the declarative mapping rules used to project data from events or node outputs into LangGraph node state and Command(resume=...) payload.

## Overview

The mapping DSL system provides two levels of data mapping:

1. **Skill-Level Mapping**: Event-to-state data mapping (configured in START node)
2. **Node-Level Mapping**: State-to-state transfer mapping (configured in individual nodes)

Both levels support run_mode separation (`developing` vs `released`) for different runtime behaviors.

## Goals

- General-purpose routing from sources (Event/Node/State) to targets (state.attributes|metadata|tool_input, resume.*).
- No/low-code: simple rules with optional transforms and conflict policies.
- Backward compatible with existing `qa_form`, `notification`, `human_text` behavior.
- Support both development (debug-friendly) and released (production-optimized) modes.
- Enable agent-level event routing via `event_routing.json`.

## Sources

- `event`: normalized event envelope with fields:
  - `event.type`: human_chat | a2a | webhook | timer | other
  - `event.source`: e.g., gui:<chatId>
  - `event.tag`: identifier to match checkpoint (e.g., metadata.i_tag)
  - `event.timestamp`: optional
  - `event.data`: payload incl. `human_text`, `qa_form_to_agent|qa_form`, `notification_to_agent|notification`, `metadata`
  - `event.context`: ids like `id`, `sessionId`, `chatId`, `msgId`
- [Deprecated] `node`: current node output (no longer used in node-level mappings)
- `state`: current state (read-only for rules)

## Targets

- `state.attributes.<path>`
- `state.metadata.<path>`
- `state.tool_input.<path>`
- `resume.<key>`

## data_mapping.json Structure

Skills save their mapping rules in `data_mapping.json` alongside the skill JSON file:

```json
{
  "developing": {
    "mappings": [
      {
        "from": ["event.data.qa_form_to_agent", "event.data.qa_form"],
        "to": [
          {"target": "state.attributes.forms.qa_form"},
          {"target": "resume.qa_form_to_agent"}
        ],
        "transform": null,
        "on_conflict": "merge_deep",
        "when": "event.type in ['human_chat','a2a']"
      }
    ],
    "options": {
      "strict": false,
      "default_on_missing": null,
      "apply_order": "top_down"
    }
  },
  "released": {
    "mappings": [
      // Same as developing, but without debug metadata
    ],
    "options": {
      "strict": true,
      "default_on_missing": null,
      "apply_order": "top_down"
    }
  },
  "node_transfers": {
    "node_name_1": {
      "mappings": [
        {
          "from": ["node.result.api_response"],
          "to": [{"target": "state.tool_input.data"}],
          "transform": "parse_json"
        }
      ]
    }
  },
  "event_data_mapping": {
    "passive_command": {
      "adapt_to_state": {
        "actions": "state.attributes.passive_command_actions",
        "run_id": "state.attributes.passive_run_id",
        "step_id": "state.attributes.passive_step_id"
      }
    }
  }
}
```

### Rule Schema Fields

- `from`: list of dot paths; first non-null value is used.
- `to`: one or more targets to write the value to.
- `transform` (optional): built-ins like `to_string`, `parse_json`, `pick`, `coalesce`, `identity`.
- `on_conflict`: overwrite | skip | merge_shallow | merge_deep | append.
- `when` (optional): simple expression with access to `event`, `node`, `state`.

## run_mode System

Skills have a `run_mode` field that controls which mapping set is used at runtime:

- **`developing`**: Debug-friendly mode

  - Includes debug metadata mappings
  - `strict: false` - lenient error handling
  - Preserves `event.data.metadata` for debugging
- **`released`**: Production-optimized mode

  - Minimal metadata only
  - `strict: true` - strict validation
  - Optimized for performance

The `run_mode` is controlled by the "Released" toggle button in the skill editor UI.

## Mapping Levels

### 1. Skill-Level Mapping (START Node)

Configured in the START node editor, applies to the entire skill:

- **Event-to-State Mapping**: Maps incoming events to state fields

Example use cases:

- Map chat messages to `state.attributes.human.last_message`
- Map QA forms to `state.attributes.forms.qa_form`

### 2. Node-Level Mapping (Other Nodes)

Configured in individual node editors, applies to state-to-state transfers:

- **State-to-State Transfer**: Maps values from the current state snapshot (which already contains preceding node outputs) into the current node's state fields
- Use `state.*` for both sources and targets

Example use cases:

- Map `node.result.api_response` to `state.tool_input.data`
- Transform JSON strings to objects with `parse_json`
- Extract specific fields with `pick` transform

## Event Data Mapping (Per-Skill)

The `event_data_mapping` key in `data_mapping.json` defines how event payload fields are projected into the resuming node's LangGraph state when a pending event arrives. This is **not** event-to-task routing (which is global) — it is per-skill data projection.

### Structure

```json
{
  "event_data_mapping": {
    "<event_type>": {
      "adapt_to_state": {
        "<source_field>": "<target_state_path>",
        ...
      }
    }
  }
}
```

- **`<event_type>`**: The event type key (e.g. `"passive_command"`, `"PassiveCommandEvent"`, `"web_hook"`)
- **`adapt_to_state`**: Object mapping source field names (from the event payload) to target state paths
- Target paths can start with `state.` (which is stripped) or be direct paths

### Example

```json
{
  "event_data_mapping": {
    "passive_command": {
      "adapt_to_state": {
        "actions": "state.attributes.passive_command_actions",
        "run_id": "state.attributes.passive_run_id",
        "step_id": "state.attributes.passive_step_id"
      }
    },
    "PassiveCommandEvent": {
      "adapt_to_state": {
        "actions": "state.attributes.passive_command_actions",
        "run_id": "state.attributes.passive_run_id",
        "step_id": "state.attributes.passive_step_id"
      }
    }
  }
}
```

### Backward Compatibility

For existing skills that use the legacy `event_routing` key in `data_mapping.json`, the system will fall back to reading `event_routing` if `event_data_mapping` is not present. New skills should use `event_data_mapping`.

## Global Event-Task Routing

> **This is the agent-level routing system.** It decides *which running task* receives an incoming event. It is completely separate from per-skill data mapping and per-skill event data mapping (`event_data_mapping`).

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Incoming Event                            │
│  (human_chat, web_hook, cloud_websocket, passive_command, …)     │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│              Global Event Routing Table                          │
│         agent/agent_files/event_routing.json                     │
│  ┌──────────────┬──────────────────────────────────────────┐     │
│  │ event_type   │ routing rule                             │     │
│  ├──────────────┼──────────────────────────────────────────┤     │
│  │ human_chat   │ task_selector: name_contains:chatter     │     │
│  │ web_hook     │ routing_key: command.run_id              │     │
│  │ ws_order_upd │ match_fields: [{event→task}, …]          │     │
│  └──────────────┴──────────────────────────────────────────┘     │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Matched ManagedTask                           │
│  → resume.py applies event_data_mapping (adapt_to_state)        │
│  → LangGraph node resumes with updated state                    │
└──────────────────────────────────────────────────────────────────┘
```

### Normalized Event Envelope

Every incoming event — regardless of source (WebSocket, webhook, chat, SSE, A2A, etc.) — is normalized by `normalize_event()` in `agent/ec_tasks/resume.py` into this standardized structure **before** routing:

```json
{
  "type": "human_chat | a2a | webhook | web_hook | passive_command | cloud_websocket | web_sse | ...",
  "source": "gui:<chatId> | agent:<id> | ...",
  "tag": "<i_tag or business tag for checkpoint matching>",
  "timestamp": "...",
  "data": {
    "human_text": "the chat message text (if any)",
    "metadata": {
      "i_tag": "...",
      "mtype": "send_chat | send_task | ...",
      "params": {
        "chatId": "...",
        "msgId": "...",
        "senderId": "...",
        "senderName": "...",
        "receiverId": "...",
        "content": "...",
        "createAt": "..."
      }
    },
    "raw": "<original message if no structured data extracted>"
  },
  "context": {
    "id": "request/message id",
    "sessionId": "...",
    "chatId": "...",
    "msgId": "...",
    "senderId": "...",
    "senderName": "...",
    "run_id": "(promoted) task run ID — from top-level or nested command",
    "client_id": "(promoted) client ID",
    "task_id": "(promoted) task ID",
    "timer_id": "(promoted) timer ID"
  }
}
```

> **Promoted fields:** Common routing identifiers (`run_id`, `client_id`, `task_id`, `timer_id`) are automatically promoted into `context` from the raw incoming message (top-level or nested `command` dict). This means you can always use `context.run_id` instead of digging into `data.raw.run_id` or `data.raw.command.client_id`.

**When specifying `event_path` in match_fields (either in `event_routing.json` or in pend_event_node Routing Match Fields), always use paths relative to this normalized envelope.** For example:

| What you want to match | `event_path` |
|------------------------|-------------|
| Event type | `type` |
| Chat ID | `context.chatId` |
| Sender ID | `context.senderId` |
| Run ID | `context.run_id` |
| Client ID | `context.client_id` |
| Task ID | `context.task_id` |
| Timer ID | `context.timer_id` |
| Business tag | `tag` |
| Human text content | `data.human_text` |
| Raw metadata param | `data.metadata.params.chatId` |

### Pend Event Node — Routing Match Fields

In the skill editor, each `pend_event_node` has an optional **Routing Match Fields** section. These fields define how the runner should route incoming events of that type to the correct task at runtime.

Each match field row has:
- **Event Field** (`event_path`): Dot-path in the normalized event envelope (see above)
- **Task Field** (`task_path`): Dot-path in the task object. Supports:
  - `state.<path>` — from `task.metadata.state` (e.g. `state.account_id`)
  - `skill.<field>` — from `task.skill` attributes (e.g. `skill.id`, `skill.name`)
  - Direct fields — from task itself (e.g. `id`, `name`)
  - Can be **blank** if auto-filled at runtime (e.g. task id is injected at launch)

These match fields are saved to the flowgram JSON as `inputsValues.matchFields.content` and read by `_extract_event_types_from_skill()` at task launch time. If match fields are configured, the runner generates `match_fields`-based routing rules; otherwise it falls back to `routing_key: command.run_id`.

### Config File Location

| Priority | Path | Description |
|----------|------|-------------|
| 1 (highest) | `<user_data_home>/event_routing.json` | User-level override, written when dynamic rules are amended |
| 2 (fallback) | `agent/agent_files/event_routing.json` | Bundled default shipped with the application |

The file is loaded once at `TaskRunner.__init__` and cached in `self._global_event_routing`. Call `reload_event_routing()` to refresh from disk.

### Config File Schema

```json
{
  "_comment": "Global agent-level event routing (optional doc fields prefixed with _)",
  "_schema": {
    "task_selector": "Static match: 'id:<id>', 'name:<name>', 'name_contains:<substr>'",
    "routing_key": "Legacy shorthand: dot-path to extract from event, auto-compared to task.id / skill.id",
    "match_fields": "Array of {event_path, task_path, transform?} — declarative multi-field matching",
    "match_mode": "'all' (default, AND) or 'any' (OR) — controls how match_fields pairs combine",
    "transforms": "lower, upper, strip, str, int, prefix:<X>, suffix:<X>",
    "queue": "Optional queue name hint"
  },
  "event_routing": {
    "<event_type>": {
      "task_selector": "<selector_string>",
      "routing_key": "<dot.path.in.event>",
      "match_fields": [
        { "event_path": "<dot.path>", "task_path": "<dot.path>", "transform": "<optional>" }
      ],
      "match_mode": "all | any",
      "queue": "<optional_queue_name>"
    }
  }
}
```

### Routing Rule Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_selector` | `string` | No | Static match pattern. Formats: `id:<task_id>`, `name:<exact_name>`, `name_contains:<substring>` |
| `routing_key` | `string` | No | Dot-path into the event object. Extracted value is compared against `task.id`, `task.state.cloud_run_id`, and `task.skill.id` |
| `match_fields` | `array` | No | Array of `{event_path, task_path, transform?}` objects for declarative multi-field matching |
| `match_mode` | `string` | No | `"all"` (default, AND) or `"any"` (OR). Controls how multiple `match_fields` entries combine |
| `queue` | `string` | No | Optional queue name hint for the matched task |

### Matching Strategies

When an event arrives, `_resolve_event_routing()` looks up the event type in the global routing table and evaluates matching strategies **in this order** (first match wins):

#### 1. `match_fields` — Declarative Multi-Field Matching

Most expressive. Compares one or more field pairs between the event and the task:

```json
{
  "match_fields": [
    { "event_path": "data.account_id", "task_path": "state.account_id" },
    { "event_path": "data.store_id",   "task_path": "state.store_id", "transform": "lower" }
  ],
  "match_mode": "all"
}
```

- **`event_path`**: Dot-path to extract a value from the incoming event/request object
- **`task_path`**: Dot-path to extract a value from the candidate `ManagedTask`. Supports:
  - `state.<path>` — from `task.metadata.state`
  - `skill.<field>` — from `task.skill` attributes (`id`, `name`, etc.)
  - Direct field names — from `task` attributes (`id`, `name`, etc.)
- **`transform`** (optional): Applied to **both** values before comparison
- **`match_mode`**:
  - `"all"` (default) — ALL field pairs must match (AND logic)
  - `"any"` — ANY field pair matching is sufficient (OR logic)

#### 2. `routing_key` — Legacy Dynamic Matching

Shorthand for extracting a single value from the event and comparing against well-known task fields:

```json
{
  "routing_key": "command.run_id"
}
```

The extracted value is compared against:
- `task.id` (if `routing_key` contains `"run_id"`)
- `task.state.cloud_run_id` (if `routing_key` contains `"run_id"`)
- `task.skill.id` (if `routing_key` contains `"skill_id"`)

#### 3. `task_selector` — Static Matching (Fallback)

Simple pattern-based matching against task properties:

```json
{
  "task_selector": "name_contains:chatter"
}
```

Supported patterns:
- `id:<task_id>` — exact match on task ID
- `name:<exact_name>` — exact match on task name
- `name_contains:<substring>` — substring match on task name

### Supported Transforms

Transforms are applied to values before comparison in `match_fields`:

| Transform | Description | Example |
|-----------|-------------|---------|
| `lower` | Lowercase | `"ABC"` → `"abc"` |
| `upper` | Uppercase | `"abc"` → `"ABC"` |
| `strip` | Strip whitespace | `" abc "` → `"abc"` |
| `str` | Convert to string | `123` → `"123"` |
| `int` | Convert to integer | `"123"` → `123` |
| `prefix:<X>` | Prepend prefix | `"123"` with `prefix:ID-` → `"ID-123"` |
| `suffix:<X>` | Append suffix | `"abc"` with `suffix:_v2` → `"abc_v2"` |

### Dynamic Amendment at Task Launch

When a task starts (`_submit_task_execution`), the runner automatically:

1. Calls `_extract_event_types_from_skill(skill)` — scans the skill's diagram for `pend_event_node` nodes and collects their `eventType` and `pendingSources`
2. Calls `_amend_event_routing_for_task(task)` — for each event type **not already in the global table**, adds a dynamic routing rule:

```json
{
  "task_selector": "id:<task.id>",
  "routing_key": "command.run_id",
  "queue": "",
  "_auto_added_by_task": "<task.id>",
  "_auto_added_by_skill": "<skill.name>"
}
```

This ensures that skills with pending event nodes (webhooks, SSE, WebSocket listeners) automatically get their events routed correctly without manual configuration.

### Default Routing Rules

The bundled `agent/agent_files/event_routing.json` ships with these defaults:

| Event Type | Strategy | Target |
|------------|----------|--------|
| `human_chat` | `task_selector: name_contains:chatter` | Chat handler task |
| `dev_human_chat` | `task_selector: name_contains:development` | Dev chat task |
| `a2a` | `task_selector: name_contains:chatter` | A2A handler task |
| `api_response` | `routing_key: command.run_id` | Task that initiated the API call |
| `web_hook` | `routing_key: command.run_id` | Task that registered the webhook |
| `cloud_websocket` | `routing_key: command.run_id` | Task that opened the WebSocket |
| `web_sse` | `routing_key: command.run_id` | Task that subscribed to SSE |
| `passive_command` | `routing_key: command.run_id` | Task that started the passive command |

### Full Example: Multi-Agent E-Commerce Setup

Multiple agents running multiple tasks, each handling different stores:

```json
{
  "event_routing": {
    "websocket_order_update": {
      "match_fields": [
        { "event_path": "data.account_id", "task_path": "state.account_id" },
        { "event_path": "data.store_id",   "task_path": "state.store_id", "transform": "lower" }
      ],
      "match_mode": "all"
    },
    "webhook_refund_request": {
      "match_fields": [
        { "event_path": "payload.merchant_id", "task_path": "state.merchant_id" }
      ],
      "match_mode": "all"
    },
    "human_chat": {
      "task_selector": "name_contains:chatter",
      "queue": "chat_queue"
    },
    "scheduled_report": {
      "routing_key": "command.run_id"
    }
  }
}
```

In this example:
- **`websocket_order_update`** events are routed to the task whose `state.account_id` AND `state.store_id` match the event's data fields (both lowercased for store_id)
- **`webhook_refund_request`** events are routed to the task whose `state.merchant_id` matches
- **`human_chat`** events go to any task with "chatter" in its name
- **`scheduled_report`** events are matched by run_id

### Backend Implementation

All routing logic lives in `agent/ec_tasks/runner.py` in the `TaskRunner` class:

| Method | Purpose |
|--------|---------|
| `_load_global_event_routing()` | Load config from disk (user override → bundled default) |
| `_save_global_event_routing()` | Save amended config to user data directory |
| `reload_event_routing()` | Refresh cached config from disk |
| `_extract_event_types_from_skill()` | Scan skill diagram for pend_event_node event types |
| `_amend_event_routing_for_task()` | Dynamically add routing rules at task launch |
| `_resolve_event_routing()` | Main routing engine: match event → task |
| `_extract_task_value()` | Dot-path extraction from ManagedTask |
| `_apply_match_transform()` | Apply transform to a value |
| `_evaluate_match_fields()` | Evaluate match_fields with AND/OR logic |

## Defaults (preserve current behavior)

**Both developing and released modes include:**

- Map QA form to `state.attributes.forms.qa_form` and `resume.qa_form_to_agent`.
- Map Notification to `state.attributes.notifications.latest` and `resume.notification_to_agent`.
- Map Human text to `state.attributes.human.last_message` and `resume.human_text`.
- Map `event.tag` to `state.attributes.cloud_task_id`. If checkpoint exists, it is also injected into checkpoint `values.attributes.cloud_task_id`.

**Developing mode additionally includes:**

- Map `event.data.metadata` to `state.attributes.debug.last_event_metadata` for debugging.

## Where it runs

### Backend (Python)

**`agent/tasks_resume.py`:**

- `DEFAULT_MAPPINGS`: Separated by run_mode (`developing` / `released`)
- `load_mapping_for_task()`: Resolves mapping rules with precedence:
  1. Node-level mapping (from `skill.config.nodes[node_name].mapping_rules`)
  2. Skill-level mapping (from `skill.mapping_rules[run_mode]`)
  3. Defaults (from `DEFAULT_MAPPINGS[run_mode]`)
- `normalize_event()`: Builds the event envelope
- `select_checkpoint()`: Finds the checkpoint by tag
- `build_resume_from_mapping()`: Applies rules to produce `(resume_payload, state_patch)`
- `build_general_resume_payload()`: Orchestrates and injects cloud_task_id

**`agent/tasks.py`:**

- `launch_unified_run()`: Unified task execution supporting all trigger types
  - Replaces `launch_scheduled_run()`, `launch_reacted_run()`, `launch_interacted_run()`
  - Consistent interrupt-resume behavior across all modes
  - Uses mapping DSL via `_build_resume_payload()`
- Uses feature flag `RESUME_PAYLOAD_V2` (default on) and deep-merges `state_patch` into `task.metadata['state']`

**`agent/ec_skills/build_agent_skills.py`:**

- `load_from_code()`: Loads `data_mapping.json` from skill root
- `load_from_diagram()`: Loads `data_mapping.json` and `run_mode` from skill JSON
- Assigns to `skill.mapping_rules` for runtime use

### Frontend (TypeScript/React)

**Skill Editor Components:**

1. **`components/mapping/SkillLevelMappingEditor.tsx`**

   - Edits skill-level mappings for START node
   - Separate sections for developing/released modes
   - JSON editor for per-skill `event_data_mapping` (adapt_to_state)
   - Info panel noting event-to-task routing is now agent-level
2. **`components/mapping/MappingEditor.tsx`**

   - Edits node-to-node transfer mappings
   - Used for all non-START nodes
   - Preview functionality for testing rules
3. **`components/sidebar/sidebar-node-renderer.tsx`**

   - Detects START node vs other nodes
   - Shows appropriate mapping editor
   - Persists to `skillInfo.config.skill_mapping` (START) or `node.data.mapping_rules` (others)
4. **`components/tools/save.tsx`**

   - Extracts skill-level mappings from START node
   - Extracts node-level mappings from other nodes
   - Generates and saves `data_mapping.json` alongside skill JSON
5. **`components/tools/readonly.tsx`**

   - Released toggle button controls `run_mode`
   - Updates both UI `mode` and backend `run_mode`

## Per-skill customization

Skills can customize mapping rules in two ways:

### 1. Via GUI (Recommended)

**For Skill-Level Mappings:**

1. Open the START node in the skill editor
2. Scroll to "Skill-Level Mapping Rules" section
3. Configure mappings for both developing and released modes
5. Save the skill

**For Node-Level Mappings:**

1. Open any non-START node in the skill editor
2. Scroll to "Node Transfer Mapping" section
3. Configure mappings from preceding node to current node
4. Use `node.*` paths for source, `state.*` paths for target
5. Save the skill

### 2. Via Code (Advanced)

Skills can set `EC_Skill.mapping_rules` programmatically:

```python
# In your skill's abc_skill.py
skill = EC_Skill(name="My Custom Skill")
skill.run_mode = "developing"  # or "released"
skill.mapping_rules = {
    "developing": {
        "mappings": [
            {
                "from": ["event.data.sample_tool_input"],
                "to": [
                    {"target": "state.tool_input.sample"},
                    {"target": "resume.sample_tool_input"}
                ],
                "on_conflict": "overwrite"
            }
        ],
        "options": {"strict": False}
    },
    "released": {
        "mappings": [...],
        "options": {"strict": True}
    },
}
```

## GUI Features (Implemented)

✅ **START Node Editor:**

- Skill-level mapping configuration
- Separate sections for developing/released modes
- Collapsible panels for organization

✅ **Other Node Editors:**

- Node-to-node transfer mapping
- Clear labels distinguishing from skill-level mapping
- Help text explaining source/target paths

✅ **Mapping Editor Component:**

- JSON-based rule editing
- Preview functionality
- Transform selection
- Conflict policy selection

✅ **Released Toggle:**

- Controls both UI mode and backend run_mode
- Visual feedback (lock/unlock icon)
- Toast notifications on mode change

## File Structure

When you save a skill, the following files are created:

```
my_skill_skill/
├── data_mapping.json                 # Mapping rules (at skill root level)
├── diagram_dir/
│   ├── my_skill_skill.json          # Main skill JSON with workFlow
│   └── my_skill_skill_bundle.json   # Multi-sheet bundle
└── code_skill/                       # Optional Python code
    └── ...
```

The `data_mapping.json` file contains:

- Skill-level mappings (from START node)
- Node-level mappings (from other nodes)
- Event data mapping (`event_data_mapping`) — per-skill config for projecting event payload fields into the resuming node's state (`adapt_to_state`)
- Separated by run_mode (developing/released)

> **Note:** Event-to-task *routing* is no longer stored in `data_mapping.json`. It is now managed at the agent level via `agent/agent_files/event_routing.json`. The per-skill `event_data_mapping` key handles event *data projection* only.

## Examples

### Example 1: Skill-Level Event Mapping

Map incoming chat messages to state:

```json
{
  "developing": {
    "mappings": [
      {
        "from": ["event.data.human_text"],
        "to": [
          {"target": "state.attributes.human.last_message"},
          {"target": "resume.human_text"}
        ],
        "transform": "to_string",
        "on_conflict": "overwrite"
      }
    ]
  }
}
```

### Example 2: Node-Level State-to-State Transfer

Map API response (already present in state) into current node's tool_input:

```json
{
  "mappings": [
    {
      "from": ["state.result.api_response"],
      "to": [{"target": "state.tool_input.data"}],
      "transform": "parse_json",
      "on_conflict": "overwrite"
    }
  ]
}
```

### Example 3: Event Routing (Agent-Level)

Event routing is now configured globally in `agent/agent_files/event_routing.json`, not per-skill.
When a task starts, the runner automatically detects `pend_event` nodes in the skill and registers
the required event routes dynamically.

**Static routing (task_selector):**
```json
{
  "event_routing": {
    "human_chat": {
      "task_selector": "name_contains:chatter",
      "queue": "chat_queue"
    }
  }
}
```

**Dynamic routing (routing_key):**
```json
{
  "event_routing": {
    "web_hook": {
      "routing_key": "command.run_id",
      "task_selector": ""
    }
  }
}
```

**Multi-field matching (match_fields):**
```json
{
  "event_routing": {
    "websocket_order_update": {
      "match_fields": [
        {"event_path": "data.account_id", "task_path": "state.account_id"},
        {"event_path": "data.store_id", "task_path": "state.store_id", "transform": "lower"}
      ],
      "match_mode": "all"
    }
  }
}
```

**Matching strategies (evaluated in order):**
1. `match_fields`: Array of `{event_path, task_path, transform?}` pairs. `match_mode` controls AND (`"all"`) or OR (`"any"`) logic.
2. `routing_key`: Legacy shorthand — extracts a value from the event and compares against task id / skill id.
3. `task_selector`: Static match by task name or id (e.g. `"name_contains:chatter"`, `"id:task_123"`).

**Supported transforms:** `lower`, `upper`, `strip`, `str`, `int`, `prefix:<X>`, `suffix:<X>`

## Testing

### Unit Tests

- `tests/test_tasks_resume.py`: Covers normalization, mapping, checkpoint selection, and orchestration

### Manual Testing Checklist

1. **Skill Creation:**

   - [ ]  Create new skill in editor
   - [ ]  Open START node, add skill-level mappings
   - [ ]  Open other nodes, add node-to-node mappings
   - [ ]  Toggle released mode
   - [ ]  Save and verify `data_mapping.json` is created
2. **Skill Loading:**

   - [ ]  Load saved skill
   - [ ]  Verify mappings appear in START node editor
   - [ ]  Verify mappings appear in other node editors
   - [ ]  Verify run_mode matches released toggle
3. **Runtime:**

   - [ ]  Run skill in developing mode
   - [ ]  Run skill in released mode
   - [ ]  Verify correct mappings are used
   - [ ]  Test interrupt-resume with scheduled tasks
4. **Unified Launch:**

   - [ ]  Test scheduled task execution
   - [ ]  Test a2a message handling
   - [ ]  Test chat message handling
   - [ ]  Verify consistent behavior across all modes

## Migration Guide

### For Existing Skills

Existing skills without `data_mapping.json` will continue to work using default mappings. To add custom mappings:

1. Open the skill in the editor
2. Configure mappings in START node (skill-level)
3. Configure mappings in other nodes (node-to-node)
4. Save the skill - `data_mapping.json` will be created automatically

### For Code-Based Skills

If your skill sets `mapping_rules` programmatically, update the structure:

**Old format:**

```python
skill.mapping_rules = {
    "mappings": [...],
    "options": {...}
}
```

**New format:**

```python
dskill.mapping_rules = {
    "developing": {
        "mappings": [...],
        "options": {"strict": False}
    },
    "released": {
        "mappings": [...],
        "options": {"strict": True}
    }
}
```

The old format is still supported for backward compatibility, but will use the same mappings for both modes.

## Troubleshooting

**Mappings not being applied:**

- Check that `data_mapping.json` exists alongside skill JSON
- Verify `run_mode` is set correctly in skill JSON
- Check logs for mapping load errors in `build_agent_skills.py`

**Wrong mappings being used:**

- Verify the released toggle matches your intended run_mode
- Check mapping precedence: Node-level → Skill-level → Defaults
- Use `logger.debug` to trace `load_mapping_for_task()` resolution

**Scheduled tasks not resuming:**

- Ensure you're using `launch_unified_run()` (old functions are deprecated)
- Check that interrupt-resume payload is being built correctly
- Verify checkpoint is being saved and retrieved

## References

- **Backend — Routing Engine:** `agent/ec_tasks/runner.py` (`TaskRunner._resolve_event_routing` and related methods)
- **Backend — Resume / Data Projection:** `agent/ec_tasks/resume.py` (`_load_event_data_mapping`, `apply_adapt_to_state_mapping`)
- **Backend — Skill Loading:** `agent/ec_skills/build_agent_skills.py`
- **Global Routing Config:** `agent/agent_files/event_routing.json`
- **Frontend — Mapping Editor:** `gui_v2/src/modules/skill-editor/components/mapping/`
- **Frontend — Save Logic:** `gui_v2/src/modules/skill-editor/components/tools/save.tsx`
- **Frontend — Skill Loader:** `gui_v2/src/modules/skill-editor/services/skill-loader.ts`
- **Example Skill:** `agent/ec_skills/dev_utils/skill_dev_utils.py`
