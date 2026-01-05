"""
Skill Editor Chat Handler

Dedicated IPC handlers for the skill editor chat feature.
This provides a simpler, development-focused chat interface for
AI-assisted flowgram creation and editing.

Communication flows:
1. Frontend → Backend: Chat messages, session management
2. Backend → Frontend: Canvas commands, chat responses, run controls
"""

from typing import Any, Optional, Dict, List
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid
import time
import traceback
import threading

from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.context_bridge import get_handler_context
from utils.logger_helper import logger_helper as logger


# ============================================================
# Type Definitions (mirrors TypeScript types)
# ============================================================

class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ChatMessage:
    """A single chat message"""
    id: str
    role: ChatRole
    content: str
    timestamp: int  # milliseconds
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatSession:
    """A chat session with history"""
    id: str
    name: str
    flowgram_id: Optional[str]
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "flowgramId": self.flowgram_id,
            "messages": [asdict(m) for m in self.messages],
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


# ============================================================
# Session Store (in-memory for now, can be persisted later)
# ============================================================

class SkillEditorChatStore:
    """In-memory store for chat sessions"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._sessions: Dict[str, ChatSession] = {}
                    cls._instance._active_generations: Dict[str, bool] = {}
        return cls._instance
    
    def create_session(self, name: str = "New Chat", flowgram_id: Optional[str] = None) -> ChatSession:
        """Create a new chat session"""
        session = ChatSession(
            id=str(uuid.uuid4()),
            name=name,
            flowgram_id=flowgram_id,
        )
        self._sessions[session.id] = session
        logger.info(f"[SkillEditorChat] Created session: {session.id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a session by ID"""
        return self._sessions.get(session_id)
    
    def get_all_sessions(self) -> List[ChatSession]:
        """Get all sessions"""
        return list(self._sessions.values())
    
    def add_message(self, session_id: str, message: ChatMessage) -> bool:
        """Add a message to a session"""
        session = self._sessions.get(session_id)
        if session:
            session.messages.append(message)
            session.updated_at = int(time.time() * 1000)
            # Update session name from first user message
            if message.role == ChatRole.USER and session.name == "New Chat":
                content = message.content
                session.name = content[:30] + "..." if len(content) > 30 else content
            return True
        return False
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
    
    def set_generation_active(self, session_id: str, active: bool):
        """Track active generation for cancellation"""
        self._active_generations[session_id] = active
    
    def is_generation_active(self, session_id: str) -> bool:
        """Check if generation is active for a session"""
        return self._active_generations.get(session_id, False)


# Global store instance
_chat_store = SkillEditorChatStore()


# ============================================================
# IPC Handlers
# ============================================================

