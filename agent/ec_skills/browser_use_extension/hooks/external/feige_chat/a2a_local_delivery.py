"""Feige in-process A2A local-delivery hook (ws062, was ws061 inline in ec_agent.py).

Keeps the hot-path OUT of the general A2A core: ``ec_agent.a2a_send_chat_message_sync`` exposes
a neutral ``register_a2a_local_delivery_hook`` extension point; this module registers the
Feige-specific behaviour.

When a Feige customer turn forwards front-desk -> Q&A (and the reply Q&A -> front-desk via
send_response_back), the recipient agent is co-located in THIS process, yet the send otherwise
pays a full A2A HTTP round-trip (serialize -> POST to the recipient's card URL -> A2A server ->
deserialize) before the message even reaches the recipient's runner queue. This hook short-
circuits that: it hands the chat message straight to the recipient's runner via the exact call
the inbound A2ATaskExecutor makes for a send_chat
(``runner.sync_task_wait_in_line("chat_message", request, async_response=...)``,
a2a_task_executor.py:139).

Safe to call cross-thread: the task queue is a thread-safe ``queue.Queue`` (ec_tasks/models.py)
and ``sync_task_wait_in_line`` is the synchronous entry the A2A server itself uses (its
direct-delivery sub-path self-marshals Feige CDP ops onto the browser loop). send_chat defaults
to ``async_response=True`` (the receiver enqueues + returns; the reply comes back as a SEPARATE
A2A request, itself routed through this same hook), so we only bypass that case and return None
(-> HTTP fallback in core) otherwise. Any miss or error returns None — a message is never dropped.

Gated by ``ECAN_A2A_LOCAL_FASTPATH=1`` (default OFF). Validation grep: ``[a2a_local]``.
"""
from __future__ import annotations

import logging
import os

# CN builds name the app logger "eCan.cn" (propagate=False) — a bare
# getLogger("eCan") record never reaches its handlers, silencing this
# module's entire log output in packaged CN apps (v0.9.95u incident:
# the WS reader looked dead because none of its lines could land).
from utils.logger_helper import logger_helper as logger

_REGISTERED = False


def _enabled() -> bool:
    return os.environ.get("ECAN_A2A_LOCAL_FASTPATH", "") == "1"


def local_delivery_hook(ctx: dict):
    """Core calls this before the A2A HTTP send. Return a non-None result when we delivered the
    message in-process (core then skips HTTP); return None to defer to the normal A2A HTTP path.

    ``ctx`` fields (set by ec_agent.a2a_send_chat_message_sync): sender_agent, recipient_agent,
    recipient_name, message, mtype, chat_msg, task_id, session_id.
    """
    if not _enabled():
        return None
    mtype = str(ctx.get("mtype") or "")
    if "send_chat" not in mtype:
        return None
    try:
        recipient = ctx.get("recipient_agent")
        message = ctx.get("message") or {}
        params = message.get("attributes", {}).get("params", {})

        # async_response: mirror a2a_task_executor._determine_async_response — send_chat -> True
        async_resp = ({"params": params}).get("async_response")
        if async_resp is None:
            async_resp = True
        if not async_resp:
            return None  # a sync-result-expecting send must use the HTTP path (waits for result)

        # Recipient must be a live, in-process agent (same object the local registry holds).
        from agent.agent_service import get_agent_by_id
        rid = getattr(recipient.get_card(), "id", None) if recipient is not None else None
        runner = getattr(recipient, "runner", None)
        if not (
            rid
            and get_agent_by_id(rid) is recipient
            and runner is not None
            and hasattr(runner, "sync_task_wait_in_line")
        ):
            return None

        chat_msg = ctx.get("chat_msg")
        task_id = ctx.get("task_id")
        evt = "dev_human_chat" if mtype == "dev_send_chat" else "chat_message"
        request = {
            "id": task_id,
            "params": {
                "id": task_id,
                "sessionId": ctx.get("session_id"),
                "message": chat_msg.model_dump() if hasattr(chat_msg, "model_dump") else chat_msg,
                "metadata": {"params": params, "async_response": async_resp},
                "acceptedOutputModes": ["text", "json", "image/png"],
                "pushNotification": None,
                "historyLength": None,
            },
        }
        logger.info(
            f"[a2a_local] in-process fast-path -> {ctx.get('recipient_name')} (skip HTTP); "
            f"evt={evt} async={async_resp} task={task_id} sess={ctx.get('session_id')}"
        )
        runner.sync_task_wait_in_line(evt, request, async_response=async_resp)
        return {"success": True, "local_fastpath": True, "recipient": ctx.get("recipient_name")}
    except Exception as exc:
        logger.warning(f"[a2a_local] fast-path error -> HTTP fallback: {exc}")
        return None


def register() -> None:
    """Plug the Feige local-delivery hook into the general A2A send core. Idempotent."""
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        # ws063: register via the standalone stdlib-only registry — NOT agent.ec_agent, which
        # pulls in agent.ec_tasks and dead-locks the import while this bundle loads during
        # ec_tasks/build_node init (ws062: "cannot import name 'TaskRunner'").
        from agent.a2a.local_delivery_hook import register_a2a_local_delivery_hook
        register_a2a_local_delivery_hook(local_delivery_hook)
        _REGISTERED = True
        logger.info("[a2a_local] Feige in-process local-delivery hook registered")
    except Exception as exc:
        logger.warning(f"[a2a_local] hook registration failed: {exc}")
