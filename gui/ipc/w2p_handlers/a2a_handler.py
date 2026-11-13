"""IPC from the chat panel to the cloud A2A gateway (agent/a2a/gateway.py)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


@IPCHandlerRegistry.handler('a2a.skill_saved')
def handle_skill_saved(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """A skill the cloud Manager had built was saved here: tell the Manager (skill_saved event).
    params: {skill_id, skill_name, store_id?, thread_id?}"""
    p = params or {}
    skill_id, skill_name = str(p.get("skill_id") or ""), str(p.get("skill_name") or "")
    if not skill_id or not skill_name:
        return create_error_response(request, 'INVALID_PARAMS', 'skill_id and skill_name are required')
    from agent.a2a.gateway import skill_saved
    sent = skill_saved(skill_id, skill_name, str(p.get("store_id") or ""), str(p.get("thread_id") or ""))
    logger.info(f"[a2a] skill_saved {skill_name} ({skill_id}) store={p.get('store_id')} sent={sent}")
    return create_success_response(request, {"sent": sent})
