"""
Node Configuration Agent

Specialized agent for configuring individual node parameters.
Inspired by BubbleLab's MilkTea agent - translates user requests into proper node configuration,
asks clarifying questions for ambiguous parameters, and validates configurations.

MULTI-SHEET SYNC (CRITICAL):
- Every skill has two files: `<name>_skill.json` (current sheet) AND `<name>_skill_bundle.json` (all sheets).
- After any node edit/config update, mirror the current sheet's `workFlow` into the bundle's main sheet (`mainSheetId`/`activeSheetId` = "main") so nodes/edges stay identical.
- Assume caller will persist BOTH files; never leave the bundle out of sync with the sheet file.
"""

import json
import uuid
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from utils.logger_helper import logger_helper as logger

from .schemas import (
    IntentType,
    ClarificationQuestion,
    ClarificationChoice,
    FlowgramNode,
    ValidationError,
    ValidationResult,
    CanvasCommand,
    NODE_TYPES,
)


class NodeConfigAction(str, Enum):
    """Actions the node config agent can take"""
    CONFIGURE = "configure"
    ASK_CLARIFICATION = "ask_clarification"
    VALIDATE = "validate"
    REJECT = "reject"
    ANSWER = "answer"


class NodeConfigOutput:
    """Output from the node config agent"""
    def __init__(
        self,
        action: NodeConfigAction,
        message: str,
        node_config: Optional[Dict[str, Any]] = None,
        clarification: Optional[List[ClarificationQuestion]] = None,
        validation: Optional[ValidationResult] = None,
        commands: Optional[List[CanvasCommand]] = None,
    ):
        self.action = action
        self.message = message
        self.node_config = node_config
        self.clarification = clarification
        self.validation = validation
        self.commands = commands or []


# ============================================================
# E-COMMERCE Q&A HANDLING PATTERN (CRITICAL)
# ============================================================
# When workflow involves product/service Q&A (on-site messaging or email):
# 1. FIRST: Query internal knowledge base using RAG query MCP tools (rag_query)
# 2. IF RAG unavailable/no answer: Defer to human assistance with 24-hour limit
#    - Use pend_event node to wait for human response
#    - Set timeout to 24 hours (86400 seconds)
# 3. IF human fails to respond within 24 hours: Auto-respond with best knowledge
#    - Search web for same product/service info, OR
#    - Search pre-specified local directory for product/service files
#
# Workflow pattern: RAG Query → Condition (has answer?) → 
#   YES: Auto-respond → END
#   NO: Pend Human (24h) → Condition (human responded?) →
#       YES: Use human response → END
#       NO: Web search OR local file search → Auto-respond → END
# ============================================================

