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

# Feature flag: when True, skill editor chat requests are relayed to
# the cloud-based SkillEditorAgent (via AppSync/Lambda) instead of
# running the local agent.  Set to False to revert to local processing.
USE_CLOUD_SKILL_EDITOR = True

_CLOUD_RELAY_AVAILABLE = False
if USE_CLOUD_SKILL_EDITOR:
    try:
        from gui.ipc.w2p_handlers.skill_editor_cloud_relay import (
            relay_create_session,
            relay_get_sessions,
            relay_get_history,
            relay_send_message,
            relay_cancel_generation,
            relay_delete_session,
        )
        _CLOUD_RELAY_AVAILABLE = True
        logger.info("[SkillEditorChat] Cloud relay mode ENABLED")
    except Exception as _import_err:
        logger.warning(f"[SkillEditorChat] Cloud relay import failed, using local agent: {_import_err}")
        _CLOUD_RELAY_AVAILABLE = False


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
    # Pipeline state persistence - survives app restarts
    pipeline_state: str = field(default="idle")
    current_plan: Optional[Dict[str, Any]] = field(default=None)
    current_request: Optional[str] = field(default=None)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "flowgramId": self.flowgram_id,
            "messages": [asdict(m) for m in self.messages],
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "pipelineState": self.pipeline_state,
            "currentPlan": self.current_plan,
            "currentRequest": self.current_request,
        }


# ============================================================
# Session Store (with disk persistence)
# ============================================================

import json
import os

MAX_SESSIONS = 50
MAX_MESSAGES_PER_SESSION = 200


def _get_chat_history_path() -> str:
    """Get the path to the chat history file"""
    try:
        from config.app_info import AppInfo
        app_info = AppInfo()
        base = getattr(app_info, "appdata_path", None) or getattr(app_info, "app_home_path", None)
        if base:
            return os.path.join(base, "skill_editor_chat_history.json")
    except Exception:
        pass
    return "skill_editor_chat_history.json"


