"""千牛 (Taobao/Tmall AliWorkbench) native-desktop customer-chat bundle.

Native Win32 client — no browser/CDP. Receive + attribution come from a
read-only process-memory scan (mem_locator over utils/win_process_memory);
select-verify + send come from OCR + desktop input (agent/mcp/server/qianniu).
See docs/QIANNIU_PLUGIN_PLAN.md.

Enabled only when ``ECAN_LIVE_CHAT_SITE`` names ``qianniu_chat`` — same gate as
pdd_chat, so unset installs are unaffected. Phase 0 ships the de-risk
primitives only; ``register()`` wires the runner bridge + observer in Phase 1.
"""

_REGISTERED = False


def _enabled() -> bool:
    try:
        from agent.ec_skills import live_chat_dispatch
        return live_chat_dispatch.site_enabled("qianniu_chat")
    except Exception:
        return False


def register() -> bool:
    """Phase 1 will register the qianniu_* tools + runner bridge here, mirroring
    pdd_chat. Phase 0 is a no-op so the half-built bundle never self-activates."""
    global _REGISTERED
    if _REGISTERED or not _enabled():
        return False
    # TODO(phase1): from . import site_tools; from . import runner_bridge;
    #               runner_bridge.register(); start the memory observer.
    return False