# Node-specific configuration schemas with detailed field info
NODE_CONFIG_SCHEMAS = {
    "llm": {
        "description": """LLM node for AI processing. Can act as a sub-agent with its own reasoning.
- System prompt defines the agent's role and capabilities
- User prompt provides the specific task with {{variable}} placeholders
- Use higher temperature (0.7-0.9) for creative reasoning
- Use lower temperature (0.1-0.3) for deterministic extraction

IMPORTANT: LLM node does NOT have tools integrated. To enable tool usage:
- Follow LLM node with an mcp_tool node
- Set mcp_tool's tool_name to "llm auto select" for LLM to pick tools dynamically
- LLM output goes to node_state["result"]["llm_result"] and node_state["tool_input"]["input"]
- mcp_tool output goes to node_state["tool_result"]
- Use code node to move data between node_state fields

LLM+MCP SUB-AGENT PROMPT PATTERN (for multi-step tasks):
When using LLM with mcp_tool for complex tasks, prompt MUST include these system sections:
1. role: Agent expertise definition
2. instructions (task decomposition): Break tasks into sub-tasks, one step at a time
   - Return JSON: {"work_done": false, "next_tool_name": "...", "next_tool_input": {...}}
   - When done: {"work_done": true, "next_tool_name": "", "next_tool_input": {}}
3. instructions (agentic execution): OBSERVE→ACT→VERIFY pattern, iterative problem-solving
4. instructions (code execution): Prefer shell scripts, use Python for complex data
5. rules: Only use listed tools, verify after every action
6. tools_to_use: Available tool names (dynamically injected)
Reference: my_prompts/test_prompt2_pr-480482.json

ERROR HANDLING (CRITICAL - include in all sub-agent prompts):
- DON'T GET STUCK: When uncertain or encountering an error, do NOT block or retry indefinitely
- COLLECT & STORE: Log error details, context, what was attempted to state["human_intervention_needed"]
- MOVE ON: Continue to the next action item
- BATCH & REPORT: Accumulate all issues, send consolidated summary at the end for human review

PROMPT MODULARITY: Instead of inline prompts, create a prompt file in my_prompts/ directory:
- Prompt files are JSON with id, title, sections (system), userSections (user)
- Set promptSelection to the prompt ID (e.g., "pr-123456") to reference it
- To modify prompts later, update the prompt JSON file, not the node config
- Format: {"id": "pr-XXXXXX", "title": "...", "sections": [...], "userSections": [...]}""",
        "fields": {
            "promptSelection": {
                "type": "select",
                "label": "Prompt Selection",
                "description": "Select a saved prompt or use inline. Prompts stored in my_prompts/ directory.",
                "required": False,
                "options": [
                    {"value": "inline", "label": "Inline (edit below)"},
                ],
                "dynamic_options": True,
                "default": "inline",
            },
            "model": {
                "type": "select",
                "label": "Model",
                "description": "The LLM model to use",
                "required": True,
                "options": [
                    {"value": "gpt-4o", "label": "GPT-4o (Recommended)"},
                    {"value": "gpt-4o-mini", "label": "GPT-4o Mini (Faster)"},
                    {"value": "claude-3-5-sonnet", "label": "Claude 3.5 Sonnet"},
                    {"value": "claude-3-5-haiku", "label": "Claude 3.5 Haiku (Faster)"},
                ],
                "default": "gpt-4o",
            },
            "system_prompt": {
                "type": "textarea",
                "label": "System Prompt",
                "description": "Instructions that define the AI's behavior and role",
                "required": False,
                "placeholder": "You are a helpful assistant...",
            },
            "user_prompt": {
                "type": "textarea",
                "label": "User Prompt",
                "description": "The prompt template with {{variable}} placeholders",
                "required": True,
                "placeholder": "Analyze the following: {{input}}",
            },
            "temperature": {
                "type": "number",
                "label": "Temperature",
                "description": "Controls randomness (0=deterministic, 1=creative)",
                "required": False,
                "min": 0,
                "max": 2,
                "default": 0.7,
            },
            "max_tokens": {
                "type": "number",
                "label": "Max Tokens",
                "description": "Maximum tokens in the response",
                "required": False,
                "min": 1,
                "max": 128000,
                "default": 4096,
            },
        },
    },
    "mcp_tool": {
        "description": """MCP tool node for executing external tools via MCP protocol.
- Executes a specific tool from an MCP server
- Tool output is stored in node_state["tool_result"]
- Set tool_name to "llm auto select" to let the preceding LLM node choose which tool to run
- When using "llm auto select", the LLM's tool choice from node_state["tool_input"] is used""",
        "fields": {
            "server_name": {
                "type": "select",
                "label": "MCP Server",
                "description": "The MCP server to use",
                "required": True,
                "dynamic_options": True,  # Options loaded from available servers
            },
            "tool_name": {
                "type": "select",
                "label": "Tool",
                "description": "The tool to call",
                "required": True,
                "depends_on": "server_name",
                "dynamic_options": True,
            },
            "tool_input": {
                "type": "json",
                "label": "Tool Input",
                "description": "Input parameters for the tool (JSON or template)",
                "required": True,
                "placeholder": '{"param": "{{variable}}"}',
            },
        },
    },
    "condition": {
        "description": """Condition node for branching workflow based on a predicate.

IF FIELD USAGE:
- Default: "state.condition" (uses node_state["condition"] attribute)
- Custom expression: Set "if" to a Python expression that evaluates to True/False
- Expression accesses node_state via "state" variable

EXPRESSION EXAMPLES:
- state["result"]["llm_result"]["success"] == True
- state["tool_result"]["status"] == "completed"
- len(state["result"]["items"]) > 0

NOTE: Expression syntax is same as loop node's loopWhileExpr.""",
        "fields": {
            "if": {
                "type": "select",
                "label": "If Condition",
                "description": "Condition source: use state.condition or custom Python expression",
                "required": True,
                "options": [
                    {"value": "state.condition", "label": "state.condition (default)"},
                    {"value": "custom", "label": "Custom Expression"},
                ],
                "default": "state.condition",
            },
            "customExpr": {
                "type": "text",
                "label": "Custom Expression",
                "description": "Python expression using 'state' variable (node_state)",
                "required": False,
                "placeholder": "state['result']['llm_result']['success'] == True",
                "show_when": {"if": ["custom"]},
            },
            "true_label": {
                "type": "text",
                "label": "True Branch Label",
                "description": "Label for the true branch",
                "required": False,
                "default": "Yes",
            },
            "false_label": {
                "type": "text",
                "label": "False Branch Label",
                "description": "Label for the false branch",
                "required": False,
                "default": "No",
            },
        },
    },
    "loop": {
        "description": """Loop node for repeating workflow sections.

LOOP MODES:
1. loopFor (fixed iterations):
   - Set loopMode to "loopFor"
   - Set loopCountExpr to integer or Python variable expression
   - Example: loopCountExpr = 10 or loopCountExpr = state["batch_count"]

2. loopWhile (condition-based):
   - Set loopMode to "loopWhile"
   - Set loopWhileExpr to Python expression returning True/False
   - Loop continues while expression returns True
   - Example: loopWhileExpr = state["result"]["llm_result"]["not_yet_finished"]

EXPRESSION USAGE:
- Expressions are Python code accessing node_state via "state" variable
- Common pattern: Use LLM result attribute, e.g., state["result"]["llm_result"]["continue_flag"]

IMPORTANT - INITIALIZE LOOP VARIABLES:
- For loopWhile, the expression variable MUST be initialized before the loop starts
- Add a code node BEFORE the loop to set initial value:
  state["result"]["llm_result"]["not_yet_finished"] = True
- This ensures the loop runs at least once

CODE NODE NOTE:
- In code nodes, the input parameter "state" IS the node_state throughout the workflow
- Modify state directly: state["my_field"] = value""",
        "fields": {
            "loopMode": {
                "type": "select",
                "label": "Loop Mode",
                "description": "Type of loop: fixed count or while condition",
                "required": True,
                "options": [
                    {"value": "loopFor", "label": "Loop For (fixed iterations)"},
                    {"value": "loopWhile", "label": "Loop While (condition-based)"},
                ],
                "default": "loopFor",
            },
            "loopCountExpr": {
                "type": "text",
                "label": "Loop Count Expression",
                "description": "Integer or Python expression for iteration count",
                "required": True,
                "placeholder": "10 or state['batch_count']",
                "show_when": {"loopMode": ["loopFor"]},
            },
            "loopWhileExpr": {
                "type": "text",
                "label": "Loop While Expression",
                "description": "Python expression returning True to continue, False to exit",
                "required": True,
                "placeholder": "state['result']['llm_result']['not_yet_finished']",
                "show_when": {"loopMode": ["loopWhile"]},
            },
            "max_iterations": {
                "type": "number",
                "label": "Max Iterations",
                "description": "Safety limit to prevent infinite loops",
                "required": False,
                "min": 1,
                "max": 1000,
                "default": 100,
            },
        },
    },
    "code": {
        "description": """Code node for custom logic and data transformation.
- The node_state variable is directly accessible in code
- Use to move data between node_state fields (e.g., from tool_result to a custom field)
- Common node_state fields:
  - node_state["result"]["llm_result"]: LLM node output
  - node_state["tool_input"]["input"]: LLM's tool selection input
  - node_state["tool_result"]: MCP tool execution result
- Return a dict to update node_state with new values""",
        "fields": {
            "language": {
                "type": "select",
                "label": "Language",
                "description": "Programming language for the code",
                "required": True,
                "options": [
                    {"value": "python", "label": "Python"},
                    {"value": "javascript", "label": "JavaScript"},
                ],
                "default": "python",
            },
            "code": {
                "type": "code",
                "label": "Code",
                "description": "The code to execute",
                "required": True,
                "placeholder": "# Access inputs via 'inputs' dict\nresult = inputs.get('data')\nreturn {'output': result}",
            },
            "timeout": {
                "type": "number",
                "label": "Timeout (seconds)",
                "description": "Maximum execution time",
                "required": False,
                "min": 1,
                "max": 300,
                "default": 30,
            },
        },
    },
    "http": {
        "fields": {
            "method": {
                "type": "select",
                "label": "HTTP Method",
                "description": "The HTTP method to use",
                "required": True,
                "options": [
                    {"value": "GET", "label": "GET"},
                    {"value": "POST", "label": "POST"},
                    {"value": "PUT", "label": "PUT"},
                    {"value": "PATCH", "label": "PATCH"},
                    {"value": "DELETE", "label": "DELETE"},
                ],
                "default": "GET",
            },
            "url": {
                "type": "text",
                "label": "URL",
                "description": "The URL to request (supports {{variables}})",
                "required": True,
                "placeholder": "https://api.example.com/{{endpoint}}",
            },
            "headers": {
                "type": "json",
                "label": "Headers",
                "description": "HTTP headers as JSON",
                "required": False,
                "placeholder": '{"Authorization": "Bearer {{token}}"}',
            },
            "body": {
                "type": "json",
                "label": "Request Body",
                "description": "Request body as JSON (for POST/PUT/PATCH)",
                "required": False,
                "placeholder": '{"data": "{{input}}"}',
                "show_when": {"method": ["POST", "PUT", "PATCH"]},
            },
            "timeout": {
                "type": "number",
                "label": "Timeout (seconds)",
                "description": "Request timeout",
                "required": False,
                "min": 1,
                "max": 120,
                "default": 30,
            },
        },
    },
    "browser_automation": {
        "description": """Browser automation sub-agent for web interaction tasks.
Use for ANY task involving reading/interacting with web pages via browser.
- Each DOM extraction + action(click, move, type, scroll, etc.) = 1 step (default max: 100 steps)
- Estimate steps per task: simple read ~2-3, form fill ~5-7, purchase flow ~10 steps
- For bulk operations (e.g., 50 orders), put this node inside a loop and batch items
- Example: 50 orders at 10 steps each → batch 5 orders per call, loop 10 times

IMPORTANT: browser_automation has its own integrated tools (mouse click, keyboard type, scroll, etc.).
- All you need is a prompt - the browser agent handles tool execution internally
- For structured output, specify JSON format in the prompt (e.g., "Return results as JSON: {products: [{name, price}]}")
- Output is stored in node_state["result"] after execution

ERROR HANDLING (CRITICAL - include in browser_automation prompts):
- DON'T GET STUCK: When uncertain or encountering an error, do NOT block or retry indefinitely
- COLLECT & STORE: Log error details, context, what was attempted to state["human_intervention_needed"]
- MOVE ON: Continue to the next action item
- BATCH & REPORT: Accumulate all issues, send consolidated summary at the end for human review

PROMPT MODULARITY: Instead of inline prompts, create a prompt file in my_prompts/ directory:
- Prompt files are JSON with id, title, sections (system), userSections (user)
- Set promptSelection to the prompt ID (e.g., "pr-123456") to reference it
- To modify prompts later, update the prompt JSON file, not the node config
- Format: {"id": "pr-XXXXXX", "title": "...", "sections": [...], "userSections": [...]}""",
        "fields": {
            "promptSelection": {
                "type": "select",
                "label": "Prompt Selection",
                "description": "Select a saved prompt or use inline. Prompts stored in my_prompts/ directory.",
                "required": False,
                "options": [
                    {"value": "inline", "label": "Inline (edit below)"},
                ],
                "dynamic_options": True,
                "default": "inline",
            },
            "provider": {
                "type": "select",
                "label": "Provider",
                "description": "Browser automation provider",
                "required": True,
                "options": [
                    {"value": "browser-use", "label": "Browser-Use (AI Agent)"},
                    {"value": "browsebase", "label": "BrowseBase"},
                    {"value": "crawl4ai", "label": "Crawl4AI"},
                ],
                "default": "browser-use",
            },
            "task": {
                "type": "textarea",
                "label": "Task",
                "description": "High-level instruction for the browser agent. Be specific about what to do on each page. Use {{variable}} for dynamic data.",
                "required": True,
                "placeholder": "Navigate to {{url}}, search for '{{query}}', extract all product names and prices from the results page",
            },
            "browser": {
                "type": "select",
                "label": "Browser",
                "description": "Browser type to use",
                "required": False,
                "options": [
                    {"value": "new chromium", "label": "New Chromium"},
                    {"value": "chromium", "label": "Chromium"},
                    {"value": "firefox", "label": "Firefox"},
                ],
                "default": "new chromium",
            },
            "browserDriver": {
                "type": "select",
                "label": "Browser Driver",
                "description": "Driver type for browser control",
                "required": False,
                "options": [
                    {"value": "native", "label": "Native"},
                    {"value": "selenium", "label": "Selenium"},
                ],
                "default": "native",
            },
            "modelProvider": {
                "type": "select",
                "label": "Model Provider",
                "description": "LLM provider for browser-use agent",
                "required": False,
                "options": [
                    {"value": "openai", "label": "OpenAI"},
                    {"value": "anthropic", "label": "Anthropic"},
                ],
                "default": "openai",
            },
            "modelName": {
                "type": "text",
                "label": "Model Name",
                "description": "LLM model name for browser-use agent",
                "required": False,
                "default": "gpt-4o",
            },
            "useThinking": {
                "type": "boolean",
                "label": "Use Thinking Mode",
                "description": "Enable thinking mode for browser-use agent",
                "required": False,
                "default": False,
            },
            "timeout_seconds": {
                "type": "number",
                "label": "Timeout (seconds)",
                "description": "Maximum time for browser automation",
                "required": False,
                "min": 10,
                "max": 600,
                "default": 120,
            },
            "systemPrompt": {
                "type": "textarea",
                "label": "System Prompt",
                "description": "System prompt for the browser agent",
                "required": False,
                "placeholder": "You are a browser automation agent...",
            },
            "prompt": {
                "type": "textarea",
                "label": "User Prompt",
                "description": "User prompt/task instruction",
                "required": False,
                "placeholder": "{{task_description}}",
            },
        },
    },
    "chat_node": {
        "fields": {
            "party": {
                "type": "select",
                "label": "Party",
                "description": "Who is sending the message",
                "required": True,
                "options": [
                    {"value": "human", "label": "Human (User)"},
                    {"value": "assistant", "label": "Assistant (AI)"},
                    {"value": "system", "label": "System"},
                ],
                "default": "human",
            },
            "messageTemplate": {
                "type": "textarea",
                "label": "Message Template",
                "description": "Message template with {{variable}} placeholders",
                "required": True,
                "placeholder": "Hello, {{user_name}}! How can I help you today?",
            },
            "wait_for_reply": {
                "type": "boolean",
                "label": "Wait for Reply",
                "description": "Whether to wait for user reply before continuing",
                "required": False,
                "default": False,
            },
        },
    },
    "pend_event": {
        "fields": {
            "prompt": {
                "type": "textarea",
                "label": "Prompt",
                "description": "Message to present to human/agent while waiting",
                "required": True,
                "placeholder": "Waiting for user approval...",
            },
            "tag": {
                "type": "text",
                "label": "Tag",
                "description": "Business tag for the interrupt (defaults to node name)",
                "required": False,
                "placeholder": "approval_required",
            },
            "eventType": {
                "type": "select",
                "label": "Event Type",
                "description": "Main event type to wait for",
                "required": True,
                "options": [
                    {"value": "human_input", "label": "Human Input"},
                    {"value": "external_api", "label": "External API"},
                    {"value": "timer", "label": "Timer"},
                    {"value": "custom", "label": "Custom Event"},
                ],
                "default": "human_input",
            },
            "pendingSources": {
                "type": "json",
                "label": "Pending Sources",
                "description": "Additional event sources to listen for (JSON array)",
                "required": False,
                "placeholder": '["email", "webhook"]',
            },
            "timeout_seconds": {
                "type": "number",
                "label": "Timeout (seconds)",
                "description": "Maximum time to wait for event (0 = no timeout)",
                "required": False,
                "min": 0,
                "max": 86400,
                "default": 0,
            },
        },
    },
}


