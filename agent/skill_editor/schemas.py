"""
Skill Editor Agent Schemas

Pydantic schemas for structured agent responses, inspired by BubbleLab's approach.
These schemas ensure type-safe communication between agents and the frontend.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field, asdict
from pydantic import BaseModel, Field, model_validator


# ============================================================
# Enums
# ============================================================

class IntentType(str, Enum):
    """Types of user intents the agent can recognize"""
    CREATE_FLOWGRAM = "create_flowgram"
    LOAD_SKILL = "load_skill"
    SAVE_SKILL = "save_skill"
    ADD_NODE = "add_node"
    REMOVE_NODE = "remove_node"
    CONNECT_NODES = "connect_nodes"
    MODIFY_NODE = "modify_node"
    RUN_FLOWGRAM = "run_flowgram"
    DEBUG_FLOWGRAM = "debug_flowgram"
    TEST_SKILL = "test_skill"  # Test skill: run/pause/step/exit
    DEPLOY_SKILL = "deploy_skill"  # Deploy skill: create task, schedule, assign agent
    ANALYZE_LOG = "analyze_log"  # Analyze a run log file for errors/failures
    EXPLAIN = "explain"
    CASUAL_CHAT = "casual_chat"
    GENERAL_CHAT = "general_chat"
    MULTI_AGENT_DESIGN = "multi_agent_design"  # Architectural design for multi-agent / multi-skill systems
    # --- App-wide general-purpose intents (action × resource model, see ActionType/ResourceType) ---
    RESOURCE_ACTION = "resource_action"  # CRUD/query/list on a managed resource (agent/task/prompt)
    APP_QA = "app_qa"  # App-wide question answering (docs RAG or source-code reading)
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    """The action dimension of an app-wide request (independent of the resource it targets).

    Pairs with ResourceType to form a two-dimensional intent, e.g. (CREATE, AGENT)
    or (LIST, TASK). This generalizes the older flat skill-centric IntentType so the
    agent can act app-wide without an enum explosion.
    """
    CREATE = "create"
    MODIFY = "modify"
    REMOVE = "remove"
    QUERY = "query"   # fetch / inspect a specific item
    LIST = "list"     # enumerate items
    QA = "qa"         # answer a question (no mutation)
    NONE = "none"     # not an app-wide action (fall back to skill-editor flow)


class ResourceType(str, Enum):
    """The resource (target) dimension of an app-wide request.

    SKILL keeps the request on the existing skill-editor pipeline. AGENT/TASK/PROMPT
    are managed entities the agent can CRUD. APP_DOCS and SOURCE are knowledge sources
    for question answering (RAG over docs vs. reading the eCan.ai source tree on EC2).
    """
    SKILL = "skill"
    AGENT = "agent"
    TASK = "task"
    PROMPT = "prompt"
    APP_DOCS = "app_docs"  # user manuals / documentation
    SOURCE = "source"      # the eCan.ai source code on the EC2 box
    NONE = "none"


class PlannerAction(str, Enum):
    """Actions the planner agent can take"""
    ASK_CLARIFICATION = "ask_clarification"
    GATHER_CONTEXT = "gather_context"
    GENERATE_PLAN = "generate_plan"
    PROCEED_TO_CODE = "proceed_to_code"
    RECOMMEND_MULTI_AGENT = "recommend_multi_agent"  # Requirements exceed single-workflow limits


class CodeAgentAction(str, Enum):
    """Actions the code agent can take"""
    GENERATE_FLOWGRAM = "generate_flowgram"
    EDIT_FLOWGRAM = "edit_flowgram"
    VALIDATE = "validate"
    ANSWER = "answer"
    REJECT = "reject"


# ============================================================
# Clarification Schemas
# ============================================================

class ClarificationChoice(BaseModel):
    """A choice option for a clarification question"""
    id: str = Field(..., description="Unique identifier for this choice")
    label: str = Field(..., description="Display label for the choice")
    description: Optional[str] = Field(None, description="Additional description")
    allow_freeform: bool = Field(False, description="When selected, show a text input for custom user input")


class ClarificationQuestion(BaseModel):
    """A clarification question to ask the user"""
    id: str = Field(..., description="Unique identifier for this question")
    question: str = Field(..., description="The question text")
    choices: List[ClarificationChoice] = Field(..., description="Available choices")
    context: Optional[str] = Field(None, description="Why this question is important")
    allow_multiple: bool = Field(False, description="Whether multiple choices can be selected")
    # UI rendering hints — consumed by the A2UI frontend
    widget_type: str = Field(
        "choice",
        description=(
            "UI widget: 'choice' (radio/button), 'multi_select' (checkbox list), "
            "'searchable_multi_select' (typeahead with substring filter + multi-pick — use for large lists), "
            "'dropdown', 'text' (free text), 'file_upload'"
        ),
    )
    data_source: Optional[str] = Field(
        None,
        description="Dynamic data source key. 'user_skills' → handler fills choices from user's S3 skill list before sending to client.",
    )


class ClarificationResponse(BaseModel):
    """User's response to clarification questions"""
    answers: Dict[str, List[str]] = Field(..., description="Map of question_id to selected choice_ids")


