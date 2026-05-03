"""
Skill Editor Agent (Orchestrator)

Orchestrates the skill editing pipeline by coordinating:
1. PlannerAgent - for clarification and planning
2. CodeAgent - for flowgram generation and editing
3. NodeConfigAgent - for single-node configuration

This agent provides a unified interface for the chat handler while
delegating specialized tasks to the appropriate sub-agents.

Inspired by BubbleLab's Pearl agent - an AI Builder Agent that helps users
build complete workflows with multiple integrations.
"""

import json
import os
import re
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Tuple
from enum import Enum

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from utils.logger_helper import logger_helper as logger

from agent.skill_editor.token_tracker import token_tracker

# Import skill scaffolding utility
from agent.ec_skills.extern_skills.extern_skills import scaffold_skill, user_skills_root

# Import from schemas
from .schemas import (
    IntentType,
    PlannerAction,
    AgentResponse,
    CanvasCommand,
    ClarificationChoice,
    ClarificationQuestion,
    ImplementationPlan,
    PlanStep,
    Flowgram,
    FlowgramNode,
    FlowgramEdge,
    NodePosition,
    NODE_TYPES,
    get_node_types_description,
)

# Import sub-agents
from .planner_agent import PlannerAgent, get_planner_agent
from .code_agent import CodeAgent, get_code_agent
from .node_config_agent import NodeConfigAgent, NodeConfigAction, get_node_config_agent
from .prompt_store import prompt_store
from .tools_catalog import build_tools_catalog
from .i18n import t, detect_language, get_language_instruction


def _is_lambda_runtime() -> bool:
    try:
        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            return True
        if os.environ.get("LAMBDA_TASK_ROOT"):
            return True
        exec_env = os.environ.get("AWS_EXECUTION_ENV", "")
        return exec_env.startswith("AWS_Lambda")
    except Exception:
        return False


def _norm_s3_prefix(prefix: str) -> str:
    p = (prefix or "").strip()
    p = p.lstrip("/")
    p = p.rstrip("/")
    return p


def _safe_user_dir_name(username: str) -> str:
    u = (username or "").strip()
    if not u:
        return "unknown"
    try:
        if "@" in u:
            local_part, domain_part = u.split("@", 1)
            return f"{local_part}_{domain_part.replace('.', '_')}"
    except Exception:
        pass
    return u.replace("@", "_").replace(".", "_")


INTENT_CLASSIFIER_SYSTEM_PROMPT = """You are an intent classification assistant for an e-commerce workflow editor.

Return JSON ONLY (no markdown) with this schema:
{
  "intent": "<one of the allowed intents>",
  "confidence": <number from 0.0 to 1.0>,
  "reason": "<brief reason>"
}

Allowed intents:
- create_flowgram
- load_skill
- save_skill
- add_node
- remove_node
- connect_nodes
- modify_node
- run_flowgram
- debug_flowgram
- test_skill
- deploy_skill
- analyze_log
- explain
- casual_chat
- general_chat

Guidelines:
- If the user has an existing canvas/workflow open (has_canvas=true), prefer modify_node unless the user is explicitly asking to create a new workflow.
- If the user is asking to change structure/wiring/loop/condition/nodes, that is modify_node.
- If the user is asking how to do something or wants an explanation, that is explain.
- If the user message is short social chatter (e.g. acknowledgements like "awesome", "thanks", "cool") and not a workflow request, that is casual_chat.
- If the user is asking for a direct factual answer unrelated to building/editing a workflow (e.g. "who is the president of russia"), that is explain.
- If the user mentions a log file path and asks to analyze, diagnose, or review logs/errors/failures, that is analyze_log.
"""


# ============================================================
# System Prompt Builder (Pearl-style)
# ============================================================

def build_skill_editor_system_prompt(
    user_name: str = "User",
    available_node_types: Optional[List[str]] = None,
    current_flowgram_summary: Optional[str] = None,
    additional_context: Optional[str] = None,
) -> str:
    """
    Build the system prompt for the SkillEditorAgent.
    
    Similar to BubbleLab's Pearl agent buildSystemPrompt function.
    This prompt defines the agent's role, capabilities, decision process,
    and output format.
    
    Args:
        user_name: Name of the user
        available_node_types: List of available node types
        current_flowgram_summary: Summary of current workflow state
        additional_context: Any additional context to include
        
    Returns:
        System prompt string
    """
    # Get node types description
    if available_node_types is None:
        available_node_types = list(NODE_TYPES.keys())
    
    node_types_desc = get_node_types_description()
    
    # Build current workflow context
    workflow_context = ""
    if current_flowgram_summary:
        workflow_context = f"""
CURRENT WORKFLOW:
{current_flowgram_summary}
"""
    
    # Build additional context section
    extra_context = ""
    if additional_context:
        extra_context = f"""
ADDITIONAL CONTEXT:
{additional_context}
"""
    
    return f"""You are Sam, an AI Builder Agent specializing in creating and editing eCan.ai workflows (called Flowgrams).
You reside inside the eCan.ai Skill Editor, a visual workflow builder for automation.

YOUR ROLE:
- Expert in building end-to-end workflows with multiple nodes and integrations
- Good at explaining your thinking process to the user in a clear and concise manner
- Expert in automation, logic, loops, conditions, and data manipulation
- Understand user's high-level goals and translate them into complete workflow configurations
- Ask clarifying questions when requirements are unclear
- Help users build workflows that can include multiple nodes and complex logic
- Configure individual nodes with proper parameters

AVAILABLE NODE TYPES:
{node_types_desc}

DECISION PROCESS:
1. Analyze the user's request carefully
2. Determine the user's intent:
   - Are they asking for information/guidance? → Use ANSWER
   - Are they requesting skill/workflow creation? → Use CODE (always use planning even if it seems simple)
   - Are they requesting skill/workflow edits? → Use EDIT (by default)
   - Are they configuring a specific node? → Use CONFIGURE
   - Is critical information missing? → Use QUESTION
   - Are they asking for testing this skill/workflow? → Use TEST
   - Are they asking for deploying this skill/workflow? → Use DEPLOY
   - Is the request infeasible? → Use REJECT
3. For workflow generation:
   - Identify all the nodes/integrations needed
   - Check if all required information is provided
   - If ANY critical information is missing → ASK QUESTION immediately
   - DO NOT make assumptions or use placeholder values, do thorough feasibility analysis, try to identify gating items, show stoppers early and get them resolved with requester, whenever you're not so sure about how to do a task, ask the requester about it until you feel confident that you can breakdown the task into known steps. 
   - If request is clear and feasible → GENERATE workflow and validate it

OUTPUT FORMAT (JSON):
You MUST respond in JSON format with one of these structures:

Question (when you need MORE information from user):
{{
  "type": "question",
  "message": "Specific question to ask the user to clarify their requirements"
}}

Answer (when providing information or guidance WITHOUT generating code):
{{
  "type": "answer",
  "message": "Detailed explanation, guidance, or answer to the user's question"
}}

Code (when generating or editing workflow):
{{
  "type": "code",
  "message": "Brief explanation of what was created/modified",
  "flowgram": {{ ... }}  // The flowgram JSON structure
}}

Configure (when configuring a specific node):
{{
  "type": "configure",
  "message": "Explanation of the configuration",
  "node_id": "node_id",
  "config": {{ ... }}  // Node configuration
}}

Rejection (when infeasible):
{{
  "type": "reject",
  "message": "Clear explanation of why this request cannot be fulfilled"
}}

Test (when testing the skill/workflow):
{{
  "type": "test",
  "action": "run" | "pause" | "step" | "exit",
  "message": "Explanation of the test action",
  "breakpoints": ["node_id_1", "node_id_2"]  // Optional: nodes to pause at for step mode
}}

Deploy (when deploying the skill/workflow):
{{
  "type": "deploy",
  "message": "Explanation of the deployment",
  "task_config": {{
    "task_name": "descriptive_task_name",
    "skill_name": "current_skill_name",
    "schedule": "cron_expression or 'now' for immediate",
    "agent_name": "existing_agent_name or null to create new",
    "new_agent_config": {{  // Only if agent_name is null
      "name": "new_agent_name",
      "description": "agent description"
    }}
  }}
}}

WHEN TO USE EACH TYPE:
- Use "question" when you need MORE information from the user to proceed
- Use "answer" when providing helpful information, explanations, or guidance WITHOUT generating workflow
  Examples: explaining features, listing available nodes, providing usage guidance, answering how-to questions
- Use "code" when you have enough information to generate or edit a complete workflow
- Use "configure" when the user wants to configure a specific node's parameters
- Use "test" when user wants to test/debug the current skill:
  - "run": Start or resume execution from the beginning
  - "pause": Pause execution at current node
  - "step": Execute one node at a time (step-through debugging)
  - "exit": Stop testing and exit test mode
- Use "deploy" when user wants to deploy the skill as a scheduled task:
  - Creates a task using the current skill
  - Schedules it (cron expression or immediate)
  - Assigns to an existing agent or creates a new one
  - Kicks off the task
- Use "reject" when the request is infeasible or outside your capabilities

CRITICAL WORKFLOW GENERATION RULES:
1. Each node must have a unique ID
2. Nodes must be properly connected with edges
3. Apply proper logic: use condition nodes for branching, loop nodes for iteration
4. Access data from upstream nodes using template syntax: {{{{node_id.output_field}}}}
5. Validate the workflow structure before returning
6. If validation fails, fix the errors iteratively
7. Keep edits minimal - only change what's necessary

CRITICAL EDITING RULES (Pearl-style iterative editing):
- When editing, highlight the changes necessary
- Use comments to indicate where unchanged parts have been skipped
- KEEP THE EDIT MINIMAL - only modify what's necessary
- Validate after each edit and fix any errors

NODE CONFIGURATION RULES:
- Each node type has specific required and optional parameters
- Use the node's schema to understand what parameters are needed
- For LLM nodes: model, system_prompt, user_prompt are key parameters
- For Code nodes: language and code are required
- For HTTP nodes: url and method are required
- For Condition nodes: condition expression is required
- For Loop nodes: items source and loop variable are required

LIMITATIONS:
- Cannot access external systems outside the configured MCP tools and integrations
- Cannot create accounts on platforms on behalf of users
- Cannot perform actions that would violate privacy or ethical guidelines
- Cannot access proprietary information about internal architecture
- Limited context window - may not recall very distant parts of long conversations
- For actions requiring human credentials, defer to human assistance via pend_event

CONTEXT:
User: {user_name}
{workflow_context}{extra_context}

Remember: You are an expert builder. Apply logic and transformations to make the workflow work correctly!
Respond in the user's language when possible, but default to English for technical terms."""


# ============================================================
# Pipeline State
# ============================================================

class PipelineState(str, Enum):
    """State of the skill editor pipeline"""
    IDLE = "idle"
    PLANNING = "planning"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"
    GENERATING = "generating"
    EDITING = "editing"
    CONFIGURING_NODE = "configuring_node"  # Node configuration mode
    COLLECTING_REQUIREMENTS = "collecting_requirements"  # Domain QA collection
    REVIEWING_WORKFLOW_DESCRIPTION = "reviewing_workflow_description"  # User reviewing SOP-based workflow desc
    COLLECTING_LOG_ANALYSIS_INFO = "collecting_log_analysis_info"  # Pre-analysis info collection
    AWAITING_LOG_FIX_CONFIRMATION = "awaiting_log_fix_confirmation"  # User confirming auto-fix after log analysis
    COMPLETE = "complete"


# ============================================================
# Skill Editor Agent Class (Orchestrator)
# ============================================================

