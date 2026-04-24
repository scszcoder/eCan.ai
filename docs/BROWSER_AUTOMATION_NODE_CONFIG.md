# Browser Automation Node — Data-Driven Configuration

This document describes the JSON config blocks on the Browser Automation node that
replace what used to be hardcoded `if skill_name == "..."` branches in
`agent/ec_skills/build_node.py`. All blocks are optional; leaving them blank
yields the generic / non-skill-specific default behavior.

The goal is that the same Browser Automation node can service any skill —
what used to be special-cased for `rt_chat_bot`, `customer_front_desk`, etc.
is now driven by configuration on the node editor.

All blocks live on the node editor under **Node Behavior** (collapsible section
below **Hot-Path Optimization**). Each field is a string that is parsed as JSON
at runtime — non-JSON strings are tolerated (logged as non-fatal) and treated
as "unset".

---

## 1. `assignment` — Assignment Scope & URL Rewriting

Controls how the node reacts when a runtime "assignment scope" is present on
the state (e.g. `assignment_session_id`, `assignment_tab_id`,
`assignment_chat_url`, `assignment_customer_name`).

### Schema

```json
{
  "enabled": true,
  "require_any_of": ["session_id", "customer_id"],
  "on_missing": "skip_node",
  "scope_contract_template": "[ASSIGNED SCOPE]\nsession_id={session_id}\ntab_id={tab_id}\nchat_url={chat_url}\ncustomer_name={customer_name}",
  "navigate_field": "chat_url",
  "strip_url_regex": "https?://(?:127\\.0\\.0\\.1|localhost):9877/chat\\?session=[^\\s\"']+",
  "strip_url_replacement": "[assigned chat tab already open]"
}
```

### Fields

| Field | Default | Purpose |
|---|---|---|
| `enabled` | `true` | Master switch for the entire `assignment` block. |
| `require_any_of` | `[]` | Scope fields (from `session_id`, `customer_id`, `tab_id`, `chat_url`, `customer_name`) that must be present. If none are present, behavior follows `on_missing`. |
| `on_missing` | `"skip_node"` | `"skip_node"` → node returns `{all_done: False, work_done: False}` immediately; any other value → continue. |
| `scope_contract_template` | `""` | If non-empty, appended to the task text with `{session_id}`, `{tab_id}`, `{chat_url}`, `{customer_name}` substituted (missing keys render empty). |
| `navigate_field` | `"chat_url"` | Which scope field supplies the deterministic start URL. Overrides `_extract_preferred_start_url` heuristic when present. |
| `strip_url_regex` | `""` | If non-empty and the session is already started, this regex is applied to the combined task text to remove bare URLs (avoids re-navigating when the tab is already open). |
| `strip_url_replacement` | `"[assigned chat tab already open]"` | Replacement text for stripped URLs. |

### When to use

Set this when your skill receives tightly-scoped assignments from another agent
(e.g. a front-desk dispatcher pushes `{session_id, chat_url, tab_id}`). The
scope contract block is injected into the prompt so the LLM never confuses the
assigned customer with another one.

---

## 2. `preDispatch` — Pre-Dispatch Fast-Path

Replaces the hardcoded `customer_front_desk` front-desk fast-path. When the node
runs, it checks for an active browser event monitor with a matching label, and
if the monitor has reported actionable items, it opens a tab per item and
round-robin-assigns each to a discovered recipient agent — **bypassing the LLM
entirely**.

### Schema

```json
{
  "enabled": true,
  "source_monitor_label": "conversation_became_active",
  "require_url_path": "/control",
  "allowed_statuses": ["ok", "empty", "no_match"],
  "item_fields": {
    "session_id": ["session", "session_id", "customer_id"],
    "customer_name": ["customer_name", "name", "customer"],
    "chat_url": ["chat_url"]
  },
  "chat_url_template": "http://127.0.0.1:9877/chat?session={session_id}",
  "recipient_filter": {
    "task_keywords": ["feige_chat"],
    "skill_keywords": ["rt_chat_bot"]
  },
  "assignment_extra_fields": [],
  "dispatched_flag_attr": "_ecan_frontdesk_dispatched_all",
  "dispatch_state_attr": "_ecan_frontdesk_dispatch_state",
  "log_tag": "FrontDesk",
  "result_marker_key": "frontdesk_fastpath",
  "history_prefix": "frontdesk_fastpath"
}
```