class SkillEditorChatStore:
    """Persistent store for chat sessions - saves to disk"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._sessions: Dict[str, ChatSession] = {}
                    cls._instance._active_generations: Dict[str, bool] = {}
                    cls._instance._initialized = False
        return cls._instance
    
    def _ensure_initialized(self):
        """Load sessions from disk on first access"""
        if not self._initialized:
            self._load_from_disk()
            self._initialized = True
    
    def _load_from_disk(self):
        """Load chat sessions from disk"""
        try:
            history_path = _get_chat_history_path()
            if os.path.exists(history_path):
                with open(history_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for session_data in data.get("sessions", []):
                    messages = []
                    for msg_data in session_data.get("messages", []):
                        messages.append(ChatMessage(
                            id=msg_data.get("id", str(uuid.uuid4())),
                            role=ChatRole(msg_data.get("role", "user")),
                            content=msg_data.get("content", ""),
                            timestamp=msg_data.get("timestamp", int(time.time() * 1000)),
                            attachments=msg_data.get("attachments", []),
                            metadata=msg_data.get("metadata", {})
                        ))
                    
                    session = ChatSession(
                        id=session_data.get("id", str(uuid.uuid4())),
                        name=session_data.get("name", "Chat"),
                        flowgram_id=session_data.get("flowgramId"),
                        messages=messages,
                        created_at=session_data.get("createdAt", int(time.time() * 1000)),
                        updated_at=session_data.get("updatedAt", int(time.time() * 1000)),
                        pipeline_state=session_data.get("pipelineState", "idle"),
                        current_plan=session_data.get("currentPlan"),
                        current_request=session_data.get("currentRequest"),
                    )
                    self._sessions[session.id] = session
                
                logger.info(f"[SkillEditorChat] Loaded {len(self._sessions)} sessions from disk")
        except Exception as e:
            logger.warning(f"[SkillEditorChat] Failed to load chat history: {e}")
    
    def _save_to_disk(self):
        """Save chat sessions to disk"""
        try:
            # Enforce limits
            if len(self._sessions) > MAX_SESSIONS:
                sessions_list = sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)
                for session in sessions_list[MAX_SESSIONS:]:
                    del self._sessions[session.id]
            
            for session in self._sessions.values():
                if len(session.messages) > MAX_MESSAGES_PER_SESSION:
                    session.messages = session.messages[-MAX_MESSAGES_PER_SESSION:]
            
            history_path = _get_chat_history_path()
            dir_path = os.path.dirname(history_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            data = {
                "sessions": [s.to_dict() for s in self._sessions.values()],
                "savedAt": int(time.time() * 1000)
            }
            
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"[SkillEditorChat] Saved {len(self._sessions)} sessions to disk")
        except Exception as e:
            logger.error(f"[SkillEditorChat] Failed to save chat history: {e}")
    
    def create_session(self, name: str = "New Chat", flowgram_id: Optional[str] = None) -> ChatSession:
        """Create a new chat session"""
        self._ensure_initialized()
        session = ChatSession(
            id=str(uuid.uuid4()),
            name=name,
            flowgram_id=flowgram_id,
        )
        self._sessions[session.id] = session
        self._save_to_disk()
        logger.info(f"[SkillEditorChat] Created session: {session.id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a session by ID"""
        self._ensure_initialized()
        return self._sessions.get(session_id)
    
    def get_all_sessions(self) -> List[ChatSession]:
        """Get all sessions"""
        self._ensure_initialized()
        return list(self._sessions.values())
    
    def add_message(self, session_id: str, message: ChatMessage) -> bool:
        """Add a message to a session"""
        self._ensure_initialized()
        session = self._sessions.get(session_id)
        if session:
            session.messages.append(message)
            session.updated_at = int(time.time() * 1000)
            # Update session name from first user message
            if message.role == ChatRole.USER and session.name == "New Chat":
                content = message.content
                session.name = content[:30] + "..." if len(content) > 30 else content
            self._save_to_disk()
            return True
        return False
    
    def update_session(self, session: ChatSession):
        """Update a session and save to disk"""
        self._ensure_initialized()
        if session.id in self._sessions:
            self._sessions[session.id] = session
            self._save_to_disk()
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        self._ensure_initialized()
        if session_id in self._sessions:
            del self._sessions[session_id]
            self._save_to_disk()
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
        # Unwrap 'input' key if present (frontend sends { input: { ... } })
        p = (params or {}).get("input") or params or {}
        logger.info(f"[SkillEditorChat] create_session called with params: {p}")
        
        name = p.get("name", "New Chat")
        flowgram_id = p.get("flowgramId")

        # --- Cloud relay mode ---
        if _CLOUD_RELAY_AVAILABLE:
            cloud_result = relay_create_session(name=name, flowgram_id=flowgram_id)
            if cloud_result:
                logger.info(f"[SkillEditorChat] Cloud create_session OK: {cloud_result.get('id')}")
                return create_success_response(request, cloud_result)
            else:
                logger.warning("[SkillEditorChat] Cloud create_session failed, falling back to local")

        # --- Local fallback ---
        session = _chat_store.create_session(name=name, flowgram_id=flowgram_id)
        
        # Return session data directly (same format as Lambda)
        # Frontend expects: { id, name, flowgramId, createdAt, updatedAt }
        return create_success_response(request, session.to_dict())
        
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
        # --- Cloud relay mode ---
        if _CLOUD_RELAY_AVAILABLE:
            cloud_sessions = relay_get_sessions()
            if cloud_sessions is not None:
                logger.info(f"[SkillEditorChat] Cloud get_sessions OK: {len(cloud_sessions)} sessions")
                return create_success_response(request, {
                    "sessions": cloud_sessions,
                    "count": len(cloud_sessions)
                })
            else:
                logger.warning("[SkillEditorChat] Cloud get_sessions failed, falling back to local")

        # --- Local fallback ---
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
        # Unwrap 'input' key if present (frontend sends { input: { ... } })
        p = (params or {}).get("input") or params or {}
        session_id = p.get("sessionId")
        if not session_id:
            return create_error_response(request, 'INVALID_PARAMS', "sessionId is required")

        limit = p.get("limit")
        offset = p.get("offset", 0)

        # --- Cloud relay mode ---
        if _CLOUD_RELAY_AVAILABLE:
            cloud_history = relay_get_history(session_id, limit=limit, offset=offset)
            if cloud_history is not None:
                logger.info(f"[SkillEditorChat] Cloud get_history OK for session={session_id}")
                return create_success_response(request, cloud_history)
            else:
                logger.warning("[SkillEditorChat] Cloud get_history failed, falling back to local")

        # --- Local fallback ---
        session = _chat_store.get_session(session_id)
        if not session:
            return create_error_response(request, 'SESSION_NOT_FOUND', f"Session {session_id} not found")
        
        limit = p.get("limit")
        offset = p.get("offset", 0)
        
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


