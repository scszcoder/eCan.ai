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

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import mcp.types as types
from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger, get_traceback


def _feige_ledger_send_chat(stage: str, message_text: Any, **fields: Any) -> None:
    """Best-effort structured logging for Feige customer-chat payloads."""
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.trace_ledger import (
            log_payload,
            parse_jsonish_dict,
        )

        payload = parse_jsonish_dict(message_text)
        if not payload:
            return
        has_customer = bool(
            payload.get("customer_id")
            or payload.get("customerId")
            or payload.get("customer_name")
            or payload.get("customerName")
            or payload.get("name")
        )
        has_feige_turn = bool(
            payload.get("latest_message")
            or payload.get("last_message")
            or payload.get("response_text")
            or payload.get("latest_message_msg_id")
            or payload.get("source_customer_msg_id")
        )
        if not (has_customer and has_feige_turn):
            return
        log_payload(stage, payload, **fields)
    except Exception:
        return


def _feige_payload_from_message_text(message_text: Any) -> Dict[str, Any]:
    try:
        if not isinstance(message_text, str) or not message_text.strip():
            return {}
        payload = json.loads(message_text)
        if not isinstance(payload, dict):
            return {}
        has_customer = bool(
            payload.get("customer_id")
            or payload.get("customerId")
            or payload.get("customer_name")
            or payload.get("customerName")
            or payload.get("name")
        )
        has_feige_turn = bool(
            payload.get("latest_message")
            or payload.get("last_message")
            or payload.get("response_text")
            or payload.get("latest_message_msg_id")
            or payload.get("source_customer_msg_id")
        )
        return payload if has_customer and has_feige_turn else {}
    except Exception:
        return {}


def _is_feige_response_payload(payload: Dict[str, Any]) -> bool:
    return bool(
        isinstance(payload, dict)
        and str(payload.get("response_text") or "").strip()
        and str(payload.get("customer_name") or payload.get("customer_id") or "").strip()
    )

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

# Per-(sender, recipient, customer, content-hash) response dedup.  Prevents
# the responder LLM from sending the *exact same* reply twice in a single
# step — without blocking the front-desk from dispatching legitimate new
# customer messages for the same customer. Key components:
#   - sender        : distinguishes different agents
#   - recipient     : front-desk→responder and responder→front-desk don't collide
#   - customer      : per-customer scoping
#   - content hash  : only an identical message text is considered a duplicate
# Window kept short (in-single-step scope) so fast typing conversations pass.
_send_chat_response_dedup: Dict[str, float] = {}
_SEND_CHAT_RESPONSE_DEDUP_S = 3  # seconds

# Per-(recipient, customer) QA-response pending lock.  Stops parallel
# over-dispatch where multiple QA workers (or the front-desk's leftover
# LLM) all produce an answer for the same customer turn and route it to
# the same typing agent, which then types each answer in sequence and
# makes later turns appear to "reply to the wrong question" (observed
# 20:48:19 → 20:49:14 cascade on customer A where 4 QAs each answered
# 怎么退换货 and the last arrived after the customer had already sent
# 发什么快递).  Set when any `response_text`-bearing payload hits
# send_chat, cleared by HOT-PATH-B after it successfully types into
# Feige.  A TTL safety cap unblocks the lock if the responder crashes
# before clearing it.
#
# TTL tuning 2026-04-22: lowered from 120s → 30s after customer C stall
# (HOT-PATH-B never ran for 客户C because the chat_message for 客户C was
# dropped between submit and pend_event resume due to graph-state bleed;
# the 120s lock then blocked 客户C's follow-up "有实物图吗？" until TTL
# expired 2 minutes later).  HOT-PATH-B typically clears the lock in
# <5 s; 30 s is ample safety margin and strictly preferable to stalling
# a customer reply for 2 minutes.  The content-hash stale-check below
# (mark_qa_response_pending) provides a second line of defence when a
# NEW customer turn arrives before the previous lock has expired.
_qa_response_pending_lock: Dict[str, Tuple[float, str]] = {}  # key → (ts, content_hash)
_QA_RESPONSE_PENDING_TTL_S = 30.0  # safety cap


