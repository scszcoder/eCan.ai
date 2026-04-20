# Browser Event Monitor Design

This document describes the current real-time browser event monitor design used by the `browser_automation` node.

It covers:

- architecture and lifecycle
- supported monitor source types
- how monitors resume `pend_event`
- parameter meanings
- skill JSON examples
- current limitations

## 1. Design Goals

The browser event monitor system exists to let a `browser_automation` node:

- observe browser state in real time or near-real time
- emit normalized `browser_event` messages
- resume `pend_event` nodes without re-running expensive discovery logic
- keep monitoring logic session-scoped instead of hardcoding site-specific behavior in node runtime code

The current design separates:

- prompt policy
- monitor configuration
- session monitor lifecycle
- workflow resume routing

## 2. High-Level Architecture

The main components are:

- browser session capability
  - [event_monitor_capability.py](/Users/songc/PycharmProjects/eCan.ai/agent/ec_skills/browser_use_extension/event_monitor_capability.py)
- monitor runtime
  - [event_monitor.py](/Users/songc/PycharmProjects/eCan.ai/agent/ec_skills/browser_use_extension/event_monitor.py)
- browser-use extension tools
  - [extension_tools_service.py](/Users/songc/PycharmProjects/eCan.ai/agent/ec_skills/browser_use_extension/extension_tools_service.py)
  - [extension_tools_views.py](/Users/songc/PycharmProjects/eCan.ai/agent/ec_skills/browser_use_extension/extension_tools_views.py)
- workflow resume path
  - [prep_skills_run.py](/Users/songc/PycharmProjects/eCan.ai/agent/ec_skills/prep_skills_run.py)
  - [resume.py](/Users/songc/PycharmProjects/eCan.ai/agent/ec_tasks/resume.py)

Conceptually:

1. the node defines `inputsValues.eventMonitors.content`
2. the browser session starts session-scoped monitors
3. a monitor detects a matching event
4. the monitor emits a normalized `browser_event`
5. the runner dispatches the event to waiting workflows
6. a `pend_event` node resumes when `browserEventLabel` matches the monitor label

## 3. Lifecycle

### 3.1 Session-scoped ownership

Event monitors are owned by the browser session capability, not by a site-specific strategy.

This means:

- monitors can stay alive across loop iterations
- browser-use `done()` does not have to delete monitor definitions
- the workflow can return to `pend_event` while monitors continue to observe the session

### 3.2 `done()` behavior

`done()` means the current `browser_automation` node invocation is complete.

It does not necessarily mean the whole skill is complete.

The browser node supports:

- `keep`
  - `done()` does not stop active monitors
- `stop`
  - `done()` stops active monitors for the current session

For looped workflows like:

- `loop -> browser_automation -> pend_event`

the usual setting is:

- `On Done = keep`

because monitors need to remain alive while `pend_event` waits for the next event.

## 4. Event Routing

Monitors emit a normalized browser event envelope and dispatch through the existing runner path.

The important routing behavior is:

- monitor config `label`
- `pend_event.inputsValues.browserEventLabel.content`

These must match.

Example:

```json
{
  "eventType": "browser_event",
  "browserEventLabel": "conversation_became_active"
}
```

When a monitor with label `conversation_became_active` fires, the waiting `pend_event` resumes.

## 5. Supported Source Types

Current source types recognized by config:

- `http_polling`
- `websocket`
- `sse`
- `dom_mutation`
- `cdp_raw`

Current implementation status:

- `http_polling`: implemented
- `websocket`: implemented
- `sse`: implemented
- `dom_mutation`: implemented
- `cdp_raw`: not implemented yet

Important note:

- `dom_mutation` currently means independent DOM snapshot + diff loop
- it is not a true browser-native `MutationObserver` subscription path yet

## 6. Frequency Model

### 6.1 HTTP polling

`http_polling` is passive interception.

It does not generate browser requests by itself.
It only observes requests the page is already making.

So its effective frequency is controlled by the site, not by our monitor config.

Example:

- if the page posts to `/batch_get_params` every 2 seconds, the monitor sees events every 2 seconds

### 6.2 WebSocket

WebSocket monitoring is event-driven.

No polling interval applies.

### 6.3 SSE

SSE monitoring is event-driven.

No polling interval applies.

### 6.4 DOM mutation

`dom_mutation` now runs in its own independent async loop.

This is important:

- it is no longer tied to browser-use step cadence
- it no longer waits for an LLM call between checks

The relevant parameter is:

- `domCheckIntervalMs`

Current behavior:

- default: `250`
- minimum enforced: `50`

This loop repeatedly:

1. queries DOM state
2. normalizes items
3. diffs against the previous snapshot
4. emits a `browser_event` if the configured change condition is met

## 7. Monitor Parameters

The node editor writes monitor config into:

- `data.inputsValues.eventMonitors.content`

Each item is a monitor config object.

### 7.1 Common fields

#### `id`

Stable internal id for the monitor.

Example:

```json
"id": "mon_conversation_list"
```

#### `label`

Semantic event label used by workflow routing.

This should match `pend_event.browserEventLabel`.

Example:

```json
"label": "conversation_became_active"
```

#### `enabled`

Whether this monitor is enabled.

Example:

```json
"enabled": true
```

#### `sourceType`

Source type:

- `http_polling`
- `websocket`
- `sse`
- `dom_mutation`
- `cdp_raw`

Example:

```json
"sourceType": "dom_mutation"
```

#### `urlPatterns`

List of URL substrings or regex-like patterns used to scope the monitor.

Meaning depends on source type:

- `http_polling`: request URL patterns
- `websocket`: WS URL patterns
- `sse`: SSE request URL patterns
- `dom_mutation`: page URL patterns for the DOM extractor

Example:

```json
"urlPatterns": ["workspace-chat", "control"]
```