# ============================================================
# Plan Schemas
# ============================================================

class PlanStep(BaseModel):
    """A step in the implementation plan"""
    title: str = Field(..., description="Step title")
    description: str = Field(..., description="Detailed description of what this step does")
    node_types: List[str] = Field(default_factory=list, description="Node types used in this step")
    goal: str = Field("", description="The measurable goal this step must achieve (used for agentic verification)")


class ImplementationPlan(BaseModel):
    """Implementation plan generated by the planner"""
    summary: str = Field(..., description="Brief overview of what the workflow will accomplish")
    goals: List[str] = Field(default_factory=list, description="High-level measurable goals the workflow must achieve")
    steps: List[PlanStep] = Field(..., description="Step-by-step breakdown")
    estimated_nodes: List[str] = Field(default_factory=list, description="Estimated node types needed")
    complexity: str = Field("medium", description="Estimated complexity: simple, medium, complex")


# ============================================================
# Planner Agent Output
# ============================================================

class PlannerOutput(BaseModel):
    """Structured output from the planner agent"""
    action: PlannerAction = Field(..., description="The action to take")
    questions: Optional[List[ClarificationQuestion]] = Field(
        None, description="Clarification questions (when action is ask_clarification)"
    )
    plan: Optional[ImplementationPlan] = Field(
        None, description="Implementation plan (when action is generate_plan)"
    )
    context_request: Optional[Dict[str, Any]] = Field(
        None, description="Context request info (when action is gather_context)"
    )
    message: Optional[str] = Field(
        None, description="Optional message to display to user"
    )


# ============================================================
# Flowgram Schemas
# ============================================================

class NodePosition(BaseModel):
    """Position of a node on the canvas"""
    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")


class FlowgramNode(BaseModel):
    """
    A node in the flowgram, matching UI shape:
    {
      id, type,
      meta: { position: {x, y} },
      data: { title, inputsValues?, inputs?, outputs?, script?, ... },
      blocks?, edges? (for loop)
    }
    """
    id: str = Field(..., description="Unique node identifier")
    type: str = Field(..., description="Node type (e.g., 'llm', 'mcp', 'condition', 'browser-automation', 'pend_event_node')")
    label: Optional[str] = Field(None, description="Display label/title (internal)")
    title: Optional[str] = Field(None, description="Display title (UI-facing)")
    # Internal position used during parsing; UI position is stored under meta.position
    position: Optional[NodePosition] = Field(None, description="Internal position (legacy/internal); serialize via meta.position")
    # Backward-compat: legacy config (internal form). UI form lives in data/inputsValues.
    config: Dict[str, Any] = Field(default_factory=dict, description="Legacy internal config; UI config should be in data.inputsValues/data.*")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Metadata including position")
    data: Dict[str, Any] = Field(default_factory=dict, description="Node data (title, inputsValues, inputs, outputs, script, etc.)")
    blocks: Optional[List["FlowgramNode"]] = Field(None, description="Internal nodes for container types (loop)")
    edges: Optional[List["FlowgramEdge"]] = Field(None, description="Internal edges for container types (loop)")
    # Backward-compat alias for internal edges (loop)
    internal_edges: Optional[List["FlowgramEdge"]] = Field(None, description="Alias for edges for loop/internal blocks")


