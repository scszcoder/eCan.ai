"""
Code Agent for Skill Editor

A code generation agent that creates and edits flowgrams based on:
1. User requests (direct or from planner)
2. Implementation plans from PlannerAgent
3. Iterative validation and fixing

Inspired by BubbleLab's Boba/Pearl agent pattern.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from utils.logger_helper import logger_helper as logger

from .token_tracker import token_tracker

from .schemas import (
    CodeAgentAction,
    CodeAgentOutput,
    Flowgram,
    FlowgramNode,
    FlowgramEdge,
    NodePosition,
    ValidationResult,
    ValidationError,
    ImplementationPlan,
    CanvasCommand,
    NODE_TYPES,
)
from .validator_agent import get_validator_agent, ValidatorAction

# Re-import for the rest of the file
from .schemas import (
    get_node_types_description,
)
from .placement import place_nodes, LOOP_INTERNAL_CFG
from .prompt_store import prompt_store
from .prompt_store import safe_format


# ============================================================
# Constants
# ============================================================

MAX_VALIDATION_RETRIES = 3
DEFAULT_NODE_SPACING_X = 250
DEFAULT_NODE_SPACING_Y = 150
START_POSITION_X = 100
START_POSITION_Y = 100

# ---------------------------------------------------------------------------
# Baseline data_mapping.json rules
# These are always present; the LLM can add workflow-specific rules on top.
# ---------------------------------------------------------------------------

_BASE_MAPPINGS = [
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
        "from": ["event.tag"],
        "to": [
            {"target": "state.attributes.cloud_task_id"}
        ],
        "on_conflict": "overwrite"
    },
    # Async response mode: controls whether send_response_back sends via A2A or skips
    {
        "from": ["event.data.metadata.async_response", "event.context.async_response"],
        "to": [
            {"target": "state.attributes.async_response"}
        ],
        "on_conflict": "overwrite"
    },
]

_DEV_DEBUG_MAPPING = {
    "from": ["event.data.metadata"],
    "to": [
        {"target": "state.attributes.debug.last_event_metadata"}
    ],
    "on_conflict": "overwrite"
}

DEFAULT_BASELINE_MAPPINGS: Dict[str, Any] = {
    "developing": {
        "mappings": _BASE_MAPPINGS + [_DEV_DEBUG_MAPPING],
        "options": {
            "strict": False,
            "default_on_missing": None,
            "apply_order": "top_down"
        }
    },
    "released": {
        "mappings": list(_BASE_MAPPINGS),
        "options": {
            "strict": True,
            "default_on_missing": None,
            "apply_order": "top_down"
        }
    },
    "node_transfers": {},
    "event_routing": {},
}

# Preferred prompt pool IDs (fallback defaults when config is missing)
DEFAULT_LLM_PROMPT_ID = "pr-454780"
DEFAULT_BROWSER_PROMPT_ID = "pr-935241"
# User prompts are stored in user_data directory (production-safe)
MY_PROMPTS_DIR = None  # Will be set dynamically based on current user

def _get_my_prompts_dir() -> Path:
    """Get user-specific prompts directory (production-safe)."""
    global MY_PROMPTS_DIR
    if MY_PROMPTS_DIR is None:
        from utils.user_path_helper import get_user_data_dir
        user_data_dir = get_user_data_dir(subdir="my_prompts")
        MY_PROMPTS_DIR = Path(user_data_dir)
    return MY_PROMPTS_DIR

# Default scaffold for code nodes
CODE_NODE_DEFAULT_TEMPLATE = """# Here, you can retrieve input variables from the node using 'state'
import time

def main(node_state, *, runtime, store):
    # Build the output object
    print("in myfunc0.........", node_state)
    time.sleep(1)
    print("myfunc0 woke now, outa here.....")
    state["result"]["llm_result"] = {"all_done": False}
    state["result"]["status"]"myfunc0 succeeded!!!"
    return state
"""


# ============================================================
# System Prompts
# ============================================================

CODE_GENERATION_PROMPT = """You are a Code Agent for the Skill Editor, specializing in generating flowgram workflows.

Your role is to translate user requests and implementation plans into concrete flowgram structures (nodes and edges).

## AVAILABLE NODE TYPES:
{node_types}

## NODE SCHEMA REFERENCE:
{node_schema}

## MAPPING DSL REFERENCE (data_mapping.json):
The Mapping DSL lets you declare data movement rules in data_mapping.json so that data flows between events, nodes, and state without code nodes. Prefer mapping rules over code nodes when the task is pure data routing.

{mapping_dsl}

## CURRENT CANVAS STATE:
{canvas_context}

## IMPLEMENTATION PLAN (if provided):
{plan_context}

## TERMINOLOGIES:
- **Flowgram**: A workflow definition in JSON format
- **Node**: A component of a flowgram that performs a specific task
- **Edge**: A connection between nodes in a flowgram
- **Canvas**: The visual representation of a flowgram in the Skill Editor
- Flowgram, Skill, Workflow are used interchangeably

## SKILL DIRECTORY STRUCTURE:
Skills are stored in `my_skills/` under the application's data directory.
Each skill follows this structure:
  my_skills/<skill_name>_skill/
    diagram_dir/
      <skill_name>_skill.json        # Main flowgram definition
      <skill_name>_skill_bundle.json # Additional sheets/data

When you generate a flowgram, the system will automatically:
1. Create the skill directory structure
2. Save the flowgram JSON files
3. Load the skill into the canvas for editing

## WORK DECOMPOSITION STRATEGY:
- **BREAK DOWN COMPLEXITY**: Decompose complex requests into manageable components
- **MULTI-PHASE**: For long workflows, divide into phases with clear milestones
- **IDENTIFY BLOCKERS**: Flag gating items or show-stoppers in your response message
- **IDENTIFY LOOPS**: Any repeatable task should be placed inside a loop node
- **IDENTIFY HUMAN IN THE LOOPS**: Any instance where human interaction is required should be mapped to a pend_event node

## FLOWGRAM GENERATION RULES:
1. Every flowgram MUST have a "start" node and an "end" node
2. All nodes must be connected - no orphan nodes
3. **NODE NAMING CONVENTION (CRITICAL - MUST FOLLOW EXACTLY)**: Node IDs MUST use the node type as prefix (replace hyphens with underscores):
   - LLM nodes (type="llm"): `llm_<purpose>` (e.g., "llm_analyze_order", "llm_process_message")
   - Condition nodes (type="condition"): `condition_<purpose>` (e.g., "condition_check_status", "condition_has_orders")
   - Loop nodes (type="loop"): `loop_<purpose>` (e.g., "loop_process_orders", "loop_messages")
   - Browser automation (type="browser-automation"): `browser_automation_<purpose>` (e.g., "browser_automation_scrape", "browser_automation_login")
   - MCP nodes (type="mcp"): `mcp_<purpose>` (e.g., "mcp_rag_query", "mcp_send_email")
   - Code nodes (type="code"): `code_<purpose>` (e.g., "code_init_vars", "code_transform_data")
   - Chat nodes (type="chat_node"): `chat_node_<purpose>` (e.g., "chat_node_alert", "chat_node_summary")
   - Pend event (type="pend_event"): `pend_event_<purpose>` (e.g., "pend_event_human_review")
   - HTTP nodes (type="http"): `http_<purpose>` (e.g., "http_fetch_data", "http_post_result")
   - RAG nodes (type="rag"): `rag_<purpose>` (e.g., "rag_query_kb", "rag_search")
   **The prefix MUST match the node type (with hyphens replaced by underscores)** - this is validated and will cause errors if wrong.
4. Position nodes in a logical flow (top to bottom or left to right)
5. Include proper configuration for each node type
6. For LLM nodes, include system_prompt and user_prompt in config
7. For MCP tool nodes, include tool_name and tool_input in config
8. For condition nodes, include the condition expression
9. Populate flowgram.metadata with `skillName` (snake_case), `description`, and helpful tags/owner info
10. Infer a concise snake_case skill name when the user does not provide one explicitly (e.g., "ebay000" → "ebay000")
11. ALWAYS write the `message` field as a short, human-readable summary of what you built (do not echo raw JSON)
12. Include where the skill was saved in your message (e.g., "Created 'ebay000' skill with start→end flow. Saved to my_skills/ebay000_skill/")
13. **MCP TOOL DEFAULT**: Prefer the MCP auto-select tool. Set the MCP callable/tool to "llm auto select" unless the user explicitly names a specific tool.
14. **UI SHAPE**: Emit nodes with `meta.position` and `data` (title, inputsValues, inputs, outputs, script for code). Emit edges with `sourceNodeID/targetNodeID/sourcePortID/targetPortID`. Do not include null handles; omit absent fields entirely.

## EDGE CONNECTIVITY VALIDATION (CRITICAL - MOST COMMON ERROR):
Before finalizing your flowgram, VERIFY these connectivity rules:
1. **Every node except start must have at least one incoming edge**
2. **Every node except end must have at least one outgoing edge**
3. **Condition nodes REQUIRE incoming edges**: The node BEFORE a condition MUST connect TO the condition!
   - WRONG: node_A exists, condition_B exists, but no edge from node_A to condition_B
   - RIGHT: {{"source": "node_A", "target": "condition_B"}} edge exists
4. **Loop nodes**: Must have incoming edge from previous node and outgoing edge to next node
5. **Double-check**: After creating ALL edges, trace the flow from start to end - every node must be reachable
6. **DO NOT WRITE NULLS INTO EDGES**: Never emit `"sourcePortID": null` or `"targetNodeID": null` etc. If a field is unknown, omit it entirely. Null-valued edge fields cause the canvas to render condition connections incorrectly.

## MULTI-SHEET SYNC (CRITICAL):
- Each skill has two files: `<name>_skill.json` (current sheet) AND `<name>_skill_bundle.json` (all sheets).
- After generation/fix, COPY the current `workFlow` into the bundle’s main sheet (`mainSheetId`/`activeSheetId` = "main") so nodes/edges stay identical.
- Always assume the caller will persist BOTH files; never leave the bundle out of sync with the sheet file.

**COMMON MISTAKE (FIX THIS)**: Creating a condition node but forgetting to connect the previous node TO it.
Example: If you have `browser_automation_login` followed by `condition_check_data`, you MUST create an edge:
  {{"source": "browser_automation_login", "target": "condition_check_data"}}

**VERIFICATION CHECKLIST** (run through this before outputting):
- [ ] Does every condition node have an incoming edge? (Check each one!)
- [ ] Does every loop node have an incoming edge?
- [ ] Can you trace a path from "start" to every node?
- [ ] Can you trace a path from every node to "end"?

## E-COMMERCE Q&A HANDLING PATTERN (CRITICAL):
When workflow involves product/service Q&A (on-site messaging or email), follow this order:
1. **FIRST**: Query internal knowledge base using RAG query MCP tools (rag_query)
2. **IF RAG unavailable/no answer**: Defer to human assistance with 24-hour limit
   - Use pend_event node to wait for human response
   - Set timeout to 24 hours (86400 seconds)
3. **IF human fails to respond within 24 hours**: Auto-respond with best knowledge
   - Search web for same product/service info, OR
   - Search pre-specified local directory for product/service files

Workflow pattern:
```
RAG Query → Condition (has answer?) →
  YES: Auto-respond → END
  NO: Pend Human (24h timeout) → Condition (human responded?) →
      YES: Use human response → END
      NO: Web search OR local file search → Auto-respond → END
```

## BROWSER_AUTOMATION NODE - CRITICAL UNDERSTANDING:
The `browser_automation` node is a **SUB-AGENT with its own internal LLM**, NOT a simple action node!

