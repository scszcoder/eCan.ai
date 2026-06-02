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

# ---------------------------------------------------------------------------
# Log rotation sibling detection — for multi-part runtime logs
# (e.g., eCan.log + eCan.log.1 + eCan.log.2 + eCan.log.3)
# ---------------------------------------------------------------------------
import os
import re
from pathlib import Path as _Path

# Maximum age gap between siblings to be considered "same run" (seconds).
# Sliding-window: a sibling is included if its mtime is within this many
# seconds of any other already-included sibling's mtime.
_ROTATION_MTIME_WINDOW_SECS = 24 * 60 * 60   # 24 hours

# Cap to avoid pulling in huge archives if the dir has dozens of rotations.
_ROTATION_MAX_FILES = 8

# Section marker prepended to each sibling in the concatenated upload — lets
# the LLM see exactly which file each line came from.
_ROTATION_SECTION_HDR = "\n\n========== {fname} (mtime={mtime}, size={size:,} bytes) ==========\n\n"


def _detect_log_rotation_siblings(picked_path: str) -> List[_Path]:
    """Return sibling rotated log files in the same dir as ``picked_path``.

    Detection: filename pattern (``{base}.log*``) + mtime sliding-window.
    Returned list is sorted by mtime ascending — chronological order suitable
    for direct concatenation. The picked file is always included.

    Example: picked='C:/Users/me/eCan.log' returns [eCan.log.3, .2, .1, eCan.log]
    sorted by their mtime (oldest first).
    """
    try:
        picked = _Path(picked_path)
        if not picked.is_file():
            return []

        parent = picked.parent
        if not parent.is_dir():
            return [picked]

        # Match `{base}.log` or `{base}.log.<N>` or `{base}.log.<date>` etc.
        # Strip rotation suffix from picked filename to find the base pattern.
        name = picked.name
        m = re.match(r"^(?P<base>.+?\.log)(?:\.[\w.-]+)?$", name, flags=re.IGNORECASE)
        if not m:
            return [picked]
        base = m.group("base")
        pattern = re.compile(rf"^{re.escape(base)}(\.[\w.-]+)?$", flags=re.IGNORECASE)

        candidates: List[_Path] = []
        for entry in parent.iterdir():
            if entry.is_file() and pattern.match(entry.name):
                candidates.append(entry)

        if not candidates:
            return [picked]

        # Build a (path, mtime) list and run the sliding-window filter
        with_mtime = sorted(
            ((p, p.stat().st_mtime) for p in candidates),
            key=lambda x: x[1],
        )
        # Always anchor on the picked file's mtime
        picked_mtime = picked.stat().st_mtime
        kept: List[_Path] = []
        for p, mt in with_mtime:
            if abs(mt - picked_mtime) <= _ROTATION_MTIME_WINDOW_SECS:
                kept.append(p)
            else:
                # Also keep if it's within window of any already-kept sibling
                if kept and any(
                    abs(mt - kp.stat().st_mtime) <= _ROTATION_MTIME_WINDOW_SECS for kp in kept
                ):
                    kept.append(p)

        if picked not in kept:
            kept.append(picked)

        # Cap at _ROTATION_MAX_FILES, preferring most recent
        if len(kept) > _ROTATION_MAX_FILES:
            kept = sorted(kept, key=lambda p: p.stat().st_mtime, reverse=True)[:_ROTATION_MAX_FILES]

        return sorted(kept, key=lambda p: p.stat().st_mtime)
    except Exception as e:
        logger.warning(f"[SkillEditorChat] Rotation sibling detection failed: {e}")
        try:
            return [_Path(picked_path)]
        except Exception:
            return []


