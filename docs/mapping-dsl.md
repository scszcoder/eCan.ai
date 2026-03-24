# Mapping DSL — data\_mapping.json Reference

> **Canonical GUI doc:** [gui_v2/src/modules/skill-editor/doc/mapping-dsl.md](../gui_v2/src/modules/skill-editor/doc/mapping-dsl.md)
>
> This file is the **authoritative runtime reference** for the mapping DSL,
> the template `data_mapping.json`, and the per-event-type data schemas that
> feed into it.
>
> For browser-event monitor architecture, source types, lifecycle semantics, and browser monitor config examples, see [Browser Event Monitor Design](C:\Users\songc\PycharmProjects\eCan.ai\docs\BROWSER_EVENT_MONITOR.md).

---

## Table of Contents

1. [Overview](#overview)
2. [Universal Event Envelope](#universal-event-envelope)
3. [State After pend\_event Resumes](#state-after-pend_event-resumes)
4. [Per-Type Event Data Schemas](#per-type-event-data-schemas)
5. [Event Routing Mechanisms](#event-routing-mechanisms)
6. [matchFields — Declarative Event Filtering](#matchfields--declarative-event-filtering)
7. [Template data\_mapping.json](#template-data_mappingjson)
8. [DSL Reference](#dsl-reference)
9. [Fallback Default Mappings](#fallback-default-mappings)
10. [Where It Runs](#where-it-runs)
11. [Troubleshooting](#troubleshooting)

---

## Overview

Every skill can ship a `data_mapping.json` next to its diagram JSON.
This file tells the runtime how to **project event data into node state**
(`state.*`) and the **resume payload** (`resume.*`) when a `pend_event` node
fires.

There are four top-level sections:

| Section | Purpose |
|---|---|
| `developing` | Mapping rules applied when `run_mode == "developing"` |
| `released` | Mapping rules applied when `run_mode == "released"` |
| `node_transfers` | Per-node state→state transfer rules (keyed by node name) |
| `event_data_mapping` | Per-event-type `adapt_to_state` projections |

If a skill has **no** `data_mapping.json`, the runtime falls back to
`DEFAULT_MAPPING_RULE` in `agent/ec_skill.py` (line 48) or
`DEFAULT_MAPPINGS` in `agent/ec_tasks/resume.py` (line 557).

---

## Universal Event Envelope

All events are normalized through `normalize_event()` in
`agent/ec_tasks/resume.py` into this structure **before** any mapping runs:

```python
{
    "type": str,              # "human_chat", "a2a", "timer", "browser_event", "webhook", …
    "source": str,            # Origin identifier (senderId or "gui:<chatId>")
    "tag": str,               # Business tag (typically the pend_event node name)
    "i_tag": str,             # Backward-compat alias for tag
    "timestamp": str,         # ISO timestamp
    "data": {...},            # Event-specific payload (varies by type — see below)
    "context": {              # Auto-promoted routing fields
        "id": str,            # Message ID
        "sessionId": str,
        "chatId": str,
        "msgId": str,
        "senderId": str,
        "senderName": str,
        "client_id": str,     # Promoted from top-level or msg.command
        "task_id": str,
        "run_id": str,
        "timer_id": str,
        "timer_name": str,
        "sub_type": str,      # Subscription label (browser_event)
        "sub_id": str,
    }
}
```

> **Promoted fields:** `client_id`, `task_id`, `run_id`, `timer_id`,
> `timer_name`, `sub_type`, `sub_id` are automatically lifted into `context`
> from the raw message top-level or nested `command` dict.

---

## State After pend\_event Resumes

When a `pend_event` node fires, two things happen:

### 1. Event appended to `state["events"]`

```python
state["events"][-1] = {
    "event_type": str,        # event.type
    "source": str,            # event.source
    "timestamp": str,
    "context": dict,          # event.context (full)
    "tag": str,               # event.tag
    "node": str,              # pend_event node name/ID
    "data": dict,             # event.data (if present)
}
```

### 2. State patch (if present)

```python
# If resume payload contains "_state_patch":
state = deep_merge(state, resume_payload["_state_patch"])

# If resume payload contains "chat_attributes":
state["attributes"]["chat_attributes"].update(resume_payload["chat_attributes"])
```

---

## Per-Type Event Data Schemas

### 1. `human_chat`

Triggered when a human sends a chat message.

**event.data:**
```python
{
    "human_text": str,           # The message text
    "metadata": {
        "chatId": str,
        "msgId": str,
        "senderId": str,
        "senderName": str,
        "mtype": "send_chat",    # Always "send_chat" for human_chat
        "timestamp": str,
    },
    "raw": Any,                  # Fallback raw message object
}
```

**pend\_event config:**
```json
{ "eventType": "human_chat", "timeoutSec": 0 }
```

---

### 2. `a2a` (Agent-to-Agent)

Triggered when another agent sends a message to this skill.

**event.data:**
```python
{
    "human_text": str,           # Extracted from message.parts[0].text
    "message": {
        "role": str,             # "agent", "user", "assistant"
        "parts": [
            {"type": "text", "text": str},
            {"type": "file", "file": {"name": str, "mimeType": str, "bytes": bytes, "uri": str}},
            {"type": "data", "data": dict, "metadata": dict},
        ],
        "metadata": dict,
    },
    "metadata": dict,
    "raw": Any,
}
```

**pend\_event config:**
```json
{ "eventType": "a2a", "agentIds": "agent-id-1,agent-id-2" }
```

---

### 3. `timer`

Triggered when a named timer fires (created via the `add_timer` MCP tool).

> **NOTE:** Timer fields live at the **event top level**, not nested in `event.data`.

**Full event structure:**
```python
{
    "type": "timer",
    "timer_name": str,           # Must match pend_event timerName
    "timer_id": str,
    "fire_count": int,
    "agent_id": str,
    "timestamp": int,            # Unix milliseconds
    "source": "timer_service",
}
```

**pend\_event config:**
```json
{ "eventType": "timer", "timerName": "poll_orders" }
```

**Routing:** `timerName` in pend\_event matches `context.timer_name` (auto-promoted).

---

### 4. `browser_event`

Triggered by Chrome DevTools Protocol (CDP) events from a browser subscription.

> **NOTE:** Browser event fields live at the **event top level**, not nested in `event.data`.

**Full event structure:**
```python
{
    "type": "browser_event",
    "sub_type": str,             # User-defined label (matches browserEventLabel)
    "sub_id": str,
    "event_method": str,         # e.g. "Page.frameNavigated"
    "domain": str,               # "Page", "Runtime", "Network", …
    "fire_count": int,
    "session_id": str,
    "params": dict,              # CDP event parameters
    "agent_id": str,
    "timestamp": int,
    "source": "browser_event_service",
}
```

**pend\_event config:**
```json
{ "eventType": "browser_event", "browserEventLabel": "price_api" }
```

**Routing:** `browserEventLabel` matches `context.sub_type` (auto-promoted).

---

### 5. `passive_command` (Hybrid Cloud)

Cloud sends commands to the ground-side `passive0` helper; ground responds with results.

**Cloud → Ground (command):**
```python
{
    "schema_version": 1,
    "type": "browser_use_passive_step" | "skill_passive_step",
    "run_id": str,
    "step_id": str,
    "acct_site_id": str,
    "agent_id": str,
    "skill_id": str,
    "node_id": str,
    "actions": [
        {"action": str, "selector": str, ...},
    ],
    "include_screenshot": bool,
    "stop_on_error": bool,
}
```

**Ground → Cloud (result):**
```python
{
    "schema_version": 1,
    "type": "browser_use_passive_step_result",
    "run_id": str,
    "step_id": str,
    "ok": bool,
    "elapsed_ms": int,
    "actions": [dict],
    "action_results": [
        {"output": str, "error": str | None},
    ],
    "errors": [str],
    "browser": {
        "url": str, "title": str,
        "viewport": {"width": int, "height": int},
        "screenshot": str,      # Base64 if requested
        "cookies": list,
    },
    "dom_tree": dict | None,
}
```

**data\_mapping.json for passive\_command:**
```json
{
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

---

### 6. `webhook`

Triggered by an external HTTP POST to the webhook endpoint.

**event.data:**
```python
{
    "raw": Any,  # HTTP POST body (JSON-parsed dict or raw string)
}
```

**pend\_event config:**
```json
{
  "eventType": "webhook",
  "matchFields": [
    {"event_path": "data.raw.event_type", "literal": "order_created"}
  ]
}
```

---

### 7. `websocket` (Cloud Task Result)

Triggered when a cloud LLM task completes and sends its result back.

**event.data:**
```python
{
    "workType": str,
    "agentID": str,
    "result": dict,
    "raw": dict,
}
```

---

### 8. `system`, `mqtt`, `sse`

**Status: NOT IMPLEMENTED** as pend\_event sources. Reserved for future use.

---

## Event Routing Mechanisms

| Mechanism | Config Field | Matches Against |
|---|---|---|
| Timer name | `timerName` | `context.timer_name` |
| Browser event label | `browserEventLabel` | `context.sub_type` |
| Declarative field matching | `matchFields` | Any event path |
| Multiple event sources | `pendingSources` | Array of `{type, …}` objects |
| Resume policy | `resumePolicy` | `"first"` = first match; `"all"` = wait for all |
| Timeout | `timeoutSec` | 0 = forever; >0 = seconds |

### Composite Routing Keys (Internal)

- Timer events → key `"timer:<timer_name>"`
- Browser events → key `"browser_event:<label>"`

---

## matchFields — Declarative Event Filtering

```json
{
  "matchFields": [
    {
      "event_path": "context.timer_name",
      "literal": "check_orders"
    },
    {
      "event_path": "data.raw.event_type",
      "literal": "order_created",
      "transform": "lower"
    }
  ]
}
```

All entries must match (AND logic).

---

## Template data\_mapping.json

Below is a **comprehensive template** that covers every event type.
Copy it into your skill's root directory as `data_mapping.json` and
remove/modify the sections you don't need.

When a skill has **no** `data_mapping.json` (or `mappings: []`), the runtime
automatically applies the [Fallback Default Mappings](#fallback-default-mappings)
defined in `resume.py` / `ec_skill.py`.

```json
{
  "_comment": "Template data_mapping.json — remove sections you don't need",

  "developing": {
    "mappings": [
      {
        "_comment": "QA form → state + resume (all event types)",
        "from": ["event.data.qa_form_to_agent", "event.data.qa_form"],
        "to": [
          {"target": "state.attributes.forms.qa_form"},
          {"target": "resume.qa_form_to_agent"}
        ],
        "on_conflict": "merge_deep"
      },
      {
        "_comment": "Notification → state + resume",
        "from": ["event.data.notification_to_agent", "event.data.notification"],
        "to": [
          {"target": "state.attributes.notifications.latest"},
          {"target": "resume.notification_to_agent"}
        ],
        "on_conflict": "merge_deep"
      },
      {
        "_comment": "Human text → state + resume (human_chat, a2a)",
        "from": ["event.data.human_text"],
        "to": [
          {"target": "state.attributes.human.last_message"},
          {"target": "resume.human_text"}
        ],
        "transform": "to_string",
        "on_conflict": "overwrite"
      },
      {
        "_comment": "Resolve i_tag from nested metadata paths",
        "from": ["event.data.params.metadata.i_tag", "event.data.metadata.i_tag"],
        "to": [
          {"target": "event.tag"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "_comment": "Tag → cloud_task_id for checkpoint correlation",
        "from": ["event.tag"],
        "to": [
          {"target": "state.attributes.cloud_task_id"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "_comment": "Async response mode flag",
        "from": ["event.data.metadata.async_response", "event.context.async_response"],
        "to": [
          {"target": "state.attributes.async_response"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "_comment": "[DEV ONLY] Debug metadata snapshot",
        "from": ["event.data.metadata"],
        "to": [
          {"target": "state.attributes.debug.last_event_metadata"}
        ],
        "on_conflict": "overwrite"
      },

      {
        "_comment": "--- Timer event: fire_count to state ---",
        "from": ["event.fire_count"],
        "to": [
          {"target": "state.attributes.timer.fire_count"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "_comment": "--- Timer event: timer_name to state ---",
        "from": ["event.timer_name", "event.context.timer_name"],
        "to": [
          {"target": "state.attributes.timer.name"}
        ],
        "on_conflict": "overwrite"
      },

      {
        "_comment": "--- Browser event: CDP event method ---",
        "from": ["event.event_method"],
        "to": [
          {"target": "state.attributes.browser_event.event_method"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "_comment": "--- Browser event: CDP params ---",
        "from": ["event.params"],
        "to": [
          {"target": "state.attributes.browser_event.params"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "_comment": "--- Browser event: subscription label ---",
        "from": ["event.sub_type", "event.context.sub_type"],
        "to": [
          {"target": "state.attributes.browser_event.label"}
        ],
        "on_conflict": "overwrite"
      },

      {
        "_comment": "--- Webhook: raw body ---",
        "from": ["event.data.raw"],
        "to": [
          {"target": "state.attributes.webhook.payload"}
        ],
        "on_conflict": "overwrite"
      },

      {
        "_comment": "--- Websocket / cloud task result ---",
        "from": ["event.data.result"],
        "to": [
          {"target": "state.attributes.cloud_task.result"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "_comment": "--- Websocket: workType ---",
        "from": ["event.data.workType"],
        "to": [
          {"target": "state.attributes.cloud_task.work_type"}
        ],
        "on_conflict": "overwrite"
      },

      {
        "_comment": "--- A2A: full message object ---",
        "from": ["event.data.message"],
        "to": [
          {"target": "state.attributes.a2a.message"}
        ],
        "on_conflict": "overwrite"
      },

      {
        "_comment": "--- Context: chatId for reply routing ---",
        "from": ["event.context.chatId"],
        "to": [
          {"target": "state.attributes.chat_id"}
        ],
        "on_conflict": "skip"
      },
      {
        "_comment": "--- Context: senderId ---",
        "from": ["event.context.senderId"],
        "to": [
          {"target": "state.attributes.sender_id"}
        ],
        "on_conflict": "overwrite"
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
      {
        "from": ["event.data.qa_form_to_agent", "event.data.qa_form"],
        "to": [
          {"target": "state.attributes.forms.qa_form"},
          {"target": "resume.qa_form_to_agent"}
        ],
        "on_conflict": "merge_deep"
      },
      {
        "from": ["event.data.notification_to_agent", "event.data.notification"],
        "to": [
          {"target": "state.attributes.notifications.latest"},
          {"target": "resume.notification_to_agent"}
        ],
        "on_conflict": "merge_deep"
      },
      {
        "from": ["event.data.human_text"],
        "to": [
          {"target": "state.attributes.human.last_message"},
          {"target": "resume.human_text"}
        ],
        "transform": "to_string",
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.data.params.metadata.i_tag", "event.data.metadata.i_tag"],
        "to": [
          {"target": "event.tag"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.tag"],
        "to": [
          {"target": "state.attributes.cloud_task_id"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.data.metadata.async_response", "event.context.async_response"],
        "to": [
          {"target": "state.attributes.async_response"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.fire_count"],
        "to": [
          {"target": "state.attributes.timer.fire_count"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.timer_name", "event.context.timer_name"],
        "to": [
          {"target": "state.attributes.timer.name"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.event_method"],
        "to": [
          {"target": "state.attributes.browser_event.event_method"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.params"],
        "to": [
          {"target": "state.attributes.browser_event.params"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.sub_type", "event.context.sub_type"],
        "to": [
          {"target": "state.attributes.browser_event.label"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.data.raw"],
        "to": [
          {"target": "state.attributes.webhook.payload"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.data.result"],
        "to": [
          {"target": "state.attributes.cloud_task.result"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.data.workType"],
        "to": [
          {"target": "state.attributes.cloud_task.work_type"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.data.message"],
        "to": [
          {"target": "state.attributes.a2a.message"}
        ],
        "on_conflict": "overwrite"
      },
      {
        "from": ["event.context.chatId"],
        "to": [
          {"target": "state.attributes.chat_id"}
        ],
        "on_conflict": "skip"
      },
      {
        "from": ["event.context.senderId"],
        "to": [
          {"target": "state.attributes.sender_id"}
        ],
        "on_conflict": "overwrite"
      }
    ],
    "options": {
      "strict": true,
      "default_on_missing": null,
      "apply_order": "top_down"
    }
  },

  "node_transfers": {
    "_comment": "Per-node state→state transfer rules. Key = node name.",
    "example_node": {
      "mappings": [
        {
          "from": ["state.result.api_response"],
          "to": [{"target": "state.tool_input.next_step_data"}],
          "transform": "parse_json",
          "on_conflict": "overwrite"
        }
      ],
      "options": {
        "strict": false,
        "default_on_missing": null,
        "apply_order": "top_down"
      }
    }
  },

  "event_data_mapping": {
    "_comment": "Per-event-type adapt_to_state projections (read by apply_adapt_to_state_mapping).",

    "passive_command": {
      "routing_key": "run_id",
      "adapt_to_state": {
        "actions": "state.attributes.passive_command_actions",
        "run_id": "state.attributes.passive_run_id",
        "step_id": "state.attributes.passive_step_id"
      },
      "resume_with": {
        "event_type": "passive_command"
      }
    },
    "PassiveCommandEvent": {
      "routing_key": "run_id",
      "adapt_to_state": {
        "actions": "state.attributes.passive_command_actions",
        "run_id": "state.attributes.passive_run_id",
        "step_id": "state.attributes.passive_step_id"
      },
      "resume_with": {
        "event_type": "passive_command"
      }
    },

    "webhook": {
      "adapt_to_state": {
        "raw": "state.attributes.webhook.payload"
      }
    },

    "timer": {
      "adapt_to_state": {
        "timer_name": "state.attributes.timer.name",
        "timer_id": "state.attributes.timer.id",
        "fire_count": "state.attributes.timer.fire_count"
      }
    },

    "browser_event": {
      "adapt_to_state": {
        "sub_type": "state.attributes.browser_event.label",
        "event_method": "state.attributes.browser_event.event_method",
        "params": "state.attributes.browser_event.params",
        "fire_count": "state.attributes.browser_event.fire_count"
      }
    },

    "websocket": {
      "adapt_to_state": {
        "result": "state.attributes.cloud_task.result",
        "workType": "state.attributes.cloud_task.work_type"
      }
    }
  }
}
```

### Minimal Skeleton

If your skill only needs the defaults (human\_chat / QA form / notification), use:

```json
{
  "developing": {
    "mappings": [],
    "options": { "strict": false, "apply_order": "top_down" }
  },
  "released": {
    "mappings": [],
    "options": { "strict": true, "apply_order": "top_down" }
  },
  "node_transfers": {},
  "event_data_mapping": {}
}
```

Empty `mappings: []` causes the runtime to apply `DEFAULT_MAPPINGS` from
`resume.py` (which already handles `human_text`, `qa_form`, `notification`,
`cloud_task_id`, and `async_response`).

---

## DSL Reference

### Sources

| Namespace | Description |
|---|---|
| `event.*` | Normalized event envelope (see above) |
| `state.*` | Current graph state snapshot (read-only) |
| `node.*` | **Deprecated** — rewritten to `state.result.*` at runtime |

### Targets

| Prefix | Writes to |
|---|---|
| `state.attributes.<path>` | `state_patch["attributes"][…]` → merged into graph state |
| `state.metadata.<path>` | `state_patch["metadata"][…]` |
| `state.tool_input.<path>` | `state_patch["tool_input"][…]` |
| `resume.<key>` | `resume_payload[key]` → returned to orchestrator |

### Rule Schema

```json
{
  "from": ["event.data.field_a", "event.data.field_b"],
  "to": [
    {"target": "state.attributes.my_field"},
    {"target": "resume.my_field"}
  ],
  "transform": "to_string",
  "on_conflict": "overwrite"
}
```

- **`from`** — List of dot-paths. First non-null wins.
- **`to`** — One or more targets.
- **`transform`** (optional) — See table below.
- **`on_conflict`** — `overwrite` | `skip` | `merge_shallow` | `merge_deep` | `append`.

### Transforms

| Name | Description |
|---|---|
| `identity` | No-op (default) |
| `to_string` | JSON-serialize or `str()` |
| `parse_json` | `json.loads()` if string; pass-through if already dict/list |
| `pick` | Extract sub-path: `{"name": "pick", "args": {"path": "a.b.c"}}` |
| `coalesce` | First non-null from sub-paths: `{"name": "coalesce", "args": {"paths": ["x","y"]}}` |

### Options

| Key | Type | Description |
|---|---|---|
| `strict` | `bool` | `true` = fail on missing source (released); `false` = skip silently |
| `default_on_missing` | `any` | Value when all `from` paths are null (default: `null`) |
| `apply_order` | `str` | `"top_down"` — rules evaluated in array order |

---

## Fallback Default Mappings

When no `data_mapping.json` exists, the runtime uses these built-in rules
(defined identically in `resume.py:_BASE_MAPPINGS` and `ec_skill.py:DEFAULT_MAPPING_RULE`):

| Source | Target | Transform | Conflict |
|---|---|---|---|
| `event.data.qa_form_to_agent` / `event.data.qa_form` | `state.attributes.forms.qa_form` + `resume.qa_form_to_agent` | — | `merge_deep` |
| `event.data.notification_to_agent` / `event.data.notification` | `state.attributes.notifications.latest` + `resume.notification_to_agent` | — | `merge_deep` |
| `event.data.human_text` | `state.attributes.human.last_message` + `resume.human_text` | `to_string` | `overwrite` |
| `event.tag` | `state.attributes.cloud_task_id` | — | `overwrite` |
| `event.data.metadata.async_response` / `event.context.async_response` | `state.attributes.async_response` | — | `overwrite` |

**Developing mode** additionally maps:

| Source | Target |
|---|---|
| `event.data.metadata` | `state.attributes.debug.last_event_metadata` |

### Fallback enrichment (`build_general_resume_payload`)

Even beyond the mapping rules, `resume.py` lines 907–1036 apply hardcoded
fallback enrichment that **always runs**:

- `human_text` → `state.attributes.human.last_message` + `resume_payload["human_text"]`
- `event.data.metadata` → `state.attributes.debug.last_event_metadata`
- `event.context.chatId` → `state.attributes.chat_id`
- Channel metadata (`channel_id`, `channel_chat_id`, …) → `state.attributes.*`
- `async_callback` results → `state.attributes.passive_command*` + `adapt_to_state` mapping
- User message → appended to `state.history` as `HumanMessage`

This means even a completely empty `data_mapping.json` will still route
`human_text` and chat context into state correctly.

---

## Where It Runs

### Resolution Precedence (`load_mapping_for_task`)

1. **Node-level** — `skill.config.nodes[<node_name>].mapping_rules`
2. **Skill-level** — `skill.mapping_rules[<run_mode>]` (loaded from `data_mapping.json`)
3. **Defaults** — `DEFAULT_MAPPINGS[<run_mode>]` in `resume.py`

### Key Functions

| Function | File | Purpose |
|---|---|---|
| `normalize_event()` | `resume.py:247` | Build universal event envelope |
| `build_resume_from_mapping()` | `resume.py:659` | Apply mapping rules → `(resume, state_patch)` |
| `build_general_resume_payload()` | `resume.py:836` | Full orchestration + fallback enrichment |
| `build_node_transfer_patch()` | `resume.py:731` | Apply `node_transfers` rules |
| `load_mapping_for_task()` | `resume.py:792` | Resolve mapping rules by precedence |
| `apply_adapt_to_state_mapping()` | `resume.py:161` | Apply `event_data_mapping.*.adapt_to_state` |
| `_load_event_data_mapping()` | `resume.py:211` | Load `event_data_mapping` from skill |
| `_build_data_mapping()` | `code_agent.py:2303` | Merge LLM-generated rules onto baseline defaults |
| `DEFAULT_MAPPING_RULE` | `ec_skill.py:48` | Fallback mapping rules for `EC_Skill` |

---

## Troubleshooting

- **Mappings not applied?** — Check that `data_mapping.json` exists at skill root. Check `run_mode`.
- **Wrong mappings?** — Precedence: Node-level → Skill-level → Defaults. Use `logger.debug` to trace `load_mapping_for_task()`.
- **Timer/browser events not landing in state?** — These fields are at the event **top level**, not in `event.data`. Use `event.timer_name` / `event.sub_type` in your `from` paths (or rely on `context.timer_name` / `context.sub_type` after auto-promotion).
- **`event_data_mapping` not firing?** — Only applies to `async_callback` results routed through `build_general_resume_payload`. Check the event type key matches exactly.
- **`node_transfers` ignored?** — Legacy `node.*` sources are rewritten to `state.result.*`. Ensure the source data exists in `state.result`.

---

## References

- **Runtime — Resume / Mapping:** `agent/ec_tasks/resume.py`
- **Skill Model:** `agent/ec_skill.py` (`DEFAULT_MAPPING_RULE`, `EC_Skill.mapping_rules`)
- **Code Agent Builder:** `agent/skill_editor/code_agent.py` (`_build_data_mapping`)
- **Skill Loading:** `agent/ec_skills/build_agent_skills.py`
- **Global Event Routing:** `agent/agent_files/event_routing.json`
- **GUI Mapping Editor:** `gui_v2/src/modules/skill-editor/components/mapping/`
- **GUI Save Logic:** `gui_v2/src/modules/skill-editor/components/tools/save.tsx`
- **Detailed GUI Doc:** [gui_v2/src/modules/skill-editor/doc/mapping-dsl.md](../gui_v2/src/modules/skill-editor/doc/mapping-dsl.md)
- **Tests:** `tests/test_tasks_resume.py`
