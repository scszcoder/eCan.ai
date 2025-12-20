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

import time
import uuid
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger, get_traceback


# ==================== Helper Functions ====================

def _get_agent_by_id(agent_id: str):
    """Get agent by ID from the application context."""
    try:
        from agent.agent_service import get_agent_by_id
        return get_agent_by_id(agent_id)
    except Exception as e:
        logger.error(f"[chat_tools] Failed to get agent by id: {e}")
        return None


def _get_agent_by_name(agent_name: str):
    """Get agent by name from the application context."""
    try:
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


def _get_all_agents() -> List[Dict[str, Any]]:
    """Get all available agents."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if not mainwin or not mainwin.agents:
            return []
        
        agents_info = []
        for agent in mainwin.agents:
            card = getattr(agent, 'card', None)
            if card:
                agents_info.append({
                    "id": getattr(card, 'id', ''),
                    "name": getattr(card, 'name', 'Unknown'),
                    "description": getattr(card, 'description', ''),
                    "url": getattr(card, 'url', ''),
                    "status": getattr(agent, 'status', 'unknown'),
                })
        return agents_info
    except Exception as e:
        logger.error(f"[chat_tools] Failed to get all agents: {e}")
        return []


def _build_chat_message(
    sender_agent_id: str,
    chat_id: str,
    message_text: str,
    sender_name: str = "",
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
                "i_tag": "",
                "createAt": int(time.time() * 1000),
                "senderName": sender_name,
                "status": "success",
                "role": "agent",
                "ext": "",
                "human": False,
                **(metadata or {}),
            }
        }
    }


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
        sender_agent = _get_agent_by_id(sender_agent_id)
        if not sender_agent:
            return {
                "success": False,
                "error": f"Sender agent not found: {sender_agent_id}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get recipient agent
        recipient_agent = None
        if recipient_agent_id:
            recipient_agent = _get_agent_by_id(recipient_agent_id)
        if not recipient_agent and recipient_agent_name:
            recipient_agent = _get_agent_by_name(recipient_agent_name)
        
        if not recipient_agent:
            return {
                "success": False,
                "error": f"Recipient agent not found: {recipient_agent_id or recipient_agent_name}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get sender name
        sender_name = ""
        sender_card = getattr(sender_agent, 'card', None)
        if sender_card:
            sender_name = getattr(sender_card, 'name', '')
        
        # Generate chat_id if not provided
        if not chat_id:
            chat_id = f"chat-{str(uuid.uuid4())[:8]}"
        
        # Build the message
        chat_message = _build_chat_message(
            sender_agent_id=sender_agent_id,
            chat_id=chat_id,
            message_text=message_text,
            sender_name=sender_name,
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
            - filter_name: str (optional) - Filter agents by name (partial match)
            
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
        filter_name = config.get("filter_name", "").lower()
        
        agents = _get_all_agents()
        
        # Apply filters
        if exclude_self:
            agents = [a for a in agents if a["id"] != exclude_self]
        
        if filter_name:
            agents = [a for a in agents if filter_name in a["name"].lower()]
        
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
    tool_schema = types.Tool(
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
    tool_schema = types.Tool(
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
    tool_schema = types.Tool(
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
                agent_lines = [f"- {a['name']} (ID: {a['id']})" for a in agents]
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