### 7.2 HTTP polling fields

#### `methods`

Allowed HTTP methods.

Example:

```json
"methods": ["POST"]
```

#### `contentFilters`

Body substring filters.

The monitor dispatches only when a body filter matches.

Example:

```json
"contentFilters": ["has_new", "session_id"]
```

#### `minBodyLength`

Ignore short bodies.

Example:

```json
"minBodyLength": 10
```

### 7.3 WebSocket fields

#### `frameDirection`

Which frames to observe:

- `incoming`
- `outgoing`
- `both`

Example:

```json
"frameDirection": "incoming"
```

### 7.4 SSE fields

#### `sseEventTypes`

Optional SSE event names to match.

Example:

```json
"sseEventTypes": ["message", "update"]
```

### 7.5 DOM mutation fields

#### `domSelector`

Legacy root selector hint.

This still exists, but the preferred modern path is the advanced extractor JSON in `cdpFilterExpr`.

Example:

```json
"domSelector": "#chantListScrollArea"
```

#### `domAttributes`

Whether attribute mutations are relevant.

Currently this is mostly metadata/config compatibility. The active DOM monitor is based on periodic normalized diff, not low-level attribute-event callbacks.

#### `domChildList`

Whether child-list changes are relevant.

#### `domSubtree`

Whether subtree changes are relevant.

#### `domCheckIntervalMs`

Independent DOM check interval in milliseconds.

This is the key real-time parameter for DOM monitors.

Example:

```json
"domCheckIntervalMs": 100
```

### 7.6 CDP raw fields

#### `cdpDomain`

Reserved for future raw CDP event support.

#### `cdpEventMethod`

Reserved for future raw CDP event support.

#### `cdpFilterExpr`

For `dom_mutation`, this currently carries advanced extractor JSON.

For future `cdp_raw`, this can also carry raw CDP filter expressions.

## 8. Advanced DOM Extractor JSON

For `dom_mutation`, the advanced extractor schema is stored in:

- `cdpFilterExpr`

The runtime parses it as JSON.

Important fields:

### `page_url_patterns`

List of page URL substrings the extractor should match.

### `roots`

Root selectors to search under.

### `items`

List extraction rules. Each item rule describes:

- repeated item selector
- extracted fields

### `identity.key_fields`

Composite identity fields.

This is critical for real-world portals that do not expose a stable conversation id.

Example:

```json
"identity": {
  "key_fields": ["name", "time_text", "preview"]
}
```

### `emit_on`

Change mode:

- `added`
- `changed`
- `reordered`
- `top_changed`
- `added_or_reordered`

### `top_n`

Used by `top_changed` and top-list oriented monitoring.

### `empty_text_patterns`

Page text markers that indicate empty state.

## 9. Sample Configs

### 9.1 Chat conversation list monitor

This is suitable for a left-panel inbox where conversations move to the top when new customer messages arrive.

```json
{
  "id": "mon_recent_conversations",
  "label": "conversation_became_active",
  "enabled": true,
  "sourceType": "dom_mutation",
  "urlPatterns": ["workspace-chat", "chantListScrollArea"],
  "domSelector": "#chantListScrollArea",
  "domChildList": true,
  "domSubtree": true,
  "domAttributes": false,
  "domCheckIntervalMs": 100,
  "cdpFilterExpr": "{\n  \"page_url_patterns\": [\"workspace-chat\", \"chantListScrollArea\"],\n  \"roots\": [\"#chantListScrollArea\", \".pigeonChatScrollBox\"],\n  \"items\": [\n    {\n      \"selector\": \"[data-qa-id='qa-conversation-chat-item'][data-kora='conversation']\",\n      \"fields\": {\n        \"name\": {\n          \"source\": \"text\",\n          \"selector\": \".MP1bk3ccfHC9V2SnPCGD, .Jv6FtqUv5VoYARd2pp4y\"\n        },\n        \"preview\": {\n          \"source\": \"text\",\n          \"selector\": \".lF_M7QiFB0ukHWpMfQde\"\n        },\n        \"time_text\": {\n          \"source\": \"text\",\n          \"selector\": \".CEnLM8MEGksTdgi_8Lqf\"\n        }\n      }\n    }\n  ],\n  \"identity\": {\n    \"key_fields\": [\"name\", \"time_text\", \"preview\"]\n  },\n  \"emit_on\": \"added_or_reordered\",\n  \"top_n\": 10,\n  \"empty_text_patterns\": [\"最近联系人\", \"星标用户\", \"最近搜索\"]\n}"
}
```

### 9.2 Chat-page HTTP polling monitor

This is suitable when the chat page already polls a backend endpoint.

```json
{
  "id": "mon_chat_polling",
  "label": "chat_message_added",
  "enabled": true,
  "sourceType": "http_polling",
  "urlPatterns": ["/batch_get_params"],
  "methods": ["POST"],
  "contentFilters": ["has_new", "session_id"],
  "minBodyLength": 20
}
```

### 9.3 WebSocket monitor

```json
{
  "id": "mon_ws_updates",
  "label": "realtime_message_update",
  "enabled": true,
  "sourceType": "websocket",
  "urlPatterns": ["/ws", "/socket"],
  "frameDirection": "incoming",
  "contentFilters": ["message", "session_id"]
}
```

### 9.4 SSE monitor

```json
{
  "id": "mon_sse_updates",
  "label": "stream_update",
  "enabled": true,
  "sourceType": "sse",
  "urlPatterns": ["/events", "/stream"],
  "sseEventTypes": ["message", "update"],
  "contentFilters": ["session_id"]
}
```

## 10. Persistence and Self-Modification

The system now supports runtime monitor refinement followed by persistence back into the skill files.

Relevant tool:

- `bu_persist_session_monitors_to_skill`

Behavior:

- persists the current configured session monitors back into:
  - `<skill>/diagram_dir/<name>_skill.json`
  - `<skill>/diagram_dir/<name>_skill_bundle.json`

Recommended policy:

1. load or inspect existing saved monitor config
2. validate quickly
3. rediscover only if needed
4. persist only after the refined config is validated and reusable

Do not persist speculative low-confidence configs.

## 11. Prompting Guidance

For browser-use prompts, the recommended pattern is:

1. reuse saved monitor config first
2. validate quickly
3. only rediscover if validation fails
4. upsert live session monitor
5. persist validated improvements
6. finish current invocation with `done()`

For looped workflows:

- `loop -> browser_automation -> pend_event`

the node should usually use:

- `On Done = keep`

so monitors remain alive while `pend_event` waits for the next event.

## 12. Current Limitations

### 12.1 `cdp_raw`

The schema exists, but runtime support is not implemented yet.

### 12.2 DOM monitor name

`dom_mutation` currently means independent DOM snapshot + diff loop.

It is not yet a true browser-native `MutationObserver` pipeline.

### 12.3 HTTP polling cadence

`http_polling` does not actively poll.

It only observes the page's own requests.

### 12.4 Tool-driven persistence

Monitor persistence is explicit.

It does not happen automatically on every `done()` because that would save bad experimental configs too easily.

## 13. Recommended Defaults

For chat portals:

- conversation list monitor:
  - `sourceType = dom_mutation`
  - `emit_on = added_or_reordered`
  - `domCheckIntervalMs = 100` or `150`
  - composite `identity.key_fields`

- chat message monitor:
  - `sourceType = http_polling` when the page already polls
  - `sourceType = websocket` when the site is WS-based
  - `sourceType = sse` when the site is SSE-based

## 14. Files of Interest

