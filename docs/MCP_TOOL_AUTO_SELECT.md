# MCP Tool Auto-Select

How an LLM picks an MCP tool and fills its input parameters in eCan.ai, and why we don't put the full tool schema into the prompt.

For what happens **after** the tool(s) are picked (parallel vs serial, multi-tool batches), see [MULTI_TOOL_CALLS.md](./MULTI_TOOL_CALLS.md).

---

## The size problem

With 130+ MCP tools registered, putting every tool's full `inputSchema` into the LLM prompt would burn ~172 KB of context per turn — most of it for tools the LLM won't pick anyway. The full schemas carry per-parameter types, descriptions, `required` lists, enum constraints, and nested-object shapes that the LLM only needs *after* it has decided which tool to invoke.

eCan.ai's design: **compact prompt at decide-time, full schema at dispatch-time**. The LLM makes its decision and drafts its tool-call JSON from compact info; the server validates and patches that JSON against the full schema before actually calling the tool.

This is **one LLM call, not two**. We do not do a textbook two-round scheme (round 1: pick the tool name; round 2: re-prompt the LLM with that tool's full schema to fill params). We save the second LLM round; the cost is occasional malformed input that the server-side reconciliation has to salvage.

---

## What the LLM sees in the prompt

The prompt template uses a `{{tools_schema}}` placeholder. At render time, `agent/ec_skills/prompt_variable_providers.py:_provide_tools_schema` walks every registered tool and emits one compact entry per tool:

```json
{
  "name": "send_chat",
  "description": "Send a chat message to another agent...",
  "params": ["sender_agent_id", "recipient_agent_id", "message", "chat_id"]
}
```

Three fields, nothing else:

- **`name`** — what the LLM puts into `tool_name`.
- **`description`** — one-line prose (XML category tags stripped). This is where the tool author tells the LLM **when** to use it and **what** to pass.
- **`params`** — flat list of parameter **names only**. No types, no per-param descriptions, no `required` flags, no nested-object shapes.

If the tool's `inputSchema` uses the canonical `{"input": {...}}` wrapper (most tools do), the `input` key is stripped automatically — the LLM sees the inner param names directly. So a schema like

```json
{ "type": "object", "required": ["input"],
  "properties": { "input": { "type": "object", "required": ["prompt"],
    "properties": { "prompt": {"type":"string"}, "context_hint": {"type":"string"} }}}}
```

renders compactly as `params: ["prompt", "context_hint"]`.

**Size impact:** ~172 KB → ~38 KB across ~130 tools (~78% reduction). The LLM's context budget gets to be spent on the actual conversation history.

## How the LLM fills input from just parameter names

It can, for three reasons that compound:

1. **Names are the contract.** `customer_id`, `chat_id`, `prompt`, `query`, `recent` — well-designed param names are semantic. The LLM infers types from convention (`*_id` → string, `recent`/`count` → integer, `enable_*` → bool).
2. **The `description` carries intent in prose.** "Pass the user's question verbatim", "Number of hours to look back", "ID of the recipient agent. Either this or recipient_agent_name is required." This is where to put hints that would otherwise live in per-parameter descriptions inside the full schema.
3. **The conversation provides values.** The LLM has the user's message, the chat history, and prior tool results in its context. Most parameter values come from there.

The LLM emits a JSON tool call:

```json
{
  "tool_name": "send_chat",
  "tool_input": {
    "input": {
      "sender_agent_id": "agent_48bdd6...",
      "message": "Hello!",
      "chat_id": "客户14"
    }
  }
}
```

(The `"input"` wrapper matches the canonical schema shape. Tool nodes do still accept flat input as a defensive fallback.)

## Server-side reconciliation (4 passes)

When the LLM's JSON reaches the MCP node (`agent/ec_skills/build_node.py`, the `if use_llm_auto_select:` block around line 6097), the dispatcher runs these passes in order before invoking the tool:

### Pass 1 — Full-schema fetch

`_get_tool_schema_by_name(tool_name)` (line 5579) pulls the **complete** `inputSchema` from `mainwin.mcp_tools_schemas` (GUI) or the cloud `get_tool_schemas()` registry (lambda). This is the rich schema with types, descriptions, `required` lists, enum constraints — exactly what we kept OUT of the prompt.

### Pass 2 — Schema-aware fallback build

`_build_input_from_config` + `_validate_tool_input_against_schema` (line 6428): if the LLM's input doesn't satisfy the full schema, build a default input from the **node's design-time `config_metadata.inputsValues`** using the full schema as a template, then merge the LLM's input on top.

This means a skill author can set sensible defaults in the flowgram editor that auto-fill when the LLM misses a field — without ever needing the LLM to know about them.

### Pass 3 — Type coercion

`_coerce_all_inputs` (line 6434) walks the full schema and fixes every value:

| LLM emitted | Schema expects | Coerced to |
|---|---|---|
| `"42"` | integer | `42` |
| `""` | required string | tool-specific default or empty value |
| missing | required boolean | `False` |
| missing `recent` for `gmail_read_titles` | integer | `72` (from `TOOL_FIELD_DEFAULTS`) |

`TOOL_FIELD_DEFAULTS` (line 5642) holds tool-specific defaults for required fields the LLM commonly omits. Use sparingly — better to fix the param name or description so the LLM gets it right.

### Pass 4 — Runtime-context auto-fill

The LLM **cannot know** its own runtime identity — there's no way for an agent to put the right `agent_id` in a tool call because the agent isn't told who it is. The server backfills from `state.attributes`:

```python
if actual_tool_name == 'send_chat' and _ctx_chat_id:
    _target['chat_id'] = _ctx_chat_id  # → log: [MCP Auto-Fill] chat_id backfilled from state context=客户14

if _ctx_agent_id:
    if 'agent_id' in _target and not _target.get('agent_id'):
        _target['agent_id'] = _ctx_agent_id
    if 'sender_agent_id' in _target and not _target.get('sender_agent_id'):
        _target['sender_agent_id'] = _ctx_agent_id

# recipient_agent_id for send_chat → from the last chat_message event's senderId,
# so reply-to routing works without the LLM having to remember who messaged it.
```

You'll see these as `[MCP Auto-Fill]` log lines at INFO level — they fire on every Feige Q&A turn, for example.

There is also a **`Harmony-channel` fallback** for GPT-5 / o-series models that occasionally emit tool calls in OpenAI's Harmony dialect (`to=tool_name <body>`) instead of standard JSON (line 6163). The recovery adopts the `to=` header as `tool_name` and uses the next `input`-bearing JSON as the body, salvaging what would otherwise be a silent drop.

---

## Authoring a new tool — checklist

If you're adding a new MCP tool, here's how to make it work with the compact-prompt scheme:

1. **Pick semantic parameter names.** `customer_id`, `query`, `prompt`, `recent` — not `arg1`, `param`, `data`. The LLM has nothing else to go on.
2. **Write a description that says when and what to pass.** The first sentence should answer "what does this do"; the second should say "when should the LLM call this"; the rest can hint at the input shape. Bonus: include a 1-line example of typical input values inline in the description.
3. **Use the `{"input": {...}}` wrapper convention.** See `agent/mcp/server/skill_editor_proxy.py:get_consult_skill_editor_tool_schema` for a clean example. The compact renderer strips the wrapper automatically.
4. **Register the schema.** Add a call to `add_tool_schema(...)` inside `build_agent_mcp_tools_schemas()` in `agent/mcp/server/tool_schemas.py`. Wrap in `try/except` if the schema imports anything GUI-only (so cloud workers can skip it gracefully).
5. **Register the cloud-direct dispatch entry.** Add `"my_tool_name": ("module.path", "async_function_name")` to `_CLOUD_TOOL_REGISTRY` in `agent/ec_skills/build_node.py` (line ~407). This is what lets the tool execute server-side without spinning up the MCP HTTP server.
6. **Implement the body** with signature `async def async_my_tool(mainwin, args: Dict[str, Any]) -> List[TextContent]`. Read params as `args["input"]["param_name"]` (the canonical path) — and ideally make the body tolerant of both wrapped and flat input for test-harness use.

For tools where the LLM consistently misses a required field, prefer:

- (a) renaming the param to be more obvious
- (b) improving the description prose
- (c) adding to `TOOL_FIELD_DEFAULTS`

…rather than implementing a true second-round LLM call. We have ~130 tools working with this scheme today; cases where compact-prompt + reconciliation aren't enough are rare.

## When you might want a true second-round LLM call

You'd add a second round if you have a tool with:

- Deeply nested object input that's hard to draft from param names alone.
- Enum-restricted string values the LLM doesn't infer from context.
- Conditional required fields ("if `mode == X` then `target` is required").

The mechanic would be:

1. Detect weak first-pass output (tool errors with `validation_error`, or required field missing after coercion + auto-fill).
2. Re-prompt the LLM with `<full_schema_for_just_this_one_tool>` in context.
3. Use the corrected input on retry.

We don't ship this today. If you start seeing the same tool listed repeatedly in `tool_failed:validation_*` ledger entries, that's the signal to add it selectively for that tool.

---

## Where to look in code

| Concern | File:line |
|---|---|
| Compact-prompt build (`{{tools_schema}}` substitution) | `agent/ec_skills/prompt_variable_providers.py:157` |
| LLM's tool-call JSON parsing | `agent/ec_skills/build_node.py:6102` (the `if use_llm_auto_select:` block) |
| Full-schema fetch at dispatch | `agent/ec_skills/build_node.py:5579` (`_get_tool_schema_by_name`) |
| Schema-aware fallback build | `agent/ec_skills/build_node.py:6428` (`_build_input_from_config`) |
| Type coercion | `agent/ec_skills/build_node.py:5647` (`_coerce_value_to_type`, `_coerce_all_inputs`) |
| Tool-specific defaults | `agent/ec_skills/build_node.py:5642` (`TOOL_FIELD_DEFAULTS`) |
| Runtime context backfill (`agent_id`, `chat_id`, `recipient_agent_id`) | `agent/ec_skills/build_node.py:6437-6485` |
| Harmony-channel recovery | `agent/ec_skills/build_node.py:6163` |
| Cloud-direct dispatch registry | `agent/ec_skills/build_node.py:_CLOUD_TOOL_REGISTRY` ~line 407 |
| Tool schema list (master) | `agent/mcp/server/tool_schemas.py:build_agent_mcp_tools_schemas` |
| Multi-tool execution (parallel / serial) | `docs/MULTI_TOOL_CALLS.md` |
