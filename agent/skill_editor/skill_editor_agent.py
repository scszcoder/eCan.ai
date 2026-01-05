"""
Skill Editor Agent

A LangGraph-based agent that processes chat messages for skill editing.
It can:
1. Understand user intent from natural language
2. Generate flowgram structures (nodes, edges)
3. Issue canvas commands to manipulate the editor
4. Run/debug flowgrams through chat

This agent uses the existing LLM infrastructure and can be extended
with MCP tools for canvas control.
"""

import json
import time
import uuid
import traceback
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from utils.logger_helper import logger_helper as logger


# ============================================================
# Types and Constants
# ============================================================

class IntentType(str, Enum):
    """Types of user intents the agent can recognize"""
    CREATE_FLOWGRAM = "create_flowgram"
    ADD_NODE = "add_node"
    REMOVE_NODE = "remove_node"
    CONNECT_NODES = "connect_nodes"
    MODIFY_NODE = "modify_node"
    RUN_FLOWGRAM = "run_flowgram"
    DEBUG_FLOWGRAM = "debug_flowgram"
    EXPLAIN = "explain"
    GENERAL_CHAT = "general_chat"
    UNKNOWN = "unknown"


@dataclass
class CanvasCommand:
    """A command to be sent to the frontend canvas"""
    type: str  # e.g., "canvas.add_node", "canvas.remove_node", etc.
    payload: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "payload": self.payload}


@dataclass
class AgentResponse:
    """Response from the skill editor agent"""
    message: str
    commands: List[CanvasCommand] = field(default_factory=list)
    intent: IntentType = IntentType.GENERAL_CHAT
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "commands": [cmd.to_dict() for cmd in self.commands],
            "intent": self.intent.value,
            "metadata": self.metadata,
        }


# Node type definitions for the skill editor
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
        "description": "Conditional branching node",
        "has_inputs": True,
        "has_outputs": True,
        "config_schema": {
            "condition": "string",
            "true_branch": "string",
            "false_branch": "string",
        }
    },
    "loop": {
        "description": "Loop node for iterative processing",
        "has_inputs": True,
        "has_outputs": True,
        "config_schema": {
            "max_iterations": "number",
            "condition": "string",
        }
    },
}


# ============================================================
# System Prompts
# ============================================================

SYSTEM_PROMPT = """You are an AI assistant specialized in helping users create and edit flowgram workflows.

A flowgram is a visual workflow consisting of nodes and edges:
- **Nodes** represent actions (LLM calls, tool calls, conditions, etc.)
- **Edges** connect nodes to define the flow of execution

Available node types:
{node_types}

Current canvas state:
{canvas_context}

Your capabilities:
1. **Create flowgrams**: Design complete workflows based on user descriptions
2. **Add nodes**: Add specific nodes to the canvas
3. **Connect nodes**: Create edges between nodes
4. **Modify nodes**: Update node configurations
5. **Explain**: Explain what a workflow does or how to build one
6. **Run/Debug**: Help users run and debug their workflows

When generating flowgram structures, output them in this JSON format:
```json
{{
  "nodes": [
    {{"id": "node_1", "type": "start", "label": "Start", "position": {{"x": 100, "y": 100}}}},
    {{"id": "node_2", "type": "llm", "label": "Process", "position": {{"x": 100, "y": 200}}, "config": {{...}}}}
  ],
  "edges": [
    {{"source": "node_1", "target": "node_2"}}
  ]
}}
```

Be helpful, concise, and provide actionable suggestions. When users describe what they want to build, 
translate that into concrete flowgram structures they can use.
"""

INTENT_CLASSIFICATION_PROMPT = """Classify the user's intent from their message.

User message: {user_message}

Canvas context (current state):
{canvas_context}

Classify into one of these intents:
- create_flowgram: User wants to create a new workflow from scratch
- add_node: User wants to add a specific node
- remove_node: User wants to remove a node
- connect_nodes: User wants to connect existing nodes
- modify_node: User wants to change a node's configuration
- run_flowgram: User wants to run/execute the workflow
- debug_flowgram: User wants to debug or step through the workflow
- explain: User wants explanation about workflows or nodes
- general_chat: General conversation or questions

Respond with ONLY the intent name, nothing else.
"""


