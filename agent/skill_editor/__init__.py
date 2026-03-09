"""
Skill Editor Module

Provides AI-powered skill editing capabilities through chat.

Architecture:
- PlannerAgent: Gathers requirements, asks clarification questions, generates implementation plans
- CodeAgent: Generates and edits flowgrams based on plans or direct requests
- SkillEditorAgent: Orchestrates the planning and code generation pipeline
"""

# Schemas (Pydantic models for structured data)
from .schemas import (
    # Enums
    IntentType,
    PlannerAction,
    CodeAgentAction,
    StreamEventType,
    # Clarification
    ClarificationChoice,
    ClarificationQuestion,
    ClarificationResponse,
    # Planning
    PlanStep,
    ImplementationPlan,
    PlannerOutput,
    # Flowgram
    NodePosition,
    FlowgramNode,
    FlowgramEdge,
    Flowgram,
    # Validation
    ValidationError,
    ValidationResult,
    # Agent outputs
    CodeAgentOutput,
    CanvasCommand,
    AgentResponse,
    StreamEvent,
    # Constants
    NODE_TYPES,
    get_node_types_description,
)

# Planner Agent
from .planner_agent import (
    PlannerAgent,
    get_planner_agent,
    reset_planner_agent,
)

# Code Agent
from .code_agent import (
    CodeAgent,
    get_code_agent,
    reset_code_agent,
)

# Node Config Agent
from .node_config_agent import (
    NodeConfigAgent,
    NodeConfigAction,
    NodeConfigOutput,
    NODE_CONFIG_SCHEMAS,
    get_node_config_agent,
)

# Validator Agent
from .validator_agent import (
    ValidatorAgent,
    ValidatorAction,
    ValidatorOutput,
    get_validator_agent,
)

# Prompt Store
from .prompt_store import (
    prompt_store,
    safe_format,
)

# Skill Editor Agent (orchestrator)
from .skill_editor_agent import (
    SkillEditorAgent,
    get_skill_editor_agent,
    reset_skill_editor_agent,
)

__all__ = [
    # Enums
    "IntentType",
    "PlannerAction",
    "CodeAgentAction",
    "StreamEventType",
    # Clarification
    "ClarificationChoice",
    "ClarificationQuestion",
    "ClarificationResponse",
    # Planning
    "PlanStep",
    "ImplementationPlan",
    "PlannerOutput",
    # Flowgram
    "NodePosition",
    "FlowgramNode",
    "FlowgramEdge",
    "Flowgram",
    # Validation
    "ValidationError",
    "ValidationResult",
    # Agent outputs
    "CodeAgentOutput",
    "CanvasCommand",
    "AgentResponse",
    "StreamEvent",
    # Constants
    "NODE_TYPES",
    "get_node_types_description",
    # Planner Agent
    "PlannerAgent",
    "get_planner_agent",
    "reset_planner_agent",
    # Code Agent
    "CodeAgent",
    "get_code_agent",
    "reset_code_agent",
    # Node Config Agent
    "NodeConfigAgent",
    "NodeConfigAction",
    "NodeConfigOutput",
    "NODE_CONFIG_SCHEMAS",
    "get_node_config_agent",
    # Validator Agent
    "ValidatorAgent",
    "ValidatorAction",
    "ValidatorOutput",
    "get_validator_agent",
    # Prompt Store
    "prompt_store",
    "safe_format",
    # Skill Editor Agent (orchestrator)
    "SkillEditorAgent",
    "get_skill_editor_agent",
    "reset_skill_editor_agent",
]
