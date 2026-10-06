"""Which live-chat platforms this machine serves (Settings switch).

Stored as ``ECAN_LIVE_CHAT_SITE`` (comma-separated) in <appdata>/run.env, read
at startup before the site bundles register -- so a change applies after a
restart. 飞鸽 is always on (its bundle is not gated); this switch adds the
opt-in bundles, so one process can serve 飞鸽 + 拼多多 + 千牛 together.
Empty = 飞鸽 only, exactly as before this setting existed.
"""

import os
from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger

KEY = "ECAN_LIVE_CHAT_SITE"
SITES = {
    "pdd_chat": {"zh": "拼多多", "en": "Pinduoduo"},
    "qianniu_chat": {"zh": "千牛 (天猫/淘宝)", "en": "Qianniu (Tmall/Taobao)"},
}
# Accepted when saved by an older build; 飞鸽 is on regardless.
_LEGACY_SITES = {"feige_chat"}


def _split(value: str) -> list:
    return [s.strip() for s in str(value or "").split(",") if s.strip()]


def _state() -> Dict[str, Any]:
    from utils.run_env import read_value
    saved = read_value(KEY) or ""
    running = os.environ.get(KEY, "") or ""
    return {
        "site": saved,
        "sites": [s for s in _split(saved) if s in SITES],
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
    raw = (params or {}).get('sites', (params or {}).get('site'))
    sites = [str(s).strip() for s in raw if str(s).strip()] if isinstance(raw, list) else _split(raw)
    bad = [s for s in sites if s not in SITES and s not in _LEGACY_SITES]
    if bad:
        return create_error_response(request, 'INVALID_PARAMS', f"unknown live-chat site {bad[0]!r}")
    site = ",".join(dict.fromkeys(sites))
    try:
        from utils.run_env import set_value
        set_value(KEY, site or None)
        logger.info(f"[live_chat_site] set to {site or '(default: feige)'} -- applies after restart")
        return create_success_response(request, _state())
    except Exception as e:
        logger.error(f"[live_chat_site] save failed: {e}")
        return create_error_response(request, 'LIVE_CHAT_SITE_ERROR', str(e))
