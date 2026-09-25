"""Which live-chat platform this machine serves (Settings switch).

Stored as ``ECAN_LIVE_CHAT_SITE`` in <appdata>/run.env, read at startup before
the site bundles register -- so a change applies after a restart. Empty =
飞鸽 (the default, exactly as before this setting existed).
"""

import os
from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger

KEY = "ECAN_LIVE_CHAT_SITE"
SITES = {
    "": {"zh": "飞鸽 (抖店)", "en": "Feige (Douyin)"},
    "pdd_chat": {"zh": "拼多多", "en": "Pinduoduo"},
}


def _state() -> Dict[str, Any]:
    from utils.run_env import read_value
    saved = read_value(KEY) or ""
    running = os.environ.get(KEY, "") or ""
    return {
        "site": saved,
        "running_site": running,
        "restart_needed": saved != running,
        "options": [{"value": k, "label_zh": v["zh"], "label_en": v["en"]} for k, v in SITES.items()],
    }


@IPCHandlerRegistry.handler('live_chat_site.get')
def handle_get(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    try:
        return create_success_response(request, _state())
    except Exception as e:
        return create_error_response(request, 'LIVE_CHAT_SITE_ERROR', str(e))


@IPCHandlerRegistry.handler('live_chat_site.set')
def handle_set(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    site = str((params or {}).get('site') or '').strip()
    if site not in SITES:
        return create_error_response(request, 'INVALID_PARAMS', f"unknown live-chat site {site!r}")
    try:
        from utils.run_env import set_value
        set_value(KEY, site or None)
        logger.info(f"[live_chat_site] set to {site or '(default: feige)'} -- applies after restart")
        return create_success_response(request, _state())
    except Exception as e:
        logger.error(f"[live_chat_site] save failed: {e}")
        return create_error_response(request, 'LIVE_CHAT_SITE_ERROR', str(e))