See [Section 23](#23-files-of-interest-updated) for the updated and expanded file list.

---

## 15. DOM Trimming and Focus

Added 2026-03-29. Commits `7018130cd`, `48b9bc968`.

Browser automation nodes in real-time customer service generate large DOM snapshots that waste tokens and slow responses. Two mechanisms now exist to reduce DOM size before it reaches the LLM.

### 15.1 DOM Focus Selector

A CSS selector filter that uses CDP to hide all elements NOT matching the given selectors before DOM extraction.

**How it works:**

1. Before each browser-use step, CDP evaluates the selector(s)
2. All elements outside the matched subtrees are set to `display: none`
3. browser-use extracts only the visible (relevant) DOM
4. After the step, visibility is restored

**Configuration:**

In the skill editor, the browser automation node has a `DOM Focus Selector` field:

```
#messages, .chat-input, .conversation-list
```

Multiple selectors are comma-separated. The runtime reads this from:

```
data.inputsValues.domFocusSelector.content
```

**When to use:**

- Chat portals where the agent only needs the message area and input box
- Pages with heavy navigation chrome, ads, or sidebar content
- Any scenario where the full DOM exceeds ~20K characters

### 15.2 DOM Limit

A hard cap on the maximum clickable elements character length returned by browser-use.

**Configuration:**

In the skill editor, the `DOM Limit (chars)` field accepts a number:

- Minimum: `1000`
- Maximum: `50000`
- Blank: uses browser-use's adaptive default (~18K-25K depending on model context size)

The runtime reads this from:

```
data.inputsValues.domLimit.content
```

And passes it as `max_clickable_elements_length` to the browser-use agent.

**When to use:**

- When DOM Focus Selector alone is not sufficient
- As a safety net to prevent runaway token usage
- For models with smaller context windows

### 15.3 Recommended settings for chat portals

| Setting | Recommended Value | Rationale |
|---------|-------------------|-----------|
| DOM Focus Selector | `#chatArea, .chat-input, .msg-list` | Only extract chat-relevant DOM |
| DOM Limit | `8000` - `15000` | Sufficient for message history + input |
| domCheckIntervalMs | `100` - `150` | Fast event detection |

These settings together can reduce per-step token usage by 60-80% compared to full-page DOM extraction.

---

## 16. Browser Slot System

Added 2026-03-29. Commits `7018130cd`, `48b9bc968`.

The browser slot system enables horizontal scaling across multiple Chrome instances on a single machine, with explicit capacity tracking per instance.

### 16.1 Concept

A **browser slot** represents one Chrome instance identified by its CDP port. Each slot has:

- `cdp_port`: the Chrome DevTools Protocol port (e.g., 9228, 9229)
- `max_agents`: maximum concurrent agents allowed on this Chrome instance
- `user_data_dir`: Chrome user data directory (for profile isolation)
- `profile`: Chrome profile directory name
- `status`: `idle` | `active` | `full` | `error`
- `assigned_agents`: list of currently assigned agent IDs

### 16.2 Configuration

Browser slots are configured in **Settings > Browser**:

```json
{
  "browser_slots": [
    {
      "cdp_port": 9228,
      "max_agents": 12,
      "user_data_dir": "C:/Users/songc/AppData/Local/Google/Chrome/User Data",
      "profile": "Default"
    },
    {
      "cdp_port": 9229,
      "max_agents": 8,
      "user_data_dir": "C:/BrowserProfiles/Chrome2",
      "profile": "Profile1"
    }
  ],
  "browser_max_agents_per_instance": 12
}
```

If `browser_slots` is empty, the system falls back to legacy port-pool mode with `browser_max_agents_per_instance` as the global cap.

The settings are exposed via `general_settings.py` properties:

- `browser_slots` (list of dicts)
- `browser_max_agents_per_instance` (int, 0 = use built-in default of 12)

### 16.3 Slot assignment

When a browser automation node starts, the runtime resolves a Chrome instance:

1. **Task state** is checked first: if the task already has `browser_slot_id` or `cdp_port` from a previous run, the same slot is reused (sticky assignment)
2. **Skill editor config** is checked next: the node can specify an explicit `cdpPort` or enable `cdpPortAuto` (auto-assign)
3. **Auto-assign** (`pick_auto_slot`): selects the slot with the most remaining capacity

```
pick_auto_slot(agent_id):
  - if agent is already assigned to a slot, return that slot (sticky)
  - otherwise, find slot with status != error and lowest load ratio
  - assign agent and return slot
```

When the agent's browser session ends, `release_agent(agent_id)` is called to free the slot capacity.

### 16.4 Skill editor UI

The browser automation node editor has a `CDP Port Auto` checkbox:

- **Unchecked** (default): uses the explicit `cdpPort` field value (default 9228)
- **Checked**: port is auto-assigned from the slot pool at runtime

### 16.5 Monitoring

`BrowserManager.get_slots_summary()` returns the current state of all slots:

```python
[
    {"id": "slot_9228", "cdp_port": 9228, "max_agents": 12, "assigned": 5, "status": "active"},
    {"id": "slot_9229", "cdp_port": 9229, "max_agents": 8, "assigned": 8, "status": "full"},
]
```

### 16.6 Capacity planning

| Agents | Chrome Instances | Suggested Config |
|--------|-----------------|-----------------|
| 1-12 | 1 | Single slot, cdp_port 9228, max_agents 12 |
| 13-24 | 2 | Two slots on ports 9228 + 9229 |
| 25-36 | 3 | Three slots, consider separate user data dirs |

Each Chrome instance consumes ~500MB-2GB RAM depending on the pages loaded. Plan memory accordingly.

---

## 17. Immediate Response Optimization

Added 2026-03-29. Commits `7018130cd`, `48b9bc968`.

For real-time customer service, response latency is critical. The system enforces a strict 2-step execution contract for chat agent invocations.

### 17.1 Problem

Without constraints, browser-use agents tend to:

1. Navigate to the chat page (even if already there)
2. Read messages
3. Compose a reply
4. Send the reply
5. Scroll to verify the reply appeared
6. Read the page again to confirm
7. Finally call `done()`

This results in 5-7 browser-use steps per response, taking 15-30 seconds.

### 17.2 Solution: 2-step runtime scope contract

The system prompt for customer service chat agents now enforces:

```
Step 1: Read the page
  - Navigate to assigned chat tab if needed
  - Read the latest customer message
  - Decide reply

Step 2: Reply and finish
  - Type reply into chat input
  - Click Send (or press Enter)
  - Immediately call done(success=true)
  - Do NOT verify the send worked
```

### 17.3 Forbidden operations

The prompt explicitly forbids time-wasting actions:

- Do NOT call `bu_send_chat`, `bu_list_session_monitors`, or other extension tools during reply
- Do NOT assign or re-assign sessions
- Do NOT verify, check, or validate that the message appeared
- Do NOT scroll to confirm
- Do NOT take extra steps after sending

### 17.4 Results

| Metric | Before | After |
|--------|--------|-------|
| Steps per response | 5-7 | 2 |
| Response latency | 15-30s | 3-8s |
| Tokens per response | 8K-15K | 2K-5K |

The key insight is that verification is unnecessary: if the send fails, the next event-driven invocation will detect the unsent state.

---

## 18. Inter-Agent Chat Communication

Added 2026-03-28. Commits `48b9bc968`, `8b79e15b4`.

Browser-use extension tools now support agent-to-agent messaging for multi-agent customer service scenarios (e.g., front-desk router + specialist agents).

### 18.1 Tools

**`bu_send_chat(sender_agent_id, recipient_agent_id, message, ...)`**

Send a chat message to another agent. Supports:

- Recipient resolution by ID or name (case-insensitive)
- Auto-generated `chat_id` if not provided
- Message types: `text`, `form`, `notification`
- Attachments
- Stale agent ID fallback (resolves historical IDs to current agents)

**`bu_list_chat_agents()`**

List all available agents with their current task/skill assignments. Used for agent discovery before sending.

### 18.2 Auto-dispatch (load balancing)

When an agent repeatedly targets the same recipient within a 30-second window, the system auto-rotates to peer agents (agents with matching skills):

```
Agent A sends to Agent B (chat agent)  → delivered to B
Agent A sends to Agent B again         → auto-routed to Agent C (peer)
Agent A sends to Agent B again         → auto-routed to Agent D (peer)
```

This prevents work concentration on a single agent and enables organic load balancing across a swarm.

**Requirements:**

- `bu_list_chat_agents()` must be called first (discovery step)
- Peer agents must share the same skill set
- Dispatch tracking expires after 30 seconds of inactivity

### 18.3 Typical multi-agent flow

```
Front-desk agent (monitors conversation list)
  ↓ event: new customer detected
  ↓ bu_send_chat → service agent A
  ↓ event: another customer
  ↓ bu_send_chat → service agent B (auto-dispatched)
  ↓ event: another customer
  ↓ bu_send_chat → service agent C (auto-dispatched)

Service agent A/B/C (each handles assigned customer)
  ↓ reads customer message
  ↓ types reply
  ↓ done()
  ↓ waits for next event via pend_event
```

---

## 19. Extension Tools Reference (Real-Time)

Added 2026-03-28. Commits `48b9bc968`, `8b79e15b4`.

New browser-use extension tools for real-time scenarios:

### 19.1 Session monitor tools

| Tool | Purpose |
|------|---------|
| `bu_list_session_monitors` | List all active monitors on current browser session |
| `bu_upsert_session_monitor` | Create or update a monitor (id-based upsert) |
| `bu_remove_session_monitor` | Delete a monitor by ID |
| `bu_get_session_monitor_snapshot` | Query current monitor state/data |
| `bu_reconfigure_event_monitor` | Adjust monitor settings at runtime |
| `bu_persist_session_monitors_to_skill` | Save monitor config back to skill JSON |

### 19.2 DOM inspection tools

| Tool | Purpose |
|------|---------|
| `bu_inspect_dom_regions` | Extract DOM regions by CSS selectors |
| `bu_discover_chat_adapter` | Auto-detect chat UI patterns (input box, send button, message list) |
| `bu_normalize_page_state` | Standardize page structure for comparison |
| `bu_diff_normalized_state` | Compare two page states to detect changes |

### 19.3 Communication tools

| Tool | Purpose |
|------|---------|
| `bu_send_chat` | Send message to another agent |
| `bu_list_chat_agents` | List available agents for messaging |

### 19.4 Data tools

| Tool | Purpose |
|------|---------|
| `bu_rag_query` | Query the knowledge base (RAG) |
| `extract_dom` | Extract structured data from page |

---

## 20. Token Tracking Enhancements

Added 2026-03-27 through 2026-03-29. Commits `8b79e15b4`, `060f2894c`.

Fine-grained token tracking is now available for all token-consuming operations.

### 20.1 Tracked sources

| Source Type | Description | Where Tracked |
|-------------|-------------|---------------|
| `skill_llm_node` | LLM node invocation | build_node.py |
| `skill_browser_llm_call` | browser-use agent's internal LLM calls | llm_utils.py |
| `mcp_rag` | RAG tool calls (embedding, query) | via record_mcp_usage |
| `mcp_image_gen` | Image generation tools | via record_mcp_usage |
| `skill_editor` | Skill editor LLM calls | skill_editor/token_tracker.py |

### 20.2 Fields recorded per invocation

| Field | Type | Description |
|-------|------|-------------|
| `skill_name` | string | Skill that triggered the call |
| `source_type` | string | Category (see above) |
| `vendor` | string | Provider: openai, anthropic, google, deepseek, ollama |
| `model` | string | Model name: gpt-4o, claude-3-sonnet, etc. |
| `input_tokens` | int | Prompt/input token count |
| `output_tokens` | int | Completion/output token count |
| `start_time` | datetime | Call start time (ms precision) |
| `end_time` | datetime | Call end time (ms precision) |
| `duration_ms` | int | Call duration in milliseconds |
| `cost_usd` | float | Estimated cost based on pricing table |

### 20.3 Storage

- **Database**: `token_usage` table (SQLAlchemy, SQLite)
- **JSONL ledger**: `runlogs/token_usage_bookings.jsonl` (append-only audit trail)

### 20.4 Analytics UI

The Account page (accessible via double-click on the LED token display in the top header bar) includes an expandable Token Usage Analytics section with:

1. **Bar chart**: Stacked input/output tokens over time. Period selector: 24h, 3d, 1w, 1m, 12m, 36m. CSV download.
2. **Pie charts**: Double-click any bar to see per-model and per-skill breakdown. Shows total LLM invocation count.
3. **Usage alarms**: Daily and monthly progress bars with configurable thresholds. Green below limit, red above.

---

## 21. Hot Path (LLM Bypass)

Added 2026-04. The hot path is a latency optimization that skips the LLM entirely for structured, predictable event responses. It cuts Phase-2 latency from ~15s (LLM think + multi-step) to ~2s (direct tool calls).

Two implementations exist. Both run after browser session setup (CDP connection is live) but before the browser-use agent is invoked.

### 21.1 Built-in chat message reply bypass

Location: `build_node.py` (post-setup HOT-PATH block, ~line 9540).

Trigger conditions (all must be true):

- the incoming event is **not** a `browser_event` (i.e. it is a task invocation with a payload)
- the payload contains both `response_text` and `customer_name` (or `customer_id`)
- the extension tools registry has both a `*_open_session` and a `*_send_message` tool registered

When triggered:

1. calls `*_open_session(customer_name=...)` to navigate to the customer's chat
2. waits 0.5s
3. calls `*_send_message(text=response_text)` to type and send the reply
4. clears `state.input` and payload attributes to prevent duplicate sends
5. returns immediately with `state.result.llm_result = {"hot_path": true, "action": "<open>+<send>", "customer": "..."}`

If either tool call fails, the hot path aborts silently and falls back to the normal LLM path.

### 21.2 Configurable action templates

Location: `build_node.py` (~line 7435).

This variant lets users define custom trigger/action rules in the node editor. It runs **before** the built-in variant.

#### Configuration

Stored in `data.inputsValues.hotPathActions.content` as JSON:

```json
[
  {
    "trigger": {
      "event_type": "chat_message",
      "has_fields": ["response_text", "customer_name"]
    },
    "actions": [
      {"tool": "feige_open_session", "args": {"customer_name": "{{customer_name}}"}},
      {"tool": "feige_send_message", "args": {"text": "{{response_text}}"}}
    ]
  }
]
```

#### Trigger matching

- `trigger.event_type`: must match the current event's `event_type` (from `state.prompt_refs.events`)
- `trigger.has_fields`: all listed fields must be present in the parsed `state.input` payload

Only the first matching rule is attempted.

#### Action execution

For each action in the `actions` array:

1. resolve `{{field}}` placeholders from the payload
2. look up the tool in the extension tools registry
3. call with `browser_session` if the tool's signature expects it
4. wait 0.3s between actions
5. if any action fails, abort the sequence

On success, returns with `state.result.llm_result = {"hot_path": true, "hot_path_type": "configurable"}`.

#### GUI status

There is currently no GUI editor for `hotPathActions`. It must be set manually in the skill JSON. A future node editor form is planned.

### 21.3 Execution order

```
1. Configurable hot path (hotPathActions)  — if config exists and trigger matches → return
2. Built-in chat reply hot path            — if response_text + customer_name → return
3. Normal LLM invocation                   — full browser-use agent run
```

The `_hot_path_done` flag ensures only one variant runs per invocation.

---

## 22. GUI Node Editor Field Reference

The browser automation node editor (`gui_v2/src/modules/skill-editor/nodes/browser-automation/form-meta.tsx`) exposes the following configuration fields. All values are stored under `data.inputsValues.<fieldName>.content`.

### 22.1 General settings

| Field | Type | Description |
|-------|------|-------------|
| `browserType` | select | Browser type (chromium, firefox, webkit) |
| `browserDriver` | select | Driver mode (native, playwright) |
| `cdpPort` | string | Explicit Chrome DevTools port (default 9228) |
| `cdpPortAuto` | boolean | Auto-assign port from slot pool (overrides cdpPort) |
| `runEnvironment` | select | Execution environment: full_local, passive_local, hybrid_cloud, full_cloud |
| `profile` | select | Chrome profile to use (fetched from backend) |
| `shopName` | select | Shop/store name for file organization |
| `customShopName` | string | Custom shop name (when shopName = "custom") |

### 22.2 LLM settings

| Field | Type | Description |
|-------|------|-------------|
| `modelProvider` / `provider` | select | LLM provider (openai, anthropic, etc.) |
| `modelName` / `model` | select | Model name |
| `useThinking` | boolean | Enable extended thinking (for reasoning models like Qwen) |
| `useVision` | boolean | Enable vision/screenshot input to the LLM |

### 22.3 Privacy and safety

| Field | Type | Description |
|-------|------|-------------|
| `privacyStrategy` | select | Privacy mode: none, mask_pii, anonymize |
| `enableJudge` | boolean | Enable secondary LLM judge for action verification |

### 22.4 Performance settings

| Field | Type | Description |
|-------|------|-------------|
| `flashMode` | boolean | Enable flash mode for minimal-latency responses |
| `maxSteps` | number | Max browser-use steps per invocation (1-100) |
| `maxActionsPerStep` | number | Max actions per browser-use step (1-20) |
| `nodeTimeoutSeconds` | number | Hard timeout for the node (minimum 300s) |
| `domFocusSelector` | string | CSS selector to focus DOM extraction (hide non-matching elements) |
| `domLimit` | number | Hard cap on DOM character length (1000-50000) |
| `loopHistoryMode` | select | History handling across pend_event loop iterations |
| `actionableField` | string | Per-item field name marking actionable items |

### 22.5 Loop History Mode

Controls how the browser-use agent's history is handled when reused across pend_event loop iterations.

| Value | Behavior |
|-------|----------|
| `clear` (default) | Wipe history on each iteration. Best for stateless flows (e.g. front-desk dispatch). |
| `trim:5` / `trim:10` / `trim:20` | Keep last N history items (rolling window). Useful when some recent context helps. |
| `accumulate` | Keep all history. Only for short-lived loops where cross-round memory is intentional. |

### 22.6 Actionable Field

When set, the browser-event task hint emits a deterministic `actionable_items` list filtered from raw event items instead of dumping every item. The LLM receives a hard rule that it MUST process each listed entry.

This defeats LLM hallucination of "already handled" claims since the list is ground truth. Domain-agnostic: works for customer support (pending reply), inbox triage (unread), queue processing, form-filling checklists — any extractor that populates this field.

Leave empty to preserve legacy raw-items behavior.

### 22.7 Event Monitors section (collapsible)

The event monitors section is collapsible (click to expand). It contains:

#### `eventMonitorDonePolicy`

Select dropdown: `keep` or `stop`. Controls whether monitors stay alive when the browser node calls `done()`.

#### Monitor list

Each monitor item has:

**Common fields:**

| Field | Description |
|-------|-------------|
| `label` | Semantic event label (must match `pend_event.browserEventLabel`) |
| `sourceType` | Monitor type: http_polling, websocket, sse, dom_mutation, cdp_raw |
| `urlPatterns` | URL substring/regex patterns (comma-separated) |
| `enabled` | Toggle switch |

**HTTP polling fields:** `methods`, `contentFilters`, `minBodyLength`

**WebSocket fields:** `frameDirection` (incoming/outgoing/both), `contentFilters`

**SSE fields:** `sseEventTypes`, `contentFilters`

**DOM mutation fields:**

| Field | Description |
|-------|-------------|
| `domSelector` | Legacy root selector |
| `domCheckIntervalMs` | Polling interval (default 250ms, min 50ms) |
| `domChildList` | Watch child list changes |
| `domSubtree` | Watch subtree changes |
| `domAttributes` | Watch attribute changes |

**DOM extractor fields (advanced, inline in form):**

These fields replace the raw `cdpFilterExpr` JSON editor for common cases. The form auto-rebuilds `cdpFilterExpr` from these values.

| Field | Type | Description |
|-------|------|-------------|
| `domPageUrlPatterns` | string (comma-sep) | Page URL patterns the extractor matches |
| `domExtractorRoots` | string (comma-sep) | Root CSS selectors to search under |
| `domItemSelector` | string | Repeated item CSS selector |
| `domKeyFields` | string (comma-sep) | Composite identity fields (e.g. "session, time_text, preview") |
| `domEmitOn` | select | Change mode: added, changed, reordered, top_changed, added_or_reordered |
| `domTopN` | number | Top-N items for top_changed mode (default 10) |
| `domEmptyTextPatterns` | string (comma-sep) | Text markers indicating empty state |
| `domSessionSource` | select | Session field source: attr, text, closest_text |
| `domSessionSelector` | string | CSS selector for session field |
| `domSessionAttr` | string | Attribute name for session field |
| `domSessionRegex` | string | Regex to extract session value |
| `domSessionGroup` | number | Regex capture group |
| `domChatUrlSource` | select | Chat URL field source: attr, text |
| `domChatUrlSelector` | string | CSS selector for chat URL |
| `domChatUrlAttr` | string | Attribute for chat URL (default "href") |
| `domNameSource` | select | Name field source: text, closest_text, attr |
| `domNameSelector` | string | CSS selector for name field |
| `domNameClosest` | string | Closest ancestor selector for name |
| `domNameRegex` | string | Regex to extract name |
| `domNameGroup` | number | Regex capture group |
| `domNameSplitBefore` | string | Split text before this delimiter |

---

## 23. Files of Interest (Updated)

- runtime monitor engine:
  - [event_monitor.py](agent/ec_skills/browser_use_extension/event_monitor.py)
- monitor data models:
  - [monitor_models.py](agent/ec_skills/browser_use_extension/monitor_models.py)
- session capability:
  - [event_monitor_capability.py](agent/ec_skills/browser_use_extension/event_monitor_capability.py)
- extension tools:
  - [extension_tools_service.py](agent/ec_skills/browser_use_extension/extension_tools_service.py)
  - [extension_tools_views.py](agent/ec_skills/browser_use_extension/extension_tools_views.py)
- browser node runtime (hot path + all settings):
  - [build_node.py](agent/ec_skills/build_node.py)
- browser node editor UI:
  - [form-meta.tsx](gui_v2/src/modules/skill-editor/nodes/browser-automation/form-meta.tsx)
  - [index.ts](gui_v2/src/modules/skill-editor/nodes/browser-automation/index.ts)
- browser slot management:
  - [browser_manager.py](gui/manager/browser_manager.py)
- general settings (slot config):
  - [general_settings.py](gui/config/general_settings.py)
- event routing:
  - [runner.py](agent/ec_tasks/runner.py)
- inter-agent chat tools:
  - [chat_tools.py](agent/mcp/server/chat_utils/chat_tools.py)
- token tracking:
  - [token_tracker.py](agent/ec_skills/token_tracker.py)
- condition evaluator (cycle-detection fix):
  - [flowgram2langgraph.py](agent/ec_skills/flowgram2langgraph.py)

---

## 24. Auto-Dispatch (LLM-Free Agent Routing)

Added 2026-04-19.

Auto-dispatch is a configurable mechanism that routes actionable items from browser events directly to agents **without invoking the LLM**. It replaces the LLM's "Phase 1" decision (which agent should handle which customer) with a deterministic, sub-second dispatch.

### 24.1 When it fires

Auto-dispatch runs inside the browser automation node, after the event monitor delivers a `browser_event` with actionable items, but **before** the browser-use LLM agent is invoked. If auto-dispatch handles the event, the LLM is skipped entirely for that iteration.

```
browser_event arrives (with actionable_items)
  ↓
auto-dispatch config present?  ──no──→  LLM handles everything (legacy path)
  ↓ yes
trigger matches? ──no──→  LLM handles everything
  ↓ yes
candidates available? ──no──→  LLM handles everything
  ↓ yes
dispatch items to agents ──→ return immediately (hot_path_type: "auto_dispatch")
```

### 24.2 Configuration

Stored in `data.inputsValues.autoDispatch.content` as a JSON object:

```json
{
  "trigger": {
    "event_type": "browser_event",
    "require_actionable": true
  },
  "agent_selection": {
    "strategy": "first_available",
    "filter_by_tasks": ["客户应答"],
    "affinity_ttl_s": 1800
  },
  "payload_template": {
    "customer_id": "{{customer_id || identity_key || customer_name}}",
    "customer_name": "{{customer_name || name}}",
    "latest_message": "{{last_message || latest_message}}"
  },
  "item_filter": {
    "required_fields": ["customer_name", "last_message"]
  },
  "dispatch": {
    "tool": "send_chat",
    "dedup": true,
    "per_item": true
  }
}
```

All fields are optional with sensible defaults. Only `trigger.event_type` is needed for a minimal config.

### 24.3 Template resolution

Payload templates use `{{field}}` placeholders resolved from each actionable item's data. The `||` operator provides fallback fields:

```
{{customer_id || identity_key || customer_name}}
```

Tries `customer_id` first, then `identity_key`, then `customer_name`. Uses the first non-empty value. Non-template strings (no `{{`/`}}`) pass through as-is.

Implementation: `_resolve_template()` in `build_node.py:43`.

### 24.4 Agent selection strategies

#### `first_available` (default — load-aware)

Picks the candidate with the **fewest pending tasks**. Ties broken by list order.

Load is measured by querying each agent's `runner._task_states` and counting entries where `_done` is `False`. This is cached once per dispatch batch to avoid repeated lookups.

```
candidate A: 3 pending tasks
candidate B: 1 pending task   ← selected
candidate C: 2 pending tasks
```

#### `round_robin`

Rotates through candidates. When `per_item: true`, each actionable item advances the index independently, so a batch of 3 items dispatches to 3 different agents (if 3+ candidates exist).

The round-robin index is stored per `node_name` in a module-level dict and persists across invocations within the same process.

### 24.5 Affinity / sticky routing

Before any strategy runs, the dispatcher checks whether the customer was **previously assigned** to one of the current candidates. If so — and the assignment is fresher than `affinity_ttl_s` (default 1800s / 30 min) — the same agent is reused. This keeps an ongoing conversation on one agent.

```
customer "Alice" → agent B (first dispatch)
customer "Alice" → agent B (affinity hit, even if agent C has lower load)
  ... 35 min later ...
customer "Alice" → agent C (affinity expired, strategy picks lowest load)
```

The affinity table (`_auto_dispatch_affinity`) is module-level and survives across invocations. Stale entries (older than 2× TTL) are pruned after each dispatch batch.

The customer identity key is derived from the resolved `customer_id` or `customer_name` template field.

### 24.6 Candidate filtering

Candidates are filtered in two stages:

1. **Disabled agents excluded** — agents with `status == "disabled"` are never candidates.
2. **Task filter** — if `filter_by_tasks` is set, only agents whose `tasks` list intersects the filter are candidates. This implements basic capability matching (e.g., only agents assigned the "客户应答" task can receive customer chats).

If no candidates remain after filtering, auto-dispatch returns `None` and the LLM handles the event.

### 24.7 Dedup integration

When `dispatch.dedup` is `true` (default), each successful dispatch records the customer in the existing dedup caches (`_send_chat_dedup_cache` and `_send_chat_customer_last` in `extension_tools_service.py`). This prevents the same customer from being dispatched again within the dedup window (60s / 45s respectively).

### 24.8 Log markers

```
[AUTO-DISPATCH] sent 'Alice' → responder_1 (load=2) msg='{"customer_id":...}', node=browser_1
[AUTO-DISPATCH] 3/3 items dispatched, skipping LLM Phase 1, node=browser_1
[AUTO-DISPATCH] No candidate agents after filter (filter_by_tasks=['客户应答']), node=browser_1
```

### 24.9 Example: 飞鸽 customer service

For the Douyin 飞鸽 (Feige) customer service workflow:

- **Front-desk agent** runs a browser automation node with a DOM mutation event monitor watching the conversation list.
- When new customers appear, the event monitor emits a `browser_event` with actionable items (customers needing a reply).
- **autoDispatch** routes each customer to a responder agent using `first_available` (load-aware) strategy.
- **hotPathActions** (Section 21.2) on the responder agent delivers the reply back to the customer without LLM.

Combined, the two hot paths eliminate both LLM calls in the dispatch→reply loop:

```
browser_event (new customer)
  ↓ autoDispatch (no LLM) — ~50ms
responder agent receives task
  ↓ LLM generates reply text — ~3-8s
responder returns reply
  ↓ hotPathActions (no LLM) — ~1s
reply delivered to customer

Total: ~4-9s  (vs ~40s without hot paths)
```

---

## 25. Condition Evaluator Stability (Cycle Detection)

Added 2026-04-19.

### 25.1 Problem

The LangGraph condition evaluator in `flowgram2langgraph.py` uses `_unwrap_message_json()` to preprocess state before evaluating conditional edge expressions like `not state["result"]["llm_result"]["all_done"]`.

This function recursively traverses the state dict to extract JSON from markdown code blocks in message fields. However, LangGraph state can contain **shared sub-objects** — multiple top-level keys referencing the same inner dict (e.g., `state["result"]` and `state["tool_result"]` pointing to the same object). Without cycle detection, these shared references caused the same objects to be visited exponentially many times, exceeding Python's recursion limit (~3000).

The actual nesting depth was only 6-8 levels, but 18-45 shared-object "cycles" per evaluation caused the blowup.

### 25.2 Impact

When `_unwrap_message_json` hit the recursion limit, `_safe_eval_expr` caught the exception and returned `False`. For the expression `not state["result"]["llm_result"]["all_done"]`, returning `False` made the graph believe `all_done=True` — **prematurely terminating the loop** before reaching `pend_event`. The browser automation node never waited for events, breaking the entire real-time monitoring flow.

### 25.3 Fix

Three guards were added to `_unwrap_message_json()`:

1. **`_seen_ids` set** — tracks `id(obj)` of every visited container (dict or list). If an object has already been visited, it is returned as-is without recursing.
2. **Depth limit** (`_depth > 30`) — hard cap that returns the object unchanged.
3. **Diagnostic counters** — `_max_depth_hit`, `_cycles_broken`, and container count are logged after each evaluation for observability.

```python
_seen_ids = set()
_max_depth_hit = [0]
_cycles_broken = [0]

def _unwrap_message_json(obj, _depth=0):
    if _depth > 30:
        return obj
    obj_id = id(obj)
    if isinstance(obj, (dict, list)):
        if obj_id in _seen_ids:
            _cycles_broken[0] += 1
            return obj
        _seen_ids.add(obj_id)
    # ... normal traversal ...
```

### 25.4 Verification

After deployment, logs confirm zero condition-eval failures with typical stats:

```
[condition-eval] _unwrap stats: max_depth=7, cycles_broken=23, containers_visited=184
```

The fix is transparent — existing behavior is preserved for acyclic state, and shared objects are simply visited once.

---

## 26. Disabled Agent Filtering

Added 2026-04-19.

### 26.1 Problem

`list_chat_agents()` / `_get_all_agents()` in `chat_tools.py` returns **all** agents including disabled ones. When auto-dispatch (or the LLM) selected a disabled agent as the dispatch target, messages were queued but never consumed — the disabled agent has no running task runner.

### 26.2 Fix

Two filters were added:

1. **In `_try_auto_dispatch`** (line 160-163): candidates exclude agents with `status == "disabled"`.
2. **In the pre-resolved agent list** injected into state (line ~7678): the `_all_agents` list that the LLM sees is also filtered, so even the LLM fallback path won't target disabled agents.

```python
_all_agents = [
    a for a in _agents_result.get("agents", [])
    if a.get("status", "active") != "disabled"
]
```

---

## 27. Files of Interest (Addendum)

- auto-dispatch + template resolver + agent load helper:
  - [build_node.py](agent/ec_skills/build_node.py) (lines 43-310)
- condition evaluator cycle detection:
  - [flowgram2langgraph.py](agent/ec_skills/flowgram2langgraph.py) (lines ~197-250)
- dedup caches (used by auto-dispatch):
  - [extension_tools_service.py](agent/ec_skills/browser_use_extension/extension_tools_service.py)
- agent listing (disabled filter upstream):
  - [chat_tools.py](agent/mcp/server/chat_utils/chat_tools.py)
