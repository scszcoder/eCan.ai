# eCan.ai Skill Editor — Node Schema Reference

You are generating workflow JSON for the eCan.ai skill editor. A skill is a directed graph of **nodes** connected by **edges**. Every skill has exactly one `start` node and one `end` node.

---

## 1. Top-Level Skill JSON Structure

```jsonc
{
  "skillId": "<uuid>",
  "skillName": "<snake_case_name>",
  "version": "1.0.0",
  "description": "",
  "schemaVersion": "1.0.1",
  "mode": "development",        // "development" | "released"
  "workFlow": {
    "nodes": [ /* array of Node objects */ ],
    "edges": [ /* array of Edge objects */ ]
  },
  "run_mode": "developing",           // "developing" | "released"
  "run_in_cloud": false,               // true = orchestration runs on cloud server
  "hybrid_cloud_mode": false,          // true = cloud orchestration + local execution helper
  "local_helper_skill_id": null,       // skill ID of the local helper (when hybrid_cloud_mode=true)
  "local_helper_skill_name": null,     // skill name of the local helper
  "local_helper_machine": null,        // machine name where local helper runs (e.g. "my-desktop")
  "config": {
    "run_in_cloud": false,             // mirrors top-level; authoritative for runtime
    "hybrid_cloud_mode": false,        // mirrors top-level
    "local_helper_skill_id": null,     // mirrors top-level
    "local_helper_skill_name": null,   // mirrors top-level
    "local_helper_machine": null,      // mirrors top-level
    "nodes": {},
    "skill_mapping": {
      "developing": { "mappings": [], "options": { "strict": false, "apply_order": "top_down" } },
      "released":   { "mappings": [], "options": { "strict": true,  "apply_order": "top_down" } }
    }
  }
}
```

### Execution Modes: Local vs Cloud vs Hybrid

Skills can run in three modes controlled by `run_in_cloud` and `hybrid_cloud_mode`:

| Mode | `run_in_cloud` | `hybrid_cloud_mode` | Description |
|---|---|---|---|
| **Full Local** | `false` | `false` | Everything runs on the user's machine. Default for development. |
| **Full Cloud** | `true` | `false` | Orchestration AND execution both run on the cloud server. No local machine needed. |
| **Hybrid Cloud** | `true` | `true` | Orchestration (LLM calls, state management) runs in cloud, but nodes that need local resources (browser automation, local file access, MCP tools) are delegated to a **local helper** machine. |

**Hybrid Cloud parameters** (only relevant when `hybrid_cloud_mode = true`):

| Parameter | Description |
|---|---|
| `local_helper_skill_id` | The skill ID of the local helper agent that receives delegated work. Auto-generated (e.g. `"code-skill-9116a9a1-..."`) |
| `local_helper_skill_name` | Display name of the local helper skill (typically matches the ID) |
| `local_helper_machine` | The registered machine name where the local helper runs (e.g. `"schome"`, `"office-pc"`). Must match a machine that has checked in with the cloud. |