@IPCHandlerRegistry.handler('skill_editor.chat.create_session')
def handle_create_session(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Create a new chat session for skill editing
    
    Args:
        request: IPC request object
        params: {
            "name": Optional[str] - Session name
            "flowgramId": Optional[str] - Associated flowgram ID
        }
    
    Returns:
        Session info with ID
    """
    try:
        logger.info(f"[SkillEditorChat] create_session called with params: {params}")
        
        name = (params or {}).get("name", "New Chat")
        flowgram_id = (params or {}).get("flowgramId")
        
        session = _chat_store.create_session(name=name, flowgram_id=flowgram_id)
        
        return create_success_response(request, {
            "session": session.to_dict(),
            "message": "Session created successfully"
        })
        
    except Exception as e:
        logger.error(f"[SkillEditorChat] Error creating session: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'SESSION_CREATE_ERROR',
            f"Error creating session: {str(e)}"
        )


@IPCHandlerRegistry.handler('skill_editor.chat.get_sessions')
def handle_get_sessions(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get all chat sessions
    
    Args:
        request: IPC request object
        params: None
    
    Returns:
        List of sessions
    """
    try:
        sessions = _chat_store.get_all_sessions()
        return create_success_response(request, {
            "sessions": [s.to_dict() for s in sessions],
            "count": len(sessions)
        })
        
    except Exception as e:
        logger.error(f"[SkillEditorChat] Error getting sessions: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'SESSION_GET_ERROR',
            f"Error getting sessions: {str(e)}"
        )


@IPCHandlerRegistry.handler('skill_editor.chat.get_history')
def handle_get_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get chat history for a session
    
    Args:
        request: IPC request object
        params: {
            "sessionId": str - Session ID
            "limit": Optional[int] - Max messages to return
            "offset": Optional[int] - Offset for pagination
        }
    
    Returns:
        List of messages
    """
    try:
        session_id = (params or {}).get("sessionId")
        if not session_id:
            return create_error_response(request, 'INVALID_PARAMS', "sessionId is required")
        
        session = _chat_store.get_session(session_id)
        if not session:
            return create_error_response(request, 'SESSION_NOT_FOUND', f"Session {session_id} not found")
        
        limit = (params or {}).get("limit")
        offset = (params or {}).get("offset", 0)
        
        messages = session.messages[offset:]
        if limit:
            messages = messages[:limit]
        
        return create_success_response(request, {
            "messages": [asdict(m) for m in messages],
            "total": len(session.messages),
            "sessionId": session_id
        })
        
    except Exception as e:
        logger.error(f"[SkillEditorChat] Error getting history: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'HISTORY_GET_ERROR',
            f"Error getting history: {str(e)}"
        )


@IPCHandlerRegistry.handler('skill_editor.chat.send_message')
def handle_send_message(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Send a chat message and get AI response
    
    This is the main entry point for chat-based skill editing.
    The handler will:
    1. Store the user message
    2. Process with LLM agent
    3. Send canvas commands as needed
    4. Return assistant response
    
    Args:
        request: IPC request object
        params: {
            "sessionId": str - Session ID
            "content": str - Message content
            "attachments": Optional[List] - File attachments
            "canvasContext": Optional[Dict] - Current canvas state
        }
    
    Returns:
        Assistant response message
    """
    try:
        session_id = (params or {}).get("sessionId")
        content = (params or {}).get("content", "")
        attachments = (params or {}).get("attachments", [])
        canvas_context = (params or {}).get("canvasContext")
        
        logger.info(f"[SkillEditorChat] send_message called - sessionId={session_id}, content_length={len(content)}, has_canvas_context={canvas_context is not None}")
        
        if not session_id:
            return create_error_response(request, 'INVALID_PARAMS', "sessionId is required")
        if not content.strip():
            return create_error_response(request, 'INVALID_PARAMS', "content is required")
        
        session = _chat_store.get_session(session_id)
        if not session:
            # Auto-create session if not exists
            session = _chat_store.create_session()
            session_id = session.id
        
        # Create and store user message
        user_message = ChatMessage(
            id=str(uuid.uuid4()),
            role=ChatRole.USER,
            content=content,
            timestamp=int(time.time() * 1000),
            attachments=attachments,
            metadata={"canvasContext": canvas_context} if canvas_context else {}
        )
        _chat_store.add_message(session_id, user_message)
        
        # Mark generation as active
        _chat_store.set_generation_active(session_id, True)
        
        try:
            # Process with LLM agent
            # TODO: Integrate with actual LLM agent for flowgram generation
            # For now, return a placeholder response
            logger.info(f"[SkillEditorChat] Processing message with LLM agent...")
            assistant_content = _process_chat_message(session, user_message, canvas_context)
            logger.info(f"[SkillEditorChat] LLM response generated, length={len(assistant_content)}")
            
            # Create and store assistant message
            assistant_message = ChatMessage(
                id=str(uuid.uuid4()),
                role=ChatRole.ASSISTANT,
                content=assistant_content,
                timestamp=int(time.time() * 1000),
            )
            _chat_store.add_message(session_id, assistant_message)
            
            logger.info(f"[SkillEditorChat] Returning response for session {session_id}")
            return create_success_response(request, {
                "message": asdict(assistant_message),
                "sessionId": session_id,
                "sessionName": session.name
            })
            
        finally:
            _chat_store.set_generation_active(session_id, False)
        
    except Exception as e:
        logger.error(f"[SkillEditorChat] Error sending message: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'MESSAGE_SEND_ERROR',
            f"Error sending message: {str(e)}"
        )


@IPCHandlerRegistry.handler('skill_editor.chat.cancel_generation')
def handle_cancel_generation(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Cancel ongoing LLM generation
    
    Args:
        request: IPC request object
        params: {
            "sessionId": str - Session ID
        }
    
    Returns:
        Cancellation status
    """
    try:
        session_id = (params or {}).get("sessionId")
        if not session_id:
            return create_error_response(request, 'INVALID_PARAMS', "sessionId is required")
        
        was_active = _chat_store.is_generation_active(session_id)
        _chat_store.set_generation_active(session_id, False)
        
        return create_success_response(request, {
            "cancelled": was_active,
            "sessionId": session_id
        })
        
    except Exception as e:
        logger.error(f"[SkillEditorChat] Error cancelling generation: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'CANCEL_ERROR',
            f"Error cancelling generation: {str(e)}"
        )


@IPCHandlerRegistry.handler('skill_editor.chat.delete_session')
def handle_delete_session(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete a chat session
    
    Args:
        request: IPC request object
        params: {
            "sessionId": str - Session ID to delete
        }
    
    Returns:
        Deletion status
    """
    try:
        session_id = (params or {}).get("sessionId")
        if not session_id:
            return create_error_response(request, 'INVALID_PARAMS', "sessionId is required")
        
        deleted = _chat_store.delete_session(session_id)
        
        return create_success_response(request, {
            "deleted": deleted,
            "sessionId": session_id
        })
        
    except Exception as e:
        logger.error(f"[SkillEditorChat] Error deleting session: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'DELETE_ERROR',
            f"Error deleting session: {str(e)}"
        )


# ============================================================
# LLM Processing
# ============================================================

# Flag to control whether to use the full LLM agent or fallback responses
USE_LLM_AGENT = True


def _process_chat_message(
    session: ChatSession,
    message: ChatMessage,
    canvas_context: Optional[Dict[str, Any]]
) -> str:
    """Process a chat message with the LLM agent
    
    Uses the SkillEditorAgent for LLM-powered responses when available,
    falls back to basic pattern matching otherwise.
    
    Args:
        session: Current chat session
        message: User message to process
        canvas_context: Current state of the canvas
    
    Returns:
        Assistant response text
    """
    if USE_LLM_AGENT:
        try:
            return _process_with_agent(session, message, canvas_context)
        except Exception as e:
            logger.warning(f"[SkillEditorChat] Agent processing failed, using fallback: {e}")
            return _process_fallback(message, canvas_context)
    else:
        return _process_fallback(message, canvas_context)


def _process_with_agent(
    session: ChatSession,
    message: ChatMessage,
    canvas_context: Optional[Dict[str, Any]]
) -> str:
    """Process message using the SkillEditorAgent with LLM"""
    try:
        from agent.skill_editor import get_skill_editor_agent
        
        agent = get_skill_editor_agent()
        logger.info(f"[SkillEditorChat] Processing with SkillEditorAgent")
        
        # Process message synchronously
        response = agent.process_message_sync(
            message=message.content,
            canvas_context=canvas_context,
            session_id=session.id
        )
        
        logger.info(f"[SkillEditorChat] Agent response intent: {response.intent.value}")
        
        # If agent generated canvas commands, send them to frontend via IPC
        if response.commands:
            logger.info(f"[SkillEditorChat] Agent generated {len(response.commands)} canvas commands")
            _send_canvas_commands(session.id, response.commands)
        
        return response.message
        
    except ImportError as e:
        logger.error(f"[SkillEditorChat] Failed to import SkillEditorAgent: {e}")
        raise
    except Exception as e:
        logger.error(f"[SkillEditorChat] Agent processing error: {e}\n{traceback.format_exc()}")
        raise


def _send_canvas_commands(session_id: str, commands: list) -> None:
    """Send canvas commands to frontend via IPC"""
    logger.info(f"[SkillEditorChat] _send_canvas_commands called with {len(commands)} commands for session={session_id}")
    try:
        from gui.ipc.api import IPCAPI
        ipc = IPCAPI.get_instance()
        
        for idx, cmd in enumerate(commands):
            cmd_dict = cmd.to_dict() if hasattr(cmd, 'to_dict') else cmd
            logger.debug(f"[SkillEditorChat] Sending command {idx+1}/{len(commands)}: {cmd_dict.get('type')}")
            ipc.push_skill_editor_canvas_command(
                session_id=session_id,
                command_type=cmd_dict.get('type', 'unknown'),
                payload=cmd_dict.get('payload', {})
            )
            logger.info(f"[SkillEditorChat] Sent canvas command: {cmd_dict.get('type')}")
        logger.info(f"[SkillEditorChat] All {len(commands)} canvas commands sent successfully")
    except Exception as e:
        logger.error(f"[SkillEditorChat] Failed to send canvas commands: {e}\n{traceback.format_exc()}")


def _process_fallback(
    message: ChatMessage,
    canvas_context: Optional[Dict[str, Any]]
) -> str:
    """Fallback processing with basic pattern matching (no LLM)"""
    logger.info(f"[SkillEditorChat] _process_fallback called - using pattern matching (no LLM)")
    content = message.content.lower()
    
    if "hello" in content or "hi" in content:
        logger.debug("[SkillEditorChat] Fallback matched: greeting")
        return "Hello! I'm your AI assistant for building workflows. Describe what you'd like to create, and I'll help you build it step by step."
    
    if "create" in content or "build" in content or "make" in content:
        logger.debug("[SkillEditorChat] Fallback matched: create/build/make")
        return (
            "I understand you want to create a workflow. To help you better, could you describe:\n\n"
            "1. **What is the main goal** of this workflow?\n"
            "2. **What inputs** does it need?\n"
            "3. **What outputs** should it produce?\n\n"
            "For example: 'Create a workflow that takes a PDF file, extracts text, and summarizes it using an LLM.'"
        )
    
    if "node" in content or "add" in content:
        logger.debug("[SkillEditorChat] Fallback matched: node/add")
        return (
            "I can help you add nodes to your workflow. Available node types include:\n\n"
            "- **LLM Node**: For AI/language model processing\n"
            "- **Code Node**: For custom Python/JavaScript code\n"
            "- **HTTP Node**: For API calls\n"
            "- **Condition Node**: For branching logic\n"
            "- **Loop Node**: For iterating over data\n\n"
            "Which type of node would you like to add?"
        )
    
    if canvas_context:
        node_count = len(canvas_context.get("nodes", []))
        edge_count = len(canvas_context.get("edges", []))
        logger.debug(f"[SkillEditorChat] Fallback matched: canvas context ({node_count} nodes, {edge_count} edges)")
        return (
            f"I can see your current workflow has **{node_count} nodes** and **{edge_count} connections**. "
            "What would you like to modify or add?"
        )
    
    logger.debug("[SkillEditorChat] Fallback matched: default response")
    return (
        "I'm here to help you build and edit workflows through conversation. "
        "You can ask me to:\n\n"
        "- **Create** a new workflow from a description\n"
        "- **Add** nodes (LLM, code, HTTP, conditions, etc.)\n"
        "- **Connect** nodes together\n"
        "- **Run** and debug your workflow\n"
        "- **Explain** what a workflow does\n\n"
        "What would you like to do?"
    )