# ============================================================
# Skill Editor Agent Class
# ============================================================

class SkillEditorAgent:
    """
    Agent for processing skill editor chat messages.
    
    This agent:
    1. Classifies user intent
    2. Generates appropriate responses
    3. Creates canvas commands when needed
    4. Maintains conversation context
    """
    
    def __init__(self, llm=None):
        """
        Initialize the skill editor agent.
        
        Args:
            llm: LangChain LLM instance. If None, will use default from settings.
        """
        self._llm = llm
        self._conversation_history: List[Dict[str, str]] = []
        logger.info("[SkillEditorAgent] Initialized")
    
    @property
    def llm(self):
        """Lazy load LLM from settings if not provided"""
        if self._llm is None:
            try:
                self._llm = self._load_llm_from_settings()
                logger.info("[SkillEditorAgent] Loaded LLM from settings")
            except Exception as e:
                logger.error(f"[SkillEditorAgent] Failed to load LLM: {e}")
                raise
        return self._llm
    
    def _load_llm_from_settings(self):
        """Load LLM instance from application settings"""
        try:
            from app_context import AppContext
            from agent.ec_skills.llm_utils.llm_utils import select_or_create_llm
            
            mainwin = AppContext.get_main_window()
            if mainwin is None:
                raise RuntimeError("Main window not available")
            
            # Get LLM providers and default from settings
            llm_providers = getattr(mainwin, 'llm_providers', [])
            default_llm = getattr(mainwin, 'default_llm', None)
            config_manager = getattr(mainwin, 'config_manager', None)
            
            if not llm_providers:
                raise RuntimeError("No LLM providers configured")
            
            # Use the standard LLM selection logic
            llm_instance = select_or_create_llm(
                default_llm=default_llm,
                llm_providers=llm_providers,
                config_manager=config_manager,
                allow_fallback=True
            )
            
            if llm_instance is None:
                raise RuntimeError("Failed to create LLM instance")
            
            return llm_instance
            
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Error loading LLM: {e}")
            # Try fallback to a simple ChatOpenAI if available
            try:
                from langchain_openai import ChatOpenAI
                import os
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    logger.info("[SkillEditorAgent] Using fallback OpenAI LLM")
                    return ChatOpenAI(model="gpt-4o-mini", api_key=api_key)
            except Exception:
                pass
            raise
    
    def _format_node_types(self) -> str:
        """Format node types for the system prompt"""
        lines = []
        for name, info in NODE_TYPES.items():
            lines.append(f"- **{name}**: {info['description']}")
        return "\n".join(lines)
    
    def _format_canvas_context(self, canvas_context: Optional[Dict]) -> str:
        """Format canvas context for prompts"""
        if not canvas_context:
            return "Empty canvas (no nodes or edges)"
        
        nodes = canvas_context.get("nodes", [])
        edges = canvas_context.get("edges", [])
        
        if not nodes:
            return "Empty canvas (no nodes or edges)"
        
        lines = [f"Nodes ({len(nodes)}):"]
        for node in nodes[:10]:  # Limit to first 10 nodes
            lines.append(f"  - {node.get('id')}: {node.get('type')} ({node.get('label', 'unnamed')})")
        
        if len(nodes) > 10:
            lines.append(f"  ... and {len(nodes) - 10} more nodes")
        
        lines.append(f"\nEdges ({len(edges)}):") 
        for edge in edges[:10]:
            lines.append(f"  - {edge.get('source')} → {edge.get('target')}")
        
        if len(edges) > 10:
            lines.append(f"  ... and {len(edges) - 10} more edges")
        
        return "\n".join(lines)
    
    async def classify_intent(self, message: str, canvas_context: Optional[Dict] = None) -> IntentType:
        """
        Classify the user's intent from their message.
        
        Args:
            message: User's chat message
            canvas_context: Current canvas state
            
        Returns:
            Classified intent type
        """
        logger.debug(f"[SkillEditorAgent] Classifying intent for message: {message[:50]}...")
        try:
            prompt = INTENT_CLASSIFICATION_PROMPT.format(
                user_message=message,
                canvas_context=self._format_canvas_context(canvas_context)
            )
            
            # Use LLM to classify intent
            logger.debug("[SkillEditorAgent] Invoking LLM for intent classification")
            response = await self._invoke_llm_async(prompt)
            intent_str = response.strip().lower()
            logger.debug(f"[SkillEditorAgent] LLM returned intent: {intent_str}")
            
            # Map to IntentType
            intent_map = {
                "create_flowgram": IntentType.CREATE_FLOWGRAM,
                "add_node": IntentType.ADD_NODE,
                "remove_node": IntentType.REMOVE_NODE,
                "connect_nodes": IntentType.CONNECT_NODES,
                "modify_node": IntentType.MODIFY_NODE,
                "run_flowgram": IntentType.RUN_FLOWGRAM,
                "debug_flowgram": IntentType.DEBUG_FLOWGRAM,
                "explain": IntentType.EXPLAIN,
                "general_chat": IntentType.GENERAL_CHAT,
            }
            
            return intent_map.get(intent_str, IntentType.UNKNOWN)
            
        except Exception as e:
            logger.error(f"[SkillEditorAgent] Intent classification failed: {e}")
            return IntentType.UNKNOWN
    
    async def _invoke_llm_async(self, prompt: str) -> str:
        """Invoke LLM asynchronously"""
        logger.debug(f"[SkillEditorAgent] _invoke_llm_async called, prompt length: {len(prompt)}")
        try:
            # Try async invoke first
            if hasattr(self.llm, 'ainvoke'):
                logger.debug("[SkillEditorAgent] Using async LLM invocation (ainvoke)")
                response = await self.llm.ainvoke(prompt)
                result = response.content if hasattr(response, 'content') else str(response)
                logger.debug(f"[SkillEditorAgent] LLM response length: {len(result)}")
                return result
            else:
                # Fallback to sync
                logger.debug("[SkillEditorAgent] Falling back to sync LLM invocation")
                from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
                response = self.llm.invoke(prompt)
                result = response.content if hasattr(response, 'content') else str(response)
                logger.debug(f"[SkillEditorAgent] LLM response length: {len(result)}")
                return result
        except Exception as e:
            logger.error(f"[SkillEditorAgent] LLM invocation failed: {e}")
            raise
    
    async def _stream_llm_async(self, prompt: str):
        """Stream LLM response asynchronously, yielding chunks"""
        logger.debug(f"[SkillEditorAgent] _stream_llm_async called, prompt length: {len(prompt)}")
        chunk_count = 0
        try:
            # Try async streaming first
            if hasattr(self.llm, 'astream'):
                logger.debug("[SkillEditorAgent] Using async LLM streaming (astream)")
                async for chunk in self.llm.astream(prompt):
                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if content:
                        chunk_count += 1
                        yield content
                logger.debug(f"[SkillEditorAgent] Streaming complete, yielded {chunk_count} chunks")
            elif hasattr(self.llm, 'stream'):
                # Fallback to sync streaming
                logger.debug("[SkillEditorAgent] Falling back to sync LLM streaming")
                for chunk in self.llm.stream(prompt):
                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if content:
                        chunk_count += 1
                        yield content
                logger.debug(f"[SkillEditorAgent] Streaming complete, yielded {chunk_count} chunks")
            else:
                # No streaming support, yield full response
                logger.warning("[SkillEditorAgent] LLM does not support streaming, falling back to full response")
                response = await self._invoke_llm_async(prompt)
                yield response
        except Exception as e:
            logger.error(f"[SkillEditorAgent] LLM streaming failed after {chunk_count} chunks: {e}")
            raise
    
    def _invoke_llm_sync(self, prompt: str) -> str:
        """Invoke LLM synchronously"""
        try:
            response = self.llm.invoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"[SkillEditorAgent] LLM invocation failed: {e}")
            raise
    
    def _extract_flowgram_from_response(self, response: str) -> Optional[Dict]:
        """Extract flowgram JSON from LLM response"""
        logger.debug(f"[SkillEditorAgent] Extracting flowgram from response (length: {len(response)})")
        try:
            # Look for JSON block in response
            import re
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                flowgram = json.loads(json_match.group(1))
                logger.info(f"[SkillEditorAgent] Extracted flowgram from JSON block: {len(flowgram.get('nodes', []))} nodes, {len(flowgram.get('edges', []))} edges")
                return flowgram
            
            # Try to find raw JSON
            json_match = re.search(r'\{[\s\S]*"nodes"[\s\S]*\}', response)
            if json_match:
                flowgram = json.loads(json_match.group(0))
                logger.info(f"[SkillEditorAgent] Extracted flowgram from raw JSON: {len(flowgram.get('nodes', []))} nodes, {len(flowgram.get('edges', []))} edges")
                return flowgram
            
            logger.debug("[SkillEditorAgent] No flowgram JSON found in response")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"[SkillEditorAgent] Failed to parse flowgram JSON: {e}")
            return None
    
    def _generate_canvas_commands(self, flowgram: Dict) -> List[CanvasCommand]:
        """Generate canvas commands from a flowgram structure"""
        logger.debug(f"[SkillEditorAgent] Generating canvas commands from flowgram")
        commands = []
        
        # Add nodes
        for node in flowgram.get("nodes", []):
            commands.append(CanvasCommand(
                type="canvas.add_node",
                payload={
                    "nodeType": node.get("type", "llm"),
                    "position": node.get("position", {"x": 100, "y": 100}),
                    "config": {
                        "id": node.get("id"),
                        "label": node.get("label", node.get("id")),
                        **node.get("config", {})
                    }
                }
            ))
        
        # Add edges
        for edge in flowgram.get("edges", []):
            commands.append(CanvasCommand(
                type="canvas.add_edge",
                payload={
                    "sourceNodeId": edge.get("source"),
                    "targetNodeId": edge.get("target"),
                    "sourceHandle": edge.get("sourceHandle"),
                    "targetHandle": edge.get("targetHandle"),
                }
            ))
        
        return commands
    
    async def process_message(
        self,
        message: str,
        canvas_context: Optional[Dict] = None,
        session_id: Optional[str] = None
    ) -> AgentResponse:
        """
        Process a chat message and generate a response.
        
        Args:
            message: User's chat message
            canvas_context: Current canvas state (nodes, edges)
            session_id: Chat session ID for context
            
        Returns:
            AgentResponse with message and optional commands
        """
        logger.info(f"[SkillEditorAgent] Processing message: {message[:100]}...")
        
        try:
            # Classify intent
            intent = await self.classify_intent(message, canvas_context)
            logger.info(f"[SkillEditorAgent] Classified intent: {intent.value}")
            
            # Build system prompt
            system_prompt = SYSTEM_PROMPT.format(
                node_types=self._format_node_types(),
                canvas_context=self._format_canvas_context(canvas_context)
            )
            
            # Build conversation messages
            messages = [
                SystemMessage(content=system_prompt),
            ]
            
            # Add conversation history (last 5 exchanges)
            for hist in self._conversation_history[-10:]:
                if hist["role"] == "user":
                    messages.append(HumanMessage(content=hist["content"]))
                else:
                    messages.append(AIMessage(content=hist["content"]))
            
            # Add current message
            messages.append(HumanMessage(content=message))
            
            # Generate response
            response_text = await self._invoke_llm_async(
                "\n".join([f"{m.type}: {m.content}" for m in messages])
            )
            
            # Update conversation history
            self._conversation_history.append({"role": "user", "content": message})
            self._conversation_history.append({"role": "assistant", "content": response_text})
            
            # Extract flowgram and generate commands if applicable
            commands = []
            if intent in [IntentType.CREATE_FLOWGRAM, IntentType.ADD_NODE, IntentType.CONNECT_NODES]:
                flowgram = self._extract_flowgram_from_response(response_text)
                if flowgram:
                    commands = self._generate_canvas_commands(flowgram)
                    logger.info(f"[SkillEditorAgent] Generated {len(commands)} canvas commands")
            
            return AgentResponse(
                message=response_text,
                commands=commands,
                intent=intent,
                metadata={"session_id": session_id}
            )
            
        except Exception as e:
            error_msg = f"I encountered an error processing your request: {str(e)}"
            logger.error(f"[SkillEditorAgent] Error: {e}\n{traceback.format_exc()}")
            return AgentResponse(
                message=error_msg,
                intent=IntentType.UNKNOWN,
                metadata={"error": str(e)}
            )
    
    def process_message_sync(
        self,
        message: str,
        canvas_context: Optional[Dict] = None,
        session_id: Optional[str] = None
    ) -> AgentResponse:
        """
        Synchronous version of process_message.
        
        Args:
            message: User's chat message
            canvas_context: Current canvas state
            session_id: Chat session ID
            
        Returns:
            AgentResponse with message and optional commands
        """
        import asyncio
        
        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, use run_async_in_sync
                from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
                return run_async_in_sync(
                    self.process_message(message, canvas_context, session_id)
                )
            else:
                return loop.run_until_complete(
                    self.process_message(message, canvas_context, session_id)
                )
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(
                self.process_message(message, canvas_context, session_id)
            )
    
    async def process_message_streaming(
        self,
        message: str,
        canvas_context: Optional[Dict] = None,
        session_id: Optional[str] = None,
        on_chunk: Optional[callable] = None
    ) -> AgentResponse:
        """
        Process a chat message with streaming response.
        
        Args:
            message: User's chat message
            canvas_context: Current canvas state
            session_id: Chat session ID
            on_chunk: Callback function called with each chunk (chunk: str, index: int)
            
        Returns:
            AgentResponse with complete message and optional commands
        """
        logger.info(f"[SkillEditorAgent] Processing message (streaming): {message[:100]}...")
        
        try:
            # Classify intent
            intent = await self.classify_intent(message, canvas_context)
            logger.info(f"[SkillEditorAgent] Classified intent: {intent.value}")
            
            # Build system prompt
            system_prompt = SYSTEM_PROMPT.format(
                node_types=self._format_node_types(),
                canvas_context=self._format_canvas_context(canvas_context)
            )
            
            # Build conversation messages
            messages = [
                SystemMessage(content=system_prompt),
            ]
            
            # Add conversation history (last 5 exchanges)
            for hist in self._conversation_history[-10:]:
                if hist["role"] == "user":
                    messages.append(HumanMessage(content=hist["content"]))
                else:
                    messages.append(AIMessage(content=hist["content"]))
            
            # Add current message
            messages.append(HumanMessage(content=message))
            
            # Build prompt string
            prompt = "\n".join([f"{m.type}: {m.content}" for m in messages])
            
            # Stream response
            full_response = []
            chunk_index = 0
            
            async for chunk in self._stream_llm_async(prompt):
                full_response.append(chunk)
                if on_chunk:
                    try:
                        on_chunk(chunk, chunk_index)
                    except Exception as e:
                        logger.warning(f"[SkillEditorAgent] Chunk callback error: {e}")
                chunk_index += 1
            
            response_text = "".join(full_response)
            
            # Update conversation history
            self._conversation_history.append({"role": "user", "content": message})
            self._conversation_history.append({"role": "assistant", "content": response_text})
            
            # Extract flowgram and generate commands if applicable
            commands = []
            if intent in [IntentType.CREATE_FLOWGRAM, IntentType.ADD_NODE, IntentType.CONNECT_NODES]:
                flowgram = self._extract_flowgram_from_response(response_text)
                if flowgram:
                    commands = self._generate_canvas_commands(flowgram)
                    logger.info(f"[SkillEditorAgent] Generated {len(commands)} canvas commands")
            
            return AgentResponse(
                message=response_text,
                commands=commands,
                intent=intent,
                metadata={"session_id": session_id, "streamed": True}
            )
            
        except Exception as e:
            error_msg = f"I encountered an error processing your request: {str(e)}"
            logger.error(f"[SkillEditorAgent] Error: {e}\n{traceback.format_exc()}")
            return AgentResponse(
                message=error_msg,
                intent=IntentType.UNKNOWN,
                metadata={"error": str(e)}
            )
    
    def clear_history(self):
        """Clear conversation history"""
        self._conversation_history = []
        logger.info("[SkillEditorAgent] Conversation history cleared")


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