@IPCHandlerRegistry.background_handler('skill_editor.chat.send_message')
def handle_send_message(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Send a chat message and get AI response
    
    This is the main entry point for chat-based skill editing.
    The handler will:
    1. Store the user message
    2. Process with LLM agent (planning + code generation)
    3. Send canvas commands as needed
    4. Return assistant response with optional clarification/plan/flowgram
    
    Args:
        request: IPC request object
        params: {
            "sessionId": str - Session ID
            "content": str - Message content
            "attachments": Optional[List] - File attachments
            "canvasContext": Optional[Dict] - Current canvas state
            "clarificationResponses": Optional[Dict] - Answers to clarification questions
        }
    
    Returns:
        Assistant response with message, clarification, plan, flowgram, validation
    """
    try:
        # Unwrap 'input' key if present (frontend sends { input: { ... } })
        p = (params or {}).get("input") or params or {}
        session_id = p.get("sessionId")
        content = p.get("content", "")
        attachments = p.get("attachments", [])
        canvas_context = p.get("canvasContext")
        clarification_responses = p.get("clarificationResponses")
        
        logger.info(f"[SkillEditorChat] send_message called - sessionId={session_id}, content_length={len(content)}, has_canvas_context={canvas_context is not None}, has_clarification_responses={clarification_responses is not None}")
        
        if not session_id:
            return create_error_response(request, 'INVALID_PARAMS', "sessionId is required")
        if not content.strip():
            return create_error_response(request, 'INVALID_PARAMS', "content is required")

        # --- Cloud relay mode ---
        if _CLOUD_RELAY_AVAILABLE:
            logger.info(f"[SkillEditorChat] Relaying send_message to cloud for session={session_id}")
            # Parse canvas_context / clarification_responses if they are JSON strings
            parsed_canvas = canvas_context
            if isinstance(parsed_canvas, str):
                try:
                    import json as _json
                    parsed_canvas = _json.loads(parsed_canvas)
                except (ValueError, TypeError):
                    pass
            parsed_clarification = clarification_responses
            if isinstance(parsed_clarification, str):
                try:
                    import json as _json
                    parsed_clarification = _json.loads(parsed_clarification)
                except (ValueError, TypeError):
                    pass

            # When canvas has 0 nodes but a skillName, inject nodes/edges from the local
            # skill JSON so the cloud Lambda can parse them (the skill may only exist locally).
            if isinstance(parsed_canvas, dict) and not parsed_canvas.get("nodes"):
                skill_name = parsed_canvas.get("skillName")
                if skill_name:
                    try:
                        from agent.ec_skills.extern_skills.extern_skills import user_skills_root
                        sdir = f"{skill_name}_skill" if not skill_name.endswith("_skill") else skill_name
                        skill_json_path = user_skills_root() / sdir / "diagram_dir" / f"{sdir}.json"
                        if skill_json_path.exists():
                            import json as _json
                            local_skill = _json.loads(skill_json_path.read_text(encoding="utf-8"))
                            wf = local_skill.get("workFlow", {})
                            local_nodes = wf.get("nodes", [])
                            local_edges = wf.get("edges", [])
                            if local_nodes:
                                parsed_canvas["nodes"] = local_nodes
                                parsed_canvas["edges"] = local_edges
                                logger.info(f"[SkillEditorChat] Injected {len(local_nodes)} nodes from local skill: {skill_name}")
                    except Exception as e:
                        logger.warning(f"[SkillEditorChat] Failed to inject local skill nodes: {e}")

            cloud_result = relay_send_message(
                session_id=session_id,
                content=content,
                attachments=attachments if attachments else None,
                canvas_context=parsed_canvas if isinstance(parsed_canvas, dict) else None,
                clarification_responses=parsed_clarification if isinstance(parsed_clarification, dict) else None,
                flowgram_id=p.get("flowgramId"),
            )
            if cloud_result is not None:
                logger.info(
                    f"[SkillEditorChat] Cloud send_message OK: state={cloud_result.get('state')}, "
                    f"intent={cloud_result.get('intent')}"
                )

                # Push result to frontend.  If the AppSync subscription client
                # is running it already relays stream_chunk / stream_end events
                # from the cloud in real time — pushing a SECOND stream_end here
                # would corrupt the frontend's streaming state machine.
                # Only push from the synchronous cloud relay response when the
                # subscription is NOT active (fallback path).
                try:
                    sub_active = False
                    try:
                        from gui.ipc.appsync_subscription_client import appsync_sub_client
                        sub_active = appsync_sub_client.is_running
                    except Exception:
                        pass

                    if not sub_active:
                        msg = cloud_result.get("message") or {}
                        msg_content = msg.get("content", "") if isinstance(msg, dict) else ""
                        msg_id = msg.get("id", str(uuid.uuid4())) if isinstance(msg, dict) else str(uuid.uuid4())

                        from gui.ipc.api import IPCAPI
                        ipc = IPCAPI.get_instance()

                        if cloud_result.get("state") == "processing":
                            ipc.push_skill_editor_chat_chunk(
                                session_id=session_id,
                                message_id=msg_id,
                                chunk=msg_content,
                                chunk_index=0,
                            )
                        else:
                            ipc.push_skill_editor_chat_done(
                                session_id=session_id,
                                message_id=msg_id,
                                full_content=msg_content,
                            )

                        # Forward flowgram as a canvas command so the local frontend loads it
                        flowgram_data = cloud_result.get("flowgram")
                        if flowgram_data:
                            ipc.push_skill_editor_canvas_command(
                                session_id=session_id,
                                command_type="canvas.load_flowgram_data",
                                payload={"flowgram": flowgram_data},
                            )
                    else:
                        logger.debug(
                            f"[SkillEditorChat] Subscription active — skipping duplicate "
                            f"push for state={cloud_result.get('state')}"
                        )
                except Exception as relay_push_err:
                    logger.debug(f"[SkillEditorChat] Cloud relay push to frontend skipped: {relay_push_err}")

                # When subscription is active the real data (plan, clarification,
                # flowgram) will arrive via stream_end events.  Returning the
                # full result here would cause the frontend to render duplicate
                # messages/plans.  Return a "processing" placeholder instead.
                if sub_active:
                    msg = cloud_result.get("message") or {}
                    placeholder = {
                        "sessionId": cloud_result.get("sessionId", session_id),
                        "state": "processing",
                        "intent": cloud_result.get("intent"),
                        "message": {
                            "id": msg.get("id") if isinstance(msg, dict) else None,
                            "role": "assistant",
                            "content": "",
                            "timestamp": int(time.time() * 1000),
                            "metadata": {"placeholder": True},
                        },
                    }
                    return create_success_response(request, placeholder)
                return create_success_response(request, cloud_result)
            else:
                logger.warning("[SkillEditorChat] Cloud send_message failed, falling back to local agent")

        # --- Local fallback ---
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
            metadata={
                "canvasContext": canvas_context if canvas_context else None,
                "clarificationResponses": clarification_responses if clarification_responses else None
            }
        )
        _chat_store.add_message(session_id, user_message)
        
        # Mark generation as active
        _chat_store.set_generation_active(session_id, True)

        try:
            assistant_message_id = str(uuid.uuid4())

            chunk_index = 0
            def on_event(event: Dict[str, Any]) -> None:
                nonlocal chunk_index
                try:
                    if not isinstance(event, dict):
                        return
                    event_type = event.get("type")
                    if event_type not in ["progress", "chunk"]:
                        return

                    data = event.get("data") or {}
                    chunk_text = None
                    if event_type == "progress":
                        chunk_text = data.get("message")
                    else:
                        chunk_text = data.get("content")

                    if not isinstance(chunk_text, str) or not chunk_text.strip():
                        return

                    from gui.ipc.api import IPCAPI
                    ipc = IPCAPI.get_instance()
                    ipc.push_skill_editor_chat_chunk(
                        session_id=session_id,
                        message_id=assistant_message_id,
                        chunk=chunk_text,
                        chunk_index=chunk_index,
                    )
                    chunk_index += 1
                except Exception:
                    return

            # Process with LLM agent
            logger.info(f"[SkillEditorChat] Processing message with LLM agent...")
            agent_result = _process_chat_message(session, user_message, canvas_context, clarification_responses, on_event=on_event)
            logger.info(f"[SkillEditorChat] LLM response generated, state={agent_result.get('state')}")

            try:
                from gui.ipc.api import IPCAPI
                ipc = IPCAPI.get_instance()
                ipc.push_skill_editor_chat_done(
                    session_id=session_id,
                    message_id=assistant_message_id,
                    full_content=agent_result.get("message", "") or "",
                )
            except Exception:
                pass

            # Create and store assistant message
            assistant_message = ChatMessage(
                id=assistant_message_id,
                role=ChatRole.ASSISTANT,
                content=agent_result.get("message", ""),
                timestamp=int(time.time() * 1000),
                metadata={
                    "state": agent_result.get("state"),
                    "intent": agent_result.get("intent"),
                    "hasClarification": "clarification" in agent_result,
                    "hasPlan": "plan" in agent_result,
                    "hasFlowgram": "flowgram" in agent_result,
                    "clarification": agent_result.get("clarification"),
                    "plan": agent_result.get("plan"),
                }
            )
            _chat_store.add_message(session_id, assistant_message)

            # Build response
            response_data = {
                "message": asdict(assistant_message),
                "sessionId": session_id,
                "sessionName": session.name,
                "state": agent_result.get("state", "complete"),
                "intent": agent_result.get("intent"),
            }

            # Include clarification questions if present
            if "clarification" in agent_result:
                response_data["clarification"] = agent_result["clarification"]
                logger.info(f"[SkillEditorChat] Including {len(agent_result['clarification'])} clarification questions")

            # Include plan if present
            if "plan" in agent_result:
                response_data["plan"] = agent_result["plan"]
                logger.info(f"[SkillEditorChat] Including implementation plan")

            # Include flowgram if present
            if "flowgram" in agent_result:
                response_data["flowgram"] = agent_result["flowgram"]
                logger.info(f"[SkillEditorChat] Including flowgram")

            # Include validation if present
            if "validation" in agent_result:
                response_data["validation"] = agent_result["validation"]
                logger.info(f"[SkillEditorChat] Including validation result")

            logger.info(f"[SkillEditorChat] Returning response for session {session_id}")
            return create_success_response(request, response_data)

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
        # Unwrap 'input' key if present (frontend sends { input: { ... } })
        p = (params or {}).get("input") or params or {}
        session_id = p.get("sessionId")
        if not session_id:
            return create_error_response(request, 'INVALID_PARAMS', "sessionId is required")

        # --- Cloud relay mode ---
        if _CLOUD_RELAY_AVAILABLE:
            cancelled = relay_cancel_generation(session_id)
            logger.info(f"[SkillEditorChat] Cloud cancel_generation: {cancelled}")
            return create_success_response(request, {
                "cancelled": cancelled,
                "sessionId": session_id
            })

        # --- Local fallback ---
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
        # Unwrap 'input' key if present (frontend sends { input: { ... } })
        p = (params or {}).get("input") or params or {}
        session_id = p.get("sessionId")
        if not session_id:
            return create_error_response(request, 'INVALID_PARAMS', "sessionId is required")

        # --- Cloud relay mode ---
        if _CLOUD_RELAY_AVAILABLE:
            deleted = relay_delete_session(session_id)
            logger.info(f"[SkillEditorChat] Cloud delete_session: {deleted}")
            return create_success_response(request, {
                "deleted": deleted,
                "sessionId": session_id
            })

        # --- Local fallback ---
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
    canvas_context: Optional[Dict[str, Any]],
    clarification_responses: Optional[Dict[str, List[str]]] = None,
    on_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """Process a chat message with the LLM agent
    
    Uses the SkillEditorAgent for LLM-powered responses when available,
    falls back to basic pattern matching otherwise.
    
    Args:
        session: Current chat session
        message: User message to process
        canvas_context: Current state of the canvas
        clarification_responses: Answers to previous clarification questions
    
    Returns:
        Dict with message, clarification, plan, flowgram, validation, state
    """
    if USE_LLM_AGENT:
        try:
            return _process_with_agent(session, message, canvas_context, clarification_responses, on_event=on_event)
        except Exception as e:
            logger.warning(f"[SkillEditorChat] Agent processing failed, using fallback: {e}")
            fallback_msg = _process_fallback(message, canvas_context)
            return {"message": fallback_msg, "state": "complete"}
    else:
        fallback_msg = _process_fallback(message, canvas_context)
        return {"message": fallback_msg, "state": "complete"}


def _process_with_agent(
    session: ChatSession,
    message: ChatMessage,
    canvas_context: Optional[Dict[str, Any]],
    clarification_responses: Optional[Dict[str, List[str]]] = None,
    on_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """Process message using the SkillEditorAgent with LLM
    
    Returns a dict with:
    - message: str - The response text
    - clarification: Optional[List] - Clarification questions if needed
    - plan: Optional[Dict] - Implementation plan if generated
    - flowgram: Optional[Dict] - Generated flowgram
    - validation: Optional[Dict] - Validation result
    - state: str - Pipeline state
    """
    try:
        from agent.skill_editor import get_skill_editor_agent
        from agent.skill_editor.schemas import ImplementationPlan, PlanStep
        
        agent = get_skill_editor_agent()
        
        # Restore agent state from session (survives app restarts)
        if session.pipeline_state and session.pipeline_state != "idle":
            logger.info(f"[SkillEditorChat] Restoring pipeline state from session: {session.pipeline_state}")
            agent.restore_state(
                pipeline_state=session.pipeline_state,
                current_plan=session.current_plan,
                current_request=session.current_request
            )
        
        logger.info(f"[SkillEditorChat] Processing with SkillEditorAgent")
        logger.info(f"[SkillEditorChat] Pipeline state: {agent.pipeline_state.value}")
        
        # Process message synchronously
        response = agent.process_message_sync(
            message=message.content,
            canvas_context=canvas_context,
            session_id=session.id,
            clarification_responses=clarification_responses,
            on_event=on_event,
        )
        
        logger.info(f"[SkillEditorChat] Agent response intent: {response.intent.value}")
        logger.info(f"[SkillEditorChat] Has clarification: {response.clarification is not None}")
        logger.info(f"[SkillEditorChat] Has plan: {response.plan is not None}")
        logger.info(f"[SkillEditorChat] Has flowgram: {response.flowgram is not None}")
        
        # If agent generated canvas commands, send them to frontend via IPC
        if response.commands:
            logger.info(f"[SkillEditorChat] Agent generated {len(response.commands)} canvas commands")
            _send_canvas_commands(session.id, response.commands)
        
        # Build result dict
        result = {
            "message": response.message,
            "intent": response.intent.value,
            "state": response.metadata.get("state", "complete"),
        }
        
        # Include clarification questions if present
        if response.clarification:
            result["clarification"] = [q.model_dump() for q in response.clarification]
            logger.info(f"[SkillEditorChat] Returning {len(response.clarification)} clarification questions")
        
        # Include plan if present
        if response.plan:
            result["plan"] = response.plan.model_dump()
            logger.info(f"[SkillEditorChat] Returning implementation plan")
        
        # Include flowgram if present
        if response.flowgram:
            result["flowgram"] = response.flowgram.model_dump()
            logger.info(f"[SkillEditorChat] Returning flowgram with {len(response.flowgram.nodes)} nodes")
        
        # Include validation if present
        if response.validation:
            result["validation"] = response.validation.model_dump()
            logger.info(f"[SkillEditorChat] Returning validation result: valid={response.validation.valid}")
        
        # Save agent state back to session for persistence
        session.pipeline_state = agent.pipeline_state.value
        session.current_plan = agent.current_plan.model_dump() if agent.current_plan else None
        session.current_request = agent.current_request
        _chat_store.update_session(session)
        logger.debug(f"[SkillEditorChat] Saved pipeline state to session: {session.pipeline_state}")
        
        return result
        
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
    
    # Parse canvas_context if it's a JSON string
    if isinstance(canvas_context, str):
        try:
            import json
            canvas_context = json.loads(canvas_context)
        except (json.JSONDecodeError, TypeError):
            canvas_context = None
    
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
