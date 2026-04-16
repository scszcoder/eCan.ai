# Multi-Tool Calls in MCP Tool Nodes

LLM auto-select MCP nodes normally execute one tool per invocation.  When the
LLM returns `tool` as a **list** instead of a single object, the node enters
**multi-tool mode** and executes the whole list in one pass.

---

## LLM Output Format

```json
{
  "multi_tool_calls": "serial",
  "tool": [
    {
      "tool_name": "<name>",
      "tool_input": { ... }
    },
    {
      "tool_name": "<name>",
      "tool_input": { ... }
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `tool` | list | Ordered list of tool call objects. Each item has `tool_name` and `tool_input`. |
| `multi_tool_calls` | `"serial"` \| `"parallel"` | Execution order. Default when absent: `"serial"`. |

---

## Execution Modes

### `"serial"` (default)

Tools run one after another in list order.  The result of each tool is
available to all subsequent tools via **placeholder substitution** and
**pipe_output_to** (see below).

### `"parallel"`

All tools are dispatched concurrently with `asyncio.gather`.  Inter-tool
data wiring is **not available** in parallel mode — all inputs must be
fully specified upfront.

Use parallel mode when the tools are independent and latency matters
(e.g. fetching two separate data sources simultaneously).

---

## Inter-Tool Data Wiring (serial mode only)

In serial mode the executor maintains a **results context** that grows as
each tool completes.  Later tools can reference earlier results using two
complementary mechanisms.

### Option A — `{{placeholder}}` Substitution

Write a `{{key}}` token inside any string value of a later tool's
`tool_input`.  The executor replaces it before the tool is called.

**Supported key forms:**

| Syntax | Resolves to |
|---|---|
| `{{rag_query}}` | Text result of the most recent call to the tool named `rag_query` |
| `{{my_alias}}` | Text result of the tool that declared `"alias": "my_alias"` |
| `{{tool_result[2]}}` | Text result of the tool at 0-based index 2 in the list |

Unresolved placeholders (no matching key in context) are left **as-is** so
the LLM can detect the gap rather than receiving a silent empty string.

**Example — ACK → RAG → answer pipeline:**

```json
{
  "multi_tool_calls": "serial",
  "tool": [
    {
      "tool_name": "bu_send_chat",
      "tool_input": {
        "customer_id": "张三",
        "customer_name": "张三",
        "response_text": "我帮您查一下，请稍等。"
      }
    },
    {
      "alias": "rag_answer",
      "tool_name": "rag_query",
      "tool_input": { "query": "运费多少" }
    },
    {
      "tool_name": "bu_send_chat",
      "tool_input": {
        "customer_id": "张三",
        "customer_name": "张三",
        "response_text": "{{rag_answer}}"
      }
    }
  ]
}
```

The `"alias"` field gives the tool a stable name for referencing.  Without
an alias, the tool name itself (`rag_query`) is also registered and usable
as a placeholder key.

### Option B — `pipe_output_to`

A terser alternative for the simple "inject previous result into the next
tool" case.  Declare `pipe_output_to` on a tool and the executor
automatically injects the text result into the specified field of the
**immediately following** tool.

```json
{
  "multi_tool_calls": "serial",
  "tool": [
    {
      "tool_name": "bu_send_chat",
      "tool_input": {
        "customer_id": "张三",
        "customer_name": "张三",
        "response_text": "我帮您查一下，请稍等。"
      }
    },
    {
      "tool_name": "rag_query",
      "tool_input": { "query": "运费多少" },
      "pipe_output_to": "response_text"
    },
    {
      "tool_name": "bu_send_chat",
      "tool_input": {
        "customer_id": "张三",
        "customer_name": "张三"
      }
    }
  ]
}
```

`pipe_output_to` is silently cleared when the source tool fails, so no
bad data is forwarded.

### Mixing A and B

Both mechanisms work simultaneously.  You can use `pipe_output_to` for the
main data flow and `{{alias}}` for secondary references within the same
tool list.

---

## State After Execution

`state["tool_result"]` is set to a list of succeeded call summaries:

```json
[
  { "tool_name": "bu_send_chat", "result": "..." },
  { "tool_name": "rag_query",    "result": "...", "alias": "rag_answer" },
  { "tool_name": "bu_send_chat", "result": "..." }
]
```

`state["result"]["llm_result"]["multi_tool_calls"]` is persisted with the
execution mode (`"serial"` or `"parallel"`) for downstream nodes to inspect.

---

## Item Fields Reference

| Field | Required | Description |
|---|---|---|
| `tool_name` | yes | MCP tool name |
| `tool_input` | yes | Tool input dict (schema backfill applied automatically) |
| `alias` | no | Stable name for `{{alias}}` placeholder references |
| `pipe_output_to` | no | Field name in the **next** tool's input to inject this result into |

---

## Prompt Instruction Snippet

Add this to the LLM system prompt to teach the syntax:

```
When you need to call multiple tools, return a JSON object with:
- "multi_tool_calls": "serial" (sequential, supports data wiring) or "parallel" (concurrent)
- "tool": a list of tool call objects, each with "tool_name" and "tool_input"

In serial mode you can wire the output of one tool into a later tool's input
using the {{placeholder}} syntax.  Give a tool an "alias" to reference its
result by a stable name:

  {"alias": "knowledge", "tool_name": "rag_query", "tool_input": {"query": "..."}}

Then in a later tool: "response_text": "{{knowledge}}"

Or use "pipe_output_to": "<field>" to inject the result directly into the
immediately following tool's input without writing a placeholder.
```
