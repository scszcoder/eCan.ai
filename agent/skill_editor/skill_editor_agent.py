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
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from utils.logger_helper import logger_helper as logger

# Import skill scaffolding utility
from agent.ec_skills.extern_skills.extern_skills import scaffold_skill, user_skills_root

# Import from schemas
from .schemas import (
    IntentType,
    PlannerAction,
    AgentResponse,
    CanvasCommand,
    ClarificationQuestion,
    ImplementationPlan,
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
        )
    
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
    def pipeline_state(self) -> PipelineState:
        """Get current pipeline state"""
        return self._pipeline_state
    
    def _classify_intent_simple(self, message: str) -> IntentType:
        """Simple rule-based intent classification"""
        msg_lower = message.lower()
        
        # Load skill intent - check first as it's specific
        if any(phrase in msg_lower for phrase in ["load", "open", "load up", "switch to"]) and "skill" in msg_lower:
            return IntentType.LOAD_SKILL
        
        # Save skill intent
        if any(phrase in msg_lower for phrase in ["save", "save as", "export"]) and ("skill" in msg_lower or "workflow" in msg_lower or "flowgram" in msg_lower):
            return IntentType.SAVE_SKILL
        
        # Creation intents
        if any(word in msg_lower for word in ["create", "build", "make", "generate", "new workflow"]):
            return IntentType.CREATE_FLOWGRAM
        
        # Node operations
        if "add" in msg_lower and "node" in msg_lower:
            return IntentType.ADD_NODE
        if "remove" in msg_lower or "delete" in msg_lower:
            return IntentType.REMOVE_NODE
        if "connect" in msg_lower or "link" in msg_lower:
            return IntentType.CONNECT_NODES
        if "modify" in msg_lower or "change" in msg_lower or "update" in msg_lower:
            return IntentType.MODIFY_NODE
        
        # Test skill intents
        if any(phrase in msg_lower for phrase in ["test", "run test", "step through", "pause", "exit test"]) and \
           any(word in msg_lower for word in ["skill", "workflow", "this"]):
            return IntentType.TEST_SKILL
        
        # Deploy skill intents
        if any(phrase in msg_lower for phrase in ["deploy", "schedule", "create task", "assign agent", "kick off"]) and \
           any(word in msg_lower for word in ["skill", "workflow", "this"]):
            return IntentType.DEPLOY_SKILL
        
        # Execution intents (legacy - for direct run without test mode)
        if "run" in msg_lower or "execute" in msg_lower:
            return IntentType.RUN_FLOWGRAM
        if "debug" in msg_lower or "step" in msg_lower:
            return IntentType.DEBUG_FLOWGRAM
        
        # Explanation
        if any(word in msg_lower for word in ["explain", "what", "how", "why", "help"]):
            return IntentType.EXPLAIN
        
        return IntentType.GENERAL_CHAT
    
    def _should_use_planner(self, intent: IntentType) -> bool:
        """Determine if the planner should be used for this intent"""
        # Use planner for complex creation tasks
        return intent in [
            IntentType.CREATE_FLOWGRAM,
        ]
    
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
        
        try:
            # Handle node configuration clarification responses
            if clarification_responses and self._pipeline_state == PipelineState.CONFIGURING_NODE:
                logger.info("[SkillEditorAgent] Processing node config clarification responses")
                return await self._handle_node_config_clarification(
                    clarification_responses, canvas_context, session_id, on_event
                )
            
            # Handle clarification responses
            if clarification_responses and self._pipeline_state == PipelineState.AWAITING_CLARIFICATION:
                logger.info("[SkillEditorAgent] Processing clarification responses")
                return await self._handle_clarification_response(
                    clarification_responses, canvas_context, session_id, on_event
                )
            
            # Handle plan approval
            if self._pipeline_state == PipelineState.AWAITING_PLAN_APPROVAL:
                if any(word in message.lower() for word in ["yes", "ok", "approve", "proceed", "do it", "do them", "go ahead"]):
                    logger.info("[SkillEditorAgent] Plan approved, proceeding to code generation")
                    return await self._generate_from_plan(canvas_context, session_id, on_event)
                elif any(word in message.lower() for word in ["no", "cancel", "revise", "change"]):
                    logger.info("[SkillEditorAgent] Plan rejected, resetting")
                    self._pipeline_state = PipelineState.IDLE
                    self._current_plan = None
                    return AgentResponse(
                        message="Understood. Please describe what you'd like to change about the plan.",
                        intent=IntentType.GENERAL_CHAT,
                        metadata={"session_id": session_id}
                    )
            
            # Classify intent
            intent = self._classify_intent_simple(message)
            logger.info(f"[SkillEditorAgent] Classified intent: {intent.value}")
            
            # Store current request
            self._current_request = message
            
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
                return await self._run_node_configuration(message, canvas_context, session_id, on_event)
            
            # Decide whether to use planner or go directly to code
            if self._should_use_planner(intent):
                return await self._run_planning_phase(message, canvas_context, session_id, on_event)
            else:
                # For simpler intents, go directly to code agent
                return await self._run_code_generation(message, canvas_context, session_id, intent, on_event)
            
        except Exception as e:
            error_msg = f"I encountered an error processing your request: {str(e)}"
            logger.error(f"[SkillEditorAgent] Error: {e}\n{traceback.format_exc()}")
            self._pipeline_state = PipelineState.IDLE
            return AgentResponse(
                message=error_msg,
                intent=IntentType.UNKNOWN,
                metadata={"error": str(e), "session_id": session_id}
            )
    
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
                message="I couldn't determine which skill to load. Please specify the skill name, e.g., 'load ebay000 skill'.",
                intent=IntentType.LOAD_SKILL,
                metadata={"session_id": session_id}
            )
        
        # Check if skill exists on disk
        if not skill_name.endswith("_skill"):
            skill_dir_name = f"{skill_name}_skill"
        else:
            skill_dir_name = skill_name
            skill_name = skill_name.replace("_skill", "")
        
        skill_path = user_skills_root() / skill_dir_name
        skill_file_path = skill_path / "diagram_dir" / f"{skill_dir_name}.json"
        
        logger.info(f"[SkillEditorAgent] Looking for skill at: {skill_file_path}")
        
        if not skill_file_path.exists():
            # List available skills
            available_skills = []
            skills_root = user_skills_root()
            if skills_root.exists():
                for d in skills_root.iterdir():
                    if d.is_dir() and d.name.endswith("_skill"):
                        available_skills.append(d.name.replace("_skill", ""))
            
            skills_list = ", ".join(available_skills[:10]) if available_skills else "none found"
            return AgentResponse(
                message=f"Skill '{skill_name}' not found. Available skills: {skills_list}",
                intent=IntentType.LOAD_SKILL,
                metadata={"session_id": session_id, "available_skills": available_skills}
            )
        
        # Load the flowgram from disk
        flowgram = self._load_flowgram_from_disk(skill_name)
        
        if not flowgram:
            return AgentResponse(
                message=f"Failed to load skill '{skill_name}'. The skill file may be corrupted.",
                intent=IntentType.LOAD_SKILL,
                metadata={"session_id": session_id}
            )
        
        # Set as current flowgram
        self.code_agent.set_current_flowgram(flowgram)
        
        # Send canvas.load_flowgram command
        commands = [CanvasCommand(
            type="canvas.load_flowgram",
            payload={
                "skillPath": str(skill_path),
                "skillName": skill_dir_name
            }
        )]
        
        node_count = len(flowgram.nodes)
        edge_count = len(flowgram.edges)
        
        logger.info(f"[SkillEditorAgent] Loaded skill '{skill_name}' with {node_count} nodes, {edge_count} edges")
        
        return AgentResponse(
            message=f"Loaded skill **{skill_name}** with {node_count} nodes and {edge_count} edges. You can now edit this workflow.",
            commands=commands,
            intent=IntentType.LOAD_SKILL,
            flowgram=flowgram,
            metadata={"session_id": session_id, "skillPath": str(skill_path)}
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
                message="No workflow to save. Please create or load a skill first.",
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
        
        # Scaffold to disk
        skill_path = self._scaffold_skill_to_disk(flowgram)
        
        if not skill_path:
            return AgentResponse(
                message="Failed to save the skill. Please try again.",
                intent=IntentType.SAVE_SKILL,
                metadata={"session_id": session_id}
            )
        
        skill_name = flowgram.metadata.get("skillName", "skill") if flowgram.metadata else "skill"
        node_count = len(flowgram.nodes)
        edge_count = len(flowgram.edges)
        
        logger.info(f"[SkillEditorAgent] Saved skill '{skill_name}' to {skill_path}")
        
        return AgentResponse(
            message=f"Saved skill **{skill_name}** with {node_count} nodes and {edge_count} edges to `{skill_path}`.",
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
                message="Please select a node on the canvas first, then tell me how you'd like to configure it.",
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
                message="I lost track of which node we were configuring. Please select the node again.",
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
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Run the planning phase with PlannerAgent"""
        logger.info("[SkillEditorAgent] Running planning phase")
        self._pipeline_state = PipelineState.PLANNING
        
        # Run planner
        planner_output = await self.planner.plan(
            user_message=message,
            canvas_context=canvas_context,
            on_event=on_event
        )
        
        logger.info(f"[SkillEditorAgent] Planner action: {planner_output.action.value}")
        
        if planner_output.action == PlannerAction.ASK_CLARIFICATION:
            # Need clarification from user
            self._pipeline_state = PipelineState.AWAITING_CLARIFICATION
            self._pending_clarification = planner_output.questions
            
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
                message=f"{planner_output.message or 'Here is my implementation plan:'}\n\n{plan_text}\n\nWould you like me to proceed with this plan?",
                intent=IntentType.CREATE_FLOWGRAM,
                plan=planner_output.plan,
                metadata={"session_id": session_id, "state": "awaiting_plan_approval"}
            )
        
        else:  # PROCEED_TO_CODE
            # Request is clear enough, proceed directly
            return await self._generate_from_plan(canvas_context, session_id, on_event)
    
    async def _handle_clarification_response(
        self,
        responses: Dict[str, List[str]],
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Handle user's clarification responses"""
        logger.info("[SkillEditorAgent] Handling clarification response")
        
        # Continue planning with responses
        planner_output = await self.planner.plan(
            user_message=self._current_request or "",
            canvas_context=canvas_context,
            clarification_responses=responses,
            on_event=on_event
        )
        
        if planner_output.action == PlannerAction.ASK_CLARIFICATION:
            # More clarification needed
            self._pending_clarification = planner_output.questions
            return AgentResponse(
                message=planner_output.message or "I have a few more questions:",
                intent=IntentType.CREATE_FLOWGRAM,
                clarification=planner_output.questions,
                metadata={"session_id": session_id, "state": "awaiting_clarification"}
            )
        
        elif planner_output.action == PlannerAction.GENERATE_PLAN:
            self._pipeline_state = PipelineState.AWAITING_PLAN_APPROVAL
            self._current_plan = planner_output.plan
            plan_text = self._format_plan_for_display(planner_output.plan)
            
            return AgentResponse(
                message=f"Based on your answers, here's my plan:\n\n{plan_text}\n\nShall I proceed?",
                intent=IntentType.CREATE_FLOWGRAM,
                plan=planner_output.plan,
                metadata={"session_id": session_id, "state": "awaiting_plan_approval"}
            )
        
        else:
            return await self._generate_from_plan(canvas_context, session_id, on_event)
    
    def _canvas_context_to_flowgram(self, canvas_context: Optional[Dict]) -> Optional[Flowgram]:
        """
        Convert canvas context (from frontend) to a Flowgram object for editing.
        
        The canvas_context contains the current state of the canvas including nodes and edges.
        """
        logger.info(f"[SkillEditorAgent] _canvas_context_to_flowgram called with canvas_context: {canvas_context is not None}")
        if canvas_context:
            logger.info(f"[SkillEditorAgent] Canvas context keys: {list(canvas_context.keys())}")
        
        if not canvas_context:
            logger.warning("[SkillEditorAgent] No canvas context provided for edit operation")
            return None
        
        try:
            nodes_data = canvas_context.get("nodes", [])
            edges_data = canvas_context.get("edges", [])
            logger.info(f"[SkillEditorAgent] Canvas context has {len(nodes_data)} nodes, {len(edges_data)} edges")
            
            if not nodes_data:
                # Try to load from disk if skill name is provided
                skill_name = canvas_context.get("skillName")
                if skill_name:
                    logger.info(f"[SkillEditorAgent] Canvas has no nodes but has skillName: {skill_name}, trying to load from disk")
                    return self._load_flowgram_from_disk(skill_name)
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
            blocks_data = n.get("blocks", [])
            if blocks_data:
                blocks = [self._parse_canvas_node(b, i) for i, b in enumerate(blocks_data)]
            
            # Parse internal edges
            internal_edges_data = n.get("edges", []) or n.get("internal_edges", [])
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
            # Construct skill file path
            # Handle both "skill_name" and "skill_name_skill" formats
            if not skill_name.endswith("_skill"):
                skill_dir_name = f"{skill_name}_skill"
            else:
                skill_dir_name = skill_name
                skill_name = skill_name.replace("_skill", "")
            
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
                logger.warning(f"[SkillEditorAgent] Skill file has no nodes: {skill_file_path}")
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
    
    def _node_to_json(self, node: FlowgramNode) -> Dict[str, Any]:
        """Convert a FlowgramNode to JSON-serializable dict for skill file."""
        config = node.config or {}
        
        # Handle condition nodes - ensure conditions array is present
        if node.type == "condition":
            if "conditions" not in config or not config.get("conditions"):
                config["conditions"] = [
                    {"key": f"if_{node.id[-5:]}", "value": {}},
                    {"key": f"else_{node.id[-5:]}", "value": {}},
                ]
        
        node_json = {
            "id": node.id,
            "type": node.type,
            "data": {
                "title": node.label or node.id,
                **config
            },
            "meta": {
                "position": {"x": node.position.x, "y": node.position.y} if node.position else {"x": 100, "y": 100}
            }
        }
        
        # Handle loop nodes with blocks
        if node.type == "loop" and node.blocks:
            node_json["blocks"] = [self._node_to_json(block) for block in node.blocks]
            if node.internal_edges:
                node_json["edges"] = [
                    {
                        "sourceNodeID": e.source,
                        "targetNodeID": e.target,
                        "sourcePortID": e.source_handle,
                        "targetPortID": e.target_handle,
                    }
                    for e in node.internal_edges
                ]
        
        return node_json
    
    def _scaffold_skill_to_disk(self, flowgram: Flowgram) -> Optional[str]:
        """
        Scaffold skill files to disk based on the generated flowgram.
        Returns the skill path if successful, None otherwise.
        """
        try:
            metadata = flowgram.metadata or {}
            skill_name = metadata.get("skillName") or metadata.get("name") or "generated_skill"
            description = metadata.get("description") or "Workflow generated via Skill Editor"
            
            # Convert flowgram to JSON-serializable dict
            # IMPORTANT: Frontend uses "meta.position" schema, not "position"
            skill_json = {
                "skillName": skill_name,
                "description": description,
                "workFlow": {
                    "nodes": [self._node_to_json(n) for n in flowgram.nodes],
                    "edges": [
                        {
                            "sourceNodeID": e.source,
                            "targetNodeID": e.target,
                            "sourcePortID": e.source_handle,
                            "targetPortID": e.target_handle,
                        }
                        for e in flowgram.edges
                    ]
                },
                "metadata": metadata
            }
            
            # Bundle JSON (empty for now, can be extended)
            bundle_json = {
                "sheets": [],
                "order": [],
                "activeSheetId": None
            }
            
            # Scaffold the skill directory and files
            skill_path = scaffold_skill(
                skill_name=skill_name,
                description=description,
                kind="diagram",
                skill_json=skill_json,
                bundle_json=bundle_json
            )
            
            logger.info(f"[SkillEditorAgent] Scaffolded skill to disk: {skill_path}")
            return str(skill_path)
            
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Failed to scaffold skill: {e}\n{traceback.format_exc()}")
            return None

    async def _generate_from_plan(
        self,
        canvas_context: Optional[Dict],
        session_id: Optional[str],
        on_event: Optional[Callable]
    ) -> AgentResponse:
        """Generate flowgram from the current plan"""
        logger.info("[SkillEditorAgent] Generating flowgram from plan")
        self._pipeline_state = PipelineState.GENERATING
        
        # Generate with code agent
        code_output = await self.code_agent.generate(
            user_message=self._current_request or "",
            canvas_context=canvas_context,
            plan=self._current_plan,
            on_event=on_event
        )
        
        self._pipeline_state = PipelineState.COMPLETE
        
        # Generate canvas commands if flowgram was created
        commands = []
        skill_path = None
        if code_output.flowgram:
            # Scaffold skill to disk
            skill_path = self._scaffold_skill_to_disk(code_output.flowgram)
            
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
        
        # For edit operations, use edit method with current canvas state
        if intent in [IntentType.ADD_NODE, IntentType.REMOVE_NODE, IntentType.MODIFY_NODE, IntentType.CONNECT_NODES]:
            # Convert canvas_context to Flowgram for editing
            current_flowgram = self._canvas_context_to_flowgram(canvas_context)
            code_output = await self.code_agent.edit(
                edit_request=message,
                current_flowgram=current_flowgram,
                on_event=on_event
            )
        else:
            code_output = await self.code_agent.generate(
                user_message=message,
                canvas_context=canvas_context,
                on_event=on_event
            )
        
        self._pipeline_state = PipelineState.COMPLETE
        
        commands = []
        skill_path = None
        if code_output.flowgram:
            # Always scaffold to disk for both create and edit operations
            # This ensures the skill file is updated and the frontend can reload it
            skill_path = self._scaffold_skill_to_disk(code_output.flowgram)
            
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
        
        This is called from a background_handler thread, so we use asyncio.run()
        which handles event loop creation and cleanup automatically.
        """
        import asyncio
        
        # asyncio.run() is the recommended way to run async code from sync context
        # It automatically creates a new event loop, runs the coroutine, and cleans up
        return asyncio.run(
            self.process_message(message, canvas_context, session_id, clarification_responses, on_event)
        )
    
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
        
        # Create a combined event handler
        def combined_event_handler(event: Dict):
            if on_event:
                on_event(event)
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
            # Use code agent's edit method
            code_output = await self.code_agent.edit(
                edit_request=edit_request,
                on_event=on_event
            )
            
            self._pipeline_state = PipelineState.COMPLETE
            
            # Generate canvas commands
            commands = []
            if code_output.flowgram:
                commands = self.code_agent.generate_canvas_commands(code_output.flowgram)
            
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
                message=f"I encountered an error editing the workflow: {str(e)}",
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
                message=f"I encountered an error configuring the node: {str(e)}",
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
                message="No skill is currently loaded. Please load or create a skill first.",
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
                message="No skill is currently loaded. Please load or create a skill first before deploying.",
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
