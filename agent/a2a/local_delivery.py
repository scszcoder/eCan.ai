"""In-process A2A delivery: a chat sent to an agent running in THIS process
skips the HTTP round-trip (serialize -> POST -> recipient's A2A server ->
deserialize) and goes straight to the recipient's runner, through the same call
the A2A server makes (``A2ATaskExecutor.execute`` ->
``runner.sync_task_wait_in_line``).

The request handed to the runner has the same shape as the one the server
builds: fresh task/session ids (the server generates them -- the sender's
trace ids never reach the runner over HTTP either), ``metadata = {"params":
..., "async_response": True}``, the server's accepted output modes.

Only chat sends (async: the reply comes back as its own send), only to an
agent that is registered here AND running here -- an agent object whose store
runs on another machine is gated out locally and must still be reached over
the network.  Anything else, or any error, returns None and the caller uses
HTTP; a message is never dropped.  Kill switch: ``ECAN_A2A_LOCAL_FASTPATH=0``.
Log grep: ``[a2a_local]``.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Optional

from utils.logger_helper import logger_helper as logger


def enabled() -> bool:
    return os.environ.get("ECAN_A2A_LOCAL_FASTPATH", "1") != "0"


def local_runner_for(recipient: Any):
    """The recipient's runner if it is a running agent of this process, else None."""
    if recipient is None or not getattr(recipient, "_running", False):
        return None
    try:
        from agent.agent_service import get_agent_by_id
        rid = getattr(recipient.get_card(), "id", None)
        if not rid or get_agent_by_id(rid) is not recipient:
            return None
    except Exception:
        return None
    runner = getattr(recipient, "runner", None)
    return runner if runner is not None and hasattr(runner, "sync_task_wait_in_line") else None


def deliver_chat(recipient: Any, recipient_name: str, mtype: str, chat_msg: Any,
                 params: dict) -> Optional[dict]:
    """Deliver a chat in-process. Returns a JSON-RPC-like result, or None (use HTTP)."""
    if not enabled() or "send_chat" not in str(mtype or ""):
        return None
    runner = local_runner_for(recipient)
    if runner is None:
        return None
    try:
        from agent.a2a.langgraph_agent.a2a_task_executor import SUPPORTED_CONTENT_TYPES
        task_id, session_id = str(uuid.uuid4()), str(uuid.uuid4())
        request = {
            "id": task_id,
            "params": {
                "id": task_id,
                "sessionId": session_id,
                "message": chat_msg.model_dump() if hasattr(chat_msg, "model_dump") else chat_msg,
                "metadata": {"params": params, "async_response": True},
                "acceptedOutputModes": SUPPORTED_CONTENT_TYPES,
                "pushNotification": None,
                "historyLength": None,
            },
        }
        evt = "dev_human_chat" if mtype == "dev_send_chat" else "chat_message"
        logger.info(f"[a2a_local] in-process -> {recipient_name} (no HTTP) evt={evt} task={task_id}")
        runner.sync_task_wait_in_line(evt, request, async_response=True)
        return {"jsonrpc": "2.0", "result": {"id": task_id, "contextId": session_id, "kind": "task",
                                             "status": {"state": "submitted"}},
                "local_fastpath": True, "recipient": recipient_name}
    except Exception as exc:
        logger.warning(f"[a2a_local] in-process delivery to {recipient_name} failed -> HTTP: {exc}")
        return None