### Fields

| Field | Default | Purpose |
|---|---|---|
| `enabled` | `false` | Master switch. Must be `true` to enable any pre-dispatch behavior. |
| `source_monitor_label` | `""` | **Required when enabled.** The `label` of the browser event monitor whose `last_items` array is the source of actionable items. |
| `require_url_path` | `""` | If non-empty, the monitor's `last_current_url` must contain this substring (empty disables the check). |
| `allowed_statuses` | `["ok", "empty", "no_match"]` | Monitor `last_status` values that are considered dispatch-ready. |
| `item_fields.session_id` | `["session", "session_id", "customer_id"]` | Fallback chain for the session/customer ID field on each item (first non-empty value wins). Required — items without a session id are skipped. |
| `item_fields.customer_name` | `["customer_name", "name", "customer"]` | Fallback chain for the customer's display name (optional). |
| `item_fields.chat_url` | `["chat_url"]` | Fallback chain for the per-session chat URL. |
| `chat_url_template` | `""` | If the item has no `chat_url`, synthesize one from this template. Supports `{session_id}`, `{customer_id}`, `{customer_name}`. |
| `recipient_filter.task_keywords` | `[]` | Agents whose `tasks` list contains any of these keywords (case-insensitive substring match) are candidate recipients. |
| `recipient_filter.skill_keywords` | `[]` | Agents whose `skills` list contains any of these keywords are candidate recipients. |
| `assignment_extra_fields` | `[]` | Extra keys to forward from the monitor item onto the outgoing assignment payload (beyond `customer_id`, `session_id`, `chat_url`, `tab_id`, `customer_name`). |
| `dispatched_flag_attr` | `"_ecan_frontdesk_dispatched_all"` | Attribute name set on the `browser_session` to signal that dispatch is complete. **Must match `stepPatches.pre_dispatch_flag_attr`** if both blocks are used. |
| `dispatch_state_attr` | `"_ecan_frontdesk_dispatch_state"` | Attribute name on `browser_session` where the dispatcher caches its `opened_tabs`, `assigned_sessions`, `service_agents`, and `rr_index`. |
| `log_tag` | `"PreDispatch"` | Prefix used in log lines. |
| `result_marker_key` | `"frontdesk_fastpath"` | Key on the result payload that downstream consumers can use to recognize a fast-path result. |
| `history_prefix` | `"predispatch"` | Prefix for the `history` string returned with the result. |

If both `recipient_filter.task_keywords` and `recipient_filter.skill_keywords`
are empty, the fallback is "all agents other than the sender".

### Behavior summary

1. Node entry → look up a monitor with `label == source_monitor_label`.
2. If monitor not found, not in an allowed status, or URL path mismatch → **bail out silently**, letting the node proceed to the normal LLM path.
3. Otherwise, for each item in `last_items`:
   - Open a dedicated tab at its `chat_url` (cached per session).
   - Round-robin assign the session to a discovered recipient agent via `send_chat`.
4. Set `browser_session.<dispatched_flag_attr> = True` so any concurrently-running LLM step aborts.
5. Return a fast-path result — no LLM call.

---

## 3. `stepPatches` — Browser-Use Step Hooks

Enables optional monkey-patches that wrap `browser-use`'s `agent.step()` for:

- **`refocus_assigned_tab`** — Before each step, if `assignment_tab_id` is set on state, snap focus back to that tab via DOM activation. Used by service agents that must not drift to another customer tab mid-run.
- **`abort_when_pre_dispatched`** — Before each step, check `getattr(browser_session, pre_dispatch_flag_attr, False)`; if true, abort. Used by the front-desk skill whose LLM may auto-trigger concurrently with a pre-dispatch fast-path.

