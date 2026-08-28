"""Feige chat external hook bundle.

See ``hook.yaml`` for the runtime manifest, ``feige_hooks.py`` for the
hook implementations, and ``dom_assets.py`` for the DOM selectors / JS
snippets / verification helpers relocated out of ``build_node.py``.

Phase 5A (2026-04-24): ``front_desk.py`` now owns the PreDispatch
fast-path wrapper and registers itself with ``build_node`` as a
before-browser-use-run hook on package import.
"""

# Register the front-desk PreDispatch hook with build_node.  Guarded
# so re-importing this package (which can happen under some test / hot
# reload paths) doesn't double-register the hook.
_FD_HOOK_REGISTERED = globals().get("_FD_HOOK_REGISTERED", False)
if not _FD_HOOK_REGISTERED:
    from . import front_desk as _front_desk
    _front_desk.register()
    _FD_HOOK_REGISTERED = True

# Register the actionable-items prompt-build hook (Phase 7, 2026-04-24).
# Owns the front-desk pattern's filter + protocol-override + agent_list
# injection + auto-dispatch short-circuit, previously inline in
# ``build_node._run_browser_use``.
_AI_HOOK_REGISTERED = globals().get("_AI_HOOK_REGISTERED", False)
if not _AI_HOOK_REGISTERED:
    from . import actionable_items as _actionable_items
    _actionable_items.register()
    _AI_HOOK_REGISTERED = True

# Register the live-chat placeholder handler (mt051C, 2026-05-28).
# Owns the direct-delivery placeholder typing coroutine that runner.py
# used to inline as ``_enqueue_direct_placeholder``'s closure.  Runner
# now fires ``Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED`` via
# ``live_chat_dispatch``; this registration plugs Feige in.
_DD_HOOK_REGISTERED = globals().get("_DD_HOOK_REGISTERED", False)
if not _DD_HOOK_REGISTERED:
    from . import direct_delivery as _direct_delivery
    _direct_delivery.register()
    _DD_HOOK_REGISTERED = True

# Register the in-process A2A local-delivery hot-path (ws062).  Keeps the
# direct-to-runner-queue optimization in the Feige layer; the A2A core
# (ec_agent) only exposes a neutral register_a2a_local_delivery_hook point.
# Gated by ECAN_A2A_LOCAL_FASTPATH=1 inside the hook (default OFF).
_A2A_LOCAL_HOOK_REGISTERED = globals().get("_A2A_LOCAL_HOOK_REGISTERED", False)
if not _A2A_LOCAL_HOOK_REGISTERED:
    from . import a2a_local_delivery as _a2a_local_delivery
    _a2a_local_delivery.register()
    _A2A_LOCAL_HOOK_REGISTERED = True

# Register the runner bridge (2026-08-01).  The generic task runner
# resolves ALL its site-specific live-chat capabilities (trace ledger,
# delivery durability, tab pool, typing lock, DOM helpers, tunables,
# ...) through this one object via
# ``live_chat_dispatch.runner_bridge()`` — ``ec_tasks/runner.py`` no
# longer imports any feige_chat module directly.
_RUNNER_BRIDGE_REGISTERED = globals().get("_RUNNER_BRIDGE_REGISTERED", False)
if not _RUNNER_BRIDGE_REGISTERED:
    from . import runner_bridge as _runner_bridge
    _runner_bridge.register()
    _RUNNER_BRIDGE_REGISTERED = True

# Startup delivery-durability scan (2026-08-01, moved here from main.py).
# When the PREVIOUS process died unexpectedly, the platform startup stamps
# a neutral pid-marked signal (ECAN_PREV_BOUNDARY_UNEXPECTED_PID); this
# bundle then terminally aborts any pending delivery records that process
# left behind.  The bundle auto-loads at process start via
# ``build_node._discover_external_hook_bundles``, so timing is equivalent
# to the old main.py call site.  Guarded like the registrations above so
# re-import never double-runs the scan.
_DURABILITY_STARTUP_SCAN_DONE = globals().get("_DURABILITY_STARTUP_SCAN_DONE", False)
if not _DURABILITY_STARTUP_SCAN_DONE:
    _DURABILITY_STARTUP_SCAN_DONE = True
    try:
        import os as _dur_os
        if _dur_os.environ.get("ECAN_PREV_BOUNDARY_UNEXPECTED_PID") == str(_dur_os.getpid()):
            from .delivery_durability import abort_pending_from_previous_process as _dur_abort
            _dur_abort()
    except Exception as _dur_err:
        import logging as _dur_logging
        __import__("utils.logger_helper", fromlist=["logger_helper"]).logger_helper.warning(
            f"[FEIGE-DURABILITY] startup abort scan failed: {_dur_err}"
        )

# Register the Feige site tools (round 2, 2026-08-02).  The four
# browser-use controller actions (feige_list_sessions / feige_open_session
# / feige_get_chat_thread / feige_send_message) and the off-DOM WS send
# helper moved out of the platform's extension_tools_service into
# ``site_tools.py``; importing the module registers the actions on the
# shared custom_controller via its decorators, exactly as early as before
# (this bundle auto-loads at process start).
_SITE_TOOLS_REGISTERED = globals().get("_SITE_TOOLS_REGISTERED", False)
if not _SITE_TOOLS_REGISTERED:
    from . import site_tools as _site_tools  # noqa: F401
    _SITE_TOOLS_REGISTERED = True
