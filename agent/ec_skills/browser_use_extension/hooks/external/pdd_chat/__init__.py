"""Pinduoduo (拼多多) merchant customer chat bundle.

Inbound: the titan WebSocket, decoded by ``ws_protocol`` and dispatched by
``ws_observer``. Outbound: ``pdd_*`` controller actions that drive the chat
page (``dom``). Wire-level notes: git-ignored WS_PDD_PROTOCOL_SPEC.md.

Enabled only when ``ECAN_LIVE_CHAT_SITE`` names ``pdd_chat``. Registering a
second live-chat bridge unconditionally would leave calls made outside a node
run (direct delivery, chat tools) unable to choose a bridge -- breaking the
Feige bundle on installs that never asked for Pinduoduo. Imported without the
switch, this package does nothing; ``site.py`` (the probe preset) is always
available.
"""

_REGISTERED = False


def _enabled() -> bool:
    try:
        from agent.ec_skills import live_chat_dispatch
        return live_chat_dispatch.site_enabled("pdd_chat")
    except Exception:
        return False


def register() -> bool:
    """Register the tools and the runner bridge. Idempotent; False when not enabled."""
    global _REGISTERED
    if _REGISTERED:
        return True
    if not _enabled():
        return False
    from . import site_tools  # noqa: F401 -- registers the pdd_* controller actions
    from . import runner_bridge
    runner_bridge.register()
    _REGISTERED = True
    try:
        from utils.logger_helper import logger_helper as logger
        logger.info("[pdd_chat] Pinduoduo live-chat bundle registered")
    except Exception:
        pass
    return True


try:
    register()
except Exception as _exc:  # a broken optional bundle must never stop the app
    try:
        from utils.logger_helper import logger_helper as logger
        logger.warning(f"[pdd_chat] not registered: {_exc}")
    except Exception:
        pass