def build_node_config_system_prompt(
    node_type: str,
    node_schema: Dict[str, Any],
    available_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build the system prompt for the NodeConfigAgent.
    
    Similar to BubbleLab's MilkTea agent buildSystemPrompt function.
    
    Args:
        node_type: Type of the node being configured
        node_schema: Schema for the node type
        available_context: Available context (MCP servers, upstream outputs, etc.)
        
    Returns:
        System prompt string
    """
    # Format schema fields for the prompt
    fields_info = []
    for field_name, field_info in node_schema.get("fields", {}).items():
        field_desc = f"  - **{field_name}** ({field_info.get('type', 'text')}): {field_info.get('description', 'No description')}"
        if field_info.get("required"):
            field_desc += " [REQUIRED]"
        if field_info.get("default") is not None:
            field_desc += f" (default: {field_info.get('default')})"
        if field_info.get("type") == "select" and not field_info.get("dynamic_options"):
            options = [opt["value"] for opt in field_info.get("options", [])]
            field_desc += f"\n    Options: {', '.join(options)}"
        fields_info.append(field_desc)
    
    # Format available context
    context_info = ""
    if available_context:
        context_parts = []
        if available_context.get("mcp_servers"):
            context_parts.append(f"Available MCP Servers: {', '.join(available_context['mcp_servers'])}")
        if available_context.get("upstream_outputs"):
            context_parts.append(f"Upstream Node Outputs: {', '.join(available_context['upstream_outputs'])}")
        if available_context.get("variables"):
            context_parts.append(f"Available Variables: {', '.join(available_context['variables'])}")
        if context_parts:
            context_info = "\n\nAVAILABLE CONTEXT:\n" + "\n".join(context_parts)
    
    return f"""You are NodeConfig Agent, a Builder Agent specializing in configuring "{node_type}" nodes.

YOUR ROLE:
- Expert in configuring node parameters for workflow automation
- Understand user's high-level goals and translate them into proper node configuration
- Ask clarifying questions when request is unclear or missing required information
- Reject requests that are infeasible or outside the scope of this node type
- Apply logic and data transformations to configure parameters correctly

DECISION PROCESS:
1. Analyze the user's request carefully
2. Check if request is within scope of "{node_type}" node → If not, REJECT immediately
3. Check the node's schema for REQUIRED parameters:
   - Look at each required field in the schema
   - Verify the user's request provides enough information for EACH required parameter
   - If ANY required parameter is missing or unclear from the request → ASK QUESTION immediately
   - DO NOT make assumptions or use placeholder values
   - DO NOT proceed with configuration if required information is missing
4. If request is clear and feasible → GENERATE configuration

OUTPUT FORMAT (JSON):
You MUST respond in JSON format with one of these structures:

Rejection (when infeasible or out of scope):
{{
  "type": "reject",
  "message": "Clear explanation of why this request cannot be fulfilled with {node_type} node"
}}

Question (when clarification needed):
{{
  "type": "question",
  "message": "Specific question to ask the user",
  "field": "field_name_being_asked_about"
}}

Configuration (when ready to configure):
{{
  "type": "config",
  "message": "Brief explanation of the configuration",
  "config": {{
    "field_name": "value",
    "another_field": 123
  }}
}}

NODE TYPE: {node_type}

NODE SCHEMA:
{chr(10).join(fields_info)}
{context_info}

CRITICAL RULES:
1. Only configure parameters that exist in the schema
2. Respect field types (text, number, select, json, textarea)
3. For select fields, only use values from the available options
4. Use template syntax {{{{variable}}}} to reference dynamic values from workflow context
5. For JSON fields, ensure valid JSON structure
6. If the user mentions multiple nodes or cross-node operations, REJECT - you only configure ONE node at a time

Remember: You are an expert builder. Apply logic and transformations to make the parameters work correctly!"""


class NodeConfigAgent:
    """
    Agent for configuring individual node parameters.
    
    Responsibilities:
    - Parse user requests about node configuration
    - Ask clarifying questions for ambiguous parameters
    - Validate node configurations against schemas
    - Generate canvas commands to update nodes
    """
    
    def __init__(self, llm=None):
        """
        Initialize the NodeConfigAgent.
        
        Args:
            llm: LangChain LLM instance for natural language processing
        """
        self.llm = llm
        self._context: Dict[str, Any] = {}
        self._system_prompt_cache: Dict[str, str] = {}
        logger.info("[NodeConfigAgent] Initialized")
        
    def set_llm(self, llm):
        """Set the LLM instance"""
        self.llm = llm
        logger.debug("[NodeConfigAgent] LLM instance set")
        
    def get_node_schema(self, node_type: str) -> Optional[Dict[str, Any]]:
        """Get the configuration schema for a node type"""
        schema = NODE_CONFIG_SCHEMAS.get(node_type)
        logger.debug(f"[NodeConfigAgent] get_node_schema({node_type}): {'found' if schema else 'not found'}")
        return schema
    
    def get_available_node_types(self) -> List[str]:
        """Get list of available node types"""
        types = list(NODE_CONFIG_SCHEMAS.keys())
        logger.debug(f"[NodeConfigAgent] Available node types: {types}")
        return types
    
    def validate_config(
        self,
        node_type: str,
        config: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate a node configuration against its schema.
        
        Args:
            node_type: Type of the node
            config: Configuration to validate
            
        Returns:
            ValidationResult with errors and warnings
        """
        logger.info(f"[NodeConfigAgent] Validating config for node type: {node_type}")
        logger.debug(f"[NodeConfigAgent] Config to validate: {config}")
        
        errors = []
        warnings = []
        
        schema = self.get_node_schema(node_type)
        if not schema:
            logger.warning(f"[NodeConfigAgent] Unknown node type: {node_type}")
            errors.append(ValidationError(
                message=f"Unknown node type: {node_type}",
                severity="error"
            ))
            return ValidationResult(valid=False, errors=errors, warnings=warnings)
        
        fields = schema.get("fields", {})
        
        # Check required fields
        for field_name, field_info in fields.items():
            if field_info.get("required", False):
                # Check show_when conditions
                show_when = field_info.get("show_when")
                if show_when:
                    should_show = False
                    for dep_field, dep_values in show_when.items():
                        if config.get(dep_field) in dep_values:
                            should_show = True
                            break
                    if not should_show:
                        continue  # Field not required due to show_when
                
                if field_name not in config or config[field_name] is None or config[field_name] == "":
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Required field '{field_info.get('label', field_name)}' is missing",
                        severity="error"
                    ))
        
        # Validate field types and constraints
        for field_name, value in config.items():
            if field_name not in fields:
                warnings.append(ValidationError(
                    field=field_name,
                    message=f"Unknown field '{field_name}'",
                    severity="warning"
                ))
                continue
            
            field_info = fields[field_name]
            field_type = field_info.get("type")
            
            # Type validation
            if field_type == "number" and value is not None:
                try:
                    num_val = float(value)
                    min_val = field_info.get("min")
                    max_val = field_info.get("max")
                    if min_val is not None and num_val < min_val:
                        errors.append(ValidationError(
                            field=field_name,
                            message=f"'{field_info.get('label', field_name)}' must be at least {min_val}",
                            severity="error"
                        ))
                    if max_val is not None and num_val > max_val:
                        errors.append(ValidationError(
                            field=field_name,
                            message=f"'{field_info.get('label', field_name)}' must be at most {max_val}",
                            severity="error"
                        ))
                except (ValueError, TypeError):
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"'{field_info.get('label', field_name)}' must be a number",
                        severity="error"
                    ))
            
            # Select validation
            if field_type == "select" and not field_info.get("dynamic_options"):
                options = field_info.get("options", [])
                valid_values = [opt["value"] for opt in options]
                if value not in valid_values:
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Invalid value for '{field_info.get('label', field_name)}'. Valid options: {', '.join(valid_values)}",
                        severity="error"
                    ))
            
            # JSON validation
            if field_type == "json" and value is not None and isinstance(value, str):
                try:
                    json.loads(value)
                except json.JSONDecodeError as e:
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Invalid JSON in '{field_info.get('label', field_name)}': {str(e)}",
                        severity="error"
                    ))
        
        is_valid = len(errors) == 0
        logger.info(f"[NodeConfigAgent] Validation result: valid={is_valid}, errors={len(errors)}, warnings={len(warnings)}")
        if errors:
            logger.debug(f"[NodeConfigAgent] Validation errors: {[e.message for e in errors]}")
        if warnings:
            logger.debug(f"[NodeConfigAgent] Validation warnings: {[w.message for w in warnings]}")
        
        return ValidationResult(
            valid=is_valid,
            errors=errors,
            warnings=warnings
        )
    
    def generate_clarification_questions(
        self,
        node_type: str,
        partial_config: Dict[str, Any],
        user_request: str,
    ) -> List[ClarificationQuestion]:
        """
        Generate clarification questions for missing or ambiguous configuration.
        
        Args:
            node_type: Type of the node
            partial_config: Partial configuration from user
            user_request: Original user request
            
        Returns:
            List of clarification questions
        """
        logger.info(f"[NodeConfigAgent] Generating clarification questions for {node_type}")
        logger.debug(f"[NodeConfigAgent] Partial config: {partial_config}")
        
        questions = []
        schema = self.get_node_schema(node_type)
        if not schema:
            logger.warning(f"[NodeConfigAgent] No schema found for {node_type}")
            return questions
        
        fields = schema.get("fields", {})
        
        for field_name, field_info in fields.items():
            # Skip if already configured
            if field_name in partial_config and partial_config[field_name]:
                continue
            
            # Skip non-required fields unless they seem important
            if not field_info.get("required", False):
                continue
            
            # Check show_when conditions
            show_when = field_info.get("show_when")
            if show_when:
                should_show = False
                for dep_field, dep_values in show_when.items():
                    if partial_config.get(dep_field) in dep_values:
                        should_show = True
                        break
                if not should_show:
                    continue
            
            # Generate question based on field type
            field_type = field_info.get("type")
            
            if field_type == "select" and not field_info.get("dynamic_options"):
                options = field_info.get("options", [])
                choices = [
                    ClarificationChoice(
                        id=opt["value"],
                        label=opt["label"],
                        description=opt.get("description")
                    )
                    for opt in options
                ]
                questions.append(ClarificationQuestion(
                    id=f"config_{field_name}",
                    question=f"Which {field_info.get('label', field_name).lower()} would you like to use?",
                    choices=choices,
                    context=field_info.get("description"),
                    allow_multiple=False
                ))
            elif field_type in ["text", "textarea", "code"]:
                # For text fields, we might ask for more details
                # This would typically be handled by the LLM
                pass
        
        logger.info(f"[NodeConfigAgent] Generated {len(questions)} clarification questions")
        if questions:
            logger.debug(f"[NodeConfigAgent] Questions: {[q.id for q in questions]}")
        
        return questions
    
    async def configure_node(
        self,
        node_id: str,
        node_type: str,
        user_request: str,
        current_config: Optional[Dict[str, Any]] = None,
        clarification_responses: Optional[Dict[str, List[str]]] = None,
        available_context: Optional[Dict[str, Any]] = None,
    ) -> NodeConfigOutput:
        """
        Configure a node based on user request.
        
        Args:
            node_id: ID of the node to configure
            node_type: Type of the node
            user_request: User's configuration request
            current_config: Current node configuration
            clarification_responses: Responses to previous clarification questions
            available_context: Available context (e.g., MCP servers, upstream outputs)
            
        Returns:
            NodeConfigOutput with configuration or clarification questions
        """
        logger.info(f"[NodeConfigAgent] Configuring node {node_id} ({node_type})")
        logger.debug(f"[NodeConfigAgent] User request: {user_request[:100] if user_request else 'None'}...")
        logger.debug(f"[NodeConfigAgent] Current config: {current_config}")
        logger.debug(f"[NodeConfigAgent] Clarification responses: {clarification_responses}")
        
        schema = self.get_node_schema(node_type)
        if not schema:
            logger.warning(f"[NodeConfigAgent] Unknown node type: {node_type}")
            return NodeConfigOutput(
                action=NodeConfigAction.REJECT,
                message=f"I don't know how to configure nodes of type '{node_type}'. Available types: {', '.join(self.get_available_node_types())}"
            )
        
        # Start with current config or empty
        config = dict(current_config or {})
        logger.debug(f"[NodeConfigAgent] Starting config: {config}")
        
        # Apply clarification responses
        if clarification_responses:
            logger.info(f"[NodeConfigAgent] Applying {len(clarification_responses)} clarification responses")
            for question_id, answers in clarification_responses.items():
                if question_id.startswith("config_"):
                    field_name = question_id[7:]  # Remove "config_" prefix
                    if answers:
                        config[field_name] = answers[0]  # Take first answer for single-select
                        logger.debug(f"[NodeConfigAgent] Applied clarification: {field_name}={answers[0]}")
        
        # Use LLM to parse user request and extract configuration
        if self.llm and user_request:
            logger.info("[NodeConfigAgent] Using LLM to extract config from request")
            try:
                extracted_config = await self._extract_config_from_request(
                    node_type, user_request, schema, available_context
                )
                logger.debug(f"[NodeConfigAgent] LLM extracted config: {extracted_config}")
                
                # Handle special response types from LLM (MilkTea-style)
                if extracted_config.get("_rejected"):
                    logger.info(f"[NodeConfigAgent] LLM rejected the request")
                    return NodeConfigOutput(
                        action=NodeConfigAction.REJECT,
                        message=extracted_config.get("_message", "This request cannot be fulfilled with this node type.")
                    )
                
                if extracted_config.get("_needs_clarification"):
                    logger.info(f"[NodeConfigAgent] LLM needs clarification")
                    # Generate a clarification question from LLM's response
                    llm_question = ClarificationQuestion(
                        id=f"llm_clarify_{extracted_config.get('_field', 'general')}",
                        question=extracted_config.get("_message", "Could you provide more details?"),
                        choices=[],  # Open-ended question
                        allow_multiple=False,
                        required=True
                    )
                    return NodeConfigOutput(
                        action=NodeConfigAction.ASK_CLARIFICATION,
                        message=extracted_config.get("_message", "I need more information:"),
                        clarification=[llm_question]
                    )
                
                # Filter out special keys and update config
                clean_config = {k: v for k, v in extracted_config.items() if not k.startswith("_")}
                config.update(clean_config)
            except Exception as e:
                logger.warning(f"[NodeConfigAgent] Failed to extract config from request: {e}")
        
        # Check if we need clarification
        questions = self.generate_clarification_questions(node_type, config, user_request)
        if questions:
            logger.info(f"[NodeConfigAgent] Returning {len(questions)} clarification questions")
            return NodeConfigOutput(
                action=NodeConfigAction.ASK_CLARIFICATION,
                message="I need a bit more information to configure this node:",
                clarification=questions
            )
        
        # Validate the configuration
        validation = self.validate_config(node_type, config)
        if not validation.valid:
            logger.warning(f"[NodeConfigAgent] Configuration validation failed with {len(validation.errors)} errors")
            error_messages = [e.message for e in validation.errors]
            return NodeConfigOutput(
                action=NodeConfigAction.VALIDATE,
                message=f"The configuration has some issues:\n- " + "\n- ".join(error_messages),
                node_config=config,
                validation=validation
            )
        
        # Generate canvas command to update the node
        logger.info(f"[NodeConfigAgent] Configuration valid, generating canvas command")
        commands = [
            CanvasCommand(
                type="canvas.update_node",
                payload={
                    "nodeId": node_id,
                    "config": {"inputsValues": config}
                }
            )
        ]
        
        # Generate success message
        field_labels = []
        for field_name, value in config.items():
            field_info = schema.get("fields", {}).get(field_name, {})
            label = field_info.get("label", field_name)
            field_labels.append(f"**{label}**: {self._format_value(value)}")
        
        message = f"I've configured the {node_type} node with:\n" + "\n".join(field_labels)
        
        logger.info(f"[NodeConfigAgent] Node {node_id} configured successfully")
        logger.debug(f"[NodeConfigAgent] Final config: {config}")
        
        return NodeConfigOutput(
            action=NodeConfigAction.CONFIGURE,
            message=message,
            node_config=config,
            validation=validation,
            commands=commands
        )
    
    def configure_node_sync(
        self,
        node_id: str,
        node_type: str,
        user_request: str,
        current_config: Optional[Dict[str, Any]] = None,
        clarification_responses: Optional[Dict[str, List[str]]] = None,
        available_context: Optional[Dict[str, Any]] = None,
    ) -> NodeConfigOutput:
        """Synchronous version of configure_node"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.configure_node(
                            node_id, node_type, user_request,
                            current_config, clarification_responses, available_context
                        )
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.configure_node(
                        node_id, node_type, user_request,
                        current_config, clarification_responses, available_context
                    )
                )
        except RuntimeError:
            return asyncio.run(
                self.configure_node(
                    node_id, node_type, user_request,
                    current_config, clarification_responses, available_context
                )
            )
    
    def _get_system_prompt(
        self,
        node_type: str,
        schema: Dict[str, Any],
        available_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Get or build the system prompt for a node type.
        
        Args:
            node_type: Type of the node
            schema: Node configuration schema
            available_context: Available context
            
        Returns:
            System prompt string
        """
        # Create cache key based on node_type and context
        cache_key = f"{node_type}_{hash(str(available_context)) if available_context else 'no_ctx'}"
        
        if cache_key not in self._system_prompt_cache:
            self._system_prompt_cache[cache_key] = build_node_config_system_prompt(
                node_type, schema, available_context
            )
            logger.debug(f"[NodeConfigAgent] Built and cached system prompt for {node_type}")
        
        return self._system_prompt_cache[cache_key]
    
    async def _extract_config_from_request(
        self,
        node_type: str,
        user_request: str,
        schema: Dict[str, Any],
        available_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Use LLM to extract configuration values from user request.
        
        Uses a comprehensive system prompt similar to BubbleLab's MilkTea agent
        to properly understand user intent and extract configuration.
        
        Args:
            node_type: Type of the node
            user_request: User's natural language request
            schema: Node configuration schema
            available_context: Available context
            
        Returns:
            Extracted configuration values
        """
        logger.debug(f"[NodeConfigAgent] _extract_config_from_request called for {node_type}")
        if not self.llm:
            logger.debug("[NodeConfigAgent] No LLM available, returning empty config")
            return {}
        
        # Build system prompt (MilkTea-style)
        system_prompt = self._get_system_prompt(node_type, schema, available_context)
        
        # Build messages for the LLM
        from langchain_core.messages import SystemMessage, HumanMessage
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_request)
        ]
        
        try:
            logger.debug("[NodeConfigAgent] Invoking LLM with system prompt for config extraction")
            logger.debug(f"[NodeConfigAgent] System prompt length: {len(system_prompt)} chars")
            
            response = await self.llm.ainvoke(messages)
            response_text = response.content if hasattr(response, 'content') else str(response)
            logger.debug(f"[NodeConfigAgent] LLM response: {response_text[:300]}...")
            
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                parsed = json.loads(json_str)
                
                # Handle different response types from the agent
                response_type = parsed.get("type", "config")
                
                if response_type == "reject":
                    logger.info(f"[NodeConfigAgent] LLM rejected request: {parsed.get('message')}")
                    return {"_rejected": True, "_message": parsed.get("message", "Request rejected")}
                
                elif response_type == "question":
                    logger.info(f"[NodeConfigAgent] LLM needs clarification: {parsed.get('message')}")
                    return {
                        "_needs_clarification": True,
                        "_message": parsed.get("message", "Need more information"),
                        "_field": parsed.get("field")
                    }
                
                elif response_type == "config":
                    config = parsed.get("config", {})
                    logger.info(f"[NodeConfigAgent] Successfully extracted {len(config)} config values from LLM")
                    return config
                
                else:
                    # Fallback: treat the whole response as config
                    logger.info(f"[NodeConfigAgent] Treating response as direct config: {len(parsed)} values")
                    return parsed
            else:
                logger.warning("[NodeConfigAgent] No JSON found in LLM response")
        except Exception as e:
            logger.warning(f"[NodeConfigAgent] Failed to parse LLM response: {e}")
        
        return {}
    
    def _format_value(self, value: Any) -> str:
        """Format a value for display"""
        if isinstance(value, str):
            if len(value) > 50:
                return f'"{value[:50]}..."'
            return f'"{value}"'
        elif isinstance(value, dict):
            return "<JSON object>"
        elif isinstance(value, list):
            return f"[{len(value)} items]"
        else:
            return str(value)


# Singleton instance
_node_config_agent: Optional[NodeConfigAgent] = None


def get_node_config_agent() -> NodeConfigAgent:
    """Get or create the NodeConfigAgent singleton"""
    global _node_config_agent
    if _node_config_agent is None:
        _node_config_agent = NodeConfigAgent()
    return _node_config_agent