### Schema

```json
{
  "refocus_assigned_tab": true,
  "abort_when_pre_dispatched": true,
  "pre_dispatch_flag_attr": "_ecan_frontdesk_dispatched_all"
}
```

### Fields

| Field | Default | Purpose |
|---|---|---|
| `refocus_assigned_tab` | `false` | Install a per-step hook that re-focuses `state.assignment_tab_id` before each step. |
| `abort_when_pre_dispatched` | `false` | Install a per-step hook that aborts the step loop when the pre-dispatch flag is set on the browser session. |
| `pre_dispatch_flag_attr` | `"_ecan_frontdesk_dispatched_all"` | Attribute name checked by the abort hook. **Must match `preDispatch.dispatched_flag_attr`** when both blocks are used together. |

### Back-compat

The legacy `enable_step_refocus` input is still honored — setting it is
equivalent to `stepPatches: { "refocus_assigned_tab": true }`.

---

## 4. `tabPolicy` — Tab Guardrail Text

Controls the per-step "tab discipline" paragraph injected into the LLM's task
text.

### Accepted values

| Value | Behavior |
|---|---|
| `""` / `strict_single_tab` (default) | Inject the strict text: "Never use `switch_tab`. Work in the current tab only." |
| `allow_assigned_tab` | Inject the permissive text: "If an assigned `tab_id` is provided, you may `switch_tab` once to focus it. Otherwise, never `switch_tab`." |

This is a **simple string select**, not a JSON block.

---

## Migration snippets for known skills

### `rt_chat_bot` (service agent)

```json
// assignment
{
  "enabled": true,
  "require_any_of": ["session_id", "customer_id"],
  "on_missing": "skip_node",
  "scope_contract_template": "[ASSIGNED SCOPE]\nsession_id={session_id}\ntab_id={tab_id}\nchat_url={chat_url}\ncustomer_name={customer_name}\n\nYou MUST only interact with this customer session. Never serve another customer in this run.",
  "navigate_field": "chat_url",
  "strip_url_regex": "https?://(?:127\\.0\\.0\\.1|localhost):9877/chat\\?session=[^\\s\"']+",
  "strip_url_replacement": "[assigned chat tab already open]"
}
```

```json
// stepPatches
{ "refocus_assigned_tab": true }
```

```
// tabPolicy
allow_assigned_tab
```

### `customer_front_desk` (dispatcher)

```json
// preDispatch
{
  "enabled": true,
  "source_monitor_label": "conversation_became_active",
  "require_url_path": "/control",
  "allowed_statuses": ["ok", "empty", "no_match"],
  "item_fields": {
    "session_id": ["session", "session_id", "customer_id"],
    "customer_name": ["customer_name", "name", "customer"],
    "chat_url": ["chat_url"]
  },
  "chat_url_template": "http://127.0.0.1:9877/chat?session={session_id}",
  "recipient_filter": {
    "task_keywords": ["feige_chat"],
    "skill_keywords": ["rt_chat_bot"]
  },
  "dispatched_flag_attr": "_ecan_frontdesk_dispatched_all"
}
```

```json
// stepPatches
{
  "abort_when_pre_dispatched": true,
  "pre_dispatch_flag_attr": "_ecan_frontdesk_dispatched_all"
}
```

`preDispatch.dispatched_flag_attr` and `stepPatches.pre_dispatch_flag_attr`
**must match** — they are two ends of the same signal.

---

## How configs are loaded

Each block is read by `build_browser_automation_node` via the shared
`_parse_json_input(inputs, key)` helper (`agent/ec_skills/build_node.py`). It
tolerantly accepts a dict, a JSON string, or an empty string. Invalid JSON is
logged as a non-fatal warning and treated as "unset" — the node falls back to
the generic default.

No backend save/load plumbing changes were needed — these are generic string
fields on `inputsValues` that ride through the existing skill-graph
serialization path.