def _read_and_concat_rotation_siblings(picked_path: str) -> tuple:
    """Return (concatenated_bytes, [(filename, size, mtime), ...]).

    Each sibling is prefixed with a section marker so the LLM can see file
    boundaries. Files are concatenated in chronological order (oldest first),
    matching the natural reading order of a continuous run.
    """
    siblings = _detect_log_rotation_siblings(picked_path)
    if not siblings:
        return b"", []

    parts: List[bytes] = []
    summary: List[tuple] = []
    for p in siblings:
        try:
            stat = p.stat()
            data = p.read_bytes()
            hdr = _ROTATION_SECTION_HDR.format(
                fname=p.name,
                mtime=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                size=stat.st_size,
            )
            parts.append(hdr.encode("utf-8"))
            parts.append(data)
            summary.append((p.name, stat.st_size, stat.st_mtime))
        except Exception as e:
            logger.warning(f"[SkillEditorChat] Failed to read sibling {p}: {e}")

    return b"".join(parts), summary


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

                # --- Log file upload interception ---
                # If the cloud Lambda returned a presigned upload URL, upload
                # the local file to S3 and send a follow-up message so the
                # Lambda can read it and proceed with analysis.
                _cr_msg = cloud_result.get("message") or {}
                _cr_meta = _cr_msg.get("metadata") if isinstance(_cr_msg, dict) else None
                _upload_req = _cr_meta.get("log_upload_request") if isinstance(_cr_meta, dict) else None
                if isinstance(_upload_req, dict):
                    _local_path = _upload_req.get("local_file_path", "")
                    _upload_url = _upload_req.get("upload_url", "")
                    if _local_path and _upload_url:
                        # Helper: push a progress message to the chat panel
                        def _push_upload_status(text: str, as_chunk: bool = False):
                            try:
                                from gui.ipc.api import IPCAPI
                                _ipc = IPCAPI.get_instance()
                                if as_chunk:
                                    _ipc.push_skill_editor_chat_chunk(
                                        session_id=session_id,
                                        message_id="log-upload-status",
                                        chunk=text,
                                        chunk_index=0,
                                    )
                                else:
                                    _ipc.push_skill_editor_chat_done(
                                        session_id=session_id,
                                        message_id=str(uuid.uuid4()),
                                        full_content=text,
                                    )
                            except Exception:
                                pass

                        try:
                            from pathlib import Path as _P
                            _fp = _P(_local_path)
                            if _fp.is_file():
                                # Detect rotated siblings (eCan.log, .log.1, .log.2, ...)
                                # and stitch them into a single chronologically-ordered
                                # blob so the cloud agent sees the full continuous run.
                                _file_bytes, _rot_summary = _read_and_concat_rotation_siblings(_local_path)
                                if not _file_bytes:
                                    _file_bytes = _fp.read_bytes()
                                    _rot_summary = [(_fp.name, len(_file_bytes), _fp.stat().st_mtime)]
                                _size_kb = len(_file_bytes) / 1024

                                if len(_rot_summary) > 1:
                                    _siblings_list = ", ".join(f"`{n}`" for n, _, _ in _rot_summary)
                                    _push_upload_status(
                                        f"🔗 Detected {len(_rot_summary)} rotated log parts: {_siblings_list}\n"
                                        f"⬆️ Uploading stitched log ({_size_kb:,.1f} KB)...",
                                        as_chunk=True,
                                    )
                                else:
                                    _push_upload_status(
                                        f"⬆️ Uploading log file ({_size_kb:,.1f} KB)...",
                                        as_chunk=True,
                                    )

                                import requests as _http
                                _put_resp = _http.put(
                                    _upload_url,
                                    data=_file_bytes,
                                    headers={"Content-Type": "text/plain; charset=utf-8"},
                                    timeout=120,
                                )
                                if _put_resp.status_code in (200, 204):
                                    logger.info(
                                        f"[SkillEditorChat] Uploaded log file to S3 "
                                        f"({len(_file_bytes):,} bytes)"
                                    )
                                    _push_upload_status(
                                        f"\u2705 Log file uploaded successfully "
                                        f"({_size_kb:,.1f} KB). Analyzing..."
                                    )
                                    # Follow-up: trigger Lambda to read from S3 and analyze
                                    followup = relay_send_message(
                                        session_id=session_id,
                                        content="Log file uploaded successfully",
                                    )
                                    if followup is not None:
                                        cloud_result = followup
                                else:
                                    logger.warning(
                                        f"[SkillEditorChat] S3 presigned PUT failed: "
                                        f"{_put_resp.status_code}"
                                    )
                                    _push_upload_status(
                                        f"\u274C Log file upload failed (HTTP {_put_resp.status_code}). "
                                        f"Please try again."
                                    )
                            else:
                                logger.warning(
                                    f"[SkillEditorChat] Log file not found: {_local_path}"
                                )
                                _push_upload_status(
                                    f"\u274C Log file not found: `{_local_path}`\n\n"
                                    f"Please check the path and try again."
                                )
                        except Exception as _upload_err:
                            logger.warning(
                                f"[SkillEditorChat] Log upload failed: {_upload_err}"
                            )
                            _push_upload_status(
                                f"\u274C Log file upload failed: {_upload_err}"
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
                            # Forward structured data (clarification, plan,
                            # state, etc.) so the frontend handleDone can
                            # set pending states from the local-ws push.
                            ipc.push_skill_editor_chat_done(
                                session_id=session_id,
                                message_id=msg_id,
                                full_content=msg_content,
                                extra=cloud_result,
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

                # When subscription is active the real structured data
                # (plan, clarification, flowgram) MAY arrive via stream_end
                # events — but the subscription enrichment is not always
                # reliable (bare stream_end).  Include the structured data
                # in the sync response so the frontend can use whichever
                # arrives first.  The frontend dedup logic protects against
                # double-rendering.
                if sub_active:
                    msg = cloud_result.get("message") or {}
                    placeholder = {
                        "sessionId": cloud_result.get("sessionId", session_id),
                        "state": cloud_result.get("state", "processing"),
                        "intent": cloud_result.get("intent"),
                        "clarification": cloud_result.get("clarification"),
                        "plan": cloud_result.get("plan"),
                        "flowgram": cloud_result.get("flowgram"),
                        "validation": cloud_result.get("validation"),
                        "message": {
                            "id": msg.get("id") if isinstance(msg, dict) else None,
                            "role": "assistant",
                            "content": msg.get("content", "") if isinstance(msg, dict) else "",
                            "timestamp": msg.get("timestamp", int(time.time() * 1000)) if isinstance(msg, dict) else int(time.time() * 1000),
                            "metadata": msg.get("metadata") if isinstance(msg, dict) else None,
                        },
                    }
                    return create_success_response(request, placeholder)
                return create_success_response(request, cloud_result)
            else:
                logger.warning("[SkillEditorChat] Cloud send_message failed, falling back to local agent")

        # --- Local fallback ---
        # Ensure canvas_context is parsed (may still be a JSON string)
        local_canvas = canvas_context
        if isinstance(local_canvas, str):
            try:
                import json as _json
                local_canvas = _json.loads(local_canvas)
            except (ValueError, TypeError):
                local_canvas = None
        # Inject nodes from local disk if canvas is empty but has skillName
        if isinstance(local_canvas, dict) and not local_canvas.get("nodes"):
            skill_name = local_canvas.get("skillName")
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
                            local_canvas["nodes"] = local_nodes
                            local_canvas["edges"] = local_edges
                            logger.info(f"[SkillEditorChat] Local fallback: injected {len(local_nodes)} nodes from disk: {skill_name}")
                except Exception as e:
                    logger.warning(f"[SkillEditorChat] Local fallback: failed to inject nodes: {e}")

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
            agent_result = _process_chat_message(session, user_message, local_canvas, clarification_responses, on_event=on_event)
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


# ---------------------------------------------------------------------------
# Cloud-proposed CLI command execution (desktop only)
#
# The cloud helper agent proposes an `ecan` CLI command for agent/task CRUD.
# The client runs it locally via this handler; the (sync-capable) CLI applies
# it to the local DB and propagates to cloud, then the client posts the result
# back to the agent as context. We invoke a fixed argv list (no shell) built
# from the STRUCTURED proposal — never the raw LLM string — so it is
# injection-safe.
# ---------------------------------------------------------------------------
_CLI_VERB = {"create": "add", "modify": "update", "remove": "remove", "query": "get", "list": "list"}
_CLI_FLAG = {"name": "-n", "description": "-d", "status": "-s", "priority": "-p"}


def _repo_root_for_cli() -> str:
    """Absolute path to the repo root where ecan_cli.py lives."""
    return str(_Path(__file__).resolve().parents[3])


def _build_ecan_argv(proposal: Dict[str, Any]) -> Optional[List[str]]:
    """Map a structured proposal {action, resource, target, fields} to `ecan` argv.

    Returns None when the proposal is unsupported or missing required parts.
    """
    action = str((proposal or {}).get("action") or "").lower()
    resource = str((proposal or {}).get("resource") or "").lower()
    target = (proposal or {}).get("target")
    fields = (proposal or {}).get("fields") or {}

    # Prompts are file-backed (group `prompts`, name/content fields). Modify maps
    # to `add --overwrite` since the CLI has no separate non-interactive update.
    if resource == "prompt":
        if action == "list":
            return ["prompts", "list"]
        if action == "query":
            return ["prompts", "get", str(target)] if target else None
        if action == "remove":
            return ["prompts", "remove", str(target), "-f"] if target else None
        if action == "create":
            name, content = fields.get("name"), fields.get("content")
            return ["prompts", "add", "-n", str(name), "-c", str(content)] if (name and content) else None
        if action == "modify":
            name = target or fields.get("name")
            content = fields.get("content")
            return ["prompts", "add", "-n", str(name), "-c", str(content), "--overwrite"] if (name and content) else None
        return None

    if resource not in ("agent", "task"):
        return None
    verb = _CLI_VERB.get(action)
    if not verb:
        return None
    group = "agents" if resource == "agent" else "tasks"
    argv: List[str] = [group, verb]

    if action == "list":
        return argv
    if action in ("query", "remove"):
        if not target:
            return None
        argv.append(str(target))
        if action == "remove":
            argv.append("-f")  # the user already confirmed in the UI
        return argv
    if action == "create":
        name = fields.get("name")
        if not name:
            return None
        argv += ["-n", str(name)]
        if fields.get("description"):
            argv += ["-d", str(fields["description"])]
        return argv
    if action == "modify":
        if not target:
            return None
        argv.append(str(target))
        for key, val in fields.items():
            if val is None:
                continue
            flag = _CLI_FLAG.get(key)
            if flag:
                argv += [flag, str(val)]
        return argv if len(argv) > 3 else None
    return None


def _ensure_cli_session(user_id: str) -> None:
    """Make sure the CLI sees the GUI's logged-in user so @requires_auth passes.

    The CLI reads `.ecan_session.json` at the repo root. We refresh it with the
    current GUI user (best-effort) before running write commands.
    """
    if not user_id:
        return
    try:
        import json as _json
        from datetime import datetime as _dt
        sess_path = os.path.join(_repo_root_for_cli(), ".ecan_session.json")
        existing = {}
        if os.path.exists(sess_path):
            with open(sess_path, "r", encoding="utf-8") as f:
                existing = _json.load(f) or {}
        if existing.get("username") == user_id:
            return
        with open(sess_path, "w", encoding="utf-8") as f:
            _json.dump({"username": user_id, "logged_in_at": _dt.now().isoformat()}, f)
    except Exception as e:
        logger.warning(f"[SkillEditorChat] could not ensure CLI session: {e}")


@IPCHandlerRegistry.handler('skill_editor.chat.execute_command')
def handle_execute_command(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Run a cloud-proposed `ecan` CLI command locally and return its output.

    Params: { "proposal": {action, resource, target, fields}, "userId": str }
    """
    try:
        p = (params or {}).get("input") or params or {}
        proposal = p.get("proposal") or {}
        user_id = p.get("userId") or ""

        argv = _build_ecan_argv(proposal)
        if argv is None:
            return create_error_response(request, 'INVALID_PARAMS',
                                         "Unsupported or incomplete command proposal")

        # Write ops need CLI auth; refresh the session from the GUI user.
        if proposal.get("action") in ("create", "modify", "remove"):
            _ensure_cli_session(user_id)

        import sys as _sys
        import subprocess
        repo_root = _repo_root_for_cli()
        cli_entry = os.path.join(repo_root, "ecan_cli.py")
        cmd = [_sys.executable, cli_entry] + argv
        pretty = "ecan " + " ".join(argv)
        logger.info(f"[SkillEditorChat] Executing CLI: {pretty}")

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=repo_root)
        return create_success_response(request, {
            "success": proc.returncode == 0,
            "returnCode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": pretty,
        })
    except subprocess.TimeoutExpired:
        return create_error_response(request, 'COMMAND_TIMEOUT', "Command timed out after 120s")
    except Exception as e:
        logger.error(f"[SkillEditorChat] execute_command failed: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'COMMAND_FAILED', str(e))


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
            logger.error(f"[SkillEditorChat] Agent processing failed, using fallback: {e}\n{traceback.format_exc()}")
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


# ---------------------------------------------------------------------------
# Fallback message translations
# ---------------------------------------------------------------------------

_FALLBACK_MESSAGES = {
    'en-US': {
        'greeting': (
            "Hello! I'm your AI assistant for building workflows. "
            "Describe what you'd like to create, and I'll help you build it step by step."
        ),
        'create': (
            "I understand you want to create a workflow. To help you better, could you describe:\n\n"
            "1. **What is the main goal** of this workflow?\n"
            "2. **What inputs** does it need?\n"
            "3. **What outputs** should it produce?\n\n"
            "For example: 'Create a workflow that takes a PDF file, extracts text, and summarizes it using an LLM.'"
        ),
        'add_node': (
            "I can help you add nodes to your workflow. Available node types include:\n\n"
            "- **LLM Node**: For AI/language model processing\n"
            "- **Code Node**: For custom Python/JavaScript code\n"
            "- **HTTP Node**: For API calls\n"
            "- **Condition Node**: For branching logic\n"
            "- **Loop Node**: For iterating over data\n\n"
            "Which type of node would you like to add?"
        ),
        'canvas_context': (
            "I can see your current workflow has **{node_count} nodes** and **{edge_count} connections**. "
            "What would you like to modify or add?"
        ),
        'default': (
            "I'm here to help you build and edit workflows through conversation. "
            "You can ask me to:\n\n"
            "- **Create** a new workflow from a description\n"
            "- **Add** nodes (LLM, code, HTTP, conditions, etc.)\n"
            "- **Connect** nodes together\n"
            "- **Run** and debug your workflow\n"
            "- **Explain** what a workflow does\n\n"
            "What would you like to do?"
        ),
    },
    'zh-CN': {
        'greeting': (
            "你好！我是你的 AI 工作流助手。"
            "请描述你想创建的内容，我会一步步帮你构建。"
        ),
        'create': (
            "我了解你想创建一个工作流。为了更好地帮助你，请描述：\n\n"
            "1. **这个工作流的主要目标**是什么？\n"
            "2. 它需要**哪些输入**？\n"
            "3. 它应该产生**什么输出**？\n\n"
            "例如：'创建一个工作流，读取 PDF 文件，提取文本，并使用 LLM 进行摘要。'"
        ),
        'add_node': (
            "我可以帮你向工作流添加节点。可用的节点类型包括：\n\n"
            "- **LLM 节点**：用于 AI / 大语言模型处理\n"
            "- **代码节点**：用于自定义 Python/JavaScript 代码\n"
            "- **HTTP 节点**：用于 API 调用\n"
            "- **条件节点**：用于分支逻辑\n"
            "- **循环节点**：用于数据迭代\n\n"
            "你想添加哪种类型的节点？"
        ),
        'canvas_context': (
            "我可以看到你当前的工作流有 **{node_count} 个节点**和 **{edge_count} 个连接**。"
            "你想修改或添加什么？"
        ),
        'default': (
            "我可以通过对话帮你构建和编辑工作流。"
            "你可以让我：\n\n"
            "- **创建**一个新的工作流\n"
            "- **添加**节点（LLM、代码、HTTP、条件等）\n"
            "- **连接**节点\n"
            "- **运行**和调试工作流\n"
            "- **解释**工作流的功能\n\n"
            "你想做什么？"
        ),
    },
}


def _get_fallback_lang() -> str:
    """Detect language for fallback messages (cached after first call)."""
    if not hasattr(_get_fallback_lang, '_cached'):
        try:
            from utils.i18n_helper import detect_language
            _get_fallback_lang._cached = detect_language(
                default_lang='zh-CN',
                supported_languages=list(_FALLBACK_MESSAGES.keys())
            )
        except Exception:
            _get_fallback_lang._cached = 'zh-CN'
    return _get_fallback_lang._cached


def _fb(key: str, **kwargs) -> str:
    """Get a localized fallback message by key."""
    lang = _get_fallback_lang()
    msgs = _FALLBACK_MESSAGES.get(lang, _FALLBACK_MESSAGES['zh-CN'])
    msg = msgs.get(key, _FALLBACK_MESSAGES['en-US'].get(key, key))
    if kwargs:
        return msg.format(**kwargs)
    return msg


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
    raw_content = message.content
    
    if "hello" in content or "hi" in content or "你好" in content:
        logger.debug("[SkillEditorChat] Fallback matched: greeting")
        return _fb('greeting')
    
    # Explain / question intent (must be checked BEFORE create to avoid
    # "explain" being swallowed by the create branch when "帮我" is present)
    _is_explain = (
        "explain" in content or "what does" in content or "how does" in content
        or "describe" in content or content.endswith("?")
        or any(w in raw_content for w in [
            "解释", "说明", "介绍", "描述", "原理", "什么意思", "什么作用",
            "做什么", "干什么", "干嘛", "怎么运行", "怎么工作", "如何",
        ])
        or raw_content.strip().endswith("？")
    )
    if _is_explain and canvas_context:
        nodes = canvas_context.get("nodes", [])
        edges = canvas_context.get("edges", [])
        if nodes:
            logger.debug(f"[SkillEditorChat] Fallback matched: explain with {len(nodes)} nodes")
            return _build_fallback_explain(nodes, edges, canvas_context.get("skillName", ""))
    
    if "create" in content or "build" in content or "make" in content or \
       "创建" in content or "构建" in content or "生成" in content or "新建" in content or \
       "帮我" in content or "新工作流" in content or "新的工作流" in content or \
       "做一个" in content or "做个" in content:
        logger.debug("[SkillEditorChat] Fallback matched: create/build/make")
        return _fb('create')
    
    if "node" in content or "add" in content or "节点" in content or "添加" in content:
        logger.debug("[SkillEditorChat] Fallback matched: node/add")
        return _fb('add_node')
    
    if canvas_context:
        node_count = len(canvas_context.get("nodes", []))
        edge_count = len(canvas_context.get("edges", []))
        if node_count > 0:
            logger.debug(f"[SkillEditorChat] Fallback matched: canvas context ({node_count} nodes, {edge_count} edges)")
            return _fb('canvas_context', node_count=node_count, edge_count=edge_count)
    
    logger.debug("[SkillEditorChat] Fallback matched: default response")
    return _fb('default')


def _build_fallback_explain(nodes: list, edges: list, skill_name: str) -> str:
    """Build a basic workflow description from canvas data (no LLM needed)."""
    lang = _get_fallback_lang()
    is_zh = lang.startswith("zh")

    if is_zh:
        lines = []
        if skill_name:
            lines.append(f"当前工作流 **{skill_name}** 包含 **{len(nodes)} 个节点**和 **{len(edges)} 个连接**：\n")
        else:
            lines.append(f"当前工作流包含 **{len(nodes)} 个节点**和 **{len(edges)} 个连接**：\n")

        for i, node in enumerate(nodes):
            n_type = node.get("type", "unknown")
            data = node.get("data", {}) if isinstance(node.get("data"), dict) else {}
            label = node.get("label") or data.get("label", "")
            desc = data.get("description") or data.get("prompt", "")
            if desc:
                desc = str(desc)[:120]
            tag = f"[{n_type}]"
            line = f"{i+1}. {tag} **{label}**" if label else f"{i+1}. {tag}"
            if desc:
                line += f" — {desc}"
            lines.append(line)

        if edges:
            lines.append("\n**连接关系：**")
            # Build id→label map
            id_label = {}
            for n in nodes:
                nid = n.get("id", "")
                data = n.get("data", {}) if isinstance(n.get("data"), dict) else {}
                id_label[nid] = n.get("label") or data.get("label", nid)
            for e in edges:
                src = id_label.get(e.get("source", ""), e.get("source", ""))
                tgt = id_label.get(e.get("target", ""), e.get("target", ""))
                lines.append(f"- {src} → {tgt}")

        lines.append("\n> 注意：此为基本描述。完整的 AI 分析暂时不可用，请检查网络连接或稍后重试。")
        return "\n".join(lines)
    else:
        lines = []
        if skill_name:
            lines.append(f"The workflow **{skill_name}** has **{len(nodes)} nodes** and **{len(edges)} connections**:\n")
        else:
            lines.append(f"The current workflow has **{len(nodes)} nodes** and **{len(edges)} connections**:\n")

        for i, node in enumerate(nodes):
            n_type = node.get("type", "unknown")
            data = node.get("data", {}) if isinstance(node.get("data"), dict) else {}
            label = node.get("label") or data.get("label", "")
            desc = data.get("description") or data.get("prompt", "")
            if desc:
                desc = str(desc)[:120]
            tag = f"[{n_type}]"
            line = f"{i+1}. {tag} **{label}**" if label else f"{i+1}. {tag}"
            if desc:
                line += f" — {desc}"
            lines.append(line)

        if edges:
            lines.append("\n**Connections:**")
            id_label = {}
            for n in nodes:
                nid = n.get("id", "")
                data = n.get("data", {}) if isinstance(n.get("data"), dict) else {}
                id_label[nid] = n.get("label") or data.get("label", nid)
            for e in edges:
                src = id_label.get(e.get("source", ""), e.get("source", ""))
                tgt = id_label.get(e.get("target", ""), e.get("target", ""))
                lines.append(f"- {src} → {tgt}")

        lines.append("\n> Note: This is a basic description. Full AI analysis is temporarily unavailable — please check your connection or try again later.")
        return "\n".join(lines)