class SkillEditorAgent:
    """
    Orchestrator agent for the skill editor pipeline.
    
    Inspired by BubbleLab's Pearl agent - coordinates multiple sub-agents
    to help users build complete workflows through conversation.
    
    This agent coordinates:
    1. PlannerAgent for clarification and planning
    2. CodeAgent for flowgram generation and editing
    3. NodeConfigAgent for single-node configuration
    4. Pipeline state management
    5. Conversation history
    """
    
    def __init__(self, llm=None, user_name: str = "User"):
        """
        Initialize the skill editor agent.
        
        Args:
            llm: LangChain LLM instance. If None, sub-agents will use default from settings.
            user_name: Name of the user for personalized responses.
        """
        self._llm = llm
        self._user_name = user_name
        self._planner: Optional[PlannerAgent] = None
        self._code_agent: Optional[CodeAgent] = None
        self._node_config_agent: Optional[NodeConfigAgent] = None
        self._conversation_history: List[Dict[str, str]] = []
        self._pipeline_state = PipelineState.IDLE
        self._pending_clarification: Optional[List[ClarificationQuestion]] = None
        self._current_plan: Optional[ImplementationPlan] = None
        self._current_request: Optional[str] = None
        self._selected_node: Optional[Dict[str, Any]] = None  # Currently selected node for configuration
        self._casual_chat_rounds_by_session: Dict[str, int] = {}
        self._loaded_context_key: Optional[str] = None
        self._log_analysis_context: Optional[Dict[str, str]] = None  # {file_path, log_content, last_analysis}
        self._pending_log_analysis_info: Optional[Dict[str, Any]] = None  # Pre-analysis info for log analysis
        # Structured error from the most recent failed skill run — populated by session restore
        # when the Fargate task reports failure (see _handle_skill_run_result in handler.py).
        # Shape: {failed_node_id, failed_node_type, error_type, error_message,
        #         input_at_failure, fix_hypothesis, iteration}
        self._last_run_error: Optional[Dict[str, Any]] = None
        # --- Taxonomy / domain-aware requirement collection ---
        self._classified_domain: Optional[str] = None
        self._classified_intent_taxonomy: Optional[str] = None
        self._requirement_answers: Dict[str, Any] = {}  # collected QA answers keyed by question id
        self._domain_qa_done: bool = False  # True after domain-specific follow-up Q&A has been asked (or skipped)
        self._workflow_description: Optional[str] = None  # natural-language workflow description for user review
        # Accumulated clarification answers across planner rounds (old pipeline)
        self._accumulated_clarification_answers: Dict[str, List[str]] = {}
        self._all_asked_questions: Dict[str, ClarificationQuestion] = {}  # all questions keyed by id across rounds
        self._clarification_round: int = 0
        self._MAX_CLARIFICATION_ROUNDS: int = 3
        self._last_saved_skill_name: Optional[str] = None  # persisted across invocations for edit fallback
        self._cached_flowgram_dict: Optional[Dict[str, Any]] = None  # cached flowgram from last generation/edit (survives Lambda restarts via session)
        self._user_lang: str = "en"  # detected language: 'zh' or 'en'
        logger.info("[SkillEditorAgent] Initialized")
    
    def get_system_prompt(self, canvas_context: Optional[Dict] = None) -> str:
        """
        Get the Pearl-style system prompt for the agent.
        
        Args:
            canvas_context: Current canvas state for workflow summary
            
        Returns:
            System prompt string
        """
        # Build workflow summary from canvas context
        workflow_summary = None
        if canvas_context:
            nodes = canvas_context.get("nodes", [])
            edges = canvas_context.get("edges", [])
            if nodes:
                node_types = [n.get("type", "unknown") for n in nodes]
                workflow_summary = f"Nodes: {len(nodes)} ({', '.join(set(node_types))}), Connections: {len(edges)}"
        
        return build_skill_editor_system_prompt(
            user_name=self._user_name,
            current_flowgram_summary=workflow_summary,
        ) + get_language_instruction(self._user_lang)
    
    def build_messages(self, user_message: str, canvas_context: Optional[Dict] = None) -> List:
        """
        Build the message list for LLM invocation (Pearl-style).
        
        Args:
            user_message: Current user message
            canvas_context: Current canvas state
            
        Returns:
            List of LangChain messages
        """
        messages = []
        
        # Add system prompt
        system_prompt = self.get_system_prompt(canvas_context)
        messages.append(SystemMessage(content=system_prompt))
        
        # Add conversation history (last 10 messages)
        for msg in self._conversation_history[-10:]:
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg.get("content", "")))
            elif msg.get("role") == "assistant":
                messages.append(AIMessage(content=msg.get("content", "")))
        
        # Add current user message with context
        context_info = ""
        if canvas_context:
            nodes = canvas_context.get("nodes", [])
            edges = canvas_context.get("edges", [])
            selected = canvas_context.get("selectedNodes", [])
            if nodes or selected:
                context_info = f"\n\n[Canvas: {len(nodes)} nodes, {len(edges)} edges"
                if selected:
                    context_info += f", selected: {selected}"
                context_info += "]"
        
        messages.append(HumanMessage(content=f"{user_message}{context_info}"))
        
        return messages
    
    def add_to_history(self, role: str, content: str):
        """Add a message to conversation history"""
        self._conversation_history.append({"role": role, "content": content})
        # Keep history manageable
        if len(self._conversation_history) > 50:
            self._conversation_history = self._conversation_history[-40:]
    
    def _add_response_to_history(self, response: AgentResponse):
        """Add assistant response to conversation history"""
        # Extract meaningful content from response
        content = response.message
        if response.plan:
            content += f"\n[Plan generated: {response.plan.summary}]"
        if response.clarification:
            questions = [q.question for q in response.clarification]
            content += f"\n[Clarification questions: {'; '.join(questions)}]"
        self.add_to_history("assistant", content)
    
    @property
    def planner(self) -> PlannerAgent:
        """Get or create the planner agent"""
        if self._planner is None:
            self._planner = PlannerAgent(llm=self._llm)
            logger.debug("[SkillEditorAgent] Created PlannerAgent")
        return self._planner
    
    @property
    def code_agent(self) -> CodeAgent:
        """Get or create the code agent"""
        if self._code_agent is None:
            self._code_agent = CodeAgent(llm=self._llm)
            logger.debug("[SkillEditorAgent] Created CodeAgent")
        return self._code_agent
    
    @property
    def node_config_agent(self) -> NodeConfigAgent:
        """Get or create the node config agent"""
        if self._node_config_agent is None:
            self._node_config_agent = NodeConfigAgent(llm=self._llm)
            logger.debug("[SkillEditorAgent] Created NodeConfigAgent")
        return self._node_config_agent

    @property
    def tools_catalog_text(self) -> str:
        """Build and cache the compact tools catalog for prompt injection."""
        if not hasattr(self, "_tools_catalog_cache"):
            try:
                self._tools_catalog_cache = build_tools_catalog(owner=self._user_name)
                logger.info("[SkillEditorAgent] Tools catalog built (%d chars)", len(self._tools_catalog_cache))
            except Exception as exc:
                logger.warning("[SkillEditorAgent] Failed to build tools catalog: %s", exc)
                self._tools_catalog_cache = "(tools catalog not available)"
        return self._tools_catalog_cache
    
    @property
    def pipeline_state(self) -> PipelineState:
        """Get current pipeline state"""
        return self._pipeline_state
    
    @property
    def current_plan(self) -> Optional[ImplementationPlan]:
        """Get current implementation plan"""
        return self._current_plan
    
    @property
    def current_request(self) -> Optional[str]:
        """Get current user request"""
        return self._current_request

    @property
    def classified_domain(self) -> Optional[str]:
        return self._classified_domain

    @property
    def classified_intent_taxonomy(self) -> Optional[str]:
        return self._classified_intent_taxonomy

    @property
    def requirement_answers(self) -> Dict[str, Any]:
        return self._requirement_answers

    @property
    def domain_qa_done(self) -> bool:
        return self._domain_qa_done

    @property
    def workflow_description(self) -> Optional[str]:
        return self._workflow_description

    @property
    def pending_log_analysis_info(self) -> Optional[Dict[str, Any]]:
        return self._pending_log_analysis_info

    @property
    def log_analysis_context(self) -> Optional[Dict[str, Any]]:
        return self._log_analysis_context

    @property
    def accumulated_clarification_answers(self) -> Dict[str, Any]:
        return self._accumulated_clarification_answers

    @property
    def last_saved_skill_name(self) -> Optional[str]:
        return self._last_saved_skill_name

    @property
    def cached_flowgram_dict(self) -> Optional[Dict[str, Any]]:
        return self._cached_flowgram_dict

    @property
    def clarification_round(self) -> int:
        return self._clarification_round

    @property
    def user_lang(self) -> str:
        return self._user_lang

    def restore_state(
        self,
        pipeline_state: str,
        current_plan: Optional[Dict[str, Any]] = None,
        current_request: Optional[str] = None,
        classified_domain: Optional[str] = None,
        classified_intent_taxonomy: Optional[str] = None,
        requirement_answers: Optional[Dict[str, Any]] = None,
        domain_qa_done: bool = False,
        workflow_description: Optional[str] = None,
        accumulated_clarification_answers: Optional[Dict[str, Any]] = None,
        clarification_round: int = 0,
        pending_clarification: Optional[List[Dict[str, Any]]] = None,
        pending_log_analysis_info: Optional[Dict[str, Any]] = None,
        log_analysis_context: Optional[Dict[str, Any]] = None,
        last_saved_skill_name: Optional[str] = None,
        cached_flowgram_dict: Optional[Dict[str, Any]] = None,
        user_lang: Optional[str] = None,
        last_run_error: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Restore agent state from persisted session data (survives app restarts)"""
        try:
            logger.info(f"[SkillEditorAgent] restore_state called: pipeline_state={pipeline_state}, has_plan={current_plan is not None}")
            self._pipeline_state = PipelineState(pipeline_state)
            if user_lang in ("zh", "en"):
                self._user_lang = user_lang
            self._current_request = current_request
            self._classified_domain = classified_domain
            self._classified_intent_taxonomy = classified_intent_taxonomy
            self._requirement_answers = requirement_answers or {}
            self._domain_qa_done = domain_qa_done
            self._workflow_description = workflow_description
            self._accumulated_clarification_answers = accumulated_clarification_answers or {}
            self._clarification_round = clarification_round
            self._pending_log_analysis_info = pending_log_analysis_info
            self._log_analysis_context = log_analysis_context
            self._last_saved_skill_name = last_saved_skill_name
            self._cached_flowgram_dict = cached_flowgram_dict
            self._last_run_error = last_run_error

            # If log analysis info state but no pending info, reset to idle
            if self._pipeline_state == PipelineState.COLLECTING_LOG_ANALYSIS_INFO and not self._pending_log_analysis_info:
                logger.info("[SkillEditorAgent] COLLECTING_LOG_ANALYSIS_INFO but no pending info — resetting to IDLE")
                self._pipeline_state = PipelineState.IDLE

            # If awaiting fix confirmation but no analysis context, reset to idle
            if self._pipeline_state == PipelineState.AWAITING_LOG_FIX_CONFIRMATION and not self._log_analysis_context:
                logger.info("[SkillEditorAgent] AWAITING_LOG_FIX_CONFIRMATION but no analysis context — resetting to IDLE")
                self._pipeline_state = PipelineState.IDLE

            # Restore pending clarification questions (needed to resolve choice IDs → labels)
            if pending_clarification and isinstance(pending_clarification, list):
                try:
                    self._pending_clarification = [
                        ClarificationQuestion(**q) if isinstance(q, dict) else q
                        for q in pending_clarification
                    ]
                except Exception as pc_err:
                    logger.warning(f"[SkillEditorAgent] Failed to restore pending_clarification: {pc_err}")
                    self._pending_clarification = None
            
            if current_plan:
                # Reconstruct ImplementationPlan from dict
                steps = [
                    PlanStep(
                        title=s.get("title", "Step"),
                        description=s.get("description", ""),
                        node_types=s.get("node_types", [])
                    )
                    for s in current_plan.get("steps", [])
                ]
                self._current_plan = ImplementationPlan(
                    summary=current_plan.get("summary", ""),
                    steps=steps,
                    estimated_nodes=current_plan.get("estimated_nodes", []),
                    complexity=current_plan.get("complexity", "medium")
                )
            else:
                self._current_plan = None
            
            logger.info(f"[SkillEditorAgent] Restored state: pipeline={self._pipeline_state.value}, has_plan={self._current_plan is not None}")
        except Exception as e:
            import traceback
            logger.error(f"[SkillEditorAgent] Failed to restore state: {e}\n{traceback.format_exc()}")
            self._pipeline_state = PipelineState.IDLE
            self._current_plan = None
            self._current_request = None
    
    def _classify_intent_simple(self, message: str) -> IntentType:
        """Fast rule-based classification for trivially unambiguous intents.

        Only handles clear-cut system commands (casual chat, log analysis,
        load/save).  Everything else returns GENERAL_CHAT so the LLM
        taxonomy classifier can decide.
        """
        msg_lower = message.lower()

        # Casual chat: short acknowledgements / social chatter
        if self._is_casual_chat_message(message):
            return IntentType.CASUAL_CHAT

        # Log analysis: user wants to analyze a log file
        if self._is_log_analysis_request(message):
            return IntentType.ANALYZE_LOG

        # Load skill intent - explicit system command (English + Chinese)
        if (any(phrase in msg_lower for phrase in ["load", "open", "load up", "switch to"]) and "skill" in msg_lower) or \
           any(w in message for w in ["加载技能", "打开技能", "切换到"]):
            return IntentType.LOAD_SKILL

        # Save skill intent - explicit system command (English + Chinese)
        if (any(phrase in msg_lower for phrase in ["save", "save as", "export"]) and ("skill" in msg_lower or "workflow" in msg_lower or "flowgram" in msg_lower)) or \
           any(w in message for w in ["保存", "存一下", "存储", "导出"]):
            return IntentType.SAVE_SKILL

        # Explicit create / generate workflow (skip expensive taxonomy LLM call)
        _create_en = any(p in msg_lower for p in [
            "create a workflow", "create workflow", "build a workflow", "build workflow",
            "generate a workflow", "generate workflow", "make a workflow", "make workflow",
            "design a workflow", "design workflow", "new workflow",
        ])
        _create_zh = any(w in message for w in [
            "生成", "创建", "新建", "构建", "设计", "搭建",
            "做一个", "做个", "帮我做", "帮我建",
        ]) and any(w in message for w in ["工作流", "流程", "workflow"])
        if _create_en or _create_zh:
            return IntentType.CREATE_FLOWGRAM

        # Everything else → let the LLM taxonomy classifier decide
        return IntentType.GENERAL_CHAT

    def _infer_domain_fast(self, message: str) -> Optional[str]:
        """Fast keyword-based domain inference to skip the taxonomy LLM call."""
        msg = (message or "").lower()
        _DOMAIN_KEYWORDS = {
            "product_listing": ["listing", "产品", "product", "asin", "商品", "listing优化"],
            "competition_analysis": ["竞品", "竞争", "competitor", "competition", "对手", "competing"],
            "market_research": ["调研", "市场", "research", "market", "趋势", "trend", "销量", "排名", "top"],
            "advertising": ["广告", "ppc", "advertising", "campaign", "推广", "投放", "bid"],
            "customer_support": ["客服", "客户", "customer", "support", "review", "评论", "feedback"],
            "supply_chain": ["供应链", "inventory", "库存", "物流", "shipping", "采购", "supplier"],
            "content_creation": ["内容", "content", "文案", "copywriting", "seo", "关键词", "keyword"],
            "data_reporting": ["report", "报告", "数据", "analytics", "统计", "dashboard"],
        }
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            if any(kw in msg for kw in keywords):
                return domain
        return None

    def _is_log_analysis_request(self, message: str) -> bool:
        """Detect if the user wants to analyze a log file.
        Also matches follow-up questions when a prior log analysis is active.
        """
        msg = (message or "").strip().lower()
        if not msg:
            return False

        # Must have a log/analyze keyword
        log_keywords = [
            "log", "logs", "analyze", "analyse", "analysis",
            "diagnose", "debug log", "run log", "error log",
            "failure", "traceback", "stack trace",
        ]
        has_log_keyword = any(kw in msg for kw in log_keywords)
        if not has_log_keyword:
            # Even without explicit log keyword, detect follow-up references
            # to a prior log analysis (e.g. "do you see api key issues?",
            # "上述文件", "the file above", "从上面的log")
            if self._log_analysis_context:
                followup_cues = [
                    "上述", "上面", "above", "the file", "that file",
                    "该文件", "这个文件", "之前的", "前面的",
                    "api key", "error", "warning", "issue", "problem",
                    "是否", "有没有", "do you see", "did you find",
                    "can you check", "what about",
                ]
                if any(cue in msg for cue in followup_cues):
                    return True
            return False

        # If we have an active log analysis context, a log keyword alone
        # is enough — the user is asking a follow-up about the same log.
        if self._log_analysis_context:
            return True

        # Otherwise must reference a file path or file-like token
        # Matches: C:\..., /home/..., ./foo.log, foo.log, foo.txt, etc.
        has_file_ref = bool(re.search(
            r'(?:'
            r'[a-zA-Z]:\\[\w\\.\-/ ]+'       # Windows absolute path
            r'|/[\w/.\-]+'                     # Unix absolute path
            r'|\.[\\/][\w/.\\\-]+'             # Relative path ./foo or .\foo
            r'|[\w\-]+\.(?:log|txt|out|err)'   # Bare filename with log-like extension
            r')',
            message  # case-sensitive original to preserve paths
        ))

        if has_file_ref:
            return True

        # Even without a file path, if the user explicitly asks to analyze
        # logs (e.g. "help me analyze the logs", "analyze my run log"),
        # classify as ANALYZE_LOG — the clarification flow will ask for the path.
        analyze_verbs = ["analyze", "analyse", "diagnose", "debug", "check", "inspect", "review", "look at", "examine"]
        log_nouns = ["log", "logs", "run log", "error log", "logfile", "log file"]
        has_analyze = any(v in msg for v in analyze_verbs)
        has_log_noun = any(n in msg for n in log_nouns)
        if has_analyze and has_log_noun:
            return True

        return False

    def _extract_file_path_from_message(self, message: str) -> Optional[str]:
        """Extract a file path from a user message."""
        if not message:
            return None
        # Try common path patterns in priority order
        patterns = [
            r'[A-Za-z]:\\[\w\\.\-/ ]+',       # Windows absolute
            r'/[\w/.\-]+',                      # Unix absolute
            r'\.[\\/][\w/.\\\-]+',              # Relative path
            r'[\w\-]+\.(?:log|txt|out|err)',    # Bare filename
        ]
        for pat in patterns:
            m = re.search(pat, message)
            if m:
                return m.group(0).strip()
        return None

    def _is_explain_request(self, message: str) -> bool:
        msg = (message or "").strip().lower()
        if not msg:
            return False

        # Avoid misclassifying workflow-building prompts as explanations.
        # Only block when the message contains BOTH a workflow term AND an action verb.
        # Questions like "what does the first loop do?" should NOT be blocked.
        action_verbs = [
            "add ", "remove ", "delete ", "modify", "modif", "edit",
            "create", "build", "generate", "load", "save", "deploy",
            "connect", "disconnect",
        ]
        workflow_nouns = [
            "workflow", "flowgram", "skill", "node", "edge",
            "loop", "condition", "branch",
        ]
        has_action = any(v in msg for v in action_verbs)
        has_wf_noun = any(n in msg for n in workflow_nouns)
        # Chinese action verbs and workflow nouns for the same blocker
        action_verbs_zh = ["添加", "删除", "移除", "修改", "编辑", "创建", "新建", "生成", "构建", "部署", "连接", "断开"]
        workflow_nouns_zh = ["工作流", "流程图", "技能", "节点", "边", "循环", "条件", "分支"]
        has_action_zh = any(v in message for v in action_verbs_zh)
        has_wf_noun_zh = any(n in message for n in workflow_nouns_zh)
        # If the message has both an action verb and a workflow noun, it's likely
        # a building/editing request, not an explain request.
        if (has_action and has_wf_noun) or (has_action_zh and has_wf_noun_zh):
            return False
        # Also block standalone action verbs like "test", "run", "debug" as intents
        standalone_action = any(msg.startswith(v.strip()) for v in ["test", "run", "debug"])
        if standalone_action and not any(w in msg for w in ["explain", "what", "how", "why", "?"]):
            return False

        normalized = re.sub(r"\s+", " ", msg).strip()

        # Common short Q&A / explain-style prompts (English).
        if any(w in normalized for w in ["explain", "help"]):
            return True

        # Chinese explain/question keywords
        if any(w in message for w in ["解释", "说明", "帮我理解", "介绍", "描述", "告诉我"]):
            return True
        # Chinese question phrases ("what does X do", "what is X for", etc.)
        if any(w in message for w in ["做什么", "干什么", "什么意思", "什么作用", "什么用", "干嘛", "是什么", "怎么运行", "怎么工作"]):
            return True

        starts_with_question_word = any(
            normalized.startswith(w)
            for w in [
                "who ",
                "what ",
                "when ",
                "where ",
                "which ",
                "why ",
                "how ",
            ]
        )
        if starts_with_question_word:
            return True

        # Chinese question starters
        stripped = message.strip()
        if any(stripped.startswith(w) for w in ["什么", "为什么", "怎么", "怎样", "如何", "哪个", "哪里", "谁", "什么时候", "多少"]):
            return True

        # Question marks (half-width and full-width)
        if normalized.endswith("?") or stripped.endswith("？"):
            return True

        return False

    def _is_casual_chat_message(self, message: str) -> bool:
        msg = (message or "").strip().lower()
        if not msg:
            return False

        # If message contains clear workflow-related terms, it isn't casual.
        workflow_markers = [
            "workflow",
            "flowgram",
            "skill",
            "node",
            "edge",
            "loop",
            "condition",
            "branch",
            "connect",
            "disconnect",
            "add ",
            "remove ",
            "delete ",
            "modify",
            "modif",
            "edit",
            "create",
            "build",
            "generate",
            "load",
            "save",
            "deploy",
            "test",
            "debug",
            "run",
        ]
        if any(m in msg for m in workflow_markers):
            return False

        # Normalize to alphanumerics/spaces for token matching.
        normalized = re.sub(r"[^a-z0-9\s]", " ", msg)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return False

        words = normalized.split()
        if len(words) > 6:
            return False

        casual_phrases = {
            "awesome",
            "great",
            "nice",
            "cool",
            "sweet",
            "perfect",
            "amazing",
            "love it",
            "thanks",
            "thank you",
            "thx",
            "ty",
            "got it",
            "ok",
            "okay",
            "yep",
            "yeah",
            "yup",
            "haha",
            "lol",
        }

        # Match whole-string phrase (after normalization).
        if normalized in casual_phrases:
            return True

        # Simple single-word acknowledgements.
        if len(words) == 1 and words[0] in {"awesome", "great", "nice", "cool", "sweet", "perfect", "amazing", "thanks", "thx", "ty", "ok", "okay", "yep", "yeah", "yup", "lol", "haha"}:
            return True

        return False

    def _format_canvas_context_for_intent(self, canvas_context: Optional[Dict]) -> str:
        if not canvas_context:
            return "Empty canvas"
        # Handle case where canvas_context is a JSON string (from web/AppSync)
        if isinstance(canvas_context, str):
            try:
                import json
                canvas_context = json.loads(canvas_context)
            except (json.JSONDecodeError, TypeError):
                return "Empty canvas"
        if not isinstance(canvas_context, dict):
            return "Empty canvas"
        nodes = canvas_context.get("nodes", [])
        edges = canvas_context.get("edges", [])
        selected = canvas_context.get("selectedNodes", [])
        node_lines = []
        for n in (nodes or [])[:10]:
            node_lines.append(f"{n.get('id')}:{n.get('type')}:{n.get('label', '')}")
        more = ""
        if isinstance(nodes, list) and len(nodes) > 10:
            more = f" (+{len(nodes) - 10} more)"
        return (
            f"nodes={len(nodes) if isinstance(nodes, list) else 0}{more}; "
            f"edges={len(edges) if isinstance(edges, list) else 0}; "
            f"selected={selected}; "
            f"sample_nodes=[{', '.join(node_lines)}]"
        )

    def _get_llm_info(self) -> Dict[str, str]:
        """Return provider/model metadata for the current LLM instance."""
        try:
            llm = self.planner.llm
            model = getattr(llm, "model_name", None) or getattr(llm, "model", None) or "unknown"
            cls_name = type(llm).__name__
            # Try to get provider info from onboarding metadata
            onboarding = getattr(llm, "_onboarding_info", None)
            if onboarding:
                provider = onboarding.get("display_name") or onboarding.get("provider") or cls_name
            else:
                provider = cls_name
            base_url = getattr(llm, "openai_api_base", None) or getattr(llm, "base_url", None) or ""
            return {"provider": str(provider), "model": str(model), "class": cls_name, "base_url": str(base_url)}
        except Exception as e:
            return {"provider": "unknown", "model": "unknown", "class": "unknown", "base_url": "", "error": str(e)}

    async def _invoke_llm_async(self, prompt: str, *, action: str = "") -> str:
        llm = self.planner.llm
        llm_info = self._get_llm_info()
        logger.info(
            f"[SkillEditorAgent] LLM call — provider={llm_info['provider']}, "
            f"model={llm_info['model']}, class={llm_info['class']}, "
            f"prompt_len={len(prompt):,} chars"
        )
        if hasattr(llm, "ainvoke"):
            resp = await llm.ainvoke(prompt)
            token_tracker.record(resp, agent="SkillEditorAgent", action=action)
            return resp.content if hasattr(resp, "content") else str(resp)
        resp = llm.invoke(prompt)
        token_tracker.record(resp, agent="SkillEditorAgent", action=action)
        return resp.content if hasattr(resp, "content") else str(resp)

    async def _invoke_llm_fast(self, prompt: str, *, action: str = "") -> str:
        """Use a lighter/faster model for structured-output tasks like
        requirement collection where speed matters more than deep reasoning."""
        import os
        fast_model = os.environ.get("SKILL_EDITOR_FAST_MODEL", "gpt-4.1-mini")
        try:
            from langchain_openai import ChatOpenAI
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                return await self._invoke_llm_async(prompt, action=action)
            llm = ChatOpenAI(model=fast_model, api_key=api_key, temperature=0.3)
            logger.info(f"[SkillEditorAgent] Fast LLM call — model={fast_model}, prompt_len={len(prompt):,}")
            resp = await llm.ainvoke(prompt)
            token_tracker.record(resp, agent="SkillEditorAgent", action=action)
            return resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            logger.warning(f"[SkillEditorAgent] Fast LLM failed ({e}), falling back to default")
            return await self._invoke_llm_async(prompt, action=action)

    def _extract_json_from_text(self, text: str) -> Optional[Any]:
        try:
            json_match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
            if json_match:
                return json.loads(json_match.group(1))
            # Try bare JSON array first, then object
            json_match = re.search(r"\[[\s\S]*\]", text)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except (json.JSONDecodeError, ValueError):
                    pass
            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception:
            return None

    def _is_vague_edit_request(self, message: str) -> bool:
        msg = (message or "").strip().lower()
        if not msg:
            return True

        has_modif_stem = bool(re.search(r"\bmodif\w*", msg))

        vague_phrases = [
            "do some modification",
            "some modification",
            "some changes",
            "make some changes",
            "modify this",
            "edit this",
            "tweak this",
            "adjust this",
            "improve this",
            "refine this",
            "optimize this",
            "fix this",
        ]
        if any(p in msg for p in vague_phrases):
            return True

        if has_modif_stem:
            if re.search(r"\b(do|make)\s+some\s+modif\w*\b", msg) or re.search(r"\bsome\s+modif\w*\b", msg):
                return True

        # If the message only signals intent but has no target/action details, treat as vague.
        specific_markers = [
            "wrap",
            "loop",
            "condition",
            "branch",
            "connect",
            "disconnect",
            "remove",
            "delete",
            "add",
            "rename",
            "replace",
            "change",
            "update",
            "set ",
            "node ",
            "edge ",
            "id ",
            "->",
        ]
        has_specifics = (
            any(m in msg for m in specific_markers)
            or (msg.count('"') >= 2)
            or (msg.count("'") >= 2)
        )
        if not has_specifics and len(msg.split()) <= 10:
            return True

        return False

    def _is_edit_plan(self, plan: Optional[ImplementationPlan]) -> bool:
        if not plan or not plan.summary:
            return False
        return plan.summary.strip().lower().startswith("edit:")

    def _normalize_canvas_context(self, canvas_context: Optional[Dict]) -> Optional[Dict]:
        """Normalize canvas_context by back-filling nodes/edges from lastFlowgramJson.

        When the frontend's documentService is out of sync (e.g. skill just
        loaded), it sends nodes=[] but includes a `lastFlowgramJson` fallback.
        This method merges the fallback into the primary fields so all
        downstream code sees a consistent view.
        """
        if not canvas_context or not isinstance(canvas_context, dict):
            return canvas_context
        nodes = canvas_context.get("nodes")
        if isinstance(nodes, list) and len(nodes) > 0:
            return canvas_context  # already has real nodes
        # Try lastFlowgramJson fallback (sent by frontend)
        last_fj = canvas_context.get("lastFlowgramJson")
        if isinstance(last_fj, dict):
            wf = last_fj.get("workFlow") or last_fj
            fallback_nodes = wf.get("nodes") or []
            fallback_edges = wf.get("edges") or []
            if fallback_nodes:
                logger.info(f"[SkillEditorAgent] Back-filling canvas_context from lastFlowgramJson: {len(fallback_nodes)} nodes, {len(fallback_edges)} edges")
                canvas_context = {**canvas_context, "nodes": fallback_nodes, "edges": fallback_edges}
                return canvas_context
        # Try cached flowgram from a previous generation in this session
        if self._cached_flowgram_dict:
            wf = self._cached_flowgram_dict.get("workFlow") or self._cached_flowgram_dict
            fallback_nodes = wf.get("nodes") or []
            fallback_edges = wf.get("edges") or []
            if fallback_nodes:
                logger.info(f"[SkillEditorAgent] Back-filling canvas_context from cached_flowgram_dict: {len(fallback_nodes)} nodes, {len(fallback_edges)} edges")
                canvas_context = {**canvas_context, "nodes": fallback_nodes, "edges": fallback_edges}
        return canvas_context

    def _has_loaded_canvas(self, canvas_context: Optional[Dict]) -> bool:
        """Return True if the user has an existing workflow loaded.

        We treat either:
        - non-empty nodes list, OR
        - a provided skillName, OR
        - a previously saved skill name (from earlier generation in this session)
        as evidence of a loaded workflow.
        """
        if canvas_context and isinstance(canvas_context, dict):
            try:
                nodes = canvas_context.get("nodes")
                if isinstance(nodes, list) and len(nodes) > 0:
                    return True
            except Exception:
                pass
            try:
                skill_name = canvas_context.get("skillName")
                if isinstance(skill_name, str) and skill_name.strip():
                    return True
            except Exception:
                pass
        # Fallback: check if we previously saved a skill in this session
        if self._last_saved_skill_name:
            return True
        return False

    def _should_require_edit_confirmation(self, intent: IntentType, message: str, canvas_context: Optional[Dict]) -> bool:
        if intent not in [IntentType.ADD_NODE, IntentType.REMOVE_NODE, IntentType.MODIFY_NODE, IntentType.CONNECT_NODES]:
            return False
        has_canvas = self._has_loaded_canvas(canvas_context)
        if not has_canvas:
            return False

        if intent == IntentType.MODIFY_NODE and self._is_node_config_request(message, canvas_context):
            return False

        msg_lower = (message or "").lower()
        # Deterministic validate/repair requests should not require confirmation.
        if any(w in msg_lower for w in ["validate", "repair", "fix connections", "fix connectivity", "fix edges"]):
            return False

        return True

    async def _emit_progress(self, on_event: Optional[Callable], message: str) -> None:
        if not on_event:
            return
        try:
            import asyncio
            result = on_event({"type": "progress", "data": {"message": message}})
            # Handle both sync and async callbacks
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            return

    async def _classify_intent_llm(self, message: str, canvas_context: Optional[Dict]) -> Tuple[IntentType, float, str]:
        has_canvas = self._has_loaded_canvas(canvas_context)
        canvas_summary = self._format_canvas_context_for_intent(canvas_context)
        _intent_prompt = prompt_store.get("intent_classifier", default=INTENT_CLASSIFIER_SYSTEM_PROMPT)
        prompt = (
            f"{_intent_prompt}\n\n"
            f"has_canvas={str(has_canvas).lower()}\n"
            f"canvas_summary={canvas_summary}\n\n"
            f"user_message={json.dumps(message)}\n"
            f"{get_language_instruction(self._user_lang)}"
        )

        try:
            response = await self._invoke_llm_async(prompt)
            data = self._extract_json_from_text(response) or {}
            intent_str = str(data.get("intent", "general_chat")).strip()
            confidence = float(data.get("confidence", 0.0) or 0.0)
            reason = str(data.get("reason", "")).strip()

            try:
                intent = IntentType(intent_str)
            except Exception:
                intent = IntentType.GENERAL_CHAT

            return intent, max(0.0, min(1.0, confidence)), reason
        except Exception as e:
            logger.error(f"[SkillEditorAgent] LLM intent classification failed: {e}")
            return IntentType.GENERAL_CHAT, 0.0, ""

    # Mapping from taxonomy intent strings → IntentType enum values
    _TAXONOMY_INTENT_MAP: Dict[str, IntentType] = {
        "casual_chat": IntentType.CASUAL_CHAT,
        "multi_agent_design": IntentType.MULTI_AGENT_DESIGN,
        "new_feature": IntentType.CREATE_FLOWGRAM,
        "explain": IntentType.EXPLAIN,
        "find_content": IntentType.EXPLAIN,
        "research": IntentType.EXPLAIN,
        "review": IntentType.EXPLAIN,
        "generate_docs": IntentType.EXPLAIN,
        "troubleshoot_debug": IntentType.ANALYZE_LOG,
        "git_ops": IntentType.GENERAL_CHAT,
        "run_workflow": IntentType.RUN_FLOWGRAM,
        "config_mgmt": IntentType.MODIFY_NODE,
        "refactor": IntentType.MODIFY_NODE,
        "data_analysis_viz": IntentType.GENERAL_CHAT,
        "need_info": IntentType.GENERAL_CHAT,
        "other": IntentType.GENERAL_CHAT,
    }

    async def _classify_with_taxonomy(
        self, message: str, canvas_context: Optional[Dict]
    ) -> Tuple[IntentType, str, float, str]:
        """Classify both intent AND domain using the prompt categorization taxonomy.

        Returns:
            (intent: IntentType, domain: str, confidence: float, reasoning: str)
        """
        taxonomy_text = prompt_store.get_taxonomy()
        if not taxonomy_text:
            # Fallback to legacy classifier if taxonomy file unavailable
            intent, conf, reason = await self._classify_intent_llm(message, canvas_context)
            return intent, "need_info", conf, reason

        has_canvas = self._has_loaded_canvas(canvas_context)
        canvas_summary = self._format_canvas_context_for_intent(canvas_context)

        prompt = (
            f"{taxonomy_text}\n\n"
            "---\n"
            "Classify the following user message using the taxonomy above.\n"
            "Return **JSON only** (no markdown fences) matching the `categorize_prompt` tool schema.\n\n"
            f"has_canvas={str(has_canvas).lower()}\n"
            f"canvas_summary={canvas_summary}\n\n"
            f"user_message={json.dumps(message)}\n"
        )

        try:
            response = await self._invoke_llm_fast(prompt, action="classify_taxonomy")
            data = self._extract_json_from_text(response) or {}
            tax_intent_str = str(data.get("intent", "need_info")).strip()
            domain = str(data.get("domain", "need_info")).strip()
            confidence = float(data.get("confidence", 0.0) or 0.0)
            reasoning = str(data.get("reasoning", "")).strip()

            intent = self._TAXONOMY_INTENT_MAP.get(tax_intent_str, IntentType.GENERAL_CHAT)

            logger.info(
                f"[SkillEditorAgent] Taxonomy classification: "
                f"tax_intent={tax_intent_str} → {intent.value}, domain={domain}, "
                f"confidence={confidence:.2f}, reasoning={reasoning[:120]}"
            )
            return intent, domain, max(0.0, min(1.0, confidence)), reasoning
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Taxonomy classification failed: {e}")
            return IntentType.GENERAL_CHAT, "need_info", 0.0, ""

    def _should_use_planner(self, intent: IntentType, canvas_context: Optional[Dict] = None) -> bool:
        """Determine if the planner should be used for this intent"""
        # Use planner for complex creation tasks.
        # For GENERAL_CHAT, only use planner when canvas is empty (otherwise keep the interaction conversational
        # and avoid multi-choice clarification cards for edits).
        if intent == IntentType.CREATE_FLOWGRAM:
            return True
        if intent == IntentType.CASUAL_CHAT:
            return False
        if intent == IntentType.GENERAL_CHAT:
            has_canvas_nodes = bool(
                canvas_context
                and isinstance(canvas_context.get("nodes"), list)
                and len(canvas_context.get("nodes")) > 0
            )
            return not has_canvas_nodes
        return False

    def _should_require_clarification(self, message: str, intent: IntentType) -> bool:
        """
        Decide whether to force clarification for planning.
        Default: require clarification for workflow creation/general chat unless user opts out.
        """
        msg_lower = (message or "").lower()
        # Force phrases (English/Chinese)
        force_phrases = ["force clarify", "force clarification", "always ask", "强制澄清", "必须澄清", "请先问问题"]
        if any(p in msg_lower for p in force_phrases):
            return True
        # Opt-out phrases
        opt_out_phrases = [
            "skip clarifications",
            "no questions",
            "no need to clarify",
            "no clarification needed",
            "no need for clarification",
            "直接生成",
            "不用问",
            "不用提问",
            "无需澄清",
        ]
        if any(p in msg_lower for p in opt_out_phrases):
            return False
        # Default: require for planner intents
        return intent in [IntentType.CREATE_FLOWGRAM, IntentType.GENERAL_CHAT, IntentType.MULTI_AGENT_DESIGN]

    @staticmethod
    def _needs_multi_agent(message: str) -> bool:
        """Fast keyword heuristic: does this message clearly require multiple concurrent agents?

        Returns True only when there are explicit concurrency/parallelism signals AND
        the volume clearly exceeds what a single sequential workflow can handle.
        We err on the side of false-negative (let the LLM planner decide) rather than
        false-positive (wrongly routing a simple request to the architect).
        """
        import re as _re
        msg = (message or "").lower()

        _STRONG_PATTERNS = [
            # Explicit concurrency with numbers > 1
            _re.compile(r"\b([2-9]\d*|\d{2,})\s+(simultaneous|concurrent|parallel|at.once|at.the.same.time)"),
            _re.compile(r"\b(simultaneous|concurrent|parallel)\b.{0,30}\b([2-9]\d*|\d{2,})\b"),
            # "N users / sessions / chats / tabs" at the same time
            _re.compile(r"\b([2-9]\d*|\d{2,})\s+(users?|customers?|clients?|sessions?|chats?|tabs?|agents?)\b.{0,60}\b(at.once|simultaneously|concurrently|at.the.same.time|in.parallel)"),
            _re.compile(r"\b(handle|serve|support|manage)\b.{0,30}\b([2-9]\d*|\d{2,})\s+(users?|customers?|clients?|sessions?|chats?|tabs?)"),
            # Explicit multi-agent vocabulary
            _re.compile(r"\b(multiple\s+agents?|agent\s+pool|worker\s+agents?|manager\s+agent|agent\s+coordinator)\b"),
            _re.compile(r"\b(20|30|50|100)\s+(tabs?|windows?|browsers?|instances?)\b"),
        ]

        return any(p.search(msg) for p in _STRONG_PATTERNS)

    def _handle_casual_chat(self, message: str, session_id: Optional[str]) -> AgentResponse:
        session_key = session_id or "default"
        rounds = int(self._casual_chat_rounds_by_session.get(session_key, 0) or 0) + 1
        self._casual_chat_rounds_by_session[session_key] = rounds

        max_rounds = 10
        if rounds > max_rounds:
            return AgentResponse(
                message=t("casual_chat_redirect", self._user_lang),
                intent=IntentType.CASUAL_CHAT,
                metadata={"session_id": session_id, "state": self._pipeline_state.value, "casual_rounds": rounds},
            )

        # Default: acknowledge and gently pivot back.
        return AgentResponse(
            message=t("casual_chat_default", self._user_lang),
            intent=IntentType.CASUAL_CHAT,
            metadata={"session_id": session_id, "state": self._pipeline_state.value, "casual_rounds": rounds},
        )

    @staticmethod
    def _extract_log_highlights(raw: str, context_lines: int = 3) -> str:
        """Extract and **categorize** noteworthy log lines with surrounding context.

        Returns a structured string with issues grouped by category in priority
        order so the LLM sees critical-but-rare issues (like auth / API-key
        failures) before high-volume noise (like repeated schema errors).

        Categories (highest priority first):
          1. AUTH FAILURES        – 401/403, Unauthorized, invalid API key, token rejected
          2. RUNTIME ERRORS       – Exception, Traceback, CRITICAL, FATAL, panic, OOM
          3. SCHEMA / VALIDATION  – GraphQL WrongType, missing fields, schema error
          4. GENERAL FAILURES     – failed, failure, ERROR (not already categorised)
          5. WARNINGS / RESOURCE  – WARNING, memory, disk, timeout
          6. AUTH INFO            – token present, api key configured (informational, not failures)

        Each category is capped at ``max_blocks_per_cat`` context blocks to prevent
        one noisy category from consuming the entire token budget.
        """
        import re as _re

        lines = raw.splitlines()
        if not lines:
            return ""

        # --- Define category patterns (order = display priority) ---
        # CRITICAL: AUTH FAILURES must be first and must ONLY match actual
        # rejections (401, 403, "invalid", "Unauthorized", "Authentication
        # Fails").  Informational auth lines ("Token present", "api key
        # configured") go to AUTH INFO at the bottom so they don't drown
        # out real failures.
        _categories = [
            ("🚨 AUTH FAILURES (API key / token rejected)", _re.compile(
                r"(?i)"
                r"(\bunauthorized\b"
                r"|NotAuthorizedException"
                r"|Authentication Fails"
                r"|authentication_error"
                r"|invalid_request_error"
                r"|api[_\s]?key.*invalid"
                r"|invalid.*api[_\s]?key"
                r"|InvalidApiKey"
                r"|\berrorCode['\"\s:]+401\b"
                r"|\berror.code['\"\s:]+401\b"
                r"|Error code:\s*401"
                r"|\b403\b.*\bforbidden\b"
                r"|\bforbidden\b.*\b403\b"
                r"|token\s+(expired|invalid|revoked|rejected)"
                r"|auth\w*\s*(fail|error|denied)"
                r"|Valid authorization header not provided"
                r"|connection closed during ack"
                r"|ModelProviderError.*401"
                r")",
            )),
            ("💥 RUNTIME ERRORS", _re.compile(
                r"(?i)"
                r"(Traceback \(most recent"
                r"|\bCRITICAL\b|\bFATAL\b"
                r"|\bpanic\b|\bOOM\b"
                r"|Exception(?!Input)"  # avoid GraphQL 'ExceptionInput'
                r"|Error[:\s](?!.*Validation error of type)"
                r"|\braise\s+\w+Error"
                r")",
            )),
            ("📋 SCHEMA / VALIDATION", _re.compile(
                r"(?i)"
                r"(Validation error of type"
                r"|missing required fields"
                r"|not in '.*Input'"
                r"|GraphQL.*Error"
                r"|Schema\s*Error"
                r"|Cannot return null for non-nullable"
                r")",
            )),
            ("❌ GENERAL FAILURES", _re.compile(
                r"(?i)"
                r"(\bERROR\b"
                r"|\bfailed\b|\bfailure\b"
                r"|\bretry\b.*\bfailed\b"
                r"|Task failed after"
                r")",
            )),
            ("⚠️ WARNINGS / RESOURCE", _re.compile(
                r"(?i)"
                r"(\bWARN(ING)?\b"
                r"|memory[:\s].*percent"
                r"|disk_usage"
                r"|\btimeout\b"
                r"|not installed"
                r")",
            )),
            ("ℹ️ AUTH INFO (credentials present — not failures)", _re.compile(
                r"(?i)"
                r"(Token present"
                r"|api[_\s]?key.{0,20}configured"
                r"|has API key configured"
                r"|api[_\s]?key\s*[:=]\s*\S+"  # lines that print the key value
                r"|credential\s*(found|loaded|present)"
                r"|secret\s*key"
                r")",
            )),
        ]

        max_blocks_per_cat = 15  # cap per category to keep output bounded

        # --- Classify each line into the FIRST matching category ---
        # (a line only belongs to its highest-priority category)
        cat_hits: dict = {name: set() for name, _ in _categories}
        classified: set = set()

        for idx, line in enumerate(lines):
            for cat_name, pat in _categories:
                if pat.search(line):
                    if idx not in classified:
                        cat_hits[cat_name].add(idx)
                        classified.add(idx)
                    break  # first match wins

        total_hits = sum(len(v) for v in cat_hits.values())
        if total_hits == 0:
            return ""

        # --- Build context windows per category ---
        def _build_blocks(indices: set) -> list:
            if not indices:
                return []
            windows: list = []
            for idx in sorted(indices):
                start = max(0, idx - context_lines)
                end = min(len(lines) - 1, idx + context_lines)
                if windows and start <= windows[-1][1] + 1:
                    windows[-1] = (windows[-1][0], end)
                else:
                    windows.append((start, end))
            blocks = []
            for start, end in windows[:max_blocks_per_cat]:
                block_lines = lines[start: end + 1]
                blocks.append(f"[lines {start + 1}-{end + 1}]\n" + "\n".join(block_lines))
            truncated = len(windows) - max_blocks_per_cat
            if truncated > 0:
                blocks.append(f"... and {truncated} more context blocks in this category (omitted for brevity)")
            return blocks

        # --- Assemble output ---
        sections: list = []
        sections.append(f"({total_hits} issue lines found, categorised by type)\n")

        for cat_name, _ in _categories:
            hits = cat_hits[cat_name]
            if not hits:
                continue
            blocks = _build_blocks(hits)
            section = f"\n### {cat_name} ({len(hits)} hits)\n\n"
            section += "\n---\n".join(blocks)
            sections.append(section)

        return "\n".join(sections)

    async def _run_analyze_log(
        self,
        message: str,
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """
        Read a log file from the user's message, analyze it for errors/failures,
        and return a structured summary.

        First time: asks clarification questions to collect file path, user observation,
        and expected behavior. When answers come back, proceeds to analysis.
        """
        # --- If pre-analysis info was already collected, use it ---
        if self._pending_log_analysis_info and self._pending_log_analysis_info.get("_collected"):
            file_path = self._pending_log_analysis_info.get("log_file_path") or self._extract_file_path_from_message(message)
            user_observation = self._pending_log_analysis_info.get("user_observation", "")
            expected_behavior = self._pending_log_analysis_info.get("expected_behavior", "")
            # Clear the pending info so follow-ups don't re-trigger
            self._pending_log_analysis_info = None
            self._pipeline_state = PipelineState.IDLE
            return await self._run_analyze_log_with_info(
                file_path=file_path,
                user_observation=user_observation,
                expected_behavior=expected_behavior,
                message=message,
                session_id=session_id,
                on_event=on_event,
            )

        # --- Follow-up on a previous log analysis? ---
        file_path = self._extract_file_path_from_message(message)
        if not file_path and self._log_analysis_context:
            self._pipeline_state = PipelineState.IDLE
            return await self._run_analyze_log_followup(message, session_id, on_event)

        # --- First time: collect pre-analysis info via clarification questions ---
        self._pending_log_analysis_info = {
            "original_message": message,
            "detected_file_path": file_path,  # may be None
        }

        questions = []

        _lang = self._user_lang

        # Q0: Which skill(s) are under investigation — searchable typeahead with
        # multi-pick. Handler fills choices from the user's S3 skill list. The A2UI
        # frontend renders this as a substring-filtered dropdown so the user can
        # type a phrase, narrow the list, and select multiple matches.
        questions.append(ClarificationQuestion(
            id="skill_names",
            question=t("log_qa_skill_question", _lang),
            choices=[],          # handler fills choices from S3 before sending to client
            context=t("log_qa_skill_context", _lang),
            allow_multiple=True,
            widget_type="searchable_multi_select",
            data_source="user_skills",
        ))

        # Q1: Log file path (only ask if not already detected)
        if not file_path:
            questions.append(ClarificationQuestion(
                id="log_file_path",
                question=t("log_qa_path_question", _lang),
                choices=[
                    ClarificationChoice(
                        id="path_freeform",
                        label=t("log_qa_path_freeform_label", _lang),
                        description=t("log_qa_path_freeform_desc", _lang),
                        allow_freeform=True,
                    ),
                ],
                context=t("log_qa_path_context", _lang),
                allow_multiple=False,
            ))

        # Q2: What went wrong
        questions.append(ClarificationQuestion(
            id="user_observation",
            question=t("log_qa_observation_question", _lang),
            choices=[
                ClarificationChoice(id="obs_error",        label=t("log_qa_obs_error", _lang),        allow_freeform=True),
                ClarificationChoice(id="obs_wrong_result", label=t("log_qa_obs_wrong_result", _lang), allow_freeform=True),
                ClarificationChoice(id="obs_stuck",        label=t("log_qa_obs_stuck", _lang),        allow_freeform=True),
                ClarificationChoice(id="obs_partial",      label=t("log_qa_obs_partial", _lang),      allow_freeform=True),
                ClarificationChoice(id="obs_other",        label=t("log_qa_obs_other", _lang),        allow_freeform=True),
            ],
            context=t("log_qa_observation_context", _lang),
            allow_multiple=False,
        ))

        # Q3: Expected behavior
        questions.append(ClarificationQuestion(
            id="expected_behavior",
            question=t("log_qa_expected_question", _lang),
            choices=[
                ClarificationChoice(
                    id="exp_freeform",
                    label=t("log_qa_exp_freeform_label", _lang),
                    description=t("log_qa_exp_freeform_desc", _lang),
                    allow_freeform=True,
                ),
                ClarificationChoice(id="exp_unsure", label=t("log_qa_exp_unsure", _lang)),
            ],
            context=t("log_qa_expected_context", _lang),
            allow_multiple=False,
        ))

        self._pipeline_state = PipelineState.COLLECTING_LOG_ANALYSIS_INFO
        self._pending_clarification = questions

        intro = t("log_qa_intro", _lang)
        if file_path:
            intro += "\n\n" + t("log_qa_intro_path_detected", _lang, file_path=file_path)

        return AgentResponse(
            message=intro,
            intent=IntentType.ANALYZE_LOG,
            clarification=questions,
            metadata={
                "session_id": session_id,
                "state": self._pipeline_state.value,
            },
        )

    def _sanitize_owner_for_s3(self) -> str:
        """Sanitize the owner email for use as an S3 directory name.
        Replaces '@' and '.' with '_', e.g. songc@yahoo.com → songc_yahoo_com
        """
        return (self._user_name or "unknown").replace("@", "_").replace(".", "_")

    def _generate_log_upload_url(self, file_path: str) -> Optional[Dict[str, str]]:
        """Generate a presigned S3 PUT URL for uploading a log file.

        Returns dict with {upload_url, s3_bucket, s3_key} or None.
        """
        try:
            import boto3
            import time as _time
            s3_bucket = "ecan-logs"
            sanitized_owner = self._sanitize_owner_for_s3()
            # Handle Windows paths on Linux: Path.name won't parse backslashes
            if file_path:
                import ntpath
                filename = ntpath.basename(file_path) or Path(file_path).name
            else:
                filename = "unknown.log"
            s3_key = f"{sanitized_owner}/{int(_time.time())}_{filename}"
            s3 = boto3.client("s3")
            upload_url = s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": s3_bucket,
                    "Key": s3_key,
                    "ContentType": "text/plain; charset=utf-8",
                },
                ExpiresIn=900,
            )
            logger.info(f"[SkillEditorAgent] Generated presigned upload URL for {s3_key}")
            return {"upload_url": upload_url, "s3_bucket": s3_bucket, "s3_key": s3_key}
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Failed to generate presigned upload URL: {e}")
            return None

    async def _run_analyze_log_with_info(
        self,
        file_path: Optional[str],
        user_observation: str,
        expected_behavior: str,
        message: str,
        session_id: Optional[str],
        on_event: Optional[Callable],
        pasted_content: Optional[str] = None,
    ) -> AgentResponse:
        """Run log analysis after pre-analysis info has been collected.

        Args:
            pasted_content: If provided, use this as the log content directly
                instead of reading from file_path (for cloud mode where Lambda
                cannot access local files).
        """
        self._pipeline_state = PipelineState.IDLE

        # --- Pasted content mode (cloud / Lambda — user pasted log text) ---
        if pasted_content:
            raw = pasted_content.strip()
            file_size = len(raw.encode("utf-8", errors="replace"))
            file_path = "(pasted content)"
            if not raw:
                return AgentResponse(
                    message=t("log_empty_paste", self._user_lang),
                    intent=IntentType.ANALYZE_LOG,
                    metadata={"session_id": session_id, "state": "idle"},
                )
            # Skip directly to analysis (after the file-reading block below)
        else:
            raw = None  # will be read from file below

        if not pasted_content:
            await self._emit_progress(on_event, t("progress_reading_log", self._user_lang))

            if not file_path:
                return AgentResponse(
                    message=t("log_no_file_path", self._user_lang),
                    intent=IntentType.ANALYZE_LOG,
                    metadata={"session_id": session_id, "state": "idle", "needs_file_path": True},
                )

            # --- Cloud mode: generate presigned upload URL for the client ---
            if _is_lambda_runtime():
                upload_info = self._generate_log_upload_url(file_path)
                if upload_info:
                    self._pending_log_analysis_info = {
                        "user_observation": user_observation,
                        "expected_behavior": expected_behavior,
                        "s3_bucket": upload_info["s3_bucket"],
                        "s3_key": upload_info["s3_key"],
                        "_awaiting_upload": True,
                    }
                    self._pipeline_state = PipelineState.COLLECTING_LOG_ANALYSIS_INFO
                    return AgentResponse(
                        message=t("log_uploading", self._user_lang, file_path=file_path),
                        intent=IntentType.ANALYZE_LOG,
                        metadata={
                            "session_id": session_id,
                            "state": "collecting_log_analysis_info",
                            "log_upload_request": {
                                "upload_url": upload_info["upload_url"],
                                "s3_bucket": upload_info["s3_bucket"],
                                "s3_key": upload_info["s3_key"],
                                "local_file_path": file_path,
                            },
                        },
                    )
                else:
                    # Fallback: ask user to paste content
                    self._pending_log_analysis_info = {
                        "user_observation": user_observation,
                        "expected_behavior": expected_behavior,
                        "_awaiting_paste": True,
                    }
                    self._pipeline_state = PipelineState.COLLECTING_LOG_ANALYSIS_INFO
                    return AgentResponse(
                        message=t("log_cloud_paste_request", self._user_lang, file_path=file_path),
                        intent=IntentType.ANALYZE_LOG,
                        metadata={"session_id": session_id, "state": "collecting_log_analysis_info"},
                    )

            # --- Resolve file path (handle directory → pick most recent log file) ---
            try:
                p = Path(file_path)
                if not p.exists():
                    return AgentResponse(
                        message=t("log_file_not_found", self._user_lang, file_path=file_path),
                        intent=IntentType.ANALYZE_LOG,
                        metadata={"session_id": session_id, "state": "idle", "file_not_found": True},
                    )
                if p.is_dir():
                    log_exts = {".log", ".txt", ".out", ".err"}
                    candidates = [
                        f for f in p.iterdir()
                        if f.is_file() and f.suffix.lower() in log_exts
                    ]
                    if not candidates:
                        return AgentResponse(
                            message=t("log_dir_no_logs", self._user_lang, file_path=file_path),
                            intent=IntentType.ANALYZE_LOG,
                            metadata={"session_id": session_id, "state": "idle"},
                        )
                    # Pick the most recently modified file
                    p = max(candidates, key=lambda f: f.stat().st_mtime)
                    file_path = str(p)
                    await self._emit_progress(on_event, t("log_dir_using_recent", self._user_lang, filename=p.name))
            except Exception as e:
                return AgentResponse(
                    message=t("log_read_error", self._user_lang, file_path=file_path, error=str(e)),
                    intent=IntentType.ANALYZE_LOG,
                    metadata={"session_id": session_id, "state": "idle", "read_error": str(e)},
                )

            # --- Read the file ---
            read_error = None
            file_size = 0
            try:
                file_size = p.stat().st_size
                raw = p.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                read_error = str(e)

            if read_error:
                return AgentResponse(
                    message=t("log_read_failed", self._user_lang, file_path=file_path, error=read_error),
                    intent=IntentType.ANALYZE_LOG,
                    metadata={"session_id": session_id, "state": "idle", "read_error": read_error},
                )

            if not raw or not raw.strip():
                return AgentResponse(
                    message=t("log_file_empty", self._user_lang, file_path=file_path),
                    intent=IntentType.ANALYZE_LOG,
                    metadata={"session_id": session_id, "state": "idle"},
                )

        # --- Log LLM info ---
        llm_info = self._get_llm_info()
        logger.info(
            f"[SkillEditorAgent] Log analysis using LLM: "
            f"provider={llm_info['provider']}, model={llm_info['model']}, "
            f"class={llm_info['class']}, base_url={llm_info.get('base_url', '')}"
        )

        await self._emit_progress(on_event, t("progress_pre_filtering", self._user_lang, size=f"{file_size:,}"))

        # --- Stage 1: Pre-filter — extract ERROR/WARNING/Exception lines with context ---
        highlights = self._extract_log_highlights(raw)
        logger.info(
            f"[SkillEditorAgent] Log pre-filter: {len(raw):,} chars raw, "
            f"{len(highlights):,} chars highlights extracted"
        )

        # --- Stage 2: Decide what to send to the LLM ---
        # For large logs (>500KB) with good highlights, send ONLY the highlights
        # plus a small head+tail snippet for log structure/timespan context.
        # For smaller logs, include the full content as supplementary context.
        LARGE_LOG_THRESHOLD = 500_000  # ~500KB
        is_large_log = len(raw) > LARGE_LOG_THRESHOLD and len(highlights) > 200
        if is_large_log:
            # Large log: highlights-only mode (mimics targeted grep approach)
            snippet_head = raw[:3_000]
            snippet_tail = raw[-3_000:]
            log_content = (
                snippet_head
                + f"\n\n... [{len(raw):,} chars total — only head/tail snippet shown, "
                f"see HIGHLIGHTS above for all issues] ...\n\n"
                + snippet_tail
            )
            logger.info(
                f"[SkillEditorAgent] Large log ({len(raw):,} chars) — highlights-only mode, "
                f"sending {len(highlights):,} chars highlights + 6k snippet"
            )
        else:
            MAX_CHARS = 120_000
            highlights_budget = min(len(highlights), 40_000)
            remaining_budget = MAX_CHARS - highlights_budget
            if len(raw) > remaining_budget:
                head = raw[:5_000]
                tail = raw[-(remaining_budget - 5_000):]
                log_content = (
                    head
                    + f"\n\n... [truncated {len(raw) - remaining_budget:,} characters] ...\n\n"
                    + tail
                )
            else:
                log_content = raw

        await self._emit_progress(on_event, t("progress_analyzing", self._user_lang, provider=llm_info['provider'], model=llm_info['model']))

        # --- Build analysis prompt ---
        prompt_parts = [
            "You are an expert log analyst for eCan.ai, an AI agent / workflow automation platform.\n"
            "The user has provided a run log file for analysis.\n\n"
            "**IMPORTANT**: Below you will find a PRE-FILTERED HIGHLIGHTS section that has already "
            "extracted and categorised all noteworthy lines from the log. The categories are ordered "
            "by severity:\n"
            "  1. AUTH FAILURES — actual 401/403/Unauthorized/invalid API key rejections\n"
            "  2. RUNTIME ERRORS — exceptions, tracebacks, crashes\n"
            "  3. SCHEMA/VALIDATION — GraphQL type mismatches\n"
            "  4. GENERAL FAILURES — other errors\n"
            "  5. WARNINGS/RESOURCE — warnings, memory, disk\n"
            "  6. AUTH INFO — informational lines about tokens/keys being present (NOT failures)\n\n"
            "You MUST address EVERY category that has hits. Pay SPECIAL attention to AUTH FAILURES — "
            "even a single invalid API key or 401 error is often the ROOT CAUSE that cascades into "
            "many downstream failures (e.g. LLM retries, browser-use failures, task timeouts).\n"
            "Do NOT confuse AUTH INFO (key is configured/present) with AUTH FAILURES (key is rejected/invalid).\n\n"
            "Instructions:\n"
            "1. **Log Summary**: Concise summary — which task/skill ran, node count, duration.\n"
            "2. **Issue Analysis (by category)**: For EACH category in the highlights, list every "
            "distinct issue found. For each issue state:\n"
            "   - The error message / traceback (quote the relevant log line)\n"
            "   - Which node or component produced it\n"
            "   - Root cause assessment\n"
            "   - Whether it's a **setup issue** (customer config), **code bug**, or **backend issue**\n"
            "3. **Classification Table**: Provide a summary table:\n"
            "   Issue | Type (setup/code bug/backend) | Cause\n"
            "4. **Recommended Actions**: Prioritised fix list for the customer.\n\n"
            "Format your response in clear Markdown sections.\n"
            "Be specific — quote relevant log lines when referencing errors.\n\n"
            f"File: {file_path} ({file_size:,} bytes)\n"
            f"User message: {message}\n\n"
            f"--- USER OBSERVATION (what went wrong) ---\n"
            f"{user_observation or '(not provided)'}\n\n"
            f"--- EXPECTED BEHAVIOR ---\n"
            f"{expected_behavior or '(not provided)'}\n\n"
        ]

        # Include pre-filtered highlights section FIRST so the LLM sees issues upfront
        if highlights.strip():
            prompt_parts.append(
                "--- PRE-FILTERED & CATEGORISED HIGHLIGHTS (ordered by severity) ---\n"
                f"{highlights[:40_000]}\n"
                "--- END HIGHLIGHTS ---\n\n"
            )

        if is_large_log:
            prompt_parts.append(
                "--- LOG HEAD+TAIL SNIPPET (for timespan/structure context only) ---\n"
                f"{log_content}\n"
                "--- END SNIPPET ---\n"
            )
        else:
            prompt_parts.append(
                "--- BEGIN FULL LOG (may be truncated for large files) ---\n"
                f"{log_content}\n"
                "--- END FULL LOG ---\n"
            )

        prompt = "".join(prompt_parts)

        try:
            analysis = await self._invoke_llm_async(prompt)
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Log analysis LLM call failed: {e}")
            analysis = (
                f"I was able to read the log file ({file_size:,} bytes) but encountered an error "
                f"during analysis: {e}\n\nPlease try again or provide a smaller log file."
            )

        analysis_text = str(analysis).strip()

        # Append LLM info footer so user knows which model analyzed the log
        analysis_text += (
            f"\n\n---\n*Analysis performed by **{llm_info['provider']}** / "
            f"**{llm_info['model']}** ({llm_info['class']})*"
        )

        # Save context so follow-up questions can reference this analysis
        self._log_analysis_context = {
            "file_path": file_path,
            "file_size": file_size,
            "log_content": log_content,
            "highlights": highlights,
            "last_analysis": analysis_text,
            "user_observation": user_observation,
            "expected_behavior": expected_behavior,
        }

        # Offer to auto-fix if analysis found issues
        analysis_text += (
            "\n\n---\n"
            "\U0001f527 **I can try to fix this workflow automatically** based on the issues found above. "
            "Just say **\"fix it\"** and make sure the affected skill is loaded on canvas."
        )
        self._pipeline_state = PipelineState.AWAITING_LOG_FIX_CONFIRMATION

        return AgentResponse(
            message=analysis_text,
            intent=IntentType.ANALYZE_LOG,
            metadata={
                "session_id": session_id,
                "state": self._pipeline_state.value,
                "file_path": file_path,
                "file_size": file_size,
                "llm_provider": llm_info["provider"],
                "llm_model": llm_info["model"],
            },
        )

    async def _handle_log_analysis_info_responses(
        self,
        clarification_responses: Dict[str, List[str]],
        message: str,
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """Handle pre-analysis info responses and proceed to log analysis."""
        pending = self._pending_log_analysis_info or {}
        original_message = pending.get("original_message", message)
        detected_file_path = pending.get("detected_file_path")

        logger.info(f"[SkillEditorAgent] Raw clarification_responses keys: {list(clarification_responses.keys())}")
        for k, v in clarification_responses.items():
            logger.info(f"[SkillEditorAgent]   {k!r} -> {v!r}")

        # Extract answers from clarification responses
        # Frontend sends two keys per question:
        #   "{qid}": ["choice_id"]              — the selected choice(s)
        #   "freeform_{qid}": ["typed text"]     — optional freeform text for that choice
        file_path = detected_file_path
        user_observation = ""
        expected_behavior = ""

        def _get_freeform(qid: str) -> str:
            """Get freeform text for a question, checking freeform_{qid} key first."""
            freeform_val = clarification_responses.get(f"freeform_{qid}")
            if freeform_val:
                text = freeform_val[0] if isinstance(freeform_val, list) else str(freeform_val)
                if text.strip():
                    return text.strip()
            # Fallback: check if the answer itself contains text beyond choice IDs
            ans = clarification_responses.get(qid)
            if ans:
                text = " ".join(a for a in ans if a) if isinstance(ans, list) else str(ans)
                return text.strip()
            return ""

        # Q0: skill names — multi-select, choice IDs are skill names (set by handler)
        selected_skill_names: List[str] = []
        raw_skills = clarification_responses.get("skill_names") or []
        if isinstance(raw_skills, list):
            # Filter out sentinel IDs, keep non-empty strings that look like skill names
            selected_skill_names = [s.strip() for s in raw_skills if s and s.strip() and not s.startswith("_")]
        logger.info(f"[SkillEditorAgent] Selected skill_names: {selected_skill_names}")

        # Q1: log file path
        freeform_path = _get_freeform("log_file_path")
        if freeform_path and freeform_path != "path_freeform":
            file_path = freeform_path

        # Q2: user observation — combine choice label + freeform details
        user_observation = _get_freeform("user_observation")

        # Q3: expected behavior
        expected_behavior = _get_freeform("expected_behavior")

        logger.info(
            f"[SkillEditorAgent] Log analysis info collected: file_path={file_path}, "
            f"skill_names={selected_skill_names}, "
            f"observation_len={len(user_observation)}, expected_len={len(expected_behavior)}"
        )

        # Mark as collected and proceed
        self._pending_log_analysis_info = {
            "log_file_path": file_path,
            "user_observation": user_observation,
            "expected_behavior": expected_behavior,
            "selected_skill_names": selected_skill_names,
            "_collected": True,
        }

        return await self._run_analyze_log(
            message=original_message,
            session_id=session_id,
            on_event=on_event,
        )

    def _is_fix_confirmation(self, message: str) -> bool:
        """Check if the user's message is confirming they want auto-fix applied."""
        msg_lower = message.lower().strip()
        fix_keywords = [
            "fix it", "fix this", "apply fix", "apply the fix", "apply fixes",
            "go ahead", "yes", "yeah", "yep", "sure", "ok", "okay", "do it",
            "please fix", "auto fix", "autofix", "修复", "修一下", "帮我修",
            "apply", "patch", "repair",
        ]
        return any(kw in msg_lower for kw in fix_keywords)

    async def _apply_log_analysis_fixes(
        self,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """
        Apply fixes from a previous log analysis to the current workflow on canvas.
        Uses the code_agent's edit mode to modify the flowgram based on the analysis.
        """
        ctx = self._log_analysis_context
        if not ctx or not ctx.get("last_analysis"):
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=t("log_no_analysis_for_fix", self._user_lang),
                intent=IntentType.ANALYZE_LOG,
                metadata={"session_id": session_id, "state": "idle"},
            )

        # Convert canvas context to flowgram
        current_flowgram = self._canvas_context_to_flowgram(canvas_context)
        if not current_flowgram or not current_flowgram.nodes:
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=t("log_no_workflow_for_fix", self._user_lang),
                intent=IntentType.ANALYZE_LOG,
                metadata={"session_id": session_id, "state": "idle"},
            )

        await self._emit_progress(on_event, t("progress_applying_fixes", self._user_lang))

        last_analysis = ctx["last_analysis"]
        user_observation = ctx.get("user_observation", "")
        expected_behavior = ctx.get("expected_behavior", "")

        # Build an edit request from the analysis.
        # If structured run-error context is available (populated by Fargate SNS completion),
        # prepend it so the Coder can apply a targeted fix before reading the full analysis.
        edit_request = (
            "Apply the following fixes to this workflow based on a log analysis.\n\n"
            "**IMPORTANT**: Prefer fixing by improving sub-agent prompts (adding rules, "
            "exceptions, verification steps, output format constraints) over adding new "
            "condition nodes or structural changes. The workflow should be agentic, not RPA.\n\n"
        )

        if self._last_run_error:
            err = self._last_run_error
            edit_request += "## Structured Run Error (primary diagnosis signal)\n"
            if err.get("failed_node_id"):
                edit_request += f"- **Failed node**: `{err['failed_node_id']}` ({err.get('failed_node_type', 'unknown type')})\n"
            if err.get("error_type"):
                edit_request += f"- **Error type**: `{err['error_type']}`\n"
            if err.get("error_message"):
                edit_request += f"- **Error message**: {err['error_message']}\n"
            if err.get("input_at_failure"):
                import json as _json
                input_preview = _json.dumps(err["input_at_failure"])[:400]
                edit_request += f"- **Node input at failure**: `{input_preview}`\n"
            if err.get("fix_hypothesis"):
                edit_request += f"- **Hypothesis**: {err['fix_hypothesis']}\n"
            if err.get("iteration"):
                edit_request += f"- **Fix attempt**: #{err['iteration']}\n"
            edit_request += "\nApply a **targeted fix** to the node above first, then check the full analysis below.\n\n"

        if user_observation:
            edit_request += f"**User observation (what went wrong):** {user_observation}\n\n"
        if expected_behavior:
            edit_request += f"**Expected behavior:** {expected_behavior}\n\n"
        edit_request += (
            "**Log analysis findings and recommended fixes:**\n\n"
            f"{last_analysis[:12000]}\n\n"
            "Apply all recommended fixes from the analysis above. For each fix:\n"
            "1. If the fix is a prompt improvement — update the affected node's prompt text\n"
            "2. If the fix is a configuration change — update the affected node's config\n"
            "3. If the fix requires structural changes — add/remove/rewire nodes as needed\n"
            "4. Preserve all existing nodes and edges that are not affected by the fixes\n"
        )

        self._pipeline_state = PipelineState.EDITING

        try:
            # Set the current flowgram so code_agent has context
            self.code_agent.set_current_flowgram(current_flowgram)

            code_output = await self.code_agent.edit(
                edit_request=edit_request,
                current_flowgram=current_flowgram,
                on_event=on_event,
                tools_catalog=self.tools_catalog_text,
                user_lang=self._user_lang,
            )
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Auto-fix edit failed: {e}")
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=t("log_fix_error", self._user_lang, error=str(e)),
                intent=IntentType.ANALYZE_LOG,
                metadata={"session_id": session_id, "state": "idle"},
            )

        self._pipeline_state = PipelineState.IDLE

        commands = []
        skill_path = None
        if code_output.flowgram:
            # Preserve the original skill name
            if current_flowgram.metadata and current_flowgram.metadata.get("skillName"):
                if not code_output.flowgram.metadata:
                    code_output.flowgram.metadata = {}
                code_output.flowgram.metadata["skillName"] = current_flowgram.metadata["skillName"]

            skill_path = self._save_flowgram_to_disk(
                code_output.flowgram,
                data_mapping=code_output.data_mapping,
            )
            if skill_path:
                commands = [CanvasCommand(
                    type="canvas.load_flowgram",
                    payload={
                        "skillPath": skill_path,
                        "skillName": code_output.flowgram.metadata.get("skillName", "fixed_skill"),
                    },
                )]
            else:
                commands = self.code_agent.generate_canvas_commands(code_output.flowgram)

        # Build response message
        fix_msg = code_output.message or "Fixes applied."
        fix_msg = (
            "\U0001f527 **Auto-fix applied based on log analysis**\n\n"
            f"{fix_msg}\n\n"
            "The updated workflow has been loaded onto the canvas. "
            "Please review the changes and test the skill to verify the fixes."
        )

        # Clear the fix confirmation state (keep analysis context for follow-ups)
        return AgentResponse(
            message=fix_msg,
            commands=[CanvasCommand(type=c.type, payload=c.payload) for c in commands],
            intent=IntentType.ANALYZE_LOG,
            flowgram=code_output.flowgram,
            validation=code_output.validation,
            metadata={
                "session_id": session_id,
                "state": "idle",
                "skillPath": skill_path,
                "auto_fix_applied": True,
            },
        )

    async def _run_analyze_log_followup(
        self,
        message: str,
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """Handle follow-up questions about a previously analyzed log file."""
        ctx = self._log_analysis_context
        file_path = ctx["file_path"]
        log_content = ctx["log_content"]
        last_analysis = ctx["last_analysis"]
        file_size = ctx.get("file_size", 0)

        await self._emit_progress(on_event, t("progress_answering_followup", self._user_lang, filename=Path(file_path).name))

        # Build recent conversation history for context
        history_block = ""
        recent = self._conversation_history[-6:]  # last 3 exchanges
        if recent:
            history_lines = []
            for msg in recent:
                role = "User" if msg.get("role") == "user" else "Assistant"
                history_lines.append(f"{role}: {msg.get('content', '')[:2000]}")
            history_block = "\n".join(history_lines)

        highlights = ctx.get("highlights", "")

        prompt = (
            "You are an expert log analyst for eCan.ai, an AI agent / workflow automation platform.\n"
            "You previously analyzed a log file and provided an analysis (shown below).\n"
            "The user is now asking a follow-up question about the SAME log.\n\n"
            "Answer the user's question precisely based on the log content.\n"
            "If the answer is in the log, quote the relevant lines.\n"
            "If the log does not contain information related to the question, say so clearly.\n\n"
            f"File: {file_path} ({file_size:,} bytes)\n\n"
            "--- PREVIOUS ANALYSIS ---\n"
            f"{last_analysis[:8000]}\n"
            "--- END PREVIOUS ANALYSIS ---\n\n"
        )
        if history_block:
            prompt += (
                "--- RECENT CONVERSATION ---\n"
                f"{history_block}\n"
                "--- END CONVERSATION ---\n\n"
            )
        if highlights.strip():
            prompt += (
                "--- PRE-FILTERED HIGHLIGHTS (ERROR/WARNING/Exception lines with context) ---\n"
                f"{highlights[:40_000]}\n"
                "--- END HIGHLIGHTS ---\n\n"
            )
        prompt += (
            f"User's follow-up question: {message}\n\n"
            "--- BEGIN FULL LOG ---\n"
            f"{log_content}\n"
            "--- END FULL LOG ---\n"
        )

        try:
            analysis = await self._invoke_llm_async(prompt)
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Log follow-up LLM call failed: {e}")
            analysis = f"Error during follow-up analysis: {e}\n\nPlease try again."

        followup_text = str(analysis).strip()

        # Update the last analysis so chained follow-ups accumulate context
        self._log_analysis_context["last_analysis"] = followup_text

        return AgentResponse(
            message=followup_text,
            intent=IntentType.ANALYZE_LOG,
            metadata={
                "session_id": session_id,
                "state": "idle",
                "file_path": file_path,
                "file_size": file_size,
                "is_followup": True,
            },
        )

    async def _run_explain(self, message: str, canvas_context: Optional[Dict], session_id: Optional[str], on_event: Optional[Callable]) -> AgentResponse:
        self._pipeline_state = PipelineState.IDLE
        await self._emit_progress(on_event, t("progress_answering", self._user_lang))

        lang_inst = get_language_instruction(self._user_lang)

        # Build workflow context if a skill is loaded
        workflow_desc = ""
        if canvas_context and isinstance(canvas_context, dict):
            nodes = canvas_context.get("nodes", [])
            edges = canvas_context.get("edges", [])
            skill_name = canvas_context.get("skillName", "")
            if nodes:
                workflow_desc = f"\n\nThe user has a workflow loaded on canvas"
                if skill_name:
                    workflow_desc += f" named '{skill_name}'"
                workflow_desc += f" with {len(nodes)} nodes and {len(edges)} connections.\n"
                workflow_desc += "Workflow nodes:\n"
                for i, node in enumerate(nodes):
                    n_id = node.get('id', '')
                    n_type = node.get('type', '')
                    n_label = node.get('label', node.get('data', {}).get('label', '') if isinstance(node.get('data'), dict) else '')
                    n_data = node.get('data', {})
                    workflow_desc += f"  {i+1}. [{n_type}] {n_label} (id={n_id})\n"
                    # Include key config for context
                    if isinstance(n_data, dict):
                        for key in ['prompt', 'code', 'url', 'condition', 'items', 'loopType', 'maxIterations', 'description']:
                            val = n_data.get(key)
                            if val:
                                val_str = str(val)[:300]
                                workflow_desc += f"     {key}: {val_str}\n"
                if edges:
                    workflow_desc += "Connections:\n"
                    for edge in edges:
                        workflow_desc += f"  {edge.get('source','')} → {edge.get('target','')}\n"

        prompt = (
            "You are a helpful eCan.ai skill editor assistant. Answer the user's question directly and concisely. "
            "If the question is about the current workflow on canvas, use the workflow context below to give a specific answer."
            "If the question is about current events and you are not fully certain, say that your information may be outdated.\n"
            f"{workflow_desc}\n"
            f"user_question={json.dumps(message)}\n"
            f"{lang_inst}"
        )

        try:
            answer = await self._invoke_llm_async(prompt)
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Explain answer failed: {e}")
            answer = "I had trouble generating an answer right now. Please try again."

        return AgentResponse(
            message=str(answer).strip(),
            intent=IntentType.EXPLAIN,
            metadata={"session_id": session_id, "state": self._pipeline_state.value},
        )

    async def _run_multi_agent_design(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """Handle multi-agent architecture design discussions.

        Loads the architect prompt, injects conversation history for multi-turn
        discussions, and responds with concrete multi-agent architecture recommendations.
        """
        self._pipeline_state = PipelineState.IDLE
        await self._emit_progress(on_event, t("progress_answering", self._user_lang))

        lang_inst = get_language_instruction(self._user_lang)
        architect_prompt = prompt_store.get("architect", default="")

        # Build conversation history block for multi-turn context
        history_block = ""
        if self._conversation_history:
            recent = self._conversation_history[-8:]  # last 4 exchanges
            lines = []
            for msg in recent:
                role = msg.get("role", "")
                content = (msg.get("content") or "")[:600]  # cap per message
                if role and content:
                    lines.append(f"{role.upper()}: {content}")
            if lines:
                history_block = "\n\n## Conversation History (most recent)\n" + "\n".join(lines)

        system_prompt = (
            f"{architect_prompt}\n\n"
            f"{history_block}\n\n"
            f"{lang_inst}"
        )
        user_prompt = f"user_message={json.dumps(message)}"

        try:
            answer = await self._invoke_llm_async(system_prompt + "\n\n" + user_prompt, action="multi_agent_design")
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Multi-agent design failed: {e}")
            answer = "I had trouble generating an architecture recommendation right now. Please try again."

        return AgentResponse(
            message=str(answer).strip(),
            intent=IntentType.MULTI_AGENT_DESIGN,
            metadata={"session_id": session_id, "state": self._pipeline_state.value},
        )
    
    def _is_node_config_request(self, message: str, canvas_context: Optional[Dict]) -> bool:
        """Check if the message is a node configuration request"""
        if not canvas_context:
            return False
        
        msg_lower = message.lower()
        
        # Check for configuration-related keywords
        config_keywords = ["configure", "set", "change", "update", "modify", "edit"]
        has_config_keyword = any(kw in msg_lower for kw in config_keywords)
        
        # Check if a specific node is mentioned or selected
        selected_nodes = canvas_context.get("selectedNodes", [])
        if selected_nodes and has_config_keyword:
            return True
        
        # Check for node type mentions with config intent
        node_types = ["llm", "code", "http", "condition", "loop", "mcp"]
        for node_type in node_types:
            if node_type in msg_lower and has_config_keyword:
                return True
        
        return False
    
    def _get_selected_node_from_context(self, canvas_context: Optional[Dict]) -> Optional[Dict[str, Any]]:
        """Extract the selected node from canvas context"""
        if not canvas_context:
            return None
        
        selected_nodes = canvas_context.get("selectedNodes", [])
        if selected_nodes:
            # Return the first selected node
            node_id = selected_nodes[0]
            nodes = canvas_context.get("nodes", [])
            for node in nodes:
                if node.get("id") == node_id:
                    return node
        
        return None
    
    async def process_message(
        self,
        message: str,
        canvas_context: Optional[Dict] = None,
        session_id: Optional[str] = None,
        clarification_responses: Optional[Dict[str, List[str]]] = None,
        on_event: Optional[Callable] = None
    ) -> AgentResponse:
        """
        Process a chat message through the planning and code generation pipeline.
        
        Args:
            message: User's chat message
            canvas_context: Current canvas state (nodes, edges)
            session_id: Chat session ID for context
            clarification_responses: Answers to previous clarification questions
            on_event: Callback for streaming events
            
        Returns:
            AgentResponse with message, commands, and optional clarification/plan
        """
        logger.info(f"[SkillEditorAgent] Processing message: {message[:100]}...")
        logger.info(f"[SkillEditorAgent] Pipeline state: {self._pipeline_state.value}")

        # Normalize canvas_context: parse JSON string if needed (from web/AppSync)
        if isinstance(canvas_context, str):
            try:
                import json
                canvas_context = json.loads(canvas_context)
                logger.info("[SkillEditorAgent] Parsed canvas_context from JSON string")
            except (json.JSONDecodeError, TypeError):
                logger.warning("[SkillEditorAgent] Failed to parse canvas_context string, setting to None")
                canvas_context = None
        if canvas_context is not None and not isinstance(canvas_context, dict):
            logger.warning(f"[SkillEditorAgent] canvas_context is not a dict ({type(canvas_context)}), setting to None")
            canvas_context = None

        # Back-fill nodes/edges from lastFlowgramJson when documentService is out of sync
        canvas_context = self._normalize_canvas_context(canvas_context)

        # Detect user language for i18n
        # When processing clarification responses, the message may be synthetic
        # English text (e.g. "Clarification answers submitted"), so preserve the
        # language detected from the original user request.
        if not clarification_responses:
            self._user_lang = detect_language(message)
        elif self._user_lang == "en" and self._current_request:
            self._user_lang = detect_language(self._current_request)

        await self._emit_progress(on_event, t("progress_thinking", self._user_lang))

        # Restore per-skill chat context (conversation history) once per (skill, session_id)
        try:
            if session_id:
                skill_dir_for_context = self._infer_skill_dir_name(canvas_context) or self._infer_skill_dir_name_from_current_flowgram()
                if skill_dir_for_context:
                    context_key = f"{skill_dir_for_context}:{session_id}"
                    if self._loaded_context_key != context_key:
                        self._restore_conversation_history(skill_dir_for_context, session_id)
                        self._loaded_context_key = context_key
        except Exception:
            pass
        
        # Add user message to conversation history for context accumulation
        self.add_to_history("user", message)
        
        try:
            # Handle uploaded log file (client uploaded to S3 after receiving presigned URL)
            if (
                self._pipeline_state == PipelineState.COLLECTING_LOG_ANALYSIS_INFO
                and not clarification_responses
            ):
                pending = self._pending_log_analysis_info or {}
                if pending.get("_awaiting_upload"):
                    s3_bucket = pending.get("s3_bucket", "ecan-logs")
                    s3_key = pending.get("s3_key", "")
                    user_obs = pending.get("user_observation", "")
                    expected = pending.get("expected_behavior", "")
                    logger.info(f"[SkillEditorAgent] Upload complete, reading log from S3: {s3_bucket}/{s3_key}")
                    self._pending_log_analysis_info = None
                    try:
                        import boto3
                        s3 = boto3.client("s3")
                        obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
                        raw = obj["Body"].read().decode("utf-8", errors="replace")
                        logger.info(f"[SkillEditorAgent] Read {len(raw):,} bytes from S3")
                    except Exception as e:
                        logger.error(f"[SkillEditorAgent] Failed to read log from S3: {e}")
                        self._pipeline_state = PipelineState.IDLE
                        response = AgentResponse(
                            message=t("log_cloud_read_failed", self._user_lang, error=str(e)),
                            intent=IntentType.ANALYZE_LOG,
                            metadata={"session_id": session_id, "state": "idle"},
                        )
                        self._add_response_to_history(response)
                        return response
                    response = await self._run_analyze_log_with_info(
                        file_path=s3_key,
                        user_observation=user_obs,
                        expected_behavior=expected,
                        message=message,
                        session_id=session_id,
                        on_event=on_event,
                        pasted_content=raw,
                    )
                    self._add_response_to_history(response)
                    return response

            # Handle pasted log content when in cloud mode (Lambda can't access local files)
            if (
                self._pipeline_state == PipelineState.COLLECTING_LOG_ANALYSIS_INFO
                and not clarification_responses
            ):
                pending = self._pending_log_analysis_info or {}
                if pending.get("_awaiting_paste"):
                    logger.info("[SkillEditorAgent] Received pasted log content for cloud-mode analysis")
                    user_obs = pending.get("user_observation", "")
                    expected = pending.get("expected_behavior", "")
                    self._pending_log_analysis_info = None
                    response = await self._run_analyze_log_with_info(
                        file_path=None,
                        user_observation=user_obs,
                        expected_behavior=expected,
                        message=message,
                        session_id=session_id,
                        on_event=on_event,
                        pasted_content=message,
                    )
                    self._add_response_to_history(response)
                    return response

            # If we're waiting on clarification answers, don't let casual messages derail the flow.
            if self._pipeline_state in [PipelineState.AWAITING_CLARIFICATION, PipelineState.CONFIGURING_NODE, PipelineState.COLLECTING_REQUIREMENTS, PipelineState.COLLECTING_LOG_ANALYSIS_INFO, PipelineState.AWAITING_LOG_FIX_CONFIRMATION] and not clarification_responses:
                if self._is_casual_chat_message(message):
                    response = AgentResponse(
                        message=t("casual_chat_awaiting_answers", self._user_lang),
                        intent=IntentType.CASUAL_CHAT,
                        metadata={"session_id": session_id, "state": self._pipeline_state.value},
                    )
                    self._add_response_to_history(response)
                    return response

            # Handle log analysis pre-collection responses
            if clarification_responses and self._pipeline_state == PipelineState.COLLECTING_LOG_ANALYSIS_INFO:
                logger.info("[SkillEditorAgent] Processing log analysis pre-collection responses")
                response = await self._handle_log_analysis_info_responses(
                    clarification_responses, message, session_id, on_event
                )
                self._add_response_to_history(response)
                return response

            # Handle log analysis fix confirmation (user typed e.g. "fix it")
            if self._pipeline_state == PipelineState.AWAITING_LOG_FIX_CONFIRMATION and not clarification_responses:
                if self._is_fix_confirmation(message):
                    logger.info("[SkillEditorAgent] User confirmed log analysis auto-fix")
                    response = await self._apply_log_analysis_fixes(
                        canvas_context, session_id, on_event
                    )
                    self._add_response_to_history(response)
                    return response
                else:
                    # User sent something else — treat as decline, reset to idle
                    logger.info("[SkillEditorAgent] User did not confirm fix, resetting to idle")
                    self._pipeline_state = PipelineState.IDLE
                    # Fall through to normal intent classification

            # Handle node configuration clarification responses
            if clarification_responses and self._pipeline_state == PipelineState.CONFIGURING_NODE:
                logger.info("[SkillEditorAgent] Processing node config clarification responses")
                return await self._handle_node_config_clarification(
                    clarification_responses, canvas_context, session_id, on_event
                )
            
            # Handle requirement collection responses (domain QA stage)
            if clarification_responses and self._pipeline_state == PipelineState.COLLECTING_REQUIREMENTS:
                logger.info("[SkillEditorAgent] Processing requirement collection responses")
                response = await self._handle_requirement_responses(
                    clarification_responses, canvas_context, session_id, on_event
                )
                self._add_response_to_history(response)
                return response

            # Handle clarification responses
            if clarification_responses and self._pipeline_state == PipelineState.AWAITING_CLARIFICATION:
                logger.info("[SkillEditorAgent] Processing clarification responses")
                return await self._handle_clarification_response(
                    clarification_responses, canvas_context, session_id, on_event
                )

            # Handle workflow description review (user approve / modify)
            if self._pipeline_state == PipelineState.REVIEWING_WORKFLOW_DESCRIPTION:
                logger.info("[SkillEditorAgent] Handling workflow description response")
                response = await self._handle_workflow_description_response(
                    message, canvas_context, session_id, on_event
                )
                self._add_response_to_history(response)
                return response
            
            # Handle plan approval
            if self._pipeline_state == PipelineState.AWAITING_PLAN_APPROVAL:
                # Check for explicit approval - message should be short and contain approval words
                # This prevents false positives like "before we proceed, I want to clarify..."
                msg_lower = message.lower().strip()
                msg_words = msg_lower.split()

                if self._is_casual_chat_message(message):
                    response = AgentResponse(
                        message=t("casual_chat_awaiting_approval", self._user_lang),
                        intent=IntentType.CASUAL_CHAT,
                        metadata={"session_id": session_id, "state": self._pipeline_state.value, "awaiting_plan_approval": True},
                    )
                    self._add_response_to_history(response)
                    return response
                
                # Approval: short message (<=10 words) that starts with or is an approval phrase
                approval_phrases = ["yes", "ok", "okay", "approve", "proceed", "do it", "do them", "go ahead", "let's go", "sounds good", "looks good", "go for it", "是", "好", "好的", "可以", "确认", "执行", "继续", "没问题", "同意", "通过"]
                is_short_message = len(msg_words) <= 10
                starts_with_approval = any(msg_lower.startswith(phrase) for phrase in approval_phrases)
                is_approval_only = msg_lower in approval_phrases or msg_lower.rstrip('.!') in approval_phrases
                
                # Rejection: short message that starts with or is a rejection phrase
                rejection_phrases = ["no", "cancel", "revise", "change", "wait", "hold on", "stop", "not yet", "不", "不要", "取消", "停", "等等", "修改", "重来", "不行"]
                starts_with_rejection = any(msg_lower.startswith(phrase) for phrase in rejection_phrases)
                is_rejection_only = msg_lower in rejection_phrases or msg_lower.rstrip('.!') in rejection_phrases
                
                if is_approval_only or (is_short_message and starts_with_approval):
                    # If the pending plan is an edit proposal, apply the edit (do not generate a new flowgram).
                    if self._is_edit_plan(self._current_plan):
                        logger.info("[SkillEditorAgent] Edit plan approved, applying edit")
                        try:
                            edit_request = self._current_request or ""
                            self._current_plan = None
                            return await self._run_code_generation(
                                message=edit_request,
                                canvas_context=canvas_context,
                                session_id=session_id,
                                intent=IntentType.MODIFY_NODE,
                                on_event=on_event,
                            )
                        finally:
                            self._current_plan = None
                    logger.info("[SkillEditorAgent] Plan approved, proceeding to code generation")
                    try:
                        return await self._generate_from_plan(canvas_context, session_id, on_event)
                    finally:
                        self._current_plan = None
                elif is_rejection_only or (is_short_message and starts_with_rejection):
                    logger.info("[SkillEditorAgent] Plan rejected, resetting")
                    self._pipeline_state = PipelineState.IDLE
                    is_edit_plan = self._is_edit_plan(self._current_plan)
                    self._current_plan = None
                    return AgentResponse(
                        message=(t("plan_rejected_edit", self._user_lang) if is_edit_plan else t("plan_rejected_create", self._user_lang)),
                        intent=IntentType.GENERAL_CHAT,
                        metadata={"session_id": session_id}
                    )
                # If message is longer and doesn't clearly approve/reject, treat as feedback on the plan
                # Reset state and process as a new request that may modify the plan
                else:
                    logger.info("[SkillEditorAgent] Received feedback on plan, treating as revision request")
                    self._pipeline_state = PipelineState.IDLE
                    # Don't clear the plan - let the user's feedback be processed
                    # Fall through to normal intent classification
            
            # Classify intent
            await self._emit_progress(on_event, t("progress_classifying", self._user_lang))
            intent = self._classify_intent_simple(message)

            # If the user returns to work-related actions, reset the casual chat counter.
            if intent != IntentType.CASUAL_CHAT:
                session_key = session_id or "default"
                if session_key in self._casual_chat_rounds_by_session:
                    self._casual_chat_rounds_by_session[session_key] = 0

            if intent == IntentType.GENERAL_CHAT:
                tax_intent, domain, confidence, reasoning = await self._classify_with_taxonomy(message, canvas_context)
                logger.info(
                    f"[SkillEditorAgent] Taxonomy classification: {tax_intent.value} domain={domain} "
                    f"(confidence={confidence:.2f}) reasoning={reasoning[:120]}"
                )
                self._classified_intent_taxonomy = tax_intent.value
                self._classified_domain = domain

                has_canvas = self._has_loaded_canvas(canvas_context)
                if has_canvas:
                    # When the user has a workflow loaded, low-confidence "create"
                    # results are more likely edit intent (user is talking about
                    # their loaded workflow, not asking for a brand new one).
                    if tax_intent == IntentType.CREATE_FLOWGRAM and confidence < 0.50:
                        tax_intent = IntentType.MODIFY_NODE
                    elif tax_intent == IntentType.GENERAL_CHAT and confidence < 0.5:
                        tax_intent = IntentType.MODIFY_NODE

                # Accept the LLM classification when it's specific enough
                if tax_intent != IntentType.GENERAL_CHAT and confidence >= 0.4:
                    intent = tax_intent
                elif has_canvas and tax_intent == IntentType.MODIFY_NODE:
                    intent = IntentType.MODIFY_NODE

            # When the simple classifier already detected CREATE_FLOWGRAM we still
            # need a domain to guide requirement collection.  Use a fast keyword
            # heuristic first; only call the expensive taxonomy LLM when no
            # domain can be inferred from keywords.
            if intent == IntentType.CREATE_FLOWGRAM and not self._classified_domain:
                domain = self._infer_domain_fast(message)
                if domain:
                    self._classified_domain = domain
                    logger.info(f"[SkillEditorAgent] Domain inferred via keywords: {domain}")
                else:
                    _, domain, _, _ = await self._classify_with_taxonomy(message, canvas_context)
                    self._classified_domain = domain
                    logger.info(f"[SkillEditorAgent] Domain derived via taxonomy: {domain}")

            logger.info(f"[SkillEditorAgent] Classified intent: {intent.value}")

            if intent == IntentType.CASUAL_CHAT:
                self._pipeline_state = PipelineState.IDLE
                response = self._handle_casual_chat(message, session_id)
                self._add_response_to_history(response)
                return response

            if intent == IntentType.ANALYZE_LOG:
                response = await self._run_analyze_log(message, session_id, on_event)
                self._add_response_to_history(response)
                return response

            if intent == IntentType.EXPLAIN:
                response = await self._run_explain(message, canvas_context, session_id, on_event)
                self._add_response_to_history(response)
                return response

            if intent == IntentType.MULTI_AGENT_DESIGN:
                response = await self._run_multi_agent_design(message, canvas_context, session_id, on_event)
                self._add_response_to_history(response)
                return response

            if intent == IntentType.CREATE_FLOWGRAM:
                # --- NEW PIPELINE: taxonomy → requirement collection → workflow description → planner ---
                self._current_request = message
                response = await self._run_requirement_collection(
                    message, canvas_context, session_id, on_event
                )
                self._add_response_to_history(response)
                return response

            if intent in [IntentType.ADD_NODE, IntentType.REMOVE_NODE, IntentType.MODIFY_NODE, IntentType.CONNECT_NODES]:
                await self._emit_progress(on_event, t("progress_preparing_modify", self._user_lang))
            
            # Store current request
            self._current_request = message

            # Safe edit mode: never run an LLM edit for vague modification messages.
            has_canvas = self._has_loaded_canvas(canvas_context)
            if intent in [IntentType.ADD_NODE, IntentType.REMOVE_NODE, IntentType.MODIFY_NODE, IntentType.CONNECT_NODES] and has_canvas:
                if self._is_vague_edit_request(message):
                    self._pipeline_state = PipelineState.IDLE
                    return AgentResponse(
                        message=t("vague_edit_request", self._user_lang),
                        intent=IntentType.GENERAL_CHAT,
                        metadata={"session_id": session_id, "state": "idle", "needs_edit_details": True},
                    )

            # Edit confirmation gate: propose an edit plan, then wait for explicit approval.
            if self._should_require_edit_confirmation(intent, message, canvas_context):
                await self._emit_progress(on_event, t("progress_waiting_confirmation", self._user_lang))

                items = [p.strip() for p in re.split(r"(?:\n+|;)+", (message or "").strip()) if p.strip()]
                if not items:
                    items = [message.strip()]

                plan = ImplementationPlan(
                    summary=f"Edit: {items[0]}",
                    steps=[
                        PlanStep(
                            title=("Apply requested modification to current workflow" if len(items) == 1 else f"Apply edit item {idx + 1}"),
                            description=item,
                            node_types=[],
                        )
                        for idx, item in enumerate(items)
                    ],
                    estimated_nodes=[],
                    complexity="simple",
                )

                self._pipeline_state = PipelineState.AWAITING_PLAN_APPROVAL
                self._current_plan = plan
                plan_text = self._format_plan_for_display(plan)
                return AgentResponse(
                    message=t("edit_confirmation", self._user_lang, plan_text=plan_text),
                    intent=IntentType.MODIFY_NODE,
                    plan=plan,
                    metadata={"session_id": session_id, "state": "awaiting_plan_approval", "edit_confirmation": True},
                )
            
            # Handle LOAD_SKILL intent directly
            if intent == IntentType.LOAD_SKILL:
                return await self._run_load_skill(message, session_id, on_event)
            
            # Handle SAVE_SKILL intent directly
            if intent == IntentType.SAVE_SKILL:
                return await self._run_save_skill(message, canvas_context, session_id, on_event)
            
            # Handle TEST_SKILL intent
            if intent == IntentType.TEST_SKILL:
                return await self._run_test_skill(message, canvas_context, session_id, on_event)
            
            # Handle DEPLOY_SKILL intent
            if intent == IntentType.DEPLOY_SKILL:
                return await self._run_deploy_skill(message, canvas_context, session_id, on_event)
            
            # Check if user wants to configure a specific node
            if intent == IntentType.MODIFY_NODE and self._is_node_config_request(message, canvas_context):
                response = await self._run_node_configuration(message, canvas_context, session_id, on_event)
                self._add_response_to_history(response)
                return response
            
            # Decide whether to use planner or go directly to code
            if self._should_use_planner(intent, canvas_context):
                # For GENERAL_CHAT on an empty canvas, route through the new
                # requirement-collection pipeline (domain-specific QA → workflow
                # description → planner) instead of the old planner-only path
                # that generates only 3 generic questions.
                # NOTE: use nodes-only check (not _has_loaded_canvas which also
                # considers skillName — the frontend may send skillName even when
                # the canvas has zero nodes, which would incorrectly skip this).
                canvas_nodes = (canvas_context or {}).get("nodes")
                has_real_nodes = isinstance(canvas_nodes, list) and len(canvas_nodes) > 0
                if intent == IntentType.GENERAL_CHAT and not has_real_nodes:
                    logger.info(
                        "[SkillEditorAgent] GENERAL_CHAT + empty canvas → routing "
                        "through requirement collection pipeline (domain QA)"
                    )
                    self._current_request = message
                    response = await self._run_requirement_collection(
                        message, canvas_context, session_id, on_event
                    )
                    self._add_response_to_history(response)
                    return response
                response = await self._run_planning_phase(
                    message=message,
                    canvas_context=canvas_context,
                    session_id=session_id,
                    on_event=on_event,
                    intent=intent,
                )
                self._add_response_to_history(response)
                return response
            else:
                # For simpler intents, go directly to code agent
                response = await self._run_code_generation(message, canvas_context, session_id, intent, on_event)
                self._add_response_to_history(response)
                return response
            
        except Exception as e:
            error_msg = f"I encountered an error processing your request: {str(e)}"
            logger.error(f"[SkillEditorAgent] Error: {e}\n{traceback.format_exc()}")
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=error_msg,
                intent=IntentType.UNKNOWN,
                metadata={"error": str(e), "session_id": session_id}
            )
        finally:
            try:
                if session_id:
                    skill_dir_to_persist = self._infer_skill_dir_name(canvas_context) or self._infer_skill_dir_name_from_current_flowgram()
                    if skill_dir_to_persist:
                        self._persist_conversation_history(skill_dir_to_persist, session_id)
            except Exception:
                pass
    
    async def _run_load_skill(
        self,
        message: str,
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Load an existing skill into the canvas"""
        logger.info(f"[SkillEditorAgent] Loading skill from message: {message}")
        
        # Extract skill name from message
        skill_name = self._extract_skill_name(message)
        
        if not skill_name:
            return AgentResponse(
                message=t("load_skill_no_name", self._user_lang),
                intent=IntentType.LOAD_SKILL,
                metadata={"session_id": session_id}
            )
        
        # Check if skill exists on disk
        if not skill_name.endswith("_skill"):
            skill_dir_name = f"{skill_name}_skill"
        else:
            skill_dir_name = skill_name
            skill_name = skill_name.replace("_skill", "")
        
        skill_root_uri = self._get_skill_root_uri(skill_dir_name)
        logger.info(f"[SkillEditorAgent] Looking for skill at: {skill_root_uri}")
        
        if not self._skill_exists(skill_dir_name):
            # List available skills
            available_skills = self._list_available_skills()
            skills_list = ", ".join(available_skills[:10]) if available_skills else "none found"
            return AgentResponse(
                message=t("load_skill_not_found", self._user_lang, skill_name=skill_name, skills_list=skills_list),
                intent=IntentType.LOAD_SKILL,
                metadata={"session_id": session_id, "available_skills": available_skills}
            )
        
        # Load the flowgram from disk
        flowgram = self._load_flowgram_from_disk(skill_name)
        
        if not flowgram:
            return AgentResponse(
                message=t("load_skill_corrupted", self._user_lang, skill_name=skill_name),
                intent=IntentType.LOAD_SKILL,
                metadata={"session_id": session_id}
            )
        
        # Set as current flowgram
        self.code_agent.set_current_flowgram(flowgram)

        if session_id:
            self._restore_conversation_history(skill_dir_name, session_id)
        
        # Send canvas.load_flowgram command
        commands = [CanvasCommand(
            type="canvas.load_flowgram",
            payload={
                "skillPath": str(skill_root_uri),
                "skillName": skill_dir_name
            }
        )]
        
        node_count = len(flowgram.nodes)
        edge_count = len(flowgram.edges)
        
        logger.info(f"[SkillEditorAgent] Loaded skill '{skill_name}' with {node_count} nodes, {edge_count} edges")
        
        return AgentResponse(
            message=t("load_skill_success", self._user_lang, skill_name=skill_name, node_count=node_count, edge_count=edge_count),
            commands=commands,
            intent=IntentType.LOAD_SKILL,
            flowgram=flowgram,
            metadata={"session_id": session_id, "skillPath": str(skill_root_uri)}
        )
    
    async def _run_save_skill(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Save the current workflow to disk"""
        logger.info(f"[SkillEditorAgent] Saving skill from message: {message}")
        
        # Try to get flowgram from canvas context or current flowgram
        flowgram = self._canvas_context_to_flowgram(canvas_context)
        
        if not flowgram:
            flowgram = self.code_agent.get_current_flowgram()
        
        if not flowgram:
            return AgentResponse(
                message=t("save_no_workflow", self._user_lang),
                intent=IntentType.SAVE_SKILL,
                metadata={"session_id": session_id}
            )
        
        # Check if user wants to save with a new name (save as)
        new_skill_name = self._extract_save_as_name(message)
        if new_skill_name:
            # Update metadata with new name
            if flowgram.metadata:
                flowgram.metadata["skillName"] = new_skill_name
            else:
                flowgram.metadata = {"skillName": new_skill_name}
        
        # Dual-write to disk (skill + bundle)
        skill_path = self._save_flowgram_to_disk(flowgram)
        
        if not skill_path:
            return AgentResponse(
                message=t("save_failed", self._user_lang),
                intent=IntentType.SAVE_SKILL,
                metadata={"session_id": session_id}
            )
        
        skill_name = flowgram.metadata.get("skillName", "skill") if flowgram.metadata else "skill"
        node_count = len(flowgram.nodes)
        edge_count = len(flowgram.edges)
        
        logger.info(f"[SkillEditorAgent] Saved skill '{skill_name}' to {skill_path}")
        
        return AgentResponse(
            message=t("save_skill_success", self._user_lang, skill_name=skill_name, node_count=node_count, edge_count=edge_count, skill_path=skill_path),
            intent=IntentType.SAVE_SKILL,
            flowgram=flowgram,
            metadata={"session_id": session_id, "skillPath": skill_path}
        )
    
    def _extract_save_as_name(self, message: str) -> Optional[str]:
        """Extract new skill name from a 'save as' message"""
        import re
        
        msg_lower = message.lower()
        
        # Patterns for "save as X", "save skill as X", "export as X"
        patterns = [
            r"(?:save|export)\s+(?:skill\s+)?as\s+([a-zA-Z0-9_-]+)",
            r"(?:save|export)\s+(?:to|as)\s+([a-zA-Z0-9_-]+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_skill_name(self, message: str) -> Optional[str]:
        """Extract skill name from a load skill message"""
        import re
        
        msg_lower = message.lower()
        
        # Common patterns: "load ebay000 skill", "open the ebay000 skill", "load up ebay000"
        patterns = [
            r"(?:load|open|switch to|load up)\s+(?:the\s+)?([a-zA-Z0-9_-]+?)(?:\s+skill)?(?:\s|$)",
            r"skill\s+([a-zA-Z0-9_-]+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                skill_name = match.group(1).strip()
                # Filter out common words that aren't skill names
                if skill_name not in ["the", "a", "an", "my", "this", "that", "up"]:
                    return skill_name
        
        return None
    
    async def _run_node_configuration(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Run node configuration with NodeConfigAgent"""
        logger.info("[SkillEditorAgent] Running node configuration")
        self._pipeline_state = PipelineState.CONFIGURING_NODE
        
        # Get the selected node
        selected_node = self._get_selected_node_from_context(canvas_context)
        if not selected_node:
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=t("node_config_select_first", self._user_lang),
                intent=IntentType.MODIFY_NODE,
                metadata={"session_id": session_id}
            )
        
        self._selected_node = selected_node
        node_id = selected_node.get("id", "")
        node_type = selected_node.get("type", "")
        current_config = selected_node.get("config", {}).get("inputsValues", {})
        
        logger.info(f"[SkillEditorAgent] Configuring node {node_id} of type {node_type}")
        
        # Run node config agent
        config_output = await self.node_config_agent.configure_node(
            node_id=node_id,
            node_type=node_type,
            user_request=message,
            current_config=current_config,
            available_context=canvas_context
        )
        
        if config_output.action == NodeConfigAction.ASK_CLARIFICATION:
            # Need clarification
            self._pending_clarification = config_output.clarification
            return AgentResponse(
                message=config_output.message,
                intent=IntentType.MODIFY_NODE,
                clarification=config_output.clarification,
                metadata={"session_id": session_id, "state": "configuring_node", "node_id": node_id}
            )
        
        elif config_output.action == NodeConfigAction.REJECT:
            self._pipeline_state = PipelineState.IDLE
            self._selected_node = None
            return AgentResponse(
                message=config_output.message,
                intent=IntentType.MODIFY_NODE,
                metadata={"session_id": session_id}
            )
        
        else:  # CONFIGURE or VALIDATE
            self._pipeline_state = PipelineState.COMPLETE
            self._selected_node = None
            
            commands = [CanvasCommand(type=c.type, payload=c.payload) for c in config_output.commands]
            
            return AgentResponse(
                message=config_output.message,
                commands=commands,
                intent=IntentType.MODIFY_NODE,
                validation=config_output.validation,
                metadata={"session_id": session_id, "state": "complete", "node_config": config_output.node_config}
            )
    
    async def _handle_node_config_clarification(
        self,
        responses: Dict[str, List[str]],
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Handle clarification responses for node configuration"""
        logger.info("[SkillEditorAgent] Handling node config clarification response")
        
        if not self._selected_node:
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=t("node_config_lost_track", self._user_lang),
                intent=IntentType.MODIFY_NODE,
                metadata={"session_id": session_id}
            )
        
        node_id = self._selected_node.get("id", "")
        node_type = self._selected_node.get("type", "")
        current_config = self._selected_node.get("config", {}).get("inputsValues", {})
        
        # Continue configuration with responses
        config_output = await self.node_config_agent.configure_node(
            node_id=node_id,
            node_type=node_type,
            user_request=self._current_request or "",
            current_config=current_config,
            clarification_responses=responses,
            available_context=canvas_context
        )
        
        if config_output.action == NodeConfigAction.ASK_CLARIFICATION:
            self._pending_clarification = config_output.clarification
            return AgentResponse(
                message=config_output.message,
                intent=IntentType.MODIFY_NODE,
                clarification=config_output.clarification,
                metadata={"session_id": session_id, "state": "configuring_node", "node_id": node_id}
            )
        
        else:
            self._pipeline_state = PipelineState.COMPLETE
            self._selected_node = None
            
            commands = [CanvasCommand(type=c.type, payload=c.payload) for c in config_output.commands]
            
            return AgentResponse(
                message=config_output.message,
                commands=commands,
                intent=IntentType.MODIFY_NODE,
                validation=config_output.validation,
                metadata={"session_id": session_id, "state": "complete", "node_config": config_output.node_config}
            )
    
    async def _run_planning_phase(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable],
        intent: IntentType,
    ) -> AgentResponse:
        """Run the planning phase with PlannerAgent"""
        logger.info("[SkillEditorAgent] Running planning phase")
        self._pipeline_state = PipelineState.PLANNING

        # Reset accumulated clarification state for a fresh planning run
        self._accumulated_clarification_answers = {}
        self._all_asked_questions = {}
        self._clarification_round = 0
        
        # Run planner with forced clarification policy when applicable
        require_clarification = self._should_require_clarification(message, intent)

        # When a domain has been classified, supply domain-specific QA instead of all domains
        domain_qa_override: Optional[str] = None
        if self._classified_domain and self._classified_domain not in ("need_info", "other"):
            domain_qa_override = prompt_store.get_domain_qa_for(self._classified_domain) or None

        planner_output = await self.planner.plan(
            user_message=message,
            canvas_context=canvas_context,
            on_event=on_event,
            require_clarification=require_clarification,
            domain_questions=domain_qa_override,
            tools_catalog=self.tools_catalog_text,
            user_lang=self._user_lang,
        )
        
        logger.info(f"[SkillEditorAgent] Planner action: {planner_output.action.value}")

        if planner_output.action == PlannerAction.RECOMMEND_MULTI_AGENT:
            # Planner determined requirements exceed a single workflow — pivot to architect advisor
            logger.info("[SkillEditorAgent] Planner recommended multi-agent design — pivoting to architect handler")
            self._pipeline_state = PipelineState.IDLE
            architect_response = await self._run_multi_agent_design(message, canvas_context, session_id, on_event)
            # Prepend the planner's reasoning as context so the architect response is coherent
            if planner_output.message:
                architect_response.message = planner_output.message + "\n\n" + architect_response.message
            return architect_response

        if planner_output.action == PlannerAction.ASK_CLARIFICATION:
            # Need clarification from user
            self._pipeline_state = PipelineState.AWAITING_CLARIFICATION
            self._pending_clarification = planner_output.questions
            # Track all asked questions for enrichment across rounds
            if planner_output.questions:
                for q in planner_output.questions:
                    self._all_asked_questions[q.id] = q
            
            return AgentResponse(
                message=planner_output.message or "I have some questions to better understand your requirements:",
                intent=IntentType.CREATE_FLOWGRAM,
                clarification=planner_output.questions,
                metadata={"session_id": session_id, "state": "awaiting_clarification"}
            )
        
        elif planner_output.action == PlannerAction.GENERATE_PLAN:
            # Plan generated, ask for approval
            self._pipeline_state = PipelineState.AWAITING_PLAN_APPROVAL
            self._current_plan = planner_output.plan
            
            # Format plan for display
            plan_text = self._format_plan_for_display(planner_output.plan)
            
            return AgentResponse(
                message=t("plan_present", self._user_lang, plan_message=planner_output.message or t("plan_present_default_header", self._user_lang), plan_text=plan_text),
                intent=IntentType.CREATE_FLOWGRAM,
                plan=planner_output.plan,
                metadata={"session_id": session_id, "state": "awaiting_plan_approval"}
            )
        
        else:  # PROCEED_TO_CODE
            # Request is clear enough, proceed directly
            return await self._generate_from_plan(canvas_context, session_id, on_event)
    
    def _build_enriched_request_with_answers(self) -> str:
        """Build a richer user_message that includes the original request plus
        all accumulated clarification answers so the planner/code-agent sees
        the full picture — not just the original (possibly trivial) message."""
        parts: List[str] = []
        base = (self._current_request or "").strip()
        if base:
            parts.append(f"Original user request: {base}")
        if self._accumulated_clarification_answers:
            qa_lines: List[str] = []
            q_map = self._all_asked_questions or {}
            for qid, answer_ids in self._accumulated_clarification_answers.items():
                q_obj = q_map.get(qid)
                q_text = q_obj.question if q_obj else qid
                # Resolve answer labels when possible
                labels: List[str] = []
                for aid in answer_ids:
                    if q_obj:
                        match = next((c for c in q_obj.choices if c.id == aid), None)
                        labels.append(match.label if match else aid)
                    else:
                        labels.append(aid)
                qa_lines.append(f"- {q_text}: {', '.join(labels)}")
            parts.append("User's answers to clarification questions:\n" + "\n".join(qa_lines))
        return "\n\n".join(parts) if parts else base

    async def _handle_clarification_response(
        self,
        responses: Dict[str, List[str]],
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Handle user's clarification responses"""
        logger.info("[SkillEditorAgent] Handling clarification response")

        # Accumulate answers across rounds
        for qid, answer_ids in responses.items():
            self._accumulated_clarification_answers[qid] = answer_ids
        self._clarification_round += 1
        logger.info(
            f"[SkillEditorAgent] Clarification round {self._clarification_round}, "
            f"accumulated {len(self._accumulated_clarification_answers)} answer(s)"
        )

        # Build enriched request that includes all accumulated answers
        enriched_request = self._build_enriched_request_with_answers()

        # Cap clarification rounds — if we've already asked enough, force plan generation
        force_plan = self._clarification_round >= self._MAX_CLARIFICATION_ROUNDS
        if force_plan:
            logger.info("[SkillEditorAgent] Max clarification rounds reached — forcing plan generation")

        # Continue planning with ALL accumulated responses
        planner_output = await self.planner.plan(
            user_message=enriched_request,
            canvas_context=canvas_context,
            clarification_responses=self._accumulated_clarification_answers,
            on_event=on_event,
            require_clarification=False,
            tools_catalog=self.tools_catalog_text,
            user_lang=self._user_lang,
        )
        
        if planner_output.action == PlannerAction.RECOMMEND_MULTI_AGENT:
            logger.info("[SkillEditorAgent] Planner (clarification phase) recommended multi-agent design — pivoting")
            self._pipeline_state = PipelineState.IDLE
            architect_response = await self._run_multi_agent_design(
                self._current_request or message, canvas_context, session_id, on_event
            )
            if planner_output.message:
                architect_response.message = planner_output.message + "\n\n" + architect_response.message
            return architect_response

        if planner_output.action == PlannerAction.ASK_CLARIFICATION and not force_plan:
            # More clarification needed
            self._pending_clarification = planner_output.questions
            # Track all asked questions for enrichment across rounds
            if planner_output.questions:
                for q in planner_output.questions:
                    self._all_asked_questions[q.id] = q
            return AgentResponse(
                message=planner_output.message or "I have a few more questions:",
                intent=IntentType.CREATE_FLOWGRAM,
                clarification=planner_output.questions,
                metadata={"session_id": session_id, "state": "awaiting_clarification"}
            )
        
        elif planner_output.action == PlannerAction.GENERATE_PLAN or force_plan:
            self._pipeline_state = PipelineState.AWAITING_PLAN_APPROVAL
            plan = planner_output.plan
            if not plan and force_plan:
                # Ask plannerAgent one final time with explicit instruction to produce a plan
                logger.info("[SkillEditorAgent] Force-generating plan after max rounds")
                planner_output2 = await self.planner.plan(
                    user_message=enriched_request,
                    canvas_context=canvas_context,
                    clarification_responses=self._accumulated_clarification_answers,
                    on_event=on_event,
                    require_clarification=False,
                    tools_catalog=self.tools_catalog_text,
                    user_lang=self._user_lang,
                )
                plan = planner_output2.plan
            self._current_plan = plan
            if plan:
                plan_text = self._format_plan_for_display(plan)
                return AgentResponse(
                    message=t("plan_from_answers", self._user_lang, plan_text=plan_text),
                    intent=IntentType.CREATE_FLOWGRAM,
                    plan=plan,
                    metadata={"session_id": session_id, "state": "awaiting_plan_approval"}
                )
            # Fallback: proceed directly to code generation with enriched context
            self._current_request = enriched_request
            return await self._generate_from_plan(canvas_context, session_id, on_event)
        
        else:
            # Update _current_request with enriched context so code gen has full picture
            self._current_request = enriched_request
            return await self._generate_from_plan(canvas_context, session_id, on_event)

    # ------------------------------------------------------------------
    # Domain-aware requirement collection  (NEW PIPELINE STAGES)
    # ------------------------------------------------------------------

    async def _run_requirement_collection(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """Start domain-specific requirement collection.

        First checks whether the request requires multi-agent design (concurrency /
        parallelism signals). If so, pivots immediately to the architect handler
        before asking any domain Q&A. Otherwise, proceeds with standard requirement
        collection → planner pipeline.
        """
        # Fast-path: detect obvious multi-agent requirements before going through Q&A
        if self._needs_multi_agent(message):
            logger.info(
                "[SkillEditorAgent] Multi-agent requirement detected in requirement collection — pivoting to architect handler"
            )
            return await self._run_multi_agent_design(message, canvas_context, session_id, on_event)

        domain = self._classified_domain or "need_info"
        logger.info(f"[SkillEditorAgent] Starting requirement collection for domain={domain}")
        self._pipeline_state = PipelineState.COLLECTING_REQUIREMENTS
        await self._emit_progress(on_event, t("progress_gathering_requirements", self._user_lang, domain=domain))

        domain_qa = prompt_store.get_domain_qa_for(domain) or ""
        req_collector_prompt = prompt_store.get("requirement_collector", default="")

        # Extract the Domain Definitions section from the taxonomy so the LLM
        # knows what business areas to probe for.
        taxonomy_text = prompt_store.get_taxonomy() or ""
        domain_defs_section = ""
        if taxonomy_text:
            import re as _re
            m = _re.search(r"(## Domain Definitions.*?)(?=\n## |\Z)", taxonomy_text, _re.DOTALL)
            if m:
                domain_defs_section = m.group(1).strip()

        prompt = (
            "You are a requirement collection assistant for the eCan.ai skill editor.\n\n"
            "## REQUIREMENT COLLECTOR INSTRUCTIONS\n"
            f"{req_collector_prompt}\n\n"
        )
        if domain_defs_section:
            prompt += (
                "## BUSINESS DOMAIN REFERENCE\n"
                "Use the following domain definitions to ask domain-relevant questions. "
                "Questions MUST probe the specific concerns of the classified domain.\n\n"
                f"{domain_defs_section}\n\n"
            )
        if domain_qa:
            prompt += (
                "## DOMAIN-SPECIFIC DECISION TREE (for this domain — FOLLOW THIS)\n"
                "You MUST use the questions in this decision tree as the **primary source** "
                "of your clarification questions. Convert each tree question into a "
                "multiple-choice question. Only add extra questions if the tree does not "
                "cover an important aspect of the user's request.\n\n"
                f"{domain_qa}\n\n"
            )
        prompt += (
            "## TASK\n"
            "The user wants to create a new workflow. Based on their message, the domain "
            "definitions, and the domain QA decision tree above, generate a JSON array of "
            "3-8 clarification questions to gather the most critical requirements. "
            "Each question should have multiple-choice options where possible.\n\n"
            "Return **JSON only** (no markdown fences) with this schema:\n"
            '[\n'
            '  {\n'
            '    "id": "q1",\n'
            '    "question": "question text",\n'
            '    "choices": [\n'
            '      {"id": "c1", "label": "Choice 1", "description": "optional detail"},\n'
            '      {"id": "c2", "label": "Choice 2"},\n'
            '      {"id": "other", "label": "Other", "allow_freeform": true}\n'
            '    ],\n'
            '    "context": "why this matters (optional)",\n'
            '    "allow_multiple": false\n'
            '  }\n'
            ']\n\n'
            "Guidelines:\n"
            "- **PRIORITY**: Convert the domain QA decision tree questions into the JSON format "
            "FIRST. These are the most important questions.\n"
            "- Then add any extra domain-specific questions the tree does not cover.\n"
            "- Propose reasonable defaults as first choices.\n"
            "- Keep questions concise and actionable.\n"
            "- Generate up to 8 questions — aim for completeness over brevity.\n"
            "- Set \"allow_multiple\": true when the user can reasonably select more than one option "
            "(e.g. trigger types, output destinations, notification channels).\n"
            "- ALWAYS include an 'Other' choice (with \"allow_freeform\": true) as the last option "
            "so the user can provide a custom answer.\n\n"
            f"classified_domain={domain}\n"
            f"user_message={json.dumps(message)}\n"
            f"{get_language_instruction(self._user_lang)}"
        )

        try:
            response = await self._invoke_llm_fast(prompt, action="requirement_collection")
            raw_questions = self._extract_json_from_text(response)
            if raw_questions is None:
                logger.warning(
                    "[SkillEditorAgent] Failed to parse requirement questions from LLM response "
                    "(first 500 chars): %s", (response or "")[:500]
                )
            if not isinstance(raw_questions, list):
                raw_questions = [raw_questions] if isinstance(raw_questions, dict) else []

            questions: List[ClarificationQuestion] = []
            for rq in raw_questions:
                if not isinstance(rq, dict):
                    continue
                choices = []
                for rc in (rq.get("choices") or []):
                    if isinstance(rc, dict) and rc.get("id") and rc.get("label"):
                        choices.append(ClarificationChoice(
                            id=str(rc["id"]),
                            label=str(rc["label"]),
                            description=rc.get("description"),
                            allow_freeform=bool(rc.get("allow_freeform", False)),
                        ))
                # Auto-tag "Other" choices with allow_freeform if LLM didn't
                for ch in choices:
                    if not ch.allow_freeform and (ch.id.lower() in ("other", "other_option") or ch.label.lower().startswith("other")):
                        ch.allow_freeform = True
                if not choices:
                    continue
                questions.append(ClarificationQuestion(
                    id=str(rq.get("id", f"q{len(questions)+1}")),
                    question=str(rq.get("question", "")),
                    choices=choices,
                    context=rq.get("context"),
                    allow_multiple=bool(rq.get("allow_multiple", False)),
                ))

            if not questions:
                # Fallback: skip requirement collection, go straight to workflow description
                logger.warning("[SkillEditorAgent] No clarification questions generated, skipping to workflow description")
                return await self._generate_workflow_description(message, canvas_context, session_id, on_event)

            self._pending_clarification = questions
            return AgentResponse(
                message=t("requirement_collection_intro", self._user_lang),
                intent=IntentType.CREATE_FLOWGRAM,
                clarification=questions,
                metadata={
                    "session_id": session_id,
                    "state": "collecting_requirements",
                    "domain": domain,
                },
            )
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Requirement collection failed: {e}")
            # Fallback: skip to workflow description
            return await self._generate_workflow_description(message, canvas_context, session_id, on_event)

    async def _handle_requirement_responses(
        self,
        responses: Dict[str, List[str]],
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """Process the user's answers to requirement questions.

        After the initial (generic) round, check whether domain-specific
        follow-up Q&A is available.  If so, run a second round of questions
        sourced from prompts/qa/{domain}.md before proceeding to the
        workflow description.
        """
        logger.info(f"[SkillEditorAgent] Handling requirement responses: {list(responses.keys())}")

        # Build a lookup from question_id → {choice_id → label} using
        # the pending clarification questions (restored from session state).
        q_text_map: Dict[str, str] = {}     # qid → question text
        choice_label_map: Dict[str, Dict[str, str]] = {}  # qid → {cid → label}
        if self._pending_clarification:
            for q in self._pending_clarification:
                q_text_map[q.id] = q.question
                choice_label_map[q.id] = {c.id: c.label for c in q.choices}

        # Merge freeform text into the corresponding question answers
        freeform_keys = [k for k in responses if k.startswith("freeform_")]
        for fk in freeform_keys:
            qid = fk[len("freeform_"):]
            freeform_text = (responses.pop(fk) or [""])[0]
            if freeform_text and qid in responses:
                # Replace generic "other" ID with the actual freeform text
                responses[qid] = [
                    f"other: {freeform_text}" if v.lower() in ("other", "other_option") else v
                    for v in responses[qid]
                ]

        # Merge answers into accumulated requirement_answers.
        # Store human-readable text (question text → list of choice labels)
        # so the workflow-description prompt is meaningful to the LLM.
        for qid, answer_ids in responses.items():
            q_label = q_text_map.get(qid, qid)
            resolved_labels = []
            cid_map = choice_label_map.get(qid, {})
            for aid in answer_ids:
                resolved_labels.append(cid_map.get(aid, aid))
            self._requirement_answers[q_label] = resolved_labels

        logger.info(f"[SkillEditorAgent] Resolved requirement answers: {self._requirement_answers}")

        # --- Domain-specific follow-up Q&A (second round) ---
        if not self._domain_qa_done:
            self._domain_qa_done = True  # mark so we don't loop a third time
            domain = self._classified_domain or "need_info"
            domain_qa = prompt_store.get_domain_qa_for(domain) or ""
            if domain_qa and domain not in ("need_info", "other"):
                logger.info(
                    f"[SkillEditorAgent] Domain QA available for '{domain}', "
                    "generating domain-specific follow-up questions"
                )
                return await self._run_domain_followup_qa(
                    domain, domain_qa, canvas_context, session_id, on_event
                )
            else:
                logger.info(
                    f"[SkillEditorAgent] No domain QA for '{domain}', "
                    "skipping to workflow description"
                )

        # Proceed to workflow description generation
        return await self._generate_workflow_description(
            self._current_request or "",
            canvas_context,
            session_id,
            on_event,
        )

    async def _run_domain_followup_qa(
        self,
        domain: str,
        domain_qa: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """Generate a second round of domain-specific clarification questions.

        Uses the domain QA decision tree (from ``prompts/qa/{domain}.md``) plus
        the answers already collected in the initial round to produce targeted
        follow-up questions.
        """
        await self._emit_progress(on_event, t("progress_asking_domain_questions", self._user_lang, domain=domain))

        # Build summary of answers collected so far
        answers_summary = ""
        if self._requirement_answers:
            parts = []
            for qid, vals in self._requirement_answers.items():
                parts.append(f"- {qid}: {', '.join(vals) if isinstance(vals, list) else str(vals)}")
            answers_summary = "\n".join(parts)

        prompt = (
            "You are a requirement collection assistant for the eCan.ai skill editor.\n\n"
            "## DOMAIN-SPECIFIC DECISION TREE\n"
            f"{domain_qa}\n\n"
        )
        if answers_summary:
            prompt += (
                "## ANSWERS ALREADY COLLECTED IN ROUND 1\n"
                f"{answers_summary}\n\n"
            )
        prompt += (
            "## TASK\n"
            "Based on the domain QA decision tree above and the answers the user has already "
            "provided, generate a focused set of **follow-up clarification questions** (3–8) "
            "that drill into domain-specific details not yet covered.\n\n"
            "Guidelines:\n"
            "- Do NOT re-ask questions whose answers are already captured above.\n"
            "- Follow the decision-tree branches that match the user's earlier answers.\n"
            "- Where the tree calls for sub-questions (e.g. Q4 → Q4.1 → Q4.1.1), include "
            "those sub-questions if the parent answer triggers them.\n"
            "- Offer multiple-choice options where sensible; always include an 'Other' freeform option.\n"
            "- Set \"allow_multiple\": true when the user can reasonably select more than one option.\n"
            "- Keep the set concise (3–8 questions max).\n\n"
            "Return **JSON only** (no markdown fences) matching this schema:\n"
            '[\n'
            '  {\n'
            '    "id": "dq1",\n'
            '    "question": "question text",\n'
            '    "choices": [\n'
            '      {"id": "c1", "label": "Choice 1", "description": "optional detail"},\n'
            '      {"id": "other", "label": "Other", "allow_freeform": true}\n'
            '    ],\n'
            '    "context": "why this matters (optional)",\n'
            '    "allow_multiple": false\n'
            '  }\n'
            ']\n\n'
            f"classified_domain={domain}\n"
            f"user_message={json.dumps(self._current_request or '')}\n"
            f"{get_language_instruction(self._user_lang)}"
        )

        try:
            response = await self._invoke_llm_async(prompt, action="domain_followup_qa")
            raw_questions = self._extract_json_from_text(response)
            if raw_questions is None:
                logger.warning(
                    "[SkillEditorAgent] Failed to parse domain followup questions from LLM response "
                    "(first 500 chars): %s", (response or "")[:500]
                )
            if not isinstance(raw_questions, list):
                raw_questions = [raw_questions] if isinstance(raw_questions, dict) else []

            questions: List[ClarificationQuestion] = []
            for rq in raw_questions:
                if not isinstance(rq, dict):
                    continue
                choices = []
                for rc in (rq.get("choices") or []):
                    if isinstance(rc, dict) and rc.get("id") and rc.get("label"):
                        choices.append(ClarificationChoice(
                            id=str(rc["id"]),
                            label=str(rc["label"]),
                            description=rc.get("description"),
                            allow_freeform=bool(rc.get("allow_freeform", False)),
                        ))
                # Auto-tag "Other" choices with allow_freeform if LLM didn't
                for ch in choices:
                    if not ch.allow_freeform and (ch.id.lower() in ("other", "other_option") or ch.label.lower().startswith("other")):
                        ch.allow_freeform = True
                if not choices:
                    continue
                questions.append(ClarificationQuestion(
                    id=str(rq.get("id", f"dq{len(questions)+1}")),
                    question=str(rq.get("question", "")),
                    choices=choices,
                    context=rq.get("context"),
                    allow_multiple=bool(rq.get("allow_multiple", False)),
                ))

            if not questions:
                logger.info("[SkillEditorAgent] No domain follow-up questions generated, proceeding to workflow description")
                return await self._generate_workflow_description(
                    self._current_request or "", canvas_context, session_id, on_event
                )

            self._pending_clarification = questions
            return AgentResponse(
                message=t("domain_qa_intro", self._user_lang, domain=domain.replace("_", " ")),
                intent=IntentType.CREATE_FLOWGRAM,
                clarification=questions,
                metadata={
                    "session_id": session_id,
                    "state": "collecting_requirements",
                    "domain": domain,
                    "domain_qa_round": True,
                },
            )
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Domain follow-up QA failed: {e}")
            return await self._generate_workflow_description(
                self._current_request or "", canvas_context, session_id, on_event
            )

    async def _generate_workflow_description(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """Generate a natural-language workflow description for user approval.

        Uses SOP (if found for domain), the collected QA answers, and the user's
        original request to synthesise a workflow description.
        """
        domain = self._classified_domain or "need_info"
        logger.info(f"[SkillEditorAgent] Generating workflow description for domain={domain}")
        self._pipeline_state = PipelineState.REVIEWING_WORKFLOW_DESCRIPTION
        await self._emit_progress(on_event, t("progress_drafting_description", self._user_lang))

        sop_content = prompt_store.get_sop_for(domain) or ""
        domain_qa = prompt_store.get_domain_qa_for(domain) or ""

        # Build collected answers summary
        answers_summary = ""
        if self._requirement_answers:
            parts = []
            for qid, vals in self._requirement_answers.items():
                parts.append(f"- {qid}: {', '.join(vals) if isinstance(vals, list) else str(vals)}")
            answers_summary = "\n".join(parts)

        prompt = (
            "You are a workflow architect for the eCan.ai skill editor.\n\n"
            "## GOAL\n"
            "Produce a clear, detailed **natural-language description** of the workflow that "
            "will be built. The description should be understandable by a non-technical user "
            "so they can confirm or request changes before implementation begins.\n\n"
        )
        if sop_content:
            prompt += (
                "## STANDARD OPERATING PROCEDURE (SOP) FOR THIS DOMAIN\n"
                "Follow this SOP closely when designing the workflow steps:\n\n"
                f"{sop_content}\n\n"
            )
        if domain_qa:
            prompt += (
                "## DOMAIN Q&A REFERENCE\n"
                f"{domain_qa}\n\n"
            )
        if answers_summary:
            prompt += (
                "## USER'S ANSWERS TO REQUIREMENT QUESTIONS\n"
                f"{answers_summary}\n\n"
            )
        prompt += (
            "## FORMAT\n"
            "Return a response in this structure (plain text, no JSON):\n\n"
            "**Skill Name**: <suggested name>\n\n"
            "**Summary**: <1-2 sentence overview>\n\n"
            "**Workflow Steps**:\n"
            "1. <Step name> — <what this step does>\n"
            "2. …\n\n"
            "**Branches / Conditions** (if any):\n"
            "- After step N: if <condition> then <A>, else <B>\n\n"
            "**Inputs**: <what triggers the workflow and what data it needs>\n\n"
            "**Outputs**: <what the workflow produces>\n\n"
            f"classified_domain={domain}\n"
            f"user_message={json.dumps(message)}\n"
            f"{get_language_instruction(self._user_lang)}"
        )

        try:
            response = await self._invoke_llm_async(prompt, action="generate_workflow_description")
            self._workflow_description = response.strip()
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Workflow description generation failed: {e}")
            self._workflow_description = (
                f"(Auto-generation failed — proceeding with original request.)\n\n{message}"
            )

        return AgentResponse(
            message=t("workflow_description_review", self._user_lang, description=self._workflow_description),
            intent=IntentType.CREATE_FLOWGRAM,
            metadata={
                "session_id": session_id,
                "state": "reviewing_workflow_description",
                "domain": domain,
            },
        )

    async def _handle_workflow_description_response(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable],
    ) -> AgentResponse:
        """Handle user's response to the workflow description (approve / modify)."""
        msg_lower = message.lower().strip()
        msg_words = msg_lower.split()

        approval_phrases = [
            "yes", "ok", "okay", "approve", "proceed", "do it", "go ahead",
            "let's go", "sounds good", "looks good", "go for it", "confirmed",
            "confirm", "build it", "let's build",
            "是", "好", "好的", "可以", "确认", "执行", "继续", "没问题", "同意", "通过", "开始构建",
        ]
        rejection_phrases = [
            "no", "cancel", "stop", "start over", "restart", "never mind",
            "start fresh", "start afresh", "from scratch",
            "不", "不要", "取消", "停", "重来", "重新开始", "从头开始",
        ]

        is_short = len(msg_words) <= 10
        is_approval = any(msg_lower.startswith(p) for p in approval_phrases) or msg_lower.rstrip(".!") in approval_phrases
        is_rejection = any(msg_lower.startswith(p) for p in rejection_phrases) or msg_lower.rstrip(".!") in rejection_phrases

        # Detect "start over" intent even in longer messages (e.g. "i'd like to start afresh build a new skill")
        restart_cues = ["start over", "start fresh", "start afresh", "from scratch", "new skill", "build a new", "create a new", "重新开始", "从头开始", "新技能", "创建新"]
        wants_restart = any(cue in msg_lower for cue in restart_cues)

        if is_short and is_rejection:
            # User cancelled — reset
            logger.info("[SkillEditorAgent] Workflow description rejected, resetting")
            self._pipeline_state = PipelineState.IDLE
            self._workflow_description = None
            self._requirement_answers = {}
            self._domain_qa_done = False
            self._classified_domain = None
            return AgentResponse(
                message=t("plan_rejected_start_over", self._user_lang),
                intent=IntentType.GENERAL_CHAT,
                metadata={"session_id": session_id},
            )

        if wants_restart and not is_approval:
            # User wants to abandon current workflow and start a brand new one.
            # Reset all pipeline state so the message is treated as a fresh request.
            logger.info("[SkillEditorAgent] Detected new-skill intent during workflow review, resetting and re-routing")
            self._pipeline_state = PipelineState.IDLE
            self._workflow_description = None
            self._requirement_answers = {}
            self._domain_qa_done = False
            self._classified_domain = None
            self._classified_intent_taxonomy = None
            self._current_request = message
            # Classify and route from scratch (replicate the CREATE_FLOWGRAM path)
            _, domain, _, _ = await self._classify_with_taxonomy(message, canvas_context)
            self._classified_domain = domain
            logger.info(f"[SkillEditorAgent] Re-classified domain for fresh start: {domain}")
            return await self._run_requirement_collection(
                message, canvas_context, session_id, on_event
            )

        if is_approval or (is_short and is_approval):
            # Approved — feed workflow description into planner
            logger.info("[SkillEditorAgent] Workflow description approved, proceeding to planner")
            await self._emit_progress(on_event, t("progress_approved_planning", self._user_lang))

            # Enrich the current request with the approved workflow description
            enriched_request = (
                f"## APPROVED WORKFLOW DESCRIPTION\n{self._workflow_description}\n\n"
                f"## ORIGINAL USER REQUEST\n{self._current_request or message}\n"
            )
            self._current_request = enriched_request

            # Proceed to planning phase (existing flow)
            return await self._run_planning_phase(
                message=enriched_request,
                canvas_context=canvas_context,
                session_id=session_id,
                on_event=on_event,
                intent=IntentType.CREATE_FLOWGRAM,
            )

        # User has modifications — regenerate description with their feedback
        logger.info("[SkillEditorAgent] User provided feedback on workflow description, regenerating")
        await self._emit_progress(on_event, t("progress_updating_description", self._user_lang))

        # Append feedback to context and regenerate
        feedback_message = (
            f"{self._current_request or ''}\n\n"
            f"## USER FEEDBACK ON PREVIOUS DESCRIPTION\n"
            f"Previous description:\n{self._workflow_description}\n\n"
            f"User's modification request: {message}\n"
        )
        return await self._generate_workflow_description(
            feedback_message, canvas_context, session_id, on_event,
        )

    def _canvas_context_to_flowgram(self, canvas_context: Optional[Dict]) -> Optional[Flowgram]:
        """
        Convert canvas context (from frontend) to a Flowgram object for editing.
        
        The canvas_context contains the current state of the canvas including nodes and edges.
        """
        logger.info(f"[SkillEditorAgent] _canvas_context_to_flowgram called with canvas_context: {canvas_context is not None}")
        if canvas_context:
            logger.info(f"[SkillEditorAgent] Canvas context keys: {list(canvas_context.keys())}")
        
        if not canvas_context:
            # Fallback: if we have a previously saved skill name, try loading from disk
            if self._last_saved_skill_name:
                logger.info(f"[SkillEditorAgent] No canvas context but have lastSavedSkillName={self._last_saved_skill_name}, loading from disk")
                loaded = self._load_flowgram_from_disk(self._last_saved_skill_name)
                if loaded:
                    return loaded
            # Fallback: use cached flowgram from session
            if self._cached_flowgram_dict:
                logger.info("[SkillEditorAgent] No canvas context, using cached flowgram dict as fallback")
                return self._flowgram_dict_to_flowgram(self._cached_flowgram_dict)
            logger.warning("[SkillEditorAgent] No canvas context provided for edit operation")
            return None
        
        try:
            nodes_data = canvas_context.get("nodes", [])
            edges_data = canvas_context.get("edges", [])
            logger.info(f"[SkillEditorAgent] Canvas context has {len(nodes_data)} nodes, {len(edges_data)} edges")
            
            if not nodes_data:
                # Try to load from disk if skill name is provided
                skill_name = canvas_context.get("skillName") or self._last_saved_skill_name
                if skill_name:
                    logger.info(f"[SkillEditorAgent] Canvas has no nodes but has skillName: {skill_name}, trying to load from disk")
                    loaded = self._load_flowgram_from_disk(skill_name)
                    if loaded:
                        return loaded
                # Fallback: use cached flowgram from last generation/edit (survives Lambda restarts)
                if self._cached_flowgram_dict:
                    logger.info("[SkillEditorAgent] Using cached flowgram dict as fallback (0 canvas nodes, disk load failed/skipped)")
                    return self._flowgram_dict_to_flowgram(self._cached_flowgram_dict)
                # Fallback: check if frontend sent lastFlowgramJson in canvas_context
                last_fj = canvas_context.get("lastFlowgramJson")
                if isinstance(last_fj, dict):
                    logger.info("[SkillEditorAgent] Using lastFlowgramJson from canvas_context as fallback")
                    return self._flowgram_dict_to_flowgram(last_fj)
                logger.warning("[SkillEditorAgent] Canvas context has no nodes and no skillName")
                return None
            
            # Convert nodes - handle both frontend schema (meta.position) and backend schema (position)
            nodes = []
            for n in nodes_data:
                nodes.append(self._parse_canvas_node(n, len(nodes)))
            
            # Convert edges - handle both frontend schema (sourceNodeID) and backend schema (source)
            edges = []
            for e in edges_data:
                source = e.get("sourceNodeID") or e.get("source", "")
                target = e.get("targetNodeID") or e.get("target", "")
                source_handle = e.get("sourcePortID") or e.get("sourceHandle") or e.get("source_handle")
                target_handle = e.get("targetPortID") or e.get("targetHandle") or e.get("target_handle")
                
                if source and target:
                    edges.append(FlowgramEdge(
                        source=source,
                        target=target,
                        source_handle=source_handle,
                        target_handle=target_handle
                    ))
            
            # Get metadata from canvas context
            metadata = canvas_context.get("metadata", {})
            if not metadata.get("skillName"):
                metadata["skillName"] = canvas_context.get("skillName") or "edited_skill"
            
            flowgram = Flowgram(
                nodes=nodes,
                edges=edges,
                metadata=metadata
            )
            
            logger.info(f"[SkillEditorAgent] Converted canvas context to flowgram: {len(nodes)} nodes, {len(edges)} edges")
            return flowgram
            
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Failed to convert canvas context to flowgram: {e}")
            return None

    def _flowgram_dict_to_flowgram(self, data: Dict[str, Any]) -> Optional[Flowgram]:
        """Convert a cached flowgram dict (Flowgram.model_dump() output) back to a Flowgram object."""
        try:
            return Flowgram.model_validate(data)
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Failed to restore flowgram from cached dict: {e}")
            return None
    
    def _parse_canvas_node(self, n: Dict[str, Any], index: int) -> FlowgramNode:
        """
        Parse a canvas node dict into FlowgramNode, handling loop nodes with blocks.
        Handles both frontend schema (meta.position, data.title) and backend schema (position, label).
        """
        node_id = n.get("id", f"node_{index}")
        node_type = n.get("type", "llm")
        
        # Get position from either meta.position or position
        pos = n.get("meta", {}).get("position") or n.get("position") or {"x": 100, "y": 100}
        
        # Get label from data.title or label
        label = n.get("data", {}).get("title") or n.get("label") or node_id
        
        # Get config from data or config
        config = n.get("data", {}) or n.get("config", {})
        
        # Handle loop nodes with blocks
        blocks = None
        internal_edges = None
        
        if node_type == "loop":
            # Parse blocks (internal nodes)
            blocks_data = n.get("blocks", []) or n.get("data", {}).get("blocks", [])
            if blocks_data:
                blocks = [self._parse_canvas_node(b, i) for i, b in enumerate(blocks_data)]
            
            # Parse internal edges
            internal_edges_data = (
                n.get("edges", [])
                or n.get("internal_edges", [])
                or n.get("data", {}).get("edges", [])
                or n.get("data", {}).get("internal_edges", [])
            )
            if internal_edges_data:
                internal_edges = [
                    FlowgramEdge(
                        source=e.get("sourceNodeID") or e.get("source", ""),
                        target=e.get("targetNodeID") or e.get("target", ""),
                        source_handle=e.get("sourcePortID") or e.get("sourceHandle") or e.get("source_handle"),
                        target_handle=e.get("targetPortID") or e.get("targetHandle") or e.get("target_handle"),
                    )
                    for e in internal_edges_data
                    if (e.get("sourceNodeID") or e.get("source")) and (e.get("targetNodeID") or e.get("target"))
                ]
        
        return FlowgramNode(
            id=node_id,
            type=node_type,
            label=label,
            position=NodePosition(x=pos.get("x", 100), y=pos.get("y", 100)),
            config=config,
            blocks=blocks,
            internal_edges=internal_edges
        )
    
    def _load_flowgram_from_disk(self, skill_name: str) -> Optional[Flowgram]:
        """
        Load a flowgram from disk given the skill name.
        
        Args:
            skill_name: Name of the skill (e.g., "ebay000")
            
        Returns:
            Flowgram object if found, None otherwise
        """
        try:
            if not skill_name.endswith("_skill"):
                skill_dir_name = f"{skill_name}_skill"
            else:
                skill_dir_name = skill_name
                skill_name = skill_name.replace("_skill", "")

            if _is_lambda_runtime():
                skill_root_uri = self._get_skill_root_uri(skill_dir_name)
                logger.info(f"[SkillEditorAgent] Loading flowgram from S3: {skill_root_uri}")
                skill_json = self._read_skill_json_from_s3(skill_dir_name)
                if not skill_json:
                    logger.warning(f"[SkillEditorAgent] Skill file not found in S3 for: {skill_dir_name}")
                    return None
            else:
                skill_file_path = user_skills_root() / skill_dir_name / "diagram_dir" / f"{skill_dir_name}.json"
                logger.info(f"[SkillEditorAgent] Loading flowgram from disk: {skill_file_path}")

                if not skill_file_path.exists():
                    logger.warning(f"[SkillEditorAgent] Skill file not found: {skill_file_path}")
                    return None

                with open(skill_file_path, 'r', encoding='utf-8') as f:
                    skill_json = json.load(f)
            
            # Extract workflow data
            workflow = skill_json.get("workFlow", {})
            nodes_data = workflow.get("nodes", [])
            edges_data = workflow.get("edges", [])
            
            if not nodes_data:
                logger.warning(f"[SkillEditorAgent] Skill file has no nodes: {skill_dir_name}")
                return None
            
            # Convert nodes - handle frontend schema (meta.position) and loop blocks
            nodes = []
            for n in nodes_data:
                nodes.append(self._parse_canvas_node(n, len(nodes)))
            
            # Convert edges - handle frontend schema (sourceNodeID/targetNodeID)
            edges = []
            for e in edges_data:
                source = e.get("sourceNodeID") or e.get("source", "")
                target = e.get("targetNodeID") or e.get("target", "")
                source_handle = e.get("sourcePortID") or e.get("sourceHandle")
                target_handle = e.get("targetPortID") or e.get("targetHandle")
                
                if source and target:
                    edges.append(FlowgramEdge(
                        source=source,
                        target=target,
                        source_handle=source_handle,
                        target_handle=target_handle
                    ))
            
            # Build metadata
            metadata = {
                "skillName": skill_name,
                "description": skill_json.get("description", ""),
            }
            
            flowgram = Flowgram(
                nodes=nodes,
                edges=edges,
                metadata=metadata
            )
            
            logger.info(f"[SkillEditorAgent] Loaded flowgram from disk: {len(nodes)} nodes, {len(edges)} edges")
            return flowgram
            
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Failed to load flowgram from disk: {e}")
            return None
    
    def _config_to_inputs_values(self, config: Dict[str, Any], node_type: str) -> Dict[str, Any]:
        """
        Convert simplified config format to proper inputsValues format for frontend.
        
        The frontend expects inputsValues with structure:
        {
            "fieldName": {
                "type": "constant" | "template",
                "content": value
            }
        }
        """
        inputs_values = {}
        
        # Fields that should use "template" type (can contain {{variable}} placeholders)
        template_fields = {
            "system_prompt", "systemPrompt", "user_prompt", "prompt", "task", 
            "message", "code", "url", "query_path"
        }
        # Fields that should not be emitted into inputsValues
        skip_fields = {"conditions", "blocks", "internal_edges", "inputs", "outputs", "code", "language", "breakpoint", "agentNote"}
        
        for key, value in config.items():
            # Skip special fields that aren't inputsValues
            if key in skip_fields:
                continue

            # promptSelection should serialize as an ID container without FlowValue 'type'
            # so the UI treats it as a prompt ID and resolves the title from the prompt store.
            if key == "promptSelection":
                if value is None:
                    continue
                if isinstance(value, dict) and "content" in value:
                    inputs_values[key] = {"content": value.get("content")}
                else:
                    inputs_values[key] = {"content": value}
                continue
            
            # If value is already in inputsValues format, keep it
            if isinstance(value, dict) and ("type" in value or "content" in value):
                inputs_values[key] = value
                continue
            
            # Convert to proper format
            value_type = "template" if key in template_fields else "constant"
            inputs_values[key] = {
                "type": value_type,
                "content": value
            }
        
        return inputs_values
    
    def _node_to_json(self, node: FlowgramNode) -> Dict[str, Any]:
        """Convert a FlowgramNode to JSON-serializable dict for skill file."""
        config = node.config or {}
        # Map internal to UI canonical types
        type_out = node.type
        if type_out == "browser_automation":
            type_out = "browser-automation"
        if type_out == "pend_event":
            type_out = "pend_event_node"
        if type_out == "mcp_tool":
            type_out = "mcp"

        if type_out == "llm":
            config.setdefault("temperature", 0.3)
            config.setdefault("useThinking", False)
        if type_out == "browser-automation":
            provider = config.get("provider")
            if provider and not config.get("tool"):
                config["tool"] = provider
            if "provider" in config:
                del config["provider"]
            config.setdefault("temperature", 0.3)
            config.setdefault("useThinking", False)
        
        # Handle condition nodes - ensure conditions array is present
        if node.type == "condition":
            if "conditions" not in config or not config.get("conditions"):
                config["conditions"] = [
                    {"key": f"if_{node.id[-5:]}", "value": {}},
                    {"key": f"else_{node.id[-5:]}", "value": {}},
                ]
        
        # Build the data object with proper inputsValues format
        data = {
            "title": getattr(node, "title", None) or node.label or node.id,
        }

        # Persist agent note if present
        agent_note = config.get("agentNote")
        if isinstance(agent_note, str) and agent_note.strip():
            data["agentNote"] = agent_note

        try:
            data["breakpoint"] = bool(config.get("breakpoint")) if isinstance(config.get("breakpoint"), bool) else False
        except Exception:
            data["breakpoint"] = False

        mcp_callable = None
        mcp_breakpoint = None
        if type_out == "mcp":
            try:
                if isinstance(config.get("callable"), dict):
                    mcp_callable = config.get("callable")
                elif isinstance(config.get("data"), dict) and isinstance((config.get("data") or {}).get("callable"), dict):
                    mcp_callable = (config.get("data") or {}).get("callable")
            except Exception:
                mcp_callable = None
            try:
                mcp_breakpoint = config.get("breakpoint") if isinstance(config, dict) else None
            except Exception:
                mcp_breakpoint = None
        
        # For nodes that use inputsValues format (llm, browser_automation, mcp_tool, etc.)
        if type_out in ["llm", "browser-automation", "mcp", "http", "code", "chat_node", "pend_event_node", "rag"]:
            # Convert config to inputsValues format
            config_for_inputs_values = config
            if type_out == "mcp" and isinstance(config, dict):
                config_for_inputs_values = {
                    k: v
                    for k, v in config.items()
                    if k not in {"callable", "breakpoint", "data", "tool_name", "tool_input"}
                }

            inputs_values = self._config_to_inputs_values(config_for_inputs_values, type_out)
            if inputs_values or type_out == "mcp":
                data["inputsValues"] = inputs_values

            if type_out == "mcp":
                if not isinstance(mcp_callable, dict):
                    mcp_callable = {
                        "id": "llm-auto-select",
                        "name": "llm auto select",
                        "desc": "Let the LLM automatically select the appropriate tool based on the context",
                        "params": {"type": "object", "properties": {}},
                        "returns": {"type": "object", "properties": {}},
                        "type": "system",
                        "source": "",
                    }
                data["data"] = {"callable": mcp_callable}
                data["breakpoint"] = bool(mcp_breakpoint) if isinstance(mcp_breakpoint, bool) else False
            
            # Also include inputs schema for frontend (typed where known)
            property_types = {}
            if type_out == "llm":
                property_types = {
                    "modelProvider": {"type": "string"},
                    "modelName": {"type": "string"},
                    "attachments": {"type": "object"},
                    "apiKey": {"type": "string"},
                    "apiHost": {"type": "string"},
                    "temperature": {"type": "number"},
                    "systemPrompt": {"type": "string"},
                    "prompt": {"type": "string"},
                    "promptSelection": {"type": "object", "properties": {}},
                }
            elif type_out == "browser-automation":
                property_types = {
                    "tool": {"type": "string"},
                    "browser": {"type": "string"},
                    "browserDriver": {"type": "string"},
                    "cdpPort": {"type": "string"},
                    "shopName": {"type": "string"},
                    "customShopName": {"type": "string"},
                    "modelProvider": {"type": "string"},
                    "modelName": {"type": "string"},
                    "temperature": {"type": "number"},
                    "useThinking": {"type": "boolean"},
                    "profile": {"type": "string"},
                    "systemPrompt": {"type": "string"},
                    "prompt": {"type": "string"},
                    "promptSelection": {"type": "object"},
                }
            data["inputs"] = {
                "type": "object",
                "properties": {
                    key: property_types.get(
                        key,
                        {"type": "string" if isinstance(val.get("content"), str) else "object"}
                    )
                    for key, val in inputs_values.items()
                }
            }
            
            # Include outputs schema
            data["outputs"] = {
                "type": "object",
                "properties": {
                    "result": {"type": "object", "description": "Node execution result"},
                    "condition": {"type": "boolean", "description": "Node execution condition"},
                    "resolved": {"type": "boolean", "description": "Node execution resolved status"},
                    "case": {"type": "string", "description": "Node execution case"}
                }
            }
            # Code node script
            if type_out == "code":
                data["script"] = {
                    "language": config.get("language", "python"),
                    "content": config.get("code", "")
                }
        else:
            # For simple nodes (start, end, condition, loop), just spread config
            # but filter out internal-only keys the UI doesn't need
            _internal_keys = {"breakpoint"}  # already set above
            data.update({k: v for k, v in config.items() if k not in _internal_keys})

            # Standard 4-field output schema for condition nodes
            if type_out == "condition":
                data.setdefault("outputs", {
                    "type": "object",
                    "properties": {
                        "result": {"type": "object", "description": "Node execution result"},
                        "condition": {"type": "boolean", "description": "Node execution condition"},
                        "resolved": {"type": "boolean", "description": "Node execution resolved status"},
                        "case": {"type": "string", "description": "Node execution case"},
                    },
                })

            # Start node: outputs describe the flow's input parameters
            if type_out == "start":
                data.setdefault("outputs", {"type": "object", "properties": {}})

            # End node: inputsValues, inputs schema, and nested data.data
            if type_out == "end":
                data.setdefault("inputsValues", {})
                data.setdefault("data", {"inputsValues": {}})
                data.setdefault("inputs", {"type": "object", "properties": {}})
        
        node_json = {
            "id": node.id,
            "type": type_out,
            "meta": {
                "position": {"x": node.position.x, "y": node.position.y} if node.position else {"x": 100, "y": 100}
            },
            "data": data,
        }
        
        # Handle loop nodes with blocks
        if node.type == "loop" and node.blocks:
            node_json["blocks"] = [self._node_to_json(block) for block in node.blocks]
            internal_edges = node.internal_edges or node.edges
            if internal_edges:
                node_json["edges"] = [
                    {
                        "sourceNodeID": e.source,
                        "targetNodeID": e.target,
                        **({"sourcePortID": e.source_handle} if e.source_handle is not None else {}),
                        **({"targetPortID": e.target_handle} if e.target_handle is not None else {}),
                    }
                    for e in internal_edges
                ]
        
        return node_json
    
    def _mirror_workflow_into_bundle(self, skill_json: Dict[str, Any], bundle_json: Dict[str, Any]) -> None:
        """
        Ensure bundle main sheet mirrors the current workFlow (nodes/edges).
        """
        now_ms = int(__import__("time").time() * 1000)
        main_sheet_id = bundle_json.get("mainSheetId") or bundle_json.get("main_sheet_id") or "main"
        bundle_json["mainSheetId"] = main_sheet_id
        bundle_json["activeSheetId"] = main_sheet_id
        if "openTabs" not in bundle_json or not bundle_json["openTabs"]:
            bundle_json["openTabs"] = [main_sheet_id]
        sheets = bundle_json.get("sheets", [])
        if not sheets:
            sheets = [{
                "id": main_sheet_id,
                "name": "Main",
                "document": skill_json["workFlow"],
                "createdAt": now_ms,
                "lastOpenedAt": now_ms,
            }]
        else:
            # Find main sheet, update or create
            found = False
            for s in sheets:
                if s.get("id") == main_sheet_id:
                    s["document"] = skill_json["workFlow"]
                    if "lastOpenedAt" in s:
                        s["lastOpenedAt"] = now_ms
                    found = True
                    break
            if not found:
                sheets.append({
                    "id": main_sheet_id,
                    "name": "Main",
                    "document": skill_json["workFlow"],
                    "createdAt": now_ms,
                    "lastOpenedAt": now_ms,
                })
        bundle_json["sheets"] = sheets

    def _write_skill_and_bundle(self, skill_json: Dict[str, Any], bundle_json: Dict[str, Any], skill_path: Path) -> None:
        """
        Persist both skill and bundle files, ensuring bundle main sheet mirrors workFlow.
        """
        try:
            # Mirror before write
            self._mirror_workflow_into_bundle(skill_json, bundle_json)
            # Skill file
            skill_path.write_text(json.dumps(skill_json, indent=2, ensure_ascii=False))
            # Bundle path
            bundle_path = skill_path.with_name(skill_path.stem + "_bundle.json")
            bundle_path.write_text(json.dumps(bundle_json, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Failed writing skill/bundle: {e}")

    def _write_skill_and_bundle_to_s3(self, skill_json: Dict[str, Any], bundle_json: Dict[str, Any], skill_dir_name: str, data_mapping: Optional[Dict[str, Any]] = None) -> None:
        try:
            self._mirror_workflow_into_bundle(skill_json, bundle_json)
            skill_key = self._s3_skill_json_key(skill_dir_name)
            bundle_key = self._s3_bundle_json_key(skill_dir_name)
            self._s3_put_json(skill_key, skill_json)
            self._s3_put_json(bundle_key, bundle_json)
            # Write data_mapping.json — always overwrite when caller supplies one,
            # otherwise create default if the file doesn't exist yet.
            dm_key = self._s3_data_mapping_key(skill_dir_name)
            if data_mapping:
                self._s3_put_json(dm_key, data_mapping)
            elif not self._s3_exists(dm_key):
                from agent.skill_editor.code_agent import DEFAULT_BASELINE_MAPPINGS
                self._s3_put_json(dm_key, DEFAULT_BASELINE_MAPPINGS)
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Failed writing skill/bundle to S3: {e}")

    def _save_flowgram_to_disk(self, flowgram: Flowgram, data_mapping: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Save a flowgram to disk (skill + bundle) ensuring dual-write and bundle mirroring.
        Works for both create and edit operations.

        If *data_mapping* is provided it is persisted as ``data_mapping.json``
        alongside the skill files.  When ``None`` the existing mapping is left
        untouched (or a baseline default is created if the file is missing).
        """
        try:
            original_metadata: Dict[str, Any] = dict(flowgram.metadata or {})

            # Normalize/fix connectivity before persisting so the saved JSON uses the real
            # condition port IDs (e.g., if_branch/else_branch) instead of hallucinated handles.
            try:
                from agent.skill_editor import get_validator_agent

                validator = get_validator_agent()
                fixed_dict = validator.fix_disconnected_nodes(flowgram.model_dump())
                flowgram = Flowgram.model_validate(fixed_dict)

                # Validator outputs may omit metadata; preserve original metadata (especially skillName).
                if not flowgram.metadata:
                    flowgram.metadata = dict(original_metadata)
                else:
                    for k, v in original_metadata.items():
                        if k not in flowgram.metadata:
                            flowgram.metadata[k] = v
            except Exception as e:
                logger.warning(f"[SkillEditorAgent] Validator fix before save failed: {e}")

            metadata = flowgram.metadata or {}
            skill_name = metadata.get("skillName") or metadata.get("name") or "generated_skill"
            self._last_saved_skill_name = skill_name
            description = metadata.get("description") or "Workflow generated via Skill Editor"
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()

            # Convert flowgram to JSON-serializable dict in UI shape
            default_config = {
                "skill_mapping": {"developing": "", "released": "", "event_data_mapping": ""},
                "nodes": {},
                "run_in_cloud": False,
            }
            saved_config = metadata.get("config")
            if isinstance(saved_config, dict):
                for k, v in saved_config.items():
                    default_config[k] = v

            skill_json = {
                "skillId": metadata.get("skillId", ""),
                "skillName": skill_name,
                "version": metadata.get("version", "1.0.0"),
                "lastModified": metadata.get("lastModified", now_iso),
                "workFlow": {
                    "nodes": [self._node_to_json(n) for n in flowgram.nodes],
                    "edges": [
                        {
                            "sourceNodeID": e.source,
                            "targetNodeID": e.target,
                            **({"sourcePortID": e.source_handle} if e.source_handle is not None else {}),
                            **({"targetPortID": e.target_handle} if e.target_handle is not None else {}),
                        }
                        for e in flowgram.edges
                        if e.source is not None and e.target is not None
                    ]
                },
                "mode": metadata.get("mode", "development"),
                "run_mode": metadata.get("run_mode", "developing"),
                "config": default_config,
                "schemaVersion": metadata.get("schemaVersion", "1.0.1"),
                "run_in_cloud": metadata.get("run_in_cloud", False),
                "hybrid_cloud_mode": metadata.get("hybrid_cloud_mode", False),
                "local_helper_skill_id": metadata.get("local_helper_skill_id", ""),
                "local_helper_machine": metadata.get("local_helper_machine", ""),
                "local_helper_skill_name": metadata.get("local_helper_skill_name", ""),
            }

            skill_dir_name = f"{skill_name}_skill"
            if _is_lambda_runtime():
                bundle_json: Dict[str, Any] = {
                    "mainSheetId": "main",
                    "activeSheetId": "main",
                    "openTabs": ["main"],
                    "sheets": [],
                }
                existing_bundle = self._read_bundle_json_from_s3(skill_dir_name)
                if isinstance(existing_bundle, dict) and existing_bundle:
                    bundle_json = existing_bundle
                self._write_skill_and_bundle_to_s3(skill_json, bundle_json, skill_dir_name, data_mapping=data_mapping)
                skill_root_uri = self._get_skill_root_uri(skill_dir_name)
                logger.info(f"[SkillEditorAgent] Saved flowgram to S3 (dual-write): {skill_root_uri}")
                return str(skill_root_uri)
            else:
                # Resolve skill directory paths
                skills_root = user_skills_root()
                skill_root = skills_root / skill_dir_name
                diagram_dir = skill_root / "diagram_dir"
                diagram_dir.mkdir(parents=True, exist_ok=True)
                skill_json_path = diagram_dir / f"{skill_dir_name}.json"
                bundle_path = diagram_dir / f"{skill_dir_name}_bundle.json"

                # Load existing bundle (if any), else default shell
                bundle_json: Dict[str, Any] = {
                    "mainSheetId": "main",
                    "activeSheetId": "main",
                    "openTabs": ["main"],
                    "sheets": [],
                }
                if bundle_path.exists():
                    try:
                        bundle_json = json.loads(bundle_path.read_text())
                    except Exception:
                        bundle_json = {
                            "mainSheetId": "main",
                            "activeSheetId": "main",
                            "openTabs": ["main"],
                            "sheets": [],
                        }

                # Dual-write skill + bundle with mirroring
                self._write_skill_and_bundle(skill_json, bundle_json, skill_json_path)

                # Write data_mapping.json
                dm_path = skill_root / "data_mapping.json"
                if data_mapping:
                    dm_path.write_text(json.dumps(data_mapping, indent=2, ensure_ascii=False))
                elif not dm_path.exists():
                    from agent.skill_editor.code_agent import DEFAULT_BASELINE_MAPPINGS
                    dm_path.write_text(json.dumps(DEFAULT_BASELINE_MAPPINGS, indent=2, ensure_ascii=False))

                logger.info(f"[SkillEditorAgent] Saved flowgram to disk (dual-write): {skill_json_path}")
                # Return skill root directory; frontend appends diagram_dir/<name>_skill.json
                return str(skill_root)
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Failed to save flowgram: {e}\n{traceback.format_exc()}")
            return None

    def _sync_existing_skill_bundle(self, skill_root: str, skill_name: str) -> None:
        """
        Given a skill root and name, load the skill JSON and bundle JSON, mirror workFlow into bundle main sheet,
        and persist both files.
        """
        try:
            if _is_lambda_runtime():
                skill_dir_name = f"{skill_name}_skill" if not skill_name.endswith("_skill") else skill_name
                skill_json = self._read_skill_json_from_s3(skill_dir_name)
                if not skill_json:
                    logger.warning(f"[SkillEditorAgent] Skill file not found for sync in S3: {skill_dir_name}")
                    return
                bundle_json = self._read_bundle_json_from_s3(skill_dir_name) or {}
            else:
                root_path = Path(skill_root)
                skill_json_path = root_path / "diagram_dir" / f"{skill_name}_skill.json"
                bundle_json_path = root_path / "diagram_dir" / f"{skill_name}_skill_bundle.json"
                if not skill_json_path.exists():
                    logger.warning(f"[SkillEditorAgent] Skill file not found for sync: {skill_json_path}")
                    return
                skill_json = json.loads(skill_json_path.read_text())
                bundle_json = {}
                if bundle_json_path.exists():
                    try:
                        bundle_json = json.loads(bundle_json_path.read_text())
                    except Exception:
                        bundle_json = {}
            # Ensure minimal bundle structure
            bundle_json.setdefault("mainSheetId", "main")
            bundle_json.setdefault("activeSheetId", "main")
            bundle_json.setdefault("openTabs", ["main"])
            bundle_json.setdefault("sheets", [])

            if _is_lambda_runtime():
                self._write_skill_and_bundle_to_s3(skill_json, bundle_json, skill_dir_name)
            else:
                self._write_skill_and_bundle(skill_json, bundle_json, skill_json_path)
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Failed to sync skill/bundle for {skill_root}: {e}")

    def _get_skill_root_uri(self, skill_dir_name: str) -> str:
        if _is_lambda_runtime():
            bucket, key_root = self._get_s3_bucket_and_root()
            prefix = _norm_s3_prefix(key_root)
            user_dir = _safe_user_dir_name(self._get_effective_username())
            parts = [p for p in [prefix, user_dir, "my_skills", skill_dir_name] if p]
            return f"s3://{bucket}/" + "/".join(parts)
        return str(user_skills_root() / skill_dir_name)

    def _get_s3_bucket_and_root(self) -> Tuple[str, str]:
        bucket = os.environ.get("S3_BUCKET")
        key_root = os.environ.get("S3_KEY_ROOT", "")
        if not bucket:
            raise ValueError("S3_BUCKET env var is required when running on Lambda")
        return bucket, key_root

    def _s3_client(self):
        import boto3

        return boto3.client("s3")

    def _s3_skill_json_key(self, skill_dir_name: str) -> str:
        bucket, key_root = self._get_s3_bucket_and_root()
        _ = bucket
        prefix = _norm_s3_prefix(key_root)
        user_dir = _safe_user_dir_name(self._get_effective_username())
        parts = [p for p in [prefix, user_dir, "my_skills", skill_dir_name, "diagram_dir", f"{skill_dir_name}.json"] if p]
        return "/".join(parts)

    def _s3_bundle_json_key(self, skill_dir_name: str) -> str:
        bucket, key_root = self._get_s3_bucket_and_root()
        _ = bucket
        prefix = _norm_s3_prefix(key_root)
        user_dir = _safe_user_dir_name(self._get_effective_username())
        parts = [p for p in [prefix, user_dir, "my_skills", skill_dir_name, "diagram_dir", f"{skill_dir_name}_bundle.json"] if p]
        return "/".join(parts)

    def _s3_data_mapping_key(self, skill_dir_name: str) -> str:
        bucket, key_root = self._get_s3_bucket_and_root()
        _ = bucket
        prefix = _norm_s3_prefix(key_root)
        user_dir = _safe_user_dir_name(self._get_effective_username())
        parts = [p for p in [prefix, user_dir, "my_skills", skill_dir_name, "data_mapping.json"] if p]
        return "/".join(parts)

    def _s3_put_json(self, key: str, payload: Dict[str, Any]) -> None:
        bucket, _ = self._get_s3_bucket_and_root()
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self._s3_client().put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")

    def _s3_get_json(self, key: str) -> Optional[Dict[str, Any]]:
        bucket, _ = self._get_s3_bucket_and_root()
        try:
            obj = self._s3_client().get_object(Bucket=bucket, Key=key)
            raw = obj["Body"].read()
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _s3_exists(self, key: str) -> bool:
        bucket, _ = self._get_s3_bucket_and_root()
        try:
            self._s3_client().head_object(Bucket=bucket, Key=key)
            return True
        except Exception:
            return False

    def _read_skill_json_from_s3(self, skill_dir_name: str) -> Optional[Dict[str, Any]]:
        return self._s3_get_json(self._s3_skill_json_key(skill_dir_name))

    def _read_bundle_json_from_s3(self, skill_dir_name: str) -> Optional[Dict[str, Any]]:
        return self._s3_get_json(self._s3_bundle_json_key(skill_dir_name))

    def _read_context_json_from_s3(self, skill_dir_name: str, session_id: str) -> Optional[Dict[str, Any]]:
        return self._s3_get_json(self._s3_context_json_key(skill_dir_name, session_id))

    def _write_context_json_to_s3(self, skill_dir_name: str, session_id: str, payload: Dict[str, Any]) -> None:
        self._s3_put_json(self._s3_context_json_key(skill_dir_name, session_id), payload)

    def _s3_context_json_key(self, skill_dir_name: str, session_id: str) -> str:
        bucket, key_root = self._get_s3_bucket_and_root()
        _ = bucket
        prefix = _norm_s3_prefix(key_root)
        user_dir = _safe_user_dir_name(self._get_effective_username())
        parts = [p for p in [prefix, user_dir, "my_skills", skill_dir_name, "contexts", f"{session_id}.json"] if p]
        return "/".join(parts)

    def _skill_exists(self, skill_dir_name: str) -> bool:
        if _is_lambda_runtime():
            return self._s3_exists(self._s3_skill_json_key(skill_dir_name))
        skill_path = user_skills_root() / skill_dir_name / "diagram_dir" / f"{skill_dir_name}.json"
        return skill_path.exists()

    def _list_available_skills(self) -> List[str]:
        if _is_lambda_runtime():
            bucket, key_root = self._get_s3_bucket_and_root()
            prefix = _norm_s3_prefix(key_root)
            user_dir = _safe_user_dir_name(self._get_effective_username())
            list_prefix = "/".join([p for p in [prefix, user_dir, "my_skills"] if p])
            if list_prefix:
                list_prefix = list_prefix + "/"
            try:
                resp = self._s3_client().list_objects_v2(Bucket=bucket, Prefix=list_prefix, Delimiter="/")
                dirs = [
                    cp.get("Prefix", "")
                    for cp in (resp.get("CommonPrefixes") or [])
                    if isinstance(cp, dict)
                ]
                out: List[str] = []
                for d in dirs:
                    d2 = d[len(list_prefix):] if d.startswith(list_prefix) else d
                    d2 = d2.rstrip("/")
                    if d2.endswith("_skill"):
                        out.append(d2.replace("_skill", ""))
                return sorted(out)
            except Exception:
                return []
        available_skills: List[str] = []
        skills_root = user_skills_root()
        if skills_root.exists():
            for d in skills_root.iterdir():
                if d.is_dir() and d.name.endswith("_skill"):
                    available_skills.append(d.name.replace("_skill", ""))
        return sorted(available_skills)

    def _get_effective_username(self) -> str:
        try:
            env_user = os.environ.get("ECAN_USERNAME") or os.environ.get("ECAN_USER") or os.environ.get("USER_EMAIL")
            if isinstance(env_user, str) and env_user.strip():
                return env_user.strip()
        except Exception:
            pass
        try:
            from utils.env.secure_store import get_current_username

            u = get_current_username()
            if isinstance(u, str) and u.strip():
                return u.strip()
        except Exception:
            pass
        try:
            if isinstance(self._user_name, str) and self._user_name.strip():
                return self._user_name.strip()
        except Exception:
            pass
        return "unknown"

    def _infer_skill_dir_name(self, canvas_context: Optional[Dict[str, Any]]) -> Optional[str]:
        try:
            if canvas_context and isinstance(canvas_context, dict):
                raw = None
                if isinstance(canvas_context.get("metadata"), dict):
                    raw = canvas_context.get("metadata", {}).get("skillName")
                if not raw:
                    raw = canvas_context.get("skillName")
                if isinstance(raw, str) and raw.strip():
                    name = raw.strip()
                    if name.endswith("_skill"):
                        return name
                    return f"{name}_skill"
        except Exception:
            return None
        return None

    def _infer_skill_dir_name_from_current_flowgram(self) -> Optional[str]:
        try:
            fg = self.code_agent.get_current_flowgram() if self._code_agent else None
            if fg and isinstance(fg.metadata, dict):
                raw = fg.metadata.get("skillName")
                if isinstance(raw, str) and raw.strip():
                    name = raw.strip()
                    if name.endswith("_skill"):
                        return name
                    return f"{name}_skill"
        except Exception:
            return None
        return None

    def _restore_conversation_history(self, skill_dir_name: str, session_id: str) -> None:
        try:
            data = None
            if _is_lambda_runtime():
                data = self._read_context_json_from_s3(skill_dir_name, session_id)
            else:
                path = user_skills_root() / skill_dir_name / "contexts" / f"{session_id}.json"
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                history = data.get("conversation_history")
                if isinstance(history, list):
                    self._conversation_history = history
        except Exception:
            return

    def _persist_conversation_history(self, skill_dir_name: str, session_id: str) -> None:
        payload = {
            "session_id": session_id,
            "skill": skill_dir_name,
            "conversation_history": self._conversation_history,
        }
        if _is_lambda_runtime():
            self._write_context_json_to_s3(skill_dir_name, session_id, payload)
            return
        ctx_dir = user_skills_root() / skill_dir_name / "contexts"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        path = ctx_dir / f"{session_id}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _is_trivial_message(self, msg: Optional[str]) -> bool:
        """Return True when *msg* carries no actionable task info."""
        if not msg:
            return True
        m = (msg or "").strip().lower()
        return len(m) < 12 and not any(kw in m for kw in ("create", "build", "make", "automate", "workflow", "skill"))

    async def _generate_from_plan(
        self,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Generate flowgram from the current plan"""
        logger.info("[SkillEditorAgent] Generating flowgram from plan")
        self._pipeline_state = PipelineState.GENERATING
        await self._emit_progress(on_event, t("progress_plan_approved_codegen", self._user_lang))

        # Build full context from conversation history
        # This ensures the code agent has the complete picture of what user wants
        context_messages = []
        for msg in self._conversation_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                context_messages.append(f"[{role.upper()}]: {content}")

        # If the original request is trivial (e.g. "hello"), derive a richer task
        # description from accumulated clarification answers + conversation history.
        effective_request = self._current_request or ""
        if self._is_trivial_message(effective_request):
            enriched = self._build_enriched_request_with_answers()
            if enriched and len(enriched) > len(effective_request):
                effective_request = enriched
                logger.info("[SkillEditorAgent] Enriched trivial request for code gen")
        
        # Combine conversation context with current request
        full_context = ""
        if len(context_messages) > 1:
            full_context = "## CONVERSATION HISTORY (for context):\n" + "\n".join(context_messages[:-1]) + "\n\n"
        full_context += "## CURRENT REQUEST:\n" + effective_request
        
        # Generate with code agent
        code_output = await self.code_agent.generate(
            user_message=full_context,
            canvas_context=canvas_context,
            plan=self._current_plan,
            on_event=on_event,
            tools_catalog=self.tools_catalog_text,
            user_lang=self._user_lang,
        )
        
        # If no flowgram was produced, surface a clear failure message rather
        # than passing through raw LLM text that looks like a generic greeting.
        if not code_output.flowgram:
            logger.warning("[SkillEditorAgent] Code generation produced no flowgram — returning error to user")
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=t("codegen_failed", self._user_lang),
                intent=IntentType.CREATE_FLOWGRAM,
                metadata={"session_id": session_id, "state": "idle", "generation_failed": True},
            )

        self._pipeline_state = PipelineState.COMPLETE
        
        # Generate canvas commands if flowgram was created
        commands = []
        skill_path = None
        if code_output.flowgram:
            # Dual-write skill + bundle to disk
            await self._emit_progress(on_event, t("progress_saving", self._user_lang))
            skill_path = self._save_flowgram_to_disk(code_output.flowgram, data_mapping=code_output.data_mapping)
            
            # If skill was scaffolded to disk, only send load_flowgram command
            # The frontend will load the nodes from disk via loadSkillFile
            # This avoids race conditions between load_flowgram and individual node commands
            if skill_path:
                commands = [CanvasCommand(
                    type="canvas.load_flowgram",
                    payload={"skillPath": skill_path, "skillName": code_output.flowgram.metadata.get("skillName", "generated_skill")}
                )]
            else:
                # No disk scaffold - send individual node commands for in-memory editing
                commands = self.code_agent.generate_canvas_commands(code_output.flowgram)
        
        return AgentResponse(
            message=code_output.message or "I've generated the workflow for you.",
            commands=[CanvasCommand(type=c.type, payload=c.payload) for c in commands],
            intent=IntentType.CREATE_FLOWGRAM,
            flowgram=code_output.flowgram,
            validation=code_output.validation,
            metadata={"session_id": session_id, "state": "complete", "skillPath": skill_path}
        )
    
    async def _run_code_generation(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        intent: IntentType,
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Run direct code generation without planning"""
        logger.info(f"[SkillEditorAgent] Direct code generation for intent: {intent.value}")
        self._pipeline_state = PipelineState.GENERATING
        await self._emit_progress(on_event, t("progress_working", self._user_lang, intent=intent.value))

        msg_lower = (message or "").lower()

        # When editing, we must preserve the currently loaded skill identity.
        target_skill_name: Optional[str] = None
        if canvas_context and isinstance(canvas_context, dict):
            try:
                raw_skill_name = canvas_context.get("skillName")
                if isinstance(raw_skill_name, str) and raw_skill_name.strip():
                    target_skill_name = raw_skill_name.strip()
                    if target_skill_name.endswith("_skill"):
                        target_skill_name = target_skill_name[: -len("_skill")]
            except Exception:
                target_skill_name = None

        current_flowgram_for_edit: Optional[Flowgram] = None

        # Deterministic validate/repair-only mode: do NOT call LLM; run ValidatorAgent on the current canvas.
        if intent in [IntentType.MODIFY_NODE, IntentType.CONNECT_NODES] and canvas_context:
            if any(w in msg_lower for w in ["validate", "repair", "fix connections", "fix connectivity", "fix edges"]):
                try:
                    current_flowgram = self._canvas_context_to_flowgram(canvas_context)
                    if current_flowgram:
                        from agent.skill_editor import get_validator_agent

                        validator = get_validator_agent()
                        fixed_dict = validator.fix_disconnected_nodes(current_flowgram.model_dump(), task_context=message)
                        fixed_flowgram = Flowgram.model_validate(fixed_dict)
                        self.code_agent.set_current_flowgram(fixed_flowgram)

                        skill_path = self._save_flowgram_to_disk(fixed_flowgram)
                        commands = []
                        if skill_path:
                            commands = [CanvasCommand(
                                type="canvas.load_flowgram",
                                payload={"skillPath": skill_path, "skillName": fixed_flowgram.metadata.get("skillName", "generated_skill")}
                            )]

                        self._pipeline_state = PipelineState.COMPLETE
                        return AgentResponse(
                            message=t("validated_connections", self._user_lang),
                            commands=[CanvasCommand(type=c.type, payload=c.payload) for c in commands],
                            intent=IntentType.MODIFY_NODE,
                            flowgram=fixed_flowgram,
                            validation=None,
                            metadata={"session_id": session_id, "skillPath": skill_path, "state": "complete"}
                        )
                except Exception as e:
                    logger.error(f"[SkillEditorAgent] Deterministic validation failed: {e}")

        # For edit operations, use edit method with current canvas state
        if intent in [IntentType.ADD_NODE, IntentType.REMOVE_NODE, IntentType.MODIFY_NODE, IntentType.CONNECT_NODES]:
            # Convert canvas_context to Flowgram for editing
            current_flowgram = self._canvas_context_to_flowgram(canvas_context)
            current_flowgram_for_edit = current_flowgram

            # Ensure CodeAgent knows what the current workflow is (important when canvas_context had 0 nodes
            # but we loaded from disk via skillName).
            if current_flowgram_for_edit:
                try:
                    self.code_agent.set_current_flowgram(current_flowgram_for_edit)
                except Exception:
                    pass

            code_output = await self.code_agent.edit(
                edit_request=message,
                current_flowgram=current_flowgram,
                on_event=on_event,
                tools_catalog=self.tools_catalog_text,
                user_lang=self._user_lang,
            )
        else:
            code_output = await self.code_agent.generate(
                user_message=message,
                canvas_context=canvas_context,
                on_event=on_event,
                tools_catalog=self.tools_catalog_text,
                user_lang=self._user_lang,
            )
        
        self._pipeline_state = PipelineState.COMPLETE
        
        commands = []
        skill_path = None
        if code_output.flowgram:
            # For edit intents, never allow changing the underlying skill name (prevents writing to generated_skill).
            if intent in [IntentType.ADD_NODE, IntentType.REMOVE_NODE, IntentType.MODIFY_NODE, IntentType.CONNECT_NODES]:
                desired_skill_name = None
                if target_skill_name:
                    desired_skill_name = target_skill_name
                elif current_flowgram_for_edit and current_flowgram_for_edit.metadata:
                    desired_skill_name = current_flowgram_for_edit.metadata.get("skillName")
                if isinstance(desired_skill_name, str) and desired_skill_name.strip():
                    if not code_output.flowgram.metadata:
                        code_output.flowgram.metadata = {}
                    code_output.flowgram.metadata["skillName"] = desired_skill_name.strip()

            # Guard: never allow LLM edits to wipe nodes unless the user explicitly asked to remove/delete.
            try:
                old_count = 0

                # Prefer the authoritative loaded flowgram for edits (covers cases where canvas_context has 0 nodes
                # but skillName was provided and we loaded from disk).
                if current_flowgram_for_edit and getattr(current_flowgram_for_edit, "nodes", None) is not None:
                    old_count = len(current_flowgram_for_edit.nodes)

                if old_count <= 0 and canvas_context and isinstance(canvas_context.get("nodes"), list):
                    old_count = len(canvas_context.get("nodes"))

                if old_count <= 0 and self.code_agent.get_current_flowgram():
                    old_count = len(self.code_agent.get_current_flowgram().nodes)

                new_count = len(code_output.flowgram.nodes)
                is_explicit_delete = any(w in msg_lower for w in ["remove", "delete"]) 
                if old_count > 0 and new_count < old_count and not is_explicit_delete:
                    logger.warning(
                        f"[SkillEditorAgent] Refusing to apply edit that reduces node count {old_count} -> {new_count}"
                    )
                    self._pipeline_state = PipelineState.COMPLETE
                    return AgentResponse(
                        message=t("edit_refused_node_loss", self._user_lang),
                        intent=intent,
                        metadata={"session_id": session_id, "state": "complete", "refused": True}
                    )
            except Exception:
                pass

            # Always dual-write to disk for both create and edit operations
            # This ensures the skill file and bundle stay in sync and frontend can reload
            skill_path = self._save_flowgram_to_disk(code_output.flowgram, data_mapping=code_output.data_mapping)

            # Cache flowgram dict in memory so it survives to the next Lambda invocation (via session state)
            try:
                self._cached_flowgram_dict = code_output.flowgram.model_dump()
            except Exception:
                pass
            
            # Send load_flowgram command to reload the updated skill
            # The frontend will load the nodes from disk via loadSkillFile
            if skill_path:
                commands = [CanvasCommand(
                    type="canvas.load_flowgram",
                    payload={"skillPath": skill_path, "skillName": code_output.flowgram.metadata.get("skillName", "generated_skill")}
                )]
            else:
                # Fallback: send individual node commands for in-memory editing
                commands = self.code_agent.generate_canvas_commands(code_output.flowgram)
        
        return AgentResponse(
            message=code_output.message,
            commands=[CanvasCommand(type=c.type, payload=c.payload) for c in commands],
            intent=intent,
            flowgram=code_output.flowgram,
            validation=code_output.validation,
            metadata={"session_id": session_id, "skillPath": skill_path}
        )
    
    def _format_plan_for_display(self, plan: Optional[ImplementationPlan]) -> str:
        """Format implementation plan for user display"""
        if not plan:
            return "No plan available."
        
        lines = [
            f"**Summary:** {plan.summary}",
            f"**Complexity:** {plan.complexity}",
            "",
            "**Steps:**"
        ]
        
        for i, step in enumerate(plan.steps, 1):
            lines.append(f"{i}. **{step.title}**")
            lines.append(f"   {step.description}")
            if step.node_types:
                lines.append(f"   _Nodes: {', '.join(step.node_types)}_")
        
        lines.append("")
        lines.append(f"**Estimated nodes:** {', '.join(plan.estimated_nodes)}")
        
        return "\n".join(lines)
    
    def process_message_sync(
        self,
        message: str,
        canvas_context: Optional[Dict] = None,
        session_id: Optional[str] = None,
        clarification_responses: Optional[Dict[str, List[str]]] = None,
        on_event: Optional[Callable] = None
    ) -> AgentResponse:
        """Synchronous wrapper for process_message.
        
        Handles both cases:
        - When called from a thread without an event loop: uses asyncio.run()
        - When called from within a running event loop (e.g., desktop app with PyQt): 
          uses nest_asyncio or runs in a new thread
        """
        import asyncio
        
        coro = self.process_message(message, canvas_context, session_id, clarification_responses, on_event)
        
        try:
            # Check if there's already a running event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(coro)
        
        # There's a running loop (e.g., PyQt/PySide desktop app)
        # Run the coroutine in a separate thread with its own event loop
        import concurrent.futures
        
        def run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_new_loop)
            return future.result()
    
    async def process_message_streaming(
        self,
        message: str,
        canvas_context: Optional[Dict] = None,
        session_id: Optional[str] = None,
        on_chunk: Optional[Callable] = None,
        on_event: Optional[Callable] = None
    ) -> AgentResponse:
        """
        Process a chat message with streaming response.
        
        Args:
            message: User's chat message
            canvas_context: Current canvas state
            session_id: Chat session ID
            on_chunk: Callback for text chunks (chunk: str, index: int)
            on_event: Callback for structured events
            
        Returns:
            AgentResponse with complete message and optional commands
        """
        logger.info(f"[SkillEditorAgent] Processing message (streaming): {message[:100]}...")
        
        # Create a combined event handler that handles both sync and async callbacks
        async def combined_event_handler(event: Dict):
            if on_event:
                import asyncio
                result = on_event(event)
                if asyncio.iscoroutine(result):
                    await result
            # Also send chunks if it's a chunk event
            if event.get("type") == "chunk" and on_chunk:
                on_chunk(event.get("data", {}).get("content", ""), event.get("data", {}).get("index", 0))
        
        # Use the standard process_message with event handler
        return await self.process_message(
            message=message,
            canvas_context=canvas_context,
            session_id=session_id,
            on_event=combined_event_handler
        )
    
    def clear_history(self):
        """Clear conversation history and reset pipeline state"""
        self._conversation_history = []
        self._pipeline_state = PipelineState.IDLE
        self._pending_clarification = None
        self._current_plan = None
        self._current_request = None
        self._selected_node = None
        if self._planner:
            self._planner.clear_history()
        if self._code_agent:
            self._code_agent.clear()
        logger.info("[SkillEditorAgent] History and state cleared")
    
    def get_pending_clarification(self) -> Optional[List[ClarificationQuestion]]:
        """Get pending clarification questions"""
        return self._pending_clarification
    
    def get_current_plan(self) -> Optional[ImplementationPlan]:
        """Get the current implementation plan"""
        return self._current_plan
    
    def get_current_flowgram(self) -> Optional[Flowgram]:
        """Get the current flowgram from code agent"""
        if self._code_agent:
            return self._code_agent.get_current_flowgram()
        return None
    
    async def edit_flowgram(
        self,
        edit_request: str,
        canvas_context: Optional[Dict] = None,
        session_id: Optional[str] = None,
        on_event: Optional[Callable] = None
    ) -> AgentResponse:
        """
        Pearl-like iterative flowgram editing.
        
        This method allows iterative refinement of the current flowgram through
        natural language requests. It validates changes and provides feedback.
        
        Args:
            edit_request: Natural language description of the edit
            canvas_context: Current canvas state
            session_id: Chat session ID
            on_event: Callback for streaming events
            
        Returns:
            AgentResponse with updated flowgram and validation
        """
        logger.info(f"[SkillEditorAgent] Edit flowgram request: {edit_request[:100]}...")
        self._pipeline_state = PipelineState.EDITING
        
        try:
            # Convert canvas context to Flowgram for editing
            current_flowgram = self._canvas_context_to_flowgram(canvas_context)
            if current_flowgram:
                self.code_agent.set_current_flowgram(current_flowgram)

            # Use code agent's edit method
            code_output = await self.code_agent.edit(
                edit_request=edit_request,
                current_flowgram=current_flowgram,
                on_event=on_event,
                tools_catalog=self.tools_catalog_text,
                user_lang=self._user_lang,
            )
            
            self._pipeline_state = PipelineState.COMPLETE
            
            # Generate canvas commands
            commands = []
            if code_output.flowgram:
                commands = self.code_agent.generate_canvas_commands(code_output.flowgram)
                # Cache flowgram for session persistence
                try:
                    self._cached_flowgram_dict = code_output.flowgram.model_dump()
                except Exception:
                    pass
            
            # Check validation
            if code_output.validation and not code_output.validation.valid:
                # Validation failed - provide feedback
                error_messages = [e.message for e in code_output.validation.errors]
                message = f"{code_output.message}\n\n⚠️ **Validation Issues:**\n- " + "\n- ".join(error_messages)
                message += "\n\nWould you like me to fix these issues?"
            else:
                message = code_output.message
            
            return AgentResponse(
                message=message,
                commands=[CanvasCommand(type=c.type, payload=c.payload) for c in commands],
                intent=IntentType.MODIFY_NODE,
                flowgram=code_output.flowgram,
                validation=code_output.validation,
                metadata={"session_id": session_id, "state": "complete"}
            )
            
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Edit flowgram error: {e}\n{traceback.format_exc()}")
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=t("error_editing", self._user_lang, error=str(e)),
                intent=IntentType.UNKNOWN,
                metadata={"error": str(e), "session_id": session_id}
            )
    
    def edit_flowgram_sync(
        self,
        edit_request: str,
        canvas_context: Optional[Dict] = None,
        session_id: Optional[str] = None,
        on_event: Optional[Callable] = None
    ) -> AgentResponse:
        """Synchronous version of edit_flowgram"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
                return run_async_in_sync(
                    self.edit_flowgram(edit_request, canvas_context, session_id, on_event)
                )
            else:
                return loop.run_until_complete(
                    self.edit_flowgram(edit_request, canvas_context, session_id, on_event)
                )
        except RuntimeError:
            return asyncio.run(
                self.edit_flowgram(edit_request, canvas_context, session_id, on_event)
            )
    
    async def configure_node(
        self,
        node_id: str,
        node_type: str,
        config_request: str,
        current_config: Optional[Dict[str, Any]] = None,
        canvas_context: Optional[Dict] = None,
        session_id: Optional[str] = None,
        on_event: Optional[Callable] = None
    ) -> AgentResponse:
        """
        Direct node configuration API (Pearl-like).
        
        Allows configuring a specific node through natural language.
        
        Args:
            node_id: ID of the node to configure
            node_type: Type of the node
            config_request: Natural language configuration request
            current_config: Current node configuration
            canvas_context: Current canvas state
            session_id: Chat session ID
            on_event: Callback for streaming events
            
        Returns:
            AgentResponse with configuration result
        """
        logger.info(f"[SkillEditorAgent] Configure node {node_id} ({node_type})")
        self._pipeline_state = PipelineState.CONFIGURING_NODE
        
        try:
            config_output = await self.node_config_agent.configure_node(
                node_id=node_id,
                node_type=node_type,
                user_request=config_request,
                current_config=current_config,
                available_context=canvas_context
            )
            
            if config_output.action == NodeConfigAction.ASK_CLARIFICATION:
                self._selected_node = {"id": node_id, "type": node_type, "config": {"inputsValues": current_config or {}}}
                self._pending_clarification = config_output.clarification
                return AgentResponse(
                    message=config_output.message,
                    intent=IntentType.MODIFY_NODE,
                    clarification=config_output.clarification,
                    metadata={"session_id": session_id, "state": "configuring_node", "node_id": node_id}
                )
            
            self._pipeline_state = PipelineState.COMPLETE
            commands = [CanvasCommand(type=c.type, payload=c.payload) for c in config_output.commands]
            
            return AgentResponse(
                message=config_output.message,
                commands=commands,
                intent=IntentType.MODIFY_NODE,
                validation=config_output.validation,
                metadata={"session_id": session_id, "state": "complete", "node_config": config_output.node_config}
            )
            
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Configure node error: {e}\n{traceback.format_exc()}")
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=t("error_configuring_node", self._user_lang, error=str(e)),
                intent=IntentType.UNKNOWN,
                metadata={"error": str(e), "session_id": session_id}
            )


    # ============================================================
    # Test and Deploy Methods
    # ============================================================
    
    async def _run_test_skill(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """
        Handle skill testing requests: run, pause, step, exit.
        
        Test actions:
        - run: Start or resume execution from the beginning
        - pause: Pause execution at current node
        - step: Execute one node at a time (step-through debugging)
        - exit: Stop testing and exit test mode
        """
        logger.info(f"[SkillEditorAgent] Test skill request: {message}")
        
        msg_lower = message.lower()
        
        # Determine test action
        if "exit" in msg_lower or "stop test" in msg_lower or "quit test" in msg_lower:
            action = "exit"
            action_msg = "Exiting test mode."
        elif "pause" in msg_lower:
            action = "pause"
            action_msg = "Pausing skill execution at current node."
        elif "step" in msg_lower or "next" in msg_lower:
            action = "step"
            action_msg = "Stepping to next node."
        else:
            action = "run"
            action_msg = "Starting skill test execution."
        
        # Get current skill name from canvas context or code agent
        skill_name = None
        if canvas_context and canvas_context.get("metadata"):
            skill_name = canvas_context["metadata"].get("skillName")
        
        if not skill_name and self.code_agent._current_flowgram:
            skill_name = self.code_agent._current_flowgram.metadata.get("skillName") if self.code_agent._current_flowgram.metadata else None
        
        if not skill_name:
            return AgentResponse(
                message=t("no_skill_loaded", self._user_lang),
                intent=IntentType.TEST_SKILL,
                metadata={"session_id": session_id}
            )
        
        # Extract breakpoints if mentioned
        breakpoints = []
        if "breakpoint" in msg_lower or "break at" in msg_lower:
            # Extract node IDs mentioned after "breakpoint" or "break at"
            if canvas_context and canvas_context.get("nodes"):
                for node in canvas_context["nodes"]:
                    node_id = node.get("id", "")
                    if node_id.lower() in msg_lower:
                        breakpoints.append(node_id)
        
        # Create test command
        test_command = CanvasCommand(
            type="skill.test",
            payload={
                "action": action,
                "skill_name": skill_name,
                "breakpoints": breakpoints
            }
        )
        
        return AgentResponse(
            message=action_msg,
            commands=[test_command],
            intent=IntentType.TEST_SKILL,
            metadata={
                "session_id": session_id,
                "test_action": action,
                "skill_name": skill_name,
                "breakpoints": breakpoints
            }
        )
    
    async def _run_deploy_skill(
        self,
        message: str,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """
        Handle skill deployment requests: create task, schedule, assign agent, kick off.
        
        Deployment flow:
        1. Create a task using the current skill
        2. Schedule it (cron expression or immediate)
        3. Assign to an existing agent or create a new one
        4. Kick off the task
        """
        logger.info(f"[SkillEditorAgent] Deploy skill request: {message}")
        
        msg_lower = message.lower()
        
        # Get current skill name
        skill_name = None
        if canvas_context and canvas_context.get("metadata"):
            skill_name = canvas_context["metadata"].get("skillName")
        
        if not skill_name and self.code_agent._current_flowgram:
            skill_name = self.code_agent._current_flowgram.metadata.get("skillName") if self.code_agent._current_flowgram.metadata else None
        
        if not skill_name:
            return AgentResponse(
                message=t("no_skill_for_deploy", self._user_lang),
                intent=IntentType.DEPLOY_SKILL,
                metadata={"session_id": session_id}
            )
        
        # Parse schedule from message
        schedule = "now"  # Default to immediate
        if "schedule" in msg_lower:
            # Look for cron-like patterns or time expressions
            if "every hour" in msg_lower:
                schedule = "0 * * * *"
            elif "every day" in msg_lower or "daily" in msg_lower:
                schedule = "0 0 * * *"
            elif "every week" in msg_lower or "weekly" in msg_lower:
                schedule = "0 0 * * 0"
            elif "every minute" in msg_lower:
                schedule = "* * * * *"
        
        # Parse agent name from message
        agent_name = None
        new_agent_config = None
        if "agent" in msg_lower:
            # Check for "new agent" or "create agent"
            if "new agent" in msg_lower or "create agent" in msg_lower:
                # Generate a new agent name based on skill
                new_agent_config = {
                    "name": f"{skill_name}_agent",
                    "description": f"Agent for running {skill_name} skill"
                }
            # Otherwise try to extract existing agent name (would need more context)
        
        # Generate task name
        task_name = f"{skill_name}_task"
        
        # Create deploy command
        deploy_command = CanvasCommand(
            type="skill.deploy",
            payload={
                "task_name": task_name,
                "skill_name": skill_name,
                "schedule": schedule,
                "agent_name": agent_name,
                "new_agent_config": new_agent_config
            }
        )
        
        # Build response message
        if schedule == "now":
            schedule_msg = "immediately"
        else:
            schedule_msg = f"on schedule '{schedule}'"
        
        agent_msg = ""
        if new_agent_config:
            agent_msg = f" A new agent '{new_agent_config['name']}' will be created."
        elif agent_name:
            agent_msg = f" Assigned to agent '{agent_name}'."
        
        response_msg = f"Deploying skill '{skill_name}' as task '{task_name}' to run {schedule_msg}.{agent_msg}"
        
        return AgentResponse(
            message=response_msg,
            commands=[deploy_command],
            intent=IntentType.DEPLOY_SKILL,
            metadata={
                "session_id": session_id,
                "task_config": {
                    "task_name": task_name,
                    "skill_name": skill_name,
                    "schedule": schedule,
                    "agent_name": agent_name,
                    "new_agent_config": new_agent_config
                }
            }
        )


# ============================================================
# Singleton Instance
# ============================================================

_agent_instance: Optional[SkillEditorAgent] = None


def get_skill_editor_agent() -> SkillEditorAgent:
    """Get or create the singleton skill editor agent instance"""
    global _agent_instance
    if _agent_instance is None:
        logger.info("[SkillEditorAgent] Creating new singleton instance")
        _agent_instance = SkillEditorAgent()
    return _agent_instance


def reset_skill_editor_agent():
    """Reset the singleton instance (useful for testing)"""
    global _agent_instance
    logger.info("[SkillEditorAgent] Resetting singleton instance")
    if _agent_instance:
        _agent_instance.clear_history()
    _agent_instance = None
