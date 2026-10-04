"""千牛 (Taobao/Tmall AliWorkbench) native-desktop customer-chat bundle.

Native Win32 client — no browser/CDP. Receive + attribution come from a
read-only process-memory scan (mem_locator over utils/win_process_memory);
select-verify + send come from OCR + desktop input (agent/mcp/server/qianniu).
See docs/QIANNIU_PLUGIN_PLAN.md.

Enabled only when ``ECAN_LIVE_CHAT_SITE`` names ``qianniu_chat`` — same gate as
pdd_chat, so unset installs are unaffected. Registers the runner bridge and
starts the read-only memory observer. The qianniu_* MCP tools register with the
MCP server independently (agent/mcp/server/server.py), not here.
"""

_REGISTERED = False


def _enabled() -> bool:
    try:
        from agent.ec_skills import live_chat_dispatch
        return live_chat_dispatch.site_enabled("qianniu_chat")
    except Exception:
        return False


def register() -> bool:
    """Register the runner bridge and start the memory observer. Idempotent;
    False when not enabled."""
    global _REGISTERED
    if _REGISTERED or not _enabled():
        return False
    from . import runner_bridge, observer
    runner_bridge.register()
    if observer.observer_enabled():
        observer.get_observer().start()
    _REGISTERED = True
    try:
        from utils.logger_helper import logger_helper as logger
        logger.info("[qianniu_chat] 千牛 live-chat bundle registered")
    except Exception:
        pass
    return True


try:
    register()
except Exception as _exc:  # a broken optional bundle must never stop the app
    try:
        from utils.logger_helper import logger_helper as logger
        logger.warning(f"[qianniu_chat] not registered: {_exc}")
    except Exception:
        pass
