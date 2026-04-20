"""
Chat Tools - MCP tools for inter-agent and agent-human communication.

Tools:
- send_chat: Send a chat message to another agent or agent group
- list_chat_agents: List available agents that can receive chat messages
- get_chat_history: Get chat history for a conversation

These tools enable multi-agent communication where:
1. An agent can send messages to another agent as part of a skill workflow
2. An agent can be instructed via prompt to contact another agent
3. Agents can query available peers and chat history

References:
- ec_agent.py: a2a_send_chat_message_sync, a2a_send_chat_message_async
- llm_utils.py: find_opposite_agent, build_a2a_response_message
- my_twin_chatter_skill.py: parrot function (lines 131-142)
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger, get_traceback

# ── Dispatch tracking ──
# Prevents LLMs from skipping agent discovery and concentrating all work
# on a single "remembered" agent.  Works for any tool path (bu_send_chat
# or MCP send_chat).
#
# _sender_dispatch_state: per-sender tracking of discovery + recipients
# _last_discovery_ts:     global fallback — any list_chat_agents call
#                         within the window counts as discovery for all
#                         senders (needed because MCP list_chat_agents
#                         doesn't always carry a sender ID).
_sender_dispatch_state: Dict[str, Dict[str, Any]] = {}
_last_discovery_ts: float = 0.0

_DISPATCH_WINDOW_SEC = 30  # reset tracking after this many seconds of inactivity

# Per-(sender, customer) response dedup.  Prevents the responder LLM from
# sending multiple replies for the same customer in a single step.
_send_chat_response_dedup: Dict[str, float] = {}  # "sender|customer" → ts
_SEND_CHAT_RESPONSE_DEDUP_S = 15  # seconds


def _get_dispatch_state(sender_id: str) -> Dict[str, Any]:
    """Get or create dispatch tracking state for a sender, auto-expiring stale entries."""
    global _last_discovery_ts
    now = time.time()
    state = _sender_dispatch_state.get(sender_id)
    if state is None or (now - state.get("ts", 0)) > _DISPATCH_WINDOW_SEC:
        state = {"discovered": False, "sent_to": [], "ts": now}
        _sender_dispatch_state[sender_id] = state
    # If any list_chat_agents call happened recently, credit this sender
    if not state.get("discovered") and (now - _last_discovery_ts) < _DISPATCH_WINDOW_SEC:
        state["discovered"] = True
        state["sent_to"] = []
    state["ts"] = now
    return state


def _mark_discovery(sender_id: str, agents: List[Dict[str, Any]]):
    """Record that a sender performed agent discovery."""
    global _last_discovery_ts
    _last_discovery_ts = time.time()
    state = _get_dispatch_state(sender_id)
    state["discovered"] = True
    state["agent_count"] = len(agents)
    state["sent_to"] = []  # reset recipients on fresh discovery


# ==================== Helper Functions ====================

def _get_agent_by_id(agent_id: str, mainwin=None):
    """Get agent by ID from the application context."""
    try:
        if mainwin is not None and getattr(mainwin, "agents", None):
            return next(
                (ag for ag in mainwin.agents if getattr(getattr(ag, 'card', None), 'id', None) == agent_id),
                None,
            )
        from agent.agent_service import get_agent_by_id
        return get_agent_by_id(agent_id)
    except Exception as e:
        logger.error(f"[chat_tools] Failed to get agent by id: {e}")
        return None


def _get_agent_by_name(agent_name: str, mainwin=None):
    """Get agent by name from the application context."""
    try:
        if mainwin is None:
            from app_context import AppContext
            mainwin = AppContext.get_main_window()
        if not mainwin or not mainwin.agents:
            return None
        
        # Case-insensitive name matching
        agent_name_lower = agent_name.lower()
        for agent in mainwin.agents:
            card = getattr(agent, 'card', None)
            if card:
                name = getattr(card, 'name', '')
                if name.lower() == agent_name_lower:
                    return agent
        return None
    except Exception as e:
        logger.error(f"[chat_tools] Failed to get agent by name: {e}")
        return None


def _get_all_agents(mainwin=None) -> List[Dict[str, Any]]:
    """Get all available agents."""
    try:
        if mainwin is None:
            from app_context import AppContext
            mainwin = AppContext.get_main_window()
        if not mainwin or not mainwin.agents:
            return []
        
        agents_info = []
        for agent in mainwin.agents:
            card = getattr(agent, 'card', None)
            if card:
                # Collect task names and skill names so callers can filter
                task_names = []
                skill_names = []
                # agent.tasks is a list of task objects set at init time
                task_descriptions = []
                agent_tasks = getattr(agent, 'tasks', None)
                if isinstance(agent_tasks, list):
                    for t in agent_tasks:
                        tname = getattr(t, 'name', '')
                        if tname:
                            task_names.append(tname)
                        tdesc = getattr(t, 'description', '') or ''
                        if tdesc:
                            task_descriptions.append(tdesc)
                        # Skill name from task's skill reference
                        t_skill = getattr(t, 'skill', None)
                        sname = ''
                        if t_skill:
                            sname = getattr(t_skill, 'name', '') or ''
                        if not sname:
                            sname = getattr(t, 'skill_name', '') or ''
                        if sname and sname not in skill_names:
                            skill_names.append(sname)
                agents_info.append({
                    "id": getattr(card, 'id', ''),
                    "name": getattr(card, 'name', 'Unknown'),
                    "description": getattr(card, 'description', ''),
                    "url": getattr(card, 'url', ''),
                    "status": getattr(agent, 'status', 'unknown'),
                    "tasks": task_names,
                    "task_descriptions": task_descriptions,
                    "skills": skill_names,
                })
        return agents_info
    except Exception as e:
        logger.error(f"[chat_tools] Failed to get all agents: {e}")
        return []


def _resolve_recipient_fallback(
    recipient_agent_id: str,
    recipient_agent_name: str,
    sender_agent_id: str,
    mainwin=None,
):
    """Resolve a live recipient when a stale agent id is requested."""
    try:
        agents = getattr(mainwin, "agents", None) or []
        if not agents:
            return None

        sender_agent_id = str(sender_agent_id or "").strip()
        requested_id = str(recipient_agent_id or "").strip()
        requested_name = str(recipient_agent_name or "").strip().lower()

        candidates = []
        for agent in agents:
            card = getattr(agent, "card", None)
            if not card:
                continue
            agent_id = str(getattr(card, "id", "") or "").strip()
            if sender_agent_id and agent_id == sender_agent_id:
                continue
            candidates.append(agent)

        if not candidates:
            return None

        if requested_name:
            for agent in candidates:
                card = getattr(agent, "card", None)
                name = str(getattr(card, "name", "") or "").strip().lower()
                if name == requested_name:
                    return agent

        # If requested_id doesn't look like a real agent ID, try matching it as a name.
        # The LLM sometimes passes the agent display name as the ID field.
        if requested_id and not requested_id.startswith("agent_"):
            _id_as_name = requested_id.lower()
            for agent in candidates:
                card = getattr(agent, "card", None)
                name = str(getattr(card, "name", "") or "").strip().lower()
                if name == _id_as_name:
                    logger.info(
                        f"[chat_tools] Resolved name-as-id fallback: "
                        f"requested_id='{requested_id}' -> agent name='{name}'"
                    )
                    return agent

        # Legacy front-desk -> service-agent mapping. The service agent id is not stable
        # across sessions, but the front-desk workflow still carries the historical id.
        if requested_id == "agent_b31f281332104b93":
            for agent in candidates:
                card = getattr(agent, "card", None)
                name = str(getattr(card, "name", "") or "").strip().lower()
                if name == "joan b":
                    return agent
            for agent in candidates:
                card = getattr(agent, "card", None)
                name = str(getattr(card, "name", "") or "").strip().lower()
                if "joan" in name:
                    return agent

        if len(candidates) == 1:
            return candidates[0]

        return None
    except Exception as e:
        logger.error(f"[chat_tools] Failed recipient fallback resolution: {e}")
        return None


def _build_chat_message(
    sender_agent_id: str,
    chat_id: str,
    message_text: str,
    sender_name: str = "",
    receiver_agent_id: str = "",
    message_type: str = "text",
    attachments: List[Dict] = None,
    metadata: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Build a standardized chat message structure.
    
    Uses the same format as build_a2a_response_message in llm_utils.py.
    """
    msg_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    
    return {
        "id": str(uuid.uuid4()),
        "messages": [sender_agent_id, chat_id, msg_id, task_id, message_text],
        "attributes": {
            "params": {
                "content": {
                    "type": message_type,
                    "text": message_text,
                    "i_tag": "",
                    "dtype": message_type,
                    "card": {},
                    "code": {},
                    "form": [],
                    "notification": {},
                },
                "attachments": attachments or [],
                "chatId": chat_id,
                "senderId": sender_agent_id,
                "receiverId": receiver_agent_id,
                "i_tag": "",
                "createAt": int(time.time() * 1000),
                "senderName": sender_name,
                "status": "success",
                "role": "agent",
                "ext": "",
                "human": False,
                "transport": "a2a",
                "senderType": "agent",
                **(metadata or {}),
            }
        }
    }


