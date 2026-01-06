"""
Skill Editor Agent (Orchestrator)

Orchestrates the skill editing pipeline by coordinating:
1. PlannerAgent - for clarification and planning
2. CodeAgent - for flowgram generation and editing

This agent provides a unified interface for the chat handler while
delegating specialized tasks to the appropriate sub-agents.
"""

import json
import traceback
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from utils.logger_helper import logger_helper as logger

# Import from schemas
from .schemas import (
    IntentType,
    PlannerAction,
    AgentResponse,
    CanvasCommand,
    ClarificationQuestion,
    ImplementationPlan,
    Flowgram,
    NODE_TYPES,
    get_node_types_description,
)

# Import sub-agents
from .planner_agent import PlannerAgent, get_planner_agent
from .code_agent import CodeAgent, get_code_agent
from .node_config_agent import NodeConfigAgent, NodeConfigAction, get_node_config_agent


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
    
    This agent coordinates:
    1. PlannerAgent for clarification and planning
    2. CodeAgent for flowgram generation and editing
    3. Pipeline state management
    4. Conversation history
    """
    
    def __init__(self, llm=None):
        """
        Initialize the skill editor agent.
        
        Args:
            llm: LangChain LLM instance. If None, sub-agents will use default from settings.
        """
        self._llm = llm
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
        
        # Execution intents
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
                if any(word in message.lower() for word in ["yes", "ok", "approve", "proceed", "go ahead"]):
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
        if code_output.flowgram:
            commands = self.code_agent.generate_canvas_commands(code_output.flowgram)
        
        return AgentResponse(
            message=code_output.message or "I've generated the workflow for you.",
            commands=[CanvasCommand(type=c.type, payload=c.payload) for c in commands],
            intent=IntentType.CREATE_FLOWGRAM,
            flowgram=code_output.flowgram,
            validation=code_output.validation,
            metadata={"session_id": session_id, "state": "complete"}
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
        
        # For edit operations, use edit method
        if intent in [IntentType.ADD_NODE, IntentType.REMOVE_NODE, IntentType.MODIFY_NODE, IntentType.CONNECT_NODES]:
            code_output = await self.code_agent.edit(
                edit_request=message,
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
        if code_output.flowgram:
            commands = self.code_agent.generate_canvas_commands(code_output.flowgram)
        
        return AgentResponse(
            message=code_output.message,
            commands=[CanvasCommand(type=c.type, payload=c.payload) for c in commands],
            intent=intent,
            flowgram=code_output.flowgram,
            validation=code_output.validation,
            metadata={"session_id": session_id}
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