**When to use hybrid cloud**: When the skill needs both cloud scalability (e.g. for LLM orchestration, scheduling, always-on availability) AND access to local resources (e.g. controlling a browser on the user's desktop, reading local files, using locally-installed tools).

**Important**: These fields appear both at the top level and inside `config`. The `config` copy is authoritative at runtime — always keep them in sync.

---

### Bundle Format (`*_bundle.json`) — Multi-Sheet Skills

For advanced skills with multiple sheets (sub-workflows), a separate `*_bundle.json` wraps the workflow inside a sheet container. **For 99% of use cases, you only need the single-sheet format above.** The bundle format exists for multi-sheet composition using `sheet-call` nodes.

```jsonc
{
  "mainSheetId": "main",
  "sheets": [
    {
      "id": "main",
      "name": "Main",
      "document": {
        "nodes": [ /* same node array as workFlow.nodes */ ],
        "edges": [ /* same edge array as workFlow.edges */ ]
      }
    }
    // additional sheets go here for multi-sheet skills
  ],
  "openTabs": ["main"],
  "activeSheetId": "main"
}
```

Unless you are building a multi-sheet skill with `sheet-call` nodes, **ignore this format and use the standard `workFlow` structure above**.

---

## 2. Edge Schema

Edges connect nodes sequentially. The execution engine follows edges from `start` to `end`.

```jsonc
{
  "sourceNodeID": "<node_id>",
  "targetNodeID": "<node_id>",
  "sourcePortID": "<port_key>"   // ONLY for condition node branches (e.g. "if_Md18X", "else_3R1Sq")
}
```

- **Simple edge**: omit `sourcePortID` — means "when source finishes, go to target"
- **Condition branch edge**: include `sourcePortID` matching one of the condition node's `conditions[].key`

---

## 3. Shared Node Structure

Every node follows this shape:

```jsonc
{
  "id": "<type>_<nanoid5>",     // e.g. "llm_uUkJj", "code_FySR7"
  "type": "<node_type_string>",  // see catalog below
  "meta": {
    "position": { "x": 100, "y": 200 }  // canvas position, for layout only
  },
  "data": {
    "title": "<Display Name>",
    "agentNote": "<Explain what this node does, its inputs/outputs, and why it was chosen>",
    "inputsValues": { /* node-specific parameters — see each node */ },
    // ... node-specific fields
    "outputs": {                 // standard output schema (shared by all nodes)
      "type": "object",
      "properties": {
        "result":    { "type": "object",  "description": "Node execution result" },
        "condition": { "type": "boolean", "description": "Node execution condition" },
        "resolved":  { "type": "boolean", "description": "Node execution resolved status" },
        "case":      { "type": "string",  "description": "Node execution case" }
      }
    }
  }
}
```

### Input Value Format

All `inputsValues` fields use this wrapper:

```jsonc
{
  "type": "constant",   // "constant" for static values, "template" for string interpolation
  "content": <value>    // the actual value (string, number, boolean, array, object)
}
```

- Use `"type": "constant"` for fixed values
- Use `"type": "template"` for strings that may contain `{{variable}}` interpolation (prompts, message templates)

---

## 4. Node Catalog

### 4.1 `start` — Entry Point

**Type string**: `"start"`  
**ID convention**: `"start"` (singleton)  
**Purpose**: The mandatory entry point of every skill. Execution begins here.

```jsonc
{
  "id": "start",
  "type": "start",
  "meta": { "position": { "x": 0, "y": 0 } },
  "data": {
    "title": "Start",
    "outputs": { /* standard outputs */ }
  }
}
```

**Parameters**: None. Just connect its output edge to the first working node.

---

### 4.2 `end` — Exit Point

**Type string**: `"end"`  
**ID convention**: `"end"` (singleton)  
**Purpose**: The mandatory termination point. Execution stops when this node is reached.

```jsonc
{
  "id": "end",
  "type": "end",
  "meta": { "position": { "x": 800, "y": 0 } },
  "data": {
    "title": "End",
    "data": { "inputsValues": {} }
  }
}
```

**Parameters**: None.

---

### 4.3 `llm` — LLM Call

**Type string**: `"llm"`  
**ID convention**: `"llm_<nanoid5>"`  
**Purpose**: Calls a large language model. Sends a system prompt + user prompt, receives structured or free-form text. The LLM response is stored in `state["result"]["llm_result"]`.

```jsonc
{
  "id": "llm_uUkJj",
  "type": "llm",
  "data": {
    "title": "LLM_1",
    "inputsValues": {
      "modelProvider":   { "type": "constant",  "content": "OpenAI" },
      "modelName":       { "type": "constant",  "content": "gpt-4o" },
      "apiKey":          { "type": "constant",  "content": "sk-xxx" },
      "apiHost":         { "type": "constant",  "content": "https://api.openai.com/v1" },
      "temperature":     { "type": "constant",  "content": 0.5 },
      "useThinking":     { "type": "constant",  "content": false },
      "attachments":     { "type": "constant",  "content": [] },
      "systemPrompt":    { "type": "template",  "content": "You are a helpful assistant." },
      "systemPromptId":  { "type": "constant",  "content": "in-line or a prompt id which is the pointer to actual prompt" },
      "prompt":          { "type": "template",  "content": "Summarize: {{state.result.data}}" },
      "promptId":        { "type": "constant",  "content": "in-line or a prompt id which is the pointer to actual prompt" },
      "promptSelection": { "type": "constant",  "content": "in-line" }
    }
  }
}
```

**Key Parameters**:
| Parameter | Type | Description |
|---|---|---|
| `modelProvider` | string | `"OpenAI"`, `"Anthropic"`, `"Google"`, `"DeepSeek"`, etc. |
| `modelName` | string | Model identifier, e.g. `"gpt-4o"`, `"claude-sonnet-4-20250514"`, `"gemini-2.5-pro"` |
| `apiKey` | string | API key for the provider |
| `apiHost` | string | API base URL |
| `temperature` | number | 0.0–2.0, controls randomness |
| `useThinking` | boolean | Enable extended thinking / chain-of-thought |
| `systemPrompt` | template | System prompt text (use `"type": "template"` for interpolation) |
| `prompt` | template | User prompt text |
| `systemPromptId` | string | `"in-line"` for inline prompt, or a prompt library ID |
| `promptId` | string | `"in-line"` for inline prompt, or a prompt library ID |
| `promptSelection` | string | `"in-line"` or a prompt library entry ID (e.g. `"pr-477148"`) |
| `attachments` | array | File attachments for multimodal input |

**Output**: `state["result"]["llm_result"]` contains the LLM response object with fields like `text`, `tools`, `all_done`, etc.

---

### 4.4 `mcp` — MCP Tool Call

**Type string**: `"mcp"`  
**ID convention**: `"mcp_<nanoid5>"`  
**Purpose**: Calls an MCP (Model Context Protocol) tool. Can be a specific named tool or `"llm-auto-select"` which lets the preceding LLM node pick the tool automatically.

```jsonc
{
  "id": "mcp_fhdzh",
  "type": "mcp",
  "data": {
    "title": "MCP_1",
    "run_local": false,
    "run_code_language": "python",
    "run_code_source": "",
    "callable": {
      "id": "llm-auto-select",
      "name": "llm auto select",
      "desc": "Let the LLM automatically select the appropriate tool based on the context",
      "params":  { "type": "object", "properties": {} },
      "returns": { "type": "object", "properties": {} },
      "type": "system",
      "source": ""
    },
    "inputsValues": {}
  }
}
```

**Key Parameters**:
| Parameter | Type | Description |
|---|---|---|
| `callable.id` | string | `"llm-auto-select"` (LLM picks tool) or a specific tool name like `"navigate_to"`, `"click_element"` |
| `callable.name` | string | Display name |
| `callable.desc` | string | Description for LLM tool selection |
| `callable.params` | object | JSON Schema of the tool's input parameters |
| `callable.type` | string | `"system"` (built-in) or `"custom"` |
| `run_local` | boolean | Force local execution even in cloud mode |

**Usage pattern**: Typically placed right after an `llm` node. The LLM node generates a tool call plan in `state["result"]["llm_result"]["tools"]`, and the MCP node executes it.

**Individual tool**: refer to a separate tools schemas for detailed description of each individual tool usage.

---

### 4.5 `code` — Python Code Execution

**Type string**: `"code"`  
**ID convention**: `"code_<nanoid5>"`  
**Purpose**: Executes arbitrary Python code. The code must define a `main(state, *, runtime, store)` function that receives and returns the workflow state dict.

```jsonc
{
  "id": "code_FySR7",
  "type": "code",
  "data": {
    "title": "Code_1",
    "inputsValues": {
      "input": { "type": "constant", "content": "" }
    },
    "script": {
      "language": "python",
      "content": "def main(state, *, runtime, store):\n  state['result'] = {'status': 'ok'}\n  return state"
    }
  }
}
```

**Key Parameters**:
| Parameter | Type | Description |
|---|---|---|
| `script.language` | string | Always `"python"` |
| `script.content` | string | Python source code. Must define `main(state, *, runtime, store)` |
| `inputsValues.input` | constant | Optional input string passed to the node |

**Code Contract**:
- `state` is a dict containing the full workflow state including `state["result"]` from previous nodes
- Must return `state` (modified in-place or as new dict)
- Can use `import` statements, `time.sleep()`, etc.
- Has access to `runtime` and `store` keyword args for advanced integration

---

### 4.6 `condition` — Branching

**Type string**: `"condition"`  
**ID convention**: `"condition_<nanoid5>"`  
**Purpose**: Evaluates Python expressions to route execution to different branches. Each branch has a unique port key used in edge `sourcePortID`.

```jsonc
{
  "id": "condition_IwVfC",
  "type": "condition",
  "data": {
    "title": "Condition",
    "conditions": [
      {
        "key": "if_Md18X",
        "value": {
          "mode": "custom",
          "expr": "state[\"result\"][\"llm_result\"][\"tools\"]"
        }
      },
      {
        "key": "else_3R1Sq",
        "value": {}
      }
    ]
  }
}
```

**Key Parameters**:
| Parameter | Type | Description |
|---|---|---|
| `conditions` | array | Ordered list of branches |
| `conditions[].key` | string | Unique port ID like `"if_<nanoid5>"` or `"else_<nanoid5>"`. Used in edge `sourcePortID` |
| `conditions[].value.mode` | string | `"custom"` for Python expression evaluation |
| `conditions[].value.expr` | string | Python expression evaluated against `state`. Truthy = take this branch |

**Rules**:
- Conditions are evaluated top-to-bottom; first truthy match wins
- The last condition with empty `value: {}` acts as the `else` (default) branch
- You can have multiple `if` branches + one `else`
- Edge from this node MUST include `sourcePortID` matching the condition `key`

**ID conventions for keys**: `"if_<nanoid5>"` for conditional branches, `"else_<nanoid5>"` for the default branch.

**Full example** — branch on whether LLM requested tool calls, with corresponding edges:

```jsonc
// Node
{
  "id": "condition_IwVfC",
  "type": "condition",
  "data": {
    "title": "Has Tools?",
    "conditions": [
      {
        "key": "if_Md18X",
        "value": { "mode": "custom", "expr": "state[\"result\"][\"llm_result\"][\"tools\"]" }
      },
      {
        "key": "else_3R1Sq",
        "value": {}
      }
    ]
  }
}

// Edges (note sourcePortID matching condition keys)
{ "sourceNodeID": "condition_IwVfC", "targetNodeID": "mcp_fhdzh",  "sourcePortID": "if_Md18X" }
{ "sourceNodeID": "condition_IwVfC", "targetNodeID": "chat_SI70g", "sourcePortID": "else_3R1Sq" }
```

---

### 4.7 `loop` — Iteration (Container Node)

**Type string**: `"loop"`  
**ID convention**: `"loop_<nanoid5>"`  
**Purpose**: Repeats its inner nodes until a condition is met or a count is reached. This is a **container node** — it has `blocks` (child nodes) and inner `edges`.

```jsonc
{
  "id": "loop_LZXpT",
  "type": "loop",
  "data": {
    "title": "Loop_1",
    "loopMode": "loopWhile",
    "loopCountExpr": "",
    "loopWhileExpr": "not state[\"result\"][\"llm_result\"][\"all_done\"]"
  },
  "blocks": [
    { /* block-start node */ },
    { /* inner nodes... */ },
    { /* block-end node */ }
  ],
  "edges": [
    { "sourceNodeID": "block_start_xxx", "targetNodeID": "first_inner_node" },
    { "sourceNodeID": "last_inner_node", "targetNodeID": "block_end_xxx" }
  ]
}
```

**Key Parameters**:
| Parameter | Type | Description |
|---|---|---|
| `loopMode` | string | `"loopWhile"` (condition-based, set as default, should cover vast majority of the scenarios) or `"loopCount"` (fixed iterations) |
| `loopWhileExpr` | string | Python expression; loop continues while truthy. Only used when `loopMode = "loopWhile"`. Default: `not state["result"]["llm_result"]["all_done"]` |
| `loopCountExpr` | string | Integer expression for number of iterations. Only used when `loopMode = "loopCount"` |

**Container structure**: `blocks` must contain:
1. A `block-start` node (entry point of the loop body)
2. One or more working nodes (llm, mcp, code, etc.)
3. A `block-end` node (exit point of the loop body)

Inner `edges` connect `block-start → inner nodes → block-end`. The loop automatically re-enters from `block-start` on each iteration.

**Full example** — LLM + MCP agentic loop that repeats until the LLM signals completion:

```jsonc
// Loop node with inner blocks and edges
{
  "id": "loop_LZXpT",
  "type": "loop",
  "data": {
    "title": "AgentLoop",
    "loopMode": "loopWhile",
    "loopCountExpr": "",
    "loopWhileExpr": "not state[\"result\"][\"llm_result\"][\"all_done\"]",
    "data": { "inputsValues": {} }
  },
  "blocks": [
    { "id": "block_start_aGVcT", "type": "block-start", "data": {} },
    {
      "id": "llm_uUkJj", "type": "llm",
      "data": {
        "title": "LLM_1",
        "inputsValues": {
          "modelProvider":  { "type": "constant", "content": "OpenAI" },
          "modelName":      { "type": "constant", "content": "gpt-4o" },
          "apiKey":         { "type": "constant", "content": "sk-xxx" },
          "apiHost":        { "type": "constant", "content": "https://api.openai.com/v1" },
          "temperature":    { "type": "constant", "content": 0.5 },
          "systemPrompt":   { "type": "template", "content": "You are a helpful assistant." },
          "systemPromptId": { "type": "constant", "content": "in-line" },
          "prompt":         { "type": "template", "content": "" },
          "promptId":       { "type": "constant", "content": "in-line" },
          "promptSelection":{ "type": "constant", "content": "in-line" }
        }
      }
    },
    {
      "id": "mcp_fhdzh", "type": "mcp",
      "data": {
        "title": "MCP_1",
        "callable": {
          "id": "llm-auto-select", "name": "llm auto select",
          "desc": "Let the LLM automatically select the appropriate tool",
          "params": { "type": "object", "properties": {} },
          "returns": { "type": "object", "properties": {} },
          "type": "system", "source": ""
        },
        "inputsValues": {}
      }
    },
    { "id": "block_end_ZD_YW", "type": "block-end", "data": {} }
  ],
  "edges": [
    { "sourceNodeID": "block_start_aGVcT", "targetNodeID": "llm_uUkJj" },
    { "sourceNodeID": "llm_uUkJj",         "targetNodeID": "mcp_fhdzh" },
    { "sourceNodeID": "mcp_fhdzh",         "targetNodeID": "block_end_ZD_YW" }
  ]
}

// Outer edges connecting the loop into the main flow
{ "sourceNodeID": "start",     "targetNodeID": "loop_LZXpT" }
{ "sourceNodeID": "loop_LZXpT", "targetNodeID": "end" }
```

**Nested loop example** — outer loop waits for human input, conditionally branches into an inner loop that runs browser automation + code:

```jsonc
// Outer loop (Loop_2) — its blocks contain an inner loop (Loop_4)
{
  "id": "loop_oIPxU",
  "type": "loop",
  "data": {
    "title": "Loop_2",
    "loopMode": "loopWhile",
    "loopCountExpr": "",
    "loopWhileExpr": "not state[\"result\"][\"llm_result\"][\"all_done\"]",
    "data": { "inputsValues": {} }
  },
  "blocks": [
    { "id": "block_start_DjI2o", "type": "block-start", "data": {} },

    // Wait for human chat before each iteration
    {
      "id": "pend_event_Z6bv3", "type": "pend_event_node",
      "data": {
        "title": "PendEvent_1",
        "inputsValues": {
          "eventType": { "type": "constant", "content": "human_chat" },
          "resumePolicy": { "type": "constant", "content": "first" },
          "timeoutSec": { "type": "constant", "content": 0 }
        }
      }
    },

    // Branch: chat reply vs browser automation sub-loop
    {
      "id": "condition_29KO-", "type": "condition",
      "data": {
        "title": "Condition",
        "conditions": [
          { "key": "if_mrhJm", "value": {} },
          { "key": "else_BQ9rp", "value": {} }
        ]
      }
    },

    // Chat reply branch
    {
      "id": "chat_sgGqQ", "type": "chat_node",
      "data": {
        "title": "Chat_1",
        "inputsValues": {
          "party": { "type": "constant", "content": "human" },
          "messageTemplate": { "type": "template", "content": "" }
        }
      }
    },

    // *** INNER LOOP (nested inside the outer loop's blocks) ***
    {
      "id": "loop_ZEUpP",
      "type": "loop",
      "data": {
        "title": "Loop_4",
        "loopMode": "loopWhile",
        "loopCountExpr": "",
        "loopWhileExpr": "not state[\"result\"][\"llm_result\"][\"all_done\"]",
        "data": { "inputsValues": {} }
      },
      "blocks": [
        { "id": "block_start_wLSMh", "type": "block-start", "data": {} },
        {
          "id": "browser_automation_XJH8a", "type": "browser-automation",
          "data": {
            "title": "Browser_2",
            "inputsValues": {
              "tool":          { "type": "constant", "content": "browser-use" },
              "browser":       { "type": "constant", "content": "new chromium" },
              "modelProvider": { "type": "constant", "content": "OpenAI" },
              "modelName":     { "type": "constant", "content": "gpt-4o" },
              "systemPrompt":  { "type": "template", "content": "You are a browser agent..." },
              "prompt":        { "type": "template", "content": "" }
            }
          }
        },
        {
          "id": "code_AVBAo", "type": "code",
          "data": {
            "title": "Code_1",
            "script": { "language": "python", "content": "def main(state, *, runtime, store):\n  state['result'] = {'status': 'ok'}\n  return state" }
          }
        },
        { "id": "block_end_bg9_G", "type": "block-end", "data": {} }
      ]
      // inner loop edges omitted for brevity — same pattern: block-start → browser → code → block-end
    },

    { "id": "block_end_EUIy2", "type": "block-end", "data": {} }
  ],
  "edges": [
    { "sourceNodeID": "block_start_DjI2o", "targetNodeID": "pend_event_Z6bv3" },
    { "sourceNodeID": "pend_event_Z6bv3",  "targetNodeID": "condition_29KO-" },
    { "sourceNodeID": "condition_29KO-",    "targetNodeID": "chat_sgGqQ",  "sourcePortID": "if_mrhJm" },
    { "sourceNodeID": "condition_29KO-",    "targetNodeID": "loop_ZEUpP",  "sourcePortID": "else_BQ9rp" },
    { "sourceNodeID": "chat_sgGqQ",         "targetNodeID": "block_end_EUIy2" },
    { "sourceNodeID": "loop_ZEUpP",         "targetNodeID": "block_end_EUIy2" }
  ]
}
```

**Key points for nested loops**:
- An inner `loop` node is placed inside the outer loop's `blocks` array, just like any other node
- The inner loop has its own `blocks` and `edges` arrays (same structure recursively)
- The outer loop's `edges` connect to/from the inner loop node by its ID, treating it as a single node
- Nesting depth is unlimited — you can have loops within loops within loops

---

### 4.8 `block-start` / `block-end` — Loop Boundaries

**Type strings**: `"block-start"`, `"block-end"`  
**ID conventions**: `"block_start_<nanoid5>"`, `"block_end_<nanoid5>"`  
**Purpose**: Structural markers inside a `loop` container. They define where the loop body begins and ends. No configuration needed.

```jsonc
{ "id": "block_start_aGVcT", "type": "block-start", "data": {} }
{ "id": "block_end_ZD_YW",   "type": "block-end",   "data": {} }
```

---

### 4.9 `pend_event_node` — Wait for External Event

**Type string**: `"pend_event_node"`  
**ID convention**: `"pend_event_<nanoid5>"`  
**Purpose**: Suspends execution until an external event arrives (human chat, timer fire, webhook, browser event, agent-to-agent message, etc.). This is how skills react to asynchronous inputs.

```jsonc
{
  "id": "pend_event_LEK3M",
  "type": "pend_event_node",
  "data": {
    "title": "PendEvent_1",
    "inputsValues": {
      "eventType":      { "type": "constant", "content": "human_chat" },
      "messageType":    { "type": "constant", "content": "" },
      "agentIds":       { "type": "constant", "content": "" },
      "timerName":      { "type": "constant", "content": "" },
      "browserEventLabel": { "type": "constant", "content": "" },
      "pendingSources": { "type": "constant", "content": [] },
      "timeoutSec":     { "type": "constant", "content": 0 },
      "resumePolicy":   { "type": "constant", "content": "first" },
      "matchFields":    { "type": "constant", "content": [] }
    }
  }
}
```

**Key Parameters**:
| Parameter | Type | Description |
|---|---|---|
| `eventType` | string | Primary event type: `"human_chat"`, `"a2a"`, `"webhook"`, `"websocket"`, `"mqtt"`, `"sse"`, `"timer"`, `"browser_event"`, `"system"`, `"other"` |
| `messageType` | string | Sub-filter for `websocket`/`sse`/`webhook`/`system` events |
| `agentIds` | string | Comma-separated agent IDs for `a2a` events |
| `timerName` | string | Timer name to listen for when `eventType = "timer"` |
| `browserEventLabel` | string | Subscription label when `eventType = "browser_event"` |
| `pendingSources` | array | Additional event types to listen for simultaneously. Each item: `{ "type": "timer", "timerName": "poll_price" }` or `{ "type": "browser_event", "browserEventLabel": "price_api" }` |
| `timeoutSec` | number | Timeout in seconds (0 = wait forever) |
| `resumePolicy` | string | `"first"` (resume on first event) or `"all"` |
| `matchFields` | array | Declarative field matching: `[{ "event_path": "context.timer_name", "literal": "check_orders" }]` |

**When the event arrives**: Execution resumes, and the event data is appended to `state["events"]` and merged into `state` via state_patch.

---

### 4.10 `chat_node` — Send/Receive Chat Messages

**Type string**: `"chat_node"`  
**ID convention**: `"chat_<nanoid5>"`  
**Purpose**: Sends a message to the GUI chat interface or to another agent. Used for human-facing responses.

```jsonc
{
  "id": "chat_SI70g",
  "type": "chat_node",
  "data": {
    "title": "Chat_1",
    "inputsValues": {
      "party":           { "type": "constant", "content": "human" },
      "messageTemplate": { "type": "template", "content": "Here is your answer: {{state.result.llm_result.text}}" }
    }
  }
}
```

**Key Parameters**:
| Parameter | Type | Description |
|---|---|---|
| `party` | string | `"human"` (send to GUI chat) or an agent ID (send to another agent) |
| `messageTemplate` | template | Message content with `{{variable}}` interpolation. Use `"type": "template"` |

---

### 4.11 `browser-automation` — Browser Automation (browser_use)

**Type string**: `"browser-automation"`  
**ID convention**: `"browser_automation_<nanoid5>"`  
**Purpose**: Runs an autonomous browser sub-agent using browser_use. The agent has its own LLM and tool set as well as a run controller. For a given prompt, this browser sub-agent can navigate, click, type, extract data, and interact with web pages for up to 100 consecutive steps (each sequence of DOM extraction + action (click, move, type, scroll, etc.) = 1 step.

```jsonc
{
  "id": "browser_automation_yXLdl",
  "type": "browser-automation",
  "data": {
    "title": "Browser_1",
    "inputsValues": {
      "tool":            { "type": "constant", "content": "browser-use" },
      "browser":         { "type": "constant", "content": "existing chrome" },
      "browserDriver":   { "type": "constant", "content": "native" },
      "cdpPort":         { "type": "constant", "content": "9228" },
      "runEnvironment":  { "type": "constant", "content": "full_local" },
      "privacyStrategy": { "type": "constant", "content": "none" },
      "enableJudge":     { "type": "constant", "content": false },
      "shopName":        { "type": "constant", "content": "" },
      "customShopName":  { "type": "constant", "content": "" },
      "modelProvider":   { "type": "constant", "content": "OpenAI" },
      "modelName":       { "type": "constant", "content": "gpt-4o" },
      "temperature":     { "type": "constant", "content": 0.3 },
      "useThinking":     { "type": "constant", "content": false },
      "useVision":       { "type": "constant", "content": false },
      "profile":         { "type": "constant", "content": "" },
      "systemPrompt":    { "type": "template", "content": "You are a browser automation agent..." },
      "prompt":          { "type": "template", "content": "Go to amazon.com and search for..." },
      "promptSelection": { "type": "constant", "content": "inline" }
    }
  }
}
```

**Key Parameters**:
| Parameter | Type | Description |
|---|---|---|
| `tool` | string | `"browser-use"` (CDP-based) or `"selenium"` |
| `browser` | string | `"existing chrome"` (attach to running Chrome, default setting), `"chromium"` (launch new), `"adspower"` (anti-detect) |
| `browserDriver` | string | `"native"` (CDP direct) or `"webdriver"` (Selenium-based) |
| `cdpPort` | string | Chrome DevTools Protocol port (default `"9228"`) |
| `runEnvironment` | string | `"full_local"` (all local), `"cloud_llm"` (cloud LLM + local browser) |
| `privacyStrategy` | string | `"none"`, `"filter"`, `"cloud"` — privacy filtering level |
| `enableJudge` | boolean | Enable action-judging step for safety |
| `modelProvider` | string | LLM provider for the browser agent's reasoning |
| `modelName` | string | LLM model for the browser agent |
| `temperature` | number | LLM temperature |
| `useThinking` | boolean | Extended thinking for browser agent |
| `useVision` | boolean | Use screenshots for visual understanding | this will be slow and costly, is turned off by default |
| `systemPrompt` | template | System prompt for the browser agent |
| `prompt` | template | Task instruction for what the browser should do |

---

### 4.12 `variable` — Variable Declaration & Assignment

**Type string**: `"variable"`  
**ID convention**: `"variable_<nanoid5>"`  
**Purpose**: Declares or assigns variables in the workflow state. Useful for initializing counters, accumulators, or storing intermediate results.

```jsonc
{
  "id": "variable_xK3mQ",
  "type": "variable",
  "data": {
    "title": "Variable_1",
    "assign": [
      {
        "operator": "declare",
        "left": "sum",
        "right": {
          "type": "constant",
          "content": 0,
          "schema": { "type": "integer" }
        }
      }
    ]
  }
}
```

**Key Parameters**:
| Parameter | Type | Description |
|---|---|---|
| `assign` | array | List of assignment operations |
| `assign[].operator` | string | `"declare"` (create new var), `"assign"` (update existing) |
| `assign[].left` | string | Variable name |
| `assign[].right` | object | Value with `type`, `content`, `schema` |

---


### 4.13 `sheet-call` — Invoke Another Sheet (mostly not needed)

**Type string**: `"sheet-call"`  
**ID convention**: `"sheet_call_<nanoid5>"`  
**Purpose**: Calls another sheet (sub-workflow) within the same skill, with input/output mapping. Enables modular, reusable workflow composition.

```jsonc
{
  "id": "sheet_call_xK3mQ",
  "type": "sheet-call",
  "data": {
    "title": "SheetCall_1",
    "callName": "Call_1",
    "targetSheetId": "<sheet_id>",
    "inputMapping": {},
    "outputMapping": {}
  }
}
```

---

### 4.14 `comment` — Annotation (Non-Executable)

**Type string**: `"comment"`  
**ID convention**: `"comment_<nanoid5>"`  
**Purpose**: Visual annotation on the canvas. Does NOT execute. Used for documentation.

---


## 5. Common Workflow Patterns

### Pattern A: Simple Chat Agent (Loop)

```
start → loop(while: not all_done) {
                              _________________________________________
                             |                                         |
                             v                                         |
    block-start → pend_event -> llm -> condition → mcp(llm-auto-select) → block-end
                                            |
                                            ------> chat_node
} → end
```

The LLM plans actions, MCP executes them, loop repeats until the LLM sets `all_done = true`.

### Pattern B: Event-Driven with Branching

```
start → pend_event(human_chat) → condition {
    if (has tools): → mcp → ...
    else:           → chat(reply to human) → ...
} → end
```

Wait for human input, branch on whether the LLM wants to use tools or just reply.

### Pattern C: Timer-Based Polling

```
start → llm(instruct add_timer call) → mcp(llm-auto-select: executes add_timer) → loop(while: true) {
    block-start → llm → mcp → pend_event(timer: "poll_15s") → block-end
} → end
```

The LLM node before the loop tells the model to call `add_timer` with the timer name and period; the MCP node executes it. Inside the loop, execute LLM + tools, then wait for a timer event before the next iteration.

### Pattern D: Browser Automation Task

```
start → browser-automation(task: "Go to amazon.com and find product X") → code(process results) → end
```

### Pattern E: Multi-Event Listener

```
start → pend_event(eventType: "timer", pendingSources: [{"type": "human_chat"}, {"type": "browser_event", "browserEventLabel": "price_api"}]) → condition {
    if (timer):         → llm(poll) → ...
    if (human_chat):    → chat(reply) → ...
    if (browser_event): → code(process price) → ...
} → end
```

---

## 6. State Object

All nodes share a `state` dict that flows through the graph:

```python
state = {
    "result": {
        "llm_result": { ... },   # Output from last LLM node
        "status": "...",          # Output from last code/mcp node
    },
    "events": [ ... ],           # Event envelopes from pend_event nodes
    "attributes": {
        "agent_id": "...",
        "chat_id": "...",
    },
    "messages": [ ... ],         # Chat message history
    "metadata": { ... },         # Skill metadata
}
```

Key paths used in expressions:
- `state["result"]["llm_result"]["text"]` — LLM response text
- `state["result"]["llm_result"]["tools"]` — Tool calls from LLM (truthy if LLM wants to call tools)
- `state["result"]["llm_result"]["all_done"]` — LLM signals task completion
- `state["events"][-1]` — Last received event envelope
- `state["events"][-1]["event_type"]` — Type of the last event

---

## 7. ID Generation Rules

- Node IDs: `"<type_prefix>_<nanoid(5)>"` — e.g. `"llm_uUkJj"`, `"code_FySR7"`, `"condition_IwVfC"`
- Condition keys: `"if_<nanoid(5)>"` or `"else_<nanoid(5)>"` — e.g. `"if_Md18X"`, `"else_3R1Sq"`
- Block markers: `"block_start_<nanoid(5)>"`, `"block_end_<nanoid(5)>"`
- Singleton IDs: `"start"`, `"end"` (always these exact strings)

Use 5-character alphanumeric random suffixes (nanoid style) for uniqueness.