class FlowgramEdge(BaseModel):
    """An edge connecting two nodes (UI shape)"""
    sourceNodeID: str = Field(..., description="Source node ID")
    targetNodeID: str = Field(..., description="Target node ID")
    sourcePortID: Optional[str] = Field(None, description="Source handle/port ID")
    targetPortID: Optional[str] = Field(None, description="Target handle/port ID")
    label: Optional[str] = Field(None, description="Edge label")

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_keys(cls, data: Any) -> Any:
        """Allow legacy edge keys (source/target/source_handle/target_handle)"""
        if isinstance(data, dict):
            if "source" in data and "sourceNodeID" not in data:
                data["sourceNodeID"] = data.pop("source")
            if "target" in data and "targetNodeID" not in data:
                data["targetNodeID"] = data.pop("target")
            if "source_handle" in data and "sourcePortID" not in data:
                data["sourcePortID"] = data.pop("source_handle")
            if "target_handle" in data and "targetPortID" not in data:
                data["targetPortID"] = data.pop("target_handle")
            if "sourceHandle" in data and "sourcePortID" not in data:
                data["sourcePortID"] = data.pop("sourceHandle")
            if "targetHandle" in data and "targetPortID" not in data:
                data["targetPortID"] = data.pop("targetHandle")
        return data

    @property
    def source(self) -> str:
        return self.sourceNodeID

    @property
    def target(self) -> str:
        return self.targetNodeID

    @property
    def source_handle(self) -> Optional[str]:
        return self.sourcePortID

    @property
    def target_handle(self) -> Optional[str]:
        return self.targetPortID


class Flowgram(BaseModel):
    """Complete flowgram structure"""
    nodes: List[FlowgramNode] = Field(default_factory=list, description="List of nodes")
    edges: List[FlowgramEdge] = Field(default_factory=list, description="List of edges")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# Optional helper schema to document common LLM inputsValues fields (keeps inputsValues flexible)
class LLMInputsValues(BaseModel):
    modelProvider: Optional[Any] = None
    modelName: Optional[Any] = None
    attachments: Optional[Any] = None
    apiKey: Optional[Any] = None
    apiHost: Optional[Any] = None
    temperature: Optional[Any] = None  # may include schema block
    systemPrompt: Optional[Any] = None
    prompt: Optional[Any] = None
    promptSelection: Optional[Any] = None


class SkillFile(BaseModel):
    """
    Top-level skill file shape matching UI/export:
    {
      skillId, skillName, version, lastModified,
      workFlow: { nodes, edges },
      mode, run_mode, config, schemaVersion
    }
    """
    skillId: str = Field("", description="Skill identifier")
    skillName: str = Field(..., description="Skill name")
    version: str = Field("1.0.0", description="Version string")
    lastModified: Optional[str] = Field(None, description="ISO timestamp of last modification")
    workFlow: Flowgram = Field(default_factory=Flowgram, description="Workflow content")
    mode: str = Field("development", description="Editor mode")
    run_mode: str = Field("developing", description="Runtime mode")
    config: Dict[str, Any] = Field(default_factory=lambda: {"nodes": {}}, description="Additional configuration")
    schemaVersion: str = Field("1.0.1", description="Schema version")


# Update forward references for self-referential types
FlowgramNode.model_rebuild()


# ============================================================
# Code Agent Output
# ============================================================

class ValidationError(BaseModel):
    """A validation error in the flowgram"""
    node_id: Optional[str] = Field(None, description="Node ID with the error")
    field: Optional[str] = Field(None, description="Field with the error")
    message: str = Field(..., description="Error message")
    severity: str = Field("error", description="Severity: error, warning, info")


class ValidationResult(BaseModel):
    """Result of flowgram validation"""
    valid: bool = Field(..., description="Whether the flowgram is valid")
    errors: List[ValidationError] = Field(default_factory=list, description="Validation errors")
    warnings: List[ValidationError] = Field(default_factory=list, description="Validation warnings")