**Capabilities:**
- Has its own LLM that can read/understand page DOM, extract data, and make decisions
- Can execute up to **100 consecutive interaction steps** (click, type, scroll, navigate, etc.)
- Per prompt request, can return structured JSON output including status flags and extracted data (
- Handles complex multi-step web interactions autonomously

**CORRECT Pattern - Batch Browser Work:**
Instead of creating multiple browser_automation + llm node pairs, batch related browser work:
1. Write a **detailed prompt** describing all browser tasks
2. Configure the browser_automation node's prompt to always must return JSON with an `all_done` boolean flag
3. Wrap with a **loop node (while type)** that continues until `all_done` is true

Example: Processing eBay orders
- WRONG: browser_automation (login) → llm (analyze) → browser_automation (navigate) → llm (extract) → ...
- RIGHT: Single browser_automation node with prompt: "Login to eBay, navigate to orders, process up to 3 unshipped orders by checking messages for cancellations and generating shipping labels. Must always return JSON with processed_orders array and all_done boolean." → Wrap in while loop checking all_done

**When to use separate LLM nodes:**
- Non-browser reasoning/data processing (e.g., comparing API response data)
- Aggregating results from multiple sources
- Complex business logic that doesn't involve browser interaction

## SUB-AGENT ERROR HANDLING PATTERN (CRITICAL):
When building workflows with sub-agents (LLM+MCP tools or browser_automation), ALWAYS include this behavior in prompts:
1. **DON'T GET STUCK**: When uncertain or encountering an error, do NOT block or retry indefinitely
2. **COLLECT & STORE**: Gather all information needed for human intervention (error details, context, what was attempted)
3. **MOVE ON**: Continue to the next action item in the task list
4. **BATCH HUMAN REQUESTS**: Accumulate all items requiring human intervention throughout execution
5. **REPORT AT END**: Send a consolidated summary of all human-intervention-needed items at the very end

Include in sub-agent prompts:
```
When you encounter an error or are unsure how to proceed:
- Log the issue with full context (error message, what you tried, what data you have)
- Store it in state["human_intervention_needed"] array
- Move on to the next task item
- At the end, report all accumulated issues for human review
```

## CONDITION NODE STRUCTURE (IMPORTANT):
Condition nodes have multiple output branches (if/elseif/else). They require:

1. A `conditions` array in the config with branch definitions
2. Each condition has a unique `key` (e.g., "if_xxx", "elseif_xxx", "else_xxx") and a `value` object
3. Order: if branch first, then any elseif branches, then else branch last
4. By default, only if and else branches (no elseif). Add elseif branches only when needed.
5. Edges FROM condition nodes MUST use `source_handle` (or `sourcePortID`) matching the condition key
6. Note: Each elseif branch adds ~27px to the node height
7. **Connectivity rule (CRITICAL)**: Every condition node MUST have exactly one INCOMING edge from the immediately preceding node in the flow. Then add OUTGOING edges for every branch using the branch key as `source_handle`.

Example condition node (default - no elseif):
{{
  "id": "condition_1",
  "type": "condition",
  "label": "Check Status",
  "position": {{"x": 400, "y": 200}},
  "config": {{
    "conditions": [
      {{"key": "if_branch", "value": {{}}}},
      {{"key": "else_branch", "value": {{}}}}
    ]
  }}
}}

Example condition node with elseif:
{{
  "id": "condition_2",
  "type": "condition",
  "label": "Multi-way Branch",
  "position": {{"x": 400, "y": 200}},
  "config": {{
    "conditions": [
      {{"key": "if_high", "value": {{}}}},
      {{"key": "elseif_medium", "value": {{}}}},
      {{"key": "elseif_low", "value": {{}}}},
      {{"key": "else_default", "value": {{}}}}
    ]
  }}
}}

Example edges from condition node:
{{
  "source": "condition_1",
  "target": "success_node",
  "source_handle": "if_branch"
}},
{{
  "source": "condition_1",
  "target": "failure_node",
  "source_handle": "else_branch"
}}

## LOOP NODE STRUCTURE (IMPORTANT):
Loop nodes are container nodes that hold internal nodes. They have a special structure:

1. Loop nodes MUST have a `blocks` array containing internal nodes
2. The `blocks` array MUST include:
   - A "block-start" node (type: "block-start") at the beginning
   - A "block-end" node (type: "block-end") at the end
   - Any content nodes (llm, mcp, code, etc.) between them
3. Loop nodes MUST have an `internal_edges` array connecting ALL blocks (use key `internal_edges`, NOT `edges`)
4. Internal node positions are RELATIVE to the loop's internal coordinate system:
   - block-start: position around (30, 0)
   - Content nodes: y ~16, x spread between 120 and 450
   - block-end: position at the right side

### LOOP INTERNAL EDGE REQUIREMENTS (CRITICAL - MOST COMMON ERROR):
**Every node inside a loop MUST be connected via internal edges!**

1. **block-start** must have outgoing edge to the first content node
2. **Every content node** must have:
   - At least one INCOMING edge (from block-start or previous node)
   - At least one OUTGOING edge (to next node or block-end)
3. **block-end** must have incoming edge from the last content node
4. **Condition nodes inside loops** follow the same rules as top-level:
   - MUST have incoming edge from previous node
   - Each branch (if/else) must have outgoing edge

**COMMON MISTAKE**: Creating nodes inside a loop but forgetting to connect them!
Example: If loop has `block_start_1 → rag_query → condition_check → llm_respond → block_end_1`:
- WRONG: Only edges `block_start_1 → rag_query` and `condition_check → llm_respond` (missing `rag_query → condition_check`)
- RIGHT: ALL edges present: `block_start_1 → rag_query → condition_check → llm_respond → block_end_1`

**VERIFICATION for loop nodes**: After creating internal edges, verify:
- [ ] Can you trace from block-start to EVERY internal node?
- [ ] Can you trace from EVERY internal node to block-end?
- [ ] Does every condition node inside the loop have an incoming edge?

### LOOP MODES:
1. **loopFor** (fixed iterations):
   - Set loopMode to "loopFor"
   - Set loopCountExpr to integer or Python expression: "10" or "state['batch_count']"

2. **loopWhile** (condition-based):
   - Set loopMode to "loopWhile"
   - Set loopWhileExpr to Python expression returning True/False
   - Loop continues while expression returns True
   - Example: loopWhileExpr = "state['result']['llm_result']['not_yet_finished']"

### EXPRESSION USAGE:
- Expressions are Python code accessing node_state via "state" variable
- Common pattern: Use LLM result attribute, e.g., state["result"]["llm_result"]["continue_flag"]

### IMPORTANT - INITIALIZE LOOP VARIABLES:
- For loopWhile, the expression variable MUST be initialized BEFORE the loop starts
- Add a code node BEFORE the loop to set initial value:
  ```python
  state["result"]["llm_result"]["not_yet_finished"] = True
  ```
- This ensures the loop runs at least once

Example loop node (loopFor - simple):
{{
  "id": "loop_1",
  "type": "loop",
  "label": "Process Items",
  "position": {{"x": 400, "y": 200}},
  "config": {{"loopMode": "loopFor", "loopCountExpr": "3", "loopWhileExpr": ""}},
  "blocks": [
    {{"id": "block_start_1", "type": "block-start", "label": "Loop Start", "position": {{"x": 30, "y": 0}}, "config": {{}}}},
    {{"id": "llm_in_loop", "type": "llm", "label": "Process", "position": {{"x": 200, "y": 16}}, "config": {{}}}},
    {{"id": "block_end_1", "type": "block-end", "label": "Loop End", "position": {{"x": 450, "y": 16}}, "config": {{}}}}
  ],
  "internal_edges": [
    {{"source": "block_start_1", "target": "llm_in_loop"}},
    {{"source": "llm_in_loop", "target": "block_end_1"}}
  ]
}}

Example loop node (with condition - NOTICE ALL EDGES):
{{
  "id": "loop_process_messages",
  "type": "loop",
  "label": "Process Messages",
  "position": {{"x": 400, "y": 200}},
  "config": {{"loopMode": "loopWhile", "loopCountExpr": "", "loopWhileExpr": "state['has_more_messages']"}},
  "blocks": [
    {{"id": "block_start_msg", "type": "block-start", "label": "Loop Start", "position": {{"x": 30, "y": 0}}, "config": {{}}}},
    {{"id": "rag_query_kb", "type": "rag", "label": "Query KB", "position": {{"x": 150, "y": 16}}, "config": {{}}}},
    {{"id": "condition_has_answer", "type": "condition", "label": "Has Answer?", "position": {{"x": 300, "y": 50}}, "config": {{"conditions": [{{"key": "if_yes", "value": {{}}}}, {{"key": "else_no", "value": {{}}}}]}}}},
    {{"id": "llm_respond", "type": "llm", "label": "Auto Respond", "position": {{"x": 450, "y": 16}}, "config": {{}}}},
    {{"id": "pend_event_human", "type": "pend_event", "label": "Wait Human", "position": {{"x": 450, "y": 100}}, "config": {{}}}},
    {{"id": "block_end_msg", "type": "block-end", "label": "Loop End", "position": {{"x": 600, "y": 50}}, "config": {{}}}}
  ],
  "internal_edges": [
    {{"source": "block_start_msg", "target": "rag_query_kb"}},
    {{"source": "rag_query_kb", "target": "condition_has_answer"}},
    {{"source": "condition_has_answer", "target": "llm_respond", "source_handle": "if_yes"}},
    {{"source": "condition_has_answer", "target": "pend_event_human", "source_handle": "else_no"}},
    {{"source": "llm_respond", "target": "block_end_msg"}},
    {{"source": "pend_event_human", "target": "block_end_msg"}}
  ]
}}
NOTE: In the above example, EVERY node has incoming AND outgoing edges:
- block_start_msg → rag_query_kb (rag_query_kb has incoming)
- rag_query_kb → condition_has_answer (condition has incoming!)
- condition_has_answer → llm_respond AND pend_event_human (both branches have outgoing)
- llm_respond → block_end_msg AND pend_event_human → block_end_msg (both paths reach end)

## CONDITION NODE IF FIELD:
- Default: "state.condition" (uses node_state["condition"] attribute)
- Custom expression: Set "if" to "custom", then set "customExpr" to Python expression
- Expression accesses node_state via "state" variable
- Examples:
  - state["result"]["llm_result"]["success"] == True
  - state["tool_result"]["status"] == "completed"
  - len(state["result"]["items"]) > 0

## CODE NODE NOTE:
- In code nodes, the input parameter "state" IS the node_state throughout the workflow
- Modify state directly: state["my_field"] = value
- Use code nodes to initialize loop variables before loops

## OUTPUT FORMAT:
You MUST respond with valid JSON containing the flowgram.

**CRITICAL NODE STRUCTURE**: Each node uses `data.inputsValues` with typed values:
- Constant values: `{{"type": "constant", "content": <value>}}`
- Template strings (with variables): `{{"type": "template", "content": "text with {{{{var}}}}"}}`

{{
  "action": "generate_flowgram",
  "message": "Brief, human-readable summary of what was created",
  "flowgram": {{
    "nodes": [
      {{
        "id": "start",
        "type": "start",
        "meta": {{"position": {{"x": 100, "y": 200}}}},
        "data": {{"title": "Start"}}
      }},
      {{
        "id": "browser_automation_fetch_orders",
        "type": "browser-automation",
        "meta": {{"position": {{"x": 350, "y": 200}}}},
        "data": {{
          "title": "Browser Task",
          "inputsValues": {{
            "tool": {{"type": "constant", "content": "browser-use"}},
            "browser": {{"type": "constant", "content": "new chromium"}},
            "browserDriver": {{"type": "constant", "content": "native"}},
            "cdpPort": {{"type": "constant", "content": ""}},
            "shopName": {{"type": "constant", "content": "ebay"}},
            "customShopName": {{"type": "constant", "content": ""}},
            "modelProvider": {{"type": "constant", "content": "OpenAI"}},
            "modelName": {{"type": "constant", "content": "gpt-4o"}},
            "temperature": {{"type": "constant", "content": 0.3}},
            "useThinking": {{"type": "constant", "content": false}},
            "profile": {{"type": "constant", "content": ""}},
            "systemPrompt": {{"type": "template", "content": "You are a browser automation agent."}},
            "prompt": {{"type": "template", "content": "Navigate to eBay and perform the task."}},
            "promptSelection": {{"type": "constant", "content": "inline"}}
          }}
        }}
      }},
      {{
        "id": "llm_analyze_data",
        "type": "llm",
        "meta": {{"position": {{"x": 600, "y": 200}}}},
        "data": {{
          "title": "Process with AI",
          "inputsValues": {{
            "modelProvider": {{"type": "constant", "content": "OpenAI"}},
            "modelName": {{"type": "constant", "content": "gpt-4o-mini"}},
            "temperature": {{"type": "constant", "content": 0.5}},
            "useThinking": {{"type": "constant", "content": false}},
            "systemPrompt": {{"type": "template", "content": "You are a helpful assistant."}},
            "systemPromptId": {{"type": "constant", "content": "in-line"}},
            "prompt": {{"type": "template", "content": "Process: {{{{input}}}}"}},
            "promptId": {{"type": "constant", "content": "in-line"}},
            "promptSelection": {{"type": "constant", "content": "inline"}}
          }}
        }}
      }},
      {{
        "id": "mcp_send_email",
        "type": "mcp",
        "meta": {{"position": {{"x": 850, "y": 200}}}},
        "data": {{
          "title": "MCP Tool",
          "callable": {{
            "id": "llm-auto-select",
            "name": "llm auto select",
            "desc": "Let the LLM automatically select the appropriate tool",
            "type": "system",
            "source": ""
          }},
          "inputsValues": {{}}
        }}
      }},
      {{
        "id": "end",
        "type": "end",
        "meta": {{"position": {{"x": 1100, "y": 200}}}},
        "data": {{"title": "End"}}
      }}
    ],
    "edges": [
      {{"sourceNodeID": "start", "targetNodeID": "browser_automation_fetch_orders"}},
      {{"sourceNodeID": "browser_automation_fetch_orders", "targetNodeID": "llm_analyze_data"}},
      {{"sourceNodeID": "llm_analyze_data", "targetNodeID": "mcp_send_email"}},
      {{"sourceNodeID": "mcp_send_email", "targetNodeID": "end"}}
    ],
    "metadata": {{
      "skillName": "workflow_name",
      "description": "What this workflow does"
    }}
  }},
  "data_mapping": {{
    "developing": {{
      "mappings": [
        {{
          "from": ["event.data.custom_field"],
          "to": [{{"target": "state.attributes.custom"}}],
          "on_conflict": "overwrite"
        }}
      ]
    }},
    "released": {{
      "mappings": [
        {{
          "from": ["event.data.custom_field"],
          "to": [{{"target": "state.attributes.custom"}}],
          "on_conflict": "overwrite"
        }}
      ]
    }},
    "node_transfers": {{}},
    "event_routing": {{}}
  }}
}}

NOTE: The `data_mapping` field is OPTIONAL. Baseline event-to-state mappings (human_text, qa_form,
notification, cloud_task_id, async_response) are always included automatically.
Only add `data_mapping` when the workflow needs EXTRA routing beyond the baseline.
Prefer mapping rules over code nodes for pure data movement.

For simple answers without code generation:
{{
  "action": "answer",
  "message": "Your explanation or answer here (human readable)"
}}

For requests that cannot be fulfilled:
{{
  "action": "reject",
  "message": "Explanation of why this cannot be done"
}}

## SUB-AGENT NODES (browser_automation, llm):
These nodes are sub-agents that execute prompts with their own tools. When configuring them, you're essentially "generating prompts from prompts" - translating the user's high-level goal into specific instructions for the sub-agent.

### BROWSER_AUTOMATION NODE (IMPORTANT):
Use for ANY task involving reading/interacting with web pages via a browser. Key guidelines:

1. **When to use**: Any task requiring browser interaction - web scraping, form filling, purchasing, data extraction from websites
2. **Step counting**: Each DOM extraction + action (click, move, type, scroll, etc.) = 1 step. Default max is 100 steps.
3. **Batch sizing**: For repetitive tasks (e.g., processing orders), estimate steps per item:
   - Simple page read: ~2-3 steps
   - Form fill + submit: ~5-7 steps  
   - Complex purchase flow (shipping label): ~10 steps per order
4. **Loop pattern (CRITICAL)**: If the sub-task has an unknown/variable number of items (common in e-commerce: returns, cases, disputes, buyer messages, orders), you MUST wrap the browser_automation node inside a loop node.
   - Reason: browser_automation can run only ~100 steps consecutively; long lists will exceed this.
   - Use batching: if task needs 10 steps/item, process ~5-8 items per browser_automation call
   - Loop iterates through batches until all items processed
   - Exception: only keep browser_automation outside a loop when it is clearly a one-shot operation (single login, single page fetch, single settings change)
5. **Integrated tools**: browser_automation has its own tools (mouse click, keyboard type, scroll, etc.) - all you need is a prompt
6. **JSON output**: For structured output, specify JSON format in the prompt (e.g., "Return results as JSON: {{products: [{{name, price}}]}}")
7. **Output location**: Results stored in node_state["result"] after execution

Example: Purchasing shipping labels for 50 orders (~10 steps each):
- Create loop node iterating over order batches (5 orders per batch)
- Inside loop: browser_automation node with prompt like:
  "For each order in {{{{batch}}}}: Navigate to shipping portal, fill in order details, purchase label, save confirmation. Return results as JSON."

Config example:
{{
  "provider": "browser-use",
  "task": "Navigate to {{{{url}}}} and extract product prices from the search results. Return as JSON: {{products: [{{name, price}}]}}",
  "browser": "new chromium",
  "timeout_seconds": 120,
  "modelProvider": "openai",
  "modelName": "gpt-4o"
}}

### LLM NODE (IMPORTANT - NO INTEGRATED TOOLS):
LLM nodes do NOT have tools integrated. To enable tool usage:
1. Follow LLM node with an mcp_tool node
2. Set mcp_tool's tool_name to "llm auto select" for LLM to pick tools dynamically
3. System prompt defines the agent's role and available capabilities
4. User prompt provides the specific task with {{{{variable}}}} placeholders
5. For complex reasoning, use higher temperature (0.7-0.9)
6. For deterministic extraction, use lower temperature (0.1-0.3)

### LLM+MCP SUB-AGENT PROMPT PATTERN (CRITICAL):
When LLM node works with mcp_tool as a sub-agent for multi-step tasks, the prompt MUST include these sections:

**System Prompt Sections (in order):**
1. **role**: Define the agent's expertise (e.g., "You are a Windows PC expert...")
2. **instructions** (task decomposition): 
   - Break complex tasks into manageable sub-tasks (divide and conquer)
   - Summarize measurable end goals for each task/sub-task
   - Craft a plan where each item translates to ≤3 tool calls
   - Execute ONE step at a time, return single JSON: {{"work_done": false, "next_tool_name": "...", "next_tool_input": {{...}}}}
   - When done: {{"work_done": true, "next_tool_name": "", "next_tool_input": {{}}}}
3. **instructions** (agentic execution):
   - OBSERVE BEFORE ACT: Gather context before modifying (use os_list_dir, read files)
   - VERIFY AFTER EVERY ACTION: Check results, don't assume success
   - PARSE OUTPUT CAREFULLY: Look for 'Error', 'Exception', 'Failed' in output
   - ITERATIVE PROBLEM-SOLVING: If fails, read error → identify cause → fix → re-run
   - SELF-CORRECTION LOOP: After 3 failed attempts, try alternative approach
4. **instructions** (code execution):
   - PREFER SHELL SCRIPT: Use run_shell_script for file ops, text processing
   - Use run_code (Python) for complex data structures, JSON, math
   - Write robust code with error handling, progress messages
   - Verify code results, don't assume success
5. **rules**: 
   - ONLY use tools from [Tools To Use] section
   - Verify tool name matches exactly before calling
   - Fall back to run_code/run_shell_script if no suitable tool
   - NEVER skip verification after tool calls
6. **tools_to_use**: List of available tool names (dynamically injected)

**User Prompt Sections:**
- **goals**: Specific measurable objectives for this task

Reference prompt: my_prompts/test_prompt2_pr-480482.json

## PROMPT MODULARITY (IMPORTANT):
For LLM and browser_automation nodes, use modular prompts instead of inline text:
1. **Create prompt file**: Save prompts in my_prompts/ directory as JSON files
2. **Reference by ID**: Set node's `promptSelection` config to the prompt ID (e.g., "pr-123456")
3. **Prompt file format**:
   {{
     "id": "pr-XXXXXX",
     "title": "descriptive_name",
     "sections": [  // System prompt sections
       {{"id": "role-xxx", "type": "role", "items": ["You are..."]}}
     ],
     "userSections": [  // User prompt sections
       {{"id": "user-goals-xxx", "type": "goals", "items": ["Goal 1", "Goal 2"]}},
       {{"id": "user-rules-xxx", "type": "rules", "items": ["Rule 1"]}},
       {{"id": "user-instructions-xxx", "type": "instructions", "items": ["Step 1", "Step 2"]}}
     ]
   }}
4. **Benefits**: To modify prompts later, update the prompt JSON file instead of node config
5. **Node config**: Set `"promptSelection": "pr-XXXXXX"` instead of inline system_prompt/user_prompt

## NODE_STATE DATA FLOW (LANGGRAPH):
Since we use LangGraph as the workflow runtime, node_state is the data carrier between nodes:
- **LLM node output**: node_state["result"]["llm_result"] and node_state["tool_input"]["input"]
- **MCP tool output**: node_state["tool_result"]
- **Code node**: node_state is directly accessible - use to move data between fields

Example code node to transform data:
```python
# Move tool result to a custom field
result = node_state["tool_result"]
node_state["processed_data"] = result["data"]
return node_state
```

## IMPORTANT:
- Generate complete, valid flowgrams
- Use descriptive node labels
- Position nodes to avoid overlap
- Include all necessary configurations
- Connect all nodes properly
"""

EDIT_FLOWGRAM_PROMPT = """You are a Code Agent for the Skill Editor, specializing in editing existing flowgrams.

## CURRENT FLOWGRAM:
{current_flowgram}

## EDIT REQUEST:
{edit_request}

## AVAILABLE NODE TYPES:
{node_types}

## NODE SCHEMA REFERENCE:
{node_schema}

## MAPPING DSL REFERENCE (data_mapping.json):
The Mapping DSL lets you declare data movement rules in data_mapping.json so that data flows between events, nodes, and state without code nodes. Prefer mapping rules over code nodes when the task is pure data routing.

{mapping_dsl}

## EDIT RULES:
1. Preserve existing node IDs when modifying nodes
2. Only change what's necessary for the edit
3. Maintain valid connections after edits
4. Update positions if adding/removing nodes to avoid overlap
5. Keep the start and end nodes

## CONDITION NODE STRUCTURE (IMPORTANT):
When adding or editing condition nodes:
1. They MUST have a `conditions` array in config with branch definitions
2. Each condition has a unique `key` (e.g., "if_xxx", "elseif_xxx", "else_xxx") and a `value` object
3. Order: if branch first, then any elseif branches, then else branch last
4. Edges FROM condition nodes MUST include `source_handle` matching the condition key

Example condition node config:
{{"conditions": [{{"key": "if_branch", "value": {{}}}}, {{"key": "else_branch", "value": {{}}}}]}}

Example edges FROM a condition node (CRITICAL - must include source_handle):
{{"source": "condition_1", "target": "success_node", "source_handle": "if_branch"}}
{{"source": "condition_1", "target": "failure_node", "source_handle": "else_branch"}}

## LOOP NODE STRUCTURE (IMPORTANT):
When adding or editing loop nodes, they MUST have:
1. A `blocks` array with block-start, content nodes, and block-end
2. An `internal_edges` array connecting the blocks
3. Internal positions relative to loop's coordinate system (block-start at x:30, content at x:120-450, block-end at right)

### LOOP MODES:
1. **loopFor**: Set loopMode to "loopFor", loopCountExpr to integer or Python expression
2. **loopWhile**: Set loopMode to "loopWhile", loopWhileExpr to Python expression (True to continue)
   - Example: loopWhileExpr = "state['result']['llm_result']['not_yet_finished']"

### INITIALIZE LOOP VARIABLES:
- For loopWhile, add a code node BEFORE the loop to initialize the expression variable
- Example: state["result"]["llm_result"]["not_yet_finished"] = True

## CONDITION NODE IF FIELD:
- Default: "state.condition" (uses node_state["condition"])
- Custom: Set "if" to "custom", "customExpr" to Python expression
- Examples: state["result"]["llm_result"]["success"] == True

## CODE NODE NOTE:
- Input parameter "state" IS the node_state throughout the workflow
- Use to initialize loop variables or transform data between nodes

## EDITING NODES INSIDE A LOOP:
When the user asks to add/remove/update nodes "inside", "in", or "within" a loop:
1. Find the target loop node in the flowgram
2. Modify its `blocks` array (add/remove/update nodes)
3. Update its `internal_edges` array to maintain proper connections
4. Keep block-start as the first node and block-end as the last node in the chain
5. Position new internal nodes between x:120-450, y:16

Example requests that target loop internals:
- "add an llm node inside the loop" → Add to loop's blocks array
- "remove the mcp node from the loop" → Remove from loop's blocks array
- "connect the llm to the code node in the loop" → Update loop's internal_edges

## SUB-AGENT NODES (browser_automation, llm):
These nodes are sub-agents that execute prompts. When configuring them, translate the user's goal into specific sub-agent instructions.

### BROWSER_AUTOMATION NODE:
Use for ANY task involving web page interaction. Key guidelines:
1. Each DOM extraction + action (click, move, type, scroll, etc.) = 1 step. Default max is 100 steps.
2. Has integrated tools (mouse, keyboard, scroll) - all you need is a prompt
3. For structured output, specify JSON format in the prompt
4. Output stored in node_state["result"]
5. If the sub-task has an unknown/variable number of items (returns/messages/cases/orders), put browser_automation inside a loop node (exception: clearly one-shot)

### LLM NODE (NO INTEGRATED TOOLS):
1. LLM does NOT have tools - follow with mcp_tool node for tool usage
2. Set mcp_tool's tool_name to "llm auto select" for dynamic tool selection
3. LLM output: node_state["result"]["llm_result"] and node_state["tool_input"]["input"]
4. MCP tool output: node_state["tool_result"]
5. Use code node to move data between node_state fields

### PROMPT MODULARITY:
For LLM and browser_automation nodes, use modular prompts:
1. Create prompt file in my_prompts/ directory (JSON format)
2. Set node's `promptSelection` to the prompt ID (e.g., "pr-123456")
3. To modify prompts later, update the prompt JSON file, not the node config

## OUTPUT FORMAT:
Respond with the complete updated flowgram:

{{
  "action": "edit_flowgram",
  "message": "Description of changes made",
  "flowgram": {{
    "nodes": [...],
    "edges": [...],
    "metadata": {{...}}
  }}
}}
"""


# ============================================================
# Code Agent Class
# ============================================================

class CodeAgent:
    """
    Code generation agent that creates and edits flowgrams.
    
    This agent:
    1. Generates flowgrams from natural language or plans
    2. Edits existing flowgrams based on requests
    3. Validates flowgram structure
    4. Iteratively fixes validation errors
    """
    
    def __init__(self, llm=None):
        """
        Initialize the code agent.
        
        Args:
            llm: LangChain LLM instance. If None, will use default from settings.
        """
        self._llm = llm
        self._current_flowgram: Optional[Flowgram] = None
        self._generation_history: List[Dict[str, Any]] = []
        logger.info("[CodeAgent] Initialized")
    
    @property
    def llm(self):
        """Lazy load LLM from settings if not provided"""
        if self._llm is None:
            try:
                self._llm = self._load_llm_from_settings()
                logger.info("[CodeAgent] Loaded LLM from settings")
            except Exception as e:
                logger.error(f"[CodeAgent] Failed to load LLM: {e}")
                raise
        return self._llm
    
    def _load_llm_from_settings(self):
        """Load LLM instance from application settings"""
        try:
            from app_context import AppContext
            from agent.ec_skills.llm_utils.llm_utils import pick_llm
            
            mainwin = AppContext.get_main_window()
            if mainwin is None:
                raise RuntimeError("Main window not available")
            
            config_manager = getattr(mainwin, 'config_manager', None)
            if config_manager is None:
                raise RuntimeError("Config manager not available")
            
            # Get LLM providers and default LLM from config_manager
            llm_providers = config_manager.llm_manager.get_all_providers()
            default_llm = config_manager.general_settings.default_llm
            
            logger.info(f"[CodeAgent] Default LLM setting: {default_llm}")
            logger.info(f"[CodeAgent] Available providers: {len(llm_providers) if llm_providers else 0} providers")
            
            if not llm_providers:
                raise RuntimeError("No LLM providers configured")
            
            # Log provider details (mask API keys)
            for provider in llm_providers:
                name = provider.get('name', 'unknown')
                api_key = provider.get('api_key') or provider.get('apiKey')
                if api_key:
                    masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
                    logger.info(f"[CodeAgent] Provider '{name}': API key = {masked_key}")
            
            # TODO: QUESTIONABLE CODE - Currently commented out, pending review
            # This code was originally intended to prefer OpenAI for complex flowgram generation,
            # but it has several issues:
            # 1. It forcibly overrides user's LLM configuration choice
            # 2. It caused RyoAIS and other custom LLMs to be ignored even when explicitly configured
            # 3. It assumes OpenAI is always better for skill editor tasks (not necessarily true)
            # 
            # Decision: Keep code commented for now, review later to determine if:
            # - This optimization is actually needed for flowgram generation quality
            # - If needed, implement it in a way that respects user configuration
            # - Or delete if proven unnecessary
            #
            # Related issue: RyoAIS was being forced to OpenAI, causing 5+ minute response times
            # 
            # # For skill editor, prefer OpenAI for complex flowgram generation
            # # Override default if OpenAI is available
            # skill_editor_llm = default_llm
            # if any(p.get('name', '').lower() == 'openai' for p in llm_providers):
            #     skill_editor_llm = 'openai'
            #     logger.info(f"[CodeAgent] Overriding default LLM '{default_llm}' with 'openai' for skill editor")
            # Use unified method to get default LLM config
            llm_config = config_manager.llm_manager.get_default_llm_config()
            
            llm_instance = pick_llm(
                default_llm=llm_config['provider_id'],
                llm_providers=llm_providers,
                config_manager=config_manager,
                allow_fallback=False
            )
            
            if not llm_instance:
                raise RuntimeError(f"[CodeAgent] Failed to create LLM instance for provider '{llm_config['provider_id']}'")
            
            # Log which model is being used
            model_name = getattr(llm_instance, 'model_name', None) or getattr(llm_instance, 'model', None)
            logger.info(f"[CodeAgent] Using LLM from Settings: {llm_config['provider_id']}, model: {model_name or llm_config['model_name']}")
            
            # Increase max_tokens for complex flowgram generation
            # Default is often 4096, but complex workflows need more
            if hasattr(llm_instance, 'max_tokens'):
                llm_instance.max_tokens = 16384
                logger.info(f"[CodeAgent] Set max_tokens to 16384 for complex flowgram generation")
            
            return llm_instance
            
        except Exception as e:
            logger.error(f"[CodeAgent] Failed to load LLM from Settings: {e}")
            raise
    
    def _format_canvas_context(self, canvas_context: Optional[Dict]) -> str:
        """Format canvas context for prompts"""
        if not canvas_context:
            return "Empty canvas (no nodes or edges)"
        
        nodes = canvas_context.get("nodes", [])
        edges = canvas_context.get("edges", [])
        
        if not nodes:
            return "Empty canvas (no nodes or edges)"
        
        lines = [f"Nodes ({len(nodes)}):"]
        for node in nodes[:10]:
            lines.append(f"  - {node.get('id')}: {node.get('type')} ({node.get('label', 'unnamed')})")
        
        if len(nodes) > 10:
            lines.append(f"  ... and {len(nodes) - 10} more nodes")
        
        lines.append(f"\nEdges ({len(edges)}):")
        for edge in edges[:10]:
            lines.append(f"  - {edge.get('source')} → {edge.get('target')}")
        
        if len(edges) > 10:
            lines.append(f"  ... and {len(edges) - 10} more edges")
        
        return "\n".join(lines)
    
    def _format_plan_context(self, plan: Optional[ImplementationPlan]) -> str:
        """Format implementation plan for prompts"""
        if not plan:
            return "No implementation plan provided"
        
        lines = [
            f"Summary: {plan.summary}",
            f"Complexity: {plan.complexity}",
            f"Estimated nodes: {', '.join(plan.estimated_nodes)}",
            "\n## PLAN STEPS (YOU MUST IMPLEMENT EACH STEP):"
        ]
        
        for i, step in enumerate(plan.steps, 1):
            lines.append(f"\n### Step {i}: {step.title}")
            lines.append(f"Description: {step.description}")
            if step.node_types:
                lines.append(f"**REQUIRED NODE TYPES FOR THIS STEP: {', '.join(step.node_types)}**")
                lines.append(f"You MUST create nodes of these types to implement this step.")
        
        lines.append("\n## CRITICAL PLAN IMPLEMENTATION RULES:")
        lines.append("1. **EVERY plan step MUST be implemented** - do not skip any steps")
        lines.append("2. **Use the EXACT node types specified** in each step's 'REQUIRED NODE TYPES'")
        lines.append("3. If a step says 'loop', you MUST create a loop node with blocks")
        lines.append("4. If a step says 'browser_automation', you MUST create a browser_automation node")
        lines.append("5. If a step says 'mcp_tool', you MUST create an mcp_tool node")
        lines.append("6. Connect the nodes from each step in sequence to form the complete workflow")
        
        return "\n".join(lines)

    @staticmethod
    async def _emit_progress(on_event, message: str) -> None:
        """Send a progress event to the client (best-effort)."""
        if not on_event:
            return
        try:
            import asyncio
            result = on_event({"type": "progress", "data": {"message": message}})
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    async def _invoke_llm_async(self, prompt: str, *, action: str = "") -> str:
        """Invoke LLM asynchronously"""
        logger.debug(f"[CodeAgent] Invoking LLM, prompt length: {len(prompt)}")
        try:
            if hasattr(self.llm, 'ainvoke'):
                response = await self.llm.ainvoke(prompt)
                token_tracker.record(response, agent="CodeAgent", action=action)
                result = response.content if hasattr(response, 'content') else str(response)
                logger.debug(f"[CodeAgent] LLM response length: {len(result)}")
                return result
            else:
                response = self.llm.invoke(prompt)
                token_tracker.record(response, agent="CodeAgent", action=action)
                result = response.content if hasattr(response, 'content') else str(response)
                logger.debug(f"[CodeAgent] LLM response length: {len(result)}")
                return result
        except Exception as e:
            logger.error(f"[CodeAgent] LLM invocation failed: {e}")
            raise
    
    async def _stream_llm_async(self, prompt: str):
        """Stream LLM response asynchronously"""
        logger.debug(f"[CodeAgent] Streaming LLM, prompt length: {len(prompt)}")
        chunk_count = 0
        try:
            if hasattr(self.llm, 'astream'):
                async for chunk in self.llm.astream(prompt):
                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if content:
                        chunk_count += 1
                        yield content
                logger.debug(f"[CodeAgent] Streaming complete, {chunk_count} chunks")
            elif hasattr(self.llm, 'stream'):
                for chunk in self.llm.stream(prompt):
                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if content:
                        chunk_count += 1
                        yield content
                logger.debug(f"[CodeAgent] Streaming complete, {chunk_count} chunks")
            else:
                response = await self._invoke_llm_async(prompt)
                yield response
        except Exception as e:
            logger.error(f"[CodeAgent] LLM streaming failed: {e}")
            raise
    
    def _parse_flowgram_from_response(self, response: str, task_context: Optional[str] = None) -> Optional[Dict]:
        """Extract flowgram JSON from LLM response
        
        Args:
            response: The LLM response to parse
            task_context: The original user request for logical sequencing during edge fixing
        """
        # Use stored task context if not provided
        if task_context is None:
            task_context = getattr(self, '_current_task_context', None)
        logger.debug(f"[CodeAgent] Parsing flowgram from response (length: {len(response)})")
        
        parsed_data = None
        
        # First try direct JSON parsing
        try:
            # Try to extract JSON from markdown code block
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                try:
                    parsed_data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # Try to find raw JSON object with "flowgram" key
            if not parsed_data:
                json_match = re.search(r'\{[\s\S]*"flowgram"[\s\S]*\}', response)
                if json_match:
                    try:
                        parsed_data = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass
            
            # Try to find just the flowgram object with "nodes" key
            if not parsed_data:
                json_match = re.search(r'\{[\s\S]*"nodes"[\s\S]*\}', response)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                        if "nodes" in data:
                            parsed_data = {"action": "generate_flowgram", "flowgram": data, "message": ""}
                        else:
                            parsed_data = data
                    except json.JSONDecodeError:
                        pass
            
        except Exception as e:
            logger.debug(f"[CodeAgent] Direct JSON parse failed: {e}")
        
        # If direct parsing failed, use ValidatorAgent to fix the JSON
        if not parsed_data:
            logger.info("[CodeAgent] Direct JSON parsing failed, using ValidatorAgent to repair")
            parsed_data = self._parse_with_validator(response)
        
        # Always fix disconnected nodes if we have a flowgram
        if parsed_data:
            parsed_data = self._fix_disconnected_nodes(parsed_data, task_context=task_context)
        
        return parsed_data
    
    def _fix_disconnected_nodes(self, data: Dict, task_context: Optional[str] = None) -> Dict:
        """Fix disconnected nodes in the flowgram using ValidatorAgent
        
        Args:
            data: The flowgram data to fix
            task_context: The original user request for logical sequencing
        """
        try:
            validator = get_validator_agent()
            fixed_data = validator.fix_disconnected_nodes(data, task_context=task_context)
            return fixed_data
        except Exception as e:
            logger.warning(f"[CodeAgent] Failed to fix disconnected nodes: {e}")
            return data
    
    def _parse_with_validator(self, response: str, continuation_attempt: int = 0) -> Optional[Dict]:
        """Use ValidatorAgent to parse and fix malformed JSON"""
        import asyncio
        
        MAX_CONTINUATION_ATTEMPTS = 2
        
        try:
            validator = get_validator_agent()
            validator.set_llm(self.llm)
            
            # Run async validation synchronously
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            validator.validate_and_fix(response)
                        )
                        result = future.result()
                else:
                    result = loop.run_until_complete(validator.validate_and_fix(response))
            except RuntimeError:
                result = asyncio.run(validator.validate_and_fix(response))
            
            if result.action == ValidatorAction.VALID or result.action == ValidatorAction.FIXED:
                logger.info(f"[CodeAgent] ValidatorAgent: {result.message}")
                data = result.fixed_json
                
                # Normalize the result
                if data:
                    if "flowgram" in data:
                        return data
                    if "nodes" in data:
                        return {"action": "generate_flowgram", "flowgram": data, "message": ""}
                    return data
            
            elif result.action == ValidatorAction.TRUNCATED:
                # Output was truncated - try to continue generation
                if continuation_attempt < MAX_CONTINUATION_ATTEMPTS:
                    logger.info(f"[CodeAgent] Output truncated, requesting continuation (attempt {continuation_attempt + 1})")
                    continued_response = self._request_continuation(result.truncated_content)
                    if continued_response:
                        # Combine original + continuation and try again
                        combined = response.rstrip() + continued_response
                        return self._parse_with_validator(combined, continuation_attempt + 1)
                else:
                    logger.warning(f"[CodeAgent] Max continuation attempts reached, cannot complete truncated output")
            
            else:
                logger.warning(f"[CodeAgent] ValidatorAgent could not fix JSON: {result.message}")
                if result.original_error:
                    logger.debug(f"[CodeAgent] Original error: {result.original_error}")
            
        except Exception as e:
            logger.error(f"[CodeAgent] ValidatorAgent failed: {e}")
        
        return None
    
    def _request_continuation(self, truncated_content: str) -> Optional[str]:
        """Request LLM to continue generating from truncated output"""
        import asyncio
        
        try:
            # Take the last portion of truncated content for context
            context_length = min(4000, len(truncated_content))
            context = truncated_content[-context_length:]
            
            continuation_prompt = f"""Your previous response was truncated. Continue EXACTLY from where you left off.

DO NOT repeat any content. Just continue the JSON from this point:

...{context}

Continue the JSON output (do not include any text before the continuation):"""
            
            logger.info("[CodeAgent] Requesting continuation from LLM")
            
            # Run async LLM call
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self._invoke_llm_async(continuation_prompt)
                        )
                        continuation = future.result()
                else:
                    continuation = loop.run_until_complete(self._invoke_llm_async(continuation_prompt))
            except RuntimeError:
                continuation = asyncio.run(self._invoke_llm_async(continuation_prompt))
            
            if continuation:
                logger.info(f"[CodeAgent] Received continuation (length: {len(continuation)})")
                return continuation
                
        except Exception as e:
            logger.error(f"[CodeAgent] Continuation request failed: {e}")
        
        return None

    def _ensure_start_end_nodes(self, flowgram: Optional[Flowgram]) -> None:
        """Ensure the flowgram has start/end nodes, minimal connectivity, and metadata defaults."""
        if not flowgram:
            return

        if flowgram.metadata is None:
            flowgram.metadata = {}

        metadata = flowgram.metadata

        if not metadata.get("skillName"):
            base_name = metadata.get("name") or "generated skill"
            slug = re.sub(r"[^a-z0-9]+", "_", base_name.lower()).strip("_")
            metadata["skillName"] = slug or "generated_skill"

        if not metadata.get("description"):
            metadata["description"] = metadata.get("summary") or "Workflow generated via Skill Editor"

        start_node = next((node for node in flowgram.nodes if node.type == "start"), None)
        if not start_node:
            start_node = FlowgramNode(
                id="start",
                type="start",
                label="Start",
                position=NodePosition(x=START_POSITION_X, y=START_POSITION_Y),
                config={}
            )
            flowgram.nodes.insert(0, start_node)

        end_node = next((node for node in flowgram.nodes if node.type == "end"), None)
        if not end_node:
            end_node = FlowgramNode(
                id="end",
                type="end",
                label="End",
                position=NodePosition(x=START_POSITION_X, y=START_POSITION_Y),  # Will be repositioned by layout
                config={}
            )
            flowgram.nodes.append(end_node)

        def edge_exists(src: str, dst: str) -> bool:
            return any(edge.source == src and edge.target == dst for edge in flowgram.edges)

        if not any(edge.source == start_node.id for edge in flowgram.edges):
            next_node = next((node for node in flowgram.nodes if node.id != start_node.id), None)
            target_id = next_node.id if next_node else end_node.id
            if not edge_exists(start_node.id, target_id):
                flowgram.edges.insert(0, FlowgramEdge(source=start_node.id, target=target_id))

        if not any(edge.target == end_node.id for edge in flowgram.edges):
            candidate = next((node for node in reversed(flowgram.nodes) if node.id not in {start_node.id, end_node.id}), None)
            source_id = candidate.id if candidate else start_node.id
            if not edge_exists(source_id, end_node.id):
                flowgram.edges.append(FlowgramEdge(source=source_id, target=end_node.id))

        flowgram.metadata = metadata
        
        # Apply automatic layout to avoid overlapping nodes
        self._apply_layout(flowgram)
    
    def _fix_missing_incoming_edges(self, flowgram: Flowgram) -> None:
        """
        Auto-fix missing incoming edges to condition and loop nodes (including loop internals).
        Infers the previous node based on position (x-coordinate) and creates the missing edge.
        """
        if not flowgram or not flowgram.nodes:
            return

        def fix_for(nodes: List[FlowgramNode], edges: List[FlowgramEdge]) -> None:
            nodes_with_incoming = set()
            for edge in edges:
                if edge.target:
                    nodes_with_incoming.add(edge.target)

            sorted_nodes = sorted(nodes, key=lambda n: n.position.x if n.position else 0)

            for i, node in enumerate(sorted_nodes):
                if node.type in ["start", "block-start"]:
                    continue
                if node.id in nodes_with_incoming:
                    continue

                prev_node = None
                for j in range(i - 1, -1, -1):
                    candidate = sorted_nodes[j]
                    if candidate.type not in ["end", "block-end"]:
                        prev_node = candidate
                        break

                if prev_node:
                    new_edge = FlowgramEdge(source=prev_node.id, target=node.id)
                    edges.append(new_edge)
                    nodes_with_incoming.add(node.id)
                    logger.info(f"[CodeAgent] Auto-fixed: Added missing edge {prev_node.id} -> {node.id}")

        # Top-level
        fix_for(flowgram.nodes, flowgram.edges)

        # Loop internals
        for node in flowgram.nodes:
            if node.type == "loop" and node.blocks:
                internal_edges = list(node.internal_edges or [])
                fix_for(node.blocks, internal_edges)
                node.internal_edges = internal_edges
    
    def _fix_node_naming(self, flowgram: Flowgram) -> None:
        """
        Auto-fix node IDs to follow naming convention (type prefix).
        Updates node IDs and all edge references.
        """
        if not flowgram or not flowgram.nodes:
            return
        
        type_to_prefix = {
            "llm": "llm_",
            "condition": "condition_",
            "loop": "loop_",
            "browser_automation": "browser_automation_",
            "mcp_tool": "mcp_tool_",
            "code": "code_",
            "chat_node": "chat_node_",
            "pend_event": "pend_event_",
            "http": "http_",
            "rag": "rag_",
        }
        
        # Build mapping of old ID -> new ID
        id_mapping = {}
        for node in flowgram.nodes:
            if node.type in type_to_prefix:
                expected_prefix = type_to_prefix[node.type]
                if not node.id.startswith(expected_prefix):
                    # Generate new ID with correct prefix
                    # Remove any existing type-like prefix first
                    clean_id = node.id
                    for prefix in type_to_prefix.values():
                        if clean_id.startswith(prefix):
                            clean_id = clean_id[len(prefix):]
                            break
                    # Also handle short prefixes like "browser_" or "mcp_"
                    short_prefixes = ["browser_", "mcp_", "automation_"]
                    for sp in short_prefixes:
                        if clean_id.startswith(sp):
                            clean_id = clean_id[len(sp):]
                            break
                    
                    new_id = f"{expected_prefix}{clean_id}"
                    id_mapping[node.id] = new_id
                    logger.info(f"[CodeAgent] Auto-fixed: Renamed node '{node.id}' -> '{new_id}'")
        
        # Apply ID changes to nodes
        for node in flowgram.nodes:
            if node.id in id_mapping:
                node.id = id_mapping[node.id]
            # Also fix blocks inside loop nodes
            if node.blocks:
                for block in node.blocks:
                    if block.id in id_mapping:
                        block.id = id_mapping[block.id]
        
        # Update edge references — use field names directly, NOT @property aliases
        # (edge.source is a read-only @property returning sourceNodeID; assignment
        #  via the property raises AttributeError in Pydantic v2)
        for edge in flowgram.edges:
            if edge.sourceNodeID in id_mapping:
                edge.sourceNodeID = id_mapping[edge.sourceNodeID]
            if edge.targetNodeID in id_mapping:
                edge.targetNodeID = id_mapping[edge.targetNodeID]
        
        # Update internal edges in loop nodes
        for node in flowgram.nodes:
            if node.internal_edges:
                for edge in node.internal_edges:
                    if edge.sourceNodeID in id_mapping:
                        edge.sourceNodeID = id_mapping[edge.sourceNodeID]
                    if edge.targetNodeID in id_mapping:
                        edge.targetNodeID = id_mapping[edge.targetNodeID]
    
    def _apply_layout(self, flowgram: Flowgram) -> None:
        """
        Apply automatic layout algorithm to position nodes.
        Uses Sugiyama-style layered DAG placement to avoid overlapping
        and tangled edges. Accounts for different node sizes (e.g., loop nodes are larger).
        """
        if not flowgram or not flowgram.nodes:
            return
        
        try:
            # Extract node IDs, edge tuples, and node types
            node_ids = [node.id for node in flowgram.nodes]
            edge_tuples = [(edge.source, edge.target) for edge in flowgram.edges]
            node_types = {node.id: node.type for node in flowgram.nodes}
            
            # Compute placement using the placement algorithm with node type awareness
            placement = place_nodes(node_ids, edge_tuples, node_types)
            
            # Apply placement to nodes
            for node in flowgram.nodes:
                if node.id in placement:
                    x, y = placement[node.id]
                    node.position = NodePosition(x=x, y=y)
            
            logger.debug(f"[CodeAgent] Applied layout to {len(flowgram.nodes)} nodes")
        except Exception as e:
            logger.warning(f"[CodeAgent] Layout failed, using default positions: {e}")
            # Fallback: simple vertical layout
            for i, node in enumerate(flowgram.nodes):
                if not node.position:
                    node.position = NodePosition(
                        x=START_POSITION_X,
                        y=START_POSITION_Y + i * DEFAULT_NODE_SPACING_Y
                    )

    def _summarize_flowgram(self, flowgram: Optional[Flowgram]) -> str:
        """Generate a concise human-readable summary of the flowgram."""
        if not flowgram or not flowgram.nodes:
            return "Created a starter workflow."

        metadata = flowgram.metadata or {}
        skill_name = metadata.get("skillName") or metadata.get("name")
        total_nodes = len(flowgram.nodes)
        unique_types = sorted({node.type for node in flowgram.nodes if node.type})

        ordered_nodes = sorted(
            flowgram.nodes,
            key=lambda n: (
                n.position.x if n.position else 0,
                n.position.y if n.position else 0,
            )
        )
        labels = [node.label or node.id for node in ordered_nodes]
        path_preview = " → ".join(labels[:6])
        if len(labels) > 6:
            path_preview += " → …"

        type_text = ", ".join(unique_types) if unique_types else "mixed nodes"
        prefix = f"Created '{skill_name}' workflow" if skill_name else "Created workflow"
        summary = f"{prefix} with {total_nodes} nodes ({type_text})."
        if path_preview:
            summary += f" Primary path: {path_preview}."
        return summary

    def _finalize_message(self, raw_message: Any, flowgram: Optional[Flowgram]) -> str:
        """Ensure the message returned to the user is human-friendly."""
        if isinstance(raw_message, str):
            text = raw_message.strip()
            if text:
                return text

        if isinstance(raw_message, dict):
            for key in ("summary", "description"):
                value = raw_message.get(key)
                if isinstance(value, str):
                    text = value.strip()
                    if text:
                        return text

        return self._summarize_flowgram(flowgram)

    def _apply_internal_layout(self, blocks: List[FlowgramNode]) -> None:
        """
        Apply layout to internal nodes of a loop.
        Positions block-start at left, block-end at right, and content nodes in between.
        """
        if not blocks:
            return
        
        x_start = LOOP_INTERNAL_CFG["x_start"]
        x_end = LOOP_INTERNAL_CFG["x_end"]
        y_start = LOOP_INTERNAL_CFG["y_start"]
        spacing_x = LOOP_INTERNAL_CFG["node_spacing_x"]
        spacing_y = LOOP_INTERNAL_CFG["node_spacing_y"]
        
        # Separate block markers from content nodes
        block_start = None
        block_end = None
        content_nodes = []
        
        for node in blocks:
            if node.type == "block-start":
                block_start = node
            elif node.type == "block-end":
                block_end = node
            else:
                content_nodes.append(node)
        
        # Position block-start
        if block_start:
            block_start.position = NodePosition(
                x=LOOP_INTERNAL_CFG["block_start_x"],
                y=LOOP_INTERNAL_CFG["block_start_y"]
            )
        
        # Position block-end
        if block_end:
            block_end.position = NodePosition(
                x=LOOP_INTERNAL_CFG["block_end_x"],
                y=LOOP_INTERNAL_CFG["block_end_y"]
            )
        
        # Position content nodes in the usable area with proper spacing
        if content_nodes:
            # Calculate available width for content nodes
            usable_width = x_end - x_start
            
            # Arrange content nodes horizontally with spacing
            num_nodes = len(content_nodes)
            if num_nodes == 1:
                # Single node: center it
                content_nodes[0].position = NodePosition(
                    x=x_start + usable_width // 2 - 100,  # Center (assuming ~200px node width)
                    y=y_start
                )
            else:
                # Multiple nodes: distribute with spacing
                # Calculate step based on number of nodes
                total_spacing = (num_nodes - 1) * spacing_x
                if total_spacing > usable_width:
                    # Not enough horizontal space, stack vertically
                    for i, node in enumerate(content_nodes):
                        node.position = NodePosition(
                            x=x_start,
                            y=y_start + i * spacing_y
                        )
                else:
                    # Distribute horizontally
                    for i, node in enumerate(content_nodes):
                        node.position = NodePosition(
                            x=x_start + i * spacing_x,
                            y=y_start
                        )

    def _maybe_save_inline_prompt(self, node_id: str, node_type: str, config: Dict[str, Any]) -> None:
        """
        If a node has inline prompts (systemPrompt/prompt) but no promptSelection,
        save them into my_prompts as a new prompt file and set promptSelection to that ID.
        """
        try:
            prompt_sel = config.get("promptSelection")
            if prompt_sel not in [None, "", "inline", "in-line"]:
                return

            system_prompt = config.get("systemPrompt") or config.get("system_prompt")
            user_prompt = config.get("prompt") or config.get("user_prompt")
            if not system_prompt and not user_prompt:
                return

            my_prompts_dir = _get_my_prompts_dir()
            my_prompts_dir.mkdir(parents=True, exist_ok=True)
            prompt_id = f"pr-{uuid.uuid4().hex[:6]}"
            base_id = (node_id or "").strip()
            base_type = (node_type or "").strip()
            if base_id and base_type and base_id.startswith(base_type + "_"):
                title = f"{base_id}_prompt"
            else:
                title = f"{base_type or 'node'}_{base_id or 'node'}_prompt"
            now_iso = datetime.utcnow().isoformat()

            prompt_doc: Dict[str, Any] = {
                "id": prompt_id,
                "title": title,
                "topic": node_type,
                "usageCount": 0,
                "sections": [],
                "userSections": [],
                "lastModified": now_iso,
            }

            lower_type = (node_type or "").lower()
            normalized_user = (user_prompt or "").strip()
            return_hint = ""
            if normalized_user:
                for marker in ["Return ", "return ", "RETURN "]:
                    if marker in normalized_user:
                        return_hint = normalized_user.split(marker, 1)[1].strip()
                        break

            if system_prompt:
                prompt_doc["sections"].append({
                    "id": f"instructions-{uuid.uuid4().hex[:8]}",
                    "type": "instructions",
                    "items": [system_prompt],
                })
            if user_prompt:
                prompt_doc["sections"].append({
                    "id": f"goals-{uuid.uuid4().hex[:8]}",
                    "type": "goals",
                    "items": [normalized_user],
                })

            if lower_type in ["browser_automation", "browser-automation"]:
                instr = [
                    "Follow the task goal precisely and operate only within the target website.",
                    "Be explicit and step-by-step; avoid skipping important UI interactions.",
                    "Do not fabricate outcomes; if blocked by login, captcha, or unexpected UI, report it clearly.",
                ]
                if return_hint:
                    instr.append(f"Return exactly the requested output format: {return_hint}")
                else:
                    instr.append("Return a machine-readable result (JSON) and do not include extra prose.")
                prompt_doc["sections"].append({
                    "id": f"guidelines-{uuid.uuid4().hex[:8]}",
                    "type": "guidelines",
                    "items": instr,
                })

                prompt_doc["sections"].append({
                    "id": f"rules-{uuid.uuid4().hex[:8]}",
                    "type": "rules",
                    "items": [
                        "Return ONLY valid JSON. No markdown, no backticks, no additional text.",
                        "Always follow the output schema exactly.",
                        "If you cannot complete the task, return a JSON object with success=false and include a clear error message.",
                        "The JSON must be parseable by standard JSON parsers.",
                        "Output JSON schema: {\"success\": true|false, \"summary\": \"string\", \"result\": { }, \"errors\": [ {\"message\": \"string\", \"details\": { } } ] }",
                    ],
                })
                prompt_doc["sections"].append({
                    "id": f"examples-{uuid.uuid4().hex[:8]}",
                    "type": "examples",
                    "items": [
                        "Example JSON output: {\n  \"success\": true,\n  \"summary\": \"Logged in and retrieved 3 open returns\",\n  \"result\": {\n    \"returns\": [\n      {\"order_id\": \"123-456\", \"status\": \"open\"}\n    ]\n  },\n  \"errors\": []\n}",
                    ],
                })
            else:
                instr = [
                    "Follow the task goal precisely.",
                    "Be explicit and step-by-step; include checks and edge cases when relevant.",
                    "Do not fabricate results; if information is missing, state what is missing and what to do next.",
                ]
                if return_hint:
                    instr.append(f"Return exactly the requested output format: {return_hint}")
                prompt_doc["sections"].append({
                    "id": f"guidelines-{uuid.uuid4().hex[:8]}",
                    "type": "guidelines",
                    "items": instr,
                })

                if lower_type in ["llm"]:
                    prompt_doc["sections"].append({
                        "id": f"rules-{uuid.uuid4().hex[:8]}",
                        "type": "rules",
                        "items": [
                            "Return ONLY valid JSON. No markdown, no backticks, no additional text.",
                            "Always follow the output schema exactly.",
                            "If you are missing required information, return a JSON object with status=error and list what is missing.",
                            "The JSON must be parseable by standard JSON parsers.",
                            "Output JSON schema: {\"status\": \"ok\"|\"error\", \"summary\": \"string\", \"data\": { }, \"missing\": [\"string\"], \"errors\": [ {\"message\": \"string\", \"details\": { } } ] }",
                        ],
                    })
                    prompt_doc["sections"].append({
                        "id": f"examples-{uuid.uuid4().hex[:8]}",
                        "type": "examples",
                        "items": [
                            "Example JSON output: {\n  \"status\": \"ok\",\n  \"summary\": \"Classified the case and extracted key fields\",\n  \"data\": {\n    \"case_type\": \"return\",\n    \"order_id\": \"123-456\",\n    \"customer_issue\": \"item damaged\"\n  },\n  \"missing\": [],\n  \"errors\": []\n}",
                        ],
                    })

            my_prompts_dir = _get_my_prompts_dir()
            out_path = my_prompts_dir / f"{title}.json"
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(prompt_doc, f, ensure_ascii=False, indent=2)

            config["promptSelection"] = prompt_id
            logger.info(f"[CodeAgent] Saved inline prompt for node '{node_id}' to {out_path}")
        except Exception as e:
            logger.warning(f"[CodeAgent] Failed to save inline prompt for node '{node_id}': {e}")

    def _apply_config_defaults(self, node_type: str, config: Dict[str, Any]) -> None:
        def _get_default_node_llm_config() -> Dict[str, Any]:
            defaults = {
                "modelProvider": "",
                "modelName": "",
                "apiHost": "",
                "temperature": 0.3,
                "useThinking": False,
            }
            try:
                from app_context import AppContext
                mainwin = AppContext.get_main_window()
                if not mainwin or not hasattr(mainwin, 'config_manager'):
                    return defaults

                llm_config = mainwin.config_manager.llm_manager.get_default_llm_config()
                provider_dict = llm_config.get("provider_dict") or {}
                defaults["modelProvider"] = llm_config.get("provider_id") or ""
                defaults["modelName"] = llm_config.get("model_name") or ""
                defaults["apiHost"] = provider_dict.get("base_url") or ""
            except Exception as e:
                logger.warning(f"[CodeAgent] Failed to load default node LLM config from Settings: {e}")
            return defaults

        llm_defaults = _get_default_node_llm_config()

        if node_type == "llm":
            if llm_defaults["modelProvider"]:
                config.setdefault("modelProvider", llm_defaults["modelProvider"])
            if llm_defaults["modelName"]:
                config.setdefault("modelName", llm_defaults["modelName"])
            config.setdefault("temperature", llm_defaults["temperature"])
            config.setdefault("useThinking", llm_defaults["useThinking"])
            config.setdefault("attachments", [])
            config.setdefault("apiKey", "")
            if llm_defaults["apiHost"]:
                config.setdefault("apiHost", llm_defaults["apiHost"])
            if not config.get("promptSelection"):
                config["promptSelection"] = DEFAULT_LLM_PROMPT_ID
                logger.info(f"[CodeAgent] LLM node missing promptSelection; defaulting to {DEFAULT_LLM_PROMPT_ID}")

            config.setdefault("systemPrompt", "")
            config.setdefault("prompt", "")

        elif node_type == "browser_automation":
            provider = config.get("provider")
            if provider and not config.get("tool"):
                config["tool"] = provider
            if "provider" in config:
                del config["provider"]
            if llm_defaults["modelProvider"]:
                config.setdefault("modelProvider", llm_defaults["modelProvider"])
            if llm_defaults["modelName"]:
                config.setdefault("modelName", llm_defaults["modelName"])
            config.setdefault("browser", "new chromium")
            config.setdefault("browserDriver", "native")
            config.setdefault("temperature", llm_defaults["temperature"])
            config.setdefault("useThinking", llm_defaults["useThinking"])
            config.setdefault("timeout_seconds", 120)
            config.setdefault("tool", "browser-use")
            config.setdefault("cdpPort", "")
            config.setdefault("shopName", "")
            config.setdefault("customShopName", "")
            config.setdefault("profile", "")
            if not config.get("promptSelection"):
                config["promptSelection"] = DEFAULT_BROWSER_PROMPT_ID
                logger.info(
                    f"[CodeAgent] Browser node missing promptSelection; defaulting to {DEFAULT_BROWSER_PROMPT_ID}")

            config.setdefault("systemPrompt", "")
            config.setdefault("prompt", "")
        elif node_type == "code":
            config.setdefault("language", "python")
            if not config.get("code"):
                config["code"] = CODE_NODE_DEFAULT_TEMPLATE
    def _parse_node(self, n: Dict[str, Any], index: int) -> FlowgramNode:
        """Parse a node dict into FlowgramNode, handling loop and condition nodes."""
        pos = n.get("position", {"x": 100, "y": 100})
        node_type = n.get("type", "llm")
        # Normalize type naming
        if node_type == "browser-automation":
            node_type = "browser_automation"
        config = dict(n.get("config", {}) or {})

        # If LLM provided data.inputsValues, merge into config (using content values)
        data_section = n.get("data", {}) or {}
        inputs_values = data_section.get("inputsValues") or {}
        for key, val in inputs_values.items():
            if key in config:
                continue
            if isinstance(val, dict) and "content" in val:
                config[key] = val.get("content")
            else:
                config[key] = val

        # If prompts are inline and promptSelection is missing/inline, persist a prompt file
        self._maybe_save_inline_prompt(n.get("id", f"node_{index}"), node_type, config)

        # Apply node-type defaults so validator/canvas get required fields
        self._apply_config_defaults(node_type, config)
        
        # Handle condition nodes - ensure they have conditions array
        if node_type == "condition":
            if "conditions" not in config or not config.get("conditions"):
                # Generate unique branch keys
                node_id = n.get("id", f"condition_{index}")
                config["conditions"] = [
                    {"key": f"if_{node_id[-5:]}", "value": {}},
                    {"key": f"else_{node_id[-5:]}", "value": {}},
                ]
        
        # Parse blocks for loop nodes
        blocks = None
        internal_edges = None
        
        if node_type == "loop":
            blocks_data = n.get("blocks", [])
            if blocks_data:
                blocks = [self._parse_node(b, i) for i, b in enumerate(blocks_data)]
                # Apply internal layout to ensure proper spacing
                self._apply_internal_layout(blocks)
            else:
                # Create default block-start and block-end if not provided
                block_start_id = f"block_start_{n.get('id', index)}"
                block_end_id = f"block_end_{n.get('id', index)}"
                blocks = [
                    FlowgramNode(
                        id=block_start_id,
                        type="block-start",
                        label="Loop Start",
                        position=NodePosition(
                            x=LOOP_INTERNAL_CFG["block_start_x"],
                            y=LOOP_INTERNAL_CFG["block_start_y"]
                        ),
                        config={}
                    ),
                    FlowgramNode(
                        id=block_end_id,
                        type="block-end",
                        label="Loop End",
                        position=NodePosition(
                            x=LOOP_INTERNAL_CFG["block_end_x"],
                            y=LOOP_INTERNAL_CFG["block_end_y"]
                        ),
                        config={}
                    )
                ]
                internal_edges = [
                    FlowgramEdge(source=block_start_id, target=block_end_id)
                ]
            
            # Parse internal edges - check both "internal_edges" and "edges" keys
            # ValidatorAgent uses "edges" while LLM might use "internal_edges"
            internal_edges_data = n.get("internal_edges", []) or n.get("edges", [])
            if internal_edges_data:
                internal_edges = [
                    FlowgramEdge(
                        source=e.get("source") or e.get("sourceNodeID") or "",
                        target=e.get("target") or e.get("targetNodeID") or "",
                        source_handle=e.get("source_handle") or e.get("sourceHandle") or e.get("sourcePortID"),
                        target_handle=e.get("target_handle") or e.get("targetHandle") or e.get("targetPortID"),
                    )
                    for e in internal_edges_data
                ]

        return FlowgramNode(
            id=n.get("id", f"node_{index}"),
            type=node_type,
            label=n.get("label", n.get("title", n.get("id", "Node"))),
            title=n.get("title", n.get("label", n.get("id", "Node"))),
            position=NodePosition(
                x=pos.get("x", 100),
                y=pos.get("y", 100)
            ),
            config=config,
            blocks=blocks,
            internal_edges=internal_edges,
        )

    def _parse_code_agent_output(self, response: str) -> CodeAgentOutput:
        """Parse LLM response into CodeAgentOutput"""
        data = self._parse_flowgram_from_response(response)
        
        if not data:
            return CodeAgentOutput(
                action=CodeAgentAction.ANSWER,
                message=response
            )
        
        # Parse action
        action_str = data.get("action", "generate_flowgram")
        try:
            action = CodeAgentAction(action_str)
        except ValueError:
            action = CodeAgentAction.GENERATE_FLOWGRAM
        
        # Parse flowgram if present
        flowgram = None
        flowgram_data = data.get("flowgram")
        if flowgram_data:
            try:
                nodes = []
                for n in flowgram_data.get("nodes", []):
                    nodes.append(self._parse_node(n, len(nodes)))
                
                edges = []
                for e in flowgram_data.get("edges", []):
                    # Handle both source/target and sourceNodeID/targetNodeID formats
                    source = e.get("source") or e.get("sourceNodeID") or ""
                    target = e.get("target") or e.get("targetNodeID") or ""
                    edges.append(FlowgramEdge(
                        source=source,
                        target=target,
                        source_handle=e.get("source_handle") or e.get("sourceHandle") or e.get("sourcePortID"),
                        target_handle=e.get("target_handle") or e.get("targetHandle") or e.get("targetPortID"),
                        label=e.get("label")
                    ))
                
                flowgram = Flowgram(
                    nodes=nodes,
                    edges=edges,
                    metadata=flowgram_data.get("metadata", {})
                )
                self._ensure_start_end_nodes(flowgram)
                self._fix_missing_incoming_edges(flowgram)
                self._fix_node_naming(flowgram)

                # Safety net: if edges were lost (e.g. node renaming failed earlier),
                # rebuild the sequential chain so nodes are never fully isolated.
                node_ids = {n.id for n in flowgram.nodes}
                valid_edges = [e for e in flowgram.edges if e.sourceNodeID in node_ids and e.targetNodeID in node_ids]
                if len(valid_edges) < len(flowgram.edges):
                    dropped = len(flowgram.edges) - len(valid_edges)
                    logger.warning(f"[CodeAgent] Dropped {dropped} invalid edge(s) referencing non-existent nodes")
                    flowgram.edges = valid_edges
                if len(flowgram.nodes) > 1 and not flowgram.edges:
                    logger.warning("[CodeAgent] No valid edges after parsing — rebuilding sequential chain")
                    self._fix_missing_incoming_edges(flowgram)
                    self._ensure_start_end_nodes(flowgram)

                logger.info(f"[CodeAgent] Parsed flowgram: {len(flowgram.nodes)} nodes, {len(flowgram.edges)} edges")
            except Exception as e:
                import traceback as _tb
                logger.warning(f"[CodeAgent] Error parsing flowgram: {e}\n{_tb.format_exc()}")

        message = self._finalize_message(data.get("message"), flowgram)

        # Extract data_mapping from LLM response and merge with baseline defaults
        data_mapping = self._build_data_mapping(data.get("data_mapping"))

        return CodeAgentOutput(
            action=action,
            message=message,
            flowgram=flowgram,
            data_mapping=data_mapping,
        )
    
    # ------------------------------------------------------------------
    # data_mapping.json construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_data_mapping(llm_mapping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build a data_mapping.json payload by merging LLM-generated rules on
        top of the baseline defaults.

        The baseline covers event→state routing for human_text, qa_form,
        notification, cloud_task_id, and async_response.  The LLM may add
        workflow-specific rules (e.g. webhook fields, node transfers).

        Returns a ready-to-persist ``data_mapping.json`` dict.
        """
        import copy
        mapping = copy.deepcopy(DEFAULT_BASELINE_MAPPINGS)

        if not llm_mapping or not isinstance(llm_mapping, dict):
            return mapping

        # Merge extra mappings produced by the LLM into each run-mode section
        for mode in ("developing", "released"):
            extra = llm_mapping.get(mode)
            if isinstance(extra, dict):
                extra_rules = extra.get("mappings")
                if isinstance(extra_rules, list):
                    mapping[mode]["mappings"].extend(extra_rules)
                # Let LLM override options if explicitly provided
                extra_opts = extra.get("options")
                if isinstance(extra_opts, dict):
                    mapping[mode]["options"].update(extra_opts)

        # Merge node_transfers & event_routing if provided
        for key in ("node_transfers", "event_routing"):
            extra_section = llm_mapping.get(key)
            if isinstance(extra_section, dict):
                mapping[key].update(extra_section)

        return mapping

    def validate_flowgram(self, flowgram: Flowgram, plan: Optional[ImplementationPlan] = None) -> ValidationResult:
        """Validate a flowgram structure"""
        logger.debug(f"[CodeAgent] Validating flowgram with {len(flowgram.nodes)} nodes")
        errors = []
        warnings = []
        
        node_ids = {n.id for n in flowgram.nodes}
        
        # Check if plan's required node types are present
        if plan and plan.estimated_nodes:
            generated_types = {n.type for n in flowgram.nodes}
            # Also check blocks inside loop nodes
            for node in flowgram.nodes:
                if node.type == "loop" and node.blocks:
                    for block in node.blocks:
                        generated_types.add(block.type)
            
            for required_type in plan.estimated_nodes:
                # Normalize type names (browser-automation vs browser_automation)
                normalized_required = required_type.replace("-", "_")
                normalized_generated = {t.replace("-", "_") for t in generated_types}
                
                if normalized_required not in normalized_generated and required_type not in ["start", "end", "block-start", "block-end"]:
                    errors.append(ValidationError(
                        message=f"Plan requires '{required_type}' node but none was generated. The plan specified this node type must be used.",
                        severity="error"
                    ))
        
        # Check for start node
        has_start = any(n.type == "start" for n in flowgram.nodes)
        if not has_start:
            errors.append(ValidationError(
                message="Flowgram must have a 'start' node",
                severity="error"
            ))
        
        # Check for end node
        has_end = any(n.type == "end" for n in flowgram.nodes)
        if not has_end:
            errors.append(ValidationError(
                message="Flowgram must have an 'end' node",
                severity="error"
            ))
        
        # Check for duplicate node IDs
        seen_ids = set()
        for node in flowgram.nodes:
            if node.id in seen_ids:
                errors.append(ValidationError(
                    node_id=node.id,
                    message=f"Duplicate node ID: {node.id}",
                    severity="error"
                ))
            seen_ids.add(node.id)
        
        # Check node types are valid
        for node in flowgram.nodes:
            if node.type not in NODE_TYPES:
                warnings.append(ValidationError(
                    node_id=node.id,
                    message=f"Unknown node type: {node.type}",
                    severity="warning"
                ))
        
        # Check node naming convention - ID must start with node type prefix
        type_to_prefix = {
            "llm": "llm_",
            "condition": "condition_",
            "loop": "loop_",
            "browser_automation": "browser_automation_",
            "mcp_tool": "mcp_tool_",
            "code": "code_",
            "chat_node": "chat_node_",
            "pend_event": "pend_event_",
            "http": "http_",
            "rag": "rag_",
        }
        for node in flowgram.nodes:
            if node.type in type_to_prefix:
                expected_prefix = type_to_prefix[node.type]
                if not node.id.startswith(expected_prefix):
                    errors.append(ValidationError(
                        node_id=node.id,
                        message=f"Node '{node.id}' has type '{node.type}' but ID doesn't start with '{expected_prefix}'. Rename to '{expected_prefix}{node.id}' or similar.",
                        severity="error"
                    ))
        
        # Check edges reference valid nodes
        for edge in flowgram.edges:
            if edge.source not in node_ids:
                errors.append(ValidationError(
                    message=f"Edge source '{edge.source}' does not exist",
                    severity="error"
                ))
            if edge.target not in node_ids:
                errors.append(ValidationError(
                    message=f"Edge target '{edge.target}' does not exist",
                    severity="error"
                ))
        
        # Check for orphan nodes (not connected) and nodes missing incoming/outgoing edges
        nodes_with_incoming = set()
        nodes_with_outgoing = set()
        for edge in flowgram.edges:
            nodes_with_outgoing.add(edge.source)
            nodes_with_incoming.add(edge.target)
        
        for node in flowgram.nodes:
            # Skip start/end and internal block nodes
            if node.type in ["start", "block-start"]:
                # Start nodes should have outgoing edges
                if node.id not in nodes_with_outgoing:
                    errors.append(ValidationError(
                        node_id=node.id,
                        message=f"Start node '{node.id}' has no outgoing edge",
                        severity="error"
                    ))
            elif node.type in ["end", "block-end"]:
                # End nodes should have incoming edges
                if node.id not in nodes_with_incoming:
                    errors.append(ValidationError(
                        node_id=node.id,
                        message=f"End node '{node.id}' has no incoming edge",
                        severity="error"
                    ))
            else:
                # Regular nodes should have both incoming and outgoing edges
                if node.id not in nodes_with_incoming and node.id not in nodes_with_outgoing:
                    errors.append(ValidationError(
                        node_id=node.id,
                        message=f"Node '{node.id}' is completely disconnected (no edges)",
                        severity="error"
                    ))
                elif node.id not in nodes_with_incoming:
                    errors.append(ValidationError(
                        node_id=node.id,
                        message=f"Node '{node.id}' has no incoming edge - workflow cannot reach this node",
                        severity="error"
                    ))
                elif node.id not in nodes_with_outgoing:
                    # Nodes before end should have outgoing edges (except condition branches that may end)
                    warnings.append(ValidationError(
                        node_id=node.id,
                        message=f"Node '{node.id}' has no outgoing edge - workflow may dead-end here",
                        severity="warning"
                    ))
        
        # Check LLM nodes have required config
        for node in flowgram.nodes:
            if node.type == "llm":
                if not node.config.get("system_prompt") and not node.config.get("user_prompt"):
                    warnings.append(ValidationError(
                        node_id=node.id,
                        field="config",
                        message="LLM node should have system_prompt or user_prompt",
                        severity="warning"
                    ))
        
        is_valid = len(errors) == 0
        logger.info(f"[CodeAgent] Validation result: valid={is_valid}, errors={len(errors)}, warnings={len(warnings)}")
        
        return ValidationResult(
            valid=is_valid,
            errors=errors,
            warnings=warnings
        )
    
    def _node_to_canvas_payload(self, node: FlowgramNode) -> Dict[str, Any]:
        """Convert a FlowgramNode to canvas command payload, handling loop and condition nodes."""
        payload = {
            "nodeType": node.type,
            "position": {"x": node.position.x, "y": node.position.y},
            "config": {
                "id": node.id,
                "label": getattr(node, "title", None) or node.label,
                **node.config
            }
        }
        
        # Handle condition nodes - ensure conditions array is in data for frontend
        if node.type == "condition":
            conditions = node.config.get("conditions", [])
            if not conditions:
                # Generate default conditions if not present
                conditions = [
                    {"key": f"if_{node.id[-5:]}", "value": {}},
                    {"key": f"else_{node.id[-5:]}", "value": {}},
                ]
            payload["data"] = {
                "title": node.label,
                "conditions": conditions,
            }
        
        # Handle loop nodes with blocks
        if node.type == "loop" and node.blocks:
            payload["blocks"] = [
                {
                    "id": b.id,
                    "type": b.type,
                    "meta": {"position": {"x": b.position.x, "y": b.position.y}},
                    "data": {"title": b.label, **b.config}
                }
                for b in node.blocks
            ]
            if node.internal_edges:
                payload["edges"] = [
                    {"sourceNodeID": e.source, "targetNodeID": e.target}
                    for e in node.internal_edges
                ]
        
        return payload
    
    def generate_canvas_commands(self, flowgram: Flowgram) -> List[CanvasCommand]:
        """Generate canvas commands from a flowgram"""
        logger.debug(f"[CodeAgent] Generating canvas commands for {len(flowgram.nodes)} nodes")
        commands = []
        
        # Clear existing canvas first
        commands.append(CanvasCommand(
            type="canvas.clear",
            payload={}
        ))
        
        # Add nodes
        for node in flowgram.nodes:
            commands.append(CanvasCommand(
                type="canvas.add_node",
                payload=self._node_to_canvas_payload(node)
            ))
        
        # Add edges
        for edge in flowgram.edges:
            commands.append(CanvasCommand(
                type="canvas.add_edge",
                payload={
                    "sourceNodeId": edge.source,
                    "targetNodeId": edge.target,
                    "sourceHandle": edge.source_handle,
                    "targetHandle": edge.target_handle,
                    "label": edge.label
                }
            ))
        
        logger.info(f"[CodeAgent] Generated {len(commands)} canvas commands")
        return commands
    
    async def generate(
        self,
        user_message: str,
        canvas_context: Optional[Dict] = None,
        plan: Optional[ImplementationPlan] = None,
        on_event: Optional[Callable] = None
    ) -> CodeAgentOutput:
        """
        Generate a flowgram from user request and optional plan.
        
        Args:
            user_message: User's request
            canvas_context: Current canvas state
            plan: Implementation plan from PlannerAgent
            on_event: Callback for streaming events
            
        Returns:
            CodeAgentOutput with generated flowgram
        """
        logger.info(f"[CodeAgent] Generating flowgram for: {user_message[:100]}...")
        
        # Store task context for ValidatorAgent to use during edge fixing
        self._current_task_context = user_message
        
        try:
            await self._emit_progress(on_event, "Building generation prompt…")

            # Build prompt — safe_format leaves JSON braces in .md files intact
            raw_prompt = prompt_store.get("code_gen", default=CODE_GENERATION_PROMPT)
            prompt = safe_format(
                raw_prompt,
                node_types=get_node_types_description(),
                node_schema=prompt_store.get_node_schema(),
                mapping_dsl=prompt_store.get_mapping_dsl(),
                canvas_context=self._format_canvas_context(canvas_context),
                plan_context=self._format_plan_context(plan),
            )
            
            prompt += f"\n\n## USER REQUEST:\n{user_message}"
            
            # Invoke LLM
            await self._emit_progress(on_event, "Generating workflow — this may take 1-2 minutes for complex skills…")
            logger.debug("[CodeAgent] Invoking LLM for generation")
            response = await self._invoke_llm_async(prompt, action="generate")
            
            # Check for empty response
            if not response or not response.strip():
                logger.error("[CodeAgent] LLM returned empty response - possible timeout or API error")
                return CodeAgentOutput(
                    action=CodeAgentAction.REJECT,
                    message="I couldn't generate the workflow - the AI model returned an empty response. This might be due to a timeout or API issue. Please try again."
                )
            
            # Parse response
            output = self._parse_code_agent_output(response)
            
            # Validate if flowgram was generated
            if output.flowgram:
                await self._emit_progress(on_event, f"Validating generated workflow ({len(output.flowgram.nodes)} nodes)…")
                validation = self.validate_flowgram(output.flowgram, plan)
                output.validation = validation
                
                # Store current flowgram
                self._current_flowgram = output.flowgram
                
                # Retry if validation failed
                if not validation.valid and MAX_VALIDATION_RETRIES > 0:
                    n_errors = len(validation.errors)
                    await self._emit_progress(on_event, f"Validation found {n_errors} error(s) — auto-fixing…")
                    logger.info("[CodeAgent] Validation failed, attempting fix...")
                    output = await self._fix_validation_errors(
                        output, validation, user_message, canvas_context, plan,
                        on_event=on_event,
                    )
                
                # Send flowgram event
                if on_event and output.flowgram:
                    import asyncio
                    logger.info(f"[CodeAgent] 🎨 Sending flowgram event with {len(output.flowgram.nodes)} nodes, {len(output.flowgram.edges)} edges")
                    result = on_event({
                        "type": "flowgram",
                        "data": output.flowgram.model_dump(exclude_none=True)
                    })
                    # Handle both sync and async callbacks
                    if asyncio.iscoroutine(result):
                        await result
                    logger.info("[CodeAgent] 🎨 Flowgram event sent successfully")
                elif not on_event:
                    logger.warning("[CodeAgent] ⚠️ No on_event callback provided - flowgram event not sent")
                elif not output.flowgram:
                    logger.warning("[CodeAgent] ⚠️ No flowgram in output - flowgram event not sent")
            
            return output
            
        except Exception as e:
            import traceback
            logger.error(f"[CodeAgent] Generation failed: {e}\n{traceback.format_exc()}")
            return CodeAgentOutput(
                action=CodeAgentAction.REJECT,
                message=f"Failed to generate flowgram: {str(e)}"
            )
    
    async def _fix_validation_errors(
        self,
        output: CodeAgentOutput,
        validation: ValidationResult,
        user_message: str,
        canvas_context: Optional[Dict],
        plan: Optional[ImplementationPlan],
        retry_count: int = 0,
        on_event: Optional[Callable] = None,
    ) -> CodeAgentOutput:
        """Attempt to fix validation errors by re-generating"""
        if retry_count >= MAX_VALIDATION_RETRIES:
            logger.warning(f"[CodeAgent] Max retries ({MAX_VALIDATION_RETRIES}) reached")
            return output
        
        logger.info(f"[CodeAgent] Fix attempt {retry_count + 1}/{MAX_VALIDATION_RETRIES}")
        await self._emit_progress(on_event, f"Fix attempt {retry_count + 1}/{MAX_VALIDATION_RETRIES} — regenerating…")
        
        # Build fix prompt
        error_messages = [e.message for e in validation.errors]
        fix_prompt = f"""The generated flowgram has validation errors. Please fix them.

ERRORS:
{chr(10).join(f'- {e}' for e in error_messages)}

ORIGINAL REQUEST: {user_message}

Please regenerate the flowgram with these errors fixed.
"""
        
        raw_prompt = prompt_store.get("code_gen", default=CODE_GENERATION_PROMPT)
        prompt = safe_format(
            raw_prompt,
            node_types=get_node_types_description(),
            node_schema=prompt_store.get_node_schema(),
            mapping_dsl=prompt_store.get_mapping_dsl(),
            canvas_context=self._format_canvas_context(canvas_context),
            plan_context=self._format_plan_context(plan),
        )
        prompt += f"\n\n{fix_prompt}"
        
        # Re-invoke LLM
        response = await self._invoke_llm_async(prompt, action=f"fix_attempt_{retry_count + 1}")
        new_output = self._parse_code_agent_output(response)
        
        if new_output.flowgram:
            await self._emit_progress(on_event, f"Validating fix attempt {retry_count + 1}…")
            new_validation = self.validate_flowgram(new_output.flowgram, plan)
            new_output.validation = new_validation
            
            if new_validation.valid:
                logger.info("[CodeAgent] Fix successful, flowgram is now valid")
                await self._emit_progress(on_event, "Validation passed ✓")
                self._current_flowgram = new_output.flowgram
                return new_output
            else:
                # Recurse
                return await self._fix_validation_errors(
                    new_output, new_validation, user_message, 
                    canvas_context, plan, retry_count + 1,
                    on_event=on_event,
                )
        
        return output
    
    async def edit(
        self,
        edit_request: str,
        current_flowgram: Optional[Flowgram] = None,
        on_event: Optional[Callable] = None
    ) -> CodeAgentOutput:
        """
        Edit an existing flowgram.
        
        Args:
            edit_request: What to change
            current_flowgram: Current flowgram to edit
            on_event: Callback for streaming events
            
        Returns:
            CodeAgentOutput with edited flowgram
        """
        flowgram = current_flowgram or self._current_flowgram
        
        if not flowgram:
            return CodeAgentOutput(
                action=CodeAgentAction.REJECT,
                message="No flowgram to edit. Please generate one first."
            )
        
        logger.info(f"[CodeAgent] Editing flowgram: {edit_request[:100]}...")
        
        try:
            await self._emit_progress(on_event, "Preparing edit…")

            # Build edit prompt
            raw_edit_prompt = prompt_store.get("edit_flowgram", default=EDIT_FLOWGRAM_PROMPT)
            prompt = safe_format(
                raw_edit_prompt,
                current_flowgram=json.dumps(flowgram.model_dump(), indent=2),
                edit_request=edit_request,
                node_types=get_node_types_description(),
                node_schema=prompt_store.get_node_schema(),
                mapping_dsl=prompt_store.get_mapping_dsl(),
            )
            
            # Invoke LLM
            await self._emit_progress(on_event, "Applying edit — please wait…")
            response = await self._invoke_llm_async(prompt, action="edit")
            output = self._parse_code_agent_output(response)
            
            if output.flowgram:
                output.action = CodeAgentAction.EDIT_FLOWGRAM
                
                # Re-run placement algorithm to avoid overlaps after edit
                self._apply_layout(output.flowgram)
                
                validation = self.validate_flowgram(output.flowgram)
                output.validation = validation
                self._current_flowgram = output.flowgram
                
                if on_event:
                    import asyncio
                    result = on_event({
                        "type": "flowgram",
                        "data": output.flowgram.model_dump(exclude_none=True)
                    })
                    # Handle both sync and async callbacks
                    if asyncio.iscoroutine(result):
                        await result
            
            return output
            
        except Exception as e:
            logger.error(f"[CodeAgent] Edit failed: {e}")
            return CodeAgentOutput(
                action=CodeAgentAction.REJECT,
                message=f"Failed to edit flowgram: {str(e)}"
            )
    
    def generate_sync(
        self,
        user_message: str,
        canvas_context: Optional[Dict] = None,
        plan: Optional[ImplementationPlan] = None,
        on_event: Optional[Callable] = None
    ) -> CodeAgentOutput:
        """Synchronous version of generate"""
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
                return run_async_in_sync(
                    self.generate(user_message, canvas_context, plan, on_event)
                )
            else:
                return loop.run_until_complete(
                    self.generate(user_message, canvas_context, plan, on_event)
                )
        except RuntimeError:
            return asyncio.run(
                self.generate(user_message, canvas_context, plan, on_event)
            )
    
    def get_current_flowgram(self) -> Optional[Flowgram]:
        """Get the current flowgram"""
        return self._current_flowgram
    
    def set_current_flowgram(self, flowgram: Flowgram):
        """Set the current flowgram"""
        self._current_flowgram = flowgram
    
    def clear(self):
        """Clear current flowgram and history"""
        self._current_flowgram = None
        self._generation_history = []
        logger.info("[CodeAgent] Cleared")


# ============================================================
# Singleton Instance
# ============================================================

_code_agent_instance: Optional[CodeAgent] = None


def get_code_agent() -> CodeAgent:
    """Get or create the singleton code agent instance"""
    global _code_agent_instance
    if _code_agent_instance is None:
        logger.info("[CodeAgent] Creating new singleton instance")
        _code_agent_instance = CodeAgent()
    return _code_agent_instance


def reset_code_agent():
    """Reset the singleton instance"""
    global _code_agent_instance
    logger.info("[CodeAgent] Resetting singleton instance")
    if _code_agent_instance:
        _code_agent_instance.clear()
    _code_agent_instance = None