def _infer_session_chat_id(message_text: str) -> str:
    """Infer a stable chat/session id from JSON message text when possible."""
    if not isinstance(message_text, str) or not message_text.strip():
        return ""
    try:
        payload = json.loads(message_text)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in ("session_id", "sessionId", "customer_id", "customerId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# ==================== Tool Implementations ====================

def send_chat(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a chat message to another agent.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - sender_agent_id: str (required) - ID of the sending agent
            - recipient_agent_id: str (optional) - ID of the recipient agent
            - recipient_agent_name: str (optional) - Name of the recipient agent
            - chat_id: str (optional) - Existing chat ID, or new one will be created
            - message: str (required) - Message text to send
            - message_type: str (optional) - "text", "form", "notification" (default: "text")
            - attachments: list (optional) - File attachments
            - async_send: bool (optional) - If True, send asynchronously (default: True)
            
    Returns:
        Dict with send result:
        {
            "success": bool,
            "message_id": str,
            "chat_id": str,
            "recipient": str,
            "timestamp": int
        }
    """
    try:
        sender_agent_id = config.get("sender_agent_id", "")
        recipient_agent_id = config.get("recipient_agent_id", "")
        recipient_agent_name = config.get("recipient_agent_name", "")
        chat_id = config.get("chat_id", "")
        message_text = config.get("message", "")
        message_type = config.get("message_type", "text")
        attachments = config.get("attachments", [])
        async_send = config.get("async_send", True)
        
        # Validate required fields
        if not sender_agent_id:
            return {
                "success": False,
                "error": "sender_agent_id is required",
                "timestamp": int(time.time() * 1000)
            }
        
        if not message_text:
            return {
                "success": False,
                "error": "message is required",
                "timestamp": int(time.time() * 1000)
            }
        
        if not recipient_agent_id and not recipient_agent_name:
            return {
                "success": False,
                "error": "Either recipient_agent_id or recipient_agent_name is required",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get sender agent
        sender_agent = _get_agent_by_id(sender_agent_id, mainwin)
        if not sender_agent:
            return {
                "success": False,
                "error": f"Sender agent not found: {sender_agent_id}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get recipient agent
        recipient_agent = None
        if recipient_agent_id:
            recipient_agent = _get_agent_by_id(recipient_agent_id, mainwin)
        if not recipient_agent and recipient_agent_name:
            recipient_agent = _get_agent_by_name(recipient_agent_name, mainwin)
        
        if not recipient_agent:
            recipient_agent = _resolve_recipient_fallback(
                recipient_agent_id=recipient_agent_id,
                recipient_agent_name=recipient_agent_name,
                sender_agent_id=sender_agent_id,
                mainwin=mainwin,
            )

        if not recipient_agent:
            return {
                "success": False,
                "error": f"Recipient agent not found: {recipient_agent_id or recipient_agent_name}",
                "timestamp": int(time.time() * 1000)
            }

        if recipient_agent:
            resolved_card = getattr(recipient_agent, "card", None)
            resolved_id = str(getattr(resolved_card, "id", "") or "").strip()
            resolved_name = str(getattr(resolved_card, "name", "") or "").strip()
            if resolved_id and resolved_id != recipient_agent_id:
                logger.info(
                    f"[send_chat] Recipient fallback resolved requested={recipient_agent_id or recipient_agent_name} "
                    f"-> live_recipient={resolved_name or resolved_id}"
                )
        
        # Get sender name
        sender_name = ""
        sender_card = getattr(sender_agent, 'card', None)
        if sender_card:
            sender_name = getattr(sender_card, 'name', '')

        resolved_sender_id = getattr(getattr(sender_agent, "card", None), "id", "") or sender_agent_id
        resolved_recipient_id = getattr(getattr(recipient_agent, "card", None), "id", "") or recipient_agent_id

        # ── Dedup: skip if same sender already sent for this customer recently ──
        # Prevents the responder LLM from sending multiple replies for the
        # same customer in a single step (duplicate tool calls).
        try:
            _msg_obj = None
            if isinstance(message_text, str):
                try:
                    _msg_obj = json.loads(message_text)
                except Exception:
                    pass
            if isinstance(_msg_obj, dict):
                _sc_cust = str(
                    _msg_obj.get("customer_id") or _msg_obj.get("customer_name") or ""
                ).strip()
                # Normalize: strip message-preview suffix ("sc|有紫色款吗？" → "sc")
                if "|" in _sc_cust:
                    _prefix = _sc_cust.split("|", 1)[0].strip()
                    if _prefix:
                        _sc_cust = _prefix
                if _sc_cust:
                    _sc_dedup_key = f"{resolved_sender_id}|{_sc_cust}"
                    _sc_now = time.time()
                    _sc_last = _send_chat_response_dedup.get(_sc_dedup_key)
                    if _sc_last is not None and (_sc_now - _sc_last) < _SEND_CHAT_RESPONSE_DEDUP_S:
                        logger.info(
                            f"[send_chat] DEDUP: skipping duplicate response for "
                            f"customer '{_sc_cust}' from sender={resolved_sender_id} "
                            f"(last sent {_sc_now - _sc_last:.1f}s ago, "
                            f"window={_SEND_CHAT_RESPONSE_DEDUP_S}s)"
                        )
                        return {
                            "success": True,
                            "message_id": "",
                            "chat_id": chat_id,
                            "recipient": resolved_recipient_id,
                            "timestamp": int(_sc_now * 1000),
                            "dedup": True,
                            "note": f"Duplicate response for '{_sc_cust}' suppressed"
                        }
                    _send_chat_response_dedup[_sc_dedup_key] = _sc_now
                    # Prune old entries
                    _sc_stale = [
                        k for k, t in _send_chat_response_dedup.items()
                        if _sc_now - t > _SEND_CHAT_RESPONSE_DEDUP_S * 3
                    ]
                    for k in _sc_stale:
                        _send_chat_response_dedup.pop(k, None)
        except Exception as _dedup_err:
            logger.debug(f"[send_chat] Response dedup check failed (non-fatal): {_dedup_err}")

        # ── General-purpose auto-distribution ──
        # When a sender targets the same recipient multiple times in quick
        # succession while peer agents with matching skills exist, transparently
        # rotate to the next unsent peer.  This prevents LLMs from concentrating
        # all work on a single "remembered" agent without requiring the LLM
        # to explicitly call list_chat_agents or implement round-robin logic.
        #
        # "Peer agents" = agents that share at least one skill with the original
        # target (i.e. they have the same capability).  This avoids redistributing
        # customer-service work to unrelated agents like "cloud B" or "Joe Bo".
        dispatch = _get_dispatch_state(resolved_sender_id)
        all_agents = _get_all_agents(mainwin)

        # Determine the target agent's skills so we can find peers
        # (agents with the same skill = same capability)
        target_skills = []
        for a in all_agents:
            if a.get("id") == resolved_recipient_id:
                target_skills = a.get("skills", [])
                break
        # Peer agents: share at least one skill with the target, excluding sender
        if target_skills:
            peer_agents = [
                a for a in all_agents
                if a.get("id") != resolved_sender_id
                and a.get("id") != resolved_recipient_id
                and any(s in target_skills for s in a.get("skills", []))
            ]
        else:
            peer_agents = []
        # Include the original target in the pool for tracking
        eligible_agents = [a for a in all_agents if a.get("id") == resolved_recipient_id] + peer_agents

        if len(eligible_agents) > 1:
            sent_list = dispatch.setdefault("sent_to", [])
            if resolved_recipient_id in sent_list:
                # This recipient was already targeted — auto-rotate to next unsent peer
                unsent = [a for a in eligible_agents if a["id"] not in sent_list]
                if unsent:
                    new_target = unsent[0]
                    old_name = getattr(getattr(recipient_agent, "card", None), "name", resolved_recipient_id)
                    logger.info(
                        f"[send_chat] Auto-distribute: {old_name} already received a message, "
                        f"redirecting to {new_target['name']} (ID: {new_target['id']})"
                    )
                    # Re-resolve recipient agent to the new target
                    recipient_agent = _get_agent_by_id(new_target["id"], mainwin)
                    resolved_recipient_id = new_target["id"]
                    if not recipient_agent:
                        logger.warning(f"[send_chat] Auto-distribute target not found: {new_target['id']}")
                # else: all peers already received — allow repeat (natural overflow)
            sent_list.append(resolved_recipient_id)

        if resolved_sender_id and resolved_recipient_id and resolved_sender_id == resolved_recipient_id:
            logger.error(
                f"[send_chat] Blocked self-send sender={resolved_sender_id} recipient={resolved_recipient_id} "
                f"chat_id={chat_id or '<pending>'} message_preview={str(message_text)[:200]}"
            )
            return {
                "success": False,
                "error": f"Self-send blocked for agent {resolved_sender_id}",
                "sender_agent_id": resolved_sender_id,
                "recipient_agent_id": resolved_recipient_id,
                "timestamp": int(time.time() * 1000),
            }

        # Generate chat_id if not provided
        if not chat_id:
            inferred_chat_id = _infer_session_chat_id(message_text)
            chat_id = inferred_chat_id or f"chat-{str(uuid.uuid4())[:8]}"
        
        # Build the message
        chat_message = _build_chat_message(
            sender_agent_id=sender_agent_id,
            chat_id=chat_id,
            message_text=message_text,
            sender_name=sender_name,
            receiver_agent_id=resolved_recipient_id,
            message_type=message_type,
            attachments=attachments,
        )
        
        # Send the message
        msg_id = chat_message["messages"][2]
        
        try:
            if async_send:
                # Non-blocking send (fire-and-forget)
                future = sender_agent.a2a_send_chat_message_async(recipient_agent, chat_message)
                logger.info(f"[send_chat] Message queued for async delivery to {recipient_agent_name or recipient_agent_id}")
            else:
                # Blocking send (wait for response)
                response = sender_agent.a2a_send_chat_message_sync(recipient_agent, chat_message)
                logger.info(f"[send_chat] Message sent synchronously to {recipient_agent_name or recipient_agent_id}")
            
            recipient_name = ""
            recipient_card = getattr(recipient_agent, 'card', None)
            if recipient_card:
                recipient_name = getattr(recipient_card, 'name', '')
            
            return {
                "success": True,
                "message_id": msg_id,
                "chat_id": chat_id,
                "recipient_id": getattr(recipient_card, 'id', '') if recipient_card else '',
                "recipient_name": recipient_name,
                "async": async_send,
                "message": f"Message sent to {recipient_name}",
                "timestamp": int(time.time() * 1000)
            }
            
        except Exception as send_err:
            logger.error(f"[send_chat] Failed to send message: {send_err}")
            return {
                "success": False,
                "error": f"Failed to send message: {str(send_err)}",
                "timestamp": int(time.time() * 1000)
            }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendChat")
        logger.error(err_trace)
        return {
            "success": False,
            "error": err_trace,
            "timestamp": int(time.time() * 1000)
        }


def list_chat_agents(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all available agents that can receive chat messages.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - exclude_self: str (optional) - Agent ID to exclude from list
            - filter_name: str (optional) - Filter agents by id or name (partial match)
            
    Returns:
        Dict with list of agents:
        {
            "success": bool,
            "agents": [
                {
                    "id": str,
                    "name": str,
                    "description": str,
                    "url": str,
                    "status": str
                }
            ],
            "count": int,
            "timestamp": int
        }
    """
    try:
        exclude_self = config.get("exclude_self", "")
        filter_name = (config.get("filter_name") or "").lower()
        filter_task_name = (config.get("filter_task_name") or "").lower()
        filter_task_description = (config.get("filter_task_description") or "").lower()

        agents = _get_all_agents(mainwin)

        # Apply filters
        if exclude_self:
            agents = [a for a in agents if a["id"] != exclude_self]

        if filter_name:
            agents = [
                a for a in agents
                if filter_name in a["name"].lower() or filter_name in a["id"].lower()
            ]

        if filter_task_name:
            agents = [
                a for a in agents
                if any(filter_task_name in t.lower() for t in a.get("tasks", []))
            ]

        if filter_task_description:
            agents = [
                a for a in agents
                if any(filter_task_description in d.lower() for d in a.get("task_descriptions", []))
            ]
        
        # Record discovery so send_chat's dispatch gate knows the caller
        # is aware of the available agent pool.
        caller_id = config.get("exclude_self") or config.get("_sender_id", "")
        if caller_id:
            _mark_discovery(caller_id, agents)
        else:
            # No sender ID available (MCP path) — record global discovery
            global _last_discovery_ts
            _last_discovery_ts = time.time()
        logger.info(
            f"[list_chat_agents] Recorded discovery: sender={caller_id or '(global)'}, "
            f"agent_count={len(agents)}"
        )

        return {
            "success": True,
            "agents": agents,
            "count": len(agents),
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        err_trace = get_traceback(e, "ErrorListChatAgents")
        logger.error(err_trace)
        return {
            "success": False,
            "error": err_trace,
            "agents": [],
            "count": 0,
            "timestamp": int(time.time() * 1000)
        }


def get_chat_history(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get chat history for a conversation.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - chat_id: str (required) - Chat ID to get history for
            - limit: int (optional) - Maximum number of messages (default: 50)
            - offset: int (optional) - Offset for pagination (default: 0)
            
    Returns:
        Dict with chat history:
        {
            "success": bool,
            "chat_id": str,
            "messages": [...],
            "count": int,
            "timestamp": int
        }
    """
    try:
        chat_id = config.get("chat_id", "")
        limit = config.get("limit", 50)
        offset = config.get("offset", 0)
        
        if not chat_id:
            return {
                "success": False,
                "error": "chat_id is required",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get chat history from database service
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if not main_window or not hasattr(main_window, 'db_chat_service'):
            return {
                "success": False,
                "error": "Chat service not available",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get chat messages
        try:
            chat_data = main_window.db_chat_service.get_chat_by_id(chat_id, True)
            
            if not chat_data or not chat_data.get("success"):
                return {
                    "success": False,
                    "error": f"Chat not found: {chat_id}",
                    "timestamp": int(time.time() * 1000)
                }
            
            messages = chat_data.get("data", {}).get("messages", [])
            
            # Apply pagination
            total_count = len(messages)
            messages = messages[offset:offset + limit]
            
            return {
                "success": True,
                "chat_id": chat_id,
                "messages": messages,
                "count": len(messages),
                "total_count": total_count,
                "offset": offset,
                "limit": limit,
                "timestamp": int(time.time() * 1000)
            }
            
        except Exception as db_err:
            logger.error(f"[get_chat_history] Database error: {db_err}")
            return {
                "success": False,
                "error": f"Failed to get chat history: {str(db_err)}",
                "timestamp": int(time.time() * 1000)
            }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGetChatHistory")
        logger.error(err_trace)
        return {
            "success": False,
            "error": err_trace,
            "timestamp": int(time.time() * 1000)
        }


# ==================== Tool Schema Functions ====================

def add_send_chat_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add send_chat tool schema to the tool schemas list."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="send_chat",
        description=(
            "<category>Communication</category><sub-category>Chat</sub-category>"
            "Send a chat message to another agent. This enables inter-agent communication "
            "where one agent can message another agent as part of a workflow or when instructed. "
            "The message is sent via the A2A (Agent-to-Agent) protocol. "
            "Use async_send=True (default) for fire-and-forget, or False to wait for delivery confirmation."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["sender_agent_id", "message"],
                    "properties": {
                        "sender_agent_id": {
                            "type": "string",
                            "description": "ID of the agent sending the message."
                        },
                        "recipient_agent_id": {
                            "type": "string",
                            "description": "ID of the recipient agent. Either this or recipient_agent_name is required."
                        },
                        "recipient_agent_name": {
                            "type": "string",
                            "description": "Name of the recipient agent. Either this or recipient_agent_id is required."
                        },
                        "chat_id": {
                            "type": "string",
                            "description": "Existing chat ID. If not provided, a new chat will be created."
                        },
                        "message": {
                            "type": "string",
                            "description": "The message text to send."
                        },
                        "message_type": {
                            "type": "string",
                            "enum": ["text", "form", "notification"],
                            "description": "Type of message. Default: text."
                        },
                        "attachments": {
                            "type": "array",
                            "description": "File attachments to include with the message."
                        },
                        "async_send": {
                            "type": "boolean",
                            "description": "If True (default), send asynchronously. If False, wait for delivery."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_list_chat_agents_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add list_chat_agents tool schema to the tool schemas list."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="list_chat_agents",
        description=(
            "<category>Communication</category><sub-category>Chat</sub-category>"
            "List all available agents that can receive chat messages. "
            "Use this to discover which agents are available for communication."
        ),
        inputSchema={
            "type": "object",
            "required": [],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "exclude_self": {
                            "type": "string",
                            "description": "Agent ID to exclude from the list (typically the calling agent)."
                        },
                        "filter_name": {
                            "type": "string",
                            "description": "Filter agents by name (partial match, case-insensitive)."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_get_chat_history_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add get_chat_history tool schema to the tool schemas list."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="get_chat_history",
        description=(
            "<category>Communication</category><sub-category>Chat</sub-category>"
            "Get the message history for a chat conversation. "
            "Useful for reviewing past interactions or providing context."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["chat_id"],
                    "properties": {
                        "chat_id": {
                            "type": "string",
                            "description": "The chat ID to get history for."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of messages to return. Default: 50."
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Offset for pagination. Default: 0."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


# ==================== Async Wrappers for Server ====================

async def async_send_chat(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for send_chat tool."""
    try:
        input_config = args.get('input', {})
        result = send_chat(mainwin, input_config)
        
        if result.get("success"):
            msg = (
                f"✅ Message sent successfully to {result.get('recipient_name', 'recipient')}\n"
                f"Chat ID: {result.get('chat_id')}\n"
                f"Message ID: {result.get('message_id')}"
            )
        else:
            msg = f"❌ Failed to send message: {result.get('error', 'Unknown error')}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"send_chat_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncSendChat")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_list_chat_agents(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for list_chat_agents tool."""
    try:
        input_config = args.get('input', {})
        result = list_chat_agents(mainwin, input_config)
        
        if result.get("success"):
            agents = result.get("agents", [])
            if agents:
                agent_lines = [
                    f"- {a['name']} (ID: {a['id']}, tasks: {', '.join(a.get('tasks', [])) or 'none'})"
                    for a in agents
                ]
                msg = f"📋 Available agents ({result.get('count', 0)}):\n" + "\n".join(agent_lines)
            else:
                msg = "📋 No agents available for chat."
        else:
            msg = f"❌ Failed to list agents: {result.get('error', 'Unknown error')}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"list_chat_agents_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncListChatAgents")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_get_chat_history(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for get_chat_history tool."""
    try:
        input_config = args.get('input', {})
        result = get_chat_history(mainwin, input_config)
        
        if result.get("success"):
            messages = result.get("messages", [])
            msg = (
                f"📜 Chat history for {result.get('chat_id')}\n"
                f"Showing {result.get('count', 0)} of {result.get('total_count', 0)} messages"
            )
            if messages:
                # Show last few messages as preview
                preview_count = min(5, len(messages))
                msg += f"\n\nLast {preview_count} messages:"
                for m in messages[-preview_count:]:
                    sender = m.get("senderName", m.get("senderId", "Unknown"))
                    content = m.get("content", {})
                    text = content.get("text", str(content))[:100]
                    msg += f"\n- [{sender}]: {text}"
        else:
            msg = f"❌ Failed to get chat history: {result.get('error', 'Unknown error')}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"get_chat_history_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncGetChatHistory")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]