class CodeAgentOutput(BaseModel):
    """Structured output from the code agent"""
    action: CodeAgentAction = Field(..., description="The action taken")
    message: str = Field(..., description="Message to display to user")
    flowgram: Optional[Flowgram] = Field(
        None, description="Generated or edited flowgram"
    )
    validation: Optional[ValidationResult] = Field(
        None, description="Validation result"
    )
    data_mapping: Optional[Dict[str, Any]] = Field(
        None, description="Data mapping rules for data_mapping.json (merged with baseline defaults)"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# ============================================================
# Canvas Commands
# ============================================================

class CanvasCommand(BaseModel):
    """A command to be sent to the frontend canvas"""
    type: str = Field(..., description="Command type (e.g., 'canvas.add_node')")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Command payload")
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "payload": self.payload}


# ============================================================
# Agent Response
# ============================================================

class AgentResponse(BaseModel):
    """Unified response from the skill editor agent"""
    message: str = Field(..., description="Response message to display")
    commands: List[CanvasCommand] = Field(default_factory=list, description="Canvas commands")
    intent: IntentType = Field(IntentType.GENERAL_CHAT, description="Classified intent")
    
    # Planning phase data
    clarification: Optional[List[ClarificationQuestion]] = Field(
        None, description="Clarification questions if needed"
    )
    plan: Optional[ImplementationPlan] = Field(
        None, description="Implementation plan if generated"
    )
    
    # Code generation data
    flowgram: Optional[Flowgram] = Field(
        None, description="Generated flowgram"
    )
    validation: Optional[ValidationResult] = Field(
        None, description="Validation result"
    )
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


# ============================================================
# Streaming Events
# ============================================================

class StreamEventType(str, Enum):
    """Types of streaming events"""
    CHUNK = "chunk"
    CLARIFICATION = "clarification"
    PLAN = "plan"
    PROGRESS = "progress"
    FLOWGRAM = "flowgram"
    VALIDATION = "validation"
    CANVAS_COMMAND = "canvas_command"
    COMPLETE = "complete"
    ERROR = "error"


class StreamEvent(BaseModel):
    """A streaming event sent to the frontend"""
    type: StreamEventType = Field(..., description="Event type")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event data")
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type.value, "data": self.data}


# ============================================================
# Node Type Definitions
# ============================================================