def _qa_pending_key(recipient_id: str, customer_id: str) -> str:
    return f"{(recipient_id or '').strip()}|{(customer_id or '').strip()}"


def mark_qa_response_pending(
    recipient_id: str, customer_id: str, content_hash: str = ""
) -> None:
    """Record that *recipient_id* has a QA answer in flight for *customer_id*.

    ``content_hash`` (optional) is a short digest of the response_text so a
    subsequent send_chat with a *different* response can detect that the
    previous turn has logically been answered (even if HOT-PATH-B never
    cleared the lock) and replace the lock rather than deadlock.
    """
    k = _qa_pending_key(recipient_id, customer_id)
    if k.strip("|"):
        _qa_response_pending_lock[k] = (time.time(), content_hash or "")


def clear_qa_response_pending(recipient_id: str, customer_id: str) -> None:
    """Release the pending lock (called by HOT-PATH-B after typing)."""
    k = _qa_pending_key(recipient_id, customer_id)
    _qa_response_pending_lock.pop(k, None)


def _check_qa_response_pending(
    recipient_id: str,
    customer_id: str,
    incoming_content_hash: str = "",
    wait_drain_timeout_s: float = 5.0,
    wait_drain_poll_s: float = 0.1,
) -> float:
    """Return age (s) of an active pending lock, or 0.0 if none/expired.

    Same-content lock (likely a duplicate retry of the SAME reply): the
    age is returned so the caller can SKIP as a duplicate.

    Different-content lock (a NEW reply arrived for the same customer
    while a prior reply is still pending): waits for the prior turn to
    actually finish — its CDP click + bubble confirmation typically
    clears the lock in 2–4 s — instead of optimistically clearing the
    lock and racing. Two replies racing on the same Feige DOM produced
    one `input_cleared_no_bubble` (lost) and one `outgoing_bubble`
    (delivered) in the 2026-05-16 emulator run. Queuing behind the prior
    turn avoids that race. Falls back to the previous stale-replace
    behaviour only if the prior turn never clears within
    ``wait_drain_timeout_s``.
    """
    k = _qa_pending_key(recipient_id, customer_id)
    entry = _qa_response_pending_lock.get(k)
    if entry is None:
        return 0.0
    ts, stored_hash = entry
    age = time.time() - ts
    if age > _QA_RESPONSE_PENDING_TTL_S:
        _qa_response_pending_lock.pop(k, None)
        return 0.0
    if not (
        incoming_content_hash
        and stored_hash
        and incoming_content_hash != stored_hash
    ):
        # Same content (or no hash to compare) → existing behaviour.
        return age

    # Different content → queue behind the prior turn.
    wait_start = time.time()
    last_log_t = wait_start
    logger.info(
        f"[send_chat] QA-PENDING WAIT-DRAIN: prior reply still in flight "
        f"for recipient={recipient_id!r} customer={customer_id!r} "
        f"(prior_age={age:.1f}s); waiting up to {wait_drain_timeout_s:.1f}s "
        f"for it to complete before sending this one."
    )
    while True:
        current = _qa_response_pending_lock.get(k)
        # Lock cleared (HOT-PATH-B finished typing prior reply) → proceed.
        # Or the stored hash has flipped to ours (a parallel waiter already
        # marked us) → also proceed without re-marking.
        if current is None or current[1] == incoming_content_hash:
            waited = time.time() - wait_start
            logger.info(
                f"[send_chat] QA-PENDING WAIT-DRAIN: prior reply cleared "
                f"after {waited:.2f}s for recipient={recipient_id!r} "
                f"customer={customer_id!r}; proceeding with new reply."
            )
            return 0.0
        elapsed = time.time() - wait_start
        if elapsed >= wait_drain_timeout_s:
            logger.warning(
                f"[send_chat] QA-PENDING STALE-REPLACE: prior reply did "
                f"not clear in {wait_drain_timeout_s:.1f}s for "
                f"recipient={recipient_id!r} customer={customer_id!r} "
                f"(stored_hash={stored_hash} != "
                f"incoming_hash={incoming_content_hash}); force-releasing "
                f"lock and proceeding (prior turn may have crashed)."
            )
            _qa_response_pending_lock.pop(k, None)
            return 0.0
        now = time.time()
        if (now - last_log_t) > 1.0:
            logger.info(
                f"[send_chat] QA-PENDING WAIT-DRAIN: still waiting "
                f"({elapsed:.1f}s/{wait_drain_timeout_s:.1f}s) for prior "
                f"reply to clear (recipient={recipient_id!r} "
                f"customer={customer_id!r})."
            )
            last_log_t = now
        time.sleep(wait_drain_poll_s)


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
    
    # Build sender metadata - set in both metadata and top-level for compatibility
    # Some consumers look in metadata, others look in params directly
    sender_metadata = {
        "senderId": sender_agent_id,
        "senderName": sender_name,
        "receiverId": receiver_agent_id,
        "transport": "a2a",
        "senderType": "agent",
        "chatId": chat_id,
        "sender_agent_id": sender_agent_id,  # Include for child agent to identify sender
        **(metadata or {})
    }
    
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
                "sender_agent_id": sender_agent_id,  # Include for child agent to identify parent sender
                "metadata": sender_metadata,  # Include metadata for consumers that expect it
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
        _feige_ledger_send_chat(
            "send_chat_called",
            message_text,
            sender_agent_id=sender_agent_id,
            requested_recipient_agent_id=recipient_agent_id,
            requested_recipient_agent_name=recipient_agent_name,
            chat_id=chat_id,
            async_send=bool(async_send),
        )

        shutdown_feige_payload = _feige_payload_from_message_text(message_text)
        if shutdown_feige_payload:
            try:
                from agent.ec_tasks.runner import (
                    is_app_shutdown_active,
                    is_app_shutdown_drain_finalized,
                )
                shutdown_active = is_app_shutdown_active()
                shutdown_finalized = is_app_shutdown_drain_finalized()
            except Exception:
                shutdown_active = False
                shutdown_finalized = False
            shutdown_response_payload = _is_feige_response_payload(shutdown_feige_payload)
            if shutdown_active and not shutdown_response_payload:
                _feige_ledger_send_chat(
                    "delivery_aborted_shutdown",
                    message_text,
                    reason="send_chat_feige_task_suppressed_during_shutdown",
                    sender_agent_id=sender_agent_id,
                    requested_recipient_agent_id=recipient_agent_id,
                    requested_recipient_agent_name=recipient_agent_name,
                    chat_id=chat_id,
                )
                logger.warning(
                    f"[send_chat] Suppressed Feige Q&A assignment during shutdown "
                    f"sender={sender_agent_id!r} recipient={recipient_agent_id or recipient_agent_name!r}"
                )
                return {
                    "success": True,
                    "aborted": True,
                    "abort_reason": "send_chat_feige_task_suppressed_during_shutdown",
                    "chat_id": chat_id,
                    "timestamp": int(time.time() * 1000),
                }
            if shutdown_response_payload and shutdown_finalized:
                _feige_ledger_send_chat(
                    "delivery_aborted_shutdown",
                    message_text,
                    reason="send_chat_response_after_shutdown_drain",
                    sender_agent_id=sender_agent_id,
                    requested_recipient_agent_id=recipient_agent_id,
                    requested_recipient_agent_name=recipient_agent_name,
                    chat_id=chat_id,
                )
                logger.warning(
                    f"[send_chat] Suppressed Feige response after shutdown drain "
                    f"sender={sender_agent_id!r} recipient={recipient_agent_id or recipient_agent_name!r}"
                )
                return {
                    "success": True,
                    "aborted": True,
                    "abort_reason": "send_chat_response_after_shutdown_drain",
                    "chat_id": chat_id,
                    "timestamp": int(time.time() * 1000),
                }
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
        _feige_ledger_send_chat(
            "send_chat_resolved_recipient",
            message_text,
            sender_agent_id=resolved_sender_id,
            recipient_agent_id=resolved_recipient_id,
            requested_recipient_agent_id=recipient_agent_id,
            requested_recipient_agent_name=recipient_agent_name,
            chat_id=chat_id,
        )

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
                    # ── QA-response pending-lock guard ──
                    # Only applies to payloads carrying `response_text` —
                    # i.e. QA workers answering a customer turn (NOT the
                    # front-desk's assignment payloads, which carry
                    # session_id/chat_url instead).  If another answer is
                    # already in flight to this recipient for this customer,
                    # suppress so the typing agent handles exactly one reply
                    # per customer turn.
                    _sc_has_response = bool(
                        str(_msg_obj.get("response_text") or "").strip()
                    )
                    # Compute content hash up-front so the QA-pending
                    # stale-replace check can use it.  If the new
                    # response content differs from the content that
                    # acquired the existing lock, the previous turn is
                    # logically over (HOT-PATH-B may have crashed or
                    # the event was lost in graph-state bleed) and the
                    # lock is released inside _check_qa_response_pending.
                    #
                    # Hash on response_text only (the actual outbound message),
                    # NOT the whole envelope.  Envelopes carry per-turn fields
                    # (source_customer_msg_id, source_latest_message) that
                    # change every turn even when response_text is identical,
                    # which would defeat stale-replace and let retries of the
                    # same fallback reply through (trace de08120f32da0ef3 sent
                    # the same "您好，我这边暂未收到您的具体问题..." 5x).
                    # Front-desk assignment payloads carry no response_text;
                    # for those fall back to the whole envelope.
                    _sc_response_text_for_hash = str(_msg_obj.get("response_text") or "").strip()
                    _sc_content_hash = hashlib.md5(
                        (_sc_response_text_for_hash or message_text or "").encode("utf-8", errors="replace")
                    ).hexdigest()[:12]
                    if _sc_has_response:
                        _sc_pending_age = _check_qa_response_pending(
                            resolved_recipient_id,
                            _sc_cust,
                            incoming_content_hash=_sc_content_hash,
                        )
                        if _sc_pending_age > 0:
                            logger.info(
                                f"[send_chat] QA-PENDING SKIP: another answer already "
                                f"in flight to recipient={resolved_recipient_id} "
                                f"for customer '{_sc_cust}' "
                                f"(pending {_sc_pending_age:.1f}s, "
                                f"ttl={_QA_RESPONSE_PENDING_TTL_S}s). "
                                f"Suppressing duplicate from sender={resolved_sender_id}."
                            )
                            _feige_ledger_send_chat(
                                "send_chat_dedup_skip",
                                message_text,
                                sender_agent_id=resolved_sender_id,
                                recipient_agent_id=resolved_recipient_id,
                                chat_id=chat_id,
                                dedup_reason="qa_response_pending",
                                pending_age_s=_sc_pending_age,
                            )
                            return {
                                "success": True,
                                "message_id": "",
                                "chat_id": chat_id,
                                "recipient": resolved_recipient_id,
                                "timestamp": int(time.time() * 1000),
                                "dedup": True,
                                "dedup_reason": "qa_response_pending",
                                "note": (
                                    f"Another answer for customer '{_sc_cust}' is "
                                    f"already in flight to this recipient; suppressed."
                                ),
                            }
                        # No lock (or previous lock was released as stale).
                        # Acquire it with the current response's content
                        # hash so a future differing-content send can
                        # detect staleness without waiting for TTL.
                        mark_qa_response_pending(
                            resolved_recipient_id, _sc_cust, _sc_content_hash
                        )
                    _sc_dedup_key = (
                        f"{resolved_sender_id}|{resolved_recipient_id}|"
                        f"{_sc_cust}|{_sc_content_hash}"
                    )
                    _sc_now = time.time()
                    _sc_last = _send_chat_response_dedup.get(_sc_dedup_key)
                    if _sc_last is not None and (_sc_now - _sc_last) < _SEND_CHAT_RESPONSE_DEDUP_S:
                        logger.info(
                            f"[send_chat] DEDUP: skipping exact-duplicate response for "
                            f"customer '{_sc_cust}' sender={resolved_sender_id} "
                            f"recipient={resolved_recipient_id} hash={_sc_content_hash} "
                            f"(last sent {_sc_now - _sc_last:.1f}s ago, "
                            f"window={_SEND_CHAT_RESPONSE_DEDUP_S}s)"
                        )
                        _feige_ledger_send_chat(
                            "send_chat_dedup_skip",
                            message_text,
                            sender_agent_id=resolved_sender_id,
                            recipient_agent_id=resolved_recipient_id,
                            chat_id=chat_id,
                            dedup_reason="exact_duplicate_response",
                            dedup_age_s=_sc_now - _sc_last,
                            content_hash=_sc_content_hash,
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
                    _feige_ledger_send_chat(
                        "send_chat_auto_distributed",
                        message_text,
                        sender_agent_id=resolved_sender_id,
                        old_recipient_name=str(old_name or ""),
                        recipient_agent_id=resolved_recipient_id,
                        recipient_agent_name=str(new_target.get("name") or ""),
                        chat_id=chat_id,
                    )
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
        
        # Chat creation is now handled in a2a_send_chat_message_sync/a2a_send_chat_message_async
        # to avoid duplication and ensure it's done before the message is sent

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
        _feige_ledger_send_chat(
            "send_chat_a2a_send_start",
            message_text,
            sender_agent_id=resolved_sender_id,
            recipient_agent_id=resolved_recipient_id,
            chat_id=chat_id,
            message_id=msg_id,
            async_send=bool(async_send),
        )
        _durable_feige_response_payload = (
            shutdown_feige_payload
            if shutdown_feige_payload and _is_feige_response_payload(shutdown_feige_payload)
            else {}
        )
        if _durable_feige_response_payload:
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.delivery_durability import record_pending_delivery
                record_pending_delivery(
                    _durable_feige_response_payload,
                    source="send_chat_a2a_start",
                    sender_agent_id=resolved_sender_id,
                    recipient_agent_id=resolved_recipient_id,
                    requested_recipient_agent_id=recipient_agent_id,
                    requested_recipient_agent_name=recipient_agent_name,
                    chat_id=chat_id,
                    message_id=msg_id,
                    async_send=bool(async_send),
                )
            except Exception:
                pass
        
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
            _feige_ledger_send_chat(
                "send_chat_a2a_send_success",
                message_text,
                sender_agent_id=resolved_sender_id,
                recipient_agent_id=resolved_recipient_id,
                recipient_name=recipient_name,
                chat_id=chat_id,
                message_id=msg_id,
                async_send=bool(async_send),
            )
            
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
            if _durable_feige_response_payload:
                try:
                    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.delivery_durability import clear_pending_delivery
                    clear_pending_delivery(_durable_feige_response_payload)
                except Exception:
                    pass
            _feige_ledger_send_chat(
                "send_chat_a2a_send_failed",
                message_text,
                sender_agent_id=resolved_sender_id,
                recipient_agent_id=resolved_recipient_id,
                chat_id=chat_id,
                message_id=msg_id,
                error=str(send_err),
            )
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
        # Handle both dict input and JSON string input
        input_config = args.get('input', {})
        
        # If input_config is a string, try to parse it as JSON
        if isinstance(input_config, str):
            try:
                input_config = json.loads(input_config)
            except json.JSONDecodeError as e:
                return [TextContent(type="text", text=f"❌ Failed to parse input JSON: {e}")]
        
        # If input_config is still a string (JSON parse failed), try to use it as the message
        if isinstance(input_config, str):
            input_config = {"message": input_config}
        
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
