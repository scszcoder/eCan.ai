# Data-Driven Prompt Variable Resolution

This document describes the declarative, cascading resolution system used to populate `{{var_name}}` placeholders in LLM prompt templates at runtime.

## Goals
- Data-driven: customers populate prompt variables via JSON config — no source code changes needed.
- Cascading priority: multiple layers (code node → prompt JSON → skill config → built-in providers) so the most specific source always wins.
- Extensible: new providers can be registered at runtime; new source types can be added without touching the resolver.
- Backward compatible: existing `prompt_refs` usage continues to work unchanged.

## Resolution Chain

When the LLM node encounters `{{var_name}}` in a prompt template, it resolves the value using this priority order (first match wins):

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | `state["prompt_refs"][var]` | Explicit — set by a preceding code node |
| 2 | `prompt["variables"][var]` | Prompt-level declaration in the prompt JSON file |
| 3 | `skill.mapping_rules["prompt_variables"][var]` | Skill-level declaration in the skill's mapping rules |
| 4 | `BUILTIN_PROVIDERS[var]` | Built-in provider registered in the provider registry |
| 5 | `""` | Fallback empty string |

## Variable Declaration Schema

Prompt-level and skill-level declarations share the same schema. Each declaration specifies a `source` type and source-specific fields:

### `builtin` — delegate to a registered provider
```json
{
  "name": "skills_schema",
  "source": "builtin",
  "key": "skills_schema",
  "description": "JSON list of all available agent skills"
}
```

### `static` — literal string value
```json
{
  "name": "store_name",
  "source": "static",
  "value": "My eBay Store",
  "description": "Store display name"
}
```

### `state_path` — dot-path into the node state dict
```json
{
  "name": "order_count",
  "source": "state_path",
  "path": "result.llm_result.order_count",
  "description": "Number of orders from last query"
}
```

### `code` — Python expression evaluated with state in scope
```json
{
  "name": "history_length",
  "source": "code",
  "code": "len(state.get('history', []))",
  "description": "Number of conversation turns"
}
```
Available in eval scope: `state`, `mainwin`, `json`, `time`, `len`, `str`, `int`, `float`, `list`, `dict`, `bool`, `isinstance`, `getattr`, `hasattr`.

### `api` — HTTP GET/POST to a URL
```json
{
  "name": "inventory_data",
  "source": "api",
  "url": "https://my-api.com/inventory",
  "method": "GET",
  "headers": {"Authorization": "Bearer {{token}}"},
  "description": "Live inventory data from external API"
}
```
- `method`: `GET` (default) or `POST`.
- `body` (optional, POST only): JSON body to send.
- `headers` (optional): HTTP headers dict.
- Timeout: 10 seconds.

## Built-in Providers

These are always available without any declaration:

| Provider Name | Description |
|---------------|-------------|
| `skills_schema` | JSON summary of all agent skills (name + description + id) |
| `tools_schema` | JSON summary of all MCP tool schemas |
| `current_time` | Current UTC time in ISO format |
| `current_time_local` | Current local time in ISO format |
| `agent_name` | Name of the current agent |
| `agent_id` | ID of the current agent |
| `chat_id` | Current chat session ID |
| `task_id` | Current task ID |
| `human_input` | Latest human input text |
| `step_count` | Current step count |
| `max_steps` | Max steps limit |

## Prompt JSON `variables` Field

Add a top-level `"variables"` array to any prompt JSON file:

```json
{
  "id": "pr-4adab1",
  "title": "ecan_assistant_prompt",
  "sections": [ ... ],
  "variables": [
    {
      "name": "skills_schema",
      "source": "builtin",
      "key": "skills_schema",
      "description": "JSON list of all available agent skills"
    },
    {
      "name": "current_time",
      "source": "builtin",
      "key": "current_time_local",
      "description": "Current local time in ISO format"
    },
    {
      "name": "agent_name",
      "source": "builtin",
      "key": "agent_name",
      "description": "Name of the current agent"
    }
  ]
}
```

The `name` field must match the `{{var_name}}` placeholder in the prompt template sections.

## Skill-Level `prompt_variables`

Skills can declare variable overrides in `EC_Skill.mapping_rules`:

```json
{
  "mappings": [ ... ],
  "prompt_variables": {
    "store_name": {
      "source": "static",
      "value": "My Custom Store"
    },
    "order_count": {
      "source": "state_path",
      "path": "attributes.order_count"
    }
  }
}
```

Skill-level declarations have lower priority than prompt-level declarations but higher priority than built-in providers. This allows skills to provide default values that prompts can override.

## Where It Runs

- **Provider registry**: `agent/ec_skills/prompt_variable_providers.py`
  - `register_provider(name, fn)` — register a new built-in provider.
  - `get_provider(name)` — look up a provider by name.
  - `list_providers()` — list all registered provider names.
  - `resolve_prompt_variables(variable_names, state, mainwin, prompt_variables, skill_prompt_variables)` — execute the full cascading resolution chain.
  - `_resolve_variable_declaration(decl, state, mainwin)` — resolve a single declaration dict.
  - `_resolve_state_path(state, path)` — resolve a dot-separated path into the state dict.

- **Prompt template resolution**: `agent/ec_skills/build_node.py`
  - `_resolve_prompt_templates()` extracts the `"variables"` field from the prompt JSON and returns it as a third element in its return tuple: `(system_text, user_text, prompt_variables)`.
  - `build_llm_node()` captures `prompt_level_variables` and passes them into the `llm_node_callable` closure.
  - `build_browser_automation_node()` similarly captures `_browser_prompt_vars` for the `_auto` closure.
  - Both closures call `resolve_prompt_variables()` at runtime to populate `format_context` before substituting `{{var_name}}` placeholders.

## Customer Extension Points (No Source Code Access)

| Method | Difficulty | When to Use |
|--------|-----------|-------------|
| Prompt JSON `"variables"` field | Easy | Declare how each variable should be populated |
| Skill `mapping_rules.prompt_variables` | Easy | Skill-specific variable defaults |
| Code node sets `state["prompt_refs"]` | Medium | Dynamic values computed at runtime |
| `register_provider()` from a Python plugin | Advanced | Reusable providers across all prompts |

## Relationship to Mapping DSL

The prompt variable resolution system complements the [Mapping DSL](./mapping-dsl.md):

- **Mapping DSL** routes data from events/nodes into `state.attributes`, `state.metadata`, `state.tool_input`, and `resume.*`.
- **Prompt Variable Resolution** reads from `state`, `prompt_refs`, prompt JSON, and skill config to populate `{{var_name}}` placeholders in prompt templates.

A typical flow:
1. An event arrives → Mapping DSL routes `event.data.customer_name` → `state.attributes.customer_name`.
2. Prompt variable resolution reads `state.attributes.customer_name` via a `state_path` declaration → populates `{{customer_name}}` in the prompt.

## Testing

- Verify that `{{var_name}}` placeholders are correctly substituted by inspecting LLM node debug logs (`[prompt_var]` prefix).
- Test cascading priority by setting the same variable at multiple levels and confirming the highest-priority source wins.
- Test custom providers by calling `register_provider()` before the LLM node runs.