NODE_TYPES = {
    "start": {
        "description": "Entry point of the workflow",
        "has_inputs": False,
        "has_outputs": True,
    },
    "end": {
        "description": "Exit point of the workflow",
        "has_inputs": True,
        "has_outputs": False,
    },
    "block-start": {
        "description": "Entry point inside a loop node (internal use)",
        "has_inputs": False,
        "has_outputs": True,
        "is_internal": True,
    },
    "block-end": {
        "description": "Exit point inside a loop node (internal use)",
        "has_inputs": True,
        "has_outputs": False,
        "is_internal": True,
    },
    "llm": {
        "description": "LLM node for AI processing with prompts",
        "has_inputs": True,
        "has_outputs": True,
        "config_schema": {
            "model": "string",
            "system_prompt": "string",
            "user_prompt": "string",
            "temperature": "number",
        }
    },
    "mcp_tool": {
        "description": "MCP tool node for external tool calls",
        "has_inputs": True,
        "has_outputs": True,
        "config_schema": {
            "tool_name": "string",
            "tool_input": "object",
        }
    },
    "condition": {
        "description": "Conditional branching node with if/elseif/else branches. Each branch has a unique key used as sourcePortID in edges.",
        "has_inputs": True,
        "has_outputs": True,
        "has_multiple_outputs": True,  # Condition nodes have multiple output ports (if/elseif/else branches)
        "config_schema": {
            "conditions": "array",  # Array of {key: "if_xxx"/"elseif_xxx"/"else_xxx", value: {}}
        },
        "default_conditions": [
            {"key": "if_branch", "value": {}},
            {"key": "else_branch", "value": {}},
        ],
        # Note: elseif branches can be added between if and else
        # Each elseif adds ~1/5 of typical node height (about 27px for 134px node)
        "size": {"width": 300, "height": 200},  # Base size
        "height_per_elseif": 27,  # Additional height per elseif branch
    },
    "loop": {
        "description": "Loop node for iterative processing. Contains internal nodes in a 'blocks' array with block-start and block-end markers.",
        "has_inputs": True,
        "has_outputs": True,
        "is_container": True,  # Loop nodes contain other nodes
        "config_schema": {
            "loopMode": "string",  # 'loopFor' | 'loopWhile' | 'loopForEach'
            "loopCountExpr": "string",  # Expression for loop count (loopFor mode)
            "loopWhileExpr": "string",  # Expression for while condition (loopWhile mode)
        },
        "internal_structure": {
            "blocks": "array",  # Internal nodes including block-start, block-end, and content nodes
            "edges": "array",  # Internal edges connecting blocks
        },
        "size": {"width": 570, "height": 345},  # Default size
        "usable_area": {
            "x_start": 120,  # Left margin not usable
            "x_end": 450,    # Right margin not usable (570 - 120)
            "y_start": 178,  # Top area not usable (header)
        },
    },
    "code": {
        "description": "DEPRECATED — DO NOT USE. Custom code execution node. Use llm + mcp instead.",
        "has_inputs": True,
        "has_outputs": True,
        "deprecated": True,
        "config_schema": {
            "language": "string",
            "code": "string",
        }
    },
    "http": {
        "description": "DEPRECATED — DO NOT USE. HTTP request node. Use mcp_tool with appropriate tool instead.",
        "has_inputs": True,
        "has_outputs": True,
        "deprecated": True,
        "config_schema": {
            "url": "string",
            "method": "string",
            "headers": "object",
            "body": "object",
        }
    },
    "browser_automation": {
        "description": "Browser automation node using browser-use agent for web interactions, this sub-agent can run {max_steps} steps to read anyu url page, understand it and then interact with it, including clicking, typing, scrolling, etc. The input will a text prompt describing what to do with with the browser.",
        "has_inputs": True,
        "has_outputs": True,
        "config_schema": {
            "provider": "string",  # 'browser-use' | 'browsebase' | 'crawl4ai'
            "task": "string",  # High-level instruction text for the agent
            "browser": "string",  # Browser type (e.g., 'new chromium')
            "browserDriver": "string",  # Driver type ('native', 'selenium', etc.)
            "cdpPort": "string",  # CDP port for browser connection
            "modelProvider": "string",  # LLM provider for browser-use agent
            "modelName": "string",  # LLM model name
            "useThinking": "boolean",  # Enable thinking mode for browser-use
            "profile": "string",  # Browser profile name
            "promptSelection": "string",  # 'inline' or 'saved'
            "systemPrompt": "string",  # System prompt for the agent
            "prompt": "string",  # User prompt/task instruction
            "timeout_seconds": "number",  # Max time for browser automation
            "enable_guardrail_timer": "boolean",  # Enable timeout tracking
            "wait_for_done": "boolean",  # Whether to interrupt when external completion is needed
        }
    },
    "pend_event": {
        "description": "Interrupt node that pauses workflow and waits for external event or human input",
        "has_inputs": True,
        "has_outputs": True,
        "config_schema": {
            "prompt": "string",  # Message to present to human/agent
            "tag": "string",  # Business tag for the interrupt (defaults to node_name)
            "eventType": "string",  # Main event type to wait for
            "pendingSources": "array",  # Additional event sources to listen for
        }
    },
    "chat_node": {
        "description": "Chat node that sends messages to the user via TaskRunner GUI",
        "has_inputs": True,
        "has_outputs": True,
        "config_schema": {
            "role": "string",  # Message role ('assistant', 'user', 'system')
            "message": "string",  # Message template to send
            "wait_for_reply": "boolean",  # Whether to wait for user reply
        }
    },
    "rag": {
        "description": "DEPRECATED — DO NOT USE. RAG node. Use mcp_tool with rag_query tool instead.",
        "has_inputs": True,
        "has_outputs": True,
        "deprecated": True,
        "config_schema": {
            "query_path": "string",  # Dotted path to extract query from state
        }
    },
}


def get_node_types_description() -> str:
    """Format node types for prompts, excluding deprecated types."""
    lines = []
    for name, info in NODE_TYPES.items():
        if info.get("deprecated"):
            continue
        lines.append(f"- **{name}**: {info['description']}")
    return "\n".join(lines)
