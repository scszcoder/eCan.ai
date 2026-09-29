"""IPC handlers for media generation (skill-editor media-gen node)."""

from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_success_response
from utils.logger_helper import logger_helper as logger


@IPCHandlerRegistry.handler('media.list_models')
def handle_list_media_models(request: IPCRequest, params: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Models the ecanai llm-proxy serves, from GET /models (cached per process):
    ``{"models": [{"id", "capabilities"}]}``. Proxy unreachable / not configured
    -> an empty list (the editor then uses its built-in suggestions)."""
    models = []
    try:
        from agent.ec_skills.media.proxy_media_client import ProxyMediaClient
        client = ProxyMediaClient.from_ecanai()
        try:
            caps = client.get_model_capabilities()
        finally:
            client.close()
        models = [{"id": model_id, "capabilities": c} for model_id, c in caps.items()]
    except Exception as e:
        logger.warning(f"[media.list_models] model list unavailable: {type(e).__name__}: {e}")
    return create_success_response(request, {"models": models})
